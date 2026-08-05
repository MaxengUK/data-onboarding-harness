"""Checks that need the bound source read (§6.2.2 connectivity, schema, encoding, volume).

Each of these can be `UNAVAILABLE` for a reason that has nothing to do with
whether it is implemented: the probe may not have been able to establish the
fact the check compares against. That is why `CheckStatus.UNAVAILABLE` covers
both cases — in either one, nothing was verified, and a blocker that verified
nothing blocks.

**No source value appears in any detail below.** Byte offsets, counts, and
manifest-declared column names only. The natural breach here is the helpful
error message, and it would be written by someone trying to make the report more
useful — so the rule is stated where the details are written.
"""

from __future__ import annotations

from kernel.stages.preflight.contract import (
    CheckContext,
    Outcome,
    failed,
    not_applicable,
    passed,
    unavailable,
)
from kernel.stages.preflight.registry import implements


def _probe_gap(context: CheckContext) -> str | None:
    """Why the source could not be established, if it could not."""
    probe = context.source
    if probe.unsupported is not None:
        return probe.unsupported
    if probe.read_error is not None:
        return f"source could not be read: {probe.read_error}"
    return None


@implements("connectivity.source_reachable")
def source_reachable(context: CheckContext) -> Outcome:
    probe = context.source
    if probe.unsupported is not None:
        return unavailable(probe.unsupported)
    if probe.read_error is not None:
        return failed(f"{probe.location_uri or 'declared source'}: {probe.read_error}")
    return passed(f"read {probe.location_uri}")


@implements("schema.mapped_columns_exist")
def mapped_columns_exist(context: CheckContext) -> Outcome:
    gap = _probe_gap(context)
    if gap is not None:
        return unavailable(gap)

    probe = context.source
    if probe.columns is None:
        return unavailable("the source header could not be parsed")

    declared = tuple(context.manifest.sources[0].column_map)
    missing = tuple(name for name in declared if name not in probe.columns)

    if missing:
        # Missing names are manifest content, so naming them is safe and is the
        # whole point. The *source's* extra columns are deliberately counted
        # rather than listed — an unmapped header is still client content, and
        # nothing here needs it.
        return failed(
            f"{len(missing)} of {len(declared)} mapped columns are absent from "
            f"the source: {', '.join(missing)}"
        )

    return passed(
        f"all {len(declared)} mapped columns present "
        f"(delimiter {probe.delimiter!r}, sniffed and recorded)"
    )


@implements("encoding.declared_encoding_decodes")
def declared_encoding_decodes(context: CheckContext) -> Outcome:
    probe = context.source
    if probe.unsupported is not None:
        return unavailable(probe.unsupported)
    if probe.read_error is not None:
        return unavailable(f"source could not be read: {probe.read_error}")

    encoding = context.manifest.sources[0].encoding
    if probe.encoding_error is not None:
        return failed(f"declared encoding {encoding} does not decode the source: "
                      f"{probe.encoding_error}")

    return passed(f"declared encoding {encoding} decoded the whole object strictly")


@implements("encoding.collation_consistent")
def collation_consistent(context: CheckContext) -> Outcome:
    """The one genuine `NOT_APPLICABLE` in this build.

    Collation is a catalog property of a database. A file has none — not one
    this build cannot read, one that does not exist — so the check has no
    meaning for the manifest rather than no implementation. The distinction is
    drawn from `binding.kind`, a declared manifest fact, which is the only thing
    allowed to produce this status.
    """
    if context.manifest.sources[0].binding.kind == "file":
        return not_applicable("a file binding has no collation to be consistent about")
    return unavailable("needs a source adapter to read catalog collation")


@implements("volume.source_not_empty")
def source_not_empty(context: CheckContext) -> Outcome:
    gap = _probe_gap(context)
    if gap is not None:
        return unavailable(gap)

    row_count = context.source.row_count
    if row_count is None:
        return unavailable("the source could not be counted")
    if row_count == 0:
        return failed("the source holds no rows")

    return passed(f"{row_count} rows")


@implements("schema.canonical_schema_resolves")
def canonical_schema_resolves(context: CheckContext) -> Outcome:
    """§7.6. One id, one artifact — and the mapped fields must exist in it."""
    binding = context.binding
    if binding.error is not None:
        return failed(binding.error)

    if binding.unknown_fields:
        return failed(
            f"the column map names {len(binding.unknown_fields)} canonical "
            f"field(s) that {context.manifest.canonical_schema} does not "
            f"declare: {', '.join(binding.unknown_fields)}"
        )

    assert binding.schema is not None
    return passed(
        f"{binding.schema.id} resolved; {len(binding.columns)} of "
        f"{len(binding.schema.field_names)} canonical fields are mapped"
    )


