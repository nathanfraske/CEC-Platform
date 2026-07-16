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

## Phase-0 rulings (owner, 2026-07-16 night)

1. **§12b mezzanine dock RATIFIED** ("cleanest approach; all hubs will have
   it anyway" → Hub-side socket = standard hub fitment, feeds D-3/OQ-77).
   Fallbacks: USB direct / RJ-45 to a hub port. **Tester RJ-45 must be
   PoE-SAFE** → adopt the ENT mis-plug chain (REQ-MOD-COMMON-053: SS110 +
   SMAJ58A + TPS26621 + DETECT series R + pin-7 conditioning, ≈+$2.7).
2. Sense-wire §7: explained to owner (approve/decline the rev3 read-taps +
   PS_ON# drive + −12 V sense adds) — pending their word.
3. R-bank ladder proposal v1 (below) — pending nod.
4. **OQ-1/OQ-10 WAIVED for ST** ("just want it to exist; we know plenty of
   shops"). Pro/Max keep the canonical gate queue.
5. Blade samples: owner orders at some point; **press-fit tool + lever-assist
   de-fit mechanism drafting QUEUED** (deck mechanical work, OQ-86 extension).

## R-bank ladder proposal v1 (2026-07-16 — pending owner nod; [wb] until then)

Basis: HoRX 50 W family legs, forced air + plates, ~48 % derate target;
binary-ish switched GROUPS of parallel legs (AOD4184A low-side + ATOF fuse
per group); vernier (2× IXTH75N10L2, assigned 12 V) interpolates between
steps and runs the OCP fine-ramps; minor-rail OCP = bank steps (fence says
coarse staircase is in-scope).

| Rail | Leg value | Per-leg @rail | Groups (legs) | ST-1000 total | ST-1300 total |
|---|---|---|---|---|---|
| 12 V | 6.0 Ω | 2.0 A / 24 W (48 %) | 1+1+2+4+8+16 (+12 ST-1300) | 32 legs = 64 A / 768 W | 44 legs = 88 A / 1056 W |
| 5 V | 1.0 Ω | 5.0 A / 25 W (50 %) | 1+1+2 | 4 legs = 20 A / 100 W | same |
| 3.3 V | 0.68 Ω | 4.85 A / 16 W (32 %) | 1+1+2 | 4 legs = 19.4 A / 64 W | same |
| 5VSB | 3.3 Ω | 1.5 A / 7.6 W | 1+1 | 2 legs = 3.0 A (+ dedicated 3.5 A/500 ms peak leg, small-FET) | same |
| −12 V | 47 Ω 10 W | 0.26 A | 1 | 1 leg (presence) | same |

Totals: ST-1000 = 43 legs ≈ the committed "~40"; ST-1300 = 55 ≈ "~52".
Step resolution: 2.0 A on 12 V (vernier fills 0–2 A continuously), 5 A /
4.85 A on the minors (cross-load corners = one group each). Why 6.0 Ω over
the priced 5R: honest 48 % derate + round 2 A steps; same family/price
class ([wb] confirm the 6R sibling's LCSC line at BOM lock; 5R fallback =
2.4 A/28.8 W legs, 58 % — still acceptable with plates).
