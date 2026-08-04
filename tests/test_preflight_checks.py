"""Every check category, made to fail on purpose (CLAUDE.md §6.2.2, §0).

**A control that passes proves nothing.** Each of the seven §6.2.2 categories has
at least one test here that breaks a manifest or an environment and watches the
category report it. Where this build implements a check, the demonstration is a
`FAILED`; where it does not, the demonstration is an `UNAVAILABLE` that blocks —
which is the honest form of "this category is not implemented" and the reason
none of them is stubbed.

The tests are written against the *report*, not against the check functions, so
they exercise the path a client's verdict actually takes: registry lookup,
implementation dispatch, severity from the registration, verdict from the
statuses.
"""

from __future__ import annotations

from pathlib import Path

from kernel.stages.preflight import CheckStatus, run_preflight
from schemas.manifest import Manifest
from tests.conftest import KERNEL_VERSION, MINIMAL_MANIFEST, manifest_with


def status_of(report, check_id: str) -> CheckStatus:
    return next(line.status for line in report.results if line.check_id == check_id)


def detail_of(report, check_id: str) -> str:
    return next(line.detail for line in report.results if line.check_id == check_id)


def run(manifest: Manifest, environment: dict[str, str]):
    return run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)


# --- 1. connectivity & privilege ---------------------------------------------


def test_connectivity_fails_when_the_source_is_not_there(manifest, environment, source_dir) -> None:
    (source_dir / "generation.csv").unlink()

    report = run(manifest, environment)

    assert status_of(report, "connectivity.source_reachable") is CheckStatus.FAILED
    assert report.verdict.value == "blocked"


def test_connectivity_is_unavailable_for_a_database_binding(manifest, environment) -> None:
    """Not `not_applicable`: a database source is one that *should* be checked,
    and calling it inapplicable is the erosion `CheckStatus` warns against."""
    database = manifest_with(
        sources=[
            MINIMAL_MANIFEST["sources"][0]
            | {"binding": {"kind": "database", "connection_ref": "env:DSN", "objects": ["t"]}}
        ]
    )

    report = run(database, environment)

    assert status_of(report, "connectivity.source_reachable") is CheckStatus.UNAVAILABLE
    assert "adapter" in detail_of(report, "connectivity.source_reachable")


def test_a_literal_connection_ref_is_refused(manifest, environment) -> None:
    """§7.1: never a literal credential. The rule gets broken by convenience
    during a demo, so the refusal is in the resolver rather than in a lint."""
    literal = manifest_with(
        sources=[
            MINIMAL_MANIFEST["sources"][0]
            | {
                "binding": {
                    "kind": "file",
                    "connection_ref": "/srv/data",
                    "objects": ["generation.csv"],
                }
            }
        ]
    )

    report = run(literal, environment)

    assert status_of(report, "connectivity.source_reachable") is CheckStatus.FAILED
    assert "literal" in detail_of(report, "connectivity.source_reachable")


# --- 2. schema conformance ----------------------------------------------------


def test_schema_fails_when_a_mapped_column_is_absent(manifest, environment, source_dir) -> None:
    (source_dir / "generation.csv").write_text("Baska;Tarih\n1;2026-08-01\n", encoding="utf-8")

    report = run(manifest, environment)

    assert status_of(report, "schema.mapped_columns_exist") is CheckStatus.FAILED
    assert "Uretim" in detail_of(report, "schema.mapped_columns_exist")


def test_the_unimplemented_schema_checks_block(manifest, environment) -> None:
    """Three of the four schema checks need a semantic type binding the manifest
    cannot express (BUILD-PLAN item 3). None is stubbed; all three block."""
    report = run(manifest, environment)

    for check_id in (
        "schema.types_match_semantic_types",
        "schema.declared_key_present",
        "schema.no_undeclared_pii_column",
    ):
        assert status_of(report, check_id) is CheckStatus.UNAVAILABLE
        assert check_id in {line.check_id for line in report.blocking}


# --- 3. encoding & locale -----------------------------------------------------


