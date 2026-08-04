"""The audit store: what we did to what arrived (CLAUDE.md §4.2.6).

**Bronze holds what arrived; this store holds what we did to it.** That division
settles most "where does this go" questions on its own, and it is why the two
stores are parallel rather than nested: `AuditRecord`s are produced by
`normalize`, i.e. *after* `ingest`, so writing them into Bronze would be a
post-`ingest` write to Bronze (P10) and would destroy the partition content hash
that §4.2.5 layer 3 depends on.

**The second consumer of `kernel/storage`**, and the first test of whether that
abstraction was shaped around Bronze. It was not: five of its six members serve
this store unchanged, and the one Bronze-shaped assumption it carries — that a
caller always knows the name of the object it wants — turns out to be a property
worth keeping rather than a limitation worth removing. See `store.py` on why
listing a store is not a tamper-evident way to read it.

**The public surface is four functions, and none of them mutates anything.**
`write_segment` creates, `verify_segment` and `read_segment` check and read,
`segment_data_object` locates. There is no update, append-into, delete, or
compaction entry point, and adding one is a §0 violation rather than a feature
request. `tests/test_audit.py` asserts this by introspection.

**In-boundary by construction.** Segments hold per-record pre-image hashes over
PII-typed fields, so nothing here crosses the trust boundary and the egress gate
refuses `AuditRecord` structurally rather than by policy (§8 scope table).
`SegmentRef` is the deliberate exception and carries no in-boundary marker: it
holds counts, ids and an artifact-level content hash, all of which §8 permits by
name, because it describes the segment rather than reproducing its contents.

**Retention.** `audit.retention_days` ≥ `bronze.retention_days`, refused at
manifest load (`schemas/manifest.py`) and reported by preflight. An audit store
that expires first leaves the data present with no account of what was done to
it — P8 failing silently on a date nobody chose.
"""

from kernel.audit.errors import AuditError, AuditIntegrityError, SegmentExistsError
from kernel.audit.segment import (
    SEGMENT_ROWS,
    SegmentRef,
    assign_segments,
    segment_index,
    sort_key,
)
from kernel.audit.store import (
    SEGMENT_OBJECT,
    SEGMENT_SCHEMA,
    read_segment,
    segment_data_object,
    verify_segment,
    write_segment,
)

__all__ = [
    "SEGMENT_OBJECT",
    "SEGMENT_ROWS",
    "SEGMENT_SCHEMA",
    "AuditError",
    "AuditIntegrityError",
    "SegmentExistsError",
    "SegmentRef",
    "assign_segments",
    "read_segment",
    "segment_data_object",
    "segment_index",
    "sort_key",
    "verify_segment",
    "write_segment",
]
