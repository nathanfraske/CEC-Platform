# Prompt-tier audit — IMPLEMENTATION PUNCHLIST (2026-06-13)

Source findings: `claude-panel-report.md` (30 confirmed / 3 rejected) + `v4-findings.json`
(DeepSeek-V4 cross-check — folded in below once it lands). Catalog of every audited
prompt: `catalog.md`.

**Scope note (read first).** Every item here is a **prompt-construction / loop-plumbing**
change — none touches a locked decision, a ratified constraint, the spec, or board copper,
so none crosses the human-ratification boundary. BUT several change *what the EI-02 seats
see* (T1 prompt, control-lane carry-forward, CORPUS_BRIEF scope). EI-02 is a **live
measurement instrument** with a committed prereg (PP-06). Therefore: **land these as one
batch, then re-establish the A/B baseline** with a fresh lane-tagged run before trusting any
new lift number. The pre-fix ei02verify run (drc_mean aug 22.0 / ctrl 9.67; 0 deltas applied)
is the "before" snapshot. Flagged per-item as `REBASELINE: yes/no`.

Legend: **Sev** H/M/L (verifier-corrected grade) · **Retires** = other findings this item
closes · **Effort** S/M/L · **Status** ☐ todo.

---

## IMPLEMENTATION STATUS — 2026-06-13 (turn 1)

**DONE + host-tested** (`tests/test_prompt_audit_fixes.py` 4/4; existing EI-02/EI-01/auditor/reason suites still green; `py_compile` clean):
- **P1a** `board_manifest()` in-container helper (`cec_fullstack.py`, after `congestion_grid`).
- **P1b/d/e** T1 prompt rewritten: injects the ref inventory (`ref@(x,y)[val]`) + net→refs, the SENSE
  CORRIDOR (from the fenced sense refs), grounds the waypoint examples in real refs, labels the
  `contested` net list as the actionable signal. Manifest wired into `run()` + the T1 call.
- **P2** fence stated in the T1 prompt + a generation-path drop guard (fenced-net intents and
  all-fenced-ref waypoints dropped, logged not silent).
- **P3** EI-02 lane-gated carry-forward (`intents_aug` updated on augmented rounds only; control
  rounds seed from `ovd.INTENTS[board]`) — the A/B-integrity fix.
- **P4** CL24 spec charter fed `CORPUS_BRIEF` + `LOCKED_DECISIONS_BRIEF` + the fence; manager_rules
  relabeled "unratified."
- **P5e** "CONSOLIDATION" defined at the rule cap. **P9** T1 `temperature=0.0` + `nothink=True`.
- **P10** actuation-space charter told which levers have effectors. **P12** T8 explicit decline criteria.
- **P1c** (owner D1 = drop + re-prompt): unknown-net/ref intents dropped + recorded; the dropped tokens
  feed the next augmented round's prompt ("do NOT use these again"). Control lane stays pristine.
- **P7a/b** (owner D2 = in-family only): generation seats (T1/T4) get an in-family-only `CORPUS_BRIEF_GEN`;
  the full brief stays on the auditor (T5/T8). Brief now orders in-family first so truncation drops the
  off-family tail. (Owner D3 = batch + re-baseline run after all code lands.)

**WITHDRAWN — false positives found while implementing against source (NOT bugs):**
- **P8 (M7)** — `coverage_note` is an INPUT payload field (`cec_judge_local.py:1279`, computed by
  `cf_budget_exemplars`), not a requested output; the prose tells the seat to USE it. No schema mismatch.
- **P11b (V4[10])** — the fullstack narrate seat is deliberately NOT fed the numeric facts (CL-21,
  `cec_vision_narrate.py:15-17`); "facts-alongside" is the judge/bakeoff path, not narrate. Nothing to defer to.
