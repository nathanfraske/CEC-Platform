# Closed-Loop Pipeline Implementation List (CL-01 through CL-20)

Two-zone corpus with human promotion gate, full loop closure (dimensions, placement,
routing, FEM, review, learning), and the analyst tier for high-reasoning,
low-format-compliance models.

**Provenance:** builds on the verified punchlist read (`main @ e2abe03`), the SB addendum,
the Hub Standard and 12VHPWR fab-gate audits, the model-selection session (June 2026), and
PR #18 diff stats. Line anchors have drifted since e2abe03; every landing point below is by
file and symbol. Re-verify against the current tree before implementing; do not take this
document's word over the code. Model size and throughput figures are estimates from the
model-selection session anchored to two measured points; re-verify at download.

## Operating rules for the implementing agent

1. The spec wins. Nothing here amends `CEC-Platform-Ground-Truth-Spec.md`; anything that
   touches a design decision is surfaced to the owner, never resolved by assumption.
2. No new mandatory services. Everything is file-based or GitHub-native, per the cold-start
   and self-host-parity invariants. If a design wants a database or daemon beyond the local
   orchestrator process, redesign it.
3. Provenance is mandatory. No corpus entry, constraint, or calibration value enters without
   a source that resolves to a document, a measurement run, or a named human decision.
   Model knowledge is not a source. Model output (including analyst traces) is not a source.
4. Consent gates on irreversible actuation. Anything that spends money, places an order, or
   flashes hardware stays consent-gated regardless of how automated the rest becomes.
5. Do not duplicate PR #18 (`claude/constraint-aware-placer`): it carries the Docker
   routing environment, constraint registry and extracted corpus, hard checkers
   (`cec_hc.py`, `cec_verify_hc.py`), placer (`cec_place.py`), DC-IR (`cec_dcir.py`),
   self-correction loop (`cec_loop.py`), and `dispatch.ps1`. Read that branch before
   touching anything adjacent. Rebase, do not re-implement.
6. Punchlist dependencies: R-01 (seed diversity), R-02 (single DRC), R-05 (graceful
   degradation) are prerequisites for any unattended overnight run. R-12 (read PR #18
   before runner dispatch) applies to CL-07.
7. Before pushing: `python3 -m py_compile scripts/*.py`, `scripts/checklist.sh`,
   `scripts/check-all.sh`.

Priorities: **P0** = enforcement boundary or protects against drift/spend. **P1** = required
for the closed loop. **P2** = needs accumulated history to pay off. Effort: S / M / L.

---

# Product thesis (added after the depth-versus-breadth reframe)

This system is depth-first. The product is one excellent board per family plus a
defensible review, never a mass design tool. The overnight candidate mass is internal
exploration machinery whose purpose is sparing the human serial backtracking; what
reaches the human is the converged survivor and the evidence behind it.

Two deliverables, sequenced:
1. **The reviewer ships first.** The cascade, facts serialization, swarm, panel, and deep
   path form a standalone fab-gate review that pays immediately on human-designed boards
   (the Hub and 12VHPWR audits were its manual prototype) and generates the decisions and
   corpus entries the generator needs to mature.
2. **The foundation layer matures behind it.** Placement and routing to a high-completion
   board, critical nets templated, the human doing intent, judgment calls, and bring-up.
   The 95 percent figure is the AM-12 trend target, earned per board family as the corpus
   eats that family's failure modes once each, never a launch promise.

Knowledge custody: the system's domain knowledge lives in legible substrates (corpus
entries with sources, policy, prompt hashes, settled records), so base models are rented
cognition, swappable without losing anything learned. Training is confined to
discriminative components behind replay evals (PC-04, Decision 17); the system itself is
never trained.

---

# Part 1: Corpus zones and the promotion gate

### CL-01: Corpus zone split and schema fields (P0, M)

**Goal.** One entry schema, two zones: `corpus/staging/` (agent-writable) and
`corpus/promoted/` (human-only). Promotion moves an entry without changing its ID.

**Landing points.** PR #18's `scripts/cec_constraints.py` registry and
`scripts/constraints/corpus-extracted.json`; the SB-13 schema (classes A/B/C plus heuristic
prose, lifecycle states).

**Implementation.**
- Directory split under `scripts/constraints/` (or `corpus/` at repo root; DECISION 1):
  `staging/` and `promoted/`, one JSON file per entry or per family, entry IDs stable.
- Schema additions: `state` (draft, under-review, promoted, deprecated, superseded),
  `signoff` block (human identity, date, evidence link), `promotion` block (date, shadow
  record pointer, promoting PR), `source` (existing, with type whitelist per CL-18),
  `class` (A/B/C/heuristic).
- Migration of the PR #18 extracted corpus: every existing entry lands in `staging/`
  unless the owner re-signs it during a one-time review pass (DECISION 2). No entry is
  grandfathered into `promoted/` without a resolvable source and a signoff.

**Verify.** Linter (CL-03) green on the migrated tree; one entry shows a full lifecycle in
git history: created in staging, promoted with ID unchanged and promotion block appended.

### CL-02: Server-side promotion enforcement (P0, S)

**Goal.** No model at any tier can make an entry load-bearing. A signoff field is text a
model can write; the unforgeable gate is GitHub's server-side review requirement.

**Implementation.**
- `CODEOWNERS` maps `corpus/promoted/**` (and `cec-policy.json`, CL-10) to the owner.
- Branch protection on the default branch: require pull request, require review from code
  owners, no bypass for agent accounts or bots.
- Optional hardening: require signed commits on the protected branch; only the owner holds
  the signing key.
- Agent identity separation: agents and the orchestrator authenticate as a dedicated
  machine account with no review or approval rights, and the owner approves from the
  owner's account only. Enable dismiss-stale-approvals and
  require-approval-of-most-recent-push. If agents run under the owner's token (a PAT on
  the night box), the server-side gate is theater; this bullet is the entire difference.
- Document the branch topology (DECISION 1): either agents commit directly to a `staging`
  branch with promotion PRs to main, or PRs everywhere with staging-only PRs auto-approved
  by a bot. Either is acceptable; the invariant is that merges touching `promoted/**`
  require the owner's GitHub-verified approval.

**Verify.** A test PR from an agent account touching `corpus/promoted/` cannot be merged
without the owner's approval; one touching only `staging/` can.

### CL-03: Compiler and linter enforcement (P0, M)

**Goal.** Second, independent enforcement point at the consumer, so a failure of either
gate fails safe.

**Landing points.** The constraint compiler in `cec_constraints.py`; the SB-14 provenance
linter; CI workflow.

**Implementation.**
- Compiler emits blocking artifacts (`.kicad_dru` fragments, netlist assertion sets,
  placement keep-apart tables, scorer limits) only from entries with `state: promoted` and
  a complete signoff block.
- Dual-target compilation: `.kicad_dru` custom rules bind KiCad DRC only and do not ride
  the DSN export into Freerouting, so any constraint expressible as netclass geometry
  (widths, clearances, via sizes) must also compile into the netclass layer the router
  consumes, or every candidate violates it during routing and dies at DRC afterward,
  burning the night's compute on boards that were doomed at export. Constraints only
  expressible as custom rules are enforced post-route at DRC by design, budgeted and
  logged, never silent.
- Staging entries compile into a separate advisory check set with a distinct flag
  namespace (`ADV-` prefix) so decision logs and the cascade unambiguously distinguish
  advisory fires from gate fires. Advisory checks can never block, never auto-sign-deny,
  never feed `human_signoff`'s blocking-flag count.
- Linter rules added to CI: no blocking artifact references a non-promoted entry; no
  promoted entry lacks signoff or a resolvable source; Class A entries must resolve to a
  line in the current spec version (CL-06); source-type whitelist (CL-18).

**Verify.** Hand-craft a staging entry and a promoted entry; compile; assert the staging
entry appears only in the advisory set and the promoted entry only in the blocking set.
Break each linter rule once and confirm CI fails.

### CL-04: Shadow mode runtime and promotion requests (P1, M)

**Goal.** Staging entries earn promotion with field evidence instead of arriving cold.

**Landing points.** The check cascade in `cec_synth_pipeline.py`; `cec_dispatch`; the run
ledger (SB-01); the inbox (SB-02).

**Implementation.**
- The cascade runs the advisory set on every candidate, every night. Each fire appends a
  ledger event: entry ID, board, candidate hash, run ID, locus.
- A shadow-record aggregator (`scripts/cec_shadow.py`): per-entry fire history, boards
  touched, and judge annotations of true/false positive (the judge annotates during the
  morning review, CL-12).
- Promotion request generator: when an entry's shadow record crosses a configurable
  threshold (fires observed, zero unexplained false positives, or owner request), emit an
  inbox item bundling the entry, its shadow record, and the source document reference. The
  owner's approval action is the promotion PR.

**Verify.** Seed one staging entry that is known to fire on a current board (for example a
netclass-conformance rule against the pre-fix 12VHPWR snapshot); run a night; confirm the
shadow record accumulates and a promotion request renders with the evidence attached.

### CL-05: Demotion, supersession, and conflict detection (P1, S)

**Implementation.**
- State transitions out of `promoted` (deprecate, supersede) are human-only, enforced by
  the same CL-02 gate since they edit `promoted/**`.
- Misfire evidence: judge or bench flags a promoted entry as having fired wrongly; the flag
  attaches to the entry's record and surfaces in the inbox. The loop never disables a
  promoted entry on its own.
- Linter conflict detection: a staging entry whose scope overlaps a promoted entry with a
  contradictory assertion is flagged for human resolution; it cannot be promoted while the
  conflict stands.

**Verify.** Create a deliberate staging/promoted contradiction; linter flags it; promotion
request for the staging entry is blocked until resolved.

### CL-06: Class A routing exception (P0, S)

**Goal.** The corpus never becomes a side channel for amending the spec.

**Implementation.** Class A entries are spec-derived; their source must resolve to a line
in the current spec version. A new Class A assertion therefore implies a spec revision
first: the flow is spec-revision proposal to the owner, spec merges, then the corpus entry
citing the new line. The linter rejects any Class A entry whose source does not resolve,
and the inbox templates make the spec-first path the default for anything an agent
classifies as A.

**Verify.** Attempt to add a Class A entry citing a nonexistent spec section; linter fails.

---

# Part 2: Closing the loop

### CL-07: Local orchestrator daemon (P1, L; gated on R-01, R-02, R-05, R-12)

**Goal.** The overnight loop runs unattended on the workstation: generation, checks,
scoring, analysis, bundling, with crash discipline and resume.

