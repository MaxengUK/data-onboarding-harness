"""Synthetic-fixture guard (CLAUDE.md §0, §5, §8.2).

Scans the tree for values that are not merely PII-*shaped* but checksum- or
range-*authentic* (a real TCKN/VKN checksum, a real MSISDN block, a real
province plate code). Fixtures must use documented invalid ranges instead —
see tests/fixtures/README.md.
"""

import csv
import io
import os
import re
import sys
from pathlib import Path

from kernel.checksums import is_valid_tckn, is_valid_vkn, normalise_msisdn

REPO_ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_DIR_NAMES = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
}
EXCLUDED_DIR_SUFFIXES = (".egg-info",)

TEXT_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".csv", ".tsv", ".txt", ".md",
    ".py", ".toml", ".ini", ".cfg", ".sql", ".xml", ".log",
}

# Optional national prefix (0 / 90 / 0090 / +90), itself optionally followed
# by a separator, ahead of the 5xx mobile core (e.g. "+90 555 123 45 67").
MSISDN_PATTERN = re.compile(
    r'(?<!\d)(?:(?:\+90|0090|90|0)[ \t\-]?)?5\d{2}[ \t\-]?\d{3}[ \t\-]?\d{2}[ \t\-]?\d{2}(?!\d)'
)
TCKN_PATTERN = re.compile(r'\b[1-9]\d{10}\b')
VKN_PATTERN = re.compile(r'\b\d{10}\b')
# A bare 10-digit number is ~1/9 likely to pass the VKN checksum by chance, so
# it is only evaluated where a vkn/vergi/tax_id label identifies it — either
# nearby in the text, or naming its column. One pattern serves both so they
# cannot drift apart.
VKN_CONTEXT_PATTERN = re.compile(r'vkn|vergi|vd_no|tax[_ ]?(?:id|no)', re.IGNORECASE)
VKN_CONTEXT_RADIUS = 40
# In a CSV the label is in the header row and the values are hundreds of lines
# below it, so the proximity rule can never reach them. These get a
# column-aware pass instead — see _scan_delimited_vkn.
DELIMITED_EXTENSIONS = {".csv", ".tsv"}
# [ \t\-] only (no \s) so this can never span a line break.
PLATE_PATTERN = re.compile(
    r'\b(0[1-9]|[1-7][0-9]|8[0-1])[ \t\-]*[A-Z]{1,3}[ \t\-]*\d{2,4}\b'
)

#: ISO-8601 timestamps are blanked before the plate scan, because the plate
#: pattern matches inside one. The day number, the `T` separator and the first
#: two digits of the hour read as province code, plate letter and plate digits —
#: a well-formed plate by every rule the pattern knows.
#:
#: No example is written out here, deliberately: an ISO timestamp in this file
#: would trip the very scanner this comment explains. §0 warns about exactly
#: that ("a literal will block the very test that needs it"), and the warning
#: was demonstrated on this fix — the guard blocked the commit that introduced
#: it. `tests/synthetic.iso_timestamp()` builds one at runtime instead.
#:
#: This is a false positive worth fixing rather than working around. ISO
#: timestamps are unavoidable here — audit records, run manifests, freshness
#: columns and half the fixtures carry them — so leaving it would mean the guard
#: blocking legitimate commits routinely. A control that cries wolf gets
#: disabled, and this one is the last thing standing between a real identifier
#: and a public repository (§0, §5).
#:
#: Blanking rather than skipping the line: a line can hold both a timestamp and
#: a genuine plate, and dropping the whole line would hide the second.
ISO_TIMESTAMP_PATTERN = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?'
)

#: What a blanked timestamp is replaced with, one character per character so
#: offsets are preserved.
#:
#: **Not a space, and the difference is a fabricated violation.** The plate
#: pattern joins its parts with `[ \t\-]*`, so filling with spaces welds
#: whatever sat either side of the timestamp into one candidate:
#: `ilce=34 <timestamp> ABC 123` becomes a province code, a run of spaces and a
#: letter-digit group — a plate the original line does not contain. The guard
#: would then report a leak that is not there, in a file nobody can fix, which
#: is the same "control that cries wolf" failure the blanking exists to prevent.
#:
#: A delimiter would hide it in CSV and TSV, where a comma or semicolon breaks
#: the run. It bites in `.log`, `.txt` and `.md`, which the guard also scans.
#:
#: `~` cannot appear in `[ \t\-]`, `[A-Z]` or `\d`, so no fill region can be
#: crossed by the pattern and no match can be created through one.
TIMESTAMP_FILL = "~"


# The three below delegate to `kernel.checksums`, which the `has_checksum`
# predicate (§7.5) also uses. The names differ on purpose: the guard asks
# "should I assume this is real and refuse the commit", the predicate asks "is
# this well-formed". Same arithmetic, two questions, and the guard's wording
# should keep saying which one it is asking.
def is_authentic_tckn(tckn: str) -> bool:
    """Whether a TCKN is checksum-valid, i.e. one that could have been issued."""
    return is_valid_tckn(tckn)


def is_authentic_vkn(vkn: str) -> bool:
    """Whether a VKN is checksum-valid under the GİB mod-9 / mod-10 algorithm."""
    return is_valid_vkn(vkn)


