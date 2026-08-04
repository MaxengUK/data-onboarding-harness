# STATUS — 4 August 2026

**Reflects:** `CLAUDE.md` v0.5.1 · repo `MaxengUK/data-onboarding-harness` @ `35787a2`
**Sessions:** first build session (3 Aug) closed BUILD-PLAN items 1 and 2, item 3 partially. Second session (4 Aug): the Bronze substrate decisions in §4 were taken and written into `CLAUDE.md` 0.5.0, the repo was licensed, and the first half of item 4 was built — the storage path abstraction and the Bronze store, with `ingest`, `profile`, the audit store and CLI wiring all deliberately out of scope.
**This is a living document.** Sections are updated in place as items close, not appended to. Where a section records a decision rather than a state, it says so.

---

## 1. Position against BUILD-PLAN

| # | Item | Est. days | Status |
|---|---|---|---|
| 1 | Repo skeleton, Pydantic schemas, JSON Schema, CI guard | 1.5 | ✅ Closed |
| 2 | Evidence emitter, egress allowlist, Leg 1 | 1.0 | ✅ Closed (Leg 1 at unit level; end-to-end deferred to Gate 0 close) |
| 3 | Predicate registry + semantic type registry | 1.0 | ◐ Semantic type registry seeded in `kernel/registries.py`; **predicate registry not started** |
| 4a | Path abstraction (`kernel/storage`) + Bronze store (`kernel/bronze`) | 1.0 | ✅ Closed. 30 tests; each control verified by breaking it |
| 4b | Audit store — second consumer of `kernel/storage` (§4.2.6) | 1.0 | ⬜ Next |
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
2. ~~**`docs/ROADMAP.md` and `docs/BUILD-PLAN.md` presence has never been verified.**~~ Closed — both are present in `docs/`.
3. ~~**No LICENSE file.**~~ Closed — proprietary `LICENSE` added at the repo root. MIT and Apache were both rejected: the repo carries `tr-core`, which is the reusable rule asset the whole economic argument in §1 rests on, and a permissive licence would place it in the public domain of every engagement it touches. See §8 for the obligation this leaves open.
4. **CI has never been checked against a `pytest` run that includes `duckdb`.** `tests/test_bronze.py` imports it to read Parquet row group metadata. It is a declared runtime dependency, so this should be fine, but "should be fine" is what item 1 above is about.

---

## 4. Decisions taken before Bronze (item 4) — ✅ closed

Both blocking questions are decided and written into `CLAUDE.md` §4.2.1–4.2.6 (v0.5.0). Recorded here as decisions, with what they cost, so item 4 starts from a settled position.

**Storage substrate — Parquet files, not database tables.** Decided on three grounds (§4.2.1). The one that settled it was the §12 content hash: a file's hash is its bytes, whereas a table has to be scanned and canonicalised first — row order, type rendering, NULL representation — so making a table hashable means solving a *new* determinism problem in order to deliver the determinism guarantee. Portability and schemalessness both point the same way. Addressed through a **path abstraction** (§4.2.2): local FS, S3, Azure Blob equally valid, no local-disk assumption.

**How immutability is enforced — tamper-evidence, not tamper-prevention (§4.2.5).** The honest framing, because Bronze is client-owned: the Harness cannot prevent modification of a store it does not control, and designing as if it could would assume away the ownership model. Three layers — single-writer API with no `overwrite` parameter, read-only filesystem bits as an explicit *speed bump nothing may depend on*, and the content hash verified on every read as the actual control, failing the run with `BronzeIntegrityError`. This is exactly the testable form the previous session asked for, and it is now a Gate 0 criterion (§15): modify a partition's bytes on disk, the read fails; write the same partition id twice, it is refused.

**`AuditRecord` does *not* live in Bronze.** The previous session's note that "Bronze also now hosts `AuditRecord`" was wrong, and finding out why produced the sharpest correction of this pass: audit records are produced by `normalize`, i.e. *after* `ingest`, so writing them into Bronze is a post-ingest write to Bronze and a direct P10 violation. It also breaks the content hash — a partition that grows as later stages run has no stable hash, so §4.2.5's third layer collapses. The audit store is a **separate, parallel, append-only store** under the same three-layer discipline (§4.2.6), with `audit.retention_days` ≥ `bronze.retention_days` enforced as a preflight blocker.

**Build-order consequence.** Item 4 is two stores, not one, split into 4a (built this session, §4a) and 4b. It stays ahead of preflight — preflight's new governance blocker is a check on the audit store's retention, so the manifest models have to exist first.

**A third defect surfaced while building 4a**, and it is the same shape as B1 and B5: §4.2 and the §6 stage table both promised `ingest` lands raw input *byte-for-byte*. Writing the store made it obvious that the promise cannot hold — non-UTF-8 bytes do not enter a text column, and a `binding.kind: database` source has no byte stream in existence to preserve. Replaced in `CLAUDE.md` 0.5.1 with the property that does hold and that the pre-image guarantee actually needs: Bronze loads input **unmodified and uncoerced**, and the content hash covers what Bronze actually stores. The residual question belongs to `ingest` and is recorded in §4a.2. **The pattern holds at six findings: every spec-level error was found by trying to write the code, never by re-reading the document.**

### 4.1 Known spec/code divergence — half closed, half deliberate

| Spec (§7.1) | Code (`schemas/manifest.py`) | Status |
|---|---|---|
| `bronze.format`, typed `Literal["parquet"]` (§4.2.1) | `BronzeConfig.format` | ✅ Closed in 4a |
| `audit:` block — `location`, `retention_days` | No `AuditConfig` model | ⬜ Item 4b |
| `audit.retention_days` ≥ `bronze.retention_days`, governance blocker (§6.2.2) | No cross-field validator | ⬜ Item 4b |

