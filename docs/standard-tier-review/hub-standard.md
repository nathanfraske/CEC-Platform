# Hub Standard — refinement pass for a consumer sales push

Read-only review, 2026-07-03. Verified against the live files with `kicad-cli`
10.0.4 + `pcbnew` (not against CLAUDE.md's prose, which the file itself warns
goes stale). Board: `hubs/hub-standard/hub-standard.kicad_pcb` /
`.kicad_sch`. No `DRAFT` marker present (already graduated, per R-03).

## Headline: the board is much further along than CLAUDE.md's action items 0/3 say

Action items 0 and 3 in CLAUDE.md both read "PCB (GUI) work still pending" /
"remaining before fab: the GUI pour/route pass." **That is stale.** Direct
measurement:

- ERC: 60 raw hits, but 58 are `lib_symbol_mismatch` (benign cache noise) + 2
  `endpoint_off_grid` (the documented pre-existing off-grid PWR_FLAG stamps).
  **Zero real ERC errors.**
- DRC: 33 raw hits — 0 `track_width`, 0 unconnected, 0 copper clearance/short,
  0 courtyard overlap. 29 are cosmetic silkscreen (24 `silk_edge_clearance`, 4
  `silk_over_copper`, 1 `silk_overlap`) and **4 are `hole_clearance` (severity
  `error`)**, all internal to `J_USB` (pad-to-own-mounting-NPTH, 0.165–0.20 mm
  vs a 0.25 mm rule).
- U7 (2nd TPS2121), J_5V (`MAIN_5V_IN`), J_KVM (NanoKVM aux, right-angle
  S5B-PH-K-S), D7, R15–R24, TH1/R25/C16 (board-temp NTC) are **all present,
  placed, and routed** on the committed PCB — this is the §2.9 power-mux +
  NanoKVM-aux + NTC work CLAUDE.md's action item 0 still lists as "PCB to-do
  (GUI)." RJ-45 shield tabs SH1/SH2 on J2–J5 are tied to GND (verified per-pad).
  91 footprints, 769 tracks, 136 vias, GND poured and filled.
- A **fab snapshot already exists** (`fab/hub-standard-proto-v1/`): full
  gerber set + drill + a 100%-LCSC-sourced 37-line BOM + CPL (77 placements).
  Its own README calls out "29 cosmetic silk DRC warnings" as non-blocking —
  consistent with what's measured here, **except it does not mention the 4
  `hole_clearance` errors**, which is the one live gap (see below).

**Net:** CLAUDE.md's own punch list needs an update — it is describing a board
state from before 2026-06-06, not the current one.

## 1. FAB-READINESS

