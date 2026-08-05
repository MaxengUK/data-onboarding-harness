"""**This module does not implement CLAUDE.md §7.4. Do not write code against it.**

The same sketch-predates-the-spec problem as `schemas/rule.py`, and the missing
pieces are the ones §6.2.2's pack checks actually need: there is no `layer`
(`core` / `sector` / `client`), so precedence and the §7.4 "narrower layer wins"
resolution cannot be expressed; no `overrides:` declaration, so a client rule
shadowing a core rule cannot be rejected at load as §7.4 requires; and no
`corroborated_by`, so §9.6's rule that a `pass_through`-corroborated rule may not
live above the `client` layer has nothing to inspect.

Version strings are equally provisional: §7.1 declares packs as
`core/tr-core@^1.4`, a range, and nothing here parses or resolves one.

Closing this is BUILD-PLAN item 3, together with the predicate registry and the
rule schema. Until then preflight reports all four §6.2.2 pack checks as
`unavailable` rather than writing them against these fields — a check built on a
model the spec does not recognise would make the gap look closed while verifying
something nobody specified.
"""

from pydantic import BaseModel, Field


class PackRuleRef(BaseModel):

    model_config = {"extra": "forbid"}
    id: str
    severity: str = "error"

class PackManifest(BaseModel):
    """**Provisional. Not the pack schema this version of the Harness loads.**

    Published so the artifact set is complete, not because anything reads it.
    Layer, precedence and override declarations are absent, so a pack authored
    against these fields cannot be resolved by a later version.
    """

    model_config = {"extra": "forbid"}

    name: str
    version: str
    sector: str | None = None
    description: str
    rules: list[PackRuleRef] = Field(default_factory=list)