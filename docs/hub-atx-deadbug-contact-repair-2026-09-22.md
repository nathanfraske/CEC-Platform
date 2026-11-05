# Hub / ATX dead-bug mating repair - 2026-09-22

**Later same-day ECO:** [capacitor and access closure](hub-atx-cap-eco-access-closure-2026-09-22.md)
implements the two real capacitors, M2 lug, compact recessed Hub and eight passing
planar access checks. The historical mechanical-only state below is retained as
evidence, not the next placement input.

## Result and scope

**The dead-bug flip is included.** The Hub component face points inward toward
ATX F.Cu. Hub-to-ATX coordinates are `x = 86 - x_hub`, `y = y_hub + 9.8 mm`.
This is a reflection about assembly Y plus a translation, not a top-view overlay.

The repaired mechanical pair has **18/18 coincident same-number, same-role
contacts**, versus 12/18 mismatches before. Maximum numerical residual is below
0.000001 mm (CAD arithmetic, not manufacturing accuracy). Native placement DRC
with the existing project/rule sidecars reports **0 ATX / 0 Hub violations**.
Both members also pass the corrected production contact-frame checker.

**The complete stack remains unqualified.** Four access checks still fail and
supplier tolerances, actual M2 hardware, opposing-body/plug clearance, the two-cap
electrical ECO, and physical samples remain outstanding. The new final hardware
signoff requirement withholds fabrication release while these are unresolved.

![Repaired numbered contacts](../build/hub-atx-stack-repair-20260922/repaired-contact-registration.png)

## What was repaired generically

1. Local footprint handedness is explicit. `mating_rotation()` rejects a board
   reflection without a declared local X/Y footprint reflection. It supports
   arbitrary angles and has synthetic tests for both conventions.
2. `mezzanine-segment-contract` now measures every actual pad in the canonical
   assembly frame, checking unique contact identity, logical role and inward
   component face. Matching origins and angles cannot hide wrong contact arrays.
3. The paired assembly-access evaluator also compares actual numbered contacts
   when `contact_pairs` are declared. Electrical role qualification remains the
   separate domain check; an access-only result does not claim electrical proof.
4. Final manufacturing admission uses the existing generic hardware-qualification
   mechanism with an explicit stack requirement. A future release must bind the
   exact pair's file hashes and recheck actual mating/access. Certification, paired
   sources and checker code are signoff-cache dependencies.

The domain contract contains the connector names, roles and solved seats.
The shared math, contact checker and hardware gate contain no part-coordinate
exceptions. The bounded placement study reuses the existing generic contact-space
packer; its named support symmetry and reservoir inputs are study configuration,
not a claim that automatic capacitor ECO or whole-stack placement is implemented.

## Footprint and placement evidence

The vendored 2x2, 2x3 and 2x4 SSQ socket footprints had header-handed arrays.
They now use the standard opposite-handed socket numbering, including pad 2 at
local X=-2.54 mm, and the manufacturer's recommended 1.02 mm nominal PCB holes.
The hole size still needs finished-hole/process tolerance qualification.

Sources reviewed:

