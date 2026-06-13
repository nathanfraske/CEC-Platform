---
name: deepseek-v4-auditor
description: "DeepSeek-V4-Flash-284B is the T5 deep auditor seat; runs Windows-native on :8007, proxied by the broker as an external backend."
metadata: 
  node_type: memory
  type: project
  originSessionId: e3a448e2-18b9-4234-aa65-3140311e0e72
---

The **T5 deep auditor / overnight reviewer** seat (`cec_fullstack` `DEEP_AUDITOR`,
`CEC_VLLM_REVIEWER_MODEL`, `cec_inloop_audit` `V4_MODEL`) is **DeepSeek-V4-Flash-284B**,
alias `deepseek-v4-flash`. Owner 2026-06-11 retired MiniMax-M2.7 from CEC paths and put V4 here.

**Where it lives:** GGUF `Q4_K_M-XL` (163 GB, 4 shards) at
`/mnt/e/models/DeepSeek-V4-Flash-GGUF/Q4_K_M-XL/` (NOT in `/mnt/e/AI Models` with the other
seats — it's under `/mnt/e/models/`).

**It runs Windows-native, NOT in WSL/Docker** (mainline llama.cpp can't do the V4 arch — needs
a fork). Launcher `E:\toolchain\run-v4-flash.bat` runs `E:\toolchain\llama.cpp-v4\build\bin\llama-server.exe`:
hybrid layout `--n-gpu-layers 999 --override-tensor "exps=CPU" --flash-attn on -c 32768 -t 16`,
serving `0.0.0.0:8007` alias `deepseek-v4-flash`. Routed experts live in **host RAM (~135–140 GB)**;
attention/non-expert tensors + KV on the 5090. The bat has a **preflight: refuses to launch with
<145 GB free physical RAM** (`free-gb.ps1`); box has 191.5 GB total. It self-heals the OpenSSL
runtime DLLs (copies `libcrypto/libssl-3-x64.dll` from KiCad 10) — a fresh fork rebuild ships
without them. If RAM is short, free WSL page cache first: `wsl -e bash /mnt/e/toolchain/drop-wsl-caches.sh`.

**Launch from WSL** (owner gives UAC auth): `powershell.exe -NoProfile -ExecutionPolicy Bypass
-Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','E:\toolchain\run-v4-flash.bat'
-WorkingDirectory 'E:\toolchain'"`. Cold load is slow (163 GB mmap off NTFS). Watch
`/mnt/e/toolchain/v4-flash-server.log`. Health: `curl http://<win-gw>:8007/health`.

**Firewall:** rule `CEC-v4flash-8007-WSL` allows TCP 8007 from `172.16.0.0/12` (the WSL NAT
subnet) to `llama-server.exe`. Re-add with `E:\toolchain\fix-firewall.bat` (self-elevating UAC)
if a popup ever replaces it with a block rule.

**Broker wiring:** registered in `models.json` (live + vendored `ops/cec-llm-broker/`) as a
`managed:false` external backend — `host:"windows-host"` (broker resolves → WSL default gateway,
the Windows host), `port:8007`, `served:"deepseek-v4-flash"`, `backend:"llama-win"`. The broker
**proxies but never starts/stops/idle-reaps** it (same class as `cec-worker-vision-win:8090`). It
**does count `vram_gb` in GPU arbitration**, so when V4 is loaded the broker evicts *managed*
seats to fit — but it never evicts V4 itself.

**Plays-nice constraint (the live risk):** V4 holds GPU the whole time it's loaded. Single 5090 =
32 GB. If V4's GPU footprint + a managed worker seat (e.g. `cec-worker-vision` 25 GB) exceeds the
budget, the broker can't evict the external V4 → OOM. Set V4's `vram_gb` to its MEASURED footprint
and ensure the in-loop interleaving doesn't co-resident a heavy seat with V4. See [[llm-broker]],
[[windows-native-serving]]. Measured decode ~7 tok/s, prompt ~15 tok/s @ 32k ctx (Jun 12 log).
