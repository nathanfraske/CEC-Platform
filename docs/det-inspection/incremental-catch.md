# VLM incremental-catch measurement — the number the seat rides on

Authority: `docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md` (OWNER RULING) §3:
*"The seat's existence rides EXCLUSIVELY on the incremental catch number ... measured on planted
unknown-unknowns the checkers cannot see by construction ... a documented null retires the seat."*

Harness: `scripts/cec_vision_incremental.py` → `incremental-catch.json`. Live run 2026-06-11 on
`cec-worker-vision` (Qwen3.6-35B-A3B + mmproj), board `pcie-8pin-2port-routed`.

## What was measured

Three **render-stage** corruptions where the **board file stays correct** (so the DFM layer, which
reads the board file, sees nothing) and there is **no frozen reference** (the fresh-synthesis case, so
the render-diff has nothing to diff). The deterministic pre-pass therefore MISSES all three **by
construction** — confirmed: DFM finds **0 new violations** on the untouched board file. The only thing
that can catch them is an intelligent read of the single render = the VLM anomaly pass.

Samples are committed under `incremental-samples/` (clean + the three corruptions).

| scenario | corruption (render only) | pre-pass | VLM | evidence (VLM's own words) |
|---|---|---|---|---|
| dropped_zone | one localized 12V pour painted out of the render | MISS | **CAUGHT** | "Large black rectangular void in lower-left quadrant appears to be **missing copper or data layer**, not explained by component body omission" |
| rotated_layer | back copper rotated 7° in the render | MISS | **CAUGHT** | "corrupted or **mis-exported** graphic element... **layer misalignment** or export inconsistency" |
| corrupt_svg | whole body sheared by an injected SVG transform | MISS | miss* | flagged *local* oddities ("misaligned pads", "isolated pad cluster") but never named the **global** shear |
| CLEAN_CONTROL | none (intact render) | — | **false positive** | flagged the legitimate **CEC copper logo** as a "non-PCB artifact / mirrored text" |

\* conservative scoring (keyword evidence per scenario). The VLM raised *related local* flags on the
sheared board, so a human chasing them might reach the corruption — but it did **not identify the gross
geometric distortion**, so it scores as a miss.

## Result

- **Incremental catch over the completed pre-pass: 2/3 (0.667).** Both *localized* render corruptions
  (a missing fill, a rotated/garbled layer) caught with specific, correct descriptions.
- **The miss is CL-21-consistent and informative**: the VLM caught the two *localized structural*
  anomalies and missed the one *global geometric* distortion (a uniform shear). That is exactly the
  measurement/geometry weakness CL-21 predicts — the seat is good at "this region looks wrong / a
  feature is missing," weak at "the whole board's geometry is off."
- **False-positive rate is non-zero**: on a clean render it flagged the intentional CEC copper logo.
  Tunable (a one-line benign-feature note to the prompt — *not* a measurement crutch), recorded here
  un-tuned for honesty.

## Owner decision (not taken here)

Per the ruling, the vision-seat `eval_gate` in `cec-policy.json` is owner-gated and sign-able to
load-bearing **only against this incremental-catch number**, and **only for discrepancy / anomaly
surfacing — never the measurement role** (which stays recorded FAILED, CL-19 pattern). The number is
**> 0, not a null**, so the seat is *not* auto-retired; but it carries a real false-positive rate, so
the keep/retire/tune call is the owner's. The safety envelope is unchanged: every VLM flag is advisory
and re-checked by determinism — it can only *add* a caught unknown-unknown, never subtract trust from
the deterministic gate.

## Re-run

```bash
# warm the seat first (cold-load ~8 min from drvfs), then:
docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py
docker exec docker-routing-1 python3 /workspace/scripts/cec_vision_incremental.py --dry-run  # no GPU
```
