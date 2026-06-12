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

## Naming the delta (candidates, by git archaeology since the 06-09 freeze)

`versions.env` / the FR jar are **unchanged** (still 1.7.0 pinned) — not a toolchain version bump. The
changed inputs are all **code paths**:

| input | changed | commit(s) | why it could move thermal/drc |
|---|---|---|---|
| **thermal-FEM** (`cec_synth_pipeline.electrothermal_solve`) | 2026-06-10 | `6f10b96` (AM-04 analytic anchors), `bb9fb7a` (CL-03), `1549b69` (CL-25) | the model that reads max_T from the copper. The handoff's "MODEL DEBT" note states the fix **"changes the SB-08 golden thermal band"**; AM-04 added IPC-2152 conservatism. **Prime suspect.** |
| **FR layer-policy** (`cec_fr`) | 2026-06-11 | `d26651d` (layer policy + plane pricing) | observed live: `layer policy: stripped 2 track segment(s) from plane layer(s) ['12V','GND']`. Changes which copper FR lays → routed-copper input to the thermal model. Explains the **drc 4 → 10** (routing changed). |
| **scorer** (`cec_score`) | 2026-06-11 | `20c8978`, `30a38c7` | DRC filtering / gates; could shift the reported drc count. |
| **board** | only at the keepout | `9eb33b0` | accounts for the +4.7, not the +25. |

## Scope flag (item 2c's explicit ask)

This is **not** a toolchain version bump (FR jar / KiCad / container pinned), so it does **not** silently
touch every future route via a dependency. BUT the thermal-FEM change is a **platform-wide model change**:
every board's reported `thermal_max_T` shifted when `cec_synth_pipeline` changed on 06-10 — the SB-08
golden is just where it surfaced. If the new model is the more-correct one (the MODEL DEBT note says the
**old** model was ~5× optimistic — summing all net segments incl. zero-current Kelvin stubs instead of the
serial min-cut), then **128.2 was an optimistic-model artifact and ~153–158 is the honest read of the same
copper**. That materially reframes item 3:

- The board did not get 30 °C worse. The **model got more conservative** (+25), and the keepout added a
  real but small +4.7.
- So item-3a re-route targets the **+4.7 keepout term** (restore the displaced current to a cooler
  corridor → back toward 153). The 128.2 "old baseline class" is likely unreachable under the corrected
  model and should not be the re-route target — the honest target is the corrected-model pre-keepout
  number (~153), not the optimistic-model 128.2.
- Item-3b acceptance rationale should state plainly that the baseline moved because the **thermal model
  was corrected**, with margin-to-material-limits computed under the new (conservative) model.

## Confirmation still owed (the precise per-commit bisect)

This forensic NAMES the candidate deltas and proves code-drift is dominant. To pin the exact commit that
moved 128.2 → 153.2, bisect: run the pre-keepout board with `cec_synth_pipeline` / `cec_fr` checked out
at each candidate commit. Expected: the AM-04 thermal-FEM commit (`6f10b96`) carries most of the +25; the
FR layer-policy commit (`d26651d`) carries the drc 4 → 10. That bisect is the next no-approval step.

Reproduce the decisive experiment:
```bash
git show 9eb33b0~1:tests/golden/eps-8pin/eps8pin-module.kicad_pcb > /tmp/old.kicad_pcb
# route + score + thermal /tmp/old.kicad_pcb under current code at passes 10/opt_time 20
```
