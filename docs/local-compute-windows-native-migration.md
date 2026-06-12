# Windows-native LLM serving — migration plan & verification

Status: **verification / gated build-out** (opened 2026-06-12, owner directive). Companion to
`docs/local-compute-exploration.md` (the WSL substrate) and `docs/ai-box-upgrade-analysis-2026-06-12.md`.

## Why

The local-LLM seats cold-load their GGUFs from `E:\AI Models` over the WSL2 **drvfs** mount
(`/mnt/e`, ~47 MB/s). For a 17–25 GB model that is minutes of cold load every swap. The models
already live on a Windows NTFS volume; serving them from a **Windows-native** llama.cpp reads them
at native NTFS speed and deletes the drvfs tax entirely. The control plane (the broker, the CEC
pipeline) stays where it is; only the *serving* of a seat moves.

The move is **per-seat, behind URL knobs, reversible at every step** (the V4-auditor pattern,
generalized): each `cec_judge_local` seat already resolves its endpoint from a `CEC_VLLM_*_URL`
env var, and the broker registry maps an alias → a backend. A Windows-native seat is just a
registry entry whose backend is a Windows host port instead of a compose service. Move one seat,
run its existing seat-compare/eval harness as the gate, then the next. **The WSL broker stays up as
the fallback until the last seat moves** — nothing is one-way.

## Verification checklist (gate before committing to the migration)

