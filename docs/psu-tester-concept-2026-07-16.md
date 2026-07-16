# CEC PSU Tester (Pro / Max) — concept, realistic requirements, positioning

DRAFT (2026-07-16). The owner's earlier tester spec thread was NOT FOUND in
this repo family (all 16 remote refs, commit messages, session-handoff branch,
and agent memory swept — no "tester"/"dummy load"/"Chroma"/PSU-load vocabulary
anywhere), so this is a fresh spec-out from the owner's one-line brief plus
platform DNA. **Reconcile against the original thread when located** (likely a
local-machine session or chat); where this draft and that thread disagree, the
thread wins.

**Owner brief (2026-07-16, verbatim):** "the PSU tester specifically —
basically a DC load but fully done to ATX testing without bodging wires like
you would have to on Chroma gear."

## 1. The concept

An **ATX-native programmable DC load station**: the PSU under test plugs its
own harness straight in — 24-pin, EPS, PCIe 6+2, 12V-2x6 — into the same male
board headers a motherboard/GPU presents (all already vendored in `lib/`:
Mini-Fit 5566/5569 family, 87427, 45586, Molex 219116). No banana-jack bodges,
no crimped adapter looms, no floating grounds. Behind every connector: a
programmable sink, per-pin/per-rail CEC instrumentation, and an ATX-aware
sequencer that runs the whole test book a Chroma rig needs an operator and a
fixture-build to attempt.

Two variants, mapping 1:1 onto the platform's ruled sensing tiers:
- **Tester Pro** — characterization-class sensing (INA240/fast-SAR DNA, the
  Pro module front ends), full ATX conformance sequencing.
- **Tester Max** — adds the ruled **Max instrument channel** (20 MHz-class
  shared wideband path, AD9253-class fast ADC + FPGA): 20 MHz is exactly the
  industry ripple/noise measurement bandwidth, so the Max variant does
  spec-bandwidth ripple, transient microscopy, and the microarc/contact-ΔV
  research channel at the tester's own connectors.

## 2. What it must do (the test book)

- **Static loads**: per-rail CC/CR/CP, cross-load matrix (the classic
  min-12V/max-minor and inverse corners), 12V main + EPS×2 + PCIe×N +
  12VHPWR + 5V/3.3V (~20–25 A class) + 5VSB (3 A) + −12 V (0.3 A sink).
- **Dynamic/transient**: programmable load steps with GPU-class edges
  (~1–10 A/µs at the connector), PCIe CEM5.1 power-excursion profiles (2–3×
  bursts, ms class) — "replay a GPU" as a canned recipe.
- **ATX sequencing/timing**: PS_ON# drive, PWR_OK delay, T1/T2/T3 rail-rise
  timing/order/monotonicity, 5VSB behavior, µs-timestamped.
- **12VHPWR sideband**: present SENSE0/SENSE1 straps (command 150–600 W
  capability), read CARD_PWR_STABLE / CARD_CBL_PRES# — the module boards
  already tap exactly these.
