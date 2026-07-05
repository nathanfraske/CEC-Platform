# Pro/Max "bench mode" (stream everything) — exploration (2026-07-05)

**EXPLORATION ONLY — no spec, schematic, board, CLAUDE.md, or owner-queue file touched.**
Owner ask: can Pro and Max variants run a mode where ALL sensed data streams out, instead of
only the bursty/interesting bits the platform normally filters to. Every number below is sourced
to the spec section or a datasheet; anything not confirmed is marked **UNVERIFIED**. Read-first:
spec §6.10, §6.13, §6.11, §3.1–§3.3, §2.3/§2.6, §6.14, §4/§5, §6.9, OQ-5/OQ-9/OQ-15/OQ-20/OQ-58/OQ-59.

## 1. What "all data" means per variant

The platform already draws this distinction in two places: §6.10's ring-buffer/ALERT model
("pre-roll... freeze and dump," not a firehose) is explicitly scoped to **"the digital-sensor
modules (24-pin, EPS, PCIe)"** only. The Pro streaming path (§3.2, §6.9) carries no such language
— it is described as continuously "streaming... module to Hub," always on. So "bench mode" is
really two separate asks: (a) *deliver continuously instead of filtering to events* — Pro mostly
already does this at its chosen rate; (b) *deliver at the ADC's real native rate*, not the
platform's design point. (b) is the harder ask and is what the rest of this document sizes.

| Variant | Channels populated | Design point | ADC's real ceiling (datasheet) | Raw payload at ceiling |
|---|---|---|---|---|
| 12VHPWR Pro (§6.9, lead case) | 6× INA240 current + 1 rail-V divider = 7 of 8 LTC2358-18 inputs | 50 kHz × 6 ch ≈ **900 kB/s** (spec-quoted) | **LTC2358-18, verified**: 200 ksps/ch guaranteed at all 8 ch enabled; per-channel ceiling *rises* as fewer channels are enabled (datasheet Table: 7ch→225, **6ch→250**, 5ch→300 ksps) | 6ch × 250 ksps × 3 B/sample ≈ **4.5 MB/s** — see derivation below |
| EPS Pro / PCIe Pro (PROPOSED, §6.13, OQ-58) | 1 fast-ADC channel per cable (2 or 3) | not specified — no design point exists yet | ADC part **OPEN** (OQ-58: LTC2358-18 vs **ADS131M08**). Verified: ADS131M08 is 24-bit delta-sigma, **32 ksps/ch max** (all 8 ch) — a very different ceiling than the LTC2358-18's 200–250 ksps/ch SAR | LTC2358-18 case (3 cables × 425 ksps, 3ch-enabled row) ≈ 3.8 MB/s; ADS131M08 case (3 × 32 ksps) ≈ 288 kB/s — **7–13× apart depending on OQ-58** |
| Standard EPS/PCIe (§6.13 detection front-end) | 1 comparator per cable (INA181 + TLV7011), **no ADC on this path at all** | n/a | n/a — it is a threshold-crossing GPIO event, never a waveform | **none exists to stream** |
| 12VHPWR/EPS/PCIe Max (PROPOSED, §6.11/§6.13) | Per-pin continuous envelope/RMS (not raw) + **one shared** fast ADC behind a 6:1 mux, ~10–20 MSa/s, bit depth open (OQ-17) | trigger-driven burst only — explicitly **not continuous** | If run continuously on one pin at the high end (20 MSa/s × 18-bit ≈ 2.25 B) ≈ **45 MB/s for that one pin alone** | Simultaneous 6-pin continuous raw is **explicitly declined in §6.11 itself**: "would need six fast ADCs or a high-end DAS and crosses into a six-channel scope front end (BOM past $200)... the Max does not include it." |

Byte-packing note: the spec's own 900 kB/s figure back-solves to exactly 3 bytes/sample
(6 × 50,000 × 3 = 900,000); the LTC2358-18's native resolution is 18 bits (2.25 B), so the extra
~0.75 B/sample is presumably firmware framing overhead (status/channel tag), not a datasheet word
size — flagged, not a datasheet fact. LTC2358-18 headline figures (200 ksps/ch, 8-ch simultaneous,
18-bit, 219 mW typ/259 mW max at full 8-ch 200 ksps) verified directly from the Analog Devices
235818f datasheet (Features list; Power Requirements and Maximum Sampling Frequency tables).

