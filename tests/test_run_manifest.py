"""Tests for the run manifest (CLAUDE.md §12, §4.2.5 layer 3).

Two tests carry this file.

`test_a_segment_absent_from_the_manifest_cannot_be_read` is the property the
whole module exists for. Neither store can be enumerated, so the manifest is not
a convenience index over them — it is the only thing that says which bytes a run
is entitled to read and what they should hash to. A read path that would fetch an
unnamed object is a read path that verifies nothing, and it would put the audit
store back in the position §4.2.6 was written to get it out of.

`test_the_manifest_hash_is_what_catches_a_tampered_segment` closes the other half.
The lookup could refuse unknown ids and still be worthless if the verification it
feeds were bypassed on the way through, so the manifest-mediated read is attacked
the same way `test_audit.py` attacks the direct one.

PII-shaped values are constructed at runtime (§0).
"""

import hashlib
import stat
from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from kernel.audit import (
    SEGMENT_ROWS,
    assign_segments,
    segment_data_object,
    write_segment,
)
from kernel.audit.errors import AuditIntegrityError
from kernel.bronze import BronzeIntegrityError, partition_data_object, write_partition
from kernel.gates.egress_gate import EgressPolicy, EgressViolation, validate_for_egress
from kernel.run_manifest import (
    RunManifest,
    UnknownPartitionError,
    UnknownSegmentError,
    read_audit_segment,
    read_bronze_partition,
)
from kernel.storage import LocalPath
from kernel.storage.base import StoragePath
from schemas.audit import AuditRecord
from tests.synthetic import find_valid_tckn, synthetic_local_msisdn

RUN_ID = "run-2026-08-04-0001"
PARTITION = "20260804T093000Z-a1b2c3d4"
KERNEL_VERSION = "0.5.2"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def audit_records() -> list[AuditRecord]:
    return [
        AuditRecord(
            row_ordinal=ordinal,
            record_key=digest(f"row-{ordinal}"),
            column_name="customer_msisdn",
            rule_id="tr-core.phone.msisdn_format",
            transform_name="canonicalize_phone",
            pre_image_hash=digest(synthetic_local_msisdn()),
            post_image_hash=digest(f"post-{ordinal}"),
        )
        for ordinal in (0, 4, 11)
    ]


def raw_frame() -> pl.DataFrame:
    return pl.DataFrame({"tckn": [find_valid_tckn(), None], "amount": ["1250.00", "N/A"]})


def empty_manifest(run_id: str = RUN_ID) -> RunManifest:
    return RunManifest(
        run_id=run_id, kernel_version=KERNEL_VERSION, manifest_hash=digest("manifest")
    )


def audit_location(tmp_path: Path) -> StoragePath:
    return LocalPath(tmp_path) / "audit"


def bronze_location(tmp_path: Path) -> StoragePath:
    return LocalPath(tmp_path) / "bronze"


def write_one_segment(location: StoragePath, run_id: str = RUN_ID):
    index, bucket = next(iter(assign_segments(audit_records()).items()))
    return write_segment(
        location, run_id=run_id, bronze_partition=PARTITION, index=index, records=bucket
    )


def write_two_segments(location: StoragePath, run_id: str = RUN_ID):
    """Two segments on disk, so a test can record one and ask for the other."""
    spanning = audit_records() + [
        record.model_copy(update={"row_ordinal": record.row_ordinal + SEGMENT_ROWS})
        for record in audit_records()
    ]
    return [
        write_segment(
            location, run_id=run_id, bronze_partition=PARTITION, index=index, records=bucket
        )
        for index, bucket in assign_segments(spanning).items()
    ]


def make_writable(path: Path) -> Path:
    """Undo layer 2 so a test can attack the object from outside its API."""
    path.chmod(stat.S_IWUSR | stat.S_IRUSR)
    return path


# --- the centre --------------------------------------------------------------


def test_a_written_segment_is_readable_through_the_manifest(tmp_path: Path) -> None:
    """The intended path, end to end: write, record, look up, verify, read."""
    location = audit_location(tmp_path)
    ref = write_one_segment(location)
    manifest = empty_manifest().with_audit_segments([ref])

    frame = read_audit_segment(manifest, location, ref.segment_id)

    assert frame.height == ref.record_count
    assert manifest.segment(ref.segment_id) is ref


def test_a_segment_absent_from_the_manifest_cannot_be_read(tmp_path: Path) -> None:
    """The segment exists on disk and is perfectly readable — and is refused.

    That gap is the whole point. The bytes being present says nothing about
    whether anything can attest to them, and the audit store has no second index
    to fall back on.

    The manifest deliberately names a *different* segment of the same run rather
    than being empty. An empty manifest makes almost any lenient lookup blow up
    on its own; a populated one is the case that matters, because there a lookup
    that fell back to "close enough" would return the wrong reference, the hash
    would match its own bytes, and the read would succeed silently with the wrong
    segment. That is the failure this test has to be able to see.
    """
    location = audit_location(tmp_path)
    recorded, unrecorded = write_two_segments(location)
    manifest = empty_manifest().with_audit_segments([recorded])

    on_disk = segment_data_object(
        location, unrecorded.run_id, unrecorded.bronze_partition, unrecorded.index
    )
    assert on_disk.exists()

    with pytest.raises(UnknownSegmentError) as excinfo:
        read_audit_segment(manifest, location, unrecorded.segment_id)

    assert unrecorded.segment_id in str(excinfo.value)


