from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ValidationViolation(BaseModel):
    rule_id: str
    row_index: Optional[int] = None
    column_name: Optional[str] = None
    invalid_value: Optional[str] = None
    message: str

class EvidenceRecord(BaseModel):
    run_id: str
    tenant: str
    engagement: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: str
    violations: List[ValidationViolation] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)