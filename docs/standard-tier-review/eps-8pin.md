# EPS 8-pin module (Standard tier) — refinement review

Scope: `modules/eps-8pin/`. Read-only review against CLAUDE.md, spec §6.1/6.2/6.4/6.13,
and the checked-in `.kicad_sch`/`.kicad_pcb`/BOM as ground truth (measured with
`kicad-cli sch erc` / `pcb drc` / `sch export netlist`, KiCad 10.0.4). No files
under `modules/` were changed.

## 1. Fab-readiness

**Correction to the assumed gap:** the board is *not* pre-C6. Every footprint on the
PCB already matches the v3.10 schematic — `cec-RF_Module:ESP32-C6-MINI-1` (U1),
§6.13's INA181A2 (SOT-23-6, U20/U21) and TLV7011 (SOT-23-5, U30/U31), TS-1088 buttons,
`cec:RJ45_FTP_Shielded_Horizontal` (J1), PESD5V0S1**BA** (D1), and the pegless Molex
`87427-0802` connectors. All 45 schematic parts are placed (49 footprints incl. 3 M3
mounts + logo); "Update PCB from Schematic" is done. So the real remaining gap is
larger than a passive-pull: **the board carries 0 tracks, 0 vias, and 0 filled zones**
— it is a placed-only floorplan, not a routed board.

- ERC: 100 violations, all benign per the board's own notes (53 `pin_to_pin`
  Unspecified/easyeda noise, 45 `lib_symbol_mismatch`, 1 `pin_not_driven` on U2 TXD,
  1 `pin_not_connected` on U1's documented NC pad). No real ERC debt.
- DRC: 121 violations + 183 unconnected items. Breakdown: 54 `silk_overlap` + 50
  `silk_over_copper` + 11 `silk_edge_clearance` (all cosmetic silk-text, mostly the
  dense per-cable sense band — INA238/shunt/INA181/TLV7011 in a ~30 mm span), 4
  `hole_clearance` (J5 USB-C's own NPTH-vs-pad geometry — intrinsic to the vendored
  USB-C footprint, not a placement fault; worth checking against the same footprint
  on the other boards that use it), 2 `lib_footprint_mismatch` (benign generator
  artifact). **Zero copper-space violations** — the placement itself is DRC-clean.
  183 unconnected = pure ratsnest (every net, sampled), i.e. "nothing is routed yet,"
  not "something is broken."
- One `GND` zone exists (In1+In2, unfilled — correct, "Fill All Zones" is a GUI step).
  The 12V IN/OUT pours described in the README are **not yet zones** — they're
  non-copper guide graphics on `Dwgs.User`/`Cmts.User`/`Eco1.User`/`Eco2.User` (16+9+30+20
  graphic objects), i.e. a routing *plan*, not routed copper.
- **Real remaining work, honestly sized:** this is a full GUI routing pass — 2× 12V
  IN/OUT pours split at each shunt (mirrored F/B, via-stitched), GND fill, the
  four-wire Kelvin taps off each shunt's inner edge, the control→sense spine (I²C,
  THRESH, DETC×2), CAN, the USB diff pair, then re-fill/re-DRC. Comparable in scope to
  the EPS route-to-clean exercise already logged in CLAUDE.md's Done section (which
  used a *copy* of an earlier floorplan revision, not this committed one) — call it a
  half-day-to-day GUI/sub-agent-routing-pass task, not a five-minute pull.
- Board size measured at **96 × 37 mm**, not the 96 × 35 mm the README's placement
  section still describes. Git history shows the height was widened 35→37 in the
  later "loop iteration 2" placement revision (commit `14906cc`, to open a wider
  control→sense spine channel) — a real, committed change the README section never
  caught up to. Not a fab blocker, just a doc/board mismatch (see §5).

## 2. Space

