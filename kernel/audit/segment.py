"""Segment identity and assignment — a pure function of the source row (§4.2.6).

**The question this module answers is "what is the audit store's partition?"**

§4.2.6 says a growing store has no stable content hash, and that is true — but it
is true of Bronze too. The Bronze *store* grows without limit, one partition per
batch, forever; nobody proposed hashing "Bronze", because §4.2.5 hashes a
*partition*. So the audit store does not need a new mechanism, it needs its own
unit of closure. That unit is a **segment**: written once, hashed at write, never
touched again, with its id and hash recorded in the run manifest (§12).

**What closes a segment: the source row ordinal, and nothing else.**

`normalize` produces audit records concurrently, and the tempting design is to
buffer per worker and flush when a buffer fills. That does not work, and the
reason is worth stating because it is not obvious: worker completion order varies
between runs, so buffer boundaries vary, so segment boundaries vary, so the same
input serialises to different bytes. Buffering per worker moves the
nondeterminism, it does not remove it.

So assignment is a pure function of a value the input already fixes. **Segment N
carries the audit records of source rows `[N·SEGMENT_ROWS, (N+1)·SEGMENT_ROWS)`.**
No clock, no worker identity, no accumulated state, no arrival order — given the
same records in any order whatsoever, this module produces the same segments with
the same contents. That is what makes the §12 replay guarantee extend to the
audit store rather than stopping at canonical output.

Two rejected alternatives, recorded so they are not re-proposed:

- **Time-based flushing** (every N seconds) reads the wall clock, so segment
  boundaries move between runs. P2 falls immediately.
- **Byte-size-based flushing** is a function of the *compressed* size, which is a
  function of the writer version — a polars upgrade would silently re-segment a
  store whose earlier segments were cut differently.

A count of rows has neither property: it is fixed by the input alone.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field

from schemas.audit import AuditRecord

#: Source rows per segment. Matches `PARQUET_WRITER_OPTIONS["row_group_size"]` so
#: that a full segment is exactly one row group, which keeps the physical layout
#: predictable rather than a function of how many mutations a batch happened to
#: produce.
#:
#: This bounds the writer's memory too, and that is not incidental: it is why the
#: audit store does not inherit Bronze's whole-extract memory ceiling (see
#: `kernel/bronze`). A segment is bounded by construction; a Bronze partition is
#: bounded by the size of the extract.
SEGMENT_ROWS = 100_000


def segment_index(row_ordinal: int) -> int:
    """Which segment a source row's audit records belong to. Pure.

    The whole determinism argument of this module rests on this function reading
    nothing but its argument. If it ever needs a second input — a buffer state, a
    worker id, a clock — the property has been lost, whatever the second input is.
    """
    if row_ordinal < 0:
        raise ValueError(f"row ordinal cannot be negative, got {row_ordinal}")
    return row_ordinal // SEGMENT_ROWS


def sort_key(record: AuditRecord) -> tuple[int, str, str, str, str, str, str]:
    """The total order of records within a segment.

    **Total, not merely deterministic.** A sort that leaves ties resolves them by
    input order, and input order is exactly the worker completion order this
    module exists to eliminate — so a partial key would pass a single-threaded
    test and fail in production, which is the worst available outcome.

    `(row_ordinal, rule_id, transform_name)` is not total on its own: one row, one
    rule and one transform applied to two columns ties on all three. `column_name`
    and `record_key` close that, and the two hashes close the residual case of a
    rule applied twice to one column with different pre-images. Beyond that point
    two records are equal in every field the schema carries, so their order cannot
    affect the bytes.
    """
    return (
        record.row_ordinal,
        record.column_name,
        record.rule_id,
        record.transform_name,
        record.record_key,
        record.pre_image_hash,
        record.post_image_hash,
    )


def assign_segments(records: Iterable[AuditRecord]) -> dict[int, list[AuditRecord]]:
    """Group `records` into segments, each in canonical order. Pure.

    No I/O, no clock, no mutation of the input. Feed it the same records in any
    permutation and it returns the same mapping — that assertion is
    `test_audit.py`'s central test, and it is the one that stops a future
    "optimisation" reintroducing worker-order dependence.
    """
    grouped: dict[int, list[AuditRecord]] = {}
    for record in records:
        grouped.setdefault(segment_index(record.row_ordinal), []).append(record)

    return {index: sorted(bucket, key=sort_key) for index, bucket in sorted(grouped.items())}


class SegmentRef(BaseModel):
    """A written audit segment, as recorded in the run manifest (§12).

    **Carries what is constant across the segment**, which is why `AuditRecord`
    no longer does. Every record in a segment shares one run and one Bronze
    partition, so stamping them on each record is redundancy — and worse than
    redundancy, because it makes a segment's bytes a function of the run's
    identity rather than of the records' content. With them held here, two runs
    over identical input produce byte-identical segments, and a replay can be
    diffed against the original exactly as §12 asks.

    Like `PartitionRef` and for the same reason, this type deliberately does
    **not** carry `IN_BOUNDARY_ONLY`. Every field is §8-permitted — counts, ids,
    and an *artifact-level* content hash, which §8 names explicitly. The marker
    belongs on `AuditRecord`, whose per-record pre-image hashes are what §8
    denies. Adding it here reflexively would confuse "produced by the audit
    store" with "reversible to a field value".

    Deliberately carries no timestamp. See `schemas/audit.py` on why time belongs
    to the run rather than to what the run wrote.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    run_id: str
    bronze_partition: str = Field(
        description="The Bronze partition these records were derived from (§4.2.4)"
    )
    index: int = Field(ge=0, description="Segment ordinal — rows [i·N, (i+1)·N)")
    content_hash: str = Field(description="sha256 of the stored bytes, hex")
    size_bytes: int
    record_count: int
    writer: str = Field(
        description="Library and version that produced the bytes, e.g. 'polars-1.43.2'"
    )

    @property
    def segment_id(self) -> str:
        """The store-relative address, derived rather than minted.

        Unlike a Bronze partition id, which is deliberately not reproducible
        (`kernel/bronze/partition.py`), this is a pure function of the run and the
        ordinal range. The asymmetry is not an inconsistency: a partition id
        records an *arrival*, and arrivals do not repeat; a segment id records a
        *computation*, and computations do. Replay has to be able to construct the
        same names, so the name is derived.
        """
        return f"{self.run_id}/{self.bronze_partition}/{self.index:06d}"
