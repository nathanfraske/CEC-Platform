# Hub reservoir architecture comparison - 2026-09-21

**Later owner decision, 2026-09-21:** the supercapacitor cost is unacceptable;
exclude it from active selection. Retain its study below only as historical
research. The authorized two-cap fit result is in
`hub-two-cap-fit-study-2026-09-21.md`.

## Decision summary

The horizontal supercapacitor is electrically plausible and saves height, but
it is not the low-cost choice for the existing 10 ms persistence requirement.
Carry **two Lelon VZH472M1CTR-1816 capacitors** as the simpler, currently stocked
JLC-native path. Carry **Eaton PHV-5R4H474-R + BQ25173 + LM73100** as the compact
alternative only if the height/placement benefit warrants the cost and sourcing
work. Neither option is qualified for release yet.

| Screened option | Height / space | Calculated hold-up | Parts cost, USD |
| --- | --- | --- | --- |
| One Lelon 4700 uF / 16 V | 17 mm maximum nominal-package height including L tolerance | 9.22 ms aged ideal upper bound: fails before ESR | 0.7927 at ten |
| Two of the same in parallel | Two 18 mm cans; about 42 x 21 mm local planning rectangle, not a final courtyard | 15.23-18.15 ms in stated ESR/leakage sensitivity cases | 1.5854 for the pair at ten-plus of each part |
| Eaton 0.47 F horizontal pack with charger/isolation | Cap body maximum 17.3 x 14.5 x 9 mm; electronics/support/lead lands additional | 154.24 ms at selected aged screening resistance; harsher ESR case fails | 10.4885 for three main parts at ten; 10.99-12.49 provisional with unquoted auxiliary allowance |

The cost figures are component subtotals, not assembled-board quotes or net BOM
deltas. They exclude removal credit for old C1, sourcing fees, assembly setup,
wave-solder operations, shipping, tariffs and taxes. Additional independent
fault protection, if required, is not fully costed. The supercap is not necessary
solely to provide 10 ms; its reason to exist here is compact low-height storage.

No active ECAD, BOM, footprint, routing or mechanical contract was changed. No
vendor message, sourcing request or order was sent. Companion correspondence is
in `hub-reservoir-supplier-questions-2026-09-21.md`.

## Authority and verification

Authority remains `build/ordinary-relief-next-inputs-20260920.json`:

- Hub retained placement: `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`, SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
- ATX retained placement: `build/native-assembly-placement-pass-20260920/atx-24pin-rev3/02-placement/board.kicad_pcb`, SHA256 `cb851d4dd9c7418e53ee316c26e7fac4fbd99cb8b55bfa8f77c89b249e807773`.
- Reproducer: `tmp/hub_reservoir_architecture_comparison_20260921.py`.
- Results: `build/hub-reservoir-architecture-comparison-20260921/screen.json`.
- Existing numerical regressions: **10 tests and 7 subtests pass**. Additional
  study assertions check the lossless analytic result, monotonic ESR/readiness
  response, fixed load, source hashes and source signatures before/after.

Unchanged load is **195.653766 mA at 3.3 V**, already including the agreed 20%
margin, with wired-only MCU operation and 85% efficiency floor. Input demand is
**0.759597 W**. Do not add a second 20% margin or invent radio loads. Existing
regulation floor is 3.45 V and persistence allocation is 10 ms. Upstream
`C_bulk1` is not counted as isolated hold-up capacitance.

The source detector stays upstream of the hold-up element. Its existing static
trip interval is 4.05972-4.66258 V; nominal 4.35519 V. Shutdown is initiated by
loss of the selected +5VSB source, **not by buck dropout**. Time in the tables
is available rail-hold time, before detection/firmware latency is subtracted.

## Proposed supercap circuit, not an approved schematic

Normal supply remains selected +5VSB through existing D1 to `+5V_HOLD` and the
existing 3.3 V buck. A separate branch charges the supercap from selected +5VSB
through **BQ25173DSGR / C2942216**. The supercap feeds `+5V_HOLD` through
**LM73100RPWR / C3210761**, oriented for discharge into the load and reverse
blocking from the normal supply into storage. Keep the upstream detector on
the source side. This permits normal Hub boot without waiting for an empty
supercap to charge; do not put the charger or a large charging resistor in the
sole normal-power/discharge path.

