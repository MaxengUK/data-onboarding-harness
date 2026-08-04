"""Tests for the audit store (CLAUDE.md §4.2.6).

Two tests carry this file, and the rest describe intentions around them.

`test_worker_order_cannot_move_a_segment_boundary` is the acceptance criterion
for the whole design: `normalize` produces audit records concurrently, and if
segment contents depend on which worker finished first, then the same input
serialises to different bytes and §12 replay stops at canonical output instead of
covering the account of what was done. Every other property here — pure
assignment, a total sort order, sorting inside the writer rather than trusting
the caller — exists to make that test pass, and if it is ever weakened they are
all unmotivated.

`test_modified_segment_fails_on_read` is the §4.2.5 layer 3 equivalent of
`test_bronze.py`'s centre. Bronze's version proves a modified partition cannot be
processed unnoticed; this one proves the same of a modified *account* of
processing, which is the failure P8 cares about most and would otherwise be the
easiest to make quietly.

PII-shaped values are constructed at runtime (§0). Audit records carry hashes
rather than values, but the hashes are taken over realistic inputs so the
fixtures describe what the store will really hold.
"""

import hashlib
import inspect
import random
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from kernel import audit
from kernel.audit import (
    SEGMENT_ROWS,
    AuditIntegrityError,
    SegmentExistsError,
    SegmentRef,
    assign_segments,
    read_segment,
    segment_data_object,
    segment_index,
    sort_key,
    verify_segment,
    write_segment,
)
from kernel.storage import LocalPath
from kernel.storage.base import StoragePath
from schemas.audit import AuditRecord
from tests.synthetic import synthetic_local_msisdn, synthetic_person_name

RUN_ID = "run-2026-08-04-0001"
PARTITION = "20260804T093000Z-a1b2c3d4"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def record(
    row_ordinal: int,
    column_name: str = "customer_msisdn",
    rule_id: str = "tr-core.phone.msisdn_format",
    transform_name: str = "canonicalize_phone",
) -> AuditRecord:
    pre = synthetic_local_msisdn()
    return AuditRecord(
        row_ordinal=row_ordinal,
        record_key=digest(f"row-{row_ordinal}"),
        column_name=column_name,
        rule_id=rule_id,
        transform_name=transform_name,
        pre_image_hash=digest(pre),
        post_image_hash=digest(f"90{pre}"),
    )


def a_batch() -> list[AuditRecord]:
    """Records spanning a segment boundary, several columns and several rules.

    Deliberately more than one mutation per row: a single-mutation-per-row fixture
    would pass even with a partial sort key, which is the defect
    `sort_key` exists to prevent.
    """
    ordinals = [0, 1, 7, SEGMENT_ROWS - 1, SEGMENT_ROWS, SEGMENT_ROWS + 3, 2 * SEGMENT_ROWS]
    return [
        record(ordinal, column_name=column, rule_id=rule)
        for ordinal in ordinals
        for column in ("customer_msisdn", "customer_name")
        for rule in ("tr-core.phone.msisdn_format", "tr-core.name.trim")
    ]


def audit_location(tmp_path: Path) -> StoragePath:
    return LocalPath(tmp_path) / "audit"


def write_all(location: StoragePath, records: list[AuditRecord], run_id: str = RUN_ID):
    """The intended path: `assign_segments` groups and orders, the store writes."""
    return [
        write_segment(
            location,
            run_id=run_id,
            bronze_partition=PARTITION,
            index=index,
            records=bucket,
        )
        for index, bucket in assign_segments(records).items()
    ]


def write_all_unordered(location: StoragePath, records: list[AuditRecord], run_id: str = RUN_ID):
    """Group by segment but hand the records over in arrival order.

    Two layers sort — `assign_segments` and the writer — and the intended path
    exercises only the first, so a break in the second passes unnoticed if every
    test goes through `write_all`. This is the path a careless caller takes, and
    it is the one that has to hold anyway (`write_segment`'s docstring says so),
    so the central test runs both.
    """
    grouped: dict[int, list[AuditRecord]] = {}
    for record_ in records:
        grouped.setdefault(segment_index(record_.row_ordinal), []).append(record_)

    return [
        write_segment(
            location,
            run_id=run_id,
            bronze_partition=PARTITION,
            index=index,
            records=bucket,
        )
        for index, bucket in sorted(grouped.items())
    ]