| # | Item | Verified state | Blocking? |
|---|---|---|---|
| 1 | 5VSB/MAIN_5V/hold-up trunk widths | `+5VSB` 1.0/0.5mm, `/5VSB_RAW` 1.0mm, `/MAIN_5V_RAW` 1.0/0.5mm, `/+5V_HOLD` 1.0/0.5mm — all ≥ netclass floor | No — done |
| 2 | GND plane | Single filled zone, DRC reports 0 unconnected/short | No — done |
| 3 | RJ-45 shield tabs SH1/SH2 → GND | Confirmed on J2–J5 | No — done |
| 4 | §2.9 U7/J8(now `J_5V`)/dividers | Placed + routed (R15–R18 sense dividers, C_SS2, R_ILIM2 present) | No — done |
| 5 | J7 (now `J_KVM`) NanoKVM aux + D7 + R19–R24 | Placed + routed | No — done |
| 6 | TH1/R25/C16 board-temp NTC | Placed + routed | No — done |
| 7 | **`hole_clearance` ×4 inside `J_USB`** (pad vs the connector's own mounting NPTH, error severity) | Real, currently fails `scripts/check-all.sh`'s `--severity-error` CI gate (verified: `kicad-cli pcb drc --severity-error` exits 5, reports exactly these 4) | **Yes — the one real gate failure found** |
| 8 | Cosmetic silk (29 hits: TH1, C8/SW_RESET, J_KVM ×2, C1/TP_VBUS) | Non-blocking per fab README, confirmed harmless (label-over-pad/edge, no copper impact) | No |
| 9 | CPL/BOM/gerbers | Already generated and committed in `fab/hub-standard-proto-v1/` | No |

**Action:** either source a `J_USB` footprint whose mounting-peg NPTH clears
0.25 mm from adjacent pads (common on THT/SMT-hybrid USB-C parts — this is a
footprint-geometry artifact of the XKB U262-16XN-4BVC11 land, not a layout
mistake), or add a documented `.kicad_dru` exception for this specific
same-footprint pad↔NPTH pair with the datasheet clearance cited. Either is a
30-minute fix; right now it is the only thing between this board and a clean
`--severity-error` CI run.

## 2. SPACE

Board outline: **98 × 74 mm = 7,252 mm²** (`gr_rect` 70,90 → 168,164). This is
not an arbitrary number — it is set almost exactly by the 4× M3 mount
rectangle (86 × 61.75 mm, all four corners) plus a uniform ~6 mm edge margin.
**Shrinking the outline materially means moving the mounting holes, i.e. a
chassis decision, not a layout tidy-up.**

Area dominated by (verified courtyard/bbox, largest first):

| Item | On-board area | Note |
|---|---|---|
| U1 ESP32-S3-WROOM-1 (module + antenna keepout) | body 25.5×18mm (~459mm²) + keepout | See below — mostly already off-board |
| C1 4700µF hold-up can | ~19×21mm (~400mm²), 21mm tall | Mandatory, §2.7 |
| 4× RJ-45 (J2–J5) | ~345mm² each = 1,380mm² | LOCKED connector, mandatory |
| 4× M3 mounts (incl. keepout) | ~100mm² each = 400mm² | Mandatory, chassis-set |
| J_5VSB + J_5V (2× 2-pin JST) | ~140+138mm² = 278mm² | Candidate for 1-connector consolidation (already flagged, action item 0c) |
| J_KVM (NanoKVM aux, 5-pin) | ~120mm² | Consumer-fit candidate, see §3 |
| J_USB, LEDs, LDO, TJA1051, buttons, misc passives | remainder | — |

**Antenna keepout, precisely measured:** the courtyard polygon for U1 (a
non-convex L-shape, computed from its actual `F.Courtyard` segments, not just
a bounding box) totals **~1,400 mm²**, of which **~950 mm² hangs entirely off
the board's left edge** (the antenna tail is already positioned to overhang
free space past x=70, i.e. someone already did the "let the antenna radiate
off-board" trick). Only **~450 mm² of keepout is actually consuming on-board
area** beyond the module's own 459 mm² body. So: dropping the keepout
entirely (as EPS/PCIe already did for their C6, "no wireless, per user")
recovers **roughly 450 mm², ~6% of the board** — real, but far more modest
than a naive full-bounding-box read (~2,000 mm², ~27%) would suggest. Worth
doing, not worth overselling.

**Concrete, low-risk shrink/simplify levers (no locked-decision conflict):**
1. **J_5VSB + J_5V → one 3-pin feed.** Already the plan of record (action
   item 0c, "fix later"). Saves one THT connector + ~140mm² + one more cable
   for the consumer to plug in during setup. Do this on the next rev.
2. **Antenna keepout drop** (if WiFi/BLE is not shipping at Standard — see
   decision list). ~450mm² on-board reclaim, modest but free.
3. **Drop or DNP the NanoKVM aux subsystem for the mainstream SKU** (J_KVM +
   D7 + R19–R24 = 8 line items, ~120mm² + supporting passives). See §3 — this
   is more a consumer-fit/assembly-simplicity argument than an area argument
   (BOM cost of the subsystem is ~$0.14/board, trivial; the win is one fewer
   THT connector to hand-place and one fewer feature surface to support).

**Bigger lever, needs an owner call:** the mezzanine design
(`docs/mezzanine-stack-design-2026-06-24.md`) shrinks the *shared mount
rectangle* to ≤~76×60mm when the Hub stacks on the 24-pin module, eliminating
the RJ-45 cable + the 2-pin power-in cable for that one link. That is a
double-digit-percent board/BOM reduction if it ever applies to a Standard-tier
consumer SKU — see decision list (mezzanine scope is presently ENT-AIR-only
per the 8th ruling, "beyond-AIR scope extension FLAGGED FOR REVIEW").

## 3. CONSUMER FIT

**Sales thesis is "know what your PC is doing, consolidated" — a monitoring
appliance, not a hobbyist dev board.** Ranked by consumer impact:

1. **NanoKVM aux link (J_KVM/D7/R19–R24) is the single biggest tier-fit
   mismatch on this board.** It exists to feed a PCIe NanoKVM capture card
   that a mainstream Standard-tier buyer is very unlikely to own — it's a
   forensic/enthusiast accessory (§2.9's own framing: "the dead-system
   forensic-recovery case"). Populating it on every unit adds one more THT
   connector to hand-assemble and one more feature the box has to explain in
   the manual for ~$0.14 of parts and no consumer-visible benefit at Standard.
   Recommend: DNP by default on the consumer SKU (footprint stays for a
   future Pro/accessory bundle), or omit outright if there's no near-term
   NanoKVM product to pair it with.
2. **Dual power-in connectors (J_5VSB + J_5V).** Two separate small JST
   cables from the 24-pin module to the Hub is friction during a consumer's
   own install (vs. one 3-pin cable) and is already the acknowledged
   production target (action item 0c). This is pure setup-ergonomics upside
   with no downside — prioritize it.
3. **7× SK6812 LED chain vs. what a "know what your PC is doing" appliance
   needs.** Seven individually addressable RGB LEDs (Adalight + CEC override)
   is enthusiast-RGB scale, not "status at a glance" scale, and it's the
   dominant lever on the still-open OQ-2 5VSB budget (7 LEDs at full white
   ≈0.4A on the Hub alone, before any module). A consumer product mostly
   needs: power/link-good, an alert/fault color, maybe one per-port
   presence indicator. Flag as a candidate for a firmware-capped smaller
   "meaningful" palette rather than full addressable Adalight — this doesn't
   need fewer *physical* LEDs (still cheap, small) so much as a smaller
   *marketed* max-current state, which is squarely OQ-2's open question.
4. **Hidden GPIO0 service button** — fine as-is, invisible to the consumer,
   no change needed.
5. **Missing for consumers — setup ergonomics / status-at-a-glance:** nothing
   on the board gives a human a way to tell "is this thing working" without a
   host app or the LED chain's software state. Worth a product-level (not
   board-level) note: a single dedicated "Hub OK" indicator that's
   meaningful even with the LED chain dark or the firmware not yet
   configured would help the very first unboxing experience. This is a
   firmware/UX gap, not a board defect, but flagging it since it's exactly
   what "know what your PC is doing" implies at first power-up.
6. **Board-temp NTC (TH1)** is a nice, cheap addition that quietly supports
   the "know what your PC is doing" thesis (Concierge thermal watch) — keep.

## 4. BOM COST-DOWN (target ~$36/100qty; documented parts total ~$12.11/board, 2026-06-05)

| Line | Live stock (checked today) | Risk |
|---|---|---|
| C1 4700µF (Samxon/Ymin VKMI2101C472MV, **C487318**) | **275 units**, $0.73@100 | Still thin for a 100+ qty run with zero attrition margin; single-source can, was ~385 on 2026-06-05 — down, not up. Recheck before any order; consider a 2nd-source can footprint-compatible alternative. |
| U4 TPS3839K33DBZR (**C96333**) | **259 units**, $0.48@100 | Same story — was ~120 on 2026-06-05, now 259 (improved but still thin). Recheck before ordering. |
| J2–J5 RJ-45 Kinghelm KH-RJ45-58 (**C2683360**) | 1,280 units, $0.19–0.34 | Comfortable for a 100-board run (needs 400) but single-source part (the design-ref Wuerth alternative was already rejected for pitch mismatch) — worth a 2nd-source watch, not urgent. |
| J_KVM S5B-PH-K-S (**C157923**) | 11,880 units, $0.06@100 | No risk; cheap regardless of the DNP decision above. |

Other cost-down opportunities:
- **NanoKVM aux subsystem removal** (§3 item 1) trims ~$0.14/board + one THT
  placement — small dollar impact, real assembly-time impact at volume.
- **A quick note found in passing:** the schematic's C1 (**Samxon/Ymin
  VKMI2101C472MV, C487318**) does not match CLAUDE.md/README's documented
  part (**Panasonic EEVFK1C472M, C401967**) — see §5, drift item 1. Before
  ordering, decide which can is actually wanted and correct whichever side
  is wrong; don't ship on an un-reconciled substitution.