def normalize_msisdn(raw: str) -> str:
    """Strip separators and any national prefix, keeping the 10 subscriber digits."""
    return normalise_msisdn(raw)


def is_authentic_msisdn(raw: str) -> bool:
    """Gerçek bir operatör numarası olup olmadığını kontrol eder."""
    core = normalize_msisdn(raw)
    if len(core) != 10 or not core.startswith('5'):
        return False
    # 555 sentetik test bloğudur; diğer 5XX blokları gerçek kabul edilerek bloklanır
    return not core.startswith('555')


def _is_binary(raw: bytes) -> bool:
    return b'\x00' in raw[:8192]


def read_text_safely(path: Path) -> str | None:
    """Best-effort text read: returns None for binary content, never raises on bad encoding."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if _is_binary(raw):
        return None
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='replace')


def is_excluded_dir(name: str) -> bool:
    return name in EXCLUDED_DIR_NAMES or any(name.endswith(suf) for suf in EXCLUDED_DIR_SUFFIXES)


def iter_scannable_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_excluded_dir(d)]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                yield path


def _has_vkn_context(content: str, start: int, end: int) -> bool:
    window = content[max(0, start - VKN_CONTEXT_RADIUS):end + VKN_CONTEXT_RADIUS]
    return VKN_CONTEXT_PATTERN.search(window) is not None


def _detect_delimiter(header_line: str, suffix: str) -> str:
    if suffix == ".tsv":
        return "\t"
    # tr-TR exports frequently use ';' because ',' is the decimal separator.
    return ";" if header_line.count(";") > header_line.count(",") else ","


def _scan_delimited_vkn(content: str, suffix: str) -> dict[str, str]:
    """Checksum-valid VKNs sitting in a column whose *header* names one.

    Returns {value: column_name}. Naming the column is the context here, so no
    proximity requirement applies — that is the whole point, since a header row
    is arbitrarily far from the values beneath it.
    """
    if not content:
        return {}

    delimiter = _detect_delimiter(content.split("\n", 1)[0], suffix)
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)

    found: dict[str, str] = {}
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        return found

    targets = {
        idx: name.strip()
        for idx, name in enumerate(header)
        if VKN_CONTEXT_PATTERN.search(name)
    }
    if not targets:
        return found

    try:
        for row in reader:
            for idx, column_name in targets.items():
                # Ragged rows are normal in a broken export; just skip short ones.
                if idx < len(row) and is_authentic_vkn(row[idx].strip()):
                    found[row[idx].strip()] = column_name
    except csv.Error:
        # A malformed export must not take the whole scan down; keep what we have.
        pass

    return found


def scan_file_for_leaks(file_path: Path) -> list[str]:
    content = read_text_safely(file_path)
    if content is None:
        return []
    violations = []

    for match in TCKN_PATTERN.finditer(content):
        if is_authentic_tckn(match.group()):
            violations.append(f"Authentic TCKN detected: {match.group()}")

    delimited_vkn: dict[str, str] = {}
    if file_path.suffix.lower() in DELIMITED_EXTENSIONS:
        delimited_vkn = _scan_delimited_vkn(content, file_path.suffix.lower())
        for value, column_name in delimited_vkn.items():
            violations.append(f"Authentic VKN detected in column '{column_name}': {value}")

    for match in VKN_PATTERN.finditer(content):
        # Already reported by the column-aware pass above; don't say it twice.
        if match.group() in delimited_vkn:
            continue
        if _has_vkn_context(content, match.start(), match.end()) and is_authentic_vkn(match.group()):
            violations.append(f"Authentic VKN detected: {match.group()}")

    for match in MSISDN_PATTERN.finditer(content):
        if is_authentic_msisdn(match.group()):
            violations.append(f"Authentic MSISDN detected: {match.group()}")

    # Line-by-line so the plate pattern can never match across a line break.
    for line in content.splitlines():
        # Same length, so any offset the pattern reports still points at the
        # right column of the original line.
        without_timestamps = ISO_TIMESTAMP_PATTERN.sub(
            lambda match: TIMESTAMP_FILL * len(match.group()), line
        )
        for match in PLATE_PATTERN.finditer(without_timestamps):
            violations.append(f"Authentic Turkish Plate detected: {match.group()}")

    return violations


def collect_violations(root: Path = REPO_ROOT) -> dict[Path, list[str]]:
    """Pure scan: {file: [violation, ...]} for every leak found under root. No I/O side effects."""
    results = {}
    for path in iter_scannable_files(root):
        leaks = scan_file_for_leaks(path)
        if leaks:
            results[path] = leaks
    return results


def main(root: Path = REPO_ROOT) -> int:
    print("Running Synthetic-Fixture Guard...")
    violations = collect_violations(root)

    if not violations:
        print("Guard Passed: No authentic PII detected in the tree.")
        return 0

    for filepath, leaks in violations.items():
        print(f"\n[CRITICAL] Data leakage detected in: {filepath}")
        for leak in leaks:
            print(f"  - {leak}")

    print("\nGuard Failed: Authentic PII data must not be committed to the repository!")
    print("Use synthetic test data (e.g., invalid TCKN/VKN checksums, 555-prefix MSISDNs, out-of-range plate codes).")
    return 1


if __name__ == "__main__":
    sys.exit(main())