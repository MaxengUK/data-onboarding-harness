# BUILD PLAN — Harness v0.4.0 → Gate 1

**Reflects:** `CLAUDE.md` v0.4.0 · last reviewed August 2026 · see `ROADMAP.md`
**Scope:** Gate 0 (synthetic) + Gate 1 (dealership, real data). Phase 1–3 items are out of scope by design.
**Headline:** ~30 person-days over ~10 calendar weeks. Cash cost is negligible; the binding constraint is founder time.

---

## 1. Cost summary

| Category | Amount | Note |
|---|---|---|
| Founder time (Nazif) | **~30 person-days** | The real cost — 30 days not billed to another engagement |
| Cash, build period | **~$50–100 / month** | Registry, small test VM, model calls for discovery Layer D |
| Third-party licences | **$0** | Entire stack is Apache 2.0 / MIT / BSD-3 |
| Not included | see §5 | Certification, UI, sustain mode, local LLM |

The temptation with an all-OSS stack is to report the cost as near-zero. It is not. Thirty founder-days in a two-person consultancy is the largest single expenditure on the table, and it should be compared against thirty days of billable delivery, not against a software licence.

**Estimate confidence:** Gate 0 (~20 days) is moderately reliable — it is bounded work on synthetic data. Gate 1 (~10 days) is not, because its calendar depends on a client. See §6.

---

## 2. Work split — who does what

Legend: **C** = Claude writes it (code, tests, schemas, docs) · **N** = Nazif's judgment or access is required · **X** = off-the-shelf, wrapped not written

| # | Item | Owner | Nazif days | Week | Why Nazif is needed |
|---|---|---|---|---|---|
| 1 | Repo skeleton, Pydantic schemas (manifest, pack, rule, evidence), CI synthetic-fixture guard | C + N review | 1.5 | 1 | Approving the canonical schema shape — it is expensive to change later |
| 2 | Evidence emitter, egress allowlist, Leg 1 leak test | C + N review | 1.0 | 1–2 | Deciding what may leave the boundary is a commercial and legal call, not a coding one |
| 3 | Predicate registry (~15 predicates) + semantic type registry | C + N decides list | 1.0 | 2 | The semantic type list is the reuse mechanism; it must reflect real client data shapes |
| 4 | Bronze store — partitioning, immutability enforcement, pre-image lookup | C | 1.5 | 2–3 | Storage substrate decision (Postgres / DuckDB / object store) |
| 5 | Preflight — all seven check categories | C + N defines severities | 2.0 | 3 | What counts as a blocker vs. warning is a client-relationship judgment |
| 6 | Arming — interactive + standing, client IdP interface (stubbed in Gate 0) | C + N decides IdP path | 1.0 | 3 | How the client's IdP will actually be reached |
| 7 | Walking skeleton: `preflight → ingest → Bronze → profile → emit` (WAP) | C | 1.5 | 3 | — |
| 8 | Replay / determinism assertion against fixed Bronze partition | C | 0.5 | 3 | — |
| 9 | **`tr-core` v0** — i/İ casing, date, number separators, MSISDN, TCKN/VKN checksum, plate-province, tr-aware fingerprint | C + **N validates** | 2.0 | 3–4 | **The highest-value item and the one Claude cannot finish alone.** Turkish edge cases come from having seen real dealer data, not from documentation |
| 10 | `map → normalize → validate` | C | 1.5 | 4 | — |
| 11 | Property-based tests (Hypothesis) for predicates and transforms | C | 0.5 | 4 | — |
| 12 | Discovery Layer A — profiling, format clustering, locale-aware fingerprint clustering | C | 1.5 | 4–5 | — |
| 13 | Readiness Report generator (TR/EN) | C + N shapes language | 1.0 | 5 | Business-language wording is what gets signed; it must sound like the client's own vocabulary |
| 14 | Leg 2 re-identification test | C | 1.0 | 5 | — |
| 15 | Synthetic fixture design + Gate 0 acceptance run | **N** + C | 1.5 | 5–6 | Fixtures must resemble real dirt without containing real identifiers |
| 16 | Gate 0 findings and fixes | C + N | 1.5 | 6 | — |
| | **Gate 0 subtotal** | | **20.0** | **1–6** | |
| 17 | Client access: credentials, JIT grant, read-only verification, DPA check | **N only** | 2.0 | 7–8 | Nothing here is technical; it is access, legal, and relationship work |
| 18 | Manifest authoring for the dealership source | N + C | 1.5 | 7–8 | Column mapping requires knowing what the DMS fields actually mean |
| 19 | `client/tekbas` pack — rules from real data | **N decides**, C writes | 2.0 | 8 | Only Nazif can say whether a discovered constraint is a real business rule |
| 20 | Discovery run + Readiness Report delivery | C + N | 1.0 | 8–9 | — |
| 21 | Client review cycle | **N** | 1.0 active | 9–10 | Calendar-heavy, effort-light — mostly waiting |
| 22 | Remediation, metrics capture, Gate 1 close | C + N | 2.5 | 10 | — |
| | **Gate 1 subtotal** | | **10.0** | **7–10** | |
| | **Total** | | **30.0** | | |

