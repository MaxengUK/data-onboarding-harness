"""Egress gate and Leg 1 leak test (CLAUDE.md §8, §8.1, §8.2, P5).

**Scope of the Leg 1 tests here.** §8.2 specifies Leg 1 as end to end: a
synthetic fixture seeded with PII markers is run through the pipeline and the
emitter must fail closed. There is no pipeline yet (BUILD-PLAN item 7), so these
exercise the same contract at the unit boundary: an evidence object carrying PII
is handed to the serializer, and the serializer must raise rather than return an
artifact. Producing output is the failure condition either way.

**This must be upgraded to the end-to-end form at Gate 0 close**, when
`preflight -> ingest -> Bronze -> profile -> emit` exists. The unit form cannot
catch a leak introduced by a stage that never consults the gate; only the
end-to-end form can. Do not treat the presence of these tests as Leg 1 being
satisfied.

All PII-shaped values are constructed at runtime (§0) - see tests/synthetic.py.
"""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from kernel.gates.egress_gate import (
    EgressModel,
    EgressPolicy,
    EgressViolation,
    KAnonymisedValues,
    ShapeSummary,
    ValueCount,
    validate_for_egress,
)
from kernel.registries import (
    ConfidenceBand,
    RuleState,
    SemanticType,
    StageName,
)
from schemas.audit import AuditRecord
from schemas.evidence import (
    BandCount,
    ColumnProfile,
    EvidenceArtifact,
    Metrics,
    RuleOutcome,
)
from tests.synthetic import (
    find_valid_tckn,
    synthetic_local_msisdn,
    synthetic_person_name,
)

DECLARED_COLUMNS = frozenset({"brand_code", "order_date", "customer_ref"})
DECLARED_CANONICAL = frozenset({"brand", "delivery_date"})

POLICY = EgressPolicy(
    k_anonymity_min=5,
    declared_columns=DECLARED_COLUMNS,
    declared_canonical_fields=DECLARED_CANONICAL,
)

#: Fixed so that serialization is byte-comparable across runs (P2).
FIXED_TIME = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def clean_artifact() -> EvidenceArtifact:
    """An artifact that is entirely on the §8 allowlist."""
    return EvidenceArtifact(
        run_id="run-2026-08-03-0001",
        kernel_version="0.4.1",
        manifest_hash=_digest("manifest"),
        pack_versions=["core/tr-core@1.4.0", "sector/automotive@0.3.0"],
        reference_ids=["cardata.brand_catalog"],
        generated_at=FIXED_TIME,
        stage=StageName.PROFILE,
        rule_outcomes=[
            RuleOutcome(
                rule_id="tr-core.phone.msisdn_format",
                state=RuleState.ENFORCED,
                evaluated_count=111204,
                violation_count=412,
                hold_rate=0.9963,
            )
        ],
        column_profiles=[
            ColumnProfile(
                column_name="brand_code",
                canonical_field="brand",
                semantic_type=SemanticType.BRAND,
                row_count=111204,
                null_rate=0.012,
                cardinality=8,
                top_shapes=[ShapeSummary(shape="AAAA", count=90210)],
            )
        ],
        metrics=Metrics(
            reuse_ratio=0.62,
            promotions=3,
            band_distribution=[BandCount(band=ConfidenceBand.MONEY, count=44)],
        ),
    )


# --- Leg 1: PII must fail closed ------------------------------------------------


def test_leg1_distinct_values_of_pii_type_fail_closed():
    artifact = clean_artifact()
    tckn = find_valid_tckn()
    artifact.column_profiles[0].distinct_values = KAnonymisedValues(
        semantic_type=SemanticType.TCKN,
        cardinality=1,
        values=[ValueCount(value=tckn, count=900)],
    )

    with pytest.raises(EgressViolation, match="PII-typed"):
        validate_for_egress(artifact, POLICY)


def test_no_field_level_hash_channel_exists():
    """There is deliberately no way to export a digest of a column's values.

    A field hash is reversible whenever the value space is enumerable, and for
    real field types it always is: an MSISDN space is ~10^9, a TCKN ~10^11 with
    a checksum, a date a few tens of thousands. How many distinct values the
    dataset happens to hold is a different quantity entirely, so no cardinality
    threshold can make such a hash safe. Only artifact-level digests — over a
    whole partition, manifest, or pack — are permitted.

    This asserts the absence, so that re-adding a field hash has to be a
    deliberate act that breaks a test rather than a quiet new export channel.
    """
    assert not any("hash" in name for name in ColumnProfile.model_fields)


