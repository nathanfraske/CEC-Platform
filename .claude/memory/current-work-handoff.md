# Current work handoff

_Updated 2026-06-13 ~10:55 CDT (status-check + cleanup + V4 capstone running)._

## STATUS CHECK + CLEANUP 2026-06-13 ~10:55 CDT (read this first)
**The intended overnight `cec_fullstack` run COMPLETED NATURALLY ~10:03** — full 7 h (02:51→10:03), 35 rounds,
morning bundle (`docs/fullstack-run-2026-06-13/bundle.json`, `end_of_run_review:true`, `DONE:` at run.log:716)
+ REVIEW.md (1.7 MB) + per-seat streams. **Result: did NOT converge** — `gate_passing:0`, `pareto_finalists:0`;
stuck in a local minimum (pours clipped by routed traces in 32/34 rounds → "notched-corridor keepout / re-pour-
after-route"; drc not improving; panel escalating; max_T 271–297 °C). V4 auditor worked rounds 1–~22 (injected 4
governance rules, rounds 8 & 12) then **CRASHED ~08:51 on a CUDA assert** (`GGML_ASSERT(stat==cudaSuccess)`,
ggml-cuda.cu:3445 — not OOM); rounds 23–34 ran on the deterministic auditor stub.

**ACTIONS TAKEN this session (all done):**
1. **Killed the redundant watchdog relaunch** (PID 310300) — the watchdog had misread the clean 10:03 exit as a
   crash and relaunched a fresh daytime run from round 1 with no V4. Gone.
2. **Killed the watchdog** (`cec_night_watch.sh` PID 139208) — it was still alive (ends ~11:13) and would have
   re-relaunched within 10 min.
3. **Patched the watchdog** `scripts/cec_night_watch.sh`: added a phantom-relaunch guard — `relaunch_run()` now
   refuses to relaunch if a `^[..:..] DONE:` marker is present in run.log, and latches `run_done=1`. A completed
   run is produced exactly once; a genuine crash (no DONE) still relaunches. Syntax-checked.
4. **Restarted V4** Windows-native (`E:\toolchain\run-v4-flash.bat`). Freed RAM first: stopped
   `docker-worker-volume-vision-1` + WSL cache reclaim → Windows free 140→165 GB (bat preflight needs ≥145).
   V4 `/health`=200 in ~75 s (its pages were still in standby from the morning). Broker→:8007 path smoke-tested OK.
   (`manager-fast` had already dropped off.) NOTE: worker-volume-vision is STOPPED — restart it before the next
   `cec_fullstack` run (broker can start it on demand, or `sg docker -c 'docker start docker-worker-volume-vision-1'`).
5. **V4 CAPSTONE of the completed run — RUNNING** (owner ask "have V4 do the capstone check"). New committed-WIP
   driver `scripts/cec_fs_capstone.py`: assembles a FACTUAL dossier (bundle + first-run measurement trajectory +
   per-round auditor findings + final-board metrics), corpus-briefed exactly like the in-loop seat, and calls
   deepseek-v4-flash via the broker. Output → `docs/fullstack-run-2026-06-13/CAPSTONE-v4.{json,md}` (reasoning to
   streams/capstone.jsonl). Run it again: `python3 scripts/cec_fs_capstone.py --run-dir docs/fullstack-run-2026-06-13`.
   An independent Claude multi-agent cross-check is running in parallel to adversarially verify V4's verdict.

**NOT yet committed:** `scripts/cec_fs_capstone.py` + the `cec_night_watch.sh` patch (will offer to the owner).

### VERIFIED BUG found by the capstone cross-check (the night's real finding) — item4 corridor-avoid lever DEAD all 34 rounds
The loop's primary REACTIVE actuator for the dominant failure class (pour clipping) **fired zero times** due to a
dict key-name mismatch — VERIFIED at source + in run.log (not just an LLM claim):
- `cec_fr.derive_power_pours` emits pour dicts keyed `{"net","layer","polygon"}` (cec_fr.py:617-618) — NO `rect_mm`.
- `cec_fr02.clipped_corridor_rects` reads `p.get("rect_mm") or p.get("rect")` (cec_fr02.py:326) → always `None` →
  `if net in want and rect:` always False → **returns `{}` unconditionally** (cec_fr02.py:322-329).
