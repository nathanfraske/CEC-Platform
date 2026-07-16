# Pro + Max board family — exhaustive design sheet (pipeline input)

_Owner ask (2026-07-16): the design-rules-with-best-practices treatment for the Pro
and Max boards, after the Standard sheet. DERIVED VIEW — canonical: spec §3/§6.11-13,
`docs/research/max-instrument-channel-decision-2026-06-11.md` (+4 companions, the
RULED Max architecture — spec §6.11 text is stale vs it, owner-pen item),
`docs/bench-mode-max-stack-2026-07-05.md`, `docs/bench-mode-instrument-requirements-
2026-07-16.md`, and on branch `claude/pipeline-consolidation`:
`docs/supercap-ups-study-2026-07-15.md` (+ owner rulings in its commit chain) and
`docs/pipeline-solver-roadmap.md`. Sibling sheets: `testers/DESIGN-SHEET.md` (the
tester-max digitizer lane shares parts + rules with the Max module lane),
`docs/enterprise-requirements/board-program/ENT-DESIGN-SHEET.md` (the P4 escape and
RS-485/T1 tiering context), `docs/standard-tier-review/STANDARD-DESIGN-SHEET.md`
(everything not restated here — sensing corridors, pours, stackups — INHERITS).
Working-basis numbers tagged **[wb]**._

## A. Board census

| Board | State | Notes |
|---|---|---|
| `hubs/hub-pro` | unbuilt (platform summary + this sheet) | ESP32-P4, 8 ports, per-port RS-485 RX (OQ-5 working basis), USB HS |
| `modules/12vhpwr-pro` | 99-line schematic stub — capture pending | P4 + 6× INA240A3 + LTC2358-18 + REF3033 + RS-485 stream |
| EPS Pro / PCIe Pro | defined by §6.13 ladder, not yet boards | INA240 fast path + fast ADC + RS-485; magnitude/shape tier |
| EPS Max / PCIe Max / 12VHPWR Max | defined by the 2026-06-11 ruling + §6.11 | per-cable spectral: AD9253-105 + GW5A-25 digitizer lane |
| Supercap hold-up provision | **RULED (pipeline branch, 2026-07-15 chain)**: Pro + Max modules carry a **DNP 2S radial supercap provision** (LCSC-native small cells, 5–10 s target; hand-solder this run; the earlier Eaton pack split Pro=PHV 2.5 F / Max=PHB 5 F is the pack-form provenance) | changes the persist class — see §C.13 |

## B. Floorplan doctrine (zones — additions over the Standard sheet)

```
[Z-SAR]    12VHPWR Pro analog island: LTC2358-18 + REF3033 + per-channel RC,
           fed by the six INA240 outputs — one quiet zone between the sense
           band and the MCU; AGND strategy per C.2 (island policy, single tie).
[Z-STREAM] RS-485 corner at the RJ-45: transceiver at jack pins 4/5, 120 Ω
           coupled pair, TX-only (module→Hub); fail-safe bias lives HUB-side.
[Z-DIGI]   Max digitizer lane (module + tester-max shared rules): AFE →
           AD9253-105 → GW5A-25, LVDS kept short/unbroken; digitizer-on-main,
           never a mezzanine unless the Max program ships one (tester-max
           precedent note).
[Z-FAST]   Max fast path: ONE fast ADC fed by TWO differential front ends —
           per-cable shunt pair + Rogowski coil pair (owner design basis,
           2026-07-05): both routed as guarded diff pairs from the sensor to
           the AFE; the Rogowski integrator sits AT the AFE, not at the coil.
[Z-SCAP]   Supercap provision: 2S radial DNP footprints + charge-limit R +
           Schottky + balance bleed, downstream of the module's 5VSB entry;
           seated height 8.5–11 mm class — check the enclosure lid line.
[Z-HUBPRO] Hub Pro: Standard-hub zones + a per-port RS-485 receiver strip
           between the port field and the P4 (8× RX, OQ-5 point-to-point
           working basis), USB HS front end.
```

## C. Per-component placement rules (rule → why → pipeline check)