- **P11c (V4[9])** — the narrate prompt ALREADY states the advisory role ("You are NOT a judge… Do
  NOT output any pass/fail, intact/clipped, or count", `cec_vision_narrate.py:45-47`).

**REMAINING — decision-INDEPENDENT (next turn; sequenced for review-sized batches):**
- **P5a** auditor prompt reorder (lead with `failure_class` actuation; demote `proposed_lever`).
- **P5b** validate/coerce the cloud (Sonnet) auditor output vs `AUDIT_SCHEMA`.
- **P5c** role-define `verdict` (or drop). **P5d** advertise `_PENALTY_METRIC` + make `inject()` reject non-priceable metrics.
- **P6a-f** T4 panel redesign (per-lens rules, progress cross-round delta, plane-integrity reframe,
  name the `action` field, escalate calibration, finishing-lens DRC loci).
- **P7c** round-task-ahead-of-brief ordering (minor). **P11a** net/ref per diff-region (latent — only
  fires on reference boards; eps-8pin has none).

**DECISIONS RESOLVED (owner, 2026-06-13):** D1 = drop + re-prompt (P1c, done) · D2 = in-family only
(P7a/b, done) · D3 = batch + re-baseline run (pending — after P5/P6 land, run one fresh lane-tagged
`cec_fullstack`, compare A/B to the pre-fix snapshot, annotate PP-06 that the instrument changed).

---

## P1 — T1 board manifest + emit-time ref/net validation  ☐
**Sev H · Retires H1, M1, M2 · Effort M · REBASELINE: yes**

The keystone fix (the U5 root cause). One new in-container helper feeds three grounding gaps.

- **P1a — manifest builder.** New helper (sibling to `cec_fr02._fp_center`, or in
  `cec_fullstack`) that, once per round/run in-container, dumps from `board.GetFootprints()`:
  `[{ref, value/role, x_mm, y_mm}]` for routing-relevant parts (connectors, ESP, CAN xcvr,
  shunts, sense ICs), the **net→endpoint-ref map** for the contested nets, and the board
  outline bbox. Reuse the pcbnew access `pour_facts`/`congestion_grid` already open.
  - files: `scripts/cec_fr02.py` (or `scripts/cec_fullstack.py`), called from `run()` near grid build.
- **P1b — inject into T1 prompt.** Add the manifest to `intent_manager`'s user prompt; replace
  the bare `U2`/`U1` examples with refs drawn from the real inventory.
  - files: `scripts/cec_fullstack.py:698-709`.
- **P1c — validate at emit (no more silent drop).** In `intent_manager()` (`:716`), reject any
  intent whose `net`/`ref`/`between` is not in the manifest; log the drop; and feed an
  explicit "unknown-ref dropped: …" line into NEXT round's prompt so the seat self-corrects.
  Decision: post-resolve validation (preferred) **vs** schema `enum` populated from the
  manifest. Recommend validation — a per-board enum bloats `INTENTS_SCHEMA` and the grammar.
  - files: `scripts/cec_fullstack.py:716`; optionally pass manifest into `cec_fr02.compile_intents`
    so the drop is named there too (`cec_fr02.py:191-193`).
- **P1d (M1) — corridor geometry.** Include the `SENSEC*_HI/_LO` pour bboxes (from `pour_facts`,
  `cec_fullstack.py:507-509`) and/or shunt/INA refs+positions as the labeled keep-out the
  "route AROUND the corridor" instruction refers to.
- **P1e (M2) — hotspots.** Resolve GR-01 hotspot cells to mm centroids + dominant overlapping
  nets/refs before serializing, **or** drop the raw `(i,j,ratio)` index list and pass only the
  net-keyed `contested`/`order` list. (`cec_router.py:1259-1268`.)
- **Test:** host test — manifest builder returns eps-8pin refs `{U1,U2,U3,U10,U11,U20,U21,U30,U31,RS1,RS2,J1,J5,D1,D2}`;
  validation rejects an intent on `U5`/a non-existent net and keeps a valid one. Integration:
  short in-container `cec_fullstack --rounds 2` → grep intents/ for any non-existent ref (expect none).

## P2 — T1 fence awareness  ☐
**Sev H · Effort S · REBASELINE: yes**

The actuator fence (`BOARD_PINNED_REFS['eps-8pin']=('RS1','RS2','U20','U21','U2')` + every
Kelvin net) is enforced on the auditor/V4 delta path but not on T1 generation.
- **P2a** — add a verbatim line to the T1 prompt: `FENCED — never target these nets or anchor to
  these refs: nets=[…kelvin/sense…], refs=[RS1,RS2,U20,U21,U2].` (`cec_fullstack.py:698-709`).
- **P2b** — defensively filter in `intent_manager()` before return (drop intents whose net
  `is_fenced()` / whose `ref ∈ fence['refs']`, logged) **or** pass `fence` into
  `compile_intents` to reject fenced targets like `finding_to_delta` does.
  - files: `scripts/cec_fullstack.py` (fence at `:1077-1090`), `scripts/cec_fs_actuator.py:63,102`,
    `scripts/cec_fr02.py:161-225`.
- **Test:** host — a T1 intent on `/SENSEC2_HI` or anchored to `RS2` is dropped+logged.
- **Dep:** shares the manifest/fence plumbing with P1; do P1 then P2.

## P3 — EI-02 control-lane intent gating  ☐
**Sev H · Retires M15 · Effort S · REBASELINE: yes (this IS the A/B integrity fix)**

`intents` is a single carry-forward var (`cec_fullstack.py:1163`), reassigned unconditionally
(`:1193`) and injected as `LAST ROUND intents` every round regardless of lane — so augmented
waypoints leak into control rounds and bias the lift.
- **Fix:** maintain `intents_aug`/`intents_ctrl` separately, or on a control round pass
  `prev_intents=ovd.INTENTS[board]` (signed seed) and don't let a control round overwrite the
  augmented carry-forward — mirroring `lr_view` blanking (`:1184`).
  - files: `scripts/cec_fullstack.py:1163,1184,1193`, `intent_manager` `:705/709`.
- **Test:** host — `lane_for` + carry-forward: a control round's T1 `prev_intents` excludes the
  prior augmented round's intents. (Pure helper, unit-testable like `lane_for`.)

## P4 — CL24 spec-conformance charter gets REAL ratified knowledge  ☐
**Sev H · Effort S · REBASELINE: no**

`_slice_spec` labels its input "RATIFIED RULES / LOCKED DECISIONS" but the caller feeds
`json.dumps(manager_rules)` (`cec_fullstack.py:1336`) — auto-generated, capped, and **empty on
control rounds** (`empty_corpus` self-tag, `cec_verifier.py:318`).
- **Fix:** build `rules_excerpt` from `CORPUS_BRIEF` + a compact locked-decisions/fence summary
  (pin allocation, RJ-45 lock, Kelvin fence nets+refs, §6.4 shunts) + manager_rules; if
  manager_rules stay, relabel them "in-run standing rules (unratified)" in `_slice_spec`.
  - files: `scripts/cec_fullstack.py:1336`, `scripts/cec_verifier.py:80-82`.
- **Test:** host — `_slice_spec` output contains a locked-decision token (e.g. RJ-45 / a fence
  ref) even on a control round.

## P5 — T5 auditor prompt cleanup (cluster)  ☐
**Sev M · Retires M3, M4, M5, M6 · Effort M · REBASELINE: yes (changes auditor behavior)**

- **P5a (M3)** — lead the prompt with what actuates: `failure_class` drives the loop
  (placement→GR-02; scoring→may price *iff* a gate-passing candidate exists; routing→records
  diagnosis); demote `proposed_lever` to "ADVISORY CONTEXT ONLY — fill briefly." Drop the
  imperative "name THAT lever" for the inert field. (`cec_fullstack.py:795-797,824-828`.)
- **P5b (M4)** — validate the **cloud** auditor file against `AUDIT_SCHEMA` after load; coerce
  missing/invalid `verdict`→`repair` (mirror the deepseek guard `:889`); normalize out-of-enum
  `failure_class` (it drives T0 at `:1371`); show the literal enum sets inline in the cloud
  prompt. (`cec_fullstack.py:847,864`.)
- **P5c (M5)** — drop `verdict` from `AUDIT_SCHEMA` or role-define it (it shares the panel's
  enum but has no effector — anchor-presence only). (`cec_fullstack.py:142,151`.)
- **P5d (M6)** — derive the advertised "Penalisable keys" from `_PENALTY_METRIC` (`:349`), not
  `PENALISABLE` (`:78`); make `inject()` reject metrics absent from `_PENALTY_METRIC` instead of
  logging them `accepted:raised` (`:962,987`); drop `diffpair_unrouted` (never produced here).
- **P5e (V4-NEW, L)** — define "CONSOLIDATION." The prompt says "At the cap propose only a
  CONSOLIDATION or nothing" (`cec_fullstack.py:802-803`) without saying what one is — give a
  one-line definition + example (merge two standing rules into one) so the seat can comply at cap.
- **Test:** host — a cloud-auditor JSON with a bad `failure_class` is coerced; a penalty on
  `gate_fail` is rejected not silently dropped.

## P6 — T4 worker_panel redesign (cluster)  ☐
**Sev M · Retires M8, M9, M10, M11 · Effort M · REBASELINE: yes**

- **P6a** — per-lens rules instead of the shared "accept iff hard gates pass AND lens"
  (`cec_fullstack.py:738-741`): **safety** = gates are already deterministic, don't re-judge;
  given gate state decide repair-vs-escalate. **finishing** = accept iff residual DRC is
  cosmetic-class ("gate state isn't your job"). **progress** = keyed to the objective/drc/effort
  trajectory ACROSS rounds.
- **P6b** — give the **progress** lens the prior 1-2 rounds' `{objective, drc, effort}` (it
  currently gets one round's scalars, `:732-733`, yet is asked to judge improvement).
- **P6c** — drop "plane integrity" from the safety label (determinism owns it) **or** feed
  `det_clipped_nets` + per-net island counts from `pour_facts` framed as facts-to-confirm.
- **P6d** — name the schema field in prose: `reply with field "action": one of accept|repair|escalate`
  (`PANEL_SCHEMA.action` `:188`; currently only the grammar saves it).
- **P6e** — escalate calibration: restrict "escalate if structural" to the safety lens (the
  other two lack geometry/trajectory). (Note: with 3 voters escalate already needs a majority,
  so cost is wasted budget, not a safety regression.)
- **P6f (V4-NEW, M)** — give the **finishing** lens DRC *locations* (not just the count): it is
  asked to judge "dangling copper, cosmetics vs structure" from scalars alone. Feed `drc_loci`
  (already computed by `cec_score.drc_types`/`drc_loci`) so cosmetic-vs-structural is groundable.
- **Test:** host — progress lens prompt includes a cross-round delta block; safety lens prompt
  no longer claims to judge plane integrity from a scalar.

## P7 — CORPUS_BRIEF scoping + relevance-ordered truncation  ☐
**Sev M · Retires M12, M13 · Effort S · REBASELINE: yes (changes T1/T4/T5/T8 context)**

`promoted_corpus_brief` keeps all entries (~83% off-family for eps-8pin), prepended first,
and truncates by filename sort order (`cec_fullstack.py:405-451`).
- **P7a** — for the generation/routing seats (T1/T4) pass only the in-family subset (`n_in`
  already computed), or only entries with empty `scope.families` AND a routing-relevant `kind`
  (layout/plane/keepout/thermal), excluding measurement/judge/conn-rating families.
- **P7b** — order in-family (layout/thermal/keepout first) before truncating; truncate the
  off-family tail; log dropped count + whether any in-family entry was dropped.
- **P7c** — place the round-specific task block ahead of the brief.
- **Test:** host — brief for eps-8pin T1 excludes 12VHPWR/REF3030 off-family entries; a synthetic
  >13k corpus drops off-family first, never an in-family layout rule.
- **Dep:** interacts with P1/P5/P6 (same prompts) — sequence P7 after them to avoid churn.

## P8 — T7 coverage_note schema mismatch  ☐
**Sev M · Effort S · REBASELINE: no**

Prose instructs a `coverage_note` field absent from `CORPUS_FIT_SCHEMA` (`additionalProperties:false`)
→ dead instruction + scribe-path bait. **Fix:** delete the sentence (fold into `confidence`/
`insufficient_precedent`) or add `coverage_note` (string, not required) to the schema.
- files: `scripts/cec_judge_local.py:961,889`.

## P9 — T1 sampling/nothink  ☐
**Sev M · Effort S · REBASELINE: yes (minor)**

T1 runs a thinking model at temp 0.2 on a strict-JSON task, no `nothink`, not in `_FLOOR_MODELS`.
**Fix:** `temperature=0.0` + `nothink=True` (grammar-constrained emit), or add
`cec-worker-vision` to `CEC_VLLM_FLOOR_MODELS`. (`cec_fullstack.py:712-714`, `cec_judge_local.py:117,261`.)

## P10 — CL24 actuation-space charter effector set  ☐
**Sev L · Effort S · REBASELINE: no**

State which `OWNED_LEVERS` actually have effectors this run (`failure_class→GR-02`,
`scorer_penalty`, `manager_rule`) and that `proposed_lever` is recorded-only, so the actuation
question is answerable. (`cec_verifier.py:118-123,92-100`.) *Pairs with P5a.*

## P11 — T6 vision narrate grounding + role/deference  ☐
**Sev L-M · Effort S · REBASELINE: no**

- **P11a (L2)** — when regions are passed, also pass the net/ref each pixel bbox overlaps;
  recognize the region-narration path is unreachable for reference-less boards (eps-8pin) and
  stop the prompt implying region work that never happens. (`scripts/cec_vision_narrate.py:51-65`,
  `cec_fullstack.py:111`.)
- **P11b (V4-NEW, M)** — instruct the VLM to DEFER to the supplied deterministic facts: "only
  flag anomalies NOT already covered by the supplied facts; if a fact states a pour is intact,
  do not flag it broken." The facts-alongside protocol supplies facts but never tells the seat
  to defer to them → false positives. (V4[10].)
- **P11c (V4-NEW, L)** — state the advisory role IN the prompt: "your output is advisory only and
  will not gate/block routing; do not emit a gate decision." (Role is enforced in code but not
  stated to the seat. V4[9].)