- `cec_fullstack` item4 (957→962→963) gets `{}` → `pending_corridor_avoid=[]` → the `item4:` log (964) + the
  `T1 + corridor-avoid` log (886) NEVER print. Confirmed: 0 occurrences in run.log across the run + relaunch.
- CONSEQUENCE: V4 correctly diagnosed "foreign nets crossing `/SENSEC*` sense corridors → pour fragments → DRC+thermal"
  EVERY round and proposed the right lever, but the deterministic effector was a silent no-op → 34 rounds of correct
  diagnosis, zero actuation = the local minimum. (max_T 243-712C is an ADVISORY thin-neck artifact, not a gate;
  plane_signal_mm is a scorer WEIGHT not a gate; gate = kelvin_ok AND diffpair_ok AND drc==0 AND pour_integrity_ok.)
- RECOMMENDED FIX (routing-class, board-specific, no ratified constraint touched; NOT yet applied — owner PR process):
  (1) `clipped_corridor_rects` derive `rect_mm` from the `polygon` bbox (one-line correctness fix);
  (2) widen the force-corridor keepout in `cec_router._vital_keepouts_from_rules` to the FULL connector→shunt pour
  rectangle minus a Kelvin-tap notch, for `/SENSEC1_HI/LO` + `/SENSEC2_HI/LO`. Do NOT change pour-after-route ordering.
  Expected: pour-clip 32/34→~0, drc→~4 finishing floor, gate-passing reachable. Also a process gap: after V4 dropped
  at r~22 the T8 guard returned 503/findings=0 (== "all clear") — silently removed the local-minimum tripwire.
- Cross-check full result: `/tmp/claude-1000/.../tasks/wrmxgdloc.output`.

### IMPLEMENTED 2026-06-13 (3 owner-directed changes + Opus-auditor test wiring) — verified, UNCOMMITTED
All verified (host tests 8/8, container proof, EI-01 spec-verify, existing tests green, 3-agent adversarial
review = 0 blockers; the 1 should-fix + 2 nits folded in). NOT committed yet (kept separate from the
unrelated pre-existing `cec_facts.py` working-tree change — do NOT sweep that into the commit).
1. **LEVER FIX (make item4 work)** — `cec_fr02.clipped_corridor_rects` now derives `rect_mm` from the
   producer's `polygon` bbox (was reading absent `rect_mm`/`rect` → `{}` → item4 dead). CONTAINER-PROVEN on
   real board eps-8pin-r34: producer keys `['layer','net','polygon']` → 4 corridor rects → 4 FR-02
   avoid-intents (`LEVER_WORKS=True`). (Did NOT widen the proactive keepout in
   `cec_router._vital_keepouts_from_rules` — that's the cross-check's other rec; it needs a route-verify for
   kelvin-stranding, left as a follow-up.)
2. **VISION GATE** — `cec_fullstack.vision_pour_check(rec,rnd,run_vlm=False)`: per round computes only the
   DETERMINISTIC pour facts (which feed the blocking gate + item4); the advisory VLM narrate is gated to
   finalists (existing `vision_judge` path). Knob `CEC_FS_VISION_EVERY_ROUND=1` restores per-round narrate.
   `vision_required_unmet` now uses `vlm_attempted` so a gated round isn't a false "seat down".
3. **EI-01 corpus_state** — `cec_ledger.corpus_state(live_rules)` → `{promoted_tree, staging_tree,
   live_rules_sha, manager_rules_sha, adv_set_sha}` (trees=git `HEAD:corpus/{promoted,staging}`;
   live_rules_sha=round-time content hash; manager/adv = effective-influence pins). Wired into:
   `append()` (new `live_rules=` kwarg + on every row), `manifest()` (trees), the fullstack + inloop
   measurement rows, the two `mode="decision"` injection-boundary appends, and `ledger_round(...,live_rules)`.
   `query --corpus-state` = compact per-row view. SPEC-VERIFY reproduced: rounds share scripts_sha while
   live_rules_sha flips across an injection (temp-ledger demo). New test: `tests/test_ei01_lever_vision.py`.
