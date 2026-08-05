"""The rule schema and its lifecycle invariants (CLAUDE.md §7.2, §7.3, §11).

The centre is `test_a_discovered_rule_cannot_be_promoted_by_editing_it`. §11 says
confirmation requires a signed Data Readiness Report entry and cannot be set by
a config edit — and until this validator existed, `state: proposed` became
`state: enforced` with one keystroke and P4 held only by convention.

`test_a_written_band_is_refused_rather_than_ignored` is its companion. Pydantic's
default would drop an unknown key silently, so a pack author writing
`band: money` over a 0.91 hold rate would see no error and believe it took
effect. Refusing beats ignoring; §9.4 exists because rules learned from dirty
data encode the dirt, and a confidence label assertable independently of its
evidence defeats the mitigation it belongs to.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kernel.registries import ConfidenceBand, RuleState, SemanticType
from schemas.rule import Evidence, Rule

AUTHORED = {
    "id": "tr-core.phone.msisdn_format",
    "title": "Mobile number must be a valid TR MSISDN",
    "stage": "normalize",
    "kind": "format",
    "state": "enforced",
    "severity": "error",
    "applies_to": {"semantic_type": "phone_mobile"},
    "predicate": "matches_pattern",
    "params": {"pattern": "digits"},
    "repair": {"transform": "canonicalize_phone", "reversible": True},
    "provenance": {"source": "authored", "author": "maxeng"},
}

DISCOVERED = {
    "id": "draft.gate0.chassis_determines_brand",
    "title": "Chassis number determines brand",
    "stage": "validate",
    "kind": "functional_dependency",
    "state": "proposed",
    "determinant": ["chassis_no"],
    "dependent": ["brand"],
    "evidence": {
        "hold_rate": 0.9963,
        "violating_rows": 412,
        "total_rows": 111204,
        "discovered_by": "b_dependency.hyfd",
        "corroborated_by": ["cardata.brand_catalog"],
    },
    "downstream_impact": "high",
    "provenance": {"source": "discovered"},
}


def evidence(**overrides) -> Evidence:
    base = {
        "hold_rate": 0.95,
        "violating_rows": 5,
        "total_rows": 100,
        "discovered_by": "b_dependency.hyfd",
    }
    return Evidence.model_validate(base | overrides)


# --- the centre ---------------------------------------------------------------


def test_a_discovered_rule_cannot_be_promoted_by_editing_it() -> None:
    """§11: the transition cannot be set by a config edit.

    The attack this closes is not malice, it is convenience — a draft pack sits
    in a repo, a rule looks obviously right, and `proposed` becomes `enforced`
    with one keystroke and no signature anywhere.
    """
    for promoted in ("confirmed", "enforced"):
        forged = DISCOVERED | {"state": promoted, "predicate": "is_not_null"}

        with pytest.raises(ValidationError, match="signature_ref"):
            Rule.model_validate(forged)


def test_a_signed_discovered_rule_loads() -> None:
    signed = DISCOVERED | {
        "state": "confirmed",
        "provenance": {"source": "discovered", "signature_ref": "DRR-2026-08-014"},
    }

    assert Rule.model_validate(signed).state is RuleState.CONFIRMED


def test_a_blank_signature_is_not_a_signature() -> None:
    forged = DISCOVERED | {
        "state": "confirmed",
        "provenance": {"source": "discovered", "signature_ref": "   "},
    }

    with pytest.raises(ValidationError, match="signature_ref"):
        Rule.model_validate(forged)


def test_an_authored_rule_needs_no_signature() -> None:
    """An authored rule was never a hypothesis, so P4 does not apply to it."""
    assert Rule.model_validate(AUTHORED).state is RuleState.ENFORCED


# --- band and derived_from_client_data_only ----------------------------------


def test_a_written_band_is_refused_rather_than_ignored() -> None:
    """Silently dropping it would be worse: the author sees no error and
    believes it took effect."""
    with pytest.raises(ValidationError, match="band"):
        Evidence.model_validate(
            {
                "hold_rate": 0.91,
                "violating_rows": 9,
                "total_rows": 100,
                "discovered_by": "b_dependency.hyfd",
                "band": "money",
            }
        )


def test_the_band_follows_the_hold_rate() -> None:
    corroborated = {"corroborated_by": ("cardata.brand_catalog",)}

    assert evidence(hold_rate=1.0, **corroborated).band is ConfidenceBand.TRIVIAL
    assert evidence(hold_rate=0.9963, **corroborated).band is ConfidenceBand.MONEY
    assert evidence(hold_rate=0.95, **corroborated).band is ConfidenceBand.AMBIGUOUS
    assert evidence(hold_rate=0.5, **corroborated).band is ConfidenceBand.NOISE


def test_an_uncorroborated_rule_is_capped_at_ambiguous() -> None:
    """§9.4/2, and the circularity guard's whole point.

    A rule mined from a client's own data cannot be presented as
    high-confidence on the strength of that same data, however cleanly it holds.
    """
    uncorroborated = evidence(hold_rate=0.9963)

    assert uncorroborated.band is ConfidenceBand.AMBIGUOUS
    assert evidence(hold_rate=0.9963, corroborated_by=("odmd.segment_map",)).band is (
        ConfidenceBand.MONEY
    )


def test_derived_from_client_data_only_cannot_disagree_with_the_evidence() -> None:
    """§9.4/3: the client must see that the machine learned this from their data."""
    assert evidence().derived_from_client_data_only
    assert not evidence(corroborated_by=("cardata.brand_catalog",)).derived_from_client_data_only


def test_the_computed_fields_serialise() -> None:
    """§9.3's report needs them, so being unwritable must not mean being absent."""
    rendered = evidence().model_dump(mode="json")

    assert rendered["band"] == ConfidenceBand.AMBIGUOUS.value
    assert rendered["derived_from_client_data_only"] is True


