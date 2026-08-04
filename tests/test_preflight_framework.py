"""The verdict machinery (CLAUDE.md §6.2.2, §6.2.3).

The centre of this file is `test_an_unimplemented_blocker_blocks`. Every other
property preflight claims rests on it: if a check that never ran could be
counted as passing, the verdict would describe how much of preflight was built
rather than anything about the client's source, and it would do so while looking
like a clean bill of health.

`test_not_applicable_does_not_block` is its counterweight. Without the second
status the first rule would make every manifest permanently blocked by checks
that have no meaning for it, and the pressure to relax the first rule would come
from a real problem — which is exactly how a control gets softened.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from kernel.stages.preflight import (
    BY_ID,
    REGISTRY,
    Category,
    CheckClass,
    CheckResult,
    CheckStatus,
    PreflightReport,
    Severity,
    Verdict,
    run_preflight,
)
from tests.conftest import KERNEL_VERSION


def result(
    check_id: str,
    status: CheckStatus,
    severity: Severity = Severity.BLOCKER,
    category: Category = Category.GOVERNANCE,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        category=category,
        severity=severity,
        check_class=CheckClass.VERIFICATION,
        status=status,
        detail="constructed by a test",
    )


def report_of(*results: CheckResult, digest=None) -> PreflightReport:
    return PreflightReport(results=results, digest=digest)


# --- the centre --------------------------------------------------------------


def test_an_unimplemented_blocker_blocks(manifest, environment) -> None:
    """The property everything else rests on, asserted against a real run.

    Eighteen registered checks have no implementation in this build. Not one of
    them may be counted as passing, and the report must name them — a verdict
    that hid its own gaps would answer the opposite of the question §6.2.4 sells
    preflight on.
    """
    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)

    unavailable_blockers = [
        line
        for line in report.results
        if line.status is CheckStatus.UNAVAILABLE and line.severity is Severity.BLOCKER
    ]

    assert unavailable_blockers, "expected this build to have unimplemented blockers"
    assert report.verdict is Verdict.BLOCKED
    assert set(unavailable_blockers) <= set(report.blocking)


def test_not_applicable_does_not_block() -> None:
    """The counterweight: without it, every manifest is blocked forever by
    checks that have no meaning for it."""
    report = report_of(
        result("governance.audit_outlives_bronze", CheckStatus.PASSED),
        result("encoding.collation_consistent", CheckStatus.NOT_APPLICABLE),
        digest=_any_digest(),
    )

    assert report.blocking == ()
    assert report.verdict is Verdict.READY


def test_a_failed_and_a_never_run_blocker_are_treated_alike() -> None:
    """In both cases nothing was verified, and the verdict may not prefer one."""
    failed = report_of(result("a.b", CheckStatus.FAILED), digest=_any_digest())
    never_ran = report_of(result("a.b", CheckStatus.UNAVAILABLE), digest=_any_digest())

    assert failed.verdict is never_ran.verdict is Verdict.BLOCKED


def test_a_warning_never_blocks() -> None:
    report = report_of(
        result("volume.row_count_within_bounds", CheckStatus.FAILED, Severity.WARNING),
        digest=_any_digest(),
    )

    assert report.verdict is Verdict.READY
    assert [line.check_id for line in report.warnings] == ["volume.row_count_within_bounds"]


# --- what the verdict must say -----------------------------------------------


def test_blocked_names_the_category_and_the_check(manifest, environment) -> None:
    from kernel.stages.preflight import render_report

    rendered = render_report(
        run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)
    )

    assert "BLOCKED BY:" in rendered
    assert "schema.declared_key_present" in rendered
    assert "(schema)" in rendered


def test_warnings_are_listed_individually_by_name(manifest, environment) -> None:
    """§6.2.3 rule 4: acknowledged individually and by name. The name is the
    check id, and it has to be in the report for arming to be able to take it."""
    from kernel.stages.preflight import render_report

    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)
    rendered = render_report(report)

    assert "acknowledge individually" in rendered
    for warning in report.warnings:
        assert warning.check_id in rendered


# --- severity comes from the registry, not from anywhere else ----------------


def test_a_result_never_disagrees_with_its_registration(manifest, environment) -> None:
    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)

    for line in report.results:
        spec = BY_ID[line.check_id]
        assert (line.severity, line.category, line.check_class) == (
            spec.severity,
            spec.category,
            spec.check_class,
        )


def test_the_manifest_cannot_carry_a_severity(manifest) -> None:
    """A configurable severity is a one-line bypass moving every blocker to
    warning — the same argument that keeps `overwrite` off the stores."""
    serialised = manifest.model_dump()

    assert not any("sever" in key.lower() for key in serialised)
    assert "blocker" not in str(serialised).lower()


def test_no_preflight_entry_point_takes_a_bypass_parameter() -> None:
    """§0: no `--force` or `--skip-checks` on preflight blockers, and no bulk
    acknowledgement (§6.2.3 rule 4)."""
    from kernel.stages.preflight import runner

    forbidden = ("force", "skip", "override", "acknowledge", "ack_all", "ignore", "bypass")

    for name, function in vars(runner).items():
        if name.startswith("_") or not callable(function):
            continue
        if getattr(function, "__module__", "") != runner.__name__:
            continue
        for parameter in inspect.signature(function).parameters:
            assert not any(token in parameter.lower() for token in forbidden), (
                f"{name}({parameter}) would let a caller past a blocker"
            )


def test_registered_ids_are_the_only_implementable_ones() -> None:
    """An implementation bound to an unregistered id would appear in reports
    without ever having been specified."""
    from kernel.stages.preflight.registry import implements

    with pytest.raises(KeyError, match="not a registered"):
        implements("governance.invented_by_a_developer")(lambda context: None)


def test_a_check_result_is_frozen() -> None:
    line = result("a.b", CheckStatus.PASSED)

    with pytest.raises(ValidationError):
        line.status = CheckStatus.FAILED


def _any_digest():
    """A digest whose presence lets the verdict turn on the checks alone."""
    from kernel.stages.preflight import DigestComponent, PreflightDigest

    return PreflightDigest(value="0" * 64, covers=tuple(DigestComponent))


def test_every_registered_check_is_reached_by_a_run(manifest, environment) -> None:
    """The runner walks the registry, not the implementations — so all 29 appear
    in every report, whether or not this build can run them."""
    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)

    assert len(report.results) == len(REGISTRY)
    assert {line.check_id for line in report.results} == {spec.check_id for spec in REGISTRY}
