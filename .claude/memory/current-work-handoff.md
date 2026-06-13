# Current work handoff

_Updated 2026-06-13 ~08:00Z (DeepSeek-V4 LIVE in the cec_fullstack auditor seat, run launched for the night)._

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
- **KNOWN/NEXT:** RAM-tight → per-round is slow (worker reasons heavily over the 35-entry brief, ~3-5 min/round
  → ~14 V4 auditor passes over 7 h). NOT YET COMMITTED at handoff time: the durable changes (compose n-cpu-moe,
  broker vram_gb, cec_fullstack corpus+seat-labels, cec_review_doc.py, v4_up fix, hooks) — commit + push.

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
