# Datasheet provenance audit — USB-backfeed package (2026-07-24)

**What this is.** A parameter-by-parameter re-verification of every device limit,
threshold, and curve cited in the 2026-07-24 USB-backfeed protection package, per
`docs/agent-working-principles.md` item 11 ("datasheet provenance is PER-PARAMETER,
never per-agent"): every number entering a simulation, margin calculation, or spec text
must trace to the vendored datasheet, file + section, AT THE POINT OF USE — not to an
upstream artifact that merely cites it. Triggered by finding that the known LP5907
6.5V→6.0V error (already caught in `docs/usb-ingress-bom-delta-2026-07-24.md`'s
CORRECTION section) had NOT actually been propagated into the other three artifacts or
into the live SPICE code — i.e. the per-artifact fix had not closed the per-parameter
gap the rule is about.

**Scope audited, 1:1 against primary sources:**
1. `scripts/sim/cec_backfeed_models.py` + `scripts/sim/cec_backfeed_cases.py` (the
   ngspice device models and the six verification cases).
2. `docs/spice-backfeed-verify-2026-07-24.md` (every numeric device claim).
3. `docs/psu-tester-failure-survey-2026-07-24.md` (every abs-max/rating cited per
   finding).
4. `docs/usb-ingress-bom-delta-2026-07-24.md` (strap-math inputs, part ratings).

**Method.** Every vendored datasheet was extracted with `pdftotext -layout` and grepped
for the exact table/section cited; two image-only vendor PDFs (no text layer) were read
directly via page-rendering. Six parts referenced in these artifacts had NO vendored
datasheet — `lib/datasheets/` was checked first, then each was fetched from a primary
source (manufacturer, or the exact LCSC-hosted mirror the artifacts themselves named)
and vendored in this pass (list below). Where a fetched datasheet changed a load-bearing
model parameter (the F5 polyfuse), the model was recalibrated and the affected SPICE
cases were **actually re-run** (inside `docker-routing-1`, the same ngspice 44.2/KLU
engine the original work used) rather than hand-estimated — the corrected numbers below
are real simulation output, not projections.

---

## Verdict counts

| Verdict | Count |
|---|---|
| CONFIRMED (matches vendored/fetched primary source exactly) | 23 |
| WRONG — fixed this pass | 4 |
| FLAGGED FINDING — surfaced, not silently resolved (design trade-off, not a lookup) | 1 |
| Re-verified from the task's "known already" list — confirmed still accurate | 2 |
| Correctly labeled ASSUMPTION already (no datasheet exists to check against) | 6 |
| N/A — no numeric claim actually made anywhere in scope | 1 |

Most consequential first, the four WRONG items:

1. **LP5907 abs-max, 6.5V used where the datasheet says 6.0V** — the fix was recorded in
   one artifact's correction note but not propagated to the other two docs (5 further
   prose occurrences) OR into the live sim code, where `cec_backfeed_cases.py` Case F had
   a hardcoded `6.5` threshold actually driving simulated results, not just prose.
2. **F5 (KVM) polyfuse trip-time calibration used a Littelfuse 1206L110TH stand-in's
   numbers** where the real populated part (FUZETEC FSMD110-16-1206R) is now fetchable —
   a 3× error in the calibrated `E_thresh` (6.4 vs the real 19.2 A²s).
3. **TJA1051T/3 CAN bus-pin voltage rating stated as "±42V-class"**; the real vendored
   datasheet gives ±58V exactly, no "42V" figure appears anywhere in it.
4. **ESP32 ADC clamp-current arithmetic (12VHPWR OV scenario) understated ~5.7×** (13µA
   vs the correct ~74µA) — a Thevenin-resistance omission, not a datasheet error.

None of the four changes verdicts (FAIL stays FAIL, PASS stays PASS everywhere), but all
four are real numbers that were wrong and are now fixed in place.

---

## Part 1 — `scripts/sim/cec_backfeed_models.py` / `cec_backfeed_cases.py`