## P12 — T8 V4 batch-auditor decline criteria  ☐
**Sev M · Effort S · REBASELINE: no (V4-NEW)**

The batch auditor is "invited to DECLINE (its measured value is restraint)" (`cec_fullstack.py:38-40`,
T8 prompt in `run()`) but the prompt gives no criteria for *when* declining is appropriate → it
may decline too often (skipping useful audits) or too rarely (wasted deep-reason compute).
**Fix:** add explicit decline guidance, e.g. "decline if round metrics are unchanged from prior
rounds, or the board is fully routed with no failures; otherwise audit." (V4[13].)

---

## Recommended sequence (value × safety × dependency)
1. **P1** (U5 root cause; retires M1/M2) — keystone.
2. **P3** (A/B integrity — it biases the EI-02 measurement directly).
3. **P2** (fence safety on the generation path).
4. **P4** (trivial; corpus already loaded).
5. **P5**, **P6** (auditor + panel clusters; incl. V4-new P5e/P6f).
6. **P7** (context scoping — after the prompt edits settle).
7. **P8, P9, P10, P11, P12** (small finishers; P11/P12 are V4-new).
8. **Re-baseline:** one fresh lane-tagged `cec_fullstack` run; compare A/B to the pre-fix
   snapshot; confirm zero hallucinated refs in intents/, control rounds carry seed intents,
   and CL24 spec charter sees ratified tokens. Update PP-06 prereg note that the instrument changed.

