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

## Pinned CURRENT-model values (the known debt, measured 2026-06-10)

| term | current model | correct (hand) | debt |
|---|---|---|---|
| HC cross_mm2 | **1.044** (= 3 × 0.348, segment-SUM) | 0.348 (serial min-cut) | ~3× optimistic area |
| HC dT | **4.8 °C** | ≈ 6.12 °C (Picard on min-cut) | optimistic |
| via I split | 5.0 A ✓ | 5.0 A | — |
| via dT | 175.3 °C | ~same (constant delta only) | — |
| shunt P | 0.05 W | 0.05 W ✓ | — |

PR one (this PR) pins the **current model** column as the composition anchor.
PR two (the debt fix: serial min-cut, per-cluster via split, k-by-feature-layer)
moves the anchor to the **correct** column — with this file as the witness that
the movement direction was derived BEFORE the fix, and the SB-08 band re-freeze
riding the same owner-reviewed diff. Chart-point anchors (dt_ipc formula) must
NOT move in PR two: the formula is not the debt, the composition is.
