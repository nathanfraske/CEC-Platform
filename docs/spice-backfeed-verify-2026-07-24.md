# SPICE verification: USB-backfeed protection package (2026-07-24)

**What this is.** Independent SPICE-level verification of the v1.6.0 USB-backfeed
protection package (spec `CEC-Platform-Ground-Truth-Spec.md` Sections 2.9 / 6.14; owner
rulings recorded in `docs/owner-queue.md`'s three 2026-07-24 rows; per-board part plan
`docs/usb-ingress-bom-delta-2026-07-24.md`), before and after mitigation, across the six
cases the verification request specified (A-F below). Every device model is fit to a
real, cited datasheet value; every case is either a real ngspice transient run or (Case E
only, by its own nature — see below) a closed-form paper bound built on the same
calibrated models. Sim scripts: `scripts/sim/cec_backfeed_models.py` (device models,
ngspice runner, analysis helpers) and `scripts/sim/cec_backfeed_cases.py` (the six
cases). Every number in this document traces back to those two files — re-run with
`python3 scripts/sim/cec_backfeed_cases.py [A|B|C|D|E|F ...]`.

## Engine

**ngspice 44.2** (KLU direct linear solver), run inside `docker-routing-1` (the repo's
existing routing container, which already carries ngspice for `scripts/cec_spice.py` and
`scripts/cec_spice_sanity.py`). Neither the host nor the container has PySpice; ngspice
itself is the real, proper engine here, driven directly (`docker exec docker-routing-1
ngspice -b <deck>.cir`) rather than through a Python wrapper library, which is both
simpler and matches the repo's own established pattern for the two prior SPICE scripts.
No fallback numerical integrator was needed — real ngspice was available throughout.

Every transient deck runs with `UIC` (use initial conditions) and explicit `IC=` on every
capacitor that represents a "starts dead/uncharged" state (a faulty PSU's bulk cap, a
module's own local bulk before power-up, a polyfuse's thermal-energy state) — see
Methodology note 2 below for why this matters and what breaks without it. Full transient
vectors are pulled back via `wrdata` (plain ASCII) and analyzed in numpy on the host
(peak, threshold-duration, and charge-integral all computed independently in Python, not
via ngspice's `.measure`) — see Methodology note 1.

## Methodology notes (things that would otherwise silently corrupt the results)

These are recorded because they are exactly the kind of error that looks like a circuit
finding instead of a tooling bug, and because a future re-run of this harness needs to
not reintroduce them.

1. **ngspice's `.measure`/`meas` command has interactive-vs-batch-mode friction** (the
   interactive control-block command name does not match what a first read of the
   ngspice docs suggests). Rather than fight it, every case here dumps the full
   transient waveform via `wrdata` and does peak/duration/charge analysis in plain,
   independently-checkable numpy (`cec_backfeed_models.peak_abs` /
   `duration_above` / `charge_coulombs`) — more code, but every intermediate number is
   inspectable.
2. **ngspice computes a DC operating point at t=0 by default**, even for a `.tran`
   analysis. For a "thermal energy" accumulator capacitor (the polyfuse I²t model, below)
   this means the op-point solver finds the capacitor's own *steady-state* value and
   starts the transient already sitting there — silently erasing the entire "does it
   accumulate stress *from zero* fast enough to trip" question. Fixed with `IC=0` on
   every such node plus `.tran ... UIC` (skip the op-point calculation, start from
   specified initial conditions). Caught by a calibration self-test that produced an
   immediately-implausible result (energy already at its 22.76s-time-constant asymptote
   at t=0), not by inspection.
3. **The first line of any SPICE deck is unconditionally consumed as the title and
   silently discarded as a circuit element** — classic SPICE convention, and a real trap
   for programmatically-generated decks: a title-less deck does not error, it just
   silently deletes your first real component. Every deck-building function in
   `cec_backfeed_models.py` starts with a `TITLE` comment line for exactly this reason;
   several ad hoc debugging snippets during development did not, produced a floating
   node, and were briefly (and wrongly) diagnosed as an ngspice switch-convergence bug
   before the real cause was found by bisecting down to the simplest possible circuit.
4. **Plain resistors do not support `i(Rname)` in this ngspice build** (`Error: no such
   function as i`) — only independent-source branches do. Every place a resistor's
   current is needed, a `0V` voltage source is inserted in series as an explicit ammeter
   and `i(Vammeter)` is read instead (the same trick the repo's own
   `cec_spice_sanity.py` already uses).
