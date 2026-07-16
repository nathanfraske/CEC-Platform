# Tester Standard (ST-1000 / ST-1300) — main board

DRAFT — no schematic yet. Design basis: docs/psu-tester-architecture-sketch-2026-07-16.md
(§11), docs/psu-tester-bom-draft-2026-07-16.md (§3a/3b), testers/DESIGN-SHEET.md.

ONE board, two population variants: ST-1000 (~1000 W, 2 fans) and ST-1300
(~1300 W, 3 fans) differ ONLY in R-bank leg count, fan count, and fuse values —
never in copper. Compute: ESP32-C6 + TJA1051T/3, DETECT 2.2 kΩ (CAN-only tier),
PWM+RC setpoints, ONE small 2-device L2 vernier, SCP crowbars, NO fast channel,
NO OVP stage, NO RS-485/T1. Slot-bundle posture (sketch §12): blade slot deck +
Hub Standard bay; feature fence and kill-line per sketch §11.

## Stand-up sequence (recorded 2026-07-16 night — owner ask "next steps")

PHASE 0 — owner decisions gating design start: (1) §12b mezzanine dock
ratify/decline (defines deck Hub bay + tester link block); (2) atx24
sense-wire study §7 (PS_ON# drive / PWR_OK µs / −12 V on rev3 — the ST
fence's T1/T3/T6 + −12 V tests ride the 24-pin module); (3) R-bank step
ladder nod (proposal to be drafted); (4) OQ-1/OQ-10 program-gate posture
(ST ahead of, or behind, the canonical interviews/competitive-buy gates).
PHASE 1 — physical, start now: OQ-86 blade sample order (63969-1 depth
≤4.0 mm + deck-scale gang-insertion = #1 mech risk); chassis/extrusion/
plate quotes; duct P-Q → fan lock at first chassis article.
PHASE 2 — design: ST main board capture (six-gate machinery, DESIGN-SHEET
§C/§H); slot-deck board (keying checker extended; bay-LCD headers; Hub bay
per §12b; NOTE: empty alternate slot loads via a PASSIVE pass-through
daughterboard = the retail OQ-89 assembly as slot filler); firmware
scaffold (cec_module runtime, interlock FSM, POST/cross-cal, displays,
OQ-85 profile/MARK contracts); placement/routing via the pipeline
(pipeline-consolidation branch carries the current router).
BUNDLE LONG POLE (platform-side): W6 — EPS + PCIe routing passes (zero
copper today); the $1,299 bundle ships real modules.
PHASE 3 — proto: JLC + consigned THT, chassis FA, POST bring-up, blade
confirm-soak, T1/T3/T6 vs known-good PSU, SCP on sacrificial unit,
report end-to-end.
