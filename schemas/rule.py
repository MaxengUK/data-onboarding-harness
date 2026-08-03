from typing import Any, Literal

from pydantic import BaseModel, Field


class RuleDefinition(BaseModel):
    id: str
    name: str
    description: str
    layer: Literal["L1_structural", "L2_semantic", "L3_cross_entity", "L4_business"]
    severity: Literal["critical", "error", "warning", "info"] = "error"
    params: dict[str, Any] = Field(default_factory=dict)