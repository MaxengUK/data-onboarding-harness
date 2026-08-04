"""The Bronze store: write once, verify on every read (CLAUDE.md §4.2).

Three layers enforce immutability (§4.2.5), and the module is shaped by the fact
that only the third one carries weight:

1. **API** — one write path. `write_partition` errors if the id exists, there is
   no `overwrite` parameter, and no function here mutates a stored partition.
2. **Filesystem** — read-only after write, best effort. A speed bump, not a wall.
   Failure is logged and the run continues.
3. **Content hash** — recorded at write, re-verified before every read. A
   mismatch raises `BronzeIntegrityError` and fails the run.
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import polars as pl

from kernel.bronze.errors import BronzeIntegrityError, PartitionExistsError
from kernel.bronze.partition import PartitionRef, default_clock, new_partition_id
from kernel.storage.base import ObjectExistsError, StoragePath

logger = logging.getLogger(__name__)

#: Object name inside a partition. A partition is one directory holding one file.
DATA_OBJECT = "data.parquet"

#: Parquet writer options, pinned (§4.2.1, P2).
#:
#: Measured on polars 1.43.2 before pinning: repeated writes of one frame are
#: byte-stable, and thread count does not affect output. But `row_group_size`
#: defaults to a value *derived from the data*, and at 400k rows the default and
#: an explicit 100_000 produce different bytes. So the risk is not that one call
#: returns two answers; it is that a derived default drifts with input shape or a
#: library release, silently, the way the exporter's line endings drifted with
#: the host OS.
#:
#: What this does and does not buy:
#: - It does **not** make Bronze verification depend on write reproducibility.
#:   `verify_partition` re-hashes stored bytes; it never re-serialises. Existing
#:   partitions survive a polars upgrade untouched.
#: - It **does** make a partition's bytes a function of its data alone, so two
#:   ingests of one extract are comparable by hash, and it makes any future
#:   Parquet *output* (where P2 applies directly) deterministic by construction.
#: - It does **not** survive a library version bump. `PartitionRef.writer`
#:   records the version so that difference is explicable rather than mysterious.
PARQUET_WRITER_OPTIONS: dict[str, object] = {
    "compression": "zstd",
    "compression_level": 3,
    "statistics": True,
    "row_group_size": 100_000,
    "data_page_size": 1024 * 1024,
}

_WRITER = f"polars-{pl.__version__}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialise(frame: pl.DataFrame) -> bytes:
    """Serialise `frame` to Parquet bytes under the pinned options.

    The single call site of `write_parquet` in the kernel. Serialising to a
    buffer rather than to a path is what lets the hash be taken over exactly the
    bytes that are then stored — "what was hashed" and "what was written" are the
    same object rather than two things asserted to be equal.
    """
    buffer = io.BytesIO()
    frame.write_parquet(buffer, **PARQUET_WRITER_OPTIONS)  # type: ignore[arg-type]
    return buffer.getvalue()


def partition_data_object(location: StoragePath, partition_id: str) -> StoragePath:
    """The data object's location inside `location` for `partition_id`."""
    return location / partition_id / DATA_OBJECT


def write_partition(
    location: StoragePath,
    frame: pl.DataFrame,
    *,
    partition_id: str | None = None,
    clock: Callable[[], datetime] = default_clock,
) -> PartitionRef:
    """Write `frame` as a new Bronze partition and return its reference.

    There is no `overwrite` parameter and there must never be one (§0). If
    `partition_id` names an existing partition this raises
    `PartitionExistsError` rather than replacing anything.

    `frame` is written as given. Bronze does not infer types, enforce a schema,
    or repair values (§4.2, 0.5.1): whatever `ingest` hands over is what is
    stored, including values no downstream stage will accept. Bronze must never
    be the thing that changed a value.
    """
    partition_id = partition_id or new_partition_id(clock)
    data = _serialise(frame)
    target = partition_data_object(location, partition_id)

    try:
        target.write_bytes(data)
    except ObjectExistsError as exc:
        raise PartitionExistsError(
            f"partition {partition_id!r} already exists at {location.uri}; "
            f"re-ingesting a source is always a new partition (§4.2.4)"
        ) from exc

    if not target.make_read_only():
        # Layer 2 only. §4.2.5: "nothing may depend on it" — so this is a log
        # line and not a failure. Some substrates have no equivalent, and
        # refusing to operate there would be the wrong call.
        logger.warning(
            "could not mark Bronze partition read-only at %s; "
            "layer 2 unavailable on this substrate, integrity still enforced "
            "by content hash (CLAUDE.md §4.2.5)",
            target.uri,
        )

    return PartitionRef(
        partition_id=partition_id,
        content_hash=_sha256(data),
        size_bytes=len(data),
        row_count=frame.height,
        created_at=clock().astimezone(UTC),
        writer=_WRITER,
    )


def verify_partition(location: StoragePath, ref: PartitionRef) -> bytes:
    """Re-hash the stored partition and check it against `ref`; return the bytes.

    §4.2.5 layer 3. Raises `BronzeIntegrityError` on mismatch. Not optional, not
    sampled, and not downgradable to a warning — every read goes through here.

    The authority for `ref.content_hash` is the run manifest (§12), *outside* the
    partition. Nothing writes the expected hash next to the data: co-locating it
    would make the check circular, since whoever edited the data could edit the
    recorded hash to match.
    """
    target = partition_data_object(location, ref.partition_id)
    data = target.read_bytes()
    actual = _sha256(data)
    if actual != ref.content_hash:
        raise BronzeIntegrityError(
            f"Bronze partition {ref.partition_id!r} at {target.uri} does not "
            f"match the hash recorded at write time "
            f"(expected {ref.content_hash}, found {actual}); "
            f"the partition has been modified since it was written"
        )
    return data


def read_partition(location: StoragePath, ref: PartitionRef) -> pl.DataFrame:
    """Read a Bronze partition, verifying its content hash first.

    Verification is unconditional: there is no parameter that skips it, because
    a read path that can skip it is a read path that will be used to skip it.
    """
    return pl.read_parquet(io.BytesIO(verify_partition(location, ref)))