**Landing points.** `cec_dispatch.request_candidates` (the `where="runner"` seam),
`cec_loop.py` (PR #18; read first per R-12), `cec_synth_pipeline.py`, the ledger.

**Implementation.**
- `scripts/cec_orchestrator.py`: phase scheduler (generate, check, score, analyze, bundle),
  consuming a queue (GitHub Issues per the SB-02 design or a file queue; DECISION 3),
  appending a ledger line per stage with the determinism manifest.
- Per-candidate try/except with a quarantine directory; a watchdog process; resume-from-
  ledger so a crash costs one candidate. Depends on the R-05 graceful-degradation fix
  landing first.
- Scheduled task (Windows Task Scheduler on the rig; systemd unit for any Linux runner
  parity box). The orchestrator is a local process, consistent with rule 2; it owns no
  state outside the ledger and the filesystem.
- Stage wall-times instrumented into the ledger from night one; the budget allocator
  (successive halving over the existing cascade) reads measured costs, never assumptions.

**Verify.** Kill the orchestrator mid-night; restart; it resumes from the ledger without
re-running completed candidates, and the quarantine directory holds only the interrupted
one.

### CL-08: Failure attribution and nested re-entry (P1, M)

**Goal.** Dimensions, placement, and routing nest as outer, middle, and inner loops, with
attribution deciding which loop absorbs a failure.

**Landing points.** `cec_loop.py` (extend) or new `scripts/cec_attribution.py`; the
bisection loop; the ledger.

**Implementation.**
- Deterministic feature extraction per failed candidate: unrouted count per param set, DRC
  violation clustering by component and net, FEM hotspot loci, which check IDs fired
  (gate and advisory separately).
- Attribution rules, in order: unroutable across all param sets for one placement is a
  placement fault (re-enter middle loop); unroutable across all placements first retries one
  relaxed-but-legal rules variant (clearance and via choices inside the spec envelope)
  before being attributed as an outline fault (re-enter outer loop, bisection direction
  up), because board growth fights the 100 mm cost target and overtight rules mimic a
  small outline; hotspot or violation localized at a
  via field or rule artifact is a routing-rule fault (adjust costs inside the spec
  envelope, re-enter inner loop); a promoted-entry fire is a design fault citing the entry.
- The manager tier writes the attribution narrative from the deterministic features; the
  features decide the routing, the narrative is for the ledger and the morning bundle.
- Each attribution lands as a reward or penalty on the generator config that produced the
  candidate (bandit state lives in the ledger; bounds live in policy, CL-10).
- Outline priors: per-board-family success rates by outline from the ledger inform the
  bisection's starting point.

**Verify.** Replay a known unroutable case (shrink eps-8pin's outline below feasible);
attribution selects outline fault and the outer loop grows it; ledger shows the lineage.

### CL-09: Placement portfolio generation (P1, M)

**Landing points.** `cec_place.py` (PR #18), `cec_hc.py`, the user-pin consent system.

**Implementation.**
- Portfolio generator emitting N legal placements per board per night. Operators: seeded
  perturbation of unpinned refs, block-level alternatives, rotation sets on symmetric
  blocks, cluster swaps.
- Every emitted placement passes the hard-constraint checker before any routing compute:
  user pins frozen, keep-apart table satisfied (the REF3030/LP5907 class), Kelvin pairs
  local, connector refs on their edges, cap-to-node proximity.
- Soft-pin class added to the consent system: a ref movable within a stated radius, so the
  portfolio explores around hand placement without violating its intent. Consent file
  format extension; default remains hard pin.

**Verify.** N=8 on eps-8pin yields at least N distinct placement hashes, all passing
`cec_hc` pre-route, with pinned refs byte-identical across all eight.

### CL-10: Policy as code (P0, S)

**Goal.** Everything the loop may tune lives in one versioned, PR-gated file; the loop
tunes inside declared bounds and can never widen them.

**Implementation.**
- `cec-policy.json` (CODEOWNERS-protected per CL-02): role-to-model bindings (CL-14) with
  per-model fields (model ID, quant, license_cleared, eval-gate status), bandit bounds,
  per-night budgets (wall clock, deep-path token cap), cascade thresholds, prompt hashes,
  policy version.
- Orchestrator loads it at start of night, records its hash in every ledger manifest, and
  refuses to run if any load-bearing binding has `license_cleared: false` or a failed eval
  gate.
- Nightly autonomy: allocation shifts within bounds only. Bound changes, threshold changes,
  and binding changes are PRs.

**Verify.** Set a bandit bound; confirm the orchestrator clamps an attempted out-of-bound
allocation and logs the clamp. Flip `license_cleared` to false on a bound model; the
orchestrator refuses that binding at startup.

### CL-11: Golden regression seeding (P0, M; ties to SB-08 and punchlist R-03)

**Goal.** The drift anchor. Every change to code, policy, or promoted corpus must keep
known-bad failing and known-good passing.

**Implementation.**
- Fixtures from the two audits, four board states: Hub Standard with the TPS2121 PR1
  defect and with the four-resistor divider fix; 12VHPWR with the 136 signal-size lane
  vias and with netclass-conformant vias. These are real, already-labeled cases.
- CI job runs the cascade against the fixtures and asserts invariants by flag ID:
  known-bad fires the expected check IDs; known-good fires none of them. Blocking for any
  PR touching `scripts/`, `cec-policy.json`, or `corpus/promoted/`.
- Note: the TPS2121 case only fires once a corresponding Class B entry exists (see CL-18's
  flow); until then the fixture carries an expected-fail marker so the gap is visible
  instead of silently green. The via case is checkable today with the netclass-conformance
  parser check.
- Goldens are frozen regression anchors and are burned for tuning the moment a prompt or
  charter is adjusted against them, which the verify steps in this document literally
  instruct. Keep a separate held-out eval pool, thin at first and grown from every
  adjudicated override and bench label, that prompt and charter tuning never touches.
  Goldens gate CI; the holdout measures generalization.
- Execution venue per the SB-08 decision (self-hosted runner versus PR #18's container;
  DECISION 4).

**Verify.** Revert the via fix on the fixture in a test branch; CI goes red on exactly the
expected flag ID.

### CL-12: Morning bundle and verdict schema (P1, M)

**Goal.** The judge consumes a curated bundle and emits machine-readable verdicts; the
owner's morning is two short queues; every owner action is a calibration label.

**Implementation.**
- Bundle builder per finalist: top-side render (`kicad-cli` export), score row with deltas
  against the ledger incumbent, decision log, fired checks (gate and `ADV-` separately),
  resolved generator config, and any flag types not previously seen.
- Verdict JSON schema (lock the fields with the owner before agents code against it;
  DECISION 7): run ID, board, ranking, per-candidate verdict enum (accept, hold, escalate),
  cited check IDs per reason, drafted-entry references, novel-flag list, confidence,
  judge-model manifest (model ID, quant, prompt hash).
- Judge annotates advisory fires as true or false positive (feeds CL-04 shadow records).
- Owner verdict action (inbox or a small CLI): accept or override per candidate; the action
  writes a labeled case (judge verdict, owner verdict, board, run) to the ledger. This is
  the SB-09 calibration stream.

**Verify.** One full night, one morning: the bundle renders, the judge emits schema-valid
JSON, an owner override lands in the ledger as a labeled case.

### CL-13: Bench write-back schema (P1, S now, L when boards arrive; ties to SB-06)

**Goal.** Hardware is the label of record. Land the schema now so nights accumulate
predictions to compare against the moment fabbed boards exist.

**Implementation.**
- Outcome label schema attached to run lineage: predicted hotspot loci and margins versus
  measured temperatures; predicted Kelvin channel matching versus measured spread; defects
  that escaped to hardware, each mapped to the check that should have caught it (or to
  "no check existed", which drafts a staging entry).
- `cec_ledger.py label <run_id> ...` CLI for bench-session entry; labels feed judge
  calibration (CL-12) and entry justification (CL-04).

**Verify.** Schema round-trips through the ledger; a synthetic label on a past run renders
in that run's lineage query.

---

# Part 3: The analyst tier

The capability ladder is at least two-dimensional: reasoning depth and format compliance
are independent axes. MiniMax-M2.7 (owner's direct usage finding) sits high on the first
and low on the second: it reasons through hard problems effectively and cannot be relied
on to emit a one-line or schema-shaped answer. The pattern that uses such a model safely
is a composite: an analyst that thinks in free form, and an extractor that compiles the
thinking into schema, grounded span by span. This is the same thinking/answer separation
reasoning models perform internally, rebuilt externally where the seam is controllable
and verifiable.

### CL-14: Role contracts in policy (P0, S)

**Implementation.**
- Roles declared in `cec-policy.json`: worker, verifier, extractor, manager, analyst,
  judge, frontier. Per-role contract fields: format_reliability (holds schemas under
  pressure: yes/no/partial), reasoning_depth class, throughput class, context budget,
  residency cost (RAM/VRAM at the bound quant), license status, eval-gate status.
- Bindings as of the June 2026 model-selection session (re-verify sizes at download):
  worker Qwen3.6-35B-A3B (~22 GB Q4); verifier and extractor Qwen3.6-27B dense (~17 GB Q4);
  manager gpt-oss-120b; analyst Qwen3.5-397B-A17B (Apache 2.0, ~165 to 175 GB at
  UD-Q3_K_XL) as the clean-license occupant, MiniMax-M2.7 (~108 to 135 GB quantized)
  BLOCKED pending CL-20; judge per eval gate; frontier per API for the morning review.
- A model may hold multiple roles only if it passes each role's eval gate independently.

**Verify.** Policy loads; orchestrator refuses a binding with a failed or absent eval gate
for a load-bearing role.

### CL-15: The deep path composite, analyst plus extractor (P1, M)

**Goal.** `deep_verdict(bundle)` as a single invokable unit anywhere the pipeline needs a
verdict on a hard case.

**Implementation.**
- Analyst call: free-form prose contract, no schema demanded. The prompt asks for analysis
  ending in an explicit conclusions section; nothing about the output is parsed beyond
  locating that section. The full trace is stored, hashed, and ledgered as an intermediate
  artifact with the analyst's model manifest.
- Extractor call: fills the verdict schema (CL-12's schema, or a check-specific one) with
  mandatory quoted evidence spans copied verbatim from the trace for every substantive
  field.
- Span verifier: deterministic string match of every quoted span against the trace
  (cheap, automatic, zero tolerance), plus optional entailment spot-check by the verifier
  model. Verdict-class fields may quote only from the conclusions section; evidence
  fields may quote anywhere. This structural rule blocks the cherry-pick failure where a
  hedged aside becomes the verdict with technically valid spans. A non-grounded
  extraction is rejected; one re-extract attempt; then escalation to the frontier judge,
  or to the owner inbox when frontier is unavailable, never a silent drop.
- "No conclusion reached" is a valid and honest extraction outcome. It triggers one
  analyst continuation prompt ("state your conclusions") or escalation. The extractor
  never synthesizes a verdict the analyst did not reach; that rule is the whole safety
  property of the seam.

**Verify.** Feed the extractor a trace with no conclusion; assert it returns
no-conclusion rather than a fabricated verdict. Feed it a trace and corrupt one quoted
span; the span verifier rejects.

### CL-16: Deep-path routing policy (P1, S)

**Implementation.**
- Deterministic triggers, never default: attribution ambiguous (CL-08 rules tie or
  conflict), novel flag type, gate and advisory checks in contradiction, judge confidence
  below threshold, a Pareto-frontier candidate with an anomalous metric, or swarm
  contention (CL-24: a deduped finding cluster that deterministic triage can neither
  confirm nor refute, or swarm agents disagreeing at one locus).
- Per-night deep-path budget in policy (token and wall-clock caps); jobs queue and batch
  into the analyst residency window (CL-17).
- Every deep-path invocation ledgered with trigger reason, so the analyst-usefulness eval
  (CL-19) has its denominator.

**Verify.** A night with zero triggers spends zero analyst tokens; a seeded ambiguous
attribution routes exactly one bundle through the deep path.

### CL-17: Residency scheduler (P1, M)

**Goal.** The 192 GB ceiling means one large resident model at a time; the schedule, never
luck, decides which.

**Implementation.**
- Phase-based loading in the orchestrator: generation and check phases keep the worker and
  extractor/verifier resident (GPU-class, ~22 GB and ~17 GB); the analysis phase unloads
  them as needed and loads the analyst (~108 to 175 GB depending on binding, expert
  offload via ik_llama.cpp); the manager loads for attribution narratives in its own
  window if co-residency with the analyst does not fit.
- Load and unload events, model hashes, and quant identifiers recorded in the ledger
  manifest, so any verdict is attributable to the exact resident stack.
- Measure actual resident sizes and tok/s on first load and write them back into the
  policy file's residency fields (PR), replacing the session estimates.

**Verify.** A night's ledger shows clean phase windows with no failed-allocation events;
the policy file's residency fields match measured values after the first calibration PR.

### CL-18: Trace-to-corpus derivation rule (P0, S)

**Goal.** Analyst traces accelerate corpus growth without ever becoming sources, keeping
rule 3 intact.

**Implementation.**
- Traces are derivation context. A drafted entry must cite the datasheet section, spec
  line, or measurement run the trace pointed at; the trace attaches as rationale via its
  ledger hash.
- Heuristic-prose entries distilled from a trace acquire a valid source only at the
  owner's signature, at which point the source type is "named human decision" with the
  trace as attached rationale.
- Linter enforces a source-type whitelist (document, measurement run, named human
  decision, spec line) and rejects any source field resolving to a model artifact.

**Verify.** Draft an entry whose source field points at a trace hash; linter rejects it.
The same entry citing the TI TPS2121 datasheet section with the trace as rationale passes.

### CL-19: Extractor fidelity eval, then analyst usefulness eval (P0, S; P2, M)

**Implementation.**
- Extractor fidelity (build first, it is cheap and automatic): labeled (trace, gold
  extraction) pairs, seeded from the two audits by writing each audit's reasoning as a
  trace and its findings table as the gold schema. Metrics: span existence 100 percent
  required, field accuracy, hallucinated-verdict rate with zero tolerance. Gates any
  extractor model or prompt change (CL-14 eval-gate field).
- Analyst usefulness (P2, needs history): on labeled hard cases, deep path versus fast
  path, scored by agreement with eventual human verdicts and bench outcomes. Decides
  whether the deep path earns its budget, per trigger class.

**Verify.** Extractor eval runs in CI in under a minute on the seeded set; a deliberately
broken extractor prompt fails the gate.

### CL-20: License gate for MiniMax-M2.7 (P0, S)

**Implementation.**
- Per the model-selection session, M2.7 ships under a Modified-MIT license whose
  commercial-use terms were flagged for review before any pipeline use. Re-verify the
  current license text directly; obtain written authorization or counsel sign-off if the
  flag holds.
- Until cleared: `license_cleared: false` in policy, binding BLOCKED, orchestrator refuses
  it for any load-bearing role (CL-10 enforcement). Qwen3.5-397B-A17B (Apache 2.0) holds
  the analyst binding in the interim.
- Bench-only experimentation with M2.7 (no pipeline artifacts consumed downstream) is a
  policy question for the owner; if allowed, its outputs are marked non-load-bearing in
  the ledger.

**Verify.** With the flag false, a deep-path job binds the Apache analyst; flipping the
flag in a test policy (not merged) binds M2.7 and the ledger manifest shows it.

---

# Part 4: Adversarial visual review

Every stage so far requires a rule, a parser, or a mesh to exist before a defect is
visible to it. The panel is the one stage that needs none of those: it looks. It
automates the third modality of the two fab-gate audits (a reviewer looking at the
board), alongside parsing and datasheet reading, and its highest-value hunting ground is
exactly where the deterministic checks are blind.

### CL-21: Render evidence pipeline (P1, M)

**Goal.** The panel is only as good as what it sees; raw full-board screenshots waste
most of a vision model's resolution budget.

**Landing points.** `scripts/render.sh`, `kicad-cli` (pcb render, pcb export svg), the
pad-to-net parser from the audit work, placement data.

**Implementation.**
- View set per candidate: full-board top and bottom composites for gestalt; per-copper-
  layer SVG exports; block crops generated from placement clusters (sizing guideline:
  passives want roughly 25 px/mm or better to be reviewable, so an 80 mm board needs
  crops, with the full-board view reserved for layout gestalt); diff renders against the
  ledger incumbent highlighting changed regions.
- Net-colorized overlays: KiCad's SVG exports are geometry by layer and carry no net
  tags, so post-processing them by membership is the wrong mechanism. Generate the
  overlay SVG directly from the parsed board data instead (the parser already holds
  track, via, and pad coordinates with their nets), drawing named net families (power
  classes, Kelvin pairs, DETECT, CAN) over the base render. This is what makes the
  NTC-cap-distance and pair-2-termination classes visible to a vision pass.
- Locating aids on every view: a coordinate grid, legible ref designators, and region IDs
  on crops. Vision models name regions and refs far more reliably than they emit pixel
  coordinates, and the CL-22 finding contract's locus field accepts refs and region IDs
  for exactly this reason.
- Coverage overlay, stated honestly: a map of what each deterministic check examined and
  where it fired, never a cleared-equals-safe claim. The 12VHPWR via defect existed
  because netclass membership was wrong, so DRC ran clean over the exact defect; an
  overlay painting that region safe would have steered reviewers away from the one
  finding that mattered. A fixed fraction of panel and swarm budget therefore always runs
  blind, with no overlay, as coverage-agnostic sampling.
- All headless and file-based, emitted into the candidate's bundle directory; the CL-12
  bundle builder consumes the same set.

**Verify.** Render set for one eps-8pin candidate generates in one command; a 0402 in a
block crop is legible at the stated px/mm; net colorization spot-checks against the
parser's pad-to-net map.

### CL-22: Adversarial visual panel (P1, L)

**Goal.** Independent vision-capable reviewers whose contract is to find what is wrong
with the board as seen, with every finding falsifiable and triaged deterministically
before it costs human minutes.

**Landing points.** CL-12 bundle, CL-15 deep path, CL-11 fixtures, SB-05 fab preflight,
`cec-policy.json` role bindings.

**Implementation.**
- Seats: frontier (multimodal) plus the local analyst, which per the June session is the
  natively multimodal model in the local set (verify modality at binding; the CL-14
  contract gains a `modality` field, and text-only bindings such as gpt-oss-120b are
  ineligible). The analyst seat runs through the deep path: free-form visual analysis,
  extractor compiles findings, span verifier grounds them. Optional third seat: a small
  open VLM, bound only after passing the golden render eval.
- Charters instead of one generic find-issues prompt: thermal adjacency; current path and
  via transitions; measurement integrity (Kelvin symmetry, sense-pair locality);
  manufacturability (slivers, acid traps, silk over pads); EMC (loop area, returns over
  splits); connector and termination completeness. Each seat reviews under each charter
  independently.
- Two-pass protocol: pass 1 blind (renders only, no decision log, no other panelist's
  output, preventing anchoring); pass 2 with context (netlist annotations for the flagged
  region, datasheet for parts named) to refine mechanism and severity. Aggregation
  dedupes by locus and mechanism after all seats commit; cross-seat agreement raises
  priority, disagreement routes to the deep path.
- Finding contract: locus (region, refs, coordinates), mechanism (why it is a defect),
  severity, and a falsifiable verification path (the parser check, FEM probe, bench
  measurement, or datasheet line that would confirm or refute it). A finding without a
  verification path is returned to the panelist once, then dropped.
- Triage: every finding attempts deterministic verification first. Confirmed findings
  become defects, and where a rule could have caught them, drafted staging entries whose
  source is the verification artifact, never the finding itself, per CL-18. Refuted
  findings are dismissed with reason and logged against the panelist. Unverifiable but
  plausible findings go to the judge and owner with the panelist's calibration record
  attached.
- Calibration: per-seat, per-charter precision and recall from adjudicated outcomes. The
  golden render eval comes free from the CL-11 fixtures: pre-fix Hub and 12VHPWR renders
  must yield the REF3030 proximity and the lane-via findings, post-fix renders must stay
  quiet at those loci. Gates any seat's model or prompt change. The eval sets honest
  expectations: the TPS2121 class is invisible to this stage by design and is excluded
  from its recall denominator.
- Placement in the loop: nightly on the Pareto finalists under a budget (Decision 8);
  mandatory at fab preflight (SB-05), where every finding must be dispositioned
  (confirmed-fixed, dismissed-with-reason, or accepted-risk, the latter two owner-only)
  before the consent-gated order.

**Verify.** Run the panel against the pre-fix Hub fixture render set; the thermal charter
yields the REF3030 adjacency with a verification path the triage step confirms via the
keep-apart parser check; the post-fix render set yields no finding at that locus.

---

# Part 5: Swarm verification layer

The funnel now has three review strata with inverted contracts. The swarm is many
invocations of a small model, each over a tiny evidence slice with a terse fixed-format
output. The panel (Part 4) is few invocations of large multimodal models over renders.
The analyst is fewer still, long prose, contention only. The extractor bridges prose to
schema everywhere. Each stratum's contract matches what its models do reliably, and no
stratum is asked for what it confabulates.

### CL-23: Board-facts serialization (P1, M)

**Goal.** A canonical, deterministic, textual representation of the board. The swarm's
substrate is facts rather than pixels, and small models reason better over explicit facts
than over raw file formats or images.

**Landing points.** The pad-to-net parser from the audit work; placement and via tables;
`cec_score.Metrics`; the CL-12 bundle builder.

**Implementation.**
- One generator (`scripts/cec_facts.py`) emitting per-board JSON plus a flat text
  rendering: refs with positions, rotations, courtyards; pad-to-net map; per-net via
  tables (size, drill, layer pairs); netclass membership and class minima; pairwise
  distances for declared part classes (regulators, references, shunts, sense pairs);
  layer transitions per net; zone coverage summaries; check flag loci.
- Sliceable by region, net family, ref set, or charter, so a swarm job's context is a few
  hundred tokens of relevant facts rather than the whole board.
- Deterministic and hashed into the ledger manifest. The same serialization feeds the
  judge bundle, the deep path, and the panel's pass-2 context, so every tier argues over
  identical facts.
- Grounding against the audits: the REF3030 finding is fully expressible in this
  substrate (two regulator-class parts, 8.45 mm apart, 8 mm target), as are the
  via-netclass, cap-to-node, and termination classes. The serialization makes those
  catchable by text-only models with no vision involved.

**Verify.** Serialize the pre-fix 12VHPWR fixture; the lane-via facts (count, size,
netclass minima) appear; a slice request for the Power12V net family returns only the
relevant subset; an identical board produces an identical hash.

### CL-24: Swarm adversarial verifier tier (P1, L)

**Goal.** Breadth-layer adversarial review on every candidate, every night, cheap enough
to never be rationed, with output constrained to what a small model produces reliably.

**Landing points.** `cec-policy.json` roles (new role `adversarial-verifier`, bound to
the worker model), CL-23 facts, CL-16 triggers, the cascade.

**Implementation.**
- Decorrelation by input, never by temperature (the R-01 lesson restated for models):
  each swarm job is one charter, one evidence slice, one framing. Charters mirror
  CL-22's plus fact-native ones: netclass conformance reasoning, distance-rule hunting,
  corpus-entry violation hunting (the job gets one promoted entry plus the relevant
  slice), spec-line conformance (the job gets the spec excerpt). Framings vary what
  accompanies the slice: spec excerpt, datasheet excerpt, relevant promoted entries, or
  nothing.
- Micro-schema output contract, strict and small: up to N findings per job, each one
  line: charter, locus (refs or nets), claim. No severity, no verification path, no
  prose. Severity and verification paths are assigned downstream at aggregation by the
  manager or extractor, because confabulated calibration is the known small-model failure
  and the contract never requests it.
- The funnel: dedup by locus and claim across all jobs; cluster; deterministic triage
  first (most fact-derived claims are mechanically checkable against the same facts
  file); confirmed becomes a defect or a staging draft per CL-18; refuted is logged
  against the charter; contention (unconfirmable, or agents disagreeing at one locus)
  becomes a deep-path trigger (CL-16).
- Calibration at charter granularity: per-charter precision from triage outcomes decides
  budget, and a charter below a precision floor is suspended pending prompt revision
  (PR-gated; prompt hashes live in policy). Per-finding human adjudication is explicitly
  rejected as the model; the funnel exists so it never becomes necessary.
- Residency: the swarm window keeps the worker resident on GPU. At the researched quants
  the worker (~22 GB) and the 27B extractor (~17 GB) exceed 32 GB VRAM together, so
  aggregation and extraction run phase-sequential or hybrid-offloaded per CL-17; measure
  on first load.
- Throughput (estimate; measure night one): at the researched 120 to 240 tok/s with a
  few-hundred-token contract per job, thousands of swarm jobs per night are plausible on
  this rig. The budget allocator treats swarm cost as near zero relative to FEM and
  analyst tokens, which is the point of the stratum.

**Verify.** Run the swarm against the pre-fix fixtures' facts: the distance-hunting
charter yields the REF3030 finding and the netclass charter yields the lane-via finding;
triage confirms both deterministically; the post-fix facts yield neither; a deliberately
broken charter prompt falls below the precision floor and is suspended.

---

# Part 6: Red-team findings and amendments

A self-adversarial pass over Parts 1 through 5. Inline corrections were applied directly
to CL-02, CL-03, CL-08, CL-11, CL-15, and CL-21 (agent identity separation, dual-target
compilation, relaxed-rules retry before outline growth, golden/holdout split,
conclusions-only verdict sourcing, overlay honesty and the corrected colorization
mechanism). The structural findings land here as two new items and twelve amendments.

### CL-25: Audit-derived check pack and intake gate (P0, M)

**Finding.** Parts 1 through 5 depend throughout on the six check classes derived from
the Hub and 12VHPWR audits, and this list never itemized them. The fixtures (CL-11), the
swarm verifies (CL-24), and the triage step (CL-22, CL-24) all assume they exist. PR #18
carries `cec_hc.py`, and nothing verifies it covers these specific classes.

**Implementation.**
- The six classes as named checks with stable IDs: netclass membership audit plus per-net
  via and track geometry against class minima; thermal aggressor and victim keep-apart;
  cap-to-node proximity; BOM field lint (placeholder and empty value patterns);
  schematic-and-PCB sync plus artifact freshness; per-board spec-conformance netlist
  assertions. Landing: extend `cec_hc.py` and `cec_verify_hc.py` after reading PR #18, or
  a new `cec_checks_audit.py` if the shapes do not fit.
- Intake gate: the loop refuses to generate candidates for any board failing the
  schematic-side subset (sync, ERC freshness, BOM lint, netlist assertions). The TPS2121,
  desync, and R1 classes live upstream of layout, and a loop that routes a broken netlist
  all night produces perfectly routed wrong boards.

**Verify.** Each check fires on its originating pre-fix fixture by ID and stays quiet on
the post-fix fixture; a board with a stale ERC is refused at intake with a named reason.

### CL-26: Minimal viable night (P0, M)

**Finding.** The critical path to the first useful overnight run threads R-01, R-02,
R-05, CL-07, CL-08, CL-09, and CL-23, which is weeks of build before any signal. Every
budget and throughput number in this document is an estimate until a night actually runs.

**Implementation.** A deliberately disposable thin loop, retired by CL-07: the R-01 seed
fix, CL-23 facts, a swarm-only review pass, and a manual morning read, driven by a plain
PowerShell or Python loop with no daemon, no inbox, and no judge. Its outputs are the
measured stage costs (route, score, swarm) the budget allocator needs, the first charter
calibration data, and proof of signal inside days. Build it before the orchestrator, and
let nothing in it harden into architecture.

**Verify.** One night on eps-8pin yields a ledger of measured stage wall-times and at
least one triage-confirmed swarm finding or a documented zero with charter stats.

### Amendments

**AM-01: Recall estimation and checking the checkers (CL-04, CL-12, CL-22, CL-24).** The
calibration stream measures precision only on what gets surfaced: a judge that buries a
candidate class is never overridden on it, and a triage bug that wrongly refutes findings
silently suspends a charter for being right. A random audit fraction of non-surfaced
candidates and triage-refuted findings goes to the owner or frontier each week, and the
triage verifiers themselves join the CL-11 golden scope.

**AM-02: Every corpus entry ships a minimal failing fixture (CL-01, CL-04, CL-11).** An
entry that never fires accumulates no shadow evidence and stagnates in staging even when
correct. Each entry carries a fixture snippet that makes it fire, linter-enforced; this
proves the compiled check works, gives promotion evidence independent of nightly luck,
and replaces CL-11's expected-fail marker the day a TPS2121 entry is drafted (its fixture
is the pre-fix Hub board).

**AM-03: Bandit epoching (CL-08, CL-10).** Every gate or policy change shifts the
environment, so reward history collected under an old manifest mislabels configs under
the new one. Partition bandit state by policy-plus-corpus manifest hash, or use a
discounted sliding window; never let pre-change history dominate post-change allocation.

**AM-04: FEM is uncalibrated until the bench says otherwise (CL-13, scorer).** Until the
first CL-13 write-back, the electrothermal scores are confident numbers with no measured
anchor. Add analytic goldens now (IPC-2152 trace-heating curves, closed-form 1D
conduction cases) as FEM sanity checks, and mark FEM-derived scores as uncalibrated in
every bundle until a bench label exists for the board family.

**AM-05: Owner bandwidth is a budgeted resource (CL-04, CL-12, CL-16).** One reviewer.
WIP caps per inbox class (open promotion requests, nightly finalists, dispositions) sized
to stated review minutes per day, orchestrator-enforced like any other budget. Absence
mode holds escalations and promotions; nothing auto-signs in absence, which
`human_signoff` already guarantees and this makes explicit.

**AM-06: Ledger mechanics (SB-01, CL-07, CL-24).** Thousands of swarm fires per night in
one git-tracked JSONL bloats history fast and invites concurrent-append corruption.
Shard per run or per month; high-volume streams (swarm fires) go to sidecar files with
hashes in the ledger; single-writer rule: the orchestrator owns appends, everything else
submits through it.

**AM-07: Pin the execution environment first (CL-07, CL-17).** The rig is Windows, the
chain is Linux-leaning: AMGX is Linux-first, headless Freerouting wants xvfb on Linux,
and ik_llama.cpp builds vary by platform. CUDA on WSL2 is supported and is the likely
landing. Decide the venue (WSL2, native, or PR #18's container), then golden-run the
entire chain in it once, end to end, before building anything further on top
(Decision 10).

**AM-08: Define convergence on the front (CL-07, CL-08).** Scalar improvement-below-
epsilon is ill-defined over a multidimensional Pareto front. Convergence per board is
hypervolume improvement (or dominance count) below epsilon over N runs, computed from
the ledger.

**AM-09: Critical-net templates and the router ceiling (CL-09, scorer).** Freerouting
will route Kelvin and sense nets legally and badly, and the loop must never be rewarded
for letting it. Measurement-integrity nets are pre-routed or template-routed and locked
through the consent system; the router's scope is the routable bulk. State this in the
scorer too: candidates are compared on the unlocked portion, and any candidate that
touched a locked net is dead on arrival.

**AM-10: Injection hygiene (CL-12, CL-15, CL-22, CL-24).** Model-authored text re-enters
model contexts across trust boundaries (drafted entries into judge bundles, shadow
records into promotion requests, traces into extraction). Render all such text as quoted
data fields with provenance labels, never as bare instructions in the prompt body;
staging-authored text never enters a load-bearing context unlabeled; fetched datasheet
extractions are sanitized before context entry.

**AM-11: Context ceilings are enforced, never hoped (CL-23, CL-24).** The slicer
enforces hard token budgets per job and fails fast when a slice exceeds them; slicer
version and slice hash join the per-job ledger manifest so a finding is attributable to
exactly what its agent saw.

**AM-12: The loop needs a success metric or it optimizes its internals forever (whole
document).** Two numbers, ledgered and trended: human-edit distance between the loop's
winning candidate and the board actually ordered (how much hand-fixing the winner
needed), and the first-loop-fabbed-board milestone. Every other metric in this document
is instrumental to these two.

---

# Part 7: Rebuilt ideas

Each red-team kill in Part 6 destroyed a mechanism while leaving its intention intact.
This part rebuilds the intentions, and each rebuild was itself attacked before landing
here; the bounds written into every entry are what that second pass imposed. Ideas whose
original form stays dead: cleared-equals-safe, single-language constraint compilation,
unratified whole-trace extraction, and seeds-as-diversity.

### RB-01: Coverage as declared scope, two review budgets (amends CL-01, CL-21, CL-22, CL-24)

**Recovered intention.** The killed overlay wanted to point scarce review attention where
automation is blind. The claim that died was that a quiet check means a safe region.

**Rebuild.** Every corpus entry and named check declares a coverage scope, expressed only
in the CL-23 facts dimensions (net families, netclasses, part classes, regions); anything
inexpressible there is unscoped and counts as zero coverage. The complement of all
declared scopes is the computed blind map, and review budget splits two ways: a
scope-complement-directed share that hunts declared blind spots, and an unconditional
random blind share that hunts wrong declarations. Run against the 12VHPWR case, this
inverts the original failure: the netclass check's scope is nets in the Power12V class,
the defective lane nets sat outside it, so the complement map points reviewers at them
(power-pattern geometry with no conformance coverage) where the killed overlay pointed
reviewers away.

**Bounds from the confirmation pass.** Scope declarations are schema fields under the
same provenance and signoff regime as everything else; the linter flags suspiciously
broad scopes; over-broad claims get falsified by escapes (RB-07); the random blind share
never shrinks below its floor regardless of how complete coverage claims look; complement
hunting is weighted by the spec's own criticality tiers so it does not drown early.

### RB-02: Constraint pushdown table (amends CL-03)

**Recovered intention.** The dual-target fix wanted one source of truth enforced
everywhere. The general principle underneath: every constraint enforces at the earliest
stage that can express it (generation, then placement, then routing, then DRC, then
review), because late enforcement burns compute on doomed candidates.

**Rebuild.** The compiler maintains a generated, never hand-edited, pushdown table: per
entry, its true earliest horizon and the artifact emitted per stage (DSN netclass
geometry, placer keep-apart row, `.kicad_dru` rule, netlist assertion, review-bundle
note). Residuals that cannot move earlier are recorded and feed RB-01's blind map
honestly.

**Bounds.** Horizon is capped by entry class: promoted Class A and B hard entries may
push to generation and routing; heuristics never push below review time, which compiles
the standing ban on heuristics hardening into gates. Multi-target drift is caught because
each entry's AM-02 fixture runs against every emitted target, so a representation that
diverges fails its own fixture.

### RB-03: Analyst ratification of extraction (amends CL-15, CL-19)

**Recovered intention.** Conclusions-only sourcing killed cherry-picking and quietly
demanded the one thing the analyst-profile model is worst at, writing a clean compressed
conclusion. The original intention, extracting from the whole trace, was right; it lacked
a fidelity guarantee.

**Rebuild.** Conclusions-sourced verdicts remain the default and skip this path. When the
extractor's verdict is sourced outside the conclusions section, or the section is absent
or thin, the verdict goes back to the analyst as a forced choice: the extracted verdict
versus a deterministically perturbed distractor (polarity negated or locus swapped), plus
a neither option. The analyst confirming its own compression is a binary task well inside
even a format-weak model's reliability, and a neither answer escalates rather than
coerces.

**Bounds.** The distractor is generated by deterministic template perturbation, never by
the extractor, so it cannot strawman its own competition. Ratifications batch into the
analyst residency window and are budgeted with the deep path. CL-19's eval gains
ratification cases, and the residual risk (an analyst ratifying a wrong compression of
its own ambiguous trace) is accepted as bounded by the neither-escalation and the eval.

### RB-04: Consent integrity invariant (amends CL-02, CL-10)

**Recovered intention.** The CODEOWNERS fix was one instance of a general invariant: a
consent gate is real only if the approving identity is unreachable from the processes it
gates.

**Rebuild.** Enumerate every consent surface (corpus promotion, spec revision, policy
bounds, golden edits, scope declarations, fab spend) and apply the invariant uniformly:
the owner identity and any spend credential never exist on the night box; approvals
happen from the owner's own devices; the machine account's permissions are listed in a
CODEOWNERS-protected manifest; a weekly audit script reports any credential or permission
on the box that the manifest does not name.

**Bounds.** The confirmation pass found the real threat is convenience erosion, the owner
approving from the agent box because it is nearby, so the design makes the safe path the
convenient one (phone or web approvals) and the audit script exists to catch drift rather
than to prevent a determined owner from undermining their own gate, which no design can.

### RB-05: Diversity floor in outcome space (amends CL-08, CL-24)

**Recovered intention.** The seeds kill (R-01) established that diversity must be
constructed; this rebuild makes it measured, so the portfolio cannot silently collapse
into a mode while reporting healthy candidate counts.

**Rebuild.** Per board per night, a diversity floor over the survivor set (post stage-0),
measured in outcome space: score-vector spread, check-fire fingerprints, routed-topology
hashes. The allocator treats the floor as a constraint alongside budgets.

**Bounds.** Outcome space, never input space, because trivial perturbations inflate input
distance without semantic difference; survivors only, because garbage is maximally
diverse; and the floor decays with RB-06 convergence, because forcing exploration on a
converged front wastes the night.

### RB-06: Convergence as the allocation signal (amends CL-07, CL-08, AM-03, AM-08)

**Recovered intention.** AM-08 defined convergence; this makes it useful: a converged
board releases its budget to unconverged boards.

**Rebuild.** Per-board hypervolume curves, epoch-normalized by the policy-plus-corpus
manifest (a corpus change renormalizes objectives and legitimately resets the curve). The
allocator reads curve derivatives and shifts nightly budget toward the steepest fronts.

**Bounds.** Flatness is portfolio-conditional evidence, never proof: the curve may be
flat because the current operators are exhausted rather than because the board is done.
The allocator's first response to flatness is injecting a novel operator or framing
(cheap); board-converged is declared only when novelty also flattens.

### RB-07: Escape labels on checks (amends AM-01, CL-05; symmetric with SB-09)

**Recovered intention.** The overlay kill rested on checks being wrong about their own
coverage; this gives that failure a feedback channel. Humans calibrate judges; escapes
calibrate checks.

**Rebuild.** Every escape (a defect confirmed downstream of a stage whose declared scope
covered it) writes a label against the specific check and scope claim, into the ledger
and the inbox.

**Bounds.** Labels inform and never actuate: auto-demoting a deterministic gate that is
right the vast majority of the time would be a worse failure than the one being fixed, so
demotion and scope correction remain human-only per CL-05, with the label as the
evidence in front of the owner.

---

# Part 8: Decision forensics

Through Part 7, every decider in the system is calibrated except one. Judges calibrate
against overrides and outcomes (SB-09, CL-12), charters against triage precision (CL-24),
checks against escapes (RB-07). The apex node, the owner, is the only uncalibrated
decider, and the corpus is downstream of every decision that node makes. This part puts
the apex inside the calibration frame, with one risk dominating the design: a system that
learns from decisions will, unless firewalled, learn to please the decider, and bias
stops slipping in and starts being optimized in.

### DF-01: Decision record schema and taxonomy (P0 for capture, S)

**Goal.** Capture cannot be retroactive; the schema lands before the analytics matter.

**Implementation.**
- Taxonomy of decision classes: corpus lifecycle (promote, reject, demote, supersede,
  scope-correct), verdicts (accept, override-up, override-down, escalate), preflight
  dispositions (confirmed-fixed, dismissed-with-reason, accepted-risk), policy changes,
  spec revisions, attribution overrides.
- Per-decision record in the ledger: decision class, artifact (entry ID, candidate hash,
  run ID), decider identity and manifest (human, or model with quant and prompt hash),
  the evidence-bundle hash (exactly what was in front of the decider; a decision is
  interpretable only relative to what was visible), verdict, cited reasons, and a
  counterfactual stub (for a rejected promotion, the fixture and shadow record state what
  the entry would have gated; for an override, what the judge would have shipped).
- Reasons are click-to-cite from the bundle's items rather than free text, which makes
  reason-evidence coherence mechanically checkable (citing evidence absent from the
  bundle is a forensic red flag) and lowers per-decision friction rather than raising it.
- Covariates are ambient only, derived from timestamps the ledger already holds: queue
  depth, session position (decision number within a sitting), per-item elapsed time. No
  additional input is ever demanded of the decider for forensics' sake.
- Consent line in policy for any human whose decisions are captured; today that is the
  owner, and the line exists for the day a collaborator holds a queue.

**Verify.** One morning session produces records whose bundle hashes resolve, whose cited
reasons all exist in their bundles, and whose covariates reconstruct the session timeline
without the owner having typed anything extra.

### DF-02: Blinded decision views (P1, S)

**Goal.** Provenance that is irrelevant to a decision's correctness should be invisible
at decision time and retained in the ledger.

**Implementation.** The promotion view hides which tier or model drafted the entry; the
evidence is the source document, the fixture, and the shadow record, and authorship adds
bias without adding correctness. The verdict view hides generator configs; the judge and
owner rank boards, the bandit reads configs from the ledger afterward. Blinding is a
view-layer property; the ledger stays complete.

**Bounds from the red pass.** Blinding only fields demonstrably irrelevant to
correctness; anything arguably load-bearing stays visible, because hidden relevant
context produces worse decisions in the name of fairer ones.

### DF-03: Consistency probes (P2, S; owner opt-in)

**Goal.** Decision noise (the same case decided differently by the same decider) is
invisible without test-retest, and no existing channel measures it.

**Implementation.** A small declared fraction of each period's queue consists of repeat
probes: previously decided items re-presented, epoch-matched so the corpus and policy
manifest at re-presentation equals the original (a retest against a changed corpus
measures the corpus, never the decider). The owner opts in once in policy and knows
probes exist in aggregate without knowing which items they are.

**Bounds from the red pass.** Disguised probes without standing consent would be the
system deceiving its owner, so the opt-in and the aggregate announcement are
non-optional. Probes spend real review minutes and live inside the AM-05 bandwidth
budget. At realistic decision volumes (tens per week), noise estimates take a quarter or
more to mean anything, and the reports say so rather than narrating thin data.

### DF-04: The forensic analysis pass (P2, M)

**Goal.** Patterns in the decision ledger, surfaced on a cadence, with statistics doing
the finding and models doing only the narrating.

**Implementation.**
- A deterministic statistics layer computes everything reportable: base rates by decision
  class, conditional rates (promotion by source type, by entry class, by board family),
  drift across epochs, session-position effects, reason-evidence coherence failures,
  cross-decider divergence on similar evidence profiles, probe test-retest agreement, and
  the automation-bias signature (owner-judge agreement trending toward unity while
  per-item review time collapses, later contradicted by regret).
- Hard floors: no pattern is reported below a minimum N and effect size, computed
  deterministically. The interpreting model (manager or analyst) narrates only findings
  the deterministic layer flagged; it never mines the raw decision log for patterns,
  which would be the bulk-generation anti-pattern in statistical clothing.
- Once CL-13 outcomes exist, regret becomes the primary lens: false-accept regret
  (promoted entries that misfired, accepted boards that failed bench) versus false-reject
  regret (rejected entries whose defect class later escaped). Regret asymmetry per
  category is the bias measure that matters, because balancing regret requires being
  right while balancing rates only requires counting.
- Findings land as inbox items requiring explicit disposition (acknowledge, contest,
  correct). Ignoring a finding is itself a recorded decision, forensically visible. The
  mirror cannot force a look; it records that none was taken.
- Cadence monthly to quarterly, retrospective always. AM-10 hygiene applies to the
  report text like any model-authored artifact.

**Bounds from the red pass.** Never a live dashboard during decision sessions and never a
rate target, because a decider who watches their own rates starts balancing quotas
instead of judging cases. Reports are read after deciding, not during.

### DF-05: The anti-ratchet firewall (P0 as a standing rule, S)

**Goal.** The user-stated purpose is every tier self-correcting from decision knowledge;
the dominant failure mode of exactly that is tiers optimizing toward
decision-acceptance, drafting entries shaped to pass and framing evidence to please,
which evolves a sycophantic corpus around the owner's revealed preferences.

**Implementation.**
- Two channels, strictly separated. Outcome-validated findings (a decision later
  confirmed or contradicted by bench, field, or escape data) flow to every tier and may
  drive prompt revisions, charter changes, and threshold proposals through the normal PR
  gate. Raw acceptance patterns (what the owner tends to promote, unvalidated by any
  outcome) flow to the owner only.
- Promotion likelihood, acceptance rate, and any proxy of them are banned as optimization
  signals anywhere in the system: never in bandit rewards (which remain cascade survival
  plus confirmed verdicts), never in drafting prompts, never in charter revision
  criteria. The linter-equivalent here is a policy assertion the orchestrator checks: no
  reward or revision config references a decision-rate field.
- Tier-facing correction proposals are PRs like everything else; the forensics layer
  proposes and the gates dispose.

**Bounds from the red pass.** Reason capture is a floor and never proof: click-to-cite
catches citing absent evidence and cannot certify that cited reasons are true reasons.
Human deciding is partially opaque; the system records, it does not mind-read, and the
design claims nothing stronger.

### DF-06: Universal decision capture, every agent and tier (P0 for schema, M)

**Goal.** DF-01 generalized: every decision point in the pipeline (swarm findings, triage
verdicts, extractor selections, manager attributions and routings, judge rankings, bandit
allocations, orchestrator scheduling) produces a forensic record, with the human as one
decider among many rather than the only one observed.

**Implementation.**
- The DF-01 record gains three fields: a machine-readable **claim** (what the decision
  asserts about the world), a **verification hook** from a closed vocabulary (which check
  ID, fixture, bench measurement, or future event settles the claim), and a **settlement
  state** (open, provisional, settled at Grade 1/2/3 per DF-07).
- Capture is tiered by consequence: full records for claim-bearing decisions; aggregate
  counters for high-volume micro-decisions with no standalone claim (per-candidate bandit
  draws aggregate, while a policy-level allocation shift gets a full record). Tiering is
  declared in policy, never improvised.
- A claim without a hook is legal and scores zero forever: it can inform, it can never
  earn. Vagueness becomes reward-neutral instead of reward-positive.

**Verify.** One night yields full records for every swarm finding and triage verdict with
hooks that resolve, aggregate counters for allocation draws, and zero unhooked claims
carrying nonzero reward.

### DF-07: The reward is graded vindication by reality (P0 as a standing rule, S)

**Goal.** The answer to what replaces acceptance: a decision is rewarded when reality
later vindicates its claim, and the gradient always points toward reality, never toward
authority. Authority routes and gates; reality rewards.

**Implementation.**
- Three grades of ground truth. **Grade 1**, physical: bench measurements, field escapes,
  fab outcomes (CL-13). Sparse, slow, decisive. **Grade 2**, deterministic: DRC, parser
  checks, triage confirmation, span matches, golden fixtures. Abundant, fast, narrower.
  **Grade 3**, adjudication by a higher tier or the human: provisional always, re-graded
  whenever Grade 1 or 2 evidence arrives on the same claim.
- This unifies rather than replaces: cascade survival and triage confirmation, the
  existing dense rewards, already are Grade 2 vindications. The new currency renames and
  extends what the bandit and charters consume today.
- Novelty weighting against check-simulation: a Grade 2 confirmation inside
  already-declared scope earns little (redundant with the check that confirmed it); a
  vindicated claim from the RB-01 complement earns much; the largest reward pays when a
  finding becomes a promoted entry **and** that entry's fixture passes **and** it scores
  its first true-positive fire. Promotion is necessary along that path and is never the
  paying event; the post-promotion fire is, which keeps the trigger reality-shaped.
- Banned rewards, extending DF-05: acceptance or its likelihood, agreement with consensus
  (herding pays under it, and the most valuable record in the ledger is the lone dissent
  later proven right), finding volume, and token thrift as a primary signal. The
  orchestrator's policy assertion extends to all of these.

**Verify.** A seeded redundant claim (in-scope, check-confirmable) settles at small
reward; the same defect claimed from the complement settles larger; a synthetic
consensus-agreement reward field in a test policy is refused at load.

### DF-08: Settlement mechanics (P1, M)

**Implementation.**
- Most settlement is synchronous and same-night: triage is the settling event for the
  bulk of swarm claims, so those records open and close inside one run. Open claims (the
  bench-gated and escalated minority) are matched by a settlement pass inside DF-04's
  analysis job, never a new daemon beyond the orchestrator.
- Role separation: no model manifest may both author a claim and be the settling
  authority for that claim's class. The deterministic layer settles Grade 2; where a
  model settles at Grade 3 it must be a different manifest, and Grade 3 is provisional
  regardless.
- Calibration-weighted provisional authority: a decider's weight in Grade 3 settlement is
  proportional to its own settled vindication record. Influence over provisional truth is
  earned from the same currency; final settlement always belongs to reality.
- Per-claim scoring only. When a chain fails (placement to score to judge to bench),
  each link's claim settles as scoped; diffuse chain blame is never computed as reward.
  Chain-level fault narrative is a Grade 3 forensic report for the inbox, written by the
  analyst, consumed by the owner.

**Verify.** A claim authored and settled by the same manifest is rejected at write; a
bench failure settles the FEM margin claim and the judge ranking claim separately, each
against its own scope, with no automatic cross-link penalty.

### DF-09: Tier learning channels and churn control (P1, M)

**Implementation.**
- Counterfactual mining: every Grade 1 or 2 contradiction of a Grade 3 decision becomes a
  labeled case in the contradicted role's holdout pool automatically; the eval sets grow
  themselves from the system's own mistakes.
- Disagreement harvesting: two deciders, same input hash, contradictory claims, later
  settled, yields a paired teaching example; prompt revisions cite these pairs and travel
  the normal PR gates.
- Routing learning: the manager's invocation decisions (which tier, deep or fast path)
  carry claims like any other and settle against whether the routing changed the outcome,
  generalizing CL-19's analyst-usefulness eval to every routing choice.
- Churn control: a role's prompt may change at most once per epoch window, every revision
  passes golden and holdout gates, and manifests keep cross-version statistics from
  pooling silently. Without this, continuous learning makes every forensic comparison a
  comparison of strangers.
- A standing lone-dissent report: vindicated minority claims surfaced per period, because
  they locate undervalued charters and corpus gaps better than any aggregate rate.

**Verify.** A deliberately wrong triage settlement (seeded) lands as a holdout case for
the triage verifier; a prompt revision attempted twice in one epoch is refused.

### DF-10: Agent consistency probes as determinism canaries (P2, S)

**Implementation.** DF-03 generalized to agents, with a sharper payoff: re-presenting an
identical input hash to a pinned local manifest must reproduce the decision, so
divergence is an environment-drift alarm (build, quant, or serving-stack change escaped
the manifest) before it is anything else. For frontier API seats, the same probes measure
nondeterminism, and that measurement bounds the Grade 3 weight their settlements deserve.
Probe volume rides the existing budgets.

**Verify.** A probe against the pinned worker reproduces byte-identical output; the same
probe after a deliberate serving-flag change fires the drift alarm; a frontier seat's
probe variance lands in its calibration record.

---

# Part 9: The process corpus

The owner's counterclaim to the DF-08 volume concern: a massive forensic record is an
asset rather than exhaust, capable of feeding large models and improving a third corpus
over time. The counterclaim is half right and the half that is right changes the design.
Three corpuses now exist by name: corpus one is electrical (what is true about boards,
human-gated), corpus two is the eval pools (goldens and holdout, labeled cases of the
system being right or wrong about specific artifacts), and corpus three is process (how
decisions relate to outcomes: claims, contexts, settlements, grades, lineage). Corpus
three is the only one that grows at machine speed with mechanical provenance, because
every record is born carrying its evidence hash and is labeled by reality at settlement.
What makes it rare as data: vindication labels are reality-supervised, where nearly all
model supervision elsewhere is preference-supervised, which is acceptance-shaped. The
original volume objection survives only as machinery containment: contain the system,
hoard the records.

### PC-01: Corpus definition and custody (P1 for the capture criterion, S)

**Implementation.**
- Contents: the DF-06 records in full for every claim-bearing decision, settlement
  linkage, grade history including re-grades, lineage, manifests. The DF-06 tiering
  criterion shifts accordingly: full capture for anything with a settleable claim
  (training value), aggregate counters only for the claimless.
- Custody: sidecar storage per AM-06, hashes in the ledger, default private. If any of it
  is ever pooled or published, the Appendix D de-identified corpus write is the template
  discipline. Scale arithmetic is unthreatening (thousands of records nightly at
  kilobyte size is gigabytes per year); the expensive parts are indexing and training,
  both addressed below.

**Verify.** A night's claim-bearing decisions all appear in the sidecar with resolvable
hashes; claimless allocations appear only as counters.

### PC-02: Retrieval, the corpus as case law (P2, M)

**Implementation.**
- At decision time, a decider receives the k most similar settled claims (matched on
  scope, charter, claim class, board-family facts), with outcomes. Decisions may cite
  precedent, and precedent citations join the DF-01 reason capture.
- Retrieval bundles must include settled misses (similar contexts whose claims were
  refuted, or that later escaped), never a highlight reel of successes.
- A retrieval-free control arm runs permanently on a declared fraction of decisions, so
  whether case-law context actually improves vindication is itself measured in the DF-07
  currency rather than assumed.

**Bounds from the red pass.** Precedent ossification is the failure mode: deciders
anchored on their own past become more like their past selves, and the corpus only
contains claims somebody made, so its blind spots are inherited. The complement hunting
and blind fractions of RB-01 are what keep injecting off-distribution claims, and the
control arm is what catches retrieval making decisions worse.

### PC-03: Distillation, process regularities into corpus one and policy (P2, M)

**Implementation.**
- The analyst periodically mines for stable regularities (a claim class from a charter in
  a board family settling true at a high rate under a condition) and drafts heuristic
  entries or threshold proposals, through staging and PR gates as always.
- Provenance resolves: the source for a mined regularity is the versioned deterministic
  query plus the hashes of the underlying settled records, which is reproducible. The
  model's narration of the pattern remains derivation context and never the source,
  exactly as analyst traces are treated under CL-18.

**Verify.** One mined regularity lands in staging with a query that re-executes to the
same result set; the linter rejects a sibling entry whose source is the narration alone.

### PC-04: Replay and training, the committed rungs (P2, L)

**Implementation.**
- Replay first, the safe rung: settled records plus manifests allow re-running historical
  decisions under a candidate prompt or model offline, scoring it in vindication currency
  against what actually settled. Before any new judge, verifier, or router manifest
  binds, it replays over the settled history. This converts the corpus into an
  ever-growing eval harness for free and is likely the highest-value consumption mode per
  unit risk.
- Training, the committed rung: vindication-labeled records as supervision for local
  fine-tunes (the 27B verifier class is the natural first target; feasibility on the
  32 GB card is measured at build, never assumed).
- Hard lines from the red pass: **discriminative roles only** (verifier, router,
  settlement-assist) may train on the corpus; generative roles (drafters, swarm
  claimants, the analyst) get retrieval only, because fine-tuning a generator on its own
  vindicated outputs narrows the claim distribution toward past successes and bakes the
  check-simulator failure into weights where reward-level novelty weighting cannot reach
  it. Training labels are **Grade 1 and 2 settlements only**; provisional Grade 3 in a
  training set is acceptance sneaking back in through the weights. Training example
  weights use the **same grade and novelty currency as DF-07**, so the trained verifier
  values what the system values. Records whose settlement meaning a later corpus change
  invalidated are marked **regime-bound** and excluded or epoch-featured, which is the
  fiddliest part of the whole rung and is named here as its main technical risk. Eval
  gates for any trained manifest must include reality-anchored cases quarantined from
  training (the audit fixtures and the newest escapes), because a model trained and
  evaluated on the same distribution shares its blind spots invisibly.
- Meta-Goodhart guard: producing training data is never rewarded. The corpus is the
  exhaust of normal operation; rewards remain DF-07.

**Verify.** A candidate judge manifest replays over settled history and reports
vindication delta before binding; a training run attempted with Grade 3 labels in the set
is refused; a trained verifier's gate includes quarantined audit cases it never saw.

---

# Part 10: Directed routing and the router upgrade

Provenance: verified 2026-06-09 against the Freerouting GitHub releases and README. The
pipeline pins 1.7.0; current stable is the 2.2.x line (2.2.4 referenced by the README and
KiCad plugin integration). Confirmed changes since the pin: copper pour connectivity
fixes, infinite-loop and crash fixes, a board-hash stagnation check, a DSN layer-
initialization fix (Issue #676), a scoring system with JSON result export on the CLI
path, the optimizer re-enabled for CLI and API, an official Python client, Docker images
on GHCR, and multi-threading prepared but not enabled by default. Stewardship note: the
maintainer announced stepping back from active development after v2.1.0, with 2.2.x
continuing as a stability series; design against the DSN/SES file formats and a vendored,
hash-pinned jar, never against promised future upstream features.

### FR-01: Router migration gate, 1.7.0 to 2.2.x (P0 before any overnight scale-up, M)

**Implementation.**
- Vendor the 2.2.4 jar by hash; update `ensure_jar` and `route-prereqs.sh` search paths;
  the jar version joins the determinism manifest, so migration is an AM-03 epoch event.
- Determinism probe before adoption (the DF-10 pattern): identical DSN routed twice on
  2.2.4 must produce identical output hashes; the new stagnation check and hybrid
  strategy may have changed determinism properties, and the diversity design (R-01)
  assumes the router is deterministic per parameter set.
- Param surface revalidation: the 1.7-era CLI arguments and the R-01 spread logic against
  the 2.x settings model (global settings file, CLI overrides); re-verify that the spread
  actually produces distinct candidates on 2.2.4.
- Pour-handling retest on the actual boards: the AM-09 router-ceiling judgment was
  calibrated on 1.7.0-era pour behavior, and the L3 split pours and lane-zone boards are
  exactly the case the 2.2.x connectivity fixes target. Re-measure before inheriting old
  pessimism.
- Adopt the CLI scoring JSON as a stage-0 pre-kill signal (free, arrives with the route);
  `cec_score` remains authoritative and the only scorer the cascade trusts.

**Verify.** Side-by-side route of eps-8pin and 12vhpwr-standard on 1.7.0 and 2.2.4:
completion, DRC count, via count, and pour connectivity compared; two identical 2.2.4
runs hash-identical; R-01 spread yields distinct candidate hashes on 2.2.4.

### FR-02: Route intent compiler (P1, M; one bench test gates the mechanism)

**Goal.** The manager (or the human, or the analyst from a render) expresses where a
route should go; deterministic machinery turns that into constraints the router must
obey. Intent and execution separate, which is the guided-routing pattern commercial tools
ship (route guides, flow planning), with a model in the sketcher's seat.

**Implementation.**
- Intent vocabulary is relational, never coordinates: ordered waypoints as refs, regions,
  and edges ("from J3, along the south edge, between U2 and H2, to U5 pin row"), a layer
  plan, and avoid-regions. The compiler resolves to geometry through the CL-23 facts
  file, which sidesteps model coordinate weakness exactly as CL-21's locating aids do.
- Primary mechanism, fixed waypoints: the compiler materializes short, DRC-legal track
  stubs on the target net at each resolved waypoint, marked fixed; the DSN export carries
  them as immovable wires; the router must connect through them. **Gating bench test
  (VERIFY):** lock a stub in KiCad, export DSN, confirm the wire carries the
  fixed/protect attribute, run headless 2.2.4, confirm the stub survives and is routed
  through. If the KiCad exporter does not emit the attribute for locked tracks, the
  compiler injects it into the DSN directly (one s-expression edit; the parser
  infrastructure already exists).
- Secondary mechanism, sequential corridors, for the few highest-intent nets: temporary
  keepout rule areas carve the corridor's complement, that net routes alone, the result
  is fixed, keepouts lift, next net. Keepouts are global rather than per-net, hence
  sequential and expensive; budgeted to a handful of nets per board.
- Stub hygiene: orphan stubs from failed routes are cleaned in a post-pass; successful
  routes absorb stubs as ordinary net copper.

**Verify.** A directed net on eps-8pin routes through three compiler-placed waypoints on
the planned layers; deleting the intent and re-routing free produces a measurably
different path.

### FR-03: Corridor executor, bounded (P2, L)

**Goal.** The strongest form of the owner's idea: for a fully specified corridor, copper
generation is geometry rather than search, so a deterministic executor lays the trace.

**Implementation.** Input is a resolved polyline, layer plan, and netclass; the executor
emits offset segments at class width, places vias at layer changes, nudges locally within
a declared tolerance, and submits to full KiCad DRC as the only judge of legality.
**Scope bound, non-negotiable:** no search, no improvisation. Blocked beyond tolerance
means fail with the obstacle named, per-net failure attribution back to the manager,
never a creative detour. The bound is what keeps this a few hundred lines of geometry
instead of a second autorouter project, and it doubles as the hedge against upstream
stagnation, since directed nets then depend on nothing outside the repo.

**Verify.** The executor lays a specified two-layer corridor DRC-clean; the same corridor
with a deliberate obstacle inside tolerance nudges around it; outside tolerance it fails
naming the obstacle.

### FR-04: The three-tier routing ladder and the directed control arm (P1, S)

**Implementation.**
- The ladder, extending AM-09: human templates for measurement-integrity nets (locked,
  untouchable), directed routing for important nets (FR-02/FR-03), free autorouting for
  the bulk. Tier assignment is per-net in the board manifest, owner-editable.
- Route intents are claims in the DF-06 sense: "net X along corridor C completes
  DRC-clean and improves metric M," hooked to the DRC result and the score delta, settled
  in DF-07 currency. Vindicated intents become PC-02 case law per board family;
  recurring vindicated patterns are PC-03 distillation candidates.
- The control arm, permanent: directed nets also route free on sibling candidates, and
  directed routing earns or loses its budget by measured vindication against the free
  baseline, never by assumption. If the manager's intent loses to the free router, that
  is a finding, and the mechanism still pays as a cheap compiler for human-sketched
  intent.

**Verify.** One board family accumulates settled intent claims with both arms present;
the allocator's directed-routing budget moves in the direction the settlements point.

---

# Part 11: Global plan and local repair

The observed failure (the loop ending on an unrouted net whose fix was a two-second
human repair) decomposes into a planning problem and a repair problem. The owner's
challenge on simultaneity reframed the planning side as a ladder. The property wanted,
every route decision aware of every other net, has proven realizations that are iterative
with shared state rather than literally simultaneous: negotiated congestion (the IC-world
standard for three decades) and topological-first routing (deciding which side of which
obstacle each net passes, globally, before any geometry exists). The ladder climbs those
on evidence, and AM-12 is the exit condition: stop climbing the moment human-edit
distance hits target for the family.

The ladder: **G1** congestion detection and contested assignment (GR-01) → **G2** full
negotiated congestion (GR-05) → **G3** topological plan (GR-06) → **G4** learned
end-to-end routing, a watch item never a build item; any future learned router enters
only as a manifest through replay and golden gates, and training one on the system's own
routes is Decision 17 territory.

### GR-01: Congestion grid and plan v1 (P1, M)

**Implementation.** A coarse grid over the board from the facts file; demand estimated
per cell from airwire bounding boxes; hotspot detection deterministic. The contested-net
subset gets corridor and layer assignments before routing (manager presiding over the
contested calls), compiled into FR-02 directed intents, contested nets routed first.

**Verify.** A seeded two-net congestion fixture: detection flags the channel; assignment
routes both clean where free routing fails.

### GR-02: Deterministic repair battery (P1, S; runs before any model)

**Implementation.** On a blocked net, the mechanical moves in order: shift each
free-class obstacle in the corridor perpendicular by clearance plus width, layer swap,
via insertion; re-route the single blocked net; full DRC. Cheapest hypothesis first,
the CL-08 pattern again. The observed failure class (a movable blocker) should fall to
this rung with no model call.

**Verify.** The seeded movable-blocker fixture repairs mechanically; the repair claim
settles at Grade 2 in the same run.

### GR-03: Locus repair agent (P1, M)

**Implementation.**
- Bundle: airwire endpoints, every corridor obstacle with net, class, and mobility
  (template and locked immovable, directed renegotiable, free movable), clearance
  numbers, a render crop with CL-21 locating aids. Small context by design; the repair
  problem needs the locus, never the board.
- Closed, copper-only move vocabulary: `shift_segment`, `reroute_net(corridor_intent)`,
  `add_via`, `swap_layer`. At most N moves per plan, K attempts per failure. A shifted
  segment's own net must re-route clean inside the same plan. Component moves are outside
  the vocabulary and attribute upward to placement.
- Execution by FR-02/FR-03 plus a shift primitive; full DRC settles the plan's claim in
  the same run, making repair plans the fastest-settling Grade 2 claims in the system,
  so whether models can do this is measured within days, never assumed.

**Verify.** A seeded blocker fixture beyond the mechanical battery repairs from a model
plan; a seeded capacity-shortfall fixture attributes upward within K attempts.

### GR-04: Repair-to-upstream feedback (P2, S)

**Implementation.** Repair recurrence per pattern per board family flags a plan or
placement hole the repairs keep papering over; the finding drafts a plan heuristic or
placement constraint through staging. Vindicated repairs enter PC-02 case law for future
loci.

**Verify.** Three same-pattern repairs on one family generate one staging draft citing
all three settlements.

### GR-05: Negotiated congestion, the full loop (P2, M)

**Implementation.** PathFinder-style negotiation on the GR-01 grid: all nets plan
iteratively, contested-cell costs rise each round, replanning continues to equilibrium or
an iteration cap; output is corridor and layer plans for every net, deterministic and
seeded so the manifest discipline holds. This is the entire-project-in-mind property at
coarse granularity, implemented sequentially with shared cost state, which is how the
mature field actually does it.

**Verify.** A fixture conflict resolves by negotiation alone with no manager call;
re-running produces the identical equilibrium.

### GR-06: Topological plan rung (P2/P3, L; climb gated by Decision 20)

**Implementation.**
- Homotopy assignment for contested nets: which side of each coarse obstacle, which layer
  span. A rubber-band sketch relaxed for all contested nets together; crossings resolve
  as via insertions or class reassignments; channel capacity checked against the GR-05
  grid so a topologically valid plan is also geometrically plausible.
- Models adjudicate only contested class choices, which are discrete, relational, and
  facts-native (north of U2 versus south of U2 is exactly the representation the tier
  handles well); deterministic relaxation does the bulk negotiation.
- Geometrization through FR-02 and FR-03. Failures fall back to the repair loop, which
  already exists.
- Feasibility rests on the board class: low-to-moderate density, two to four layers, few
  genuine topology choices per board. Explicitly out of scope: a full topological-router
  re-implementation, concurrent geometric optimization, and learned end-to-end routing.

**Verify.** The originally observed failure, replayed: the topological stage assigns the
blocked net its alternate class before routing and the failure never occurs.

---

# Part 12: The capability ladder registry

The routing discussion surfaced a distinction that holds everywhere: every tier is built
from frozen capability (base models, Freerouting, the FEA solver, KiCad DRC, any future
learned router; improves only when someone else retrains or rewrites it) and owned
iteration (corpus, settlements, case law, calibrations, holdout pools; improves from this
project's reality every night). The shipping AI layout tools are frozen capability with
no iteration attached. This system's edge is the inverse, and the iterative harness
doubles as an adoption machine: replay evaluates any future frozen capability against the
entire settled history before it earns a binding. This part makes the classification
first-class so no tier's learning story is implicit.

### CR-01: The registry (P1, S; lands with CL-10)

**Implementation.** A section of `cec-policy.json`, one table: per tier, its frozen
components, its owned-iteration mechanisms, its rungs, current rung, the
vindication-currency metric gating a climb, and the exit condition that stops climbing
(the AM-12 contribution target for the family). Climbs are PRs; the registry absorbs
Decision-20-style climb gates so they stop multiplying as ad-hoc decisions.

**Verify.** The registry loads; the orchestrator refuses a rung the registry does not
mark current; a climb attempt without its gate metric satisfied fails the policy
assertion.

### CR-02: The per-tier ladders (P1 to enumerate, climbs individually gated)

- **Routing:** G1 detection/assignment → G2 negotiated congestion → G3 topological plan
  → G4 learned routing (watch only). Repair rungs: deterministic battery → model agent →
  repair case law → optional trained move-classifier (discriminative, PC-04-legal).
  Already specified in Parts 10 and 11.
- **Placement:** P1 constrained portfolio (CL-09, current) → P2 congestion-aware
  placement against the GR-01 grid → P3 case-law-guided placement and distilled block
  templates per family → P4 learned placement (watch only). Exit:
  placement-attributed failure rate and placement-class edit distance at target.
- **Scoring:** S1 uncalibrated solver plus analytic anchors (AM-04, current) → S2
  bench-calibrated per-family correction (SB-06) → S3 learned surrogates (hotspot and
  DC-IR predictors trained on solver runs settled against bench; discriminative,
  exogenous labels, PC-04-legal; never authoritative, the solver stays judge; surrogate
  earns stage-0 pre-kill duty only) → S4 surrogate-primary stage-0. Exit:
  prediction-versus-bench error inside tolerance. Surrogates are epoch-managed and
  auto-flagged for demotion when bench error drifts out of tolerance.
- **Review (swarm, panel, judge, extractor, analyst):** R1 prompted base models with
  calibration tracking (current) → R2 retrieval augmentation, case law in context
  (PC-02) → R3 trained verifier and judge manifests (PC-04 gates). No R4 for generative
  roles; the Decision 17 moratorium is the ceiling.
- **Corpus:** the lifecycle is the ladder (draft → shadow → promoted) and is already
  built; its progress metric is scope-map coverage per family (RB-01).

### CR-03: Frozen-component adoption protocol (P0 as a standing rule, S)

**Implementation.** Generalizes the G4 rule to every tier: any external frozen
capability (a learned router, a new solver, a new base model) enters only as a manifest,
passes replay over settled history plus the quarantined reality-anchored gate cases,
then runs as a control arm against the incumbent on sibling candidates, earning full
budget only by settled vindication. Replay is in-distribution by construction, which is
exactly why the quarantined reality cases and the control arm are non-optional.

**Verify.** A deliberately weak stand-in component fails at the replay stage; a passing
component appears in the ledger running its control arm before any full-budget night.

---

# Build order and dependencies

1. **CL-01, CL-02, CL-03** (zones and both enforcement points), plus **CL-10** policy file
   and **CL-06** Class A routing. Everything else writes into these.
2. **CL-11** golden seeding, **CL-25** audit-derived check pack and intake gate, and
   **CL-19** extractor fidelity eval. All are protective and buildable today from the two
   audits. **AM-07**'s environment decision and end-to-end golden run land here too,
   before anything else stacks on the venue.
3. Punchlist **R-01, R-02, R-05** if not landed, then **CL-26** minimal viable night for
   measured costs and first signal, then **CL-07** orchestrator and **CL-08** attribution
   (R-12: read PR #18's `cec_loop` first).
4. **CL-04** shadow mode, **CL-12** morning bundle and verdict schema, **CL-21** render
   evidence pipeline, and **CL-23** board-facts serialization (the bundle consumes both).
5. **CL-09** placement portfolio, **CL-14** role contracts, **CL-15/16/17** deep path and
   residency, then **CL-24** swarm verifier tier and **CL-22** adversarial visual panel
   (CL-24 needs CL-23 and the role contracts; CL-22 needs CL-11 fixtures, CL-15
   extractor, CL-21 renders).
6. **CL-05, CL-13, CL-18, CL-20** as they slot; CL-13's schema lands early, its value
   arrives with the next fabbed boards.
7. **CL-19** analyst-usefulness eval once deep-path history accumulates.
8. The Part 7 rebuilds ride their amended items rather than standing alone: RB-02 lands
   with CL-03, RB-04 with CL-02 and CL-10, RB-01 and RB-07 with the corpus schema and the
   coverage work (CL-01, CL-21, CL-25), RB-03 with CL-15, RB-05 and RB-06 with the
   allocator once CL-26's measured costs exist.
9. Decision forensics phases by data availability: **DF-01/DF-06** capture schemas,
   **DF-05** firewall, and **DF-07** reward rule land with the ledger and inbox in step 1
   (capture cannot be retroactive and both rules are cheap standing assertions);
   **DF-02** blinded views with CL-12; **DF-08** settlement with the first nights;
   **DF-03/DF-10** probes and **DF-04/DF-09** analytics and learning channels only once
   decision volume exists.
10. The process corpus phases by rung: **PC-01**'s capture criterion lands with DF-06 in
    step 1 (records not captured now are gone forever); **PC-02** retrieval and **PC-04**
    replay once a quarter of settled history exists; **PC-03** distillation and the
    **PC-04** training rung only after replay has proven the harness and Decision 17 is
    made.
11. Router work: **FR-01** migration gate before any overnight scale-up (Decision 18 sets
    whether the minimal viable night runs first on pinned 1.7.0 for a baseline or
    migrates immediately); **FR-02** intent compiler after its gating bench test passes;
    **FR-04** ladder and control arm with the first directed nets; **FR-03** executor
    only if the waypoint mechanism proves insufficient or upstream stalls.
12. Plan and repair: **GR-02/GR-03** with the first overnight failures (the cheapest wins
    in the whole document); **GR-01** with the plan stage; **GR-05** when repair
    recurrence shows systematic congestion; **GR-06** only on Decision 20 evidence.
13. **CR-01** registry and **CR-03** adoption rule land with the policy file in step 1
    (both are cheap standing structure); **CR-02** rungs climb individually on their own
    gates thereafter.

# Decisions required from the owner before implementation

1. Branch topology and corpus location: staging branch with promotion PRs, or PRs
   everywhere; `corpus/` at root versus under `scripts/constraints/` (CL-01, CL-02).
2. Migration disposition of PR #18's extracted corpus: which entries get the one-time
   re-sign into promoted versus all-to-staging (CL-01).
3. Queue substrate for the orchestrator: GitHub Issues versus file queue (CL-07; same
   decision as SB-02).
4. Golden-regression execution venue: self-hosted runner versus PR #18's container
   (CL-11; same decision as SB-08).
5. M2.7 license path: who reviews the Modified-MIT terms, or stay on the Apache analyst
   indefinitely (CL-20).
6. Deep-path nightly budget: token and wall-clock caps (CL-16).
7. Verdict schema lock: review and freeze the CL-12 field set before agents code against
   it.
8. Visual panel cadence and seats: how many Pareto finalists get the panel nightly, and
   whether the frontier seat runs nightly or only at fab preflight (CL-22; this is an API
   spend decision).
9. Initial swarm charter set, per-night swarm budget, and the precision floor that
   suspends a charter (CL-24).
10. Execution environment for the night shift: WSL2, native Windows, or PR #18's
    container, followed by the one-time end-to-end golden run in it (AM-07).
11. Data egress policy for frontier seats: which artifact classes (board files, renders,
    facts, BOMs) may leave the box to an API, weighed against the open-hardware posture
    and the defensive-publication timing (CL-22).
12. Owner bandwidth budget: stated review minutes per day, and the WIP caps per inbox
    class derived from it (AM-05).
13. Second reviewer for the periodic decision-forensics report: the report is process
    statistics rather than electrical judgment, so a non-hardware second reader (CEC
    Chris is the natural candidate) adds real independence; alternatively accept the
    single-operator residual, recorded as such (DF-04).
14. Probe opt-in and fraction: whether consistency probes run at all, and what share of
    the queue they may consume inside the AM-05 budget (DF-03).
15. Vindication reward weights: the relative pay of Grade 1 versus Grade 2 settlements
    and the novelty multipliers (in-scope, complement, check-creating), since these
    weights shape what every tier learns to value (DF-07; set in policy, changed by PR).
16. Process-corpus custody: retention horizon, private-by-default confirmation, and the
    de-identification rules that would apply if any of it is ever pooled or published
    (PC-01; the Appendix D corpus discipline is the template).
17. The generative-training moratorium: generative roles take retrieval only under PC-04;
    define now what evidence would ever lift that (a holdout regime strong enough to
    detect distribution narrowing), or make the moratorium permanent on the record.
18. Router migration timing: run the minimal viable night on pinned 1.7.0 first to bank a
    baseline and avoid stacking two unknowns, or migrate to 2.2.4 immediately and
    baseline once. Either is defensible; stacking the migration mid-stream is the one
    wrong answer (FR-01, CL-26).
19. Plan-stage depth: ship GR-01 detection-plus-assignment as v1, or jump straight to the
    GR-05 negotiation loop (GR-01, GR-05).
20. The topological climb gate: the quantified evidence that justifies building GR-06,
    for example completion or edit-distance shortfall persisting on a family after GR-05
    plus the repair loop are both in place (GR-06).
21. Registry ratification: a one-time review fixing each tier's starting rung, each climb
    gate's metric, and each exit condition (CR-01, CR-02). After this, climbs are
    ordinary PRs against the registry rather than new decisions.
