"""The run manifest: the only authority for what a run read and wrote (§12).

**Why this exists as a type rather than as a log line.** §4.2.5 layer 3 is the
only one of the three immutability layers that carries weight, and it works by
comparing stored bytes against a hash recorded *elsewhere*. "Elsewhere" was
unspecified for the audit store until CLAUDE.md 0.5.2 — §12 named Bronze
partition ids and content hashes and named nothing for audit segments, so the
control §4.2.6 mandates had no record to rest on. This module is that record.

**Neither store can be enumerated, and that is the point.** There is no
`list_partitions` and no `list_segments`; both stores are addressed by known id.
A directory listing would be a weaker authority than the manifest, not a
convenient equivalent to it: a listing reports what is present *now*, which is
exactly what a tamper controls, so a deleted object simply does not appear and a
missing one becomes indistinguishable from one that was never written. The
manifest catches that; a listing cannot. The consequence is stated plainly in
§12 and enforced here — **an object absent from the run manifest is unreadable,
not merely unrecorded.**

**The two kinds of reference are not held on the same terms.**

- Bronze partitions are **read** by a run and may have been written by earlier
  runs. §4.2's read-once property depends on that, and so does backtesting a
  newly confirmed rule against historical Bronze. So a `PartitionRef` here is not
  required to carry this run's id — it has no run id at all, deliberately.
- Audit segments are **written** by the run, and a run can write no others. So
  every `SegmentRef` here must carry this manifest's `run_id`, and one that does
  not is a malformed manifest rather than a cross-run reference. That is checked,
  not assumed.

**What is not here yet.** §12's run manifest also carries resolved pack versions,
reference snapshot ids, the arming record, and the ordered list of applied
transforms. Those are absent rather than defaulted, and the distinction matters:
an `arming: ArmingRecord | None = None` would let a run emit a manifest with no
arming record and still look complete, which is the silently-permissive failure
mode this repo has already had to close once. Each lands with the stage that
produces it — arming with BUILD-PLAN item 5, pack versions with the pack loader,
applied transforms with `normalize`.

**Not an evidence artifact.** Every field here happens to be §8-permitted — run
id, kernel version, and artifact-level content hashes, which §8 names explicitly
— but that is not why it does not cross the boundary. It does not cross because
P5 says evidence is the only export, and the egress gate refuses this type on
sight for the reason it refuses any other non-`EgressModel`: it was not built by
the emitter. Marking it `IN_BOUNDARY_ONLY` would be the reflexive mistake
`PartitionRef` warns against — that marker means "reversible to a field value",
not "not exported", and diluting it weakens the structures that need it.
"""

from __future__ import annotations

from collections.abc import Iterable

import polars as pl
from pydantic import BaseModel, Field, model_validator

from kernel.audit.segment import SegmentRef
from kernel.audit.store import read_segment
from kernel.bronze.partition import PartitionRef
from kernel.bronze.store import read_partition
from kernel.storage.base import StoragePath


class RunManifestError(Exception):
    """Base for run manifest failures."""


class UnknownPartitionError(RunManifestError):
    """A Bronze partition was requested that this run manifest does not name.

    Not a lookup miss to be handled — a refusal. The manifest is the authority
    for which bytes a run is entitled to read (§12), so a partition it does not
    name is one that no recorded hash can verify. Reading it anyway would mean
    operating on an unverified partition, which is the exact outcome §4.2.5
    exists to make impossible.
    """


class UnknownSegmentError(RunManifestError):
    """An audit segment was requested that this run manifest does not name.

    Sharper than its Bronze counterpart, because the audit store has no other
    index. Bronze partition ids at least appear in Bronze's own directory
    structure; a segment reachable only by a manifest that never recorded it is
    an account of processing that nothing can attest to, and P8 is better served
    by refusing to read it than by returning it unverified.
    """