def test_encoding_fails_when_the_declared_encoding_does_not_decode(
    manifest, environment, source_dir
) -> None:
    """cp1254-encoded Turkish text declared as UTF-8. A real onboarding failure,
    not a synthetic one — it is the first thing a Windows-exported extract does.
    """
    (source_dir / "generation.csv").write_bytes(
        "Uretim;Sehir\n120.5;İstanbul\n".encode("cp1254")
    )

    report = run(manifest, environment)

    assert status_of(report, "encoding.declared_encoding_decodes") is CheckStatus.FAILED
    assert "byte offset" in detail_of(report, "encoding.declared_encoding_decodes")


def test_the_same_file_passes_when_the_encoding_is_declared_correctly(
    environment, source_dir
) -> None:
    (source_dir / "generation.csv").write_bytes(
        "Uretim;Sehir\n120.5;İstanbul\n".encode("cp1254")
    )
    declared = manifest_with(
        sources=[MINIMAL_MANIFEST["sources"][0] | {"encoding": "cp1254"}]
    )

    report = run(declared, environment)

    assert status_of(report, "encoding.declared_encoding_decodes") is CheckStatus.PASSED


def test_collation_is_not_applicable_to_a_file_and_does_not_block(
    manifest, environment
) -> None:
    report = run(manifest, environment)

    assert status_of(report, "encoding.collation_consistent") is CheckStatus.NOT_APPLICABLE
    assert "encoding.collation_consistent" not in {line.check_id for line in report.blocking}


# --- 4. volume & freshness ----------------------------------------------------


def test_volume_fails_on_an_empty_source(manifest, environment, source_dir) -> None:
    (source_dir / "generation.csv").write_text("", encoding="utf-8")

    report = run(manifest, environment)

    assert status_of(report, "volume.source_not_empty") is CheckStatus.FAILED


def test_row_count_outside_the_declared_bounds_warns_without_blocking(
    environment, source_dir
) -> None:
    """§6.2.2: blocker for empty/truncated, warning otherwise. The warning must
    be visible and must not stop the run."""
    (source_dir / "generation.csv").write_text(
        "Uretim\n" + "1.0\n" * 50, encoding="utf-8"
    )
    tight = manifest_with(preflight={"row_count_bounds": {"min": 1, "max": 10}})

    report = run(tight, environment)

    assert status_of(report, "volume.row_count_within_bounds") is CheckStatus.FAILED
    assert "volume.row_count_within_bounds" in {line.check_id for line in report.warnings}
    assert "volume.row_count_within_bounds" not in {line.check_id for line in report.blocking}


# --- 5. packs & rules ---------------------------------------------------------


def test_declaring_a_pack_blocks_because_nothing_can_resolve_it(
    manifest, environment
) -> None:
    """The category's failing demonstration. There is no pack loader, so a
    manifest that declares a pack cannot be verified and must not proceed."""
    with_packs = manifest_with(packs=["core/tr-core@^1.4"])

    report = run(with_packs, environment)

    assert status_of(report, "packs.declared_packs_resolvable") is CheckStatus.UNAVAILABLE
    assert "pack loader" in detail_of(report, "packs.declared_packs_resolvable")
    assert report.verdict.value == "blocked"


def test_declaring_no_packs_resolves_vacuously_and_says_so(manifest, environment) -> None:
    """The vacuity is load-bearing — it is what lets the walking skeleton run —
    so the detail has to prevent it being read as "packs were verified"."""
    report = run(manifest, environment)

    assert status_of(report, "packs.declared_packs_resolvable") is CheckStatus.PASSED
    assert "nothing to resolve" in detail_of(report, "packs.declared_packs_resolvable")


# --- 6. governance ------------------------------------------------------------


def test_governance_fails_without_a_dpa_reference(manifest, environment) -> None:
    """Declaration class: the reference must be present. Its truth is not tested,
    and the check is still a blocker."""
    blank = manifest.model_copy(
        update={"governance": manifest.governance.model_copy(update={"dpa_ref": "   "})}
    )

    report = run(blank, environment)

    assert status_of(report, "governance.dpa_reference_recorded") is CheckStatus.FAILED


