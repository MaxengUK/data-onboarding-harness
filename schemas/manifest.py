from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SourceBinding(BaseModel):
    kind: Literal["database", "file"]
    dialect: str | None = None
    connection_ref: str
    objects: list[str]
    posture: Literal["replica", "snapshot", "primary"] = "replica"


class SourceConfig(BaseModel):
    name: str
    binding: SourceBinding
    format: str
    encoding: str = "utf-8"
    locale: str = "tr-TR"
    column_map: dict[str, str]


class BronzeConfig(BaseModel):
    location: str = Field(
        description=(
            "A path abstraction, not a local path (§4.2.2). Resolved by "
            "kernel.storage.resolve_location; local FS, S3 and Azure Blob are "
            "equally valid, though only local is implemented in this build."
        )
    )
    #: Pinned, not a toggle (§4.2.1). The key exists so a future second substrate
    #: can be added without a schema shape change, and today exactly one value
    #: loads. It must never be widened to a free string "for flexibility": a
    #: configurable format field advertises that other formats work, and §4.2.1's
    #: three arguments — the content hash, portability, schemalessness — say they
    #: do not.
    #:
    #: `Literal` rather than the `egress.evidence_only` treatment (a bool with a
    #: validator that refuses False) because the two differ in what a second
    #: value would mean. A second egress mode would need its own gate, so the
    #: field stays open and the refusal is behavioural. A second Bronze format is
    #: a new substrate implementation; until one exists there is nothing for the
    #: type to admit, and `Literal` says exactly that at the type level.
    format: Literal["parquet"] = "parquet"
    partition_by: str = "batch_id"
    retention_days: int = Field(..., gt=0, description="Mandatory — preflight fails if unset")


class TargetConfig(BaseModel):
    kind: str
    connection_ref: str
    canonical: str
    staging: str
    quarantine: str
    retention_days: int = 90


class ArmingConfig(BaseModel):
    form: Literal["interactive", "standing"] = "interactive"
    idp_ref: str = "client"
    ttl_minutes: int = 60


class PreflightConfig(BaseModel):
    sample_limit: int = 200
    freshness_window_hours: int = 48
    row_count_bounds: dict[str, int] = Field(default_factory=lambda: {"min": 1, "max": 10000000})
    estimated_run_minutes: int = 45
    arming: ArmingConfig = Field(default_factory=ArmingConfig)


class EgressConfig(BaseModel):
    evidence_only: bool = True
    k_anonymity_min: int = 5

    @field_validator("evidence_only")
    @classmethod
    def reject_non_evidence_egress(cls, value: bool) -> bool:
        """`evidence_only: false` is a silent bypass of P5, so it is refused.

        The field stays a bool rather than becoming Literal[True] so that a
        future version supporting a second egress mode can allow it without a
        schema shape change. Until such a mode exists with its own gate, the
        only honest behaviour is to fail at load time rather than at the
        boundary, where "off" would mean the emitter is simply not consulted.
        """
        if not value:
            raise ValueError(
                "egress.evidence_only=false is not supported in this version: "
                "evidence is the only export (P5), and there is no second "
                "egress path for the gate to police"
            )
        return value


class Manifest(BaseModel):
    engagement: str
    tenant: str
    sector: str
    canonical_schema: str
    mode: Literal["discover", "execute"] = "execute"
    cadence: Literal["one_shot", "continuous"] = "one_shot"
    sources: list[SourceConfig]
    bronze: BronzeConfig
    target: TargetConfig
    preflight: PreflightConfig = Field(default_factory=PreflightConfig)
    packs: list[str] = Field(default_factory=list)
    external_references: list[str] = Field(default_factory=list)
    egress: EgressConfig = Field(default_factory=EgressConfig)