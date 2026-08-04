"""Partition identity and the reference that carries it (CLAUDE.md §4.2.4)."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, Field

#: Hex characters of randomness in a partition id. Uniqueness comes from here,
#: not from the timestamp: two batches can start inside the same second.
_SUFFIX_HEX = 8


def default_clock() -> datetime:
    return datetime.now(UTC)


def new_partition_id(clock: Callable[[], datetime] = default_clock) -> str:
    """Mint a partition id: sortable, unique, and not derived from content.

    Sortable via the UTC timestamp prefix, unique via the random suffix.

    **Not a content hash, deliberately.** §4.2.4 requires that re-ingesting
    identical data produce a *new* partition; a content-addressed id would
    collide instead, which is the opposite behaviour. The content hash is
    recorded alongside the id in `PartitionRef`, never as the id.

    **Not reproducible, deliberately.** Replay determinism comes from the id
    recorded in the run manifest (§12), not from being able to regenerate it. A
    reproducible id would have to be a function of the data, which is the
    content-addressing this rejects.
    """
    stamp = clock().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(_SUFFIX_HEX // 2)}"


class PartitionRef(BaseModel):
    """A written Bronze partition, as recorded in the run manifest (§12).

    Every field here is on the §8 evidence allowlist — counts, timestamps, and an
    **artifact-level** content hash, which §8 permits by name ("of a Bronze
    partition"). So this type deliberately does *not* carry the
    `IN_BOUNDARY_ONLY` marker that `schemas/audit.AuditRecord` does. Adding one
    reflexively would be wrong: the thing §8 denies is a hash of *field values*,
    and this is a hash of a file.

    Lives in `kernel/bronze` rather than `schemas/` because it is not a manifest,
    pack, or evidence schema. An earlier note here expected it to move into a
    run-manifest schema once §12 was implemented; it did not, and the reason is
    worth keeping. `kernel/run_manifest.py` *references* this type rather than
    owning it, because moving it would invert the dependency — the store that
    produces a reference would then depend on the record that collects it — and
    because a `PartitionRef` is meaningful on its own: it is what
    `write_partition` returns, before any manifest exists to record it.

    **Deliberately carries no run id.** A run manifest may name partitions
    written by *earlier* runs, which is what §4.2's read-once property and rule
    backtesting against historical Bronze both depend on. `SegmentRef` is the
    opposite case and does carry one, because a run writes only its own audit
    segments (§12).
    """

    model_config = {"frozen": True}

    partition_id: str
    content_hash: str = Field(description="sha256 of the stored bytes, hex")
    size_bytes: int
    row_count: int
    created_at: datetime
    writer: str = Field(
        description=(
            "Library and version that produced the bytes, e.g. 'polars-1.43.2'. "
            "Recorded because pinned writer options hold within a version but "
            "not across one: after an upgrade, the same frame may serialise to "
            "different bytes. That does not invalidate existing partitions — "
            "verification re-hashes stored bytes, it does not re-serialise — but "
            "it makes a cross-version byte difference an explicable fact rather "
            "than a mystery."
        )
    )
