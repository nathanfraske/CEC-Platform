# Max-tier bench-mode data stack: FPGA ingest, link budget, Hub consolidation

**ANALYSIS ONLY — PROPOSED framing. No spec, schematic, board, CLAUDE.md, or owner-queue file is touched.** Builds on, without restating: the **design basis of record**, `docs/research/max-instrument-channel-decision-2026-06-11.md` (owner-ratified channel architecture) plus companions `connector-microarcing-and-sampling-value-2026-06-11.md`, `dc-series-arc-signatures-2026-06-11.md`, `low-voltage-arc-spectra-r1-2026-06-11.md`, `gpu-12vhpwr-fault-phenomenology-2026-06-10.md` (all `docs/research/`); and the **foundation**, `docs/bench-mode-exploration-2026-07-05.md` (Pro-tier math, LTC2358-18 figures, RS-485/USB-HS/UART findings), extended here to Max and a new "Max Hub" concept.

Spec anchor: §6.11, §6.13, §13.2a, OQ-15/16/17/18/19/20/21/58/59/60, Appendix B. §6.11's wording predates the 2026-06-11 research ruling (freshness gap, §1/§5) — `docs/owner-queue.md` (read only, not edited) already tracks this: *"Max instrument-channel ruling → spec ... spec edit rides the owner pen."* This is analysis toward that pen edit, not a substitute for it.

## 1. The Max bench-mode data budget

**Frame, confirmed not re-litigated.** The 2026-06-11 ruling collapsed the original §6.11 three-layer table (per-pin DC/slow; per-pin continuous HF envelope/RMS; one shared trigger-driven fast capture) to **two layers**: per-pin DC/slow stays (dV/dI, imbalance, telemetry-rate — Tier A, sampling-value-curve doc); per-pin HF/fast is retired outright ("nothing wants per-pin HF," channel-decision doc §2). What survives is **one shared wideband instrument channel** — Route A (deconvolved shunt) plus Route C (PCB Rogowski di/dt pickup), blended digitally, one dual-input fast ADC (option A1 or A2, OQ-17/OQ-21 still open per owner-queue.md). Owner's tonight description — slow path across all 6 INA240 outputs into one ADC/FPGA, plus one fast ADC reading a shunt-differential and a coil-differential pair — **matches this two-layer, Route-A+C architecture closely**, with one live mismatch, flagged rather than resolved: see §6 Q1.

**Slow path** (owner: "one ADC, all 6 INA240s, FPGA decimates to ~50 kHz, usable ~10 kHz"). This is the FPGA's *decimated output* rate, not a new ADC ceiling — it maps onto the existing OQ-21 precision-plane choice, now FPGA-ingested instead of read raw by the P4:

