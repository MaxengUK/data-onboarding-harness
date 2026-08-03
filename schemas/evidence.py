"""The exportable evidence artifact (CLAUDE.md §8, P5, §13).

This is the §8 artifact — the only thing that crosses the trust boundary. Its
in-boundary counterpart, which may hold per-record pre-image hashes, is
`schemas/audit.py`; see that module for why the two are separate types.

Every field declares the §8 value class it belongs to via `Egress(...)`. An
undeclared field does not serialize — `kernel.gates.egress_gate` raises. Per §0,
adding a field here means updating the §8 allowlist and both legs of the §8.2
leak test in the same change.

What is deliberately absent is as load-bearing as what is present. There is no
`invalid_value` (a source cell value, P5), no `message` (free text drawn from
the run), and no `row_index` (a row locator: combined with Bronze access it
points at a person, which is the "reconstructable projection" §8 denies).
Row-level detail belongs in the quarantine partition inside the boundary (§6.1).
Exported evidence is aggregate.
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from kernel.gates.egress_gate import (
    Egress,
    EgressKind,
    EgressModel,
    KAnonymisedValues,
    ShapeSummary,
)
from kernel.registries import ConfidenceBand, RuleState, SemanticType, StageName


class RuleOutcome(EgressModel):
    """What one rule did to a batch, in counts. Never which records."""

    rule_id: Annotated[str, Egress(EgressKind.RULE_ID)]
    state: Annotated[RuleState, Egress(EgressKind.RULE_STATE)]
    evaluated_count: Annotated[int, Egress(EgressKind.COUNT)]
    violation_count: Annotated[int, Egress(EgressKind.COUNT)]
    hold_rate: Annotated[float, Egress(EgressKind.RATE)]


class ColumnProfile(EgressModel):
    """§9.1 layer A output for one column: statistics and shapes, no values.

    `distinct_values` is the §8.1 exception and is populated only when all three
    of its conditions hold. When they do not, `top_shapes` is the answer.
    """

    column_name: Annotated[str, Egress(EgressKind.COLUMN_NAME)]
    canonical_field: Annotated[str | None, Egress(EgressKind.CANONICAL_FIELD_NAME)] = None
    semantic_type: Annotated[SemanticType, Egress(EgressKind.SEMANTIC_TYPE)]
    row_count: Annotated[int, Egress(EgressKind.COUNT)]
    null_rate: Annotated[float, Egress(EgressKind.RATE)]
    cardinality: Annotated[int, Egress(EgressKind.COUNT)]
    top_shapes: list[ShapeSummary] = Field(default_factory=list)
    distinct_values: KAnonymisedValues | None = None


class BandCount(EgressModel):
    """One entry of the §13 `band_distribution` metric.

    A list of these rather than a mapping: an open dict would put free-text keys
    into the artifact, and the gate refuses mappings for exactly that reason.
    """

    band: Annotated[ConfidenceBand, Egress(EgressKind.CONFIDENCE_BAND)]
    count: Annotated[int, Egress(EgressKind.COUNT)]


class Metrics(EgressModel):
    """The §13 metric set, as explicit fields rather than an open dict."""

    reuse_ratio: Annotated[float | None, Egress(EgressKind.RATE)] = None
    kernel_churn: Annotated[int | None, Egress(EgressKind.COUNT)] = None
    promotions: Annotated[int | None, Egress(EgressKind.COUNT)] = None
    time_to_first_evidence_ms: Annotated[int | None, Egress(EgressKind.DURATION_MS)] = None
    time_to_signed_ruleset_ms: Annotated[int | None, Egress(EgressKind.DURATION_MS)] = None
    signature_rate: Annotated[float | None, Egress(EgressKind.RATE)] = None
    signed_coverage: Annotated[float | None, Egress(EgressKind.RATE)] = None
    band_distribution: list[BandCount] = Field(default_factory=list)


class EvidenceArtifact(EgressModel):
    """The only artifact that crosses the boundary (P5).

    Identified by an opaque `run_id` and the manifest hash rather than by tenant
    or engagement name: neither is on the §8 allowlist, and the recipient
    already knows which engagement they are looking at.
    """

    run_id: Annotated[str, Egress(EgressKind.RUN_ID)]
    kernel_version: Annotated[str, Egress(EgressKind.KERNEL_VERSION)]
    manifest_hash: Annotated[str, Egress(EgressKind.CONTENT_HASH)]
    pack_versions: Annotated[list[str], Egress(EgressKind.PACK_VERSION)] = Field(
        default_factory=list
    )
    reference_ids: Annotated[list[str], Egress(EgressKind.REFERENCE_ID)] = Field(
        default_factory=list
    )
    # Supplied by the caller from the run manifest. There is no default_factory
    # here on purpose: defaulting to a clock read would make two identical runs
    # produce different bytes, which is a P2 failure.
    generated_at: Annotated[datetime, Egress(EgressKind.TIMESTAMP)]
    stage: Annotated[StageName, Egress(EgressKind.STAGE_NAME)]
    rule_outcomes: list[RuleOutcome] = Field(default_factory=list)
    column_profiles: list[ColumnProfile] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
