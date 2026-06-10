# Closed-loop framework → repo parity plan

**Status date:** 2026-06-10 (written at the end of the wave-1 kickoff session)
**Framework:** `docs/closed-loop-implementation-list.md` (CL-01..26, AM-01..12, RB-01..07, DF-01..10, PC-01..04, FR-01..04, GR-01..06, CR-01..03)
**Ground truth for current state:** the 10-agent reconciliation sweep (2026-06-10), every claim
verified by file reads against branch `claude/closed-loop-wave1`. Matrix totals: **2 exists /
47 partial / 40 missing / 5 conflict** across ~95 items. This file is the working plan of
record for reaching parity; CLAUDE.md carries only the pointer.

---

## 1. Decisions locked (owner, 2026-06-10) — cite these, do not re-ask

| # | Decision | Resolution |
|---|---|---|
| 1a | Corpus location | `corpus/` at repo root: `staging/` (agent-writable) + `promoted/` (human-only) |
| 1b | Branch topology | PRs everywhere, path-gated: CODEOWNERS on `corpus/promoted/**`, `cec-policy.json`, `tests/golden/**`, `corpus/SCHEMA.md`; staging-only PRs merge review-free |
| 2 | Migration disposition | ALL entries to staging (263 = 5 general + 258 extracted); nothing grandfathered; owner re-sign pass promotes |
| 4 | Golden venue | In-container (`cec/routing:kicad10`) — the SB-08 decision, already recorded in `cec_golden.py` |
| 5 | M2.7 license | **CLEARED** by owner ("M2.7 clears, do not worry about that") → `license_cleared: true`; M2.7 is the analyst/deep-auditor binding |
| 10 | Night venue (AM-07) | WSL2 + routing container on this box (de facto proven: broker systemd unit, overnight ran here) |
| 18 | Router migration timing | Baseline banked on pinned 1.7.0 (the 2026-06-09 63-route night WAS the baseline); FR-01 → 2.2.4 later as a clean AM-03 epoch event |

**Still open (ask before building the dependent item):** 3 (queue substrate — SB-02's design
leaned GitHub Issues; confirm at CL-07), 6 (deep-path budgets), 7 (verdict schema lock — owner
review required BEFORE agents code against CL-12), 8 (panel cadence/seats — API spend), 9
(swarm charters/budget/precision floor), 11 (frontier data egress), 12 (owner bandwidth/WIP
caps), 13 (second forensics reader), 14 (probe opt-in), 15 (vindication weights), 16
(process-corpus custody), 17 (generative-training moratorium), 19 (plan-stage depth), 20
(topological climb gate), 21 (registry ratification).

## 2. Conflict resolutions (framework doc vs measured tree — reality won)

1. **Lifecycle vocabulary (CL-01):** SB-13 `status` lifecycle KEPT (`proposed → sim_validated
   → bringup_validated | human_approved → deprecated`); framework `promoted` ≡
   `human_approved` + `signoff` + residence in `promoted/`. See `corpus/SCHEMA.md`.
2. **Class letters (CL-06):** as-built taxonomy kept — **A = external standard, B =
   spec-derived** (doc had them inverted). The spec-line-resolution / spec-first rule binds to
   **Class B** and is lint-enforced at promotion.
3. **Dual-target compilation (CL-03):** Freerouting provably ignores netclass widths
   (CLAUDE.md measured finding). The "enforce at the earliest expressible stage" principle
   (RB-02) survives, but the router-stage target is the **post-route copper synthesizer
   (`cec_fr.synthesize_power_copper` / `add_power_pours`) + DRC**, never router-consumed
   netclasses. The pushdown table must encode this.
4. **CL-26 minimal viable night: DONE.** The 2026-06-09 overnight (63 routes, both PCIe kelvin
   findings, stage timings in manifest/ledger) was it, on pinned FR 1.7.0. Measured stage
   costs exist; the budget allocator reads them, not estimates.
5. **DF-10 determinism probes:** deep tiers are stochastic BY DESIGN (M2.7 sampling floors are
   a bench-verified safety rule). Byte-identity probes apply only to temp-0 seats; sampling
   params join the manifest; tempered seats get variance-bounding probes instead.
