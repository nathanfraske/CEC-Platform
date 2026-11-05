# Hub single-capacitor qualification and conditional interface lift

## Decision

Do not replace C1 or lift the mating interface yet. Lelon VZH472M1CTR-1816 /
C249940 is native-listed and available in small quantities at JLC, and passes
the current **fresh-part sudden-source-loss** model. It does **not** guarantee
the established 10 ms persistence window across its full datasheet endurance
envelope. This is a calculation/qualification screen, not a physical bench test.

No schematic, BOM, PCB, routing, power-budget, shutdown-threshold, mounting or
stack-contract file was modified. The existing dirty worktree was preserved.

## Current authority and executable checks

- Hierarchical source: `beta/hub-standard-rev2/hub-standard-rev2.kicad_sch`,
  including `02-holdup-3v3.kicad_sch` and `01-power-input-selection.kicad_sch`.
- Existing requirements: `scripts/cec_hub_holdup.py` and
  `docs/beta-power-regulator-selection-2026-08-02.md`.
- Native Hub/ATX sources: `build/ordinary-relief-next-inputs-20260920.json`.
  `tmp/hub_stack_height_review_20260920.py` rechecked source hashes and source
  hierarchy signatures before inspection and PCB hashes afterward.
- Study: `tmp/evaluate_hub_single_cap_20260921.py`.
- Results and authority hashes:
  `build/hub-single-cap-qualification-20260921/screen.json`.
- Generic read-only calculator: `scripts/cec_reservoir_screen.py`.
  It is not wired into production release acceptance and must not be described
  as a new automatic qualification gate.
- Validation command:
  `.venv/bin/python -m pytest -q tests/test_reservoir_screen.py tests/test_hub_holdup.py`.
  Result: **10 tests passed, 7 subtests passed**. Includes independent analytic
  checks for ideal energy, ESR-only discharge, leakage-only discharge, numerical
  convergence, invalid-input rejection, and the live hierarchical hold-up topology.

## Stock observed on 2026-09-21 around 17:30 UTC

