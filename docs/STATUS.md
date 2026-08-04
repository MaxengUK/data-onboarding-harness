# STATUS — 4 August 2026

**Reflects:** `CLAUDE.md` v0.5.0 · repo `MaxengUK/data-onboarding-harness` @ `7178011`
**Sessions:** first build session (3 Aug) closed BUILD-PLAN items 1 and 2, item 3 partially. Second session (4 Aug) is spec and governance only — no kernel code changed: the Bronze substrate decisions in §4 were taken and written into `CLAUDE.md` 0.5.0, and the repo was licensed.
**This is a living document.** Sections are updated in place as items close, not appended to. Where a section records a decision rather than a state, it says so.

---

## 1. Position against BUILD-PLAN

| # | Item | Est. days | Status |
|---|---|---|---|
| 1 | Repo skeleton, Pydantic schemas, JSON Schema, CI guard | 1.5 | ✅ Closed |
| 2 | Evidence emitter, egress allowlist, Leg 1 | 1.0 | ✅ Closed (Leg 1 at unit level; end-to-end deferred to Gate 0 close) |
| 3 | Predicate registry + semantic type registry | 1.0 | ◐ Semantic type registry seeded in `kernel/registries.py`; **predicate registry not started** |
| 4 | Bronze store **+ audit store** | 1.5 → 2.0 | ⬜ Next. Both blocking decisions taken — see §4. Estimate raised: it is two stores, not one |
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
3. ~~**No LICENSE file.**~~ Closed — proprietary `LICENSE` added at the repo root. MIT and Apache were both rejected: the repo carries `tr-core`, which is the reusable rule asset the whole economic argument in §1 rests on, and a permissive licence would place it in the public domain of every engagement it touches. See §8 for the obligation this leaves open.

---

## 4. Decisions taken before Bronze (item 4) — ✅ closed

Both blocking questions are decided and written into `CLAUDE.md` §4.2.1–4.2.6 (v0.5.0). Recorded here as decisions, with what they cost, so item 4 starts from a settled position.

**Storage substrate — Parquet files, not database tables.** Decided on three grounds (§4.2.1). The one that settled it was the §12 content hash: a file's hash is its bytes, whereas a table has to be scanned and canonicalised first — row order, type rendering, NULL representation — so making a table hashable means solving a *new* determinism problem in order to deliver the determinism guarantee. Portability and schemalessness both point the same way. Addressed through a **path abstraction** (§4.2.2): local FS, S3, Azure Blob equally valid, no local-disk assumption.

**How immutability is enforced — tamper-evidence, not tamper-prevention (§4.2.5).** The honest framing, because Bronze is client-owned: the Harness cannot prevent modification of a store it does not control, and designing as if it could would assume away the ownership model. Three layers — single-writer API with no `overwrite` parameter, read-only filesystem bits as an explicit *speed bump nothing may depend on*, and the content hash verified on every read as the actual control, failing the run with `BronzeIntegrityError`. This is exactly the testable form the previous session asked for, and it is now a Gate 0 criterion (§15): modify a partition's bytes on disk, the read fails; write the same partition id twice, it is refused.

**`AuditRecord` does *not* live in Bronze.** The previous session's note that "Bronze also now hosts `AuditRecord`" was wrong, and finding out why produced the sharpest correction of this pass: audit records are produced by `normalize`, i.e. *after* `ingest`, so writing them into Bronze is a post-ingest write to Bronze and a direct P10 violation. It also breaks the content hash — a partition that grows as later stages run has no stable hash, so §4.2.5's third layer collapses. The audit store is a **separate, parallel, append-only store** under the same three-layer discipline (§4.2.6), with `audit.retention_days` ≥ `bronze.retention_days` enforced as a preflight blocker.

**Build-order consequence.** Item 4 is now two stores, not one, and it stays ahead of preflight — preflight's new governance blocker is a check on the audit store's retention, so the manifest models have to exist first.

### 4.1 Known spec/code divergence — deliberate, closes with item 4