## Cross-cutting tests to add (host, no broker/container)
- `tests/test_prompt_audit_fixes.py`: manifest builder (P1a), ref/net validation rejects U5 (P1c),
  fence filter (P2), control-lane carry-forward gating (P3), `_slice_spec` ratified content (P4),
  cloud-auditor coercion + penalty rejection (P5b/P5d), CORPUS_BRIEF off-family drop + truncation
  order (P7). Then run the existing suite + `cec_corpus_lint` + SB-08 golden in-container.

## Open decisions for the owner (none block planning)
- **D1:** ref validation = post-resolve drop+re-prompt (recommended) vs schema enum. (P1c)
- **D2:** CORPUS_BRIEF for generation seats = in-family only (recommended) vs in-family +
  routing-relevant-platform-wide. (P7a)
- **D3:** EI-02 re-baseline — these are an instrument change mid-experiment; confirm a clean
  re-baseline run is wanted before any new lift number is reported (PP-06).

---

## DeepSeek-V4 cross-check  ✅ (18 findings, 1634 s / 7317 tok; catalog-only — no code access)

V4 saw only the verbatim prompt catalog, not the source — a useful independent control. Net:
strong corroboration on the keystones, 3 genuine new items, and 5 false positives that the
Claude panel's code-grounded verification already covers (which validates that the panel's
adversarial-verify step earned its keep).

