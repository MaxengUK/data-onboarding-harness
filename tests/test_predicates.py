"""The closed predicate registry (CLAUDE.md §7.5, §0).

Three properties carry this file.

`test_a_predicate_cannot_be_declared_without_all_three` is the structural one:
implementation, parameter contract and scope are taken positionally by
`__new__`, so a member missing any of them fails at class creation. Scope is the
one that would otherwise default silently and fail latest — a column-scope
predicate handed a single cell returns a confident, meaningless answer.

`test_no_predicate_raises_on_any_input` is the operational one. §6 gives
`validate` exactly one reaction to bad data — quarantine (§6.1) — which it
cannot reach if the check itself exploded, so a predicate that raises converts a
data problem into a run failure.

The third is newer and is what the rest of this file mostly defends: **no
predicate answers a question it was not asked.** Whether a blank is an absence,
what a missing side means, and whether a pattern anchors were all decided inside
the kernel and invisible from a rule. Each is now a declaration, and each has a
test below that goes red the moment the declaration is replaced by a default.
"""

from __future__ import annotations

import inspect
from enum import Enum

import pytest

from kernel.checksums import is_valid_tckn, is_valid_vkn
from kernel.predicates import (
    ChecksumAlgorithm,
    FrameAlignmentError,
    MatchMode,
    MissingPolicy,
    PatternName,
    Predicate,
    PredicateParamError,
    Scope,
    check_params,
)
from tests.synthetic import find_valid_tckn, find_valid_vkn, iso_timestamp

#: Every input a predicate might be handed, including the ones that would make a
#: careless implementation raise.
HOSTILE_INPUTS = (
    None,
    "",
    "   ",
    0,
    -1,
    1.5,
    True,
    [],
    {},
    ["a", None],
    {"a": None},
    "N/A",
    "٢٠٢٦",
)

#: ASCII digits are the only ones the kernel treats as digits. Built as a
#: translation rather than as literal identifiers so nothing here resembles one.
TO_ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
TO_DEVANAGARI = str.maketrans("0123456789", "०१२३४५६७८९")

#: One value that satisfies each registered pattern. Every member needs an entry
#: — `test_every_pattern_has_an_example` fails otherwise — so a pattern added
#: without one cannot skip the trailing-whitespace sweep below.
VALID_EXAMPLES: dict[PatternName, str] = {
    PatternName.DIGITS: "12345",
    PatternName.ISO_DATE: "2026-08-01",
    PatternName.ISO_TIMESTAMP: iso_timestamp(),
    PatternName.NON_BLANK: "x",
    PatternName.EMAIL_SHAPE: "someone@example.com",
}


def sample_params(predicate: Predicate) -> dict:
    """Valid params for `predicate`, built from its declared contract."""
    defaults: dict[str, object] = {
        "pattern": PatternName.DIGITS,
        "algorithm": ChecksumAlgorithm.TCKN,
        "min": 0,
        "max": 10,
        "limit": 5,
        "values": ("a", "b"),
        "earlier": "a",
        "later": "b",
        "left": "a",
        "right": "b",
        "fields": ("a", "b"),
        "on_missing": MissingPolicy.FAIL,
        "treat_blank_as_null": True,
    }
    return {name: defaults[name] for name in predicate.params}


# --- the centre ---------------------------------------------------------------


def test_a_predicate_cannot_be_declared_without_all_three() -> None:
    """Structural, not conventional: the class fails to build.

    Note `__new_member__`, not `__new__`. Enum moves a custom `__new__` there
    during class creation and puts its own value-lookup constructor in its
    place — so a version of this test written against `__new__` raises
    `TypeError` from the lookup failing and proves nothing about the
    declaration contract. It passed that way until the sibling test below
    exposed it.
    """
    with pytest.raises(TypeError):

        class Incomplete(str, Enum):
            __new__ = Predicate.__new_member__

            FORGOTTEN = "forgotten"


