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


class SemanticType(str, Enum):
    """What a column *means*, independent of what the client called it."""

    # --- PII-typed ---
    TCKN = "tckn"
    VKN = "vkn"
    PHONE_MOBILE = "phone_mobile"
    EMAIL = "email"
    PERSON_NAME = "person_name"
    ADDRESS = "address"
    VEHICLE_PLATE = "vehicle_plate"
    CHASSIS_NO = "chassis_no"

    # --- not PII-typed ---
    BRAND = "brand"
    MODEL = "model"
    CATEGORY = "category"
    PROVINCE_CODE = "province_code"
    DATE = "date"
    CURRENCY_AMOUNT = "currency_amount"
    COUNT = "count"
    OPAQUE_KEY = "opaque_key"


#: Drives the §8 egress rules and the §6.2.2 undeclared-column check.
#: A type is PII-typed if it identifies a natural person either on its own or
#: in combination with data the recipient can reasonably obtain. Chassis and
#: plate are here deliberately: both resolve to an owner through registries a
#: recipient can reach, so treating them as vehicle attributes would be wrong.
PII_SEMANTIC_TYPES: frozenset[SemanticType] = frozenset(
    {
        SemanticType.TCKN,
        SemanticType.VKN,
        SemanticType.PHONE_MOBILE,
        SemanticType.EMAIL,
        SemanticType.PERSON_NAME,
        SemanticType.ADDRESS,
        SemanticType.VEHICLE_PLATE,
        SemanticType.CHASSIS_NO,
    }
)


def is_pii(semantic_type: SemanticType) -> bool:
    return semantic_type in PII_SEMANTIC_TYPES


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
