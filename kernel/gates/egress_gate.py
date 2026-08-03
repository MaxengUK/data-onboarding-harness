"""Schema-constrained egress serializer (CLAUDE.md §8, §8.1, P5).

Deny by default. Every field of an evidence model must declare which §8 value
class it belongs to; a field that declares nothing does not serialize, it raises.
That is the whole design: adding a bare `str` to an evidence model is a build
failure rather than a silent new export channel.

**There is no masking.** Masking is allow-then-redact — it presumes the value
was permitted and merely needs tidying, so the day someone adds a field the
redactor does not know about, it leaves quietly. Here nothing leaves unless it
was named in advance.

Two independent layers:

1. The Pydantic model defines *structure* — which fields exist, and their types.
2. This serializer independently validates *value classes* — a hash is really a
   hash, a semantic type is really a registry member, a column name was really
   declared in the manifest. Trusting the model alone is not enough, because the
   model is exactly what a future change edits.

The gate imports nothing from `schemas/`; the egress contract types below are
what evidence models are built from, which keeps the dependency acyclic and
means this file can be reasoned about on its own.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel

from kernel.registries import (
    ConfidenceBand,
    DiscoveryAlgorithm,
    RuleState,
    SemanticType,
    StageName,
    TransformName,
    is_pii,
)


class EgressViolation(Exception):
    """Raised when a value is not provably on the §8 allowlist.

    Always fails the run (§8). It is never caught and downgraded to a warning —
    a boundary that can be argued past is not a boundary.
    """


class EgressKind(str, Enum):
    """The §8 permitted value classes, one per allowlist entry."""

    COUNT = "count"
    RATE = "rate"
    DURATION_MS = "duration_ms"
    TIMESTAMP = "timestamp"
    RUN_ID = "run_id"
    RULE_ID = "rule_id"
    PACK_VERSION = "pack_version"
    KERNEL_VERSION = "kernel_version"
    #: Artifact-level digests only — a Bronze partition, a manifest, a pack.
    #: There is deliberately no field-level equivalent: a digest of a column's
    #: values is reversible whenever the *value space* is enumerable, and for
    #: every real field type it is. An MSISDN column has a space of ~10^9, a
    #: TCKN ~10^11 constrained by a checksum, a date a few tens of thousands —
    #: all trivially swept regardless of how many distinct values the dataset
    #: happens to hold. Cardinality measures the wrong quantity, so no threshold
    #: on it can make a field hash safe. An artifact digest is different in kind:
    #: its input is an entire file, which is not enumerable.
    CONTENT_HASH = "content_hash"
    COLUMN_NAME = "column_name"
    CANONICAL_FIELD_NAME = "canonical_field_name"
    SEMANTIC_TYPE = "semantic_type"
    TRANSFORM_NAME = "transform_name"
    DISCOVERY_ALGORITHM = "discovery_algorithm"
    # Kernel-owned closed vocabularies. Their members are fixed at release time,
    # so they cannot carry source content — but they still declare themselves,
    # because "it is an enum" is the kind of implicit allowance this gate exists
    # to do without.
    STAGE_NAME = "stage_name"
    RULE_STATE = "rule_state"
    CONFIDENCE_BAND = "confidence_band"
    REFERENCE_ID = "reference_id"
    FORMAT_SHAPE = "format_shape"
    DISTINCT_VALUE = "distinct_value"


@dataclass(frozen=True)
class Egress:
    """Field-level declaration: `Annotated[int, Egress(EgressKind.COUNT)]`.

    Read by the serializer, not by Pydantic. Its absence is what makes an
    undeclared field fail.
    """

    kind: EgressKind


class EgressModel(BaseModel):
    """Base for every structure allowed to cross the boundary.

    §8: "An adapter that hands the emitter a structure it did not construct is
    the most likely way this boundary gets breached." Membership in this class
    is how the emitter recognises what it built. A Great Expectations result
    object, or a bare dict, is not an EgressModel and is refused on sight —
    before any question of its contents arises.
    """


# --- §8 constants -----------------------------------------------------------

#: §8.1 caps a distinct-value list at this cardinality.
MAX_DISTINCT_CARDINALITY = 50

MAX_LABEL_LENGTH = 128
MAX_DISTINCT_VALUE_LENGTH = 200

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{7,63}$")
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_PACK_VERSION = re.compile(r"^[a-z0-9][a-z0-9/_-]*@\d+\.\d+\.\d+$")
_REFERENCE_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
#: Shapes are masks, not regexes: digits collapse to 9, letters to A, and
#: punctuation stays literal ("+99 999 999 99 99"). Anything outside that
#: alphabet means a raw value is being passed off as a shape.
_FORMAT_SHAPE = re.compile(r"^(?=.*[9A])[9A +\-._:/()\[\]#]{1,64}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


# --- egress contract types --------------------------------------------------


class ValueCount(EgressModel):
    """One distinct value and its group count. Only legal inside §8.1."""

    value: Annotated[str, Egress(EgressKind.DISTINCT_VALUE)]
    count: Annotated[int, Egress(EgressKind.COUNT)]


class KAnonymisedValues(EgressModel):
    """A distinct-value list under the §8.1 exception.

    All three conditions must hold; the gate raises if any does not. It does not
    quietly fall back to shapes — producing the compliant alternative is the
    profiling stage's job, and a gate that silently substitutes output is a gate
    nobody can reason about.
    """

    semantic_type: Annotated[SemanticType, Egress(EgressKind.SEMANTIC_TYPE)]
    cardinality: Annotated[int, Egress(EgressKind.COUNT)]
    values: list[ValueCount]


class ShapeSummary(EgressModel):
    """The §8.1 fallback: how many values look like this, not which they are."""

    shape: Annotated[str, Egress(EgressKind.FORMAT_SHAPE)]
    count: Annotated[int, Egress(EgressKind.COUNT)]


@dataclass(frozen=True)
class EgressPolicy:
    """Per-run egress parameters, from the manifest's `egress` block.

    `declared_columns` and `declared_canonical_fields` are the manifest's own
    vocabulary. A column name is permitted by §8, but "permitted" cannot mean
    "any string, provided the field is labelled column_name" — that is a hole
    wide enough for a cell value. Membership is checked, and an empty set means
    nothing was declared, so nothing passes.
    """

    k_anonymity_min: int
    declared_columns: frozenset[str] = field(default_factory=frozenset)
    declared_canonical_fields: frozenset[str] = field(default_factory=frozenset)


# --- scalar value-class validation ------------------------------------------


def _reject(path: str, detail: str) -> None:
    raise EgressViolation(f"{path}: {detail}")


def _require_int(value: Any, path: str) -> int:
    # bool is an int subclass; a flag smuggled into a count is still a defect.
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(path, f"expected an integer, got {type(value).__name__}")
    return value


def _require_clean_text(value: Any, path: str, max_length: int) -> str:
    if not isinstance(value, str):
        _reject(path, f"expected a string, got {type(value).__name__}")
    if not value:
        _reject(path, "empty string")
    if len(value) > max_length:
        _reject(path, f"longer than {max_length} characters")
    if _CONTROL_CHARS.search(value):
        _reject(path, "contains control characters")
    return value


def _require_pattern(value: Any, pattern: re.Pattern[str], path: str, label: str) -> str:
    text = _require_clean_text(value, path, MAX_LABEL_LENGTH)
    if not pattern.match(text):
        _reject(path, f"not a well-formed {label}")
    return text


def _require_member(value: Any, enum_type: type[Enum], path: str) -> None:
    if not isinstance(value, enum_type):
        _reject(
            path,
            f"not a member of the closed {enum_type.__name__} registry "
            f"(got {type(value).__name__})",
        )


def _validate_scalar(value: Any, kind: EgressKind, policy: EgressPolicy, path: str) -> None:
    """Check one value against the §8 class its field declared."""
    if kind is EgressKind.COUNT:
        if _require_int(value, path) < 0:
            _reject(path, "a count cannot be negative")

    elif kind is EgressKind.RATE:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _reject(path, f"expected a number, got {type(value).__name__}")
        if not 0.0 <= float(value) <= 1.0:
            _reject(path, f"a rate must lie in [0, 1], got {value}")

    elif kind is EgressKind.DURATION_MS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _reject(path, f"expected a number, got {type(value).__name__}")
        if float(value) < 0:
            _reject(path, "a duration cannot be negative")

    elif kind is EgressKind.TIMESTAMP:
        if not isinstance(value, datetime):
            _reject(path, f"expected a datetime, got {type(value).__name__}")
        if value.tzinfo is None or value.utcoffset() is None:
            # A naive timestamp means "some local time somewhere", which is not
            # reproducible and not comparable across a client and MAXENG.
            _reject(path, "timestamp must be timezone-aware")

    elif kind is EgressKind.RUN_ID:
        _require_pattern(value, _RUN_ID, path, "run id")

    elif kind is EgressKind.RULE_ID:
        _require_pattern(value, _RULE_ID, path, "rule id")

    elif kind is EgressKind.PACK_VERSION:
        _require_pattern(value, _PACK_VERSION, path, "pack version (name@x.y.z)")

    elif kind is EgressKind.KERNEL_VERSION:
        _require_pattern(value, _SEMVER, path, "kernel version")

    elif kind is EgressKind.CONTENT_HASH:
        _require_pattern(value, _SHA256_HEX, path, "sha256 digest")

    elif kind is EgressKind.COLUMN_NAME:
        name = _require_clean_text(value, path, MAX_LABEL_LENGTH)
        if name not in policy.declared_columns:
            _reject(
                path,
                "column name was not declared in the manifest; an undeclared "
                "name is indistinguishable from a cell value",
            )

    elif kind is EgressKind.CANONICAL_FIELD_NAME:
        name = _require_clean_text(value, path, MAX_LABEL_LENGTH)
        if name not in policy.declared_canonical_fields:
            _reject(path, "canonical field name was not declared in the manifest")

    elif kind is EgressKind.SEMANTIC_TYPE:
        _require_member(value, SemanticType, path)

    elif kind is EgressKind.TRANSFORM_NAME:
        _require_member(value, TransformName, path)

    elif kind is EgressKind.DISCOVERY_ALGORITHM:
        _require_member(value, DiscoveryAlgorithm, path)

    elif kind is EgressKind.STAGE_NAME:
        _require_member(value, StageName, path)

    elif kind is EgressKind.RULE_STATE:
        _require_member(value, RuleState, path)

    elif kind is EgressKind.CONFIDENCE_BAND:
        _require_member(value, ConfidenceBand, path)

    elif kind is EgressKind.REFERENCE_ID:
        _require_pattern(value, _REFERENCE_ID, path, "reference registry id")

    elif kind is EgressKind.FORMAT_SHAPE:
        shape = _require_clean_text(value, path, MAX_LABEL_LENGTH)
        if not _FORMAT_SHAPE.match(shape):
            _reject(
                path,
                "not a mask (digits as 9, letters as A, punctuation literal); "
                "a raw value cannot be exported as a shape",
            )

    elif kind is EgressKind.DISTINCT_VALUE:
        # Structural only. What actually authorises a distinct value to leave is
        # the three-condition §8.1 check applied to the list that contains it.
        _require_clean_text(value, path, MAX_DISTINCT_VALUE_LENGTH)

    else:  # pragma: no cover - unreachable while EgressKind stays closed
        _reject(path, f"no validator registered for egress kind {kind!r}")


# --- structure-level rules --------------------------------------------------


def _check_k_anonymity(node: KAnonymisedValues, policy: EgressPolicy, path: str) -> None:
    """The §8.1 exception: all three conditions, or nothing leaves."""
    if is_pii(node.semantic_type):
        _reject(
            f"{path}.semantic_type",
            f"distinct values of PII-typed '{node.semantic_type.value}' may never be exported",
        )

    if node.cardinality > MAX_DISTINCT_CARDINALITY:
        _reject(
            f"{path}.cardinality",
            f"cardinality {node.cardinality} exceeds the §8.1 limit of "
            f"{MAX_DISTINCT_CARDINALITY}; export shapes instead",
        )

    # Without this, the cap is evaded by understating cardinality and shipping
    # the full list anyway.
    if len(node.values) != node.cardinality:
        _reject(
            f"{path}.values",
            f"declared cardinality {node.cardinality} does not match the "
            f"{len(node.values)} values carried",
        )

    for index, entry in enumerate(node.values):
        if entry.count < policy.k_anonymity_min:
            _reject(
                f"{path}.values[{index}]",
                f"group count {entry.count} is below k_anonymity_min "
                f"{policy.k_anonymity_min}",
            )


# --- traversal --------------------------------------------------------------


def _egress_marker(field_info: Any) -> Egress | None:
    for meta in field_info.metadata:
        if isinstance(meta, Egress):
            return meta
    return None


def _validate_unmarked(value: Any, policy: EgressPolicy, path: str) -> None:
    """A field that declared no §8 class. Only nested evidence structures pass."""
    if getattr(type(value), "IN_BOUNDARY_ONLY", False):
        _reject(
            path,
            f"{type(value).__name__} is an in-boundary audit structure and never "
            "crosses the trust boundary (§8, §12)",
        )

    if isinstance(value, EgressModel):
        _validate_model(value, policy, path)
        return

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_unmarked(item, policy, f"{path}[{index}]")
        return

    if isinstance(value, dict):
        # An open mapping is exactly the shape adapter output arrives in, and
        # its keys are free text by construction. Model it explicitly instead.
        _reject(
            path,
            "a mapping cannot be exported; declare an explicit model so every "
            "key and value is named in advance",
        )

    _reject(
        path,
        f"field declares no egress kind, so {type(value).__name__} is not on the "
        "§8 allowlist",
    )


def _validate_model(model: EgressModel, policy: EgressPolicy, path: str) -> None:
    if isinstance(model, KAnonymisedValues):
        _check_k_anonymity(model, policy, path)

    for name, field_info in type(model).model_fields.items():
        value = getattr(model, name)
        child = f"{path}.{name}"

        if value is None:
            # An absent value exports nothing, so there is nothing to authorise.
            continue

        marker = _egress_marker(field_info)
        if marker is None:
            _validate_unmarked(value, policy, child)
            continue

        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                _validate_scalar(item, marker.kind, policy, f"{child}[{index}]")
        else:
            _validate_scalar(value, marker.kind, policy, child)


def validate_for_egress(artifact: Any, policy: EgressPolicy) -> None:
    """Raise EgressViolation unless every value is provably §8-permitted."""
    if getattr(type(artifact), "IN_BOUNDARY_ONLY", False):
        raise EgressViolation(
            f"artifact: {type(artifact).__name__} is an in-boundary audit "
            "structure and never crosses the trust boundary (§8, §12)"
        )

    if not isinstance(artifact, EgressModel):
        raise EgressViolation(
            f"artifact: {type(artifact).__name__} was not constructed by the "
            "emitter; adapter output and raw mappings are refused on sight (§8)"
        )

    _validate_model(artifact, policy, "artifact")


def serialize_evidence(artifact: Any, policy: EgressPolicy) -> str:
    """Validate, then render canonical JSON. Raises rather than emitting a
    partial or redacted artifact.

    Byte-identical for identical input (P2): fixed indent, sorted keys, LF, and
    no clock read anywhere — every timestamp is supplied by the caller.
    """
    validate_for_egress(artifact, policy)
    payload = artifact.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
