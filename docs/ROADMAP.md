# ROADMAP — Data Onboarding Harness

**Reflects:** `CLAUDE.md` v0.4.0 · last reviewed August 2026
**Source:** external comparative review, July 2026 (benchmark set: Great Expectations, Soda, dbt tests, Deequ, Monte Carlo, Anomalo, Ataccama ONE, Informatica IDMC, Collibra DQ, Talend, Splink/Tamr/Zingg, clean-room architectures)
**Verdict:** MVP-viable. Gate 0 scope stands. All four blocking corrections are resolved in spec v0.4.0; everything else is phased and trigger-gated.

This document carries no version of its own. `CLAUDE.md` is the versioned artifact because it is constitutional; this and `BUILD-PLAN.md` are derived planning documents that record which spec state they were written against. Keeping three version numbers in lockstep is bookkeeping a two-person team abandons by week three — the "Reflects" line is the whole convention.

---

## 0. How to read this

The review produced sixteen recommendations. Four of them are **defects** — the spec is internally inconsistent or structurally wrong, and the cost of fixing them rises steeply once code exists. Twelve are **enhancements**, individually justified and collectively dangerous: adopting them all converts the Harness into the product §1 explicitly says it is not.

Every phase below therefore carries an **entry trigger**. A phase does not open because the previous one closed; it opens when its trigger fires. Nothing here is a commitment to build.

---

## 1. Blockers — all resolved in spec v0.4.0

Kept as a record of what was wrong and how it was fixed. Two of the four were fixed differently from what this document originally proposed.

| # | Defect | Resolution in v0.4.0 |
|---|---|---|
| B1 | **Pre-image hash contradiction (§12).** The spec claimed a client could be shown what a value was, from a hash. A hash verifies a claimed value; it cannot produce one. | **Fixed more broadly than proposed.** Rather than a dedicated pre-image table, **Bronze** became a core concept (P10, §4.2): raw input is landed immutably and every stage after `ingest` reads Bronze, never the source. Bronze *is* the pre-image store. This also repaired a second defect nobody had flagged — the §12 replay guarantee was undefendable while replay re-read a live source, and is now defined against a fixed Bronze partition |
| B2 | **Emit was not atomic (§6).** A run failing mid-`emit` left partial canonical output in the client's target schema. | Write-audit-publish, specified in §6.3. The kill switch is defined against the same boundary, so aborting never has to unwind a partial write |
| B3 | **Arming identity was unspecified (§6.2.3).** | **Fixed with more structure than proposed.** Identity resolves against the client's IdP in both forms, and §6.2.3 now defines two: interactive arming for one-shot runs and digest-bound **standing authorization** for scheduled continuous runs, which voids itself on any drift. The second form did not exist when this document was written and exists because per-batch approval on a continuous feed is approval fatigue |
| B4 | **Gate 1 signature-rate metric was Goodhart-exposed (§15).** | `signature_rate` is now paired with `signed_coverage` (violations caught by signed rules ÷ total violations). Both must pass at Gate 1 |

The pattern worth noting: two of four fixes came out structurally larger than the diagnosis suggested. Defects at spec level tend to be symptoms of a missing concept rather than local errors — B1 was not a wording problem, it was the absence of Bronze.

---

## 2. Phase 0 — MVP (Gate 0 → Gate 1)

**Trigger:** none. This is the current build.

Scope is unchanged from `CLAUDE.md` §15 plus two pulled-forward items:

- **`discovery_budget_minutes` manifest field**, enforced from the first discovery layer. Cheap now; retrofitting a budget into a running miner is not. The full FD benchmark waits for Layer B (Phase 2).
- **Property-based tests (Hypothesis) for predicates and transforms.** The review placed this late. It belongs here: the predicate registry is being written now, and adding generative tests to a registry that already has thirty entries is strictly more work than adding them to one that has five.
- **Evidence artifact lineage recording.** Not the composition test itself (Phase 1) — just the identifiers that make the test possible later. Omitting it now means the historical artifacts are untestable when the test arrives.

Explicitly still out: Layers B/C/D, Splink `resolve`, MCP server, any UI, attestation, sustain mode.

---

## 3. Phase 1 — Trust and loop closure (Gate 1 → Gate 2)

**Trigger:** Gate 1 passes, or a client requests a formal security review — whichever comes first.

