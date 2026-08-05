"""Closed, kernel-owned vocabularies (CLAUDE.md §7.5).

Packs reference these by name and may not extend them inline. A closed registry
is serialisable, diffable, reviewable, and cannot name anything that was not
shipped in the release — which is what makes `applies_to.semantic_type` a
portable binding and what lets §8 allow "transform names" into evidence at all.

This is the seed the §7.5 registries grow from: only the members the egress gate
needs today are listed. BUILD-PLAN item 3 extends *this file* rather than
starting a second registry beside it.

Note on §0 and §3: entries here are concept names, never locale or client
strings. There is no `tr_msisdn_canonical` transform — there is
`CANONICALIZE_PHONE`, whose locale is a parameter supplied by a pack.
"""

from enum import Enum
from typing import Self


# **Every member declares whether it is PII-typed, as part of being a member.**
#
# The declaration used to be a `frozenset` beside the enum, which meant a type
# added without being added to the set defaulted to non-PII — silently, and
# non-PII types are eligible for §8.1 distinct-value export. The failure was a
# forgotten line making a column's values exportable, with nothing to notice it.
#
# Declaring it in the member makes the omission impossible rather than
# reviewable: `__new__` takes the flag positionally, so `FOO = "foo"` raises a
# TypeError at class creation and the import fails. There is no state in which a
# member exists without a classification.
#
# The `str` value is unaffected — `SemanticType.TCKN == "tckn"` and
# `.value == "tckn"` both hold — so Pydantic validation, JSON Schema generation
# and the egress gate's isinstance membership check behave exactly as before.
#
# A type is PII-typed if it identifies a natural person either on its own or in
# combination with data the recipient can reasonably obtain. Chassis and plate
# are PII-typed deliberately: both resolve to an owner through registries a
# recipient can reach, so treating them as vehicle attributes would be wrong.
#
# Kept out of the class docstring on purpose: `schemas/export_json_schema.py`
# publishes that docstring as the type's `description` in every generated JSON
# Schema, and a rationale about `__new__` is not something a schema consumer has
# any use for.
class SemanticType(str, Enum):
    """What a column means, independent of what the client called it.

    Each member declares whether it is PII-typed (§7.5, §8).
    """

    def __new__(cls, value: str, is_pii: bool) -> Self:
        member = str.__new__(cls, value)
        member._value_ = value
        member.is_pii = is_pii
        return member

    is_pii: bool

    TCKN = ("tckn", True)
    VKN = ("vkn", True)
    PHONE_MOBILE = ("phone_mobile", True)
    EMAIL = ("email", True)
    PERSON_NAME = ("person_name", True)
    ADDRESS = ("address", True)
    VEHICLE_PLATE = ("vehicle_plate", True)
    CHASSIS_NO = ("chassis_no", True)

    BRAND = ("brand", False)
    MODEL = ("model", False)
    CATEGORY = ("category", False)
    PROVINCE_CODE = ("province_code", False)
    DATE = ("date", False)
    CURRENCY_AMOUNT = ("currency_amount", False)
    COUNT = ("count", False)
    OPAQUE_KEY = ("opaque_key", False)
    #: Energy sector (§9.5 `prior` mode). A metered quantity in MWh — not a
    #: currency amount, which is what it would otherwise be forced into, and the
    #: distinction matters because the rules that apply to it come from physics
    #: (generation ≥ 0, efficiency ≤ theoretical ceiling) rather than from money.
    #:
    #: A sector type in the kernel registry is not a P3 violation: §8 permits
    #: semantic type labels to cross the boundary *because* MAXENG owns the word
    #: list and ships it in the release, so a pack that could add one at runtime
    #: would put an externally-authored string into a permitted egress class.
    #: The type is kernel-owned; its shape and its rules belong to a pack.
    ENERGY_QUANTITY = ("energy_quantity", False)


def is_pii(semantic_type: SemanticType) -> bool:
    """Kept as a function because `kernel.gates.egress_gate` reads it that way.

    Delegates to the member's own flag; there is no second source of truth to
    drift from.
    """
    return semantic_type.is_pii


class TransformName(str, Enum):
    """Closed enum §8 requires before a transform name may enter evidence."""

    TRIM = "trim"
    COLLAPSE_WHITESPACE = "collapse_whitespace"
    CASEFOLD = "casefold"
    PARSE_DATE = "parse_date"
    PARSE_DECIMAL = "parse_decimal"
    CANONICALIZE_PHONE = "canonicalize_phone"
    CANONICALIZE_TAX_ID = "canonicalize_tax_id"
    CANONICALIZE_PLATE = "canonicalize_plate"


class DiscoveryAlgorithm(str, Enum):
    """Layer-qualified algorithm names from §9.1."""

    A_FORMAT_CLUSTER = "a_structural.format_cluster"
    A_CONSTRAINT_SUGGEST = "a_structural.constraint_suggest"
    B_FUNCTIONAL_DEPENDENCY = "b_dependency.hyfd"
    B_UNIQUE_COLUMN_COMBINATION = "b_dependency.ucc"
    B_INCLUSION_DEPENDENCY = "b_dependency.ind"
    B_DENIAL_CONSTRAINT = "b_dependency.denial"
    C_TEMPORAL_BASELINE = "c_temporal.baseline"
    D_SEMANTIC_LABEL = "d_semantic.llm_label"


class StageName(str, Enum):
    """The §6 pipeline stages."""

    PREFLIGHT = "preflight"
    INGEST = "ingest"
    PROFILE = "profile"
    DISCOVER = "discover"
    MAP = "map"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    RESOLVE = "resolve"
    EMIT = "emit"


class RuleState(str, Enum):
    """The §11 rule lifecycle."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    ENFORCED = "enforced"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


class ConfidenceBand(str, Enum):
    """The §9.2 confidence bands."""

    TRIVIAL = "trivial"
    MONEY = "money"
    AMBIGUOUS = "ambiguous"
    NOISE = "noise"
