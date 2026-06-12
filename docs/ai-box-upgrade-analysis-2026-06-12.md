# AI-box upgrade analysis — expected performance for the CEC local-LLM pipeline (2026-06-12)

Owner question: how much more performance from an AI box = **Threadripper PRO 9965WX**, **8 × 32 GB
DDR5-6000** (256 GB, 8-channel 1DPC), **two RTX 5090s**. Grounded in the pipeline's *measured* bottlenecks,
not vendor headline numbers.

## Why this box is unusually well-matched

The 2026-06-11 validation-run retrospective named the limiter explicitly: *"broker model-swap / 502 / 503
on the single 5090, NOT reasoning/compute."* T6 vision, T8 deep auditor, and T7 reviewer all failed to
swap-contention. Separately, the experts-in-RAM MoE managers are **memory-bandwidth-bound** on a
2-channel consumer platform. The proposed box hits **all three** real bottlenecks: VRAM contention,
RAM bandwidth, and core count.

## Baseline (current box)

| | current |
|---|---|
| CPU | Intel Core Ultra 7 265K — **dual-channel** DDR5 (~100 GB/s) |
| RAM | 192 GB physical / **125 GB WSL2 ceiling** |
| GPU | **single** RTX 5090 (32 GB) |
| models | live on `E:\AI Models` (drvfs ~150 MB/s → 6.5–10.5 min cold loads) |

## Proposed box (verified specs)

9965WX = **24 cores / 48 threads** Zen 5, 4.2 / 5.4 GHz, **8-channel DDR5 ECC RDIMM up to 6400 MT/s**,
128 MB L3, **128 PCIe 5.0 lanes**, 350 W. With 8 × 32 GB = **256 GB at 1 DIMM/channel** (the optimal
topology for hitting DDR5-6000 stably) and **2 × RTX 5090 = 64 GB VRAM**.

## 1. 2 × 5090 (32 → 64 GB VRAM) — eliminates the swap thrash (the #1 measured limiter)

Today one heavy model is resident at a time and the broker swaps the single 5090 — exactly what 502/503'd
the vision, deep-auditor, and reviewer seats. 64 GB lets the hot tiers be **co-resident** (worker ~27 GB
on GPU0 + vision/auditor on GPU1), so the overnight loop runs **all seats live** instead of degrading to
1–2 tiers. **This is the single biggest qualitative win** — it turns a 0-gate-passing / 4-tiers-down
night into a fully-staffed one.

- *Caveat:* the 5090 has **no NVLink** (consumer Blackwell); two-GPU is over PCIe 5.0. The value here is
  **co-residency, not 2× single-model throughput** — tensor-parallel would be PCIe-interconnect-bound.
  For this pipeline, co-residency is the thing you actually need.

## 2. 256 GB 8-channel DDR5-6000 (~384 GB/s vs ~100 GB/s) — the quantifiable decode win

MoE decode with experts-in-RAM is **memory-bandwidth-bound**, so tok/s scales ~linearly with bandwidth.
8-channel DDR5-6000 ≈ **~3.8× the bandwidth** of dual-channel. **Capacity (32 vs 64 GB sticks) does not
affect this — only the channel count and speed do**, so the decode speedups are identical at 256 or 512 GB:

| tier | measured now | expected (~3× real-world) |
|---|---|---|
| gpt-oss-120b reviewer | 22 tok/s | **~65–80 tok/s** |
| DeepSeek-V4 / deep auditor | ~13 tok/s | **~38–48 tok/s** |

**Residency at 256 GB — the critical threshold still clears:**
- **DeepSeek-V4 (~160 GB) fits FULLY resident** in 256 GB with ~90 GB to spare. At the current 125 GB
  WSL2 ceiling it **pages**; at 256 GB it is warm and fast — exactly what the new overnight-auditor chair
  (DeepSeek, owner 2026-06-12) needs.
- The two **live CEC manager tiers fit together but tightly**: DeepSeek (160) + gpt-oss-120b (63) ≈
  **223 GB**; after OS/WSL + the routing container's JVMs (~12–25 GB) you are near the 256 GB edge. During
  an overnight run with routing going *and* both managers resident, expect to keep **one** deep tier hot
  (DeepSeek) and load the fast reviewer on demand — workable, not effortless.
- **What 512 GB (8 × 64) would add over 256:** headroom only — keep DeepSeek + gpt-oss + M2.7 (the other
  project) + generous free page cache all warm at once (325 GB of MoEs fit in 512 with room). **No speed
  difference.** Choose 512 only if you'll run the other project's big models alongside CEC, or want zero
  residency-management thought.

## 3. 24 Zen 5 cores (+128 PCIe 5.0 lanes) — routing + prefill

Freerouting is CPU-bound (~1 JVM/core). 24 Zen 5 cores fed by 8-channel RAM give ~24 solid parallel route
candidates plus faster MoE **prefill** (the auditor's long prompts). Modest over the existing 24-thread
runner; large over the 4-vCPU cloud box.

## 4. Cold loads ≈ eliminated

Models on drvfs (~150 MB/s) cost 6.5–10.5 min cold today. With 256 GB they **stay warm** (the working set
fits); and on the WRX90's PCIe-5 NVMe in WSL ext4, a genuine cold load drops to seconds.

## Bottom line

| workload | expected gain |
|---|---|
| **Overnight runs** | **transformational** — swap-starved → all-tiers-live (the gain that matters most, and what the new DeepSeek overnight auditor needs to be resident + fast) |
| Deep auditor / reviewer decode | **~3–4×** (bandwidth) + no cold-swap |
| Worker inference per-call | ~unchanged (already GPU-resident) — the win is pipeline concurrency |
| Routing | moderate over the existing runner |
| Cold loads | ~eliminated |

**Honest caveats:** no-NVLink caps multi-GPU tensor-parallel (co-residency is the real value);
DDR5-6000 at 8 × 32 GB RDIMM 1DPC is within the 6400 spec but validate stability (5600 fallback ≈ still
~3.6×); the exact bandwidth multiplier depends on the current RAM's actual clock. 256 GB is sufficient for
the CEC pipeline alone; 512 GB only buys slack for running the other LLM project's models alongside it.

Sources: [AMD Threadripper PRO 9965WX](https://www.amd.com/en/products/processors/workstations/ryzen-threadripper/9000-wx-series/amd-ryzen-threadripper-pro-9965wx.html),
[Puget Systems 9965WX](https://www.pugetsystems.com/parts/CPU/AMD-Ryzen-Threadripper-Pro-9965WX-4-2GHz-24-Core-350W-16362/).
Pipeline bottleneck + model figures: `docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md`, the
`local-llm-as-agent` memory, and the validation-run retrospective.
