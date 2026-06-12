# Owner ruling — deterministic inspection pipeline; VLM is narration + anomaly only

**Type:** OWNER RULING (design ruling, binding). **By:** nathanfraske. **Date:** 2026-06-11.
**Supersedes:** the Role-1-primary recommendation in `docs/vision-seat-role-rationale-2026-06-11.md`.
**Grounded by:** `docs/research/grounding-cl21-vlm-seat-redesign-2026-06-11.md` (the head-two dive).

## The ruling (owner's words, verbatim)

> "The pipeline adopts the shape of that research I just presented. Deterministic pre-pass owns
> detection, and the VLM is explicitly for narration and anomaly surfacing, it should not make
> judgements that are set in stone. The reason the seat continues to exist rides exclusively on the
> incremental catch number. This supersedes the rationale doc's recommendation, and you must mark
> this as an owner ruling."

## What it binds

1. **Deterministic pre-pass OWNS detection.** A render-diff module (XOR/subtraction → threshold →
   morphological open/close → connected-component region list) against the frozen known-good
   reference render — no alignment stage (renders are pixel-registered by construction) — plus the
   DRC/DFM layer (native KiCad sliver / dead-copper / min-width + a custom acid-trap rule) detects
   every enumerable defect class. This is the primary detection path.
2. **The VLM does NOT judge.** Roles 1 (consistency auditor as judge) and 2 (reference comparison as
   judge) are RETIRED — they are deterministic now. The VLM is restricted to **narration of the
   diff regions** and an **open-ended anomaly pass** for unknown-unknowns (toolchain/renderer bugs
   no checker can see). It never measures, never gates; its output is a flag, never a set-in-stone
   verdict. Any retained comparison is strictly pairwise against the frozen reference. The safety
   envelope (every flag deterministically re-checked) is unchanged.
3. **The seat's existence rides EXCLUSIVELY on the incremental catch number.** The only figure that
   justifies keeping the VLM seat is its INCREMENTAL catch rate over the completed deterministic
   pre-pass, measured on planted unknown-unknowns the checkers cannot see by construction (corrupt
   SVG export, layer rotated in the render only, a zone dropped from the render while facts stay
   correct). That number goes in the eval record either way; **a documented null retires the seat.**
4. **Benchmark gate before any VLM work:** the pre-pass must hit ≥99% per-class catch on the
   enumerable classes (consistent with the AOI reference-method <0.2% error) or the diff/morphology
   is fixed first. The VLM is not touched until that number exists.

## Provenance for citation

This ruling is the authority for: the deterministic-diff pre-pass (`cec_render_diff` / pipeline
wiring), the planted-defect battery (`cec_defect_battery`), the VLM re-role (narration-only,
heuristic deleted), and the five CL-21 corpus entries staged from the dive. The vision-seat
`eval_gate` in `cec-policy.json` is sign-able to load-bearing ONLY against the incremental-catch
number, never the measurement role (which is recorded FAILED, CL-19 pattern).