**Why the audit half stays open.** `AuditConfig` without an audit store is a model with no writer, and the cross-field validator is only meaningful once preflight has a check to run it from. Both land with 4b.

**The failure mode while it is open** is unchanged and worth restating, because it is the one that could persist quietly: the divergence runs in the direction where the code is *silently permissive*. A manifest carrying an `audit:` block today is accepted and ignored, not rejected. Close that first in 4b.

**On the `Literal["parquet"]` shape.** Kept rather than dropped because a configurable `format` field advertises that other formats work. Note this differs from `egress.evidence_only`, which stays a `bool` refused by a validator: a second egress mode would need its own gate, so that field stays open and the refusal is behavioural, whereas a second Bronze format is a new substrate implementation and until one exists there is nothing for the type to admit.

---

## 4a. Built this session — path abstraction and Bronze store

`kernel/storage/` (§4.2.2) and `kernel/bronze/` (§4.2). 30 tests. Not built, by decision: `ingest`, `profile`, CLI wiring, the audit store, S3/Azure backends, partition listing, retention and GC.

**Writer determinism was the real work.** Measured before pinning, on polars 1.43.2: repeated writes of one frame are byte-stable, thread count does not affect output, and the Parquet footer carries no timestamp — `created_by` is just `"Polars"`. So there is no run-to-run nondeterminism to find today. But `row_group_size` defaults to a value *derived from the data*, and at 400k rows the default and an explicit `100_000` produce different bytes. The risk was never that one call returns two answers; it is a derived default drifting with input shape or a library release, which is the same failure class as the exporter writing CRLF on one host and LF on another.

`PARQUET_WRITER_OPTIONS` pins compression, level, statistics, row group size and page size, and `_serialise` is the kernel's only `write_parquet` call site.

**What pinning does not buy, stated so nobody over-reads it later.** Bronze verification does *not* depend on write reproducibility: `verify_partition` re-hashes stored bytes and never re-serialises, so existing partitions survive a polars upgrade untouched. What pinning buys is that a partition's bytes are a function of its data alone — making two ingests of one extract comparable by hash — and that future Parquet *output*, where P2 applies directly, is deterministic by construction. It does not survive a version bump, so `PartitionRef.writer` records the library version and a cross-version byte difference stays explicable.

**Every control was verified by breaking it**, per the lesson from the first session:

| Break | Result |
|---|---|
| `_serialise` ignores the pinned options | Row group test failed — 2 observed, 3 expected |
| `read_partition` skips `verify_partition` | Both tamper tests failed |
| `delete_partition(force=…)` added to the module | Both introspection tests failed |

The second one is worth keeping in mind: without verification, a truncated partition surfaced as a polars `ComputeError`. Verification does not only catch tampering, it converts an incomprehensible parser crash into a named diagnosis.

**Two design notes that will matter later.** The expected hash is never written next to the data — its authority is the run manifest (§12), outside the partition, because co-locating it would make the check circular. And `write_bytes` uses `O_CREAT|O_EXCL` rather than write-temp-then-rename, so a partition id is claimed atomically; the cost is a possible partial object after a crash, which is harmless because the `PartitionRef` is returned only after the write completes and an unnamed partition is unreachable.

### 4a.1 Memory — not a Bronze problem, a single-node ceiling showing up in Bronze

A partition is serialised whole in memory and read back whole. This should not be logged as a Bronze defect to be fixed with a streaming writer, because it is not where the limit lives: §14 puts the harness on Polars + DuckDB, single-node, with a Spark backend held in reserve for volumes that force it. **A dataset that does not fit in memory does not fit this build anywhere** — `profile`, `validate` and `resolve` would each hit the same wall a step later. Bronze is simply the first place it becomes visible, because it is the first component that touches the whole extract.

The consequence for design is that a streaming Bronze writer bolted under a single-node kernel would buy nothing: the partition would land and the next stage would fall over. When the ceiling is actually reached, the answer is §14's Spark backend, and what Bronze owes that day is a storage interface that can express chunked writes. The current interface cannot, deliberately — see `kernel/storage`'s note on why the second backend is expected to change it.

Worth benchmarking at Gate 1 alongside open question 3 (approximate FD cost on a real dealership extract), since both are answered by the same measurement: how large the largest realistic extract actually is.

### 4a.2 Open for `ingest` — are source bytes preserved at all?

§4.2 v0.5.1 withdrew the *byte-for-byte* claim and left this open deliberately. The question `ingest` has to answer: **beyond loading values unmodified, does Bronze also retain the original source bytes?**

- **File sources — possible.** A `Binary` column alongside the parsed values, or the raw file landed beside the Parquet object in the same partition. Either gives a true byte-level pre-image, including bytes that are not valid UTF-8 and therefore cannot enter a text column at all. Both cost storage, roughly doubling the partition for the raw-file option.
- **Database sources — not possible, at any price.** There are no source bytes to keep. The driver materialises values before the Harness is reached; what arrives is already a decoded Python or Arrow value, and "the bytes" only ever existed on the wire. No design choice recovers them.

So the honest outcome is likely **asymmetric**: file sources may offer a stronger guarantee than database sources can. That asymmetry has to be decided deliberately and stated in the manifest or the Readiness Report rather than discovered by a client. The alternative — levelling down to the weaker guarantee everywhere for symmetry's sake — throws away a real capability on file sources, which are the common case in a first engagement.

Decide before `ingest` is written, not during.

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
