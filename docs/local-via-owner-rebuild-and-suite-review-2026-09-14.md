# Local-via owner reconstruction and concurrent suite review

## Admitted physical improvement

The current PCIe2 continuation was repaired by the canonical
`repair_local_pofv_admitted` stage in **19.651 seconds**. It now automatically
falls back from fixed-centre sizing to a bounded local owner reconstruction.

| Independent measurement | Before | After |
| --- | ---: | ---: |
| Structural DRC | 0 | 0 |
| Unconnected ratlines | 12 | 12 |
| Minimum-dimension violations | 9 | 7 |
| Invalid via/pad overlaps | 1 | 0 |
| Non-octilinear segments | 1 | 1 |

Kelvin and differential-pair checks remain passing; no foreign routing on
laid power pours was introduced. Exact protected-prefix, footprint-pose and
pad-net/position comparisons pass. The six input/hierarchy signatures and
shared engine signature were unchanged throughout the concurrent replay.
This is **not routing closure or fabrication release**. Seven dimensional
violations, twelve opens, one non-octilinear segment and broader pre-existing
release qualifications remain. No fabrication outputs were released.

- Input: `build/parallel-prefix-followup-20260914/pcie-8pin-2port/04-route/winner.kicad_pcb`.
- Input SHA256: `94f0633579da8ed288562cb5558e9e92172dc169d282b5667bf36002007debc2`.
- Admitted output: `build/local-via-rebuild-suite-20260914-c/pcie-8pin-2port/board.kicad_pcb`.
- Output SHA256: `82f98e64bc47ad32e7e7333c669b4944db56b97d3c2a89d11a964a3cddd692ba`.
- [Verified dashboard review](http://localhost:8090/?id=20260914-pcie2-local-via-rebuilt).
- Body-free review: `C:/Users/Admin/Documents/CEC-Board-Reviews/20260914-pcie2-local-via-rebuilt/render.png`.

The actual admitted move is a 0.21 mm reseat of the generated ground barrel
into its real SMD land, at the already-declared 0.30/0.20 mm POFV geometry.
Three branch/land contacts were reconstructed with five octilinear segments.
These are measured output facts, not a coordinate repair table in the engine.

## Generic changes and forensic findings

`cec_local_via_rebuild` selects only an independently failing same-net pad
overlap with **exclusive generated-local-via ownership**. It derives at most
eight seats within 1.5 mm from the actual overlapping SMD land and the board's
declared POFV profile. Native full-land containment, all-layer clearance,
hole spacing, branch reconstruction and endpoint-neckdown proofs are mandatory.
Foreign-pad contacts, precision nets, unrelated owners, non-through vias,
missing profiles and stale boundaries are refused.

The existing spatial dimension repair performs reconstruction. It removes and
re-proves the selected local ownership rather than inheriting the old exemption.
Incident generated endpoint escapes can be rebuilt; other locked tracks and
contacts stay immutable. Full independent score, constraint-identity and fab
comparisons still govern promotion. No clearance, current or escape limit was
relaxed. A failed trial is not saved; an admission failure leaves the source
family unchanged. A second pass on the admitted result is an unchanged no-op.

Two additional root causes were caught during testing:

1. **Self-collision:** the hole-distance guard checked the old barrel as if a
   relocation were drilling a second hole. On the unsaved trial, the exact
   owned barrel is now moved first and passed through the existing identity-
   scoped replacement check. Every other same-net/foreign barrel still blocks.
   This correction also applies to ordinary spatial dimension repair.
2. **Whole-escape narrowing:** the default shortest route kept a 0.96 mm local
   branch narrow, exceeding its independently measured 0.85 mm allowance.
   Reconstruction now asks the existing profiled router to minimize narrow
   length, widening sooner. The original allowance remains enforced.

Tests also exposed KiCad `SaveBoard` rewriting project settings during a
copper-only change. Spatial repair now uses `aSkipSettings=True`; it leaves
project/rule bytes intact rather than silently normalizing them.

## Concurrent board outcomes

`build/local-via-rebuild-suite-20260914-c/receipt.json` records all six inputs:

| Board | This slice |
| --- | --- |
| PCIe2 | One admitted local-via reconstruction; metrics above |
| PCIe3 | No eligible local-via assembly failure; unchanged |
| 12VHPWR | No eligible local-via assembly failure; unchanged |
| Hub | No eligible local-via assembly failure; unchanged |
| EPS | Downstream intake correctly refused its unadmitted interface ECO |
| ATX24 | Downstream intake correctly refused its unadmitted interface ECO |

These are concurrent **repair-stage replays**, not six new full routed boards.
The first exploratory replay stopped its aggregate receipt on an uncaught
EPS/ATX intake refusal; per-board receipts survived. The final runner records
that refusal explicitly without bypassing it or suppressing other boards.
The final `-c` receipt is authoritative; `-b` records the intermediate narrow-
escape refusals, and the unlettered directory includes the original false
self-collision evidence.

EPS/ATX terminal clearance remains unresolved. Inspection of the complete
single-page `lib/datasheets/XFCN_T34069_C481452.pdf` confirms the side-facing
threaded interface depicted by the footprint. It does not supply a qualified
main-to-daughterboard 3D contact transform. An arbitrary main-board depth
stagger must not be treated as a matching daughterboard hole displacement.
No staggered packing solution, exact 2D impossibility proof, footprint land
change, row widening, pinout change or dimension increase was made here.
The existing straight-row native spacing screen is still only that screen.

## Regression evidence

- `build/local-via-rebuild-integrated-tests-20260914.log`: **177 passed**,
  53.68 seconds, including the full-pipeline adapters, dimension repair,
  transformed local-via fixtures, original neckdown proof and power dependency
  integration. Earlier 51-test count overlaps this suite; do not add them.
- `build/local-via-rebuild-verification-20260914/receipt.json`: exact protected
  prefix, poses and pad nets preserved; admitted-board repeat and historical
  control-copy repair both unchanged with no errors.
- `build/local-via-rebuild-control-20260914.json`: board SHA and all four probe
  objects equal `build/power-terminal-control-20260914.json`. Historical
  zero-DRC/zero-open copper and its broader pre-existing failures are unchanged.
- `build/local-via-rebuild-generalization-20260914.json`: 58 declared core
  modules, zero core findings. Existing runtime/physical findings remain
  380/23; the whole pipeline is not declared fully generic or release-ready.
- `git diff --check` passed. WSL free storage was 72 GiB at review.

## Continuation

Use the exact admitted output hash above as the PCIe2 continuation; never select
an older dashboard entry or source by modification time. A bounded canonical
PCIe2 routing follow-up is warranted because a physical local obstacle changed.
Do not repeat unchanged failed Hub/12VHPWR/PCIe3 waves on the strength of this
inapplicable repair. Their next shared work is coordinated owned-priority
access/power dependency recovery, preserving protected power copper and proving
any regenerated signal owner end to end. EPS/ATX need paired interface geometry
and mechanical authority, not arbitrary downstream route effort.
