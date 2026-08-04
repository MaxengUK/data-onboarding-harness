"""The Preflight Report and its verdict (CLAUDE.md §6.2.3, §6.2.4).

§6.2.4 makes this a standalone deliverable — the cheapest first contact with a
client's data, answering "can this even be connected to, and what is missing"
before anyone commits to more. So the report's job is not only to say `blocked`;
it is to say *what could not be established and why*, including the checks this
build cannot run. A report that omitted those would answer half the question it
is sold on.

**The report carries no source values.** §6.2.2: where a check needs values it
samples within the declared limit and discards the sample — samples never reach
the report. The natural breach is not a leak, it is a helpful error message
quoting the offending cell, so details are built from counts, byte offsets,
column names and manifest keys. `tests/test_preflight_report.py` holds this.
"""

from __future__ import annotations

from pydantic import BaseModel

from kernel.stages.preflight.digest import PreflightDigest
from kernel.stages.preflight.result import (
    Category,
    CheckClass,
    CheckResult,
    CheckStatus,
    Severity,
    Verdict,
)

#: Rendered beside declaration-class rows so the two cannot be read as one thing
#: (§6.2.2, 0.5.4). A client seeing `restore point: passed` must not conclude a
#: restore was tested.
DECLARATION_NOTE = "declared, not verified"


class PreflightReport(BaseModel):
    """Verdict, per-check results, and what could not be established.

    Not an evidence artifact and not an `EgressModel`: it is read by the client
    inside their own boundary, so it is refused by the egress gate on sight for
    not having been built by the emitter (§8).
    """

    model_config = {"frozen": True}

    results: tuple[CheckResult, ...]
    digest: PreflightDigest | None = None
    digest_gap: str = ""

    @property
    def blocking(self) -> tuple[CheckResult, ...]:
        """Blocker-severity checks that did not pass, failed or never run."""
        return tuple(result for result in self.results if result.is_blocking)

    @property
    def verdict(self) -> Verdict:
        """§6.2.3: `ready` means every blocker passed **and a digest exists**.

        Note what the first half does *not* consult: how many checks ran, how
        many are implemented, or whether the unpassed ones look important. A
        blocker that did not run is indistinguishable here from one that failed,
        which is the point — in both cases nothing was verified.

        The digest is the second half because arming binds to it (§6.2.3 rule
        1). A `ready` with no digest would be a verdict nothing could be
        approved against, and the only way to use it would be to approve against
        something weaker — which is the failure the rule exists to prevent.
        """
        return Verdict.BLOCKED if self.blocking or self.digest is None else Verdict.READY

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        """Warning-severity checks that did not pass.

        Each is acknowledged individually and by name in the arming step
        (§6.2.3 rule 4) — the name being `check_id`. There is deliberately no
        aggregate here to acknowledge in one go, because "acknowledge all" is
        the same thing as not reading them.
        """
        return tuple(
            result
            for result in self.results
            if result.severity is Severity.WARNING
            and result.status in (CheckStatus.FAILED, CheckStatus.UNAVAILABLE)
        )

    def by_category(self, category: Category) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if result.category is category)


def render_report(report: PreflightReport) -> str:
    """Plain text, deterministic, no markup and no source values.

    Plain rather than a rich table so that a test can assert on exactly the
    bytes a reader sees; the CLI adds colour around this, never inside it.
    """
    lines: list[str] = [f"PREFLIGHT — {report.verdict.value.upper()}", ""]

    for category in Category:
        results = report.by_category(category)
        if not results:
            continue

        lines.append(f"[{category.value}]")
        for result in results:
            mark = {
                CheckStatus.PASSED: "PASS",
                CheckStatus.FAILED: "FAIL",
                CheckStatus.NOT_APPLICABLE: "n/a ",
                CheckStatus.UNAVAILABLE: "????",
            }[result.status]
            note = (
                f" ({DECLARATION_NOTE})"
                if result.check_class is CheckClass.DECLARATION
                and result.status is CheckStatus.PASSED
                else ""
            )
            lines.append(f"  {mark}  {result.check_id} [{result.severity.value}]{note}")
            lines.append(f"        {result.detail}")
        lines.append("")

    if report.digest is None:
        lines.append("NO PREFLIGHT DIGEST — nothing can be armed against this run")
        lines.append(f"  {report.digest_gap}")
        lines.append("")
    else:
        lines.append(f"DIGEST {report.digest.value}")
        lines.append(
            "  covers: " + ", ".join(component.value for component in report.digest.covers)
        )
        lines.append("")

    if report.blocking:
        lines.append("BLOCKED BY:")
        lines.extend(
            f"  {result.check_id} ({result.category.value}) — {result.status.value}"
            for result in report.blocking
        )
        lines.append("")

    if report.warnings:
        lines.append("WARNINGS — acknowledge individually, by name:")
        lines.extend(f"  {result.check_id}" for result in report.warnings)
        lines.append("")

    return "\n".join(lines)
