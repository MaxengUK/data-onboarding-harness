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

## VKN needs a label to be checked at all

A bare 10-digit number is matched by almost anything, so the guard evaluates the
VKN checksum only where a `vkn`, `vergi`, or `tax_id` label identifies the value.
How that label is found depends on the file type:

| File type | How the label is found |
|---|---|
| `.csv`, `.tsv` | The **header row** is parsed and any column whose name matches is checksummed in full, however many rows down the values sit. Delimiter is `\t` for `.tsv`; for `.csv` it is `,` or `;`, whichever the header uses more (tr-TR exports often use `;` because `,` is the decimal separator). |
| everything else | The label must appear within ~40 characters of the value — which is how it naturally reads in JSON and YAML (`"vkn": "…"`). |

**Convention:** in a CSV/TSV fixture, name the column `vkn` / `vergi_no` /
`tax_id`. That is what makes detection work at all; a VKN column called something
else is invisible to the guard.

### Known limits

- **An unlabelled column is still missed.** A checksum-valid VKN under a header
  like `musteri_no` or `vno` passes. Checksumming every bare 10-digit number
  would fire on roughly one in nine of them, so this is the deliberate side of
  that trade rather than an oversight.
- **The first line is assumed to be a header.** A headerless CSV has its first
  data row consumed as one, so a VKN on that row is only caught by the ±40 rule.

If a new fixture ever trips the guard, the fixture is wrong, not the guard —
regenerate the value using this table rather than loosening a detection pattern.
