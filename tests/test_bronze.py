"""Tests for the Bronze store (CLAUDE.md §4.2).

The centre of this file is `test_modified_partition_fails_on_read`. §4.2.5 is
explicit that Bronze is client-owned and that modification cannot be *prevented*
— what is enforced is that modified Bronze cannot be operated on unknowingly.
Every other test here describes an intention; that one is the only one that
demonstrates the control actually works. If it is ever deleted or weakened, the
rest of this file stops meaning anything.

All PII-shaped values are constructed at runtime (§0) — see `tests/synthetic.py`.
Bronze holds raw personal data by construction, so the fixture reflects that
rather than pretending Bronze only ever sees clean columns.
"""

import inspect
import math
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl
import pytest
from pydantic import ValidationError

from kernel import bronze
from kernel.bronze import (
    PARQUET_WRITER_OPTIONS,
    BronzeIntegrityError,
    PartitionExistsError,
    PartitionRef,
    partition_data_object,
    read_partition,
    verify_partition,
    write_partition,
)
from kernel.storage import LocalPath
from kernel.storage.base import StoragePath
from tests.synthetic import (
    find_valid_tckn,
    synthetic_local_msisdn,
    synthetic_person_name,
)

#: Fixed so partition ids are reproducible where a test needs to name one.
FIXED_TIME = datetime(2026, 8, 4, 9, 30, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_TIME


def raw_frame() -> pl.DataFrame:
    """A frame shaped like something `ingest` would actually land.

    Deliberately dirty: a null, a sentinel string in a column that means to be
    numeric, and inconsistent casing. §4.2 (0.5.1) says Bronze loads input
    unmodified and uncoerced, so the fixture has to contain things Bronze must
    *not* clean up.
    """
    return pl.DataFrame(
        {
            "tckn": [find_valid_tckn(), find_valid_tckn("100000002"), None],
            "msisdn": [synthetic_local_msisdn(), "0" + synthetic_local_msisdn(), ""],
            "name": [synthetic_person_name(), synthetic_person_name().upper(), None],
            "amount": ["1250.00", "N/A", "-"],
        }
    )


def bronze_location(tmp_path: Path) -> StoragePath:
    return LocalPath(tmp_path) / "bronze"


def make_writable(location: StoragePath, ref: PartitionRef) -> Path:
    """Undo layer 2 so a test can attack the partition from outside the API.

    This is what a client with admin rights on their own disk can do, which is
    exactly the threat §4.2.5 concedes it cannot prevent.
    """
    path = partition_data_object(location, ref.partition_id).path
    path.chmod(stat.S_IWUSR | stat.S_IRUSR)
    return path


# --- 7.3 the centre -------------------------------------------------------


def test_modified_partition_fails_on_read(tmp_path: Path) -> None:
    """Flip bytes on disk; the next read must fail (§4.2.5 layer 3).

    Layer 3 is the enforcement. Without this test the other five are a statement
    of intent.
    """
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())

    path = make_writable(location, ref)
    tampered = bytearray(path.read_bytes())
    tampered[len(tampered) // 2] ^= 0xFF
    path.write_bytes(bytes(tampered))

    with pytest.raises(BronzeIntegrityError) as excinfo:
        read_partition(location, ref)

    assert ref.partition_id in str(excinfo.value)


def test_verification_is_not_optional_on_any_read_path(tmp_path: Path) -> None:
    """Neither `read_partition` nor `verify_partition` can be told to skip.

    A read path that *can* skip verification is a read path that will be used to
    skip it, so the parameter must not exist (§0: blockers are not overridable).
    """
    for entry_point in (read_partition, verify_partition):
        params = inspect.signature(entry_point).parameters
        assert not any(
            token in name.lower()
            for name in params
            for token in ("skip", "verify", "check", "force", "trust", "unsafe")
        ), f"{entry_point.__name__} exposes a way to bypass verification"


def test_truncated_partition_fails_on_read(tmp_path: Path) -> None:
    """Deletion of bytes is caught as readily as substitution of them."""
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())

    path = make_writable(location, ref)
    path.write_bytes(path.read_bytes()[:-64])

    with pytest.raises(BronzeIntegrityError):
        read_partition(location, ref)