| ADC candidate (OQ-21) | Verified per-channel ceiling | Fits owner's ~50 kHz raw target? |
|---|---|---|
| LTC2358-18 (Pro's part, 18-bit SAR) | 250 ksps/ch at 6-ch-enabled (datasheet table, `bench-mode-exploration.md` §1) | Yes, 5x margin |
| ADS131M08 (cost-reduced option) | 32 ksps/ch, verified as an 8-ch aggregate (`bench-mode-exploration.md` §1); whether 6-ch-only raises this is **UNVERIFIED** | Not as measured — a real OQ-21 tension if chosen |

Byte-packing at 3 B/sample (spec's own Pro convention — §6.9's 900 kB/s back-solves to this): **6 × 50,000 × 3 = 900 kB/s raw**, numerically identical to the Pro's already-locked "~50 kHz × 6 ch ≈ 900 kB/s" design point (§6.9) — the Max's slow path is Pro's existing design point, now consolidated through fabric, not a new rate. **6 × 10,000 × 3 = 180 kB/s** at the "usable" 10 kHz tap — 10 kHz is exactly the sampling-value-curve doc's own identified knee ("the knee for consumer-relevant load dynamics," `connector-microarcing-and-sampling-value-2026-06-11.md` §2.1/2.2), a real independent cross-check, not a coincidence.

**Fast/instrument path.** Per the ruling: ADC option A1 (50–65 MS/s, 12–14 bit, dual channel) or A2 (25 MS/s "ADC342x-class," similar bit depth) — owner's choice, still open per owner-queue.md. Owner's *prototype* fast-ADC part and rate: **UNVERIFIED-pending-owner** (§6 Q1). At either ruled option, continuous full-rate delivery is nowhere near survivable:

| Option | Continuous byte rate (2 ch × 2 B, 14-bit packed) | Continuous bit rate |
|---|---|---|
| A1 (50–65 MS/s) | ~200–260 MB/s | ~1.6–2.1 Gbps |
| A2 (25 MS/s) | ~100 MB/s | ~800 Mbps |

Both exceed even a bare GbE pipe's realistic payload ceiling (~110 MB/s, §2); A2's figure fits GbE's raw 125 MB/s envelope only in theory, with zero margin for the slow path, control traffic, or any other port. **Not a link problem — no plausible link carries continuous full-rate fast-path data at either ruled ADC option.** The fast channel is structurally a windowed-burst capability, exactly as spec §6.11 already frames it ("on-demand," "burst into PSRAM") — the ruling changed what is inside the burst, not the burst shape itself.

**Documentation gap, noted in passing:** §6.11's "companion FPGA-Max backing document" is referenced three times in the spec but does not exist as a file in this repo (checked) — future sessions should not assume it is retrievable.

## 2. The link (pair 2 STREAM) — does 100BASE-T1 carry the budget

100BASE-T1 (IEEE 802.3bw) is 100 Mbps full-duplex over one balanced pair — the standard's own title. Standard Ethernet framing overhead (preamble/IFG/header/FCS) is a well-known few-percent-to-low-teens loss depending on frame size; call the realistic application payload **~90 Mbps ≈ 11 MB/s** as a round working figure (engineering estimate, not a pinned datasheet number — the primary 802.3bw text is paywalled and was not pulled).

| Delivery mode | Payload demand | vs. ~11 MB/s T1 payload | Verdict |
|---|---|---|---|
| Slow path, continuous, "usable" 10 kHz/ch | 180 kB/s (1.44 Mbps) | 1.6% | trivial, huge margin |
| Slow path, continuous, raw ~50 kHz/ch | 900 kB/s (7.2 Mbps) | 8% | comfortable |
| Fast path, on-demand 10 ms burst @ A2 | 1 MB one-shot | ~90 ms download | fine for "on-demand" |
| Fast path, on-demand 100 ms burst @ A2 | 10 MB one-shot | ~0.9 s download | acceptable, user-perceptible |
| Fast path, CONTINUOUS @ A2 (100 MB/s) | 800 Mbps | ~9x over ceiling | does not fit |
| Fast path, CONTINUOUS @ A1 (~230 MB/s) | ~1.8 Gbps | ~20x over ceiling | does not fit |

**Verdict: 100BASE-T1 carries the sustained slow/decimated budget with an order of magnitude of headroom, and carries fast-path on-demand bursts in acceptably short user-facing time. It structurally cannot, and is not expected to, carry continuous raw fast-path data at either ruled ADC option — nothing in this class does.** The honest shape is **continuous slow + decimated-fast streaming, plus on-demand raw-window pulls**, never a continuous raw firehose.

**Alternatives, checked because §6.11 invites it, not because the math demands it.** 1000BASE-T1 (automotive SPE), same pair, raises the ceiling ~10x (~110 MB/s effective) but still falls short of A1's ~230 MB/s continuous need — it would only shrink burst download time, already acceptable at 100BASE-T1. Spec §13.2 demotes 1000BASE-T1 to a factory option at ENT's *host* uplink (cost/availability), a tier with a materially higher budget than a consumer Max — independent reasoning here converges with existing skepticism rather than contradicting it. Burst-buffered delivery (PSRAM capture, trickle out over time) is not a fallback *instead of* 100BASE-T1 — it is what any link needs for the fast path, T1 included, and is already spec §6.11's own model.

CAN control stays on pair 3 throughout — mirrors ENT (§13.2a: "power, CAN, and DETECT stay on their pairs"), and §6.11's own reconciliation note says the same for consumer Max. Nothing above touches that.

## 3. Max Hub — tier-paired consolidator (N=4 and N=8)

No "Hub Max" exists anywhere in the spec today (checked §4/§5/§9/Hub tables) — new territory the owner opened tonight, answering OQ-15's "does the Max...define its own Hub-tier requirements" affirmatively and giving OQ-20's "one Max per Hub without a switch IC" constraint somewhere to go.

**Silicon shapes, ranked:**

**(i) GOWIN GW5A-class fabric + ESP32-P4 — best fit.** The owner's own working-prototype lineage (Sipeed Tang Primer 25K / GW5A-25), generalized module-to-Hub. GW5A-25, datasheet-verified: 23,040 LUT4, 180 Kbit shadow SRAM + 1008 Kbit BSRAM, DSP blocks (WebSearch, Gowin DS1103E, 2026-07-05) — matches the spec's own "20K to 25K LUT4 with DSP and BRAM" ballpark (Appendix B.2). LCSC lists GW5A-LV25MG121NC1/I0 (BGA121) at **~$44.55 single-unit** (WebSearch, LCSC, 2026-07-05) — **100-qty pricing UNVERIFIED** (likely lower per the usual volume curve, not sourced here). Sipeed Tang Primer 25K dev module retails ~$19 (module) to ~$29 (+carrier) (WebSearch, Sipeed/Amazon/AliExpress, 2026-07-05) — **dev-board retail, not a from-scratch board's BOM**, kept distinct from the LCSC figure. Role split, per Appendix B.1's own FPGA-vs-MCU logic (wire-speed, deterministic, contention-free work belongs in fabric): fabric does N×100BASE-T1 MAC-side ingest plus a GbE MAC for uplink; the P4 keeps the platform's CAN control-plane and USB HS host stack, unchanged from today's Hub Pro — the Hub becomes *symmetric* with the Max module, which already pairs FPGA-for-wire-speed-work with P4-for-decide-and-report (§6.11 Construction, Appendix B.1). **N discrete T1 PHY transceivers are still needed regardless of where MAC/switch logic lives** (fabric replaces MAC/switching, not the analog PHY), and no T1 PHY part is named anywhere in the spec — OQ-80 flags "T1 PHY part class" as open even for ratified ENT, doubly open here. **UNVERIFIED:** whether one GW5A-25 has I/O and logic budget for N×RMII/MII ingest plus a soft GbE MAC concurrently — not sized in this document.

**(ii) PolarFire ENT-posture variant — proven, wrong cost class.** ENT already runs this shape: "the hub serves the pair T1-only via 2× LAN9370 switches" (§13.2a). LAN9370, verified: 5-port 100BASE-T1 switch, 4× integrated T1 PHYs + 1 MAC port (RGMII/MII/RMII-configurable), AEC-Q100 automotive-grade, 64-pin QFN (WebSearch, Microchip product brief/GlobalSpec, 2026-07-05; price not found) — two give exactly 8 T1 ports. Real shipping precedent, but bundled with ENT's PolarFire posture (PUF key storage, Athena crypto, Libero toolchain cost, §13.1/Appendix B.3), and AEC-Q100 silicon typically carries a premium over a consumer-grade equivalent. Honest read: a capable fallback if the Max Hub ever needs ENT-grade determinism, but disproportionate to a $499–599 enthusiast product — it imports ENT's whole security/cost posture to solve a port-count problem alone.

**(iii) P4-only — states plainly what dies.** Spec's own OQ-20: "the ESP32-P4 has one RMII MAC, so a Hub supports one 100BASE-T1 / Max module without an Ethernet switch IC." A P4-only Max Hub caps at **N=1** — not the multi-port consolidator described tonight ("ingest THAT tier of modules," plural), and indistinguishable at N=1 from today's Hub Pro with one T1-capable port (§6.11's existing "Max requires a Pro+ Hub" note). If intent is genuinely N>1, option (iii) is off the table.

**N=4 / N=8 aggregate math** (continuous slow/decimated path only — the fast path never aggregates continuously, per §1/§2):

| | N=4 aggregate | N=8 aggregate | vs. GbE ~110 MB/s effective | vs. single-T1-class ~11 MB/s egress |
|---|---|---|---|---|
| "Usable" 10 kHz/ch, all ports | 0.72 MB/s (5.8 Mbps) | 1.44 MB/s (11.5 Mbps) | 0.7–1.3% | 6.5–13% |
| Raw ~50 kHz/ch, all ports | 3.6 MB/s (28.8 Mbps) | 7.2 MB/s (57.6 Mbps) | 3–6.5% | 33–65% |

GbE egress swallows either port count with room to spare. A single-T1-class Hub uplink hits 65% utilization at N=8 raw-everywhere before any burst rides on top — survivable, but thin margin for the rare worst case of several ports bursting a raw waveform pull simultaneously. **Recommend GbE (RGMII PHY) egress over USB HS at N=8**: the margin above, plus an architectural reason — if fabric already aggregates N ports, driving GbE directly from it avoids a second hop back through the P4's USB HS stack, which would reintroduce the very "P4 can't terminate N links" bottleneck the fabric exists to remove. Worth surfacing honestly: a GbE-attached Hub is a network device to the host software stack, not a USB device like every other Hub in the platform today — an integration question, not just a bandwidth one (§6 Q6/Q8).

## 4. Tier story

| Tier | What ships | Link | Source |
|---|---|---|---|
| Standard | Detect/envelope only — binary threshold-crossing event, no waveform ever digitized | CAN only | §6.13 (EPS/PCIe detection front-end), §6.1 (12VHPWR Standard imbalance) |
| Pro | Design-rate stream, already continuous today on paper (900 kB/s); bench mode is mostly a firmware/host-software gate, not new hardware | RS-485 → Hub → USB HS | `bench-mode-exploration.md` §6; P4's 5 UART + 1 LP-UART vs. 8 ports = the still-open OQ-5 cap (same doc §2) |
| Max | Ruled two-layer telemetry (per-pin slow/precision + one shared fast instrument channel) + FPGA Hub ingest + T1 + GbE egress; continuous-decimated streaming, raw only as on-demand burst windows | 100BASE-T1 (module) → FPGA Hub → GbE (recommended) | This doc §1–§3; `max-instrument-channel-decision-2026-06-11.md` |
| ENT | Origin of the T1 technique consumer Max inherits — §13.2a: "this resolves OQ-20 for the ENT line (the Max program inherits the precedent)" | 100BASE-T1 (module) → 2×LAN9370 → 1000BASE-T host | §13.2/§13.2a; adds sub-µs PTP-class sync consumer Max hasn't asked for (§6 Q7) |

EPS Max / PCIe Max (§6.13, proposed SKUs) are named in the spec as likely sharing the 12VHPWR Max's FPGA data plane — a Max Hub built per §3 would ingest that whole module family over the same T1 port class, not 12VHPWR Max alone; noted for completeness, not expanded further here.

## 5. Proposed spec hooks (candidate text — this document only, not adopted)

**§6.11 sensing-architecture refresh candidate**, aligning the LOCKED table to the research ruling and tonight's facts (today's table still shows the retired six-channel/mux model and the unsupported "2 to 5 MHz arc-signature band" language — the freshness gap noted in §1):

> Sensing architecture, two layers sharing the existing 1 mΩ per-pin shunt: (1) DC and slow precision — all six channels through one simultaneous-sampling ADC (OQ-21: LTC2358-18 or a cost-reduced alternative), FPGA-ingested and decimated for a clean reporting bandwidth rather than read raw by the P4; stays the dV/dI-and-imbalance domain. (2) On-demand full waveform capture, shared, one instrument channel, never continuous: one dual-input fast ADC (OQ-17 option A1 or A2) reading a deconvolved shunt-differential tap and a PCB Rogowski coil-differential tap, blended digitally in the FPGA, trigger-driven into PSRAM. The six-channel continuous fast array and the per-pin continuous HF envelope/RMS detector are both retired (`max-instrument-channel-decision-2026-06-11.md` §2). Capture bandwidth targets the validated ATX-ripple/transient case (up to 20 MHz-class analog BW at option A1), not the earlier unsupported 2–5 MHz arc band (`dc-series-arc-signatures-2026-06-11.md`, `low-voltage-arc-spectra-r1-2026-06-11.md`).

**Max Hub row candidate** (Hub tables, §4/§5 area):

> Hub Max (tier-paired, PROPOSED) — N ports (4 or 8, OQ-TBD) — GW5A-class FPGA + ESP32-P4 — N× 100BASE-T1 ingest (module-side), GbE/RGMII egress (host-side) — BOM not costed. Ingests the Max module family (12VHPWR Max, and EPS Max/PCIe Max per §6.13) at full telemetry rate; a Pro Hub continues to serve one Max module in degraded/N=1 mode per the existing OQ-20 note.

**Bench-mode paragraph candidate** (extends, does not replace, the Pro-tier draft already proposed in `bench-mode-exploration.md` §6):

> Bench mode is hub-consolidated and tier-paired: a Standard Hub has nothing to stream in full-telemetry mode, since no Standard module digitizes a waveform at all (§6.13). A Pro Hub's bench mode is the Pro module's existing design-rate stream (§3.2) made firmware-selectable and continuous rather than event-filtered — no new hardware. A Max Hub's bench mode is two simultaneous deliveries per port: the per-pin slow/precision plane, continuous and decimated, and the shared fast instrument channel, delivered only as operator-triggered or scheduled raw-window pulls, never a continuous firehose. No tier's bench mode implies continuous raw capture at a sensor's full native rate; every tier's ceiling is a considered architecture choice, not an oversight.

## 6. Open owner questions

1. **Fast ADC part + rate in the prototype, and a channel-makeup mismatch**: tonight's description names two current-domain differential inputs (shunt, coil), while the ruling's ADC options (A1/A2) are framed as sampling **voltage and current** simultaneously (`max-instrument-channel-decision-2026-06-11.md` §3.7) — the validated ATX-ripple use case anchoring the whole ruling is a *voltage* measurement. Where does the AC-coupled wideband voltage tap live: a third fast-ADC channel not mentioned tonight, a deliberate deferral in the rough prototype, or something else? (Flagged per instruction, not silently resolved either way.)
2. **What does the Tang Primer prototype stream today** — at what rate, over what interface (bench SPI/parallel to a laptop, USB, or already some Ethernet/T1 path)? Anchors whether "reads at max speed" (fact #1) is a measured number or an aspiration.
3. **Coil part and integrator**: is M·dI/dt restored to current by an analog integrator ahead of the ADC, or integrated digitally in the FPGA (both named as options, design-basis doc §3.4)? Is the coil a PCB-embedded trace loop (Route C) or a discrete/clip-on part on the current prototype?
4. **Slow-ADC part**: LTC2358-18 (Pro's part, clears the ~50 kHz raw figure with margin) or ADS131M08 (the cost-reduced OQ-21 option, whose verified ceiling sits below that figure, §1)? This is exactly OQ-21, still open per owner-queue.md.
5. **Max module MCU / P4-FPGA interface**: ESP32-P4 is already spec-locked for the Max module table; the live question is how the P4 talks to the FPGA — does the fabric spend the P4's one RMII MAC internally (leaving nothing for a direct T1 PHY connection from the P4 itself), or is the P4-FPGA link a separate bus (SPI/parallel/LVDS, per the existing analog-digital board-split language, §6.11 Construction)?
6. **4-vs-8-port Max Hub**: which port count is intended — Standard-parity (4) or Pro-parity (8)? The N=8 case is where the GbE-over-USB-HS recommendation in §3 actually matters; at N=4 either egress works with margin to spare.
7. **T1 ruling for the Max Hub**: does it need ENT's sub-microsecond PTP-class hardware timestamping (§13.2a), or is best-effort per-event timestamping sufficient for a bench/enthusiast product? This materially changes fabric complexity and cost — copying ENT's ambition versus right-sizing independently is a real fork, not a detail.
8. **Launch shape**: is "continuous slow + decimated-fast streaming, plus on-demand raw windows" (this document's §1–§2 recommendation) the intended v1 bench-mode behavior, or does the owner want a distinct firmware "bench mode" personality separate from the platform's always-on monitoring posture (as `bench-mode-exploration.md` §6 drafted for Pro/Max generally)?

---

**Sources for this document's own figures** (beyond the design-basis and foundation docs already cited inline): GW5A-25 resource counts and LAN9370 port/package facts — WebSearch, Gowin DS1103E datasheet summary and Microchip product brief/GlobalSpec, 2026-07-05; GW5A-25 LCSC single-unit price and Sipeed Tang Primer 25K retail price — WebSearch, LCSC listing and Sipeed/Amazon/AliExpress listings, 2026-07-05; 100BASE-T1 headline rate — IEEE 802.3bw standard title, corroborated via WebSearch summaries, 2026-07-05 (the primary IEEE text is paywalled and was not pulled). Ethernet framing-overhead percentage is a textbook estimate, not separately sourced. All other numbers trace to the design-basis research docs, the foundation doc, or the spec sections named inline.
