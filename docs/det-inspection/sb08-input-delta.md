# SB-08 golden — input-delta forensic (owner directive 2026-06-12, item 2c)

**The question.** The original `drc=10 / 153.2 °C` red **predates** the LOGO1 keepout and was mislabeled
"FR variance." But FR 1.7.0 is deterministic (item 2a: no seed, byte-stable). A deterministic system
that drifts did so because an **input changed**. Name the delta.

## The decisive experiment

Route + score + thermal the **pre-keepout golden board** (`tests/golden/eps-8pin/eps8pin-module.kicad_pcb`
at `9eb33b0~1`) under **current code**, at CI params (passes 10 / opt_time 20):

| board | code | drc | thermal_max_T | tracks | vias |
|---|---|---|---|---|---|
| pre-keepout | 2026-06-09 (frozen baseline) | 4 | **128.2** | — | — |
| pre-keepout | **current** | **10** | **153.2** | 519 | 79 |
| post-keepout (#37) | current | 0 | **157.9** | 526 | 78 |

The middle row **reproduces the "drc-10 / 153.2 red" exactly**. It is the *same board* — only the code
changed. So:

### Decomposition of the +30 °C (128.2 → 157.9)

- **+25.0 °C — CODE drift** (128.2 → 153.2, and drc 4 → 10): same pre-keepout board, old code vs current.
  **This is the dominant term.**
- **+4.7 °C — the LOGO1 keepout** (153.2 → 157.9, and drc 10 → 0): the keepout cleared the logo DRC but
  displaced current into a hotter corridor (item 2b's domain). **Minor term.**

The "variance event" was never variance: it was the pre-keepout board scored by drifted code.

## Naming the delta — PINNED by runtime bisect to FR layer-policy `d26651d` (thermal model exonerated)

`versions.env` / the FR jar are **unchanged** (still 1.7.0 pinned) — not a toolchain version bump. The
bisect was run by holding the pre-keepout board constant and swapping code via git worktrees:

| code state | drc | thermal | tracks | vias | reads |
|---|---|---|---|---|---|
| **thermal model** old vs new, *same routed board* | — | **153.2 both** | — | — | **thermal-FEM is NOT the cause** (invariant) |
| FR at `d26651d~1` (pre-layer-policy = `545f28e`) | **4** | **128.2** | 556 | 84 | reproduces the 06-09 freeze EXACTLY |
| FR current (post-`d26651d`) | 10 | 153.2 | 519 | 79 | the "variance" red |

→ **The entire +25 °C (and drc 4 → 10) is `d26651d`** — the **owner-ratified FR-04 layer-policy** change
(`CEC_FR_PLANE_POLICY`: deny FR from routing signal on plane layers 12V/GND; blind auditors re-derived it).
Before it, FR routed ~37 extra segments **on the power planes** (556 vs 519 tracks), which spread current
and ran cooler. After it those plane segments are stripped, so current concentrates in the routed
corridor → +25 °C. The thermal-FEM (`cec_synth_pipeline`, AM-04) is **not** involved (it gives 153.2 on
the same routed board under both old and new code).

**This is not a bug to revert.** The 128.2 was achieved by FR routing on power planes — which the
owner-ratified FR-04 policy correctly forbids. So the old baseline was partly an artifact of improper
plane routing; **153.2 is the honest thermal under the correct layer policy**.

## Scope flag (item 2c's explicit ask)

Not a toolchain version bump — but `d26651d` is **platform-wide**: it denies FR plane-layer routing on
*every* board. The SB-08 golden surfaced it because this board **leaned on plane-layer routing for thermal
spreading** — a real design signal: the eps cable corridors don't carry enough dedicated thermal copper,
so FR was (improperly) using the planes to spread current. That dependency is now exposed.

## Reframing item 3 (the decision)

- The board did not get 30 °C worse, and the thermal model did not change. A **correct, ratified routing
  policy removed an improper thermal crutch** (plane-layer signal routing), revealing the board's true
  ~153 °C under proper routing; the keepout adds the last +4.7.
- **Item-3a re-route must NOT revert the ratified FR-04 policy.** The principled fix is to give the board
  *real* thermal copper so it no longer needs plane routing — widen the cable corridors / add pour, and/or
  FR-02 waypoint the hot-corridor current — targeting back toward ~128–132 at drc 0 under the *current*
  layer policy. If that target is reachable, re-route wins.
- **Item-3b acceptance** states plainly: the baseline moved because the **owner-ratified FR-04 layer
  policy** stopped FR from spreading current across the power planes; 153/157.9 is the honest thermal
  under correct routing, with margin to material limits computed accordingly.

Bisect reproduction (worktree the pre-policy commit, route the pre-keepout board, thermal it):
```bash
git worktree add /tmp/wt d26651d~1
# route tests/golden/eps-8pin/eps8pin-module.kicad_pcb@9eb33b0~1 with /tmp/wt/scripts/cec_fr -> drc 4 / 128.2
```

Reproduce the decisive experiment:
```bash
git show 9eb33b0~1:tests/golden/eps-8pin/eps8pin-module.kicad_pcb > /tmp/old.kicad_pcb
# route + score + thermal /tmp/old.kicad_pcb under current code at passes 10/opt_time 20
```
