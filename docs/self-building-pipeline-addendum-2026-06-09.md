# Self-building pipeline addendum: infrastructure, actuation, and the rules corpus

Suggested in-repo location: `docs/self-building-pipeline-addendum-2026-06-09.md`
Companion to: `docs/agentic-pipeline-review-punchlist.md` (items R-01..R-12). That document
fixes what exists; this one specifies what is missing for the pipeline to be self-building:
durable memory, actuation into physical reality and back, self-maintenance with guardrails,
and the general electrical-rules corpus (including whether and how to build it).

**Baseline:** `main @ e2abe03` plus awareness of PR #18 (`claude/constraint-aware-placer`:
constraint registry, `scripts/constraints/corpus-extracted.json`, checkers, placer, DC-IR,
self-correction loop). Re-verify all landing points against the current tree before building.

## Target pipeline (for reference)

| Stage | Name | Human gate |
| --- | --- | --- |
| 0 | Brief | conversational |
| 1 | Foundation loop + project corpus (provenance-carrying) | sign-off to proceed |
| 2 | Schematic, ERC, BOM/availability | **netlist freeze (blocking)** |
| 3 | Constraint compilation (corpus -> netclasses/.kicad_dru/keepouts/gates) | reviewed with stage 4 |
| 4 | Design frame: stackup, dimension range, mounting | **frame sign-off (blocking)** |
| 5 | Main loop: placement swarm -> feasibility route screen -> routing swarm -> physics ladder -> cascade -> candidates | parks, async review |
| 6 | Loop control: defined convergence, failure attribution, entropy-consuming restarts, budgets | escalation parks |
| 7 | Release: review bundle, freeze, fab snapshot | **release (blocking)** |
| 8 | Write-back: outcomes -> corpora through sign-off gates | gated |

## Operating rules (in addition to the punchlist's)

1. **No new mandatory services.** Every component below must be file-based or GitHub-native,
   per the platform's cold-start and self-host-parity invariants. If a design wants a
   database or a daemon, redesign it.
2. **Consent gates on irreversible actuation.** Anything that spends money, places an order,
   or flashes hardware is modeled as a consent-gated tool (the `agent-core` consent pattern
   from cec-support-agent), regardless of how automated the rest is.
3. **Provenance is mandatory.** No corpus entry, constraint, or calibration value enters the
   system without a source field that resolves to a document, a measurement run, or a named
   human decision. "Model knowledge" is not a source. CI enforces this (SB-14).
4. Decisions marked DECISION are surfaced to the owner, not resolved by assumption.

Priorities: P0 = enables everything else or protects irreversible cost. P1 = required for
the full loop. P2 = needs accumulated history to be useful. Effort: S/M/L.

---

# Part 1: Memory

### SB-01: Run ledger + determinism manifest (P0, M)

**Goal.** Durable, append-only record of every run so restarts, best-attempts, and
cross-session convergence detection have memory, and so "board = f(decision log)" is
actually replayable.

**Landing points.** `DecisionLog` (cec_router), `freeze_build` and the run-mode log
(cec_synth_pipeline), `versions.env`, the artifacts already uploaded by route.yml/synth.yml.

**Implementation.**
- `runs/ledger.jsonl` (or a sibling `cec-runs` repo if churn in the design repo is unwanted;
  DECISION). One line per run: `run_id`, board, mode, input hashes (netlist file sha256,
  constraint-set sha256, corpus version, policy version per SB-10), the determinism manifest
  (KiCad version from versions.env, Freerouting jar version, scripts git SHA), outputs
  (artifact name or path, board sha256), verdict, elapsed, restart lineage (`parent_run_id`).
- Emit the manifest into every decision log too, so a log is self-describing.
- A `scripts/cec_ledger.py` with `append`, `query --board --since`, `lineage <run_id>`.
- Workflows append a ledger line in the collect step (commit to a ledger branch or attach as
  an artifact the orchestrator merges; pick one and document it).

**Considerations.** Append-only; corrections are new lines referencing the old `run_id`.
Keep entries small; large artifacts stay artifacts, the ledger stores hashes and pointers.
Stage-6 convergence (objective improvement < epsilon over N runs) is computed from the
ledger, which is what makes restarts informed instead of amnesiac.

**Verify.** Two route runs on eps-8pin produce two ledger lines with identical manifests and
differing candidate hashes (after punchlist R-01 lands); `lineage` reconstructs a
restart chain.

### SB-02: Inbox: the control plane becomes resumable (P0, M)

**Goal.** Judgments, flags, and human gates become a drainable queue instead of events that
exist only while a chat is open.

