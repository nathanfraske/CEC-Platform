# Visible refinement pass — 2026-11-05

## Four accepted board edits, existing operators only

Input: `checkpoints/review-20261105-layout-craft/receipt.json`, SHA256
`823d7b711c903ac8748a596a9a56e53cdbc356160dfcec2e329cfb21a346b16b`.
Every edit was frontier-authored, privately constructed and independently
received. **No implementation, thresholds, part budgets or design rules
changed in this pass.** These are applications of the existing generalized
pipeline, not new board-specific repair code.

| Board / operation | Before → after | Measured outcome |
| --- | --- | --- |
| Hub, `replace_chain`, DETECT1 on In2.Cu | Six-segment side excursion → one diagonal and vertical beside D1/C15 | 1.111270 mm shorter; exact ports, launch/arrival rays, 200 µm width, face and locks retained |
| ATX, `replace_chain`, I2C_SCL on F.Cu | Four-segment short offset shelf → continuous 45° diagonal and vertical | 0.058579 mm shorter; source terminals, rays, 200 µm width, face and locks retained |
| EPS, `repair_chain`, DETECT on In2.Cu | 45° crossing of F.Cu CAN_TX → 90° crossing | **One real field finding cleared**, four → three; zero added length and no replacement/new finding |
| 12VHPWR, `power_contour`, P6 lower output on B.Cu | Rounded shoulders/end overhang → deliberate 45° chamfers matching adjacent P5 | **Two exact craft findings cleared**, 159 → 157; original 2.5 mm rated strokes, vias and current contract retained |

The two shortening edits save **1.169849 mm** combined. Length is not an
electrical rating. No placement, Ground return, via/drill, component, board
dimension, mating interface or source current/manufacturing requirement
changed. This slice deliberately avoids cosmetic part dragging that would
worsen actual courtyard, owner-pin or immediate-return geometry.

Native opens and errors remain zero on all nine PCBs. The 283 inherited
warnings remain. Field-policy blockers decrease **seven → six**: EPS three,
12VHPWR three; the other seven boards have zero under this checker. These
are bounded geometric nonregression/improvement results, not full SI/EMC,
barrel current, thermal, mating, fabrication or production qualification.

## Exact selected jobs and native identities

All jobs use the same source-bound workspace, code epoch and physical-policy
environment (`CEC_THERMAL_GPU_AMG=1`). Full evidence is in
`C:/Users/Admin/Documents/CEC-Board-Reviews/visual-refinement-20261105/work/`.

| Board | Job | Candidate SHA256 |
| --- | --- | --- |
| Hub | `50396a79d7bb5f0f064eac5a` | `c7f56f3ed734716f23c6e8a32b6a0edee092c0677081fae2ed6ad6a12fa7addc` |
| ATX | `21f86be4a96d9c460a089db1` | `cf4d332c30c6466087584db02979707a446716d8c057124a6434dd474f9484fc` |
| EPS | `9732e2befe6a399add51dc4c` | `2155294c33e99b68d0156faf5a41e323afe4abd992bd31242ee9e264d7d69a35` |
| 12VHPWR | `b7f1d44e729e3a7e4e75b470` | `34765dc6995f0b84c9b434a3d5fd6d9294ec035a8fd7f2de27bb7b2e10dbe25f` |

Both PCIe boards and all three daughterboards are byte-identical to input.
Fresh exact-source field jobs cover those five; each selected board has its
own saved-candidate field evidence. Old observations remain historical and
are never used to conceal changed physical fault identities.

## Visual inspection and refusals

Before/after **actual saved native copper** was viewed and shown during the
pass, with no full-name Fab overlays. Every changed region is covered by
hash-bound native SVG pairs. The EPS red/ochre overlay compares F.Cu/In2.Cu;
it is not a same-layer short. F.Cu geometry is unchanged by the EPS repair.
The underlying native layer plots and work orders are retained in the
portable checkpoint for independent review and layer comparison.

