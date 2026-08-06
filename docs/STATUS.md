# STATUS — 4–6 August 2026

**Reflects:** `CLAUDE.md` v0.6.3 · repo `MaxengUK/data-onboarding-harness` @ `d8daf2f`
**Sessions:** first build session (3 Aug) closed BUILD-PLAN items 1 and 2, item 3 partially. Second session (4 Aug): the Bronze substrate decisions in §4 were taken and written into `CLAUDE.md` 0.5.0, the repo was licensed, and **item 4 closed outright** — 4a's path abstraction and Bronze store, then 4b's audit store, plus a run manifest neither store could do without. Third session (5 Aug): **item 5 framed, items 3a and 3b closed** — the preflight framework, digest and CLI, then the canonical schema artifact preflight had been stopping at. 18 of 30 checks live, the rest registered and blocking. Fourth session (6 Aug): **a review round over 3b's predicate registry**, which found seven defects and produced the registry's first new member — see §5c.3. `ingest`, `profile` and `normalize` remain deliberately out of scope: what exists is the storage floor those stages will stand on, plus the gate that decides whether they may start.
**This is a living document.** Sections are updated in place as items close, not appended to. Where a section records a decision rather than a state, it says so.

---

## 1. Position against BUILD-PLAN

| # | Item | Est. days | Status |
|---|---|---|---|
| 1 | Repo skeleton, Pydantic schemas, JSON Schema, CI guard | 1.5 | ✅ Closed |
| 2 | Evidence emitter, egress allowlist, Leg 1 | 1.0 | ✅ Closed (Leg 1 at unit level; end-to-end deferred to Gate 0 close) |
| 3a | Canonical schema artifact + resolver + semantic type binding chain | 1.5 | ✅ Closed. 36 tests; opened 3 preflight checks and made a 4th genuinely N/A. Entity naming corrected in 0.6.3 — see §5b.4 |
| 3b | Predicate registry + §7.2 rule schema | 0.5 | ✅ Closed. 36 tests after the review round; opened the last two pack checks that do not need a loader. 14 predicates — see §5c.3 |
| 4a | Path abstraction (`kernel/storage`) + Bronze store (`kernel/bronze`) | 1.0 | ✅ Closed. 30 tests; each control verified by breaking it |
| 4b | Audit store (`kernel/audit`) + `AuditConfig` + shared serialiser | 1.0 | ✅ Closed. 35 tests; each control verified by breaking it |
| — | **Run manifest** (`kernel/run_manifest`) — unplanned, see §4b.3 | 0.5 | ✅ Closed. 13 tests |
| 5 | Preflight — framework, digest, CLI, and the checks today allows | 2.0 → 1.0 | ◐ **Framed: 18 of 30 checks implemented.** All 30 registered; the other 12 report `unavailable`. See §5a |
| 6–16 | Arming, walking skeleton, tr-core, discovery, Gate 0/1 | 24 | ⬜ Not started |

324 tests, all green. Three unplanned pieces have been added across the sessions and each closed a real defect: guard hardening, the schema sync test, and the run manifest. None was in BUILD-PLAN; all three belong in the record as scope that earned its place. The run manifest is the largest of them and the most load-bearing — §4.2.5 layer 3 was unimplementable without it, which is why it is a row here rather than a footnote.

**Preflight changed how the plan is shaped, not just what is in it.** `BUILD-PLAN.md` §2.1 now carries a rule: an item that brings a capability also brings the preflight checks depending on it, and the remaining unimplemented checks are distributed across items 7, 9, 17 and 19 rather than collected into a "finish preflight" item. A backlog item would be the easiest thing in the plan to defer, and deferring it would leave runs blocked by checks whose enabling capability already shipped — which is where the pressure to weaken "unavailable blocks" would come from.

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
| — | ~~**`schemas/rule.py` and `schemas/pack.py` do not implement §7.2–§7.4.**~~ Half closed in 3b: `rule.py` is rewritten and its warning removed. `pack.py` still does not implement §7.4 and keeps a client-worded provisional notice — the pack loader is item 9. Original finding:** Both predate the schemas the spec now describes and share almost nothing with them: no `applies_to`, `expression`, `repair` or `provenance`; a `layer: L1_structural…` enum that appears nowhere in CLAUDE.md; no pack `layer`, `overrides` or `corroborated_by`, which are exactly the fields §6.2.2's pack checks would need. | Not patched — closing it is BUILD-PLAN item 3, and a rule schema written before the predicate registry would be a third guess. Docstrings at the head of both files say they are not implementations and that no code may be written against them; preflight reports all four pack checks `unavailable` rather than binding to fields the spec does not recognise |
| — | **§7.1 named a canonical schema that did not exist.** `canonical_schema: automotive/sales_v2` has been in the manifest since 0.1, and §6 has always said `map` resolves the column map onto it, but no section said what one *is*. So `column_map`'s right-hand side named nothing, §7.5's "rules bind to semantic types" had no chain to travel, and §13's `reuse_ratio` had nothing to measure. Three preflight checks stopped at the same link. | §7.6 defines the artifact, its directory and its exact-match resolver; §6.2.2 gains `the declared canonical schema resolves`. CLAUDE.md → 0.6.0 |
| — | **§7.2 contradicted §7.5 in the same document.** The authored-rule example carried `expression: "regex_match(value, '…')"` while §7.5 says rule expressions are not a language and §0 forbids `eval`/`exec` — so the string could never have been evaluated by anything respecting this document. Its `transform: tr_msisdn_canonical` was equally stale; the registry holds `canonicalize_phone`. | §7.2 rewritten to `predicate` + `params`, with the rule that **params carry names, not content**: a pack-authored regex is executable content from outside the release. CLAUDE.md → 0.6.2 |
| — | **§12 named no record for audit segment hashes.** §4.2.6 puts the audit store under §4.2.5's three layers, and layer 3 — the only one that carries weight — needs the expected hash held *outside* the store. §12's run manifest enumerated Bronze partitions and stopped there, so the control was mandated with nothing to enforce it from. | Run manifest records audit segment ids and content hashes beside Bronze's; an object it does not name is **unreadable**, not merely unrecorded. CLAUDE.md → 0.5.2 |

