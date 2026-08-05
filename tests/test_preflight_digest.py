"""The preflight digest (CLAUDE.md §6.2.3).

Two properties, and the second is the one that would be easy to lose.

**Determinism.** Arming binds to the digest, and a standing authorization is void
the moment it changes (§6.2.3). A digest that moved on its own would void every
scheduled batch in continuous mode for no reason, and the natural cause would be
a clock read or a dict ordering — neither of which announces itself.

**Refusal to be partial.** A digest omitting pack versions means a pack bump does
not void arming, silently, exactly where §6.2.3 rule 1 promises it would. So an
unresolved component produces no digest rather than a shorter one, and the
verdict blocks.
"""

from __future__ import annotations

import pytest

from kernel.stages.preflight import (
    DigestComponent,
    DigestIncomplete,
    compute_digest,
    manifest_hash,
    run_preflight,
)
from tests.conftest import FIXED_NOW, KERNEL_VERSION, manifest_with

SCHEMA = ("Uretim", "Tarih")


def digest_for(manifest, **overrides):
    arguments = {
        "kernel_version": KERNEL_VERSION,
        "source_schema": SCHEMA,
        "row_count": 2,
    } | overrides
    return compute_digest(manifest, **arguments)


# --- determinism --------------------------------------------------------------


def test_the_same_inputs_give_the_same_digest(manifest) -> None:
    assert digest_for(manifest).value == digest_for(manifest).value


def test_the_digest_survives_a_reordered_manifest(manifest) -> None:
    """Key order is a property of how a YAML file was typed, not of what it says.

    Without canonicalisation, moving `audit:` above `bronze:` in a client's
    manifest would void their standing authorization.
    """
    reordered = manifest_with(
        **{
            key: value
            for key, value in reversed(list(manifest.model_dump(mode="json").items()))
            if key not in {"engagement", "tenant", "sector", "canonical_schema"}
        }
    )

    assert digest_for(reordered).value == digest_for(manifest).value


def test_a_changed_manifest_changes_the_digest(manifest) -> None:
    changed = manifest_with(preflight={"row_count_bounds": {"min": 2, "max": 999}})

    assert digest_for(changed).value != digest_for(manifest).value


def test_each_component_moves_the_digest(manifest) -> None:
    """A component in the coverage list but absent from the hash would be a
    claim the digest does not keep."""
    baseline = digest_for(manifest).value

    assert digest_for(manifest, kernel_version="9.9.9").value != baseline
    assert digest_for(manifest, source_schema=("Uretim",)).value != baseline
    assert digest_for(manifest, row_count=3).value != baseline
    assert digest_for(manifest_with(packs=[])).value == baseline


def test_the_manifest_hash_is_stable_and_content_addressed(manifest) -> None:
    assert manifest_hash(manifest) == manifest_hash(manifest)
    assert manifest_hash(manifest) != manifest_hash(manifest_with(tenant="someone-else"))


# --- refusal to be partial ----------------------------------------------------


def test_an_unreadable_source_produces_no_digest(manifest) -> None:
    """The two components most likely to change upstream are the two that could
    not be observed, so an approval must not be bindable."""
    with pytest.raises(DigestIncomplete) as excinfo:
        digest_for(manifest, source_schema=None, row_count=None)

    assert excinfo.value.missing == (
        DigestComponent.SOURCE_SCHEMA,
        DigestComponent.ROW_COUNTS,
    )


def test_a_declared_pack_makes_the_digest_incomplete(manifest) -> None:
    """A declared `@^1.4` is a *range*: two runs a month apart could resolve it
    differently under an identical digest. Sound only while the list is empty."""
    with pytest.raises(DigestIncomplete, match="pack_versions"):
        digest_for(manifest_with(packs=["core/tr-core@^1.4"]))


def test_an_incomplete_digest_blocks_the_verdict(manifest, environment, source_dir) -> None:
    (source_dir / "generation.csv").unlink()

    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment, now=FIXED_NOW)

    assert report.digest is None
    assert report.verdict.value == "blocked"
    assert "source_schema" in report.digest_gap


def test_a_complete_digest_covers_every_component(manifest, environment) -> None:
    report = run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment, now=FIXED_NOW)

    assert report.digest is not None
    assert report.digest.covers == tuple(DigestComponent)
    assert len(report.digest.value) == 64


def test_the_report_says_when_nothing_can_be_armed(manifest, environment, source_dir) -> None:
    from kernel.stages.preflight import render_report

    (source_dir / "generation.csv").unlink()
    rendered = render_report(
        run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment, now=FIXED_NOW)
    )

    assert "NO PREFLIGHT DIGEST" in rendered
