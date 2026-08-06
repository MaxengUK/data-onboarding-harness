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

**No predicate carries a policy it did not declare.** Three questions that look
like implementation details are client decisions, so each is a mandatory
parameter with no default: whether a blank string is an absence
(`treat_blank_as_null`), what a missing side means for a rule that compares two
of them (`on_missing`), and — through the pattern registry — whether a pattern
anchors (`MatchMode`). P3 puts variance in packs and manifests, and a default
here is variance that has been decided in the kernel and hidden.

**Locale-neutral only, in this build.** `tr_msisdn` and its relatives arrive
with `tr-core` (BUILD-PLAN item 9) as a deliberate kernel change. The line §7.5
draws holds either way: the *concept* and the *shape* are kernel-owned, the
*rule and the transform* belong to a pack.

Not in `kernel/registries.py`, which is vocabulary the egress gate imports. A
module that executes things has no business in that import chain.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from enum import Enum
from typing import Any, Self

from kernel.checksums import is_valid_tckn, is_valid_vkn


class Scope(str, Enum):
    """What a predicate is handed when it runs.

    Declared per predicate rather than inferred, because the wrong guess fails
    at run time rather than at load time: a column-scope predicate handed a
    single value returns a confident, meaningless answer.

    The four pair up: `VALUE` is one cell and `ROW` is several named cells;
    `COLUMN` is one column's values and `FRAME` is several named columns. Each
    row of that pairing is the single and the plural of the same thing.
    """

    #: One cell. The common case, and the only one `normalize` uses.
    VALUE = "value"
    #: A mapping of canonical field name to value, for cross-field rules —
    #: `delivery_date < order_date` is a denial constraint over a row (§9.1 B).
    ROW = "row"
    #: Every value of one column, for uniqueness and cardinality.
    COLUMN = "column"
    #: A mapping of canonical field name to that field's values — several
    #: columns, aligned by position. Multi-column uniqueness needs it: a
    #: canonical schema declares `key: [measurement_point_id, reading_at]`
    #: (§7.6) and no single column can verify that.
    FRAME = "frame"


class MatchMode(str, Enum):
    """Whether a pattern must match the whole value or merely occur in it.

    Declared per pattern for the reason `Scope` is declared per predicate: the
    alternatives are both wrong. Anchoring every pattern breaks `non_blank`,
    which deliberately searches; anchoring none of them lets `$` through — in
    Python `$` matches at the end of the string *or* immediately before a
    trailing newline, so `search(r"^[0-9]+$", "123\\n")` is a match. A trailing
    newline in a CSV cell is exactly the dirt this harness exists to catch, and
    a validator that accepts it passes the thing it was pointed at.
    """

    #: `fullmatch` — the pattern must account for the entire value.
    FULL = "full"
    #: `search` — the pattern must occur somewhere in the value.
    SEARCH = "search"


class MissingPolicy(str, Enum):
    """What a predicate does when the thing it compares is not there.

    A mandatory parameter on every predicate that can meet an absent side,
    because the honest answers differ by rule and neither is safe as a default.
    Fail-open hides violations — `delivery_date < order_date` silently passing
    on every row with no `order_date` is P7 inverted — and fail-closed
    quarantines rows whose only defect is an unmapped field.

    See STATUS §5c.3: `pass` inflates `hold_rate`, which drives §9.2's band, and
    a third value that removes the row from the denominator is likely needed.
    Deferred to BUILD-PLAN item 12 deliberately rather than guessed at now.
    """

    #: A missing side is a violation.
    FAIL = "fail"
    #: A missing side satisfies the rule.
    PASS = "pass"


class ChecksumAlgorithm(str, Enum):
    """Closed set of checksums `has_checksum` can be asked for."""

    TCKN = "tckn"
    VKN = "vkn"