5. **A behavioral (VCCS/`G`-element) source with its OWN output nodes inside its
   controlling expression does not behave like a passive two-terminal device** — an
   attempt to build a "smooth OV1 disconnect" as a self-referential variable conductance
   produced 0V/0A everywhere instead of the expected resistive-divider behavior. Not used
   in the final models; the OV1/PR1 select logic instead uses ngspice's native
   voltage-controlled switch (`S`/`.model SW`) with independent, single-ended,
   ground-referenced control nodes (never a floating differential control pair, never two
   switches cascaded in series) — this was also the fix for a genuine early numerical
   convergence failure ("Timestep too small... trouble with sov1-instance") that turned
   out to be two compounding problems: the title-line bug above leaving IN1 floating, and
   an originally-cascaded two-switch-per-channel OV1 design that doesn't match how the
   datasheet actually describes the behavior anyway (Sec 9.3.5: an OV-tripped channel
   gets "fast switchover to the other input... if it is a valid voltage" — i.e. OV status
   feeds the *same* selection decision, not a separate series block in front of it).
   `cec_backfeed_models.mux_priority_subckt` reflects the corrected single-switch-per-
   channel design.

## Device models and parameter sources

**SS34 Schottky (D2 on every module today; C8678, MDD).** Fit to the actual MDD
SS32-SS3200 datasheet (Rev 2024A5), fetched from the LCSC mirror of the repo's own BOM
line for C8678: `datasheet.lcsc.com/datasheet/pdf/dfa1ff67dea875d0135103ba9ada713a.pdf`.
Datasheet anchors used: **VF max = 0.55 V @ IF = 3.0 A, 25 °C** (SS32-SS35 voltage-class
group, which SS34/40V falls in) and **IR max = 0.5 mA @ VR = 40 V (rated), 25 °C** (same
group). SPICE `.model SS34 D(...)`: `N=1.10` (Schottky-typical ideality, an engineering
choice — the datasheet gives only the one precise forward point, not a full I-V curve
digitization) and `RS=0.025 Ω` (typical bulk+contact resistance for a 3 A/DO-214AC-SMA
die of this class, also an engineering choice), with `IS=1.68e-7 A` *solved* so the model
reproduces the datasheet's forward anchor exactly. **Self-test result: the fitted model
gives VF = 0.5501 V at IF = 3.0 A** (target 0.55 V) — verified before use, not assumed.
`BV=40`, `IBV=0.5m` taken directly from the datasheet for a correct high-voltage reverse
region (never actually reached in any case here, all reverse excursions are ≤12 V).

**Polyfuses (F1 on every module, C371166; F5 on the Hub's KVM stage, C5707763).**
Modeled as **resistance-with-I²t-trip**, per the verification request's own framing: a
fixed cold resistance in series, plus a *leaky-integrator* thermal-energy state
(`dE/dt = I(t)² − E/τ`, trips when `E` crosses `E_thresh`) rather than a bare (non-leaky)
I²t accumulator — a bare accumulator would eventually mis-predict a trip at *any*
sustained current however small, since `∫I²dt` grows unboundedly; the leaky form is a
standard single-pole thermal-analog simplification that correctly reproduces "a device
held at exactly its rated `Ihold` never trips, no matter how long."
Calibration (closed-form, two constraints): `E_thresh = I_test² × t_test` from the
datasheet's own "Maximum Time To Trip" row (a *worst-case max-time* guarantee, so this
model's predicted trip times are a **conservative upper bound** — a real device trips at
least this fast, plausibly faster); `τ = E_thresh / Ihold²` so the model's DC
steady-state energy at `I=Ihold` sits exactly at the trip boundary. Datasheet source:
**Littelfuse 1206L Series** (Rev 02/25/19), fetched from the LCSC mirror of the repo's
own F1 BOM line, C371166 —
`datasheet.lcsc.com` mirror of the 1206L family sheet (same document family as the
already-vendored `lib/datasheets/Littelfuse_2920L.pdf`, but the 1206-package sheet, which
is the actually-populated part):
| Part (row used) | Ihold | Itrip | Vmax | Max-Time-To-Trip | Rmin | R1max |
|---|---|---|---|---|---|---|
| **F1**: 1206L075/16 (=1206L075/16WR, C371166) | 0.75 A | 1.50 A | 16 V | 8.00 A → 0.20 s | 0.090 Ω | 0.290 Ω |
| **F5 stand-in**: 1206L110TH | 1.10 A | 2.20 A | 8 V | 8.00 A → 0.10 s | 0.040 Ω | 0.210 Ω |