def test_none_of_the_three_may_acquire_a_default() -> None:
    """Each is required *individually*, not just collectively.

    The test above only proves a member giving *nothing* fails. It passed
    unchanged when `scope` was given a default — and scope is precisely the
    declaration that would then default silently on the next predicate someone
    adds, which is the failure it exists to prevent. A default on any of the
    three turns a structural guarantee back into a convention.
    """
    parameters = inspect.signature(Predicate.__new_member__).parameters

    for name in ("value", "implementation", "params", "scope"):
        # Named-and-required, checked separately, because the two weakenings
        # look different: a default keeps the name, while collapsing the
        # signature to *args removes it. Asserting membership first turns the
        # second into a legible failure rather than a KeyError that reads like a
        # broken test.
        assert name in parameters, (
            f"Predicate.__new__ no longer names {name}. A signature that "
            f"absorbs its declarations into *args accepts a member that "
            f"declares nothing, which is what naming them prevents"
        )
        assert parameters[name].default is inspect.Parameter.empty, (
            f"Predicate.__new__ gives {name} a default, so a member can be "
            f"declared without it and inherit an answer nobody chose"
        )


def test_every_predicate_declares_all_three() -> None:
    for predicate in Predicate:
        assert callable(predicate.implementation)
        assert isinstance(predicate.params, dict)
        assert isinstance(predicate.scope, Scope)


def test_no_predicate_raises_on_any_input() -> None:
    """A predicate that raised would turn a data problem into a run failure."""
    for predicate in Predicate:
        params = sample_params(predicate)
        for value in HOSTILE_INPUTS:
            result = predicate.implementation(value, **params)
            assert isinstance(result, bool), f"{predicate.value} on {value!r}"


def test_the_registry_is_closed_to_names_it_does_not_ship() -> None:
    with pytest.raises(ValueError):
        Predicate("regex_match_but_invented")


# --- params are names, not content -------------------------------------------


def test_a_pattern_parameter_takes_a_registered_name_not_a_regex() -> None:
    """§7.5's central claim: the kernel cannot execute anything not shipped.

    A pack-authored regex would be executable content from outside the release,
    and a catastrophic-backtracking one is an availability incident in a
    client's environment rather than a bug in ours.
    """
    with pytest.raises(PredicateParamError, match="closed PatternName registry"):
        check_params(Predicate.MATCHES_PATTERN, {"pattern": r"^(a+)+$"})


def test_missing_and_unexpected_params_are_both_refused() -> None:
    with pytest.raises(PredicateParamError, match="missing"):
        check_params(Predicate.LENGTH_BETWEEN, {"min": 1})

    with pytest.raises(PredicateParamError, match="unexpected"):
        check_params(
            Predicate.IS_NULL,
            {"treat_blank_as_null": True, "pattern": PatternName.DIGITS},
        )


def test_a_param_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(PredicateParamError, match="expected int"):
        check_params(
            Predicate.CARDINALITY_AT_MOST, {"limit": "five", "treat_blank_as_null": True}
        )


def test_every_declared_param_is_accepted_by_its_implementation() -> None:
    """The contract and the signature cannot drift apart unnoticed."""
    for predicate in Predicate:
        check_params(predicate, sample_params(predicate))


# --- finding 1: anchoring is declared, and `$` does not anchor ----------------


def test_a_pattern_cannot_be_declared_without_regex_and_match_mode() -> None:
    """Same structural guarantee as `Predicate`, for the same reason.

    A pattern added as a bare `FOO = "foo"` would have no mode, and the only
    sensible fallback — search — is the one that lets a trailing newline
    through. So there is no fallback and the class refuses to build.
    """
    with pytest.raises(TypeError):

        class Incomplete(str, Enum):
            __new__ = PatternName.__new_member__

            FORGOTTEN = "forgotten"

    parameters = inspect.signature(PatternName.__new_member__).parameters
    for name in ("value", "regex", "mode"):
        assert name in parameters
        assert parameters[name].default is inspect.Parameter.empty, (
            f"PatternName.__new__ gives {name} a default, so a pattern can be "
            f"declared without it"
        )


def test_a_trailing_newline_does_not_satisfy_an_anchored_pattern() -> None:
    """The finding itself.

    In Python `$` matches at the end of the string *or* immediately before a
    trailing newline, and `matches_pattern` used `search`. So `"123\\n"`
    satisfied `digits`. A trailing newline or space in a CSV cell is precisely
    the dirt this harness exists to find, which made the validator pass the
    thing it was pointed at.
    """
    for pattern, value in (
        (PatternName.DIGITS, "12345"),
        (PatternName.ISO_DATE, "2026-08-01"),
        (PatternName.EMAIL_SHAPE, "someone@example.com"),
    ):
        assert Predicate.MATCHES_PATTERN.implementation(value, pattern=pattern)
        assert not Predicate.MATCHES_PATTERN.implementation(
            value + "\n", pattern=pattern
        ), f"{pattern.value} accepted a trailing newline"


