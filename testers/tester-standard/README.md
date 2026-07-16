# Tester Standard (ST-1000 / ST-1300) — main board

DRAFT — no schematic yet. Design basis: docs/psu-tester-architecture-sketch-2026-07-16.md
(§11), docs/psu-tester-bom-draft-2026-07-16.md (§3a/3b), testers/DESIGN-SHEET.md.

ONE board, two population variants: ST-1000 (~1000 W, 2 fans) and ST-1300
(~1300 W, 3 fans) differ ONLY in R-bank leg count, fan count, and fuse values —
never in copper. Compute: ESP32-C6 + TJA1051T/3, DETECT 2.2 kΩ (CAN-only tier),
PWM+RC setpoints, ONE small 2-device L2 vernier, SCP crowbars, NO fast channel,
NO OVP stage, NO RS-485/T1. Slot-bundle posture (sketch §12): blade slot deck +
Hub Standard bay; feature fence and kill-line per sketch §11.