F1's calibration gives `E_thresh=12.8 A²s`, `τ=22.76 s`; F5's gives `E_thresh=6.4 A²s`,
`τ=5.29 s`. **F5 caveat**: the populated part is FUZETEC FSMD110-16-1206R (C5707763, no
vendored curve available), *not* Littelfuse; the 1206L110TH row is used as a same-class
(1.1 A hold, 1206 package, same generation of PPTC construction) stand-in per the
`usb-ingress-bom-delta-2026-07-24.md` document's own framing of the Littelfuse family as
the reference curve — flagged here as an approximation, not an extraction of the actual
FUZETEC part. Pre-trip resistance (`Rcold`) is not separately tabulated as "typical" by
either datasheet row (only Rmin and post-trip-cooldown R1max are given); this file uses
0.150 Ω (F1) and 0.070 Ω (F5), an engineering estimate between the two bounds, clearly
distinct from an extracted value. **Both calibrations were verified by direct simulation
before use**: driving F1 at a constant 8 A trips the model at **t = 0.201 s** (target
0.20 s); F5 at **t = 0.101 s** (target 0.10 s). A constant-current DC check also confirms
the leaky-integrator design point: F1 held at exactly its own 0.75 A `Ihold` for 150
simulated seconds reaches 99.86% of `E_thresh` and never crosses it.

**TPS2121 priority power mux (every stage, C485916).** Behavioral model built directly
from the vendored datasheet, `lib/datasheets/TPS2121RUXR.pdf` (TI SLVSEA3F): `RON = 60
mΩ` (56 typ/70 max @25°C, `IOUT=200mA` condition, Sec 7.5 — typical used); `ILIM` law
`I_LM = 65.2 / R_ILIM^0.861` (`R_ILIM` in kΩ, Sec 9.3.2 Eq. 2) giving **1.237 A** at the
platform's 100 kΩ strap (matches `usb-ingress-bom-delta-2026-07-24.md`'s own 1.24 A
figure); soft-start slew rate from datasheet **Table 9-1** (Sec 9.3.1.1); `PR1` valid
threshold **4.27 V** and `OV1` trip threshold **6.04 V** taken directly from
`usb-ingress-bom-delta-2026-07-24.md`'s strap-value derivations (100 k/33 k and 47 k/10 k
dividers against the datasheet's `VREF=1.06V typ`); leakage `ILK,INx` **1 µA typ (25°C) /
500 µA MAX (−40…125°C, Sec 7.5 electrical table)** — both figures used, typical for
realistic-case numbers and the 500 µA MAX as the deliberately conservative bound for
every worst-case claim in this report. `ov1_trip=True` folds the OV condition directly
into the *same* channel-select decision (see Methodology note 5) rather than a separate
series-switch block, matching Sec 9.3.5's stated behavior.

**C_SS soft-start ramp time — a discrepancy found and flagged (not smoothed over).**
The repo's own documents (`docs/owner-queue.md`'s ILIM-ruling-follow-up row; spec
Section 2.9's persist-on-fault text) repeatedly cite "the hub-proven C_SS 2.2 µF (~10 ms
ramp)". No bench-measurement document backing that number was found in the repo (search
performed as part of this verification — see the task's own research trail). **The
TPS2121 datasheet's own Table 9-1 (Slew Rate vs. CSS Capacitor, VIN=5V: 100 nF→780 V/s,
1 µF→88 V/s, 10 µF→8.8 V/s) instead predicts ≈40 V/s at C_SS=2.2 µF (log-linear
interpolation, consistent 1/C scaling across all three tabulated points: `88 V/s × 1µF =
8.8 V/s × 10µF ≈ 88 V·µF/s`), giving a 0→5 V output ramp of ≈125 ms — roughly 12× slower
than the repo's stated 10 ms.** This does **not** change any safety verdict in this
report (a *slower* ramp only lowers peak inrush current further, strictly improving
margin on every axis checked here) — both figures are simulated explicitly below (Case B)
and both pass with large margin. It is flagged because the repo's own "~50 mA inrush"
estimate (`docs/owner-queue.md`) is built on the 10 ms figure and would revise down to
≈1.2 mA if the datasheet-table figure is the real one; recommend a bench check (scope the
actual C_SS=2.2µF ramp on a shipped Hub board) to settle which number is real, since nothing
else in the design currently depends on knowing which one is true.