def test_every_pattern_has_an_example() -> None:
    assert set(VALID_EXAMPLES) == set(PatternName), (
        "a pattern with no example escapes the trailing-whitespace sweep below, "
        "which is the sweep that catches the next `$`"
    )


def test_every_full_pattern_rejects_its_own_example_with_trailing_whitespace() -> None:
    """The generalisation of the test above, so a new pattern is covered too."""
    for pattern, example in VALID_EXAMPLES.items():
        assert Predicate.MATCHES_PATTERN.implementation(example, pattern=pattern), (
            f"{pattern.value} does not match its own example {example!r}"
        )
        if pattern.mode is not MatchMode.FULL:
            continue
        for suffix in ("\n", " ", "\r\n", "\t"):
            assert not Predicate.MATCHES_PATTERN.implementation(
                example + suffix, pattern=pattern
            ), f"{pattern.value} accepted a trailing {suffix!r}"


def test_no_full_mode_pattern_carries_its_own_anchors() -> None:
    """The mode anchors; the source must not restate it.

    Two anchors leave `$`'s leniency visible in a source someone will copy into
    a `SEARCH` pattern, where it is wrong again. Checked with
    `startswith`/`endswith` rather than substring containment, because
    `email_shape` legitimately contains `^` inside a negated character class.
    """
    for pattern in PatternName:
        if pattern.mode is not MatchMode.FULL:
            continue
        assert not pattern.source.startswith("^"), pattern.value
        assert not pattern.source.endswith("$"), pattern.value
        assert r"\Z" not in pattern.source, pattern.value


def test_search_mode_still_searches() -> None:
    """`non_blank` is why `fullmatch` everywhere was not the answer."""
    assert PatternName.NON_BLANK.mode is MatchMode.SEARCH
    assert Predicate.MATCHES_PATTERN.implementation("  x  ", pattern=PatternName.NON_BLANK)
    assert not Predicate.MATCHES_PATTERN.implementation("   ", pattern=PatternName.NON_BLANK)


# --- finding 2: a digit is an ASCII digit ------------------------------------


def test_non_ascii_digits_are_not_digits() -> None:
    """`\\d` spans Unicode decimal digits, and these arrive by copy-paste.

    A value that satisfies `digits` and then reaches `int()` or a checksum is
    either an exception or a confident answer about a value no issuing
    authority ever produced.
    """
    for translation in (TO_ARABIC_INDIC, TO_DEVANAGARI):
        foreign = "12345".translate(translation)
        assert not Predicate.MATCHES_PATTERN.implementation(
            foreign, pattern=PatternName.DIGITS
        ), f"{foreign!r} satisfied the digits pattern"


def test_a_checksum_refuses_non_ascii_digits() -> None:
    """The other half of the same finding, one module over.

    `str.isdigit()` is true for these and `int()` parses them, so without the
    ASCII restriction the checksum arithmetic ran over them and returned a
    verdict. The matcher and the validator have to see one universe.
    """
    for translation in (TO_ARABIC_INDIC, TO_DEVANAGARI):
        assert not is_valid_tckn(find_valid_tckn().translate(translation))
        assert not is_valid_vkn(find_valid_vkn().translate(translation))

    # The ASCII originals still pass, so the restriction did not just break it.
    assert is_valid_tckn(find_valid_tckn())
    assert is_valid_vkn(find_valid_vkn())


def test_no_kernel_digit_class_uses_the_unicode_shorthand() -> None:
    """Pins the decision across both modules that make it.

    `kernel/gates/guard.py` matches candidates and `kernel/checksums.py`
    validates them. A `\\d` in the first hands the second values it is now
    structurally incapable of vouching for.
    """
    from pathlib import Path

    import kernel.gates.guard as guard_module

    for module in (guard_module,):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.lstrip().startswith("#") or r"\\d" in line:
                continue
            assert r"\d" not in line, (
                f"{module.__name__} still uses the Unicode digit shorthand: "
                f"{line.strip()!r}"
            )

    for pattern in PatternName:
        assert r"\d" not in pattern.source, pattern.value


# --- findings 3 and 5: absence is declared, never assumed --------------------


def test_a_row_predicate_declares_what_a_missing_side_means() -> None:
    """No default, so a rule author cannot inherit one.

    `check_params` reports an omitted declaration as `missing`, which is what
    makes "no hidden default" structural rather than a convention.
    """
    for predicate in (Predicate.FIELD_BEFORE, Predicate.FIELDS_EQUAL, Predicate.KEY_IS_UNIQUE):
        assert "on_missing" in predicate.params
        with pytest.raises(PredicateParamError, match="missing.*on_missing"):
            params = sample_params(predicate)
            del params["on_missing"]
            check_params(predicate, params)


