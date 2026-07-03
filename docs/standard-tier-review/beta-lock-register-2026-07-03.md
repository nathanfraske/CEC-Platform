# Standard-tier BETA LOCK REGISTER — 2026-07-03

_The owner's ask: "anything we need to lock for the standard hub and module design and BOM
that needs tweaks or refinements, alternative parts / redesign? I'm fine putting in redesign
work now if it will fix something long-term." Sources: the six-report review pass +
SYNTHESIS-beta-plan.md, the output-interface panel, and a 12-agent parts investigation
(6 web-enabled investigators, each adversarially verified — wf_7dfb54cb-dbd). Every claim
below marked VERIFIED was re-checked live by an independent second agent this session._

## A. LOCK NOW (verified; no further debate needed)

| # | Lock | Evidence |
|---|---|---|
| A1 | **Hub C1 = Samxon/Ymin VKMI2101C472MV, LCSC C487318** (the part already shipping in schematic/BOM/PCB). The Panasonic EEVFK1C472M in CLAUDE.md/README was documentation-only — and Panasonic is OUT OF STOCK ($1.09@100 when available) vs C487318 in stock (275 LCSC / 516 JLC, $0.73@100). Fix the DOCS to match the boards, not vice versa. | VERIFIED live both channels |
| A2 | **PCIe 45586-0005 stays; no pegless variant exists anywhere.** All 7 SKUs in the family (-0005…-1206) differ only in plating/resin/packaging; "PCB Retention: Yes" is fixed parametric. The EPS-style 44→35mm height win is NOT available by part swap. Optional mechanical deviation (delete the 2 peg NPTHs from the land, retention via 16 THT tails) is a board-specific owner call, not a part change. **Fab flag: 45586-0005 is 0-stock / 9-week lead at DigiKey today ($3.03@680)** — order timing matters for any PCIe run. | VERIFIED live (Molex series chart + DigiKey) |
| A3 | **Sensor lines stay as specified** — no cross-vendor drop-in exists for any of INA240A3DR / INA228 / INA238 / INA181A2 / TLV7011. Stock today: INA240A3DR 13k+ (DigiKey, $1.93@500), INA228 healthy, INA181/TLV7011 healthy. | VERIFIED live |
| A4 | **Hub power-in consolidation part = JST S3B-XH-A, LCSC C157928** (3-pin XH RA THT, 3A/pin; curved-needle sibling C163036 40k stock as alternate). Pin order **MAIN_5V / GND(center) / 5VSB** — GND-center makes any misinsertion benign; XH shrouding already blocks reversal/offset. Same family as the existing 2-pin parts: no new assembly process. | VERIFIED live |

## B. DO NOW — no decision needed (hygiene/redesign under existing rulings)

| # | Work | Notes |
|---|---|---|
| B1 | **NEW DEFECT (found by the adversarial pass): Manufacturer↔LCSC field swap, SYSTEMIC** on eps8pin (39/31 swapped pairs), pcie-2port (39/31), pcie-3port (45/37) — C-numbers sit in the Manufacturer property, manufacturer names in the LCSC property, across ~the whole sourced BOM. Any JLC BOM import on those three boards fails wholesale. Hub + 12VHPWR clean. Mechanical fix + re-verify BOM exports. | Fix agent launched (W10) |
| B2 | **USB-C LCSC number is the wrong manufacturer's part**: boards carry C2765186 (Shou Han "TYPE-C 16PIN 2MD(073)") attached to an XKB footprint; the correct XKB part is **U262-161N-4BVC11 = LCSC C319148** (LCSC itself aliases 161N/16XN). Swap the sourcing line. | VERIFIED live; rides W10 |
| B3 | 12VHPWR U4↔U3 REF reposition (shipped defect); mirror lanes + 0.9/0.5 via upsizing (production bar per the quality-first tilt). | From review corpus (D-7) |
| B4 | 24-pin rev3: RS4 → true 4-terminal Kelvin land (WSK2512); resolve the J6 mezzanine netlist-vs-doc pin-map contradiction. | From hygiene-wave flags |
| B5 | EPS + PCIe×2: netclass/.kicad_dru + `_P/_N` prep (W5) then full routing passes (W6) through the tiered pipeline. | The bulk beta engineering |
| B6 | Hub beta layout pass: W9 antenna-keepout drop (ruled), final pours, and the A4 power-in consolidation splice (schematic + PCB). | Redesign scope verified: one connector replaces J_5VSB+J_5V; net names unchanged |
| B7 | Docs: C1 references (A1), stale connector text in EPS/PCIe BOM CSVs, EPS $32-vs-$34 reconciliation. | |

