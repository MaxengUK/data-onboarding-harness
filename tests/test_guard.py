"""Tests for kernel.gates.guard (CLAUDE.md §0, §5, §8.2)."""

from pathlib import Path

import pytest

from kernel.gates.guard import (
    collect_violations,
    is_authentic_msisdn,
    is_authentic_tckn,
    is_authentic_vkn,
    main,
    normalize_msisdn,
    scan_file_for_leaks,
)
from tests.synthetic import (
    authentic_plate,
    find_valid_tckn,
    find_valid_vkn,
    iso_timestamp,
)

# --- checksum-valid generators ------------------------------------------------
#
# Shared with the other test modules; see tests/synthetic.py for why these are
# built at runtime rather than written as literals (§0).

_find_valid_tckn = find_valid_tckn
_find_valid_vkn = find_valid_vkn


# --- TCKN ----------------------------------------------------------------------

def test_is_authentic_tckn_true_for_valid_checksum():
    valid = _find_valid_tckn("100000001")
    assert is_authentic_tckn(valid) is True


def test_is_authentic_tckn_false_for_invalid_checksum():
    valid = _find_valid_tckn("100000001")
    mutated = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert is_authentic_tckn(mutated) is False


# --- VKN -----------------------------------------------------------------------

def test_is_authentic_vkn_true_for_valid_checksum():
    valid = _find_valid_vkn("123456789")
    assert is_authentic_vkn(valid) is True


def test_is_authentic_vkn_false_for_invalid_checksum():
    valid = _find_valid_vkn("123456789")
    mutated = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert is_authentic_vkn(mutated) is False


