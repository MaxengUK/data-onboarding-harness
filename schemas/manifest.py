from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SourceBinding(BaseModel):
    kind: Literal["database", "file"]
    dialect: Optional[str] = None
    connection_ref: str
    objects: List[str]
    posture: Literal["replica", "snapshot", "primary"] = "replica"


class SourceConfig(BaseModel):
    name: str
    binding: SourceBinding
    format: str
    encoding: str = "utf-8"
    locale: str = "tr-TR"
    column_map: Dict[str, str]


class BronzeConfig(BaseModel):
    location: str
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
    row_count_bounds: Dict[str, int] = Field(default_factory=lambda: {"min": 1, "max": 10000000})
    estimated_run_minutes: int = 45
    arming: ArmingConfig = Field(default_factory=ArmingConfig)


class EgressConfig(BaseModel):
    evidence_only: bool = True
    k_anonymity_min: int = 5


class Manifest(BaseModel):
    engagement: str
    tenant: str
    sector: str
    canonical_schema: str
    mode: Literal["discover", "execute"] = "execute"
    cadence: Literal["one_shot", "continuous"] = "one_shot"
    sources: List[SourceConfig]
    bronze: BronzeConfig
    target: TargetConfig
    preflight: PreflightConfig = Field(default_factory=PreflightConfig)
    packs: List[str] = Field(default_factory=list)
    external_references: List[str] = Field(default_factory=list)
    egress: EgressConfig = Field(default_factory=EgressConfig)