"""Shared preflight fixtures: a manifest and a source that actually exist.

Kept out of the test modules because four of them need the same minimal
Gate 0 shape — a file-bound source, no packs, no external references — which is
the manifest the walking skeleton will use and the only shape this build can
carry to a `ready` verdict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from schemas.manifest import Manifest

KERNEL_VERSION = "0.4.0"

#: Twelve hours after the newest row in `CLEAN_CSV`, so the default 48h
#: freshness window passes. Fixed rather than `datetime.now()`: `run_preflight`
#: takes the clock as an argument precisely so a freshness test can be pinned.
FIXED_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)

#: Deliberately declares no packs and no external references. Both resolve
#: vacuously, which is what lets the digest be complete while BUILD-PLAN item 3
#: is open (see `kernel/stages/preflight/digest.py`).
MINIMAL_MANIFEST: dict = {
    "engagement": "gate0-energy",
    "tenant": "gate0",
    "sector": "energy",
    "canonical_schema": "energy/generation_v1",
    "sources": [
        {
            "name": "scada_export",
            "binding": {
                "kind": "file",
                "connection_ref": "env:SCADA_PATH",
                "objects": ["generation.csv"],
            },
            "format": "csv",
            "encoding": "utf-8",
            # Maps onto `canonical/energy/generation_v1.yaml`, and maps all of
            # it: the schema's key is [plant_code, reading_at] and its freshness
            # field is reading_at, so a partial map now fails two blockers
            # rather than passing quietly.
            "column_map": {
                "Santral": "measurement_point_id",
                "Okuma Zamani": "reading_at",
                "Uretim": "generation_mwh",
            },
        }
    ],
    "bronze": {"location": "/srv/harness/bronze", "retention_days": 365},
    "audit": {"location": "/srv/harness/audit", "retention_days": 365},
    "target": {
        "kind": "schema",
        "connection_ref": "env:STAGING_DSN",
        "canonical": "staging.canonical",
        "staging": "staging.canonical_wip",
        "quarantine": "staging.quarantine",
    },
    "governance": {
        "dpa_ref": "KVIS-2026-GATE0-001",
        "restore_point": "scada-snapshot-nightly",
    },
    "preflight": {"row_count_bounds": {"min": 1, "max": 1000}},
}

CLEAN_CSV = (
    "Santral;Okuma Zamani;Uretim\n"
    "PLANT-01;2026-08-01T00:00:00Z;120.5\n"
    "PLANT-01;2026-08-02T00:00:00Z;130.0\n"
)


def manifest_with(**overrides) -> Manifest:
    return Manifest.model_validate(MINIMAL_MANIFEST | overrides)


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """A directory holding a well-formed source the minimal manifest points at."""
    (tmp_path / "generation.csv").write_text(CLEAN_CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def environment(source_dir: Path) -> dict[str, str]:
    """The environment preflight resolves `env:SCADA_PATH` against.

    Passed explicitly rather than patched into `os.environ`: `run_preflight`
    takes the environment as an argument so that a preflight result never
    depends on ambient process state, and the tests exercise that contract
    rather than working around it.
    """
    return {"SCADA_PATH": str(source_dir), "STAGING_DSN": "postgres://staging"}


@pytest.fixture
def manifest() -> Manifest:
    return manifest_with()