# --- 7.1 partition identity -----------------------------------------------


def test_second_write_to_an_existing_partition_id_is_refused(tmp_path: Path) -> None:
    location = bronze_location(tmp_path)
    first = write_partition(location, raw_frame(), partition_id="batch-0001")

    with pytest.raises(PartitionExistsError):
        write_partition(location, raw_frame(), partition_id="batch-0001")

    assert verify_partition(location, first) is not None


def test_reingesting_identical_data_produces_a_new_partition(tmp_path: Path) -> None:
    """§4.2.4: identical content must not collide.

    This is why the id is not a content hash. Same frame, same second, two
    partitions — a content-addressed scheme would have refused the second write
    or silently returned the first.
    """
    location = bronze_location(tmp_path)
    frame = raw_frame()

    first = write_partition(location, frame, clock=fixed_clock)
    second = write_partition(location, frame, clock=fixed_clock)

    assert first.partition_id != second.partition_id
    assert first.content_hash == second.content_hash


def test_partition_ids_sort_chronologically(tmp_path: Path) -> None:
    earlier = bronze.new_partition_id(lambda: datetime(2026, 8, 4, 9, 0, tzinfo=UTC))
    later = bronze.new_partition_id(lambda: datetime(2026, 8, 4, 10, 0, tzinfo=UTC))

    assert earlier < later


# --- 7.2 the API surface --------------------------------------------------

#: Names that would indicate a mutation path into a written partition. The point
#: of asserting on the *surface* rather than on behaviour is that §4.2.5 layer 1
#: is a claim about what the module contains, not about what its functions do.
MUTATING_TOKENS = (
    "overwrite",
    "delete",
    "remove",
    "update",
    "append",
    "truncate",
    "compact",
    "drop",
    "purge",
    "rename",
    "replace",
)

#: Parameters that would reintroduce a mutation path through the back door.
FORBIDDEN_PARAMETERS = ("overwrite", "force", "replace", "if_exists", "mode")


def public_bronze_callables() -> dict[str, object]:
    found: dict[str, object] = {}
    for module in (bronze, bronze.store, bronze.partition, bronze.errors):
        for name, obj in vars(module).items():
            if name.startswith("_") or not callable(obj):
                continue
            if getattr(obj, "__module__", "").startswith("kernel.bronze"):
                found[name] = obj
    return found


def test_bronze_exposes_no_mutating_operation() -> None:
    """§4.2.5 layer 1, asserted by introspection.

    Same pattern as `test_egress_gate`'s check that no evidence field carries
    "hash" in its name, and for the same reason: it turns reversing a
    constitutional decision from an edit nobody notices into a red build.
    """
    offenders = [
        name
        for name in public_bronze_callables()
        for token in MUTATING_TOKENS
        if token in name.lower()
    ]

    assert not offenders, (
        f"kernel.bronze exposes mutating operations {offenders}; "
        f"§4.2.5 layer 1 rests on the surface not containing them"
    )


def test_no_bronze_entry_point_takes_an_overwrite_style_parameter() -> None:
    offenders = []
    for name, obj in public_bronze_callables().items():
        if isinstance(obj, type):
            continue
        for parameter in inspect.signature(obj).parameters:
            if parameter.lower() in FORBIDDEN_PARAMETERS:
                offenders.append(f"{name}({parameter})")

    assert not offenders, f"forbidden parameters present: {offenders}"


def test_partition_ref_is_frozen() -> None:
    """A ref whose hash can be reassigned in flight is not evidence of anything."""
    ref = PartitionRef(
        partition_id="p",
        content_hash="0" * 64,
        size_bytes=1,
        row_count=1,
        created_at=FIXED_TIME,
        writer="polars-test",
    )

    with pytest.raises(ValidationError):
        ref.content_hash = "1" * 64  # type: ignore[misc]


# --- 7.4 layer 2, without depending on it ---------------------------------


