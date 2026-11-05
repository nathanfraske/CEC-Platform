# Hub horizontal reservoir and supercapacitor investigation

**Superseded selection, 2026-09-21:** the owner rejected the supercapacitor on
cost after the circuit-cost comparison. Its research below is retained, not an
active sourcing recommendation. Continue with the two-cap conventional study
in `hub-two-cap-fit-study-2026-09-21.md`.

## Outcome

A factory-horizontal capacitor is real and feasible to investigate, but the
confirmed electrolytic is not an attractive native-JLC prototype choice. The
most interesting new option is **Eaton PHV-5R4H474-R, 0.47 F / 5.4 V**, a
factory-horizontal two-terminal supercapacitor pack with a **17.3 x 14.5 x 9 mm**
maximum body envelope. Its body fits inside the current C1 courtyard without
growing the board. This is a body-envelope result, **not** a qualified footprint,
connector fit, thermal result or circuit substitution.

No active schematic, BOM, footprint, PCB, routing or stack contract was changed.
No sourcing request, order or supplier message was submitted. JLC sourcing and
the supercapacitor charge/protection circuit remain decisions before an ECO.

## Authority and reproduced evidence

- Authority: `build/ordinary-relief-next-inputs-20260920.json`.
- Hub: `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`,
  SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
- ATX: `build/native-assembly-placement-pass-20260920/atx-24pin-rev3/02-placement/board.kicad_pcb`,
  SHA256 `cb851d4dd9c7418e53ee316c26e7fac4fbd99cb8b55bfa8f77c89b249e807773`.
- Native replay: `tmp/hub_stack_height_review_20260920.py`.
- New read-only study: `tmp/hub_horizontal_reservoir_study_20260921.py`.
- Results: `build/hub-horizontal-reservoir-study-20260921/screen.json` and
  `body-envelope-comparison.png` in the same directory.
- Source hashes and source signatures were verified before and after inspection.
- Existing model tests: **10 tests and 7 subtests passed**, using
  `.venv/bin/python -m pytest -q tests/test_reservoir_screen.py tests/test_hub_holdup.py`.

These are the retained pair, not an older schematic or an arbitrary dashboard
entry. Existing mating defects are not waived: nominal anchor transform is
`x_ATX = 86 - x_Hub`, `y_ATX = y_Hub + 9.8`, but the contact-pad registration
and 18 mm insertion problems described in the preceding height review remain.
Changing C1 cannot fix them. No new 18 mm assembly approval is implied.

## Shortlist and sourcing, checked September 21, 2026

| Candidate | Physical configuration | Sourcing result | Status |
| --- | --- | --- | --- |
| TDK B41888C3688M012 | 6800 uF, 10 V, factory 90-degree leads; D16 x L31.5 nominal, D16.5 x L33.5 maximum | TDK says Production, package 180, manufacturer MOQ 2160, no distributor inventory information; exact JLC search returned zero results | Real production ordering code; small-quantity/JLC supply unconfirmed |
| TDK B41888C4828M012 | 8200 uF, 16 V; D18 x L35 nominal, D18.5 x L37 maximum | Ordering table permits the -012 formed-lead option; exact production availability and stock not verified | Catalog-derived option, not a verified stocked SKU |
| Eaton PHV-5R4H474-R | 0.47 F, 5.4 V, factory-horizontal, maximum 17.3 x 14.5 x 9 mm | Exact live JLC search returned zero results; freshly opened Mouser page reported 418 available, USD 11.00 at one / 8.27 at ten | Strong geometry/electrical investigation candidate, not JLC-native-qualified |
| HCCCap 5.5V-2.5F / C397146 | Upright 2.5 F, 5.5 V | Live JLC page: Source JLCPCB, Extended, Wave Soldering, Economic and Standard; 145 in stock and orderable; USD 1.8669 at one / 1.5772 at ten | Proves native supercaps exist, but this upright SKU is not the requested low-profile formed part |

The HCC JLC page says 23.5 mm seated maximum, whereas its linked manufacturer
B/0 PDF gives body H1 = 23.5 +/-2 mm. That discrepancy, plus different tolerance
and life-temperature data between the listing and PDF, must be resolved before
selection. Do not silently assume 23.5 mm is a guaranteed maximum, or rotate its
upright STEP model and call it a factory-horizontal part. Its body could be low
if laid sideways, but that requires a supplier-approved formed SKU, footprint,
support and assembly process which have not been found here.

Stock is point-in-time, not reserved. The current Mouser page differs from the
older search-index snapshot (45 pieces / USD 8.54); use the fresh page, not that
stale result. These prices exclude assembly, shipping and applicable charges.