def test_field_before_fails_closed_when_asked_to() -> None:
    """The finding: this used to pass whenever either side was absent.

    `delivery_date < order_date` silently passing on every row with no
    `order_date` is P7 inverted — fail-closed on data is the constitutional
    default, and the rows with a missing date are the ones most likely wrong.
    """
    incomplete = {"order_date": "2026-01-01"}
    assert not Predicate.FIELD_BEFORE.implementation(
        incomplete,
        earlier="order_date",
        later="delivery_date",
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )
    assert Predicate.FIELD_BEFORE.implementation(
        incomplete,
        earlier="order_date",
        later="delivery_date",
        on_missing=MissingPolicy.PASS,
        treat_blank_as_null=True,
    )
    # The ordering itself still works when both sides are there.
    assert not Predicate.FIELD_BEFORE.implementation(
        {"order_date": "2026-02-01", "delivery_date": "2026-01-01"},
        earlier="order_date",
        later="delivery_date",
        on_missing=MissingPolicy.PASS,
        treat_blank_as_null=True,
    )


def test_fields_equal_does_not_call_two_absences_agreement() -> None:
    """The quieter half of the same finding.

    A bare `row.get(left) == row.get(right)` passes when both sides are
    missing, because `None == None`, while failing when only one is.
    """
    assert not Predicate.FIELDS_EQUAL.implementation(
        {},
        left="a",
        right="b",
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )
    assert Predicate.FIELDS_EQUAL.implementation(
        {"a": "x", "b": "x"},
        left="a",
        right="b",
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )


def test_an_unrecognised_missing_policy_fails_closed() -> None:
    """Unreachable through `Rule`, but the direction of the fallback matters."""
    assert not Predicate.FIELD_BEFORE.implementation(
        {},
        earlier="a",
        later="b",
        on_missing="whatever-a-broken-loader-supplied",
        treat_blank_as_null=True,
    )


# --- finding 4: one answer to "is a blank an absence" ------------------------

#: Every predicate that branches on absence. Pinned because the failure being
#: guarded is a *removal* — a predicate quietly reverting to a hardcoded answer
#: while the others keep asking.
ABSENCE_AWARE = {
    Predicate.IS_NULL,
    Predicate.IS_NOT_NULL,
    Predicate.IS_UNIQUE,
    Predicate.CARDINALITY_AT_MOST,
    Predicate.FIELD_BEFORE,
    Predicate.FIELDS_EQUAL,
    Predicate.KEY_IS_UNIQUE,
}


def test_every_absence_aware_predicate_declares_the_blank_policy() -> None:
    declaring = {p for p in Predicate if "treat_blank_as_null" in p.params}
    assert declaring == ABSENCE_AWARE, (
        "a predicate that branches on absence without declaring the policy has "
        "hardcoded a client decision (P3)"
    )


def test_the_blank_policy_has_no_default() -> None:
    for predicate in sorted(ABSENCE_AWARE, key=lambda p: p.value):
        params = sample_params(predicate)
        del params["treat_blank_as_null"]
        with pytest.raises(PredicateParamError, match="missing.*treat_blank_as_null"):
            check_params(predicate, params)


def test_a_blank_is_absent_or_present_everywhere_at_once() -> None:
    """One question, one answer, across every predicate that asks it.

    The old code answered it twice and differently: `is_null` treated `"   "` as
    absent while the row predicates tested `is None` and treated it as present.
    Each column below is one policy setting, and every predicate has to agree
    with the rest of its column.
    """
    for treat_blank_as_null, blank_is_absent in ((True, True), (False, False)):
        assert (
            Predicate.IS_NULL.implementation(
                "   ", treat_blank_as_null=treat_blank_as_null
            )
            is blank_is_absent
        )
        assert (
            Predicate.IS_NOT_NULL.implementation(
                "   ", treat_blank_as_null=treat_blank_as_null
            )
            is not blank_is_absent
        )
        # Two blanks: two absences are not a duplicate, two values are.
        assert (
            Predicate.IS_UNIQUE.implementation(
                ["   ", "   "], treat_blank_as_null=treat_blank_as_null
            )
            is blank_is_absent
        )
        # One blank beside one value: an absence does not count toward
        # cardinality, a value does.
        assert (
            Predicate.CARDINALITY_AT_MOST.implementation(
                ["   ", "x"], limit=1, treat_blank_as_null=treat_blank_as_null
            )
            is blank_is_absent
        )
        # A blank side is either `on_missing`'s business or an ordinary value
        # that happens to sort early.
        assert (
            Predicate.FIELD_BEFORE.implementation(
                {"a": "   ", "b": "2026-01-01"},
                earlier="a",
                later="b",
                on_missing=MissingPolicy.FAIL,
                treat_blank_as_null=treat_blank_as_null,
            )
            is not blank_is_absent
        )
        assert (
            Predicate.KEY_IS_UNIQUE.implementation(
                {"a": ["   ", "   "], "b": ["x", "x"]},
                fields=("a", "b"),
                on_missing=MissingPolicy.PASS,
                treat_blank_as_null=treat_blank_as_null,
            )
            is blank_is_absent
        )


