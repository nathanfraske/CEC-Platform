# Current BETA 12VHPWR: four mounts, lower RJ-45 and electrical review

**Interface intent superseded later the same day:** the owner corrected RJ-45
to face right, with USB-C moved down alongside it. See
`current-beta-12vhpwr-right-lower-io-2026-09-07.md`. The bottom-facing trials below
are historical evidence, not current placement authority.

2026-09-07. **Mechanical placement review only; not routing or fabrication
admitted.** No existing board was replaced, and no schematic or BOM was changed
in this slice. Four M2 screws means four total mounting locations, one per corner.

## Source authority

Refreshed `origin` before work. The current hierarchical root and eleven numbered
child sheets remain the manifest authority, not the stale root PCB or historical
candidate. Local handoff HEAD is `069a4126ac4ad5ca7ab51012483491c31b0ac521`;
`origin/main` is `b987ce5aed5e24282ef3b6c044e9be36957ac464`. Previous local source
repairs and the populated J2 fan header were preserved. Fresh electrical audit
source digest: `ed534df9b4021c37bb4ebb041511019579ae36bd24c0dde6ce2918f4ec467030`.

Fresh-source evidence: `build/12vhpwr-current-electrical-mounts-20260907.json`.

## Electrical findings

- All **15 recognized local-supply requirements** have distinct source capacitor
  assignments: six INA240 supplies, MCU HF bypass, CAN VCC and VIO/VCC bypasses,
  reference input, two LDO pins and three mux pins. This is a selected-device
  inventory check, not a complete PDN or effective-capacitance qualification.
- MCU source has C3 100 nF and C7 10 uF, both declaring U1.3 ownership. C7 bulk
  locality is not covered by the current 15-requirement physical matcher. Its
  source presence must not be presented as proof of correct PCB placement.
- Current power is TPS2121 U5 into direct TLV75533PDRVR U16. The executable
  radio-disabled load envelope is 176.939 mA, or **212.327 mA with 20% margin**,
  against a conservative 500 mA regulator capacity. This does not establish
  thermal, startup, hold-up or transient-load qualification.
- Current USB source is J5 VBUS_RAW -> F1 750 mA PTC -> VBUS_F -> FB1 ferrite
  -> VBUS -> U5 IN2. Reversible D+/D- banks, separate 5.1 kohm CC pulldowns,
  D3 USBLC6-2SC6 and D4 VBUS clamp are present. D3 VBUS references VBUS_RAW.
  USB goes directly to the MCU; optional near-MCU 22/33 ohm tuning positions
  recommended by Espressif are not presently provided. They require their own
  signal-integrity decision, not an assumption that current protection proves SI.
- **New durable warning:** C9 10 uF + C28 10 uF + C27 100 nF expose **20.1 uF
  nominal** upstream of active limiting. A PTC/ferrite is not a qualified inrush
  limiter, and mux output soft-start does not protect capacitors on its input.
  The new graph-based USB sink audit follows fitted passive bridges and stops
  at active devices; a synthetic test prevents this blind spot returning.
  Nominal capacitance exceeds the USB2 10 uF hard-attach screening budget;
  effective capacitance and measured current-versus-time remain unqualified.
  Do not remove needed bypass/bulk caps without requalifying the network.
- Existing U5 OVP dynamic-margin warning remains: 5.948 V worst static trip
  versus 6.0 V downstream absolute maximum, only about 52 mV before overshoot.
  FL1 remains intentionally DNP. The scoped audit has zero 12VHPWR static
  blockers and three warnings; that is not board signoff.

