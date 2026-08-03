"""schemas/json/*.json must stay in step with the Pydantic models (§7.1, §12).

Pydantic is the source of truth and the JSON Schema files are generated from it,
so nothing stops the two drifting apart when someone edits a model and forgets to
re-export. Nothing except this: the schema is regenerated in memory and compared
against what is committed.

Read-only by construction — no file writes, no git calls — so it is safe to run
anywhere and cannot "fix" a drift it was supposed to report.
"""

import pytest

from schemas.export_json_schema import OUT_DIR, SCHEMAS, render_schema

REGENERATE = "run `python -m schemas.export_json_schema` and commit the result"


@pytest.mark.parametrize("filename", sorted(SCHEMAS))
def test_committed_schema_matches_its_model(filename):
    path = OUT_DIR / filename
    assert path.exists(), f"{filename} is missing - {REGENERATE}"

    committed = path.read_text(encoding="utf-8")
    expected = render_schema(SCHEMAS[filename])

    assert committed == expected, (
        f"{filename} is out of date with its Pydantic model - {REGENERATE}"
    )


def test_no_orphan_schema_files():
    """A model that was renamed or deleted must not leave its schema behind."""
    on_disk = {path.name for path in OUT_DIR.glob("*.json")}
    assert on_disk == set(SCHEMAS), (
        f"schemas/json/ does not match the exported model set - {REGENERATE}"
    )


@pytest.mark.parametrize("filename", sorted(SCHEMAS))
def test_render_is_deterministic_and_platform_neutral(filename):
    """P2: the same model must render to the same bytes on any machine."""
    model = SCHEMAS[filename]
    first = render_schema(model)

    assert first == render_schema(model)
    assert "\r" not in first, "CR would make output differ between Windows and Linux"
    assert first.endswith("\n")
