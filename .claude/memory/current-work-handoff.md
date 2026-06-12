# Current work handoff

_Updated 2026-06-12 (env-rebuild + WSL-ephemeral policy + Windows-native Phase B)._

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