1. **LTC2358-18 (12VHPWR Pro)** → Z-SAR. Per-channel anti-alias RC at the ADC
   inputs; REF3033 at the REF pin with its bypass pair; simultaneous-sampling SAR
   wants its bypass caps at the pins and an unbroken analog reference region —
   AGND as an ISLAND joined at one tie point near the ADC (not a split plane
   wander). Check: Analog class + `audit_crosstalk` + netlist ref-chain assertion.
   [practice I.1, I.2]
2. **REF3033**: ≤10 mm [wb] from the LTC2358 REF input; never shared with the
   MCU-ADC ratiometric role (that is REF3030's Standard job — different use, spec
   note). Check: BOM lint + placement report.
3. **INA240 array (Pro, per-pin)**: Standard-sheet rules §C.1-3 INHERIT unchanged
   (RC at the INA, Rf ≤10 Ω, REF1/2 to GND for unidirectional). The Pro delta is
   only where the outputs GO (LTC2358, not the MCU ADC). Check: unchanged kelvin +
   analog gates.
4. **RS-485 (THVD1450-class)** → Z-STREAM at jack pins 4/5. 120 Ω coupled pair,
   stub from transceiver to jack minimal; STANDARD-sheet impedance caveat applies
   DOUBLE here: the platform stackup measured 91–105 Ω on the CAN geometry — the
   RS-485 class needs its own geometry tuned toward 120 Ω or an accepted-mismatch
   note at the SI bench (this is a STREAMING pair at real bit rates, unlike 500 k
   CAN). Check: `audit_impedance` on the RS485 class (make it a named class so the
   audit sees it). [practice I.3]
5. **ESP32-P4 (QFN-104, 0.35 mm pitch, EP 7.5)**: escape per the vendored footprint
   — dogbone where the ring allows, via-in-pad Type VII only if the inner ring
   forces it [wb — decide at first Pro layout]; EP via field to GND; decoupling +
   flash per Espressif's P4 hardware-design guidelines. Check: NEW
   `qfn-escape-completeness` (same shape as the ENT sheet's BGA checker, QFN
   scale). [practice I.4]
6. **AD9253-105 + GW5A-25 (Max lane + tester-max)**: LVDS 100 Ω pairs, intra-pair
   ±0.5 mm, inter-pair ±5 mm per the AD9253 DS, reference plane unbroken under the
   lane (ENT sheet §D row is the same rule — one doctrine, three boards). Clocking:
   the ADC clock is the measurement's jitter budget — dedicated route, no parallel
   switcher runs. Check: LVDS class gate + crosstalk audit. [practice I.5]
7. **Slow-path mux discipline (Max)**: one ADC walks all six INA240s via the FPGA
   (owner design basis); the six INA outputs route as a matched-length bus class
   [wb] so channel-walk timing skew stays sub-sample. Check: length report.
8. **Rogowski front end (Max fast path)**: coil pair enters as a guarded diff pair;
   integrator AT the AFE; the coil's mounting/geometry is a fixture concern (module
   board only carries the pair + guard). PLACEMENT OF VOLTAGE TRACKING IS OPEN
   (owner: fast-vs-slow path undecided; the one validated >1 MS/s use case is ATX
   ripple = a VOLTAGE measurement) — reserve an AFE input + divider position for
   it rather than deciding here. Check: reserved-position BOM row (DNP).
9. **Real bandwidth ceilings are the SENSOR'S** (owner fact 2026-07-05): INA240
   usable BW + the shunt's inductive corner cap the slow path — do not spend
   layout heroics past them; the prototype's 50 kHz/10 kHz numbers were artifacts
   of flyover wires + filter caps, not the parts. Why recorded here: stops a
   future pass "optimizing" the wrong constraint.
10. **Hub Pro per-port RS-485 receivers**: one RX per port (OQ-5 working basis),
    receiver strip adjacent to its port column, fail-safe bias resistors HUB-side
    (the module is TX-only); P4 UART/SPI fan-in documented per port. Check:
    netlist per-port assertions (pattern from hub-ent sheet 05).
11. **Hub Pro USB High-Speed**: 90 Ω pair, length-matched ±0.5 mm [wb], ESD at the
    connector; HS (480 Mbps) makes the Standard hub's USB rules load-bearing
    rather than comfortable. Check: USB class + impedance audit.
