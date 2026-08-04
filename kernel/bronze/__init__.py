"""Bronze: the immutable landing store (CLAUDE.md §4.2).

Every stage after `ingest` reads Bronze rather than the source system (P10), and
nothing modifies a partition once written. This package is the store itself: the
`ingest` stage that fills it, `profile` and the rest that read it, and the CLI
wiring are not here yet.

**The public surface is four functions, and none of them mutates anything.**
`write_partition` creates, `verify_partition` and `read_partition` check and
read, `partition_data_object` locates. There is no update, append-into, delete,
truncate, or compaction entry point, and adding one is a §0 violation rather than
a feature request — §4.2.5 layer 1 rests on the module surface simply not
containing the operation, which is a stronger statement than a flag that defaults
to off. `tests/test_bronze.py` asserts this by introspection so that reversing
the decision cannot be silent.

**Known limit — a partition is held whole in memory.** `_serialise` builds the
whole Parquet object in a buffer and `read_partition` reads it back whole. This
is not a separate scaling problem: it is where the harness's single-node ceiling
(Polars + DuckDB, §14) shows up in Bronze. A dataset that does not fit in memory
does not fit this build anywhere, and the answer when one arrives is §14's Spark
backend, not a streaming Bronze writer bolted under a single-node kernel. What
Bronze owes that day is a storage interface that can express chunked writes — the
current one cannot, deliberately (see `kernel/storage`).

**Not here, by design:** the audit store. It is a separate parallel store
(§4.2.6) and will be the second consumer of `kernel/storage`, not a second
directory inside Bronze — `AuditRecord`s are produced by `normalize`, so writing
them into Bronze would be a post-`ingest` write to Bronze (P10) and would
destroy the partition content hash that §4.2.5 layer 3 depends on.
"""

from kernel.bronze.errors import (
    BronzeError,
    BronzeIntegrityError,
    PartitionExistsError,
)
from kernel.bronze.partition import PartitionRef, new_partition_id
from kernel.bronze.store import (
    DATA_OBJECT,
    PARQUET_WRITER_OPTIONS,
    partition_data_object,
    read_partition,
    verify_partition,
    write_partition,
)

__all__ = [
    "DATA_OBJECT",
    "PARQUET_WRITER_OPTIONS",
    "BronzeError",
    "BronzeIntegrityError",
    "PartitionExistsError",
    "PartitionRef",
    "new_partition_id",
    "partition_data_object",
    "read_partition",
    "verify_partition",
    "write_partition",
]