def test_governance_fails_when_audit_would_expire_before_bronze(
    manifest, environment
) -> None:
    """**This test bypasses the loader on purpose. Do not "fix" it.**

    `schemas/manifest.py` refuses an inverted retention pair at load (§4.2.6), so
    a manifest that violates it cannot be parsed — the ordinary route into this
    check is closed, and without a bypass the check would go untested forever
    while looking covered.

    `model_copy(update=...)` is the bypass because Pydantic does not re-run
    validators on it. That is the same property `RunManifest.with_*` avoids
    relying on, used here deliberately rather than by accident.

    The obvious "repair" is to switch this to `model_validate`; it will raise,
    and the next repair is to delete the test. That would delete the only
    evidence that the §6.2.2 governance blocker *reports* the condition rather
    than silently depending on the loader having refused it first — and the
    report is where the client sees that retention was checked at all. The
    duplication between loader and check is deliberate; see
    `checks/manifest_checks.py`.
    """
    inverted = manifest.model_copy(
        update={"audit": manifest.audit.model_copy(update={"retention_days": 30})}
    )

    report = run(inverted, environment)

    assert status_of(report, "governance.audit_outlives_bronze") is CheckStatus.FAILED
    assert "outlive" in detail_of(report, "governance.audit_outlives_bronze").lower() or (
        "shorter" in detail_of(report, "governance.audit_outlives_bronze")
    )


def test_declaring_an_external_reference_blocks_for_want_of_an_adapter(
    manifest, environment
) -> None:
    with_reference = manifest_with(external_references=["cardata.brand_catalog"])

    report = run(with_reference, environment)

    assert (
        status_of(report, "governance.external_references_declare_license_mode")
        is CheckStatus.UNAVAILABLE
    )


# --- 7. capacity & recoverability --------------------------------------------


def test_capacity_fails_without_a_declared_restore_point(manifest, environment) -> None:
    blank = manifest.model_copy(
        update={"governance": manifest.governance.model_copy(update={"restore_point": ""})}
    )

    report = run(blank, environment)

    assert status_of(report, "capacity.restore_point_declared") is CheckStatus.FAILED


def test_the_unimplemented_capacity_checks_warn_rather_than_block(
    manifest, environment
) -> None:
    """§6.2.2 puts capacity at "blocker for restore point, warning otherwise",
    so three unimplemented checks here warn. Severity is the spec's, not a
    judgment made at the point of not implementing them."""
    report = run(manifest, environment)

    for check_id in (
        "capacity.space_for_output_and_quarantine",
        "capacity.egress_allowlist_pinned",
        "capacity.kill_switch_reachable",
    ):
        assert status_of(report, check_id) is CheckStatus.UNAVAILABLE
        assert check_id in {line.check_id for line in report.warnings}


# --- the shape the walking skeleton needs ------------------------------------


def test_a_minimal_manifest_still_cannot_reach_ready(manifest, environment) -> None:
    """Honest statement of where this build stands.

    Even the narrowest manifest — file source, no packs, no external references,
    every implemented check green — is blocked, by the eighteen checks nothing
    implements. `ready` arrives when those land, not before, and no flag short
    cuts it.
    """
    report = run(manifest, environment)
    implemented = [line for line in report.results if line.status is CheckStatus.PASSED]

    assert len(implemented) >= 9
    assert report.verdict.value == "blocked"
    assert report.digest is not None, "the digest is complete even while blocked"


def test_the_report_holds_every_category(manifest, environment) -> None:
    from kernel.stages.preflight import Category

    report = run(manifest, environment)

    for category in Category:
        assert report.by_category(category), f"{category.value} reported nothing"


def test_source_dir_fixture_is_used_by_reference(source_dir: Path) -> None:
    """Guards the fixtures themselves: several tests above rewrite the CSV in
    place and would silently test nothing if the path drifted."""
    assert (source_dir / "generation.csv").exists()
