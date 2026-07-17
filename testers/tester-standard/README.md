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
2. Sense-wire §7: **ALREADY IMPLEMENTED** (owner-approved 2026-07-14,
   pipeline branch 2d9fa68c: read taps + Schmitt buffers + AO3400A PS_ON#
   open-drain DRIVE + ESD clamps; drive gated to not-plugged-in / override,
   system-wide BENCH-TESTER-MODE flag = the liability answer). Dependency
   CLOSED — the tester also gains DUT power-CYCLING through the module.
3. R-bank ladder proposal v1 (below) — pending nod.
4. **OQ-1/OQ-10 WAIVED for ST** ("just want it to exist; we know plenty of
   shops"). Pro/Max keep the canonical gate queue.
5. Blade samples: owner orders at some point; **press-fit tool + lever-assist
   de-fit mechanism drafting QUEUED** (deck mechanical work, OQ-86 extension).

## R-bank ladder proposal v1.1 (2026-07-16 — pending owner nod; [wb] until then)

_v1.1 supersedes v1 pre-nod on the owner's minor-rail directive (2026-07-16
night): "I think you're underestimating the capacity of some PSU's 5V and
3v3 rails... need to be able to load and test the 5VSB rail... crossload
tests... spec all of them out to be massively overkill — I've seen PSUs
that can do like 20-30A over 5V alone." v1 minors (5 V 4 legs/20 A, 3.3 V
4/19.4 A, 5VSB 2+peak, −12 V 1) retained here for provenance only._

Basis: HoRX 50 W family legs, forced air + plates, ~48 % derate target;
binary-ish switched GROUPS of parallel legs (AOD4184A low-side + ATOF fuse
per group); vernier (2× IXTH75N10L2, assigned 12 V) interpolates between
steps and runs the OCP fine-ramps; minor-rail OCP = bank steps (fence says
coarse staircase is in-scope).

| Rail | Leg value | Per-leg @rail | Groups (legs) | ST-1000 total | ST-1300 total |
|---|---|---|---|---|---|
| 12 V | 6.0 Ω | 2.0 A / 24 W (48 %) | 1+1+2+4+8+16 (+12 ST-1300) | 32 legs = 64 A / 768 W | 44 legs = 88 A / 1056 W |
| 5 V | 1.0 Ω | 5.0 A / 25 W (50 %) | 1+1+2+4 | 8 legs = 40 A / 200 W | same |
| 3.3 V | 0.68 Ω | 4.85 A / 16 W (32 %) | 1+1+2+4 | 8 legs = 38.8 A / 128 W | same |
| 5VSB | 3.3 Ω | 1.5 A / 7.6 W | 1+1+2 | 4 legs = 6.0 A + mini-CC loop (below) | same |
| −12 V | 47 Ω 10 W | 0.26 A | 1+1 | 2 legs = 0.52 A | same |

**Operating model (owner Q&A 2026-07-17, recorded verbatim-intent):** bank
FETs are DOORS, never dimmers — fully enhanced or fully off; a leg draws its
Ohm's-law current (12 V / 6 Ω = 2 A) whenever its group is on, and nothing in
the banks modulates saturation. The staircase comes from group selection; the
ONE linear FET per rail (the 04a-d vernier, deliberately half-on in its CC
loop) slides 0–1-step continuously between staircase steps. Target 37.3 A =
banks 36 A (18 legs) + vernier 1.3 A. It is a segmented DAC: binary-weighted
coarse segments, linear interpolator fine.

**Why the duplicate 1× group (the "1+1" at the head of every ladder):**
transition insurance, not resolution. (a) GLITCH-FREE STEPPING — crossing a
binary boundary with a single 1-group is break-AND-make (3→4 legs = {1,2}
OFF + {4} ON together; any switching skew and the DUT sees a 2–8 A spike or
droop WE injected). With the spare unit, every ±1 step has a pure-ADDITIVE
path (3→4 = just ADD 1b; the {1a,1b,2}→{4} reshuffle happens later, net-zero,
under vernier cover) — every step becomes a single switch action and the
vernier's transition duty never exceeds one unit. (b) FAULT TOLERANCE — with
one 1-group, an opened LSB fuse deletes every odd step; with two, the full
staircase survives degraded. (c) WEAR/HEAT SHARING — the LSB toggles most in
any profile; two units split the switching and thermal duty (firmware
rotates which serves). Cost: one extra leg per rail (~$3). −12 V's "1+1" is
the same insurance where the whole bank is two legs.

