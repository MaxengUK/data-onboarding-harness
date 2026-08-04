"""Tests for the storage path abstraction (CLAUDE.md §4.2.2, §0)."""

import os
import stat
from pathlib import Path

import pytest

from kernel.storage import LocalPath, UnsupportedLocationScheme, resolve_location
from kernel.storage.base import ObjectExistsError, StoragePath


def test_local_path_round_trips_bytes(tmp_path: Path) -> None:
    location = LocalPath(tmp_path) / "partition" / "data.bin"
    location.write_bytes(b"payload")

    assert location.exists()
    assert location.read_bytes() == b"payload"


def test_write_bytes_creates_missing_containers(tmp_path: Path) -> None:
    """Container creation is folded into write, not a separate `mkdir` method.

    A `mkdir` on the interface would make the filesystem the default backend and
    every object store the exception, which §4.2.2 explicitly refuses.
    """
    location = LocalPath(tmp_path) / "a" / "b" / "c" / "data.bin"
    location.write_bytes(b"payload")

    assert location.read_bytes() == b"payload"


def test_write_bytes_refuses_to_overwrite(tmp_path: Path) -> None:
    """The refusal lives in the storage layer, not only in Bronze.

    A path abstraction whose `write_bytes` can destroy data is the wrong
    primitive to build an immutable store on, whoever is calling it.
    """
    location = LocalPath(tmp_path) / "data.bin"
    location.write_bytes(b"first")

    with pytest.raises(ObjectExistsError):
        location.write_bytes(b"second")

    assert location.read_bytes() == b"first"


def test_truediv_does_not_mutate_the_receiver(tmp_path: Path) -> None:
    base = LocalPath(tmp_path)
    child = base / "child"

    assert child.uri != base.uri
    assert base.uri == LocalPath(tmp_path).uri


def test_make_read_only_reports_whether_it_took(tmp_path: Path) -> None:
    """Returns a bool rather than raising — §4.2.5 layer 2 is best-effort.

    This asserts the *reporting* contract, not that the bit holds: the spec says
    root overrides it and some substrates have no equivalent, so a test that
    demanded success would fail correctly-configured environments.
    """
    location = LocalPath(tmp_path) / "data.bin"
    location.write_bytes(b"payload")

    took = location.make_read_only()

    assert isinstance(took, bool)
    if took:
        assert not os.access(location.path, os.W_OK)
        location.path.chmod(stat.S_IWUSR | stat.S_IRUSR)  # so tmp_path cleans up


def test_make_read_only_on_a_missing_object_is_false_not_an_exception(
    tmp_path: Path,
) -> None:
    assert (LocalPath(tmp_path) / "absent.bin").make_read_only() is False


@pytest.mark.parametrize(
    "uri",
    ["s3://bucket/key", "s3a://bucket/key", "az://c/k", "abfss://c/k", "gs://b/k"],
)
def test_unimplemented_backends_are_refused_by_name(uri: str) -> None:
    """§4.2.2 admits these; this build cannot address them.

    The failure has to name the scheme, because an unimplemented backend and a
    typo are different problems and preflight must be able to say which one a
    client has.
    """
    with pytest.raises(UnsupportedLocationScheme) as excinfo:
        resolve_location(uri)

    assert uri.split("://", 1)[0] in str(excinfo.value)


def test_unknown_scheme_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedLocationScheme):
        resolve_location("nonsense://somewhere/else")


def test_resolves_local_paths_and_file_uris(tmp_path: Path) -> None:
    from_bare = resolve_location(str(tmp_path))
    from_uri = resolve_location(LocalPath(tmp_path).uri)

    assert isinstance(from_bare, StoragePath)
    assert Path(from_uri.uri) == Path(from_bare.uri)


def test_remote_file_host_is_refused() -> None:
    """`file://host/path` is not the local machine and must not silently become it."""
    with pytest.raises(UnsupportedLocationScheme):
        resolve_location("file://someserver/share/bronze")