def test_leg1_cell_value_smuggled_as_a_column_name_fails_closed():
    """A person's name in a column_name field is still a cell value."""
    artifact = clean_artifact()
    artifact.column_profiles[0].column_name = synthetic_person_name()

    with pytest.raises(EgressViolation, match="not declared in the manifest"):
        validate_for_egress(artifact, POLICY)


def test_leg1_no_artifact_is_produced_when_pii_is_present():
    """§8.2: a run that completes and produces an artifact is the failure."""
    from kernel.gates.egress_gate import serialize_evidence

    artifact = clean_artifact()
    artifact.column_profiles[0].distinct_values = KAnonymisedValues(
        semantic_type=SemanticType.PERSON_NAME,
        cardinality=1,
        values=[ValueCount(value=synthetic_person_name(), count=900)],
    )

    produced = None
    with pytest.raises(EgressViolation):
        produced = serialize_evidence(artifact, POLICY)

    assert produced is None


def test_pii_value_never_appears_in_a_successful_serialization():
    from kernel.gates.egress_gate import serialize_evidence

    output = serialize_evidence(clean_artifact(), POLICY)

    assert find_valid_tckn() not in output
    assert synthetic_local_msisdn() not in output
    assert synthetic_person_name() not in output


# --- the deny-by-default mechanism itself ----------------------------------------


class UndeclaredField(EgressModel):
    """The regression this design exists to prevent: a plain str slipped in."""

    note: str


class AdapterResult(BaseModel):
    """Stands in for a wrapped library's own result object (§8)."""

    unexpected_values: list[str]


class CarriesAdapterOutput(EgressModel):
    payload: AdapterResult


def test_field_without_an_egress_declaration_is_refused():
    node = UndeclaredField(note=synthetic_person_name())

    with pytest.raises(EgressViolation, match="declares no egress kind"):
        validate_for_egress(node, POLICY)


def test_adapter_output_is_refused_at_the_top_level():
    result = AdapterResult(unexpected_values=[synthetic_person_name()])

    with pytest.raises(EgressViolation, match="not constructed by the emitter"):
        validate_for_egress(result, POLICY)


def test_adapter_output_is_refused_when_nested():
    node = CarriesAdapterOutput(
        payload=AdapterResult(unexpected_values=[synthetic_person_name()])
    )

    with pytest.raises(EgressViolation):
        validate_for_egress(node, POLICY)


def test_a_bare_mapping_is_refused():
    with pytest.raises(EgressViolation, match="not constructed by the emitter"):
        validate_for_egress({"tckn": find_valid_tckn()}, POLICY)


def test_audit_record_may_not_cross_the_boundary():
    """The §12 in-boundary artifact is structurally barred from egress."""
    record = AuditRecord(
        run_id="run-2026-08-03-0001",
        batch_id="batch-0001",
        bronze_partition="bronze/batch_id=0001",
        record_key=_digest("record"),
        column_name="customer_ref",
        rule_id="tr-core.phone.msisdn_format",
        transform_name="canonicalize_phone",
        pre_image_hash=_digest(synthetic_local_msisdn()),
        post_image_hash=_digest("post"),
        occurred_at=FIXED_TIME,
    )

    with pytest.raises(EgressViolation, match="in-boundary"):
        validate_for_egress(record, POLICY)


# --- §8.1 distinct-value exception ------------------------------------------------


def _distinct(semantic_type, cardinality, counts):
    return KAnonymisedValues(
        semantic_type=semantic_type,
        cardinality=cardinality,
        values=[ValueCount(value=f"shape-{i}", count=c) for i, c in enumerate(counts)],
    )


def test_distinct_values_pass_when_all_three_conditions_hold():
    artifact = clean_artifact()
    artifact.column_profiles[0].distinct_values = _distinct(
        SemanticType.BRAND, 3, [900, 700, 5]
    )

    validate_for_egress(artifact, POLICY)


def test_distinct_values_refused_when_cardinality_exceeds_the_limit():
    artifact = clean_artifact()
    artifact.column_profiles[0].distinct_values = _distinct(
        SemanticType.BRAND, 51, [10] * 51
    )

    with pytest.raises(EgressViolation, match="exceeds the .8.1 limit"):
        validate_for_egress(artifact, POLICY)


