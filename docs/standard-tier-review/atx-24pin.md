# 24-pin ATX module — Standard-tier consumer refinement review

Read-only review. Ground truth pulled from `modules/atx-24pin/` (the ordered/frozen
board), `modules/atx-24pin-rev2/` and `modules/atx-24pin-rev3/` (post-order
exploratory dirs — naming is confusing, see §5), `docs/24pin-rev3-respin-2026-06-24.md`,
`docs/24pin-shrink-2026-06-24.md`, `docs/mezzanine-stack-design-2026-06-24.md`,
`CEC-Platform-Ground-Truth-Spec.md` §2.7/§2.8/§6, and live `kicad-cli` ERC/DRC/netlist
runs (KiCad 10.0.4) against the actual files, not just the docs' claims about them.

**Directory-naming trap, read this first:** `modules/atx-24pin/` (no suffix) is the
**straight-through, ordered** board — 110 × 75.5 mm, 8342 mm², J3/J4 both vertical.
`modules/atx-24pin-rev2/` is *not* a copy of the ordered board — it's the shrink
study's 90°-rotated ("L") variant, 82.9 × 79.0 mm, 6576 mm². `modules/atx-24pin-rev3/`
is the respin scaffold, and its `.kicad_pcb` is byte-identical to `atx-24pin-rev2/`'s
(confirmed via checksum) — i.e. rev3's PCB baseline is the 90° L-shape, not the
shipped board. The rev3 **schematic** is a fresh, verified rebuild (confirmed below);
the rev3 **PCB** has not been touched — it still carries the old ESP32-S3 footprint,
no mux, no mezzanine header, no C6. Treat "rev3" as schematic-complete /
layout-not-started.

## 1. Fab-readiness

**Ordered board (`modules/atx-24pin/`) as-built defects, verified against the live
schematic/netlist (not just doc claims):**
- **R1 (DETECT code resistor) carries a literal placeholder value in the
  source-of-truth file today**: netlist value is the string `"R_ID (OQ-6)"`, not a
  resistance — confirmed in both `24pin-module.kicad_sch` and `bom/bom.csv` (no
  Ohm value, no MPN, no LCSC). OQ-6 was locked in spec v1.7 (CAN-only = 2.2 kΩ)
  *after* this schematic's R1 was drawn, and the fix was **never backported into
  this file** — rev3 has the correct 2.2 kΩ, but the "ordered rev2, frozen"
  reference copy still does not, even as documentation. Recommend backfilling
  2.2 kΩ into this file for the record, and separately confirming what value (if
  any) was actually stuffed on the physical assembled units — if it was DNP'd or
  populated arbitrarily, those units' DETECT/module-ID sensing may not read the
  intended code at the Hub.
- **D3 (DETECT ESD diode, PESD5V0S1UL/SOD-323)** *is* present and correctly wired
  to `/DETECT`→GND in the current schematic/netlist — this is a case where the
  repo file was fixed post-order; per the module README the **physically
  assembled rev2 units shipped without it**. Not a live repo defect, just don't
  confuse "the file has it" with "the boards have it."
- **RJ-45 VCC parallel-feed erratum confirmed live**: J1 pin 1 is on the `+5VSB`
  net (should be no-connect per spec §2.7 v3.3). Rev3 netlist confirms this is
  fixed there (J1 pad 1 → `unconnected-(J1-VCC-Pad1)`).
- **CAN net names drift confirmed live**: ordered board carries `/CAN1_P`,
  `/CAN1_N`; rev3 correctly renames to `/CAN_H`/`/CAN_L`.
- **RJ-45 is the unshielded Amphenol 54602** (`cec-Connector_RJ:RJ45_Amphenol_
  54602-x08_Horizontal`) on the ordered board, confirmed live; rev3 correctly
  moves to the platform FTP jack (`cec:RJ45_FTP_Shielded_Horizontal`).
