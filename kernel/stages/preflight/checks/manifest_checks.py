"""Checks answerable from the manifest alone (§6.2.2 packs, governance, capacity).

These can never be `UNAVAILABLE` for a probe reason — the manifest is always
there. When one is unavailable it is because this build has no way to resolve
what the manifest declares, which is a different and more honest gap.

Two of them are **declaration class** (§6.2.2, 0.5.4): they confirm a commitment
is present, not that it holds. The report renders them distinctly; here they are
marked by their registry entry, not by anything in the implementation.
"""

from __future__ import annotations

from collections.abc import Iterable

from kernel.predicates import Predicate
from kernel.registries import StageName
from kernel.stages.preflight.contract import (
    CheckContext,
    Outcome,
    failed,
    passed,
    unavailable,
)
from kernel.stages.preflight.registry import implements
from schemas.rule import Rule

#: Stages that evaluate a rule against data, and therefore need something to
#: evaluate. `discover` proposes rules rather than applying them, so a rule
#: bound to it legitimately carries neither predicate nor semantic type.
_PREDICATE_REQUIRING_STAGES = frozenset(
    {StageName.NORMALIZE, StageName.VALIDATE, StageName.RESOLVE}
)


@implements("packs.declared_packs_resolvable")
def declared_packs_resolvable(context: CheckContext) -> Outcome:
    """Vacuously satisfied when no pack is declared, and it says so.

    The vacuity is load-bearing — it is what lets a pack-free manifest reach
    `ready` while BUILD-PLAN item 3 is open — so the detail states that nothing
    was resolved rather than reporting a bare pass. A reader must not take this
    green as "the declared packs were verified".
    """
    packs = context.manifest.packs
    if not packs:
        return passed("no packs declared, so there is nothing to resolve")

    return unavailable(
        f"{len(packs)} pack(s) declared but this build has no pack loader; "
        f"schemas/pack.py does not implement §7.4 (BUILD-PLAN item 3)"
    )


def unresolved_predicates(rules: Iterable[Rule]) -> tuple[str, ...]:
    """Rule ids whose predicate the closed registry does not contain (§7.5).

    **This is the real check, and it is testable without a pack loader.** The
    check below can only ever feed it an empty list today, but the resolution
    logic is exercised directly by `tests/test_preflight_checks.py` with
    constructed rules — so when the loader lands (BUILD-PLAN item 9) this
    function does not get written, only called with something in it.

    Returns ids rather than raising: preflight reports, it does not abort.
    """
    # A `Rule` cannot hold an unregistered predicate — the field is typed to the
    # enum, so an unknown name fails at load. What can still happen is a rule
    # with no predicate at all reaching a stage that needs one, which is what
    # this reports.
    return tuple(
        rule.id
        for rule in rules
        if rule.predicate is None and rule.stage in _PREDICATE_REQUIRING_STAGES
    )


def unresolved_semantic_types(rules: Iterable[Rule]) -> tuple[str, ...]:
    """Rule ids that bind to no semantic type at all (§7.5).

    Same shape as above. An unregistered *name* cannot survive load, because
    `applies_to.semantic_type` is typed to the closed registry; what this
    catches is a rule that binds to nothing, which cannot be applied to a
    column and would silently never fire.
    """
    return tuple(
        rule.id
        for rule in rules
        if rule.applies_to is None and rule.stage in _PREDICATE_REQUIRING_STAGES
    )


@implements("packs.predicates_exist_in_registry")
def predicates_exist_in_registry(context: CheckContext) -> Outcome:
    """§7.5. Vacuous while no pack loader exists — see `declared_packs_resolvable`."""
    if context.manifest.packs:
        return unavailable(
            f"{len(context.manifest.packs)} pack(s) declared but this build has "
            f"no pack loader, so no rule can be read to check its predicate "
            f"(BUILD-PLAN item 9)"
        )

    unresolved = unresolved_predicates(())
    if unresolved:  # pragma: no cover - unreachable until a loader supplies rules
        return failed(f"{len(unresolved)} rule(s) name no predicate: {', '.join(unresolved)}")

    return passed(
        f"no packs declared, so there are no rules to check against the "
        f"{len(Predicate)} registered predicates"
    )


