## Survey 4: Redundant power path — recommendation

**Topology: keep the as-built dual-TPS2121 priority cascade as the OR/switch stage; add a per-source eFuse monitor+protect front-end (TI TPS25940-class) ahead of each of the three physical inputs, for the enterprise tier only.** Do not adopt LTC4417 as the default — validate it as a legitimate alternative (below), but the eFuse front-end already satisfies the hard requirements at lower parts count, reusing the schematic work already done (CLAUDE.md action item 0: `U7`/`U5` TPS2121 cascade, `MAIN_5V_RAW (priority) > PSU_5V (5VSB/USB OR)`).

**How this satisfies fail-detected + self-test:**

- **REQ-HUB-COMMON-050 (individually monitored, alarmed within bounded time).** Each of the 3 sources gets its own TPS25940-class eFuse in series, ahead of the TPS2121 mux stage. Its `PGOOD`/`FLT` pins are hardware comparators against configured UVLO/OVLO/ILIM thresholds — a clean digital status per source with no firmware ADC calibration or software debounce to validate. This is a direct upgrade over the board's current state, where the two TPS2121 stages only expose an `ST` pin (which of *its own two* inputs is selected) and the existing `MAIN_5V_SENSE`/`5VSB_SENSE` ADC taps (IO9/IO10) — I traced the schematic note in CLAUDE.md and found a real gap: `5VSB_SENSE` (IO10) reads `PSU_5V`, which is *already* the OR'd output of U5 (5VSB + wall-wart/USB combined). Today the design cannot tell "5VSB present, wall-wart gone" from "wall-wart present, 5VSB gone" — only the combined node. Splitting a monitor point onto each raw source (which an eFuse gives you for free via its own PG comparator) is required to make all three sources genuinely *independently* monitored, not just two.
- **REQ-HUB-COMMON-051 (self-testable without taking the machine down).** Use each eFuse's `EN` pin as the self-test lever: firmware confirms the currently-active source is healthy (PG asserted), then commands `EN` low on *that* eFuse only — a controlled, reversible simulated loss, not a real fault. The downstream TPS2121 cascade fails over seamlessly (TI specs ~5 µs typ. for TPS2121's break-before-make-free switchover), and firmware confirms (a) it never browned out — the fact it's still running and can log the event is the proof, (b) the `ST`/`PG` transition happened, (c) timestamps get logged. Re-assert `EN` and confirm clean revert. This is the standard technique for testing redundant supplies "without interrupting the load" (see the patent citation below) — the source itself is never touched, only its local gate into the shared rail. It genuinely tests the failover *mechanism*; it does not prove the upstream PSU rail can source full current under real load (a real disconnect during a maintenance window is still the only full-confidence test — flagged as a residual risk below).
- **REQ-HUB-COMMON-052 (accept an independent feed, ride through, log — "graduated from PROPOSED to binding").** TPS25940's datasheet-described role is explicitly this exact problem: *"integrated back-to-back FETs provide bidirectional current control... well suited for systems with load-side holdup energy that must not drain back to a failed supply bus"* — i.e., true reverse-current blocking, per source, ahead of the mux. That gives a documented, per-source answer to the back-feed-isolation half of OQ-55 that the spec text itself already flags as safety-critical ("confirm the mux's reverse blocking covers the shared-rail path back into the 5VSB source... add the matching isolation on the NanoKVM's slot input" — spec §2.9), rather than relying solely on the downstream TPS2121's own blocking.
- **REQ-HUB-COMMON-060/062.** The cascade + rail-sense + load-budget firmware state machine is already the architecture spec §2.9 describes and is already substantially built on the $36 consumer Hub (schematic-verified per CLAUDE.md item 0). This survey extends it, it doesn't replace it.

### Why not just move to LTC4417

LTC4417 is real and does what CLAUDE.md's framing says: it connects **one of three valid power supplies to a common output based on fixed pin-assignment priority** (V1 > V2 > V3), with `VALID1/2/3` open-drain outputs that assert once a source's voltage has sat inside its OV/UV window continuously for **256 ms** [analog.com datasheet, via search extraction — 256 ms figure is datasheet-stated]. That 256 ms qualification window is a genuine asset: it's a documented, part-spec'd "bounded time" you can cite directly against REQ-HUB-COMMON-050's "alarm within a bounded time" wording, instead of a firmware-owned threshold+debounce that has to be independently validated.

