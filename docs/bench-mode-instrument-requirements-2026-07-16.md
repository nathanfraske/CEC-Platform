# Pro & Max bench instruments — realistic requirements + positioning (2026-07-16)

Consolidation of the ruled bench-mode / Max-instrument material into one
requirements + positioning view (2026-07-16 session). NAMING NOTE: the owner's
"Pro and Max tester" means the PSU TESTER (ATX-native DC load station) — a SEPARATE product whose
canonical spec is docs/psu-tester-exploration-2026-07-14.md (branch
claude/pipeline-consolidation; owner tier ruling §6) with the reconciliation
record in docs/psu-tester-concept-2026-07-16.md. This
document covers the bench-mode INSTRUMENT posture of the Pro/Max modules,
which the PSU tester reuses as its sensing DNA.
STATUS: working analysis + decision list for owner ratification. Nothing here
alters a LOCKED decision; the Max architecture cited is the owner-ruled
2026-06-11/07-05/07-06 stack awaiting its Task-13 spec application.

## 0. Where this material lives (branch-hunt result)

Measured (all 16 remote refs swept, 2026-07-16): **everything below is
already on main** — it landed via the 2026-07-05/06 bench-mode thread:

- `docs/bench-mode-exploration-2026-07-05.md` — Pro/Max bench mode (Paths A/B,
  the delta list, PROPOSED spec text)
