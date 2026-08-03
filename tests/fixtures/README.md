# Fixture conventions

CLAUDE.md §5 makes this directory — and per §0/§8.2, the whole repository tree —
synthetic-only. The guard at `kernel/gates/guard.py` enforces it: it scans every
text file under the repo root (excluding `.git`, `.venv`, and binary content) and
fails the build on anything that is not just PII-*shaped* but checksum- or
range-*authentic*.

When a fixture needs to look like PII — for example a Leg 1 emitter leak-test seed
per CLAUDE.md §8.2 — use one of these documented invalid ranges, never a real or
checksum-valid value:

| Field | Convention | Why it's safe |
|---|---|---|
| TCKN | Any 11-digit string that fails the mod-10/mod-11 checksum `is_authentic_tckn` implements | Fails the checksum on purpose |
| VKN | Any 10-digit string that fails the GİB checksum `is_authentic_vkn` implements | Fails the checksum on purpose |
| MSISDN | `555` block, e.g. `+905551234567` | Reserved synthetic test range, explicitly excluded by `is_authentic_msisdn` |
| Plate | Province code outside `01`–`81`, e.g. `99 ABC 123` | Outside the valid TR province range the guard's plate pattern matches at all |

**VKN needs a label to be checked at all.** A bare 10-digit number is matched by
almost anything, so the guard only evaluates the checksum when a `vkn`, `vergi`,
or `tax_id` label sits within ~40 characters of the value. A fixture that embeds
a checksum-valid VKN with no such label nearby will not be caught — keep the
label next to the value if the fixture is meant to exercise VKN detection.

If a new fixture ever trips the guard, the fixture is wrong, not the guard —
regenerate the value using this table rather than loosening a detection pattern.