**The pattern, now stable across ten findings:** every serious spec-level error was a *missing concept*, not a wording error — and each was found by trying to write the code, not by re-reading the document. B1 (Bronze), B5 (audit record) and the §12 omission are the same shape: a section that was internally coherent and silently depended on something no other section provided.

**§5c.3 marks that pattern's boundary rather than breaking it.** The predicate review found seven defects and **not one of them was a spec defect** — every section of `CLAUDE.md` they touch was already right, and the code simply did not do what the section said. So the claim above survives intact and gains its complement: reading the spec finds nothing, writing the code finds missing concepts, and **reading the code finds silent policy**. The seven are all one shape — a decision that had to be made, made in the kernel, and not written down anywhere a rule author could see it. That shape is invisible from the spec by construction, because the spec says what must be decided and not who decided it.

**The corollary, learned three times today:** a control that passes proves nothing. The guard, the schema sync test, and the pre-commit hook each only earned trust when observed to *fail* where failure was correct.

---

## 3. Verification debt — clear at the start of next session

1. ~~**GitHub Actions for `48f09f1` was never checked.**~~ Closed — green, 108/108, and the synthetic-fixture guard step ran rather than being skipped.
2. ~~**`docs/ROADMAP.md` and `docs/BUILD-PLAN.md` presence has never been verified.**~~ Closed — both are present in `docs/`.
3. ~~**No LICENSE file.**~~ Closed — proprietary `LICENSE` added at the repo root. MIT and Apache were both rejected: the repo carries `tr-core`, which is the reusable rule asset the whole economic argument in §1 rests on, and a permissive licence would place it in the public domain of every engagement it touches. See §8 for the obligation this leaves open.
4. ~~**CI has never been checked against a `pytest` run that includes `duckdb`.**~~ Closed **conditionally**. It is installed and it genuinely runs: `duckdb>=0.10.0` sits in `dependencies` rather than the `dev` extra, so CI's `pip install -e .[dev]` pulls it, and `tests/test_bronze.py` exercises it for real — reading row group layout back out of the written file rather than asserting the pinned constant against itself.

    What stays open is the **declaration, not the test run**: duckdb is declared a *runtime* dependency and today nothing under `kernel/` imports it. Only tests do. That is consistent with §14 ("Polars + DuckDB for execution") read as a forward commitment, but it is not yet true as a statement about this build. **Re-open at item 12, when `profile` is written** — the first component with an actual reason to reach for it. If `profile` uses duckdb the declaration was right all along; if it does not, then either the declaration or the usage is wrong, and the question is which one moves. Left as a runtime dependency in the meantime, deliberately: demoting it to `dev` now would be a bet on the second outcome, and the whole point is that the bet is not settled.

---

## 4. Decisions taken before Bronze (item 4) — ✅ closed

Both blocking questions are decided and written into `CLAUDE.md` §4.2.1–4.2.6 (v0.5.0). Recorded here as decisions, with what they cost, so item 4 starts from a settled position.

**Storage substrate — Parquet files, not database tables.** Decided on three grounds (§4.2.1). The one that settled it was the §12 content hash: a file's hash is its bytes, whereas a table has to be scanned and canonicalised first — row order, type rendering, NULL representation — so making a table hashable means solving a *new* determinism problem in order to deliver the determinism guarantee. Portability and schemalessness both point the same way. Addressed through a **path abstraction** (§4.2.2): local FS, S3, Azure Blob equally valid, no local-disk assumption.

**How immutability is enforced — tamper-evidence, not tamper-prevention (§4.2.5).** The honest framing, because Bronze is client-owned: the Harness cannot prevent modification of a store it does not control, and designing as if it could would assume away the ownership model. Three layers — single-writer API with no `overwrite` parameter, read-only filesystem bits as an explicit *speed bump nothing may depend on*, and the content hash verified on every read as the actual control, failing the run with `BronzeIntegrityError`. This is exactly the testable form the previous session asked for, and it is now a Gate 0 criterion (§15): modify a partition's bytes on disk, the read fails; write the same partition id twice, it is refused.

**`AuditRecord` does *not* live in Bronze.** The previous session's note that "Bronze also now hosts `AuditRecord`" was wrong, and finding out why produced the sharpest correction of this pass: audit records are produced by `normalize`, i.e. *after* `ingest`, so writing them into Bronze is a post-ingest write to Bronze and a direct P10 violation. It also breaks the content hash — a partition that grows as later stages run has no stable hash, so §4.2.5's third layer collapses. The audit store is a **separate, parallel, append-only store** under the same three-layer discipline (§4.2.6), with `audit.retention_days` ≥ `bronze.retention_days` enforced as a preflight blocker.

**Build-order consequence.** Item 4 was two stores, not one, split into 4a (§4a) and 4b (§4b). Both are closed. It stayed ahead of preflight — preflight's governance blocker is a check on the audit store's retention, so the manifest models had to exist first, and they now do.

**A third defect surfaced while building 4a**, the sixth of this shape: §4.2 and the §6 stage table both promised `ingest` lands raw input *byte-for-byte*. Writing the store made it obvious that the promise cannot hold — non-UTF-8 bytes do not enter a text column, and a `binding.kind: database` source has no byte stream in existence to preserve. Replaced in `CLAUDE.md` 0.5.1 with the property that does hold and that the pre-image guarantee actually needs: Bronze loads input **unmodified and uncoerced**, and the content hash covers what Bronze actually stores. The residual question belongs to `ingest` and is recorded in §4a.2.

### 4.1 Known spec/code divergence — ✅ closed

| Spec (§7.1) | Code (`schemas/manifest.py`) | Status |
|---|---|---|
| `bronze.format`, typed `Literal["parquet"]` (§4.2.1) | `BronzeConfig.format` | ✅ Closed in 4a |
| `audit:` block — `location`, `retention_days` | `AuditConfig`, required with no default | ✅ Closed in 4b |
| `audit.retention_days` ≥ `bronze.retention_days`, governance blocker (§6.2.2) | `Manifest.audit_must_outlive_bronze` | ✅ Closed in 4b |