- [Official KiCad socket footprint](https://raw.githubusercontent.com/KiCad/kicad-footprints/master/Connector_PinSocket_2.54mm.pretty/PinSocket_2x03_P2.54mm_Vertical.kicad_mod)
  establishes the local numbering convention. The generic connector numbers are
  project contact identities; this is not a manufacturer pin-function assignment.
- [Samtec SSQ recommended PCB layout](https://suddendocs.samtec.com/prints/ssq-1xx-xx-xx-x-xx-xxx-xx-xx.pdf),
  revision A, sheet 1, confirms pitch, row spacing and hole diameter. The complete
  relevant page was visually inspected with the PDF workflow.

Canonical ATX seats, in mm (Hub seats follow the physical reflection):

| Field | X | Y | ATX rotation | Hub rotation |
| --- | ---: | ---: | ---: | ---: |
| J6P | 10.933499 | 73.868201 | 90 | 270 |
| J6C | 68.000000 | 20.159899 | 270 | 90 |
| J6D | 65.989999 | 69.500000 | 90 | 270 |
| H1 | 18.000000 | 20.159899 | unchanged | unchanged |

Reversing J6C's field direction avoids the new RJ45 collision. H1 remains its
X-symmetric support partner. Search proposals used a 0.3 mm additional broad-phase
clearance and were subsequently checked by native DRC, without relaxing rules.
The ATX remains 82x95 mm and Hub 84x80 mm. No outline or original zone boundaries
were moved; no power-bus rerouting was used to create connector space.

## Hardware and source consistency

The generator's nominal gap target is now **22 mm**, explicitly not released.
The old R25-1001802 18 mm/M2.5 support and MP006553 screws are removed from active
MPN selections, with retirement reasons retained. Their BOM rows retain required
quantities but have blank manufacturer/MPN fields and `NOT RELEASED` descriptions.
Schematic notes, component BOM notes and board READMEs no longer describe an
accepted 18 mm stack. CSV column counts and record counts were checked; no
electrical component selections or quantities were changed.

**H1 native geometry remains M2.5 pending the exact M2 hardware selection.**
It is not yet safe to claim a final mounting-hole/washer/contact envelope. The
long SSQ-03 tails also remain unchanged; their outward protrusion still needs
qualification or a coordinated shorter-tail substitution.

The prior conditional interval study remains valid only as a design allocation:
with 21.5-22.5 mm local face gap and stated seating/housing allocations, vent
clearance is at least 4.3 mm and engagement is 3.8938-5.9002 mm. Those are not new
supplier guarantees. Current VZH vent confirmation, REF-dimension bounds and
simultaneous lateral capture of the three connector fields remain required.

## Exact artifacts and limitations

Mechanical outputs:

- `build/hub-atx-stack-repair-20260922/ATX-MECHANICAL-ONLY.kicad_pcb`
- `build/hub-atx-stack-repair-20260922/Hub-MECHANICAL-ONLY.kicad_pcb`
- `build/hub-atx-stack-repair-20260922/validation.json`
- `docs/hub-atx-stack-qualification-status.json`

They derive from the exact hash-bound ATX two-cap clearance candidate and retained
Hub recorded in the preceding audit. Those native source boards are untouched.
The Hub preview applies the previously studied rigid group translations and
removes old C1 **only in the disposable preview**; the two proposed reservoirs
are represented as dimensioned rule-area reservations, not electrically
implemented capacitors. Tracks are omitted and zones unfilled in both mechanical
previews. These are neither routing inputs nor new fab-review winners.

Reproduction:

```
.venv/bin/python tmp/repair_stack_20260922.py
.venv/bin/python tmp/validate_stack_repair_20260922.py
.venv/bin/python tmp/plot_stack_repair_20260922.py
.venv/bin/python tmp/validate_stack_bom_notes_20260922.py
```

Native checks use 10-second subprocess timeouts. Regression evidence is saved
under the same build directory: **116 focused stack/mating/hardware tests and
83 full-pipeline tests pass** (separate suites, 199 tests total). Tests retain
the old bad native board as a failing control; they
do not rewrite history to make it pass. Synthetic tests reject wrong contact
positions, wrong roles, wrong component face, duplicate identities, scaled
transforms and nominal-only qualification.

## Remaining repair order

1. Jointly compact/reseat the Hub edge ports and ATX output signal/header access
   as needed, including daughterboard mating consequences. Do not automatically
   enlarge either board or move power pours. The four current failing gaps are
   TB6/TB9: 0.105 mm each; J_SIG1: -6.315 mm; J3: -5.195 mm, versus 1.2 mm required.
2. Finalize M2 support/screw/washer dimensions and connector seating/capture
   tolerances; then change H1 and any socket tail variant coherently in both
   boards and BOM. No unverified spacer MPN has been invented.
3. Integrate the approved two-cap electrical ECO, preserve opposing component and
   vent reserves, check RJ45/body/plug/latch swept volumes, then reroute and check
   full electrical/thermal/manufacturing evidence. Qualify physical samples.

No parts were ordered and no supplier was contacted. The stack is deliberately
blocked from fabrication until the required evidence exists.