def test_a_null_is_absent_under_either_policy() -> None:
    """`treat_blank_as_null` governs the blank, never the NULL itself."""
    for treat_blank_as_null in (True, False):
        assert Predicate.IS_NULL.implementation(
            None, treat_blank_as_null=treat_blank_as_null
        )


# --- finding 5: the declared key of a canonical schema can be evaluated ------


def test_a_composite_key_violation_is_caught() -> None:
    """`is_unique` reads one column, and a canonical key is usually not one."""
    duplicated = {
        "measurement_point_id": ["mp-1", "mp-1", "mp-2"],
        "reading_at": ["2026-08-01", "2026-08-01", "2026-08-01"],
    }
    assert not Predicate.KEY_IS_UNIQUE.implementation(
        duplicated,
        fields=("measurement_point_id", "reading_at"),
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )
    # Neither column is unique on its own, so no single-column check finds this.
    for column in duplicated.values():
        assert not Predicate.IS_UNIQUE.implementation(column, treat_blank_as_null=True)

    distinct = {
        "measurement_point_id": ["mp-1", "mp-1", "mp-2"],
        "reading_at": ["2026-08-01", "2026-08-02", "2026-08-01"],
    }
    assert Predicate.KEY_IS_UNIQUE.implementation(
        distinct,
        fields=("measurement_point_id", "reading_at"),
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )


def test_the_declared_key_of_a_canonical_schema_can_be_evaluated() -> None:
    """The reason this predicate exists, tied to the artifact that needed it."""
    from kernel.canonical import resolve_canonical_schema

    schema = resolve_canonical_schema("energy/generation_v1")
    assert len(schema.key) > 1, (
        "this test is pointless if the schema's key became single-column; "
        "re-point it at a composite one"
    )

    # Both directions, and the clean frame is the load-bearing half: every
    # column in it repeats, so only the *combination* distinguishes the rows. An
    # implementation that read one field would call this a violation, which is
    # how this test earns the word "composite" in its name. Asserting the
    # violating frame alone passed such an implementation happily.
    first, *rest = schema.key
    clean = {first: ["a", "a", "b"]} | {name: ["p", "q", "p"] for name in rest}
    assert Predicate.KEY_IS_UNIQUE.implementation(
        clean,
        fields=schema.key,
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )

    colliding = {name: ["a", "a", "b"] for name in schema.key}
    assert not Predicate.KEY_IS_UNIQUE.implementation(
        colliding,
        fields=schema.key,
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )


def test_a_frame_is_columns_not_rows() -> None:
    """The shape decision, asserted so it cannot drift.

    Column name → values, aligned by position: what Polars already holds, and
    what a two-column key check needs. A sequence of row mappings would build a
    Python dict per row to answer a question about two columns.
    """
    assert Predicate.KEY_IS_UNIQUE.scope is Scope.FRAME
    assert not Predicate.KEY_IS_UNIQUE.implementation(
        [{"a": 1, "b": 2}, {"a": 1, "b": 2}],
        fields=("a", "b"),
        on_missing=MissingPolicy.FAIL,
        treat_blank_as_null=True,
    )