## C. QUALIFY / HEDGE (sourcing actions, cheap, do at BOM-freeze)

| # | Action | Why |
|---|---|---|
| C1 | Add **TI INA237AIDGSR as an approved alternate** on the EPS/PCIe INA238 BOM lines (TI-stated code/hardware equivalent, same VSSOP-10; sourcing-document edit only). | INA238 is the thinnest line: ~1.8k units at DigiKey, inside TI's 2026 repricing cycle |
| C2 | **Hedge/bonded-stock buy on INA238AIDGSR** sized to the first production run; price-lock the healthy TI lines via a distributor quote before the next repricing round. | Same |
| C3 | Watch TPS3839K33 stock (thin) — same-class supervisor alternates exist if it thins further (re-run the check at BOM-freeze). | From A-item investigation |

## D. OPEN — owner decisions (unchanged from the synthesis, updated state)

| # | Decision | State |
|---|---|---|
| D-5/D-5a | 24-pin beta scope + **output form**. Form menu now: owner lean (very short stub + order-time optional extension), **Option F perpendicular daughtercard** (vertical female on an edge-soldered card — machine-solderable/AOI-able, solves the panel's own top objection to hand-crimped pigtails; owner clarified: his hunt's vertical female is an UNQUALIFIED AliExpress-class DIY part — no MPN/spec/footprint — disqualifying for the sellable BOM; Option F revives only via a COMMISSIONED properly-spec'd part (see panel doc's provenance update: crimp assembly now, commissioned part as production endgame), Form B (12cm stub), incumbent C. NEW VERIFIED FACT strengthening the move off C: **no F-F 24-pin cable exists as a commodity product anywhere** (only DIY housings/terminals) — the incumbent always meant CEC fabricates a cable class with zero commercial supply chain. | OPEN, owner lean recorded |
| D-8 | rev2 erratum consumer disclosure. | OPEN |
| D-11 | USB-C footprint: the land is FAITHFUL to the manufacturer drawing (verified byte-identical to upstream); the violations are real vs JLC's 0.2mm NPTH floor (2 pads genuinely sub-floor). NEW: a community **"modforjlc" corrected variant of this exact footprint exists** (cadlab.io / git.rbts.co prior art) — track it down and vet against the XKB mechanical drawing BEFORE settling for a documented DRU exception. Owner picks: vetted corrected footprint (preferred under quality-first, IF dimensionally faithful) vs documented exception. | OPEN, sharpened |
| OQ-2 | 5VSB/LED budget number — finalizes the power netclass width everywhere. | OPEN (owner number) |
| — | 12VHPWR pigtail spec: length/gauge/strain + the confirmed white/black SKU split. | Owner bench + D-7 |

## E. Explicitly re-verified as fine (no action)

- The XKB USB-C footprint geometry itself (do NOT hand-edit the pads/pegs blind — it matches upstream; the fix path is D-11's vetted variant or an exception).
- INA240A3DR / INA228 supply for a 100–1k run.
- The 45586 connector choice (keying is safety-load-bearing; A2).
- Alternatives investigated and REJECTED with reasons on record: Amphenol Minitek HCC (male-on-board convention, same as Molex), Würth WR-MPC3 (3.0mm pitch, incompatible), 3PEAK/Microchip sensor crosses (not drop-in), JST VH for power-in (declined on merits), AliExpress-class "female ATX" parts (no credible listing; unqualified provenance).