**Honest top-line finding for Max:** as specced, the Max is a trigger-and-burst instrument by
deliberate design choice, not a throttled firehose — §6.11 evaluated continuous six-channel raw
capture and rejected it on cost grounds, independent of any link-bandwidth question. A true
"stream everything continuously" Max would mean reopening that decision, not tuning a rate.

## 2. Path A — in-system (module → RS-485 pair-2 → Hub Pro → USB HS → host)

**RS-485 PHY.** The spec never locks a transceiver part for the consumer Pro streaming link
(only the CAN transceiver, TJA1051T/3, is locked — §3.1). The one concrete RS-485-class part
figure anywhere in the repo is **THVD1450** (TI, named only as an since-superseded ENT
receiver-bank candidate, §6.13/bom-c-module-if-base-secio.md) — web-verified at a headline
**50 Mbps** max data rate. Treat this as illustrative of "a representative class," not a locked
part. §3.2 itself calls out the risk directly: "verify rate margin and signal integrity at the
maximum offered cable length... the classic case that passes on a 1 m bench cable and fails on a
5 m customer run" — an open bench item regardless of rate chosen.

**OQ-5 compatibility with 8 continuous streams.** OQ-5's working basis is "one RS-485 receiver
per Hub port (point-to-point)" (§3.2, §5) — an electrical/topology framing. Checking the MCU side
that has to terminate it: the ESP32-P4 has **5 general-purpose UART controllers plus 1 low-power
UART** (web-verified against Espressif's ESP32-P4 docs) — fewer serial peripherals than the
8-port Pro has ports, independent of rate. Whether Hub-side RS-485 ingest is even UART-shaped
(vs. SPI-framed/oversampled) is unspecified. This is a real gap OQ-5's current wording doesn't
name: it is not just "point-to-point vs. multidrop," it is also "does the P4 have enough serial
ingest resources for 8 simultaneous links at all."

**The math (per the task's own worked-example ask).**

| | Per-port payload | ×8 ports aggregate | vs. USB HS practical ceiling (~40 MB/s, task-given; consistent with commonly-cited USB2 HS bulk figures against a 60 MB/s theoretical) | Per-link wire rate (scaled from spec's own "900 kB/s ≈ 7–10 Mbps") |
|---|---|---|---|---|
| Design point (50 kHz × 6ch) | 900 kB/s | **7.2 MB/s** | 18% — large margin | 7–10 Mbps — comfortably under a 50 Mbps-class PHY |
| Full ADC ceiling (250 ksps × 6ch, 6-ch-enabled row) | 4.5 MB/s | **36 MB/s** | 90% — no margin left for CAN/control sharing the same USB pipe | **35–50 Mbps — at or past a 50 Mbps-class PHY's own headline ceiling, before any real-cable derating** |

**Binding constraint, ranked:** (1) the RS-485 PHY/link is the first wall — full-rate per-link
demand (35–50 Mbps) sits right at a representative transceiver's own headline number, with zero
margin once real connectors/cable length are subtracted; (2) USB HS aggregate is the second wall,
immediately behind it (90% utilized, nothing left for anything else on that pipe); (3) the P4's
UART-controller count is a *structural* third wall — it does not improve by raising or lowering
the rate, only by changing how many concurrent links the MCU can terminate at all. Rough
survivable fraction: **~3× the design point (≈150 ksps/ch, ~21–30 Mbps/link, ~22 MB/s aggregate,
54% of USB HS)** still carries real margin on both (1) and (2); by the full 250 ksps/ch ceiling,
margins on both are essentially gone simultaneously — this is the spec's own "6ch@50kHz fits"
design point versus "8ch@200kSPS[-class] does not" made concrete.

Note also: an **UNVERIFIED** wrinkle worth a bench check — the original ESP32's UART hardware
tops out at 5 Mbps (Espressif datasheet, confirmed for the classic ESP32; not separately confirmed
for the P4's UART block). If that ceiling carries to the P4, even *today's already-locked* 7–10
Mbps design-point wire rate may not fit a plain UART peripheral, meaning Hub-side RS-485 ingest is
likely not a bare async-UART link in the first place — an implementation detail the spec doesn't
specify and that sits inside OQ-5.

## 3. Path B — bench-standalone (module's own USB-C, §6.14 posture)

§6.14 (owner ruling H3) currently reads **"every Standard module is usable independently of a Hub
over its own USB-C"** — worded Standard-tier only. It does not say Pro/Max modules get an
equivalent standalone port; whether they do is undecided, not silently assumed either way here.
What exists today under H3 is a *destination* mux (CAN → USB-CDC when no CAN master is present),
carrying the same processed telemetry the module would otherwise put on CAN — it is not itself a
rate upgrade. A true full-rate "bench mode" over USB-C would be a new firmware acquisition mode
layered on that existing port, not something H3 already delivers.

Bandwidth-wise, if extended to Pro/Max, this path looks good: Pro/Max modules are ESP32-P4-based,
so a module-side USB-C would run **USB High Speed** (same class as the Hub's own host link) —
the full 6-ch/250-ksps LTC2358-18 rate (4.5 MB/s) is only ~11% of one HS link's practical budget,
with no RS-485 PHY and no Hub-ingest UART-count problem in the path at all. Standard modules
already prove the bandwidth headroom exists on the *lower* tier: the 12VHPWR Standard's own
muxed-ESP32-S3-ADC ceiling is "about 12 ksps" (§6.13's own gap paragraph) ≈ tens of kB/s raw,
trivially inside even USB Full Speed's realistic ~1 MB/s CDC throughput (community-measured
ESP32-S3 figure, **UNVERIFIED** as an Espressif-guaranteed number, but consistently reported in
the 0.5–1.2 MB/s range across forum benchmarks). So Path B "just works" for whatever a module can
already sense; the open questions are firmware (a real full-rate mode, not just a destination
swap) and the ruling of whether Pro/Max get the port at all.

## 4. What bench mode requires (delta list)

- **Firmware — new acquisition mode.** §6.10's ring buffer is a pre-roll/event-freeze design,
  not a continuous-push one; a firehose mode needs a genuinely different mode (small FIFO for
  clock-domain smoothing, not a 2 s pre-roll), applying to the 24-pin/EPS/PCIe family only if
  their sensing model changes at all (see §5 — it mostly can't).
- **Firmware — framing/timestamps/sequence numbers.** Needed for host-side reconstruction and
  drop detection. This matters because §3.2 states plainly RS-485 here "carries no control
  traffic" and has **no flow control or retransmit** — a firehose mode has no backpressure today;
  USB (Path B) has native bulk-endpoint flow control, structurally safer for a lossless firehose.
- **Hardware.** None new at the *design-point* rate on Path A (it already streams continuously
  today, per spec). At the *full ADC rate*, the open item is a real transceiver-class decision
  sized against a continuous, not bursty, duty cycle — the spec currently names no part for this
  link at all. Path B needs no new module hardware: §6.14's USBLC6-2SC6 + VBUS-clamp protection
  suite already anticipates handled-outside-the-Hub operation; the only hardware-adjacent gap is
  whether Pro/Max modules get a service USB-C, which is a ruling, not a BOM change (P4 already
  has native USB HS silicon).
- **Host software.** Out of this repo's scope (boards/firmware, not host apps): a capture sink
  that can actually absorb and store 4.5–36 MB/s continuously, with a defined file/frame format.
  Not designed anywhere in the repo today.
- **Thermal/power — negligible, with a number.** The LTC2358-18's own datasheet-quoted
  dissipation *at its full rated 200 ksps/8-ch rate* is 219 mW typ / 259 mW max — the same part,
  same footprint, same board power budget the Pro module already designs around; there is no
  separately-quoted "slow mode" figure meaningfully lower than this. Running at full rate instead
  of the 50 kHz design point is a link-budget and firmware change, not a thermal redesign. Shunt
  dissipation (the real thermal number elsewhere in the platform, §6.6) is a function of load
  current, not sample rate, and is unaffected either way.

## 5. Why Standard can't do this (contrast)

Two independent ceilings, not one. First, egress: Standard has no RS-485 pair populated at all
(§2.2, Pro+ only) — its only channel is the single shared classical CAN bus (§3.1, 500 kbps
across every module). The spec's own numbers bound this directly: §6.10 states a 400 ms four-rail
24-pin readout window is "roughly 6 kB and about 0.2 s" ⇒ ~30 kB/s effective payload throughput
for reading out just *one* module's frozen window on a bus every module must share — which is
exactly why "the default window is kept short" and the spec calls Standard "a clean single-event
recorder rather than a back-to-back transient logger" (§6.10, verbatim). Second, and more
fundamental: even the *sensor's own acquisition* is capped independent of egress — §6.10 notes
the 24-pin's I2C bus running 1 kHz across four channels already "sits near the full-round ceiling
at 1 MHz" — so there is no spare native rate hiding behind the CAN bottleneck the way there is on
the Pro's parallel-lane LTC2358-18; the I2C bus itself is nearly saturated at today's design
point. This is precisely why the §6.13 ladder frames Standard as *detection* (no waveform ever
digitized), Pro as *characterization*, Max as *spectral* — that ladder is about measurement
depth; bench mode is a different, roughly orthogonal axis (delivery completeness), and Standard's
ladder position means there is no raw waveform in existence on that tier to stream in the first
place, not merely a link too small to carry one.

## 6. Recommendation and OQ hooks

**Pro, at the existing design point:** already substantially a firmware/host-software feature on
paper — the 900 kB/s stream is already continuous, not event-filtered, today. The caveat: the Pro
module itself is mostly unbuilt (the repo's `12vhpwr-pro` schematic is a DRAFT stub — RJ-45 only,
no MCU/ADC placed), so "existing hardware" means the *spec's* design point, not a board sitting on
a bench yet — there is no retrofit needed, just a build-it-right-the-first-time firmware
requirement. **Pro, at the ADC's full native rate:** not free — Section 2's math shows it lands
right at the RS-485-PHY and USB-HS walls simultaneously; Path B (module's own USB-C at HS speeds)
is architecturally the cleaner route to genuinely-full-rate per-module data, since it sidesteps
both the PHY question and the Hub's UART-count ceiling, at the cost of a tier ruling (H3 today
reads Standard-only) and losing Hub-side consolidation. **EPS/PCIe Pro:** don't exist yet; their
"all data" rate depends entirely on the OQ-58 ADC pick (7–13× apart between candidates), so bench
capability should be an explicit input to that decision, not an afterthought. **Max:** not
currently capable of continuous all-channel raw streaming, and that is a considered design
choice already recorded in §6.11 (cost-driven), not a gap — delivering it would mean reopening
that call, which this document flags but does not resolve.

**OQ hooks (surfacing, not deciding):**
- **OQ-5** should explicitly widen beyond point-to-point-vs-multidrop to include (a) the P4
  UART/serial-ingest resource ceiling found here, and (b) whether full-rate bench streaming is
  meant to work on all 8 Hub Pro ports simultaneously or a reduced subset.
- **OQ-58** (EPS Pro / PCIe Pro fast-ADC choice) materially decides the achievable bench rate for
  that tier (LTC2358-18 vs. ADS131M08 is a ~7–13× swing) — worth stating as an explicit input.
- **OQ-15 / §6.11** (Max positioning): any "stream it all continuously" ask for Max is a
  reopening of an already-reasoned-through decision, not a rate tweak; flag it as such if raised.
- **OQ-20** (Max interconnect): the proposed 100BASE-T1 link is sized for feature reporting plus
  on-demand single-capture upload — not continuous multi-channel raw — worth stating as an
  explicit assumption if OQ-20 is ever ratified.

**Draft candidate spec text (PROPOSED, NOT adopted — for owner review only, not written into the
spec by this document):**

> Pro and Max modules may support a firmware-selectable "bench/full-telemetry" mode in which the
> module's existing continuous streaming path (§3.2) or its own service USB-C (§6.14, if extended
> to Pro/Max) carries the sensing front end's native sample rate and resolution rather than the
> platform's default design point, with no onboard filtering to alert-triggered content. Bench
> mode is out-of-band from the platform's always-on monitoring posture: it trades the OQ-2
> operating point for maximum fidelity during bench/lab use, is not assumed available on every
> Hub port simultaneously, and does not alter any per-module sensing architecture locked
> elsewhere in this document.