**Landing points.** `docs/self-hosted-router.md` already states the session drives GitHub
via MCP; `resolve()` ladder flags; `human_signoff`; route/synth artifacts.

**Implementation.**
- GitHub Issues as the queue. Label taxonomy: `gate:netlist-freeze`, `gate:frame`,
  `gate:release`, `judge:candidates`, `flag:unresolved`, `escalation:human`. Structured
  issue body: run_id, board, links to artifacts/summary, the JudgeContext or flag JSON in a
  fenced block, and the allowed verdicts.
- Producers: workflow steps and the pipeline (on park) open issues. Consumers: an
  orchestrator session (interactive or scheduled headless Claude Code) drains
  `judge:*`/`flag:*`; humans approve `gate:*` issues, from any device.
- Verdicts post back as issue comments in a fixed JSON shape; the orchestrator translates a
  verdict into the next dispatch and appends the decision to the ledger; issue closes.

**Considerations.** This is also the human-gate ergonomics layer: each gate issue carries
the review bundle links (render, metrics table, decision-log summary, diff vs prior). Least
privilege for orchestrator tokens: dispatch workflows, read artifacts, write issues; no push
to main. Depends on punchlist R-04 (verdict surfacing) for good issue bodies, and intersects
PR #18's `cec_loop.py`: read that branch before building the consumer side.

**Verify.** A full loop runs with the session closed between steps: dispatch, runner
completes, issue opens, verdict comment posted, next dispatch fires, ledger shows the chain.

---

# Part 2: Actuation

### SB-03: Footprint acquisition gate (P0, M)

**Goal.** New parts enter `lib/` only through verification, because a wrong footprint is the
cheapest way to scrap a fab run.

**Landing points.** `scripts/vendor-libs.sh`, the easyeda2kicad + kicad-cli upgrade flow
recorded in CLAUDE.md (v3.9 J7 note), `lib/vendor/`, the checklist.sh path rules.

**Implementation.** A named intake step per new part: acquire symbol/footprint/3D, then
produce a verification artifact: pad geometry vs the datasheet land pattern with page
references, pin-1 orientation, courtyard, 3D sanity render. Human-gated on first use
(a `gate:part-intake` issue per SB-02); on approval the part is trusted, and its key
electrical limits enter the corpus (couples to SB-14's per-part pass). Track intake status
in a small `lib/INTAKE.md` or per-part sidecar JSON.

**Considerations.** Automate the comparisons that can be automated (pad count, pitch,
extents vs declared package) and leave the drawing comparison to the human with the
datasheet page linked; do not let an agent self-approve a footprint it generated.

**Verify.** Introduce a deliberately wrong-pitch footprint in a branch; the intake artifact
flags it before any board references it.

### SB-04: Analog block verification (P1, M)

**Goal.** Catch wrong component values and thresholds that copper-level gates cannot see.

**Landing points.** `.gitignore` already carries `spice-*.txt` and `*.raw`, so ngspice work
exists ad hoc; the detection front ends (INA181-class CSA + hysteresis comparator, spec
§6.13) and the Max capture chain are the consumers.

**Implementation.** For boards with analog content, stage 2/3 emits ngspice decks with
vendored models, plus golden expectations (transfer-function points, comparator thresholds
with hysteresis, settling). Run headlessly as a check in the cascade (`ANALOG` stage in the
STAGES registry), flags on deviation. Models are vendored with provenance like footprints.

**Considerations.** Scope to blocks where a wrong value is silent on DRC: sense dividers,
comparator networks, references, filters. Keep golden values in the project corpus with
datasheet/spec sources, never inlined in the check.

**Verify.** Perturb a hysteresis resistor in a test deck; the check flags with the expected
vs simulated threshold.

### SB-05: Fab preflight + consent-gated handoff (P1, M)

**Goal.** Stage 7 ends with the exact upload bundle and a preflight verdict, with spend
behind consent.

**Landing points.** `scripts/fab.sh`, the jlcpcb-formatted BOMs already in
`modules/*/bom/`, `fab/<rev>/` snapshot convention, DFM stage in the cascade.

**Implementation.** A `preflight` step that assembles gerbers + drill + CPL + assembler BOM,
checks them against the target fab's capability profile (a corpus `profile` entry per SB-13,
the same data the constraint compiler reads, so design rules and preflight cannot disagree),
verifies BOM line availability and basic part-to-CPL consistency, and emits a one-page
report. Quote retrieval where an API exists; order placement, if ever automated, is a
consent-gated tool with the quote in the consent prompt.

