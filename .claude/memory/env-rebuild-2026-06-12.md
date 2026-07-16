---
name: env-rebuild-2026-06-12
description: WSL distro was reinstalled 2026-06-12; the entire CEC toolchain + the LLM broker were rebuilt from scratch.
metadata: 
  node_type: memory
  type: project
  originSessionId: 481c50f1-03c6-4988-bdb6-aa3ffd3f3706
---

On 2026-06-12 an attempt to move the WSL distro to E: broke it; the distro was
reinstalled fresh. Everything in the Linux home was lost (repos, toolchains, the
`/home/nathan/cec-llm-broker`, persistent memory). The GGUF models on `E:\AI Models`
(= `/mnt/e/AI Models`) survived. The repo was re-cloned to `/home/nathan/CEC-Platform`.

Rebuilt this session (all verified working):
- **Python deps** via apt into the system python3 (so they share the interpreter with
  `pcbnew`): `python3-numpy python3-matplotlib python3-pil python3-scipy`.
- **KiCad 10.0.3** from the `ppa:kicad/kicad-10.0-releases` PPA — `kicad-cli` + `pcbnew`
  import OK in system python3.
- **Java 21** (full `openjdk-21-jre`, NOT headless — Freerouting needs libawt) + `xvfb`.
- **Docker Engine 29.5** + **NVIDIA Container Toolkit**; GPU passthrough verified
  (`docker run --gpus all` sees the RTX 5090, 32 GB, driver 595.97). `nathan` added to
  the `docker` group.
- **Routing image** `cec/routing:kicad10` built from `docker/Dockerfile.routing`.
- **The LLM broker** — see [[llm-broker]] — recreated from the CLAUDE.md spec.

Not provisioned (were not present before either / out of scope): the `deepseek-v4-flash`
GGUF (never downloaded), the vLLM `cec-judge` HF model (downloads on first use), the
`sibling cec-runs` repo (cloned separately when ledger writes are needed; compose mounts
`../../cec-runs`).