**What bounds 96 × 37 today**, measured from placement coordinates:
- Two Molex 87427-0802 (pegless) cable columns, x∈[9,58], each ~23 mm wide: connector
  pad-rows (IN top/OUT bottom, bodies overhanging off-board), a ~6 mm-tall sense row
  (shunt + INA238 + INA181/TLV7011 side-by-side, not stacked), per cable.
- A ~38 mm-wide control core, x∈[58,96]: ESP32-C6, TJA1051T/3, LP5907, USB-C (top
  edge, rot180), two buttons, DETECT front-end, and the RJ-45 overhanging the right
  edge (rot90, mouth off-board).
- Height (37 mm) is set by the connector mouth overhang top+bottom plus the mid-height
  spine channel between IN and OUT — the last size increase was *for routability*, not
  parts.

**Realistic further shrink:** the README already notes ~90 × 33 is reachable by letting
the ESP32-C6 antenna-less end overhang an edge (courtyard is already trimmed for "no
keepout," but the body itself still sits fully on-board). That's the honest remaining
geometric headroom — maybe 10–15% more area, not a step change. There is no single
dominant oversized part to attack; the two 87427 connectors and the RJ-45/USB-C edge
are all near their overhang minimum already.

**Does mezzanine/stacked construction apply here?** No — and the framing in the task
brief conflates two different things. The "stacked" concept in this repo
(`docs/mezzanine-stack-design-2026-06-24.md`, OQ-77) is a **Hub-on-24-pin** board-to-
board stack that deletes the RJ-45 cable *between the Hub and the 24-pin module*, and
its own ratification brief (`docs/enterprise-requirements/ratification/briefs/
mezzanine-oq-77.md`) recommends adopting it for **ENT-AIR appliance packaging**, not
platform-wide and not Standard-tier consumer. EPS is architecturally a different shape
of object: a **cable-inline pass-through interposer** with a PSU-side plug and a
load-side (motherboard) plug, physically living *in the middle of a power cable run*,
not adjacent to the Hub. Stacking two PCBs doesn't shrink a cable-inline module's real
footprint driver, which is the two right-angle 8-pin headers themselves.

The consumer-relevant space question is a different one: **where does this board
physically sit in a case?** An EPS interposer must go inline in the CPU-power cable,
typically routed behind the motherboard tray through a grommet cutout, a channel that
is commonly 15–25 mm deep and already congested (24-pin, PCIe, fan/ARGB cabling). A 96
× 37 mm PCB with two right-angle connector mouths overhanging ~7 mm each adds real
depth and two 90°-bend cable exits to that channel — a materially different mechanical
object than "a rail in the harness." The board's 3× M3 mounting holes assume a chassis
mounting point, but consumer cases have no standard M3 boss in the CPU-power cable
channel, so in practice this module likely rides loose (zip-tied/veLcro'd) rather than
screwed down. **This physical-integration story is currently undesigned** — worth an
owner decision (does CEC ship a mounting bracket/standoff kit, or accept "dangles in
the channel"?) more than a further PCB-area cut.

## 3. Consumer fit

**§6.13 detection front-end at Standard.** The board carries it in full: 2× INA181A2 +
2× TLV7011 + the shared THRESH RC, per spec's own estimate ~$0.85/cable → EPS
$32→~$34 (spec §6.13, confirmed at spec.md:836). This is a locked v3.10 schematic
addition (not proposed here to change), and its purpose — "a transient happened" as a
binary FREEZE-trigger event, not shape/magnitude — matches the sales thesis ("knowing
what the PC is doing") reasonably well for troubleshooting an unstable/crashing build:
it gives a consumer-facing tool something concrete to say ("cable 2 saw an OCP-class
event at 14:32") without needing a scope. The counter-argument: it is pure BOM cost
with zero consumer-visible feature *unless* firmware/app work lands on the other side
(OQ-57's bench-validated threshold + latch logic, and the app UI to surface it) — right
now it's silicon with no user-facing payoff yet. Framing, not resolving, per OQ-57/58/59:
OQ-57 (this board's own threshold/hysteresis/latch bench validation) is the one that
actually gates whether Standard's detection front-end does anything real at ship; 58/59
are the Pro/Max SKUs and don't block Standard.

**2-cable population vs. real usage.** Spec §6.2 explicitly scopes EPS as "one monitor
per cable... two on EPS" and §6.1 as "one per cable (1 to 2)" — i.e. a 1-cable EPS SKU
is spec-legal today, not a locked-decision violation. Most consumer boards (mainstream
ATX, one CPU 8-pin or a 4+4 used as one) only populate a single EPS cable; dual-8-pin
CPU power is a high-end/workstation board trait. Shipping only a 2-cable SKU means every
mainstream consumer buyer pays for a second cable's INA238 + shunt + INA181/TLV7011 +
connector pair they'll never plug in. A 1-cable "EPS-1" variant is a real, spec-legal,
generator-level trivial change (`scripts/gen-modules.py`'s `CABLES` list is
literally `[("C1","0m5"), ("C2","0m5")]`) — flagged as an owner SKU decision, not
executed here.

**USB-C flash/debug port.** Native USB-Serial-JTAG (D+/D− on the C6) plus BOOT/RESET
buttons is the right call for field firmware updates and matches every other module —
keep it populated. It's a small, cheap (~$0.30 receptacle + 2 buttons + ORing diode),
genuinely useful serviceability feature (re-flash without opening the case if the
port is accessible), not a candidate for cost-down.

## 4. BOM cost-down at the $32 target

The committed BOM (`modules/eps-8pin/bom/eps8pin-module-BOM-jlcpcb.csv`) sources 24 of
30 distinct lines; unsourced: the 4 Mini-Fit Jr THT connectors (expected — hand-solder/
consign, no LCSC line) and RS1/RS2 (see §5 — the shunt part is now actually locked,
just not yet written into this file). No priced `bom.csv` is committed for this board
(only the JLC-format CSV, which carries no cost column), so there is no source-of-truth
total to audit against $32/$34 in-repo; the spec's own §9 figure (~$34 with §6.13) is
the only anchor. Cost-down levers, ranked by leverage:

1. **1-cable SKU (§3 above)** is the single largest lever available without touching
   any locked decision — it removes a full duplicate high-current sense chain
   (INA238 + shunt + INA181/TLV7011 + connector pair) for the mainstream single-EPS-
   cable customer.
2. **THT Mini-Fit Jr connectors** are the other big line item (4 per board, hand-
   soldered/consigned — SMT assembly can't place them). This is fixed by the ATX/EPS12V
   standard and isn't optional, but it's worth the owner knowing it's a meaningfully
   higher per-unit assembly cost than the SMT-only modules (24-pin has the same
   trait).
3. Passive count is already lean (100 nF/1 µF/10 µF families reused from the Hub's
   sourced LCSC lines) — little further to squeeze there.
4. The §6.13 front-end (~$1.75/board for 2 cables) is a real, locked cost add; not a
   candidate for removal at Standard (it's the spec's OQ-9 resolution), but its ROI is
   currently unrealized pending OQ-57 firmware/bench work (§3).

## 5. Spec-vs-board drift (measured)

- **Board dimension:** README documents 96 × 35 mm; the committed `.kicad_pcb` measures
  **96 × 37 mm** (Edge.Cuts, verified). Real, git-traceable (commit `14906cc` widened it
  for spine routing), but the README section was never updated after that commit.
- **RJ-45 jack:** already the platform FTP part (`cec:RJ45_FTP_Shielded_Horizontal`,
  Kinghelm KH-RJ45-58-8P8C, C2683360), SH1/SH2 verified on the GND net via the exported
  netlist. **No drift here** — contrary to the general "24-pin/PCIe still unshielded"
  caveat in CLAUDE.md, EPS is current.
- **D1 PESD part:** BOM/schematic both read `PESD5V0S1BA` (C5261083) — the UL→BA fix is
  applied. **No drift.**
- **RS1/RS2 shunt (OQ-11):** CLAUDE.md's top-of-file summary says OQ-11 is "FULLY
  RESOLVED... incl. EPS/PCIe 0.5 mΩ CSS2H-2512R-L500F." True at the *spec* level
  (`docs/enterprise-requirements/ratification/oq-11-shunt-selection-2026-07-02.md`
  gives the exact MPN, verifies real stock: DigiKey standard reel 5,894 pcs @ $0.82/100;
  the JLCPCB mini-reel mirror C1848841 read 0 stock at that sheet's fetch). **Not yet
  true on this board** — `RS1`/`RS2` in the schematic carry no Manufacturer/MPN/LCSC
  property at all (verified in the raw `.kicad_sch`), and the BOM CSV still lists a bare
  `0.5mΩ / R_2512_6332Metric` placeholder. This is a known, tracked gap (the
  ratification sheet's own checklist explicitly defers "writing the MPN into
  `modules/eps-8pin/bom/*.csv`" as a separate follow-up pass), not a fresh problem — but
  it means "shunt part locked" cannot yet be read as "shunt part sourced on this board."
- **BOM CSV connector footprint is stale.** `bom/eps8pin-module-BOM-jlcpcb.csv` lists
  J_IN1/J_IN2/J_OUT1/J_OUT2 as `Molex_Mini-Fit_Jr_5569-08A2_2x04_P4.20mm_Horizontal`
  (the old *pegged* footprint). Both the schematic and the PCB have carried the pegless
  `87427-0802` since the 2026-06-06 pinout-fix pass; the BOM export was never
  regenerated after that change. Cosmetic for a THT/consigned line (no LCSC either way),
  but worth fixing before this CSV is handed to an assembler.
- **BOM target text:** README states "$32 (100-qty)" as the headline; the spec's own
  §9 BOM table already quotes "$32 (about $34 with the v3.8 detection front-end)" for
  this exact board. The README hasn't absorbed the $34-inclusive figure.

## 6. Owner decision list

1. **1-cable "EPS-1" SKU?** Spec-legal (§6.2/§6.1 already say "1 to 2" cables per
   module). Real BOM savings for the mainstream single-EPS-cable customer; adds a SKU
   to manage. *Decision needed: add the variant, or keep 2-cable-only Standard.*
2. **Physical mounting/consumer-install story.** No bracket/standoff/routing guidance
   exists for where this board lives behind a motherboard tray or in the PSU-cable
   channel; the 3× M3 holes imply chassis mounting a typical consumer case can't
   provide in that location. *Decision needed: design a mount/zip-tie kit, or document
   "floats in the harness" as the accepted install mode.*
3. **§6.13 payoff timing.** The detection front-end is board-committed cost with no
   consumer-visible feature until OQ-57's threshold/latch bench validation and the
   corresponding firmware/app surface land. *Decision needed: prioritize OQ-57 to
   realize the feature before/at the same time as EPS ships, or accept shipping the
   silicon ahead of the feature.*
4. **BOM/README refresh pass.** Three small, low-risk fixes bundled: (a) write
   CSS2H-2512R-L500F + a DigiKey line (JLCPCB mini-reel stock is thin) onto RS1/RS2 in
   the schematic and regenerate the BOM CSVs; (b) fix the stale 5569-08A2 connector
   footprint text in the BOM CSV to 87427-0802; (c) update the README's board-size
   (96×37) and BOM-target ($34-inclusive) text to match the committed files.
5. **Route the board.** This is the real fab-readiness item: a GUI/sub-agent routing
   pass (12V pours, GND fill, Kelvin taps, spine, CAN, USB diff pair) plus a silk-
   cleanup pass on the dense per-cable sense band (115 cosmetic DRC hits today, driven
   by 6 tightly-packed parts × 2 cables). *No decision needed, just scheduling.*