The live, JavaScript-populated [JLC detail page](https://jlcpcb.com/partdetail/Lelon-VZH472M1CTR1816/C249940)
showed Source JLCPCB, Extended, SMT Assembly, Economic and Standard:

- In stock: **50**.
- Available order quantity: **42**. Do not treat all 50 as orderable.
- 1+: USD **0.9685**; 10+: USD **0.7927**; 30+: USD **0.7048**.
- No parts were purchased or reserved. Stock and price are point-in-time only;
  these are component prices, not an assembled-PCBA quote.

Separately, the [LCSC page](https://www.lcsc.com/product-detail/C249940.html)
reported 33 in stock and USD 0.9667 at quantity one. This is not evidence of
additional JLC assembly allocation; the two pools must not be conflated.

## Electrical result: initial pass, full-endurance-envelope fail

Unchanged assumptions: load 195.653766 mA at 3.3 V **already including 20%
margin**, 85% conversion floor, reservoir start 4.15 V, regulation floor 3.45 V,
10 ms persistence budget. Converter input power is 0.759597 W. C_bulk1 is
upstream of the isolation diode and is not added to C1's reservoir energy.

The [Lelon 2026 catalog](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf),
VZH specifications and dimension/value tables (printed pages 115-116), gives
4700 uF +/-20%, 16 V, D18 x L16.5 +/-0.5 mm, 5000 h at 105 C, and capacitance
change within +/-30% **of initial value** after endurance testing. The 18 x
16.5 case has 0.048 ohm maximum impedance and 1.5 A ripple rating at 100 kHz,
20 C and 105 C respectively. The initial 20 C leakage bound at rated voltage
is 0.01*C*V = 752 uA.

The following is an ideal-energy **upper bound under the selected power/start/
floor assumptions**, not a hardware guarantee. It excludes ESR, leakage and
detection/firmware latency:

| Additional capacitance loss after initial -20% tolerance | Capacitance | Hold time |
| --- | ---: | ---: |
| 0% | 3760 uF | 13.167 ms |
| 10% | 3384 uF | 11.850 ms |
| 20% | 3008 uF | 10.534 ms |
| 30%, datasheet endurance limit | 2632 uF | **9.217 ms** |

The last line already fails before any other losses. Ideal allowable subsequent
capacitance loss is at most 24.05%; actual loss allowance is lower with ESR,
leakage and response latency. At the same -20%/-30% envelope, even an ideal
capacitor would need about **5100 uF nominal** just to reach 10 ms with zero
remaining margin. This is a screening floor, not a recommendation to select
the next value without testing it.

Illustrative constant-power integration gives 12.905 ms for initial C with
0.048 ohm effective ESR and 752 uA leakage, or 12.586 ms at 0.12 ohm. These are
**sensitivity cases**, not certified corners: 100 kHz impedance must not be
relabeled as guaranteed effective ESR over a millisecond discharge, and hot/
cold leakage and ESR are not qualified by the 20 C figures. An assumed threefold
100 kHz impedance is also not a specified end-of-life ESR limit; the endurance
specification is on tan(delta), not that impedance.

The 5000-hour test does not predict the exact time to a 30% drop in this product.
A cooler, lower-voltage mission profile might support the application, but that
requires manufacturer-supported lifetime/parameter bounds and OQ-56 evidence.
Do not claim that this candidate will fail after exactly 5000 operating hours.
The existing Ymin part is **not** newly lifetime-qualified by this comparison:
the existing model omits aging and ESR as well. Its 10000-hour rating alone does
not resolve that gap.

Topology remains correct: the comparator senses upstream +5VSB while C1 and the
buck are isolated on +5V_HOLD, so normal shutdown is triggered by source loss,
not regulator dropout. The unchanged threshold range is 4.060-4.663 V. The
13.167 ms calculation covers sudden loss, not arbitrary slow source collapse.
Source-decay profiles, detector/ISR latency, actual persistence time, cold
impedance, ripple, charging/inrush and bench correlation remain qualification
items. This study does not silently waive any of them.

## Conditional lift: 22 mm is a credible investigation target, not released

Use board-face separation, not board center-plane spacing. The cap is 17.0 mm
maximum, not the distributor's nominal 16.5 mm. The 18 mm case is wider than
the existing 16 mm body and needs a new verified land pattern/courtyard and
local placement check. It is not footprint-compatible merely because C is equal.

The fitted BOM pair is TSW-10x-17-G-D on ATX and SSQ-10x-03-G-D on Hub. Sources:

- [Samtec TSW catalog](https://suddendocs.samtec.com/catalog_english/tsw_th.pdf),
  also `lib/datasheets/Samtec_TSW_TH.pdf`, straight style -17: total pin length
  21.08 mm, solder tail 2.79 mm, mating post 15.74 mm.
- [Samtec SSW/SSQ catalog](https://suddendocs.samtec.com/catalog_english/ssw_th.pdf):
  socket body height 8.51 mm; insertion range 3.68-6.35 mm.
- `lib/datasheets/Samtec_SSQ.pdf`, revision BH: the -03 tail is about 10 mm.
  **That long solder tail does not increase the socket's seated body height.**

For both connectors fully seated on the inward-facing surfaces, nominal
insertion is `(21.08 - 2.79) + 8.51 - board_gap = 26.80 - board_gap`.

| Board-face gap | Cap to bare opposite PCB | RJ45 to bare opposite PCB* | Nominal insertion | Catalog-range screen |
| --- | ---: | ---: | ---: | --- |
| 18 mm | 1 mm | 4.6 mm | 8.8 mm | Over-insertion |
| 20 mm | 3 mm | 6.6 mm | 6.8 mm | Over-insertion |
| 21 mm | 4 mm | 7.6 mm | 5.8 mm | Within nominal range |
| 22 mm | 5 mm | 8.6 mm | 4.8 mm | Within nominal range |

*Using the 13.4 mm RJ45 bound from the existing height review; supplier drawing
revision remains to be fixed. These clearances exclude opposite components,
seating, board bow, standoff tolerances and vent space. Lelon requires vent
clearance; the reviewed catalog's vent paragraph did not expose the promised
numeric table, so no numeric manufacturer vent minimum is invented here.

Nominal connector gap interval is 20.45-23.12 mm. A 22 mm target leaves 1.12 mm
to under-insertion and 1.55 mm to over-insertion before tolerances, with 5 mm
bare-PCB space above this cap. The existing connector family may therefore
work without longer posts. Detailed part tolerances and engagement still need
qualification. Do not float connectors above the PCB or trim mating posts as
an undocumented workaround.

The current 18 mm stack comment in `cec_mezz_contract.py` is insufficient:
it checks for short posts but overlooks maximum insertion under these seating
assumptions. This is a pre-existing issue, not a reason to change the scalar
gap without an assembly ECO.

Native replay also confirms the previous X/Y registration defects remain:
4/6 J6P, 6/8 J6C and 2/4 J6D pad centers have no opposing center within 0.05 mm.
Lifting Z cannot repair them. Qualified paired contact positions/net mapping,
actual standoff thread/length, vent and two-sided body clearance, solder-tail
protrusion and cable/tool access are still required. Existing M2 owner intent
and the M2.5 hardware currently in the stack contract also need reconciliation;
no new fastener specification is selected in this read-only study.

## Recommended next decision

Preserve the load and persistence requirements. Evaluate one larger-capacitance
low-profile part or a two-cap option against tolerance **and** endurance loss,
or obtain a defensible mission-life/aging bound for this part. Resolve the
connector mating model independently; a nominal 22 mm stack is promising,
but neither it nor this capacitor is approved for production by this study.