| # | Item | Status |
|---|---|---|
| 1 | **ik_llama.cpp builds on Windows** for the MoE-offload seats (manager-m27, manager-fast: `--n-cpu-moe` experts-in-RAM) | **GATED — owner go-ahead.** The one real risk: mainline llama.cpp on Windows is first-class, the ik_llama.cpp fork may fight the MSVC/CUDA toolchain. Needs a Windows build env (not reachable from this WSL session). **Fallback if it resists:** the MoE-offload seats stay WSL-side under a modest cap, or move to mainline llama.cpp with a seat-compare eval as the gate; the dense/full-GPU seats (workers, vision) move first since mainline serves them cleanly. |
| 2 | **Measure the win** — worker-vision cold load Windows-native vs drvfs, + decode tok/s parity, same model+quant, **3-run medians** | **PARTIAL.** drvfs baseline data point: `cec-worker-quality` (27B Q4, ~17 GB) cold-loaded + first token in **~165 s** total this session (single run). A clean 3-run median needs a **cache-drop preflight between runs** (the Linux page cache makes runs 2–3 warm and unrepresentative — the broker's M2.7 entry already notes the WSL cache-drop). Windows-native side is blocked on item 1's build. Expectation to confirm: ~90 s → tens of seconds cold; decode tok/s within noise. |
| 3 | **Networking** — mirrored vs NAT, firewall, container→host latency | **DONE (2026-06-12).** Mode = **NAT** (`networkingMode` unset; default route `172.27.192.1`). The WSL `routing` container → host path (`host.docker.internal:host-gateway`) measured **~0.72 ms mean** over 10 requests to the broker — negligible. A Windows-native serving host is reached over the same gateway, so container→Windows-host adds no meaningful latency. Confirm a Windows Defender inbound rule for the chosen serving port(s) when the server binds a non-loopback address; mirrored mode is **not** required (NAT + host-gateway already works). |
| 4 | **Per-seat migration behind URL knobs** — move one seat, run its eval, then the next; broker as fallback | **READY.** Mechanism exists: broker registry + `CEC_VLLM_{WORKER,MANAGER,REVIEWER,VISION}_URL`. A Windows-native seat becomes a registry entry with an external `health`/`port` and **no** `profile/service` (the broker proxies but does not `compose up` it). Reversible: flip the URL back to the WSL backend. |
| 5 | **versions.env grows a windows-serving section** — llama.cpp tag + sha256 per binary, recorded in the eval records | **SCAFFOLDED.** A commented `windows-serving` block is in `versions.env`; fill the tag + per-binary sha256 once the Windows binaries are built (item 1), the same as every other pinned toolchain version. |

## Migration order (once item 1 clears)

1. **Dense / full-GPU seats first** (mainline llama.cpp, lowest risk): `cec-worker`,
   `cec-worker-quality`, `cec-vision-judge`, and the unified vision seats. Each: stand up the
   Windows-native server, add a broker registry entry pointing at it, flip the seat's `*_URL`, run
   the seat-compare/eval, keep the WSL backend as fallback.
2. **MoE-offload manager seats** (`cec-manager-fast`, `cec-manager`) — only after item 1 proves the
   ik_llama.cpp (or mainline) `--n-cpu-moe` path builds + serves on Windows, gated by their eval.
3. Retire a WSL backend only after its replacement passes the eval and has run as primary for a
   real session.

## Broker support for external (Windows-native) backends

The broker (`/home/nathan/cec-llm-broker`) proxies by alias and lists a catalog. A Windows-native
seat is a registry entry with `"managed": false` and `"host": "windows-host"` (resolved at runtime
to the WSL default gateway). **Implemented 2026-06-12:** the broker now honors `managed:false` —
it proxies but never `compose up`/stops the backend, excludes it from idle-reap, and counts its
`vram_gb` toward the budget but never evicts it (it can't stop a process it didn't start). The
seat `cec-worker-vision-win` (`:8090`) is registered.

---

## Buildout log (2026-06-12)

**Binaries.** Mainline llama.cpp **`b9611`**, Windows **CUDA 13.3** build (Blackwell-capable) at
`E:\llama-cpp-win\b9611\` (+ the CUDA 13.3 cudart). sha256 in `versions.env`. `llama-server.exe`:
`7b7bfe262b4dd0ec7b9dc5f13286284119f5e6b20283af3e90f643cf1b42ec13`.

**The load blocker — root-caused; needs an admin fix.** Every binary dies at load with
`0xC0000139 ENTRYPOINT_NOT_FOUND` (the on-screen dialog: *"__kmpc_dispatch_deinit could not be
located in ... ggml-base.dll"*). Cause: a Microsoft VC-redist **`libomp140.x86_64.dll` in
`C:\Windows\System32`** is missing `__kmpc_dispatch_deinit` / `__kmpc_dispatch_init_4`, which
llama.cpp's `ggml-base.dll` imports — and that System32 copy wins the load over llama.cpp's bundled
LLVM libomp (which *has* them; confirmed by dumpbin export diff). It wins even though the bundled
copy is in the exe dir, because it is pulled resident **at process init** (via the VC runtime),
before the app-dir copy is searched — so a **DotLocal `.local` redirect does NOT fix it** (verified:
the dialog still fires with `.local` in place).

**The real fix needs one elevated action** — replace the deficient System32 libomp with llama.cpp's
bundled LLVM copy (a superset; backward-compatible, so it won't break other apps):
```
copy /Y E:\llama-cpp-win\b9611\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll
```
(run elevated; back up the original first). Alternatively, a from-source llama.cpp build with
`GGML_OPENMP=OFF` drops the dependency entirely — but needs a CUDA ≥ 12.8 toolkit (box has 12.1).
Either is gated on console/UAC access (the limited remote session can't approve UAC) or an owner
decision to install the toolkit. Until then, the seat stays on the working WSL stack.

**Launch.** Must run as a real Windows process, **not** a WSL-spawned child (WSL-interop CWD
becomes an unusable `\\wsl.localhost\...` UNC path, and detached children get reaped when the
launcher exits). Launcher: `E:\llama-cpp-win\run-worker-vision.bat` (sets CWD, applies `.local`,
redirects to `srv.log`). Persistent run = the **`CEC-WorkerVision` Scheduled Task** (logon trigger,
`E:\llama-cpp-win\install-task.ps1`, registered elevated by the owner).

**Networking (verify item 3 — DONE).** NAT; broker (WSL) → Windows server over the default
gateway `172.27.192.1`; container→host ~0.72 ms. No firewall rule needed for the gateway path.

**Cold-load / decode (verify item 2).** Pending the persistent server; the broker watcher + a
benched request will fill the medians (Windows-native NTFS read vs the WSL `/mnt/e` drvfs path).

**ik_llama.cpp (verify item 1).** Risk **confirmed**: even *mainline* prebuilt Windows CUDA needed
the libomp/DotLocal fix to load, and ik_llama.cpp (a llama.cpp fork over the same ggml/libomp)
does **not** publish Windows CUDA prebuilts — so the MoE-offload seats (`cec-manager-fast`,
`cec-manager`) would need a from-source Windows build (the box has only CUDA **12.1**, too old for
sm_120 — a newer toolkit is an owner decision). Recommendation stands: move the dense/full-GPU
seats first (mainline, working), keep the MoE-offload seats on WSL until a source build is gated by
their seat-compare eval.
