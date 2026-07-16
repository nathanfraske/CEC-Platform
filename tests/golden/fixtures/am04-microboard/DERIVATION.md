# AM-04 micro-board — hand derivation (Ruling 8; the PR-two debt-fix witness)

Geometry (built by `scripts/probes/build_am04_microboard.py`, one net `HC` @ 10 A):
J1 pad → **17 mm of 5 mm-wide F.Cu** → RS1 (2-pad shunt) → **9 mm of 5 mm F.Cu** →
**via pair (0.6/0.3)** → **10 mm of 5 mm B.Cu** → J2 pad. 2 oz outer copper
(0.0696 mm). Ambient 25 °C, `net_currents: {HC: 10.0}`.

## Hand values (the CORRECT composition)

- One 5 mm × 2 oz section: **cross = 5 × 0.0696 = 0.348 mm²**. The three track
  segments are in SERIES — the serial min-cut governs: **0.348 mm²**, J = 28.7 A/mm².
- IPC-2221 external on the min-cut: `dt_ipc(10, 0.348) = 5.87 °C`; with the
  Picard ρ(T) correction at 25 °C ambient: **dT ≈ 6.12 °C → T ≈ 31.1 °C**.
- Via pair: split 10 A → **5 A per via** ✓. Barrel cross ≈ π·d·t_plating =
  π·0.3·0.0175 ≈ 0.0165 mm² → J ≈ 303 A/mm² plain (model uses its own plating
  constant → J 212, dT 175.3). Deliberately undersized — the via-math anchor.
- Shunt RS1: solver default 0.5 mΩ (no Value prop on the synthetic part) →
  P = I²R = **0.05 W** → dT = 0.05 × 25 °C/W = **1.25 °C**.

## Composition values — PR one (pinned debt) → PR two (corrected)

| term | PR-one model (debt) | PR-two corrected (now solved) | basis |
|---|---|---|---|
| HC cross_mm2 | 1.044 (= 3 × 0.348, segment-SUM) | **0.348** (serial min-cut) | series ≠ parallel |
| HC dT | 4.8 °C | **6.12 °C** | Picard on min-cut, k external |
| via I split | 5.0 A ✓ | **5.0 A** (per-cluster, one transition) | unchanged here |
| via dT | 175.3 °C | **175.3 °C** | via barrel anchor unchanged |
| shunt P | 0.05 W ✓ | **0.05 W** | I²R unchanged |

PR one pinned the **debt** column; **PR two (this diff) lands the fix** — serial
min-cut (`_min_cut`), per-transition-cluster via split (`_via_cluster_sizes`), and
the IPC k taken from the bottleneck cut's actual layer (rename-proof layer-ID test)
rather than pour membership. `test_am04_anchors.T8cCompositionAnchor` now asserts the
**corrected** column, and the SB-08 thermal band is re-frozen on the same
owner-reviewed diff. This file is the witness that the movement direction was derived
BEFORE the fix. The chart-point/Picard anchors (the `dt_ipc` formula itself) did NOT
move: the formula was never the debt — the composition was.

Note the corrected micro-board dT (6.12 °C) reproduces the independent Picard anchor
`_picard_dt(10, 0.348, 25, True)` exactly: the min-cut feeds the formula the single
0.348 mm² section, on an outer layer, which is the whole point of the fixture.