- Re-run the whole BOM cost total against current LCSC pricing before the
  sales push — the $12.11/board figure is a month old and at least two of
  its highest-risk lines have moved.

## 5. SPEC-VS-BOARD DRIFT

| # | Finding | Detail |
|---|---|---|
| 1 | **C1 part mismatch.** | Schematic/BOM ship **Samxon/Ymin VKMI2101C472MV (C487318)**. CLAUDE.md and the board README both still describe **Panasonic EEVFK1C472M (C401967)** as the built part, with a whole provenance note about correcting "polymer→electrolytic" naming for that specific Panasonic part. The two are different manufacturers/parts entirely (same value/voltage/footprint). One of the two records is wrong — most likely the prose wasn't updated when the BOM-sourcing pass substituted Samxon (LCSC stock/price reasons are the usual cause). Not a functional problem (both are 4700µF/16V CP_Elec_16x17.5), but it's exactly the kind of drift CLAUDE.md warns about maintaining honestly. |
| 2 | **CLAUDE.md action items 0 and 3 (PCB "still pending GUI work") are stale** — see §1 headline. Real board state is materially ahead of the documented state. |
| 3 | Everything else checked (pin table, DETECT 10k→+3V3 pull-ups on R5–R8, CAN 500k/TJA1051T/3/120Ω split R3+R4=60.4Ω+C7 4n7, FTP shielded jacks + SH1/SH2→GND, RJ-45-only module link, 2-pin dedicated power-in) **matches spec exactly** — no other drift found. |