The original large C1 would be replaced only in a future ECO. Keep the buck's
local input ceramics, and qualify additional bridge capacitance for takeover.
The charger needs its own local input/output bypassing and exposed-pad ground
layout per TI. Do not count a physically distant supercap as HF decoupling.

### Charge voltage and temperature

Proposed BQ feedback resistors are **38.3 kohm / 10.0 kohm, 0.1%**. With 0.8 V
reference and TI's +/-1% accuracy, nominal setpoint is 3.864 V and the
resistor/reference-only interval is **3.81930-3.90884 V**. Reserving another
20 mV in each direction gives a screening start of **3.79930 V** and ceiling
**3.92884 V**. That 20 mV is an explicit design allowance, not a measured or
manufacturer-guaranteed complete error bound: select resistor TCR, bound FB
bias, layout error and startup overshoot before accepting it.

Eaton's extended 85 C operation requires derating to 4.0 V. The lower setpoint
addresses this normal-operation limit; the prior 4.15 V / 760.5 ms estimate
must **not** be reused for this architecture. No operation above 85 C is approved.
The BQ junction-temperature protection does not measure the supercap temperature.

### Charging demand and readiness

Proposed `R_ISET = 3.00 kohm, 1%` requests 100 mA. Combining the published
270-330 A-ohm gain range and resistor tolerance gives **89.11-111.11 mA** before
thermal regulation. This is additional selected-5V-source current, not part of
the already-margined 3.3 V load. The existing KVM/port/fan loads and F5 limits
must be checked before enabling it under every source-selection mode.

At +30% capacitance, charging from empty to the proposed upper bound takes
**26.94 s in an ideal constant-current-only calculation**. This is not a maximum
ready time: leakage, voltage taper, source sharing and thermal throttling can
extend it. Initial charger dissipation can reach 0.583 W at 5.25 V input, or
0.661 W at the existing 5.948 V static OVP high corner. Actual PCB thermal design
and repeated brownout cycling need validation; do not infer continuous thermal
success from the small IC package or its thermal shutdown. A lower charge
current remains an option if source/thermal headroom is insufficient.

Firmware needs an explicit ENERGY_READY condition and defined behavior before
it is true. BQ `STAT` indicates about 98% of the programmed voltage, but that
threshold is only typical; it is not a guaranteed energy measurement. Use a
bounded, calibrated measurement or comparator, plus a qualified ESR/health
criterion. At actual storage voltages 3.70 / 3.75 / 3.80 V, the selected model
gives 18.76 / 86.49 / 155.21 ms. These are inputs to a readiness design, not
approved ADC thresholds. Quick cycling must deassert readiness; normal boot
must never imply the storage is already charged.

### Discharge screen and handoff

Capacitance is 0.47 F x 0.9 initial tolerance x 0.7 life-envelope factor =
**0.2961 F**. The model includes LM73100's 44.85 milliohm on-resistance ceiling,
an extra **50 mV path allowance**, and **1 mA parasitic allowance**. The latter
includes room for the IC, divider and nominal cap leakage, but is not a
guaranteed hot/aged leakage bound. The path allowance likewise requires
validation across current, temperature and the selected protection parts.

| Assumed cap resistance | Total modeled series resistance | Hold-up |
| --- | --- | --- |
| 0.4 ohm | 0.44485 ohm | 277.50 ms |
| 0.8 ohm | 0.84485 ohm | 154.24 ms |
| 1.6 ohm, harsher sensitivity | 1.64485 ohm | **0 ms**: immediate output below 3.45 V |

The 0.4 ohm specification is at 100 Hz; doubling it is the published life-test
ESR envelope, not a guaranteed cold DC-pulse value. The failing sensitivity is
important: more stored joules cannot overcome an excessive instantaneous ESR
drop with this direct, non-boost discharge path. Cold/aged pulse testing is a
release gate, not something the large capacitance makes unnecessary.

