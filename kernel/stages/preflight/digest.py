"""The preflight digest — what an approval will later be bound to (§6.2.3).

§6.2.3 rule 1: an arming token is void the moment anything in the digest changes.
So the digest is not an identifier for a report; it is **a claim about what would
invalidate an approval**. Everything that claim omits is something a client
approved without meaning to.

That makes a partial digest worse than no digest. If pack versions are missing
from it, then a pack version bump does not void arming — silently, and precisely
where §6.2.3 promises it would. So:

**A digest is produced only when every component it should cover was resolved,
and it records the components it covers.** A component that could not be
resolved means no digest at all and a blocked verdict, not a shorter hash.

**Empty is resolved.** A manifest declaring no packs has nothing to resolve, so
`PACK_VERSIONS` is satisfied vacuously and the digest is complete. This is not a
loophole — it is what lets a file-source, pack-free manifest reach `ready` while
BUILD-PLAN item 3 is still open, and the coverage list makes the vacuity legible
rather than hidden: the report says no packs were declared.

**No clock, ever.** Two preflights over an unchanged source and manifest must
produce the same digest, or every scheduled batch in continuous mode would drift
out of its standing authorization for no reason (§6.2.3).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from kernel.serialisation import canonical_json_bytes, content_hash
from schemas.manifest import Manifest


class DigestComponent(str, Enum):
    """The five inputs §6.2.3 names, as a closed set.

    Closed so that "the digest covers X" is checkable rather than asserted: a
    sixth input added to the hash without a member here would widen what voids
    an approval with nothing recording that it had.
    """

    SOURCE_SCHEMA = "source_schema"
    ROW_COUNTS = "row_counts"
    PACK_VERSIONS = "pack_versions"
    MANIFEST_CONTENT = "manifest_content"
    KERNEL_VERSION = "kernel_version"


class PreflightDigest(BaseModel):
    """A complete digest and the components it was computed from."""

    model_config = {"frozen": True, "extra": "forbid"}

    value: str = Field(description="sha256 over the canonicalised components, hex")
    covers: tuple[DigestComponent, ...] = Field(
        description=(
            "Every component in DigestComponent, in declaration order. The field "
            "exists so a reader can see coverage without recomputing, and so "
            "that a future partial digest would be a visibly different object "
            "rather than an indistinguishable shorter hash."
        )
    )


class DigestIncomplete(Exception):
    """A component could not be resolved, so no digest exists.

    Carries the unresolved components by name: the Preflight Report has to say
    which part of the approval surface could not be established, since "no
    digest" on its own tells a client nothing actionable.
    """

    def __init__(self, missing: tuple[DigestComponent, ...]) -> None:
        self.missing = missing
        names = ", ".join(component.value for component in missing)
        super().__init__(
            f"cannot compute a preflight digest: {names} could not be resolved. "
            f"A digest that omitted them would leave an approval bound to less "
            f"than §6.2.3 promises, so none is produced"
        )


def compute_digest(
    manifest: Manifest,
    *,
    kernel_version: str,
    source_schema: tuple[str, ...] | None,
    row_count: int | None,
) -> PreflightDigest:
    """Compute the digest, or raise `DigestIncomplete`.

    `source_schema` and `row_count` are `None` when preflight could not read the
    source — which is exactly when an approval must not be bindable, because the
    two things most likely to change upstream are the ones that could not be
    observed.

    Pack versions come from the manifest's declared list rather than from a
    resolver, and that is a real limitation rather than a simplification: a
    declared `core/tr-core@^1.4` is a *range*, and two runs a month apart could
    resolve it to different versions with an identical digest. It is sound only
    while the declared list is empty, which is the state BUILD-PLAN item 3
    closes. Until then a non-empty pack list makes the component unresolved.
    """
    missing: list[DigestComponent] = []
    if source_schema is None:
        missing.append(DigestComponent.SOURCE_SCHEMA)
    if row_count is None:
        missing.append(DigestComponent.ROW_COUNTS)
    if manifest.packs:
        missing.append(DigestComponent.PACK_VERSIONS)

    if missing:
        raise DigestIncomplete(tuple(missing))

    payload = {
        DigestComponent.SOURCE_SCHEMA.value: list(source_schema or ()),
        DigestComponent.ROW_COUNTS.value: row_count,
        DigestComponent.PACK_VERSIONS.value: list(manifest.packs),
        DigestComponent.MANIFEST_CONTENT.value: manifest_hash(manifest),
        DigestComponent.KERNEL_VERSION.value: kernel_version,
    }

    return PreflightDigest(
        value=content_hash(canonical_json_bytes(payload)),
        covers=tuple(DigestComponent),
    )


def manifest_hash(manifest: Manifest) -> str:
    """Content hash of the engagement manifest (§12).

    `mode="json"` so the hash is taken over the manifest's *values* rather than
    over Python objects whose repr could change with a Pydantic release.
    """
    return content_hash(canonical_json_bytes(manifest.model_dump(mode="json")))
