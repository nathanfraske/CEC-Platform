# Agentic-pipeline review punchlist

Suggested in-repo location: `docs/agentic-pipeline-review-2026-06-09.md`

**Baseline:** `main @ e2abe03` (2026-06-06). Line numbers below are pinned to that commit;
after PR #18 merges, re-anchor by symbol name, not line number.

**Provenance:** findings come from a full read of the pipeline chain (`cec_dispatch`,
`cec_router`, `cec_route`, `cec_fr`, `cec_score`, `cec_synth_pipeline`, both workflows, both
PowerShell wrappers, prereq scripts, hooks), `py_compile` over all 24 scripts, execution smoke
tests on a KiCad-less Ubuntu 24 box, and the GitHub API/diff for PR state. Claims marked
VERIFIED were reproduced; claims marked UNVERIFIED were not. Re-verify each item against the
current tree before changing anything; do not take this document's word over the code.

## Operating rules for the implementing agent

1. The spec wins. Nothing here overrides `CEC-Platform-Ground-Truth-Spec.md`; where an item
   touches a design decision (R-03 especially), surface it for human sign-off instead of
   resolving by assumption.
2. **Do not duplicate PR #18** (`claude/constraint-aware-placer`). It already adds: a Docker
   routing environment (`docker/`), a constraint registry + corpus
   (`scripts/cec_constraints.py`, `scripts/constraints/corpus-extracted.json`), hard checkers
   (`cec_hc.py`, `cec_verify_hc.py`), a placer (`cec_place.py`), DC-IR (`cec_dcir.py`), a
   self-correction loop (`cec_loop.py`), plotting, and `dispatch.ps1`, plus edits to
   `cec_dispatch`, `cec_router`, `cec_fr`, and `cec_synth_pipeline`. Before implementing
   anything adjacent to the `where="runner"` TODO (see R-12), read that branch first.
3. Behavior-affecting changes to scoring, gating, or candidate generation must show
   before/after evidence on a real board (eps-8pin or 12vhpwr-standard) in the PR body.
4. Before pushing: `python3 -m py_compile scripts/*.py`, `scripts/checklist.sh`, and
   `scripts/check-all.sh` (per CLAUDE.md / README contributing rules).
5. Items needing kicad-cli, pcbnew, or java are tagged RUNNER; everything else runs anywhere.

Priorities: **P0** = real compute or assurance loss today. **P1** = robustness and operability.
**P2** = polish. Effort: S (< 1 h), M (half day), L (multi-day).

---

## P0

### R-01: Seed diversity is a no-op on the default path (P0, M, RUNNER to verify)

