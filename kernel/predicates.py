"""The closed predicate registry (CLAUDE.md §7.5, §0).

A rule names a predicate and supplies parameters; the kernel resolves the name
to a callable shipped in this release. There is no expression language, no
`eval`, and no `exec` — §7.5's rationale is that a DSL means a parser to
maintain and a sandbox to get right, while dynamic evaluation breaks both
determinism (P2) and auditability (P8).

**Params carry names, not content.** `pattern: tr_msisdn` names a registered
pattern; it never supplies a regex. A pack-authored regex would be executable
content from outside the release — which ends the claim above — and a
catastrophic-backtracking one is an availability incident in a client's
environment rather than a bug in ours. Adding a pattern is a kernel change with
a test, the same friction §7.5 already accepts for adding a predicate.

**Locale-neutral only, in this build.** `tr_msisdn` and its relatives arrive
with `tr-core` (BUILD-PLAN item 9) as a deliberate kernel change. The line §7.5
draws holds either way: the *concept* and the *shape* are kernel-owned, the
*rule and the transform* belong to a pack.

Not in `kernel/registries.py`, which is vocabulary the egress gate imports. A
module that executes things has no business in that import chain.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any, Self

from kernel.checksums import is_valid_tckn, is_valid_vkn


class Scope(str, Enum):
    """What a predicate is handed when it runs.

    Declared per predicate rather than inferred, because the wrong guess fails
    at run time rather than at load time: a column-scope predicate handed a
    single value returns a confident, meaningless answer.
    """

    #: One cell. The common case, and the only one `normalize` uses.
    VALUE = "value"
    #: A mapping of canonical field name to value, for cross-field rules —
    #: `delivery_date < order_date` is a denial constraint over a row (§9.1 B).
    ROW = "row"
    #: Every value of one column, for uniqueness and cardinality.
    COLUMN = "column"


class ChecksumAlgorithm(str, Enum):
    """Closed set of checksums `has_checksum` can be asked for."""

    TCKN = "tckn"
    VKN = "vkn"


class PatternName(str, Enum):
    """Closed set of named patterns `matches_pattern` can be asked for.

    Kernel-owned for the reason in the module docstring: a pattern is
    executable content, and §7.5's claim that the kernel cannot run anything
    outside the release has to survive contact with rule parameters.

    Locale-neutral in this build. The Turkish shapes — MSISDN, plate, TCKN
    formatting — land with `tr-core` as a kernel change, at which point this
    enum grows and its test grows with it.
    """

    #: Digits only, any length. Useful before a checksum predicate.
    DIGITS = "digits"
    #: A calendar date in ISO-8601, no time part.
    ISO_DATE = "iso_date"
    #: An ISO-8601 instant, with or without a zone.
    ISO_TIMESTAMP = "iso_timestamp"
    #: Non-empty after stripping whitespace.
    NON_BLANK = "non_blank"
    #: An email-shaped string. Deliberately loose: validating an address by
    #: regex is a known false-negative machine, and this exists to catch a
    #: column that is plainly not addresses, not to reject unusual ones.
    EMAIL_SHAPE = "email_shape"


_COMPILED: dict[PatternName, re.Pattern[str]] = {
    PatternName.DIGITS: re.compile(r"^\d+$"),
    PatternName.ISO_DATE: re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    PatternName.ISO_TIMESTAMP: re.compile(
        r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"
    ),
    PatternName.NON_BLANK: re.compile(r"\S"),
    PatternName.EMAIL_SHAPE: re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
}


# --- implementations ----------------------------------------------------------
#
# Every one of these is total: it returns True or False for any input, including
# None, and never raises. A predicate that raised would turn a data problem into
# a run failure, and §6 gives `validate` exactly one way to react to bad data —
# quarantine (§6.1) — which it cannot reach if the check itself exploded.


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_not_null(value: Any) -> bool:
    return not _is_null(value)


def _matches_pattern(value: Any, *, pattern: PatternName) -> bool:
    return isinstance(value, str) and bool(_COMPILED[pattern].search(value))


def _length_between(value: Any, *, min: int, max: int) -> bool:
    return isinstance(value, str) and min <= len(value) <= max


def _value_in_set(value: Any, *, values: tuple[str, ...]) -> bool:
    return value in values


def _is_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if not isinstance(value, str):
        return False
    try:
        float(value.strip())
    except ValueError:
        return False
    return True


def _in_range(value: Any, *, min: float, max: float) -> bool:
    if not _is_numeric(value):
        return False
    return min <= float(value) <= max


def _has_checksum(value: Any, *, algorithm: ChecksumAlgorithm) -> bool:
    if not isinstance(value, str):
        return False
    checker = {
        ChecksumAlgorithm.TCKN: is_valid_tckn,
        ChecksumAlgorithm.VKN: is_valid_vkn,
    }[algorithm]
    return checker(value.strip())


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def _field_before(row: Any, *, earlier: str, later: str) -> bool:
    """`earlier` must not be after `later`. Missing either side passes.

    A row missing one of the two fields is a *mapping* problem, and reporting it
    here would attribute it to the wrong rule. §6.2.2's schema checks and `map`
    both fail on an unmapped field before any of this runs.
    """
    if not isinstance(row, dict):
        return False
    left, right = row.get(earlier), row.get(later)
    if left is None or right is None:
        return True
    return str(left) <= str(right)


def _fields_equal(row: Any, *, left: str, right: str) -> bool:
    return isinstance(row, dict) and row.get(left) == row.get(right)


def _is_unique(column: Any) -> bool:
    if not isinstance(column, (list, tuple)):
        return False
    present = [value for value in column if not _is_null(value)]
    return len(set(present)) == len(present)


def _cardinality_at_most(column: Any, *, limit: int) -> bool:
    if not isinstance(column, (list, tuple)):
        return False
    return len({value for value in column if not _is_null(value)}) <= limit


# --- the registry -------------------------------------------------------------
#
# The structural pattern from `SemanticType`, extended to three declarations
# rather than one. `__new__` takes implementation, parameter spec and scope
# positionally, so `FOO = "foo"` raises at class creation and the import fails.
# There is no state in which a predicate exists without all three.
#
# Scope is the one that would otherwise default silently, and it is the one that
# fails latest: a column-scope predicate handed a single cell returns a
# confident, meaningless answer rather than an error.


class Predicate(str, Enum):
    """A registered predicate: what it is called, what it does, what it needs."""

    def __new__(
        cls,
        value: str,
        implementation: Callable[..., bool],
        params: dict[str, type],
        scope: Scope,
    ) -> Self:
        member = str.__new__(cls, value)
        member._value_ = value
        member.implementation = implementation
        member.params = params
        member.scope = scope
        return member

    implementation: Callable[..., bool]
    params: dict[str, type]
    scope: Scope

    IS_NULL = ("is_null", _is_null, {}, Scope.VALUE)
    IS_NOT_NULL = ("is_not_null", _is_not_null, {}, Scope.VALUE)
    MATCHES_PATTERN = (
        "matches_pattern",
        _matches_pattern,
        {"pattern": PatternName},
        Scope.VALUE,
    )
    LENGTH_BETWEEN = ("length_between", _length_between, {"min": int, "max": int}, Scope.VALUE)
    VALUE_IN_SET = ("value_in_set", _value_in_set, {"values": tuple}, Scope.VALUE)
    IS_NUMERIC = ("is_numeric", _is_numeric, {}, Scope.VALUE)
    IN_RANGE = ("in_range", _in_range, {"min": float, "max": float}, Scope.VALUE)
    HAS_CHECKSUM = (
        "has_checksum",
        _has_checksum,
        {"algorithm": ChecksumAlgorithm},
        Scope.VALUE,
    )
    IS_ISO_DATE = ("is_iso_date", _is_iso_date, {}, Scope.VALUE)

    FIELD_BEFORE = (
        "field_before",
        _field_before,
        {"earlier": str, "later": str},
        Scope.ROW,
    )
    FIELDS_EQUAL = ("fields_equal", _fields_equal, {"left": str, "right": str}, Scope.ROW)

    IS_UNIQUE = ("is_unique", _is_unique, {}, Scope.COLUMN)
    CARDINALITY_AT_MOST = (
        "cardinality_at_most",
        _cardinality_at_most,
        {"limit": int},
        Scope.COLUMN,
    )


class PredicateParamError(ValueError):
    """A rule supplied parameters the predicate did not declare, or omitted some.

    Raised at *load*, never at evaluation. A rule whose parameters do not match
    its predicate is malformed, and the place to find that out is when the pack
    is read — not partway through a client's batch.

    A `ValueError` subclass on purpose: `schemas.rule.Rule` calls `check_params`
    from a Pydantic validator, and Pydantic only folds `ValueError` into a
    `ValidationError`. Inheriting from `Exception` let this escape a rule load
    raw, so a malformed pack would surface as an unhandled error rather than as
    the field-level report every other schema problem produces.
    """


def check_params(predicate: Predicate, params: dict[str, Any]) -> None:
    """Verify `params` matches what `predicate` declared. Raises, or returns None."""
    declared = set(predicate.params)
    supplied = set(params)

    missing = sorted(declared - supplied)
    unexpected = sorted(supplied - declared)
    if missing or unexpected:
        raise PredicateParamError(
            f"{predicate.value}: "
            + ", ".join(
                part
                for part in (
                    f"missing {missing}" if missing else "",
                    f"unexpected {unexpected}" if unexpected else "",
                )
                if part
            )
        )

    for name, expected in predicate.params.items():
        value = params[name]
        if isinstance(expected, type) and issubclass(expected, Enum):
            try:
                expected(value)
            except ValueError as exc:
                raise PredicateParamError(
                    f"{predicate.value}.{name}: {value!r} is not a member of "
                    f"the closed {expected.__name__} registry"
                ) from exc
        elif expected is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PredicateParamError(
                    f"{predicate.value}.{name}: expected a number, got {value!r}"
                )
        elif expected is tuple:
            if not isinstance(value, (list, tuple)):
                raise PredicateParamError(
                    f"{predicate.value}.{name}: expected a list, got {value!r}"
                )
        elif not isinstance(value, expected) or isinstance(value, bool) and expected is int:
            raise PredicateParamError(
                f"{predicate.value}.{name}: expected {expected.__name__}, got {value!r}"
            )