But it is a **controller, not an integrated switch** — it drives external P-channel MOSFETs (one per input) through a gate driver with a 6 V clamp and a slew-limiting RC network (`RS`/`CS`/Schottky `DS` per channel, sized against the MOSFET's Qg and the acceptable output droop) [datasheet + application-circuit search extraction]. That means adopting it doesn't reduce parts count versus the existing 2×TPS2121 (which have integrated FETs) — it *adds* 3 external PFETs and 3 gate-drive networks, plus new PFET selection/characterization work, in exchange for going from two 2-input parts to one 3-input part. Given the eFuse front-end above already delivers per-source monitoring, self-test, and reverse-block, the LTC4417's main *remaining* differentiator is a single-part story for the MTBF/FIT report (REQ-HUB-COMMON-080/081) and one less firmware-tuned priority threshold to validate. That's a legitimate reason to choose it, but it's an owner trade-off (cost/complexity vs. single-chip FMEA cleanliness), not a forced move — I'd present both to the owner rather than defaulting silently.

**A more important finding that argues for TPS2121/LTC4417's whole part *family*, and against the other "alternatives" named in the brief:** LM66200, LTC4415, and MAX40203 are **automatic highest-voltage-wins ideal diodes**, not fixed-priority selectors. LM66200 explicitly "uses automatic diode mode to prioritize the **highest voltage** supply" [TI product page]; MAX40203 and LTC4415 are the same class of building block (LTC4415's `EN1`/`EN2` let an external supervisor gate priority, but the chip itself has no priority-assignment logic of its own). The spec's explicit ask — main 5V > 5VSB > wall-wart **by assignment**, "rather than a firmware switch," specifically because a firmware-controlled switch on its own supply can deadlock the MCU (spec §2.9) — is a fixed-priority requirement, independent of which source happens to read the higher instantaneous voltage (main 5V and 5VSB are both nominally ~5 V and could be within noise of each other, which is exactly the "coin-flip instability" a pure highest-wins ideal diode risks). TPS2121 and LTC4417 are both assignment-priority parts (TPS2121 via `PR1`/`CP2` pin-strap threshold, confirmed against the schematic's own `MAIN_5V_RAW (priority) > PSU_5V` wiring; LTC4417 via fixed `V1 > V2 > V3` pin position). LM66200/LTC4415/MAX40203-class parts would need external voltage-biasing tricks to force a deterministic order, which erodes the "simple, cheap, integrated" case they're usually chosen for. I'm therefore not recommending any of them as the OR/prioritizer — they remain useful only as a possible low-level isolating-diode building block elsewhere (e.g., MAX40203 as a cheap discrete ideal diode inside a custom OR, not as the top-level arbiter).

### Comparison table

| Part / class | Topology | Switch | Per-source monitor | Self-test lever | Reverse-block | Price @ ~100 qty (source, date) | Verdict |
|---|---|---|---|---|---|---|---|
| **TPS2121 ×2 cascade (as-built)** | Fixed-priority mux, 2-in each, cascaded to 3 | Integrated FET | `ST` flag (which input active) + existing ADC taps (coarse — see gap above) | None built in | Yes (source-side, per datasheet; unverified at board level) | ~$0.62–0.66/ea (LCSC C485916) or ~$3.13/ea (Digikey TR, 250 MOQ) [search, 2026-07-02] | **Keep as OR stage** |
| **+ TPS25940-class eFuse front-end (proposed adder)** | Per-source protect+monitor, feeds into the cascade above | Integrated FET | PGOOD + FLT + current monitor, per source, hardware comparator | `EN` pin = commanded simulate-loss | Yes, "true reverse current blocking," explicitly for the back-feed case [TI product page] | $1.714/ea @ 100 (Digikey TPS25940LRVCR, fetched 2026-07-02) | **Recommended addition** |
| **LTC4417** | Fixed-priority mux, 3-in native | Controller only — needs 3 external PFETs + gate RC/Schottky per channel | `VALID1/2/3`, 256 ms OV/UV qualification, datasheet-spec'd | None built in (would need the same EN-style trick as above, external) | Yes (ideal-diode-style PFET control) | $7.63/ea @ 100 (GN16/SSOP-16, Digikey LTC4417IGN#PBF, fetched 2026-07-02); QFN-24 variant ~$5.33 (LCSC, only 13 in stock [unverified stock depth]) or ~$11.16 TR (2500 MOQ) | Valid alternative; adds parts/board area, buys single-chip cleanliness |
| **LTC4415** | 2-channel ideal diode, `EN1`/`EN2` gate priority externally | Integrated FET (4 A/ch) | Open-drain "forward conducting" flags per channel; current monitor via `CLIM` pins | External (needs a supervisor to drive EN) | Yes (<1 µA reverse leakage, datasheet) | Price not found via search [unverified — no data] | Not recommended: only 2 channels, priority is external, not native |
| **LM66200** | 2-channel **automatic highest-voltage-wins** ideal diode | Integrated FET (2.5 A) | `ST` (which input conducting) | `ON`/EN only (device-level disable, not per-channel priority test) | Yes | $0.3244/ea @ 100 (Digikey, fetched 2026-07-02) | Wrong topology class (not fixed-priority) — not recommended as OR |
| **MAX40203** | Single-channel ideal diode building block | Integrated FET (1 A) | None (bare diode) | `EN` | Yes, ~90 mV Vf | ~$0.46–1.01/ea depending on qty tier [search, unverified] | Building-block only, not a top-level arbiter |
| **TPS25947-class eFuse (5.5 A)** | Single-channel eFuse | Integrated FET | PGOOD + FLT (variant-dependent) | `EN` | True reverse blocking | ~$1.48–2.30/ea, low-qty snippets [search, unverified — no clean 100q break found] | Oversized for Hub-class current; TPS25940/TPS2595 (lower-current siblings) fit better |