4. **Opus-auditor test wiring** (owner asked to test Opus4.8 max-effort as auditor): `CLOUD_AUDITORS={sonnet,
   opus}` route to the claude CLI; `sonnet_audit(model=,effort=)` builds `claude -p --model <m> [--effort
   <lvl>]`; `CEC_FS_AUDIT_EFFORT` knob; warm() skips cloud models. Run with `CEC_FS_AUDITOR_MODEL=opus
   CEC_FS_AUDIT_EFFORT=max`.
- **LIVE TEST RUNNING**: `docs/fullstack-run-2026-06-13-levertest/` — `--rounds 3`, auditor=opus effort=max,
  vision gated. Watching for the `item4:` lever-fire line (proof the lever now actuates in the real loop).
- Files touched (uncommitted): cec_fr02, cec_fullstack, cec_ledger, cec_inloop_audit, cec_overnight_directed,
  cec_night_watch.sh, + new cec_fs_capstone.py, tests/test_ei01_lever_vision.py. (cec_facts.py = NOT mine.)
- Review full result: `/tmp/claude-1000/.../tasks/w86las2ps.output`.

### V4 CAPSTONE RESULT + reconciliation (done; `docs/fullstack-run-2026-06-13/CAPSTONE-v4.{json,md}`)
V4 (deepseek-v4-flash, 588s) verdict: `local_minimum`, bundle_accurate=true, confidence=high. Root cause (CORRECT):
"pour fragmentation on SENSEC2_HI/LO from foreign signal nets crossing the sense corridors → DRC; not resolved by
the loop levers in 34 rounds." Fix: "add a keepout preventing foreign nets crossing the sense corridors" — but
classified **design_escalation** ("requires human design intervention").
- V4 GOT RIGHT: the failure MECHANISM (foreign-nets-crossing-corridors, sharper than the bundle's generic "pour
  clipping"); did NOT blame thermal/scoring; verdict + bundle-accuracy match the code cross-check.
- V4 GOT WRONG (both due to NO code visibility — it got a factual metrics+findings dossier, not source):
  (1) MISSED the dead-lever bug — said levers "were unable to resolve it" (ran-but-insufficient) when item4 was
  silently dead (fired 0×). (2) OVER-ESCALATED the fix to design_escalation; the force-corridor keepout capability
  ALREADY exists in-loop (cec_router._vital_keepouts_from_rules → bake_hints DoNotAllowTracks) — the real fix is a
  routing-class in-loop change (widen keepout + fix the polygon/rect_mm key), NOT a human constraint change.
- META-FINDING (actionable): evidence-auditor (V4, behavior) vs code-auditor (Claude agents, source). The auditor
  has an OBSERVABILITY GAP — it can't tell "lever ran & insufficient" from "lever silently dead." FIX: give item4
  actuator telemetry (log "corridor-avoid produced N intents for clipped nets {…}" each round) so a dead lever
  shows up in the auditor's own evidence. Same blind spot: the T8 guard's `findings=0` after V4 crashed at r22 read
  as "all clear."

## TONIGHT (2026-06-13): DeepSeek-V4 auditor + cec_fullstack overnight run — LIVE
Owner ask evolved: "make DeepSeek run in the auditor seat and play nice," then (key correction from owner
watching the dashboard) the overnight run they want is **`cec_fullstack`** (manager panels + seat swap +
T5 auditor), NOT `cec_inloop_audit` (which the old handoff named — that one has only a Sonnet auditor + V4
checkpoint, NO manager panels). Then: brief the manager panel + auditor with the **promoted corpus**, run
for the night unattended. Full V4 detail in memory [[deepseek-v4-auditor]].

**LIVE STATE (relaunch-able):**
- **DeepSeek-V4-Flash-284B** runs **Windows-native** (`E:\toolchain\run-v4-flash.bat` → `0.0.0.0:8007` alias
  `deepseek-v4-flash`; GGUF at `/mnt/e/models/DeepSeek-V4-Flash-GGUF/Q4_K_M-XL/`, 163 GB; experts in host RAM
  ~163 GB working set but only ~73 GB committed/reclaimable, attention+KV on the 5090 ~13 GB). It is REGISTERED
  in the broker (live + vendored `ops/cec-llm-broker/models.json`) as a `managed:false` external backend
  (host `windows-host`→WSL gw, port 8007, vram_gb 13). Broker proxies; never starts/stops/evicts it.
- **The overnight run = `cec_fullstack`**, launched detached via `sg docker` (run PID was 130423):
  `CEC_STREAM_DIR=$PWD/docs/fullstack-run-2026-06-13/streams CEC_VLLM_REVIEWER_MODEL=cec-worker-vision
  setsid nohup python3 scripts/cec_fullstack.py --board eps-8pin --hours 7`. Auditor=deepseek-v4-flash
  (default), v4_every=4. Output: `docs/fullstack-run-2026-06-13/` (run.log, streams/, REVIEW.md, intents/,
  vision/, reviews/, gr01-grid.json, morning bundle).
- **PLAY-NICE solved (GPU + RAM):** V4 (13 GB GPU) + the 25 GB `cec-worker-vision` worker would OOM the 32 GB
  card. FIX: compose `worker-volume-vision` now runs `--n-cpu-moe ${CEC_VISION_NCPUMOE:-99}` (experts in host
  RAM → GPU ~8-10 GB; measured co-resident GPU ~17 GB < 32). Registry vram_gb 25→10. T7 reviewer pointed at
  `cec-worker-vision` (CEC_VLLM_REVIEWER_MODEL) NOT the default gpt-oss-120b (63 GB → would RAM-OOM with V4).
  RAM is at the redline (~1-2 GB Windows free, committed ~86 GB of 268 limit, mild paging ~2-6k pages/sec) —
  the owner's accepted RAM-tight tradeoff; NO hard OOM (V4's pages are reclaimable mmap). To revert when V4 is
  unloaded: `CEC_VISION_NCPUMOE=0` + registry vram_gb back to 25.