## 6. OWNER DECISION LIST (not resolved here — framed with numbers)

| # | Decision | Numbers | Ties to |
|---|---|---|---|
| 1 | **Antenna keepout: keep for future Wi-Fi/BLE optionality, or drop for Standard now?** | ~450mm² (~6% of board) on-board reclaim if dropped; LP5907 (250mA max) already can't run S3 Wi-Fi TX bursts (~350mA) without a regulator change anyway, so the keepout currently buys *board-only* optionality, not working Wi-Fi. Radio certs were already declined once at ENT ATR — same cost/complexity logic may apply here. | Not a locked decision (module choice is locked to WROOM-1-N16R8 for USB-aggregation reasons, but the keepout itself is a layout choice) |
| 2 | **OQ-2: total 5VSB current cap / max LED state to budget.** | 7× SK6812 @ full white ≈0.4A on the Hub alone; JST-XH bulk feed ~3A class; shared 5VSB rail sized "~2.5A" in spec. Still genuinely open — do not set unilaterally. | OQ-2 (open) |
| 3 | **NanoKVM aux: ship populated on every consumer Standard unit, or DNP/omit?** | ~$0.14/board parts + 1 THT placement if populated; zero consumer-visible benefit at Standard without an owned NanoKVM. | Product-line scoping, not an OQ |
| 4 | **Mezzanine stack for Standard-tier Hub.** | Owner's 8th ruling (2026-07-02) already ADOPTED mezzanine "+ consumer-side per owner," but scoped the *stacked-product SKU* to ENT-AIR-only "for now," with "beyond-AIR scope extension FLAGGED FOR REVIEW." If/when extended to Standard: mount rectangle shrinks from 86×61.75mm to ≤~76×60mm per the design doc, and the RJ-45 + 2-pin power-in cable pair for that link disappear entirely (one less cable in the consumer's box). This is the single largest space/BOM lever available, gated entirely on that review. | 8th ruling R5; OQ-77 |
| 5 | **§2.9 module-rail scope (OQ-53), external power-in form (OQ-54), source-OR part/back-feed verification (OQ-55), persist-on-fault + hold-up sizing bench verify (OQ-56).** | All still open per spec; the board already implements the 3-source (MAIN_5V/5VSB/wall-wart-via-NanoKVM) OR architecture with 2× TPS2121, so these are verification/scope items against hardware that already exists, not design-open items. | OQ-53/54/55/56 |
| 6 | **C1 part identity (Samxon vs Panasonic)** — pick the actual intended can and correct the other record before the next order. | See §5 item 1. | Not an OQ; documentation/BOM correctness |
| 7 | **`hole_clearance` fix approach on `J_USB`** — footprint swap vs. a documented DRU exception. | 4 hits, 0.165–0.20mm vs 0.25mm rule, error severity, currently fails the CI gate. | Not an OQ; fab go/no-go |
