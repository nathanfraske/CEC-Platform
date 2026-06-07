# `docker/` — Linux container home for the CEC compute plane

Phase 0 of [`docs/local-compute-exploration.md`](../docs/local-compute-exploration.md). This gives the
CPU compute plane (Freerouting JVM swarm + `kicad-cli` DRC) a clean Linux home and an opt-in GPU
inference service for the local judge tiers — on a Windows 11 box via WSL2 + Docker, or on bare Linux.

Why bother: on Linux, **Freerouting runs truly headless** (the official image is a REST server — no
Xvfb, none of the Windows interactive-desktop hack in [`docs/self-hosted-router.md`](../docs/self-hosted-router.md)),
and vLLM/PyTorch/FEM are all Linux-first. The compute plane itself is **CPU/RAM-bound** (one ~0.5 GB
JVM per core) — the GPU is only for the inference tier and future ML, not for Freerouting or DRC.

## Contents

| File | What |
|---|---|
| `Dockerfile.routing` | CPU compute container: `kicad/kicad:10.0` + JRE 21 + xvfb + numpy/scipy/requests. Runs the `cec_*` pipeline. |
| `compose.yaml` | `routing` (CPU) + `freerouting` (headless REST) + `inference` (GPU, opt-in) + a commented `fem` stub. |
| `.wslconfig.example` | RAM/core split for WSL2 — copy to `%UserProfile%\.wslconfig`. |

## One-time host setup (Windows 11 + WSL2)

1. **Windows NVIDIA driver ≥ 576** (do **not** install a Linux driver inside WSL2 — the Windows one
   is paravirtualized through). **WSL2 ≥ 2.7.0** (`wsl --version`; the Blackwell CUDA-graph fix).
2. Copy `.wslconfig.example` → `%UserProfile%\.wslconfig`, then `wsl --shutdown`.
3. In the distro: install **Docker** (Docker Desktop WSL2 backend, or Docker Engine) + the **NVIDIA
   Container Toolkit**. Verify the GPU reaches a container:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
   ```
   If the 5090 isn't seen, run `nvidia-cdi-refresh` (documented Blackwell-in-WSL fix; microsoft/WSL#14452).
4. **Put the repo on the WSL ext4 home (`~/`), NOT on `/mnt/c`.** The DSN/SES round-trip is
   many-small-file churn and is dramatically slower over the `/mnt/c` 9P mount. `git clone` it inside WSL.

(On bare Linux: just Docker + the NVIDIA Container Toolkit; skip steps 1–2 and the `/mnt/c` caveat.)

## Run

```bash
# Build the CPU compute container (matches versions.env KICAD_IMAGE)
docker compose -f docker/compose.yaml build routing

# Start the headless Freerouting REST server + the routing container
docker compose -f docker/compose.yaml up -d freerouting routing

# Route a board (the existing pipeline; Freerouting runs headless via xvfb-run in-container)
docker compose -f docker/compose.yaml run --rm routing \
    python3 scripts/cec_router.py --board eps-8pin --seeds 0,1,2,3 --passes 12 --opt-time 30

# Opt-in: bring up the local GPU inference server for the judge tiers (Thrust A)
#   set CEC_VLLM_IMAGE to a Blackwell-ready (CUDA 12.8 / sm_120) vLLM image first
docker compose -f docker/compose.yaml --profile inference up -d inference
```

Decision logs land in the gitignored `build/route/` (and accumulate in `build/route/corpus/` — the
training substrate for the surrogate ranker, Thrust C).

## Notes, caveats, and the things to verify

- **`kicad-cli` has no Specctra export.** The DSN/SES round-trip rides KiCad's SWIG `pcbnew` bindings
  (`cec_fr.ExportSpecctraDSN`/`ImportSpecctraSES`), which work in the `kicad/kicad:10.0` image — the
  Dockerfile fails the build early if `import pcbnew` doesn't work. SWIG is deprecated upstream;
  the eventual migration is to the KiCad **IPC API server** (`kicad-cli api-server`).
- **Freerouting wiring.** Today `cec_fr` spawns the pinned **1.7.0** jar itself (works headless
  in-container via xvfb). The `freerouting` REST service + the `CEC_FREEROUTING_URL` env var are the
  **future path** (Task #2) — switching `cec_fr` to POST jobs to the REST API. Until that's wired, the
  REST service is just running alongside; the jar path is what executes.
- **GPU sharing.** The 5090 is **not MIG-capable**: run at most one heavy GPU job at a time, or share
  via **MPS**/time-slicing. The `inference` service caps itself at `--gpu-memory-utilization 0.5` so a
  FEM/router job has headroom; since the judge tiers default to deterministic, keep it **off** unless a
  local LLM tier is actually engaged, leaving the whole GPU free.
- **vLLM image.** `vllm/vllm-openai:latest` may not yet support Blackwell `sm_120` cleanly — set
  `CEC_VLLM_IMAGE` to a known-good 5090 image (e.g. a CUDA-12.8 / PyTorch-≥2.7 build). Use **AWQ**
  (not FP8/FP4 — Blackwell FP8 tensor cores aren't usefully exposed through WSL2 dxgkrnl yet).
- **Core pinning.** When you run the inference server alongside routing, pin cores (E-cores → JVMs,
  a couple of P-cores → the inference host) and cap `--max-workers` to avoid the measured contention
  penalty. Not wired here yet — a follow-up under Task #4.
