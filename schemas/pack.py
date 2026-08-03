from typing import List, Optional
from pydantic import BaseModel, Field

class PackRuleRef(BaseModel):
    id: str
    severity: str = "error"

class PackManifest(BaseModel):
    name: str
    version: str
    sector: Optional[str] = None
    description: str
    rules: List[PackRuleRef] = Field(default_factory=list)