- **DRAFT marker still present** in both `atx-24pin/` and `atx-24pin-rev3/`, which
  means CI/`check-all.sh` currently skips ERC/DRC on the "ordered, frozen" board.
  A quick independent `kicad-cli` pass here found **0 ERC errors** (39 warnings,
  all benign lib-symbol-mismatch/unconnected-wire noise) and **21 DRC hits, 0 of
  them structural** on the ordered board — mostly silk-edge-clearance plus 4
  `hole_clearance` errors that are internal to the J5 USB-C footprint's own pad-
  vs-NPTH spacing (library geometry, not a routing mistake, but worth a glance
  against the vendored XKB footprint before another fab run).

**Is the rev3 respin list right-sized for a Standard/consumer push?** Mixed.
Items 1–5 in the respin doc's change list (DETECT poke-ack tap, ESD diode, FTP
jack, CAN rename, J1.1 no-connect) are exactly the right scope — small, bring
this board to platform parity, no design judgment needed. **Verified live in the
rev3 schematic: all five are actually implemented** (R7 100 kΩ tap → `/DETECT_
SENSE` → U1 IO10-equivalent pad 12; D1 = PESD5V0S1BA; J1 = FTP footprint; CAN_H/
CAN_L; J1 pin 1 open). Good — the respin doc's "BUILT" claim holds up against the
actual netlist.

Items 6 (C6 MCU + §6.13) and the mezzanine + power-mux work are a different
animal: they're real feature adds, not fab-parity fixes, and they arrived in the
**same respin** as the parity items. For a Standard-tier consumer push that wants
schedule, **6 and the mezzanine/mux are gold-plating relative to "ship a
corrected, fab-ready 24-pin"** — they're good ideas (see §2/§3) but they add BOM
cost (§4), a new connector family, and mechanical coordination with a Hub rev that
doesn't exist yet. A minimal-risk path is a "rev3a" that ships items 1–5 + the
locked §6.4 shunt parts only, with C6/§6.13/mezzanine held for a "rev3b"/"rev4"
once the Hub-side mezzanine socket and the BOM number are actually worked out.

**Other things found, not yet in any tracked list:**
- Rev3's `board-manifest.json` is a **byte-identical copy** of rev2's — it still
  lists all three items in `errata_rev3` (CAN rename, R1 migration, ESD diode) as
  outstanding, and its `net_aliases` block still maps `CAN1_H/L → /CAN1_P//CAN1_N`
  even though the rev3 schematic no longer has those net names at all. This file
  will feed corpus/vendor-BOM tooling with stale facts about rev3 until updated.
