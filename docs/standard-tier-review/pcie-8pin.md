# PCIe 8-pin Standard-tier review — 2-port & 3-port SKUs

Reviewed 2026-07-03 against kicad-cli 10.0.4 ground truth (schematic + PCB), `scripts/gen-pcie-condensed.py`,
CLAUDE.md, and `CEC-Platform-Ground-Truth-Spec.md` §6.1/§6.4/§6.13. Read-only pass; no repo files touched
besides this report. Both boards carry a `DRAFT` marker (CI skips ERC/DRC).

## 1. Fab-readiness

**Both boards are placement-complete, ZERO copper.** `grep -c '(segment\|(via'` = 0/0 on both
`.kicad_pcb` files; the 28 `(zone ...)` blocks per board are unfilled pour/guide outlines, not routed
copper. This is consistent with the README's own "Next in GUI: Fill All Zones, route, re-DRC" — but it
means **neither board is fab-ready today**, only floorplan-ready. Anyone reading only the top-line
"DRC 0 structural" claim in CLAUDE.md/README should not infer routed.

Measured DRC (structural, i.e. excluding the routing step that hasn't happened):

| | 2-port | 3-port |
|---|---|---|
| silk_overlap / silk_over_copper / silk_edge_clearance | 110 / 69 / 15 | 140 / 79 / 19 |
| hole_clearance | 4 | 4 |
| solder_mask_bridge + shorting_items (SW2 BOOT/RESET pads) | 1 + 1 | 1 + 1 |
| lib_footprint_mismatch | 2 | 2 |
| unconnected items | 183 | 224 |

The SW2 mask-bridge/shorting pair is the documented-benign headless artifact (identical geometry to
the EPS board's known false positive; absent in the GUI). The 194/238 silk hits are real but purely
cosmetic pre-fab cleanup (dense condensed layout, expected before a silk pass) — not a blocker, but
non-trivial: 3-4x the silk-violation count of the EPS board at a similar footprint density, worth a
dedicated silk pass before tape-out, not just "glance at a render."

**New, previously undocumented finding:** 4x `hole_clearance` on J5 (USB-C receptacle, XKB
U262-16XN-4BVC11) on *both* boards — an NPTH-to-pad spacing of 0.165-0.20 mm against a 0.25 mm board
rule, inside the connector's own footprint. This is not in the "documented-benign" list anywhere in
CLAUDE.md. It is inherent to the shared USB-C footprint (same land is used on EPS/24-pin/12VHPWR), so
it is a repo-wide footprint-vs-DRU mismatch, not a PCIe-specific defect — but nobody has flagged it before
this pass. Recommend either tightening the footprint's NPTH keepout or loosening the hole-clearance rule
for this one footprint (with a documented exception), and doing it once in `lib/` rather than per board.

**Confirmed correct (no action needed):** ESP32-C6-MINI-1 + §6.13 front-end (INA181A2/TLV7011) ARE on
both PCBs, not just the schematics — the CLAUDE.md action-item -1 wording ("PCBs need Update-PCB-from-
Schematic to pull the C6 land") is stale; `gen-pcie-condensed.py`'s regen already did this. J1 is
already `cec:RJ45_FTP_Shielded_Horizontal` (Kinghelm C2683360) on both boards, schematic and PCB — the
CLAUDE.md checklist line "24-pin + the two PCIe SKUs still carry the unshielded 54602" is **also stale**
for these two boards (true for 24-pin, not for PCIe since the condensed regen). Pin allocation
(netlist-verified): pin 7 unconnected/reserved, pins 4/5 unconnected (Standard, RS-485 dark), pin 8 →
`/DETECT`, pins 3/6 → CAN — matches the locked table exactly on both SKUs.

## 2. Space

**What bounds the outline:** height (44 mm) is set entirely by the Molex 45586's two 3.0 mm snap-pegs
(pegged Mini-Fit Jr THT retention) — same mechanism the EPS board escaped by moving to the pegless
87427-0802 (96×**35** mm, a 20% height cut). Width is cable-pitch × N (23 mm/cable 2-port, 20 mm/cable
3-port) plus a fixed ~34 mm electronics core (ESP32-C6 + CAN + LDO + flash front end + RJ-45), so the
per-cable marginal width is already tight and the core is the non-shrinkable floor.

**Pegless-connector lever (open, not yet explored for PCIe):** whether a pegless 45586-family sibling
exists that preserves the PCIe-specific 3rd-gen keying is unconfirmed in this repo — the vendored
description only documents 455860005/455860105 (both pegged). Unlike EPS/12V (generic Mini-Fit Jr,
free to swap families), the PCIe connector's *keying* is load-bearing (it is what stops a user plugging
an EPS cable into a GPU rail), so this is a part-search question for the owner, not a drop-in — if a
pegless PCIe-keyed part exists, both SKUs get the same ~20% height win EPS already banked.

**2-port vs 3-port as a product question:** the marginal BOM for the 3rd cable is ~$5.5 (INA238 +
INA181A2 + TLV7011 + 0.5 mΩ shunt + 2× Mini-Fit Jr headers + bypass), the PCB-area cost of accommodating
it is `README` claims. Two SKUs mean two boards to fab-qualify, stock, and support in the sales catalog
for a feature (a 3rd sensed cable) that a large fraction of consumer builds don't need. **Owner framing:**
does the catalog need both, or should Standard ship as one 3-port-capable board (BOM cost absorbed,
$42 flat) with the option to leave the 3rd cable unpopulated/unstuffed at $38, rather than maintaining
two board files, two fab runs, two DRC/silk passes? The unstuff-option collapses this section's whole
fab-readiness burden into one board.

**Mezzanine/stacking:** not applicable to this module class. It is a cable pass-through interposer with
bulky THT power connectors on two *opposite* edges (PSU-side in, GPU-side out) — a mezzanine/daughtercard
stack only saves area for a board whose I/O is edge-launched on one side or board-to-board; here the
board's entire footprint *is* the two connector rows plus the sensing band between them, so there is no
"host board" to stack onto. The real space lever is the pegless-connector question above, not a 3D
stacking scheme.

**Where it lives in a case:** this is a cable-dressing component, not a slot card — it sits inline on the
PCIe/GPU power cable between PSU and GPU, typically routed behind the motherboard tray or through a
cutout, same real estate as a cable stiffener/comb. 44 mm height + inline pass-through connectors is
already compatible with that use; a further height cut mostly helps clearance in tight ITX/SFF builds
where cable routing space is scarcest and where PCIe 8-pin cards (lower-wattage) are most common —
i.e. the size-sensitive segment and the market segment likely to still be on 8-pin power overlap.

## 3. Consumer fit

**12VHPWR-era reality check (reasoning, not a sourced market figure — flag for owner verification with
real 2026 sell-through data):** 12VHPWR/12V-2x6 has been mandatory on essentially the entire enthusiast
tier (roughly RTX 4070-class and up) since 2022-23, and by 2026 that adoption line has likely pushed
further down-stack. PCIe 8-pin remains the connector for the volume/budget segment (sub-$400 cards) and
for the large installed base of older GPUs still in service — i.e., PCIe 8-pin telemetry is a
volume/budget-segment and installed-base product, not an enthusiast one. That is a reasonable fit for a
**Standard**-tier (not Pro/Enterprise) SKU, but it argues for keeping this module as cheap and simple as
possible rather than growing it — the buyer profile is less likely to pay for a 3rd port or Pro-tier
transient characterization.

**§6.13 front-end at Standard:** appropriate for the segment — it's a $0.85/cable binary
event-detection add matching the spec's own framing (OQ-57..59 gate only the *characterization* Pro/Max
SKUs, not this binary-event front-end, which is already implemented and spec-resolved for OQ-9). No
gate blocks shipping the Standard board as designed on this axis; OQ-57's remaining bench-validation
(threshold/hysteresis tuning against real transients) is a firmware/bench item, not a board respin.

**USB-C debug population:** populated on both SKUs (J5 native USB-Serial-JTAG on the ESP32-C6, BOOT/RESET
buttons, VBUS ORing diode, CC pulldowns) — appropriate for a consumer product that may need field
re-flash without a JTAG probe; this matches the platform-wide flash/debug convention and needs no change.

## 4. BOM cost-down at $38 / $42

No `bom.csv` cost-tracking file exists for either PCIe SKU (only the JLCPCB placement CSV) — unlike
24-pin/12VHPWR-Standard, there is no committed per-line priced BOM to audit against the $38/$42 target
directly; this is itself a gap (see §5). Structural cost observations from the sourced BOM:

- The dominant scaling cost is the **per-cable sensing stack** (INA238 + INA181A2 + TLV7011 + 0.5 mΩ
  shunt + bypass), replicated N times — this is inherent to per-cable Kelvin sensing (§6.1/§6.13, locked)
  and not a cost-down target without a scope change.
- **RS1-3 (0.5 mΩ shunt) and all 4/6 Mini-Fit Jr headers carry no LCSC part** in the BOM (blank field) —
  not a cost problem, a sourcing-completeness gap (see §5); once CSS2H-2512R-L500F is written in, verify
  its JLCPCB mini-reel stock (flagged thin/0 at last check per the OQ-11 ratification sheet) before
  relying on SMT auto-placement — may need the DigiKey standard-reel part hand-fed instead, a real
  assembly-cost/logistics variable the $38/$42 target should account for.
- TJA1051T/3, LP5907, PESD5V0S1BA, INA238, INA181A2, TLV7011 are all shared parts already used
  elsewhere in the platform (24-pin/EPS/12VHPWR) — no PCIe-specific part number proliferation; BOM
  consolidation across SKUs is already good.
- The 2-SKU split itself is a cost-down question in reverse (see §2): one 3-port-capable board with an
  unstuffed 3rd-cable option likely beats maintaining two fabbed boards for a ~$5.5 delta.

## 5. Spec-vs-board drift measured

1. **Shunt part not written in despite OQ-11 now fully resolved.** Spec (2026-07-02 ruling) locks
   EPS/PCIe 0.5 mΩ to **Bourns CSS2H-2512R-L500F**; both PCIe BOMs still show "0.5mΩ" with blank
   LCSC/MPN. The OQ-11 ratification sheet itself (`docs/enterprise-requirements/ratification/
   oq-11-shunt-selection-2026-07-02.md`) already lists this exact BOM-write-in as an open checklist
   item — this review independently confirms it is still open on disk.
2. **No netclasses, no `.kicad_dru` on either PCIe board.** `net_settings.classes` = `[Default]` only,
   no `.kicad_dru` file exists in either module directory. EPS got a full netclass/DRU pass (Power12V/
   GND/Power/Signal/CAN/USB, documented in CLAUDE.md) that was never extended to PCIe — without it,
   the GUI router has no width/via guidance and DRC can't catch an under-width high-current trace on
   either PCIe board pre-route.
3. **USB net names are `/USB_DP` / `/USB_DM`, not the `_P`/`_N` suffix convention.** EPS was explicitly
   renamed (`/USB_DP`→`/USB_D_P` etc.) so KiCad auto-recognizes the differential pair; PCIe never got
   the same rename. Low-value alone (no diff-pair netclass exists yet either, see #2) but both fixes
   are one pass and should land together.
4. **`routing_guides()` in `gen-pcie-condensed.py` is fully implemented**, not the stub the file's own
   header comment claims ("routing_guides() is a STUB (returns "")") — stale comment, harmless, but
   worth a one-line fix so a future reader doesn't waste time.
5. Everything else checked (pin allocation, DETECT 2.2 kΩ code, CAN termination absence at module end,
   TJA1051T/3, RJ-45 FTP jack + SH1/SH2→GND, PESD5V0S1BA on DETECT, no RS-485 population, no Mini-Fit Jr
   on the Hub link) **matches spec/CLAUDE.md** — no other drift found.

## 6. Owner decision list

1. **Collapse to one SKU?** Ship one 3-port-capable PCIe board, sold at $38 with cable-3's sensing
   stack unstuffed, $42 fully stuffed — cuts fab/DRC/silk/qual work in half vs. maintaining 2-port and
   3-port as separate boards, for a ~$5.5 marginal BOM difference. (§2)
2. **Pegless PCIe-keyed connector search.** Does a pegless Mini-Fit Jr sibling with the 45586's 3rd-gen
   PCIe keying exist? If yes, both SKUs drop from 44 mm to ~35 mm height (the same win EPS already
   banked on 87427-0802). Needs a Molex part search, not a layout change. (§2)
3. **Write the locked CSS2H-2512R-L500F shunt MPN into both PCIe BOMs** (and check its JLCPCB mini-reel
   stock vs. the DigiKey standard-reel alternative) — mechanical follow-up, already flagged in the OQ-11
   ratification doc, just needs doing. (§4/§5)
4. **Extend the EPS netclass/`.kicad_dru`/USB `_P`/`_N` rename pass to both PCIe boards** before the
   first real route — otherwise the GUI router has no high-current width/via guidance on either SKU. (§5)
5. **J5 USB-C footprint hole-clearance exception or footprint fix**, done once in `lib/` (affects every
   board sharing this USB-C land, not just PCIe). (§1)
6. **Real 2026 GPU market-share pull for 8-pin PCIe vs. 12VHPWR** to confirm the Standard-tier framing
   in §3 — this review's market read is reasoning from general trend, not sourced 2026 data.