**(a) AGREEMENTS — raise confidence (independent, two models, code-grounded):**
- **H1** T1 missing ref inventory + free-string ref/no-validation — V4[1] (HIGH) + V4[3]. Keystone confirmed by both.
- **H3** CL24 spec-conformance charter not fed the ratified corpus — V4[14] (HIGH). Confirmed by both. *(V4 correctly singled out the spec charter; see disputed below for why it was wrong to extend it to the other two charters.)*
- **M1** T1 undefined shunt corridor — V4[2]. **M12** CORPUS_BRIEF off-family leakage — V4[0].
- **M8/M9** T4 `action` field never named in prose + safety lens "plane integrity" undefined — V4[4] (HIGH), V4[5]. **M3** T5 proposed_lever undermined by "NO direct effector" — V4[7] (HIGH).

**(b) NEW — V4 found, Claude panel missed → added as P-items:**
- **P5e** T5 "CONSOLIDATION" used at the rule cap but never defined — V4[8].
- **P6f** T4 finishing lens has no DRC locations, only counts — V4[6].
- **P11b** T6 facts-alongside supplies facts but never instructs the VLM to DEFER to them (false-positive risk) — V4[10]. **P11c** T6 advisory role not stated in-prompt — V4[9].
- **P12** T8 batch auditor "invited to decline" with no decline criteria — V4[13].