The fixed-drop wrapper conservatively raises the pre-drop floor to `Vfloor+D`
and power to `P*(1+D/Vfloor)` before integrating the existing reservoir model.
It does not represent switching waveforms or replace transient simulation.

LM73100 can require up to 125 mV input-over-output difference before forward
takeover; its cited 50 us reverse-blocking recovery is **typical, not a maximum**.
For illustration, a 0.1 V bridge-droop allocation at 0.220 A requires about
110 uF **effective** for 50 us, or 2202 uF for 1 ms, before ESR. Therefore do not
promise that a token small ceramic is sufficient. Qualify takeover, source
return and buck behavior with the actual local input network; if the transition
needs a large bridge cap the supercap's space advantage shrinks.

### Protection that remains unresolved

Normal CC/CV regulation and reverse blocking are addressed by the architecture;
it is **not single-fault overcharge-qualified**. A failed charge switch or
feedback network needs separate analysis and, if required by the product's
fault criteria, an independent cutoff. Existing 5.948 V OVP is too high to serve
as a 4.0 V supercap protector; a diode's maximum VF cannot fix that.

LM73100's 5.5 A continuous rating is not a programmable current limit: its fast
fault threshold is about 21.9 A typical. It does not establish safe storage-branch
short protection. Maximum proposed stored energy is about 4.72 J at +30% C.
Select and coordinate a fuse/eFuse or prove the branch's short behavior before
release. A protector's added resistance must be included in this model. Do not
claim the BQ charging current limit limits a short discharging the capacitor.

## Native conventional alternative

**VZH472M1CTR-1816 / C249940** is currently stocked as Source JLCPCB, SMT,
Economic and Standard. Its catalog calls for 16.5 +/-0.5 mm L, despite the JLC
page calling 16.5 mm a maximum. Use **17 mm plus assembly tolerances**, not 16.5,
in the stack study. Current catalog package envelope is approximately
20.2 x 19.2 mm maximum in plan, before lands/courtyard/vent reservations.

Two need roughly 776 mm2 of separate package-envelope area; a 42 x 21 mm local
planning rectangle is 882 mm2 versus current C1's roughly 355 mm2 courtyard.
This is **not** an assertion that the whole Hub must grow by that area. Placement
can reclaim neighboring room or split the pair if impedance and assembly permit.
Conversely, they cannot both occupy the current C1 courtyard unchanged.

Initial -20% and another -30% after the specified endurance test give 2632 uF
per capacitor, 5264 uF for the pair. Its 5000-hour test at 105 C does not, by
itself, establish the assembled product's service life.

| Effective resistance assumed per capacitor | Pair hold-up |
| --- | --- |
| Ideal, zero leakage | 18.43 ms upper bound |
| 0.048 ohm, catalog 100 kHz impedance used only as a screen | 18.15 ms |
| 0.4 ohm sensitivity | 17.06 ms |
| 1.0 ohm sensitivity | 15.23 ms |

Lossy rows use 752 uA leakage per cap, derived from the specified 20 C bound
at rated voltage. Neither that leakage nor the AC impedance proves all-temperature
DC transient performance. Remaining time beyond 10 ms is 5.23-8.15 ms for these
cases, before detection and firmware overhead; measure those overheads.

At +20% tolerance the pair is 11280 uF. Requesting a 4.15 V rise in the existing
10 ms interval asks for **4.68 A** for the capacitors alone. That exceeds the
roughly 3.8 A nominal mux current limit before load. The result is not a magical
4.68 A source: it is a slower/current-limited rise, and potentially thermal or
startup trouble. Recalculate ramp/source sharing and verify boot. Both candidate
architectures need startup work; two caps are simpler, not a drop-in proof.

A smaller 16 mm, 10 V version, **VZH472M1ATR-1616 / C249939**, is listed native
but currently **zero stock**, minimum preorder 14, estimated USD 0.6543 each.
It could reduce the two-package envelope to about 626 mm2; neither that estimate
nor a preorder page proves delivery. No stocked single low-profile part with
adequate aged margin was established in the bounded searches. Do not describe
this as proof that none exists anywhere.