def test_the_manifest_hash_is_what_catches_a_tampered_segment(tmp_path: Path) -> None:
    """Lookup must not become a way around verification.

    A manifest-mediated read that skipped the hash would be strictly worse than
    the direct one: it would look like the governed path while being the
    ungoverned one.
    """
    location = audit_location(tmp_path)
    ref = write_one_segment(location)
    manifest = empty_manifest().with_audit_segments([ref])

    path = make_writable(
        segment_data_object(location, ref.run_id, ref.bronze_partition, ref.index).path
    )
    tampered = bytearray(path.read_bytes())
    tampered[len(tampered) // 2] ^= 0xFF
    path.write_bytes(bytes(tampered))

    with pytest.raises(AuditIntegrityError):
        read_audit_segment(manifest, location, ref.segment_id)


# --- Bronze, on the same terms ------------------------------------------------


def test_a_bronze_partition_absent_from_the_manifest_cannot_be_read(tmp_path: Path) -> None:
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())

    with pytest.raises(UnknownPartitionError):
        read_bronze_partition(empty_manifest(), location, ref.partition_id)


def test_a_recorded_bronze_partition_reads_and_verifies(tmp_path: Path) -> None:
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())
    manifest = empty_manifest().with_bronze_partitions([ref])

    assert read_bronze_partition(manifest, location, ref.partition_id).height == ref.row_count


def test_a_tampered_bronze_partition_fails_through_the_manifest(tmp_path: Path) -> None:
    location = bronze_location(tmp_path)
    ref = write_partition(location, raw_frame())
    manifest = empty_manifest().with_bronze_partitions([ref])

    path = make_writable(partition_data_object(location, ref.partition_id).path)
    path.write_bytes(path.read_bytes()[:-32])

    with pytest.raises(BronzeIntegrityError):
        read_bronze_partition(manifest, location, ref.partition_id)


# --- the asymmetry between the two kinds of reference -------------------------


def test_bronze_partitions_from_earlier_runs_are_legitimate(tmp_path: Path) -> None:
    """A run reads Bronze, and §4.2's read-once property depends on this.

    A partition written months ago is exactly what a rule backtest consumes, so a
    `PartitionRef` carries no run id at all and a manifest cannot be in a
    position to reject one for coming from elsewhere.
    """
    ref = write_partition(bronze_location(tmp_path), raw_frame())
    manifest = empty_manifest(run_id="run-2026-11-30-0007").with_bronze_partitions([ref])

    assert manifest.partition(ref.partition_id) is ref
    assert "run_id" not in type(ref).model_fields


def test_a_manifest_cannot_name_another_runs_audit_segments(tmp_path: Path) -> None:
    """A run writes its own audit segments and no others (§12)."""
    ref = write_one_segment(audit_location(tmp_path), run_id="run-somebody-else-0009")

    with pytest.raises(ValidationError, match="malformed manifest"):
        empty_manifest().with_audit_segments([ref])


# --- one id, one answer -------------------------------------------------------


def test_a_repeated_segment_id_is_refused(tmp_path: Path) -> None:
    """Two references to one id would leave the verifier with no rule for choosing."""
    ref = write_one_segment(audit_location(tmp_path))
    manifest = empty_manifest().with_audit_segments([ref])

    with pytest.raises(ValidationError, match="same audit segment twice"):
        manifest.with_audit_segments([ref])


def test_a_repeated_partition_id_is_refused(tmp_path: Path) -> None:
    ref = write_partition(bronze_location(tmp_path), raw_frame())
    manifest = empty_manifest().with_bronze_partitions([ref])

    with pytest.raises(ValidationError, match="same Bronze partition id twice"):
        manifest.with_bronze_partitions([ref])


def test_extending_a_manifest_leaves_the_original_untouched(tmp_path: Path) -> None:
    """The record of what a run did is not a thing the run revises in place."""
    ref = write_one_segment(audit_location(tmp_path))
    manifest = empty_manifest()

    extended = manifest.with_audit_segments([ref])

    assert manifest.audit_segments == ()
    assert extended.audit_segments == (ref,)
    assert extended is not manifest


def test_the_manifest_is_frozen() -> None:
    manifest = empty_manifest()

    with pytest.raises(ValidationError):
        manifest.run_id = "run-something-else-0002"


# --- the boundary -------------------------------------------------------------


def test_the_run_manifest_is_refused_by_the_egress_gate(tmp_path: Path) -> None:
    """Refused for not being an evidence model, not for carrying a marker.

    Every field here is §8-permitted, so the deny-by-default posture is what
    stops it rather than a declaration that it is dangerous. Marking it
    `IN_BOUNDARY_ONLY` would blur that marker's meaning — it says "reversible to
    a field value", which is true of `AuditRecord` and false of this.
    """
    ref = write_one_segment(audit_location(tmp_path))
    manifest = empty_manifest().with_audit_segments([ref])

    with pytest.raises(EgressViolation, match="not constructed by the emitter"):
        validate_for_egress(manifest, EgressPolicy(k_anonymity_min=5))

    assert getattr(RunManifest, "IN_BOUNDARY_ONLY", False) is False