**The silently-permissive direction is closed.** A manifest carrying an `audit:` block was previously accepted and ignored; it is now parsed, and an inverted retention pair is refused at load. That the check runs at load rather than only in preflight is deliberate and not a departure from §6.2.2: preflight still reports it — a manifest that will not load is the most legible blocker there is — but load-time refusal means no code path reaches a run with an inverted pair, including one that never called preflight. The check lives with the data it constrains rather than with the stage that happens to report it, which is the same reasoning already used for `egress.evidence_only`.

**On the `Literal["parquet"]` shape.** Kept rather than dropped because a configurable `format` field advertises that other formats work. Note this differs from `egress.evidence_only`, which stays a `bool` refused by a validator: a second egress mode would need its own gate, so that field stays open and the refusal is behavioural, whereas a second Bronze format is a new substrate implementation and until one exists there is nothing for the type to admit.

---

## 4a. Built this session — path abstraction and Bronze store

`kernel/storage/` (§4.2.2) and `kernel/bronze/` (§4.2). 30 tests. Not built, by decision: `ingest`, `profile`, CLI wiring, the audit store, S3/Azure backends, partition listing, retention and GC.

**Writer determinism was the real work.** Measured before pinning, on polars 1.43.2: repeated writes of one frame are byte-stable, thread count does not affect output, and the Parquet footer carries no timestamp — `created_by` is just `"Polars"`. So there is no run-to-run nondeterminism to find today. But `row_group_size` defaults to a value *derived from the data*, and at 400k rows the default and an explicit `100_000` produce different bytes. The risk was never that one call returns two answers; it is a derived default drifting with input shape or a library release, which is the same failure class as the exporter writing CRLF on one host and LF on another.

`PARQUET_WRITER_OPTIONS` pins compression, level, statistics, row group size and page size. It began life private inside `kernel/bronze`; 4b moved it to `kernel/serialisation.py` and put a test under the claim it had been making in a docstring — see §4b.2.

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

## 4b. Built this session — the audit store

`kernel/audit/` (§4.2.6), `kernel/serialisation.py`, `AuditConfig`, and the run manifest that turned out to be a precondition rather than a follow-on. 48 new tests.

**Not built, by decision:** `normalize` (the producer of every record this store will hold), retention and GC for either store, S3/Azure backends, the remaining §12 run manifest fields, and any CLI surface. The division is the same one 4a drew — this is a place for records to go, not the thing that makes them.

**The design question was "what is the audit store's partition?"** §4.2.6 says a growing store has no stable content hash, which is true and also true of Bronze: the Bronze *store* grows too, one partition per batch, forever. Nobody proposed hashing "Bronze", because §4.2.5 hashes a partition. So the audit store did not need a new mechanism, it needed its own unit of closure. That unit is a **segment**, and the whole of 4b follows from picking what closes one.

**Segments are cut by source row ordinal, and nothing else.** Segment N carries the audit records of rows `[N·100k, (N+1)·100k)`. Assignment is a pure function of the ordinal — no clock, no worker id, no accumulated state — so the same records in any arrival order produce the same segments with the same bytes. Two alternatives were rejected on the record: **time-based flushing** reads the wall clock, so boundaries move between runs and P2 falls immediately; **byte-size flushing** is a function of the *compressed* size, so a polars upgrade would silently re-segment a store whose earlier segments were cut differently. A row count has neither property. Buffering per worker, the obvious first design, does not work either — it moves the nondeterminism rather than removing it.

**Sorting inside the writer, not only in the assigner.** `write_segment` re-sorts records it is handed, which is redundant for every correct caller. That redundancy is the point: `normalize` will hand records over in worker completion order, and a property that depends on callers being careful is not a property.

### 4b.1 Three schema decisions, all subtractions

`AuditRecord` was a stub carrying "the fields will grow". It shrank instead, and each removal bought something specific:

| Change | Why |
|---|---|
| **`occurred_at` removed** | A per-record wall-clock read is a per-record source of nondeterminism in a store whose entire integrity story is a content hash. Time belongs to the run, and the run manifest records it. P8 is unharmed: a record is reached through the segment that names its run, so "when" is answered one indirection away and answered *once*, rather than restated a million times with microsecond noise no reader wants and no replay can reproduce. |
| **`run_id`, `batch_id`, `bronze_partition` removed** | All three are constant across a segment, so they belong to the segment and now live on `SegmentRef`. The gain is not deduplication: with them on the record, a segment's bytes were a function of *which run wrote them* rather than *what was written*, so two runs over identical input produced different bytes for identical facts. With run identity held one level up, they do not — and a replay's audit store can be diffed against the original byte for byte. `batch_id` did not come back: §4.2.4 makes a batch a partition. |
| **`row_ordinal` added** | The only addition, and the one the pure segment assignment depends on. |

The direction is worth noting because it inverts the usual drift: a stub's fields normally accumulate. These three came off because writing the store made clear what each one cost, and none of them was paying for itself.

### 4b.2 The break round found a hole in a test, not in the store

Every control was broken deliberately, per the standing lesson:

| Break | Result |
|---|---|
| `write_segment` stops sorting | Writer-sort test failed — **but the central worker-order test passed** |
| `read_segment` skips `verify_segment` | Both tamper tests failed |
| A second `write_parquet` call site added | Call-site test failed |
| `RunManifest.segment()` returns the first ref instead of raising | Absent-segment test failed |
| Audit segments no longer checked against the manifest's run id | Foreign-run test failed |
| Duplicate id detection removed | Repeated-id test failed |

**The first row is the finding.** The central acceptance test — same input, different worker orders, byte-identical segments — went through `assign_segments`, which sorts. So it exercised one of the two sorting layers and would have passed with the writer's own sort deleted. A test that names the property in its title while covering half of it is worse than an absent test, because it is counted. It now runs both write paths: the intended one and the one a careless caller takes.

The same shape recurred in the run manifest tests. The absent-segment test originally asked an *empty* manifest for a segment, which makes almost any lenient lookup blow up on its own. Rewritten to record one segment and ask for a different one that is also on disk, it catches the case that matters: a lookup falling back to "close enough" returns the wrong reference, the hash matches its own bytes, and the read succeeds **silently** with the wrong segment.

