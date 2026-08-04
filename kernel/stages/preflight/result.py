"""What one preflight check produced (CLAUDE.md §6.2.2, §6.2.3).

Three axes, deliberately independent, because collapsing any two of them is how
a preflight report starts lying:

- **severity** — how much a failure costs. Fixed in the registry, never in the
  manifest.
- **status** — what happened when the check was attempted, including the case
  where it could not be attempted at all.
- **class** — whether passing means a fact was measured or a commitment was
  found (§6.2.2, 0.5.4).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    """The seven §6.2.2 check categories."""

    CONNECTIVITY = "connectivity"
    SCHEMA = "schema"
    ENCODING = "encoding"
    VOLUME = "volume"
    PACKS = "packs"
    GOVERNANCE = "governance"
    CAPACITY = "capacity"


class Severity(str, Enum):
    """§6.2.2: `blocker` stops the run, `warning` is acknowledgeable, `info` is
    reported only."""

    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class CheckStatus(str, Enum):
    """What happened when the check was attempted.

    `UNAVAILABLE` is the load-bearing one, and it means **the check did not
    run** — either because this build has no implementation for it, or because a
    prerequisite could not be established (the source was unreachable, so there
    was no header to compare against). Both cases share the only property that
    matters: nothing was verified. A blocker that did not run therefore blocks,
    and the detail says which of the two it was.

    Keeping "not implemented" and "could not run" as one status is deliberate.
    Splitting them would invite a rule that treats one of them as tolerable, and
    the whole point is that neither is: a verdict that distinguishes them is a
    verdict about how much of preflight got built.

    `NOT_APPLICABLE` is the opposite and must not be confused with it. It means
    the check has no meaning *for this manifest* — a file source has no
    collation — and it does not block. The distinction is drawn from a declared
    manifest fact, never from whether the code exists, because a code-based
    reading would let every unwritten check label itself inapplicable.
    """

    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"


class CheckClass(str, Enum):
    """Whether passing means a fact was measured or a commitment was found.

    §6.2.2 (0.5.4). `DECLARATION` is not a weaker `VERIFICATION`, and it is not a
    placeholder for one: some facts are not observable from inside the client
    boundary by a tool holding no standing access (P9). What the report may
    never do is render the two identically, because a client reading
    `restore point: passed` beside `encoding: passed` will conclude both were
    tested. One was.
    """

    VERIFICATION = "verification"
    DECLARATION = "declaration"


class Verdict(str, Enum):
    """§6.2.3. There is no third value: `ready` means every blocker passed."""

    READY = "ready"
    BLOCKED = "blocked"


class CheckResult(BaseModel):
    """One check's outcome, as it appears in the Preflight Report.

    `severity`, `category` and `check_class` are copied from the registry rather
    than decided here, so that a report can be read on its own and so that
    `tests/test_preflight_registry.py` can assert a result never disagrees with
    the registration it came from.
    """

    model_config = {"frozen": True}

    check_id: str
    category: Category
    severity: Severity
    check_class: CheckClass
    status: CheckStatus
    detail: str = Field(
        description=(
            "Why, in counts, positions, column names and manifest keys. **Never "
            "a source value.** §6.2.2 requires that samples never reach the "
            "report, and the natural way to breach that is a helpful error "
            "message quoting the offending cell."
        )
    )

    @property
    def is_blocking(self) -> bool:
        """A blocker that did not pass, whether it failed or never ran."""
        return self.severity is Severity.BLOCKER and self.status in (
            CheckStatus.FAILED,
            CheckStatus.UNAVAILABLE,
        )