def make_writable(location: StoragePath, ref: SegmentRef) -> Path:
    """Undo layer 2 so a test can attack a segment from outside its API."""
    path = segment_data_object(location, ref.run_id, ref.bronze_partition, ref.index).path
    path.chmod(stat.S_IWUSR | stat.S_IRUSR)
    return path


# --- the centre: determinism under concurrency ------------------------------


def test_worker_order_cannot_move_a_segment_boundary(tmp_path: Path) -> None:
    """Same input, deliberately different completion orders, identical bytes.

    The permutations stand in for what `normalize` will really do: workers
    finishing in an order nobody controls. Reversed and interleaved orders are
    included alongside random shuffles because a stable sort over a partial key
    can survive shuffling and still fail on a systematic reordering.
    """
    records = a_batch()
    baseline = [ref.content_hash for ref in write_all(audit_location(tmp_path / "base"), records)]

    orders = [list(reversed(records)), records[1::2] + records[0::2]]
    for seed in (1, 7, 1291):
        shuffled = records[:]
        random.Random(seed).shuffle(shuffled)
        orders.append(shuffled)

    # Both write paths, because both sort and only one of them is on the
    # intended route. Exercising `write_all` alone lets a break in the writer's
    # own sort pass unnoticed — which is exactly what happened the first time
    # this test was written.
    for writer in (write_all, write_all_unordered):
        for position, order in enumerate(orders):
            location = audit_location(tmp_path / f"{writer.__name__}-{position}")
            observed = [ref.content_hash for ref in writer(location, order)]

            assert observed == baseline, (
                f"{writer.__name__}: completion order {position} produced "
                f"different segment bytes; segment contents must be a function "
                f"of the records alone (§4.2.6)"
            )


def test_two_runs_over_identical_input_produce_identical_segments(tmp_path: Path) -> None:
    """The property gained by moving run identity onto `SegmentRef`.

    A record that stamped its own run id would make these differ, and a replay's
    audit store could then only be compared field by field rather than by bytes.
    """
    records = a_batch()

    first = write_all(audit_location(tmp_path / "first"), records, run_id="run-a-0001")
    second = write_all(audit_location(tmp_path / "second"), records, run_id="run-b-0002")

    assert [ref.content_hash for ref in first] == [ref.content_hash for ref in second]
    assert first[0].segment_id != second[0].segment_id


def test_the_writer_sorts_rather_than_trusting_its_caller(tmp_path: Path) -> None:
    """Byte-identity must not depend on the caller having been careful.

    `assign_segments` returns canonical order, so a correct caller makes this
    re-sort redundant. It is asserted anyway because `normalize` is the caller
    that will hand over records in worker order.
    """
    records = [r for r in a_batch() if segment_index(r.row_ordinal) == 0]
    location = audit_location(tmp_path)

    sorted_ref = write_segment(
        location / "sorted",
        run_id=RUN_ID,
        bronze_partition=PARTITION,
        index=0,
        records=sorted(records, key=sort_key),
    )
    jumbled_ref = write_segment(
        location / "jumbled",
        run_id=RUN_ID,
        bronze_partition=PARTITION,
        index=0,
        records=list(reversed(records)),
    )

    assert sorted_ref.content_hash == jumbled_ref.content_hash


def test_sort_key_is_total_over_the_schema() -> None:
    """Records differing in any single field must not tie.

    A tie resolves by input order, and input order is the worker order this
    design exists to eliminate — so a partial key would pass a single-threaded
    test and fail in production.
    """
    base = record(5)
    variants = [
        base.model_copy(update={"row_ordinal": 6}),
        base.model_copy(update={"column_name": "customer_name"}),
        base.model_copy(update={"rule_id": "tr-core.name.trim"}),
        base.model_copy(update={"transform_name": "trim_whitespace"}),
        base.model_copy(update={"record_key": digest("other")}),
        base.model_copy(update={"pre_image_hash": digest(synthetic_person_name())}),
        base.model_copy(update={"post_image_hash": digest("other-post")}),
    ]

    for variant in variants:
        assert sort_key(base) != sort_key(variant)


# --- §4.2.5 layer 3, via §4.2.6 ---------------------------------------------


