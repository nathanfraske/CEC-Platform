# 12VHPWR Standard — constraint-aware design-review punch-list

Generated from the agent-swarm constraint review (2026-06-07): 26-constraint deterministic
registry (`scripts/cec_constraints.py`) + a 6-category design-reviewer swarm + Opus synthesis.

**Status of this board:** reference-grade (full gamut run, hand-finalized) but **NOT physically
validated**. Items below are candidate findings weighted by cross-reviewer consensus — verify before acting.

Resolved with no action: **stackup is correct** — F.Cu/B.Cu @ 0.070 mm = 2 oz, In1/In2 @ 0.035 mm = 1 oz
(one reviewer mislabeled 0.07 mm as 1 oz; synthesis caught it).

## P1 — before fab / before power
- [ ] **REF3030 (U4) ↔ LP5907 LDO (U3) too close** — 6.1 mm pad-to-pad vs ≥8 mm. LDO self-heat couples
      into the precision reference → systematic gain error on all 6 INA240 channels. **[6/6 reviewers]**
      → move U4 from (149.38, 105.75) to ~(146.0, 105.75); cascade its passives C22 (/VREF) + C23 (+3V3).
- [ ] **J3/J4 CEM5.1 +12V/GND polarity** — the 12V-2x6 is symmetric; a swapped inner/outer row shorts
      +12V to GND through the shunts. The two connectors are also ~6 mm off the lane-array center.
      → pad-level netlist check (pins 1–6 = +12V → SENSEP*_HI, 7–12 = GND → SENSEP*_LO) against the
      Molex 2191161161 land + the target GPU; add a silk note "VERIFY CEM5.1 PIN POLARITY BEFORE POWER".
- [ ] **12V lane via current margin** — 136 vias at 0.6 mm/0.3 mm (~1.5–2 A each), 10/lane for a 9.2 A/pin
      connector; the Power12V netclass specifies 0.9/0.5 mm. → enlarge to 0.4 mm drill / 0.8 mm pad, or 15+
      vias per J3/J4 lane cluster (§6.7).

## P2 — layout quality
- [ ] **Foreign signals in the high-current corridor** — 57 sideband tracks (/SB_SENSE0, /SB_SENSE1,
      /SB_CBL_PRES, /SB_PWR_STABLE) + /TEMP1 + +3V3 cross the J3→shunt 12V zone (X 113–150, Y 61–84) →
      current-crowding + EMI coupling of the fast 12V transients into the control signals.
      → reroute /SB_* from R10–R13 (X≈150.9, already at the corridor edge) directly right to the ESP,
      out of the 12V column zone; define a signal-keepout over the corridor.
- [ ] **USB nets `/USB_DP` `/USB_DM` → `/USB_D_P` `/USB_D_N`** — the `_P/_N` suffix the diff-pair router
      auto-recognizes (EPS precedent). **[4 reviewers + deterministic]** → rename the 6 schematic labels,
      update the .kicad_pro USB netclass patterns + .kicad_dru gap rule, Update-PCB-from-Schematic,
      re-route the pair with the diff-pair router.
- [ ] **NTC filter caps misplaced** — C20 (/TEMP1) is 37 mm from R20; C21 (/TEMP2) is 56 mm from R21 (both
      parked by the LDO instead of at their NTC divider nodes) → long ADC-input nodes / EMI.
      → move C20 beside R20 (~132.75, 71.0) and C21 beside R21 (~117.25, 121.0).

## P3 — advisory / verify
- [ ] **LP5907 thermal headroom** — at 250 mA worst-case, ΔTj ≈ 109 °C → Tj ≈ 144 °C at 35 °C ambient,
      near the 150 °C limit. → confirm the firmware load budget keeps the LDO well under worst case.
- [ ] **LOGO1 is on F.Cu, not B.Cu** as the generator spec / CLAUDE.md state (passes keepout — touches
      only GND). → align the board to spec (move to B.Cu) or update the spec text.
- [ ] **REF3030 LCSC C38423** — flagged as possibly a different product than REF3030AIDBZR. → BOM verify.
- [ ] **C10–C15 INA240 V+ bypass loop ~7.4 mm** — caps sit on the GND side at rot=90. → tighten to the V+
      pad if corridor clearance allows, or document the loop length as a design constraint.
- [ ] **CF2 0.275 mm outside its RFH2/RFL2 window** — shift to ~x=121.375 to match CF1/CF3–CF6.

## Checker calibrations this review produced (already folded into cec_constraints.py)
- filtered-INA240 Kelvin scope (check the post-filter IN_P/_N, column-alignment) — was N/A, now PASS.
- `hot-sensitive-separation` now matches J4 ("12V-2x6 OUT pigtail").
- `decoupling-cap-owner` measures the real cap→IC-power-pad bypass loop (not IC centre).
