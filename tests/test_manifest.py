"""Manifest validation that is a constitutional rule rather than a type (§7.1).

Type-level constraints — a string is a string, a count is positive — are Pydantic's
and are not re-tested here. What is tested is the handful of places where loading
a manifest is refused on grounds that come from CLAUDE.md rather than from the
shape of the data, because those are the ones a future edit could relax without
anything else noticing.
"""

import pytest
from pydantic import ValidationError

from schemas.manifest import AuditConfig, BronzeConfig, Manifest

BASE = {
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
            "column_map": {"Uretim": "generation_mwh"},
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
}


def manifest(**overrides) -> Manifest:
    return Manifest.model_validate(BASE | overrides)


# --- §4.2.6 retention floor --------------------------------------------------


def test_audit_retention_shorter_than_bronze_is_refused() -> None:
    """The §6.2.2 governance blocker, enforced where the data lives.

    An audit store that expires first leaves the data present with no account of
    what was done to it — P8 failing silently on a date nobody chose.
    """
    with pytest.raises(ValidationError, match="must outlive Bronze"):
        manifest(audit={"location": "/srv/harness/audit", "retention_days": 90})


def test_audit_retention_may_exceed_bronze() -> None:
    """The constraint is one-directional, and the other direction is often right.

    The audit record holds no source values — only hashes, rule ids and transform
    names — so keeping it after the raw data is gone leaves a lawful account of
    processing without extending the life of the personal data.
    """
    loaded = manifest(audit={"location": "/srv/harness/audit", "retention_days": 3650})

    assert loaded.audit.retention_days == 3650


def test_equal_retention_is_accepted() -> None:
    assert manifest().audit.retention_days == 365


def test_the_audit_block_is_mandatory() -> None:
    """No default location: the kernel does not choose where a client's account
    of its own processing lands."""
    without_audit = {key: value for key, value in BASE.items() if key != "audit"}

    with pytest.raises(ValidationError):
        Manifest.model_validate(without_audit)


def test_bronze_retention_is_mandatory() -> None:
    with pytest.raises(ValidationError):
        AuditConfig.model_validate({"location": "/srv/audit"})

    with pytest.raises(ValidationError):
        BronzeConfig.model_validate({"location": "/srv/bronze"})


# --- §4.2.1 substrate pin ----------------------------------------------------


def test_bronze_format_admits_exactly_one_value() -> None:
    """`Literal["parquet"]`, not a free string (§4.2.1).

    A configurable format field advertises that other formats work, and §4.2.1's
    three arguments — the content hash, portability, schemalessness — say they do
    not.
    """
    with pytest.raises(ValidationError):
        BronzeConfig.model_validate(
            {"location": "/srv/bronze", "retention_days": 30, "format": "delta"}
        )


# --- §8 / P5 egress ----------------------------------------------------------


def test_evidence_only_cannot_be_switched_off() -> None:
    with pytest.raises(ValidationError, match="evidence is the only export"):
        manifest(egress={"evidence_only": False})
