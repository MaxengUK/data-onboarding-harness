"""What a check implementation sees and what it may return.

Separated from `runner.py` so that check modules can import this without
importing the runner that imports them. The cycle is not hypothetical: the
runner has to import the check modules for their `@implements` decorators to
run at all, and a check importing the runner back would make registration depend
on import order.
"""

from __future__ import annotations

from dataclasses import dataclass

from kernel.stages.preflight.result import CheckStatus
from kernel.stages.preflight.source import SourceProbe
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

    Narrow on purpose: a check needing something absent from here should say
    `unavailable` rather than reach for it. The source is probed once by the
    runner and handed over as facts, so twenty-nine checks cannot become
    twenty-nine reads of a client's production extract.
    """

    manifest: Manifest
    source: SourceProbe
