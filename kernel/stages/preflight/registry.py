"""The §6.2.2 check list, as data (CLAUDE.md §6.2.2, §6.2.3).

**Every check §6.2.2 names is registered here, implemented or not.** That is the
whole design. An implementation is looked up by check id; a registered check with
no implementation reports `UNAVAILABLE`, and a blocker that did not run blocks.
So "forgetting to write a check" is not a way to pass preflight — the check is
already in the list, already a blocker, and already failing the run.

The alternative — registering checks as they are implemented — makes the verdict
a statement about how much of preflight got built rather than about the source,
and does it silently. This repo has found that shape of defect six times; here it
is designed out rather than watched for.

**Severity is fixed here and nowhere else.** No manifest key, environment
variable or CLI flag changes it. A configurable severity is a one-line bypass
that moves every blocker to `warning`, which is the same argument that keeps
`overwrite` off the stores, `--force` off preflight, and `evidence_only: false`
unloadable. `tests/test_preflight_registry.py` pins the blocker set so that
demoting one is a red build rather than a diff nobody reads.

**Deleting a check is the other bypass**, and it is quieter: an id removed from
this tuple takes its blocker with it and preflight goes green. The same test
pins the id set, so removal fails and addition requires updating the test
deliberately.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from kernel.stages.preflight.result import Category, CheckClass, Severity


class CheckSpec(BaseModel):
    """One §6.2.2 check, declared independently of whether it can be run."""

    model_config = {"frozen": True}

    check_id: str
    category: Category
    severity: Severity
    check_class: CheckClass
    description: str


def _spec(
    check_id: str,
    category: Category,
    severity: Severity,
    description: str,
    check_class: CheckClass = CheckClass.VERIFICATION,
) -> CheckSpec:
    return CheckSpec(
        check_id=check_id,
        category=category,
        severity=severity,
        check_class=check_class,
        description=description,
    )


#: §6.2.2's table, transcribed. Severities are the "typical severity" column,
#: which is normative here: the column gives one severity per *category* except
#: where it splits ("blocker for empty/truncated, warning otherwise"; "blocker
#: for restore point, warning otherwise"), and those splits are honoured below.
REGISTRY: tuple[CheckSpec, ...] = (
    # --- Connectivity & privilege -------------------------------------------
    _spec(
        "connectivity.source_reachable",
        Category.CONNECTIVITY,
        Severity.BLOCKER,
        "The bound source can be reached and read",
    ),
    _spec(
        "connectivity.principal_is_read_only",
        Category.CONNECTIVITY,
        Severity.BLOCKER,
        "The connection principal holds no write, DDL or DML privilege on any "
        "source object, verified by inspecting granted privileges (§6.2.1)",
    ),
    _spec(
        "connectivity.grants_match_declared_scope",
        Category.CONNECTIVITY,
        Severity.BLOCKER,
        "Granted access covers exactly the objects and columns in column_map "
        "and no wider (§6.2.1)",
    ),
    _spec(
        "connectivity.target_writable",
        Category.CONNECTIVITY,
        Severity.BLOCKER,
        "The declared target is writable and distinct from the source",
    ),
    _spec(
        "connectivity.credential_expiry_exceeds_run",
        Category.CONNECTIVITY,
        Severity.BLOCKER,
        "The credential's remaining window exceeds preflight.estimated_run_minutes",
    ),
    # --- Schema conformance --------------------------------------------------
    _spec(
        "schema.mapped_columns_exist",
        Category.SCHEMA,
        Severity.BLOCKER,
        "Every column named in column_map is present in the source",
    ),
    _spec(
        "schema.types_match_semantic_types",
        Category.SCHEMA,
        Severity.BLOCKER,
        "Source types are compatible with the semantic types bound to them",
    ),
    _spec(
        "schema.declared_key_present",
        Category.SCHEMA,
        Severity.BLOCKER,
        "The declared key or unique column combination is present",
    ),
    _spec(
        "schema.no_undeclared_pii_column",
        Category.SCHEMA,
        Severity.BLOCKER,
        "No column outside column_map carries a PII-typed shape — without this, "
        "a column nobody mapped still reaches profile and its statistics reach "
        "the evidence artifact (§6.2.2)",
    ),
    # --- Encoding & locale ---------------------------------------------------
    _spec(
        "encoding.declared_encoding_decodes",
        Category.ENCODING,
        Severity.BLOCKER,
        "The declared encoding decodes the source without replacement characters",
    ),
    _spec(
        "encoding.collation_consistent",
        Category.ENCODING,
        Severity.BLOCKER,
        "Collation is consistent across the bound objects",
    ),
    _spec(
        "encoding.locale_matches_observed_shapes",
        Category.ENCODING,
        Severity.BLOCKER,
        "The declared locale matches observed date and decimal shapes",
    ),
    # --- Volume & freshness --------------------------------------------------
    _spec(
        "volume.source_not_empty",
        Category.VOLUME,
        Severity.BLOCKER,
        "The source holds at least one row",
    ),
    _spec(
        "volume.row_count_within_bounds",
        Category.VOLUME,
        Severity.WARNING,
        "The row count lies inside preflight.row_count_bounds",
    ),
    _spec(
        "volume.max_timestamp_within_freshness_window",
        Category.VOLUME,
        Severity.WARNING,
        "The newest record is inside preflight.freshness_window_hours",
    ),
    _spec(
        "volume.no_truncated_extract",
        Category.VOLUME,
        Severity.BLOCKER,
        "The extract shows no sign of having been cut short",
    ),
    # --- Packs & rules -------------------------------------------------------
    _spec(
        "packs.declared_packs_resolvable",
        Category.PACKS,
        Severity.BLOCKER,
        "Every declared pack resolves at its declared version",
    ),
    _spec(
        "packs.predicates_exist_in_registry",
        Category.PACKS,
        Severity.BLOCKER,
        "Every predicate a rule references exists in the closed registry (§7.5)",
    ),
    _spec(
        "packs.semantic_types_resolve",
        Category.PACKS,
        Severity.BLOCKER,
        "Every applies_to.semantic_type resolves in the closed registry (§7.5)",
    ),
    _spec(
        "packs.no_pass_through_above_client_layer",
        Category.PACKS,
        Severity.BLOCKER,
        "No rule corroborated by a pass_through reference lives above the "
        "client layer (§9.6)",
    ),
    # --- Governance ----------------------------------------------------------
    _spec(
        "governance.dpa_reference_recorded",
        Category.GOVERNANCE,
        Severity.BLOCKER,
        "A DPA/KVİS reference is recorded for this engagement",
        check_class=CheckClass.DECLARATION,
    ),
    _spec(
        "governance.subprocessor_register_current",
        Category.GOVERNANCE,
        Severity.BLOCKER,
        "The sub-processor register is present and current (§17)",
        check_class=CheckClass.DECLARATION,
    ),
    _spec(
        "governance.external_references_declare_license_mode",
        Category.GOVERNANCE,
        Severity.BLOCKER,
        "Every declared external reference declares a license_mode (§9.6)",
    ),
    _spec(
        "governance.quarantine_retention_defined",
        Category.GOVERNANCE,
        Severity.BLOCKER,
        "A quarantine retention target is defined (§6.1)",
    ),
    _spec(
        "governance.audit_outlives_bronze",
        Category.GOVERNANCE,
        Severity.BLOCKER,
        "audit.retention_days is at least bronze.retention_days (§4.2.6)",
    ),
    # --- Capacity & recoverability -------------------------------------------
    _spec(
        "capacity.space_for_output_and_quarantine",
        Category.CAPACITY,
        Severity.WARNING,
        "The target location has room for canonical output and quarantine",
    ),
    _spec(
        "capacity.restore_point_declared",
        Category.CAPACITY,
        Severity.BLOCKER,
        "A client-side restore point or snapshot is declared (§6.2.2)",
        check_class=CheckClass.DECLARATION,
    ),
    _spec(
        "capacity.egress_allowlist_pinned",
        Category.CAPACITY,
        Severity.WARNING,
        "The §8 egress allowlist version is pinned for this run",
    ),
    _spec(
        "capacity.kill_switch_reachable",
        Category.CAPACITY,
        Severity.WARNING,
        "The kill switch defined against the §6.3 publication boundary is reachable",
    ),
)

BY_ID: dict[str, CheckSpec] = {spec.check_id: spec for spec in REGISTRY}


#: Populated by `@implements`. A registered id absent from here is `UNAVAILABLE`
#: — the framework derives that, so nobody has to remember to write a stub.
IMPLEMENTATIONS: dict[str, Callable] = {}


def implements(check_id: str):
    """Bind an implementation to a registered check id.

    Registering an id that §6.2.2 does not contain is refused: the registry is
    the transcription of the spec, and a check invented in a `checks/` module
    would appear in reports without ever having been specified.
    """

    def bind(function):
        if check_id not in BY_ID:
            raise KeyError(
                f"{check_id!r} is not a registered §6.2.2 check; add it to "
                f"REGISTRY with a category, severity and class first"
            )
        if check_id in IMPLEMENTATIONS:
            raise KeyError(f"{check_id!r} already has an implementation")
        IMPLEMENTATIONS[check_id] = function
        return function

    return bind
