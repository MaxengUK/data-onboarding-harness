"""The rule schema — authored and discovered (CLAUDE.md §7.2, §7.3, §11).

One model rather than two, because §11's lifecycle is one object changing state:
a discovered rule is signed, confirmed, and eventually enforced. Splitting
authored and discovered rules into separate types would make promotion a
conversion and would give §7.4's id-based resolution two shapes to walk.

Three invariants are enforced here rather than trusted, and each encodes a
constitutional rule that would otherwise depend on nobody making a mistake:

1. **`enforced` requires a predicate.** P7 makes enforced rules quarantine on
   violation; a rule with nothing to evaluate cannot. A `proposed` discovered
   rule may have none — it is still a hypothesis (P4).
2. **A discovered rule needs a named signature before it can load as confirmed
   or enforced.** §11 says the transition cannot be set by a config edit; this
   is what stops promotion-by-text-editor. Declaration class in the §6.2.2
   sense: it confirms a signature was *named*, not that one was given.
3. **`repair.reversible: false` does not load.** §6 defines `normalize` as
   deterministic, reversible transforms only, so the setting cannot be honoured
   — and a setting that cannot be honoured should fail at load rather than
   present itself as available. Same treatment as `egress.evidence_only`.

**`band` and `derived_from_client_data_only` have no writable field.** Both are
computed from the evidence beside them (§9.2, §9.4). A writable band would let a
draft pack present a 0.91 hold rate as `money`, and since §9.4 exists precisely
because rules learned from dirty data encode the dirt, a confidence label that
can be asserted independently of its evidence defeats the mitigation it belongs
to. "It is computed" is not a control while a write path exists.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from kernel.predicates import Predicate, check_params
from kernel.registries import (
    ConfidenceBand,
    DiscoveryAlgorithm,
    RuleState,
    SemanticType,
    StageName,
)


class AppliesTo(BaseModel):
    """What a rule binds to.

    A semantic type, never a column name: column names do not survive the trip
    from one client to the next.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    semantic_type: SemanticType


class Repair(BaseModel):
    """The transform applied when a rule's predicate does not hold."""

    model_config = {"frozen": True, "extra": "forbid"}

    transform: str = Field(min_length=1)
    reversible: bool = True

    @model_validator(mode="after")
    def reversible_only(self) -> Repair:
        if not self.reversible:
            raise ValueError(
                "repair.reversible=false is not supported: §6 defines normalize "
                "as deterministic, reversible transforms only, so an "
                "irreversible repair has no stage that would run it"
            )
        return self


class Provenance(BaseModel):
    """Where a rule came from, and — once signed — what signed it."""

    model_config = {"frozen": True, "extra": "forbid"}

    source: Literal["authored", "discovered"]
    author: str | None = None
    signature_ref: str | None = Field(
        default=None,
        description=(
            "The signed Data Readiness Report entry that confirmed this rule. "
            "Required before a discovered rule may load as confirmed or "
            "enforced."
        ),
    )


class Evidence(BaseModel):
    """What discovery observed. `band` is derived from it, never written."""

    model_config = {"frozen": True, "extra": "forbid"}

    hold_rate: float = Field(ge=0.0, le=1.0)
    violating_rows: int = Field(ge=0)
    total_rows: int = Field(gt=0)
    discovered_by: DiscoveryAlgorithm
    corroborated_by: tuple[str, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def derived_from_client_data_only(self) -> bool:
        """§9.4/3. True when no external reference corroborates the rule.

        Computed rather than authored so it cannot disagree with
        `corroborated_by`. The client has to be able to see that the machine
        learned this from their own data.
        """
        return not self.corroborated_by

    @computed_field  # type: ignore[prop-decorator]
    @property
    def band(self) -> ConfidenceBand:
        """§9.2's band, capped at `ambiguous` when nothing corroborates (§9.4/2).

        The cap is the circularity guard doing its work: a rule mined from a
        client's own data cannot be presented as high-confidence on the strength
        of that same data, however cleanly it holds.
        """
        if self.hold_rate >= 1.0:
            unc = ConfidenceBand.TRIVIAL
        elif self.hold_rate >= 0.99:
            unc = ConfidenceBand.MONEY
        elif self.hold_rate >= 0.90:
            unc = ConfidenceBand.AMBIGUOUS
        else:
            unc = ConfidenceBand.NOISE

        if self.derived_from_client_data_only and unc is ConfidenceBand.MONEY:
            return ConfidenceBand.AMBIGUOUS
        return unc


class Rule(BaseModel):
    """One rule, authored or discovered, at some point in its lifecycle."""

    model_config = {"frozen": True, "extra": "forbid"}

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    stage: StageName
    kind: str = Field(min_length=1)
    state: RuleState = RuleState.PROPOSED
    severity: Literal["critical", "error", "warning", "info"] = "error"
    applies_to: AppliesTo | None = None

    predicate: Predicate | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    repair: Repair | None = None
    provenance: Provenance

    # --- discovered rules (§7.3) ---
    determinant: tuple[str, ...] = ()
    dependent: tuple[str, ...] = ()
    evidence: Evidence | None = None
    downstream_impact: Literal["high", "medium", "low"] | None = None

    @model_validator(mode="after")
    def params_match_the_predicate(self) -> Rule:
        if self.predicate is None:
            if self.params:
                raise ValueError(f"{self.id}: params supplied with no predicate to take them")
            return self

        check_params(self.predicate, self.params)
        return self

    @model_validator(mode="after")
    def enforced_rules_can_be_evaluated(self) -> Rule:
        """P7: an enforced rule quarantines on violation, so it must have a test."""
        if self.state is RuleState.ENFORCED and self.predicate is None:
            raise ValueError(
                f"{self.id}: state=enforced with no predicate. An enforced rule "
                f"quarantines on violation (P7), and a rule with nothing to "
                f"evaluate cannot"
            )
        return self

    @model_validator(mode="after")
    def discovered_rules_carry_their_signature(self) -> Rule:
        """§11: confirmation cannot be set by a config edit.

        Without this a draft pack's `state: proposed` becomes `state: enforced`
        in a text editor, and P4 — discovered rules are hypotheses until signed
        — holds only by convention.
        """
        promoted = self.state in (RuleState.CONFIRMED, RuleState.ENFORCED)
        unsigned = not (self.provenance.signature_ref or "").strip()
        if self.provenance.source == "discovered" and promoted and unsigned:
            raise ValueError(
                f"{self.id}: a discovered rule cannot load as "
                f"{self.state.value} without provenance.signature_ref. §11 "
                f"requires a signed Data Readiness Report entry, and this is "
                f"what stops promotion by text editor"
            )
        return self

    @model_validator(mode="after")
    def discovery_fields_belong_to_discovered_rules(self) -> Rule:
        discovery_fields = bool(self.determinant or self.dependent or self.evidence)
        if discovery_fields and self.provenance.source != "discovered":
            raise ValueError(
                f"{self.id}: carries discovery fields but declares "
                f"provenance.source={self.provenance.source!r}"
            )
        return self