- `kicad-cli sch export netlist` on rev3 prints "schematic has annotation errors"
  and rev3 ERC shows 101 violations (0 errors, but 53 `pin_to_pin` + 43
  `lib_symbol_mismatch` — both far higher counts than the ordered board's 39).
  Worth a manual look before layout starts; likely benign (multi-driver power
  nets across the new mux/mezzanine sections) but unverified here.
- The rev3 **mezzanine header (J6) pin map does not match the published pinout
  table** in `docs/mezzanine-stack-design-2026-06-24.md`. Doc table: DETECT=pin13,
  +5VSB=1/2/15, STREAM_P/N=9/10. Actual rev3 netlist: DETECT=pin 11, +5V_SYS=
  1/2/3, STREAM_P/N=8/9, pin 13 unconnected (RSVD). Same signal set, different
  pin assignment. **This matters because the Hub-side socket hasn't been
  designed yet** — whoever builds it must pull the pin map from the rev3 J6
  netlist, not the design doc table, or the mated connector pair will be wired
  wrong (the doc's own "MIRROR GOTCHA" warning applies doubly here).

## 2. Space

The two Molex Mini-Fit Jr 5569 24-circuit headers (J3 in, J4 out, ~62.6 mm
long including shroud/stabilizers) are what actually bounds the outline — the
shrink study found **both the straight and 90° layouts hit their rigid-shrink
floor at 0%** because the board is connector-perimeter-bound (straight) or
part-courtyard-bound (90°, where ESP+J3+J4 are 75% of the area). Quantified
ladder, all independently re-derivable from the docs (not yet all committed to a
board file):

| Variant | Size | Area | Status |
|---|---|---|---|
| straight-through (**shipped**, `atx-24pin/`) | 110.2×75.7 | 8342 mm² | ordered |
| 90° "L" (`atx-24pin-rev2/`, rev3's PCB baseline) | 83.1×79.2 | 6576 mm² (−21%) | DRC 0 structural, committed |
| 90° + header overhang (asymmetric, 5VSB-safe) | 79.1×73.2 | 5794 mm² (−30.5%) | **connectivity-preserving only** — DRC 31 (edge clearance/courtyard), needs a real re-route pass; lives only in `build/` (uncommitted) |
| from-scratch re-place attempt | — | — | **failed 5×** — breaks Kelvin/unconnected every time; rail core needs hand placement |

So the realistic, honest number for a rev3 layout pass is **−21% vs. shipped, DRC-
clean, already the rev3 PCB starting point** — the further −30% is real but not
yet fab-clean; budget a routing pass to close the 31 hits (mostly pulling the
5VSB/power copper in ~0.3 mm from the tightened edge) before counting on it.

**Mezzanine/stacked form — what it actually buys.** It does **not** shrink the
24-pin board's XY footprint; if anything it adds to it (TPS2121 mux + passives, a
2×8 2.00mm header, 4× M3 GND-bonded mounts vs. rev2's zero mounts). What it buys
is **Z-axis integration**: it deletes the RJ-45 patch cable and the 2-pin 5VSB
JST cable between the 24-pin module and the Hub, replacing both with an 8 mm
board-to-board stack (connector carries signals only; the 4× M3 standoffs carry
the mechanical load and the GND bond). For "space," that's a case-interior-volume
and cable-clutter win, not a board-area win — worth being precise about which
kind of "space" the sales thesis means. The $35 target absorbs this only if the
mux + connector + hardware (§4) don't push the board past the BOM ceiling — see §4.

## 3. Consumer fit

**4× INA228 vs. the sales thesis.** This is a good match, not just tolerable
cost: the INA228's per-rail hardware energy/charge accumulator is literally "what
is the PC doing" made concrete — per-rail Wh, including 3.3V/5VSB standby, is a
consumer-legible number (vampire-draw dollars, "what does idle cost me") that the
cheaper INA238 doesn't provide at all. The spec's own footnote already flags the
cost bump (§4) — that's the honest trade: INA228 buys the differentiator the
sales thesis is selling, INA238 doesn't. **This is an owner call, not a resolved
one** (see §6) — the honest middle ground worth naming is keeping INA228 only on
12V/5V (where the spec's own droop-resolution rationale actually applies) and
dropping 3.3V/5VSB to INA238, trading some of the "vampire-load" marketing story
for BOM headroom. Note OQ-13 (energy scope) is *adjacent, not resolved by this*:
whatever chip is used, the 24-pin's energy figure is this-module's-rails only,
not whole-system, and marketing copy needs to say so.

**Female-female bridging cable SKU — real consumer friction.** The module's two
Mini-Fit Jr headers are both male (§2.8, locked), so the run from J4 (module
output) to the motherboard's own male header needs a **female-female 24-pin
cable that doesn't exist as an off-the-shelf PC part** — CEC has to supply it.
For a consumer installer this is: one more box-content item that can be lost or
substituted with a wrong (standard PSU) cable, one more mated-contact pair in the
24V/high-current path, and no retail replacement path if damaged — unlike every
other cable in a PC build. It's also **not obviously priced into the $35 module
target** (a harness is a separate line/SKU) — worth confirming whether $35 is
module-only or is meant to include this cable.

**5VSB bulk-feed + MAIN_5V tap setup complexity.** In the cabled (non-mezzanine)
configuration a consumer installer runs **two separate cables** from the 24-pin
module to the Hub: the RJ-45 telemetry link and a 2-pin JST-XH 5VSB power feed —
neither is a "PC part" a builder already owns, both need case routing. The
MAIN_5V tap (action item 0b in CLAUDE.md) and its eventual consolidation with the
5VSB JST into "one 3-pin feed" is explicitly still open ("kept separate now...
fix later" — CLAUDE.md item 0c) — i.e. the team has already flagged this exact
consumer pain and deferred the fix. The mezzanine header is the real answer to
this friction (one connector, no cables) — which makes §5/§6's finding that the
**stacked-product SKU is currently scoped ENT-AIR-only, with Standard-tier
extension "flagged for review,"** the load-bearing owner question for the
consumer thesis, not an engineering one.

## 4. BOM cost-down at the $35 target

Rough, todays-typical-distributor-tier estimates at ~100 qty; every line flagged
`[quote]` needs a real jlcsearch/distributor pull before it's used to gate a
decision — this section is directional, not a BOM.

| Item | Rough delta vs. $35 baseline | Confidence |
|---|---|---|
| INA238→INA228 ×4 (already locked in) | **+$4 to +$5** (≈+$1–1.3/part) | matches the spec §9 footnote's "modest increase"; cross-checked against the ENT product-matrix figure (~$40–42 incl. a separate $5–7 T1 premium, implying a non-T1 4×INA228+§6.13 base near $33–37) — same ballpark | `[quote]` exact parts |
| §6.13 front-end, 2 rails only (INA181A2 + TLV7011 + passives ×2) | **+$1.0 to +$1.5** | rev3 populated 12V+5V only, not all 4 — the GPIO-budget note in the respin doc is why | `[quote]` |
| ESP32-S3-MINI-1 → C6-MINI-1 | **−$0.9** (per spec §"Standard-module MCU selection") | spec-stated, not independently re-quoted here | `[quote]` |
| TPS2121 power mux + passives (mezzanine/consolidation feature) | **+$0.6 to +$1.0** | rough, TI PowerPath-class part | `[quote]` |
| 2×8 2.00mm header (mezzanine, module side only) | **+$0.3 to +$0.6** | generic 2mm dual-row, unsourced MPN per the respin doc | `[quote]`, MPN TBD |
| 4× M3 metal standoffs + screws (mezzanine hardware) | **+$0.5 to +$1.2** | hardware, not silicon — may or may not count against a PCBA-only $35 | scope question |
| FTP shielded RJ-45 (Kinghelm KH-RJ45-58-8P8C) vs. unshielded 54602 | **+$0.1 to +$0.3** | small, already platform-standard elsewhere | `[quote]` |
| DETECT ESD diode (D1, PESD5V0S1BA) + poke-ack R7 | **~+$0.05** | trivial | fine |

**Net read:** a rev3 that folds in *everything* in the respin doc (parity fixes +
C6 + §6.13(2 rails) + mux + mezzanine header, excluding the standoff hardware)
lands roughly **$40–44**, i.e. **15–25% over the $35 target**, mostly driven by
the INA228 move (already locked, not new) plus the mux/mezzanine feature stack
(new, and the one part of this scope that's discretionary for Standard). A
cabled-only rev3a (parity fixes + shunts, DNP the mux/mezzanine/§6.13) is much
closer to target, roughly **$39–41** driven almost entirely by the INA228 move.
Dropping §6.13 to zero rails for Standard (reserve it for Pro/ENT, where the
spec's own "detection→characterization→spectral" ladder already lives) removes
another ~$1–1.5. These are framed choices for §6, not resolved here.

## 5. Spec-vs-board drift

- **C6-MINI + §6.13 status on this board**: still **ESP32-S3-MINI-1** and no
  §6.13 front-end on the shipped/ordered board and on the bare `atx-24pin/`
  schematic (matches CLAUDE.md action item -1's framing). **The rev3 *schematic*
  has already made this jump** — confirmed live: `U1` = ESP32-C6-MINI-1-N4,
  §6.13 populated on the 12V and 5V rails only (`U612V`/`U65V` INA181A2,
  `U712V`/`U75V` TLV7011, matching the "GPIO-budget check… bounds how many rails
  get the fast front-end" note in the respin doc — 9 of U1's GPIOs remain
  unconnected after this allocation, so there is headroom to add more rails or
  more housekeeping later without another MCU change).
- **`/CAN1_P`/`/CAN1_N` net-name drift**: confirmed live on the ordered board
  (standing compile warning, as flagged in CLAUDE.md); confirmed fixed to
  `/CAN_H`/`/CAN_L` in rev3.
- **`board-manifest.json` (rev3) is stale** — see §1, it still describes rev2's
  unfixed state after the schematic fixed it.
- **Mezzanine J6 pin map vs. design-doc pinout table mismatch** — see §1, a
  concrete, checkable discrepancy that will bite when the Hub-side socket gets
  designed if someone works from the doc instead of the netlist.
- **Shunt parts**: OQ-11 is now LOCKED (spec §6.4, 2026-07-02) — 24-pin uses
  Bourns CSS2H-2512K-2L00F (2 mΩ, ±75 ppm/°C) on 12V/5V/3.3V and Vishay WSK2512
  R025 (25 mΩ) on 5VSB. Confirmed live in rev3's BOM/netlist (RS1-3 = 2mΩ, RS4 =
  25mΩ, `R_2512_6332Metric` footprint) — this part of the design is current and
  matches spec. The ordered board's BOM (`bom.csv`) already names the correct
  Bourns/Vishay MPNs for its shunts too (RS1/RS2/RS5 = CSS2H-2512K-2L00F w/ LCSC
  C1729157; RS6 = WSK2512, no LCSC yet) — this one is in good shape.
- **Mezzanine/stacked-form scope, per the enterprise-requirements ratification
  record** (`docs/enterprise-requirements/ratification/ratification-brief-
  2026-07-02.md`, R5): the mezzanine *architecture* is adopted, explicitly
  "also being adopted consumer-side," **but the orderable stacked-product SKU is
  scoped ENT-AIR-only for now, with broader (i.e. Standard) scope "flagged for
  review."** This softens the review prompt's framing of the mezzanine as
  already "owner-adopted for consumer tier" — the architecture is shared/adopted,
  the sellable consumer SKU is not yet greenlit. Flagged as an owner item in §6,
  not resolved here.

## 6. Owner decision list (framed, not resolved)

1. **Rev3 scope split.** Ship a narrow "rev3a" (parity items 1–5 + locked
   shunts only, ~$39–41) now for the Standard/consumer push, and hold C6+§6.13+
   mux+mezzanine for a later rev once the Hub-side mezzanine socket and a real
   BOM quote exist? Or take the full respin as one board and accept the schedule
   + ~$40–44 BOM?
2. **INA228 vs INA238 split.** Keep 4×INA228 (full "know what it's doing"
   energy story, ~$35+$4–5) vs. INA228 on 12V/5V only + INA238 on 3.3V/5VSB
   (~$35+$2–2.5, loses standby-Wh precision on the two lower-current rails)?
3. **§6.13 rail count for Standard.** Populate 12V+5V (current rev3 choice,
   ~+$1–1.5) vs. zero rails on Standard and reserve the fast-transient front-end
   for Pro/ENT per the spec's own detection→characterization→spectral ladder
   (saves the cost, drops a Standard-tier "instant spike" feature)?
4. **Mezzanine as a Standard SKU, now.** The architecture is adopted and
   "also being adopted consumer-side" per the 2026-07-02 ratification record, but
   the *sellable stacked unit* is currently ENT-AIR-only with Standard extension
   flagged for review. Given it's the actual fix for the two-cable consumer
   setup friction (§3), does Standard get its own mezzanine SKU decision now, or
   does it wait behind the ENT-AIR productization?
5. **F-F bridging cable — bundle or accessory?** Include it in the $35 module
   target (module effectively can't be installed without it) or price/sell it as
   a separate accessory SKU? Affects whether "$35" is an honest install cost.
6. **BOM target itself.** If the owner wants the full respin feature set, is
   $35 still the number, or does the Standard-tier target move (the boards-table
   footnote already concedes the INA228 move alone raises it)?
7. **(Spec-revision proposal, not a board decision)** Formalize OQ-77 (mezzanine
   integrated-stack option) status for Standard specifically in a spec edit,
   since the current spec text (§2.8) still describes only the cabled RJ-45/JST
   interface for this module — the mezzanine is presently a proposal/ratification-
   record artifact, not yet spec text.
