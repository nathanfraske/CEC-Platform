# Exact heat sources, fan sensitivity and bounded 12VHPWR compaction

Date: 2026-09-07. This slice changes reusable analysis/diagnostic code and the
current 12VHPWR search policy. It does not grant routing or fabrication admission,
replace a canonical PCB, populate the optional fan header, or choose a fan.

## Authority and preserved controls

The experiment uses the current `beta/12vhpwr-standard` hierarchical schematic,
schematic-first normalization and exact source-intake checks. Its supply is the
current direct TLV75533 LDO, not the removed buck/post-LDO topology. The MCU's
physical module end remains an edge-placement constraint; this is not an RF-use
requirement. All three retained artifacts pass source intake.

Results and commands:

- `build/12vhpwr-fan-compaction-width-schema-20260907/comparison.json`
- `build/12vhpwr-fan-compaction-width-schema-20260907/02-placement/placement-candidates.json`
- `build/12vhpwr-fan-compaction-width-schema-20260907/02-placement/candidate-evaluation.json`
- `build/12vhpwr-fan-compaction-width-schema-20260907/heat-contract-replay.json`
- `build/fan-heat-pcie-regression-20260907.json`

The root/staging 12VHPWR PCB, old 12VHPWR candidate, Hub candidate and archived
PCIe two-port control hashes are unchanged. The PCIe replay still reports
0 DRC, 0 unconnected, 615 tracks, 226 vias and 1242.073 mm trace length. Its eight
existing modern release-blocker categories and their details are unchanged;
zero DRC/opens is not a claim that those other checks pass.

## Reusable fixes implemented

1. **Heat-source identity:** `U1` previously also matched `U10`, `U11`, etc.
   The field solver now maps exact references only, conserves the requested
   component watts and refuses missing physical sources or duplicate references.
   Per-source applied watts and local PCB-pad temperature are reported.
2. **Current electrical budget integration:** controller rows have a typed thermal
   role. The source inventory uses that envelope and applies its design margin
   once. Single-regulator loading follows the aggregate budget; multi-regulator
   systems require explicit load allocation. Removed historical 12VHPWR/Hub
   per-reference regulator assumptions that no longer described current hardware.
3. **Current source/artifact contract:** the manifest selects the hierarchy, and
   source values must match the actual PCB. Missing/changed parts, uncovered active
   devices and unverified source assumptions remain visible. Actual populated
   low-ohmic resistor values supply the existing shunt-loss model.
4. **Incremental convection sensitivity:** scalar or grid-shaped additional
   heat-transfer coefficients enter both the field equation and energy balance.
   Zero is the fan-off baseline. No free-air CFM is converted into guessed cooling.
   Historical metal-case/TIM coupling is now explicit opt-in, not a silent default.
5. **Temperature qualification:** the pipeline can no longer turn a cool copper
   field into a component-temperature pass. The new source contract is deliberately
   unqualified pending package and boundary-condition evidence. The confirmation
   solve must preserve the same heat contract.
6. **Copper record schema:** new force-lane tap segments omitted their width while
   imported segments included it. A later collision check unpacked six fields and
   crashed on the five-field insertion. A shared finite-geometry/positive-width
   constructor now handles all three insertion paths. No clearance or collision
   threshold was relaxed.
7. **Failure provenance:** placement worker exceptions retain their causal stack;
   exact candidate evaluations are saved before temporary-worker cleanup. A failed
   worker still fails closed, never becoming an accepted review artifact.

These new mechanisms contain no repair coordinates or board/refdes-specific move
rules. However, the pre-existing force-lane topology adapter, thermal current
tables and some placement recipes still contain product-specific assumptions.
This slice is not evidence that the entire legacy pipeline is generic.

## Bounded compaction result

One fresh seed, one strategy, three concurrent outline trials; no route probes.
The first run exposed the width-schema exception. One rerun after its repair
completed exact finalist evaluation in a 158-second placement stage.

| Outline | Area reduction vs 58 x 80 | Placement residual | Result |
| --- | ---: | ---: | --- |
| 58 x 80 mm | 0% | 0 | Zero pad/courtyard violations; six cells and 444 locked cell segments |
| 58 x 72 mm | 10% | 11 | Rejected: MCU pad bounds/edge/courtyard failures; one sensing cell refused |
| 58 x 64 mm | 20% | 19 | Rejected: MCU pad bounds/edge/courtyard failures and component collisions |

The 80 mm result preserves the previous geometric quality, including nine
decoupling findings and no stranded-component findings. It is not improved into
a routing-qualified state. The smaller results lose the MCU edge placement and
separate local supporting parts. Their failure is evidence of a search/ordering
limitation, not a lower-bound proof that the board cannot be compacted.

