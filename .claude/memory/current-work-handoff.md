# Current work handoff

_Updated 2026-06-12 by the env-rebuild session._

## Context
The WSL distro was reinstalled fresh on 2026-06-12 after a failed move to E:. The
Linux home (repos, toolchains, the cec-llm-broker, persistent memory) was wiped; the
GGUF models on `/mnt/e/AI Models` survived. This session rebuilt the whole environment
from scratch. See [[env-rebuild-2026-06-12]] and [[llm-broker]].

## Done + verified this session
- Re-cloned `nathanfraske/CEC-Platform` → `/home/nathan/CEC-Platform`.
- Python deps (apt, system python3): numpy/matplotlib/PIL/scipy — import OK with pcbnew.
- KiCad 10.0.3 (kicad-cli + pcbnew), Java 21 full JRE + xvfb.
- Docker 29.5 + NVIDIA Container Toolkit; GPU passthrough into a container verified (RTX 5090).
- Routing image `cec/routing:kicad10` built.
- `cec-llm-broker` rebuilt at `/home/nathan/cec-llm-broker`, installed as a systemd unit,
  catalog/health/stats endpoints verified, compose orchestration wiring cross-checked.
- llama.cpp `server-cuda` image pre-pulled.

## Verified end-to-end
- Real broker boot of `cec-worker-quality` round-tripped: request → on-demand `compose up`
  → GPU cold-load (~165 s) → proxied llama.cpp `chat.completion`. GPU then returned to
  baseline after stop. The full toolchain rebuild is COMPLETE and the LLM stack is live.

## Notes / next
- Not provisioned (out of scope / weren't present before): `deepseek-v4-flash` GGUF, the
  vLLM `cec-judge` HF model (auto-downloads on first request), the sibling `cec-runs` repo
  (clone next to CEC-Platform when ledger writes are needed — compose mounts `../../cec-runs`).
- The previous session's own current-work-handoff was lost in the wipe and could not be
  recovered; project state should be re-derived from git history + docs/owner-queue.md.