# --- the other two invariants -------------------------------------------------


def test_an_enforced_rule_must_have_something_to_evaluate() -> None:
    """P7: enforced rules quarantine on violation."""
    toothless = {key: value for key, value in AUTHORED.items() if key != "predicate"}
    toothless.pop("params")

    with pytest.raises(ValidationError, match="nothing to.*evaluate"):
        Rule.model_validate(toothless)


def test_a_proposed_rule_may_have_no_predicate() -> None:
    """A discovered functional dependency is a hypothesis (P4), not yet a test."""
    assert Rule.model_validate(DISCOVERED).predicate is None


def test_an_irreversible_repair_does_not_load() -> None:
    """§6 defines normalize as reversible transforms only, so the setting has no
    stage that would run it."""
    with pytest.raises(ValidationError, match="reversible"):
        Rule.model_validate(
            AUTHORED | {"repair": {"transform": "canonicalize_phone", "reversible": False}}
        )


# --- params and bindings ------------------------------------------------------


def test_params_are_checked_against_the_predicate_at_load() -> None:
    """Malformed rules are found when the pack is read, not partway through a
    client's batch."""
    with pytest.raises(ValidationError):
        Rule.model_validate(AUTHORED | {"params": {"pattern": "not_a_registered_pattern"}})

    with pytest.raises(ValidationError):
        Rule.model_validate(AUTHORED | {"predicate": "length_between", "params": {"min": 1}})


def test_params_without_a_predicate_are_refused() -> None:
    orphaned = {key: value for key, value in DISCOVERED.items()}
    orphaned["params"] = {"pattern": "digits"}

    with pytest.raises(ValidationError, match="no predicate"):
        Rule.model_validate(orphaned)


def test_a_rule_binds_to_a_semantic_type_not_a_column() -> None:
    rule = Rule.model_validate(AUTHORED)

    assert rule.applies_to is not None
    assert rule.applies_to.semantic_type is SemanticType.PHONE_MOBILE

    with pytest.raises(ValidationError):
        Rule.model_validate(AUTHORED | {"applies_to": {"column": "Müşteri GSM"}})


def test_discovery_fields_require_a_discovered_provenance() -> None:
    mislabelled = DISCOVERED | {"provenance": {"source": "authored", "author": "maxeng"}}

    with pytest.raises(ValidationError, match="discovery fields"):
        Rule.model_validate(mislabelled)


def test_an_unknown_field_is_refused() -> None:
    """extra=forbid: a typo'd field silently ignored is the same defect as a
    silently ignored band."""
    with pytest.raises(ValidationError):
        Rule.model_validate(AUTHORED | {"severty": "error"})
