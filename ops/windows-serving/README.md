# `ops/windows-serving/` — Windows-native LLM serving

Scripts for serving an LLM seat from a **Windows-native** llama.cpp (model read from `E:` at
native NTFS speed, skipping the WSL `/mnt/e` drvfs cold-load tax). Plan + status:
[`docs/local-compute-windows-native-migration.md`](../../docs/local-compute-windows-native-migration.md).

The binaries themselves are NOT in git (too large) — they live on `E:\llama-cpp-win\` (non-ephemeral
Windows FS) and are re-fetchable: mainline llama.cpp **b9611**, Windows **CUDA 13.3** build, pinned
by tag + sha256 in [`versions.env`](../../versions.env). These launchers ARE in git so the recipe
survives a WSL wipe.

| File | What |
|---|---|
| `run-worker-vision.bat` | Launches `llama-server.exe` for the worker-vision seat (Qwen3.6-35B-A3B + mmproj) on `:8090`. Sets its own CWD (so the `.local` libomp redirect applies) and redirects to `srv.log`. |
| `install-task.ps1` | Registers the `CEC-WorkerVision` Scheduled Task (logon trigger → survives reboots). **Run once, elevated.** |
| `close-dialogs.ps1` | Utility: finds + closes stuck llama-server loader error dialogs and kills the owning processes (for when a load failure leaves a modal dialog on the desktop). |

## ⚠️ Known blocker (2026-06-12) — needs one elevated action

The Windows binaries fail to load: a Microsoft VC-redist `libomp140.x86_64.dll` in
`C:\Windows\System32` lacks `__kmpc_dispatch_deinit` and is loaded (by the VC runtime) before
llama.cpp's bundled LLVM copy — so a DotLocal `.local` redirect does **not** fix it. Fix, elevated:

```
copy    C:\Windows\System32\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll.bak
copy /Y E:\llama-cpp-win\b9611\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll
```

(llama.cpp's bundled libomp is a superset — backward-compatible.) Alternatively, a from-source
build with `GGML_OPENMP=OFF` (needs a CUDA ≥ 12.8 toolkit; the box has 12.1).

## Broker wiring (already done)

The broker registers `cec-worker-vision-win` (`:8090`, `managed:false`, host → WSL default gateway).
Once the server is up, point a seat at it with `CEC_VLLM_MODEL_NAME=cec-worker-vision-win`; the WSL
`cec-worker-vision` stays the fallback.