@implements("packs.semantic_types_resolve")
def semantic_types_resolve(context: CheckContext) -> Outcome:
    """§7.5. Vacuous on the same terms, and for the same reason."""
    if context.manifest.packs:
        return unavailable(
            f"{len(context.manifest.packs)} pack(s) declared but this build has "
            f"no pack loader, so no rule can be read to check its "
            f"applies_to.semantic_type (BUILD-PLAN item 9)"
        )

    unresolved = unresolved_semantic_types(())
    if unresolved:  # pragma: no cover - unreachable until a loader supplies rules
        return failed(f"{len(unresolved)} rule(s) bind to no semantic type")

    return passed("no packs declared, so there are no rule bindings to resolve")


@implements("governance.external_references_declare_license_mode")
def external_references_declare_license_mode(context: CheckContext) -> Outcome:
    references = context.manifest.external_references
    if not references:
        return passed("no external references declared")

    return unavailable(
        f"{len(references)} external reference(s) declared but references/ holds "
        f"no adapters, so no license_mode can be read (§9.6)"
    )


@implements("governance.dpa_reference_recorded")
def dpa_reference_recorded(context: CheckContext) -> Outcome:
    """Declaration class: the reference is present, its truth is not tested."""
    reference = context.manifest.governance.dpa_ref.strip()
    if not reference:
        return failed("governance.dpa_ref is blank")

    # The reference itself is not echoed. It is a contract identifier, not
    # source data, but a report that quotes manifest strings back gets used as a
    # place to put them, and the check is about presence rather than content.
    return passed("a DPA/KVİS reference is recorded for this engagement")


@implements("governance.quarantine_retention_defined")
def quarantine_retention_defined(context: CheckContext) -> Outcome:
    target = context.manifest.target
    if not target.quarantine.strip():
        return failed("target.quarantine names no destination")

    return passed(
        f"quarantine at target.quarantine, retained {target.retention_days} days"
    )


@implements("governance.audit_outlives_bronze")
def audit_outlives_bronze(context: CheckContext) -> Outcome:
    """§4.2.6, re-checked here even though the manifest cannot load while violating it.

    The duplication is deliberate and is not belt-and-braces. `schemas/manifest.py`
    refuses an inverted pair at load, so in normal operation this check reports a
    fact already guaranteed — but §6.2.2 lists it as a governance blocker, and a
    blocker that exists only as a side effect of parsing is one nobody can see in
    the report. The client's evidence that retention was checked is this line.

    It also survives a future in which the manifest is built by something other
    than the loader, which is how `tests/test_preflight_checks.py` reaches it.
    """
    audit_days = context.manifest.audit.retention_days
    bronze_days = context.manifest.bronze.retention_days

    if audit_days < bronze_days:
        return failed(
            f"audit.retention_days ({audit_days}) is shorter than "
            f"bronze.retention_days ({bronze_days}): the raw data would outlive "
            f"the account of what was done to it (§4.2.6)"
        )

    return passed(f"audit retained {audit_days} days against Bronze's {bronze_days}")


@implements("capacity.restore_point_declared")
def restore_point_declared(context: CheckContext) -> Outcome:
    """Declaration class: a restore point is named, not exercised.

    Verifying it would mean performing a restore, which no client would keep as
    a per-run control, and the Harness holds no standing access to attempt one
    (P9). What this buys is that the commitment cannot be silently absent.
    """
    restore_point = context.manifest.governance.restore_point.strip()
    if not restore_point:
        return failed("governance.restore_point is blank")

    return passed("a client-side restore point is declared for this run")