class PatternName(str, Enum):
    """Closed set of named patterns `matches_pattern` can be asked for.

    Kernel-owned for the reason in the module docstring: a pattern is
    executable content, and §7.5's claim that the kernel cannot run anything
    outside the release has to survive contact with rule parameters.

    Each member declares its regex and its `MatchMode` positionally, so a
    member written as `FOO = "foo"` fails at class creation. The compiled
    pattern lives on the member rather than in a table beside it — a second
    structure keyed by the same names is a second thing to keep in step.

    **A `FULL` pattern carries no anchors of its own.** The mode does the
    anchoring, and writing `^`/`$` as well would state it twice while leaving
    `$`'s trailing-newline leniency visible in the source, where the next
    person to copy a pattern would carry it into a `SEARCH` one.

    Digit classes are `[0-9]`, never `\\d`. Python's `\\d` spans Unicode decimal
    digits, so `٣٤٥` and `४५६` satisfy it and then reach an `int()` or a
    checksum that either raises or answers confidently about a value no issuing
    authority ever produced. `re.ASCII` would fix that and also narrow `\\w`,
    `\\s` and `\\b` across the whole pattern — the wrong direction in a Turkish
    harness, where a future name pattern using `\\w` would quietly drop `ş`,
    `ğ` and `İ`. `[0-9]` says what it means where it is written.

    Locale-neutral in this build. The Turkish shapes — MSISDN, plate, TCKN
    formatting — land with `tr-core` as a kernel change, at which point this
    enum grows and its test grows with it.
    """

    def __new__(cls, value: str, regex: str, mode: MatchMode) -> Self:
        member = str.__new__(cls, value)
        member._value_ = value
        member.source = regex
        member.compiled = re.compile(regex)
        member.mode = mode
        return member

    source: str
    compiled: re.Pattern[str]
    mode: MatchMode

    #: ASCII digits only, any length. Useful before a checksum predicate.
    DIGITS = ("digits", r"[0-9]+", MatchMode.FULL)
    #: A calendar date in ISO-8601, no time part. Shape only — `is_iso_date`
    #: is what rejects the thirtieth of February.
    ISO_DATE = ("iso_date", r"[0-9]{4}-[0-9]{2}-[0-9]{2}", MatchMode.FULL)
    #: An ISO-8601 instant, with or without a zone.
    ISO_TIMESTAMP = (
        "iso_timestamp",
        (
            # Parenthesised deliberately: an unparenthesised two-line string
            # inside a tuple reads as a missing comma, and here a missing comma
            # would silently make this a two-element member.
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
            r"(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})?"
        ),
        MatchMode.FULL,
    )
    #: Non-empty after stripping whitespace. The one deliberate `SEARCH`: it
    #: asks whether a non-space character occurs anywhere, which is not a
    #: statement about the whole value and cannot be written as one.
    NON_BLANK = ("non_blank", r"\S", MatchMode.SEARCH)
    #: An email-shaped string. Deliberately loose: validating an address by
    #: regex is a known false-negative machine, and this exists to catch a
    #: column that is plainly not addresses, not to reject unusual ones.
    EMAIL_SHAPE = ("email_shape", r"[^@\s]+@[^@\s]+\.[^@\s]+", MatchMode.FULL)


class FrameAlignmentError(ValueError):
    """A frame's columns are not the same length.

    Raised rather than answered, and it is the one thing in this module that
    does raise on input. The no-raise property below is about *data*: a value
    the client sent must never blow up a predicate, because §6 gives `validate`
    exactly one reaction to bad data and it cannot reach it from a traceback.
    A frame whose columns disagree about how many rows there are is not data —
    it is a caller that built the projection wrong, and the rows it implies do
    not exist. Returning `False` would report that as a client's uniqueness
    violation and attribute a harness bug to their data (P8).

    Concretely, `zip` is what makes this necessary: handed columns of length
    1_000_000 and 999_999 it stops at the shorter one and reports a clean
    result over a silently truncated frame.
    """