**Considerations.** The fab profile carries a `retrieved` date; preflight warns when stale
and SB-14's refresh pass re-verifies before order. Panelization and stencil options are
profile fields, not code.

**Verify.** Preflight on the existing 12vhpwr-standard fab snapshot reproduces a pass; a
synthetic profile with tighter min-trace fails it with the offending layer named.

### SB-06: Bring-up protocol + calibration write-back (P1, L; needs hardware)

**Goal.** The self-improving core: measured reality versus the pipeline's predictions, fed
back through gates. Without this stage the corpus only ever learns what simulation already
believed.

**Landing points.** TestPoint footprints in `lib/vendor/`, the electrothermal model whose
own docstring names the IPC constant k as the tuning knob to fit 2152 data, the corpus
current table (stage 3), spec §6.10 co-capture and the golden-sample method, and the fact
that CEC modules are themselves the measurement instruments.

**Implementation.**
- Per released board, generate `bringup/<board>-<rev>/protocol.md` + `expected.json`: rails
  with tolerances, expected current draws by state, thermal predictions per high-current net
  (from ThermalResult), test-point map, firmware smoke sequence (SB-07), and a structured
  `results.json` schema.
- A `cec_bringup.py compare expected.json results.json` that emits deltas and flags.
- Calibration: prediction-vs-measured deltas produce Class C corpus entries (per-stackup,
  per-fab tuned k; measured thermal resistance; via current behavior), written only through
  the sign-off gate (stage 8), each citing the measurement `run_id` in the ledger.

**Considerations.** Results entered by a human or by a CEC Hub harness later; the schema is
the contract either way. Never auto-tune the physics model in place: calibration lands as a
corpus entry the model reads by scope, so an outlier board cannot silently skew every
future prediction (DECISION: minimum sample count before a calibration entry becomes
load-bearing; suggest 2 boards agreeing).

**Verify.** Backfill the protocol for an already-built board (hub-standard proto) and run
compare against its known bring-up numbers; deltas are sane and a calibration entry drafts
with full provenance.

### SB-07: Firmware contract artifacts (P1, M)

**Goal.** Hardware and firmware cannot drift, and bring-up has something to run, without
taking on firmware autonomy.

**Landing points.** Every board carries an ESP-family MCU (one ESP-IDF codebase by spec
v3.9 decision); the netlist parser in cec_synth_pipeline; the frozen netlist from stage 2.

**Implementation.** From the frozen netlist, generate per board: a pin-map artifact (MCU pin
-> net -> function, with the DETECT/CAN/RS-485 roles named from the spec pin table), a
board-support header (`board_<name>.h`) with GPIO/ADC channel defines, and a bring-up
firmware skeleton (rail ADC readout, DETECT read, CAN hello) in a `firmware/` scaffold or a
sibling repo (DECISION on location). Regeneration is idempotent and diffs on netlist change,
so a netlist edit after freeze is loudly visible.

**Verify.** Generate for eps-8pin; the header compiles under ESP-IDF; the pin map matches a
manual read of the schematic for five spot-checked pins.

---

# Part 3: Self-maintenance

### SB-08: Golden-board regression for the pipeline itself (P0, S-M)

