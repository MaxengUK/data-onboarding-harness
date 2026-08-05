"""The closed predicate registry (CLAUDE.md §7.5, §0).

Two properties carry this file.

`test_a_predicate_cannot_be_declared_without_all_three` is the structural one:
implementation, parameter contract and scope are taken positionally by
`__new__`, so a member missing any of them fails at class creation. Scope is the
one that would otherwise default silently and fail latest — a column-scope
predicate handed a single cell returns a confident, meaningless answer.

`test_no_predicate_raises_on_any_input` is the operational one. §6 gives
`validate` exactly one reaction to bad data — quarantine (§6.1) — which it
cannot reach if the check itself exploded, so a predicate that raises converts a
data problem into a run failure.
"""

from __future__ import annotations

import inspect
from enum import Enum

import pytest

from kernel.predicates import (
    ChecksumAlgorithm,
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
        check_params(Predicate.IS_NULL, {"pattern": PatternName.DIGITS})


def test_a_param_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(PredicateParamError, match="expected int"):
        check_params(Predicate.CARDINALITY_AT_MOST, {"limit": "five"})


def test_every_declared_param_is_accepted_by_its_implementation() -> None:
    """The contract and the signature cannot drift apart unnoticed."""
    for predicate in Predicate:
        check_params(predicate, sample_params(predicate))


# --- behaviour ----------------------------------------------------------------


def test_null_and_blank_are_the_same_thing() -> None:
    """A CSV has no NULL: an empty cell arrives as an empty string, and a rule
    author should not have to write both checks."""
    for empty in (None, "", "   "):
        assert Predicate.IS_NULL.implementation(empty)
        assert not Predicate.IS_NOT_NULL.implementation(empty)


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


def test_a_row_predicate_passes_when_a_side_is_missing() -> None:
    """A row missing one side is a mapping problem, and reporting it here would
    attribute it to the wrong rule — `map` fails on an unmapped field first."""
    assert Predicate.FIELD_BEFORE.implementation(
        {"order_date": "2026-01-01"}, earlier="order_date", later="delivery_date"
    )
    assert not Predicate.FIELD_BEFORE.implementation(
        {"order_date": "2026-02-01", "delivery_date": "2026-01-01"},
        earlier="order_date",
        later="delivery_date",
    )


def test_column_predicates_ignore_nulls() -> None:
    """Two empty cells are not a uniqueness violation; they are two unknowns."""
    assert Predicate.IS_UNIQUE.implementation(["a", None, "b", ""])
    assert not Predicate.IS_UNIQUE.implementation(["a", "a"])


def test_scopes_are_declared_where_they_are_needed() -> None:
    scopes = {predicate.scope for predicate in Predicate}

    assert scopes == set(Scope), "a scope with no predicate is an unused concept"
    assert Predicate.IS_UNIQUE.scope is Scope.COLUMN
    assert Predicate.FIELD_BEFORE.scope is Scope.ROW
    assert Predicate.MATCHES_PATTERN.scope is Scope.VALUE