def test_modified_segment_fails_on_read(tmp_path: Path) -> None:
    """Flip bytes on disk; the next read must fail.

    Without this, every other test in this file is a statement of intent.
    """
    location = audit_location(tmp_path)
    ref = write_all(location, a_batch())[0]

    path = make_writable(location, ref)
    tampered = bytearray(path.read_bytes())
    tampered[len(tampered) // 2] ^= 0xFF
    path.write_bytes(bytes(tampered))

    with pytest.raises(AuditIntegrityError) as excinfo:
        read_segment(location, ref)

    assert ref.segment_id in str(excinfo.value)


def test_truncated_segment_fails_on_read(tmp_path: Path) -> None:
    location = audit_location(tmp_path)
    ref = write_all(location, a_batch())[0]

    path = make_writable(location, ref)
    path.write_bytes(path.read_bytes()[:-64])

    with pytest.raises(AuditIntegrityError):
        read_segment(location, ref)


def test_verification_is_not_optional_on_any_read_path() -> None:
    for entry_point in (read_segment, verify_segment):
        params = inspect.signature(entry_point).parameters
        assert not any(
            token in name.lower()
            for name in params
            for token in ("skip", "verify", "check", "force", "trust", "unsafe")
        ), f"{entry_point.__name__} exposes a way to bypass verification"


# --- segment identity --------------------------------------------------------


def test_second_write_to_an_existing_segment_is_refused(tmp_path: Path) -> None:
    location = audit_location(tmp_path)
    buckets = assign_segments(a_batch())
    first = write_segment(
        location, run_id=RUN_ID, bronze_partition=PARTITION, index=0, records=buckets[0]
    )

    with pytest.raises(SegmentExistsError):
        write_segment(
            location, run_id=RUN_ID, bronze_partition=PARTITION, index=0, records=buckets[0]
        )

    assert verify_segment(location, first) is not None


def test_segment_boundary_falls_exactly_on_the_row_count() -> None:
    assert segment_index(0) == 0
    assert segment_index(SEGMENT_ROWS - 1) == 0
    assert segment_index(SEGMENT_ROWS) == 1
    assert segment_index(2 * SEGMENT_ROWS + 1) == 2


def test_segment_assignment_is_pure() -> None:
    """No accumulated state: interleaving calls cannot change an answer."""
    ordinals = [0, SEGMENT_ROWS, 3, 2 * SEGMENT_ROWS, SEGMENT_ROWS - 1]
    first_pass = [segment_index(o) for o in ordinals]
    _ = [segment_index(o) for o in reversed(ordinals)]

    assert [segment_index(o) for o in ordinals] == first_pass


def test_assign_segments_does_not_mutate_its_input() -> None:
    records = a_batch()
    before = list(records)

    assign_segments(records)

    assert records == before


def test_a_negative_row_ordinal_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        segment_index(-1)

    with pytest.raises(ValidationError):
        record(0).model_copy(update={"row_ordinal": -1}).model_validate(
            {"row_ordinal": -1, "record_key": "k", "column_name": "c",
             "rule_id": "r", "transform_name": "t",
             "pre_image_hash": "p", "post_image_hash": "q"}
        )


def test_records_cannot_be_written_into_a_segment_they_do_not_belong_to(
    tmp_path: Path,
) -> None:
    """Membership is checked, not assumed.

    Otherwise the pure assignment function is advisory: a mis-assigning caller
    could write a segment whose contents contradict its own name.
    """
    with pytest.raises(ValueError, match="do not belong"):
        write_segment(
            audit_location(tmp_path),
            run_id=RUN_ID,
            bronze_partition=PARTITION,
            index=3,
            records=[record(7)],
        )


def test_an_empty_segment_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        write_segment(
            audit_location(tmp_path),
            run_id=RUN_ID,
            bronze_partition=PARTITION,
            index=0,
            records=[],
        )


def test_segment_id_is_derived_from_the_run_and_the_ordinal_range() -> None:
    """Unlike a Bronze partition id, this is reproducible — and must be.

    A partition id records an arrival, which does not repeat; a segment id
    records a computation, which does. Replay has to construct the same names.
    """
    ref = SegmentRef(
        run_id=RUN_ID,
        bronze_partition=PARTITION,
        index=12,
        content_hash=digest("x"),
        size_bytes=1,
        record_count=1,
        writer="polars-1.43.2",
    )

    assert ref.segment_id == f"{RUN_ID}/{PARTITION}/000012"


def test_stored_records_are_readable_in_canonical_order(tmp_path: Path) -> None:
    location = audit_location(tmp_path)
    ref = write_all(location, a_batch())[0]

    frame = read_segment(location, ref)

    assert frame.columns == list(audit.SEGMENT_SCHEMA)
    assert frame["row_ordinal"].to_list() == sorted(frame["row_ordinal"].to_list())
    assert frame.height == ref.record_count


# --- the API surface ---------------------------------------------------------

#: Names that would indicate a mutation path into a written segment. Asserting on
#: the *surface* rather than on behaviour is the point: §4.2.5 layer 1 is a claim
#: about what the module contains.
MUTATING_TOKENS = (
    "overwrite",
    "delete",
    "remove",
    "update",
    "truncate",
    "compact",
    "drop",
    "purge",
    "rename",
    "replace",
)

FORBIDDEN_PARAMETERS = ("overwrite", "force", "replace", "if_exists", "mode")


def public_audit_callables() -> dict[str, object]:
    found: dict[str, object] = {}
    for module in (audit, audit.store, audit.segment, audit.errors):
        for name, obj in vars(module).items():
            if name.startswith("_") or not callable(obj):
                continue
            if getattr(obj, "__module__", "").startswith("kernel.audit"):
                found[name] = obj
    return found


def test_audit_store_exposes_no_mutating_operation() -> None:
    offenders = [
        name
        for name in public_audit_callables()
        for token in MUTATING_TOKENS
        if token in name.lower()
    ]

    assert not offenders, (
        f"kernel.audit exposes mutating operations {offenders}; §4.2.5 layer 1 "
        f"rests on the surface not containing them (§4.2.6)"
    )


def test_no_audit_entry_point_takes_an_overwrite_style_parameter() -> None:
    offenders = []
    for name, obj in public_audit_callables().items():
        if isinstance(obj, type):
            continue
        for parameter in inspect.signature(obj).parameters:
            if parameter.lower() in FORBIDDEN_PARAMETERS:
                offenders.append(f"{name}({parameter})")

    assert not offenders, f"forbidden parameters present: {offenders}"


def test_the_store_offers_no_listing_operation() -> None:
    """Reading by listing is not tamper-evident (§4.2.6).

    A listing reports what is present now, which is what an adversary controls: a
    deleted segment simply does not appear, and a missing segment becomes
    indistinguishable from one never written. The run manifest catches that.
    """
    offenders = [
        name
        for name, obj in public_audit_callables().items()
        # Exception classes are not operations, and their names collide by
        # accident: "AuditError" lowercased contains "iter".
        if not (isinstance(obj, type) and issubclass(obj, Exception))
        for token in ("list", "glob", "scan", "walk", "iterdir", "enumerate", "discover")
        if token in name.lower()
    ]

    assert not offenders, (
        f"kernel.audit exposes enumeration {offenders}; segments are addressed by "
        f"ids recorded in the run manifest (§12), not by asking the store"
    )


# --- the boundary ------------------------------------------------------------


def test_audit_records_stay_in_boundary_and_segment_refs_do_not() -> None:
    """The distinction §8's scope table draws, asserted rather than assumed.

    `AuditRecord` carries per-record pre-image hashes over PII-typed fields, so
    the egress gate must refuse it structurally. `SegmentRef` carries counts, ids
    and an artifact-level content hash — all §8-permitted — so marking it
    reflexively would confuse "produced by the audit store" with "reversible to a
    field value", exactly as `PartitionRef` documents.
    """
    assert AuditRecord.IN_BOUNDARY_ONLY is True
    assert getattr(SegmentRef, "IN_BOUNDARY_ONLY", False) is False


def test_no_audit_record_field_carries_a_source_value() -> None:
    """Every per-record field is a hash, an id, or a closed vocabulary name.

    A future field holding a raw pre-image value would make the store a copy of
    Bronze rather than an account of what was done to it — and would put a source
    value one careless export away from the boundary.
    """
    permitted = {
        "row_ordinal",
        "record_key",
        "column_name",
        "rule_id",
        "transform_name",
        "pre_image_hash",
        "post_image_hash",
    }

    assert set(AuditRecord.model_fields) == permitted, (
        "AuditRecord's field set changed; confirm the new field carries no source "
        "value and update §8's scope table in the same change"
    )