| # | Item | Why here | Effort |
|---|---|---|---|
| P1.1 | **Artifact attestation** — cosign-signed OCI image, SBOM (syft), SLSA provenance, client-side digest verification as a preflight blocker | In a "code travels" model the client's trust transfers to the artifact. Without provenance, P1–P9 reduce to "trust MAXENG". This is the first question any enterprise security review asks — but building it for a synthetic-data Gate 0 is premature | Low–medium |
| P1.2 | **Static in-boundary review artifact** — single-file, serverless HTML generated from evidence plus the draft pack; accept / question / reject per rule; emits a signature file | The only realistic path to `time_to_signed_ruleset ≤ 10 days`. Does not violate the No-UI non-goal: this is a report render, not a product surface | Medium |
| P1.3 | **Composition leak test (Leg 3)** — adversarial reconstruction across *all* historical artifacts for one engagement plus licensed references | k-anonymity degrades under successive releases. The repeat-engagement model manufactures exactly this exposure | Medium |
| P1.4 | **Rule TTL and overturn loop** — `review_by` date on every `enforced` rule; measure the rate at which clients overturn quarantine decisions; auto-demote to `proposed` past threshold | Rules rot as data shifts. Overturn rate is the only honest measure of rule quality, and nothing currently measures it | Low–medium |
| P1.5 | **Bilingual Readiness Report (TR/EN)** | Signatures are given in Turkish business language; the repo stays English. The LLM already generates business-language justifications, so this is i18n plumbing | Low |
| P1.6 | **OpenLineage + OTel emission**, inside the boundary, into the client's own tooling | Enterprise integration and supportability; also makes `time_to_first_evidence` measurable rather than asserted | Low–medium |

---

## 4. Phase 2 — Friction relief (post Gate 2, demand-gated)

**Trigger:** each item has its own. Do not open on schedule.

| # | Item | Trigger | Effort |
|---|---|---|---|
| P2.1 | **Constrained AST predicate** — allowlisted operator/function set, compiled, signed, versioned; permits in-engagement rule authoring without a kernel release | Registry friction is *measured*, not assumed: ≥ 3 engagement-blocking predicate requests. Until then the cheaper answer is a documented 30-minute predicate template with tests | Medium–high |
| P2.2 | **In-boundary local LLM** (vLLM / Ollama) for discovery Layer D | An aerospace, public-sector, or defence engagement enters the pipeline. Removes the model provider from the sub-processor register entirely and answers spec open question #5 | Medium |
| P2.3 | **Push-down profiling** — `profile` runs as read-only SQL in the source database; large volumes never land in Polars | The single-node ceiling is actually hit. Compatible with the read-only source principle | Medium |
| P2.4 | **FD/UCC/IND/DC mining (Layer B) + benchmark** — sample-mine then verify on full data, with column pruning under `discovery_budget_minutes` | Layer A alone stops producing enough `money`-band rules to fill a report | Medium |

---

## 5. Phase 3 — Product-shaped (revenue-gated)

**Trigger — changed August 2026.** The original test was *three separate clients paying for the same step*. The current plan inverts it: build continuous operation for **one** client first, prove the value, then expand through a Tekbaş Teknoloji partnership. That inversion removes the original guard, so it is replaced by a different one — **90 days running at a single client with monthly support hours below a declared ceiling, before any second client.** "Three paying clients" measured demand; this measures support economics, which is the thing that actually breaks a two-person team.

| # | Item | Note |
|---|---|---|
| P3.1 | **Sustain mode / "Data Assurance"** — scheduled re-run (preflight + validate + drift report), evidence to MAXENG, data still never crosses | **Effort reduced by v0.4.0.** The architecture is already in place: Bronze makes batches first-class, `cadence: continuous` is a manifest field, and standing authorization (§6.2.3) is the scheduling primitive. What remains is a scheduler, the review UI (P1.2), the learning loop, and the commercial decision — not an architectural change. Still the largest revenue item and the answer to the review's sharpest commercial criticism |
| P3.2 | **ODCS (Open Data Contract Standard) import/export** | The manifest is already a data contract in all but name. Low cost, real RFP value |
| P3.3 | **Optional differential privacy on evidence counters** | **With a constraint the review omits:** DP applies only to repeatedly published aggregate statistics, never to the violation counts a client reads when deciding whether to sign a rule. Noisy counts corrupt the signing decision, which is the artifact's primary purpose. Off by default; `egress.dp_epsilon` is opt-in per engagement |

**Dependency worth naming:** P3.1 cannot ship without P1.2 (the static review artifact). Continuous operation with a human-in-the-loop queue and no interface is not a product, it is a support ticket generator. If the single-client system is pulled forward ahead of Phase 1, P1.2 comes with it.

---

## 6. Declined and conditional

- **Continuous observability as a product surface.** Sustain mode (P3.1) is a scheduled re-run, not a monitoring platform. Competing with Monte Carlo or Anomalo on continuous detection is a losing position and out of scope permanently.
- **Catalog, MDM, steward UI, enterprise governance breadth.** Deliberate. These are the enterprise-suite checkboxes; entering that RFP is a lost bid that damages references.
- **Agentic remediation.** P6 is identity, not a gap. Positioning: *agentic discovery, deterministic execution* — the LLM is aggressive in discovery and has zero authority in execution.

---

## 7. Scope discipline

Sixteen accepted recommendations would consume more capacity than the entire Gate 0–2 build. The mechanism that prevents this is the trigger column, and it only works if triggers are checked rather than assumed to have fired.

Review this document at each gate close. An item whose trigger has not fired does not move up because it looks cheap; an item whose trigger has fired does not wait because the phase label says later.