def test_written_partition_is_marked_read_only_where_the_substrate_allows(
    tmp_path: Path,
) -> None:
    """Layer 2 is a speed bump, so this test refuses to be load-bearing.

    §4.2.5: "nothing may depend on it". A test that *required* the bit to hold
    would fail on an overlay filesystem or as root — correct environments where
    layer 2 is simply unavailable — and would then be teaching us to weaken the
    assertion rather than telling us anything. So where the bit did not take, the
    test skips, and layer 3 above carries the guarantee regardless.
    """
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())
    path = partition_data_object(location, ref.partition_id).path

    if os.access(path, os.W_OK):
        pytest.skip("filesystem does not enforce read-only bits (§4.2.5 layer 2)")

    with pytest.raises(OSError), open(path, "wb") as handle:
        handle.write(b"clobbered")

    assert verify_partition(location, ref)


def test_api_refuses_regardless_of_filesystem_permissions(tmp_path: Path) -> None:
    """The API refusal stands even where layer 2 does not.

    The unconditional half of the test above: with the read-only bit cleared, the
    write path still refuses, because layer 1 never depended on layer 2.
    """
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame(), partition_id="batch-0002")
    make_writable(location, ref)

    with pytest.raises(PartitionExistsError):
        write_partition(location, raw_frame(), partition_id="batch-0002")


# --- 7.5 writer determinism -----------------------------------------------


def test_same_data_written_twice_is_byte_identical(tmp_path: Path) -> None:
    location = bronze_location(tmp_path)
    frame = raw_frame()

    first = write_partition(location, frame)
    second = write_partition(location, frame)

    assert first.content_hash == second.content_hash
    assert first.size_bytes == second.size_bytes
    assert (
        partition_data_object(location, first.partition_id).read_bytes()
        == partition_data_object(location, second.partition_id).read_bytes()
    )


def test_writer_options_are_pinned_behaviourally(tmp_path: Path) -> None:
    """The row group layout must follow the pinned size, not polars' default.

    Asserting `PARQUET_WRITER_OPTIONS["row_group_size"] == 100_000` would compare
    the constant to itself and protect nothing. This reads the layout back out of
    the produced file instead.

    It bites. Measured on polars 1.43.2: 250k rows give 3 row groups under the
    pinned size and 2 under the library default, because the default is derived
    from the data. That derived default is the drift this pinning exists to stop
    — the same failure class as the exporter writing CRLF on one host and LF on
    another.
    """
    row_group_size = PARQUET_WRITER_OPTIONS["row_group_size"]
    assert isinstance(row_group_size, int)

    rows = row_group_size * 2 + row_group_size // 2
    frame = pl.DataFrame({"v": [str(i) for i in range(rows)]})

    location = bronze_location(tmp_path)
    ref = write_partition(location, frame)
    path = partition_data_object(location, ref.partition_id).path

    observed = duckdb.sql(
        "select count(distinct row_group_id) from "
        f"parquet_metadata('{path.as_posix()}')"
    ).fetchone()[0]

    assert observed == math.ceil(rows / row_group_size)


def test_ref_records_the_writer_version(tmp_path: Path) -> None:
    """Pinning holds within a polars version, not across one — so record it."""
    ref = write_partition(bronze_location(tmp_path), raw_frame())

    assert ref.writer == f"polars-{pl.__version__}"


# --- 7.6 replay -----------------------------------------------------------


def test_reading_a_partition_twice_gives_identical_results(tmp_path: Path) -> None:
    """§12: replay reads Bronze and must reproduce byte-identical input."""
    location = bronze_location(tmp_path)
    frame = raw_frame()
    ref = write_partition(location, frame)

    first = read_partition(location, ref)
    second = read_partition(location, ref)

    assert first.equals(second)
    assert verify_partition(location, ref) == verify_partition(location, ref)


def test_round_trip_preserves_the_frame_as_given(tmp_path: Path) -> None:
    """Bronze stores what it was handed — nulls, sentinels and all (§4.2, 0.5.1).

    No type inference, no schema enforcement, no value repair: `"N/A"` in a column
    that means to be numeric comes back as `"N/A"`, and an empty string does not
    become a null.
    """
    location = bronze_location(tmp_path)
    frame = raw_frame()
    ref = write_partition(location, frame)

    restored = read_partition(location, ref)

    assert restored.equals(frame)
    assert restored.schema == frame.schema
    assert restored["amount"].to_list() == ["1250.00", "N/A", "-"]
    assert restored["msisdn"][2] == ""
    assert ref.row_count == frame.height
