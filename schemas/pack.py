
from pydantic import BaseModel, Field


class PackRuleRef(BaseModel):
    id: str
    severity: str = "error"

class PackManifest(BaseModel):
    name: str
    version: str
    sector: str | None = None
    description: str
    rules: list[PackRuleRef] = Field(default_factory=list)