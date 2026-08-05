"""Generate JSON Schema files from the Pydantic models (CLAUDE.md §14).

Run it as either of these, from anywhere:

    python -m schemas.export_json_schema
    python schemas/export_json_schema.py

Output is canonical: sorted keys, fixed indent, LF endings, trailing newline.
Determinism is a requirement, not a nicety — a generated artifact whose bytes
depend on the machine that produced it cannot be diffed in review or asserted
against in CI (P2, §12). tests/test_schema_sync.py holds this file honest.
"""

import json
import sys
from pathlib import Path

# Run as a plain script, sys.path[0] is schemas/ rather than the repo root, so
# the `schemas` package itself is not importable. Under -m it already is.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import (
    AuditRecord,
    CanonicalSchema,
    EvidenceArtifact,
    Manifest,
    PackManifest,
    Rule,
)

SCHEMAS = {
    "manifest.schema.json": Manifest,
    "canonical.schema.json": CanonicalSchema,
    "pack.schema.json": PackManifest,
    "rule.schema.json": Rule,
    "evidence.schema.json": EvidenceArtifact,
    # In-boundary only (§12). Exported here because it is a schema like any
    # other; that it has a JSON Schema does not make it exportable data.
    "audit.schema.json": AuditRecord,
}

OUT_DIR = Path(__file__).resolve().parent / "json"


def render_schema(model) -> str:
    """Canonical JSON Schema text for one model.

    Keys are left in Pydantic's own order so that `properties` still reads in
    field-declaration order; sorting them would be marginally more stable across
    Pydantic upgrades but would make the generated schema harder to read against
    the model it came from.
    """
    return json.dumps(
        model.model_json_schema(),
        indent=2,
        ensure_ascii=True,
    ) + "\n"


def export_schemas() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        # newline="\n" explicitly: the default would translate to CRLF on
        # Windows and produce different bytes than the same run on Linux CI.
        (OUT_DIR / filename).write_text(
            render_schema(model), encoding="utf-8", newline="\n"
        )
    print(f"JSON Schemas successfully exported to {OUT_DIR}")


if __name__ == "__main__":
    export_schemas()