@implements("schema.declared_key_present")
def declared_key_present(context: CheckContext) -> Outcome:
    """The canonical key must be mapped, or the output cannot be keyed.

    Read as "present in what this run will produce" rather than "present in the
    source": the key is a property of the canonical schema, and a run whose
    column map omits one of its fields will emit rows nothing can identify.
    `resolve` needs a key before it can cluster at all (§6).
    """
    binding = context.binding
    if not binding.resolved:
        return unavailable(binding.error or "the canonical schema did not resolve")

    assert binding.schema is not None
    mapped = {column.canonical_field for column in binding.columns}
    missing = tuple(name for name in binding.schema.key if name not in mapped)

    if missing:
        return failed(
            f"{binding.schema.id} declares key {list(binding.schema.key)}, and "
            f"the column map does not supply {', '.join(missing)}"
        )

    return passed(f"key {list(binding.schema.key)} is fully mapped")


@implements("schema.types_match_semantic_types")
def types_match_semantic_types(context: CheckContext) -> Outcome:
    """Compares a *declared* source type against the bound semantic type.

    **Not applicable to a file binding, and this is a property of the source
    rather than a gap in the build.** A CSV has no type system: every column is
    text, so there is no declared type to be compatible or incompatible with.
    The check has meaning against a database catalog, where an `integer` column
    bound to `person_name` or a `varchar` bound to `date` is a real finding — and
    that needs a source adapter this build does not have.

    **What this check is not**, because the two are easy to conflate and the
    confusion would put locale knowledge in the kernel: comparing the *observed
    shape* of values against their semantic type — 40% of a `date`-bound column
    failing to parse — is a different check entirely. It reads values rather than
    metadata, it needs locale-aware parsing, and it belongs to discovery Layer A
    (§9.1 format clustering), not to preflight. Preflight reads schema, catalog
    and aggregate metadata (§6.2.2); a check that has to parse every value to
    reach a verdict is by construction not one of its checks.
    """
    if context.manifest.sources[0].binding.kind == "file":
        return not_applicable(
            "a file binding declares no column types; type compatibility is a "
            "catalog property. Shape-versus-type is discovery Layer A's, not "
            "preflight's"
        )

    return unavailable("needs a source adapter to read catalog column types")


@implements("volume.max_timestamp_within_freshness_window")
def max_timestamp_within_freshness_window(context: CheckContext) -> Outcome:
    """§6.2.2 freshness, measured against the schema's declared freshness field.

    Ages are reported in hours rather than by quoting the newest value: the
    value is a source cell, and the answer the reader wants is the age.
    """
    binding = context.binding
    if not binding.resolved:
        return unavailable(binding.error or "the canonical schema did not resolve")

    assert binding.schema is not None
    if binding.freshness_column is None:
        return failed(
            f"{binding.schema.id} measures freshness on "
            f"{binding.schema.freshness_field!r}, which the column map does not "
            f"supply"
        )

    gap = _probe_gap(context)
    if gap is not None:
        return unavailable(gap)

    probe = context.source
    if probe.freshness_parsed == 0:
        return unavailable(
            f"no value in the freshness column parsed as ISO-8601 "
            f"({probe.freshness_total} row(s) read). Locale-aware date parsing "
            f"arrives with tr-core (BUILD-PLAN item 9); the kernel deliberately "
            f"reads only an interchange format"
        )

    assert probe.freshness_newest is not None
    age_hours = (context.now - probe.freshness_newest).total_seconds() / 3600
    window = context.manifest.preflight.freshness_window_hours

    if age_hours > window:
        return failed(
            f"the newest record is {age_hours:.1f}h old, outside the declared "
            f"{window}h freshness window"
        )

    return passed(
        f"newest record {age_hours:.1f}h old, inside the {window}h window "
        f"({probe.freshness_parsed}/{probe.freshness_total} values readable)"
    )


@implements("volume.row_count_within_bounds")
def row_count_within_bounds(context: CheckContext) -> Outcome:
    gap = _probe_gap(context)
    if gap is not None:
        return unavailable(gap)

    row_count = context.source.row_count
    if row_count is None:
        return unavailable("the source could not be counted")

    bounds = context.manifest.preflight.row_count_bounds
    if row_count < bounds.min:
        return failed(f"{row_count} rows is below the declared minimum {bounds.min}")
    if row_count > bounds.max:
        return failed(f"{row_count} rows is above the declared maximum {bounds.max}")

    return passed(f"{row_count} rows, inside [{bounds.min}, {bounds.max}]")