12. **Supercap provision (Pro + Max modules — RULED)**: 2S radial DNP footprints +
    ONE charge-limit R (sets cold-plug peak ≤0.5 A class against the shared
    ~2.5 A 5VSB budget — study bench item) + Schottky isolation + balance bleed;
    downstream of the 5VSB entry, upstream of the LDO reservoir node (the §2.9
    pattern). Silk marks the DNP outline + polarity. Hand-solder line this run
    (owner FINAL). Check: BOM DNP lint + power-class widths + the SPICE pilot for
    the charge/discharge curve (provenance-labeled). [practice I.6]
13. **Persist-class consequence**: WITH the supercap populated, Pro/Max hold-up
    moves to tens of seconds → the persist contract flips from gasp to full-state
    (firmware/contracts/persist-on-fault.md §Tier outlook, recorded 2026-07-16;
    the concrete pack rulings live in the supercap study on the pipeline branch —
    cross-referenced there). Layout's job: the flush path (flash + its rail) stays
    powered by the reservoir node, LEDs/ports are sheddable (load-shed ISR order).
14. **Everything else INHERITS the Standard sheet**: sensing corridors, pour
    doctrine, blade interface, RJ-45/DETECT (Pro DETECT = **4.7 kΩ**, the
    CAN+RS-485 code — check row), stackups, mechanical.

## D. Routing standards (delta rows over the Standard table)

| Class | Nets | Width / rules |
|---|---|---|
| RS485 | STREAM_P/N | 0.25 mm coupled, 120 Ω TARGET — geometry tuned or mismatch accepted at the SI bench (§C.4); named class so `audit_impedance` measures it |
| LVDS | AD9253→GW5A | 100 Ω diff, ±0.5 mm intra / ±5 mm inter, unbroken reference (shared rule w/ ENT + tester sheets) |
| SAR_Analog | INA outs → LTC2358, REF | guarded, matched bus [wb], ≥2 mm from switchers, no parallel >10 mm |
| FAST_AFE | shunt + Rogowski diff pairs | guarded diff pairs, gap per AFE input Z [wb], shortest-path priority over everything except Kelvin |
| USB_HS | Hub Pro D± | 90 Ω, ±0.5 mm [wb], ESD at connector |
| SCAP | supercap charge path | 1.0 mm min; charge-R node is the deliberate bottleneck (do not "fix" it with copper) |
| DETECT | — | Pro modules 4.7 kΩ code (12VHPWR Pro row of the locked table) |

## E. Stackup