**Goal.** Agents already modify the pipeline (PR #17 merged, #18 open); changes to
`scripts/` must prove they still produce a good board before merging.

**Implementation.** A frozen floorplan (eps-8pin copy under `tests/golden/`) + stored
expectation ranges (gates_pass true, drc/unconnected bounds, track/via count bands, thermal
result bands). CI job on `scripts/**` changes: route + score + physics on the golden board,
compare to expectations. This is the spec's golden-sample method pointed at the toolchain.
Runs on the self-hosted runner (needs FR + pcbnew) or, once PR #18's Docker environment
lands, in its container on hosted runners (preferred for PR gating; DECISION).

**Considerations.** Depends on punchlist R-01 (otherwise candidate variance is zero and the
test is weaker than it looks) and pairs with R-03 + protected main with required checks.
Expectation bands, not exact values, so legitimate improvements do not false-fail; band
changes require a human-approved expectation bump in the same PR.

**Verify.** Introduce a deliberate scoring bug in a branch; the golden job goes red.

### SB-09: Judge evals from human overrides (P2, M)

**Goal.** Tier judges (Haiku/Sonnet/Opus) drift when models or policies change; measure them.

**Implementation.** Every human override of an agent verdict (visible in SB-02 issue threads
and the ledger) automatically becomes an eval case: the JudgeContext + the correct verdict,
stored under `evals/judging/`. `cec_judge_eval.py` replays the set against each tier and the
deterministic defaults, reporting agreement and the direction of disagreement
(over-accepting is the dangerous direction; weight it). Run on model or policy version
changes.

**Considerations.** Needs history to be useful; the collection mechanism should land with
SB-02 even though the harness comes later. Strip any large board paths from stored contexts;
metrics only, per the existing reason-on-metrics design.

### SB-10: Policy as code (P1, S)

**Goal.** Judge instructions are versioned artifacts, not string constants.

**Implementation.** Move GATE_NOTE and tier instructions to `scripts/policies/*.md` (or
fold into PR #18's directives if that is what they are; read the branch first). A
`policy_version` (content hash) is recorded in every ledger line and decision log. Policy
changes go through PR review like code and trigger SB-09 when it exists.

**Verify.** Change a policy file; the next run's ledger line shows the new hash; the
decision log answers "which policy judged this" without archaeology.

### SB-11: Spec-to-check traceability (P1, S-M)

**Goal.** When the spec revs, know exactly which checks and corpus entries went stale,
instead of drifting the way the README did.

**Implementation.** `docs/traceability.yaml`: spec section -> check IDs (the `chk_*`
conformance functions) -> corpus entry IDs. checklist.sh gains a rule: every conformance
check appears in the map; every mapped spec section exists in the spec file. A spec diff
plus the map yields the stale-check list mechanically.

**Considerations.** Which spec file is canonical (the repo's v3.10 line vs the v1.0.0
controlled release) is a pending human DECISION; the map should be built against whichever
is designated, and building it will itself surface encode-but-never-specified rules, which
become Class B corpus candidates (SB-14).

### SB-12: Budget governance (P2, S)

**Goal.** Cautious posture applied to resources: tokens, runner hours, restarts, fab spend.

**Implementation.** The stage-0 brief declares an envelope; the ledger accumulates per
project; dispatch refuses (and opens an `escalation:human` issue) when an envelope is
exceeded. `agent_route`'s per-loop budget stays; this is the project-level wrapper. Restart
count caps live here too (stage 6).

---

# Part 4: The general electrical-rules corpus

### SB-13: Verdict, schema, and lifecycle (P0 for the schema, M)

**Is the cross-project corpus a good idea?** Scoped narrowly: yes. As a grand transcription
of electronics knowledge: no. The reasoning, stated plainly so the implementing agent does
not over-build:

- Most general electrical rules already live in authoritative external sources (IPC-2221/
  2152/7351, fab capability pages, manufacturer datasheets and app notes). Transcribing them
  creates a maintenance burden and a drift problem: the copy rots while the source revs. The
  repo has already paid this tax once (README vs spec); do not build a second instance of it.
- Parametric rules are formulas, and code captures formulas better than data does. dt_ipc IS
  the IPC-2221 rule; the corpus should hold its parameters, applicability conditions, and
  citations, never a prose restatement of the formula.
- The genuinely valuable, unduplicable entries are: (a) measured/calibrated constants from
  your own boards (SB-06), and (b) the platform's hard-won decided rules promoted from
  project corpora with spec provenance. No external source has either. That is what the
  general corpus is for.

**Entry classes.**
- **Class A, pointer/parameter:** a citation to an authoritative source plus the inlined
  parameter values needed by code, with retrieval date and a re-verification cadence.
  Example: fab min trace/space/via for a capability class.
- **Class B, platform rule:** promoted from a project corpus or extracted from the spec,
  carrying the spec-section source. Example: TIM pad + bare contact land under EPS/PCIe
  shunts (§6.6); fixed 120R split CAN termination at the Hub.
- **Class C, calibrated:** measured constants with the measurement run_id. Example:
  tuned IPC k for JLC 4-layer 1 oz outer; measured via thermal behavior.
- **Heuristic (prose):** judge-facing rationale. Consumable by LLM tiers only.

**Schema (one JSON object per entry, one file per domain under `corpus/general/`):**

```json
{
  "id": "thermal.k_ipc.jlc4l_1oz_ext",
  "class": "C",
  "kind": "param",
  "scope": {"fab_profile": "jlc-standard-4l", "copper_oz": 1, "layer": "external"},
  "value": 0.051,
  "units": "ipc2221-k",
  "applies_to": ["physics"],
  "source": {"type": "measurement", "ref": "run:R-0042 bringup:12vhpwr-std-v1", "date": "2026-07-xx"},
  "status": "bringup_validated",
  "supersedes": null,
  "notes": "fit over 3 nets, max residual 4.1 C"
}
```

**Lifecycle:** `proposed -> sim_validated -> bringup_validated | human_approved ->
promoted -> deprecated`. The constraint compiler (stage 3) and the physics model emit
BLOCKING artifacts from entries in the `promoted/` ZONE and advisory (`ADV-`) artifacts from
`staging/` — selection is by ZONE, never by the `status` string (`status: promoted` is the
lifecycle marker, not the selector); `proposed` entries are visible to judges as context,
never compiled into hard gates. Prose heuristics never become deterministic gates by any path.

**DECISION (owner):** does the general corpus stay in the open repo (PR #18's
corpus-extracted.json is currently headed that way, and the spec it derives from is public)
or do calibrated fab/process constants (Class C) eventually move private, mirroring the
support agent's open-engine/private-corpus split? Specify before Class C accumulates.

### SB-14: Manufacturing the corpus (P1, M then ongoing)

How the corpus gets built, in passes, each with provenance discipline:

1. **Seed extraction (one-time, M).** Extract rules already paid for: the spec's decided
   rules (every LOCKED item with a numeric consequence), the `chk_*` conformance checks
   (reverse-extract what they encode; this co-produces SB-11's traceability map), the
   .kicad_dru writers, and the datasheet figures already cited in the FPGA backing doc.
   Audit PR #18's `corpus-extracted.json` first: if its entries lack source fields, the
   first task is retrofitting provenance, not adding entries.
2. **Standards/parameter pass (S per domain).** For IPC-class rules: formulas stay in code;
   corpus-entry the parameters and applicability conditions with citations. For fab rules:
   record the published capability page values with URL + date; a refresh job re-fetches,
   diffs, and flags changes (and SB-05 preflight warns on staleness before any order).
3. **Per-part pass (continuous, coupled to SB-03).** When a part passes footprint intake,
   its key electrical limits (abs-max, derating, thermal) enter the corpus with datasheet
   page references. Corpus growth rides the part-intake gate, which is what keeps provenance
   honest with zero extra ceremony.
4. **Promotion pass (continuous, human-reviewed).** Project-corpus entries that prove
   general are promoted deliberately, one review per entry, which is what keeps the
   two-corpus separation meaningful.
5. **Calibration pass (continuous, via SB-06).** Class C entries through the sign-off gate.
6. **Corpus linter (CI, S).** Schema validation; reject entries with no source or with
   `source.type: "model"`; stale-date warnings per class cadence; orphan detection (every
   `applies_to: compiler/physics` entry is consumed by at least one rule, or is marked
   informational); duplicate-scope conflict detection.

**Anti-patterns, banned explicitly:**
- Bulk LLM generation of electrical rules from model memory. An agent may draft an entry,
  but the linter rejects anything without a resolvable source. (This encodes the project
  owner's standing working rule: present real data; verify against datasheets.)
- Transcribing standards charts wholesale into data. Encode the formula, cite the chart.
- Letting a heuristic entry harden into a gate because a judge quoted it often. Promotion
  to gate status is a human action that changes the entry's class.

**Verify.** Linter green on the seeded corpus; one end-to-end thread demonstrated: a spec
rule -> Class B entry -> compiled into a board's .kicad_dru -> enforced in a route run ->
cited by ID in the decision log.

---

# Build order and dependencies

1. **SB-01 ledger + SB-02 inbox** first; everything else writes into them.
2. **SB-08 golden regression** second (agents are editing the pipeline today); depends on
   punchlist R-01 and R-03.
3. **SB-13 schema + SB-14 pass 1 and the linter** third; the constraint compiler and PR #18's
   registry need a disciplined source of truth before they accrete sourceless entries.
4. **SB-03 footprint gate + SB-05 fab preflight** fourth; they protect irreversible spend.
5. **SB-07 firmware contracts, SB-04 analog checks, SB-10 policy, SB-11 traceability** as
   they slot in.
6. **SB-06 bring-up calibration** when the next fabbed boards exist to feed it.
7. **SB-09 judge evals, SB-12 budgets** once override and spend history accumulates.

# Decisions required from the owner before implementation

1. Ledger location: in-repo `runs/` vs sibling repo (SB-01).
2. Open vs eventually-private Class C corpus data (SB-13).
3. Canonical spec line for the traceability map (SB-11; the v3.10 repo file vs the v1.0.0
   controlled release).
4. Golden-regression execution venue: self-hosted runner vs PR #18's container (SB-08).
5. Firmware scaffold location: in-repo `firmware/` vs sibling repo (SB-07).
6. Minimum sample count before a Class C calibration entry becomes load-bearing (SB-06).
