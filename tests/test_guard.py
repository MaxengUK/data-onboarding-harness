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

# --- checksum-valid generators ------------------------------------------------
#
# Both finders below brute-force the missing check digit(s) using this
# module's own is_authentic_* function. That proves the implementation is
# internally self-consistent — it accepts the digit it was used to derive
# and rejects any other — it does NOT independently verify either algorithm
# against the real TCKN/VKN government specification; no external ground
# truth is checked here. (For what it's worth, _find_valid_tckn("100000001")
# happens to reproduce a widely published checksum-valid dummy TCKN used in
# other tooling, which is some corroboration for the TCKN branch — VKN has
# no such cross-check.)
# A literal valid TCKN/VKN is deliberately never written in this file:
# the guard scans the whole tree including its own tests, and a hardcoded
# checksum-valid value here would trip it.

def _find_valid_tckn(prefix9: str) -> str:
    for check10 in range(10):
        for check11 in range(10):
            candidate = f"{prefix9}{check10}{check11}"
            if is_authentic_tckn(candidate):
                return candidate
    raise AssertionError(f"no checksum-valid TCKN found for prefix {prefix9!r}")


def _find_valid_vkn(prefix9: str) -> str:
    for check_digit in range(10):
        candidate = f"{prefix9}{check_digit}"
        if is_authentic_vkn(candidate):
            return candidate
    raise AssertionError(f"no checksum-valid VKN found for prefix {prefix9!r}")


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


@pytest.mark.parametrize("header", ["vergi_no", "tax_id", "VKN", "vergi kimlik no"])
def test_vkn_column_header_variants_are_recognised(tmp_path, header):
    valid = _find_valid_vkn("123456789")
    f = tmp_path / "export.csv"
    f.write_text(_delimited_content(",", ["ad", header], valid, 1), encoding="utf-8")
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