**eFuse host model and USB budget (given directly by the verification request, used
as-specified, not re-derived):** fast/hard trip at **2.5 A sustained ≥ 1 ms**; a **50 µC**
total-inrush-charge budget (matches the classic USB "≤10 µF bulk capacitance without a
controlled soft start" heuristic: `10 µF × 5 V = 50 µC`).

---

## Case A — Baseline UNMITIGATED module

Topology: `USB 5V (Rsrc=0.12Ω incl. cable) → D2 (SS34, forward) → module rail → 25 mΩ
shunt → faulty-PSU 5VSB bulk`, swept over `{100, 470, 1000, 3300} µF × {caps-only,
2Ω parallel fault}`.

| Bulk cap | Fault | Ipk | Hard-trip (2.5A/1ms)? | Charge (window used) | PSU-side settled V |
|---|---|---|---|---|---|
| 100 µF | none | 26.2 A | No | 0.484 mC (full charge, C·V) | 4.839 V |
| 100 µF | 2 Ω | 26.2 A | No | 125.8 mC over 60 ms window (sustained ~2.09 A) | 4.18 V |
| 470 µF | none | 26.25 A | No | 2.254 mC | 4.795 V |
| 470 µF | 2 Ω | 26.25 A | No | 127.2 mC over 60 ms | 4.18 V |
| 1000 µF | none | 26.26 A | No | 4.773 mC | 4.773 V |
| 1000 µF | 2 Ω | 26.26 A | No | 129.2 mC over 60 ms | 4.18 V |
| 3300 µF | none | 26.27 A | **Yes** (1.35 ms above 2.5 A) | 12.3 mC to the 1 ms-past-trip point (15.6 mC full 60 ms) | 4.737 V |
| 3300 µF | 2 Ω | 26.27 A | **Yes** | 12.8 mC to trip point (138.1 mC full 60 ms) | 4.18 V |

**Cross-check verdict: CONFIRMED with one correction.**
- **Ipk ~27 A: CONFIRMED.** SPICE gives 26.2-26.27 A across the whole sweep (peak is
  essentially cap-independent, set by `Rsrc + Rshunt + SS34's own RS` against `5V − Vf`);
  a hand check without SPICE — `(5 − 0.55)/(0.12+0.025+0.025) = 26.2A` — matches to
  three figures. The task's "~27 A" reference figure is right.
- **Caps-only charge, 0.5-22 mC: CONFIRMED (extrapolated).** `Q=C·ΔV` exactly, so 100 µF
  → 0.484 mC and 3300 µF → 15.6 mC (60 ms window) bracket the low end cleanly; a 4700 µF
  cap (not in this sweep — see note below) would give ≈23.3 mC, matching the "22 mC"
  figure almost exactly.
- **2 Ω-fault charge, "~400 mC": CORRECTED — window-dependent, not a fixed number, and
  the specific 2.5A/1ms hard-trip criterion is MARGINAL for this exact fault resistance,
  not a clean guaranteed hit.** The sustained current a 2 Ω-faulted PSU actually pulls
  through this path settles at **4.18 V / 2 Ω ≈ 2.09 A — *below* the stated 2.5 A
  hard-trip threshold**, confirmed independently by a plain Ohm's-law check on the SPICE-
  reported settled voltage. Charge is therefore simply `2.09A × window`, not a number
  fixed by any trip point: at the 60 ms window used here it is ~126-138 mC; reconstructing
  the earlier quick-sim's "~400 mC" implies roughly a 190 ms window (`2.09 × 0.19 ≈
  0.397 C`), which is entirely plausible for a different but unstated integration length.
  **The important, non-window-dependent facts are:** (1) 2.09 A is 2-4× a typical USB
  port's *steady-state* allowance regardless of whether it trips a specific 2.5 A fast
  comparator; (2) the 50 µC budget is blown in the first ~24 µs of the fault
  (`50µC / 2.09A`) and stays blown indefinitely — nothing in the baseline design limits
  it, ever; (3) **the 3300 µF caps-only case (no fault at all) already crosses the stated
  2.5A/1ms hard-trip on its own** (SPICE: 1.35 ms above threshold while charging; a
  simplified linear RC-time-constant hand check, `τ·ln(26/2.5) = 0.17Ω×3300µF×ln(10.4) ≈
  1.31ms`, agrees to within ~3% — the small gap is the diode's own nonlinear forward
  drop, which the hand check ignores and SPICE does not), meaning a sufficiently large —
  but entirely plausible — module bulk
  cap trips a host port with **no PSU fault involved whatsoever**. **Net: the qualitative
  finding ("this fault class is a guaranteed host-side problem") is confirmed and if
  anything strengthened by finding #3; the literal "~400 mC / trips every time" framing
  is corrected to "sustained current sits right at the edge of / just under the stated
  hard-trip threshold, is unbounded in time, and blows the charge budget in
  microseconds regardless."**

Note on topology: the task specified this exact sweep (`{100,470,1000,3300}µF`) as the
24-pin's own direct `SS34→25mΩ shunt` path. The *other* modules' path (their own SS34,
then the RJ-45 VCC tree into the Hub's 4700 µF hold-up) is topologically the same
mechanism (a forward Schottky charging a downstream bulk cap, unlimited) with a slightly
different series R; Case D(i) below runs the Hub's actual 4700 µF figure (via the
diode-less KVM tap, which is a related but distinct — and worse — path) and gives a
useful bound on the same physics.

---

## Case B — MITIGATED module

**B1. Port-side inrush (local ~30 µF bulk, through TPS2121 soft-start).**

| C_SS ramp assumption | Ipk (port-side) | Charge | ILIM margin | eFuse hard-trip? | Over 50µC budget? |
|---|---|---|---|---|---|
| 10 ms ("hub-proven", repo docs) | 15.0 mA | 150 µC | 82× | No | **Yes, nominally** (see note) |
| 125 ms (this report's datasheet-table figure) | 1.20 mA | 150 µC | 1029× | No | **Yes, nominally** |

Charge is identical either way (`Q=C·V=30µF×5V=150µC`, independent of ramp rate — charge
into a capacitor is conserved regardless of how the current is shaped over time) and
**does nominally exceed the 50 µC heuristic figure in raw coulombs.** This is flagged
explicitly rather than reported as a clean pass: the 50 µC number is the USB "≤10 µF
without a controlled soft start" heuristic, and a 30 µF local bulk is structurally over
10 µF regardless of any protection — that is *exactly why* a controlled soft-start
element is required at all, and the actual host-relevant metric (peak/average current
into the port) passes with 82-1029× margin. **Verdict: PASS on the metric that actually
protects the host (current), technically over budget on the raw-coulomb heuristic by
design, not a real deficiency — but recorded loud per the report's own instruction, since
a bare "meets the 50µC budget" claim would be false.**

**B2. Leakage path — the ORIGINAL fault class, now behind isolation.** With a faulty/
dead PSU on IN1 (mux input isolation open, PR1 invalid) and VBUS on IN2 driving OUT, the
only residual path back toward the dead PSU-side bulk is the datasheet's own `ILK,INx`
leakage spec (Sec 7.5), used here at its full-temperature-range **500 µA MAX** as a
deliberately conservative bound (25°C typical is 1 µA, 500× smaller):

| Dwell time | Charge @ 500µA (worst-case bound) | Charge @ 1µA (25°C typical) | Over 50µC budget (worst-case)? |
|---|---|---|---|
| 1 ms | 0.5 nC | 1 pC | No |
| 10 ms | 5 nC | 10 pC | No |
| 100 ms | 50 nC | 100 pC | No |
| 1 s | 0.5 µC | 1 nC | No |
| 10 s | 5 µC | 10 nC | No |

Even at 10 continuous seconds of dwell and the datasheet's worst-case full-military-
temperature-range leakage figure, accumulated charge (5 µC) sits two orders below the
50 µC budget and roughly six orders below the baseline's millisecond-scale, millicoulomb-
class event. **Verdict: PASS, overwhelming margin — the original backfeed mechanism is
eliminated, not merely limited.**

**B3. Nuisance-trip check (F1, 750 mA-hold, under normal ESP flash-burst operation).**
Representative profile: 120 mA idle baseline, 500 mA bursts, 10% duty (50 ms burst / 500
ms period), 8 cycles simulated:

| Metric | Value |
|---|---|
| Peak I²t energy state reached | 0.138 (of 12.8 threshold) |
| Margin to trip | **98.9%** |
| Nuisance-trip? | **No** |

**Verdict: PASS, overwhelming margin.**

---

## Case C — REVERSE (PSU→USB)

Elevated PSU rail (5.5 V — a plausible faulty-but-not-extreme figure, deliberately kept
*below* the 6.04 V OV1 threshold to test the "just under the cutoff" case) against
nominal 5 V VBUS.

| Path | Reverse condition | Result |
|---|---|---|
| **Old D2 (SS34, still-shipping pre-mitigation topology)** | 0.5 V reverse bias (5.5V cathode-side vs 5V anode-side) | SPICE-fitted model: **168 nA**; datasheet worst-case ceiling (IR @ full 40V VRRM, 25°C): **0.5 mA**. Either way, negligible. |
| **Mitigated mux, powered case** | IN1=5.5V (below OV1's 6.04V, so PR1 still selects it normally, no trip) | IN2/VBUS sees exactly the modeled **500 µA leakage figure** (the same ILK,INx bound as Case B) — verified directly in the full mux transient model, `V(OUT)` tracks 5.5V, `I` into VBUS = 500µA exactly. |

**Verdict: PASS on both paths.** Neither the legacy diode nor the new mux lets a
moderately-elevated PSU rail push meaningful current back toward the host; the module's
LP5907/logic *does* see 5.5 V briefly on this path (a separate, non-backfeed concern —
within the LP5907's 6.5V abs-max with margin, see Case F for the worse 12V case).

---

## Case D — KVM path

**(i) PC-USB-powered NanoKVM into the hub 4700 µF + 5VSB tree, UNMITIGATED (today's raw
rail tap, "nothing in series").**

| Metric | Value |
|---|---|
| Ipk | **33.3 A** (higher than Case A's 26.2A — no diode drop at all, worse than the module case as owner-queue predicted) |
| Hard-trip (2.5A/1ms)? | **Yes** |
| Charge to trip point | 17.8 mC |

**Verdict: FAILS badly, confirming the owner-queue's "eFuse-trip class, nothing in
series" characterization — and quantifies it as *worse* than the module baseline.**

**(ii) With the third cascade stage (U11) + 1.1A-hold polyfuse (F5).**

| Metric | 10 ms ramp | 125 ms ramp |
|---|---|---|
| Ipk (port-side) | 15.0 mA | 1.20 mA |
| ILIM margin | 82× | 1029× |
| Hard-trip? | No | No |

Nuisance-trip check (F5, representative NanoKVM draw): repo's own cited figure for the
*original* NanoKVM this header was designed against is "~0.5-1A"
(`docs/24pin-rev3-respin-2026-06-24.md`); modeled at 0.6 A burst / 0.15 A idle, 20% duty:
**peak energy reaches 5.2% of the F5 trip threshold (94.8% margin), no nuisance trip.**

**Verdict: PASS, same margin structure as the module case.**

**(iii) A powered Hub back-drives a PC port through the KVM.**

*Before* (raw tap): modeled as the Hub's healthy, regulated ~5.05V rail hitting a
representative small host-port-side local cap (20 µF) with nothing in series —
**Ipk = 33.6 A, charge = 101 µC** (over the 50µC budget by 2×, even with a small
receiving-side cap; does not cross the 1ms hard-trip window at this cap size, but the
underlying mechanism is identical to (i) and *would* at a larger cap). **FAILS.**

*After* (3rd stage + polyfuse): **architectural elimination, not a limiter fix** — the
KVM header pin is wired as `U11.IN2` only; `U11.OUT` feeds toward `U7.IN2` (the MAIN_5V
stage), and no conductive path exists from the Hub side back to the KVM pin regardless of
mux state. Residual exposure is the same `ILK,INx` leakage class quantified in Case B2
(500 µA worst-case / 1 µA typical) — not a new mechanism to re-verify. **PASS.**

---

## Case E — UNPOWERED-reverse bench gap (module AND KVM topology)

This is the one case that is **not** a SPICE transient run by its own nature — it is a
paper bound built on the same calibrated models, per the task's own framing ("state what
IS and is NOT specified... bound the risk on paper, not wave it away").

**What the TPS2121 datasheet does and does not specify**, checked directly against the
vendored PDF:
- Sec 7.5, **Fast Reverse Current Blocking (RCB)**: `IRCB` 0.2/1/2 A min/typ/max, `tRCB`
  10 µs — test condition stated only as `VOUT > VINx`; **device power/bias state is not
  stated**.
- Sec 9.3.6 (prose): *"Each channel has the always on reverse current blocking. If the
  output is forced above the selected input by VIRCB, the channel will switch off to stop
  the reverse current."* This is an **active, sense-then-act** description — a
  channel that must be "switched off" in response to a sensed condition implies a passive
  (unbiased) fallback would *not* already be blocking; if it were, there would be nothing
  for RCB to actively do.
- Sec 10.6, **Reverse Polarity Protection**: describes an external GND-side diode
  mitigation for a *mis-wired but live* supply — does not address a fully unbiased
  device either.

**Conclusion: the datasheet does not cover this operating point in either direction.**
This is exactly the gap the owner ruling already flagged as a first-article bench item;
this verification's job is to bound it, not resolve it.

**Worst-case paper bound** (OUT driven at 5V, assume the series back-to-back FET pair
degrades to a single forward-biased body diode — a common power-FET failure mode when
unbiased, `Vf≈0.6V` typical, no active current limiting since there is no bias to run the
current-limit loop):

| Path | Bound current | Polyfuse (F1/F5) I²t response |
|---|---|---|
| Module (F1, 750mA-hold) | 22.0 A (`(5−0.6)/(0.150+0.05)`) | **Would still trip, in ≈26.5 ms** (closed-form from the calibrated leaky-integrator model) |
| KVM (F5, 1.1A-hold) | 36.7 A (`(5−0.6)/(0.070+0.05)`) | **Would still trip, in ≈4.8 ms** |

**Best case** (unverified, no datasheet support either way): internal gate pull-downs
hold both series FETs fully off even with zero bias — a common load-switch design
pattern — in which case residual current is bounded only by ESD-network leakage
(nA-class).

**Verdict: REMAINS A BENCH GATE, not resolvable on paper — per the existing owner
ruling.** What this verification adds: even under the pessimistic worst-case assumption,
**F1/F5 provide a real backstop independent of the TPS2121's own unspecified behavior**
— a polyfuse's operation does not depend on the mux having any bias at all, and the
worst-case trip times (5-27 ms) are short enough to be a real, if not instant,
protective response. This does not replace the bench measurement; it bounds what is at
stake while waiting for it.

---

## Case F — OVP: cross-railed 12V-on-5VSB event

12 V fault against a 47k/10k OV1 divider (6.04V typ trip), swept two ways.

**Sweep 1 — fault edge rate** (the real rise time of a mis-wire/connector-mate event is
unstated anywhere in the design docs; swept 10-1000 ns to check sensitivity), OV1
response modeled at an assumed 2 µs (see below):

| Fault edge | V(OUT) peak | Duration above 6.5V (LP5907 abs-max) |
|---|---|---|
| 1000 ns | 12.0 V (full fault voltage reached) | 1.43 µs |
| 100 ns | 12.0 V | 1.51 µs |
| 10 ns | 12.0 V | 1.54 µs |

The exposure duration is **essentially independent of the fault edge rate** across this
whole range (1.43-1.54 µs) — `V(OUT)` tracks the fault almost instantaneously in every
case (the mux's RON is tiny relative to everything else), so the edge rate is not the
governing variable.

**Sweep 2 — OV1 response-time assumption** (the real governing variable; the datasheet
states only "turns off immediately" with no number, unlike RCB's explicit 10µs spec —
this is a flagged modeling assumption, not an extracted value):

| Assumed OV1 response τ | Duration above 6.5V |
|---|---|
| 1 µs | 0.77 µs |
| 2 µs (used above) | 1.51 µs |
| 5 µs | 3.71 µs |
| 10 µs (RCB's own documented order) | 7.38 µs |

**Verdict: MARGINAL — flagged loud, not smoothed over.** Across every response-time
assumption tried (1-10 µs, anchored at the low end on a fast comparator and at the high
end on RCB's own documented class), **the LP5907's 6.5V absolute-maximum input rating is
exceeded for roughly 0.8-7.4 µs during a fast 12V cross-rail fault**, because OV1 is
comparator-response-time-limited, not instantaneous, and the datasheet does not bound
that response time for OV1 specifically. This is a brief, µs-class excursion — most
silicon tolerates short abs-max excursions in practice, and the OV1 protection
unambiguously engages and pulls the rail back down afterward (confirmed in every run: the
mux correctly falls back to VBUS/IN2, matching the Case-mux smoke-test behavior) — but
"most parts tolerate it in practice" is not the same as "within the datasheet's own
spec," and no datasheet text authorizes any abs-max exposure duration. **Recommend
either an OV1-side RC bypass to slow the effective response window, or accepting this as
a documented, bounded, sub-10µs risk rather than an implicit zero.**

---

## Summary verdict table

| Case | Scenario | Verdict |
|---|---|---|
| A | Baseline unmitigated, caps-only | FAILS (confirmed ~27A peak; 3300µF alone crosses the 2.5A/1ms hard-trip with no fault at all) |
| A | Baseline unmitigated, 2Ω PSU fault | FAILS (sustained ~2.09A, just under the stated hard-trip threshold but unbounded in time and blows the charge budget in ~24µs regardless — "~400mC" corrected to window-dependent) |
| B1 | Mitigated, port-side inrush | PASS (82-1029× ILIM margin) — **loud note: raw charge (150µC) nominally exceeds the 50µC heuristic by design (local bulk >10µF), the current-based metric that actually matters passes overwhelmingly** |
| B2 | Mitigated, leakage into dead PSU | PASS (5µC worst-case at 10s dwell, ~6 orders under baseline) |
| B3 | Mitigated, F1 nuisance-trip | PASS (98.9% margin) |
| C | Reverse, old D2 | PASS (168nA-0.5mA, negligible) |
| C | Reverse, mitigated mux | PASS (500µA leakage bound, no OV1 trip at 5.5V) |
| D(i) | KVM unmitigated | FAILS (33.3A peak, worse than module baseline) |
| D(ii) | KVM mitigated, inrush | PASS (same margin structure as B1) |
| D(ii) | KVM mitigated, F5 nuisance-trip | PASS (94.8% margin) |
| D(iii) | KVM back-drive, before | FAILS (33.6A peak, 101µC — 2× over budget even at a small receiving cap) |
| D(iii) | KVM back-drive, after | PASS (architectural elimination, not a limiter) |
| E | Unpowered-reverse (module + KVM) | **UNRESOLVED — bench gate, per existing owner ruling.** Worst-case paper bound: F1/F5 still trip in 5-27ms even if the mux offers zero protection unbiased. |
| F | OVP cross-rail timing | **MARGINAL — flagged loud.** ~0.8-7.4µs LP5907 abs-max exposure depending on an unstated OV1 response-time assumption; OV1 does engage and recover in every run. |

## Loud list — marginal or failing items in the MITIGATED design (never smoothed over)

1. **Case B1**: the local-bulk inrush charge (150 µC) technically exceeds the 50 µC
   heuristic budget in raw coulombs — expected/by-design (>10µF bulk structurally
   requires this), current-based margin is 82-1029×, but do not report this as a clean
   "under 50µC" pass without this caveat.
2. **Case D(iii) before-mitigation**: even a small (20µF) host-side receiving cap sees
   101µC (2× over budget) from an unprotected back-drive — the after-mitigation state is
   architectural elimination and passes cleanly, but this quantifies how real the
   before-state risk was.
3. **Case E (unpowered reverse, both module and KVM topology)**: genuinely unresolved on
   paper. The datasheet does not specify this state in either direction. Worst-case bound
   shows the polyfuses still provide backstop protection (5-27ms trip), but this is not a
   substitute for the owner-ruled first-article bench measurement.
4. **Case F (OVP cross-rail timing)**: a real, non-zero, sub-10µs LP5907 abs-max
   exposure window exists and is bounded almost entirely by an *assumed* (not
   datasheet-specified) OV1 comparator response time. Not a hard fail, not a clean pass —
   flagged as a genuine open item.
5. **Methodology finding, not a case per se**: the repo's own "~10ms C_SS ramp,
   hub-proven" figure (used in `docs/owner-queue.md` and spec Section 2.9) could not be
   traced to a bench-measurement document in this repo, and the TPS2121 datasheet's own
   Table 9-1 instead predicts ≈125ms at C_SS=2.2µF — a ~12× discrepancy. Does not change
   any safety verdict here (both figures pass with large margin), but the repo's
   downstream "~50mA inrush" estimate is built on the 10ms figure and would revise to
   ≈1.2mA if the datasheet-table figure is the real one. Recommend a bench check.

## Sources

- `docs/owner-queue.md`, the three 2026-07-24 USB-backfeed rows (fault statement, ILIM
  ruling, KVM-path extension).
- `CEC-Platform-Ground-Truth-Spec.md`, Sections 2.9 and 6.14 (v1.6.0), Section 11 revision
  history entry for v1.6.0.
- `docs/usb-ingress-bom-delta-2026-07-24.md`, per-board part plan and strap-value
  derivations.
- TPS2120/TPS2121 datasheet, Texas Instruments SLVSEA3F (Aug 2018, rev. Aug 2020),
  vendored at `lib/datasheets/TPS2121RUXR.pdf`.
- 1206L Series PolySwitch Resettable PPTC datasheet, Littelfuse, Rev 02/25/19, fetched
  2026-07-24 from the LCSC mirror of the repo's own F1 line (LCSC C371166):
  `datasheet.lcsc.com/datasheet/pdf/90ef739ee6437e77b882388979caaf02.pdf`.
- SS32 THRU SS3200 Surface Mount Schottky Barrier Rectifier datasheet, MDD, Rev 2024A5,
  fetched 2026-07-24 from the LCSC mirror of the repo's own D2 line (LCSC C8678):
  `datasheet.lcsc.com/datasheet/pdf/dfa1ff67dea875d0135103ba9ada713a.pdf`.
- `docs/24pin-rev3-respin-2026-06-24.md`, NanoKVM current-draw citation (~0.5-1A, the
  original/base NanoKVM the J_KVM header was designed against).