**Evidence (VERIFIED by code read; matches the repo's own comments).** Freerouting 1.7.0 is
deterministic; identical params produce identical candidates (acknowledged at
`cec_router.py:417-421`). `cec_router._mkparams` (`cec_router.py:422-429`) returns the same
base params for every seed whenever `opt_spread == 0`, and `opt_spread` defaults to 0 in
`route.yml`. `cec_dispatch.request_candidates` passes `params=(lambda s: dict(params))`
(`cec_dispatch.py:99`), a constant for all seeds. Net effect with shipped defaults:
`route.yml` seeds `0,1,2,3` runs four identical Freerouting candidates per iteration, and
candidates mode hands the judging tier duplicate boards. `cec_fr._DEFAULT_SEED_SPREAD`
(`cec_fr.py:709`) exists for exactly this (`params=None` path, `_resolve_params` at
`cec_fr.py:754`) but both callers bypass it.

**Recommended fix.**
- In `cec_router.route`: when `opt_spread == 0` and `len(seeds) > 1`, pass `params=None` to
  `generate_batch` so the built-in spread applies, or derive a local (passes, opt_time)
  spread. Keep current behavior when a session supplies explicit per-seed params.
- In `cec_dispatch.request_candidates`: when given a single params dict and multiple seeds,
  expand to a per-seed spread around the requested values (for example opt_time scaled across
  0.5x to 1.5x), and record the **resolved** per-seed params in each `CandidateMetrics.params`
  (today every candidate records the same dict, so the judge cannot see the spread).
- Cheap adjunct: content-hash (sha256) dedupe of candidate boards before scoring, since
  scoring is the expensive step (see R-02).

**Considerations.** This changes default candidate generation, so decision logs will differ
from past runs; that is the point, but bump a `spread` note into the log entry
(`cec_router.py:439`) so the change is self-documenting. Do not alter the explicit-callable
contract of `generate_batch(params=callable)`. PR #18 touches both files (+60/+30 lines);
rebase first.

**Verify.** On a runner: route eps-8pin with seeds `0,1,2,3`, `opt_spread=0`, and assert at
least two distinct sha256 hashes among `candidate_seed*.kicad_pcb` (today: all identical).
Headless: unit-test the params-selection branch with a stubbed `generate_batch`.

### R-02: Every scored board is DRC'd twice (P0, M, RUNNER to verify)

**Evidence (VERIFIED by code read).** `cec_score.score` runs its own kicad-cli DRC and exposes
`drc_json=` (`cec_score.py:269`) explicitly to avoid a redundant run. `cec_dispatch` calls
`score(c.board)` then `_drc_types(c.board)` (`cec_dispatch.py:105-106`, `_drc_types` at
`:55`), a second full DRC on the same board. In the cascade, `View.metrics`
(`cec_synth_pipeline.py:330`, score → DRC) and `View.drc()` (`:335`) are separate runs of the
same check.

**Recommended fix (option A preferred).**
- A: extend `cec_score.Metrics` with `drc_types: dict` and `drc_loci: list`, populated from
  the JSON `score` already parses. Delete `_drc_types` from `cec_dispatch`; have
  `View.metrics` feed `View.drc()` consumers.
- B (smaller): run DRC once in the caller, pass the JSON path via `drc_json=`.

**Considerations.** `DecisionLog._m` (`cec_router.py:128-134`) serializes Metrics field by
field; extend it if fields are added. The cosmetic filter is a stated invariant ("MUST match
cec_route.verify", `cec_score.py:16,31`): consolidate `_COSMETIC`/`_FINISHING` from
`cec_dispatch.py:46-51` into `cec_score` and import, so there is one filter (see R-09).
Temp-file names keyed on `os.getpid()` (`cec_dispatch.py:58`) collide under in-process
concurrency; switch to `tempfile.mkstemp`.

**Verify.** Shim kicad-cli with a logging wrapper on PATH, run
`cec_dispatch.py request-candidates --seeds 0,1`, count `pcb drc` invocations: expect one per
candidate, not two. Confirm the candidates JSON payload is unchanged or extended only.

### R-03: The CI ERC/DRC gate currently checks zero boards (P0, S code / decision required)

**Evidence (VERIFIED by execution on 2026-06-09).** All nine directories containing design
sources carry a `DRAFT` marker (`hubs/hub-pro`, `hubs/hub-standard`, all seven `modules/*`);
`check-all.sh` skips ERC and DRC on DRAFT, so `kicad-checks.yml` effectively runs only
`audit-sch.py` plus `checklist.sh`. Meanwhile `fab/12vhpwr-standard-proto-v1/` and
`fab/hub-standard-proto-v1/` hold shipped gerbers for boards whose sources are never DRC'd in
CI. Separately, the Actions API returned zero workflow runs for the repo (unauthenticated
query, 2026-06-09), so it is possible Actions is disabled entirely; that cannot be confirmed
or fixed from inside the tree.

**Recommended fix.** Two-part:
1. Code: add a rule to `check-all.sh` that a board is always checked, DRAFT or not, when a
   `fab/<rev>/` snapshot exists for it (or introduce an explicit `FABBED`/`RELEASED` marker
   that overrides `DRAFT`). Mechanical and reversible.
2. Decision (human): which boards graduate out of `DRAFT` now. Recommend at minimum the two
   fabbed boards. Do not delete markers unilaterally; per repo rules, surface it. Expect CI to
   go red on graduation (known divergences exist, for example the 24-pin VCC parallel path
   slated for rev3); red is the desired signal, but the owner should ack it.
3. Flag to the owner: confirm GitHub Actions is enabled for the repo; with no run history,
   none of the gates fire on push regardless of markers.

**Verify.** `scripts/check-all.sh` output shows ERC/DRC lines executing for graduated boards;
a branch push produces a kicad-checks run.

### R-04: Surface run verdicts; document the synth/candidates contract (P0, S)

**Evidence (VERIFIED by code read).** A run-mode pipeline ending "sign-off withheld" exits 0
by design (`cec_synth_pipeline.py` main, comment near the return) and looks identical to
RELEASED on the workflow page; the verdict lives only inside the uploaded artifact. Candidates
mode returns results by log-scraping between `===CEC_CANDIDATES_JSON_BEGIN/END===` markers
(`cec_dispatch.py:271-273`), which works but is sensitive to log interleaving and retention.
`docs/self-hosted-router.md` documents `route.yml` only; the synth modes and the marker
contract are undocumented.

**Recommended fix.**
- In `route.yml` and `synth.yml`, add an `if: always()` step appending to
  `$GITHUB_STEP_SUMMARY` (`$env:GITHUB_STEP_SUMMARY` in the Windows steps): for route, the
  `final` block of the decision log; for synth run, the pipeline status line; for candidates,
  the `candidates.json` body in a fenced block (truncate; summary cap is 1 MiB).
- Do not change the BEGIN/END markers; they are the orchestrator contract.
- Extend `docs/self-hosted-router.md` with a "Synthesis workflow" section: the three modes,
  artifact layout (`build/candidates|synth|release/<board>/`), and the marker contract.

**Verify.** Dispatch each mode once; the run Summary panel shows the verdict without
downloading the artifact.

---

## P1

### R-05: kicad-cli absence crashes instead of degrading (P1, S)

**Evidence (VERIFIED by execution, 2026-06-09, Ubuntu 24 box without KiCad).**
`python3 scripts/cec_synth_pipeline.py --board eps-8pin` tracebacks with `FileNotFoundError`
at `View._export_netlist` (`cec_synth_pipeline.py:321-326`), despite the module header's claim
that non-route stages survive a missing toolchain (pcbnew IS guarded; kicad-cli is not).
Same exposure class: `cec_score._run_drc` (`cec_score.py:134`), `cec_dispatch._drc_types`
(`:59`) and `render` (`:126`), `cec_router.render` (`:542`), `run_sweep` render
(`cec_synth_pipeline.py:2361`), `View.drc/erc`.

**Recommended fix.** One helper in `cec_score` (already imported by all three callers, so no
new import cycle): resolve `shutil.which("kicad-cli")` once. Policy per call site: DRC/ERC and
netlist-for-scoring fail fast with the same actionable hint `route-prereqs.sh` prints; netlist
export in the cascade and the render helpers degrade (empty Netlist / `None`) with a single
warning, preserving the header's promise.

**Verify.** Re-run the exact repro on a KiCad-less box: expect either a clean degraded stage
report or a one-line actionable error; no traceback.

### R-06: Prereq script over-requires xvfb; java message mismatch (P1, S)

**Evidence (VERIFIED by code read).** `route-prereqs.sh:58-63` hard-fails any non-Windows
runner missing `xvfb-run`, but `cec_fr._fr_command` (`cec_fr.py:81-82`) wraps in xvfb only on
Linux with no `$DISPLAY` and only if `xvfb-run` exists; macOS and display-attached Linux never
need it, yet fail prereqs. Also `route-prereqs.sh:10` says "java 21+" while the check at `:49`
accepts 17+ and its own message says "needs java 17+ (21 recommended)".

**Recommended fix.** Make the xvfb check `bad` only when `uname = Linux` and `DISPLAY` is
empty; informational note otherwise. Align the header comment to the 17+/21-recommended
wording the check enforces.

**Verify.** Run `route-prereqs.sh` on macOS or a DISPLAY-set Linux session: passes. Headless
Linux without xvfb: still fails with the install hint.

### R-07: Workflows cannot dispatch atx-24pin-rev2 (P1, S)

**Evidence (VERIFIED).** Board `options:` in `route.yml:29-34` and the matching list in
`synth.yml` offer `atx-24pin` only; `modules/atx-24pin-rev2/24pin-module.kicad_pcb` exists and
`find_board` would resolve it. rev2 is the current 24-pin line (it carries
`QUILTER-CONSTRAINTS.md`, `RAIL-PLAN.md`, `LAYOUT-GUIDE.md`).

**Recommended fix.** Add `atx-24pin-rev2` to both choice lists. Decide (human) whether the
superseded `atx-24pin` stays listed. If Freerouting is run on rev2, honor the same locked
placements the Quilter constraint set names (connectors, shunts, INAs, U1 region); the FR path
must not move what Quilter is forbidden to move (placement edits are sanctioned only through
`apply_edit`).

**Verify.** workflow_dispatch shows the option; a candidates run on rev2 emits metrics.

### R-08: Edge guards in the dispatch loop and CLI (P1, S)

**Evidence (VERIFIED by code read).**
- `cec_dispatch.py:252-257`: board glob then `sorted(cands)[0]` raises bare `IndexError` when
  a module dir has no floorplan; `cec_router.find_board` (`cec_router.py:501-512`) already
  implements the same lookup with a helpful error and the same skip rules. Duplicated logic.
- `agent_route` (`cec_dispatch.py:185-187`): an `accept` verdict against an empty candidate
  list returns `None` as the accepted candidate without distinguishing it from success; an
  `accept` naming an unknown seed silently falls back to `cands[0]`.
- `request_more` with `budget_left == 0` is coerced to escalate (`:188-193`) without recording
  the coercion, so an LLM tier's stated intent is lost from the log.

**Recommended fix.** Import and use `cec_router.find_board` in the dispatch CLI. In
`agent_route`: treat accept-with-no-candidates as escalate with a logged reason; log a
`note: seed fallback` when the named seed is absent; log `note: budget-coerced escalate` on
the coercion path. The `request_fn` injection hook (`:168`) already enables headless unit
tests; add three covering these branches.

**Verify.** `python3 scripts/cec_dispatch.py request-candidates --board hub-enterprise` gives
the friendly error; unit tests pass with the stub.

---

## P2

### R-09: Finishing/cosmetic filter is free-text substring matching, defined twice (P2, M)

**Evidence (VERIFIED by code read).** `_is_finishing_only` (`cec_dispatch.py:198-207`) decides
acceptability by searching DRC item description text for `LOGO`, `SH1`, `SH2`, `SHIELD`;
descriptions are KiCad-version and wording dependent, and a future real net containing
"SHIELD" would be waved through. `_COSMETIC`/`_FINISHING` live in `cec_dispatch.py:46-51`
while the parity-critical cosmetic list lives in `cec_score` ("MUST match cec_route.verify",
`cec_score.py:16,31`). This filter is part of the judge contract (GATE_NOTE,
`cec_dispatch.py:131-137`), so changes alter accept decisions.

**Recommended fix.** Single source: move both token lists into `cec_score`; match on the
structured fields of the DRC JSON (item refs/nets) where present, falling back to description
text; name the shield-tab refs explicitly. Land with before/after structural-violation counts
on 12vhpwr-standard (a committed `DRC.rpt` exists in-tree as a cross-check) and update
GATE_NOTE wording in the same commit.

### R-10: Cross-reference cec_route vs cec_router; reconcile the stop-hook claim (P2, S)

**Evidence.** `cec_route.py` (hand-routing primitives for the sub-agent routing pass) and
`cec_router.py` (the orchestration loop) are one letter apart; both live, both documented, an
agent can grab the wrong one. Separately, `cec_fr.py:33` claims "a stop-hook checks" that
Freerouting's `logs/` never lands in the repo, but `.claude/settings.json` defines only a
SessionStart hook; whether the `kicad-happy` plugin contributes a Stop hook is UNVERIFIED from
this review. The `.gitignore` `logs/` entry is the backstop that definitely exists.

**Recommended fix.** Two-line "you may want the other file" note at the top of each module (no
rename; CLAUDE.md and README-cec_pcb reference both heavily). Inspect the kicad-happy plugin's
hooks: if no Stop hook exists, amend the `cec_fr.py` comment to cite `.gitignore` (or add the
hook if the protection is wanted).

### R-11: README pipeline sections drifted from the tree (P2, S)

**Evidence (VERIFIED).** README's board table and layout listing name `modules/atx-24pin` and
`modules/pcie-8pin` where the tree holds `atx-24pin` + `atx-24pin-rev2` and
`pcie-8pin-2port`/`-3port`; the scripts table documents the kicad-cli wrappers but none of the
Python plane (`cec_router`, `cec_synth_pipeline`, `cec_dispatch`, `cec_fr`, `cec_score`) or
the two self-hosted workflows; the working-summary date (2026-05-30) predates the v3.10
CLAUDE.md line. Fix the layout/table/tooling rows mechanically from the tree. Leave spec
version statements alone: which spec line is canonical (the repo's v3.10 file vs the v1.0.0
controlled release living outside the repo) is a pending human decision, out of scope here.

### R-12: `where="runner"` dispatch TODO. Check PR #18 before building (P2, gate on review)

**Evidence.** `request_candidates(where="runner")` raises `NotImplementedError`
(`cec_dispatch.py:96-97`); the budgeted `agent_route` loop is import-only (no CLI), so loop
state lives in the driving session rather than one decision log. PR #18 adds `cec_loop.py`
(~253 lines), `dispatch.ps1`, and ~60 lines to `cec_dispatch`; from the diff stats this is
adjacent or identical territory. **Action: read that branch first.** Only if it does not close
the gap, implement runner dispatch (gh workflow run + artifact poll, or marker scrape) inside
`request_candidates`, and persist `agent_route`'s log to disk per iteration so session-driven
judging accumulates into a single replayable record.

---

## Explicitly out of scope (already in PR #18)

Docker routing environment, constraint registry/corpus, hard checkers, DC-IR, the placer, the
self-correction loop, `dispatch.ps1`. Do not re-implement; rebase on or review that branch.

## Verification quick reference

| Item | Needs | One-line check |
| --- | --- | --- |
| R-01 | RUNNER | distinct sha256 across `candidate_seed*.kicad_pcb` at opt_spread=0 |
| R-02 | RUNNER | kicad-cli shim counts one `pcb drc` per candidate |
| R-03 | host | `check-all.sh` runs ERC/DRC on fabbed boards; a push triggers a CI run |
| R-04 | runner | run Summary shows verdict / candidates JSON |
| R-05 | anywhere | `cec_synth_pipeline.py --board eps-8pin` exits clean without KiCad |
| R-06 | mac/desktop | `route-prereqs.sh` passes where xvfb is genuinely unneeded |
| R-07 | runner | rev2 dispatchable, candidates emitted |
| R-08 | anywhere | unit tests on agent_route branches + friendly find_board error |
| R-09 | RUNNER | before/after structural counts on 12vhpwr-standard match intent |
| R-10/11 | anywhere | doc diff only; `checklist.sh` stays green |
| R-12 | n/a | PR #18 review note before any code |