**The corollary is now sharper than "break your controls".** Breaking a control tells you whether *some* test fails. It does not tell you whether the test you believed in is the one that caught it — and here, twice, it was not.

Also from this round: without verification, a truncated segment surfaces as a raw polars `ComputeError`, exactly as it did for Bronze in 4a. Verification converts an incomprehensible parser crash into a named diagnosis.

### 4b.3 The run manifest was a precondition, not a follow-on

`kernel/storage`'s six-member surface carried one Bronze-shaped assumption: **the caller always already knows the name of the object it wants.** For Bronze that is free, because §12 makes the run manifest the authority for partition ids. For the audit store it is not free — its reader asks "what happened to this record?", which is a query, and the first instinct is to add `list()`.

Adding it would have been wrong, and the reason is the same one that keeps the expected hash out of the partition it describes: **a directory listing is not tamper-evident.** It reports what is present *now*, which is exactly what an adversary controls — a deleted segment simply does not appear, and a missing segment becomes indistinguishable from one never written. So the store stayed addressable by known id, and the id had to come from somewhere.

That somewhere was named in §12 for Bronze and named nowhere for audit, which is the spec defect in §2. `kernel/run_manifest.py` closes it: partition refs and segment refs, lookups that refuse an unnamed id, and read helpers whose signature makes the manifest unavoidable. One asymmetry fell out and is now in the spec — a run may reference Bronze partitions written by **earlier** runs (read-once and rule backtesting both depend on it), but only its **own** audit segments, because a run reads Bronze and writes audit.

**Deferred rather than defaulted:** pack versions, reference snapshot ids, the arming record, applied transforms. An `arming: ArmingRecord | None = None` would let a run emit a manifest with no arming record and still look complete — the silently-permissive failure mode this repo has already had to close once, in exactly this document.

**`kernel/storage` was not changed, and that is the result.** Five of its six members served the second store unchanged. The sixth, `exists()`, still has no kernel caller — preflight's reachability check will likely be its first. The honest summary is that the abstraction was one member too wide, not one member too narrow.

---

## 5a. Built this session — preflight (item 5, partial by decision)

`kernel/stages/preflight/` and `harness preflight`. 59 tests at the time; item 3a then added a check and implemented four. **18 of §6.2.2's 30 checks are implemented**; the other 12 are registered and report `unavailable`. On the minimal manifest that is 16 `passed`, 2 `not_applicable`, 12 `unavailable`, giving 9 blocking and 3 warnings — four of the eighteen pass vacuously, on an empty pack list and an empty reference list, and `BUILD-PLAN.md` §2.1 records that both stop passing the moment anything is declared.

**A gap inventory came before any code**, and it is what set the scope. Working through the seven categories check by check produced three kinds of gap, and keeping them apart is what stopped preflight from becoming half stub with nobody able to say which half:

| Kind | Meaning | Example |
|---|---|---|
| **schema gap** | The manifest cannot *declare* the thing, so there is nothing to check | No column carries a semantic type; no credential expiry field |
| **machinery gap** | A component that does not exist | No source adapter, no pack loader, no predicate registry |
| **not applicable** | The check has no meaning for this binding | Collation, for a file source |

**The largest single finding was that the manifest cannot bind a semantic type to a column.** §7.5 calls that binding the reuse mechanism and §13 measures `reuse_ratio` through it — and `column_map` is `dict[str, str]`, source name to canonical name, with nowhere for a type to live. The chain would continue through the canonical schema (`canonical_schema: automotive/sales_v2`), which has no artifact, no loader and no schema. Three §6.2.2 checks rest on that one gap. It was left open deliberately: it is item 3's, and closing it inside item 5 would have pulled half of item 3 along with it.

### 5a.1 The design: the check list is data

**All 29 checks are registered whether or not this build can run them**, and the runner walks the registry rather than the implementations. An id with no implementation is reached anyway and reported `UNAVAILABLE` with its registered severity intact, so a blocker that was never written blocks. The alternative — registering checks as they get implemented — makes the verdict a statement about how much of preflight got built, silently. That is the seventh time this repo has met that shape; here it is designed out rather than watched for.

Four statuses, and the two that matter are the ones that are easy to confuse:

- **`UNAVAILABLE`** — the check did not run, whether because nothing implements it or because a prerequisite failed. Both share the only property that counts: nothing was verified. Blocks at blocker severity.
- **`NOT_APPLICABLE`** — the check has no meaning *for this manifest*, decided from a declared manifest fact and never from whether the code exists. Does not block. Exactly one check uses it today: collation, for a file binding.

Keeping "not implemented" and "could not run" as one status is deliberate. Splitting them would invite a rule treating one as tolerable, and the pressure to write that rule would come from a real inconvenience — which is how a control gets softened.

**Severity lives in the registry and nowhere else.** No manifest key, flag or environment variable moves a blocker to a warning, and the manifest is asserted to carry no severity-shaped key at all.

### 5a.2 The digest refuses to be partial

§6.2.3 rule 1 makes the digest **a claim about what would invalidate an approval**, so everything it omits is something a client approved without meaning to. A digest missing pack versions means a pack bump does not void arming — silently, precisely where the rule promises it would.

So a digest is produced only when every component resolved, and it records the components it covers. Unresolved means **no digest and a blocked verdict**, not a shorter hash. Empty counts as resolved: a manifest declaring no packs has nothing to resolve.

That vacuity is load-bearing rather than a loophole — it is what lets a file-source, pack-free manifest produce a complete digest while item 3 is open — so the check detail says "no packs declared, so there is nothing to resolve" rather than reporting a bare pass.

### 5a.3 Verification class and declaration class

`CLAUDE.md` 0.5.4. §6.2.2 listed "DPA reference recorded" beside "declared encoding actually decodes the source" as though they were one act. One measures an observable fact; the other confirms somebody made a written commitment.

Both belong in preflight — a missing DPA reference must stop a run — but a client reading `restore point: passed` beside `encoding: passed` will reasonably conclude both were tested, and one was. Declaration-class rows now render with "declared, not verified" beside them. Three checks are declaration class: DPA reference, sub-processor register, restore point.