## Live sourcing snapshot

Checked September 21, 2026; stock is not reserved. JLC distinguishes total stock
from available order quantity.

| Part | Source | Stock / orderable | USD at 10+ |
| --- | --- | --- | --- |
| PHV-5R4H474-R | Mouser; JLC acceptance unresolved | 418 / seller says can ship | 8.27 |
| BQ25173DSGR, C2942216 | JLCPCB native SMT | 745 / 704 | 1.1573 |
| LM73100RPWR, C3210761 | JLCPCB native SMT | 2727 / 2551 | 1.0612 |
| VZH472M1CTR-1816, C249940 | JLCPCB native SMT | 50 / 42 | 0.7927 each |

The available conventional stock supports at most 21 two-cap boards before
assembly attrition. Use fresh product pages; search-index pricing/stock differed
materially. Eaton has no verified native-JLC listing, and the existing investigation
found ultracapacitors excluded from JLC consignment. A Global Sourcing request
is not acceptance. Its wave-solder-only construction is a separate assembly gate.

## Mechanical and validation gates before either ECO

1. Repair/verify the actual Hub-ATX connector pad mating geometry and insertion
   interval. The prior 18 mm nominal gap is not accepted; a roughly 22 mm target
   is a study candidate, not a finalized stack dimension.
2. Check actual two-sided bodies, tolerances, solder tails, venting, RJ45 cable
   access and supports at the corrected mating pose. A 17 mm cap leaves nominal
   5 mm to a bare opposite board at a hypothetical 22 mm gap; occupied opposing
   volume and vent clearance reduce that. A 9 mm body alone does not prove fit.
3. Measure hot/cold/new/aged-equivalent discharge, rapid cycling and real shutdown
   latency. Include all actual hold-up loads; leave the agreed system load
   assumptions unchanged unless measured evidence requires a reviewed change.
4. Verify startup under each power source, max concurrent external loads, mux
   limits and diode/charger temperatures. Verify no source backfeed.
5. Supercap only: finish independent fault protection, readiness accuracy,
   takeover bridge network, local thermal mission and assembly acceptance.
6. Only after selection: schematic ECO, exact auxiliary MPN/LCSC selections,
   footprint/model verification, ERC, placement/DRC, stack review and bench tests.

## Sources

- [TI BQ25173 datasheet](https://www.ti.com/lit/ds/symlink/bq25173.pdf), electrical characteristics and operating/charge-control sections; local official-language copy `tmp/pdfs/hub-reservoir-architecture-20260921/bq25173.pdf`.
- [TI LM73100 datasheet](https://www.ti.com/lit/ds/symlink/lm7310.pdf), electrical and switching tables; local copy `tmp/pdfs/hub-reservoir-architecture-20260921/lm7310.pdf`.
- [Eaton PHV data sheet, September 2024](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-phv-supercapacitors-cylindrical-pack-data-sheet.pdf).
- [Lelon 2026 catalog](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf), printed pages 115-116, visually checked; local copy `tmp/pdfs/hub-single-dual-reservoir-20260920/lelon-2026-catalog.pdf`.
- [JLC BQ25173DSGR](https://jlcpcb.com/partdetail/TexasInstruments-BQ25173DSGR/C2942216), [JLC LM73100RPWR](https://jlcpcb.com/partdetail/TexasInstruments-LM73100RPWR/C3210761).
- [JLC stocked Lelon](https://jlcpcb.com/partdetail/Lelon-VZH472M1CTR1816/C249940), [JLC smaller out-of-stock Lelon](https://jlcpcb.com/partdetail/Lelon-VZH472M1ATR1616/C249939).
- [Mouser PHV-5R4H474-R](https://www.mouser.com/en/ProductDetail/Eaton-Electronics/PHV-5R4H474-R?qs=e7A2guvi5TCigmEsFz0iJw%3D%3D), fresh page rather than search-index snapshot.
- [JLC consignment terms](https://jlcpcb.com/help/article/consignment-part-terms-conditions).

Local PDFs were examined as sources, not altered or re-exported. No SPICE model,
physical sample, full thermal solve or assembly qualification was run in this study.