- `docs/bench-mode-max-stack-2026-07-05.md` — the RULED Max stack ("I agree
  with everything here and it can be ruled as such", 2026-07-05)
- `docs/research/max-instrument-channel-decision-2026-06-11.md` — the ruled
  instrument channel + the Z(f) jig / bench protocol
- `docs/max-part-selection-2026-07-05.md` — part picks (study, partly ratified)
- `docs/pricing-study-2026-07-05.md` — PRO BENCH $369 / 12VHPWR-Pro $329 /
  Max reserved band $499–599

The genuinely un-landed piece is **Task 13** (root FOLLOWUPS 2026-07-05): fold
the ruled architecture + part picks into spec §6.11 + a Max-hub row +
bench-mode text. Its gates (a) tab-form hunt and (b) pigtail form are resolved;
it waits on (c) part-pick ratification. No open PR carries any of this.

## 1. What a bench instrument is, per tier

**Bench instrument = a Pro or Max module placed in bench mode + the portable
bench tool.** Bench mode is a firmware-selectable full-fidelity posture (draft spec
text already exists, PROPOSED, in bench-mode-exploration §6) — not a separate
board. The sellable SKUs are therefore the modules themselves plus
software; the only instrument-specific *hardware* is on the Max side (the
instrumented pigtail + the internal cal jig).

Distinct thing, keep the names apart: the **step-load jig** (MOSFET-switched
resistive step; "cheap to build, no precision required because the board
measures its own step") is the internal factory/bring-up cal fixture — one
build serves Z(f) extraction and the drift benchmark. Not a customer product
today; productizing it is a someday-option, not in scope.

## 2. Pro bench instrument — what it realistically needs

**The honest gap: the Pro module itself.** `modules/12vhpwr-pro` is a 4-symbol
DRAFT stub (RJ-45 only). "Mostly a firmware/host gate, not new hardware" is
true of the *architecture*, but the board must be designed: ESP32-P4, 6×
INA240A3 on the locked 1 mΩ per-pin shunts (12vhpwr-standard front-end DNA),
LTC2358-18 + REF3033, RS-485 PHY, 12V-2x6 in + captive pigtail, USB-C on the
P4's native USB-HS. No FPGA, no T1 — deliberately.

**Rates, tier-honest (verified numbers):**
- In-system (Path A): 50 kHz × 6 ch design point ≈ 900 kB/s over RS-485 → Hub
  Pro → USB-HS. Continuous already by design; no flow control on RS-485.
- Bench-direct (Path B, module's own USB-C): LTC2358-18 native ceiling 250
  ksps/ch at 6 ch ≈ 4.5 MB/s ≈ ~11 % of one USB-HS link — with native bulk
  flow control (the lossless-firehose transport RS-485 is not).
- Headline: **"50 kHz through the system, 250 kHz on the bench."**

**RECOMMENDATION (the one tier ruling this needs):** extend §6.14 Path B to
Pro/Max — module-direct USB-C IS the Pro bench posture. It takes Hub Pro off
the bench posture's critical path entirely, sidesteps the RS-485-PHY and P4
UART-ceiling questions (OQ-5), and matches the portable-tool positioning. The
in-system PRO BENCH bundle (Hub Pro + module, $369) stays the *system* play;
the standalone bench instrument is module + software at $329.

**Firmware (new, none exists — proto/12vhpwr is the Max rig):** P4 app on the
shared components; a genuinely new continuous acquisition mode (small FIFO,
not the §6.10 pre-roll ring); framing + timestamps + sequence numbers for
drop detection; bench-mode gate + arbitration (bench session visible to
AllMyStuff); §6.14 CDC + the HID sensor-collection identity per the 2026-07-06
host-presentation ruling.

**Host:** bench tool v1 on the shared fingerprint core (see
`firmware/docs/host-data-path-fingerprinting-2026-07-16.md`), plus the piece
the delta list flags as designed nowhere: a capture sink that sustains
4.5 MB/s to disk with a defined file/frame format.

**Thermal/power: non-issue** (LTC2358-18 is 219 mW typ at full rate — already
the board's design budget). EPS/PCIe Pro variants: don't exist; their bench
rate swings 7–13× on OQ-58 (LTC2358-18 vs ADS131M08) — bench capability is an
explicit input to that pick, not an afterthought.

## 3. Max instrument — what it realistically needs

The ruled two-layer architecture on the existing 1 mΩ per-pin shunts:

- **Slow/precision plane:** all 6 channels → AD7606B (recommended; 8-ch
  true-simultaneous 16-bit, 800 ksps/ch, LCSC-native ~$15) → FPGA ingest +
  decimation. Production target **~80–100 kHz** (hard caps = INA240 clean BW
  and the shunt's ~79.6 kHz inductive corner — physics, not budget).
- **Fast instrument channel (shared, trigger-driven, never continuous):**
  **4 differential inputs** — deconvolved shunt tap, PCB Rogowski coil,
  rail-V, and connector-ΔV — into an AD9253-class quad 14-bit 80 MS/s ADC
  (~$42; OQ-17's A1/A2 formally open, study recommends AD9253-80), bursts to
  PSRAM, FPGA blends shunt+coil digitally. 20 MHz-class analog bandwidth.
- **Connector-ΔV = the instrumented pigtail (RULED 2026-07-06):**
  single-contact form — one/two sense wires tapping ONE 12 V pin's crimp at
  the GPU-plug end, watched continuously on the 4th fast channel; NOT six
  muxed wires, NOT plug-end bonding (preserves per-pin shunt attribution);
  the sensed pin doubles as the live contact-ΔV calibration reference. This
  is a new cable-assembly deliverable on the already-captive pigtail.
- **Compute/link:** GW5A-25 module FPGA (re-affirmed on merit — the only
  budget part taking the 1.28 Gbps LVDS; Tang Primer 25K continuity);
  ESP32-P4 MCU; 100BASE-T1 on pair 2 → the tier-paired **Max Hub** (ECP5
  aggregation ~$7; egress per the 2026-07-06 ruling = **USB 3.0 FIFO bridge**
  FT600Q/FT601Q class, ~200–340 MB/s real, GbE demoted to DNP-provisioned;
  FT60x LCSC sourcing still UNVERIFIED — check at part lock).
- **THE engineering risk item — the AFE.** Four differential 20 MHz-class
  front ends with µV-scale sensitivity living millimeters from a 600 W
  connector, plus the deconvolution/Rogowski-integration blend in RTL. This,
  not the digital plumbing, is the schedule driver; the proto lane (GW5A +
  AD7606 + decimator + stream FIFO + three detectors, sim-verified and
  bench-run) already de-risks most of the slow plane.
- **Per-unit cal is part of the product:** Z(f) extraction at bring-up via
  the step-load jig, constants in the cal record; first-article VRM-residue
  capture and the R-1 micro-arc characterization are the first two bench
  campaigns the instrument itself runs.

**BOM/price realism:** AD7606B ~$15 + AD9253 ~$42 + GW5A-25 ~$45 + P4 + 6×
INA240 + AFE + T1 PHY + PSRAM + pigtail assembly → plausibly ~$150–170 module
BOM, consistent with the pricing study's reserved **$499–599** retail band at
the platform's ~3.1–3.4× discipline. Treat as an estimate until Task 13's own
BOM roll-up (explicitly still owed by the part study).

## 4. Positioning

- **Ladder:** Standard = *awareness* — events + envelopes in AllMyStuff.
  Pro bench = **"the per-pin power probe"** — characterization: real
  waveforms to the ~100 kHz class, per pin, $329 standalone / $369 PRO BENCH
  system bundle. Max = **"the instrument-grade flagship"** — research:
  20 MHz-class shared channel, microarc ΔV watch, spectral fingerprints,
  $499–599 band. The owner's own line is the Max tagline: *"a Max carrying
  research-grade capture is its own bench rig."*
- **The differentiator vs a scope/power analyzer is in-situ truth:** real
  GPU + real PSU + real cable, in the real case, per-pin, always armed, with
  the §6.10 co-capture timeline across every rail in the system. A scope
  shows one probe point on a replica; CEC shows the system in production. And
  every tester feeds the fingerprint corpus that makes the consumer tiers
  smarter (the learning-loop story from the host-data-path doc).
- **Tier-honest claims (judge-tier discipline, verbatim rule):** nothing is
  marketed above validated bands until CEC bench data exists. Pro claims
  characterization; Max claims research-grade capture; Standard claims
  detection. The 250 kHz Pro figure is a *bench-direct* claim only.
- **Non-enthusiast Pro/Max buyers need no bench software** — they get richer
  evidence through the same AllMyStuff event path (events-not-streams). The
  bench posture is additive, never required. Bench tool = portable,
  no-install, same shared core (hard rule).
- **Naming (owner-corrected 2026-07-16):** "tester" is RESERVED for the PSU
  tester product; these are "bench mode" / "bench instruments." Never call
  the internal jig a tester publicly.

## 5. Critical paths + the owner decision list

**Pro bench path:** (1) ratify the Path B tier ruling (§6.14 extension —
draft spec text exists); (2) design the 12VHPWR Pro board; (3) P4 firmware
app + continuous mode + framing; (4) bench tool v1 + capture-sink file
format; (5) OQ-58 with bench rate as explicit input when EPS/PCIe Pro follow.

**Max instrument path:** Task 13 spec application (waits only on part-pick
ratification) → AFE design (risk item, start first) → module board (proto RTL
carries the slow plane) → Max Hub (ECP5 + FT60x + T1) → instrumented-pigtail
assembly → cal-jig build + Z(f) protocol → RTL productization (fast-channel
trigger/blend/deconvolution).

**Decisions for the owner:**
1. Path B ruling: module-direct USB-C bench mode on Pro/Max (recommended).
2. OQ-17: fast-ADC class — study recommends AD9253-80 (A1).
3. OQ-21: ratify AD7606B as the Max slow ADC.
4. FPGAs: GW5A-25 module / ECP5 hub (study verdicts) — nod or reopen.
5. FT600Q vs FT601Q + LCSC sourcing verify (study's flagged unknown).
6. Max Hub port count (Q6: 4 vs 8) and consumer-Max PTP need (Q7 — T1 gives
   it nearly free; consumer case hasn't asked for it).
7. Whether the step-load jig ever productizes.
8. Green-light Task 13 (the §6.11 spec application) once 2–5 are nodded.