This is not a placeholder for verification arriving later. Some facts are not observable from inside the client boundary by a tool holding no standing access (P9), and demanding a restore be *performed* before every run is not a control anyone would keep.

### 5a.4 Where this build actually stands

**Even the narrowest manifest cannot reach `ready`**, and a test asserts it. File source, no packs, no external references, every implemented check green — still blocked, by the 12 nothing implements. There is no flag that shortens that, which is the point.

That is not a failure of item 5, it is item 5 reporting honestly. §6.2.4 sells preflight as the cheapest first contact with a client's data, answering "can this even be connected to, and what is missing" — a report that names its own gaps per check *is* that deliverable.

**The break round found nothing wrong with the store this time**, which is worth recording because the previous two sessions both found the hole in a test rather than in the code. Five controls were broken and each was caught by the test that claimed it:

| Break | Result |
|---|---|
| Delete a blocker from the registry | Id-set and blocker-set tests failed |
| Demote a blocker to a warning | Blocker-set test failed |
| `UNAVAILABLE` no longer blocks | Six tests failed, including the central one |
| Quote the offending bytes in a check detail | Report leak test failed |
| Drop `pack_versions` from the digest | Digest completeness test failed |

The first is the one worth keeping in mind: **deleting a check is the quietest bypass of the entire gate.** It takes its blocker with it, the verdict goes green, and nothing else in the suite notices. The id set is pinned for that reason alone. Warning severities are deliberately not pinned — a warning becoming a blocker is a tightening, and the direction needing a guard rail is the one that makes a run easier to start.

### 5a.5 Sequencing decision — item 3 is not pulled forward

The walking skeleton (item 7) will run on a **minimal manifest**: file source, `packs: []`, no external references. Pack resolution is satisfied vacuously, the digest is complete, and the path to `ready` is open once the remaining blockers land — without item 3 moving ahead of item 5 in the plan.

The alternative was to bring the predicate registry, the rule schema and the pack loader forward so that a realistic manifest could pass. Rejected: it would have made item 5 depend on the largest unbuilt piece in the plan, and the walking skeleton's job is to prove the *pipeline shape*, which a pack-free manifest proves as well as a pack-bearing one.

### 5a.6 Not built, by decision

`normalize`, retention and GC for either store, S3/Azure backends, arming (item 6), and the 12 unimplemented checks. Two smaller ones worth naming because they will be reached for: **`StoragePath` gained no members** — the source is read whole, inheriting the single-node ceiling §4a.1 already documents, and a `read_prefix(n)` is what the first remote backend or first genuinely large extract will force. And **`harness arm` now refuses loudly** rather than printing a success line; a gate that looks armed and authorises nothing is worse than an absent command.

---

## 5b. Built this session — the canonical schema (item 3a)

`canonical/`, `schemas/canonical.py`, `kernel/canonical.py`, and the PII restructuring in `kernel/registries.py`. 30 tests.

**What was actually missing was an artifact, not a registry.** Item 3 read as "two enum lists" and was priced at one day. One of them is that. The other was never a registry: `column_map` maps a source name to a canonical *field name*, and nothing in the repo said what a canonical field is — so §7.5's "rules bind to semantic types" had no chain to travel, and §13's `reuse_ratio` had nothing to measure. Preflight found it by stopping at the same missing link three times.

**The resolver is deliberately not a pack loader**, and §7.6 now carries the reason: **rules accumulate, canonical schemas do not.** §7.4's layering exists because a `client` rule refines a `core` one — that accumulation *is* the reuse mechanism. A canonical schema is the fixed target both sides map onto, so two artifacts claiming one id is an error rather than a precedence decision. Give it precedence and a client pack can quietly change what `sales_v2` means, at which point two engagements emit different "canonical" output under one name.

### 5b.1 PII-typing became structural

`PII_SEMANTIC_TYPES` was a `frozenset` beside the enum, which meant **a type added without being added to the set defaulted to non-PII, silently** — and non-PII types are eligible for §8.1 distinct-value export. The failure mode was a forgotten line turning into an export channel, with nothing to notice.

The flag now moves into the member: `__new__` takes it positionally, so `FOO = "foo"` raises at class creation and the import fails. There is no state in which a member exists unclassified. The `str` value is untouched, so Pydantic, JSON Schema and the egress gate's membership check behave exactly as before — asserted, not assumed.

**Sector types live in the kernel registry, and §8 requires it rather than preferring it.** §8 permits semantic type labels to cross the boundary *because* MAXENG owns the word list and ships it in the release. A pack that could add a member at runtime would put an externally-authored string into a permitted egress class, and the closedness the permission rests on would be gone. The split is §7.5's existing one: the type is kernel-owned, its shape is pack-owned. `ENERGY_QUANTITY` was added for Gate 0 — a metered MWh value is not a `currency_amount`, because §9.5 puts energy in `prior` mode where the rules come from physics.

### 5b.2 What 3a opened, and one thing it did not

| Check | Before | After |
|---|---|---|
| `schema.canonical_schema_resolves` | did not exist | **implemented** (new in 0.6.0) |
| `schema.declared_key_present` | unavailable | **implemented** |
| `volume.max_timestamp_within_freshness_window` | unavailable | **implemented** |
| `schema.types_match_semantic_types` | unavailable | **not applicable** to a file binding |

The fourth row is the correction to what was planned. A CSV declares no column types, so "types compatible with bound semantic types" has nothing to be compatible with — the check has meaning against a database catalog, and that needs a source adapter this build does not have. **Comparing an observed *shape* against a semantic type is a different check**, it reads values rather than metadata, it needs locale-aware parsing, and it belongs to discovery Layer A (§9.1). Preflight reads schema, catalog and aggregate metadata; a check that must parse every value to reach a verdict is by construction not one of its checks. That reasoning is in the check itself, not only here.

The freshness check draws the same line: an ISO-8601 column is read, a Turkish date shape reports `unavailable` naming `tr-core`. Reporting it `failed` would blame the client's data for a capability the Harness does not have.

### 5b.3 The guard read ISO-8601 timestamps as plates