# --- implementations ----------------------------------------------------------
#
# Every one of these is total: it returns True or False for any input, including
# None, and never raises. A predicate that raised would turn a data problem into
# a run failure, and §6 gives `validate` exactly one way to react to bad data —
# quarantine (§6.1) — which it cannot reach if the check itself exploded.
# `FrameAlignmentError` is the documented exception, and it is not a data case.
#
# Params arrive from YAML, so an enum-typed parameter may still be a plain
# string at this point: `check_params` validates it against the registry at load
# but does not replace it. Comparisons below therefore use `==` against a member
# rather than `is`, which holds for both forms because these are `str` enums.


def _is_absent(value: Any, *, treat_blank_as_null: bool) -> bool:
    """The module's single answer to "is this value not there".

    Every predicate that branches on absence routes through here. Three things
    are being conflated the moment they are not: a database NULL, an empty CSV
    cell, and `"   "`. The first two are indistinguishable by the time a CSV is
    read — a file has no NULL — but the third is a client's decision, and
    `treat_blank_as_null` is the only place it is made.

    Before this parameter existed the answer was hardcoded, and worse, it was
    hardcoded *twice and differently*: `is_null` treated `"   "` as absent while
    the row predicates tested `is None` and treated it as present. One question,
    two answers, in one module.
    """
    if value is None:
        return True
    return bool(treat_blank_as_null) and isinstance(value, str) and not value.strip()


def _is_null(value: Any, *, treat_blank_as_null: bool) -> bool:
    return _is_absent(value, treat_blank_as_null=treat_blank_as_null)


def _is_not_null(value: Any, *, treat_blank_as_null: bool) -> bool:
    return not _is_absent(value, treat_blank_as_null=treat_blank_as_null)


def _matches_pattern(value: Any, *, pattern: PatternName) -> bool:
    if not isinstance(value, str):
        return False
    try:
        member = PatternName(pattern)
    except ValueError:
        # Unreachable through `Rule`, which calls `check_params` at load. Kept
        # so a direct caller gets a verdict rather than an AttributeError.
        return False
    if member.mode is MatchMode.FULL:
        return member.compiled.fullmatch(value) is not None
    return member.compiled.search(value) is not None


def _length_between(value: Any, *, min: int, max: int) -> bool:
    return isinstance(value, str) and min <= len(value) <= max


def _value_in_set(value: Any, *, values: tuple[str, ...]) -> bool:
    return value in values