def test_distinct_values_refused_when_a_group_is_below_k_anonymity():
    artifact = clean_artifact()
    artifact.column_profiles[0].distinct_values = _distinct(
        SemanticType.BRAND, 2, [900, 4]
    )

    with pytest.raises(EgressViolation, match="below k_anonymity_min"):
        validate_for_egress(artifact, POLICY)


def test_distinct_values_refused_when_cardinality_understates_the_list():
    """Otherwise the §8.1 cap is evaded by simply declaring a smaller number."""
    artifact = clean_artifact()
    artifact.column_profiles[0].distinct_values = _distinct(
        SemanticType.BRAND, 1, [900, 700]
    )

    with pytest.raises(EgressViolation, match="does not match"):
        validate_for_egress(artifact, POLICY)


# --- value-class validation --------------------------------------------------------


def test_negative_count_is_refused():
    artifact = clean_artifact()
    artifact.rule_outcomes[0].violation_count = -1

    with pytest.raises(EgressViolation, match="cannot be negative"):
        validate_for_egress(artifact, POLICY)


def test_rate_outside_the_unit_interval_is_refused():
    artifact = clean_artifact()
    artifact.rule_outcomes[0].hold_rate = 1.5

    with pytest.raises(EgressViolation, match=r"must lie in \[0, 1\]"):
        validate_for_egress(artifact, POLICY)


def test_naive_timestamp_is_refused():
    artifact = clean_artifact()
    # The missing tzinfo is the subject of this test, hence the suppression.
    artifact.generated_at = datetime(2026, 8, 3, 12, 0, 0)  # noqa: DTZ001

    with pytest.raises(EgressViolation, match="timezone-aware"):
        validate_for_egress(artifact, POLICY)


def test_malformed_content_hash_is_refused():
    artifact = clean_artifact()
    artifact.manifest_hash = "not-a-digest"

    with pytest.raises(EgressViolation, match="sha256 digest"):
        validate_for_egress(artifact, POLICY)


def test_raw_value_passed_off_as_a_format_shape_is_refused():
    artifact = clean_artifact()
    artifact.column_profiles[0].top_shapes = [
        ShapeSummary(shape=synthetic_local_msisdn(), count=10)
    ]

    with pytest.raises(EgressViolation, match="not a mask"):
        validate_for_egress(artifact, POLICY)


def test_undeclared_canonical_field_is_refused():
    artifact = clean_artifact()
    artifact.column_profiles[0].canonical_field = "invented_field"

    with pytest.raises(EgressViolation, match="canonical field name"):
        validate_for_egress(artifact, POLICY)


def test_column_name_is_refused_when_nothing_was_declared():
    """An empty vocabulary denies rather than waves everything through."""
    artifact = clean_artifact()
    empty = EgressPolicy(k_anonymity_min=5)

    with pytest.raises(EgressViolation, match="not declared in the manifest"):
        validate_for_egress(artifact, empty)


# --- positive path and determinism (P2) ---------------------------------------------


def test_clean_artifact_validates_and_serializes():
    from kernel.gates.egress_gate import serialize_evidence

    output = serialize_evidence(clean_artifact(), POLICY)

    assert '"run_id": "run-2026-08-03-0001"' in output
    assert output.endswith("\n")


def test_serialization_is_byte_identical_for_identical_input():
    from kernel.gates.egress_gate import serialize_evidence

    first = serialize_evidence(clean_artifact(), POLICY)
    second = serialize_evidence(clean_artifact(), POLICY)

    assert first == second
    assert "\r" not in first, "CR would differ between Windows and Linux CI"


def test_serialization_does_not_read_the_clock():
    """Two artifacts built minutes apart still serialize identically, because
    every timestamp comes from the caller rather than from `now()`."""
    from kernel.gates.egress_gate import serialize_evidence

    early = clean_artifact()
    late = clean_artifact()
    assert early.generated_at == late.generated_at == FIXED_TIME
    assert serialize_evidence(early, POLICY) == serialize_evidence(late, POLICY)


def test_non_utc_timestamp_is_accepted_and_still_deterministic():
    """Tz-awareness is the requirement, not UTC specifically."""
    from kernel.gates.egress_gate import serialize_evidence

    artifact = clean_artifact()
    artifact.generated_at = FIXED_TIME.astimezone(timezone(timedelta(hours=3)))

    output = serialize_evidence(artifact, POLICY)
    assert serialize_evidence(artifact, POLICY) == output