Found the way these things get found — the guard blocked a commit adding a freshness column to a fixture. The day number, the `T` separator and the first two digits of the hour read as province code, plate letter and plate digits, which is a well-formed plate by every rule the pattern knows.

Fixed rather than worked around in the fixture, because ISO timestamps are unavoidable here — audit records, run manifests and freshness columns all carry them — so the false positive would have recurred constantly. **A control that cries wolf gets disabled**, and this one is the last thing between a real identifier and a public repository. Timestamps are blanked in place rather than skipped by line: a row carrying both a timestamp and a plate is the normal shape of a vehicle record.

**§0's literal rule then demonstrated itself twice.** The first attempt at the fix wrote an example timestamp in a comment and a plate in a test; the guard blocked both. Both are built at runtime now. The rule reads as pedantic until the guard blocks the very commit that fixes the guard.

### 5c. Built this session — the predicate registry and the rule schema (item 3b)

`kernel/predicates.py`, `kernel/checksums.py`, a rewritten `schemas/rule.py`, and the last two pack checks that do not need a loader. 31 tests.

**The predicate registry declares three things structurally, not one.** `SemanticType`'s pattern extended: `__new__` takes implementation, parameter contract and **scope** positionally, so a member written as `FOO = "foo"` fails at class creation. Scope earns its place by being the one that would otherwise default silently and fail latest — a column-scope predicate handed a single cell returns a confident, meaningless answer rather than an error.

**Params carry names, not content**, and this is what keeps §7.5's central claim true. `matches_pattern` takes a registered `PatternName`; a pack never supplies a regex, because that would be executable content authored outside the release — and a catastrophic-backtracking one is an availability incident in a client's environment rather than a bug in ours. Patterns are locale-neutral in this build; the Turkish shapes arrive with `tr-core` as a deliberate kernel change.

**Three lifecycle invariants moved from convention into the schema:**

| Invariant | What it stops |
|---|---|
| `enforced` requires a predicate | A rule that quarantines with nothing to evaluate (P7) |
| A discovered rule needs `provenance.signature_ref` to load as confirmed or enforced | `state: proposed` becoming `state: enforced` in a text editor (§11, P4) |
| `repair.reversible: false` does not load | A setting §6 cannot honour presenting itself as available |

The second is declaration class in the §6.2.2 sense — it confirms a signature was *named*, not that one was given. Verifying the reference resolves needs the Readiness Report generator (item 13), and §5c.1 records that gap rather than letting it look closed.

**`band` and `derived_from_client_data_only` have no writable field**, and `extra="forbid"` is what makes that true rather than aspirational. Pydantic's default would have dropped a written `band` silently, so a pack author writing `band: money` over a 0.91 hold rate would have seen no error and believed it took effect — refusing beats ignoring. The band cap does real work: an uncorroborated rule at 0.9963 comes out `ambiguous`, not `money`, which is §9.4's circularity guard executing rather than being described.

### 5b.4 Open — three questions the canonical schemas leave unanswered

**Status: open. Owner: Nazif. Due: before the schemas are reviewed as drafts.**

`CLAUDE.md` 0.6.3 settled the naming principle — entities are named by the role they play, not by the client's organisational level, because `canonical/` is not layered and one schema has to fit every client in a sector. Applying it renamed `plant_code` to `measurement_point_id`. Three things it did not settle:

**1 — Where the measurement level is declared.** Whether a point is a plant, an inverter, a string or a meter is an engagement fact, and it is an input to rules rather than to identity: *generation must not exceed nameplate capacity* needs the level, *one reading per point per instant* does not. It is deliberately **not** in the key and **not** in the grain. The natural home is the manifest, since P3 puts variance there — but adding a manifest field for a rule that does not exist yet would be a field with no reader, so it is recorded rather than built.

**2 — Long format is out of scope, and its key is known.** `grain.layout: wide` now says out loud what the schema always assumed. The long form is `(measurement_point_id, reading_at, measurement_type, value)` with `measurement_type` in the key — a **different artifact under a different id**, not an edit to this one, since §7.6 makes a changed shape a new id. Worth deciding before a client arrives with a tall SCADA export, which is the common shape.

**3 — `automotive/sales_v2`'s entity is a placeholder.** `vehicle_sale` reads as "one sale of one vehicle", and `key: [chassis_no]` presumes one sale per vehicle — false the first time a car is resold. The real question is whether a row is a vehicle, an order line, or a delivery, and the three give different keys, different grains and different rules. The artifact and its comment say so; nothing else does.

### 5c.1 Open — the signature reference is named, not verified

**Status: open. Owner: unassigned. Due: item 13, the Readiness Report generator.**

`provenance.signature_ref` must be present before a discovered rule loads as confirmed or enforced, which closes promotion-by-text-editor. What it does **not** do is check that the reference names a real signed entry — any non-blank string satisfies it today. Until the Readiness Report exists there is nothing to resolve against, so the control is declaration class by necessity rather than by choice.

Recorded here because the alternative was to leave §11 looking fully enforced. When item 13 lands, the check becomes verification class and this section closes.

### 5c.2 Two structural tests had been passing for the wrong reason

Both `test_a_member_cannot_be_declared_without_its_pii_flag` and its predicate counterpart asserted that a class fails to build when a member omits its declarations, and both wrote `__new__ = X.__new__`. **That is not the custom constructor.** Enum moves a class's own `__new__` to `__new_member__` during creation and substitutes its own value-lookup `__new__` — so the `TypeError` came from the lookup failing, and neither test said anything about the contract it was named after.

Found by accident: a new sibling test asserting that no parameter may acquire a default raised `KeyError` instead of failing, because the signature it introspected had no `implementation` in it.

This is the third session running in which the break round found the hole in a test rather than in the code, and it sharpens the standing lesson one more turn. **Breaking a control tells you a test fails. It does not tell you the test failed for the reason its name claims** — and a test that passes for the wrong reason is worse than an absent one, because it is counted.

### 5c.3 The predicate review round — seven defects, one shape

A review of `kernel/predicates.py` before the list goes to Nazif. Seven findings, and the reason to keep them together is that **six of the seven are the same defect**: a decision that had to be made was made in the kernel and left invisible to the rule that depends on it. P3 puts variance in packs and manifests; a hardcoded answer is variance that has been decided and then hidden.