| # | Parameter | Value used | Primary source | Verdict |
|---|---|---|---|---|
| 1 | TPS2121 `RON` | 60 mΩ (56 typ/70 max, 25°C, `IOUT=-200mA`) | `TPS2121RUXR.pdf` Sec 7.5 Electrical Characteristics | **CONFIRMED** — table reads 56/70mΩ (25°C) exactly under `VPRI>VREF, VINx≥5.0V` |
| 2 | TPS2121 ILIM law | `I_LM = 65.2 / R_ILM^0.861` | `TPS2121RUXR.pdf` Sec 9.3.2 Eq. (2) | **CONFIRMED** verbatim; cross-checked against the datasheet's own tabulated points: 44.2kΩ→2.498A (table: 2.5A typ), 80kΩ→1.499A (table: 1.5A typ), 27kΩ→3.82A (hub), 20kΩ→4.94A (24-pin), 100kΩ→1.237A (this package's ~1A-class ruling) — all recomputed independently in Python and matched |
| 3 | TPS2121 `R_ILM` recommended window | 18–100 kΩ | `TPS2121RUXR.pdf` Sec 9.3.2 prose ("RILM is in kΩ and between 18 kΩ to 100 kΩ") | **CONFIRMED** verbatim |
| 4 | TPS2121 `t_FSW` / `t_SW` | 5µs / 100µs | `TPS2121RUXR.pdf` Sec 7.5 (Switchover Time / Fast Switchover Time rows) | **CONFIRMED** (task's "known already" item, re-verified) — table: tSW typ=100µs (`CP2 or SEL < VREF`), tFSW typ=5µs (`CP2 ≥ VREF`, TPS2121 only) |
| 5 | TPS2121 `VREF` | 1.01/1.06/1.10 V min/typ/max | `TPS2121RUXR.pdf` Sec 7.5 (Rising) | **CONFIRMED** exactly |
| 6 | TPS2121 `IRCB` / `VRCB` / `tRCB` | 0.2/1/2A; 0/25/50mV; 10µs | `TPS2121RUXR.pdf` Sec 7.5 (Fast Reverse Current Blocking) | **CONFIRMED** exactly |
| 7 | TPS2121 `ILK,INx` | 1µA (25°C) / 500µA MAX (−40…125°C) | `TPS2121RUXR.pdf` Sec 7.5 | **CONFIRMED with a nuance**: the table gives MIN/MAX pairs, not a labeled "typ", at 25°C (±1µA), and the 500µA MAX figure specifically belongs to the `\|VINx−VOUT\|≤22V` condition row (the `≤5V` condition's own −40…125°C MAX is only ±80µA). Using the 500µA figure as a blanket conservative worst-case bound is a legitimate, disclosed simplification, not an error — actual differentials in these cases range 0.5–12V, straddling both condition bands |
| 8 | TPS2121 Table 9-1 (Slew Rate vs `CSS`) | 100nF→780V/s, 1µF→88V/s, 10µF→8.8V/s (VIN=5V) | `TPS2121RUXR.pdf` Sec 9.3.1.1 Table 9-1 | **CONFIRMED** exactly (task's "known already" item, re-verified) — the ≈125ms 0→5V ramp at `C_SS=2.2µF` (log-linear 1/C interpolation between the 1µF/10µF points, which ARE exactly 10:1) is correct arithmetic: `88/2.2=40V/s`, `5V/40V/s=0.125s` |
| 9 | Pin map (VQFN-HR-12) | 1/8=OUT, 2=IN2, 3=CP2, 4=OV2, 5=OV1, 6=PR1, 7=IN1, 9=ST, 10=ILIM, 11=SS, 12=GND | `TPS2121RUXR.pdf` Sec 6 Pin Functions | **CONFIRMED** exactly |
| 10 | TPS2121 abs-max | IN1/IN2/OUT: −0.3 to 24V; OV1/OV2/PRI/SEL/ST: −0.3 to 6V | `TPS2121RUXR.pdf` Sec 7.1 | **CONFIRMED** exactly |
| 11 | SS34 `VF` @ `IF=3.0A`, 25°C | 0.55V max (SS32–SS35 group) | fetched+vendored `MDD_SS32-SS3200_C8678.pdf` (real SS32-thru-SS3200 datasheet, LCSC C8678, Rev2024A5) | **CONFIRMED** exactly — table row groups SS32/33/34/35 under the 0.55V column; SS34 self-test re-run this pass gives VF=0.5501V @ 3.0A (unaffected by any edit) |
| 12 | SS34 `IR` @ `VR=40V`(rated), 25°C | 0.5 mA | same, MDD SS32-SS3200 table | **CONFIRMED** exactly |
| 13 | SS34 `VRRM` | 40V | same | **CONFIRMED** exactly |
| 14 | SS34 `RS`=0.025Ω, `N`=1.10 | engineering estimate | *(not a datasheet extraction — labeled as such in the code)* | **CONFIRMED-AS-LABELED**: the datasheet gives only one forward point, not a curve; these are disclosed fit parameters, not claimed extractions |
| 15 | F1 polyfuse (1206L075/16WR) | Ihold .75A/Itrip 1.5A/Vmax 16V/MaxTimeToTrip 8.00A→0.20s/Rmin .090Ω/R1max .290Ω | fetched+vendored `Littelfuse_1206L_C371166.pdf` (the EXACT LCSC-mirror URL the file's own docstring already cited, now actually vendored rather than link-only) | **CONFIRMED** exactly, every field |
| 16 | F1 `Rcold`=0.150Ω | engineering estimate between Rmin/R1max | *(labeled as such)* | **CONFIRMED-AS-LABELED** — no "typ" row exists in the datasheet (only Rmin/R1max are tabulated; confirmed by reading the datasheet's own column legend) |
| 17 | **F5 polyfuse (was: 1206L110TH stand-in)** | *was* Ihold 1.10A/Itrip 2.2A/Vmax 8V/MaxTimeToTrip 8.00A→**0.10s**/Rmin .040Ω/R1max **.210Ω** | *was cited only as a "same-class stand-in," explicitly because the real part "has no vendored curve available"* | **WRONG-then-FIXED** — see the dedicated section below |
| 18 | `EFUSE_HARD_TRIP_A`/`_S` = 2.5A / 1ms | host eFuse fast-trip | *"per task spec"* — no specific host eFuse IC named or vendored (the host is an arbitrary downstream PC CEC does not control) | **CONFIRMED-AS-LABELED** — this is an explicit, disclosed task-given modeling assumption, not presented as a datasheet extraction. Plausible order-of-magnitude for a generic USB Type-C eFuse's OCP-fast-trip class, but intentionally not tied to one part |
| 19 | `EFUSE_BUDGET_C` = 50µC | "~10µF×5V heuristic" | **researched this pass**: USB 2.0 specification, downstream port inrush-current limit — max permissible bulk capacitance without a controlled soft-start is 10µF (equivalent to a 44Ω parallel-load inrush condition) | **CONFIRMED — traces to a real USB-IF spec provision**, not folklore. `Q=CV=10µF×5V=50µC` follows directly. Upgraded from "heuristic" to "spec-traceable" in this audit |
| 20 | `RSRC_USB` = 0.12Ω | USB 5V incl. cable | *"per task spec"* | **CONFIRMED-AS-LABELED** — a generic cable+contact-resistance system assumption, not a single part's datasheet figure; already honestly framed |
| 21 | OV1 response time (`ov1_tau_s`, 1–10µs sweep) | modeling assumption | *(labeled as such — the datasheet states only "turns off immediately" for OV1, no number, unlike RCB's explicit 10µs)* | **CONFIRMED-AS-LABELED** |
| 22 | Fault edge rate (10–1000ns sweep) | modeling assumption | *(labeled as such — unstated anywhere in the design docs)* | **CONFIRMED-AS-LABELED** |
| 23 | `LP5907_ABSMAX_V` (Case F threshold) | *was* 6.5 (hardcoded, live in the sim, not just prose) | `LP5907.pdf` Sec 5.1 | **WRONG-then-FIXED** — see dedicated section below |

### F5 polyfuse — the real part's datasheet was found; the model is recalibrated

The module docstring and `docs/spice-backfeed-verify-2026-07-24.md` both explicitly
flagged F5 (the hub's KVM-stage polyfuse) as modeled on a Littelfuse 1206L110TH
**stand-in**, because the actually-populated part — FUZETEC FSMD110-16-1206R, LCSC
C5707763 — "has no vendored curve available." That framing was honest at the time, but
per this rule's own logic ("fetching one and vendoring it... is in scope"), the right
move on an audit pass is to go get it, not just re-confirm the honesty of the caveat.

Fetched (LCSC's own hosted mirror for C5707763) and vendored at
`lib/datasheets/FUZETEC_FSMD110-16-1206R_C5707763.pdf` (Fuzetec Product Specification
PQ18-01ER Rev 1, 2021-03-25). The `FSMD110-16-1206R` row:

| Field | Stand-in (1206L110TH) value used | **Real part's actual value** |
|---|---|---|
| Ihold | 1.10 A | 1.10 A (same) |
| Itrip | 2.20 A | 2.20 A (same) |
| Vmax | 8 V | **16 V** |
| Max-Time-to-Trip | 8.00 A → **0.10 s** | 8.00 A → **0.30 s** |
| Rmin | 0.040 Ω | 0.040 Ω (same) |
| R1max | **0.210 Ω** | **0.180 Ω** |

Ihold/Itrip/Rmin happened to coincide (same PPTC generation/class — the reason the
stand-in was chosen in the first place was reasonable). The trip-time anchor is the
consequential difference: `E_thresh = Itest²×Ttest` is **3× larger** for the real part
(19.2 A²s vs 6.4 A²s), and `τ = E_thresh/Ihold²` is correspondingly 3× larger (15.87s vs
5.29s).

**Fixed:** `scripts/sim/cec_backfeed_models.py`'s `POLYFUSE_PARAMS` dict key renamed
`F5_1206L110TH` → `F5_FSMD110_16_1206R` (both call sites in `cec_backfeed_cases.py`
updated) with the real Ttest/R1max, a dated correction comment, and the retired
values preserved in the comment for traceability. **Re-ran the actual simulations**
(ngspice, not hand-estimated) for every F5-dependent result:

| Result | Old (stand-in) | **New (real part, re-simulated this pass)** |
|---|---|---|
| F5 constant-8A self-test trip time | t=0.101s (target 0.10s) | **t=0.303s** (target 0.30s) — ngspice-verified, not closed-form-only |
| Case D(ii) nuisance-trip: peak energy / margin | 5.2% of threshold / 94.8% margin | **2.3% of threshold / 97.7% margin** (still PASS, more margin) |
| Case E worst-case bound: F5 trip time | ≈4.8 ms | **≈14.3 ms** (bound current itself, 36.7A, is unchanged — it depends only on `Rcold`, unaffected) |

No verdict flips: the real part is *more* energy-tolerant than the stand-in modeled, so
the nuisance-trip margin only widens, and the worst-case-bound backstop still trips, just
~3× slower than previously stated (14ms vs the previously-reported 4.8ms) — still fast
enough to matter, and still independent of the TPS2121's own unspecified unbiased-reverse
behavior, per Case E's own framing.

### LP5907 abs-max — the fix existed in one artifact but had not propagated

`docs/usb-ingress-bom-delta-2026-07-24.md` already carries a dated CORRECTION section
(2026-07-24) stating the real LP5907 abs-max V(IN) is 6.0V (`LP5907.pdf` Sec 5.1: −0.3 to
6V, no transient/time-dimension carve-out — **re-confirmed this pass, exact match**), not
the 6.5V the failure survey and SPICE Case F had assumed. What that correction note did
**not** do is fix the other two places the wrong number actually lived:

- **`scripts/sim/cec_backfeed_cases.py`**: Case F had `6.5` hardcoded as the threshold
  passed to `duration_above(data, "v(out)", 6.5)` in three places — this is the number
  that actually drove the simulated "duration above abs-max" results, not merely
  descriptive prose. **Fixed**: added a module-level `LP5907_ABSMAX_V = 6.0` constant
  with a dated correction comment, replaced all three call sites, renamed the two
  affected result-dict keys (`duration_above_6p5V_s`→`duration_above_absmax_s`, etc. —
  confirmed no other file referenced the old key names), and **re-ran Case F** to get
  real corrected numbers (below).
- **`docs/spice-backfeed-verify-2026-07-24.md`**: five further prose/table occurrences of
  "6.5V" (Case F's two sweep tables + verdict prose, the summary table, the loud list,
  and one in Case C's conclusion) — all now corrected to 6.0V with inline dated notes,
  plus a new correction paragraph at the top of the Case F section.
- **`docs/psu-tester-failure-survey-2026-07-24.md`**: two further occurrences (the 24-pin
  U5/U6 row and the hub J_PWR row) — corrected, and the U5/U6 row's downstream verdict
  language ("was HIGH, → LOW post-v1.6.0") revised, because the corrected 6.0V abs-max
  means the v1.6.0 mitigation's own 6.04V typical OV1 trip point does not clearly clear
  it — see below.

Case F re-run with the corrected 6.0V threshold (real ngspice output, not projected):

| Sweep 1 (fault edge, τ=2µs) | Duration above 6.5V (wrong) | **Duration above 6.0V (corrected)** |
|---|---|---|
| 1000 ns | 1.43 µs | **1.53 µs** |
| 100 ns | 1.51 µs | **1.54 µs** |
| 10 ns | 1.54 µs | **1.57 µs** |

| Sweep 2 (OV1 response τ, 100ns edge) | Duration above 6.5V (wrong) | **Duration above 6.0V (corrected)** |
|---|---|---|
| 1 µs | 0.77 µs | **0.81 µs** |
| 2 µs | 1.51 µs | **1.54 µs** |
| 5 µs | 3.71 µs | **3.75 µs** |
| 10 µs | 7.38 µs | **7.42 µs** |

The lower threshold is crossed slightly earlier during the rise, so every exposure window
grows slightly — the finding gets marginally worse, not better, and the qualitative
verdict (MARGINAL, flagged loud) is unchanged. The materially new finding is separate:
the OV1 divider's own **typical** trip point (6.04V) now sits at/above the corrected
6.0V abs-max even at DC, before any comparator response-time excursion is considered —
this is a bigger deal than the µs-class timing exposure and is captured in the
`usb-ingress-bom-delta` addendum below.

---

## Part 2 — `docs/psu-tester-failure-survey-2026-07-24.md`

| # | Claim | Value used | Primary source | Verdict |
|---|---|---|---|---|
| 24 | INA238 bus-pin input range | 85V-input part | `INA238.pdf` Sec 5.1: `VIN+,VIN-` common-mode −0.3 to 85V | **CONFIRMED** exactly |
| 25 | 24-pin U5 TPS2121 abs-max/recommended | 22V part, abs max 24V | `TPS2121RUXR.pdf` Sec 7.1/7.3 (recommended 2.8–22V, abs-max −0.3 to 24V) | **CONFIRMED** exactly |
| 26 | LP5907 abs-max (U5/U6 row, and the hub J_PWR row) | 6.5V | `LP5907.pdf` Sec 5.1 | **WRONG — FIXED** to 6.0V (both occurrences); see LP5907 section above |
| 27 | INA181 common-mode abs-max | ≈26V, tagged `[R]` "re-verify" | `INA181A2IDBVR.pdf` Sec 6.1: differential/common-mode ±26V | **CONFIRMED** exactly — hedge resolved, re-tagged `[M]` |
| 28 | 12VHPWR rail-divider node voltage at 24V insult | 4.2V (47k/10k divider) | direct arithmetic: `24×10/57=4.21V` | **CONFIRMED** arithmetic |
| 29 | ESP ADC abs-max (for the above) | ≈3.6V, tagged `[R]` | fetched+vendored real `ESP32-S3-MINI-1.pdf` (the actual populated part, not the WROOM-1 proxy previously the only option) Table 6-1: `VDD33` −0.3 to 3.6V | **CONFIRMED at the general-pad level** — neither the MINI-1 nor the WROOM-1 module datasheet states a distinct "ADC input absolute maximum" separate from the general `VDD33` supply abs-max; using it as the pad ceiling is standard ESP32 engineering practice but is an inference, not a literally-quotable "ADC abs-max" table row. Flagged as such, not treated as a clean 1:1 citation |
| 30 | ESP ADC clamp current at the 24V insult | **13 µA** | derived from #28/#29: `(4.2−3.6)/47k` | **WRONG — FIXED**: this uses only the divider's top series resistor. The physically correct figure is the excess voltage over the loaded divider's **Thevenin resistance** (`47k‖10k=8.25kΩ`, not 47kΩ alone): `(4.21−3.6)/8.25k ≈ 74µA` — **~5.7× higher** than stated. Still leakage-class relative to what an ESP32 pad ESD/clamp structure survives, and the recommended mitigation (add a 10k series R, the 24-pin's R76 pattern) is unaffected either way, but the number itself was wrong. Fixed in both places it appeared (§2.1 table row and the ranked-findings §3 item 7 restatement) |
| 31 | Hub D8/D9 TVS part | SMAJ5.0A | fetched+vendored `MDD_SMAJ5.0A_C113952.pdf` (LCSC C113952, the ACTUAL real-board part, confirmed by reading `beta/hub-standard-rev2/hub-standard-rev2.kicad_sch`) | **CONFIRMED**: `VRWM`(standoff)=5.0V, `VBR`=6.40–7.00V, `VC`@`IPP`=9.2V, steady-state `PM(AV)`=3.3W. Directly supports the survey's "sustained 12V... sits above the TVS standoff → TVS burns out" claim — a sustained fault current vastly exceeds the 3.3W steady-state rating |
| 32 | TJA1051T/3 CAN bus-pin voltage rating | "±42 V-class" | `TJA1051.pdf` Table 5 "Limiting values": `Vx` on CANH/CANL = −58/+58V | **WRONG — FIXED** to ±58V. No "42V" figure appears anywhere in the datasheet (checked via full-text grep of the extracted PDF); the real part is meaningfully more robust than stated. Directionally-safe error (understated the margin) but still a wrong number |
| 33 | Hub F1–F4 per-port PTC | "500 mA hold... 6V rated" (schematic property note) | fetched+vendored `SMD0805-050_PTC_C46640983.pdf` (LCSC C46640983, the real board part, MPN SMD0805-050-6 confirmed from the schematic) | **CONFIRMED** exactly: Ihold=0.5A, Itrip=1.0A, Vmax=6.0V |
| 34 | Bourns CSS2H-2512R-L500x shunt power rating | "~6 W-class rating (verify exact Bourns figure)" | `Bourns_CSS2H-2512.pdf` (already vendored): CSS2H-2512R-L500x row = "0.5 mΩ / 6 W" | **CONFIRMED** — exactly 6W, not merely "~6W-class". Hedge resolved, re-tagged `[M]` |
| 35 | Shunt I²R at fault (EPS, 150A) | 11.3 W | `0.5mΩ × 150² = 11.25W` | **CONFIRMED** arithmetic, cross-checked against #34 |
| 36 | TE 63969-1 FASTON receptacle joint rating | "22.9 A/125% margin policy" (pre-existing, from an earlier CLAUDE.md-documented session, restated here) | `TE_108-1706_FASTON_PCB_receptacle_prodspec.pdf` — an image-only PDF (no text layer; `pdftotext` returns empty), read via direct page rendering | **CONFIRMED**: Figure 4 "Current Carrying Capability" explicitly labels the flat-region base rated current as "22.9 amperes"; Sec 3.3/3.5 confirm the 30°C-max-temperature-rise qualification criterion the figure is measured against. Out of this audit's primary 2026-07-24 scope (established earlier), verified anyway since the task named "connector ratings" explicitly |
| — | INA240 abs-max | *(no numeric claim made anywhere in the audited scope)* | — | **N/A** — INA240 is mentioned only structurally (REF-grounded/unidirectional, refdes) in all four artifacts; no voltage or current rating is asserted about it anywhere, so there is nothing to trace. (No INA240 datasheet is vendored either, but since no claim references one, nothing needed fetching.) |

---

## Part 3 — `docs/usb-ingress-bom-delta-2026-07-24.md`

| # | Claim | Value used | Primary source | Verdict |
|---|---|---|---|---|
| 37 | LP5907 abs-max (this doc's own CORRECTION section) | 6.0V | `LP5907.pdf` Sec 5.1 | **CONFIRMED** — this was the one artifact that already had it right; re-verified, exact match |
| 38 | OV1 divider (47k/10k) typical trip | 6.04V | `V_trip=VREF,typ×(Rt+Rb)/Rb = 1.06×57/10` | **CONFIRMED** arithmetic (=6.042V) |
| 39 | PR1 divider (100k/33k) typical valid floor | 4.27V | `1.06×133/33` | **CONFIRMED** arithmetic (=4.272V) |
| 40 | OV1 pin voltage at a 22V insult (47k/10k) | 3.86V, "< the pin's 5.5V recommended max" | `22×10/57` | **CONFIRMED** arithmetic (=3.860V); recommended-max figure cross-checked against `TPS2121RUXR.pdf` Sec 7.3 (`OV1,OV2` recommended 0–5.5V) — also **CONFIRMED** |
| 41 | Retune candidates 47k/11k→5.59V, 43k/10k→5.62V | typical trip points | same `V_trip` formula | **CONFIRMED** arithmetic (5.589V, 5.618V) |
| 42 | **Retune candidates' worst-case tolerance band** | *(not computed in the original correction note — only the typical point was checked against the 5.25V/6.0V window)* | full VREF(1.01–1.10V)+±1%-resistor stack, computed this pass | **NEW FINDING, surfaced as an addendum, not silently resolved** — see below |
| 43 | ILIM/OV1/PR1 pin abs-max figures reused from Sec 2 | 24V (IN/OUT), 6V (OV/PR pins) | `TPS2121RUXR.pdf` Sec 7.1 | **CONFIRMED** (same table as #10) |

### The OV1 retune worst-case tolerance band — flagged, not picked

The existing CORRECTION section proposes two candidate resistor pairs (47k/11k or
43k/10k) to move the OV1 trip point below the corrected 6.0V LP5907 ceiling, checking
only the **typical** trip voltage against the 5.25V (5V+5% normal max) / 6.0V (abs-max)
window. Running the same check against the **worst-case** tolerance stack (TPS2121's own
`VREF` band, 1.01–1.10V, against ±1% resistors both directions) surfaces a problem
neither candidate cleanly resolves:

| Candidate | Typical trip | Worst-case band | Verdict |
|---|---|---|---|
| 47k/11k | 5.589V | **5.24V – 5.90V** | LOW end (5.24V) sits *below* 5.25V — a nuisance-trip risk on a completely in-spec 5VSB rail in the worst corner |
| 43k/10k | 5.618V | **5.27V – 5.93V** | Clears 5.25V, but by only ~0.3% — thin |

Both candidates leave under ~1.5% of headroom somewhere in the stack, on a divider that
only has ~13% of span (5.25–6.0V) to begin with at ±5%-class `VREF` accuracy. This is a
genuine engineering trade-off (tighten to 0.1% resistors — the platform already stocks a
0.1% Yageo line for the 12VHPWR rail divider, ~$0.01 delta — or lean harder on the
existing "add an output-side zener clamp" item as the real backstop rather than the OV1
trip point alone), not a datasheet lookup, so it was **added as a dated addendum to the
existing CORRECTION section**, with both directions named and neither picked — consistent
with this repo's standing "surface it, don't assume it" rule for design decisions, per
`CLAUDE.md`'s open-questions doctrine extended sensibly here.

---

## Datasheets newly vendored this pass

None of these six parts had a vendored datasheet before this audit; all six are now at
`lib/datasheets/`, fetched from a primary source (manufacturer site where reachable,
otherwise the exact LCSC-hosted mirror for the real populated LCSC part number):

| File | Part | Why it was needed |
|---|---|---|
| `MDD_SS32-SS3200_C8678.pdf` | SS34 Schottky (D2, LCSC C8678) | Backs the SPICE model's `VF`/`IR`/`VRRM` anchors — previously cited by URL only, never vendored |
| `Littelfuse_1206L_C371166.pdf` | F1 polyfuse family sheet (LCSC C371166) | Backs the F1 I²t calibration — previously cited by URL only |
| `FUZETEC_FSMD110-16-1206R_C5707763.pdf` | F5 polyfuse, the REAL populated part (LCSC C5707763) | Previously said to have "no vendored curve available"; found and fetched this pass, and used to recalibrate the model (see above) — this is the one fetch that changed a load-bearing number |
| `MDD_SMAJ5.0A_C113952.pdf` | Hub D8/D9 power-entry TVS (LCSC C113952) | The failure survey cited SMAJ5.0A generically; this is the datasheet for the actual real-board part |
| `SMD0805-050_PTC_C46640983.pdf` | Hub F1–F4 per-port PTC (LCSC C46640983) | Confirms the schematic's own "500mA hold, 6V rated" note against a real datasheet |
| `ESP32-S3-MINI-1.pdf` | The real populated MCU (12VHPWR-Standard, EPS, PCIe, 24-pin) | Previously only the WROOM-1 and C6-MINI-1 module datasheets were vendored; the actual MINI-1 module's own datasheet is now available for the ADC/pad-voltage claim |

---

## Files changed this pass

- `scripts/sim/cec_backfeed_models.py` — F5 `POLYFUSE_PARAMS` key renamed and
  recalibrated on the real FUZETEC datasheet; module docstring corrected.
- `scripts/sim/cec_backfeed_cases.py` — `LP5907_ABSMAX_V` constant added (was a bare
  `6.5` literal in three places) and set to the correct 6.0V; F5 key references updated
  to match the model-file rename.
- `docs/spice-backfeed-verify-2026-07-24.md` — F5 polyfuse table/prose, Case D(ii)
  nuisance result, Case E bound table, Case F (both sweep tables + verdict prose), Case C
  conclusion, summary verdict table, loud-list items 3–4, and the Sources section all
  corrected with dated inline notes; re-run numbers substituted for projected ones.
- `docs/psu-tester-failure-survey-2026-07-24.md` — LP5907 abs-max (2 rows), TJA1051
  bus-pin rating, ESP-ADC clamp current (2 occurrences), CSS2H-2512 and INA181 hedges
  resolved; a provenance-audit pointer added near the top.
- `docs/usb-ingress-bom-delta-2026-07-24.md` — addendum appended to the existing
  CORRECTION section (worst-case tolerance-band finding; propagation confirmation).
- `lib/datasheets/` — six new vendored PDFs (listed above).
- `docs/datasheet-provenance-audit-2026-07-24.md` — this document.

No schematics, PCBs, golden fixtures, or generated CSVs were touched, per task
instruction. No open question was resolved by assumption: the one genuine design
trade-off found (the OV1 retune's worst-case tolerance band) was surfaced with named
options, not picked.
