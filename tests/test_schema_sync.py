"""schemas/json/*.json must stay in step with the Pydantic models (§7.1, §12).

Pydantic is the source of truth and the JSON Schema files are generated from it,
so nothing stops the two drifting apart when someone edits a model and forgets to
re-export. Nothing except this: the schema is regenerated in memory and compared
against what is committed.

Read-only by construction — no file writes, no git calls — so it is safe to run
anywhere and cannot "fix" a drift it was supposed to report.
"""

import importlib
import inspect
import pathlib

import pytest
from pydantic import BaseModel

from schemas.export_json_schema import OUT_DIR, SCHEMAS, render_schema

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def pydantic_models() -> list[type[BaseModel]]:
    """Every Pydantic model defined under `schemas/` or `kernel/`.

    Discovered by import rather than listed, so a model added anywhere in
    either package is covered without anyone remembering to register it.
    """
    found: dict[str, type[BaseModel]] = {}
    for package in ("schemas", "kernel"):
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            relative = path.relative_to(REPO_ROOT).with_suffix("")
            module = importlib.import_module(str(relative).replace("\\", ".").replace("/", "."))
            for obj in vars(module).values():
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseModel)
                    and obj is not BaseModel
                    and obj.__module__.startswith(("schemas", "kernel"))
                ):
                    found[f"{obj.__module__}.{obj.__name__}"] = obj
    return list(found.values())

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


# --- unknown keys are refused, not ignored -----------------------------------


def test_every_model_forbids_unknown_fields():
    """A typo in a client's manifest must not fall back to a default in silence.

    Pydantic ignores unknown keys by default, so `retention_day` instead of
    `retention_days` loaded cleanly and the run used 90 days while the client
    had written 5 — no error, no warning, and a quarantine lifetime nobody
    chose. Forty-three fields carry defaults a typo could reach that way.

    Found in `schemas/rule.py` first, where the same default let a written
    `band: money` be dropped silently over a 0.91 hold rate. The manifest case
    is worse: it is hand-authored in a client environment.

    Scans rather than lists, so a model added without the config is a red build
    rather than an omission somebody has to notice. There are **no exceptions
    today**; if one is ever justified, name it here with its reason rather than
    weakening the scan.
    """
    permissive = [
        f"{model.__module__}.{model.__name__}"
        for model in pydantic_models()
        if model.model_config.get("extra") != "forbid"
    ]

    assert not permissive, (
        f"these models silently ignore unknown fields: {permissive}. A key the "
        f"schema does not know is a typo, and a typo that falls back to a "
        f"default is a setting the author believes is in effect and is not"
    )
