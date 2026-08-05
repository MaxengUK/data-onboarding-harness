"""Resolving `manifest.canonical_schema` to its artifact (CLAUDE.md §7.6).

**This is not a pack loader, and the difference is the point.**

| Pack loader (§7.4) | This |
|---|---|
| Many artifacts → one merged ruleset | One id → one artifact |
| Layer precedence, narrower wins | None |
| Version ranges (`^1.4`) | The version is inside the id |
| `overrides`, `corroborated_by`, `layer` | None of them |
| Two sources supplying one rule id is normal | Two sources supplying one id is an **error** |

The reason the boundary holds: **rules accumulate, canonical schemas do not.**
§7.4's precedence exists because a `client` rule is meant to refine a `core` one,
and that accumulation is the reuse mechanism §13 measures. A canonical schema is
the fixed target both sides map onto. Give it precedence and a client pack can
quietly change what `sales_v2` means — and two engagements then emit different
"canonical" output under one name, which is the one thing canonical output
exists to prevent.

That is also why artifacts live in `canonical/` rather than under `packs/`:
co-locating them would invite the pack loader's precedence rules to reach them.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from schemas.canonical import CanonicalSchema

#: Repository-root `canonical/`. Mounted alongside packs at runtime (§14), so a
#: deployment can supply its own directory without the kernel knowing where.
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "canonical"

SUFFIXES = (".yaml", ".yml")


class CanonicalSchemaError(Exception):
    """Base for canonical schema resolution failures."""


class UnknownCanonicalSchema(CanonicalSchemaError):
    """No artifact under the root carries this id.

    A blocker rather than a fallback: a run whose canonical schema cannot be
    found has no target to map onto, and `map` would fail later with less to say.
    """


class AmbiguousCanonicalSchema(CanonicalSchemaError):
    """Two artifacts claim one id.

    **An error, not a precedence decision**, and this is where the difference
    from a pack loader becomes executable rather than documentary. A loader
    would resolve this by layer; resolving it at all would mean one id can mean
    two things depending on where the resolver looked first.
    """


class MalformedCanonicalSchema(CanonicalSchemaError):
    """The artifact exists but is not a valid canonical schema."""


def _artifact_paths(root: Path) -> list[Path]:
    return sorted(path for suffix in SUFFIXES for path in root.rglob(f"*{suffix}"))


def load_canonical_schema(path: Path) -> CanonicalSchema:
    """Read and validate one artifact."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MalformedCanonicalSchema(f"{path.name}: {exc}") from exc

    try:
        return CanonicalSchema.model_validate(document)
    except ValidationError as exc:
        raise MalformedCanonicalSchema(f"{path.name}: {exc}") from exc


def resolve_canonical_schema(
    schema_id: str, root: Path | None = None
) -> CanonicalSchema:
    """Resolve `schema_id` to exactly one artifact, or raise.

    The id is matched against each artifact's declared `id`, not against its
    path. A file's location is an operational convenience; what it claims to be
    is the artifact's own statement, and letting the path win would mean moving
    a file silently redefines a schema.
    """
    directory = root or DEFAULT_ROOT
    if not directory.is_dir():
        raise UnknownCanonicalSchema(
            f"no canonical schema directory at {directory}; "
            f"{schema_id!r} cannot be resolved"
        )

    matches = [
        (path, schema)
        for path in _artifact_paths(directory)
        if (schema := load_canonical_schema(path)).id == schema_id
    ]

    if not matches:
        raise UnknownCanonicalSchema(
            f"no canonical schema declares id {schema_id!r} under {directory}"
        )
    if len(matches) > 1:
        raise AmbiguousCanonicalSchema(
            f"{len(matches)} artifacts declare id {schema_id!r}: "
            f"{', '.join(path.name for path, _ in matches)}. One id names one "
            f"schema; there is no precedence rule to break this tie (§7.6)"
        )

    return matches[0][1]


def available_ids(root: Path | None = None) -> tuple[str, ...]:
    """Every id under the root, for error messages that name the alternatives.

    Enumeration is fine *here* and refused for the stores, and the difference is
    what the enumeration is trusted for. Bronze and the audit store are read by
    id because a listing is not tamper-evident (§4.2.6). This listing feeds a
    "did you mean" line; nothing is verified against it.
    """
    directory = root or DEFAULT_ROOT
    if not directory.is_dir():
        return ()

    return tuple(sorted(load_canonical_schema(path).id for path in _artifact_paths(directory)))
