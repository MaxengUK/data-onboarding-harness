"""The §6.2.2 check registry is pinned (CLAUDE.md §6.2.2, §0).

**"Unavailable blocks" only holds while the check is in the registry.** Deleting
an id removes its blocker and turns the verdict green, quietly and with no test
failing anywhere else — which makes deletion the cheapest available bypass of the
whole preflight gate. Demoting a blocker to a warning is the same bypass one step
softer: the check still runs, still fails, and no longer stops anything.

So two sets are frozen here: the check ids, and which of them are blockers.
Adding a check requires updating this file deliberately, which is the correct
amount of friction; removing one or downgrading one turns the build red.

Warning severities are deliberately *not* pinned. A warning becoming a blocker is
a tightening, and tightening does not need a guard rail — the direction that
needs stopping is the one that makes a run easier to start.
"""

from kernel.stages.preflight import BY_ID, REGISTRY, Category, CheckClass, Severity

#: Every §6.2.2 check, transcribed from the spec table. This set is the test.
EXPECTED_CHECK_IDS = frozenset(
    {
        "connectivity.source_reachable",
        "connectivity.principal_is_read_only",
        "connectivity.grants_match_declared_scope",
        "connectivity.target_writable",
        "connectivity.credential_expiry_exceeds_run",
        # Added in 0.6.0 with the canonical schema artifact. Adding an id here
        # is the deliberate act the pinning exists to require — §6.2.2 gained
        # the check in the same change, because a registry that becomes a
        # superset of that table loses the invariant that no check exists
        # outside it.
        "schema.canonical_schema_resolves",
        "schema.mapped_columns_exist",
        "schema.types_match_semantic_types",
        "schema.declared_key_present",
        "schema.no_undeclared_pii_column",
        "encoding.declared_encoding_decodes",
        "encoding.collation_consistent",
        "encoding.locale_matches_observed_shapes",
        "volume.source_not_empty",
        "volume.row_count_within_bounds",
        "volume.max_timestamp_within_freshness_window",
        "volume.no_truncated_extract",
        "packs.declared_packs_resolvable",
        "packs.predicates_exist_in_registry",
        "packs.semantic_types_resolve",
        "packs.no_pass_through_above_client_layer",
        "governance.dpa_reference_recorded",
        "governance.subprocessor_register_current",
        "governance.external_references_declare_license_mode",
        "governance.quarantine_retention_defined",
        "governance.audit_outlives_bronze",
        "capacity.space_for_output_and_quarantine",
        "capacity.restore_point_declared",
        "capacity.egress_allowlist_pinned",
        "capacity.kill_switch_reachable",
    }
)

#: §6.2.2's severity column, with its two documented splits: volume is "blocker
#: for empty/truncated, warning otherwise" and capacity is "blocker for restore
#: point, warning otherwise".
EXPECTED_BLOCKERS = EXPECTED_CHECK_IDS - {
    "volume.row_count_within_bounds",
    "volume.max_timestamp_within_freshness_window",
    "capacity.space_for_output_and_quarantine",
    "capacity.egress_allowlist_pinned",
    "capacity.kill_switch_reachable",
}

#: §6.2.2 (0.5.4) names exactly these three as declaration class.
EXPECTED_DECLARATIONS = frozenset(
    {
        "governance.dpa_reference_recorded",
        "governance.subprocessor_register_current",
        "capacity.restore_point_declared",
    }
)


def test_the_check_id_set_is_pinned() -> None:
    """Removing a check removes its blocker. That must not be a quiet edit."""
    registered = {spec.check_id for spec in REGISTRY}

    assert registered == EXPECTED_CHECK_IDS, (
        "the §6.2.2 check set changed. Adding a check: update EXPECTED_CHECK_IDS "
        "in the same commit. Removing one: it takes its blocker with it and "
        "preflight goes green, so say out loud why that is correct"
    )


def test_the_blocker_set_is_pinned() -> None:
    """Demoting a blocker to a warning is the bypass severity-in-the-registry
    exists to prevent, and it is a one-word diff."""
    blockers = {spec.check_id for spec in REGISTRY if spec.severity is Severity.BLOCKER}

    assert blockers == EXPECTED_BLOCKERS, (
        "a check changed blocking status. A blocker becoming a warning means a "
        "run that used to be stopped now starts with a note nobody has to read"
    )


def test_declaration_class_membership_is_pinned() -> None:
    """§6.2.2 (0.5.4): moving a check from declaration to verification is a
    promotion and needs the means to measure it; the reverse is a downgrade and
    needs saying out loud."""
    declarations = {
        spec.check_id for spec in REGISTRY if spec.check_class is CheckClass.DECLARATION
    }

    assert declarations == EXPECTED_DECLARATIONS


def test_every_category_carries_at_least_one_check() -> None:
    """A category with no checks would be a §6.2.2 heading preflight ignores."""
    covered = {spec.category for spec in REGISTRY}

    assert covered == set(Category)


def test_no_check_id_is_registered_twice() -> None:
    ids = [spec.check_id for spec in REGISTRY]

    assert len(ids) == len(set(ids))
    assert len(BY_ID) == len(REGISTRY)


def test_check_ids_are_namespaced_by_their_category() -> None:
    """The id prefix and the category cannot disagree, because the report groups
    by one and readers scan by the other."""
    for spec in REGISTRY:
        assert spec.check_id.startswith(f"{spec.category.value}."), spec.check_id