- **Protections**: OCP staircase per rail (ramp to trip, record the point +
  recovery behavior), OPP, SCP (crowbar-FET short, standard but respected),
  UVP observation under overload. (No OVP *injection* — we don't force the
  PSU's outputs.)
- **Ripple/noise**: Max variant only, at the honest 20 MHz bandwidth with the
  spec's 0.1 µF/10 µF termination at the connector.
- **Hold-up + efficiency — honest scope**: proper hold-up needs AC-side
  interruption and efficiency needs AC metering. In-scope: a cheap
  **zero-cross-timed mains interrupter accessory** (relay/SSR box) for
  hold-up/dropout, and a **metering-inlet accessory** for indicative
  wall-referenced efficiency. Out of scope: a programmable AC source —
  certifiable 80PLUS/Cybenetics efficiency stays lab territory; say so
  plainly in marketing.

## 3. Realistic architecture

- **Load stage (the hard, expensive half): hybrid.** Switched resistive banks
  carry the coarse kW-class dissipation cheaply; a linear MOSFET vernier per
  channel provides fine CC regulation and the fast transient edges. Pure
  linear at 1.5 kW is Chroma-priced thermals; pure resistive can't do
  dynamics. Hybrid gets both at hobby-shop cost. Big heatsinks + fans +
  thermal supervision (NTC ladder, the platform's own parts).
- **Power class (owner decision)**: Pro ~850 W–1 kW total; Max ~1.6 kW
  (ATX 3.1 + 600 W 12VHPWR headroom). Same chassis/architecture, more banks.
- **Sensing = the module designs, reused.** Per-pin 12VHPWR array (the
  12vhpwr-standard/-pro front end verbatim), per-cable EPS/PCIe sensing,
  24-pin four-rail block. The tester is the first internal customer for the
  Pro module front ends.
- **Brains**: ESP32-P4 (+ FPGA on Max, the GW5A/ECP5 lane), USB to the SAME
  portable bench tool (shared fingerprint core), scripted test recipes with
  auto-generated pass/fail reports against ATX 3.1 limits. A CAN port so the
  tester joins the §6.10 FREEZE bus — it can co-capture with in-system CEC
  modules on one timeline.
- **The strategic sleeper — a ground-truth generator.** The tester can replay
  *labeled* fault profiles (imbalance, sag, excursion, dropout) into CEC
  modules and verify the fingerprint pipeline catches them. That
  hardware-in-the-loop replay is (a) our own module EOL/validation rig,
  (b) the §L/OQ-56 hold-up bench, and (c) a labeled-corpus factory for the
  fingerprint library — the labeling problem partially solved in hardware.

## 4. Positioning

There is a genuine hole in the market: below Chroma/SunMoon ATE (five to six
figures, generic terminals, fixture-building required) and above the $15 LED
"PSU testers" (presence/timing only, no load), there is essentially nothing.
Reviewers run six-figure stations; repair shops and boutique SIs run nothing.

- **Tester Pro — "the PSU test bench that speaks ATX."** Repair shops, system
  integrators, boutique builders, serious enthusiasts, budget reviewers.
  Plug the PSU's own cables in, press Run ATX 3.1 Suite, get a report with
  per-pin evidence. Target retail **~$1,500–2,000** (BOM driver = load stage
  + thermals; sensing is our own cheap DNA).
- **Tester Max — "the review-lab station."** Adds spec-bandwidth ripple, the
  instrument channel, excursion microscopy, microarc/contact research at the
  tester's connectors. PSU reviewers, OEM QA labs (as a Chroma *supplement*),
  and CEC's own lab. Target retail **~$2,500–4,000**.
- **Tier-honest claims** (platform rule): conformance *checks*, not safety
  certification; efficiency indicative-only without lab AC gear; ripple
  claims Max-only. The credibility of the consumer line rides on the tester
  line never overclaiming.
- **Synergy story**: the tester carries the same sensing, speaks to the same
  bench tool, and feeds the same fingerprint corpus — buying the tester makes
  every CEC module in the field smarter.

## 5. Owner decisions to open with

1. Power class per variant (850 W/1 kW Pro, 1.6 kW Max?) — drives the load
   stage + chassis + price.
2. Load-stage architecture confirm: hybrid resistive+linear (recommended) vs
   all-linear (cost) vs regenerative (complexity — recommend against v1).
3. Connector complement per variant (how many PCIe channels; SATA/Molex
   legacy loads at all?).
4. The two AC-side accessories (mains interrupter, metering inlet): in v1 or
   later?
5. Naming: "tester" is now reserved for this product line (bench-mode
   modules are "bench instruments" — docs/bench-mode-instrument-
   requirements-2026-07-16.md).
6. Where the original spec thread lives, so this draft can be reconciled.