`CLAUDE.md` 0.5.0 describes manifest fields that `schemas/manifest.py` does not yet have. This is a **deliberate temporary divergence**, recorded so that the next session recognises it as a known gap rather than a defect, and so that it cannot quietly become permanent:

| Spec (§7.1, v0.5.0) | Code (`schemas/manifest.py`) | Closes |
|---|---|---|
| `bronze.format`, typed `Literal["parquet"]` — pinned, not a toggle (§4.2.1) | `BronzeConfig` has no `format` field | Item 4 |
| `audit:` block — `location`, `retention_days` | No `AuditConfig` model exists | Item 4 |
| `audit.retention_days` ≥ `bronze.retention_days`, governance blocker (§6.2.2) | No cross-field validator | Item 4, with the model |

**Why it was left open rather than closed immediately.** Adding the two models is a few lines, but they are the first lines of item 4, not a spec edit — `AuditConfig` without an audit store is a model with no writer, and the cross-field validator is only meaningful once preflight has a check to run it from. Writing them now would put half of item 4 in a commit labelled as a documentation change.

**Why it is safe today.** Nothing is out of sync in the enforceable sense: the JSON Schema sync test pins `schemas/json/*.json` to the Pydantic models, not the spec to the models, so it stays green. The divergence is a spec commitment that has not been implemented yet, in a direction where the code is silently permissive — a manifest carrying `format:` or `audit:` today would be accepted and ignored, not rejected. That is the failure mode to close first when item 4 starts.

**Note the shape of the `Literal["parquet"]` decision.** The alternative was to drop the field. It was kept because a configurable `format` field advertises that other formats work, while `Literal["parquet"]` keeps the schema shape available for a future second substrate and admits exactly one value today — the same pattern already used for `egress.evidence_only`, which is refused by a validator rather than typed away for the same reason.

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

---

## 8. Open — `NOTICE` file required before the first distributed build

**Status: open. Owner: unassigned. Due: Phase 1, at the point the SBOM lands.**

The `LICENSE` added at the repo root is proprietary and closes §3.3. It does not close the third-party side, and clause 4 of that file states the obligation rather than discharging it.

**The obligation.** Several dependencies are Apache License 2.0, and §4(d) of that licence requires that redistribution preserve attribution: the NOTICE text of the upstream project must travel with any distribution of a work containing it. This is not a courtesy — it is a condition of the grant, and failing it means the Apache grant does not cover the distribution at all.

**Why it becomes live in Phase 1 and not now.** The obligation attaches on *redistribution*, and today nothing is redistributed — the repo is private and the harness has never been built into an image. §14 ships the harness as **an OCI image plus a mounted client pack directory**, and that image is a redistribution containing every dependency in it. The first build for a client is therefore the first moment the requirement bites, and it bites at exactly the moment there is a deadline attached.

**Why it pairs with the SBOM.** A `NOTICE` file is only correct if the dependency inventory behind it is correct, and a hand-maintained list of transitive dependencies is wrong within weeks. Generate both from the same inventory in the same step: the SBOM is the machine-readable form, `NOTICE` is the human-readable attribution extracted from it. Doing the SBOM first and `NOTICE` later means doing the inventory twice.

**Scope note — wrapped libraries widen this.** §14 wraps Great Expectations, Soda Core, Splink, Presidio, and Deequ-style constraint suggestion. These are not yet in `pyproject.toml`; they arrive with the discovery and validation items. Whoever builds the inventory should expect the licence surface to be materially larger than today's five runtime dependencies suggest, and should check for copyleft among the transitive set at the same time — an LGPL or AGPL component inside a distributed image raises a different question than an attribution one, and it is cheaper to find it before it is load-bearing.

**Closed, same area, smaller:** `pyproject.toml` now declares `license = { file = "LICENSE" }` and carries the `Private :: Do Not Upload` classifier. The classifier is deliberately not a real one — PyPI rejects unknown classifiers, so an accidental `twine upload` fails rather than publishing a proprietary repo that carries `tr-core`. A future contributor "fixing" it to a valid classifier would remove the control, so the reason is in a comment beside it.
