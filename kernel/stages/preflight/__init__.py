"""Preflight — the pipeline entry point and the ready gate (CLAUDE.md §6.2).

Nothing runs against a client source until preflight passes. This package
produces the `ready` or `blocked` verdict and the Preflight Report; **arming is
not here** — that is BUILD-PLAN item 6, and until it exists a `ready` verdict
authorises nothing.

Three properties are worth knowing before reading further, because each one is
load-bearing rather than stylistic:

1. **The check list is data** (`registry.py`). All twenty-nine §6.2.2 checks are
   registered whether or not this build can run them, so an unimplemented
   blocker blocks instead of being absent.
2. **Severity lives in the registry and nowhere else.** No manifest key, flag or
   environment variable moves a blocker to a warning (§0).
3. **A check that did not run is not a check that passed.** `UNAVAILABLE` is a
   distinct status and blocks at blocker severity; `NOT_APPLICABLE` is decided
   by a declared manifest fact and does not.

**What this build can actually check is a minority of the list**, and the report
says so per check rather than in aggregate. That is not an apology: §6.2.4 sells
preflight as the answer to "can this even be connected to, and what is missing",
and a report naming its own gaps is the shape of that deliverable.
"""

from kernel.stages.preflight.registry import BY_ID, IMPLEMENTATIONS, REGISTRY, CheckSpec
from kernel.stages.preflight.report import PreflightReport, render_report
from kernel.stages.preflight.result import (
    Category,
    CheckClass,
    CheckResult,
    CheckStatus,
    Severity,
    Verdict,
)
from kernel.stages.preflight.runner import CheckContext, run_checks, run_preflight

__all__ = [
    "BY_ID",
    "IMPLEMENTATIONS",
    "REGISTRY",
    "Category",
    "CheckClass",
    "CheckContext",
    "CheckResult",
    "CheckSpec",
    "CheckStatus",
    "PreflightReport",
    "Severity",
    "Verdict",
    "render_report",
    "run_checks",
    "run_preflight",
]
