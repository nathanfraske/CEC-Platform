---
name: llm-broker
description: "cec-llm-broker is a standalone on-demand model orchestrator at /home/nathan/cec-llm-broker (:8080, systemd unit), NOT in the repo."
metadata: 
  node_type: memory
  type: project
  originSessionId: 481c50f1-03c6-4988-bdb6-aa3ffd3f3706
---

`cec-llm-broker` lives at **`/home/nathan/cec-llm-broker`** (outside the repo, so it is
NOT version-controlled with CEC-Platform). It is a stdlib-only Python OpenAI-compatible
reverse proxy on `0.0.0.0:8080` that orchestrates the local-LLM backends defined in
`CEC-Platform/docker/compose.yaml`.

Rebuilt from scratch 2026-06-12 from the CLAUDE.md "BROKER v2 = MODEL ORCHESTRATOR" spec
after the WSL reinstall wiped the original (see [[env-rebuild-2026-06-12]]). Files:
`broker.py`, `models.json` (registry), `cec-llm-broker.service`, `README.md`.

Behavior (matches the documented contract `cec_judge_local.py` / `cec_overnight.py` expect):
- Routes by the request `"model"` field; `GET /v1/models` returns the full catalog with a
  per-model `running` flag even with nothing up; `POST /v1/chat/completions` boots the
  backend on demand (`docker compose --profile <p> up -d <svc>`), arbitrates VRAM against
  `gpu_budget_gb` (evict LRU GPU backend to fit), proxies, and an idle reaper stops
  backends after `idle_stop_s` (30 min). Honors `X-CEC-Client`. `/broker/stats` for state.
- Installed as the systemd unit `cec-llm-broker` (`systemctl status cec-llm-broker`,
  `journalctl -u cec-llm-broker -f`). Runs as `nathan`, group `docker`.
- **Never `docker compose up/down` an LLM service by hand** — request the model through
  :8080 and let the broker manage lifecycle.

Registered aliases → compose service: cec-judge→inference(vLLM), cec-worker→worker-volume,
cec-worker-quality→worker-quality, cec-vision-judge→vision-judge,
cec-worker-vision→worker-volume-vision (the DEFAULT seat), cec-worker-quality-vision→
worker-quality-vision, cec-manager→manager-m27, cec-manager-fast→manager-fast.
The `vram_gb` values in models.json are estimates tuned so only one heavy model holds the
5090 at a time; adjust if measured footprints differ.
