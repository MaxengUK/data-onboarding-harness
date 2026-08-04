"""The audit store: closed segments, written once, verified on every read (§4.2.6).

Bronze holds what arrived; this store holds what we did to it. Neither is
derivable from the other and neither belongs inside the other — writing an
`AuditRecord` into a Bronze partition would be a post-`ingest` write to Bronze
(P10) and would leave that partition without a stable content hash.

The three layers of §4.2.5 apply here unchanged, and for the same reasons:

1. **API** — one write path. `write_segment` errors if the segment exists, there
   is no `overwrite` parameter, and no function here mutates a stored segment.
2. **Filesystem** — read-only after write, best effort. A speed bump, not a wall.
3. **Content hash** — recorded at write, re-verified before every read. A
   mismatch raises `AuditIntegrityError` and fails the run.

**Addressed by known id, never by listing.** There is no `list_segments`, and its
absence is a decision. The authority for what a run wrote is the run manifest
(§12), outside the store — the same argument that keeps the expected hash out of
the partition it describes. A directory listing tells you what is present *now*,
which is precisely what an adversary controls: a deleted segment simply does not
appear, and a missing segment becomes indistinguishable from one that was never
written. The manifest catches that; a listing cannot.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import polars as pl

from kernel.audit.errors import AuditIntegrityError, SegmentExistsError
from kernel.audit.segment import SegmentRef, segment_index, sort_key
from kernel.serialisation import (
    WRITER,
    content_hash,
    deserialise_parquet,
    serialise_parquet,
)
from kernel.storage.base import ObjectExistsError, StoragePath
from schemas.audit import AuditRecord

logger = logging.getLogger(__name__)

#: Object name inside a segment. A segment is one directory holding one file,
#: the same shape as a Bronze partition.
SEGMENT_OBJECT = "records.parquet"

#: Explicit column order and dtypes, pinned rather than inferred (P2).
#:
#: Inferring the schema from the records would make the physical layout depend on
#: the data: a segment in which every `record_key` happened to be absent would
#: infer a different column type than one in which they were present, and the two
#: would serialise differently despite describing the same kind of fact. The
#: order is `AuditRecord`'s declaration order, so the two stay legible together.
SEGMENT_SCHEMA: dict[str, pl.DataType] = {
    "row_ordinal": pl.Int64(),
    "record_key": pl.Utf8(),
    "column_name": pl.Utf8(),
    "rule_id": pl.Utf8(),
    "transform_name": pl.Utf8(),
    "pre_image_hash": pl.Utf8(),
    "post_image_hash": pl.Utf8(),
}


def segment_data_object(
    location: StoragePath, run_id: str, bronze_partition: str, index: int
) -> StoragePath:
    """The data object's location for one segment."""
    return location / run_id / bronze_partition / f"{index:06d}" / SEGMENT_OBJECT


def _to_frame(records: Sequence[AuditRecord]) -> pl.DataFrame:
    ordered = sorted(records, key=sort_key)
    return pl.DataFrame(
        [record.model_dump() for record in ordered],
        schema=SEGMENT_SCHEMA,
        orient="row",
    )


def write_segment(
    location: StoragePath,
    *,
    run_id: str,
    bronze_partition: str,
    index: int,
    records: Sequence[AuditRecord],
) -> SegmentRef:
    """Write one closed segment and return its reference.

    There is no `overwrite` parameter and there must never be one (§0). A second
    write to an existing segment raises `SegmentExistsError`.

    **Records are sorted here, not trusted to arrive sorted.** `assign_segments`
    already returns them in canonical order, so this re-sort is redundant for
    every correct caller — which is the point. The byte-identity property must
    hold for a caller that hands records over in worker completion order, because
    that is the caller `normalize` will actually be, and a property that depends
    on callers being careful is not a property.

    Membership is checked rather than assumed: every record must belong to
    `index` by `segment_index`. Without the check a mis-assigning caller could
    write a segment whose contents contradict its name, and the pure assignment
    function would be advisory rather than authoritative.
    """
    if not records:
        raise ValueError(
            f"refusing to write an empty audit segment {index} for run {run_id!r}: "
            f"a segment with no records is an object that asserts nothing"
        )

    misplaced = sorted({r.row_ordinal for r in records if segment_index(r.row_ordinal) != index})
    if misplaced:
        raise ValueError(
            f"records with row ordinals {misplaced[:5]} do not belong to segment "
            f"{index}; segment membership is a pure function of the row ordinal "
            f"(§4.2.6) and is not the caller's to decide"
        )

    data = serialise_parquet(_to_frame(records))
    target = segment_data_object(location, run_id, bronze_partition, index)

    try:
        target.write_bytes(data)
    except ObjectExistsError as exc:
        raise SegmentExistsError(
            f"audit segment {index} for run {run_id!r} on partition "
            f"{bronze_partition!r} already exists at {location.uri}; segments are "
            f"written once and never revised (§4.2.6)"
        ) from exc

    if not target.make_read_only():
        # Layer 2 only. §4.2.5: "nothing may depend on it" — so this is a log
        # line and not a failure, exactly as in Bronze.
        logger.warning(
            "could not mark audit segment read-only at %s; layer 2 unavailable "
            "on this substrate, integrity still enforced by content hash "
            "(CLAUDE.md §4.2.5, §4.2.6)",
            target.uri,
        )

    return SegmentRef(
        run_id=run_id,
        bronze_partition=bronze_partition,
        index=index,
        content_hash=content_hash(data),
        size_bytes=len(data),
        record_count=len(records),
        writer=WRITER,
    )


def verify_segment(location: StoragePath, ref: SegmentRef) -> bytes:
    """Re-hash the stored segment and check it against `ref`; return the bytes.

    §4.2.5 layer 3 by way of §4.2.6. Raises `AuditIntegrityError` on mismatch.
    Not optional, not sampled, not downgradable — every read goes through here.

    The authority for `ref.content_hash` is the run manifest (§12), *outside* the
    store. Nothing writes the expected hash next to the segment: co-locating it
    would make the check circular, since whoever edited the records could edit
    the recorded hash to match.
    """
    target = segment_data_object(location, ref.run_id, ref.bronze_partition, ref.index)
    data = target.read_bytes()
    actual = content_hash(data)
    if actual != ref.content_hash:
        raise AuditIntegrityError(
            f"audit segment {ref.segment_id!r} at {target.uri} does not match the "
            f"hash recorded at write time (expected {ref.content_hash}, found "
            f"{actual}); the account of what was done to these records has been "
            f"modified since it was written"
        )
    return data


def read_segment(location: StoragePath, ref: SegmentRef) -> pl.DataFrame:
    """Read one audit segment, verifying its content hash first.

    Verification is unconditional: there is no parameter that skips it, because a
    read path that can skip it is a read path that will be used to skip it.
    """
    return deserialise_parquet(verify_segment(location, ref))
