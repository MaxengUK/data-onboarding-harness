"""How an immutable store turns a frame into the bytes it will hash (§4.2.1, P2).

This module exists because Bronze stopped being the only immutable store. The
audit store (§4.2.6) is subject to the same three-layer discipline as Bronze —
single write path, read-only after write, content hash verified on read — and
layer 3 only means anything if both stores agree on what "the bytes" are.

**Why the options live here and not in either store.** They were `kernel/bronze`'s
private `_serialise`, documented as "the single call site of `write_parquet` in
the kernel". A second store makes that claim false three ways round: the audit
store importing Bronze's private serialiser would make audit depend on Bronze,
which §4.2.6 spends a section denying; copying the options would let the two
drift apart silently; and leaving them in Bronze would put the kernel's shared
determinism policy inside one of its two consumers. Neither store owns the
policy, so it sits beside both.

**Not in `kernel/storage`, deliberately.** That layer is byte-level and
format-agnostic on purpose — it addresses locations and moves bytes, and it has
to stay that way for an S3 or Azure backend to be implementable without knowing
what Parquet is. Serialisation is a different concern that happens to be shared
by the same two callers.

`tests/test_serialisation.py` asserts by source inspection that `write_parquet`
is called in exactly one place in the kernel. A second write path would not be
wrong because it is duplicated; it would be wrong because it would bypass the
pinned options below, and it would do so silently.
"""

from __future__ import annotations

import hashlib
import io
import json

import polars as pl

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
#: - It does **not** make store verification depend on write reproducibility.
#:   Verification re-hashes stored bytes; it never re-serialises. Existing
#:   partitions and segments survive a polars upgrade untouched.
#: - It **does** make an object's bytes a function of its data alone, so two
#:   ingests of one extract are comparable by hash, and it makes any future
#:   Parquet *output* (where P2 applies directly) deterministic by construction.
#: - It does **not** survive a library version bump. `PartitionRef.writer` and
#:   `SegmentRef.writer` record the version so that difference is explicable
#:   rather than mysterious.
PARQUET_WRITER_OPTIONS: dict[str, object] = {
    "compression": "zstd",
    "compression_level": 3,
    "statistics": True,
    "row_group_size": 100_000,
    "data_page_size": 1024 * 1024,
}

#: Identifies the library that produced a set of bytes, recorded in every store
#: reference. Pinned options hold within a version, not across one.
WRITER = f"polars-{pl.__version__}"


def serialise_parquet(frame: pl.DataFrame) -> bytes:
    """Serialise `frame` to Parquet bytes under the pinned options.

    Serialising to a buffer rather than to a path is what lets a store hash
    exactly the bytes it then writes — "what was hashed" and "what was stored"
    are the same object rather than two things asserted to be equal.
    """
    buffer = io.BytesIO()
    frame.write_parquet(buffer, **PARQUET_WRITER_OPTIONS)  # type: ignore[arg-type]
    return buffer.getvalue()


def deserialise_parquet(data: bytes) -> pl.DataFrame:
    """Read a frame back from bytes already fetched and verified by a store."""
    return pl.read_parquet(io.BytesIO(data))


def canonical_json_bytes(payload: object) -> bytes:
    """Deterministic bytes for a JSON-able value, for hashing rather than reading.

    Sorted keys and the tightest separators, so the bytes are a function of the
    *content* and not of field declaration order, dict insertion order, or
    whichever pretty-printer last touched the value. `ensure_ascii` keeps the
    output byte-identical regardless of the host's default encoding — the same
    hazard that made the JSON Schema exporter write CRLF on one platform and LF
    on another.

    Not the same job as `schemas/export_json_schema.render_schema`, which is
    indented and read by humans. This output is hashed and never displayed.
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    """The sha256 of `data`, hex — one definition for both stores.

    Shared for the same reason as the writer options: two stores that hash
    differently cannot be reasoned about together, and the §4.2.5 layer 3 claim
    is made once about both.
    """
    return hashlib.sha256(data).hexdigest()