| # | Defect | Resolution |
|---|---|---|
| 1 | **`$` accepts a trailing newline.** Python's `$` matches at end-of-string *or* before a trailing `\n`, and `matches_pattern` used `search`. So `"123\n"` satisfied `digits`, `"2026-08-05\n"` satisfied `iso_date`. A trailing newline in a CSV cell is the dirt the harness exists to catch, so the validator passed the thing it was pointed at | `MatchMode` declared per pattern, positionally, and `FULL` patterns carry no anchors of their own |
| 2 | **`\d` is not ASCII.** It spans Unicode decimal digits, so `٣٤٥` satisfied `digits`. Worse one module over: `str.isdigit()` is true for them and `int()` parses them, so `is_valid_tckn` ran its arithmetic over them and returned a verdict | `[0-9]` in every kernel digit class; `_is_ascii_digits` in `kernel/checksums.py`; the guard's patterns follow (§5c.4) |
| 3 | **`field_before` was fail-open.** A missing side passed, so `delivery_date < order_date` never fired on a row with no `order_date` — P7 inverted, on exactly the rows most likely to be wrong. `fields_equal` had it quieter: `None == None` made two absences read as agreement | `on_missing` — mandatory, no default |
| 4 | **`is_null` carried embedded policy.** NULL, empty cell and `"   "` are three things, and whether they are equivalent is a client's call. It was also answered *twice and differently*: `is_null` treated `"   "` as absent while the row predicates tested `is None` and treated it as present | `treat_blank_as_null`, routed through one `_is_absent` helper so all seven absence-aware predicates get one answer |
| 5 | **No composite-key predicate.** `energy/generation_v1` declares `key: [measurement_point_id, reading_at]` and `is_unique` reads one column, so nothing in the registry could evaluate the key the canonical schema declares | `Scope.FRAME` + `key_is_unique`, the registry's 14th member |
| — | **`is_iso_date` accepted a timestamp.** `datetime.fromisoformat` widened in 3.11; the name said date and the behaviour said date-time | `date.fromisoformat`. The name was right and the behaviour moved |
| — | **`is_numeric` accepted `nan` / `inf`.** `float()` takes all three, and then every comparison in `in_range` is False — so the rule reported a violation whose cause was in neither the value nor the bounds | Refused explicitly, in `_is_numeric` and again in `_in_range` because a float `nan` reaches the second without passing through the first |

**Two design decisions, both taken against a rejected alternative.**

*Anchoring is declared, not patched.* Replacing `$` with `\Z` fixes today and not tomorrow — `matches_pattern` still searches, and the next pattern written with `$` restores the bug. Switching wholesale to `fullmatch` breaks `non_blank`, which deliberately asks whether a non-space character occurs *anywhere* and cannot be written as a statement about a whole value. So the mode is a per-member declaration in the shape `Scope` already uses, and a `FULL` pattern's source carries no `^`/`$` at all: stating the anchor twice leaves `$`'s leniency sitting in a source someone will copy into a `SEARCH` pattern.

*A frame is columns, not rows.* `Scope.FRAME` is handed `{field name: values}`, aligned by position — what Polars already holds, and what a two- or three-column key check actually needs. The rejected shape was a sequence of row mappings, which builds a Python dict per row to answer a question about two columns; at a million rows that is a million allocations, and it would have handed `validate` (item 10) the wrong shape from the only interface telling it what to build. The scopes now pair cleanly: `VALUE`↔`ROW`, `COLUMN`↔`FRAME`.

**The alignment invariant is the one place this module raises.** Handed columns of length 1,000,000 and 999,999, `zip` stops at the shorter one and returns a clean verdict over a silently truncated frame. `FrameAlignmentError` refuses instead — and the reasoning is what keeps it consistent with "no predicate raises": the no-raise property is about *data*, because §6 gives `validate` one reaction to bad data (quarantine) and it cannot reach it from a traceback. A frame whose columns disagree about how many rows exist is not data, it is a caller that built the projection wrong. Returning `False` would attribute a harness bug to the client's data (P8); returning `True` would hide the dropped rows.

**The break round: 14 controls broken, 14 caught, and one test strengthened.** For the first time in four sessions no control was found undefended — but the standing lesson still earned its keep. `test_the_declared_key_of_a_canonical_schema_can_be_evaluated` stayed **green** under an implementation that read only the first key field, because it asserted a violating frame and a violating frame collides on one column too. It now asserts the clean direction as well, over a frame where every column repeats and only the combination distinguishes the rows — which is what makes the word "composite" in its name true.

### 5c.4 The guard and the validator now see one universe

`kernel/gates/guard.py`'s digit classes moved to `[0-9]` in the same change, and this is a consequence of finding 2 rather than tidiness. The checksum validators now refuse a non-ASCII digit outright, so a pattern still written with `\d` would hand `is_authentic_tckn` candidates it is structurally incapable of vouching for — a matcher whose verdict is about a different string than the one it matched. `normalise_msisdn` moved with them, for the same reason in the other direction: `\D` *preserves* Unicode digits, so one could survive into what that function calls "the ten subscriber digits".

A test pins the decision across both modules by reading the guard's source, because this is a property of what is written rather than of what it computes.

### 5c.5 Open — `on_missing: pass` inflates `hold_rate`

**Status: open. Owner: unassigned. Due: BUILD-PLAN item 12, discovery Layer A.**

`MissingPolicy` ships with two values, and the second has a consequence outside the predicate. A row whose side is absent and whose policy is `pass` is counted as **evaluated and satisfied** — so it raises `hold_rate`, and `hold_rate` is what §9.2 turns into a confidence band. The `money` band is 0.99–0.999, which is narrow enough that a column with a few per cent of empty cells could be carried into it by rows nobody actually tested.

The likely answer is a third value — `skip`, removing the row from the denominator rather than the numerator — which makes `hold_rate` a rate over rows the rule could genuinely be applied to. It is deliberately **not** built now: nothing computes `hold_rate` yet, discovery is item 12, and a third policy value added before its only consumer exists is a value with no reader. Recorded rather than guessed at, and the enum's docstring points here so whoever writes Layer A meets the question rather than inheriting a two-value enum that looks finished.

