import json
from pathlib import Path

from schemas import EvidenceRecord, Manifest, PackManifest, RuleDefinition

SCHEMAS = {
    "manifest.schema.json": Manifest,
    "pack.schema.json": PackManifest,
    "rule.schema.json": RuleDefinition,
    "evidence.schema.json": EvidenceRecord,
}

def export_schemas():
    out_dir = Path(__file__).parent / "json"
    out_dir.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema_data = model.model_json_schema()
        (out_dir / filename).write_text(json.dumps(schema_data, indent=2), encoding="utf-8")
    print(f"JSON Schemas successfully exported to {out_dir}")

if __name__ == "__main__":
    export_schemas()