- **Corpus briefing (owner ask):** new `cec_fullstack.promoted_corpus_brief(board)` injects the **WHOLE**
  promoted corpus (35 entries from `corpus/promoted/general/*.json`, family-scoped tagged) into T1 intent-
  manager, T4 worker-panel, AND T5 auditor prompts. VERIFIED working — REVIEW.md shows the manager explicitly
  reasoning over the ratified entries (e.g. `thermal.shunt_chassis_tim`, `meas.anchor.ref3030`).
- **Dashboard:** `http://localhost:8095` (was relaunched via `sg docker` so its in-container kicad-cli render
  works — that was the "borked plots": it needs docker-group access). Pointed at `docs/fullstack-run-2026-06-13`.
  Per-role seat panels now stream (`manager:intent`, `panel:safety/finishing/progress`, `cec-worker-vision`,
  `deepseek-v4-flash` auditor) — I threaded `seat=` labels into the T1/T4 `_chat_json` calls.
- **Reasoning capture (owner ask):** every seat's FULL chain-of-thought is in `streams/<seat>.jsonl` (cec_seat_
  stream tees reasoning+content deltas). NEW `scripts/cec_review_doc.py` assembles them into a readable
  `docs/fullstack-run-2026-06-13/REVIEW.md` (per seat, every call, full reasoning). A detached refresher
  regenerates it every 5 min for ~8 h, so it's complete by morning. Re-run any time: `python3
  scripts/cec_review_doc.py --run-dir docs/fullstack-run-2026-06-13`.
- **Also fixed:** `cec_inloop_audit.v4_up()` was broken vs the rebuilt broker (probed `/broker/models` + a
  `m['upstream']` key that no longer exist) — now uses `/v1/models` + host/port. HOOKS: session-start/-end now
  self-sync the committed `.claude/memory/` ↔ ephemeral `~/.claude/.../memory` (the committed handoff had
  drifted stale 2 KB vs 8 KB live).
- **HOW TO CHECK in the morning:** `tail docs/fullstack-run-2026-06-13/run.log` (rounds + V4 auditor every 4th);
  open the dashboard :8095; read REVIEW.md. **Relaunch if down:** the `sg docker ... setsid nohup python3
  scripts/cec_fullstack.py ...` line above (worker stays broker-resident across run restarts).
- **COMMITTED + PUSHED** (cbb9ef0 on `claude/overnight-corpus-preflight`, bot): compose n-cpu-moe, broker
  vram_gb, cec_fullstack corpus+seat-labels, cec_review_doc.py, v4_up fix, hooks. Durable on the remote.
- **CONFIRMED WORKING (monitored to ~03:10):** round 1 completed, V4 T5 auditor fired EVERY round, completed
  NATURALLY (`T5: auditor=repair`, 5.5k reasoning chars captured to deepseek-v4-flash.jsonl), round 2 started.
  The DeepSeek call is NOT stuck — it's just slow: cec_fullstack runs the deep V4 auditor EVERY round
  (`audit()` per-round, NOT gated by V4_EVERY; V4_EVERY=4 is the SEPARATE T8 deep-BATCH auditor) at ~4 tok/s
  over the big corpus-briefed prompt → ~12 min/V4-audit, ~15-20 min/round total. Auditor max_tokens=4096
  (jl.MANAGER_MAX_TOKENS), deepseek_audit timeout=900s. So ~15-20 deeply-audited rounds over 7 h (FEWER but
  DEEPER than the old 100+-round runs — the cost of V4-every-round + the 35-entry brief). NO hard OOM (committed
  ~92 GB of 268 limit; avail 0.6-4.6 GB is just V4's reclaimable mmap; mild paging).
- **THROUGHPUT LEVER (if owner wants more rounds, not deeper):** `CEC_FS_AUDITOR_MODEL=sonnet` (cloud, fast
  per-round T5) keeps V4 only on the T8 every-4th batch; or raise `CEC_FS_V4_EVERY`; or trim the corpus brief
  (promoted_corpus_brief max_chars) so the worker/auditor reason less. NOT changed — owner chose deep+whole-corpus.
- **MONITORING:** owner asked to monitor overnight + fix issues. Benign noise confirmed harmless: T6 vision
  anomaly flags are advisory-only (owner ruling, re-checked by determinism); `property.h(607) m_choices` asserts
  are benign kicad-cli stderr. Watch: run.log advancing (a new `--- round N` every ~15-20 min), RAM committed
  < 268 limit, V4 audits completing not timing out.

## Two PRs opened 2026-06-13 as nathanfraske-bot (idle-time work, owner away from PC)

NOTE on bot push: on a branch off `main` the credential helper `ops/secrets/git-credential-cec.sh`
is ABSENT (it lives on the unmerged PR #51 branch), but the git `--local` config still points at it
-> normal push fails. Workaround used: transient inline helper reading `CEC_BOT_PAT` from
`/mnt/e/secrets/cec-bot.env` (`git -c credential.helper= -c 'credential.helper=!f(){...}; f' push`);
`gh` via `GH_TOKEN`. Real fix = merge PR #51 (lands the helper on main).

- **PR #52 — `claude/am04-electrothermal-mincut`** (AM-04 PR-two model-debt fix in
  `cec_synth_pipeline.electrothermal_solve`): segment-sum -> serial min-cut (`_min_cut`, pour-span
  restricted so zero-current Kelvin stubs don't read as series necks); per-transition via clustering
  for non-poured nets vs distributed `I/total` for poured stitching fields; IPC k by the bottleneck's
  actual layer (rename-proof ID). Micro-board anchor moved to the DERIVATION.md CORRECTED column
  (cross 1.044->0.348, dT 4.8->6.12); 8/8 AM-04 + 18/18 thermal-gates tests pass. **SB-08 golden
  re-freeze left OWNER-GATED** (coupled item-3a CEC_GOLDEN_SYNTH + owner `--thermal-headroom`;
  measured: synth-OFF now correctly EXPOSES the 40A-on-0.2mm-trace fusing the old sum hid; synth-ON
  max_T 120.5C limited by the +5VSB rail, no clamp). `expectations.json` untouched (already red-pending).
  CLAUDE.md model-debt note marked RESOLVED.

- **PR #53 — `claude/corpus-promote-43`** (owner-directed corpus promotion; REVISED 2026-06-13 after two
  owner notes). **35** of 43 human_approved `staging/general` entries -> `promoted/general`, VERBATIM +
  signoff{by:nathanfraske}/promotion{promoted_by:nathanfraske-bot, pr:53}. **status FLIPPED human_approved
  -> promoted**: owner directed that status:promoted be a real machine-readable lifecycle value (not just
  the directory). Implemented as a SCHEMA-contract change (audited + adversarially reviewed via two
  workflows): added "promoted" to STATUSES + lifecycle; promoted-zone lint requires status=promoted; NEW
  staging-zone guard errors on status=promoted in staging (demotion must revert). AUDIT confirmed SAFE --
  the compiler selects blocking-vs-advisory by ZONE (cec_corpus_compile.py:297, cec_facts binding=="gate"),
  never by the status string, so the flip moves nothing in/out of the blocking set. HELD in staging (8):
  4 founders-related (dvdi.requirement_tier_verdict, meas.targets.v1 + the 2 truth_chain rows
  meas.truth_chain.claim_level/spec_wording the owner held this round) + 4 AM-02 fixture-blocked
  (can.termination.hub_split_120r, can.bitrate.classical_500k, thermal.k_ipc.external/internal). REVIEW
  CAUGHT + FIXED: (a) doc landmine in 3 files (README, addendum, closed-loop-parity-plan) wrongly said the
  compiler consumes by status -> corrected to ZONE; (b) BLOCKER -- the 3 AM-02 anchor tests
  (test_{measurement_claims,fault_phenomenology}_corpus, test_stability_budget) loaded entries from
  hard-coded STAGING paths, so the promotion MOVE broke them (42 errors), silently (not in CI). Fixed: all
  3 now merge BOTH zones + wired into kicad-checks.yml + checklist.sh. Re-froze parity (matched=20
  unchanged; corpus_only 301->317 = pre-existing drift + #51 incident entry, NOT the promotion). 0
  tombstones. Lint 0 errors; 7/7 corpus tests pass; CODEOWNERS gates corpus/promoted/ + tests/golden/.
  NOTE the credential helper now works on this branch (post-#51 base), no transient-credential workaround
  needed.

## Dashboard per-seat streaming + overnight prep (2026-06-13, branch claude/dashboard-per-seat-streams, PR #54)
- **Live dashboard REWRITTEN** to show real per-seat streaming (owner ask). New `scripts/cec_seat_stream.py`
  recorder (env-gated `CEC_STREAM_DIR`, per-seat NDJSON, no-op when unset). `cec_judge_local` transport
  now SSE-streams + tees per-seat deltas with a blocking fallback on ANY error; seat labels threaded:
  manager, manager:safety/finishing/progress, worker:<i>, reviewer, scribe, v4-checkpoint, auditor.
  `cec_dashboard` replaced the single thoughts panel with a live per-seat stack (/api/seats, /api/seat).
  cec_inloop_audit defaults+clears `CEC_STREAM_DIR=<run-dir>/streams`; passes it through the container exec.
  Adversarially reviewed (0 blockers; 5 should-fixes folded in). 10/10 judge_local tests (2 new streaming).
  **Dashboard is RUNNING** (setsid, :8090). Relaunch: `setsid python3 scripts/cec_dashboard.py --port 8090
  --run-dir docs/inloop-audit-2026-06-11 > .../dashboard.log 2>&1 < /dev/null &`. SAFETY: CEC_STREAM_DIR
  unset => byte-identical blocking transport (overnight unaffected unless a dashboard run opts in).
- **Overnight run = `cec_inloop_audit.py`**. Launch: `nohup python3 scripts/cec_inloop_audit.py --hours 7
  --board eps-8pin > docs/inloop-audit-2026-06-11/run.log 2>&1 &`. BLOCKED on owner (sudo): the route step
  execs the routing container -> first `sudo docker compose -f docker/compose.yaml up -d routing` (+ `build
  routing` if the WSL wipe dropped the image). To get per-seat streaming tonight, MERGE PR #54 first (or run
  from the branch checkout). Gap: deepseek-v4-flash (V4 morning checkpoint) not in the broker + intentionally
  unloaded for the night -> V4 is a no-op tonight by design.
- **ARCHIVE NOTE**: docs/inloop-audit-2026-06-11/ was cleared concurrently (round-117's 153 files MOVED to
  docs/inloop-audit-2026-06-12-archived-round117/ -- data safe, verified). NOT done by me; I left the
  deletions/archive UNSTAGED (owner's call) and committed only the 5 feature scripts.
- PRs now open (all bot-authored, owner-merge-only): #52 AM-04 (MERGED), #53 corpus (MERGED), #54 dashboard.

_Below: env-rebuild + WSL-ephemeral policy + Windows-native Phase B (2026-06-12)._

## Context
WSL distro reinstalled 2026-06-12 after a failed move to E:. Whole Linux home lost; GGUFs
on `/mnt/e/AI Models` survived. Rebuilt the toolchain + broker from scratch, then implemented
the owner's WSL-ephemeral state policy, then started the Windows-native serving migration.
See [[env-rebuild-2026-06-12]], [[llm-broker]], [[bot-git-auth]], [[windows-native-serving]].

## Done + on the remote (branch `claude/wsl-ephemeral-recovery`, PR #51, authored as nathanfraske-bot)
- **Toolchain rebuilt + verified**: KiCad 10/pcbnew, Python deps, Docker+NVIDIA toolkit (GPU
  in-container), routing image, the cec-llm-broker (end-to-end model boot proven).
- **WSL-ephemeral policy**: CLAUDE.md policy; `ops/provision.sh` (one-shot recovery + 4 smoke
  tests); `.claude/hooks/session-end.sh` Stop hook (pushes handoff+memory to `ops/agent-handoff`
  every session, git-plumbing, never touches the worktree); `.claude/memory/` committed; secrets
  policy + the bot PAT placed at `/mnt/e/secrets/cec-bot.env`; broker VENDORED into
  `ops/cec-llm-broker/`; corpus incident entry (lint-clean).
- **Git authors/pushes as nathanfraske-bot** via `ops/secrets/git-credential-cec.sh`.
- **Windows-native Phase B** (`docs/local-compute-windows-native-migration.md`): mainline
  llama.cpp b9611 CUDA 13.3 on `E:\llama-cpp-win\`; networking verified; broker external-backend
  support (`managed:false`, seat `cec-worker-vision-win:8090`); versions.env pinned; launchers
  vendored at `ops/windows-serving/`.

## BLOCKED / next (Windows-native)
- The Windows binaries fail to load: System32 Microsoft `libomp140.x86_64.dll` lacks
  `__kmpc_dispatch_deinit` and loads before llama.cpp's bundled copy (DotLocal `.local` does NOT
  fix it). **Fix needs ONE elevated action** (owner, when at a console with UAC):
  `copy /Y E:\llama-cpp-win\b9611\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll`
  (back up first; bundled is a superset). Or a source build with `GGML_OPENMP=OFF` (needs CUDA>=12.8).
- After the fix: start the server (Task Scheduler `CEC-WorkerVision` via `ops/windows-serving/`),
  then finish **B3** (cold-load + decode medians, Win-native vs drvfs) and **B5** (validate the
  broker proxy end-to-end). The broker seat is already wired.
- The WSL llama.cpp stack is the working production path meanwhile.