class RunManifest(BaseModel):
    """What one run read and wrote, as recorded at the end of the run (§12).

    Frozen, and extended by `with_*` methods that return new instances rather
    than by mutation. A run accumulates references as it goes — partitions at
    `ingest`, segments at `normalize` — but the record of what it did is not a
    thing it should be able to revise in place, for the same reason the stores
    it describes are not.
    """

    model_config = {"frozen": True}

    run_id: str
    kernel_version: str
    manifest_hash: str = Field(
        description="Content hash of the engagement manifest this run resolved"
    )
    bronze_partitions: tuple[PartitionRef, ...] = ()
    audit_segments: tuple[SegmentRef, ...] = ()

    @model_validator(mode="after")
    def references_are_well_formed(self) -> RunManifest:
        """Ids are unique, and every audit segment belongs to this run.

        Uniqueness first, because it is what makes "the manifest is the
        authority" a well-defined claim at all: two references sharing an id with
        different hashes leave the verifier with two answers and no rule for
        choosing, which is worse than having neither.
        """
        partition_ids = [ref.partition_id for ref in self.bronze_partitions]
        if len(set(partition_ids)) != len(partition_ids):
            raise ValueError(
                "a run manifest names the same Bronze partition id twice; the "
                "manifest is the authority for a partition's content hash (§12) "
                "and cannot hold two answers for one id"
            )

        segment_ids = [ref.segment_id for ref in self.audit_segments]
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError(
                "a run manifest names the same audit segment twice; the manifest "
                "is the authority for a segment's content hash (§12) and cannot "
                "hold two answers for one id"
            )

        foreign = sorted({ref.run_id for ref in self.audit_segments if ref.run_id != self.run_id})
        if foreign:
            raise ValueError(
                f"run manifest {self.run_id!r} names audit segments written by "
                f"runs {foreign}; a run reads Bronze but writes its own audit "
                f"segments, so a foreign segment reference is a malformed "
                f"manifest rather than a cross-run reference (§12)"
            )

        return self

    def with_bronze_partitions(self, refs: Iterable[PartitionRef]) -> RunManifest:
        """Return a new manifest naming `refs` alongside what is already here.

        Built through the constructor rather than `model_copy(update=...)`,
        which does not re-run validators — and the validator is the whole point:
        an id added twice must be refused at the moment it is added, not
        whenever someone next happens to re-parse the manifest.
        """
        return RunManifest(
            run_id=self.run_id,
            kernel_version=self.kernel_version,
            manifest_hash=self.manifest_hash,
            bronze_partitions=(*self.bronze_partitions, *refs),
            audit_segments=self.audit_segments,
        )

    def with_audit_segments(self, refs: Iterable[SegmentRef]) -> RunManifest:
        """Return a new manifest naming `refs` alongside what is already here."""
        return RunManifest(
            run_id=self.run_id,
            kernel_version=self.kernel_version,
            manifest_hash=self.manifest_hash,
            bronze_partitions=self.bronze_partitions,
            audit_segments=(*self.audit_segments, *refs),
        )

    def partition(self, partition_id: str) -> PartitionRef:
        """The recorded reference for `partition_id`, or refuse.

        This is the choke point the §4.2.5 layer 3 argument needs: the hash a
        reader verifies against comes from here, never from beside the data.
        """
        for ref in self.bronze_partitions:
            if ref.partition_id == partition_id:
                return ref

        raise UnknownPartitionError(
            f"run manifest {self.run_id!r} does not name Bronze partition "
            f"{partition_id!r}; a partition the manifest does not name has no "
            f"recorded hash to verify it against and cannot be read (§12)"
        )

    def segment(self, segment_id: str) -> SegmentRef:
        """The recorded reference for `segment_id`, or refuse."""
        for ref in self.audit_segments:
            if ref.segment_id == segment_id:
                return ref

        raise UnknownSegmentError(
            f"run manifest {self.run_id!r} does not name audit segment "
            f"{segment_id!r}; a segment the manifest does not name has no "
            f"recorded hash to verify it against and cannot be read (§12)"
        )


def read_bronze_partition(
    manifest: RunManifest, location: StoragePath, partition_id: str
) -> pl.DataFrame:
    """Read a Bronze partition named by `manifest`, verifying it first.

    The signature is the argument: there is no way to reach the bytes without
    presenting the manifest that recorded their hash.
    """
    return read_partition(location, manifest.partition(partition_id))


def read_audit_segment(
    manifest: RunManifest, location: StoragePath, segment_id: str
) -> pl.DataFrame:
    """Read an audit segment named by `manifest`, verifying it first."""
    return read_segment(location, manifest.segment(segment_id))
