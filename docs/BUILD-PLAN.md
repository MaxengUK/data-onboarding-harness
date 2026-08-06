# BUILD PLAN — Harness v0.4.0 → Gate 1

**Reflects:** `CLAUDE.md` v0.6.3 · last reviewed August 2026 · see `ROADMAP.md` and `STATUS.md`
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
| 3a | **Canonical schema artifact + narrow resolver + semantic type binding chain** | C + **N decides the schemas** | 1.5 | 2 | ✅ Built. `canonical/` ships `energy/generation_v1` and `automotive/sales_v2` as first drafts — **the field lists, the semantic type assignments and the three open questions in STATUS §5b.4 still need Nazif**, which is the part of this estimate that has not been spent. The energy entity was already renamed once (`plant_code` → `measurement_point_id`), which is the shape of correction this review is for |
| 3b | Predicate registry (14 predicates) + §7.2 rule schema | C + N decides list | 0.5 | 2 | ✅ Built, then reviewed — see STATUS §5c.3, which added `key_is_unique` and made three hidden policies into mandatory parameters. **The predicate list and the pattern list still need Nazif's review** — which predicates exist bounds what a rule can say, and the patterns are the kernel's only executable content |
| 4 | Bronze store — partitioning, immutability enforcement, pre-image lookup | C | 1.5 | 2–3 | Storage substrate decision (Postgres / DuckDB / object store) |
| 5 | Preflight — framework, digest, CLI, and the checks today's capabilities allow | C + N reviews | 1.0 | 3 | ◐ **Framed: 18 of 30 checks live.** Revised down from 2.0 — severities are pinned to §6.2.2 and are *not* per-client, so the budgeted severity negotiation does not happen. What remains is reviewing the Preflight Report as a client-facing artifact |
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

Item 3's re-pricing and item 5's cancel out, so the totals are unchanged. That is a real result rather than a rounding: the day did not vanish, it moved from a severity negotiation that turned out not to exist into a canonical schema artifact nobody had costed.

**Caveat on what this column measures.** These are *Nazif days* — judgment and access, not implementation. §2.1 attaches preflight checks to later items, and most of that work is Claude-time, which this table has never tracked. Read the additions below as scope, not as budget.

---

## 2.1 Preflight checks are a tax on capability items, not an item of their own

**Rule: an item that brings a capability also brings the preflight checks that depend on it.** There is no "finish preflight" item, and there must not be one.

The reason is what happens if there were. A capability lands, its check does not, and the check sits `unavailable` until somebody works through a backlog of them — which means every intervening run is blocked by a check whose enabling capability already exists, and the pressure to relax "unavailable blocks" comes from a real inconvenience the plan created. A backlog item would also be the easiest thing in the plan to defer, and deferring it would silently widen the gap between what the Harness *can* verify and what it *does*.

So the unimplemented checks are distributed. Each is named against the item that makes it possible:

| Item | Preflight checks it must close | Why it is that item |
|---|---|---|
| **3a** ✅ | `schema.canonical_schema_resolves` (new), `schema.declared_key_present`, `volume.max_timestamp_within_freshness_window` | Closed. The freshness one was not obvious: "newest record inside the window" cannot run until something says *which* field carries time. `schema.types_match_semantic_types` turned out **not applicable** to a file binding rather than opened — a CSV declares no types, and shape-versus-type is discovery Layer A's check, not preflight's |
| **3b** ✅ | `packs.predicates_exist_in_registry`, `packs.semantic_types_resolve` | Built, and **vacuous-pass rather than closed**, as predicted: with no pack loader there are no rules to inspect, so both pass on an empty pack list and go `unavailable` the moment item 9 declares one. The resolution logic underneath is real and tested directly with constructed rules — item 9 calls these functions, it does not write them |
| **7** (walking skeleton) | `connectivity.target_writable`, `volume.no_truncated_extract`, `capacity.space_for_output_and_quarantine`, `capacity.egress_allowlist_pinned`, `capacity.kill_switch_reachable` | The skeleton brings the target adapter, `ingest`, and the §6.3 publication boundary the kill switch is defined against. Five checks arrive with one item because one item finally gives the pipeline an output end |
| **9** (`tr-core`) | `encoding.locale_matches_observed_shapes`, `schema.no_undeclared_pii_column`, plus **re-closing all three pack checks** and the Turkish entries in `PatternName` | Both are locale knowledge. Writing either before `tr-core` exists would put Turkish shapes in the kernel and break P3 — the shape detectors currently in `kernel/gates/guard.py` are already a known instance of that defect |
| **17** (client access) | `connectivity.principal_is_read_only`, `connectivity.grants_match_declared_scope`, `connectivity.credential_expiry_exceeds_run`, `governance.subprocessor_register_current` | Three need a real bound credential to inspect; the fourth needs a maintained `SUBPROCESSORS.md` (§17). All four are access and legal work, which is what item 17 already is |
| **19** (`client/tekbas`) | `packs.no_pass_through_above_client_layer`, and the vacuity below | The first engagement to declare an external reference is the first one where `license_mode` and layer placement can be checked at all (§9.6) |

**Two checks pass vacuously today and will start blocking — by design, and it will look like a regression.** `packs.declared_packs_resolvable` and `governance.external_references_declare_license_mode` both pass on an empty list. The moment item 9 declares `core/tr-core@^1.4`, or item 19 declares Cardata, the vacuity ends and the check goes `unavailable` until a pack loader and a reference adapter exist.

That is the correct behaviour and it is worth writing down, because the day it happens the natural reading is "preflight broke". It did not: a manifest that declares something now has something to verify. **Item 9 must therefore bring the §7.4 pack loader, and item 19 the `references/` adapter** — they are not optional extras attached to those items, they are the price of declaring a pack or a reference at all.

**A source adapter is the one capability with no item.** `connectivity.source_reachable` and `encoding.collation_consistent` have database forms that need a driver-backed adapter, and no item in this plan brings one — item 18 authors a manifest for the dealership source but does not build the thing that reads it. Gate 0 is file-bound so it does not bite there. Before item 18 starts, either the adapter gets an item or the dealership extract arrives as a file; deciding that late is how a Gate 1 week disappears.

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
4. **Item 3 was mis-scoped, and the correction is instructive.** It read as "two registries, both enum lists" and was priced at one day. One of them *is* that — the predicate registry (3b) lands close to the original estimate. The other was never a registry: binding a semantic type to a column requires an artifact that did not exist in the plan at all. `column_map` maps a source name to a canonical field name, and nothing said what a canonical field *is*, so §7.5's "rules bind to semantic types" had no chain to travel and §13's `reuse_ratio` had nothing to measure. Preflight is what surfaced it — three of its checks stopped at the same missing link. **Look for this shape elsewhere: a plan item named after the thing you can see, hiding the artifact it silently assumes.**
5. **The original spec estimated Gate 0 at two weeks.** That was written before v0.4 added Bronze, write-audit-publish, two arming modes, two leak tests, and the registries. The scope roughly doubled, and the estimate here reflects the hardened spec rather than the original one. This is a correction, not a slip.
6. **Three days a week is an assumption.** At two days a week the calendar becomes fifteen weeks. At five it becomes six — but five days a week on this means violating the three-initiative ceiling, which has its own cost elsewhere.
