"""Running the registered checks and reaching a verdict (CLAUDE.md §6.2.2, §6.2.3).

The loop walks `REGISTRY`, not `IMPLEMENTATIONS`. That is the entire mechanism
behind "a check that cannot run blocks": an id with no implementation is reached
by the loop anyway, and reported `UNAVAILABLE` with its registered severity
intact. Iterating the implementations instead would make an unwritten blocker
invisible, which is the same class of defect as a listing standing in for a
manifest — the store tells you what it has, not what it should have.
"""

from __future__ import annotations

from dataclasses import dataclass

from kernel.stages.preflight.registry import IMPLEMENTATIONS, REGISTRY, CheckSpec
from kernel.stages.preflight.report import PreflightReport
from kernel.stages.preflight.result import CheckResult, CheckStatus
from schemas.manifest import Manifest


@dataclass(frozen=True)
class Outcome:
    """What one check implementation concluded.

    Deliberately not a `CheckResult`: an implementation decides *status and
    detail* and has no business setting its own severity, category or class.
    Those come from the registry, so a check cannot quietly downgrade itself.
    """

    status: CheckStatus
    detail: str


def passed(detail: str) -> Outcome:
    return Outcome(CheckStatus.PASSED, detail)


def failed(detail: str) -> Outcome:
    return Outcome(CheckStatus.FAILED, detail)


def not_applicable(detail: str) -> Outcome:
    """Use only where a *declared manifest fact* removes the check's meaning.

    Never where the code to run it is missing — that is `unavailable`, and
    conflating the two lets every unwritten check label itself inapplicable
    (see `CheckStatus`).
    """
    return Outcome(CheckStatus.NOT_APPLICABLE, detail)


def unavailable(detail: str) -> Outcome:
    """The check did not run. Say plainly why, in the detail."""
    return Outcome(CheckStatus.UNAVAILABLE, detail)


@dataclass(frozen=True)
class CheckContext:
    """Everything a check may read.

    Narrow on purpose: a check that needs something absent from here should say
    `unavailable` rather than reach for it. The source is read once by the
    runner and handed over as facts, so twenty-nine checks cannot become
    twenty-nine reads of a client's production extract.
    """

    manifest: Manifest


NOT_IMPLEMENTED = (
    "not implemented in this build; registered as a §6.2.2 check so that its "
    "absence blocks rather than passes"
)


def _result(spec: CheckSpec, outcome: Outcome) -> CheckResult:
    return CheckResult(
        check_id=spec.check_id,
        category=spec.category,
        severity=spec.severity,
        check_class=spec.check_class,
        status=outcome.status,
        detail=outcome.detail,
    )


def run_checks(context: CheckContext) -> tuple[CheckResult, ...]:
    """Run every registered check, in registry order."""
    results: list[CheckResult] = []

    for spec in REGISTRY:
        implementation = IMPLEMENTATIONS.get(spec.check_id)
        outcome = (
            unavailable(NOT_IMPLEMENTED) if implementation is None else implementation(context)
        )
        results.append(_result(spec, outcome))

    return tuple(results)


def run_preflight(manifest: Manifest) -> PreflightReport:
    """Run preflight against `manifest` and return the Preflight Report."""
    return PreflightReport(results=run_checks(CheckContext(manifest=manifest)))
