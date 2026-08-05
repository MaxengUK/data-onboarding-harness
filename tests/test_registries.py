"""The closed registries, and the PII declaration that cannot be forgotten (§7.5, §8).

The centre is `test_a_member_cannot_be_declared_without_its_pii_flag`. Everything
§8 permits about semantic types rests on the vocabulary being closed and
MAXENG-owned, and everything §8.1 forbids rests on knowing which types are
PII-typed. When that knowledge lived in a `frozenset` beside the enum, adding a
type and forgetting the set made it non-PII in silence — and non-PII types are
eligible for distinct-value export, so a forgotten line was an export channel.

The rest of this file guards the properties the restructuring had to preserve:
the value stays a plain string, so Pydantic, JSON Schema and the egress gate's
membership check are unaffected.
"""

from __future__ import annotations

import inspect
from enum import Enum

import pytest
from pydantic import BaseModel, ValidationError

from kernel.gates.egress_gate import EgressPolicy, EgressViolation, validate_for_egress
from kernel.registries import SemanticType, is_pii

# --- the centre --------------------------------------------------------------


def test_a_member_cannot_be_declared_without_its_pii_flag() -> None:
    """Structural, not conventional: the class fails to build.

    This is the whole reason the flag moved into the member. A reviewer can miss
    a line; a class that will not import cannot be missed.
    """
    with pytest.raises(TypeError):

        class Incomplete(str, Enum):
            # `__new_member__`, not `__new__`: Enum moves a custom `__new__`
            # there and substitutes its own value-lookup constructor, so a test
            # written against `__new__` raises from the lookup failing and
            # proves nothing about the declaration contract.
            __new__ = SemanticType.__new_member__

            FORGOTTEN = "forgotten"


def test_the_pii_flag_may_not_acquire_a_default() -> None:
    """Required individually, which the test above does not establish.

    A default on `is_pii` would let the next semantic type inherit non-PII
    without anyone choosing it — and non-PII types are eligible for §8.1
    distinct-value export.
    """
    parameters = inspect.signature(SemanticType.__new_member__).parameters

    for name in ("value", "is_pii"):
        # Named first, then required. The two weakenings look different: a
        # default keeps the name, while collapsing to *args removes it, and
        # without the first assertion the second reports a KeyError that reads
        # like a broken test rather than a removed guarantee.
        assert name in parameters, (
            f"SemanticType.__new__ no longer names {name}; a signature that "
            f"absorbs it into *args accepts a member declaring nothing"
        )
        assert parameters[name].default is inspect.Parameter.empty, (
            f"SemanticType.__new__ gives {name} a default, so the next type "
            f"added inherits a classification nobody chose"
        )


def test_every_type_is_classified() -> None:
    """No member may be unclassified, and the test does not enumerate them.

    Listing the expected PII set here would recreate the second source of truth
    the restructuring removed — it would pass while disagreeing with the enum.
    """
    for semantic_type in SemanticType:
        assert isinstance(semantic_type.is_pii, bool)


def test_the_pii_set_is_neither_empty_nor_everything() -> None:
    """A degenerate classification would satisfy the test above while being
    useless: all-PII blocks every §8.1 export, none-PII permits every one."""
    pii = {t for t in SemanticType if t.is_pii}

    assert pii, "no PII-typed members; §8.1 would permit distinct values of everything"
    assert pii != set(SemanticType), "everything is PII-typed; check the flags"


def test_identifiers_that_resolve_to_an_owner_are_pii_typed() -> None:
    """§7.5's judgment call, pinned because it is the one people argue with.

    Chassis and plate look like vehicle attributes and are not: both resolve to
    an owner through registries a recipient can reasonably reach, which is the
    §8.2 Leg 2 test applied at the type level rather than at the artifact level.
    """
    for semantic_type in (SemanticType.CHASSIS_NO, SemanticType.VEHICLE_PLATE):
        assert semantic_type.is_pii


def test_is_pii_delegates_rather_than_holding_a_second_answer() -> None:
    for semantic_type in SemanticType:
        assert is_pii(semantic_type) is semantic_type.is_pii


# --- what the restructuring had to leave alone --------------------------------


def test_the_value_is_still_a_plain_string() -> None:
    assert SemanticType.TCKN.value == "tckn"
    assert SemanticType.TCKN == "tckn"
    assert isinstance(SemanticType.TCKN, str)


def test_pydantic_still_validates_and_dumps_by_value() -> None:
    class Model(BaseModel):
        semantic_type: SemanticType

    assert Model.model_validate({"semantic_type": "vkn"}).semantic_type is SemanticType.VKN
    assert Model(semantic_type=SemanticType.BRAND).model_dump(mode="json") == {
        "semantic_type": "brand"
    }

    with pytest.raises(ValidationError):
        Model.model_validate({"semantic_type": "not_a_registered_type"})


def test_json_schema_still_lists_the_values() -> None:
    class Model(BaseModel):
        semantic_type: SemanticType

    rendered = Model.model_json_schema()["$defs"]["SemanticType"]["enum"]

    assert set(rendered) == {t.value for t in SemanticType}


def test_the_egress_gate_still_refuses_a_bare_string() -> None:
    """§8 permits a semantic type *label* because membership is checked. A raw
    string that happens to match must not pass as one."""
    from typing import Annotated

    from kernel.gates.egress_gate import Egress, EgressKind, EgressModel

    class Node(EgressModel):
        semantic_type: Annotated[str, Egress(EgressKind.SEMANTIC_TYPE)]

    with pytest.raises(EgressViolation, match="closed SemanticType registry"):
        validate_for_egress(Node(semantic_type="tckn"), EgressPolicy(k_anonymity_min=5))


# --- the sector type ----------------------------------------------------------


def test_the_energy_type_exists_and_is_not_a_currency_amount() -> None:
    """§9.5 puts energy in `prior` mode: its rules come from physics, not money.

    Forcing a metered MWh quantity into `currency_amount` would bind it to the
    wrong rule family and make `reuse_ratio` count a match that is not one.
    """
    assert SemanticType.ENERGY_QUANTITY.value == "energy_quantity"
    assert not SemanticType.ENERGY_QUANTITY.is_pii
    assert SemanticType.ENERGY_QUANTITY is not SemanticType.CURRENCY_AMOUNT