---

## 3. Off-the-shelf components

All wrapped through `kernel/adapters/`, never imported directly into stage logic (§0).

| Function | Component | Licence | Cost | Risk to watch |
|---|---|---|---|---|
| Validation engine | GX Core | Apache 2.0 | $0 | Now under Fivetran stewardship; GX Cloud is discontinued. **Adapter must pin the narrowest result format** — default output includes sample unexpected values (§8) |
| Entity resolution | Splink | MIT | $0 | Low. Explainable and court-defensible, which is why it was chosen over Tamr/Senzing |
| PII detection / de-identification | Presidio | MIT | $0 | Low. Turkish recognizers are thin — expect to add TCKN/VKN patterns |
| Execution engine | Polars + DuckDB | MIT | $0 | Single-node ceiling; push-down profiling is the Phase 2 relief valve |
| Schemas | Pydantic | MIT | $0 | Low |
| CLI | Typer | MIT | $0 | Low |
| Testing | pytest + Hypothesis | MIT / MPL 2.0 | $0 | Low |
| Supply chain (Phase 1) | cosign, syft | Apache 2.0 | $0 | Free, but the process cost is non-trivial |
| Discovery workstation | OpenRefine | BSD-3 | $0 | **Never in the delivery path.** Operation history compiles into a draft pack; the pack executes |
| Constraint suggestion (Phase 2) | Deequ-style | Apache 2.0 | $0 | Requires Spark — may be reimplemented rather than wrapped |

**What is deliberately not bought:** any commercial DQ platform. The comparison work established that the enterprise suites cannot be priced into engagements of this size, and that the differentiating layers — trust boundary, Turkish locale, signed rule lifecycle — are not available from any of them at any price.

---

## 4. Cash detail

| Line | Monthly | Note |
|---|---|---|
| Private container registry | ~$0–5 | GHCR; free for public repos |
| CI minutes | $0 | GitHub Actions free tier is sufficient at this scale |
| Test VM (Gate 0 environment) | ~$20–40 | Can be dropped between phases |
| Model API — discovery Layer D | ~$20–50 | Sees profile statistics and synthetic examples only, never data, so volume stays small |
| Dev compute | $0 | Existing machines |
| **Total** | **~$50–100** | Over ten weeks: roughly $150–250 all-in |

---

## 5. Not in this plan

Named explicitly so they do not get absorbed by accident:

- **SOC 2 / ISO 27001.** Identified as the top blocker for security-conscious clients. Real cash cost in the tens of thousands and months of calendar. Needed before the Picus-class conversation, not before Gate 1.
- **Review UI (Phase 1).** The static in-boundary HTML review artifact. Gate 1 runs on CLI plus report.
- **Sustain mode / continuous operation (Phase 3).** The 24/7 single-client system is a separate build with its own plan and its own trigger.
- **Supply-chain attestation (Phase 1).** Cheap in effort, but correctly placed after Gate 0 — signing infrastructure for a synthetic-data build is premature.
- **In-boundary local LLM (Phase 2).** Gated on an aerospace or public-sector engagement.

---

## 6. Where this estimate is most likely wrong

1. **`tr-core` edge cases (item 9) can double.** Two days assumes the six normalizers behave. Turkish casing interacts badly with almost everything, and real dealer data will surface combinations nobody documents. If this item runs to four days it is not a planning failure — it is the item earning its place as the moat.
2. **Gate 1 calendar is client-governed, not effort-governed.** Item 21 is one day of effort spread across two weeks of waiting. If the client's review takes a month, the calendar slips without a single extra person-day being spent. Do not compress the plan by assuming a fast turnaround.
3. **Item 17 could stall entirely.** Credential provisioning, JIT setup, and DPA confirmation depend on people outside both MAXENG and this plan. Start it in week 5, in parallel with Gate 0 — it is the only item worth beginning early.
4. **The original spec estimated Gate 0 at two weeks.** That was written before v0.4 added Bronze, write-audit-publish, two arming modes, two leak tests, and the registries. The scope roughly doubled, and the estimate here reflects the hardened spec rather than the original one. This is a correction, not a slip.
5. **Three days a week is an assumption.** At two days a week the calendar becomes fifteen weeks. At five it becomes six — but five days a week on this means violating the three-initiative ceiling, which has its own cost elsewhere.
