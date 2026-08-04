"""The kernel version, resolved from installed package metadata.

**Not the spec version.** `pyproject.toml` versions the code and `CLAUDE.md`
versions the constitutional decisions, and the two advance independently
(§12) — a comment beside the `version` key says so to whoever next reaches for a
sync. This module answers only the first question.

Read from installed metadata rather than hardcoded, so there is one place a
release changes and no second copy to drift from it. An uninstalled tree raises
rather than falling back to a placeholder: a run manifest recording
`kernel_version: "0.0.0-dev"` would identify nothing while looking identified,
and the digest that version feeds into is what an approval gets bound to.
"""

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "data-onboarding-harness"


def kernel_version() -> str:
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError as exc:  # pragma: no cover - install-time failure
        raise RuntimeError(
            f"{DISTRIBUTION} is not installed, so the kernel version cannot be "
            f"resolved; run `pip install -e .`. Preflight refuses to guess it "
            f"because the digest an approval binds to includes it (§6.2.3)"
        ) from exc
