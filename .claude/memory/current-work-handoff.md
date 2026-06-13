# Current work handoff

_Updated 2026-06-13 ~07:00Z (DeepSeek-V4 auditor seat brought live for the overnight run; older context below)._

## TONIGHT (2026-06-13): wire DeepSeek-V4-Flash into the auditor seat + start the overnight run
Owner ask: "make DeepSeek run in the auditor seat and play nice with the rest of the stack," then start
the overnight run. Owner is AT the PC and authorizes UAC prompts. Full detail in memory [[deepseek-v4-auditor]].

- **Found it**: DeepSeek-V4-Flash GGUF (Q4_K_M-XL, 163 GB, 4 shards) is at `/mnt/e/models/DeepSeek-V4-Flash-GGUF/Q4_K_M-XL/`
  (NOT `/mnt/e/AI Models`). Runs **Windows-native** on a V4-fork llama.cpp (`E:\toolchain\llama.cpp-v4`), launcher
  `E:\toolchain\run-v4-flash.bat` → `0.0.0.0:8007` alias `deepseek-v4-flash`, experts in host RAM (~135–140 GB),
  attention/KV on the 5090. Preflight needs ≥145 GB free RAM (box has 191.5 GB). Firewall rule `CEC-v4flash-8007-WSL`
  already allows TCP 8007 from the WSL NAT subnet.
- **Launched** from WSL: `powershell.exe ... Start-Process cmd /c E:\toolchain\run-v4-flash.bat`. Cold-loading now
  (163 GB mmap off NTFS, several min). Watch `/mnt/e/toolchain/v4-flash-server.log`.
- **Broker**: registering `deepseek-v4-flash` as a `managed:false` external backend (host `windows-host`→WSL gw,
  port 8007), mirroring `cec-worker-vision-win:8090`. Broker proxies; never starts/stops/reaps it; counts its
  `vram_gb` in arbitration but never evicts it. Editing live `/home/nathan/cec-llm-broker/models.json` + vendored
  `ops/cec-llm-broker/models.json`, then `systemctl restart cec-llm-broker`.
- **PLAY-NICE risk (the crux)**: V4 holds GPU the whole time it's loaded. 5090 = 32 GB. V4 footprint measured
  climbing ~3.4→~13 GB during warmup — must finalize and set `vram_gb` to the real number; then verify the in-loop
  worker seat (`cec-worker-vision` 25 GB) does NOT co-reside with V4 (32 GB cap, broker can't evict the external V4).
- **NEXT**: finish V4 load → measure GPU → set vram_gb → restart broker → e2e auditor call via :8080 →
  `sudo docker compose up -d routing` (owner authed) → launch `cec_inloop_audit.py --hours 7 --board eps-8pin`.
- HOOKS: made session-start/-end self-sync the committed `.claude/memory/` ↔ ephemeral `~/.claude/.../memory`
  (the committed handoff had drifted stale). See below.

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