The EPS target
`4b59dc7fba3c23cbf56475ef1852679d48628ca4188b3a99eb90f23be4346357`
is absent. All three remaining EPS physical IDs are identical to source;
12VHPWR's three field IDs are also unchanged. The source downstream DETECT
vertical is retained: earlier diagonal replacements crossed CAN_RX and
were correctly rejected. The successful equal-length perpendicular repair
uses `repair_chain` with **zero growth allowance**, not shortening-only
`replace_chain` and not a weakened field threshold.

Unselected work is not reported as progress:

- A Hub KVM reference shortcut had copper clearance but failed the actual
  edge/cutout guard. It was not selected.
- An ATX I2C whole-chain shortcut collided with foreign copper during the
  read-only screen. The accepted local shelf cleanup stays in a proven
  clear corridor instead.
- An initial ATX combined trial included a nominal DETECT corner chamfer
  entirely covered by an unchanged pad. Before/after inspection showed no
  visible copper improvement there, so the final selected job omits it.
  Only the actually visible I2C change is counted.
- The prior Hub C27 local-supply and ATX power/Kelvin coverage holds remain;
  neither is bypassed or quietly called repaired here.

## Remaining field work

These are full paired-conductor envelopes in millimetres, not precise
crossing loci or fabrication clearances. Exact semantic IDs, actual segment
UUIDs/endpoints and measurements are in the retained current field reports.

| Board | Physical interaction | Angle / parallel overlap | Copper envelope [xmin, ymin, xmax, ymax] |
| --- | --- | --- | --- |
| EPS | CAN_TX F.Cu ↔ SENSEC2_HI F.Cu, unshielded parallel | 0° / 3.390 mm | [61.4, 16.075, 72.6, 16.92] |
| EPS | CAN_H In2.Cu ↔ SENSEC2_HI F.Cu, first crossing | 45° | [61.4, 15.425, 73.935, 17.58] |
| EPS | CAN_H In2.Cu ↔ SENSEC2_HI F.Cu, second crossing | 45° | [71.78, 15.425, 73.935, 18.05] |
| 12VHPWR | CAN_RX In3.Cu ↔ DETECT In2.Cu | 45° | [45.7061, 27.026, 54.074, 42.7656] |
| 12VHPWR | CAN_RX In3.Cu ↔ ISENSEP6 In2.Cu | 45° | [42.625, 47.125, 45.125, 49.625] |
| 12VHPWR | CAN_RX In3.Cu ↔ CAN_H In2.Cu | 45° | [45.074999, 42.975, 47.3827, 44.8] |

Next decisions should coordinate these corridors and pair/reference
requirements, rather than moving the protected Kelvin conductors or
exchanging one crossing for another. Pair and physical return-path
qualification remain independent; a geometrically perpendicular crossing
does not by itself prove EMC compliance.

## Publication and verification

The new portable checkpoint is
`checkpoints/review-20261105-visual-refinement/`; `checkpoints/current.json`
binds receipt SHA256
`036815e07d648053eed932e8f2d40c455fccc61d339527f1bcde6e87782894bb`.
All nine relocated native checks completed: zero opens/errors/exclusions,
283 inherited warnings. Each selected job passed the complete required
native, transaction, pair, semantic-craft and field checks. The EPS repair
additionally passed its independent route contract and exact field-target
clearance. The power contour additionally passed source-derived current,
native material/neck and assembly receiving. Nothing is credited from
partial/failed jobs.

The active workbench/native-contour/inspector suite passed **434 tests** in
67.94 seconds against the new pin. No implementation changed, so earlier
backend tests are not relabelled as a new replay. The four saved candidates
and all nine relocated boards received fresh physical/native checks here.

Local evidence root:
`C:/Users/Admin/Documents/CEC-Board-Reviews/visual-refinement-20261105/`.
The live trackpad inspector is explicitly rebuilt and repointed only after
the new checkpoint is complete. No extra board-view tabs, legacy waves or
background model managers are started.
