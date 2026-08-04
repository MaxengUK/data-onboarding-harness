from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class AuditConfig(BaseModel):
    """The audit store's location and retention (§4.2.6).

    A separate store *beside* Bronze, never inside it. `AuditRecord`s are
    produced by `normalize`, i.e. after `ingest`, so writing them into a Bronze
    partition would be a post-`ingest` write to Bronze (P10) and would leave that
    partition without a stable content hash, collapsing §4.2.5 layer 3.

    There is no `format` key here, unlike `BronzeConfig`. The absence is
    deliberate: §4.2.1 pins Bronze's substrate because §4.2.1's three arguments
    are about Bronze, and the audit store's format is an internal kernel matter
    that no manifest has a reason to name. A key that cannot vary is worth
    exposing only where a reader would otherwise expect variance, and §7.1 never
    invited it here.
    """

    location: str = Field(
        description=(
            "A path abstraction, resolved the same way as bronze.location "
            "(§4.2.2). Parallel to Bronze, never a path inside it."
        )
    )
    retention_days: int = Field(
        ...,
        gt=0,
        description="Mandatory, and floored at bronze.retention_days (§4.2.6)",
    )


class TargetConfig(BaseModel):
    kind: str
    connection_ref: str
    canonical: str
    staging: str
    quarantine: str
    #: `gt=0` to match `BronzeConfig.retention_days`. Quarantine holds raw
    #: violating records (§6.1), so a zero or negative retention is the same
    #: category of undeclared-lifetime problem, and the §6.2.2 governance check
    #: "quarantine retention target defined" has nothing to affirm without it.
    retention_days: int = Field(90, gt=0)


class RowCountBounds(BaseModel):
    """Declared row count envelope for the bound source (§6.2.2).

    Typed rather than left as `dict[str, int]`, which accepted `{}` and
    `{"foo": 5}` and made the volume check a comparison against nothing. A
    blocker that silently has no bounds to compare against is the failure mode
    this repo keeps finding, so the bounds are a model with a validator.
    """

    min: int = Field(ge=0)
    max: int = Field(gt=0)

    @model_validator(mode="after")
    def min_not_above_max(self) -> "RowCountBounds":
        if self.min > self.max:
            raise ValueError(
                f"row_count_bounds.min ({self.min}) exceeds max ({self.max}): "
                f"no row count can satisfy this envelope, so every run would "
                f"fail the volume check for a reason the manifest created"
            )
        return self


class GovernanceConfig(BaseModel):
    """Declarations §6.2.2 requires be *present*, not proven (§6.2.2, 0.5.4).

    Both fields below back **declaration-class** checks: preflight verifies that
    a commitment was made and does not test whether it holds. That is not a
    weakness to be fixed later by validating the strings — a DPA reference is a
    pointer into contract work that lives outside this repository, and a restore
    point cannot be exercised by a tool holding no standing access (P9). What
    the check buys is that the commitment cannot be *absent* and unnoticed.
    """

    dpa_ref: str = Field(
        min_length=1,
        description=(
            "Reference to the executed DPA/KVİS for this engagement — a contract "
            "id or document reference, never the document itself (§2.1 L1)."
        ),
    )
    restore_point: str = Field(
        min_length=1,
        description=(
            "The client-side restore point or snapshot this run can be rolled "
            "back to (§6.2.2 capacity). Declared by the client; its existence is "
            "not verified by the Harness."
        ),
    )


class ArmingConfig(BaseModel):
    form: Literal["interactive", "standing"] = "interactive"
    idp_ref: str = "client"
    ttl_minutes: int = 60


class PreflightConfig(BaseModel):
    sample_limit: int = Field(200, gt=0)
    freshness_window_hours: int = Field(48, gt=0)
    row_count_bounds: RowCountBounds = Field(
        default_factory=lambda: RowCountBounds(min=1, max=10_000_000)
    )
    estimated_run_minutes: int = Field(45, gt=0)
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
    #: Required, with no default, exactly like `bronze`. A default location would
    #: be the kernel choosing where a client's audit record lands, and a manifest
    #: that omits the store is a manifest for a run whose account of itself has
    #: nowhere to go.
    audit: AuditConfig
    target: TargetConfig
    #: Required with no default, like `bronze` and `audit`. A default would mean
    #: the kernel supplying a DPA reference on the client's behalf, which is the
    #: one thing a governance blocker must never be able to do.
    governance: GovernanceConfig
    preflight: PreflightConfig = Field(default_factory=PreflightConfig)
    packs: list[str] = Field(default_factory=list)
    external_references: list[str] = Field(default_factory=list)
    egress: EgressConfig = Field(default_factory=EgressConfig)

    @model_validator(mode="after")
    def audit_must_outlive_bronze(self) -> "Manifest":
        """`audit.retention_days` ≥ `bronze.retention_days` (§4.2.6, §6.2.2).

        The constraint is P8, not tidiness. The two stores answer one question
        jointly — Bronze produces the pre-image, the audit record says which rule
        and which transform put it in its current state — so an audit store that
        expires first opens a window where the data is still there and the
        account of what was done to it is not. "The client can always tell what
        happened to a record" then becomes false for every record in that window,
        silently, on a date nobody chose. That failure is worse than losing both,
        because the surviving Bronze partition makes the system look intact.

        One-directional by design. Audit outliving Bronze is fine and often
        correct: the record holds no source values, only hashes, rule ids and
        transform names, so keeping it after the raw data is gone leaves a lawful
        account of processing without extending the life of the personal data.

        **Refused at load time, though §6.2.2 calls it a preflight blocker.** The
        two are not in tension: preflight still reports it, because a manifest
        that will not load is the most legible blocker there is. What load-time
        refusal adds is that no code path reaches a run with an inverted
        retention pair — not a test harness, not a future CLI subcommand that
        forgot to call preflight, not a library caller. The check lives with the
        data it constrains rather than with the stage that happens to report it,
        which is the same reasoning as `egress.evidence_only` above.
        """
        if self.audit.retention_days < self.bronze.retention_days:
            raise ValueError(
                f"audit.retention_days ({self.audit.retention_days}) is shorter "
                f"than bronze.retention_days ({self.bronze.retention_days}): the "
                f"audit store must outlive Bronze (§4.2.6). Otherwise the raw "
                f"data outlives the account of what was done to it, and P8 fails "
                f"silently on a date nobody chose"
            )
        return self