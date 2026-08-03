# STATUS — 3 August 2026

**Reflects:** `CLAUDE.md` v0.4.1 · repo `MaxengUK/data-onboarding-harness` @ `48f09f1`
**Session:** first build session. BUILD-PLAN items 1 and 2 closed, item 3 partially.
**Suggested home in repo:** `docs/STATUS.md`

---

## 1. Position against BUILD-PLAN

| # | Item | Est. days | Status |
|---|---|---|---|
| 1 | Repo skeleton, Pydantic schemas, JSON Schema, CI guard | 1.5 | ✅ Closed |
| 2 | Evidence emitter, egress allowlist, Leg 1 | 1.0 | ✅ Closed (Leg 1 at unit level; end-to-end deferred to Gate 0 close) |
| 3 | Predicate registry + semantic type registry | 1.0 | ◐ Semantic type registry seeded in `kernel/registries.py`; **predicate registry not started** |
| 4 | Bronze store | 1.5 | ⬜ Next. Two decisions pending — see §4 |
| 5–16 | Preflight, arming, walking skeleton, tr-core, discovery, Gate 0/1 | 26 | ⬜ Not started |

Two unplanned pieces were added and both closed real defects: guard hardening and the schema sync test. Neither was in BUILD-PLAN; both belong in the record as scope that earned its place.

---

## 2. Spec defects found while implementing

The session's highest-value output. Each was invisible until code forced the question.

| # | Defect | Resolution |
|---|---|---|
| B5 | **Evidence / audit naming collision.** §8 (aggregate artifact crossing the boundary) and §12 (per-record pre-image hashes staying inside) shared one word, putting the two sections in direct contradiction. | Split into `schemas/evidence.py` and `schemas/audit.py`; `AuditRecord` structurally barred from egress via a `ClassVar`. CLAUDE.md → 0.4.1 |
| — | **`invalid_value` in the committed evidence schema.** A source cell value, straight P5 violation, shipped in item 1 because the emitter did not exist yet to reject it. | Removed, along with `message` (free text) and `row_index` (row locator, a composition-attack key) |
| — | **Exporter wrote CRLF on Windows, LF on Linux.** Same models, different bytes by machine — a silent P2 violation that `.gitattributes` masked from `git diff` entirely. | `newline="\n"` plus explicit trailing newline. Would never have been found by inspection |
| — | **Cardinality threshold measured the wrong quantity.** Field-value hashes were gated on dataset cardinality, but reversibility depends on the size of the *value space*. An MSISDN column clears any plausible threshold while remaining trivially sweepable (~10⁹). | Field-value hashes denied outright. Only artifact-level content hashes survive. §8 wording corrected |
| — | **The pre-commit hook was never installed.** `pre-commit run --all-files` had been reporting Passed the whole time — it runs the hook manually, not through git's commit path. | `pre-commit install`, then verified by observing an actual commit get **blocked** |

**The pattern, now stable across five findings:** every serious spec-level error was a *missing concept*, not a wording error — and each was found by trying to write the code, not by re-reading the document. B1 (Bronze) and B5 (audit record) are the same shape.

**The corollary, learned three times today:** a control that passes proves nothing. The guard, the schema sync test, and the pre-commit hook each only earned trust when observed to *fail* where failure was correct.

---

## 3. Verification debt — clear at the start of next session

1. **GitHub Actions for `48f09f1` was never checked.** The largest commit of the session (13 files, ~1,650 lines, two new modules). Confirm green and confirm the guard step ran.
2. **`docs/ROADMAP.md` and `docs/BUILD-PLAN.md` presence in the repo has never been verified.** They may exist only outside it.
3. **No LICENSE file.**

---

## 4. Decisions pending before Bronze (item 4)

**Storage substrate.** Parquet files plus DuckDB, or Postgres tables? Both work at dealership volume, but partition semantics and replay differ. Bronze content hashes go into the run manifest (§12), so the choice determines what "partition" means for the replay assertion.

**How immutability is enforced.** P10 says Bronze is immutable. Convention writes no code and is not testable. Options range from application-level append-only discipline to filesystem permissions or a WORM-style arrangement. Whatever is chosen must be expressible as a test that fails when a partition is modified — otherwise P10 has the same status the pre-commit hook had this morning.

Bronze also now hosts `AuditRecord`, which raises its weight above preflight in the build order.

---

## 5. Small items flagged but not actioned

- `PreflightConfig.row_count_bounds` is `dict[str, int]`; a typed `RowCountBounds` model would stop `{"foo": 5}` and `{}` from validating. A preflight blocker will depend on this.
- `TargetConfig.retention_days` has no lower bound while `BronzeConfig.retention_days` has `gt=0`. Quarantine holds raw violating records; the same constraint applies.
- `tenant` and `engagement` were removed from the evidence artifact (fail-closed, correct for now). The Readiness Report (item 13) must bind itself to an engagement somehow — decide the source then.
- VKN label matching remains a fixed spelling list. The real answer is semantic-type binding via the manifest's `column_map` (§7.5), which lands with item 3. Do not keep widening the regex.
- `;` delimiter detection in the guard is tr-TR-specific knowledge sitting in the wrong layer. It belongs in `packs/core/tr-core` once that exists.

---

## 6. Deferred by decision

- **Uğur's local setup** (`pre-commit install`, dev environment): deliberately deferred to a single onboarding pass once the tool is further along.
- **Leg 1 end-to-end**: currently unit-level only. Upgrades at Gate 0 close, when a pipeline exists to run it through. Recorded in the test file itself.
- **Leg 2 re-identification test**: not started; Gate 0 scope.

---

## 7. Environment notes

- Disk went 1.3 GB → 3.52 GB free. Adequate for now; Bronze writes real files, so watch it.
- Always confirm `(.venv)` in the prompt before running anything. A run outside the venv produced a false green earlier in the session — the exporter crashed on import, wrote nothing, and `git diff --exit-code` therefore returned 0.
- The agent can commit but cannot push: the SSH key is passphrase-protected and not loaded into ssh-agent, so a non-interactive subprocess cannot use it. This accident produced a useful control and is being kept deliberately — push stays a human step.