def _is_numeric(value: Any) -> bool:
    """A finite number, or a string naming one.

    `nan`, `inf` and `-inf` are refused explicitly. `float()` accepts all three,
    and the damage shows up one predicate later: every comparison against a
    `nan` is False, so `in_range` reports a violation whose cause is nowhere in
    the rule, the value or the bounds. A rule that fails inexplicably is worse
    than one that fails — P8 is about being able to say what happened.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if not isinstance(value, str):
        return False
    try:
        return math.isfinite(float(value.strip()))
    except ValueError:
        return False


def _in_range(value: Any, *, min: float, max: float) -> bool:
    # `_is_numeric` covers the string path; the guard is repeated here because a
    # float `nan` can arrive straight from a Parquet column without passing
    # through a string at all.
    if not _is_numeric(value):
        return False
    return min <= float(value) <= max


def _has_checksum(value: Any, *, algorithm: ChecksumAlgorithm) -> bool:
    if not isinstance(value, str):
        return False
    checkers = {
        ChecksumAlgorithm.TCKN: is_valid_tckn,
        ChecksumAlgorithm.VKN: is_valid_vkn,
    }
    # `.get` rather than `[]`, and it accepts the raw string form too: these are
    # `str` enums, so the member and its value hash alike.
    checker = checkers.get(algorithm)
    if checker is None:
        return False
    return checker(value.strip())


def _is_iso_date(value: Any) -> bool:
    """A real calendar date, with no time part.

    The companion to `matches_pattern(iso_date)` rather than a duplicate of it:
    the pattern answers "is this the right shape", this answers "is this a date
    that exists". `2026-02-30` passes the first and fails the second.

    `date.fromisoformat` rather than `datetime.fromisoformat`, which accepts a
    full timestamp on 3.11+ and made this predicate's name disagree with its
    behaviour. Note it is deliberately not a shape check: on this interpreter it
    also accepts the basic form and ISO week dates, and shape is the pattern's
    question, not this one's. **Both leniencies are version-dependent** —
    `fromisoformat` widened in 3.11 and may widen again, so the accepted set
    here follows the interpreter rather than this docstring. Measured on the
    pinned 3.12; a rule needing the extended form must pair this with the
    pattern, which is the combination that is stable across versions.
    """
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def _row_sides(
    row: Any, names: tuple[str, ...], *, treat_blank_as_null: bool
) -> tuple[Any, ...] | None:
    """The named values, or None if the row is unusable or a side is absent."""
    if not isinstance(row, Mapping):
        return None
    values = tuple(row.get(name) for name in names)
    if any(_is_absent(value, treat_blank_as_null=treat_blank_as_null) for value in values):
        return None
    return values


def _resolve_missing(on_missing: MissingPolicy) -> bool:
    """The verdict for an absent side. Anything unrecognised fails closed."""
    return on_missing == MissingPolicy.PASS


def _field_before(
    row: Any,
    *,
    earlier: str,
    later: str,
    on_missing: MissingPolicy,
    treat_blank_as_null: bool,
) -> bool:
    """`earlier` must not be after `later`; an absent side is `on_missing`'s call.

    This used to pass whenever either side was missing, on the argument that a
    missing field is a mapping problem and `map` fails on one first. The
    argument holds for a field that was never mapped and not for a row whose
    `order_date` is simply empty — and the two are indistinguishable here. So
    the rule silently passed on every row missing a date, which is P7 inverted:
    fail-closed on data is the constitutional default, and this was fail-open on
    exactly the rows most likely to be wrong.
    """
    if not isinstance(row, Mapping):
        return False
    sides = _row_sides(row, (earlier, later), treat_blank_as_null=treat_blank_as_null)
    if sides is None:
        return _resolve_missing(on_missing)
    left, right = sides
    return str(left) <= str(right)


def _fields_equal(
    row: Any,
    *,
    left: str,
    right: str,
    on_missing: MissingPolicy,
    treat_blank_as_null: bool,
) -> bool:
    """Two fields must agree; an absent side is `on_missing`'s call.

    The same fail-open as `field_before` and less visible: a bare
    `row.get(left) == row.get(right)` passes when *both* sides are missing,
    because `None == None`, while failing when one is. Two absences reported as
    agreement is a verdict nobody asked for.
    """
    if not isinstance(row, Mapping):
        return False
    sides = _row_sides(row, (left, right), treat_blank_as_null=treat_blank_as_null)
    if sides is None:
        return _resolve_missing(on_missing)
    return sides[0] == sides[1]


def _present_values(column: Any, *, treat_blank_as_null: bool) -> list[Any] | None:
    if not isinstance(column, (list, tuple)):
        return None
    return [
        value
        for value in column
        if not _is_absent(value, treat_blank_as_null=treat_blank_as_null)
    ]


def _is_unique(column: Any, *, treat_blank_as_null: bool) -> bool:
    present = _present_values(column, treat_blank_as_null=treat_blank_as_null)
    if present is None:
        return False
    try:
        return len(set(present)) == len(present)
    except TypeError:
        return False


def _cardinality_at_most(column: Any, *, limit: int, treat_blank_as_null: bool) -> bool:
    present = _present_values(column, treat_blank_as_null=treat_blank_as_null)
    if present is None:
        return False
    try:
        return len(set(present)) <= limit
    except TypeError:
        return False


def _is_column(candidate: Any) -> bool:
    return isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes))


def _key_is_unique(
    frame: Any,
    *,
    fields: tuple[str, ...],
    on_missing: MissingPolicy,
    treat_blank_as_null: bool,
) -> bool:
    """No two rows share the same combination of `fields`.

    What a canonical schema's declared key needs: `energy/generation_v1` keys on
    `[measurement_point_id, reading_at]` (§7.6) and `is_unique` reads one column,
    so nothing in the registry could evaluate the key the schema declares.

    **A frame is column name → values, not a sequence of row mappings.** The
    columns are aligned by position, which is how Polars already holds them, and
    a key check needs two or three columns rather than the whole row. The
    rejected shape — a list of dicts — would build a Python dict per row, so a
    million-row batch pays a million allocations to answer a question about two
    columns, and `validate` (item 10) would be handed the wrong shape by the
    only interface that told it what to build.
    """
    if not isinstance(frame, Mapping):
        return False

    names = tuple(fields)
    if not names:
        return False

    columns = []
    for name in names:
        column = frame.get(name)
        if not _is_column(column):
            # A field the frame does not carry is a mapping problem, and `map`
            # plus §6.2.2's `declared_key_present` both fail on one before this
            # runs. Not `on_missing`'s question: that governs absent *values*.
            return False
        columns.append(column)

    lengths = {len(column) for column in columns}
    if len(lengths) > 1:
        raise FrameAlignmentError(
            f"frame columns disagree on length: "
            f"{ {name: len(column) for name, column in zip(names, columns)} }. "
            f"Zipping them would silently truncate to the shortest and report a "
            f"verdict over rows that do not exist"
        )

    seen: set[tuple[Any, ...]] = set()
    for row in zip(*columns):
        if any(_is_absent(value, treat_blank_as_null=treat_blank_as_null) for value in row):
            if not _resolve_missing(on_missing):
                return False
            continue
        try:
            if row in seen:
                return False
            seen.add(row)
        except TypeError:
            return False
    return True


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

    IS_NULL = ("is_null", _is_null, {"treat_blank_as_null": bool}, Scope.VALUE)
    IS_NOT_NULL = ("is_not_null", _is_not_null, {"treat_blank_as_null": bool}, Scope.VALUE)
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
        {
            "earlier": str,
            "later": str,
            "on_missing": MissingPolicy,
            "treat_blank_as_null": bool,
        },
        Scope.ROW,
    )
    FIELDS_EQUAL = (
        "fields_equal",
        _fields_equal,
        {
            "left": str,
            "right": str,
            "on_missing": MissingPolicy,
            "treat_blank_as_null": bool,
        },
        Scope.ROW,
    )

    IS_UNIQUE = ("is_unique", _is_unique, {"treat_blank_as_null": bool}, Scope.COLUMN)
    CARDINALITY_AT_MOST = (
        "cardinality_at_most",
        _cardinality_at_most,
        {"limit": int, "treat_blank_as_null": bool},
        Scope.COLUMN,
    )

    #: `is_unique` is kept beside this rather than replaced by it: a single
    #: column needs only a projection, and discovery Layer B's unique column
    #: combinations are mostly of size one. Two members, two cost classes.
    KEY_IS_UNIQUE = (
        "key_is_unique",
        _key_is_unique,
        {
            "fields": tuple,
            "on_missing": MissingPolicy,
            "treat_blank_as_null": bool,
        },
        Scope.FRAME,
    )


class PredicateParamError(ValueError):
    """A rule supplied parameters the predicate did not declare, or omitted some.

    Raised at *load*, never at evaluation. A rule whose parameters do not match
    its predicate is malformed, and the place to find that out is when the pack
    is read — not partway through a client's batch.

    This is also what makes the policy parameters mandatory rather than
    defaulted: a declared parameter that is not supplied is reported `missing`
    here, so there is no path by which a rule inherits a blank-handling or
    missing-side answer nobody chose.

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
        elif expected is bool:
            # Before int, and not merged with the general branch below: `bool`
            # is a subclass of `int`, so an unguarded `isinstance` check would
            # let `treat_blank_as_null: 1` through as if someone had chosen it.
            if not isinstance(value, bool):
                raise PredicateParamError(
                    f"{predicate.value}.{name}: expected true or false, got {value!r}"
                )
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