Sources: [TI USB inrush application report SLVA129](https://www.ti.com/lit/pdf/slva129),
[Espressif USB schematic guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html#usb),
[TI TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf),
[TI TPS2121](https://www.ti.com/lit/ds/symlink/tps2121.pdf).

## Mechanical implementation and generic fixes

Board policy requests four mandatory corner mounts, 3.75 mm center inset,
2.2 mm NPTH, and 6 mm hardware diameter plus 0.25 mm component clearance.
The new library footprint has both-face 6.5 mm courtyards and native outer-layer
copper/track/via/pad exclusion areas. These are PCB-only mechanical features;
screw length, torque, exact washer/standoff and fan clearances are not selected.
The 6 mm envelope is a design allowance, not a claimed hardware standard.

The shared pipeline now:

1. Prevents both legacy optional-mount deletion passes from dropping required
   mounts. Native placement and independent release checks verify count, exact
   positions, drill size/type, electrical isolation, both-face hardware clearance,
   actual substrate/cutout support and persistent copper keepouts.
2. Carries the resolved default/per-ref mounting footprint into PCB generation.
   The first trial caught an actual model/emitter mismatch: placement used the
   requested NPTH land, while materialization substituted the old plated land.
3. Preserves surviving mount identities instead of renumbering after an optional
   omission. No board-specific reference/coordinate repair was added.
4. Transforms embedded footprint zone polygons into board coordinates during
   emission. Those zones previously remained at the library origin. Native
   calibration covers translation, arbitrary rotation and flip. Both-face layer
   swaps now preserve F/B ownership rather than collapsing two layers into B.
5. Avoids inventing missing Hub/ATX peers when running an unrelated board-scoped
   electrical audit, and cannot claim a matching mezzanine when a peer is absent.

The new mount checker is included in the generic-engine audit. Legacy synthesis
still contains broader product-specific code; this slice does not claim the
entire pipeline is now generic or qualified.

## Bounded placement results

| Trial | Residual | Native pad/courtyard checks | Mandatory mounts | Electrical state |
| --- | ---: | --- | --- | --- |
| Prior 58 x 80, no mounts | 0 | Pass | Not requested then | 9 decoupling findings |
| Corrected 58 x 80, lower RJ-45 | 0 | Pass | 4/4 pass | 12 findings |
| Corrected 58 x 76, lower RJ-45 | 3 | Pass | 4/4 pass | 12 findings; MCU bypass stranded |
| Corrected 58 x 72 | 19 | Fail | Conflict with MCU | Rejected |
| Corrected 58 x 64 | 22 | Fail | Conflict with MCU | Rejected |

The 76 mm option is **5% less board area** (4408 versus 4640 mm2). Its row
still contains all six sensing cells and 444 locked internal segments. It
passes source intake and all four mount checks. The MCU stays at the left
edge (rotation 90 degrees); the RJ-45 moves to the bottom and USB stays on the
right. J2 remains fitted with unchanged return / pre-shunt 12 V / tach pinout.

This is **not an electrical improvement** over the old baseline. At 76 mm,
the row negotiation journal explicitly chose `owner_only` after the whole
macro failed; the MCU's bypasses were left behind. Native supply-pad distances
are C3 **36.287 mm** and C7 **47.038 mm**. C3 is already caught by the craft
gate; C7 exposes the bulk-locality coverage gap noted above. Neither should be
accepted. This is an upstream group-reservation defect, not a reason to hand
move those references or ask detailed routing to compensate. The next generic
slice should reserve an electrically essential owner-plus-bypass/bulk subcell
when an optional-service macro is decomposed, then requalify local returns.

No routing was started. No failed option displaced the preserved baseline.
The compact board is retained only to review connector/mount arrangement.

## Evidence and validation

Latest run: `build/12vhpwr-four-mount-76mm-review-20260907/`.
Native no-model render: `02-placement/candidates/000/placement.png`.
`mechanical-comparison.json` and `closeout.json` record exact artifact hashes,
positions, all findings and refusal of routing/release admission.

Earlier trials are retained under `build/12vhpwr-four-mount-bottom-rj45-20260907/`
(rejected footprint substitution) and
`build/12vhpwr-four-mount-emission-corrected-20260907/`.

Broader regression suite: **270 passed, 14 skipped**. After the final cutout
support check, all **52 directly affected tests pass**. These counts overlap;
they must not be added. `git diff --check` is clean.

The read-only archived PCIe replay retains **0 DRC / 0 unconnected**, 615 tracks,
226 vias and 1242.073 mm trace length. Its eight existing release-blocker
categories and their details are unchanged; its full release/generalization
verdict remains failing, not newly qualified. Four preserved control PCB hashes
(root and older 12VHPWR, Hub, archived PCIe) are unchanged. No source layouts
were overwritten and no unrelated worktree changes were discarded.

Reproduction (use a new output directory):

```sh
ulimit -c 0
.venv/bin/python scripts/cec_full_pipeline.py --board 12vhpwr-standard \
  --out build/NEW-REVIEW --replace-placement --fresh-placement-only \
  --placement-candidates-only --review-skip-route-probes \
  --strategies plain --placement-seeds 0 --workers 2 --backend cpu --no-dashboard
```
