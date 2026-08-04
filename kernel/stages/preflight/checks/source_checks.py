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