---

## 5. Small items flagged but not actioned

- `PreflightConfig.row_count_bounds` is `dict[str, int]`; a typed `RowCountBounds` model would stop `{"foo": 5}` and `{}` from validating. A preflight blocker will depend on this.
- `TargetConfig.retention_days` has no lower bound while `BronzeConfig.retention_days` has `gt=0`. Quarantine holds raw violating records; the same constraint applies.
- `tenant` and `engagement` were removed from the evidence artifact (fail-closed, correct for now). The Readiness Report (item 13) must bind itself to an engagement somehow — decide the source then.
- VKN label matching remains a fixed spelling list. The real answer is semantic-type binding via the manifest's `column_map` (§7.5), which lands with item 3. Do not keep widening the regex.
- `;` delimiter detection in the guard is tr-TR-specific knowledge sitting in the wrong layer. It belongs in `packs/core/tr-core` once that exists.
- ~~`pyproject.toml` declares `version = "0.4.0"` while `CLAUDE.md` is at 0.5.2.~~ **Closed — they are independent by decision** (`CLAUDE.md` 0.5.3). The package version versions the *code*; the spec version versions the *constitutional decisions* the code was written against. Several kernel releases can sit against one spec version, and a spec change that no code has caught up with is an ordinary state rather than an error, so lockstep would buy bookkeeping and nothing else. The gap is now recorded in three places that a future reader might reach from: a comment beside the `version` key telling them not to "sync" it, §12, and `RunManifest`, which carries **both** as separate required fields. The pair is meant to be read together — `kernel_version` explains bytes, `spec_version` explains behaviour that would otherwise look like a defect, since a run that landed Bronze byte-for-byte was correct under spec 0.5.0 and is not under 0.5.1.

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
- **`git bisect` will land on red commits that are not the defect.** This repo splits a change into `fix:` and `test:` commits, so a fix lands one commit before the tests that cover it and the suite is red in between. Known instance: **`3ff63bb` and `b2855b6` are red on their own; the drop tests arrive in `6a88111`.** Anyone bisecting into that range should read the range rather than the commit — the failures there are the old tests meeting new behaviour, not the behaviour being wrong. Recorded here rather than in the commit messages because a message naming its own hash cannot be written before the hash exists, and rewriting the two to add it would change the hashes this note points at.

---

## 8. Open — `NOTICE` file required before the first distributed build

**Status: open. Owner: unassigned. Due: Phase 1, at the point the SBOM lands.**

The `LICENSE` added at the repo root is proprietary and closes §3.3. It does not close the third-party side, and clause 4 of that file states the obligation rather than discharging it.

**The obligation.** Several dependencies are Apache License 2.0, and §4(d) of that licence requires that redistribution preserve attribution: the NOTICE text of the upstream project must travel with any distribution of a work containing it. This is not a courtesy — it is a condition of the grant, and failing it means the Apache grant does not cover the distribution at all.

**Why it becomes live in Phase 1 and not now.** The obligation attaches on *redistribution*, and today nothing is redistributed — the repo is private and the harness has never been built into an image. §14 ships the harness as **an OCI image plus a mounted client pack directory**, and that image is a redistribution containing every dependency in it. The first build for a client is therefore the first moment the requirement bites, and it bites at exactly the moment there is a deadline attached.

**Why it pairs with the SBOM.** A `NOTICE` file is only correct if the dependency inventory behind it is correct, and a hand-maintained list of transitive dependencies is wrong within weeks. Generate both from the same inventory in the same step: the SBOM is the machine-readable form, `NOTICE` is the human-readable attribution extracted from it. Doing the SBOM first and `NOTICE` later means doing the inventory twice.

**Scope note — wrapped libraries widen this.** §14 wraps Great Expectations, Soda Core, Splink, Presidio, and Deequ-style constraint suggestion. These are not yet in `pyproject.toml`; they arrive with the discovery and validation items. Whoever builds the inventory should expect the licence surface to be materially larger than today's five runtime dependencies suggest, and should check for copyleft among the transitive set at the same time — an LGPL or AGPL component inside a distributed image raises a different question than an attribution one, and it is cheaper to find it before it is load-bearing.

### 8.1 Open — decide what the image is allowed to contain

**Status: open. Owner: unassigned. Due: before the first image build, same trigger as §8.**

Auditing the generated JSON Schemas surfaced a larger question than the one being audited. Those files ship to the client (§14: an OCI image plus a mounted pack directory), which makes every class docstring a published surface — that part is closed, and `CLAUDE.md` §0 now carries the rule. What is not closed is **what else a naive image build would carry with it**.

`CLAUDE.md` sits at the repository root by §5's own layout. A `COPY . .` would put in front of the client: §1's economic argument for the product they are buying, §2.1's legal posture including where MAXENG believes its exposure lies, §13's target metrics for their engagement, and §16's open questions for counsel — one of which says in terms *"do not let either answer appear in marketing copy first"*.

None of that is a leak of client data, so no gate in the design catches it. It is a disclosure of MAXENG's own reasoning to the party it reasons about, and the only thing standing between it and a client is a decision nobody has made yet.

Three things to settle together, because they have one trigger:

1. **An explicit image manifest, not an exclusion list.** State what goes in — `kernel/`, `schemas/json/`, `canonical/`, the entry point — rather than what stays out. An exclusion list fails open every time a file is added.
2. **Where the specification lives at runtime.** The kernel references §-numbers in error messages and docstrings, and those are dangling pointers for a client with no copy. Either ship a client-facing subset, or drop the references from anything a client reads.
3. **The same question for `docs/`.** This file records estimates, defects and internal judgment. `BUILD-PLAN.md` prices founder days.

**Closed, same area, smaller:** `pyproject.toml` now declares `license = { file = "LICENSE" }` and carries the `Private :: Do Not Upload` classifier. The classifier is deliberately not a real one — PyPI rejects unknown classifiers, so an accidental `twine upload` fails rather than publishing a proprietary repo that carries `tr-core`. A future contributor "fixing" it to a valid classifier would remove the control, so the reason is in a comment beside it.
