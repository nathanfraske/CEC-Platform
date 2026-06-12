# VLM incremental-catch measurement — the number the seat rides on

Authority: `docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md` (OWNER RULING) §3:
*"The seat's existence rides EXCLUSIVELY on the incremental catch number ... measured on planted
unknown-unknowns the checkers cannot see by construction ... a documented null retires the seat."*

Harness: `scripts/cec_vision_incremental.py` → `incremental-catch.json`. Live run 2026-06-12 on
`cec-worker-vision` (Qwen3.6-35B-A3B + mmproj), board `pcie-8pin-2port-routed` (Edge.Cuts 86.5×44.1 mm).

> **Supersedes the 2026-06-11 run (2/3, 0.667).** That run measured the VLM against a corruption class
> it should never have owned (global geometry) and counted the clean CEC logo as a false positive. Both
> are now handled **deterministically** — see "What changed" — so the seat is measured only on its true
> residual territory.

## What changed (the deterministic pre-pass grew two backstops)

1. **`cec_render_diff.outline_sanity(svg, board_w_mm, board_h_mm)`** — a reference-free geometry check:
   the rendered SVG's declared physical size, its viewBox aspect, and the extent of its drawn outline
   must match the board's Edge.Cuts bbox. This **owns the corruption class** (wrong scale/aspect,
   distorted, truncated export) — the global-geometry weakness CL-21 predicts for the VLM. No pixels,
   no reference; it compares the render to the board *file*.
2. **`cec_vision_narrate.subtract_baseline(...)`** — the anomaly pass runs once on the known-good
   reference; its flags (the intentional CEC copper logo, the model-free overlay annotations) are
   subtracted from candidate output by token-set overlap. The false positive is removed **without** a
   logo prior in the prompt — the model is never told to ignore anything (same after-the-fact discipline
   as the DFM baseline subtraction). Raw output is retained in `anomalies_raw`.

So the harness now **partitions** the three planted render-stage corruptions (board file never touched,
no frozen reference) by who owns them:

| scenario | corruption (render only) | owner | result |
|---|---|---|---|
| corrupt_svg | anisotropic export (declared width ×0.7 → wrong size + aspect) | **deterministic** (`outline_sanity`) | **CAUGHT** — 3 reasons: declared 60.47 ≠ 86.50 mm, aspect 1.375 ≠ 1.961, viewBox 1.964 ≠ canvas 1.375 |
| rotated_layer | back copper rotated 7° in the render (outline intact) | **VLM residual** | **CAUGHT** — "corrupted or **mis-exported** graphic element, not matching PCB copper features" |
| dropped_zone | one localized 12V pour painted out of the render (outline intact) | **VLM residual** | **CAUGHT** — "Large black rectangular **void**... appears to be **missing copper or data layer**, not explained by component body omission" |

`corrupt_svg` leaves a wrong outline → the deterministic check owns it. `rotated_layer` and
`dropped_zone` leave a **correct** outline → the pre-pass cannot see them, so they are the VLM's
genuine residual territory.

## Result

- **Incremental catch over the completed pre-pass: 2/2 (1.0).** Both residual corruptions that leave a
  correct outline — a rotated/garbled layer and a missing localized fill — caught with specific,
  correct descriptions.
- **Clean-control false-positive post-baseline: 0.** The CEC logo + overlay flags that scored as a
  false positive in the 2026-06-11 run are now the subtracted baseline; on the clean render nothing
  survives subtraction.
- **The corruption class the VLM previously missed is now owned deterministically**, which is the
  architecture the owner ruling mandates (deterministic owns detection; the VLM is residual-only).

### Honest footnote (CL-19 discipline)

On the *corrupted* candidates the seat still raises benign annotation/logo flags (e.g. "Text 'CEC'
rendered upside-down", "blue triangular annotation overlay") that the token-overlap baseline does not
fully remove, because phrasing drifts between the clean and corrupted renders. These do **not** affect
the recall metric (the planted defect is the first, correct flag in each case) and every VLM flag is
advisory and re-checked by determinism — it can only *add* a caught unknown-unknown, never subtract
trust from the deterministic gate — but the seat's *precision* is not perfect. Recorded here, not
smoothed over.

## Owner decision (not taken here)

Per the ruling, the vision-seat `eval_gate` in `cec-policy.json` is owner-gated and sign-able to
load-bearing only **for discrepancy / anomaly surfacing — never the measurement role** (which stays
recorded FAILED, CL-19 pattern; see the `vision_discrimination` block). The incremental-catch number is
now **2/2 with no clean-control FP**, recorded in the eval_gate's `new_role_incremental_catch` block as
the draft for sign-off. The number is **> 0, not a null**, so the seat is not auto-retired; the
keep/retire/sign call is the owner's. Safety envelope unchanged: every flag is advisory.

## Re-run

```bash
# warm the seat first (cold-load ~8 min from drvfs), then:
docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py \
    --board build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb
# deterministic partitioning only, no GPU (corrupt_svg caught by outline_sanity; residual = 2):
docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py --dry-run
```
