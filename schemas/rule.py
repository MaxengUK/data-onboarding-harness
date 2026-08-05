"""**This module does not implement CLAUDE.md §7.2/§7.3. Do not write code against it.**

It is an early sketch that predates the rule schema the spec now describes, and
the two have almost nothing in common. §7.2 requires `stage`, `kind`, `state`,
`applies_to.semantic_type`, `expression`, `repair`, and `provenance`; §7.3 adds
the discovered-rule shape (`determinant`, `dependent`, `evidence`,
`corroborated_by`). None of those exist here. What does exist — `layer:
L1_structural | L2_semantic | L3_cross_entity | L4_business` — appears nowhere in
the spec at all.

The divergence is recorded rather than patched because closing it is BUILD-PLAN
item 3's work and not a side effect of another item: the predicate registry, the
semantic type binding, and the pack layer model have to land together, and a
rule schema written before them would be a third guess at the same thing.

**The concrete risk this docstring exists to prevent** is a preflight or loader
check written against these fields, which would then have to be rewritten *and*
would make the gap look closed. §6.2.2's "every referenced predicate exists in
the registry" and "every `applies_to.semantic_type` resolves" are reported as
`unavailable` for exactly this reason — that is the honest state, and a check
written against `layer` would replace it with a false green.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class RuleDefinition(BaseModel):
    """**Provisional. Not the rule schema this version of the Harness executes.**

    Published so the artifact set is complete, not because anything reads it.
    The executable rule shape lands with the predicate registry; until then no
    pack should be authored against these fields.
    """

    id: str
    name: str
    description: str
    layer: Literal["L1_structural", "L2_semantic", "L3_cross_entity", "L4_business"]
    severity: Literal["critical", "error", "warning", "info"] = "error"
    params: dict[str, Any] = Field(default_factory=dict)