Pro modules: platform 4L cable-board doctrine (Standard sheet §E) — the SAR island
and RS-485 pair fit without a 6L escalation [wb — revisit only if the 12VHPWR Pro
capture's escape density says otherwise]. Max digitizer lane: 4L with L2 unbroken
under the LVDS lane (tester-max precedent). Hub Pro: Standard-hub 4L exception
pattern (one inner GND + one inner signal) until the 8-port RS-485 strip's
congestion measures otherwise.

## F. Pipeline gates (pipeline-of-record = `claude/pipeline-consolidation`)

Standard sheet §F applies wholesale (TPC pass-form, netclass-DSN carriage, 2.5D
thermal + mirage guard, electrothermal, impedance/kelvin-loop/crosstalk audits,
SPICE pilot, SB-08, intake gate, DRAFT discipline). Pro/Max additions:
1. `audit_impedance` runs on RS485 + LVDS + USB_HS classes BEFORE first route
   (the CAN 91–105 Ω finding proves the stackup will surprise you — measure first).
2. NEW checkers: `qfn-escape-completeness` (P4), LVDS lane plane-integrity (shared
   with ENT/tester implementations — build once).
3. SPICE pilot on the supercap charge/hold-up curve + the fast-AFE input network;
   all SPICE numbers provenance-labeled (never presented as bench).
4. Bench gates that layout must not pre-empt: RS-485 SI at stream rate, AD9253
   lane eye, INA240/shunt inductive-corner characterization (§C.9), supercap
   leakage + cold-plug inrush (study items).

## G. Mechanical

Supercap seated height 8.5–11 mm class vs enclosure lid [wb — check per pack];
hand-solder line item this run (owner FINAL); polarity + DNP silk. Rogowski coil =
fixture-side mechanics, not board. Everything else inherits Standard §G.

## H. Per-board deltas

- **12vhpwr-pro**: the pathfinder — first capture order: Z-SAR + Z-STREAM onto the
  existing 12VHPWR Standard lane doctrine; DETECT 4.7 kΩ; P4 replaces S3.
- **EPS/PCIe Pro**: §6.13 ladder boards — INA240 fast path bolted onto the
  EPS/PCIe condensed frames; same Z-SAR/Z-STREAM pattern; watch OQ-9/OQ-57-59
  gating decisions.
- **EPS/PCIe/12VHPWR Max**: Z-DIGI + Z-FAST on the same frames; the 2026-06-11
  ruling is the architecture authority (spec §6.11 stale, owner-pen).
- **Hub Pro**: 8-port; RS-485 receiver strip; USB HS; bulk power JST per OQ-1;
  otherwise Standard-hub base.
- **Supercap provision**: Pro + Max module boards, DNP, per §C.12.

## I. Industry best practices — routing + placement, with citations

**I.1 Mixed-signal grounding — ADI MT-031 (*Grounding Data Converters*)**: star/
island AGND joined at one point near the converter, never split planes under
signal runs — §C.1's island policy verbatim.
**I.2 Decoupling — ADI MT-101 + the LTC2358-18 datasheet layout section**: bypass
at the pins, ref bypass dedicated; the SAR's simultaneous-sampling front end is
only as good as its reference node.
**I.3 RS-485 — TI SLLA272 (*The RS-485 Design Guide*)**: 120 Ω differential class,
termination/fail-safe bias discipline (bias at the receiving end — hub-side here),
stub minimization at the transceiver.
**I.4 MCU escape — Espressif ESP32-P4 hardware design guidelines** (QFN-104 land,
EP via field, decoupling, USB routing) — part authority at capture.
**I.5 High-speed ADC LVDS — AD9253 datasheet layout guidelines + TI SLLD009 (*LVDS
Owner's Manual*)**: pair matching, reference continuity, receiver-end termination;
clock jitter budget owns the clock route.
**I.6 Supercapacitor charge/limit practice — Eaton PHB/PHV datasheets + study**
(`docs/supercap-ups-study-2026-07-15.md`, pipeline branch, with live DigiKey/Eaton
links): single series-R charge limiting, pack-internal balancing, leakage as a
continuous 5VSB draw (bench item) — the no-IC shape is the ruled Pro/Max form.
**I.7 Impedance + skew philosophy — IPC-2141A + Bogatin (*Signal and Power
Integrity — Simplified*, 3rd ed.)**: match to the rise-time budget (LVDS tight,
SAR bus loose), measure the stackup before trusting targets — mechanized by
`audit_impedance`.
**I.8 Return paths — Ott (*Electromagnetic Compatibility Engineering*) ch. 16-17**:
unbroken references under LVDS/USB-HS/RS-485; the FAST_AFE guard discipline.
**I.9 Current sensing — TI INA240 datasheet + SBOA-class app guidance**: inherited
from the Standard sheet (§I.10 there); the Pro delta adds the ADC-side rules
(I.1/I.2 here), not new sense-side ones.
**I.10 IPC baseline — IPC-2152 / IPC-2221B / IPC-7351B / IPC-4761**: as the
Standard sheet §I.1/.5/.6 — one platform doctrine.

## J. Open items on this sheet

1. Every **[wb]**: SAR bus match, FAST_AFE gap, USB_HS match, P4 via-in-pad call,
   supercap heights — freeze at each board's layout kickoff.
2. Voltage-tracking placement (fast vs slow path) — OWNER-OPEN (§C.8); reserved
   AFE position is the hedge.
3. OQ-5 (RS-485 per-port vs multidrop) — Hub Pro's strip assumes point-to-point.
4. RS-485/LVDS impedance geometry vs the measured stackup (audit before route).
5. Supercap bench items: leakage draw, cold-plug inrush vs the 2.5 A shared rail,
   flush-path load-shed order (contract tie-in).
6. Spec §6.11 stale vs the 2026-06-11 Max ruling — owner-pen item (already
   tracked); this sheet follows the RULING.
7. Sheet lives on the firmware/tester branch; pipeline + supercap study live on
   `claude/pipeline-consolidation` — reconcile at merge.