def test_misaligned_columns_raise_rather_than_truncate() -> None:
    """`zip` stops at the shortest column and reports a clean verdict.

    The one input this module raises on, and deliberately: a frame whose
    columns disagree about how many rows there are is a caller that built the
    projection wrong, not data. Returning `False` would attribute a harness bug
    to the client's data (P8); returning `True` would hide the rows that were
    dropped.
    """
    with pytest.raises(FrameAlignmentError, match="truncate"):
        Predicate.KEY_IS_UNIQUE.implementation(
            {"a": ["x", "y", "z"], "b": ["1", "2"]},
            fields=("a", "b"),
            on_missing=MissingPolicy.FAIL,
            treat_blank_as_null=True,
        )

    # Would have been reported unique: the duplicate sits in the truncated tail.
    with pytest.raises(FrameAlignmentError):
        Predicate.KEY_IS_UNIQUE.implementation(
            {"a": ["x", "y", "x"], "b": ["1", "2", "1"], "c": ["p", "q"]},
            fields=("a", "b", "c"),
            on_missing=MissingPolicy.FAIL,
            treat_blank_as_null=True,
        )


def test_every_scope_has_a_predicate_and_frame_is_the_plural_of_column() -> None:
    scopes = {predicate.scope for predicate in Predicate}

    assert scopes == set(Scope), "a scope with no predicate is an unused concept"
    assert Predicate.IS_UNIQUE.scope is Scope.COLUMN
    assert Predicate.KEY_IS_UNIQUE.scope is Scope.FRAME
    assert Predicate.FIELD_BEFORE.scope is Scope.ROW
    assert Predicate.MATCHES_PATTERN.scope is Scope.VALUE


# --- the two small fixes ------------------------------------------------------


def test_is_iso_date_rejects_a_timestamp() -> None:
    """The name said date, `datetime.fromisoformat` accepted a datetime.

    Fixed on the behaviour side rather than the name, because the predicate's
    job is the one the pattern cannot do: `matches_pattern(iso_date)` answers
    "right shape", this answers "date that exists".
    """
    assert Predicate.IS_ISO_DATE.implementation("2026-08-01")
    assert not Predicate.IS_ISO_DATE.implementation(iso_timestamp())
    assert not Predicate.IS_ISO_DATE.implementation("2026-08-01T00:00:00")
    # The half the pattern cannot reach: right shape, no such day.
    assert Predicate.MATCHES_PATTERN.implementation(
        "2026-02-30", pattern=PatternName.ISO_DATE
    )
    assert not Predicate.IS_ISO_DATE.implementation("2026-02-30")


def test_nan_and_inf_are_not_numeric() -> None:
    """`float()` accepts all three, and `in_range` then fails inexplicably.

    Every comparison against a `nan` is False, so the rule reports a violation
    whose cause is in neither the value nor the bounds. A rule that fails for no
    findable reason is worse than one that fails (P8).
    """
    for value in ("nan", "NaN", "inf", "-inf", "Infinity", float("nan"), float("inf")):
        assert not Predicate.IS_NUMERIC.implementation(value), repr(value)
        assert not Predicate.IN_RANGE.implementation(value, min=0.0, max=10.0), repr(value)

    assert Predicate.IS_NUMERIC.implementation("3.5")
    assert Predicate.IN_RANGE.implementation("3.5", min=0.0, max=10.0)


# --- behaviour retained from before ------------------------------------------


def test_checksum_predicates_agree_with_the_shared_algorithms() -> None:
    assert Predicate.HAS_CHECKSUM.implementation(
        find_valid_tckn(), algorithm=ChecksumAlgorithm.TCKN
    )
    assert Predicate.HAS_CHECKSUM.implementation(
        find_valid_vkn(), algorithm=ChecksumAlgorithm.VKN
    )
    assert not Predicate.HAS_CHECKSUM.implementation(
        "1" * 11, algorithm=ChecksumAlgorithm.TCKN
    )


def test_iso_patterns_accept_what_the_kernel_reads_elsewhere() -> None:
    """The freshness probe reads ISO-8601, and a rule should be able to assert
    the same shape without a second definition of it."""
    assert Predicate.MATCHES_PATTERN.implementation(
        iso_timestamp(), pattern=PatternName.ISO_TIMESTAMP
    )
    assert Predicate.MATCHES_PATTERN.implementation(
        "2026-08-01", pattern=PatternName.ISO_DATE
    )
    assert not Predicate.MATCHES_PATTERN.implementation(
        "01.08.2026", pattern=PatternName.ISO_DATE
    )


def test_column_predicates_ignore_nulls() -> None:
    """Two empty cells are not a uniqueness violation; they are two unknowns."""
    assert Predicate.IS_UNIQUE.implementation(
        ["a", None, "b", ""], treat_blank_as_null=True
    )
    assert not Predicate.IS_UNIQUE.implementation(["a", "a"], treat_blank_as_null=True)
