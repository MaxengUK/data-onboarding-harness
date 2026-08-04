"""The kernel writes Parquet in exactly one place (CLAUDE.md §4.2.1, P2).

`test_only_one_write_parquet_call_site_exists` is the point of this file. The
pinned writer options are worth nothing if a second write path can be added that
does not use them, and the failure mode is silence: the new path works, its
output looks fine, and the divergence surfaces later as two partitions of the
same data with different hashes. A second call site should be a red build on the
commit that introduces it, not a puzzle six weeks afterwards.

Matched by AST rather than by text search, so that prose mentioning
`write_parquet` — including the docstrings explaining this rule — does not count
as a call site, and so a call cannot be hidden from the check by formatting it
across lines.
"""

import ast
from pathlib import Path

import polars as pl

from kernel.serialisation import (
    PARQUET_WRITER_OPTIONS,
    WRITER,
    content_hash,
    deserialise_parquet,
    serialise_parquet,
)

KERNEL_ROOT = Path(__file__).resolve().parents[1] / "kernel"

#: The one module allowed to call it. Named rather than counted, because "there
#: is one call site" and "the call site is the shared serialiser" are different
#: claims and only the second one is the rule.
SOLE_CALL_SITE = "serialisation.py"


def write_parquet_call_sites() -> list[str]:
    """Every `.write_parquet(...)` call in the kernel, as `path:line`."""
    found: list[str] = []
    for path in sorted(KERNEL_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_parquet"
            ):
                found.append(f"{path.relative_to(KERNEL_ROOT).as_posix()}:{node.lineno}")
    return found


def test_only_one_write_parquet_call_site_exists() -> None:
    sites = write_parquet_call_sites()

    assert len(sites) == 1, (
        f"expected exactly one write_parquet call site in the kernel, found "
        f"{sites}. A second write path bypasses PARQUET_WRITER_OPTIONS and makes "
        f"a store's bytes depend on which path wrote them (§4.2.1, P2)"
    )
    assert sites[0].startswith(SOLE_CALL_SITE), (
        f"the sole write_parquet call site is {sites[0]}, not {SOLE_CALL_SITE}; "
        f"the pinned options must not be re-homed inside one of their consumers"
    )


def test_the_call_site_passes_the_pinned_options() -> None:
    """One call site is worthless if it does not use the options.

    Asserted structurally: the call must forward `PARQUET_WRITER_OPTIONS` rather
    than spelling out arguments that happen to match today.
    """
    source = (KERNEL_ROOT / SOLE_CALL_SITE).read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_parquet"
    ]
    starred = [
        keyword
        for call in calls
        for keyword in call.keywords
        if keyword.arg is None
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "PARQUET_WRITER_OPTIONS"
    ]

    assert starred, "the write_parquet call does not forward PARQUET_WRITER_OPTIONS"


def test_serialisation_is_byte_stable() -> None:
    frame = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", None]})

    assert serialise_parquet(frame) == serialise_parquet(frame)


def test_round_trip_preserves_the_frame() -> None:
    frame = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", None]})

    assert deserialise_parquet(serialise_parquet(frame)).equals(frame)


def test_content_hash_is_a_sha256_of_the_bytes() -> None:
    import hashlib

    data = b"whatever the store is about to write"

    assert content_hash(data) == hashlib.sha256(data).hexdigest()


def test_writer_records_the_library_version() -> None:
    """Pinning holds within a polars version, not across one — so record it."""
    assert WRITER == f"polars-{pl.__version__}"


def test_row_group_size_is_pinned_not_derived() -> None:
    """The specific option the measurement found drifting (§4.2.1)."""
    assert PARQUET_WRITER_OPTIONS["row_group_size"] == 100_000