def test_vkn_scan_ignores_checksum_valid_number_without_context(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "no_context.csv"
    f.write_text(f"order_id,amount\n{valid},199.90\n", encoding="utf-8")
    assert scan_file_for_leaks(f) == []


def test_vkn_scan_flags_checksum_valid_number_with_context(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "with_context.csv"
    f.write_text(f"vkn,amount\n{valid},199.90\n", encoding="utf-8")
    leaks = scan_file_for_leaks(f)
    assert any("VKN" in leak for leak in leaks)


# --- VKN in delimited files ------------------------------------------------------
#
# A CSV header sits hundreds of lines above its values, so the ±40 character
# proximity rule can never reach them — and CSV is the primary shape a DMS
# export arrives in. Columns whose header names a VKN are therefore checked
# regardless of distance.

def _delimited_content(delimiter, headers, value, value_index, filler_rows=50):
    """Header row, then enough filler to put the value far out of proximity range."""
    lines = [delimiter.join(headers)]
    lines.extend([delimiter.join("x" for _ in headers)] * filler_rows)
    row = ["x"] * len(headers)
    row[value_index] = value
    lines.append(delimiter.join(row))
    return "\n".join(lines) + "\n"


def test_vkn_flagged_in_csv_column_far_below_the_header(tmp_path):
    valid = _find_valid_vkn("123456789")
    content = _delimited_content(",", ["musteri_adi", "vkn", "tutar"], valid, 1)

    leaky = tmp_path / "dms_export.csv"
    leaky.write_text(content, encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(leaky))

    # Identical bytes as .txt get only the proximity pass, which cannot reach
    # this far — proving the column-aware path is what catches the CSV case.
    as_text = tmp_path / "dms_export.txt"
    as_text.write_text(content, encoding="utf-8")
    assert not any("VKN" in leak for leak in scan_file_for_leaks(as_text))


def test_vkn_flagged_in_tsv_column(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "export.tsv"
    f.write_text(_delimited_content("\t", ["ad", "vkn"], valid, 1), encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(f))


def test_vkn_flagged_in_semicolon_delimited_csv(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "export.csv"
    f.write_text(_delimited_content(";", ["ad", "vkn", "tutar"], valid, 1), encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(f))


@pytest.mark.parametrize("header", [
    "vergi_no",
    "vergi kimlik no",
    "VKN",
    "vd_no",
    "tax_id",
    "tax_no",
    "tax no",
    "taxno",
    "TAX_ID",
])
def test_vkn_column_header_variants_are_recognised(tmp_path, header):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "export.csv"
    f.write_text(_delimited_content(",", ["ad", header], valid, 1), encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(f))


@pytest.mark.parametrize("label", ["vd_no", "tax_no", "taxno"])
def test_widened_labels_also_apply_to_the_proximity_path(tmp_path, label):
    """The label set is shared, so widening it reaches JSON/YAML as well as CSV."""
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "customer.json"
    f.write_text(f'{{"{label}": "{valid}"}}\n', encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(f))


def test_vkn_not_flagged_in_an_unlabelled_column(tmp_path):
    """Documents the residual limit: an unlabelled column is still missed.

    Checksumming every bare 10-digit number would fire on roughly one in nine
    of them, so this gap is the deliberate side of that trade.
    """
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "export.csv"
    f.write_text(_delimited_content(",", ["ad", "musteri_no"], valid, 1), encoding="utf-8")
    assert not any("VKN" in leak for leak in scan_file_for_leaks(f))


def test_vkn_next_to_its_header_is_reported_only_once(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "short.csv"
    f.write_text(f"vkn,tutar\n{valid},199.90\n", encoding="utf-8")
    assert len([leak for leak in scan_file_for_leaks(f) if "VKN" in leak]) == 1


def test_delimited_scan_survives_ragged_rows(tmp_path):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "ragged.csv"
    f.write_text(f"ad,vkn,tutar\nsadece_bir_kolon\nx,{valid}\n", encoding="utf-8")
    assert any("VKN" in leak for leak in scan_file_for_leaks(f))


# --- MSISDN --------------------------------------------------------------------
#
# The guard now scans *.py too, itself included, so a real-shaped (non-555)
# number written as one literal here would trip it. _synthetic_local_number
# assembles one from two short fragments joined at runtime instead.

def _synthetic_local_number() -> str:
    return "532" + "1234567"


@pytest.mark.parametrize("prefix", ["", "0", "90", "+90", "0090"])
def test_is_authentic_msisdn_true_for_real_shaped_number_any_prefix(prefix):
    raw = prefix + _synthetic_local_number()
    assert normalize_msisdn(raw) == _synthetic_local_number()
    assert is_authentic_msisdn(raw) is True


def test_is_authentic_msisdn_true_for_prefixed_number_with_separators():
    local = _synthetic_local_number()
    raw = "+90 " + local[:3] + " " + local[3:6] + " " + local[6:8] + " " + local[8:]
    assert is_authentic_msisdn(raw) is True


@pytest.mark.parametrize("raw", [
    "5551234567",
    "05551234567",
    "+905551234567",
])
def test_is_authentic_msisdn_false_for_reserved_555_block(raw):
    assert is_authentic_msisdn(raw) is False


def test_msisdn_scan_catches_prefixed_forms_in_text(tmp_path):
    local = _synthetic_local_number()
    raw = "+90 " + local[:3] + " " + local[3:6] + " " + local[6:8] + " " + local[8:]
    f = tmp_path / "customers.txt"
    f.write_text(f"customer_msisdn: {raw}\n", encoding="utf-8")
    leaks = scan_file_for_leaks(f)
    assert any("MSISDN" in leak for leak in leaks)


# --- Plate -----------------------------------------------------------------------
#
# Same reason as the MSISDN section: 34 is a valid province code, so writing
# a province-plus-plate literal contiguously here would trip the guard when
# it scans this file.

def _synthetic_plate() -> str:
    return "34" + " ABC 123"


def test_plate_regex_does_not_match_across_line_break(tmp_path):
    f = tmp_path / "plate_split.txt"
    f.write_text("34\nABC 123\n", encoding="utf-8")
    leaks = scan_file_for_leaks(f)
    assert not any("Plate" in leak for leak in leaks)


def test_plate_regex_matches_within_a_single_line(tmp_path):
    f = tmp_path / "plate_same_line.txt"
    f.write_text(_synthetic_plate() + "\n", encoding="utf-8")
    leaks = scan_file_for_leaks(f)
    assert any("Plate" in leak for leak in leaks)


# --- Encoding resilience -----------------------------------------------------------

def test_scan_survives_invalid_encoding_and_still_finds_the_leak(tmp_path):
    valid = _find_valid_tckn("100000001")
    f = tmp_path / "bad_encoding.txt"
    f.write_bytes(b"\xff\xfe tckn: " + valid.encode("ascii") + b" some more text")
    leaks = scan_file_for_leaks(f)
    assert any("TCKN" in leak for leak in leaks)


def test_scan_skips_binary_content(tmp_path):
    f = tmp_path / "weird.csv"
    f.write_bytes(b"col1,col2\x00\x01\x02binarydata")
    assert scan_file_for_leaks(f) == []


# --- Tree-wide scan -----------------------------------------------------------------

def test_collect_violations_scans_whole_tree_and_skips_excluded_dirs(tmp_path):
    valid = _find_valid_tckn("100000001")

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text(f"tckn: {valid}", encoding="utf-8")

    excluded = tmp_path / ".venv" / "lib"
    excluded.mkdir(parents=True)
    (excluded / "leak.md").write_text(f"tckn: {valid}", encoding="utf-8")

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02")

    violations = collect_violations(tmp_path)

    assert any(p.name == "note.md" for p in violations)
    assert not any(".venv" in p.parts for p in violations)
    assert not any(p.name == "image.png" for p in violations)


# --- Leg 1 fixture ------------------------------------------------------------------

def test_leg1_leak_fixture_passes_guard():
    fixture = Path(__file__).parent / "fixtures" / "leg1_leak_fixture.json"
    assert scan_file_for_leaks(fixture) == []


# --- main() exit-code contract --------------------------------------------------------
#
# The suite above proves the guard passes on clean input. These two prove it
# actually *fails* — an end-to-end check that a leak reaches a non-zero exit
# code, which is the only thing pre-commit and CI act on.

def test_main_returns_1_and_names_the_file_when_a_leak_is_present(tmp_path, capsys):
    valid = _find_valid_tckn("100000001")
    (tmp_path / "data").mkdir()
    leaky = tmp_path / "data" / "customers.csv"
    leaky.write_text(f"tckn,name\n{valid},Test Kullanici\n", encoding="utf-8")

    exit_code = main(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "customers.csv" in captured.out
    assert "TCKN" in captured.out


def test_main_returns_0_on_a_clean_tree(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("no identifiers here\n", encoding="utf-8")

    exit_code = main(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Guard Passed" in captured.out


# --- ISO-8601 timestamps are not plates ---------------------------------------


def test_an_iso_timestamp_is_not_reported_as_a_plate(tmp_path):
    """An ISO timestamp's day-`T`-hour run reads as province + letter + digits,
    which is a well-formed plate by every rule the pattern knows.

    Fixed rather than worked around in the fixtures. ISO timestamps are
    unavoidable in this repo: audit records, run manifests and freshness columns
    all carry them, so leaving the false positive would mean the guard blocking
    legitimate commits routinely. A control that cries wolf gets disabled, and
    this one is the last thing between a real identifier and a public repo.
    """
    readings = tmp_path / "readings.csv"
    readings.write_text(
        f"plant_code;reading_at\nPLANT-01;{iso_timestamp()}\n", encoding="utf-8"
    )

    assert scan_file_for_leaks(readings) == []


def test_blanking_a_timestamp_does_not_blind_the_plate_scan(tmp_path):
    """The reason timestamps are blanked in place rather than skipped by line.

    Dropping the whole line would hide a genuine plate that happened to share it
    with a timestamp — and a row carrying both is the normal shape of a vehicle
    record, not a contrived one.
    """
    plate = authentic_plate()
    records = tmp_path / "deliveries.csv"
    records.write_text(
        f"delivered_at;plate\n{iso_timestamp()};{plate}\n", encoding="utf-8"
    )

    leaks = scan_file_for_leaks(records)

    assert any(plate in leak for leak in leaks)


def test_an_out_of_range_province_stays_clean_beside_a_timestamp(tmp_path):
    """§0's documented escape hatch still works: 99 is not a province code."""
    records = tmp_path / "synthetic.csv"
    records.write_text(
        f"delivered_at;plate\n{iso_timestamp()};99 ABC 123\n", encoding="utf-8"
    )

    assert scan_file_for_leaks(records) == []


def test_blanking_cannot_fabricate_a_plate_across_the_gap(tmp_path):
    """The fill character is not a space, and this is why.

    The plate pattern joins its parts with `[ \t\-]*`, so a space fill welds
    whatever sat either side of a timestamp into one candidate: a province-code
    number, a run of spaces, and a letter-digit group become a plate the line
    never contained. The guard would report a leak that is not there — the same
    "cries wolf" failure the blanking was added to prevent, reintroduced by the
    fix for it.

    Delimited formats hide this, because a comma or semicolon breaks the run.
    It bites in `.log`, `.txt` and `.md`, which the guard also scans.
    """
    log = tmp_path / "run.log"
    log.write_text(f"ilce=34 {iso_timestamp()} ABC 123 adet\n", encoding="utf-8")

    assert scan_file_for_leaks(log) == []
