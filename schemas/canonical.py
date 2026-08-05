"""The canonical schema — the target both sides map onto (CLAUDE.md §7.6).

`manifest.canonical_schema` names one, `map` resolves the column map onto it,
and `emit` writes it. It is what makes a `column_map` mean anything: the map's
right-hand side is a canonical *field name*, and without a schema saying what
those fields are, the chain from a client's column to a semantic type has no
middle — which is exactly where three §6.2.2 checks stopped.

**Not a pack.** One id resolves to exactly one artifact: no layering, no merge,
no precedence, no version ranges. §7.4's layering exists because rules
*accumulate* — a `client` rule refines a `core` one, and that accumulation is
what §13 measures. A canonical schema is the opposite kind of object: the fixed
target both sides map onto. Give it precedence and a client pack can quietly
change what `sales_v2` means, at which point two engagements emit different
"canonical" output under one name.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from kernel.registries import SemanticType


class CanonicalField(BaseModel):
    """One field of the canonical schema.

    No physical type, deliberately. `emit` will need one to create a target
    table, and until a target adapter exists there is nothing to consume it — a
    field with no reader is a field that drifts out of step with reality while
    looking authoritative.
    """

    model_config = {"frozen": True}

    name: str = Field(min_length=1)
    semantic_type: SemanticType = Field(
        description=(
            "Resolved against the closed kernel registry (§7.5). This is the "
            "binding rules attach to, and the mechanism reuse_ratio measures."
        )
    )
    required: bool = Field(
        default=True,
        description="An unmapped required field fails the run at `map` (§6, P7)",
    )


class CanonicalSchema(BaseModel):
    """A canonical schema artifact, loaded from `canonical/` (§7.6)."""

    model_config = {"frozen": True}

    id: str = Field(
        min_length=1,
        description=(
            "Matches manifest.canonical_schema exactly, e.g. 'energy/generation_v1'. "
            "The version is part of the id rather than a field of its own: v2 is a "
            "different schema, not a new version of this one, so evolution is a new "
            "artifact and a deliberate re-map rather than an in-place edit that "
            "silently changes what a client's existing output means."
        )
    )
    fields: tuple[CanonicalField, ...] = Field(min_length=1)
    key: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "The declared key or unique column combination (§6.2.2). `resolve` "
            "needs one before it can cluster at all, and preflight blocks "
            "without it rather than letting discovery recover it silently."
        ),
    )
    freshness_field: str = Field(
        min_length=1,
        description=(
            "Which field the §6.2.2 freshness window is measured against. "
            "Declared rather than inferred from 'the only date-typed field': "
            "sales_v2 carries order_date beside delivery_date, so a second one "
            "is the normal case and inference would silently pick a side."
        ),
    )

    @model_validator(mode="after")
    def references_resolve_within_the_schema(self) -> CanonicalSchema:
        """`key` and `freshness_field` must name fields this schema declares.

        Checked here rather than at use because an artifact naming a field it
        does not have is broken on its own terms — it should fail when it is
        read, not when a run happens to touch the part that is wrong.
        """
        names = [field.name for field in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.id}: duplicate field names in the schema")

        declared = set(names)
        missing_key = [name for name in self.key if name not in declared]
        if missing_key:
            raise ValueError(
                f"{self.id}: key names {missing_key} which the schema does not declare"
            )

        if self.freshness_field not in declared:
            raise ValueError(
                f"{self.id}: freshness_field {self.freshness_field!r} is not a "
                f"field of this schema"
            )

        return self

    def field(self, name: str) -> CanonicalField | None:
        return next((field for field in self.fields if field.name == name), None)

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)
