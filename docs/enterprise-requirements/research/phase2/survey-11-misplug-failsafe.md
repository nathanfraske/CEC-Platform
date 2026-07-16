# Survey 11: Module-port mis-plug fail-safe (REQ-HUB-COMMON-110 / REQ-MOD-COMMON-053)

## Scope and framing

REQ-HUB-COMMON-110 and REQ-MOD-COMMON-053 are mirror requirements: either end of a module-to-Hub cable run can be the "exposed" end in a real mis-plug (a tech could plug a live cable straight into a Hub port with no module attached, or into a module's own jack with the Hub end disconnected), so **both ends need independent, full protection** — you cannot rely on "the other end will clamp it." Everything below is designed on that assumption.

A structural fact drives the whole analysis: the CEC pin table (`CLAUDE.md` / spec §2.2) is wired in literal T568B pin/color order, so a standard patch cable maps CEC's own DC pinout directly onto the Ethernet/PoE pair structure:

| Ethernet pair | Pins | CEC function | Used by 10/100BASE-T | Used by 1000BASE-T | PoE Alternative |
|---|---|---|---|---|---|
| Pair 2 (orange) | 1, 2 | VCC (+5VSB) / GND | Yes (data) | Yes | **Alt A leg 1** |
| Pair 3 (green) | 3, 6 | CAN1_H / CAN1_L | Yes (data) | Yes | **Alt A leg 2** |
| Pair 1 (blue) | 4, 5 | 100BASE-T1 (new) | No | Yes | **Alt B leg 1** |
| Pair 4 (brown) | 7, 8 | reserved / DETECT | No | Yes | **Alt B leg 2** |

This is the reason the consumer §2.4 rationale ("misuse, not accident," internal-only jack) doesn't transfer to ENT-NET: REQ-HUB-COMMON-110 correctly identifies that a real Ethernet jack on the same faceplate makes this foreseeable, not deliberate.

## (a) Per-pin current-path table

PoE common-mode fact that matters throughout: in Alternative A/B, **both wires of a pair are driven to the same DC potential together** (center-tap injection) — the differential PHY/CAN signal rides on top. So a "leg" fault moves both its pins together; the fault differential appears *between* the two pair-groups, not within one pair.

| Scenario | Pins driven | What the unprotected (as-drafted) baseline does | First thing that breaks |
|---|---|---|---|
| Non-PoE 10/100BASE-T switch | Pair2(1,2)/Pair3(3,6) carry ~1–2 Vpp transformer-coupled AC; Pair1(4,5)/Pair4(7,8) idle | Switch's weak AC rides on our VCC/CAN pins; **simultaneously our own pin1 5VSB source drives DC current into the switch's transformer center-tap/bias network** — a reverse hazard (us→them), not them→us | Likely benign both ways; energy is too low to matter. Worth a bench check that we don't upset the switch port, but not a safety case. |
| Non-PoE 1000BASE-T switch | All 4 pairs active, PAM-5 ~1 Vpp | Same as above, plus weak AC now also appears on T1 pins (4,5) and pin 7/8 | DETECT ADC may transiently misread; benign energy-wise |
| **PoE Alt-A, polarity 1**: {1,2}=+57V, {3,6}=return | Pin1 (VCC) and pin2 (GND) common-moded to +57V relative to the {3,6} leg | 57V forced onto pin1 with **no per-port element in the current BOM-C baseline** ("Per-port 5VSB distribution... no per-port limiting populated by default"). It back-feeds the *shared* +5VSB rail — all 8 ports, hold-up caps, LDOs, not just the offending port | Bulk/decoupling caps on the 5VSB rail (rated ~10–16V) fail (dielectric breakdown) in milliseconds; cascades toward every LDO fed from that rail |
| **PoE Alt-A, polarity 2**: {1,2}=return, {3,6}=+57V | CAN_H/CAN_L common-moded to +57V | Hits TJA1051T/3's bus pins | **Survives** — within its ±58V DC-limiting rating (verified §f below). This is the one fault mode the as-drafted design already tolerates. |
| **PoE Alt-B / always-on passive injector**, either polarity: {4,5}=±57V, {7,8}=return | Pin4/5 (100BASE-T1 MDI, PHY TBD survey 10) get full 57V DC, no series element exists yet | Straight onto the T1 PHY's MDI die pins | PHY die overvoltage — automotive Ethernet PHYs are NOT rated for tens of volts directly on the pin (see §e); likely instant failure, possibly propagating into the PHY's own VDD rail |
| PoE Alt-B / passive injector (cont.) | Pin 7 (reserved) + pin 8 (DETECT) get full 57V DC | Bare PESD5V0S1BA (an ESD-only part) tries to clamp; with no series limiting, fault current is bounded only by the injector's own source impedance (could be low — see below) | PESD5V0S1BA fails, almost certainly shorted, in well under a second; whatever is behind it (10k pullup/ADC on the Hub, code resistor on the module) then sees near-full fault voltage |

Two structural notes that shape the fix:
1. **Pin1's exposure is asymmetric by role.** The Hub *sources* +5VSB (current normally flows Hub→pin1); the module *sinks* it (pin1→LDO). A plain series diode blocks *reverse* current — which is exactly what's needed on the Hub side (fault voltage exceeds the Hub's own rail, driving current backward, which a diode blocks) but does **nothing** on the module side, because the 57V fault pushes current in the *same* direction a diode is built to pass. This is the crux of why item (b) needs two different answers.
2. **GND (pin2) is not floating.** Both Hub and module boards are chassis-grounded (M3 mounts), and the chassis is earthed through the PSU cord. Under the Alt-A polarity-1 fault, pin2 fights a stiff PoE source against a (usually) low-impedance earth bond — in practice this mostly pins GND near earth and pushes the full differential onto pin1, which is what the protection network below assumes. Note in passing: this makes the PC's earth bond an unintended high-current return path during the fault — a facilities-level side effect, not a component-damage one.

## (b)–(d) Recommended protection network

### Hub side (×8 ports)

| Node | Recommendation | MPN | Price @100q | Why |
|---|---|---|---|---|
| Pin 1 (VCC) | Series blocking Schottky, cathode-to-pin/anode-to-rail (reverse-blocks backfeed into the shared +5VSB rail) | **SS110** (100V, 1A, SMA/DO-214AC), MDD or similar | ~$0.01–0.02 | Not SS16: SS16 is 60V-rated against a 57V worst case — ~5% margin, too thin once temperature-derated leakage is considered. SS110 gives ~75% headroom for the same DO-214AC footprint and ~$0.01 more. MDD is already a qualified platform vendor (D_AUX=SS14 in BOM-C), so this reuses an existing supplier relationship. Forward drop (~0.5–0.6V at our ~0.1–0.5A/port load) is a non-issue against the $/port budget and doesn't meaningfully touch the 5VSB headroom question the consumer-tier rationale worried about. |
| Pin 1 (VCC), supplementary | 58V-standoff TVS across pin-to-GND, ahead of the diode | **SMAJ58A** (58V, 400W, DO-214AA/SMA) | ~$0.02–0.04 | Does **not** actively clamp the *accepted* 57V worst case (58V standoff sits essentially at that number by design) — its job is the tail risk: transients above 57V (hot-plug make/break, a slightly out-of-spec injector, coupled surge). It is a secondary hardening layer, not the primary defense; the diode is the primary defense. |
| Pin 8 (DETECT) | Series resistor ahead of the existing 10k pullup + PESD5V0S1BA + ADC tap | ~10 kΩ 1% 1206, e.g. Yageo/UNI-ROYAL family already qualified on this platform | ~$0.01 | See worked sizing below. |
| Pin 7 (reserved) | 1 MΩ bleed resistor to GND + a 60V-class TVS (can share the SMAJ58A part number) | 1MΩ 0402 (reuse platform resistor family) + SMAJ58A | ~$0.03–0.05 | Satisfies REQ-110's "pin 7 needs a defined ≥60V-tolerant termination" literally: gives a defined discharge path (not a truly floating node, which has no bound on transient ring-up) while drawing negligible current in both normal operation (57V/1MΩ = 57µA) and the accepted 57V fault. Compatible with the spec's existing "pin 7 stays reserved" posture and with the still-open 1-Wire-return exploration if it's ever adopted. |
| Pins 4/5 (100BASE-T1) | CMC + series coupling caps (≥100V) + automotive-Ethernet ESD/TVS | See §(e) | See §(e) | Feeds survey 10. |

### Module side (×1 per module board — pin1 needs an *active* answer, not a diode)

| Node | Recommendation | MPN | Price @100q | Why |
|---|---|---|---|---|
| Pin 1 (VCC), ahead of the LP5907-class LDO | **Active 60V eFuse/OVP load switch**, OVP threshold set ~6.0–6.2V (comfortably above nominal 5V + rail tolerance, comfortably below the LDO's abs-max input) | **TPS26621DRCT** (TI, 60V/800mA industrial eFuse, integrated input+output reverse-polarity protection, programmable OVP, **auto-retry**) | **$2.07** [verified, DigiKey 100q break] | This is the one place a passive diode structurally cannot work (see §a note 1: the fault is *forward*-direction relative to the module's normal current flow, so a diode passes it straight through). An active switch that measures voltage and opens the path is the only element that blocks an overvoltage regardless of direction. TPS2662x's RDS(on) is on the order of several hundred mΩ (~478 mΩ per a secondary listing — confirm at datasheet pull), giving a modest ~0.15–0.25V drop at our ~0.3–0.5A load, similar order to a diode but with a real voltage-threshold cutoff instead of just a fixed forward drop. **Auto-retry is the load-bearing feature**: REQ-MOD-COMMON-053/REQ-HUB-COMMON-110 both require "self-recovering... no sacrificial elements requiring field repair" — this explicitly rules out a one-time fuse, and TPS2662x's auto-retry satisfies it directly (it re-tries on its own timer once the fault clears; no part swap, no latch requiring a power cycle by policy). |
| Pin 1, lower-cost fallback (not recommended as primary) | Series R + zener/low-V TVS crowbar + PTC | e.g. a ~6V-class TVS + **Bourns MF-NSMF** family PPTC (60V-rated, 1206) | PTC ~$0.05–0.15 [directional; confirm exact 60V-rated SKU — the platform's existing PPTC candidate `SMD0805-050/06N` is a **6V-rated part**, not usable here without swapping to a 60V-coded sibling] + TVS ~$0.05 | Cheaper (~$0.15–0.25 vs $2.07) but the PTC's trip dynamics (thermal, seconds-scale, temperature- and aging-dependent) give messier, less deterministic pass/fail behavior for the injection bench test than a clean voltage-threshold eFuse, and it leaves a standing resistance in the normal power path (PTC hold resistance, ~0.5–4Ω) that also eats headroom. Given each module needs only *one* of these (not ×8 like the Hub ports), the ~$2 delta is a rounding error against module BOM targets ($32–99) — **recommend TPS2662x as primary** for the cleaner, testable behavior; record the PTC/zener path as an owner-selectable cost-down if margin pressure ever bites. |
| Pin 8 (DETECT) | Mirror of the Hub-side treatment: series R ahead of the module's own PESD5V0S1BA + code resistor | Same family as Hub | ~$0.01 | REQ-MOD-COMMON-053 itself already anticipates this: "DETECT carries the module's code resistor (series element ahead of it)." |
| Pin 7 | Same bleed-R + TVS as Hub | Same | ~$0.03–0.05 | Symmetric treatment |
| Pins 4/5 (100BASE-T1) | Same CMC+caps+TVS network, **streaming families only** (EPS/PCIe/12VHPWR-Std per REQ-MOD-COMMON-003); 24-pin stays CAN-only with pair 2 terminated per the locked table and needs only a voltage-tolerant passive termination, not a PHY-protection stack | See §(e) | See §(e) | Don't over-build the non-streaming family. |

### (c) DETECT hardening — worked sizing

Today's topology (confirmed against the locked §2.3 formula, `V = 3.3V × Rcode/(10k+Rcode)`, which reproduces the spec's exact numbers: 2.2k→0.595V, 4.7k→1.055V, 10k→1.650V): a bare PESD5V0S1BA sits directly on pin 8 with no current-limiting. Nexperia's datasheet gives it a peak-pulse rating (130W @ 8/20µs) but **no continuous-power rating at all** — it is sized for a single ESD event, not sustained conduction, matching the design context's own flag.

Adding a series resistor **R_s** between the RJ-45 pin and the [pullup/code-resistor + clamp] node limits fault current into the clamp, at the cost of also becoming part of the normal-operation divider (so the §2.3 threshold table shifts and must be recomputed/recalibrated in firmware — this is fine, since the table is entirely software-compared against an ADC reading, not a hardware comparator).

Illustrative sizing at R_s ≈ 10 kΩ (Hub side, added in series with the existing 10k pullup, so total = 20k):
- **Fault case**: assuming the clamp holds its node somewhere in its ~6–14V clamp range against the 57V fault, current through R_s ≈ (57−6 to 14)/10k ≈ 4.3–5.1 mA, dissipating ≈ 0.19–0.26W in R_s — fits a 1206 (0.25W) resistor with modest margin, and drops the clamp's own continuous dissipation to tens of mW (comfortably within a SOD-323's steady-state limit, unlike the present bare-pin case).
- **Recomputed code table** (total 20k): 2.2k→0.367V, 4.7k→0.634V, 10k→1.10V, 22k→1.716V, 47k→2.331V — still monotonic, still several hundred mV apart (plenty of margin for an 8-bit-class ADC at ~13mV/LSB over 3.3V), still fully in range.

The exact final R_s (I'd bracket it 4.7k–20k) trades off fault-case power dissipation against how much it compresses the low end of the code table, and depends on the actual clamp part and ADC accuracy budget chosen at schematic capture — **this is a schematic-capture/bench-calibration task, not something to lock at survey level**; the table above is illustrative of the approach and magnitude, not a final value. The same treatment (series R ahead of the code resistor + clamp) applies symmetrically on the module side per REQ-MOD-COMMON-053's own text, and the combined Hub+module series resistances feed into one recalibrated firmware table.

## (e) 100BASE-T1 pair (4/5) — note for survey 10

Automotive 100BASE-T1 PHYs (DP83TC81x, 88Q211x, LAN887x, TJA110x) are **not** rated to survive tens of volts directly on the MDI die pins — their "automotive fault tolerance" reputation comes from the *external* harness network conventionally built around them, not from the silicon surviving a direct short-to-battery on the pin. The standard automotive-Ethernet pattern (confirmed via TDK/NXP/Nexperia OPEN Alliance material) is:

**RJ-45 pin → common-mode choke (passes DC through — CMCs don't block DC, only common-mode AC noise) → series AC-coupling capacitor per line, ≥100V-rated → PHY MDI pin → PHY-side ESD/TVS.**

The coupling capacitors are the actual DC-fault-blocking element (a series cap blocks continuous DC on *either* conductor regardless of whether the fault is common-mode (passive-injector Alt-B) or differential); the CMC only handles noise; a PHY-side TVS handles ESD/EOS on the now-protected PHY node.

Real, sourced parts for this network:
- **CMC**: **TDK ACT1210L-201-2P-TL00**, OPEN Alliance 100BASE-T1-compliant, LCSC C131444, **$0.376@100q [verified LCSC]**.
- **PHY-side ESD/TVS**: **Nexperia PESD2ETH100-T**, purpose-built for automotive Ethernet in-vehicle networks, trigger voltage V_t1 = 100V min (i.e., it does *not* activate below 100V, so it stays inert through the accepted 57V fault and only intervenes on genuine overshoot), Cd < 3pF (won't load the 100Mbit signal). Price **[unverified — not confirmed in this session, estimate $0.05–0.15 based on comparable Nexperia small-signal automotive ESD parts; confirm at RFQ]**.
- **Coupling caps**: ≥100V-rated C0G/NP0 ceramic, small value (industry designs commonly land in the 1–100nF range). **Exact value is PHY-specific** (must pass the 100BASE-T1 signal band without excess attenuation while blocking DC) — **this is explicitly survey 10's to pin down against the chosen PHY's application note** (e.g., TI's SNLA389-series app notes for DP83TC81x) once that PHY is selected; flagging here as [unverified] rather than guessing a number.

This network needs to exist on **both** the Hub's 8 ports and each streaming module (EPS/PCIe/12VHPWR-Std), i.e., 8× on the Hub, 1× per streaming-module board — feeds directly into survey 10's BOM (module-ent-spec-sheets.md currently carries "$2–4/module [unv, survey 10]" for "the T1 PHY adder," which per this survey should read as *PHY + this protection network* combined, not the PHY alone).

## (f) CAN pins — TJA1051T/3 confirmed

Pulled the NXP datasheet content directly (via a text-rendered mirror of the same NXP PDF, since the raw PDF didn't extract cleanly): Table 1 (Quick reference data) lists **V_CANH / V_CANL = −58 V to +58 V, "no time limit; DC limiting value"** — this is explicitly a **continuous DC** rating, not a transient/ESD-only spec (ESD is separately rated at ±8kV per IEC 61000-4-2). This directly confirms the CLAUDE.md/spec §2.4 note that flagged this as needing datasheet confirmation ("confirm the exact fault and ESD ratings against the TJA1051T/3 datasheet") — **it checks out**. One caution for the record: a lower-quality secondary source turned up a conflicting "−27V to +40V" figure, which is very likely a confusion with the older, non-"T/3" **TJA1050** predecessor (a real, different part with that lower rating) — don't let that figure leak into any BOM note.

## (g) Compliant-PSE detection finding

IEEE 802.3af/at detection: the PSE probes with 2.7–10.1V test voltages and computes an apparent resistance. A valid PD signature is 25kΩ (±~1.25kΩ strict / 19–26.5kΩ acceptance band); **the PSE is required to reject as invalid anything ≤~15kΩ (treated as a short-circuit fault) or ≥~33kΩ (treated as open/no PD)**, and also rejects excess signature capacitance.

Our port's Alt-A leg 1 (pins 1,2) presents a **low-impedance, actively-driven ~5V rail with bulk capacitance** — not a resistor at all. Probed at 2.7–4V (below our rail), a stiff regulator fights the probe, reading as a very-low/out-of-range apparent resistance (short-circuit-like → reject). Probed at 10.1V (above our rail), a typical LDO/regulator has little or no sink capability, so the node doesn't behave like a resistive load either (also anomalous/reject-range). **With the recommended per-port blocking Schottky added**, the picture gets cleaner still: at low probe voltages the diode is reverse-biased relative to our own rail, presenting near-open (reject as "no valid PD"). Net finding: **a compliant PSE is very likely to reject this port and never apply full power on the Alt-A leg** — consistent with independent industry guidance found in this research ("active/compliant PoE injectors are safe and will not send power to a non-PoE device; passive injectors can damage a non-PoE device because they deliver power without checking compatibility").

Two important caveats, both already correctly reflected in REQ-HUB-COMMON-110's own wording:
1. This is reasoned from general 802.3 detection principles applied to our topology, not a spec clause written for "device with an active regulator on the pins" — **treat it as a corroborating finding, not the safety mechanism**, and confirm empirically per item (h).
2. **Passive injectors skip detection entirely by definition** ("no detection handshake") — this is exactly why the requirement text already frames passive injectors as the binding worst case regardless of the detection-phase finding above. Nothing in this finding should be read as license to relax the physical protection network in (b)–(e).

## (h) Injection test procedure (draft)

**Sources needed**: (1) compliant 802.3af PSE, (2) compliant 802.3at PSE, (3) compliant 802.3bt Type 3/4 PSE if available, (4) passive 24V injector, (5) passive 48V injector, (6) passive ~56–57V injector (bench supply configured with no handshake — worst case), (7) a plain non-PoE 10/100/1000BASE-T switch port (baseline signaling-compatibility check).

**DUTs**: at least one Hub port (populated with the recommended network) and one representative module per family — at minimum one streaming family (EPS or PCIe, carrying the T1 network) and the 24-pin (non-streaming, simpler exposure).

**Procedure per source**:
1. Both polarities where physically distinguishable (trivial for passive injectors — swap leads/use a crossover fixture; for compliant PSEs, test equipment/breakout that allows polarity selection, or accept the PSE's own convention if not selectable and note it).
2. Instantaneous exposure first (does anything visibly fault in the first seconds), then **sustained exposure** — recommend 60 minutes continuous — to catch slow thermal failure a short pulse test would miss (this is the realistic "left plugged in overnight" case).
3. Instrumentation during exposure: current probes on pins 1, 3, 6, 4, 5, 7, 8; thermal imaging on every protection component (catches an under-margined part running hot before it fails outright); scope capture of the DETECT ADC node and the CAN bus to characterize alarm response time.
4. Also run the plain non-PoE switch case as a baseline "no damage, and firmware correctly flags an unrecognized device rather than misreading it as a valid module class" check.

**Pass criteria** (must all hold):
- No visible or measurable component damage, before or after the sustained exposure.
- Each protection element behaves within its intended envelope (diode holds off reverse current; eFuse trips and reports fault via its status pin; TVS/clamp conducts only for genuine over-threshold excursions, not during the accepted 57V steady state).
- The anomalous condition is **detected, alarmed, and logged** within the platform's bounded/debounced alarm window (REQ-HUB-COMMON-050's language) — via the DETECT-code-mismatch path and, for CAN-pin stress cases, corroborated by the existing bus-state monitor (REQ-HUB-COMMON-054 error-passive/bus-off alarm is a natural second signal here, not a new mechanism to build).
- **Full function restored, unattended, after fault removal** — this is the crux of "self-recovering, no sacrificial elements": re-plug a real CEC module post-test and confirm DETECT-code read, CAN comms, and (streaming families) 100BASE-T1 link-up all succeed with no manual intervention, no part swap, no power-cycle-only recovery being silently required.
- **Repeat the full cycle 5–10× on the same physical unit** — a part that survives once but degrades on repeated exposure would violate the intent even if a single-shot test "passes."

This test is a natural extension of the fault-injection/FMEA work REQ-MOD-COMMON-031 already requires for in-path power elements — worth running as one combined program rather than two.

## (i) Cost roll-up @100q

| Side | Item | Qty | Unit | Extended |
|---|---|---|---|---|
| Hub (×8 ports) | SS110 series Schottky (pin1) | 8 | ~$0.02 | ~$0.16 |
| Hub | SMAJ58A supplementary TVS (pin1) | 8 | ~$0.03 | ~$0.24 |
| Hub | DETECT series R (pin8) | 8 | ~$0.01 | ~$0.08 |
| Hub | Pin7 bleed-R + TVS | 8 | ~$0.06 | ~$0.48 |
| Hub | T1 network: CMC + caps + TVS (×2 lines/port) | 8 | ~$0.376+~0.10+~0.10 ≈ $0.58 | ~$4.60 |
| **Hub total adder** | | | | **≈ $5.6/hub** (on top of BOM-C's existing $14.14 baseline) |
| Module, streaming family (EPS/PCIe/12VHPWR-Std) | TPS26621DRCT (pin1 OVP) | 1 | $2.07 | $2.07 |
| Module | DETECT series R + pin7 bleed/TVS | 1 | ~$0.08 | ~$0.08 |
| Module | T1 network (1 port only) | 1 | ~$0.58 | ~$0.58 |
| **Streaming-module adder** | | | | **≈ $2.7/module** |
| Module, 24-pin (non-streaming) | TPS26621DRCT + DETECT/pin7 (no T1 network) | 1 | — | **≈ $2.15/module** |

All trivial against the $32–99 per-module BOM targets and the Hub's existing ~$14.14 subsystem-C baseline. The T1-network unit prices ($0.376 CMC verified; TVS and coupling caps directional/unverified) are the main open pricing item, appropriately deferred to survey 10 alongside the PHY pick itself.

## REQ text refinements (proposed, not applied)

1. **REQ-HUB-COMMON-110 / REQ-MOD-COMMON-053**: consider appending a parenthetical to the "self-recovering... no sacrificial elements" clause: *"(a resettable PPTC or an auto-retry active current-limiter satisfies this; a one-time/non-resettable fuse does not)"* — closes a real ambiguity this survey had to reason through from first principles, and rules out what might otherwise look like the obvious naive answer.
2. **REQ-MOD-COMMON-053**: the per-family scope of the T1-pair network is currently implicit. Recommend an explicit sentence: *"The 100BASE-T1 external protection network (CMC + coupling caps + TVS) applies only to streaming enterprise families that carry the REQ-MOD-COMMON-003 100BASE-T1 PHY; the 24-pin (non-streaming) family's pair-2 termination needs voltage-tolerant passive termination only, not the full PHY-protection network."* Prevents a future implementer from either over-building 24-pin or under-building a streaming family.
3. No change needed to the "passive injectors are the binding worst case" framing — it's already correctly stated, and this survey's compliant-PSE finding (§g) independently supports treating it as secondary, not primary, protection.
4. No change needed to the CAN-pin baseline claim — this survey confirms ±58V is a genuine continuous-DC datasheet rating, not an assumption.

## Feeds:

- **REQ-HUB-COMMON-110**: current-path table (a), Hub-side protection network (b–d), compliant-PSE finding (g), test procedure (h).
- **REQ-MOD-COMMON-053**: module-side protection network (b–d), per-family T1-network scoping note.
- **Survey 10 (100BASE-T1 PHY)**: §(e) in full — the CMC/coupling-cap/TVS network is a hard input to the PHY pick (coupling-cap value must be validated against whichever PHY's characterized signal band; the DP83TC81x-class candidates need their exact MDI abs-max ratings pulled once the PHY is chosen, since this survey could not confirm that number from public datasheet snippets); the "$2–4/module T1 adder" placeholder in `module-ent-spec-sheets.md` should be read as PHY + protection network combined, not PHY alone.
- **BOM-C / module BOMs**: cost adders in (i); TPS26621DRCT, SS110, SMAJ58A, TDK ACT1210L-201-2P-TL00 are ready to drop into `bom-c-module-if-base-secio.md` §1 and the per-family module BOMs; the PESD2ETH100-T price and the coupling-cap value/rating remain open pending survey 10.

## Sources

Internal (repo):
- `docs/enterprise-requirements/hub-enterprise-requirements.md` — REQ-HUB-COMMON-110, -040/-042/-043/-054
- `docs/enterprise-requirements/module-requirements-common.md` — REQ-MOD-COMMON-053, -003
- `docs/enterprise-requirements/spec-sheets/bom-detailed/bom-c-module-if-base-secio.md` — current unprotected baseline, DETECT/CAN part numbers and prices
- `docs/enterprise-requirements/spec-sheets/bom-detailed/hub-ent-bom-detailed.md`, `module-ent-spec-sheets.md` — survey-10-pending placeholders
- `CEC-Platform-Ground-Truth-Spec.md` §2.3, §2.4 — DETECT code table, consumer PoE rationale and its own flagged TJA1051T/3 confirmation gap

External:
- [TJA1051.pdf — NXP official datasheet](https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf) (Table 1 quick-reference data, V_CANH/V_CANL −58 to +58V DC limiting value, read via [datasheet.live mirror](https://pdf.datasheet.live/624ef4d3/nxp.com/TJA1051T,118.html) due to raw-PDF extraction failure)
- [PESD5V0S1BA — Nexperia datasheet](https://assets.nexperia.com/documents/data-sheet/PESD5V0S1BA.pdf)
- [PESD2ETH100-T — Nexperia product page](https://www.nexperia.com/product/PESD2ETH100-T)
- [LP5907 — TI datasheet via Mouser mirror](https://www.mouser.com/datasheet/2/405/lp5907-489602.pdf) (abs max VIN = 6V)
- [TPS2662x — TI datasheet](https://www.ti.com/lit/ds/symlink/tps2662.pdf); [TPS26621DRCT — DigiKey pricing](https://www.digikey.com/en/products/detail/texas-instruments/TPS26621DRCT/9597840) ($2.07@100q verified)
- [SS110 — LCSC listings](https://www.lcsc.com/product-detail/Schottky-Barrier-Diodes-SBD_SS110_C2482.html); [SMAJ58A — LCSC](https://lcsc.com/product-detail/ESD-and-Surge-Protection-TVS-ESD_Shikues-SMAJ58A_C499822.html); [SMBJ58A — LCSC](https://www.lcsc.com/product-detail/TVS_Littelfuse_SMBJ58A_SMBJ58A_C157526.html)
- [TDK ACT1210L-201-2P-TL00 — LCSC](https://www.lcsc.com/product-detail/Common-Mode-Chokes-Filters_TDK_ACT1210L-201-2P-TL00_TDK-ACT1210L-201-2P-TL00_C131444.html); [TDK 100BASE-T1 EMC/CMC application note](https://product.tdk.com/en/techlibrary/applicationnote/automotive-ethernet.html)
- [DP83TC814x-Q1 datasheet](https://www.ti.com/lit/ds/symlink/dp83tc814r-q1.pdf); [DP83TC812/813/814 configuration application note](https://docs.ampnuts.ru/ti.com.datasheet/DP83TC814R-Q1/Application_note_SNLA389A.PDF)
- [LM74610-Q1 — TI ideal-diode controller datasheet](https://www.ti.com/lit/ds/symlink/lm74610-q1.pdf) (evaluated, not recommended — see §b)
- [Bourns MF-NSMF PPTC series](https://www.bourns.com/products/circuit-protection/resettable-fuses-multifuse-pptc/product/MF-NSMF)
- [Power over Ethernet — Wikipedia](https://en.wikipedia.org/wiki/Power_over_Ethernet) (PSE voltage/current tables, detection signature 19–26.5kΩ)
- [Understanding the IEEE 802.3af Standard — Phihong](https://www.phihong.com/understanding-the-ieee-802-3af-standard-basics-of-power-over-ethernet-poe/); [802.3af/at/bt overview — Phihong](https://www.phihong.com/802-3af-at-and-bt-exploring-active-power-over-ethernet-ieee-standards/)
- [Can the PoE Injector damage other equipment? — Ubiquiti community](https://community.ui.com/questions/Can-the-PoE-Injector-damage-other-equipment/5b46a6e8-dc51-40f4-8a5c-7bbc2998f8ef); [Can a PoE injector damage a non-PoE device — benchu-group](https://www.benchu-group.com/can-a-poe-injector-damage-a-non-poe-device); [AN1281 — Skyworks, Protecting PoE PD Designs against Non-Standard PoE Injectors](https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/an1281-injector-protection.pdf)

**[unverified]** items flagged inline: PESD2ETH100-T exact price; T1 coupling-cap exact value/rating; TPS2662x exact RDS(on) (a secondary listing suggested ~478mΩ, not confirmed against the primary datasheet table); 60V-class PPTC exact SKU/price for the module-side fallback path.