JLC's **Consignment Parts Terms & Conditions explicitly exclude ultracapacitors**.
Its general Global Sourcing/New Parts Request service is not approval for this
Eaton part. Native HCC listings and the consignment exclusion concern different
procurement routes; they are not evidence that either route universally accepts
all supercapacitors. Obtain written acceptance for the exact Eaton MPN and its
wave-solder profile before treating it as a JLC-assembled option.

## Hold-up screen: same load and shutdown requirements

Unchanged existing assumptions: 195.653766 mA at 3.3 V including the established
20% margin, wired-only MCU, 85% conversion efficiency floor, capacitor initially
at 4.15 V, regulated operation down to 3.45 V, 10 ms persistence requirement.
Converter input power is 0.759597 W. C_bulk1 is upstream and is not counted.

TDK specifies initial +/-20%, then up to 30% capacitance change in its voltage
endurance test or 40% in its useful-life envelope. These are different test
conditions, not two losses to multiply together. Applying each to initial
minimum capacitance gives:

| Candidate | Initial -20% ideal hold | Then -30% endurance | Then -40% useful-life |
| --- | ---: | ---: | ---: |
| 6800 uF | 19.05 ms | 13.34 ms | **11.43 ms** |
| 8200 uF | 22.97 ms | 16.08 ms | **13.78 ms** |

These are ideal upper bounds under the selected voltage/power assumptions,
before ESR, leakage and detection/firmware latency. Thus 6800 uF is not a robust
qualified choice merely because 11.43 exceeds 10. The larger part adds margin
but also diameter and length. Manufacturer test hours do not directly specify
this product's service life at its actual voltage and temperature.

For the Eaton pack, initial -10% and another -30% life-envelope change give
**0.2961 F**. Using its 0.4 ohm 100 Hz maximum as a screening resistance, then
doubling that to 0.8 ohm in the life-envelope sensitivity, gives:

| Effective resistance used in model | Modeled hold at 0.2961 F |
| --- | ---: |
| 0, ideal energy upper bound | 1036.9 ms |
| 0.4 ohm | 897.6 ms |
| 0.8 ohm | **760.5 ms** |
| 1.6 ohm, additional sensitivity only | 493.6 ms |

Lossy cases use 13 uA leakage, which the datasheet labels **nominal after 100 h
at 5 V / 20 C**, not worst-case hot leakage. AC ESR and DC pulse behavior are
not interchangeable across temperature, age and time scale. Accordingly these
results show substantial *screening* margin, not guaranteed milliseconds on
hardware. Extra discharge switches/diodes and charger voltage tolerances are
not included. No 1000-hour accelerated life test is relabeled as a ten-year
product qualification.

High-ESR coin-style memory-backup capacitors must not be substituted just on
capacitance. In this existing direct-reservoir model, an effective resistance
of `(4.15 - 3.45) * 3.45 / 0.759597 = 3.18 ohms` already consumes the entire
available voltage headroom at the regulation floor. This is a necessary
screening limit, not an acceptable design target.

## Mechanical findings

The exact retained outlines are Hub 84 x 80 mm and ATX 82 x 95 mm. Native Hub
RJ45s face left; after the dead-bug reflection they face right. The studied
extension is on the opposite edge, as requested.

At C1's present center (73.055, 70.5013), the Eaton maximum body envelope fits
within C1's 20.79 x 17.09 mm courtyard and intersects no other Hub footprint
courtyard. A 9 mm body leaves 9 mm to a **bare** opposite PCB at nominal 18 mm
separation. Lead bends, drilled lands, supports, insulation, assembly clearance
and solder tails are not included in this body-only fit. The new land pattern
is not a drop-in replacement for the SMD electrolytic's lands.

Projected opposing courtyards still include ATX J3, C25, FB1 and FID3. A courtyard
projection is not a physical collision: J3's modeled body is outside this cap
body projection, while its courtyard/access area reaches inward. The capacitor
still needs an actual two-sided height/lead/cable-access fit check. The invalid
contact registration means the projection itself is not a final assembly pose.

For comparison, a conservative **fully outboard** TDK 6800 uF layout with the
cylinder parallel to the edge gives a local wing **20.5 mm wide x 45.5 mm long**,
about 933 mm2 extra PCB. This includes study assumptions of 1 mm side guards,
a 5 mm axial vent reservation and a 5 mm formed-lead/pad band. Those are not
manufacturer-qualified vent/support requirements. The ATX nominal projection
extends 2 mm past this Hub edge, which is included in the outboard calculation.

That wing is an illustrative clearance strategy, **not a proven minimum or a
claim that every horizontal capacitor needs 20.5 mm extra width**. Partial
overlap with the ATX, another orientation or local relocation can reduce it,
but then the board-face gap, opposing component heights and vent space matter.
A 16.5 mm maximum diameter on a hypothetical 0.5 mm cradle is 17 mm tall, only
1 mm below the nominal 18 mm bare-board gap before tolerances. The TDK drawing's
E = 4 mm is body-to-lead-tip geometry, not an automatic 4 mm PCB standoff.

