"""The canonical schema artifact and its resolver (CLAUDE.md §7.6).

Two properties carry this file.

`test_two_artifacts_claiming_one_id_is_an_error` is where the difference from a
pack loader stops being documentary. §7.4 resolves a collision by layer, because
rules are *meant* to accumulate; resolving one here would mean an id names
different things depending on where the resolver looked first, and two
engagements could emit different "canonical" output under one name.

`test_the_shipped_artifacts_load` is the unglamorous one that matters most: the
two artifacts under `canonical/` are what Gate 0 and Gate 1 map onto, and a
schema that does not load is a run that cannot start.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from kernel.canonical import (
    AmbiguousCanonicalSchema,
    MalformedCanonicalSchema,
    UnknownCanonicalSchema,
    available_ids,
    bind_manifest,
    resolve_canonical_schema,
)
from kernel.registries import SemanticType
from schemas.canonical import CanonicalSchema
from tests.conftest import manifest_with

VALID = {
    "id": "energy/test_v1",
    "grain": {"entity": "measurement_point", "period": "instant", "layout": "wide"},
    "fields": [
        {"name": "measurement_point_id", "semantic_type": "opaque_key", "required": True},
        {"name": "reading_at", "semantic_type": "date", "required": True},
        {"name": "generation_mwh", "semantic_type": "energy_quantity"},
    ],
    "key": ["measurement_point_id", "reading_at"],
    "freshness_field": "reading_at",
}


def write_schema(directory: Path, name: str, document: dict) -> Path:
    import yaml

    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


# --- the centre ---------------------------------------------------------------


def test_two_artifacts_claiming_one_id_is_an_error(tmp_path: Path) -> None:
    """Not a precedence decision. §7.4 would resolve this by layer; here there
    is no tie to break, because a canonical schema is a fixed target rather than
    something that accumulates."""
    write_schema(tmp_path, "first", VALID)
    write_schema(tmp_path, "second", VALID)

    with pytest.raises(AmbiguousCanonicalSchema) as excinfo:
        resolve_canonical_schema("energy/test_v1", tmp_path)

    assert "no precedence rule" in str(excinfo.value)


def test_the_shipped_artifacts_load() -> None:
    """`canonical/` is what Gate 0 and Gate 1 map onto."""
    assert set(available_ids()) == {"energy/generation_v1", "automotive/sales_v2"}

    for schema_id in available_ids():
        schema = resolve_canonical_schema(schema_id)
        assert schema.id == schema_id
        assert schema.fields


def test_sales_v2_declares_which_date_carries_freshness() -> None:
    """The concrete reason §7.6 requires `freshness_field` rather than inferring.

    Two date-typed fields, and they answer different questions: an extract is
    fresh with respect to when orders were taken, not to when cars happened to
    be handed over.
    """
    schema = resolve_canonical_schema("automotive/sales_v2")
    dated = [f.name for f in schema.fields if f.semantic_type is SemanticType.DATE]

    assert len(dated) > 1, "the ambiguity this field exists to resolve is gone"
    assert schema.freshness_field == "order_date"


# --- artifact validation ------------------------------------------------------


def test_a_key_naming_an_absent_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="does not declare"):
        CanonicalSchema.model_validate(VALID | {"key": ["not_a_field"]})


def test_a_freshness_field_that_is_not_a_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a field"):
        CanonicalSchema.model_validate(VALID | {"freshness_field": "invented"})


def test_duplicate_field_names_are_refused() -> None:
    doubled = VALID | {"fields": VALID["fields"] + [VALID["fields"][0]]}

    with pytest.raises(ValidationError, match="duplicate field"):
        CanonicalSchema.model_validate(doubled)


def test_an_unregistered_semantic_type_is_refused() -> None:
    """The chain terminates in the closed kernel registry (§7.5), so a schema
    cannot introduce a type by naming one."""
    invented = VALID | {
        "fields": [{"name": "x", "semantic_type": "musteri_gsm", "required": True}],
        "key": ["x"],
        "freshness_field": "x",
    }

    with pytest.raises(ValidationError):
        CanonicalSchema.model_validate(invented)


def test_a_malformed_artifact_names_itself(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("id: x\nfields: []\n", encoding="utf-8")

    with pytest.raises(MalformedCanonicalSchema, match="broken.yaml"):
        resolve_canonical_schema("x", tmp_path)


# --- resolution ---------------------------------------------------------------


def test_an_unknown_id_is_refused(tmp_path: Path) -> None:
    write_schema(tmp_path, "one", VALID)

    with pytest.raises(UnknownCanonicalSchema, match="energy/absent_v1"):
        resolve_canonical_schema("energy/absent_v1", tmp_path)


def test_the_declared_id_wins_over_the_filename(tmp_path: Path) -> None:
    """A file's location is an operational convenience. If the path decided,
    moving a file would silently redefine a schema."""
    write_schema(tmp_path, "misleading_name", VALID)

    assert resolve_canonical_schema("energy/test_v1", tmp_path).id == "energy/test_v1"


def test_a_missing_directory_is_refused_rather_than_treated_as_empty(
    tmp_path: Path,
) -> None:
    with pytest.raises(UnknownCanonicalSchema):
        resolve_canonical_schema("energy/test_v1", tmp_path / "absent")


# --- the binding chain --------------------------------------------------------


def test_the_chain_reaches_a_semantic_type() -> None:
    """source column → canonical field → semantic type.

    Before §7.6 the chain ended at the field name, which is why §7.5's "rules
    bind to semantic types" had nothing to bind through and §13's `reuse_ratio`
    had nothing to measure.
    """
    binding = bind_manifest(manifest_with())

    by_source = {column.source_column: column for column in binding.columns}
    assert by_source["Uretim"].canonical_field == "generation_mwh"
    assert by_source["Uretim"].semantic_type is SemanticType.ENERGY_QUANTITY
    assert by_source["Okuma Zamani"].semantic_type is SemanticType.DATE


def test_the_freshness_column_is_resolved_back_to_the_source() -> None:
    """The probe needs a *source* column name, not a canonical one."""
    binding = bind_manifest(manifest_with())

    assert binding.freshness_column == "Okuma Zamani"


def test_mapping_to_a_field_the_schema_does_not_declare_is_reported() -> None:
    stray = manifest_with(
        sources=[
            {
                "name": "scada_export",
                "binding": {
                    "kind": "file",
                    "connection_ref": "env:SCADA_PATH",
                    "objects": ["generation.csv"],
                },
                "format": "csv",
                "column_map": {"Uretim": "invented_field"},
            }
        ]
    )

    binding = bind_manifest(stray)

    assert binding.unknown_fields == ("invented_field",)
    assert binding.resolved, "the schema resolved; only the mapping is wrong"


def test_an_unresolvable_schema_yields_an_error_not_an_exception() -> None:
    """Preflight turns this into a check result, so the binding reports rather
    than raises — a raise here would make one bad id abort every other check."""
    binding = bind_manifest(manifest_with(canonical_schema="energy/absent_v9"))

    assert not binding.resolved
    assert binding.error is not None
    assert binding.columns == ()


# --- grain (§7.6) -------------------------------------------------------------


def test_the_shipped_schemas_declare_a_grain() -> None:
    """A key says which rows are distinct; it does not say what a row *is*."""
    for schema_id in available_ids():
        grain = resolve_canonical_schema(schema_id).grain
        assert grain.entity
        assert grain.period in ("instant", "interval", "none")
        assert grain.layout in ("wide", "long")


def test_the_energy_entity_is_named_by_role_not_by_level() -> None:
    """§7.6, and the reason `plant_code` was wrong.

    A client measures at the plant, another at the inverter, a third at the
    string, a fourth at the meter. All four are correct and all four are the
    same role — the thing readings are attributed to — which is how IEC 61968-9
    defines `UsagePoint`. `canonical/` is not layered, so one schema has to fit
    all four, and a level-named field fits exactly one.
    """
    schema = resolve_canonical_schema("energy/generation_v1")

    assert schema.grain.entity == "measurement_point"
    assert "measurement_point_id" in schema.field_names
    assert not any(
        level in name
        for name in schema.field_names
        for level in ("plant", "inverter", "string", "meter_id")
    ), "a field named after one client's organisational level"


def test_the_wide_layout_is_declared_rather_than_assumed() -> None:
    """It was invisible until written down.

    Under `long` the same readings arrive as (point, time, measurement_type,
    value) and the key gains a column — a different artifact, not an edit to
    this one.
    """
    schema = resolve_canonical_schema("energy/generation_v1")

    assert schema.grain.layout == "wide"
    assert schema.key == ("measurement_point_id", "reading_at")
    assert "measurement_type" not in schema.field_names


def test_grain_is_required_and_refuses_an_unknown_layout() -> None:
    without_grain = {key: value for key, value in VALID.items() if key != "grain"}

    with pytest.raises(ValidationError):
        CanonicalSchema.model_validate(without_grain)

    with pytest.raises(ValidationError):
        CanonicalSchema.model_validate(
            VALID | {"grain": VALID["grain"] | {"layout": "pivoted"}}
        )


def test_granularity_is_not_part_of_the_key() -> None:
    """Level is an input to rules, not to identity.

    "Generation must not exceed nameplate capacity" needs to know whether the
    point is a plant or a string; "one reading per point per instant" does not.
    Putting the level in the key would make identity vary by client, which is
    what role-naming exists to prevent.
    """
    schema = resolve_canonical_schema("energy/generation_v1")

    assert schema.key == ("measurement_point_id", "reading_at")
    assert not hasattr(schema.grain, "level")
