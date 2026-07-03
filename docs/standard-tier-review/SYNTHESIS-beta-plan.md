# Standard-tier BETA refinement plan — synthesis of the 6-report review pass

_2026-07-03. Owner context: real purchase demand for Standard NOW; the existing boards are
the validated **ALPHA** line — owner clarification (same day): every module's prototype is a
**one-to-one replica of the board**, so each design is validated in principle as-is; beta =
"do the exact same thing," refined. **The beta line is CONFIRMED/green-lit by the owner** —
proposals below execute under the beta flag on their individual approvals; alpha artifacts
never overwritten. Shunt locks (OQ-11) re-confirmed verbally same day._ Inputs: the six reports in this
directory (hub-standard, atx-24pin, eps-8pin, pcie-8pin, 12vhpwr-standard, product-crosscut),
each verified against live kicad-cli/pcbnew state, not documentation claims._

## 1. Fleet reality (measured, not from the books)

| Board | Measured state | Distance to sellable beta |
|---|---|---|
| Hub Standard | Placed + routed; CLAUDE.md items 0/3 are STALE (U7/J_5V/J_KVM/TH1/shield tabs already in); ERC/DRC clean EXCEPT 4× USB-C footprint hole_clearance (fails the CI error gate today) | **Nearest.** Fix the USB-C footprint (lib-wide), C1 part-identity pick, final pour pass |
| 12VHPWR Standard | Routed, fab snapshot proto-v1, thermal PASS; 15 silk cosmetics | **Near.** One shipped defect to fix (U4↔U3 REF thermal coupling — the 2026-06-07 P1 that never landed), stale OQ-11 notes, pigtail spec missing |
| 24-pin ATX (MANDATORY module) | rev2 ordered w/ live erratum (RJ-45 VCC parallel path) + R1 DETECT literally `"R_ID (OQ-6)"` placeholder in the reference schematic/BOM; rev3 schematic fixes verified real but its PCB is byte-identical to rev2's (layout not started); directory naming misleads (`atx-24pin`=shipped, `-rev2`=rotated shrink study) | **Critical path.** The kit cannot ship without it; rev3a scope decision gates everything |
| EPS 8-pin | C6+§6.13+FTP **already on the PCB** (docs stale in our favor); 45/45 placed; **0 tracks/vias/zones**; board is 96×37 not the documented 96×35 | Full routing pass (the automated pipeline's job) |
| PCIe 2/3-port | Same: C6+§6.13+FTP already on both; placement-complete, **zero copper** (183–224 unconnected); no netclasses/.dru | Full routing pass ×2 (or ×1 if SKUs collapse) |

**Repo-wide defect (new, found on 3 boards):** the shared USB-C footprint carries 4×
hole_clearance errors (0.165–0.20mm vs the 0.25mm rule) — one fix in `lib/`, every board
inherits it. It currently fails Hub Standard's CI error gate.

## 2. Cross-board beta work list (no decision needed — engineering/hygiene, do under the beta flag)

W1. **USB-C footprint hole-clearance fix in lib/** (or a documented DRU exception — see D-11).
W2. **OQ-11 MPN sweep**: write CSS2H-2512R-L500F into EPS + both PCIe BOMs; write
    CSS2H-2512R-1L00F reality into 12VHPWR (RS1–RS6 still carry "OQ-11 candidate…NOT locked"
    schematic properties + README/BOM text); 24-pin rev3 carries the K-series + WSK2512 locks.
W3. **Stale-doc reconciliation** (the CLAUDE.md "keep it honest" discipline, violated in both
    directions): hub items 0/3 stale-done; EPS/PCIe "C6 pending" stale-done; EPS README 96×35→96×37;
    24-pin `board-manifest.json` byte-stale; 24-pin directory-naming README warning; 12VHPWR OQ-11 text.
W4. **R1 DETECT backport on the reference 24-pin** (2.2kΩ + MPN — the shipped board's
    source-of-truth schematic must not carry a placeholder that breaks DETECT on re-order).
W5. **Netclass/.kicad_dru + USB `_P`/`_N` rename pass onto both PCIe boards** (EPS-style) before
    any routing starts.
W6. **EPS + PCIe routing passes** through the two-plane router (cec_router + manager judge per
    the CLAUDE.md tiered-pipeline rule) once W5 lands — this is the bulk of the beta engineering.
W7. **12VHPWR U4↔U3 reposition** (the unfixed constraint-swarm P1; placement nudge + re-verify) —
    flagged to the owner because the board is GUI-owned/routed: either an owner GUI move or an
    agent pass on a beta copy, owner's call on venue (D-7).
W8. **Beta denotation mechanics**: Rev field "BETA-1" on every changed board, README revision
    tables, `fab/<board>-beta-*` snapshot naming, BOM output regeneration. Alpha artifacts frozen.
W9. **Hub beta layout: drop the WROOM antenna keepout** (owner ruling 2026-07-03, D-6a) — trim the
    U1 keepout courtyard, let GND pour/parts reclaim the ~450mm² on-board strip, re-DRC. Rides the
    same hub beta layout pass as the W1 outcome + final pours.

## 3. OWNER DECISION LIST (deduped from all six reports; framed, never resolved)

_RE-WEIGHTING NOTE (owner guiding principle, 2026-07-03): "openness, extensibility, make it
better even if it costs a bit more — do it right the first time." The reviews were briefed
cost-down-first; read the framings below through the quality-first lens instead. Concretely
this TILTS (owner still decides): D-5's INA228×4 full-energy option over the mixed-sensor
cost-down; D-4 toward funding the OQ-57 bench + app path so §6.13 ships as a FEATURE, not
dormant silicon; D-2 toward the one-board-3-port PCIe (extensibility by population) while
making EPS-1 a population option rather than a capability cut; D-7 toward requiring the
mirror-lane + via-upsize production bar; keeps USB-C service ports populated. Cost-down
findings remain recorded for when a trade is genuinely quality-neutral._

**Product / kit shape:**
- **D-1. Kit definition + honest install cost.** _PARTIALLY ANSWERED (owner, 2026-07-03):
  connectors for the cable SKUs = standard off-the-shelf panel connectors, ~$0.20 each across the
  board; and the owner is fashioning a CUSTOM female pigtail assembly that "effectively creates a
  board-mount female header" — this attacks §2.8's core premise (no stock board-mount female
  exists) and plausibly retires the F-F bridging-cable SKU question and/or the 12VHPWR captive
  pigtail form. REMAINING for the record: which module(s) the custom female header applies to
  (24-pin output? 12VHPWR output? both), its drawing/spec so it can enter the BOM + spec text,
  and the cable length catalog (OQ-4)._ Original framing: Minimum kit = Hub($36) + 24-pin($35→see D-5) +
  chosen module(s) ⇒ $103–155 component-BOM before cables. Two REQUIRED cable SKUs do not exist
  anywhere (no part, no price): the F-F 24-pin bridging cable (§2.8 promises it; the module is
  uninstallable without it) and the JST 5VSB Hub-feed cable. Decide: bundle-in-box vs accessory
  SKUs, and the patch-cable length catalog (OQ-4). The 12VHPWR captive pigtail also has NO
  length/gauge/strain spec (D-7 ties in).
- **D-2. SKU collapse via population variants.** (a) PCIe: one 3-port-capable board, 3rd cable
  unstuffed at $38 / stuffed at $42 (~$5.5 marginal) — halves layout/qual work. (b) EPS: a 1-cable
  "EPS-1" population (spec-legal per §6.1/6.2; most consumer builds use one EPS cable; deletes a
  full sense chain from the $32 target; generator change is trivial). Approve either/both as the
  beta SKU set?
- **D-3. Mezzanine consumer scope + sequence.** Adopted in principle (8th ruling) but stacked SKU
  is ENT-AIR-only pending your review. Facts from the reports: it does NOT shrink the 24-pin (adds
  parts, trades cables for 8mm Z); it IS the biggest Hub space/BOM lever (mount rectangle
  86×61.75→≤76×60, deletes the RJ-45+power cable pair); and the J6 pin map in the actual netlist
  CONTRADICTS the published design-doc table — must be resolved before any socket design. Decide:
  Standard mezzanine SKU now / after ENT-AIR / never; and authorize the OQ-77 spec-text
  formalization either way.
- **D-4. §6.13 ROI stance.** The detection front-end is locked silicon on 3 module families
  (~$0.85/cable) with ZERO consumer-visible payoff until OQ-57 (threshold/latch bench validation)
  + app surfacing land. Not proposing hardware change — the decision is: prioritize the OQ-57
  bench + firmware/app path into the beta cycle (makes it a FEATURE), or accept it as dormant
  silicon at launch (24-pin rev3 rail-count sub-choice rides this: 12V+5V ~+$1–1.5 vs zero rails).

**Per-board:**
- **D-5. 24-pin beta scope (the critical path).** Narrow "rev3a" = parity fixes 1–5 + locked
  shunts, ~$39–41, fastest to a sellable mandatory module; vs full respin (C6 + §6.13 + mux +
  mezzanine header), ~$40–44, slower, waits on D-3/D-4. Sub-choice: INA228×4 (full energy story,
  +$4–5) vs INA228×2+INA238×2 (+$2–2.5, loses standby-Wh precision on 3V3/5VSB). And: does the
  $35 target itself move (the spec footnote already concedes it)?
- **D-6. Hub beta items.** (a) ~~Antenna keepout~~ **RESOLVED (owner ruling, 2026-07-03): the
  keepout is NOT respected — DROP it in the beta layout (~450mm²/6% reclaim).** Rationale on the
  record: no intention of using Wi-Fi, ever, at this tier — an intentional radiator puts the
  product under FCC intentional-emitter certification (~$100k class cost) for a capability it
  doesn't need; instead the product positions as a SUBASSEMBLY (unintentional-radiator posture).
  Same logic as the modules' earlier keepout drops and the ENT ATR passive-only ruling. Beta
  work item → W9. (b) NanoKVM
  aux header: populate every unit (~$0.14 + THT step) vs DNP-by-default at Standard. (c) C1
  identity: schematic/BOM ship Samxon C487318, CLAUDE.md/README document Panasonic C401967 — pick
  one, fix the other record. (d) OQ-2 finally: LED/5VSB budget (7×SK6812 ≈0.4A vs the ~2.5A rail)
  — needed for the firmware cap number the rev2 erratum mitigation also leans on.
- **D-7. 12VHPWR beta bar.** Require lane-mirroring + 0.9/0.5 via upsizing for the production rev
  (recommended before any "safe under sustained per-pin fault" marketing claim) vs accept as margin
  for a first run? Venue for the U4↔U3 fix (owner GUI vs agent-on-beta-copy)? Own the pigtail spec
  (D-1) + SFF case-fit guidance — the melt-anxiety buyer is disproportionately SFF. True landed
  cost: $21 parts EXCLUDES consigned J3/J4 + pigtail assembly + 4-layer/2oz fab — re-price the $49.
- **D-8. Consumer-hazard disclosure for shipped rev2 24-pins.** The live erratum (short patch can
  put ~1.7A on a 1.5A contact) has no consumer-facing warning artifact. Decide: box insert/label +
  firmware cap as the shipped mitigation story, restrict rev2 units to non-customer use, or hold
  the mandatory module for rev3a (interacts with D-5 timing).
- **D-9. PCIe pegless-keyed connector search** (would drop 44→~35mm height, same win EPS banked)
  — authorize the Molex part search? (Engineering task, cheap; keying is safety-load-bearing so
  it's a search, not a swap-by-analogy.)
- **D-10. Market validation pull**: 2026 GPU market 8-pin vs 12VHPWR share to right-size the PCIe
  SKU bet (the review's read is trend-reasoning, not sourced data).
- **D-11. USB-C footprint fix approach**: footprint correction in lib/ (touches every board,
  needs re-verify each) vs a documented DRU exception (faster, leaves the oddity). Gate: Hub CI is
  red on it today.

**Standing items the pass re-surfaced (already yours, now with fresh context):** OQ-2 (D-6d),
OQ-4 (D-1), OQ-53–56 (hub §2.9 verification against hardware that now exists), OQ-57 (D-4),
Concierge status-surface priority (the "consolidated awareness" pitch currently has no shipped
software surface below the proposed Concierge layer — the cross-cut report's biggest consumer gap).

## 4. Recommended sequencing (my recommendation, yours to override)

1. **Now, no decision needed:** W1–W5 + W8 (hygiene wave — cheap, de-risks everything).
2. **First decisions that unblock the most:** D-5 (24-pin scope — THE critical path), D-11 (CI
   red), D-1 (cables — the kit literally can't ship without two of them), D-8 (rev2 disclosure).
3. **Then:** W6 routing passes (EPS + PCIe per the D-2 SKU outcome), W7, D-6, D-7.
4. **In parallel, product-side:** D-2/D-3/D-4 shape the catalog; D-10 informs D-2's PCIe half.

_Everything above stays proposal-only until owner sign-off; on approval each item executes under
the BETA revision flag with alpha artifacts untouched._