## Why the supercap is not a C1-only ECO

1. **Controlled charging:** 0.47 F is 100 times the present nominal 4700 uF.
   A 4.15 V rise in 10 ms would demand 195 A ideally; that cannot be inferred
   from the existing TPS2121 soft-start setting. Current limiting, source
   sharing, SS14 stress, repeated power cycling and fault dissipation must be
   modeled. At illustrative *dedicated net charging currents* of 50/100 mA,
   charging 0 to 4.15 V takes 39.0/19.5 s nominal, or 50.7/25.4 s at +30% C,
   before leakage/taper. These are not new selected current budgets.
2. **Voltage and temperature protection:** Eaton allows 5.4 V to 65 C and
   linearly derates to 4.0 V at 85 C. Existing Hub OVP has a 5.948 V static high
   corner; neither that nor a diode's *maximum* VF bounds the cap voltage safely.
   The datasheet's 6 V surge figure is not a continuous operating allowance.
   A controlled ceiling or a different rated part is needed. If charging below
   the present 4.15 V bound for high-temperature operation, rerun the energy
   model with that new minimum; do not keep claiming this table unchanged.
3. **Separate charging from hold-up delivery:** do not insert a large charging
   resistor into the only discharge path. A charger/isolated discharge path
   must keep normal system power available while the empty cap charges, prevent
   upstream backfeed, preserve local high-frequency capacitors and be checked
   for converter startup behavior. Select the architecture before assigning BOM.
4. **Energy-ready state:** the Hub must know when it has enough stored energy
   for guaranteed persistence after cold startup and quick power cycles.
   Shutdown still comes from the existing upstream +5VSB detector, not delayed
   until the supercap or regulator drops out.
5. **Pack, life and assembly qualification:** use the manufacturer's rated
   two-terminal pack as specified; do not invent an external midpoint or claim
   unspecified internal balancing. Building a pack from two raw 2.7 V cells
   would additionally require cell-voltage/balancing design. Verify local
   thermal mission profile, aging, leakage, ripple and recovery on hardware.
   Eaton specifies wave soldering and disallows whole-body reflow; it is not a
   normal reflow substitute for C1.

## Recommended next decision

Do not enlarge the Hub for a capacitor yet. Carry the Eaton horizontal pack
as the strongest **compactness** candidate, contingent on procurement/assembly
acceptance and a costed charge/protection design. USD 8.27 at ten is materially
above the roughly USD 0.79 low-profile electrolytic previously considered,
before the supercap's extra circuitry. It is not necessary for a 10 ms budget
if a conventional capacitor solution can be properly qualified.

Retain a conventional capacitor path in parallel: a qualified one/two-cap
low-profile option or an actually procurable formed electrolytic can keep the
circuit simpler. Do not trade away mission-life or shutdown timing just to
avoid a small mechanical change. Resolve the mating/contact model independently
before comparing final stacked dimensions.

## Primary sources and sourcing evidence

- [TDK exact B41888C3688M012 product](https://product.tdk.com/en/search/capacitor/aluminum-electrolytic/single-ended/info?part_no=B41888C3688M012)
- [TDK B41888 manufacturer datasheet](https://www.tdk-electronics.tdk.com/inf/20/30/db/aec/B41888.pdf),
  printed pages 3-4, 7-8 and 22; dimensional drawings were visually reviewed.
- [Eaton exact PHV-5R4H474-R product](https://www.eaton.com/sg/en-us/skuPage.PHV-5R4H474-R.html)
- [Eaton PHV datasheet, September 2024](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-phv-supercapacitors-cylindrical-pack-data-sheet.pdf),
  pages 2-3. Text was accessible through the web tool; direct PDF download was
  unsuccessful. Body dimensions also independently appear on Eaton's product
  page. No detailed Eaton lead footprint was approved from extracted drawing text.
- [Mouser exact horizontal part](https://www.mouser.com/en/ProductDetail/Eaton-Electronics/PHV-5R4H474-R?qs=e7A2guvi5TCigmEsFz0iJw%3D%3D)
- [JLC native C397146](https://jlcpcb.com/partdetail/Hcccap-5_5V_25F/C397146),
  live inventory read around 17:57 UTC; linked HCC B/0 specification checked for
  dimensional and ratings discrepancies, not qualified as a horizontal SKU.
- [JLC consignment exclusions](https://jlcpcb.com/help/article/consignment-part-terms-conditions)
- [JLC sourcing routes](https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction)

The reproducible calculator is board-independent; the one-off script here only
binds the actual Hub load and the particular mechanical research candidates.
Neither it nor this report is an automatic release acceptance gate.
