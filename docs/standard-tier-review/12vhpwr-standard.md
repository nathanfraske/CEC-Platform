# 12VHPWR Standard — refinement review (space / consumer fit / fab-readiness)

Read-only review, 2026-07-03. Ground truth = `modules/12vhpwr-standard/12vhpwr-standard-module.{kicad_sch,kicad_pcb,kicad_pro}`,
`bom/`, `fab/12vhpwr-standard-proto-v1/`, `DRC.rpt`, spec §6.1/§6.4/OQ-8/OQ-11, CLAUDE.md.

## 1. Fab-readiness

**Measured state of the routed board** (not just CLAUDE.md's claim): `DRC.rpt` (2026-06-05) shows
**0 unconnected pads, 0 copper/clearance/courtyard violations** — the 15 hits are all
`silk_edge_clearance` / `silk_overlap` / `silk_over_copper` (cosmetic). Board outline measured from
the report's coordinate spread: **58.0 × 80.0 mm** (X 112.875–170.875, Y 58.35–138.35), matching the
README's "~58×80". Stackup measured from the `.kicad_pcb` layer table: F.Cu/B.Cu 0.07 mm (2 oz),
In1.Cu/In2.Cu 0.035 mm (1 oz) — the 4-layer 2/1/1/2 claim is correct. A single combined GND zone
pours **both** inner layers (In1.Cu+In2.Cu, one polygon, ~57×79 mm span) — no F.Cu/B.Cu zones exist;
the "12V pours" are 2.5 mm **tracks**, not zone objects. `fab/12vhpwr-standard-proto-v1/` contains a
full 25-file Gerber+drill+CPL+BOM set (dated 2026-06-06), i.e. this really is fab-package-complete.

**Residual list a–e, verified:**
- **(a) Mirror lanes.** Measured per-net copper split (F.Cu vs B.Cu length) on all six `/SENSEPn_HI/_LO`
  nets: e.g. lane 6 HI is 18.35 mm F.Cu vs 7.0 mm B.Cu, lane 6 LO is 8.5 mm F.Cu vs 11.8 mm B.Cu — every
  lane is predominantly single-layer with a short opposite-layer detour, **not** the CLAUDE.md-described
  full-length F.Cu+B.Cu parallel mirror. Confirmed as described: a margin improvement (thermal already
  passes per the case-cooled FEM), not a correctness bug. **Not fab-blocking for a first consumer run**
  given the passing thermal number, but the honest one to fix before a "safe under sustained imbalance"
  claim gets stronger.
- **(b) Transition vias undersized.** Measured directly: **120 vias on `/SENSEPn` (12V power) nets at
  0.6 mm/0.3 mm**, vs. the Power12V netclass spec of 0.9 mm/0.5 mm (only 9 vias board-wide are at
  0.9/0.5). At ~8.3 A/pin nominal this is inside the 0.6/0.3 via's ~2 A@10°C rating only because ~5–10
  vias cluster per transition (paralleled), so it isn't a per-via overload — it's a **derating-margin**
  gap versus the netclass's own stated intent, worse under the sustained-imbalance/hog case the FEM
  flagged in the punchlist. Fix is mechanical (bigger via, same layout) — low risk, should land before
  a production rev but is not why proto-v1 would fail on a bench.
- **(c) OQ-11 — now actually LOCKED, board/BOM text is stale.** Spec v1.2.0 (2026-07-02, owner-delegated)
  locks 12VHPWR per-pin shunt to **Bourns CSS2H-2512R-1L00F**, the exact part this board's BOM already
  sources (LCSC C4175647). But the schematic still carries, on **all six RS1–RS6**, the literal property
  `Note = "OQ-11 candidate (spec §6.4 CSS2H 1mΩ); shunt part NOT locked"` (verified by direct grep,
  `12vhpwr-standard-module.kicad_sch` lines 5301/5607/5913/6219/6525/6831), and `README.md` / the BOM
  notes repeat "OQ-11 still OPEN". **This is a pure documentation-sync gap** (the part was right all
  along) — a 1-line property edit across 6 symbols, zero rework. Cheap to close; do it before calling
  the module "locked" externally to sales/customers.
- **(d) J3/J4 consigned.** Confirmed: BOM has no LCSC for J3/J4 (Molex 219116/2191161161) — correct by
  design (no board-mount female 12V-2×6 exists; J4 is a captive pigtail anyway), but it means the
  **$21 BOM figure below excludes both connectors and the pigtail assembly** — see §4.
- **(e) Silk cleanup.** Matches DRC.rpt exactly — 15 cosmetic hits, all silk. GUI finishing pass, no
  engineering risk.

**Separately found, not in the CLAUDE.md a–e list — real and still open:** the constraint-swarm punch-
list (`12vhpwr-review-punchlist.md`, P1 #1) flagged **U4 (REF3030) too close to U3 (LP5907 LDO)** —
"6.1 mm pad-to-pad... move U4 to ~(146.0, 105.75)". Measured current position: **U4 is still at
(149.38, 105.75)** — the exact position the punchlist flagged, unmoved. Center-to-center to U3
(157.6375, 103.95) is 8.45 mm; body-to-body is tighter. This is the one item that actually touches the
accuracy story (LDO self-heat coupling into the reference all six INA240 channels are ratioed against)
and it predates the fab snapshot — **it shipped on proto-v1 unresolved.** Recommend folding this into
the production-rev punch-list alongside (a)/(b); it's a placement nudge, not a redesign.

**Verdict — production-blocking vs. polish, for a first consumer run:**
- Blocking for "ship as a real consumer accuracy product": U4/U3 spacing (new finding above); (c)
  documentation sync (has zero engineering cost — just do it).
- Margin/production-hardening, not blocking a first run: (a) mirror lanes, (b) via upsizing — proto-v1's
  own case-cooled thermal number already passes (72.95 °C / ΔT 22.95 °C per CLAUDE.md); these lower risk
  under a *sustained single-pin-hog* fault, which is the harder-than-typical-use case the FEM was
  built to probe.
- Non-issues: (d) is a documented, deliberate consequence of the connector market (not a defect), (e) is
  cosmetic.

## 2. Space

Measured layout: the 6-lane shunt/sense corridor runs X 116.875–146.875 (30 mm, exactly 6 lanes at the
6 mm pitch the v3.4 fan-out chose) — RS1–RS6 at y=80.35, the matching INA240 row (U10–U15) directly
below at y=97.35, same X-span. The right-side core (ESP32-S3-MINI-1 at 160.875,88.35; RJ-45 at
159.65,130.28 rot90; USB-C at 168.425,72.35 rot90; CAN/LDO/REF cluster in between) occupies roughly
X 150–170 (20 mm). J3 (top, rot180) and J4 (bottom, rot0/pigtail) overhang the top/bottom board edges
by design so the connector body/mouth clears the board.

**Is there real shrink left, honestly?** The 30 mm corridor is close to a physical floor: it exists
*because* the v3.4 fan-out deliberately widened the connector's native 3 mm pin pitch to 6 mm so each
lane's INA240 (SOIC-8, ~5 mm body) plus its RC filter (RFH/RFL/CF) fits without fouling the neighboring
lane's Kelvin taps — narrowing it back toward 3 mm is the exact crowding v3.4 was created to avoid, and
isn't recommended. The genuine, low-risk reclaim is in the **control cluster between the INA row and
the ESP** (X≈149–158): U3/U4 currently sit 8.45 mm apart with slack around them (see §1) — tightening
that cluster properly (fixing the punchlist item) could pull a few mm back on the X axis without
touching the corridor. The Y axis (80 mm) is essentially connector-to-connector span (J3 mouth → shunt
row → INA row → control cluster → J4 pigtail) and is already dense; no obvious cut there without
losing the short-lane-length benefit that keeps Kelvin-loop and lane resistance low.

**Captive pigtail as an install factor — a real gap.** Nothing in the schematic, PCB, BOM, or README
specifies pigtail **length**, gauge, strain relief, or connector dress (which way it exits, how it's
routed to the GPU). This is a mechanical/assembly spec that doesn't exist yet in the repo. It matters
because of where this module physically sits: it is **not** small enough to hide inside a 12VHPWR cable
sleeve — it's a 58×80 mm PCB with an ESP32, RJ-45, and USB-C on it, needing its own mounting location
inline between the PSU cable and the GPU. That is a genuine tension with the target market: SFF and
dense-airflow builds — often exactly the segment with high-wattage GPUs and the most 12VHPWR melt
anxiety — are also the builds with the least spare volume behind/beside a GPU to park an inline sensing
board plus two right-angle 12V-2×6 headers. This isn't a board-layout fix; it's a product-fit question
(mounting bracket / cable routing guidance / a stated minimum GPU clearance) that has no owner yet.

## 3. Consumer fit — the melt-anxiety pitch

The telemetry model is well matched to the pitch as specified: per-pin current (6× INA240, imbalance is
the "leading indicator" per spec §6.1) plus **ΔT-above-ambient** (TH1 at the shunt/connector row, TH2
ambient reference — "rise, not absolute, is the alarm" per spec v3.7) is exactly the two-signal model
(imbalance leads, temperature confirms) real 12VHPWR failure reports describe. The sideband taps
(`CARD_CBL_PRES#`, `CARD_PWR_STABLE`) add a cheap, already-built "is this cable even fully seated"
signal — directly on-story for melt anxiety (partial mating is a well-known real-world cause) and
already wired to firmware-readable GPIOs (R10–R13), so this is a **software/UI** feature waiting to be
built, not a board gap.

One caveat worth stating plainly to sales: what reaches the Hub/host over Standard's CAN-only link is
firmware-derived (average current, imbalance %, ΔT), not the raw ~12 kSps/channel ADC waveform — RS-485
streaming (the high-bandwidth path) isn't populated on Standard by design. That's fine and consistent
(OQ-8: Standard is "a trend/imbalance tool, not a precision instrument"), but the pitch should say
"tracks and alarms on imbalance/heating trend" rather than imply oscilloscope-grade capture — the
Pro/Max tiers own that.

Declined items (TVS, status LED) stand — no new argument changes the physics (INA240's ±80 V
common-mode headroom, the short-fault-mode hazard of a TVS on a ~50 A rail; internal board with no
enclosure window for an LED) and I'm not relitigating them. The one genuinely open, spec-acknowledged
gap is the **GPU-plug NTC** (deferred, §6.1): today's TH1 reads the PSU-side (on-board) 12V-2×6 mated
pair, and J4's GPU-side mate is sensed only *indirectly* through conducted heat + current + voltage —
the spec says this outright ("off-board and sensed only indirectly"). Given the melt-anxiety pitch is
specifically about the connector plugged into the GPU, this is the single highest-leverage future add
(a 3rd NTC on/near the pigtail's GPU-side termination) — flagged as deferred, not as a new ask.

## 4. BOM cost-down at $49

The sourced BOM totals **~$21/board** in JLCPCB single-qty parts — real headroom against $49, but
**partially illusory** as currently scoped:
- **J3/J4 (Molex 219116, 2× per board) are consigned — $0 in the $21 figure**, but they're not free;
  Micro-Fit+/12V-2×6 headers are commodity-but-not-cheap connectors, and J4 additionally needs a
  **captive pigtail cable + GPU-side mating connector + hand-solder/assembly labor** (no length/gauge
  spec exists yet — §2). None of that is in the $21.
- Dominant BOM cost concentrates in 6× INA240A3DR ($1.87 ea = $11.24, >50% of the $21) and the ESP32
  ($4.59). INA240A3DR stock (~1.7k units, ~290 boards) is a real volume-scaling risk already flagged
  in the module's own BOM notes — worth a second-source or pre-buy check before ramping.
  Shunts (6× CSS2H-2512R-1L00F, $0.52 ea = $3.12) are now spec-locked (§1c), so no cost variance there.
- **At 100-qty pricing** (the BOM target basis) most Basic/Extended JLCPCB lines drop further, so the
  $21 single-qty figure is a conservative ceiling on parts, not a floor — genuine headroom exists on
  the sourced side. The trap is scoping "$49 target" against a partial BOM: add connector + pigtail +
  assembly + PCB fab (4-layer, 2 oz outer copper costs more than 1 oz) before treating $21 vs $49 as
  27 dollars of real margin.

## 5. Spec-vs-board drift, measured

- **RS1–6 schematic `Note` property** says shunt part "NOT locked" / OQ-11 candidate; spec v1.2.0
  (2026-07-02) locked it to the exact part already sourced. Stale text, zero engineering delta (§1c).
- **README/BOM notes** repeat "OQ-11 still OPEN" — same staleness, propagates from the schematic note.
- **U4/U3 placement** (§1, new finding) — the constraint-swarm punchlist's P1 recommendation was never
  applied; the board shipped to proto-v1 with the flagged spacing unchanged.
- Everything else checked against spec/CLAUDE.md matched the board exactly: DETECT R1 = 2.2 kΩ
  (CAN-only code, §2.3); INA240A3DR is the **D** (SOIC-8) part, not PW, per the locked decision; 6× 1 mΩ
  shunts Kelvin-sensed; REF3030 U4 = SOT-23, wired to ADC1 per the ratiometric scheme; TH1/TH2 =
  NCP15XH103F03RC into IO13/IO14; J1 = the shared FTP Kinghelm jack with SH1/SH2→GND; stackup 2/1/1/2 oz;
  no per-pin PoE clamp (consumer-ratified). No LOCKED decision is violated anywhere on this board.

## 6. Owner decision list

1. **Sync the OQ-11 "NOT locked" property on RS1–RS6 + README/BOM text** to match the 2026-07-02 spec
   lock. Zero-cost, should happen before any customer-facing "fully locked" claim. (§1c, §5)
2. **U4↔U3 spacing** — apply the constraint-swarm's own recommended reposition (unresolved since the
   2026-06-07 punchlist, still on proto-v1). Low-cost placement fix; touches the accuracy story directly.
   (§1, new finding)
3. **Decide whether (a) mirror-lane and (b) 0.9/0.5 mm via upsizing are production-rev requirements or
   accepted margin** given the case-cooled thermal PASS already on record — recommend requiring both
   before any "safe under sustained per-pin fault" marketing claim, optional for a first bench-only run.
   (§1a/b)
4. **Own the pigtail spec** (length, gauge, strain relief, dress direction) and the **module mounting /
   case-clearance guidance** for the target SFF/high-wattage segment — currently unspecified anywhere
   in the repo and is a real product-fit gap for exactly the customers this pitch targets. (§2)
5. **True landed cost check**: get J3/J4 + pigtail assembly + 4-layer/2oz PCB fab priced and re-run the
   $49 target against the *full* cost, not the $21 parts-only figure. (§4)
6. **INA240A3DR volume/second-source check** before scaling past ~290-board stock exposure. (§4)
7. **Deferred GPU-plug NTC** — no action needed now, but worth an explicit roadmap slot given it directly
   strengthens the melt-anxiety pitch's weakest link (GPU-side mate is sensed only indirectly today). (§3)