Native renders (no component bodies) are adjacent to candidates `002` (80 mm)
and `000` (64 mm). Banners explicitly distinguish placement review from rejected
geometry. No failed candidate was promoted over the preserved baseline.

Reproduction:

```sh
ulimit -c 0
.venv/bin/python scripts/cec_full_pipeline.py --board 12vhpwr-standard \
  --out build/12vhpwr-fan-compaction-width-schema-20260907 \
  --replace-placement --fresh-placement-only --placement-candidates-only \
  --review-skip-route-probes --strategies plain --placement-seeds 0 \
  --workers 3 --backend cpu --no-dashboard
```

Use a new output directory for a new experiment; do not overwrite this evidence.

## Thermal screening: explicitly incomplete, not a pass

The existing 58 x 80 placement artifact was screened at 50 C ambient with a
0.8 mm grid, current-source copper only, the declared six-layer fabrication
stackup/dielectrics, copper temperature-dependent resistance, discrete heat,
radiation and natural convection. No assumed chassis/TIM coupling was applied.
These are coarse board-field sensitivities, not converged package/airflow solves.

| Case | Peak PCB field | PCB pad field at MCU | PCB pad field at LDO |
| --- | ---: | ---: | ---: |
| Fan-off baseline | 228.53 C | 220.66 C | 193.27 C |
| Additional effective h = 25 W/m2/K | 128.41 C | 123.36 C | 106.96 C |

These temperatures must not be interpreted as predicted final operating or die
temperatures. The arbitrary h=25 case is not performance attributed to any fan.
Three unrouted USB power paths are correctly reported as uninjected; only 13 of
16 requested net cases carry their requested current in this placement artifact.
The bus scenario is the inherited nominal 600 W case (8.33 A per lane), **not**
the 9.2 A per-lane margin corner. Missing passive/contact losses, source assumptions,
uncovered Q1 and package-to-board behavior preclude qualification. Refine actual
copper constrictions, load coverage and mesh convergence before drawing physical
conclusions from these large coarse-field peaks.

The revised component scenario includes the MCU's 0.6336 W envelope with margin
and the current direct LDO's approximately 0.3611 W at nominal 5 V input. Several
other inventory entries remain typical or assumed, not worst-corner qualified.
Supply maximum voltage, quiescent-current corners and device package limits still
need a coherent all-component qualification. Heat-input/loss balance was within
0.001 W for both screens; numerical energy balance alone does not validate inputs.

Evidence: `build/fan-screen-20260907/baseline-h0.json` and `baseline-h25.json`.
The PCB hashes remained unchanged during filling/analysis of temporary copies.

## Fan integration still required

The current input sheet already has a DNP three-pin JST-PH fan provision and a
low-side switch. Its note historically references the Noctua NF-A4x10 FLX and
places the fan feed before the lane-6 shunt, outside GPU-side measurement. This
slice does not treat that historical reference as a newly confirmed selection.

For that reference fan, Noctua lists a 40 x 40 x 10 mm form factor but extended
dimensions of 11 mm without anti-vibration pads and 12 mm with them, 32 mm mounting
spacing, 12 V and 0.05 A maximum. Reserve the actual envelope, not just the nominal
"10 mm" marketing size. Its connector is 2510-3PIN, not JST-PH, so the already
documented harness-adapter issue remains open. Source:
[Noctua specifications](https://www.noctua.at/en/products/nf-a4x10-flx/specifications).

Before crediting cooling, confirm the selected fan, standoff, inlet/outlet space,
mounting/harness clearance, population choice, motor and switching losses, and
thermal shutdown behavior under a stopped/blocked fan. Installed airflow depends
on the fan/system operating point, not the free-air maximum alone:
[NMB fan engineering](https://nmbtc.com/resources/fan-engineering/).

Package/ambient interpretation references:
[Espressif module datasheet](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html),
[TI TLV755P](https://www.ti.com/product/TLV755P).

## Validation and next bounded slice

219 tests and two subtests pass across thermal source/field/injection/geometry,
outline policy, rail geometry, placement review and full-pipeline tests. Synthetic
cases use renamed component/rail identities, test U1/U10 separation, source
conservation, invalid inputs, convection closed-form agreement, spatial energy
balance, width records and retained error stacks. Actual heat-contract replay maps
successfully on 12VHPWR, Hub and the archived PCIe control while exposing each
board's unverified/uncovered devices. `git diff --check` is clean.

Next: preserve legal critical edge macros and their local supply cells during
outline transformation, reserve them before ordinary small-part seating, then
replay the same compact outlines plus PCIe. Failure should return a named packing
constraint, not park the MCU out of bounds. Do not compensate with one-off MCU
coordinates or by relaxing decoupling. Route only after physical/local-craft
admission, and repeat actual-copper thermal qualification after routing.
