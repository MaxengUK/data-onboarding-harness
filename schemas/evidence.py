from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ValidationViolation(BaseModel):
    rule_id: str
    row_index: int | None = None
    column_name: str | None = None
    invalid_value: str | None = None
    message: str

class EvidenceRecord(BaseModel):
    run_id: str
    tenant: str
    engagement: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: str
    violations: list[ValidationViolation] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)