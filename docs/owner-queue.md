# Owner queue — the standing, maintained list

**Contract:** everything here requires the OWNER (decisions, owner-only data, physical
bench, GitHub rituals, GUI board work). Agents keep this file current in the same change
that creates or retires an item — same discipline as the CLAUDE.md action items. Each
item: what / why it blocks / where recorded / queued date. Sections by kind so a free
half-hour can be spent on the right shape of work.

_Last reconciled: 2026-06-10 (the corpus-intake + cluster-5/6 + ratification-batch sessions)._

---

## 1. Decisions to make (framework decisions, ask-before-building)

| # | Decision | Blocks | Recorded |
|---|---|---|---|
| — | **SCHEMATIC MCP + DRAFTING IMPROVEMENT BACKLOG (2026-07-22, three codex audits reconciled)**: docs/schematic-mcp-improvement-plan-2026-07-22.md — B's 13-verb semantic roadmap (P0 atomic replace_components + verify_restricted_diff + pin_net_map; transaction-model prerequisite + _gated() defects to fix regardless), C1's 9-step readability/tuning ladder (atomic pipeline, orient_power_glyphs, body-aware normalize_fields, wrap/fit + bounds gates — calibrated per the charter, teeth plans included), A's structural queue (tester real-hierarchy, sheet-bounds; the rank-1 multiple_net_names electrical finding already FOLLOWUPS'd + verified). RULING: GO/priority on the §4 execution order (or slices). Full reports build/codex-*.out. | agent autonomy on schematic edits; prettier generated sheets | docs/schematic-mcp-improvement-plan-2026-07-22.md |
| — | **MEZZ MOUNTING SCHEME — STRUCTURAL SEGMENTED MEZZ (2026-07-22)**: owner riff ("split the mezzanine into 2-3 segments and have the stability derive from that") engineered in docs/mezz-structural-segments-2026-07-22.md. RECOMMENDED R1: split J6 into three KEYED THT segments (J6P 2x3 power / J6C 2x4 comms / J6D 2x2 ID, from the netlist-verified 16-pin map) that ARE the mounts — zero screws, same ~65x30 support triangle, >20x static retention margin, keying free via distinct sizes; deletes H1-H3 + shrinks the J6 field (both MEASURED refusal classes: C1|H1 + J6|U10 fired on the 2026-07-22 prop wave); disperses the 16-net right-flank funnel named in the routing-hardness attribution. R2 fallback = same + ONE provisioned M2 (DNP-able land, no respin). M2-at-4-corners answered: M2 size fine, corners physics-blocked (all four 24-pin edges owned — J3/TB/jacks/J6). ONE bench gate: peel/shake on a mated sample. RULING NEEDED: R1 vs R2-provisioned vs keep-screws; on GO the implementation is ~1 session (segment split absorbs the owed no-flip pin-map re-verification). | next mezz/placement wave on the new contract; the owed pin-map re-verify | docs/mezz-structural-segments-2026-07-22.md |
| — | **BGA-READINESS FUNDING ORDER (2026-07-23, owner: "multi-BGA boards coming up, something's gotta give")**: plan in docs/pipeline-solver-roadmap.md §BGA-READINESS. Recommended A+B: a deterministic BGA fanout/escape GENERATOR (locked copper pre-FR, the authored-cell pattern generalized) + escape-aware placement terms; C = router re-evaluation (FR-2.x fork surgery / IPC-API / commercial benchmark) trails A/B; D = 6-layer stackup+DRU authoring prereq (blind/buried via class = spec-level ruling). RULING: fund A+B now vs a different order; name the first target board (hub-pro P4? ENT PolarFire capture board?). | ENT ~2026-08 customer clock; hub-pro/P4 boards | docs/pipeline-solver-roadmap.md §BGA-READINESS |
| — | **STANDARD-TIER DEMAND + ALPHA/BETA LINE (owner, 2026-07-03)**: real purchase demand for the Standard tier NOW; ENT presents to the prospective customer **~2026-08 (one month)** — this puts a REAL CLOCK on the f1 dev-kit + TC-silicon order (demo rig lead times must fit inside the month; order soon or the demo slips). Consumer revision convention RATIFIED: existing validated prototypes = ALPHA line (all Standard modules + Hub have working prototypes, concept 100% validated); owner-approved refinements = BETA line, cleanly denoted (Rev field / README / fab naming) — recorded in CLAUDE.md. Standard-tier refinement fan-out COMPLETE (6 reports + synthesis, docs/standard-tier-review/): **the deduped 11-item OWNER DECISION LIST is in SYNTHESIS-beta-plan.md §3** (D-1 kit/cable SKUs, D-2 SKU collapse [PCIe one-board / EPS-1], D-3 mezzanine consumer scope + J6 pinout contradiction, D-4 §6.13/OQ-57 ROI, D-5 24-pin rev3a-vs-full [CRITICAL PATH], D-6 hub items incl. OQ-2, D-7 12VHPWR production bar + pigtail spec, D-8 rev2 erratum consumer disclosure, D-9 pegless-keyed search, D-10 market pull, D-11 USB-C footprint fix [Hub CI red today]); the no-decision hygiene wave W1-W8 proceeds under the beta flag. | beta-line kickoff (awaits owner approval of the refinement plan); demo-rig order clock | CLAUDE.md alpha/beta paragraph; docs/standard-tier-review/ |
| — | **D-5a RULED (owner, 2026-07-04): CONNECTOR DAUGHTERBOARD** for 24-pin/PCIe/EPS output — main board carries an inter-board connector to a stood-up PASSIVE daughterboard (thick copper, no components, does all output pin-mapping so main-board pours are freed from the connector pin field); populated as a MODDIY vertical PCB-mount header OR a soldered pigtail; **sellable daughterboard+extension-cable assembly** (soldered at the through-holes w/ strain relief) = the productized bundle that closes the remaining female-out issues (the 2026-07-03 "order-system bundle" lean in hardware form); chassis provides strain relief (designed in). 12VHPWR unchanged (captive pigtail). KILL-CHECK CLEARED (study landed 2026-07-04): real connectors exist at every family's bar — EPS ~65A/cable target = 3 contacts/polarity, PCIe ~49A = 2, 24-pin easy, on Amphenol PwrBlade / Molex Ten60Power / Hirose MCN51 (PwrBlade+Ten60 rated 30A/contact AT 30°C rise = the repo's own gate condition); study recommends PER-CABLE daughterboards (shared-housing mutual-heating derating, fault isolation, sellable-assembly fit). COST (§8) + GEOMETRY (§8.5) PASSES LANDED — owner right twice ($5 ceiling AND "40/80mm slots are massive"): commodity card-edge ELIMINATED by the footprint gate (~2.4–2.5 A/mm of slot at any pitch vs 3.7–7.2 needed; the §8.4 math was already dual-readout); premium blades $13–26/module (MCN51 OBSOLETE). §8.6 SOURCING PASS (owner-directed) REVISED THE PICKS: **EPS+PCIe = Würth REDCUBE WP-THRBU 74650094 rated terminals** (85A VERIFIED, $2.86@100, in stock; 2/cable + signal stub; ~$12–19/module) — **the load-bearing M3-joint bench item DIES** (→ incoming QC + torque control); **24-pin = pursue HPCE vertical** (~$7–10, one part = power+signals, tool-less, gate CLEARS at real pitch ~7.1A/mm; 2 UNVERIFIEDs: beams/position + right-size SKU supply — orderable-now SKU reads ~144A vs 190A need; hard-gold fingers) w/ REDCUBE 6-point committed fallback; generic M3 demoted to cost-down-after-bench ($2.5–5, bench-gated). HONEST COST: verified-ampacity = $12–19/module vs the ~$5 ceiling — owner picks the trade side per family. §8.8–§8.10 (owner-led catalog work) FINAL LADDER: **HEADLINE = all-Keystone/TE TOOL-LESS BLADE config** — universal 30A clips on the main board (SMT 3586 LCSC C238113 / THT 3557-2 C352820) + TE FASTON .250" tabs on the daughterboard (63849-1 C86469, $0.04) = **$2.7–4.6/module, RATED, tool-less, the ONLY end-to-end JLC-native path** (8197 screw alt = LCSC OOS today; REDCUBE = not carried, DigiKey proto rung; §8.8 blade-kill corrected — was TE-7A-receptacle-bound, Keystone universal clips are 30A). **OWNER SIGN-OFF (2026-07-04): the LCSC blade-config part arc is RATIFIED, conditional only on physical fit ("as long as the tabs and whatnot fit together"); MATING-FORCE gate DISMISSED by owner ruling — high insertion force is a FEATURE (part is not meant to be constantly swapped; mis-seat/pull-out absolutely unwanted). IMPLEMENTATION COMPLETE (2026-07-05): spec v1.4.0 applied; parts vendored+datasheeted; blade interface on all 4 main-board schematics (Rev BETA-2, modeled-delta proven); output-daughterboard projects built + DRC/ERC-clean w/ distinct keying (beta/output-daughterboards/). TAB FORM FINAL (2026-07-05, third form, owner sketch — full chain in blade-fit-check-2026-07-04.md addenda 2-3): **TE 63951-1** (RIGHT-ANGLE FASTON .250, LCSC C591344, in stock, $0.099-0.164/u; in-plane L per TE dwg C=63951) mounted legs-VERTICAL through the standing board's face — blade points STRAIGHT DOWN at a 2.54-8.89mm face standoff and the assembly VERTICAL-DROPS into the main-board 3586 clips' top-entry jaws (clip slot rotated perpendicular to the wall line, centreline 5.72mm off the front face). Board FLOATS 8.4-11mm clear (the tab reaches, not the board; top edge uniform 21.97mm above main board; full 7.16mm jaw engagement). Boards (iteration-4 COMPACT two-band per owner, 2026-07-06 — tabs packed below the pinout at the derived 7.10mm pitch floor: pcie 7.1 / eps 7.6 / atx24 8.4 routing-lattice-aligned): **atx24 72.8x21.4 / eps 43.0x20.0 / pcie 26.3x20.0mm** — the honest compact heights are ~20-21.4mm (the owner-requested number; the ≤15mm cap was owner-relaxed for this form; the 15mm-tall long-sliver iteration-3 variant is retained in git history if height ever outranks length again). Keying survives on pitch differentiation alone at the packed floor (proof margins ≥1.5× the 0.5mm tolerance; teeth re-verified: sabotaged 7.2mm eps pitch correctly fails). Clip row-fit asserted: body gaps 4.58/3.78/3.28mm, pad gaps 1.80/1.00/0.50mm. Float now uniform 12.41mm (leg row 4.34mm above each bottom edge, tip 11.41mm below edge level). Gates re-verified by coordinator (ERC 0, DRC 0/0 severity-error, checker 110 OKs incl. new orientation/uniform-height/clip-fit assertions, keying re-proved w/ teeth, net maps/joint counts 9/6/4 unchanged). Two earlier forms retired: 63849-1 side-entry + the 63951-1 flat-blade mis-model (its 0.27mm hang-shortfall concern is OBSOLETE — the floating-drop geometry never engages the board edge). Pricing notes stand: 63849-1 "$0.04" was stale ($0.0795@100); 63951-1 as above.** REMAINING OWNER ITEMS: (a) SAMPLE ORDER (clips 3586/3557-2 + the NEW flat tabs **63951-1 / LCSC C591344**, ~$20) for the physical FIT CHECK (his stated condition) — the check verifies the FINAL vertical-drop form: (i) the **15.75mm blade-tip chain-dimension reading** from TE dwg C=63951 (flagged by the rework as read-two-ways; a mm either way shifts the float heights), (ii) top-entry drop into the rotated 3586 jaws at the paper margins above, (iii) the 0.84mm-tolerance tab-thickness edge case from the original fit memo + the confirm-soak/contact-R trend (still recommended engineering, no longer sign-off gates); (b) chassis strain-relief numbers (pull/flex) for the enclosure design; (c) procurement: clip stock depth (LCSC 533 < one 900–1,200-clip run) or JLC-library admission before a production run; (d) optional: HPCE samples ($9.15×25, 24-pin tool-less premium) + MODDIY samples (vertical-header population option) — the vertical female headers EXIST (24p/EPS/PCIe 4.2mm, SKU CO261/MIATX-PCB ~$2) but are provenance-UNVERIFIED DIY-category (no MPN/datasheet — same class the prior hunt disqualified under quality-first): prototype-OK per §8.6, sellable BOM needs bench qualification; (e) **ITERATION-6/7 — RULED (owner, 2026-07-06) + IMPLEMENTED same day**: owner ratified the addendum-6 recommendation ("Sure, show me the pitch and everything on the boards", with the orientation requirement that the receptacle's two PCB holes align with the blade's own holes — PROVEN from the rev-E drawing views, checker-asserted). Main-board mate = **TE 63969-1 FASTON .250 PCB receptacle** (vertical top entry, 22.9A @30°C-rise, designed for our 6.35×0.81 blade — thickness at design centre, killing the old #1 thickness fit item; 63968-1 LIF = same-land fallback; LCSC C2961150 stock ~5 = restock watch, DigiKey depth ~$0.30). The 3522 alternative was studied and is DEAD on fit (closed 6.4mm fuse window vs our 6.27–6.43 blade, −0.16 worst; the fuse-blade-format RA tab that would fix it does not exist — Hunt A empty; sourcing was never the issue, LCSC C3204022); Keystone 3557/3586 retired to vendored fallbacks. Joint counts re-ratified at 22.9A/125% (18.32A/joint): **24pin 10 / eps 12 / pcie-2 12 / pcie-3 18** (atx24 GND ×4 = 18.0A = 127% hairline, surfaced and accepted). Boards REGENERATED at pitches 4.2/4.7/5.2 → **atx24 61.0×21.4 / eps 28.5×20.0 / pcie 31.0×20.0mm**; TB swaps + adds landed on all four main-board schematics (netlist-verified; ERC unchanged); gates green (checker 113 OKs incl. orientation assertions). REMAINING SAMPLE ITEMS fold into the (a) sample order, which should now include **63969-1 + 63968-1** with the 63951-1 tabs: (i) the receptacle's UN-DIMENSIONED across-thickness depth (est 3.4–3.7mm; **>4.0mm ⇒ atx24 falls back to 6.3 pitch**) — the new #1 fit item; (ii) detent-hole engagement at the 12.41mm float (retention may be friction-only); (iii) gang insertion force at 10–18 joints (≤26/44N spec max per joint; LIF halves); (iv) the 15.75mm tip-reach chain dim as before. Full record: blade-fit-check-2026-07-04.md addenda 6–7. ITERATION-8 EXPLORATION (owner-directed, 2026-07-06, addendum 8): hunted higher-ampacity/smaller mates across FASTON-world, stamped-receptacle specialists (Zierick 20A THT/25A SMT — both lose net), bigger-blade class (dead: rating doesn't transfer to a half-width blade; no .375 PCB receptacle/tab exists), and housed b2b power re-priced (PwrBlade+-class 30-48A would erase ALL bare-part sample items but stands at $13-26/module, 3-6x the band; mPOWER 18A dead) — VERDICT: STAND PAT, the 63969-1 is the THT stamped-vertical class ceiling AND the tightest floor; no owner action beyond the standing sample list. ITERATION-9 TAB-SIDE STUDY (owner-directed, 2026-07-06, addendum 9; receptacle frozen): straight/SMT tab classes killed in-architecture; the RA table's one live variant = TE 928814-1 (blade 4.3mm shorter -> stack −4.1mm; detent hole lands IN the engagement zone = possible real retention; caveats: ~0.7mm near-wall corner, 0.75–0.85 blade band, loose-piece/DigiKey-only) — RECOMMENDED ADD ~20 pcs to the (a) sample order; PCB-EDGE-FINGER option worked with real numbers (stack ~19mm = −13, −22 tabs/system) but thickness band 0.785–0.835 is UNPASSABLE at catalog fab classes + off-label contact metallurgy -> recorded as the compaction ENDGAME needing a funded bench program AND an owner ruling reversing 'the tab does the reaching, not the board'. Beta line stands pat on 63951-1. ITERATION-10 EDGE-FINGER DEEP-DIVE (owner-directed, 2026-07-06, addendum 10): every addendum-9 kill-condition attacked with verified sources + the repo solver — (i) NEW kill-weight finding addendum 9 missed: fingers force the receptacle 90° from the ratified orientation and its 7.49mm width sets an ~8.0mm row pitch → boards ~91/46/46mm (+50% length) against a real −11.5mm stack win (tops ~22.4/20.9); (ii) thickness 0.785–0.835 band UNPASSABLE at every published class (JLC + PCBWay both ±0.1 at 0.8mm, verified 2026-07-06; the full TE Style-A/B/C SKU table swallows NO standard PCB class; sort-to-band incoming QC at 25–50% EST yield = the only catalog unlock); (iii) conduction PASSES the repo dt_ipc solver (2oz×2 = 5.0°C, 4oz×2 = 1.6°C at the 18.32A policy joint — the interface, not copper, is the gate: 0.34W/joint at spec 1mΩ vs 3.4W worn at 10mΩ); (iv) hard gold at 0.8mm = PCBWay only (30–50µin, but bevel needs ≥1.2mm — soft loss, our tab is square-sheared); JLC fingers = ENIG flash (<10 insertions) though it CAN bevel 0.8 and needs a ≥50mm finger edge (eps/pcie panelize 2-up); (v) THE 4OZ ANSWER: JLC has NO 4oz tier (2-layer outer menu 1/2/2.5/3.5/4.5oz; 4-layer capped 2oz), PCBWay heavy-copper 2-layer 4oz orderable; real $/board is quote-gated from this sandbox — 2-minute owner QUOTE RECIPE in §I.5; net cost ≈ neutral-to-positive (tab+assembly saving $1.3–3.8/board vs EST fab adder $1–11). RECOMMENDATION: DO NOT ADOPT for beta; NO posture re-ruling needed today — OPTIONAL: add the two ~$30–60 COUPONS (§I.7 spec: JLC 0.8 ENIG+goldfinger + PCBWay 4oz hard-gold; thickness-ladder fingers × NPTH-detent variants) to the (a) sample order; they return the delivered-thickness distribution + real invoices, and the posture reversal activates only if they clear the sort-yield + contact bench. FEM/BLADE-INTERCONNECT AUDIT (owner-directed, 2026-07-06, docs/standard-tier-review/blade-interconnect-thermal-2026-07-06.md): the suite now models the blade/receptacle JOINT first-class (TE 63951-1 brass + 63969-1 + <=1mOhm contact, Rth CALIBRATED to TE's own 22.9A/30C-rise rating datum, worn-10mOhm scenario + gate teeth; anchor tests 15/15) — every nominal joint PASSES the 30C policy (worst atx24 GND 18.6C @18A = exactly the ratified 127% hairline; model and margin arithmetic agree). TWO BOARD FINDINGS, owner action needed: **(F1) atx24-out-db DEFECT — the four In2 bus lanes (0.3mm x 1oz) carry the full rail aggregates and are fusing-class** (field-proven: +5V 384mV @30A = 11.5W in one lane, J~2874 A/mm2; +3V3 loses 9% of the rail; 2.5D solve runs away) → REGEN REQUIRED (per-rail pour bands a la eps/pcie or a widened 2oz-outer corridor) before any fab of this board; (F2) eps/pcie daughterboards at the 52/39A worst-case basis dissipate ~1.2-2.8W on ~11cm2 → modeled still-air/no-sink dT 217/117C vs the 30C policy (unmodelled sinks are large; dT~I², half current = ~54-71C) → owner picks: heavier inner copper / area / verified sink / envelope statement — gate on the OQ-86 THERMAL SOAK, which now has model numbers to check against (17.3A -> ~17C, 18.3A -> ~19C, 22.9A -> ~30C, several-mOhm contact = the worn signature). A standing false-pessimism was also fixed (the -12V rail read as a 40A cable net). Ruling: SYNTHESIS-beta-plan.md §3 D-5a; study: docs/standard-tier-review/output-daughterboard-study-2026-07-04.md. | §2.8 revision draft; D-5a BOM-freeze gate; enclosure/chassis design | SYNTHESIS-beta-plan.md D-5a (2026-07-04) |
| — | **24-pin sensing: INA238 RULED (owner, 2026-07-05)** — owner picked the INA238 swap on supply/assembly-flow grounds ("more work to order on Digikey... and consign it or solder it myself, whereas they have tons of stock for the INA238AIDGSR at $2.0991 per 1 and 1.7855 for 10"): LCSC C2868250 live ladder verified ($1.3891@100/$1.2591@1k), JLC-native, drop-in same VSSOP-10 land, accuracy gain-bound-equivalent; energy reporting → firmware integration of the §6.10 stream (OQ-13 scope unchanged). APPLICATION IN FLIGHT: spec v1.5.0 (§6.1 LOCKED edit under ruling) + 24pin-rev3 4-symbol swap + BOM + CLAUDE.md sync + pricing addendum-2 (Complete System re-anchors $259/$279/$299, 24-pin retail ~$89-99). RESIDUAL OWNER ITEM: INA238 stock 680 at LCSC vs ~850-900 needed for a full-system 100-run (24pin 4 + EPS 2 + PCIe 2-3 per system) — the beta-lock register hedge-buy stands; restock-watch or split-source before the first run. Prior decision-row detail (DigiKey option set) retained in git history. | 24-pin beta BOM lock; Complete System Bundle price points | owner ruling 2026-07-05; pricing study + addenda |
| — | **HOST DATA PATH (ruled 2026-07-06): AllMyStuff = the consumer; two owner actions**: (a) **VID/PID acquisition** — pid.codes registration fits the CERN-OHL-S posture (free, one PID per product; needs the hardware to be open-licensed, which it is) — needed before the USB identity freezes into firmware; (b) **AllMyStuff telemetry pane** — the app today has device INVENTORY only (no telemetry ingestion anywhere in its README/ARCHITECTURE/next-milestones, measured 2026-07-06); the "just show it there" plan assumes a telemetry view lands on their side — coordinate with mrjeeves (scope: read our HID sensor collections via commodity hidapi/iio, self-describing, no CEC-specific protocol needed if the HID+CDC composite contract is adopted). Contract recommendation + PR #50 reconcile note: FOLLOWUPS 2026-07-06 entry. | firmware USB identity freeze; SB-07/OQ-85 contracts | FOLLOWUPS 2026-07-06 |
| — | **NANOKVM PRO/PCIe INTEGRATION (exploration 2026-07-06, docs/nanokvm-pro-carrier-exploration-2026-07-06.md): NO full carrier board — but three owner items surfaced**: (a) **PICK THE PRODUCT**: "NanoKVM Pro" (AX630C ARM, GbE, 4K45, Desk/ATX forms only) and "NanoKVM-PCIe" (older/cheaper SG2002 RISC-V) are DIFFERENT products, not one in two forms — the pick drives everything; (b) **HEADER REALITY CHECK**: the ATX Pro exposes NO external UART/power header (internal solder pads only per Sipeed docs) and the PCIe product's aux header is community-documented 4-pin (G/V/T/R, no confirmed 3V3 ref) — J_KVM/OQ-51 was designed against the ORIGINAL NanoKVM's 5-pin header; physically verify the chosen unit's pinout before any connector/adapter commits; the recommended MINIMAL hardware = a small breakout/adapter (not a carrier) that makes the link a repeatable connector AND enforces powering the KVM from CEC's shared rail (KVM-on-PC-USB silently breaks the §2.9 forensic-recovery guarantee); (c) **POWER BUDGET FINDING**: Pro measures ~3W (0.6A@5V) ≈ 3× what §2.9/OQ-2's shared-rail budget assumed — fold into the OQ-2 cap decision. Also: WiFi optional/removable on both lines (no-radiator posture = a purchasing choice; never mount the KVM inside the Hub enclosure); no PS_ON#/PWR_OK conflict (kit interposes the front-panel header, CEC senses the PSU side — intentional redundancy per Concierge); SoC discrepancy (AX630C vs an old RK3588 memory note) to reconcile before any BOM. | J_KVM adapter/cable SKU definition; OQ-2 budget; §2.9 forensic guarantee | exploration doc 2026-07-06 **PART II (ENT bundles, same doc, 2026-07-06): owner suspicion CONFIRMED — the PolarFire already covers it; NO carrier, and specifically no carrier-with-SE** (an SE beside a black-box SoC attests only itself — a CEC-branded carrier implying trust it cannot deliver is worse than the honest posture). Stock Pro = NOT trust-grade (AX630C silicon has secure boot/TrustZone but no evidence Sipeed uses it; CVE-2026-32296 hit the Pro line; Tailscale PREINSTALLED on the device that watches the screen; no 802.1X/VLAN/mTLS). LAN9370 cannot gate it (4×100BASE-T1/chip, all 8 ports consumed by module links, wrong PHY class). RECOMMENDED AUGUST COMPOSITE: (a) stock WiFi-ABSENT unit OUTSIDE the trust boundary, ingested as untrusted claims over the built J_KVM UART (the addendum's existing OS-vantage pattern) + (d2) endgame slide = capture-only absorption into the PolarFire (HDMI-RX ~$10-25 → fabric → signed keyframes into the Merkle log; no Linux, no network, NO HID path — an IP-KVM inside the boundary is a standing HID-injection path into the monitored host; ENT-AIR-compatible; "the witness sees the screen with its own eyes"); CEC-KVM decision box narrows to the interactive-console product question. ONE PRE-AUGUST OWNER-ADJACENT ITEM: the Libero pin-planner feasibility check (MSS USB ball map + HDMI-RX pin/IOG budget) so the endgame slide is "verified feasible" — needs the Libero license (already queued). **PART III (trusted-zone requirements plan, same doc): OWNER DECISION FRAME** — the "like any other module" bar = a 14-row cited checklist (per-unit eFuse key, signed FW + anti-rollback, pin-7 µs-window heartbeat, untrust-state-machine enrollment, zero own egress, intake ritual...). PICK BY INPUT SET: (i) visual evidence only → d2 hub absorption (deviceless, already in-zone); (ii) + trusted 1080p interactive console → **PATH B: CEC-KVM as a native ESP32-P4 module — feasible BY CONSTRUCTION** (inherits every checklist row verbatim; LT6911 HDMI→CSI → P4 hw H.264 1080p30/4K stills signed on-device over T1; HID = separately-attested opt-in w/ hub-signed session grants + hash-chained reports; BOM ~$25-45; COLLAPSES the OQ-75 decision box — no Linux, the PSIRT blocker dissolves; August one-slide win: "the KVM is just another module"); (iii) 4K-class capture + NPU screen classifier → **PATH C (Part IV): CEC carrier + MaixCAM2 gold-finger core module, P4-fronted — DISPLACES PATH A ENTIRELY** (the core module is SoC+DDR only per Sipeed's wiki: WiFi/eMMC/USB all live on the base board → radio VERIFIABLY ABSENT by construction on our carrier + CEC owns boot media/reset → verify-then-release-reset measurement outside the SoC; Axera OTP demotes to optional hardening; carrier P4 fires the full-class µs pin-7 heartbeat — the hub cannot distinguish B from C at the trust layer). ~$55-95 + module ($30-60 est, UNPUBLISHED — intake gap w/ gold-finger pinout + no-hidden-boot-flash confirmation). **RULED (owner, 2026-07-06): PATH C for the enterprise** — "we do C and just stand up the carrier, should be pretty simple." COO/§889 CONTINGENCY also ruled: if customers object to the Chinese silicon, an ALL-AMERICAN version with supply control ships as a SEPARATE SKU (not designed now — recorded as the contingency; Path B-class US-silicon variant is the natural basis). Carrier schematic design DISPATCHED (ENT module conventions: P4 trust endpoint + M.2 M-KEY socket + LT6911 bridge + gated network + DETECT/heartbeat). Remaining intake (unchanged): module price/supply terms + eMMC-less SKU question (Sipeed contact), ROM boot-order bench, M.2 mechanical spec. **PART IV-A (2026-07-06, owner-uploaded 378C/379C schematics read in full — Path C engineering risk DROPPED materially):** gold-finger = standard M.2 M-KEY 75-pos (commodity socket ~$1-2, screw-down); reset + 1.8V boot straps finger-accessible → verify-then-release-reset CONFIRMED workable; module is RADIO-FREE (WiFi = AIC8800D on the base board; carrier rule: leave the on-die EPHY MDI unmagnetized = network absence verifiable unpowered); power = ONE 5V rail, all sequencing on-module (carrier holds reset ≥100ms; STANDBY can cut compute while the P4 endpoint keeps the heartbeat); ONE SURPRISE: 32GB eMMC lives ON the module (wiki wrong) — model survives stronger via strap-selected SD/USB ROM boot from carrier-owned storage, eMMC demoted to measured scratch. REMAINING OWNER/INTAKE ITEMS: module standalone price/supply terms (#1, Sipeed contact), the possible eMMC-less SKU (same contact), ROM USB-vs-SD boot-order bench check, M.2 keying/length from the full download pack. Full analysis: exploration doc Parts III-IV-A. |
| — | **24-PIN ATX CONTROL-SIGNAL INTERACTION — RULED (owner, 2026-07-14, same day): APPROVED incl. the PESD clamps; host-attached policy = REFUSE unless explicit user override (responsibility transfers to the user). IMPLEMENTED on atx-24pin-rev3 same day (splice_24pin_atxctl.py; ERC/netlist/BOM verified — see the study's Status block). REMAINING OWNER-ADJACENT: (a) spec §6.1 note + drive-policy text (owner's pen, drafted in the study §5 row 7); (b) OQ-85 contract rows (interlocks 1–8) when the firmware-contracts bucket opens; (c) first-article bench: drive-gate power-up scope + PSU-zoo PS_ON# pull-up survey + BAT54S C545549 pin-map confirm.** Original decision text (for provenance): approve adding to **atx-24pin-rev3** (beta only, schematic-only, layout not started, ≈$0.30/board): (a) restore the alpha's PWR_OK + PS_ON# read buffers (74LVC1G17 pattern, netmap §4 — they did NOT carry into rev3, all three signals are bare J3→J_SIG1 pass-throughs today, netlist-verified); (b) NEW PS_ON# open-drain drive (AO3400A reuse + 100k gate pull-down fail-safe) so the Hub can command PSU-on over CAN — host-off PSU self-test (rails vs ±5% via the existing INA238s + PWR_OK 100–500ms timing) and §6.14 standalone/bench PSU control; (c) NEW −12V ADC divider (+3V3↔−12V, 15k/100k + clamp; healthy/off/absent all separable in-window). SCOPE HONESTY is part of the decision: PS_ON# assert = PSU-on, NOT OS boot (chipset stays S5; boot needs the front-panel PWRBTN# domain the ask excludes, or BIOS wake sources). Interlock set (two-phase CAN arm+fire, hold watchdog, release-on-CAN-loss, line-integrity check, state telemetry) goes into the OQ-85 firmware contract. Margin table + full circuit values: docs/standard-tier-review/atx24-sense-wire-interaction-study-2026-07-14.md. Sub-calls: optional PESD clamps on PS_ON#/PWR_OK (+$0.04); assert-with-host-attached default policy. | rev3 schematic pass; OQ-85 contract rows; spec §6.1 note + drive-policy OQ | study doc 2026-07-14 |
| — | **PSU-TESTER: TIER STRUCTURE RULED (owner, 2026-07-14 same day): Pro + Max tiers ONLY, no Standard tester now ("Standard is not the shop spec anyway"; the 850W base config shelves as a possible future Standard if demand shows). Pro = the full proper suite incl. the transient engine (1600W hybrid + fast channel): package landed $1,365–2,015 → list $3,495 tester-only / $3,995 w/ modules (2.0–2.9×). Max = ALL of it properly to Max-module level (+HF digitizer for SPEC-GRADE ripple + per-cable spectral, +2nd fast channel, +OVP sourcing stage, +phase-controlled AC-interrupter for absolute hold-up, Pro/Max module set): landed $2,010–3,150 → list $5,995–6,995 (2.2–3.0×; ~half Chroma-entry). Numbers + fences: study §6 addendum. STILL GATING: OQ-1 shop interviews + OQ-10 competitive buy/quote (now validating TWO price points); transient-channel bench gate (OQ-3); Max module-line dependency (EPS/PCIe Pro bounded-not-built, Max modules spec-PROPOSED).** Prior go/no-go framing (provenance): verdict = the sub-$10k gap claim is **substantially TRUE with nuance** — shops can improvise a load stack for $750–5k (Kunkin KP184s / Rigol-Siglent) but nothing turnkey ATX-connector-native exists at any Western price (SunMoon SM-268/8800 served the niche, no Western channel/no ATX 3.x; transient-capable starts ~$13k Chroma-class). Recommended shape: **hybrid load** (resistive bulk 70–80% of heat + ~300–400W linear-FET vernier + ONE gated fast channel for the ATX 3.1 excursion profile 200/180/160/120% @ 100µs–100ms, 5A/µs), CEC modules inline as instrumentation, tester = a CAN module, PS_ON#/PWR_OK automation rides the just-landed 24-pin rev3 block. BOM class $650–1,600; **target $1,995–2,495 base / $2,995–3,495 w/ transient+1600W**; thermal is the product (1600W ≈ 141 CFM, 3–4U space heater). Honesty fences: no OVP/OTP source-side tests, ripple = indicator only, absolute hold-up needs an AC-interrupter accessory. **DECIDE: pursue at all? If yes, the doc's OQ-1 first (shop interviews to validate market size at the price point — the #1 risk) + the competitive buy/quote check (OQ-2) before any hardware.** 13 decision-ready OQs in doc §5. | new-product go/no-go; no board/spec impact until ruled | exploration doc 2026-07-14 |
| — | **SUPERCAP UPS — Pro/Max/ENT hold-up (study 2026-07-15 + owner steering same day):** RE-SIZED (owner, same night: "even 30s is overkill; 5-10s, LCSC-native"): TARGET = 5-10s hold → **Pro bank 0.4-0.8F / Max bank 1-2F** (FPGA sheds at the fail interrupt per its §6.11 power gate — worst-case persist = MCU+flash, ~0.4W/1W). SHAPE = 2S of small LCSC-NATIVE 2.7V radial cells (0.8-1.6F Pro / 2-4F Max per cell) + 2 balance Rs, est $1-2.50/board, Ø8-10mm cans — beats the Eaton packs on size+cost+flow (they are DigiKey=consigned, the INA228-class flow problem). GATE CLOSED (owner checked: LCSC carries NO supercaps). FINAL: **DNP provision, owner hand-solders this run** — Pro/Max boards land a 2S radial THT pattern (2× Ø10mm @5.0mm pitch, covers the 2.7V radial families incl. Eaton HV) + POPULATED support Rs (charge-limit + 2×100k balance; harmless with cells absent, 23µA bleed). Cells bought wherever (Eaton b1/b2 = the priced picks). Applies at the Pro/Max board build-outs (Hub Pro is a skeleton today); Standard unchanged; ENT d-vs-e still gated on its persist-load bench. Superseded framing: **Pro = b2** (Eaton PHV-5R4H255-R 2.5F/5.4V/80mΩ, ~half b1 footprint, 8.5mm-class height, derated at 4.65V on a 5.4V pack, ~31s hold = ~2000× flush budget; PRICE RFQ = the gate; Kyocera SCMS22C255 alt ~$3.73) / **Max = b1** (Eaton PHB-5R0H505-R 5F/5.0V, $4.76@100 confirmed, ~62s — the doubled energy maps to Max data-heavy persist dumps). Same circuit both (1 charge R + existing Schottky; no manager IC). ENT = d-vs-e pending persist-load bench; Standard unchanged. Prior framing: **Pro/Max = NO manager IC** — 1× low-ESR 5.4V dual-cell module (or 2S discrete + passive balance; 2.5V/cell from the 5V rail = inherently derated) dropped into TODAY'S diode-LDO topology + one charge-limit R; ~12s/farad usable (~$2-5, zero ICs) — vastly exceeds the flush need. Manager IC = ENT ONLY (LTC3350, telemetry + boost for the witness load). Owner "battery on ENT" reference NOT FOUND in docs (eMMC pin noise only) — reconcile if a coin-cell provision exists elsewhere; roles differ regardless (coin cell = clock/tamper years at µA; supercap = the 0.5-3W persist burst). Prior study framing (superseded at Pro/Max): **2S2P of four 2.7V EDLC cells on TPS61094** (LCSC C3034939, the only LCSC-stocked manager; ~$8-27/board) for tens-of-seconds-to-minutes of persist ride; **ENT = Seeed-literal 4S stack on LTC3350** (I²C stack-health telemetry feeds the witness attestation; ~$15-38/board); **Standard = no change** (keep the DNP ladder hedge; measured 16-26ms electrolytic + ≤15ms flush contract suffices). Reality anchor: Seeed's real product (4×7F/2.7V series, LTC3350) benches 37s idle/18s load on a CM4 — tens of seconds, not minutes. Derated hold: Standard-class load 92-459s across 5-25F banks; ENT 12s-6min (load estimate 6×-wide — needs the real persist-power number). DECIDE: adopt per-tier? TWO unmeasured gates flagged: bench inrush/leakage vs the shared 2.5A 5VSB budget, and ENT persist load. Cell pricing = RFQ (OQ-11-style flag). Ties OQ-56/H2. | Pro/Max/ENT power-architecture divergence from Standard; ENT August demo (outage attestation) | study doc 2026-07-15 |
| — | **"SMOKE TESTER" (owner riff + refinement + STANDUP 2026-07-24):** concept + refinement recorded (docs/smoke-tester-concept-2026-07-24.md §1–§9: fuse→crowbar fault-converter, blade 32V-arc honesty → hidden 5×20 HRC 250VAC coordination, safe smoke via flameproof fusible witnesses, neon CASE-LIVE, needle-meter-not-pixels, $79 retail w/ starter kit incl. spare brick, consumables ladder). Decision #1 EXECUTED by owner directive ("make a new beta module") — folder stood up at beta/smoke-tester/ (README = board spec of record, 3 sketch SVGs, sketch BOM ≈$36.5@100 rolling to the $30–34 target at 1k, markers, manifest). REMAINING OWNER DECISIONS #2–#12 (concept §8): terminator fence, coordination ratify, witness-chamber safety review, earth-ref form, AUX scope, compliance posture, price ratify, bundle position, in-box spare brick, consumables ladder. POWER REVISED (owner no-disposables directive, 2026-07-24 same day, EXECUTED): batteryless 2S-supercap store, self-charged off the DUT 5VSB/5V ways (33Ω 2W fusible on-brick + 5.6V CV zener) + USB-C cold-start; direct-from-store domain w/ TLV431 absolute ref; Li-ion considered+rejected (UN38.3/BMS/aging). Cell line = consigned (LCSC carries no supercaps — study gate 2026-07-15), SAME cells as the Pro/Max 2S provision → shared buy. Rollup ≈$39.15@100 (+$2.7). SNOUT WEAR RETIRED (owner bench pushback 2026-07-24, owner RIGHT — 2.3Ω/115×-spec-death error-budget math in README §2): HMC/gold adder dropped (std tin), snout = damage/service spare only, wear removed from consumables forecast; NEW decision #13 keep-paddle (recommended, ~$1.3) vs board-mount-direct. SIGN-OFF EXECUTED (owner 2026-07-25 "approve on all counts"): #2,3,5,8,9,11,12,13,14 RULED (#14 arcs = BOTH), #4 adopted-pending-safety-review, #10 bundle position OPEN. BOM SOURCED same day (LCSC-primary, jlcsearch-verified; anchors C7948/C56765/C3131/C142716/C3207132/C6793760/C48642402/C1741442/C190594/C110526 + platform reuse; datasheets vendored LM339/TLV431A/SMAZ — Littelfuse 215/297 + Hongfa PDFs fetch-blocked). Sub-board folders brick/ snout/ faceplate/ stood up (own KiCad projects at capture; generator+lib = the shared layer). K1 simplified to 1-pole latching HF3F-L/5 (PG-race t0 from the PS_ON# node). REMAINING OWNER/DESK: consigned buys (neons, flicker tube, meter, missile toggle, supercaps, Mini-Fit, case quote, ATO fuse bulk), STOCK WATCHES (C6793760=800, C349125=124, C3207132=997, C190594=749), 2R090T glass-body check + #4 safety review + arc-coordination bench (gates DRAFT-drop), #10 bundle call. ARCS RIFF RECORDED (owner ask 2026-07-25, concept §9.10, decision #14): glass GDTs on the brick as the visible-AND-functional mains crowbar (fault's own energy, witness-window placement, +$1-2) + momentary LAMP-TEST/SHOW button (contained ~100mW boost strikes all gas bulbs + a flicker-flame tube — the show doubles as the safety self-test for the CASE-LIVE bulb); sealed-devices-only fence, Jacob's-ladder-class open arcs named and REJECTED, never-generate-what-you-detect rule; recommendation BOTH, ~$3-4 BOM adder, retail holds $79. Next agent phase gated on nods: Phase A CAD library → Phase B capture; DRAFT drops only after the arc-coordination bench (230VAC-into-a-way film). SMOKE SHOT ADDED (owner "I do want that" 2026-07-25): dedicated demo branch 12V → 10A-T HRC C142733 (fuse-first) → horn button (held-only) → KNP-1R pellet (the brick-witness part) in a tool-less clip = 144W puff ~100ms behind the window, ~$0.02/shot reload, kit ships 20, 50-bag refill SKU; mains-while-pressing corner cleared by the HRC; consumable ⑤ (dies on purpose); #4 review scope grows to demo-shot vent cadence. AUX DESCOPED (owner scope objection SUSTAINED 2026-07-25 — "a DMM job, not the smoke tester": port + 3 AUX ways + continuity way + adapter SKUs removed, agent's safety framing retracted on record; −$3.5–4 BOM → rollup ≈$39–41@100 / ~$31–33@1k; brick 2×8, LM339 back to 6 pkgs, meter pos-6 → STORE; cable checking lives with the DMM / deck per DESIGN-SHEET §A). BOTH-GRIDS Q ANSWERED in spec (README §3 note): 120 vs 230+ VAC input changes nothing — DC outputs identical, mains-facing parts specced at 325Vpk worst case, fuse currents input-agnostic, no switch/variant; ~400VDC PFC-bus ingress = explicit arc-bench DC row. Pellet clip = OTS KF141V-2.54-2P C475114 button-release (WJ250B C8454 fallback). DC-INCURSION Q (owner 2026-07-25): realism ladder recorded (concept §9.14 — leakage/tracking = the realistic+dominant case, handled silently by the neons; stiff 400VDC = rarest, physically a 30-45J cap dump not a supply); handling = designed WITNESS-FIRST sequence (clamp leg self-disconnects sub-ms; no 32VDC blade ever breaks 400V) + NEW FIRST-CONTACT RULE (MIN LOAD off until first green, silk + card) + bench DC rows both ways; 10×38 gPV solar-fuse upgrade evaluated + REJECTED (+$15-20, disproportionate). #15 AFTERMATH SHOW RULED AS AMENDED (owner nod + automatic directive, 2026-07-25): any POP auto-wakes the WHOLE panel (passive BF-OR D_AW1..5 → Q_AUTO ∥ TEST; DUT-harvest-powered by construction; zero-standby kept — wake signal requires a live way) + flame tube & NE_EVT relaxation blinker run while the condition lives; fence #14 AMENDED owner-authorized (HV = held ∨ live-event, never with fuse door open — lid µswitch kills boost); honest boundary: non-pop reds still need held-TEST; ~$0.50 all-in; APPLIED README §4 + BOM + SVGs. Mains-tier cost autopsy DONE (§9.15B): all-in ~$2.3-2.5, five cheaper alternatives examined + rejected for load-bearing reasons (HRC-delete = blade arc in unrated holder; shared GND fuse = kills indication mid-event; series-R = 7% measurement error; trace fuse = trust story; MOV-only = loses crowbar + show); recommendation NO CHANGE — already at honest floor. | testers/smoke-tester capture start; ST-bundle composition | beta/smoke-tester/README.md |
| 8 | Panel cadence/seats (API spend) | wave-4 CL-22 frontier seats | parity plan §1 |
| 9 | Swarm charters / budget / precision floor | wave-4 CL-24 verifier tier | parity plan §1 |
| 11 | Frontier data egress | wave-4 CL-22 frontier seat binding | parity plan §1 |
| 12 | Owner bandwidth / WIP caps | wave-3 CL-12 morning-bundle sizing | parity plan §1 |
| 13 | Second forensics reader | wave-5 DF analytics | parity plan §1 |
| 14 | Probe opt-in | wave-5 DF-10 | parity plan §1 |
| 15 | Vindication weights | wave-5 PC | parity plan §1 |
| 16 | Process-corpus custody | wave-5 | parity plan §1 |
| 17 | Generative-training moratorium | G4 watch item; any learned-router idea | parity plan §1, GR ladder |
| 19 | Plan-stage depth | GR-05 | parity plan §1 |
| 20 | Topological climb gate | GR-06 | parity plan §1 |
| — | **D-ENT-1..6 — Enterprise production-requirements program (2026-07-01; owner direction landed same day, plan §1a)**: OWNER ANSWERED in-session — compute = **PolarFire** ("just do the enterprise with PolarFire", D-ENT-2 resolved-by-direction, spec edit pending); the two enterprise variants are **ENT-AIR (air-gapped)** and **ENT-NET (networked-but-hardened)**; BOM targets **TBD** (D-ENT-3); modules **YES — requirements now, boards after ratification** (D-ENT-4). STILL OWNER'S PEN: (1) the Phase-4 spec revision formally closing OQ-7 + rewriting the §1 tier table onto the PolarFire/two-variant framing; (6) **D-ENT-6 variant↔tier mapping** — how AIR/NET map onto the Enterprise/Mission-Critical labels + where the MC redundancy set lands; (5) the D-ENT-5 line-items (1-Wire ID path, CAN-FD trigger, provenance role, mezzanine form, **radio-free MCU mandate for ENT-AIR modules** — every current module MCU is Wi-Fi/BLE-capable silicon). Also: **re-auth the Google Drive MCP connector** (token expired) so customer/owner requirement docs can be swept into intake. | OQ-7 close; §1 tier-table rewrite; module board program start | `docs/enterprise-mc-requirements-plan-2026-07-01.md` §1a |
| — | **PHASE-2 ITEMS RESOLVED by owner rulings 2026-07-02** (recorded in the registers; formal spec close rides Phase 4): (1) CRA Annex III classification → **deferred to the EU-entry trigger** ("not selling to the EU yet, keep it open") — resolve via delegated act/counsel BEFORE any first EU placement (REQ-HUB-COMMON-094, gate EU-entry); (2) CRA 2026-09-11 applicability → **no EU market placement planned now**; SBOM discipline maintained so the path stays short; (4) S-suffix → **CONFIRMED**, baseline MPFS095TS (Athena required); (5) RJ-11↔OQ-60 → **security-I/O port wins the shell** (REQ-HUB-COMMON-033); OQ-60's Max sideband connector renames at its own decision point; (6) NanoKVM on ENT-AIR → **excluded from base builds**; customer-attached KVM = outside the zero-egress guarantee (REQ-HUB-AIR-059). REMAINING OWNER ACTIONS: (3) wolfSSL FIPS OE-extension engagement at firmware kickoff (REQ-HUB-COMMON-097); ~~D-ENT-6~~ RESOLVED by second ruling 2026-07-02 (one ENT line, SKU axes posture x availability: base / MC = independent compute watchdog + redundancy pack / MC-Max = optional FAIL-FUNCTIONAL voting pair; REQ-HUB-COMMON-103..105, spec-draft §13.8, OQ-79 opened for architecture detail, survey 9 delivered — `research/phase2/survey-9-availability-ladder.md`); D-ENT-3 BOM re-baseline (RFQs); remaining D-ENT-5 line items (provenance role, mezzanine form, ATR policy, key custody, SBOM format — 1-Wire identity RESOLVED 5th ruling: poke-and-ack + MCU-key challenge, no hardware; pin-7 SYNC/FREEZE ADOPTED same ruling, suitors cleared; ~~pin-7 HEARTBEAT CHALLENGER adopt/decline~~ ADOPTED by 6th ruling 2026-07-02 — REQ-HUB-COMMON-114 + REQ-MOD-COMMON-013 [port-bound hardware-timed challenge-response, miss → auto-untrust, ≈$0 parts], folds into the v1.2.0 pin-7 table edit). SIXTH RULING 2026-07-02 also extends **T1 to the 24-pin family** (every ENT module = T1 + ESP32-P4 uniform + DETECT 10 kΩ; +$5–7/24-pin, hub side $0 — ports already T1; REQ-MOD-COMMON-003 + spec-draft §13.2a updated; the survey-10 P4-vs-STM32H5 MCU sub-choice is thereby RESOLVED to P4-uniform); the Phase-4 spec revision itself (v1.2.0 draft updated with the SKU-ladder + T1-link rulings); CEC-KVM cited recs list due at OQ-75 kickoff (FOLLOWUPS). THIRD RULING 2026-07-02: ENT module streaming = 100BASE-T1 on pair 2 (bidirectional + sub-us TIME SYNC; DETECT 10k class; OQ-20 ENT-resolved; RS-485 stays consumer-Pro) — new OQ-80, survey 10 delivered (`research/phase2/survey-10-t1-module-link.md`); the remaining open item is the OWNER'S RATIFYING NOD on the RS-485-compat-drop sub-choice (dual-mode backward compat [T1+RS-485 RX per port] vs the drop — survey 10 recommends the DROP, drafted in REQ-HUB-COMMON-043 with an owner-review tag; the research is complete, this is a sign-off, not an open research question); the module RMII-MCU pick is RESOLVED to P4-uniform by the 6th ruling. | Phase-4 spec edit; D-ENT-3/6; firmware kickoff | plan §1a/D-table; `docs/enterprise-requirements/research/phase2/INDEX.md` |
| — | **ENT NEXT-TRAJECTORY DECISIONS (2026-07-02, `docs/enterprise-requirements/next-trajectory-2026-07-02.md` §4)**: the full ordered decision queue lives there (a ratification review brief is being pre-staged so most are nods). NEW spend/tooling asks beyond the standing items: **(f1) dev-kit/EVB order** ~$600–900 (2× PolarFire Discovery Kit ~$132 ea, 2× ESP32-P4 EVB, 1× EVB-LAN9370, FlashPro, ADS7830 breakout; Icicle-pair NTB spike ~$1000+ DEFERRED — MC-Max-only); **(f2) Libero SoC license/provisioning** for the Power Estimator run + fabric work (the known DR-gap follow-up); **(f3) MPFS hedge-stock decision** — owner flagged 095TS stock as extremely limited, VERIFIED 2026-07-02 (no authorized 095-density FCVG484 stock, S or non-S; non-S is 52-wk): the one in-stock pin-compatible S part is MPFS250TS-FCVG484I (DigiKey 64 pcs @ $399.74) — decide buy 5–10 prototype/hedge units now (≈$2–4k) vs wait for the factory-direct 095TS RFQ (master BOM §3a ladder). UPDATE same session (owner finds): the **PolarFire SoC CORE (TC) line is stocked** — MPFS095TC-FCVG484E $119@100/~1-mo (production land!), 095TC-FCSG325E $109, 025TC-FCSG325E $43.70; recommendation now = **buy 3–5× 095TC-FCVG484E for prototypes (~$360–600)** + downscale the 250TS hedge to optional; ~~TC-for-PRODUCTION would require relaxing REQ-001's Athena/S posture~~ **RESOLVED — SEVENTH RULING 2026-07-02 ("I sign off")**: MPFS095TC = the PRODUCTION BASELINE, conditional on FAE confirming the Core line retains PUF secure boot + user TRNG + tamper detectors (any failure reverts to the S ladder and reopens the ruling); **MPFS095TS = the HS population option** on the same part-agnostic SerDes-free land (Athena/DPA for high-assurance channels); REQ-001/030/104 + spec sheets + v1.2.0 draft §13.1 amended; the 250TS hedge buy is now OPTIONAL (HS-option early stock only); TC prototype buy (3–5× 095TC-FCVG484E) = proceed with the dev-kit order. STILL OWNER: the FAE answers ride the D-ENT-3 RFQ/FAE engagement. Full survey `research/sourcing-alternatives-2026-07-02.md` (PIC64GX+MPF050TC = designed two-chip fallback; cross-vendor declined). Minimal set that unblocks boards: REQ-111 decision + RS-485 nod → apply v1.2.0 → OQ-11 lock → Phase-5 gate. Engineering defaults agents proceed on unless overridden are listed in §4 (HMAC-only heartbeat at ship, FIPS-claim-scope Hub-only, separate tamper-log key, raw-key module identity, eFuse+flash-enc P4 key storage, LIM-first, in-house EMC pre-scan, qualitative-FMEA-first). | **EIGHTH RULING 2026-07-02 — owner walked the whole brief** (status block at the top of the brief): N3 RFQ RATIFIED (send held for CUSTOMER design sign-off — new external gate; **prototype demo rig = the new critical path**, plan at `prototype-demo-plan-2026-07-02.md`, makes the f1 dev-kit + TC-silicon order urgent); N4 OQ-75 KICKED OFF; N5 Phase-5 strict gate RATIFIED; R1 REQ-111 DECLINED (tombstoned); R2 v1.2.0 SIGN-OFF given (application staged behind the N1 RS-485 confirm); R3 OQ-11 DELEGATED (Bourns default, engineering pick — selection agent running); R4 provenance = EVIDENCE SOURCE ONLY (in REQ-007); R5 mezzanine ADOPTED (+ consumer-side per owner; stacked-product SKU ENT-AIR-only for now — **beyond-AIR scope extension FLAGGED FOR REVIEW**); R7 custody direction RATIFIED (offline M-of-N; procedure doc → final sign-off). NINTH RULING 2026-07-02 ("Adopt these recs"): N1 RS-485 drop CONFIRMED (REQ-043 tag cleared), N2 SBOM = SPDX-native + CycloneDX-derived (REQ-014), R6 ATR = passive-receive-only NET adopted / ACTIVE emitter deferred to customer-funded NRE (draft OQ-78) → **v1.2.0 SPEC APPLICATION UNBLOCKED AND IN PROGRESS on this branch**. STILL PENDING OWNER: CEC-KVM 5-item decision box, dev-kit + TC prototype order (demo-critical), Libero license, custody procedure final sign-off when drafted, mezzanine beyond-AIR scope review | dev-kit/TC order (demo critical path); KVM decision box; Libero | ratification brief status block; prototype-demo-plan; master BOM §3a |
| — | **OQ-11 (within CSS-class)**: pick the specific EPS/PCIe 0.5 mΩ + 12VHPWR 1 mΩ parts; resolve the **CSS2H R-vs-K suffix divergence** (spec §6.4/§6.11 says -2512K-1L00F; the sourced BOM carries -2512R-1L00F / C4175647 — verify which series C4175941 actually is and align docs) | 12VHPWR/EPS/PCIe shunt sourcing; the dV/dI lanes (family class already locked by `bom.dvdi_shunt_loadlife_constraint`) | `meas.anchor.standard_current` notes; stability budget §1 |
| — | Instrument acquisition: whether/when to buy a trusted voltage reference + ammeter | everything in §6 below (the deferred-pending-instrument set) | `meas.bench.empty_instrument_state` |
| — | **SENSEC2 run retrospective — owner half (2026-06-11).** Agent items 2–5 **LANDED (PR #35)**, host-tested (scorer fixture: round 1 wins; offending-net + verifier-quorum tests green); rounds can **restart after owner merge of PR #35**. Owner-gated: (item 6) **promoted/ signing unblock** — branch-protection count fix + PR-chain merge + re-sign → lights the dark spec-conformance seat (every panel verdict is a 2-of-3 QUORUM until then); (item 7) reasoning-sheet attach + VERIFY settlement (most settled in retrospective §9); vision-seat broker-contention fix; sign the 7 corpus-entry candidates (§6) once the scorer/charter land. NOTE: **M2.7 RETIRED from the CEC pipeline → DeepSeek-V4-Flash deep auditor** (owner directive, edits landed, uncommitted). Dual-5090 = owner considering, not now. | promoted/ signing (CL-02) + reasoning sheet + vision contention + corpus sign-off | uploaded `sensec2routingrunretrospective20260611.md`; `docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md` |
| — | **Placement actuator: corridor-scoped vs generalized (2026-06-16).** The actuation lever's placement arm (`apply_placement_move` → `corridor_violations` → `apply_corridor_evict`) only moves a SENSITIVE body that sits inside a FORMED high-current corridor — so `corridor_violations()` == [] for the committed Hub (shared-bus, no cables) AND the committed eps (clean placement), and `placement_moved_rate` is structurally 0 on both (EMPIRICALLY confirmed, host pcbnew; review wf_6653dbfc). **Option (1) is now DONE + VALIDATED** (owner: "Validate the chain on EPS first"; commit 7b10fed): a live injected-EPS run showed the full chain fire — but it took a SECOND fix (the finder was never given the body-in-corridor fact, so it mis-diagnosed routing + targeted the fenced sense net). With `corridor_body_facts` surfaced, baseline placement_moved_rate 0.0 → **0.667 (2/3, U10 evicted +9mm)**. **Option (2) GENERALIZE remains the open decision:** a non-corridor "make-room" eviction band from local congestion (GR-01 hotspot / failed-waypoint geometry) so Hub-class congestion failures move a body — larger, and the corridor-evict safety model does NOT transfer (needs its own design). This is the ONLY path to placement movement on a shared-bus (no-corridor) board like the Hub. | whether to generalize the lever beyond the EPS/PCIe corridor case (Hub placement movement) | FOLLOWUPS 2026-06-16; TODO.md; docs/fullstack-run-2026-06-16-epsinject{,2}/RESULT.md |
| — | **Auditor↔verifier charter deep-dive** (CL-24 in-loop, full-process): the auditor reaches the correct diagnosis but proposes levers the 3-seat verifier (spec-conformance/evidence-provenance/actuation-space) correctly refutes every round (0 rules admitted, 6 refused). **10 lessons** w/ an evidence index linking every tier output (T0 grid → T1 intents → T5 sonnet findings+`.stream.jsonl` transcripts → CL-24 verifier seats → T6 pour/vision → T8 V4 batch → `live-rules.json`). Highlights: actuation-space seat names the owned-lever set — foreign-crossing control is owned by **FR-02 waypoint intents (T1, already live) / placement**, NOT GR-02 or pour geometry (corrects the first-draft GR-02 read); move the allowed-lever rule into the auditor prompt; split `root_cause`(bankable) from `proposed_lever`(gated); "selection≠generation" + proxy-vs-goal (DRC satisficed below the gate = local minimum, per the V4 decline); thread refute reasons + the diagnosis back to T1; **unify the citable-fact set and the verifier's bundle-fact set** — they're ONE contract that drifted (provenance seat refuted TRUE T6/FEM facts absent from the narrower bundle; zero-tolerance is sound only while bundle≡citable). Fix = one authoritative fact registry both are projections of, each fact carrying source-stage provenance — NOT widen-the-bundle (re-drifts); the spec-conformance seat is **dark until `promoted/` is signed** (ties to CL-02); **QUORUM-not-FULL rule (owner, 2026-06-11): any dark seat (empty-corpus/ timeout/error/seat-down) → the panel `final` must be typed QUORUM with a live/dark seat roster + dark-reason, never a flat full verdict — current bug, all 4 rounds reported `final:refute` flat while spec-conformance was dark every round; downstream treats QUORUM as lower-confidence.** | CL-24 charter (Decision 9) + verifier output schema + finding schema + DF/PC feedback + CL-02 corpus sign | `docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md`; observed 2026-06-11 eps validation run |

## 2. GitHub / promotion rituals

| Item | Why | Recorded |
|---|---|---|
| **Merge the open PR chain** (`claude/corpus-experiential-intake` stacked on `claude/cl19-real-register`; PR #26 first if still open) | everything this session staged | branch state |
| **Re-sign pass over staging** (Decision 2): promote what you stand behind — now 61 general entries (all the session's `human_approved`-without-signoff rows await the GitHub signoff act) + 258 extracted rows needing class/typed-source upgrades at promotion | the promoted/ zone is still EMPTY; nothing blocks until promotion is wanted, but no blocking artifact exists until then | corpus lint warnings (designed) |
| **Founders ack — exactly two items** (scope shrunk 2026-06-10): the promise rows (`meas.targets.v1`) and the dV/dI tier framing (`dvdi.requirement_tier_verdict`). The traceability wording goes to them **as decided**, not open | those two entries cannot promote without it | `meas.targets.v1` / `dvdi.requirement_tier_verdict` notes |
| Branch-protection count=1 fix (owner ruling #12 caveat) | NOTHING promotes until it lands | owner-session doc 2026-06-10 |
| CL-19 owner gate ritual: review the drafted real-register gold labels, write the `eval_gate` record into cec-policy.json | the 27B extractor seat stays non-load-bearing until then (gate FAIL recorded honestly — quote-discipline) | cl19 branch, trace gallery |
| **Review/merge PR #40** (det-inspection: deterministic pre-pass owns detection + VLM re-roled to narration/anomaly; bot-authored, supersedes the main-authored #39 which is CLOSED) | executes the owner ruling; pre-pass gate 12/12, VLM incremental 2/2 (FP=0 post-baseline) | PR #40, `docs/det-inspection/` |
| **Merge PR #41 BEFORE/WITH #40** (the CL-21 dive; bot-authored, supersedes the main-authored #38 which is CLOSED) | so the 5 staged CL-21 corpus entries' dive-refs + the ruling-doc dive-refs resolve in-tree | PR #41, branch `claude/research-cl21-vlm-seat` |
| **Vision-seat `eval_gate` decision** (cec-policy.json): sign the drafted `new_role_incremental_catch` block to load-bearing **against the 2/2 incremental-catch number** for anomaly-surfacing ONLY (never measurement), OR retire/tune the seat. The 2026-06-11 logo FP is now SUBTRACTED via the known-good-reference baseline (FP=0 on the clean control); honest caveat = precision imperfect on corrupted candidates (benign overlay/logo flags persist, advisory) | the seat stays non-load-bearing until decided; a documented null would retire it (this is 2/2, not null) | `docs/det-inspection/incremental-catch.md` |
| **Promote the 5 CL-21 corpus entries** (`corpus/staging/general/cl21-vlm-seat-2026-06-11.json`, Class H proposed) if you stand behind them | advisory-only; nothing blocks until promotion is wanted | corpus lint 0 errors |

## 3. Spec edits (drafted, waiting on the owner's pen — the corpus never amends the spec sideways)

- **v1.2.0 — THE ENTERPRISE LINE (drafted 2026-07-02, ready):**
  `docs/spec-revision-v1.2.0-draft-2026-07-02.md` — complete surgical edit set (10 edits):
  new §13 (ENT-NET/ENT-AIR on PolarFire S), §1 tier-table rewrite, tier-agnostic phrasing
  amendment (interface vs build variants), OQ-7 close, OQ-14 enterprise close, OQ-53..56
  enterprise closures, OQ-60 RJ-11 disentangle, new OQ-75 (CEC-KVM) / OQ-76 (module
  identity) / OQ-77 (mezzanine) / OQ-78 (tamper family). ~~TWO decision boxes inside:
  [D-ENT-6] tier-label mapping (recommended: ENT-NET=3/Enterprise, ENT-AIR=4/MC,
  redundancy pack standard on 4, optional on 3)~~ **SUPERSEDED — D-ENT-6 is no longer a
  decision box**, resolved by the owner's second ruling 2026-07-02 (one enterprise line,
  SKU-differentiated: posture × availability, no separate Enterprise/MC tier; plan §1a.6,
  REQ-HUB-COMMON-103..105). The one remaining decision box is OQ-75 CEC-KVM adopt/step
  order. Apply by direct edit or by approving a PR of exactly these edits.

| Edit | Drafted at | Queued |
|---|---|---|
| §6.4 no-cal grade restated **per quantity** (voltage survives no-cal; sub-1% current dies on a ±1% shunt) | `meas.cal.strategy_per_tier` | 2026-06-10 |
| 12VHPWR Standard voltage **promise ±0.5%** wording (±0.3% stays design-outcome) vs the current "~±0.3 to 0.5%" framing | `meas.targets.v1` | 2026-06-10 |
| **Traceability wording** — "characterized," full stop; no NIST claim (LOCKED; exact sentence drafted) | `meas.truth_chain.spec_wording` | 2026-06-10 |
| §6.13 capture path — **oversample-and-decimate** (SADC 50–100 kHz → 10 kHz report; 16.9 kHz RC = anti-alias) or the 2–5 kHz corner fallback; documented, never implied | `capture.10khz_disposition` | 2026-06-10 |
| §6.13 alarm threshold defaults (WARN >9.5 A / ALARM >11 A >1 s / CRITICAL imbalance >2.0 or ~0 A lane; 12 A = instantaneous ceiling only) — the spec-OQ-57 threshold lock | `alarm.12vhpwr_per_pin` | 2026-06-10 |
| dV/dI tier framing into the spec (Pro ships / Standard conditional-beta + the 0.3/0.7 mΩ gates) — after founders ack | `dvdi.requirement_tier_verdict` | 2026-06-10 |
| atx-24pin-rev2 CAN-pair naming erratum (`/CAN1_P,/CAN1_N` → `_H/_L`) — already queued as a rev3 erratum; spec mention optional | board-manifest.json | 2026-06-10 |
| **Max instrument-channel ruling → spec** (OQ-17: ONE shared wideband V+I channel, six-channel fast array RETIRED; OQ-18: deconvolved shunt + PCB Rogowski, never a second shunt; OQ-15/19 inputs re-derive; ADC option **A1 (50–65 MS/s spec-faithful) vs A2 (25 MS/s reduced-scope, documented deviation)** still owner's pick) — ruling recorded in `docs/research/max-instrument-channel-decision-2026-06-11.md`; spec edit rides the owner pen | `docs/research/max-instrument-channel-decision-2026-06-11.md` §5 | 2026-06-11 |

## 4. Physical bench / lab (the items with real-world clocks)

| Item | Why it matters NOW | Recorded |
|---|---|---|
| **rev2 24-pin bring-up** — doubly motivated: it is the host of the shunt-drift benchmark and **the benchmark clock starts at first bring-up** | the in-situ multi-week drift benchmark settles the Standard dV/dI verdict (0.3/0.7 mΩ gates); its clock runs in WEEKS — every week of delay is a week of verdict delay | `bench.shunt_drift_protocol`, `docs/protocols/shunt-drift-benchmark-2026-06-10.md` |
| **Measure in-case ambient at the board location** (cluster-1 OQ) | tests the 55 °C cutover clause; upgrades `design_ambient` H→C; also settles which REF3030 tempco governs (the U4 <70 °C check) | intake doc metrology table |
| **Measure trace thermal τ** (current step on a populated lane) | upgrades the transient-allowance τ values H→C | intake doc metrology table |
| **In-house dI/dt scope measurement at the connector** | published sources never give slew rate; needed for the §6.13/OQ-18 HF questions | cluster-6 OQs |
| **ESP32-S3 SADC long-term drift characterization** | unpublished by Espressif; the one unquantified dV/dI term the differential scheme bounds but can't eliminate | cluster-6 OQs |
| 12VHPWR U4 local-temperature check (FEM probe at U4's coordinates or thermocouple) | clears the conservative 75 ppm gate to 50 ppm if <70 °C confirmed | `stab.ref3030_drift` notes |
| OQ-56 hold-up bench check (4700 µF rides a flash write) | §2.9 power-management validation | CLAUDE.md item 0(e) |
| **Z(f) extraction jig** (MOSFET-switched resistive step-load; board measures its own step → per-unit R+L cal constants) — one build serves BOTH this and the drift benchmark's load-step profile | the Max instrument channel's deconvolution path needs per-unit cal; also V-3 (CSS2H ESL stability) | instrument-channel decision doc §4.1 |
| **VRM-residue first-article measurement** (real GPU harness, gaming+synthetic, full band; >1% of DC or clean N×f_sw line reopens fingerprinting, absence = the published null) | closes the genuinely-unmeasured cell; CEC-published null either way | instrument-channel decision doc §4.2 |
| **R-1 12 V micro-arc characterization rig** (degraded-connector metallurgy, 1–9 A, 10–20 MS/s capture) — closes the last unmeasured cell of the Sandia-null transfer (verdict already CONFIRMED at 28/42/48 V) | the novel datapoint the literature lacks; final confirmation of the fast-chain de-scope | `low-voltage-arc-spectra-r1-2026-06-11.md` §(d) |

## 5. Ten-minute desk tasks (data the agent needs, human-readable sources)

| Item | Why | Recorded |
|---|---|---|
| **Read the Mini-Fit rating table** from the vendored `lib/datasheets/Molex-PS-5556.pdf` (per-circuit amps by wire gauge / circuit count, by terminal series) — it would not machine-extract | EPS/PCIe comparator defaults stay PLACEHOLDERS until the conservative-series rating pins (`conn.minifit_conservative_terminal_basis`) | 2026-06-10 |
| **JLCPCB guaranteed-minimum via plating** (from the rev2 order/DFM data or the quote tool — capability pages are JS-rendered) | the `thermal.jmax.via_barrel` plating clause resolves against it (`fab.jlcpcb.via_plating_min`, D2 vendor entry waiting) | 2026-06-10 |
| **rev2 as-built service tier** (order confirmation) → `fab_target.service_tier` in the rev2 board-manifest | tier-conditional vendor entries resolve to zero coverage on rev2 until then | manifest `_fab_target_doc` |
| **Acquire IPC-2152** | THE upgrade trigger for every verify-note thermal entry (dt_max, the three jmax splits → re-derive from real Fig 5-2 + via appendix; H→A re-class) | cluster-1 OQs |
| Verify the REF3030AIDBZR grade rows in the vendored datasheet (initial accuracy table + both tempco ranges) at promotion | the `meas.anchor.ref3030_initial_accuracy` promotion gate | entry notes |
| Verify the Malucci white paper's 9 A extrapolation formula (ΔVt(9)=0.0322 V) | load-bearing for the 3.5 mΩ conversion + the dV/dI ~3× margin | `conn.malucci_runaway_onset` notes |

## 6. Deferred-pending-instrument (unblocks as a SET when an instrument row lands)

- Pro accuracy anchor (`meas.anchor.pro_cal_instrument`) — cannot be stated.
- Per-unit factory cal execution (`meas.cal.strategy_per_tier` Pro leg).
- Pro promise candidacy in the target table (voltage + current rows).
- The Pro "factory-calibrated against a named instrument" claim sentence.
- Ruling-7: any calibration band for ABSOLUTE electrical quantities.
- The cluster-2 electrical metrology rows themselves (instrument + method + uncertainty
  + cal-certificate state — the rows are recorded EMPTY, honestly).

## 7. Owner research / data dumps still open (the cluster series)

| Item | State |
|---|---|
| Cluster 2 — the non-electrical metrology rows (thermal camera + emissivity protocol, thermocouple + attachment, milliohm 4-wire?, DC-load ceiling, transient capture BW) | table scaffolded; electrical rows ruled EMPTY; the rest unanswered |
| Cluster 3 — rev2 fab lessons (deltas-against-expectation, two piles: physics vs JLC-vendor) + artifact pointers | typing contract ready (H + `source.type: fab` + rev2 order ref); zero entries yet |
| Cluster 4 — the burn list, by category (footprint traps, datasheet traps, library defaults, connector keying, polarity marks, vendor substitution) | REF3030 exemplar landed; the rest unwritten |
| Cluster 5 items still owed research: — (items 1/2/3/5 ratified; item 4 delivered via cluster 6) | "The other items I will present research on" — owner's words, 2026-06-10 |
| Cluster-1 thermal-gate constants: provenance now in the research doc; the named bench OQs above are its outstanding limbs | delivered |

## 8. GUI board work (owner machine, KiCad — pre-existing CLAUDE.md items, unchanged)

- Hub Standard: Fill-All-Zones + the §2.9/J7 placement-route pass + the power-pour
  punch-list (CLAUDE.md items 0/3).
- 12VHPWR Standard: the pour/route finish + Update-from-Schematic pulls (U2 value, NTC
  dividers, U4 et al.) + the FEM-driven GND stitching items (CLAUDE.md item 4).
- EPS/PCIe ×3: Update-PCB-from-Schematic for the C6 + §6.13 parts, then re-place/route
  (CLAUDE.md item −1).
- "Update Footprints from Library" passes: Hub J2–J5 FTP shield tabs; 12VHPWR J1/J3/J4.
- **24-pin rev3 — INA238 rail-sensor SUPPLY MIS-WIRING (CRITICAL, found 2026-07-07 net sweep; pre-existing, identical at HEAD).** Three of the four rail sensors have VS(pin6)/GND(pin7) daisy-chained wrong so their supply never reaches +3V3: **U10 (12V)** VS is floating (`unconnected-(U10-VS-Pad6)`) + GND on a floating net; **U11 (5V)** VS ties to U10's GND-net, GND to another floating net; **U12 (3V3)** VS ties to U11's GND-net (its GND is correctly on GND). Only **U13 (5VSB)** is right (VS→+3V3, GND→GND). Effect: the 12V/5V/3V3 sensors are unpowered as drawn — the core telemetry function. Pins 1/2 (A1/A0) are the I2C-address selects and their varied strapping is CORRECT (unique addresses), so ONLY pin6/pin7 need fixing. FIX (per sensor U10/U11/U12): VS(6)→+3V3, GND(7)→GND, and delete the two mis-chaining wires that create `Net-(U10-GND)` / `Net-(U11-GND)`. Left for the owner (hand-drawn power section, owner actively editing this file) — offered to fix on request. My new detection cells are unaffected (they tap the shunt SENSE nets, not the INA238 supply). **FIXED 2026-07-08** (owner mandated the ground-up remake): chains deleted, power symbols re-seated on the pins, netlist-verified all four sensors powered; the broken SDA pull-up cell (R3 drawn 2.54mm off its pins) fixed in the same pass.
- **24-pin rev3 — stale netclass patterns (trace/via widths, found 2026-07-07).** `.kicad_pro` net→class patterns reference old net names that match ZERO nets: `HighCurrent *RAIL*`, `CAN *CAN1_P/*CAN1_N`, `USB *USB_D+/*USB_D-`. The actual rev3 nets (`+5V_MAIN`, `SENSE12V_HI/LO`, `/CAN_H`,`/CAN_L`, `/USB_DP`,`/USB_DM`) therefore fall to the 0.2mm Default class instead of HighCurrent(2.5)/CAN(0.25)/USB(0.25). Fix the patterns to match (eps/pcie/12vhpwr patterns are already correct and are the reference). Set in the GUI so it sticks (the .kicad_pro is GUI-owned). Matters for the rev3 routing you're doing now.
- **24-pin rev3 — TPS2121 power-mux input bypass (flag, owner call).** U5's input rails `+5VSB` and `+5V_MAIN` carry no local bypass cap; the Hub's TPS2121 inputs do (C9, C14/C5/C_bulk1). May be intentional (the 24-pin is the *source*; the Hub holds the bulk), but the datasheet 0.1µF-at-input is good practice for switchover stability. Decide whether to add a 0.1µF (+ small bulk) at each mux input. **DONE 2026-07-08** (ground-up remake margin bank): C18-C21 = 100nF+10uF at BOTH inputs, netlist-verified.

## 9. Watch items (no action until their trigger)

- FR-01 router migration (1.7.0 → 2.2.4) — **GATE RUN 2026-06-10, VERDICT: REPAIR — pin
  stays 1.7.0** (ledger D-20260611-042438-2273eef8; battery workflow wf_11fb2ac3-11a;
  artifacts build/fr01/). Landed anyway: version-parametric cec_fr (sha256 pins for both
  releases, `CEC_FR_VERSION` override, Java-25 app-image fallback, 2.x true-headless +
  analytics-off + per-run settings isolation); FR-02 bench + 10/10 fixtures PASS on
  2.2.4; SB-08 golden PASS under both pins; determinism PASS (2.2.4 byte-identical raw).
  TWO BLOCKERS before any flip:
  (a) UPSTREAM: 2.2.4 infinite-loops (PolylineTrace.normalize max-depth-16) on the
      12vhpwr GND net — 0 passes in 1800 s vs 6.6 s complete on 1.7.0. Related:
      freerouting#608 (2.2.x regression vs 1.9 baseline; parity work post-dates 2.2.4;
      SMD fanout disabled in 2.2). OWNER CALL: report our clean repro upstream
      (12vhpwr DSN + log)? Otherwise watch the next FR release.
  (b) TOOLKIT: no R-01 diversity axis exists on 2.2.4 — opt_time/-oit (improvement-%),
      passes, -us/-hr/-is (incl. random), --router.via_costs ALL byte-identical at
      convergence (measured, 17 runs). Repair design: board-side per-seed perturbation
      (bake_hints micro-keepouts), then re-run gate leg B (needs ≥3/4 distinct hashes).
  At flip time only: Windows runner needs a JRE 25 (no portable Windows app-image; MSI
  only) — ten-minute desk task.
- **SB-08 golden is RED on main** (2026-06-11): drc 10 > band 6, thermal max_T 153.2 > band 147.4, reproduces on a clean baseline (NOT from PR #35 — verified by stash comparison). FR routing-variance/drift; needs a re-freeze (`cec_golden.py --freeze`, human-approved) or an FR-variance investigation. Separate from PR #35.
- Windows-side VHDX compact (~110 GB back to C:) — owner todo from the 235B retirement.
- Companion diagrams (§2.9 / Appendix D SVGs) — docs follow-up, non-blocking.
- OQ-2 5VSB cap, OQ-4 cable policy, OQ-7 Enterprise/MC scoping — platform OQs, unchanged.

- [2026-07-03] OWNER SOURCING (self-assigned): slim/flexible braided RJ-45 patch cables (lock-register G2) — feeds OQ-4 lengths + D-1 kit lines. Also: internal-USB-header→USB-C kit cable is a commodity line to pick at the same pass (G1).

- [2026-07-06] **D-5a thermal update — F1 RESOLVED + eps/pcie solid joints + OQ-86 acceptance criteria** (record: docs/standard-tier-review/thermal-wave1-daughterboard-landing-2026-07-06.md; maps in thermal-maps/). **(F1)** atx24-out-db In2-lane fusing is FIXED (per-rail full-board floods, all ZONE_CONNECTION_FULL): DC-IR +5V 30A drop 384→62.6 mV, J 2874→259, cold joule 592W-runaway→3.82W; DRC 0/0, checker 113 OK. **(eps/pcie solid joints, owner observation "you have thermal reliefs as well")** route_simple() now solid on both floods (was KiCad-default thermal relief necking the 52A/39A joints): eps dT 235→141°C, pcie dT 117→70°C (−40%), tab pads now cool/solid. All 3 daughterboards now solid. **(F2 remains, owner-gated)** the still-air no-sink worst-case coupled solve still reds (atx24 ~397°C, eps 141°C, pcie 70°C) — NOT fusing-class, the board-can't-shed-worst-case-power-in-vacuum bound; the unmodelled conduction sinks (brass blades into main board + pigtail copper + chassis) + typical-vs-worst current (dT~I²) are the softeners. Owner picks: modelled+verified sink / heavier inner copper / envelope statement — decided on the OQ-86 soak. **OQ-86 bench acceptance criteria now quantified (T1b):** contact-R spread thresholds atx24 GND σ/µ≈0.21, eps≈0.28 (E3 unequal-sharing gate); single-joint soak 17.3A→~17°C / 18.3A→~19°C / 22.9A→~30°C (±20%); N-1 — only pcie survives single-joint loss (atx24 +12V/+5VSB have zero redundancy). Fold these into the sample-order/soak checklist.

- [2026-07-16] **TESTER W-SUITE PORT-RELIEF PICK** (sketch §13; context: owner ruled 4× 12VHPWR
  = configurator option, and flagged the 8-port ledger): flagship W config = tester + 24-pin +
  EPS(2-cables/1-port) + 4× HPWR + PCIe-3(3-cables/1-port) = exactly 8 nodes on Hub Pro, zero
  spare (ST suite: Hub Standard 4 ports = tester + 3 modules). PICK NEEDED: (a) populate the
  proposed 2–3 CAN-only deck expansion jacks (~$5, keeps µs MARK timing for melt-watch
  monitors — RECOMMENDED as DNP provision either way) vs (b) USB-overflow only (zero hardware,
  ms-class alignment) vs (c) someday 12-port bench Hub (field-demand tripwire). Also standing
  tester nods still open: AD9253-105 grade + buy-ahead qty, TPS55288 final, slot-architecture
  adoption, Pro-W list ($4,995 @2.6× vs $5,295–5,495 @≈3×).

- [2026-07-16] **ENT UPLINK JACK VARIANT — RESOLVED same day (owner: "tab up is preferred" + supplied the JXD1 UL export and STEP):** JXD1-0001NL is the part AND CAD of record (vendored, shield legs corrected to plated; JXD0 CAD removed — lands measured DIFFERENT, never substitute). Original bullet retained below for provenance:** the
  owner-supplied CAD assets are **JXD0-0001NL (TAB-DOWN)**; BOM-B of record names **JXD1-0001NL
  (TAB-UP, DK 553-3266-ND, $5.95)**. Same family/electricals otherwise. PICK: (a) flip BOM-B to
  JXD0 (assets already vendored, done), or (b) keep JXD1 and re-pull its CAD (SnapEDA has the
  family), or (c) confirm land-pattern identity across the pair and treat as population choice.
  Rear-panel latch orientation is the real deciding factor. ALSO — WATCH ITEM: the **full LAN9370
  datasheet stays login-locked** (Microchip site erroring on the owner's account, support
  unresponsive); intake proceeded on the public product brief DS00002819B + UL export (pin map
  verified 64/64) — retry the portal before sheet-06 capture, else use LAN9371/72 public family
  docs for strap/clock/rail detail.

- [2026-07-16b] **eMMC PRIMARY PICK — PROPOSED, needs owner nod** (manifest row #35 was BLOCKED
  pending the RFQ; owner ruling this session: research and propose now instead of waiting,
  LCSC-native preferred, consigned/DigiKey acceptable since the MPFS SoC is consigned too). Full
  detail + citations: `bom-a-compute.md` U-EMMC row, `kicad-intake-manifest-2026-07-02.md` row
  35 annotation. **PROPOSED PRIMARY: FORESEE (Longsys) FEMDNN family** — 8GB `FEMDNN008G-A3A55`
  (LCSC C5374780), 32GB `FEMDNN032G-A3A55` (C5117593, confirmed live -40°C~+85°C), 64GB
  `FEMDNN064G-A3A56` (C5117595, confirmed live -40°C~+85°C) — all three are the exact FBGA-153
  11.5×13mm 0.5mm-pitch package the already-vendored `cec-ent-mcu:eMMC_5.1_FBGA153_Generic`
  land was built to, so picking one of these is a BOM-property pass only (no new symbol/
  footprint work), same shape as the OQ-11 shunt close. **SECOND SOURCE: Micron industrial eMMC**
  (consigned, DigiKey) — `MTFC64GBCAQTC-IT` (DK 21572466, confirmed Active/-40°C~+85°C/153-LFBGA
  11.5×13mm, $82.56@25q) covers 64GB+; the matching 8GB code in this SAME generation was not
  found this session (the older `MTFC8GAKAJCN-1M-WT` is confirmed OBSOLETE and only -25°C~+85°C
  — a quick Micron/DigiKey rep check for the current 8GB "-IT" equivalent is a real follow-up,
  not done here). **REFERENCE ONLY, do not use for new sourcing:** Zetta `ZDEMMC08GA`/
  `ZDEMMC16GA` (C3029818/C7501401, zero live LCSC stock, -25°C~+85°C only) and Kingston
  `EMMC08G-ML36-01B00` (DK 15776056, the exact part our own generic land's Description property
  already cites as one of its three ball-verification sources — CONFIRMED OBSOLETE at DigiKey,
  a dead end for new orders even though its land-fit provenance stands).
  TWO ITEMS BEFORE THIS CAN LOCK, both real research findings from this session, not
  hand-waving: **(1) STOCK** — every single eMMC candidate checked across three brands and two
  distributors (LCSC + DigiKey) showed zero or near-zero live stock at intake time (2026-07-16);
  this reproduced too consistently across too many independent parts to be a stale-cache fluke
  (the search-engine-summary layer WAS caught giving a stale "in stock" read once during this
  pass — cross-checked and corrected via a direct product-page fetch before it landed anywhere)
  — it looks like a genuine current-market thin-stock condition for eMMC BGA memory generally,
  not a bad pick. Recommend an actual RFQ/rep stock-confirm on the FORESEE trio before order
  commit, same treatment as the MagJack/RJ-11-jack thin-stock flags elsewhere in this BOM.
  **(2) 8GB TEMP GRADE** — `FEMDNN008G-A3A55` read as -40°C~+85°C by extrapolation from its
  32/64GB `-A3A55`/`-A3A56` siblings (both independently confirmed -40°C~+85°C via direct LCSC
  fetch) but a separate search-snippet read for the 8GB code itself said -25°C~+85°C; a direct
  fetch of that exact product page 404'd twice this session, so the discrepancy is UNRESOLVED,
  not silently picked either way — needs a direct datasheet pull (or an LCSC/Longsys rep
  question) before the 8GB tier can be called industrial-grade with confidence. PICK NEEDED:
  ratify FORESEE as primary (with the two follow-ups tracked, not gating), or redirect to a
  different family — the research is done either way, only the sign-off is pending.

- [2026-07-16] TESTER SLOT ADOPTION: **RULED for ST** (evening: "slot bundle — soldered is
  worse in both repairability and cost savings"); integrated carve-out RETIRED (sketch §11/§12,
  BOM §3a). NEW DECISION QUEUED — **§12a KVM-aux-header tester link (ST only, PROPOSED — urgency
  DOWNGRADED same evening: owner ruled the base 4-port ledger sufficient, PCIe/12VHPWR are
  per-DUT alternates)**: now an optional-headroom/upsell question (both GPU modules docked,
  no swap step; 4-module bundle $1,399-class); OQ-85 UART/MARK-relay chapter + relay-jitter
  bench item only IF pursued.

- [2026-07-16] **TESTER DOCK = HUB MEZZANINE (§12b, PROPOSED+RECOMMENDED — owner idea "elegant
  across tiers"):** deck presents the OQ-77 Hub-side socket; Hub stacks on; tester rides the J6
  link as a NATIVE CAN node (µs MARK intact; Pro stream has a path via STREAM_P/N 8/9); all
  RJ-45 ports return to modules at every tier; SUPERSEDES the §12a UART workaround (retire on
  ratification). Feeds D-3: the socket design (from the rev3 J6 NETLIST — doc table is wrong)
  gains a second customer beyond the stacked SKU. Sub-calls: Max tester link (port vs J6-rev
  T1 pair); Hub Pro socket provision (cheap, board unbuilt).

- [2026-07-16] **ST TESTER STAND-UP — PHASE-0 DECISION CLUSTER** (sequence recorded in
  testers/tester-standard/README.md): (1) §12b mezzanine dock ratify/decline; (2) atx24
  sense-wire §7 decision (PS_ON#/PWR_OK/−12V on rev3 — gates the ST fence's timing tests);
  (3) R-bank ladder nod when the proposal lands; (4) OQ-1/OQ-10 posture for ST (ahead/behind
  the canonical gates). PHASE-1 desk task: order the OQ-86 TE blade sample set (DigiKey).

- [2026-07-16] ST PHASE-0 RESULTS: §12b RATIFIED (+ NEW FACT: mezzanine socket = standard hub
  fitment → D-3/OQ-77 owner-pen fold needed) + tester RJ-45 PoE-safe req (ENT mis-plug chain
  adopted); OQ-1/OQ-10 WAIVED for ST. STILL OPEN: (a) sense-wire §7 — the actual decision:
  approve read-taps + PS_ON# DRIVE + −12 V sense on atx-24pin-rev3 beta (buys PSU-level
  power-on for bench/self-test, NOT OS boot) — the ST tester's T1/T3/T6 + DUT sequencing ride
  it; (b) R-bank ladder nod — now **v1.1** (README table; owner's same-night overkill
  directive applied to the minors: 5 V 8 legs/40 A, 3.3 V 8/38.8 A, 5VSB 4 legs/6 A + a
  linear mini-CC loop [CoC/DoE standby points + the 500 ms peak], −12 V 2 legs; totals
  54/66, +$30–40 BOM; one nod covers ladder + field-arrangement math);
  (c) blade sample order (owner, at some point) + press-tool/lever de-fit drafts queued.

- [2026-07-16] **ST SPLIT ARCHITECTURE (load slices vs control board) — RECOMMENDED, needs nod**
  (tester-standard README §Split): per-rail hot LOAD SLICES (switch FETs/fuses/shunts/trip
  comparators/local gate drivers; thick-Cu FR4 baseline, IMS per-slice option) + pure-SELV
  control board; unplugged-harness=no-load fail-safe; one control board across ST/Pro/Max/W;
  compartments/stacking free; SE two-chamber = same architecture. If nodded, the board census
  (DESIGN-SHEET §A/§H + agent capture partitioning) updates accordingly.

- [2026-07-16] **THERMAL GRIZZLY SPONSORSHIP THREAD (owner: "they would love to sponsor this
  kind of thing"; TG supplies on hand).** TIM schedule is now spec'd as tester DESIGN-SHEET
  rule 25 (3 joint classes; paste consumption ~15 g/unit ST → ~35 g/unit W; Kryonaut-class
  load-bearing at the vernier isolation stack; KryoSheet/Carbonaut banned at isolation sites
  — electrically conductive). OWNER MOVES: (1) TG conversation — tester-line paste supply +
  co-brand line ("interfaces by TG" class); sponsorship = $30–90/unit retail-equivalent BOM
  relief vs $1–2 industrial fallback (spec is sponsor-agnostic either way); (2) deeper fits
  to raise in the same conversation: SE halo (blocks/TIM home turf, the "commandeer CPU
  blocks" thread) and the TTV SKU (reference-TIM characterization partner + their
  delid/direct-die line is directly adjacent to the IHS-cap concavity library — a TG
  partnership there feeds the demand-first gate conversations); (3) enclosed consumer SKUs
  (12VHPWR TIM-on-shunts case model, §6.6 TIM-baseplate menu) = the platform-side surface
  if the relationship lands. **OWNER RULED (same night):** no retail TG bulk purchase —
  resistor-joint + FET-stack paste = shop-stock Kryonaut / Kingpin KPX / Arctic MX-7
  ("we buy by the gallon"); sponsored KryoSheet/Carbonaut sheets ACCEPTED at the RESISTOR
  MOUNTS only if TG hands them over (both sides grounded → conductivity harmless; reusable
  across leg swaps = service win); isolation-site ban stands. The TG ask is therefore
  SHEETS + CO-BRAND (and the SE/TTV threads), not paste supply. Remaining TIM hardware =
  AlN insulator pads + shoulder washers (engineering line, BOM §3d, no owner action).

- [2026-07-17] **TESTER LOAD-PLANE SURVEY YIELDS — two owner items** (survey = sketch §8b,
  answered "any fancier way for Pro/Max?"; verdict = hybrid staircase+vernier+fast-channel
  stands): (1) NOD WANTED — **DAC80508 setpoints at Pro/Max baseline** (pull the W-tier
  16-bit DAC down; kills PWM-RC setpoint ripple feeding the CC loops; ~$7/board, 8 ch/chip;
  ST keeps PWM-RC). (2) PARKED IDEA — **regenerative/burn-in-farm SKU**: energy-recycling
  load (~90 % of 3 kW back to the wall) is WRONG for the fidelity testers (injects converter
  noise into the DUT) but is a real product for 24/7 burn-in shops; revisit if that market
  ever knocks. Adopted-without-nod (engineering): closed-outer-loop + cal-time conductance
  map (firmware contract), FPGA-timed bank strobes on Max, SCP arm relay (owner's own
  question, §3b addendum + rule 24g).

- [2026-07-17] **NOD WANTED — per-pin loadable 12VHPWR slot on Max/W** (sketch §12d FORCE
  mode): six isolated pin nodes (~15–18 extra legs + switches, +$50–80) to deliberately
  recreate the melt scenario safely — single-pin hog to the 9.2 A bar and beyond-with-consent,
  runaway-threshold characterization. Baseline OBSERVE mode (single-node slot, per-pin R-map
  via dual-ended metrology) needs no nod — it rides existing architecture. Decide at Max
  capture.

- [2026-07-17] **RULINGS BATCH (owner, this morning) — RECORDED:** (1) LADDER v1.1 RATIFIED
  in the §12c per-slot structure ([wb] markers converted; 6R SKU confirm = the one BOM-lock
  residue). (2) SPLIT LOAD-SLICE RATIFIED ("absolutely") — unit is officially multi-board;
  IMS/metal-core = per-slice at layout via electrothermal gate (W 12 V slices the likely
  earners). (3) DAC80508 Pro/Max baseline RATIFIED. (4) PER-PIN HPWR SLOT: Max/W RATIFIED;
  Pro conditional-include PASSES its fence (+$60 ≈ +1.7 % of list, §3e) → carried on Pro.
  (5) SLAM-GATE: arm-clunk sequencing all tiers (relay stays dry-switched — physics note in
  §3b); SE gets the key-interlock + molly-guard + red-button arming console (key is IN the
  coil path, a real interlock). (6) CAPTURE STOP CORRECTED: owner never stopped the
  continuation agent (accidental/system stop) — resume is DEFERRED by owner ("wait on that
  for now"), not forbidden; errand items stay owner-held. BOM re-base = §3e (margins hold
  across all six tiers).

- [2026-07-17] **W-MERGE RATIFIED ("do the swap")**: Pro-W/Max-W SKUs retired; the ~3 kW
  tier IS Pro SE $6,995 / Max SE $9,995 (sketch §13b; §14 promoted to flagship tier; BOM §3e
  re-based ~$2,700/~$3,230, margins 2.6×/3.1×; air math drawered as provenance). Loop
  realization v1 = §14b. NEW OWNER-ADJACENT ITEMS from it: (a) CPU-block partner pick for
  the FET stations (TG Mycro the synergy candidate — fold into the TG conversation; Watercool/
  EK/Alphacool/Optimus alternates); (b) bank cold-plate quotes (custom tube-in-plate, China
  $20–50 vs western $100–250 — quote at SE capture); (c) SE rad-wall fan pick reopened
  (140 mm quiet-static class, NOT the S12038 duct ruling); (d) coolant + tubing trim call
  (EPDM service runs vs hardline showcase, clear-vs-dyed); (e) CEC Radiator Tower accessory
  SKU (optional silent-3 kW external panel + QDC whips) — define at SE program start.
## Merged from claude/placement-corridor (2026-07-07 pipeline consolidation)
## [2026-06-27] DESIGN-RATIFICATION: SENSEC 40A current path (eps-8pin-rev3) cannot be carried as-built
The constraint loop (functional-grouping placer + workflow wf_8bc87458 layer-swap) ran to its wall and ESCALATED here per the CLAUDE.md human-ratification boundary. PROVEN (adversarial field-solver verify): even with a perfectly clean pour, the F.Cu SENSEC pour pinches to a 0.08-0.13mm^2 NECK at the connector->shunt squeeze (~263C / up to 2874 A/mm^2 at 40A/cable), and there is NO B.Cu mirror pour on the routed boards (derive_power_pours defaults to F.Cu-only; only synthesize_power_copper builds the F.Cu+B.Cu mirror). Placement (now functional + corridor-clean) and routing (layer-swap done properly, commit 53c883e) are EXHAUSTED -- this is a stackup/footprint decision. OPTIONS surfaced to owner: (1) build the paralleled B.Cu mirror pour + via-fence (synthesize_power_copper) + widen the shunt-pad neck geometry; (2) grow the board to relieve the connector->shunt squeeze + spread foreign routing; (3) re-examine the 40A/cable spec + the 2-pad R_2512 shunt footprint. Awaiting owner ratification before any board change.
**[2026-06-27] RATIFIED -> Option 1** (B.Cu mirror + via-fence + shunt-neck widen). Owner chose the direct fix (doubles cross-section, no board-size change). Implementing + adversarially verifying via workflow w7q41fek9 (wf_5af478c6): wire synthesize_power_copper's F.Cu+B.Cu mirror + derive_via_field fence into the route path, via-fence across the connector->shunt neck, widen the F.Cu corridor at the neck. Locked 0.5mOhm shunt VALUE untouched; any shunt FOOTPRINT/part change is flagged back here, not made. Verify gate: field max_T at 40A within bound, neck carries 40A (both layers), mirror fills, DRC/kelvin/unconnected hold.
**[2026-06-28] RATIFIED -> WIDEN THE SHUNT GAP (R2)** + fix the cec_pcb mounting-hole degenerate-bbox edge_keepout hole + nudge H2 out of the USB channel (R1). Owner chose to widen the 3.93mm shunt gap to ~6-7mm (board grows ~3-4mm taller) so the sense cluster + overflow routing fits and the built route-under can dive the overflow to B.Cu. Executing via workflow wgmom5nel: gap-widen + bbox-fix + H2-nudge + re-place + route through all 7 hard gates. Aiming for the first fully-clean eps board.
**[2026-06-28] GPU DOWN in the routing container -- cudaErrorInsufficientDriver.** cupy can't init (CUDA driver version insufficient for the runtime) -> all electro-thermal solves fall back to CPU (the GPU AMG path is dead), so fine 0.1mm solves are ~6-9min instead of ~3min. This worked during the earlier soak, so something changed (likely a WSL restart / the host NVIDIA driver). OWNER ACTION: update the Windows-side NVIDIA driver to match the container's CUDA 12 runtime (or rebuild cec/routing:gpu against the host's CUDA), then re-verify `python3 -c "import cupy; cupy.cuda.runtime.getDeviceCount()"` in the routing container. Until fixed, keep the dashboard fine grid >=0.15mm so CPU solves stay tolerable.
**[2026-06-28] RESOLVED (self): GPU-down was a stale container, not a driver update.** force-recreate routing with compose.gpu.yaml restored the 5090 to cupy. No Windows-driver action needed after all. (The driver IS adequate -- the device was just never wired into the long-lived container.)
**[2026-06-30] OWNER DECISION -- PCIe 3-port board GROW (LEVER-2, the constraint loop escalated this).** The 3-port placement is gate-clean for KELVIN (all 12 inner-edge taps seat, commit 7548d4f, build/pcie3-rev2/pcie3-rev2.kicad_pcb) but ROUTING hits a density wall: the IN/OUT Molex connectors (~21mm deep, edge-overhanging) squeeze the sense row into a ~9.8mm window and block all horizontal routing channels, so 3 cables' detection/power signals (/DETAMPC1-3, /THRESH, I2C, +3V3, GND) are forced across the F.Cu SENSEC pours with no B.Cu channel to relayer them -> foreign_on_pour=46t+11v (uncleanable), unconnected 3-4. No gate was relaxed/faked. RECOMMENDED CHANGE (ratify one or both, then re-run the route): (a) PREFERRED -- grow board HEIGHT 44 -> ~56mm so the IN/OUT connector rows sit ~6mm further from the sense row, opening horizontal B.Cu channels above+below it (directly clears foreign_on_pour + unconnected); (b) widen cable PITCH 20 -> ~24mm (board ~115mm wide) to separate the J_OUT connectors (clears the middle-cable kelvin cut-vertex). eps is clean at 2 cables/21.7mm pitch with an OPEN sense row; the 3-port packs 50% more cables into ~the same outline. This is a board-outline + gen-pcie-condensed.py change. Agent recommendation: start with (a); add (b) if the middle-cable cut-vertex persists.
**[2026-06-30] UPDATE -- PCIe 3-port grow is CONFIRMED needed (the force-trace fix did NOT avoid it).** The owner-caught redundant-SENSEC-force-trace inefficiency was real and FIXED (commit 4df3243, flag CEC_SENSEC_FORCE_POUR_ONLY, opt-in, no eps/2-port regression -- cut 3-port SENSEC tracks 80->35), but it freed VERTICAL corridor room, not the HORIZONTAL channel the wall needs. Root cause confirmed: a LAYER bind -- 3 cables' detection/power signals must cross 6 high-current pours with only 2 signal-capable layers (F.Cu + B.Cu; both inners are GND). Solid pours -> 22 foreign strand; foreign crosses -> pours shred + kelvin fails. TWO RESOLUTIONS for the owner: (1) GROW -- height 44->~56mm (recommended; opens B.Cu channels) and/or pitch 20->~24mm (~115mm wide); keeps the dual-GND stackup + the validated 62C thermal. (2) STACKUP -- make an inner layer SIGNAL not GND so foreign routes inner; no board grow but spends GND-plane area = worse thermal + return path, and ripples to the whole cable family. Agent recommendation: grow the height. Then re-route (the force-pour fix + the grow together should clear it).
**[2026-06-30] EXECUTED the height grow (owner sign-off) -- PRIMARY BIND CLEARED + verified, but a SECONDARY tap-synthesis wall surfaced (NOT pitch).** Applied H 44->56 in gen-pcie-condensed.py (per-SKU height in the SKU tuple; `_apply_height` re-centers the sense row to BAND_Y=H/2 -- the IN/OUT 45586 courtyards reach y=16.94/H-16.94 so H/2 centers the clear window; 2-port PROVEN INERT: H=44->BAND_Y=22, byte-identical). The connector clear-window grew 10.1->22.1mm and the horizontal B.Cu channels above/below the sense row went ~0.7mm -> ~6.7mm each. Regenerated the 3-port floorplan (103.4x56mm, passives 28/28). Route-oracle verdict (route_oracle_grade, gate-clean recipe, passes 10->24):
  - **WIN (the ratified target): foreign_on_pour 46t+11v -> 0t/0v** -- the LAYER BIND IS CLEARED. Thermal stays in budget (max_T ~59C / dT ~9C, gate 30). The grow did exactly its job.
  - **SECONDARY WALL: the route does not COMPLETE at the grown geometry.** kelvin_ok=False; unconnected jumped 3-4 (H=44) -> 28 (H=56), critical = every cable's /SENSEC*_LO + GND. Higher effort (24 passes) converged the DRC (49->8, mostly headless mask-bridge false-pos) but did NOT change the failing net class -> structural, not pass-budget.
  - **ISOLATED (pcbnew inspection of the routed board):** asymmetric HI vs LO. /SENSEC1_HI = 138mm2 F.Cu pour + 2 Kelvin-tap tracks -> connects. /SENSEC1_LO & /SENSEC3_LO = 136.7mm2 pour but **0 tracks/0 vias** -> the LO-side Kelvin taps (INA pad8/pad4) were never laid, so the INA LO inputs float in the pour antipad -> kelvin fail + the LO ratline. This is the **tap-synthesis path** failing asymmetrically at the taller board, which ties to the router-feasibility route()/golden synthesis gap (route_once does not run the full synthesize_kelvin_taps that cec_golden does).
  - **NEXT LEVER = the tap-synthesis fix, NOT pitch.** Pitch widens horizontal cable spacing; this failure is the VERTICAL shunt-LO->INA-LO tap, so pitch would not touch it (declined per principle: don't spend a lever on a differently-shaped, isolated cause). The grown floorplan is committed (ratified geometry banked); getting the LO taps laid at the grown geometry is the remaining work (tooling, in cec_fr's tap synthesis / the oracle route path).
**[2026-06-30] CONVERGENT BLOCKER ROOT-CAUSED (blocks BOTH the 3-port grow AND the placer-autonomy milestone-1).** Building the intent-compiler (SLICE-1b) surfaced that a FRESH synth_one-placed eps fails the route-oracle the SAME way as the grown 3-port: kelvin_ok=False on every cable's /SENSEC*_LO. Root cause (pcbnew + the synthesize_kelvin_taps `refused` report, NOT theory): the INA238 LO Kelvin tap (IN-, **pad 9**) is REFUSED by defence-2 (the clearance guard that refuses any straight tap stub crossing foreign copper). Geometry: on the VSSOP-10 INA238, IN- (pad 9, y~19.8) sits TOP-CLUSTERED next to IN+ (pad 10, y~19.3), while the LO shunt terminal is at the BOTTOM (RS.2, y~23.3) -- so the straight LO stub must travel UP across the shunt/HI band and clips foreign copper -> refused -> the INA238 IN- floats in the pour antipad -> kelvin fail + the /SENSEC*_LO ratline. The HI tap (pad 10 -> top shunt terminal) is short and clean, so it is laid. The committed hand-finalized eps (515cae7) does NOT hit this -- its INA238 seat clears the LO tap; the AUTO-seat (_seat_sense_ics) does not. **This is the single highest-leverage fix:** re-seat the INA238 so the LO tap channel is clear (or allow a 1-bend LO tap / extend tap_channel_keepout to reserve the LO channel). It is a placement/tap-guard fix (NOT a partition, grow, or pass-budget issue, all ruled out) -- and fixing it likely gate-cleans BOTH the grown 3-port and the autonomous eps. The intent-compiler is the natural vehicle (an agent issues a re-seat intent), but the seat geometry is the substance. See memory `ina238-lo-tap-refusal-blocker.md`.

## 2026-07-07 — parity-report re-freeze (CODEOWNERS-gated)
- `tests/test_cl03_compiler.T6ParityGolden` is the ONE remaining red in the 883-test suite on
  claude/pipeline-consolidation: the live compile now reads matched 22 / registry 38 /
  corpus_only 315 vs the frozen report's 20 / 34 / 317 — the checker registry legitimately GREW
  (beta-arc + branch checkers) since the freeze. Re-freezing tests/golden/parity-report.json is
  an owner act (tests/golden/** is CODEOWNERS-gated). Until then this red is expected.

## 2026-07-08 — spec §6.4/OQ-11 text correction needed (5VSB shunt, AS-BUILT divergence)
- Owner confirmed (physical rev2 board in hand) + verified in the ordered rev2 layout: the 5VSB
  shunt shipped as a 2-TERMINAL 25mΩ (Resistor Today LCSR2512FR025K9L, LCSC C494568) on the plain
  R_2512 land — the alpha schematic's Vishay WSK2512 4-terminal was swapped before order and never
  recorded. Spec §6.4 ("5VSB keeps the WSK2512... four-terminal") + the OQ-11 v1.6 text + the
  v1.3.0 register-B4 beta note now contradict the as-built. rev3's RS4 has been reverted to the
  as-built 2T part (2026-07-08, netlist-verified; Kelvin = copper-drawn taps at layout per §6.8
  like the other rails). SPEC EDIT IS THE OWNER RITUAL: update §6.4/OQ-11/B4 note to record the
  2T part (or re-ratify the WSK for a future rev — the 2T's ~±100ppm TCR vs WSK ~±35ppm is the
  trade being given up).

## 2026-07-08 — atx24 blade-row pitch contract conflict (module ⇄ daughterboard)
- The atx24-out-db as-built tab row is 10 @ 4.2mm; the module side now carries TE 63969-1
  receptacles (iteration 7) whose courtyard is 4.29mm wide — they physically cannot pack at
  4.2 (measured: courtyard/short DRC on the fresh 24-pin seed). The eps interface uses 4.7mm
  with the same receptacle and is proven. RECOMMEND: standardize the atx24 interface at 4.7mm
  contiguous (platform-uniform blade pitch) and re-pitch the DRAFT atx24-out-db tab row to
  match (it is regenerable; no fab has occurred). The fresh 24-pin synthesis proceeds at 4.7.

## 2026-07-08 — output-daughterboard study OPEN ITEM 5: CLOSED (owner ruling)
- Sense-return option: NOT shipping ("no significant drop; adds architecture we don't need").
  J_SIG1 trimmed 2x5 -> 1x4 on the module, pin order matched to the db J20 stub
  (1=-12V, 2=PS_ON#, 3=PWR_OK, 4=GND), alignment contract = collinear with the blade row,
  pad1 one field pitch beyond the last slot. The db re-pitch item (above) now ALSO carries
  this stub-position rule when atx24-out-db regenerates.

## 2026-07-08 — two RATIFIED placement checkers over-constrain (opus fundamentals audit)
- `kelvin-sense-adjacent-shunt` (ratified, max 5.0mm) REJECTS the shipped hand 24-pin:
  RS5→U12 measures 5.91mm as-built. Recommend recalibrating to 6.0mm (covers the as-built
  worst case with margin) or recording RS5/U12 as a documented exception. Your ratification.
- `decoupling-cap-owner` (ratified, 3.5mm ownership model) false-fires on 2 of 3 hand boards
  (hub C13 4.1mm; hand 24-pin C3/C4 4.0/3.5mm) and is superseded by the new calibrated
  functional 7.0mm oracle gate (passes all 3 hand boards, 0 violations). Recommend retiring
  it in favor of the oracle term, or bumping to 7.0mm. Your ratification.

## 2026-07-08 — orphaned checker calibration (pre-gating)
- The high-current pour family (high-current-pour-present / min-pour-cross-section /
  trace-width-high-current) and cec_dfm_check's DFM classes are now WIRED into the oracle
  verdict as ADVISORY fields. Gating them needs calibration you should ratify:
  (a) pour-present's net classification name-matches /DET12V + /ATX_NEG12V (signals) as
  high-current — needs the straddle-pair-derived force-net list instead of name heuristics;
  (b) the DFM set counts 94 hits on the SHIPPED 12vhpwr fab board — the type list needs
  triage (which classes gate vs report) against boards you accept.

- [2026-07-09] SPEC fold-in owed: per-cable output-field UNIFORMITY ruling (pinout free within ampacity; identical across cable positions + across PCIe-2/3 SKUs -- owner, 2026-07-09, production/interchangeability grounds). Pipeline enforcement landing separately; the spec §2.8-adjacent text needs the owner ritual.
  - SPEC TEXT READY (agent-drafted, 2026-07-09): 'Every cable position's output field on a per-cable board is a geometrically identical, interchangeable unit -- output blade tabs at a single uniform cable pitch, each cable's output pour byte-for-byte the same shape laid over its own tabs -- enforced by a route-time gate and the derive-once-stamp-N pour rule, so a daughterboard built for one slot fits every slot.'

- **[2026-07-11] Windows TdrDelay bump (10-min desk task, optional):** sustained GPU solver
  bursts on the 5090 (which also drives the display + AllMyStuff's WebView2 UI) caused a
  display-driver stutter/reset — dmesg `dxg ioctl -22` burst; your AllMyStuff remote terminal
  dropped in the same event. Agent-side default is now CPU-AMG for interactive-hours solves, so
  this is optional: raising `HKLM\...\GraphicsDrivers\TdrDelay` (e.g. 2->10s) gives compute
  kernels patience and stops the resets if you want the GPU path while at the machine.

- **[2026-07-23] TWO GOLDEN RE-FREEZE RITUALS (CODEOWNERS-gated, from the 20-red test triage):**
  (a) **CL03 parity golden** (`tests/golden/parity-report.json`): the live checker registry
  legitimately grew 34 -> 42 since the freeze (new: decoupler-adjacency-k5, ecap-edge-distance,
  fiducial-protocol, kelvin-sense-no-connector-tap, mlcc-edge-orientation,
  no-foreign-on-high-current-pour, sense-body-clear-of-pour, via-on-pad; +6 corpus entries).
  Ritual: `python3 scripts/cec_corpus_compile.py`, copy `build/corpus-compiled/parity.json`
  over the golden in an owner-approved PR. Until then `test_cl03_compiler.T6ParityGolden`
  stays a known-red (honest: enforcement growth, not rot).
  (b) **route-oracle fixture** (`tests/golden/fixtures/route-oracle/eps-rev3-n2`): the
  2026-07-22 injection fail-closed correctly stamps it INJECTION INCOMPLETE (4/5 SENSEC nets
  inject no current on that routed state). Either the injection path gets completed for the
  fixture class (thermal-injection lane) or the fixture re-freezes under the newer craft
  standard (FOLLOWUPS already owes that re-freeze). Do NOT relax the fail-closed -- it kills
  a real vacuous-pass mirage. `test_route_oracle.test_gate_clean_placement_passes` stays a
  known-red until one of the two lands.

- **[2026-07-23] 24-PIN RUNTIME H-GROW (74x55 -> 74x59) vs the no-growth ruling — YOUR CALL:**
  every 24-pin wave materializes at H=59, not the static 55: the pre-existing SHUNT_GAP
  lever ("SHUNT_GAP may grow H", cec_fresh_wave BOARD_WH note) auto-grows the height for
  shunt-row spacing legality. It predates and has been firing through your 2026-07-23
  shrink-only ruling ("growth needs exhausted-ideas + my sign-off"). Options: (a) sign off
  H=59 as the 24-pin's working envelope for now; (b) direct a machinery pass to make the
  shunt row legal at 55 (walk-pitch/cell work — the honest-but-larger effort); (c) let the
  post-clean shrink pass reclaim it later (the documented plan of record: "the shrink pass
  comes after a gate-clean baseline exists"). Agent default until ruled: (c) — no further
  growth, mechanism left as-is, flagged on every readout.

- **[2026-07-24] USB BACKFEED INTO FAULTY-PSU BULK (owner discovery, CONFIRMED by transient
  sim) — BETA DESIGN DECISION:** with a module USB-attached and a dead/faulty PSU connected,
  VBUS charges the PSU's 5VSB bulk through the module's ORing diode (24-pin: directly through
  the 25mohm shunt; other modules: through the RJ45 tree into the hub's 4700uF hold-up).
  Simulated: Ipk ~27A in all cases; Q = 0.5mC (100uF) to 22mC (4700uF tree) vs the 50uC USB
  inrush budget; a 2ohm-faulted PSU draws ~400mC SUSTAINED -> host port eFuse trips every
  time (or rail sag on unprotected benches). The HUB is already safe (TPS2121 mux: reverse
  blocking + ILIM + soft-start, both stages). The MODULES' SS34 ORing diode blocks only the
  reverse direction (PSU->USB); the forward path is unlimited. PROPOSED (quality-first):
  propagate the hub front-end pattern -- TPS2121 (C485916, already sourced/vendored) as the
  module USB ingress: VBUS + the module's 5VSB source as mux inputs, logic rail as output;
  kills the class at the root (~$0.6/board; alternatives TPS2115A ~$0.5 or TPS2553 load
  switch + keep D2). Needs your sign-off as a beta-line schematic change to every module.
  INTERIM (no respin, do now for PSU-tester work): a powered USB hub or USB isolator between
  the bench PC and any module when testing suspect PSUs = sacrificial per-port limiting;
  document in the tester workflow (also: a tripped port reads as "dead module" -- worth a
  troubleshooting note so it is not misdiagnosed). First-article bench item if adopted:
  verify TPS2121 reverse behavior with OUT driven while both inputs dead, module topology.
  - **ILIM ruling follow-up (owner question 2026-07-24, "is ILIM specced for that / rely on it alone?"):**
    NO single reliance -- the load-bearing mitigation is the mux's INPUT ISOLATION (back-to-back
    FETs; the PSU bulk is simply not in the USB circuit), not the limiter. ILIM+CSS only handle
    the module's own local caps: at the hub-proven C_SS 2.2uF (~10ms ramp), inrush ~= 50mA --
    three orders under any port limit; spec ILIM ~1A (above ESP flash-burst ~500mA, under port
    budgets; +-20% accuracy irrelevant to safety). DEFENSE-IN-DEPTH spec for sign-off:
    (1) TPS2121 ingress per module (isolation = layer 1); (2) ~750mA-hold polyfuse on VBUS
    AHEAD of the mux (~$0.03, layer 2 -- protects the host even against a failed/mis-soldered
    mux); (3) OVP pin set (~6V IN1 cutoff) so a faulty PSU shoving a high 5VSB disconnects
    instead of cooking the logic (free margin for the PSU-tester environment); (4) FIRST-ARTICLE
    BENCH GATE: unpowered reverse behavior, OUT driven at 5V with both inputs dead (the blocking
    specs assume a live device -- this is the one datasheet gap that needs measurement).
  - **KVM-path extension (owner catch 2026-07-24, "this would also cause our KVM route issues"):**
    CONFIRMED and WORSE than the module case -- as-built, J_KVM pin 1 is a RAW +5VSB rail tap
    (the §2.9 three-source OR is still PROPOSED = OQ-53..56 open), so: (a) a PC-USB-powered
    NanoKVM faces the hub 4700uF + the ENTIRE module 5VSB tree (eFuse-trip class, nothing in
    series); (b) a powered hub back-drives the PC port THROUGH the KVM (its header 5V ~= its
    VBUS); (c) even the intended wall-wart forensic path works by back-driving U7's OUT -- the
    exact unpowered-reverse bench-gap case. PROPOSED RESOLUTION (resolves-toward OQ-53/55):
    third TPS2121 cascade stage -- KVM 5V as the LOWEST-priority mux INPUT (spec §2.9 order:
    MAIN_5V > 5VSB > USB > wall-wart/KVM), + ~1A-hold polyfuse on the KVM 5V pin (defense
    layer 2; D7 ESD on the ref pin already present). Turns the forensic path into a designed
    input and fixes all three directions with the already-sourced part. INTERIM bench rule:
    never connect the NanoKVM USB-C to a PC while its aux cable is on a powered hub; wall-wart
    only for the forensic path. The first-article unpowered-reverse bench gate now covers TWO
    load-bearing cases (module ingress + KVM path).
  - **STATUS (2026-07-24, this row + both sub-rows): SPEC'D — spec/BOM half DONE, schematic
    half PENDING.** The ratified package landed as controlled spec **v1.6.0** (Document
    control summary; §2.9 hardening-block + KVM third stage; §4 aux-link row note; §6.14
    module USB-ingress mux block incl. the ARGB per-source-diode-OR exclusion; §9 ~+$1.0/board
    note; OQ-53/OQ-55 resolution notes per the no-silent-rewrite convention; §11 full entry;
    Outstanding board action 7 opened) with 2026-07-24 owner-ruling provenance citing these
    rows. Per-board part/refdes/net-move plan (real LCSC-verified parts: TPS2121 C485916
    stock 3,473; VBUS polyfuse Littelfuse 1206L075/16WR C371166 stock 7,735; KVM polyfuse
    FUZETEC FSMD110-16-1206R C5707763 stock 1,015 — restock watch; ILIM 100k→1.24A typ w/
    datasheet math, OV1 47k/10k→6.04V, PR1 100k/33k→4.27V, C_SS 2.2uF C23630):
    `docs/usb-ingress-bom-delta-2026-07-24.md`. Generated bom/*.csv untouched (regenerate
    from schematics). REMAINING: the beta schematic implementation pass (Sonnet via MCP,
    CLAUDE.md action item 6) on the 5 sensing modules + hub-standard-rev2, then the
    first-article unpowered-reverse bench gate (owner clock). Interim bench rules are in
    force and recorded in spec §2.9.
  - **OWNER RULINGS 2026-07-24 (in-session) on the survey findings:**
    (a) **Finding 3 SIGNED OFF**: hub OV dividers on every TPS2121 stage (U5/U7 + the new KVM
    stage), same 47k/10k ~6.04V posture as the module package -- LUMPED into the running
    schematic pass (forwarded to the agent same-day). Spec addendum note owed (v1.6.x) at the
    morning consolidation.
    (b) **Finding 1 (mains ingress) RULED -- layered posture**: (i) a testing-METHODOLOGY smoke
    test before sensitive equipment ever connects to a DUT PSU (pre-flight with sacrificial/
    protected instrumentation); (ii) fast-shutdown-on-detection where feasible -- the 24-pin
    rev3's PS_ON# drive is now a DIRECT PSU-shutdown actuator for the tester (owner caveat,
    recorded verbatim in intent: NOT guaranteed on a faulty PSU -- treat as mitigation, never
    as the safety case); (iii) full station-safety hardware (RCD/GFCI + isolation transformer +
    earth-bonded frame w/ M3 chassis bond) = a PRO/MAX TESTING-STATION tier feature. The
    tester product spec carries all three layers when drafted.
  - **SPICE VERIFICATION LANDED (96d93157, docs/spice-backfeed-verify-2026-07-24.md, ngspice 44.2,
    datasheet-fit models):** mitigated design PASSES B/C/D with 82-1029x margins; baseline confirms
    ~27A (and NEW: a healthy 3300uF PSU alone crosses the 2.5A/1ms hard-trip -- no fault needed);
    KVM unmitigated is WORSE (33.3A). TWO MARGINALS FOR YOUR EYE: (F) the LP5907 sees a real
    0.8-7.4us excursion above 6.5V abs-max during a fast 12V cross-rail fault -- governed by the
    TPS2121's UNDOCUMENTED OV response time (options: accept-with-bench-check, or a small output
    clamp/TVS; your call at the schematic review); (E) unpowered-reverse confirmed genuinely
    unspecified -- but the layer-2 polyfuses bound the worst case (trip 5-27ms even with ZERO mux
    protection), so the bench gate confirms rather than carries the safety case. Methodology flag:
    the repo's "~10ms C_SS ramp hub-proven" figure is untraceable; datasheet Table 9-1 predicts
    ~125ms (12x gap) -- both pass as simulated, but the downstream "~50mA inrush" estimate should
    be restated from the datasheet figure.

## 2026-07-25 — HUB INNER-LAYER DOCTRINE: two owner rulings conflict (DECISION OWED)

**The conflict.** 2026-07-23 (recorded verbatim on `hub-standard-rev2.pour_asks` in
`scripts/cec_fresh_wave.py`): *"do the ugly giant pours inside of that layer instead of on
top"* — power floods belong on the freed In2, because post-route additive floods do not
consume routing space, so In2 is empty at route time and still serves as a third routing
layer. 2026-06-14 stackup ruling: the hub's second inner is a **SIGNAL** layer. A 2026-07-25
in-session discussion (owner asked for industry practice, then approved moving rails to the
2 oz outers) was **BACKED OUT UNAPPLIED** once the 07-23 ruling surfaced — the agent should
have surfaced it before recommending. Nothing about the hub's rail layers has changed.

**Measured cost of the current (07-23) doctrine**, on a fresh routed hub
(`build/hubfix/doctrine-routed.kicad_pcb`, seed 260, post-SWIG-fix):
- B.Cu carries 125 segments / 790 mm of signal.
- **19 of them (15%) cross ≥2 different In2 nets** — a reference-split crossing each.
- **127 mm (16%) of B.Cu length runs over In2 void** — no reference copper beneath at all.
- In2 rail floods: `/VCC_P1` 4434 mm², `GND` 323 mm², everything else ≤41 mm².
- No dead zones (the 07-25 hygiene reapers work: the previously-measured 0 mm² `/PSU_5V`
  and floating `/+5V_HOLD` are gone).

**Separate defect, independent of the doctrine (recommend fixing either way):** `/VCC_P1`
alone occupies **4434 mm² — 72% of the 88×70 board** — for a per-port RJ-45 VCC feed of
~0.5 A, which IPC-2152 satisfies with a fraction of a millimetre of width. That is the
"giant amorphous blob" class from the 24-pin review, on the hub, and it is what squeezed the
new In2 GND fill down to 323 mm². Flood extent should follow the net's ampacity + reach, not
the leftover area.

**Options:** (a) KEEP 07-23 (floods on In2) and let the GND fill take whatever the floods
leave — the 15%/16% reference numbers stand; (b) rails to the 2 oz outers, In2 = signal +
stitched GND fill (mechanism is landed and inert: set `power_pour_layers` on the board);
(c) keep floods on In2 but size them to ampacity, which likely fixes most of the 15%/16%
without touching the doctrine at all.

**Landed regardless (both doctrines benefit):** post-route In2 GND fill at priority 0 with
island removal (`cec_fr.add_inner_gnd_fill`, `inner_gnd_fill` board param) — measured
5510 mm² before the floods take priority, 323 mm² after.

## 2026-07-25 — 12VHPWR FORCE COPPER: RESOLVED same day (row kept for the record; my first diagnosis was wrong)

**Measured regression** (07-19 vs today, same board/params class): SENSEP lane copper
480.8 mm → 119.7 mm, locked segments 164 → 62, **max lane width 2.50 mm → 0.25 mm**. On a
600 W / 50 A connector board that is a fusing hazard, not cosmetics. The 0.25 mm copper is
not a shrunken lane — it is Freerouting routing the 12 V nets at signal width because **no
force lane was laid at all**: `[materialize] force lanes: 0/6 laid`.

**Root cause chain, each step measured:**
1. The **via-in-pad ruling (2026-07-25)** correctly excludes barrels overlapping ANY pad.
2. The LO via field's search window sits directly under the shunt's LO pad — which is also
   where the **sense cell** packs the INA240 for short Kelvin. Named blockers, identical on
   all six lanes: `pad U10.5 x12, pad RS1.2 x10, pad U10.6 x7`.
3. Widening the search to walk the lane's own descent (landed) gets past the via site, and
   the lane then refuses one gate later: `LO spoke vs RFL1.2 [/IN1_N]` — the spoke from the
   shunt pad to the relocated field crosses the cell's own filter resistors.
4. Underneath it all the placement walk is already over-constrained:
   `[rails] 6 cols need 60mm > 41mm avail -> walk INFEASIBLE at the 9.0mm cell floor`.

**Why this is an owner decision and not an agent fix:** every remaining path touches a
ratified rule — (a) exempt the lane's OWN shunt pad from the via-in-pad ruling (via-in-pad
is an assembly/solder-wicking concern; filled/capped vias are a normal fab option, but it is
your ruling to relax); (b) loosen the sense cell's Kelvin packing to open a lane corridor
(cell geometry is blueprint-ratified); (c) grow the board, which the 2026-07-23 standing rule
forbids ("machinery, never millimetres"); (d) build a real path search that routes the LO
spoke AROUND the cell instead of straight — the only option that touches no ruling, and the
largest piece of work.

**RESOLVED THE SAME DAY, NO DECISION NEEDED — and the framing above was wrong.** Owner
pushback ("it *was* just fine, something we just did broke it all") was correct: this was a
regression, not three rules colliding. Two defects in the 07-24 via-in-pad guard caused it,
both fixed in `cec_force_lanes` without touching the via-in-pad ruling, the ratified cell
packing, or the board size:

1. **Phantom square pads.** The guard tested `half = max(w,h)/2` on BOTH axes, modelling every
   pad as a square of its longest dimension. The 3.35 × 1.23 mm shunt LO pad excluded ±1.675 mm
   in y where its true half-extent is 0.615, and the INA240's 0.60 × 1.95 mm pads excluded over
   3× their real width. That phantom copper — not the ruling — sealed the via window. Half
   extents now come per-axis from the pad's real bounding box (rotated pads included).
2. **Reachability checked too late.** Sites were picked blind to the spoke and the spoke was
   validated only after the whole field was chosen, so ONE unreachable site refused an entire
   50 A lane. Each candidate site now proves its own spoke during the search.

**Verified on the same board/seed that produced 0/6:** `force lanes: 6/6 laid`, lane copper
**480.8 mm at 2.50 mm max width** — the exact 07-19 good-era figure (broken: 119.7 mm at
0.25 mm), structural DRC 27 → 15. Options (a)–(d) above are all moot; nothing was relaxed.

**Landed meanwhile (no ruling touched):** the refusal now names its blockers (`pad U10.5 x12,
...`) instead of an opaque "no clear LO via site" — it took two rounds of that message to
find this, and the next person should not pay that cost again.

## 2026-07-25 — "NOTHING PLACES INSIDE A POUR" (owner ruling): measured, not yet enforceable

**The ruling:** the pour is set first and is never encroached upon; if a placement cannot work
without a pour incursion, the POURS get redone rather than the rule bent.

**What landed:** `cec_constraints.laid_pour_incursion_summary` + the
`no-incursion-in-laid-pour` checker, measured against the pours ACTUALLY ON THE BOARD and
including PARTS (not just tracks/vias). Every grade now reports `incursion` and the wave
prints it. This was needed because the existing `no-foreign-on-high-current-pour` rule
re-derives a corridor box instead of reading the laid pours: it reported `foreign=0t` on the
eps winner while that board carried **4 foreign pads (C1, C20), 7 tracks and 4 vias** inside
the pours.

**Not folded into the gate yet, deliberately.** Nothing in the pipeline can currently satisfy
it, and a gate no board can pass is a stopped line. The two halves that are missing:

1. **Placer avoidance.** The mechanism exists (`pourfirst_avoid_boxes` +
   `_legalize_avoiding_pours`, used by the p8/p9 passes) but is fed only by the pour-first
   freeze. MEASURED DEAD END: enabling `pour_first` on eps produces a board with **no force
   pours at all** — the solve finds the nets already connected, the single-owner whitelist
   then drops every manifold, and the empty frozen state supersedes the live asks. It reported
   `incursion=0` for the worst possible reason. Do not enable pour_first on the cable boards.
2. **The redo loop.** The pours are derived FROM the placement (connector→shunt corridors), so
   "pours first" needs a real two-pass: place anchors → derive pour regions → place the rest
   avoiding them → re-derive → converge, with the owner's escalation (placement impossible ->
   redo the pours) as the loop's exit. That is an architectural rung, not a patch.

**Recommended sequence:** (a) feed the placer avoid-boxes from the PourPlan corridors rather
than the pour-first freeze — that alone should clear the 4 foreign PADS, which are the part of
the ruling nothing else can fix; (b) then the two-pass convergence; (c) then flip the gate on.

## 2026-07-26 — NET-CURRENT MODEL: RESOLVED for the tabled boards (owner basis applied)

Surfaced while sizing via fields (owner: "don't just say it gives some amperage without
checking it against design spec... plan for worst case"). `cec_synth_pipeline._net_currents`
assigns any net matching `"3V3"` a flat **0.8 A**. That figure matches **neither** spec anchor:

* the module's own **+3V3 logic rail** is bounded by its source — the **LP5907 LDO, 250 mA
  maximum per the TI datasheet** (spec Hub regulator row). 0.8 A is **3.2× the ceiling**.
* the **24-pin ATX 3.3 V RAIL** is ~**18 A** — three ATX 3.3 V circuits against the
  **6 A/circuit** bar (spec §2.8). The 6 A figure is PER CIRCUIT, not the rail: the
  2026-07-06 re-ratification (TE 63969-1, 22.9 A at 125% = 18.32 A/joint) gives atx24 ten
  joints with **3V3 ×2**, and two blades only make sense above one joint's 18.32 A. (My
  first pass mis-read the per-circuit figure as the rail — owner correction 2026-07-26:
  "we have two blades, because I have seen much more amperage than that.") 0.8 A is
  **~22× too small** for that rail.

The same function routes every `_HI`/`_LO` net to `cable_current_A` (default 40 A) regardless
of which rail it belongs to, so a 24-pin `/SENSE3V3_HI` — a 6 A-class circuit — is modelled at
40 A while `+3V3` is modelled at 0.8 A.

Anything sized from these numbers is guesswork: pour widths (IPC inverse), via counts, the
electrothermal injection, and the ampacity-deficit prints all consume them. Via sizing now
takes the spec's own margin policy (§2.8: continuous rating ≥125% of sustained worst case at
≤30 °C rise) applied to a stated per-net current, but the per-net current itself still comes
from this model.

**Owed:** a per-board net-current table grounded in the spec anchors (6 A/circuit for 24-pin
rails, LDO ceilings for logic rails, ~13 A/pin → 52 A/cable EPS, ~39 A/cable PCIe, per-pin
12VHPWR), replacing the substring-matched defaults. Until then, treat every current-derived
number on the 24-pin as unverified.

**RESOLVED 2026-07-26** for the four tabled boards. `_SPEC_NET_CURRENTS` in
`cec_synth_pipeline` now carries a per-board, per-net design-basis table consulted ahead of
the substring heuristics, every figure sourced:

* **24-pin 3.3 V and 5 V = 20 A** — owner ruling 2026-07-26 ("the most we're going to see is
  like 20 A on 3v3 and 5V, and with margin we should be good"). This is the REAL ceiling and
  supersedes per-pin arithmetic: J3 physically carries 4× 3.3 V, 5× 5 V, 2× 12 V circuits
  (counted from the netlist), but no PSU sources the full 6 A bar on every pin at once. The
  agent's first pass derived 5 V as 5×6 = 30 A, which needs 37.5 A at the 125 % margin and
  EXCEEDS its two ratified joints (36.6 A) — a teeth test caught the contradiction.
* 24-pin 12 V = 12 A (2 circuits × the 6 A bar; 15 A at margin vs one joint's 18.32 A).
* 24-pin 5VSB = 3 A (ATX standby is a 2.5–3 A rail, not a 6 A circuit).
* logic rails bounded by their SOURCE: `+3V3` = 0.25 A (LP5907 LDO ceiling), `+5VSB` = 0.5 A.
* cable boards keep the owner per-cable basis: EPS 52 A, PCIe 39 A, 12VHPWR 9.2 A per pin.

Teeth assert each rail against its RATIFIED JOINT COUNT at the 125 % margin, so a future
current edit that outgrows its blades fails the suite instead of shipping.

**Still open:** boards outside the table (hub, argb, eps-rev3) fall through to the substring
heuristics, and `GND` still takes `cable_current_A` on every board.

## 2026-07-26 — PCIe-3port seat conflict: diagnosed, blocked on the anchor_pins frame

That board has published only placement-only skeletons for days. Cause is exact: the third
cable's sense cell seats at x≈87.5 and the RJ-45's default seat spans x 82.9–101.7 /
y 11.6–28.6, so **U32 (a SOT-23-5) lands entirely inside J1** — `courtyard overlaps J1|U32`
on every variant and every seed, before routing.

Geometrically there is room: U32's row ends at y 24.1 and the board is 44.1 tall, so a jack
seat at y 31–35 clears it while keeping the right-edge overhang the cable needs, with no
dimension change. **That fix was tried and reverted**: `anchor_pins` does not place in the
frame the measurement assumed — every trial (y = 31, 32, 33, 34.5) failed earlier with
`J1 1 pad(s) out of bounds`, where the unpinned board passes that same check. The
anchor_pins coordinate convention needs establishing before pinning any connector this way;
until then the board stays as it is rather than trading one refusal for an earlier one.

## 2026-07-26 — DECISION NEEDED: two current tables disagree on the 24-pin rails

Found while wiring the pour-eligibility gate (a rail a track carries should not get a
plane). Two sources feed current-dependent decisions and they do not agree:

| net | `cec_thermal_overlay` | `spec_net_current` |
|---|---|---|
| `/SENSE5V_HI` | **25.0 A** | **20.0 A** |
| `+5VSB` | **5.0 A** | **0.5 A** |
| `/SENSE5V_LO` | absent | 20.0 A |
| `+3V3` | absent | 0.25 A |

The spec table encodes your 2026-07-26 ruling ("the most we're going to see is like 20A on
3v3 and 5V"); the overlay's 25 A predates it. The `+5VSB` gap is larger and may not be drift
at all — 0.5 A reads like the module's own standby draw while 5.0 A reads like the
pass-through rail, i.e. two different quantities sharing a name.

Nothing was silently reconciled. The pour gate takes the **larger** of the two, so a rail can
never lose copper to the smaller of two disagreeing numbers. But the two tables also feed
THERMAL gates, where max() is not automatically the right rule, so this needs your call:
which table is authoritative per quantity, and is `+5VSB` one net or two?

## 2026-07-26 — incursion decomposed: it is THREE problems, not one

The 24-pin's "incursion 127/103/173" has been quoted as a single number. Measured by kind
and layer on the s963 winner it splits into three items with different owners:

| kind | layer | n | owner |
|---|---|---|---|
| pad | F.Cu | 102 | PLACER — parts seated inside laid pours |
| via | In2 / B.Cu / F.Cu | 93 / 47 / 33 | ROUTER — inner reservation just landed, expect movement |
| track | F.Cu / In2 | 92 / 11 | ROUTER — same |

By producer, the biggest pad group is **`patch` (69)** — the guaranteed shunt patches. Those
sit exactly where the Kelvin rule REQUIRES the sense IC to be, hard against the shunt's inner
edge. So most of the placer-side number is not a part that wandered into a pour; it is the
"placements literally cannot work without a pour incursion" case you named on 2026-07-25,
where the answer is to redo the POUR (leave the tap window), not evict the part.

That matters for sequencing: an eviction-only fix would fight the Kelvin gate and lose. The
work is a pour-redo loop, and it should be scoped against these three numbers separately so
progress is visible instead of averaged into one figure.

## 2026-07-26 — pour-fix validation: 6 rounds x 4 boards, seeds 990-1001

| board | n | pads | tracks | vias | diag | stray | gap | dead |
|---|---|---|---|---|---|---|---|---|
| eps-8pin | 6 | 2-6 | 0-9 | 1-5 | 0-2 | 0 | 0 | 0 | (pour_over) |
| pcie-8pin-2port | 6 | 9-21 | 2-9 | 5-12 | 0-2 | 0 | 0 | 0 | (pour_over) |
| 12vhpwr-standard | 6 | 0 | 0 | 0 | 0-2 | 0 | 0 | 0 | (pour_over) |
| atx-24pin-rev3 | 6 | 69-72 | 53-78 | 13-32 | 3-5 | 0-5 | 0 | 0 | REAL |

Verified on ALL SIX 24-pin winners, not one sample: `+3V3` never pours (the 391mm2 In2 slab
across the shunt row is gone) and `/SENSE3V3_HI` never touches In2 -- 2-3 zones at
~350-415mm2 on F.Cu+B.Cu, against six zones on three layers at 1869mm2 before. EPS
connectivity held (unconn 24 vs a 21-24 pre-fix band) with kelvin_ok intact, so reclaiming
~3900mm2 of copper cost nothing.

STILL OPEN, unchanged by this work: the 24-pin's 69-72 pad incursions are a structural floor
(five seeds, no movement), ~69 of them `patch` pads where the Kelvin rule requires the sense
IC. That needs the pour-REDO loop -- carving the patch reservation at PLAN time around the
sense IC's required seat. Carving it after placement would only redefine the region to match
reality and make the metric meaningless, which is why it was not done as a quick fix.

## 2026-07-26 — DECISION NEEDED: the candidate reference is stale because pour quality is not ranked

The per-board `candidate/` folders are the reference you open. After today's pour fixes the
24-pin's stored candidate is STILL the pre-fix board (`band-core-mid-compact-s390`): +3V3
poured, /SENSE3V3_HI on three layers, 6 zones, 974mm2 -- i.e. it still shows every defect
reported today, even though the pipeline no longer produces them.

Promotion ranks on the routing sort_key alone, and unconnected sorts FIRST:

| | stored (s390) | new (s1000) |
|---|---|---|
| pour overlaps (p/t/v) | 370/111/171 | 72/71/21 |
| long diagonals | 17 | 5 |
| stray vias | 14 | 0 |
| DRC | 86 | 26 |
| unconnected | 114 | 127 |

So a board that is 5x worse on pour overlap, 3x on diagonals and 3x on DRC keeps the slot on
an 11% unconnected edge. Nothing was silently re-ranked -- what "best" means is your call.
Options: (a) add pour-quality terms to the sort key, (b) keep routing-first but refuse to
promote a candidate that regresses pour metrics, (c) leave as-is and read candidates as
"best routed", judging pour quality only from wave winners.
