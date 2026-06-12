# cec-llm-broker

On-demand local-LLM **model orchestrator** on `0.0.0.0:8080`. One OpenAI-compatible
reverse proxy in front of every local-LLM backend on this box, so the CEC pipeline
(and any other project) never thrash the single RTX 5090 by hand.

> Rebuilt from the CEC `CLAUDE.md` spec on **2026-06-12** after the WSL move to E:
> wiped the original `/home/nathan/cec-llm-broker`. The model files themselves
> survived on `E:\AI Models` (= `/mnt/e/AI Models`).

## What it does

- **Route by model name** — the request's `"model"` field selects a `models.json`
  entry; the broker proxies to that backend's host port and rewrites the alias to
  the backend's real served name.
- **Start on demand** — if the backend is down, `docker compose --profile <p> up -d
  <svc>` then poll its health URL. **Never `compose up/down` an LLM service by hand.**
- **GPU/VRAM arbitration** — before starting, checks `vram_gb` vs `gpu_budget_gb`
  over what is already running; if it would overflow, evicts the least-recently-used
  GPU backend first (after letting its in-flight generations drain).
- **Catalog always answers** — `GET /v1/models` lists the full registry with a
  per-model `running` flag even with nothing up (broker-liveness probe).
- **Idle reaper** — stops any backend idle > `idle_stop_s` (default 30 min).
- **Ride-through** — concurrent requests for a cold model block on the same start;
  nobody double-starts, nobody 503s during a 10-min cold load.

Fail-safe: a backend that won't come up surfaces an error; the client's own
deterministic fallback (e.g. `cec_judge_local`) takes over.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/models` (or `/models`) | full catalog `{data:[{id, running, ...}]}` |
| POST | `/v1/chat/completions` | route by `model`, boot-on-demand, proxy |
| POST | `/v1/completions`, `/v1/embeddings` | same routing, generic proxy |
| GET | `/health` | liveness |
| GET | `/broker/stats` | running backends, GPU budget/use, request counts |

Honors the `X-CEC-Client` request header for stats attribution.

## Run

```bash
# foreground (dev)
python3 broker.py

# as a service (survives WSL restarts)
sudo cp cec-llm-broker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cec-llm-broker
journalctl -u cec-llm-broker -f
```

## Config

`models.json` — `gpu_budget_gb`, `idle_stop_s`, `compose_file`, and the per-alias
backend map (profile/service/port/served/health/vram_gb). Tune `vram_gb` /
`gpu_budget_gb` to decide which backends may coexist on the 5090. Backends and GGUF
filenames mirror `CEC-Platform/docker/compose.yaml`.

Env overrides: `CEC_BROKER_PORT`, `CEC_BROKER_HOST`, `CEC_BROKER_REGISTRY`,
`CEC_BROKER_UPSTREAM_HOST`.

## Registered models (2026-06-12)

| alias | backend | port | model |
|---|---|---|---|
| `cec-judge` | vLLM | 8000 | Qwen3-Coder-30B-A3B-AWQ |
| `cec-worker` | llama.cpp | 8002 | Qwen3.6-35B-A3B UD-Q4_K_M |
| `cec-worker-quality` | llama.cpp | 8004 | Qwen3.6-27B Q4_K_M |
| `cec-vision-judge` | llama.cpp | 8006 | Qwen3-VL-32B-Instruct |
| `cec-worker-vision` | llama.cpp | 8012 | Qwen3.6-35B-A3B + mmproj **(default seat)** |
| `cec-worker-quality-vision` | llama.cpp | 8014 | Qwen3.6-27B + mmproj |
| `cec-manager` | llama.cpp | 8003 | MiniMax-M2.7 (retired from CEC paths, kept registered) |
| `cec-manager-fast` | llama.cpp | 8005 | gpt-oss-120b MXFP4 (default reviewer) |

> `deepseek-v4-flash` (the opt-in deep auditor named in `cec_judge_local`) is **not**
> registered: its GGUF was never downloaded and it has no compose service. The
> default reviewer `cec-manager-fast` covers the reviewer tier. Add a registry entry
> + a compose service once the model is on disk.