**5VSB mini-CC loop (v1.1)**: the v1 "small-FET peak leg" upgrades to a
proper small LINEAR channel (DPAK-class FET + op-amp, 0–3.5 A programmable,
extrusion-mounted) — one cell, three duties: the ATX 3.5 A/500 ms peak-leg
pulse, FINE standby setpoints for CoC/DoE efficiency points (0.05/0.15/
0.5/1 A class — coarse 1.5 A steps can't hit these), and 5VSB OCP ramps.

**Overkill margins (v1.1 headline)**: 5 V 40 A vs the worst-seen ~30 A
(+33 %); 3.3 V 38.8 A vs ~25 A (+55 %); 5VSB 6 A vs ~3.5 A (+71 %); −12 V
0.52 A vs 0.3–0.5 A spec class. Every rail independently group-switched →
ALL ATX crossload corners reachable (max-minors/min-12V and inverse) as
firmware sequences over the same banks; the DUT's own combined-minor limit
bounds actual concurrent dissipation, so tester capacity is never the cap
in a crossload or OCP hunt. Lever if "massively" should be bigger: 5 V
+2 legs → 50 A (+1 position, ~$6).

Totals (v1.1): ST-1000 = 32 + 22 = **54 legs**; ST-1300 = **66 legs**
(v1: 43/55). BOM delta vs v1: +11 minor legs ≈ +6 positions ≈ +$30–40
(resistors + 3 more AOD4184A/ATOF group sets + plate inches).
Step resolution: 2.0 A on 12 V (vernier fills 0–2 A continuously), 5 A /
4.85 A on the minors (coarse staircase in-scope per fence; option noted in
FOLLOWUPS — one L2 device relay-switchable to 5 V/3.3 V if shops ever want
fine minor-rail OCP hunts). Why 6.0 Ω over
the priced 5R: honest 48 % derate + round 2 A steps; same family/price
class ([wb] confirm the 6R sibling's LCSC line at BOM lock; 5R fallback =
2.4 A/28.8 W legs, 58 % — still acceptable with plates).

## Field arrangement math v1 (2026-07-16 — companion to ladder v1, rides the same nod)

- **Part — ONE housing everywhere**: HoRX 50 W aluminum-shell family (RX24-class
  gold shell, ~51×30×17 mm body, end terminal lugs, base mounting ears). Priced
  line = the 5R C2923747 ($1.71–3.24, healthy stock); ladder v1 wants the 6R
  sibling ([wb] confirm its LCSC line at BOM lock; 5R fallback = 2.4 A/28.8 W
  legs at 58 %). Values by rail: 6R0 (12 V) / 1R0 (5 V) / 0R68 (3.3 V) / 3R3
  (5VSB) — same shell, one mechanical design — plus one 47R 10 W small shell
  (−12 V). Terminals are screw/solder LUGS, not .250 blades: a bolted .250 male
  blade lug per terminal makes the deck reach (Arcol HS50 push-on-terminal
  variant = western-sourcing fallback) — [wb] at blade-sample time.
- **Fold rules** (the wall-cartridge form, DESIGN-SHEET 22b v2): positions at
  ~36 mm pitch along the wall (30 mm shell + air gap); back-to-back pairs = 2
  legs/position; walls at ~50 mm pitch (3 mm plate + 2×17 mm shells + ~13 mm
  air), fins PARALLEL to airflow; ONE row tall per wall, always (single gang
  drop into the deck + one feed bar; height never scales). Scaling axes, in
  order: row length along the flow axis (cheap; preheat absorbed — worst-case
  air rise ~20 K at W-tier CFM), then wall count across the duct. NEVER a
  second row vertically on a wall.
- **Census** (v1.1 overkill minors = 22 legs ≈ 11 positions on every model;
  rows budgeted ≤ ~400 mm against the 430–450 mm console class):

| Model | 12 V legs | Minor legs | Total | Positions | Walls × pos/row | Duct |
|---|---|---|---|---|---|---|
| ST-1000 | 32 | 22 | 54 | 27 | 3 × 9 (~324 mm) | ~160 mm |
| ST-1300 | 44 | 22 | 66 | 33 | 3 × 11 (~396 mm) | ~160 mm |
| Pro / Max | ~53 | 22 | ~75 | 38 | 4 × 10 (~360 mm) | ~210 mm |
| Pro-W / Max-W | ~96–100 | ~22 | ~120–125 (§13) | ~61 | 6 × 11 (~396 mm) = two lanes of 3 | 2 × ~160 mm (§13 two-lane) |

- **Continuous-power ledger** (banks × per-leg W + verniers): Pro 12 V
  53×24 ≈ 1.27 kW + 8 verniers ≈ 0.4 kW ≈ the 1600 W continuous rating ✓;
  W ~100×24 ≈ 2.4 kW + 13 verniers ≈ 0.6–0.75 kW ≈ 3.0 kW ✓ (installed
  ~125×50 W ≈ 6.2 kW at the ~48 % derate doctrine — the 2× part-count margin
  IS the derate, that's where "~120" comes from). Minor capacity adds ≤~390 W
  (200+128+30+…) but concurrent actual is DUT-bounded (a real unit's
  combined-minor limit is ~130 W) — capacity is for coverage + OCP hunts,
  not simultaneous dissipation; duct sizing unchanged.
- **Volume check (the "does it balloon" answer)**: W-tier = 6 walls × ~400 mm
  rows × ~100 mm resistor zone ≈ 13 L total for 3 kW delivered — the field
  IS the heatsink AND the radiator, so no second thermal volume exists to grow;
  air rise ≈ 20 K at 263 CFM. Banks are PER RAIL and pooled: the fixture matrix
  routes any head (12V-2x6/EPS/PCIe/24-pin) into the same 12 V plane; only the
  12 V bank count scales with tier, minors are constant (22 legs everywhere,
  ladder v1.1).
- Group maps beyond ST (Pro 53-leg / W ~100-leg 12 V ladders) = [wb] at each
  tier's ladder pass; switching/fusing stays per GROUP (AOD4184A + ATOF sized
  at group current), the resistor is the per-leg unit, trip watch per group.
- CORRECTION trail: 22b's original "ST-1000 = one double-sided plate" was
  pre-math (a single row would be ~790 mm); v1-minors math said 2 walls;
  ladder v1.1's overkill minors settle ST-1000 at THREE walls (3 × 9). Fixed
  in DESIGN-SHEET 22b.

## Split architecture — hot load slices vs cool control board (owner question 2026-07-16 night; RECOMMENDED, pending nod)

Owner: "make the hot loop ends with all the hot components on their own
(metal cored?) PCB, run the signalling to them, all signaling separate —
so we can put them in different compartments or stacked or whatever?"

RECOMMENDATION: YES, with one sharpening — the BIG heat is already
off-PCB by design (50 W legs on chassis plates, vernier/SCP FETs on the
extrusion). What actually splits off is the SWITCHING LAYER, as per-rail
**LOAD SLICES**: bank-switch FETs + ATOF fuses + loop shunts + trip
comparators + LOCAL gate drivers on small hot-zone boards; the control
board stays pure SELV logic in the cool zone. Substrate: thick-copper FR4
baseline; IMS/metal-core = a PER-SLICE OPTION where SMD switch dissipation
concentrates (the 12 V group rows at W-tier currents) — decide per slice
at layout with the electrothermal gate, don't blanket-IMS.

Rules that make the split safe:
- Gate DRIVERS live ON the slice; the harness carries logic-level
  enable/PWM only (never gate charge over a cable).
- De-gate pull-downs live ON the slice → **an unplugged harness IS the
  safe state (no load), physically.**
- Kelvin pairs stay on-slice (shunt → comparator local); only digital
  trip/latch lines cross.
- Keyed connectors, counted in the fail-safe analysis.

What it buys: compartment/stacking freedom (owner's ask); ONE control
board across ST/Pro/Max/W — W = MORE IDENTICAL SLICES (the DESIGN-SHEET §H
population strategy physicalized); the slice is the service unit (burned
group = swap a cheap board); and the SE two-chamber wet-gallery/dry-deck
becomes the SAME architecture instead of a special case. Precedent: the
fast-channel-slice is already its own board for µH reasons — this
generalizes the pattern. Cost: +connectors/assembly, offset by slice reuse
across four SKUs.
