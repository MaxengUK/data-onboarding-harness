"""Running the registered checks and reaching a verdict (CLAUDE.md §6.2.2, §6.2.3).

The loop walks `REGISTRY`, not `IMPLEMENTATIONS`. That is the entire mechanism
behind "a check that cannot run blocks": an id with no implementation is reached
by the loop anyway, and reported `UNAVAILABLE` with its registered severity
intact. Iterating the implementations instead would make an unwritten blocker
invisible, which is the same class of defect as a listing standing in for a
manifest — the store tells you what it has, not what it should have.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kernel.canonical import bind_manifest
from kernel.stages.preflight import checks as _checks  # noqa: F401  (registers)
from kernel.stages.preflight.contract import CheckContext, Outcome, unavailable
from kernel.stages.preflight.digest import (
    DigestIncomplete,
    PreflightDigest,
    compute_digest,
)
from kernel.stages.preflight.registry import IMPLEMENTATIONS, REGISTRY, CheckSpec
from kernel.stages.preflight.report import PreflightReport
from kernel.stages.preflight.result import CheckResult
from kernel.stages.preflight.source import SourceProbe, probe_source
from schemas.manifest import Manifest

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


def run_preflight(
    manifest: Manifest,
    *,
    kernel_version: str,
    environment: dict[str, str],
    now: datetime,
    canonical_root: Path | None = None,
) -> PreflightReport:
    """Run preflight against `manifest` and return the Preflight Report.

    The three keywords are required and none has a default. `kernel_version`
    enters the digest an approval binds to, so a guessed value would bind an
    approval to a version nobody shipped. `environment` and `now` are passed
    rather than read from `os.environ` and the system clock, because a preflight
    whose result depends on ambient process state is one no test can pin and no
    operator can reproduce.

    **The canonical schema is resolved before the source is probed**, and the
    order matters: the schema declares which field carries freshness, and the
    probe uses that to derive one scalar from one column and discard the rest.
    Probing first would mean either retaining every column's values for a check
    to search later — a source-value store handed to twenty-nine checks — or
    reading the source twice.
    """
    binding = bind_manifest(manifest, canonical_root)
    probe = probe_source(manifest, environment, binding.freshness_column)
    results = run_checks(
        CheckContext(manifest=manifest, source=probe, binding=binding, now=now)
    )

    digest: PreflightDigest | None = None
    digest_gap = ""
    try:
        digest = compute_digest(
            manifest,
            kernel_version=kernel_version,
            source_schema=probe.columns,
            row_count=probe.row_count,
        )
    except DigestIncomplete as exc:
        digest_gap = str(exc)

    return PreflightReport(results=results, digest=digest, digest_gap=digest_gap)


__all__ = ["CheckContext", "SourceProbe", "run_checks", "run_preflight"]
