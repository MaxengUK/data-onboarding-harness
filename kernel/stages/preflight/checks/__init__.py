"""The check implementations this build has (§6.2.2).

**Importing this package is what registers them.** `@implements` runs at import
time, so `runner.py` imports this package before walking the registry; a module
added here without being imported would register nothing and its checks would
silently report `UNAVAILABLE`. That failure is at least safe — an unregistered
check blocks rather than passes — but it would be confusing, so the imports
below are the registration list and should be read as one.

Split by what a check *reads*, not by §6.2.2 category, because that is the line
along which they actually differ: a source check can be unavailable because the
probe failed, a manifest check never can.

Ten of the twenty-nine registered checks are implemented here, plus one
`NOT_APPLICABLE` case. The other eighteen are absent by decision rather than by
oversight — see `docs/STATUS.md` for the gap inventory that decided which.
"""

from kernel.stages.preflight.checks import manifest_checks, source_checks

__all__ = ["manifest_checks", "source_checks"]
