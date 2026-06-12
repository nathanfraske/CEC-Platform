# Deterministic inspection pre-pass — benchmark record

Authority: `docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md` (OWNER RULING).
Grounded by: `docs/research/grounding-cl21-vlm-seat-redesign-2026-06-11.md` (the head-two dive).

The owner ruling: **the deterministic pre-pass owns detection**; the VLM is narration + open-ended
anomaly only and its seat rides exclusively on its incremental catch over this pre-pass. The gate
before any VLM work: **≥99% per-class catch on the enumerable classes, 0 false positives**.

## The pre-pass (two layers)

1. **Render-diff** — `scripts/cec_render_diff.py`. Per-channel abs-diff of the candidate's model-free
   copper render vs the frozen known-good reference render → threshold → morphological open/close →
   connected-component region list. No alignment stage: the renders are pixel-registered by
   construction (same kicad-cli SVG → rsvg-convert toolchain, same `--page-size-mode 2`), the AOI
   condition under which reference subtraction sits below 0.2% error. Catches every defect that is a
   copper **delta** vs the reference.
2. **DRC/DFM** — `scripts/cec_dfm_check.py`. Absolute manufacturability violations on a **single**
   board (the case a freshly synthesized board with no prior golden presents):
   - **native KiCad checks, confirmed enabled** (item 3): `copper_sliver`, `isolated_copper`
     (dead copper), `connection_width` (necking / mousebite / starved connection — forced on with a
     DFM `.kicad_dru` `(constraint connection_width (min 0.13mm))` regardless of board settings),
     `clearance`, `shorting_items`, read at `--severity-all` with `--refill-zones`. None of these are
     in the DRC `ignored_checks` set; they run and simply do not fire on the clean reference.
   - **custom acid-trap rule** — KiCad's one native gap (no acute-angle predicate). A geometric scan
     for an acute copper wedge: two same-net track legs leaving a shared vertex with `< 40°` between
     their outward directions (below 45° so the routine 45° router bend does not fire). It over-fires
     in absolute terms at benign pad convergences, so it is meant to run **reference-baseline-
     subtracted** — which the battery does.

A class is **caught** if **either** layer flags a region overlapping the planted site.

## Battery result — `cec_defect_battery.py` → `defect-battery.json`

Reference board: `build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb`. Each defect is planted
on a copy down to minimum feature size, rendered at `CEC_DIFF_ZOOM=8` (a 0.1–0.2 mm feature is
sub-pixel at the SVG's native 96 dpi), diffed vs the reference render, and DFM-checked with the clean
reference's violations subtracted (so DFM has a 0-by-construction false-positive control).

| class | caught | by | notes |
|---|---|---|---|
| open | ✓ | diff+dfm | track deleted |
| short | ✓ | diff+dfm | bridge two nets → shorting_items |
| mousebite | ✓ | dfm | necked middle segment → connection_width |
| spur | ✓ | diff+dfm | 0.2 mm stub ⟂ off a track midpoint |
| pinhole | ✓ | diff | min-feature copper void (excised piece) |
| spurious_copper | ✓ | diff | isolated 1 mm dab |
| sliver | ✓ | diff+dfm | 0.06 mm thin wedge → track_width |
| acid_trap | ✓ | diff+dfm | 20° wedge at a track endpoint → custom acid_trap rule fires |
| unexpected_keepout | ✓ | diff+dfm | copper cleared in a window (absence) |
| corridor_anomaly | ✓ | diff | copper intruding a reserved clear band |
| wrong_net_fill | ✓ | diff+dfm | wide bridge to a different net → shorting_items |
| stale_fill_conflict | ✓ | diff | copper changed while facts stay correct (the conflict case) |
| CLEAN_CONTROL | — | — | 0 diff regions, 0 new DFM → **FP = 0** |

**Per-class recall 12/12 (100.0%), false-positive regions 0 → PASS.**

The gate is met → VLM work (re-role to narration + the incremental-catch measurement) is unblocked.
The classical six (open, short, mousebite, spur, pinhole, spurious copper) and the gap classes (stale
fill, acid trap, unexpected keepout, corridor anomaly, wrong-net fill) are all caught; the conflict
case (`stale_fill_conflict`) is caught by the render-diff exactly because the diff is reference-based,
not facts-based.

## Re-run

```bash
docker exec docker-routing-1 python3 /workspace/scripts/cec_defect_battery.py \
    --board build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb
```

Runs in the routing container (needs pcbnew + scipy + rsvg-convert). Each pcbnew board op is isolated
in its own subprocess — one board load per interpreter — because repeated `LoadBoard` in a single
interpreter returns invalidated SWIG proxies (recorded pcbnew footgun).