### BOM adder estimate (100 qty, enterprise/MC tier over the existing consumer 2-source baseline)

| Item | Qty | Unit (100q) | Extended |
|---|---|---|---|
| TPS25940LRVCR eFuse front-end | 3 | $1.71 [Digikey, fetched 2026-07-02] | ~$5.15 |
| Support passives per eFuse (ILIM/UVLO/OVLO dividers, bypass, PG/FLT pull-ups) | 3 sets | ~$0.35 [estimate] | ~$1.05 |
| Hold-up bank upsize (2nd 4700 µF or step to ~10,000 µF electrolytic — see below) | 1 | ~$1.00 incremental [estimate] | ~$1.00 |
| Rear-bracket CEC power-in connector (OQ-54 closure — see below) | 1 | ~$0.50–1.50 (existing platform 2-pin JST-XH class part) | ~$1.00 |
| **Subtotal — recommended (keep TPS2121 cascade + eFuse fronts)** | | | **≈ $8–9** |
| *If also swapping the mux to LTC4417 (alternative, not recommended by default):* | | | |
| LTC4417IGN (replaces 2× TPS2121) | 1 | $7.63 | $7.63 |
| less 2×TPS2121 removed | −2 | −$0.65 (LCSC) to −$3.13 (Digikey) | −$1.30 to −$6.26 |
| 3× external P-FET + gate RC/Schottky network | 3 sets | ~$0.35–0.50 [estimate] | ~$1.05–1.50 |
| **Net incremental for the LTC4417 swap, on top of the above** | | | **≈ +$2 to +$8** |

Combined worst case (eFuse fronts + LTC4417 swap) lands around **$10–17/unit at 100 qty**; the recommended path (eFuse fronts, cascade kept) is **~$8–9/unit**. Against the D-ENT-3 re-baseline comparables ($1.5–3k/unit class, per `docs/enterprise-requirements/research/customer-integration-audit-2026-07-01.md`), this is noise — the deciding factor between the two paths is engineering risk and parts count, not dollars, so I'm not defaulting to the more expensive option just because Enterprise is framed as non-cost-constrained.

### Hold-up sizing sanity (item d) — ties to REQ-HUB-COMMON-062/070/071

The board already carries a 4700 µF Panasonic EEVFK1C472M (16 V rated, ~5 V rail) hold-up reservoir. Illustrative sanity check (my calculation, not a substitute for the OQ-56 bench item, which the spec/owner-queue already correctly frame as the real gate):

- Usable swing: ~5.0 V down to a regulator dropout floor of roughly 3.4 V (LP5907-class LDO headroom + margin) → ΔV ≈ 1.6 V.
- ΔQ = C·ΔV = 4700 µF × 1.6 V = 7.52 mC.
- At a flush-mode load of 50–150 mA (ESP32-S3 active current ~24 mA with Wi-Fi off per Espressif's own measurement docs, plus SPI-NOR active current on top, LEDs already gated off per the spec's `FORENSIC_EXTRACTION` mode): **t ≈ 50–150 ms**.

Compared against typical SPI NOR flash timing (order-of-magnitude, general industry figures — I could not pull a clean primary-source AC-characteristics table for a specific part in this pass, mark **[unverified]**): a single **page program** (256 B) is typically ~1–3 ms; a **4 KB sector erase** is typically tens-to-~100 ms. That means the existing 4700 µF comfortably covers a page-program-only write, but is marginal-to-insufficient against an erase-then-write sequence, especially if a tamper-log entry (REQ-HUB-COMMON-070/071) and a telemetry frozen-window both need to flush in the same event.