**(c) SEVERITY DISAGREEMENTS (V4 graded higher; Claude lower because it could see downstream containment):**
- V4 rates T4 action-name (V4[4]) and T5 proposed_lever (V4[7]) **HIGH**; Claude graded them medium because the strict grammar + deterministic guards contain the damage. Both true: V4 flags "the prompt as written is broken," Claude "downstream catches it." Keep Claude's grade for *prioritization*, but the prompt is still worth fixing — these are in P5/P6 regardless.

**(d) FALSE POSITIVES — catalog-only blind spots, refuted by code (NO action; logged for the record):**
- V4[15] "evidence-provenance charter missing evidence" — **refuted:** `_slice_evidence` injects "THE EVIDENCE THE CLAIM CITES" (`cec_verifier.py:_slice_evidence`).
- V4[16] "actuation-space charter missing owned levers" — **refuted:** `_slice_actuation` injects "LEVERS THE LOOP ACTUALLY OWNS" + metric history (`ctx['levers']`).
- V4[17] "CL24 missing output schema" — **refuted:** `VERDICT_SCHEMA` enum support/refute/uncertain (`cec_verifier.py:65-68`, used at `:247`).
- V4[11] "T7 missing output schema" — **refuted:** `CORPUS_FIT_SCHEMA` strict grammar (`cec_judge_local.py:889`, used at `:1302`).
- V4[12] "T7 undefined min_peers" — **refuted:** the system prompt says "(you are told the count)" and the payload carries `min_peers` (`cec_judge_local.py:957-958,1275`).
- *Lesson:* V4 pattern-matched "charter told to use X, but X not in the prompt text I was shown" across all three CL24 charters; only the **spec** charter is actually mis-fed (H3) — the other two are correctly sliced. Code access is what disambiguated. This is exactly why the Claude panel verified against source, and why the cross-check is run catalog-only as an independent control rather than as the system of record.

**Updated totals: 30 Claude-confirmed + 5 V4-new (P5e, P6f, P11b, P11c, P12) = 35 actionable items across P1-P12; 3 Claude-rejected + 5 V4-false-positive = 8 dispositioned non-issues.**