6. **Model bindings (CL-14/17/20):** ceiling is **125 GB RAM** (measured; 192 GB is the
   physical-box spec, not the WSL2 runtime). Analyst = **MiniMax-M2.7** (102 GB, fits, license
   cleared, miner→scribe + floors already productionized). Qwen3.5-397B is dead (would not be
   RAM-resident). Reviewer = gpt-oss-120b (bench verdict, PR #26). In-loop manager stays
   worker-class (broker-swap thrash otherwise). Worker residency numbers come from
   `models.json` (27/22 GB), not the doc's estimates.
7. **Landing-point drift:** `cec_hc.py` is the high-current ROUTING toolkit, not a check pack
   — CL-25 extends `cec_constraints.py` + the `cec_synth_pipeline` stage lists.
   `cec_dispatch where="runner"` is the LOCAL slot pool; the GitHub-dispatch leg is still
   punchlist R-12. No DSN parser exists (FR-02's "one s-expr edit" needs new code). No
   netclass-conformance check exists yet (CL-11's via golden depends on CL-25 building it).

## 3. Landed tonight (branch `claude/closed-loop-wave1`, stacked on PR #26)

- **CL-01 (core):** two-zone split live; `corpus/SCHEMA.md` (reconciled schema: signoff/
  promotion/fixture/scope blocks, zone rules); one-shot `scripts/cec_corpus_migrate.py` RUN:
  263 entries → `corpus/staging/{general,extracted}/`, `promoted/` empty by design; legacy
  locations removed.
- **CL-02 (server half):** `.github/CODEOWNERS` + branch protection **LIVE on main** (require
  PR; approvals 0; code-owner review ⇒ owner approval required exactly when owned paths are
  touched; dismiss-stale; last-push-approval). Verified via API response.
- **CL-03/05/06 (lint slice):** `cec_corpus_lint.py` rewritten zone-aware: promotion rules
  (human_approved + signoff; extracted rows must carry the full schema upgrade; Class B needs
  resolving spec source), cross-zone duplicate-id, `conflicts_with` promotion blockers, AM-02
  fixture rule (error for new entries, warn for migrated), legacy-location errors. 0 errors /
  268 designed warnings on the migrated tree; `checklist.sh` green.
- **Ledger:** `constraint_corpus_sha256` now hashes the whole corpus tree (the AM-03 epoch
  key); legacy hash kept for pre-migration checkouts.
- **Framework doc vendored** at `docs/closed-loop-implementation-list.md`.
- **Context from earlier same-day work:** PR #26 (manager-tier wiring: REVIEWER default
  cec-manager-fast, miner→scribe, sampling floors, broker-native overnight) — OPEN, merge
  first. VLM scouting complete + downloads (see §6).

## 4. Remaining work to parity, by wave

### Wave 1 remainder — LANDED 2026-06-10 (the enforcement + capture skeletons)
Done this session (dependency-free, host- AND container-runnable, `checklist.sh` green):
- **CL-10** `cec-policy.json` (CODEOWNERS-gated) + `scripts/cec_policy.py` loader. Roles +
  bindings with MEASURED residency (worker 27 / worker-quality 22 / reviewer-fast 9+60 /
  analyst M2.7 28+96 GB), `license_cleared` (M2.7 true), eval-gate status (extractor/verifier/
  frontier/vision-judge marked **non-load-bearing** until their gates exist — that is how an
  unbuilt seat avoids refusing the night). Three load-time guards: (1) a *load-bearing* binding
  with `license_cleared:false` or a failed/absent gate **refuses load**; (2) the DF-05/07
  anti-ratchet firewall — `scan_banned()` walks the whole policy (skipping its own denylist) and
  any external reward/revision config, equality-on-normalized-token (not substring, so prose is
  not a false positive) over {acceptance, promotion-likelihood, consensus-agreement,
  finding-volume, token-thrift-primary}; (3) `clamp()` keeps a nightly allocation inside
  `bandit_bounds` and logs every clamp to the ledger (`mode=policy-clamp`) — the loop can never
  widen a bound. `policy_sha256()` is the value stamped into every manifest.
- **DF-01/DF-06 + PC-01** in `cec_ledger.py`: `decision()` record (class from the closed DF-01
  taxonomy, artifact, decider+manifest, evidence_bundle_hash, cited_reasons, counterfactual,
  ambient covariates, DF-02 blinded_view, policy_sha256) **+ the DF-06 three: machine-readable
  `claim`, closed-vocab `hook` {check_id|fixture|bench|span_match|golden|future_event}, and
  `settlement` {state, grade 1/2/3}**. PC-01 capture criterion: `settleable = claim AND hook`
  → `capture: full`, else `counter-eligible` (a claim without a hook is legal and scores zero).
  `settle()`/`label` are append-only DF-07 updates (`settles:` pointer; `label` = a CL-13
  physical outcome → Grade-1 settle). **AM-06** sharding: `counter()` streams claimless
  high-volume micro-decisions to per-stream sidecars (`decisions/counters/<stream>.jsonl`),
  single-writer by append, never polluting the main decision stream. CLI: `decision`/`settle`/
  `label`.
- **CR-01/CR-03 registry** = the `registry` section of `cec-policy.json`: per-tier (routing/
  placement/scoring/review/corpus) frozen vs owned split, CR-02 rungs, `current_rung`,
  climb-gate metric, exit condition; `ratified:false` pending **Decision 21** (present the table
  for owner sign-off). CR-03 adoption protocol (manifest → replay over settled history + the
  quarantined reality cases → control arm → full budget only on settled vindication) as a
  standing policy block.
- Tests: `tests/test_cec_policy.py` (15) + `tests/test_ledger_decision.py` (10) — 25 green on
  the host. `cec_policy validate` wired into `checklist.sh`.

Still open in wave 1 (owner action): **CL-02 owner half** — create the agent machine account
(no approval rights), move night-box auth off the owner identity, then the RB-04 weekly
credential/permission audit script. Until the machine account exists the CL-02 gate is
documentation (RB-04 finding, noted in CODEOWNERS).

<details><summary>Original wave-1-remainder spec (for reference)</summary>

- **CL-10 `cec-policy.json` + `scripts/cec_policy.py` loader:** role contracts
  (worker/verifier/extractor/manager/reviewer/analyst/judge/frontier + `modality` field per
  CL-22), bindings with MEASURED residency (worker 27, worker-quality 22, manager-fast 9 GB
  VRAM / 60 GB RAM, M2.7 28/96), `license_cleared` (M2.7 true, owner 2026-06-10), eval-gate
  status (extractor: ABSENT until CL-19), per-night budgets (Decision 6 placeholders, clamped),
  bandit bounds, prompt hashes, policy_version. Loader assertions: refuse load-bearing binding
  with failed/absent eval gate or `license_cleared:false`; refuse any reward/revision config
  referencing banned fields (DF-05/07 list: acceptance-rate, promotion-likelihood, consensus-
  agreement, finding-volume, token-thrift-primary); bound-clamp helper with ledger log.
- **DF-01/DF-06 capture schema (cannot be retroactive):** `cec_ledger.py` `decision` record
  (decision_class, artifact, decider manifest incl. sampling params, evidence_bundle_hash,
  verdict, cited_reasons, counterfactual stub, claim, verification_hook, settlement{state,
  grade}) + `label` CLI (CL-13 schema rides this) + AM-06 sharding (high-volume streams to
  sidecars, hashes in ledger, single-writer rule).
- **PC-01 capture criterion** (full records iff settleable claim; counters otherwise) — lands
  inside the DF-06 schema.
- **CR-01/CR-03 registry:** policy section enumerating each tier's frozen/owned split, rungs
  (CR-02 ladders), current rung, climb gate, exit condition; adoption protocol as a standing
  policy assertion. Decision 21 ratifies the initial rungs — present as a table for sign-off.
- **CL-02 (owner half):** create the agent machine account (no approval rights); move night-box
  auth off the owner identity; then the RB-04 audit script (weekly credential/permission report).

</details>

### Wave 2 (protective checks — buildable today from the two audits)
- **CL-25 audit check pack + intake gate: LANDED 2026-06-10.** The six classes as stable IDs
  (`cec_constraints.CL25_CLASSES`): three NEW checkers — `netclass-geometry-conformance`
  (per-net track/via vs `.kicad_pro` class minima; Kelvin-stub track exemption on shared
  force+sense nets, same split as `derive_cross_section_dru`; vias always checked — **fires
  on the committed 12VHPWR**, the audit's lane-via pre-fix state, so the CL-11 via golden is
  unblocked), `bom-field-lint` (placeholder/empty patterns; OQ-11/THT known-open gaps noted
  not failed), `sch-pcb-sync` (instance-ref set diff with lib_symbols excision + board-only
  ref exclusion; freshness in detail) — and three mapped to pre-existing checkers (thermal
  keep-apart, cap-to-node, netlist assertions). `intake_gate()` runs the schematic-side
  subset + live severity-ERROR ERC (benign-filtered; DRAFT boards skip per repo convention)
  and is wired into `cec_router.route()` — refusal raises with NAMED reasons, ledger-logged
  (`mode=intake`), `CEC_SKIP_INTAKE=1` overrides. CLI: `cec_constraints.py <board> --intake`.
  Also: `detect-resistor-code` taught the Hub posture (≥2 RJ-45/DETECT ⇒ expect the §2.3
  10k pull-ups, not the module code value — was a false-fail on Hub Standard); synth-pipeline
  DFM stage gained `netclass_geometry` (delegating Check). Verified in-container: EPS ADMIT
  (DRAFT ERC-skip), Hub ADMIT (honest — its refs ARE in sync; the CLAUDE.md J7-pending
  narrative was stale), 12VHPWR netclass fire, cross-wired-sch refusal with named reasons;
  10 tests (`tests/test_cl25_checks.py`); SB-08 golden PASS post-change.
- **CL-11 golden seeding: LANDED 2026-06-10.** Four frozen fixtures under
  `tests/golden/fixtures/` (owner-gated path): `12vhpwr-pre-lanevias` = the committed board
  (still carries the audit's signal-size lane vias; measured 240 via-dimension hits on
  `/SENSEP*`, band floor 100), `12vhpwr-post-lanevias` = derived known-good (337 vias
  normalized to class minima via `cec_golden_fixtures.py --freeze`; invariant: ZERO via hits
  anywhere, while track hits remain by design — net-scoped assertions ride the new checker
  payload), `hub-pre/post-tps2121` = git `a271253~1`/`a271253` schematics (the four-resistor
  R15–R18 divider commit) with the **expected-fail marker** on pre (the TPS2121 Class B
  entry doesn't exist; the gap reports VISIBLY, and the runner FAILS the day a bound check
  starts firing, forcing the marker flip per AM-02). Runner `scripts/cec_golden_fixtures.py`
  (verify = CI gate; `--freeze` = derived-fixture regeneration, owner-reviewed); manifest
  `tests/golden/fixtures.json`. CI: new kicad-checks.yml step running the verifier inside
  the pinned KiCad image (pcbnew), unconditional (superset of the framework's path scope).
  Holdout split: `tests/holdout/` created with the never-tune rules — grown from adjudicated
  overrides/bench labels, thin-is-honest. Teeth verified in-container (swapped post-fixture
  → FAIL exit 1); 8 host tests (`tests/test_golden_fixtures.py`).
- **CL-19 extractor fidelity eval:** (trace, gold) pairs seeded from the two audits; span
  existence 100%, zero hallucinated verdicts; gates the extractor binding in policy (CI <1 min).
- **CL-03 compiler (full):** corpus→artifact compilation from promoted entries only
  (`.kicad_dru` fragments, netlist assertions, keep-apart tables, scorer limits) + staging→
  `ADV-` advisory set wired through the cascade with `human_signoff` exclusion + RB-02
  pushdown table (generated, fixture-validated per target, FR-fact-aware per §2.3).
  Includes deciding how the hand-maintained registry derives from / reconciles with promoted
  entries — flag to owner if any registry rule lacks a promotable source.
- **AM-04 analytic FEM anchors:** IPC-2152 trace-heating + closed-form 1D conduction goldens;
  FEM scores marked `uncalibrated` in every bundle until a CL-13 bench label exists. (Also
  carries the SB-08 golden's known model-debt note: segment-sum cross-section optimism.)

### Wave 3 (the loop — orchestrator, attribution, bundle)
- **CL-07 orchestrator** (`scripts/cec_orchestrator.py`): phase scheduler over the existing
  cascade; queue per Decision 3; per-candidate quarantine + watchdog + resume-from-ledger;
  systemd timer (venue = WSL2 per Decision 10); stage wall-times from night one (seed with the
  2026-06-09 measured costs). Note: remote compute leg = punchlist R-12, optional.
- **CL-08 attribution + nested re-entry:** deterministic feature extraction → ordered rules
  (placement fault / relaxed-rules retry before outline growth / routing-rule fault /
  promoted-entry fire) → bandit state in ledger keyed by policy+corpus manifest (AM-03
  epoching); manager narrative is ledger-only. AM-08/RB-06 hypervolume convergence + RB-05
  outcome-space diversity floor ride the allocator.
- **CL-04 shadow mode:** `scripts/cec_shadow.py` per-entry fire aggregation from ledger events;
  promotion-request generator → inbox item (CL-04 ties to Decision 3 queue).
- **CL-12 morning bundle + verdict schema:** **Decision 7 (owner locks fields) BEFORE coding**;
  bundle builder reuses CL-21 renders + CL-23 facts; owner verdict action writes labeled cases
  (SB-09 calibration stream); DF-02 blinded views (promotion view hides drafting tier; verdict
  view — note the dispatch-judge exception recorded in the matrix).
- **CL-23 board-facts serialization** (`scripts/cec_facts.py`): the substrate for swarm/panel/
  intent-compiler; sliceable; hashed into manifests (AM-11 hard token budgets per slice). Most
  fields already derivable from `cec_pcb`/`cec_score`/pcbnew readers.
- **CL-21 render evidence pipeline:** view set (full composites, per-layer SVG, ≥25 px/mm block
  crops, diff renders), net-colorized overlays drawn FROM parsed board data, locating aids
  (grid/refs/region IDs), RB-01 coverage map + unconditional blind share. Bake in the VLM
  research findings: model SELECTS from pre-marked region IDs + pre-computed measurements —
  never emits coordinates; facts JSON rides alongside renders; contradiction with facts ⇒
  hallucination flag.

### Wave 4 (review strata)
- **CL-24 swarm verifier tier:** new `adversarial-verifier` role on the worker; decorrelation
  by input slice/charter/framing; micro-schema findings (no severity/no verification path from
  small models); dedup → deterministic triage → contention = deep-path trigger; per-charter
  precision calibration with suspension floor (Decision 9 sets charters/budget/floor).
- **CL-22 adversarial visual panel:** seats = frontier (Decision 8/11 gate API spend/egress) +
  local VLM (see §6) via the deep path; charters; two-pass blind→context protocol; finding
  contract with falsifiable verification path; triage; golden render eval from CL-11 fixtures
  (REF3030 + lane-vias must fire pre-fix, stay quiet post-fix) gates ANY seat binding.
- **CL-15/16/17 deep path:** analyst(M2.7 free-form, trace ledgered) + extractor(27B, span-
  verified, conclusions-only sourcing + RB-03 ratification fallback) + deterministic span
  verifier; CL-16 triggers (never default) + budgets (Decision 6); CL-17 residency scheduler =
  mostly the broker's existing arbitration + phase windows recorded in manifests.
  Note: `cec_judge_local` already carries the miner→scribe + floors machinery the analyst
  seat needs; `deep_verdict()` composes it with the extractor + span verifier.
- **CL-18 trace-to-corpus rule:** lint already rejects model sources; add `rationale_trace`
  acceptance + the whitelist test from the framework's verify step.

### Wave 5 (forensics analytics, router upgrade, plan/repair ladder)
- **DF-02/03/04/08/09/10 + PC-02/03/04** as decision volume accumulates (Decisions 13–17).
- **FR-01 router migration gate** (jar 2.2.4 by hash; determinism probe; R-01 spread
  revalidation; pour retest on the lane-zone boards; CLI-scoring as stage-0 pre-kill) — an
  AM-03 epoch event; **FR-02 intent compiler** AFTER its gating bench test (locked-stub DSN
  protect attribute survives headless FR — requires writing the DSN-touching code that does
  not exist yet); FR-04 ladder + control arm; FR-03 executor only if waypoints prove
  insufficient (substrate: `cec_route.py` Router primitives).
- **GR-02 deterministic repair battery first** (cheapest win; extends `cec_router.
  targeted_repair` + `MANAGER_REPAIRS`), GR-03 locus agent, GR-01 congestion grid (seed:
  `cec_synth_pipeline.rudy()`), GR-05/06 on evidence (Decisions 19/20).

## 5. Owner action items (cannot be done by agents)
1. **Merge PR #26** (manager-tier wiring), then the wave-1 PR.
2. **Create the agent machine account** + repo collaborator (write, no approval rights); move
   the night-box token to it. Until then the CL-02 gate is documentation (RB-04 finding).
3. **Re-sign pass over staging** (Decision 2): promote what you stand behind — the 5 general
   seeds are `human_approved` awaiting signoff; the 258 extracted rows need class/typed-source
   upgrades at promotion (lint enforces).
4. **Decision 7** (verdict schema lock) before wave-3 CL-12 coding; Decisions 6/8/9/11/12 when
   their waves arrive; Decision 21 registry ratification when CR-01 lands.
5. Optional hardware note: the 125 GB WSL2 ceiling is the binding constraint everywhere; if the
   physical 192 GB is real, raising the WSL2 allocation (.wslconfig) changes the analyst math.

## 6. Vision model (CL-22 local seat) — scouting verdict + state
- **M2.7 is text-only** (confirmed at source) — local panel seat needs a real VLM.
- **Plan:** two-tier — existing workers gain eyes via mmproj (`Qwen3.6-35B-A3B` +
  `Qwen3.6-27B`, ~0.9 GB each, `--mmproj` flag in compose + models.json) as volume
  crop-readers; **Qwen3-VL-32B-Instruct Q4_K_M** (19.8 GB + 1.2 GB mmproj, Apache-2.0, fits
  fully in VRAM) as the grounding-proven judge (RefCOCO-trained box/point; family tops UniPCB,
  the first VLM PCB-inspection benchmark; year-hardened llama.cpp path).
- **Downloads:** running at session end (background wget -c, resumable) into
  `/mnt/e/AI Models/{qwen3.6-35b-a3b,qwen3.6-27b,qwen3-vl-32b}/`. Verify sizes, then register
  in `models.json` (new entries `cec-vision-judge`, mmproj args on the worker entries are a
  compose change behind a profile or env).
- **Bake-off before any binding** (CL-22 eval gate): golden render eval — pre-fix Hub render
  must yield REF3030 adjacency, pre-fix 12VHPWR must yield the lane-via finding, post-fix
  renders stay quiet; open question is early-fusion grounding (no published RefCOCO numbers
  for Qwen3.5/3.6) vs Qwen3-VL — settle on real KiCad crops.
- Deferred (download only on demonstrated judge miss): GLM-4.6V 106B-A12B (MIT, grounding-
  first) and Qwen3.5-122B-A10B (OCRBench 92.1) — both contend with M2.7 page-cache residency.

## 7. Verification state of tonight's pieces
- Migration + zone lint + `checklist.sh`: green (0 errors; 268 designed migration warnings).
- Branch protection: verified live via API response (require PR + code-owner reviews).
- NOT yet run post-corpus-move: in-container golden (`cec_golden.py`) — the corpus hash change
  touches the ledger manifest only, but run it before merging the wave-1 PR per the SB-08 rule
  (`scripts/**` changed).
- The 263-entry staging tree carries zero fixtures (AM-02 warnings) — fixture authoring is
  part of the re-sign/promotion flow, not a blocker.