**Recommendation:** this is dominantly a **firmware** lever, not a capacitor-sizing one — commit to an append-only/log-structured write path for anything on the persist-on-fault critical path (pre-erased circular region, background erase only during healthy operation, never on the power-loss path). That single decision likely makes the existing consumer hold-up cap adequate. For Enterprise/MC, cheaply double the margin anyway (a 2nd 4700 µF or a single ~10,000 µF electrolytic, ~$1 adder) since REQ-HUB-COMMON-062 uses the word "guaranteed." Escalate to a dedicated supercapacitor (Vishay 196/195 HVC-class or similar — these are explicitly marketed for exactly this "power failure and write cache protection for enterprise SSD/HDD" role) **only if the bench item proves the electrolytic path insufficient**: at these currents even a few-hundred-mF supercap is generous (a 1 F cell alone gives ~10+ seconds at 150 mA), so the real cost of that escalation is the charge-management circuit (inrush limiting, leakage budget against the OQ-2 standby cap, possible cell balancing), not the capacitor itself.

### OQ-53..56 closure proposal (enterprise tier)

| OQ | Proposal |
|---|---|
| **OQ-53** (module-rail scope) | Out of this survey's depth (Hub-side redundancy was the ask). Recommend deferring as a separate module-tier decision — Enterprise/MC Hub redundancy does not require the module fleet to ride the shared rail; leave modules on 5VSB-only per current Standard behavior unless a future survey makes the case. |
| **OQ-54** (external forensic power-in) | Propose **close**: make a dedicated rear-bracket CEC power-in **mandatory** at Enterprise/MC (not solely dependent on the NanoKVM's USB-C being bracket-accessible, which spec text itself flags as uncertain — "some are internal"). REQ-HUB-COMMON-052's "SHALL accept" wording is binding language; an uncertain connector doesn't satisfy "SHALL." |
| **OQ-55** (source-OR part + back-feed isolation) | Propose **close** on: keep the TPS2121 cascade, add TPS25940-class eFuse front-ends per source for monitoring/self-test/reverse-block (primary); record LTC4417 as a validated, owner-selectable alternative if single-chip FMEA cleanliness is prioritized over parts count. Either way, **bench-verify** reverse-block behavior under a real dead-PSU fault injection (REQ-HUB-COMMON-081 FMEA) — don't rely on datasheet claims alone, consistent with the spec's own existing caveat. |
| **OQ-56** (persist-on-fault + hold-up sizing) | Propose **close contingent on a firmware commitment** to page-program-only writes on the critical path; hardware side, upsize the hold-up bank modestly now (cheap insurance) and gate any supercap escalation on the actual bench measurement, not a datasheet estimate. |

### Risks

- **Self-test is partial, not end-to-end.** Disabling a source via its eFuse `EN` proves the mux/failover mechanism works; it does not prove the upstream PSU rail can deliver full current under real load. A true full-confidence test still needs a real disconnect during a maintenance window — this is a documented limitation of self-test-without-interruption generally (see patent citation below), not specific to this design.
- **The granularity gap is real today.** As currently wired, `5VSB_SENSE` reads the already-OR'd 5VSB/wall-wart node, not each source individually — this must be fixed (via the eFuse front-end or an equivalent split sense point) for REQ-HUB-COMMON-050 to be honestly satisfiable at Enterprise tier.
- **LCSC stock depth is thin for some LTC44xx variants** (QFN-24 LTC4417IUF showed only 13 units at LCSC in this search pass) — if LTC4417 is chosen, plan on Digikey/Mouser sourcing at enterprise volumes, not the JLCPCB/LCSC assembly flow the consumer tier uses; Analog Devices/Linear parts also carry longer standard lead times (10 weeks, per Digikey) than the TI parts already in the design.
- **Pricing in this survey is web-search-snapshot quality**, not live distributor-cart pricing. Two numbers were confirmed via direct product-page fetch with a clean quantity-break table (LTC4417IGN, LM66200DRLR, TPS25940LRVCR); the rest came through the search tool's own synthesis and are marked [unverified] — re-quote before costing D-ENT-3.
- **Hold-up math above is illustrative**, built on assumed regulator dropout and assumed flush-mode current draw, not measured. It should not be treated as satisfying the OQ-56 bench item.
- **eFuse addition is a firmware-facing change** (new PG/FLT/EN lines, GPIO budget on the Hub MCU not verified in this pass) — flag as a dependency for whoever owns Hub firmware.
- **CAN/uplink redundancy (Phase-2 research item 5) is explicitly out of scope here** — REQ-HUB-COMMON-050's "power feed, uplink, CAN transceiver where fitted" language means this survey only closes the power leg of that requirement.

### Feeds

REQ-HUB-COMMON-050, REQ-HUB-COMMON-051, REQ-HUB-COMMON-052, REQ-HUB-COMMON-060, REQ-HUB-COMMON-062 (`docs/enterprise-requirements/hub-enterprise-requirements.md` §6–7); brief tie to REQ-HUB-COMMON-070/071 (tamper-log persistence shares the same flush/hold-up path); **D-ENT-6** (this redundancy pack is a discrete, addable hardware capability — a front-end + optional mux swap — not architecturally fused to either variant label, so it's a scope knob D-ENT-6 can assign to Enterprise-only, MC-only, or both without redesign). Spec §2.9 (PROPOSED); OQ-53, OQ-54, OQ-55, OQ-56.

### Sources

- [LTC4417 Datasheet and Product Info | Analog Devices](https://www.analog.com/en/products/ltc4417.html)
- [LTC4417 datasheet PDF | Analog Devices](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4417.pdf)
- [LTC4417IGN#PBF | DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC4417IGN-PBF/3838533) — direct-fetched pricing table, 2026-07-02
- [LTC4417IUF#PBF | DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC4417IUF-PBF/3838535)
- [LTC4417IUF#PBF | LCSC](https://www.lcsc.com/product-detail/Power-Distribution-Switches_Analog-Devices-LTC4417IUF-PBF_C580907.html)
- [LTC4415 - Dual 4A Ideal Diodes datasheet | Analog Devices](https://www.analog.com/media/en/technical-documentation/data-sheets/4415fa.pdf)
- [LTC4415EMSE#TRPBF | DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC4415EMSE-TRPBF/2769736)
- [LM66200 data sheet, product information and support | TI.com](https://www.ti.com/product/LM66200)
- [LM66200DRLR | DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/LM66200DRLR/15856663) — direct-fetched pricing table, 2026-07-02
- [MAX40203 datasheet | Analog Devices](https://www.analog.com/media/en/technical-documentation/data-sheets/max40203.pdf)
- [MAX40203AUK+T | Mouser](https://www.mouser.com/ProductDetail/Analog-Devices-Maxim-Integrated/MAX40203AUK+T)
- [TPS25947xx eFuse datasheet | TI.com](https://www.ti.com/lit/ds/symlink/tps25947.pdf)
- [TPS25947 data sheet, product information and support | TI.com](https://www.ti.com/product/TPS25947)
- [TPS212x Priority Power MUX datasheet | TI.com](https://www.ti.com/lit/ds/symlink/tps2121.pdf)
- [TPS2121RUXR | LCSC](https://www.lcsc.com/product-detail/C485916.html)
- [TPS2595xx eFuse datasheet | TI.com](https://www.ti.com/lit/ds/symlink/tps2595.pdf)
- [TPS25940 data sheet, product information and support | TI.com](https://www.ti.com/product/TPS25940)
- [TPS25940LRVCR | DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TPS25940LRVCR/4915502) — direct-fetched pricing table, 2026-07-02
- [Redundant power supplies and in-field testing (US Patent 10613154)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10613154)
- [Vishay 196 HVC Energy Storage Capacitors Technical Note](https://www.vishay.com/docs/28444/embcharg196hvc.pdf)
- [Current Consumption Measurement of Modules - ESP32-S3 — ESP-IDF Programming Guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/current-consumption-measurement-modules.html)
- [Introduction to the PMBus](https://pmbus.org/wp-content/uploads/2017/07/introduction_to_pmbus.pdf)
- [Winbond W25Q128JV datasheet (RevH)](https://www.winbond.com/resource-files/W25Q128JV%20RevH%2003102021%20Plus.pdf) — page-program/sector-erase timing figures in this report are order-of-magnitude industry norms, marked [unverified] pending a clean primary-source AC-characteristics extraction

---

**Files referenced (internal, not web sources):** `/home/user/CEC-Platform/docs/enterprise-requirements/hub-enterprise-requirements.md`, `/home/user/CEC-Platform/docs/enterprise-mc-requirements-plan-2026-07-01.md`, `/home/user/CEC-Platform/CEC-Platform-Ground-Truth-Spec.md` (§2.9, lines 255–336), `/home/user/CEC-Platform/docs/owner-queue.md`, `/home/user/CEC-Platform/CLAUDE.md` (action item 0, §2.9 prototype).
