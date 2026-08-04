"""The Preflight Report carries no source values (CLAUDE.md §6.2.2, §8.2 Leg 1).

§6.2.2: where a check needs values it samples within the declared limit and
discards the sample — samples never reach the report. The way that gets breached
is not a leak, it is a **helpful error message**: `column 'Müşteri GSM' contains
invalid value '5551234567'` is what somebody writes while trying to make a
report more useful, and it is a source value in a document.

So this file is Leg 1's shape applied to preflight: a source seeded with
recognisable PII markers is run end to end, and no marker may appear anywhere in
the rendered report. Markers are constructed at runtime (§0), never as literals.
"""

from __future__ import annotations

from pathlib import Path

from kernel.stages.preflight import render_report, run_preflight
from tests.conftest import KERNEL_VERSION, manifest_with
from tests.synthetic import (
    find_valid_tckn,
    synthetic_local_msisdn,
    synthetic_person_name,
)


def seeded_source(source_dir: Path) -> tuple[str, ...]:
    """A source whose every cell is a recognisable marker, and the marker list.

    Deliberately dirty in the ways that make a check *want* to quote a value:
    an undeclared PII column, a sentinel in a numeric column, and a row that is
    ragged relative to the header.
    """
    tckn = find_valid_tckn()
    msisdn = synthetic_local_msisdn()
    name = synthetic_person_name()

    source_dir.joinpath("generation.csv").write_text(
        "Uretim;TCKN;GSM;AdSoyad\n"
        f"N/A;{tckn};{msisdn};{name}\n"
        f"120.5;{tckn};{msisdn};{name};fazladan\n",
        encoding="utf-8",
    )
    return (tckn, msisdn, name)


def test_no_source_value_reaches_the_rendered_report(source_dir, environment) -> None:
    markers = seeded_source(source_dir)

    rendered = render_report(
        run_preflight(manifest_with(), kernel_version=KERNEL_VERSION, environment=environment)
    )

    for marker in markers:
        assert marker not in rendered, (
            "a source value reached the Preflight Report. §6.2.2 requires that "
            "samples never reach it, and the usual cause is an error message "
            "quoting the offending cell"
        )


def test_no_source_value_reaches_any_check_detail(source_dir, environment) -> None:
    """Asserted on the structured results too, not only on the rendering.

    A renderer that happened to truncate would make the first test pass while
    the value sat in the report object, one `model_dump()` away from a log line.
    """
    markers = seeded_source(source_dir)

    report = run_preflight(
        manifest_with(), kernel_version=KERNEL_VERSION, environment=environment
    )
    serialised = str(report.model_dump())

    for marker in markers:
        assert marker not in serialised


def test_an_encoding_failure_reports_a_position_not_the_bytes(
    source_dir, environment
) -> None:
    """The check most tempted to quote the source, since the offending bytes are
    exactly what a reader wants."""
    source_dir.joinpath("generation.csv").write_bytes(
        "Uretim;Sehir\n120.5;İstanbul\n".encode("cp1254")
    )

    report = run_preflight(
        manifest_with(), kernel_version=KERNEL_VERSION, environment=environment
    )
    detail = next(
        line.detail
        for line in report.results
        if line.check_id == "encoding.declared_encoding_decodes"
    )

    assert "byte offset" in detail
    assert "\\x" not in detail and "0x" not in detail


def test_the_report_names_declaration_class_rows_distinctly(manifest, environment) -> None:
    """§6.2.2 (0.5.4): a client reading `restore point: passed` must not conclude
    a restore was tested."""
    rendered = render_report(
        run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)
    )

    for line in rendered.splitlines():
        if "capacity.restore_point_declared" in line or "dpa_reference_recorded" in line:
            assert "declared, not verified" in line


def test_rendering_is_deterministic(manifest, environment) -> None:
    """P2 applies to the report as much as to the pipeline: two runs over one
    unchanged source must produce the same document, or a diff means nothing."""
    first = render_report(
        run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)
    )
    second = render_report(
        run_preflight(manifest, kernel_version=KERNEL_VERSION, environment=environment)
    )

    assert first == second
