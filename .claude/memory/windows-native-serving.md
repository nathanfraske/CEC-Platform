---
name: windows-native-serving
description: Phase B — moving LLM seats off the WSL/drvfs cold-load tax to Windows-native llama.cpp; the libomp/DotLocal gotcha and launch rules.
metadata: 
  node_type: memory
  type: project
  originSessionId: 481c50f1-03c6-4988-bdb6-aa3ffd3f3706
---

Phase B (owner directive 2026-06-12): serve LLM seats from a **Windows-native** llama.cpp so the
GGUFs read from `E:` at native NTFS speed instead of the slow WSL `/mnt/e` drvfs cold-load.
Plan + log: `docs/local-compute-windows-native-migration.md`. Per-seat, reversible, WSL broker is
the fallback. See [[llm-broker]] (external-backend support) and [[env-rebuild-2026-06-12]].

Binaries: mainline llama.cpp **b9611 CUDA 13.3** at `E:\llama-cpp-win\b9611\` (Blackwell/sm_120).
Pinned in `versions.env` (`LLAMACPP_WIN_*`).

**Two gotchas that cost hours — remember these:**
1. **libomp load failure (BLOCKING, needs admin).** Every llama.cpp Windows binary dies with
   `0xC0000139 ENTRYPOINT_NOT_FOUND` ("__kmpc_dispatch_deinit could not be located in ggml-base.dll")
   because the Microsoft VC-redist `libomp140.x86_64.dll` in `C:\Windows\System32` lacks
   `__kmpc_dispatch_deinit`/`__kmpc_dispatch_init_4` and is pulled resident at process init (via the
   VC runtime) BEFORE the bundled LLVM libomp in the exe dir — so a **DotLocal `.local` redirect does
   NOT fix it** (verified). Real fix = one ELEVATED action: `copy /Y
   E:\llama-cpp-win\b9611\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll` (bundled is a
   superset; back up first). Or a source build with `GGML_OPENMP=OFF` (needs CUDA>=12.8 toolkit; box
   has 12.1). Blocked while on a limited remote (no UAC). WSL stack is the working fallback.
2. **Launch as a real Windows process, NOT from WSL.** A WSL-spawned `.exe` gets an unusable
   `\\wsl.localhost\...` CWD (breaks `.local`/DLL resolution) and detached children are reaped when
   the WSL launcher exits. Use the launcher `E:\llama-cpp-win\run-worker-vision.bat` via the
   **`CEC-WorkerVision` Scheduled Task** (logon trigger; `install-task.ps1`, registered elevated by
   the owner — the agent is blocked from creating elevated persistence).

Broker seat `cec-worker-vision-win` (:8090, managed:false, host windows-host→default gw 172.27.192.1).
To use it: `CEC_VLLM_MODEL_NAME=cec-worker-vision-win`. ik_llama.cpp (MoE-offload seats) has no
Windows CUDA prebuilt → those stay on WSL pending a source build (box has only CUDA 12.1, too old).
