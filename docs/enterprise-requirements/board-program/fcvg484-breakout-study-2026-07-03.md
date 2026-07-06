# FCVG484 breakout/fanout feasibility study (2026-07-03)

_Status: DRAFT board-program study. Scope: the single biggest layout risk flagged for the
ENT hub — can the MPFS FCVG484's 6-layer stackup (`hub-ent-variants-plan.md` §5) actually
carry the hub's real signal demand, or does the part force an 8-layer board? This is a
**feasibility study, not a pin-assignment freeze** — the final ball-by-ball assignment is a
Libero/pin-planner deliverable that must confirm every number here before sheet-02 capture
locks. Does not touch `hubs/hub-enterprise/**`, `scripts/cec_sch_*.py`, or
`scripts/cec_sym_audit.py` (owned by other agents in flight)._

**Inputs:** `docs/enterprise-requirements/spec-sheets/hub-ent-variants-plan.md` (§3 IO
budget, §5 stackup, §7 MCX growth), `lib/vendor-data/mpfs-fcvg484-pins.csv` (the cached
484-ball map + its own provenance/caveats header), `lib/cec-ent-compute.pretty/BGA-484_19x19mm_P0.8mm_MPFS_FCVG484.kicad_mod`
(0.8mm pitch / 0.4mm pad / 0.5mm NSMD land), CLAUDE.md's stackup + netclass conventions
(existing platform via/track classes, for comparison). Computed with
`scripts/cec_fcvg484_breakout_study.py`; the full per-ball ring/quadrant table is written
to `docs/enterprise-requirements/board-program/fcvg484-ring-quadrant-table.csv` (run with
`--csv` to regenerate).

## Verdict, up front

**6-layer is OK, WITH CONDITIONS.** The ENT hub's actual signal demand on this part is
small (see §1) — on the order of 85-100 balls out of 484, i.e. the design uses roughly
one-fifth of the package. Because every signal-capable bank (GPIO_BANK1, HSIO_BANK0, MSSIO)
has 2-4x more balls than the demand needs, the designer has real freedom to **choose the
shallow-ring balls** for nearly everything and simply leave the rest of each bank
unpopulated/NC. That freedom is what makes 6 layers workable at all on a 0.8mm-pitch,
484-ball part.

The conditions:
1. **Via-in-pad (filled + capped, IPC-4761 Type VII) on a bounded ~35-50-ball subset** — the
   two banks that have **no shallow choice at all** (JTAG_SYSCTRL, 13 balls, and SGMII, 10
   balls — both sit entirely at ring 4-7, fixed by silicon, see §1) plus whatever spills
   past ring 3 in MSSIO once its ~28-ball demand is tallied (§1, §4). This is a bounded,
   named list of balls, not full-part via-in-pad.
2. **A genuine, controlled-impedance inner signal layer reachable from the NW quadrant**
   (where JTAG_SYSCTRL + SGMII + the deep half of MSSIO all sit) for the SGMII differential
   pairs and the JTAG bus. The plan's L4 ("pwr/sig") is the candidate layer; §3 below argues
   it needs to reserve real area for this, not just nominal "sig" in its name.
3. Everything else (both RGMII buses, the pin-7 fabric-GPIO mesh, QSPI, eMMC, I2C, CAN,
   misc GPIO) can be placed at ring ≤ 3 by choice and fan out on the component layer (L1)
   with ordinary staggered dog-bone vias — no via-in-pad required for those.
4. The **existing platform Signal netclass (0.22 mm track) does not fit in a BGA escape
   channel at 0.8 mm pitch** (§2) — this board needs its own, finer BGA-fanout netclass.
   This is new scope, not a reuse of an existing `.kicad_dru` class.

The **8-layer fallback triggers** are named in §5 and are real, not hypothetical: DDR
populated instead of LIM-only is the big one.

## 1. Ball-field geometry: what's actually used, and where it sits

`scripts/cec_fcvg484_breakout_study.py` classifies every ball by **ring** (grid-step
distance from the package edge; ring 0 = outer perimeter, ring 10 = package center on this
22×22 grid) and **quadrant** (NW/NE/SW/SE, split at grid center). Per-category population:

| Category | n | Quadrant(s) | Max ring | Shallow choice? |
|---|---|---|---|---|
| POWER | 169 | all 4 (32/53/51/33) | 10 (die center) | n/a — plane-fed, see §3 |
| MSS_DDR | 88 | SW (84), NW (4) | 7 | moot if LIM-only (§5) |
| GPIO_BANK1 (fabric GPIO) | 84 | NW (28), NE (56) | 7 | **yes** — ring≤3 covers 61/84 |
| HSIO_BANK0 (fabric high-speed IO) | 60 | SE (100%) | 7 | **yes** — ring≤3 covers 40/60 |
| MSSIO (MSS peripheral IO, banks 2+4) | 38 | NW (100%) | 6 | **yes, tight** — ring≤3 covers 29/38 |
| XCVR (SerDes, **NC** — part-agnostic land) | 22 | NE (12), SE (10) | 3 | n/a — unused, shallow only |
| JTAG_SYSCTRL (System Controller bank 3) | 13 | NW (100%) | 7 | **no — 100% at ring 4-7** |
| SGMII (MSS-SGMII, 2 fixed lanes + refclk) | 10 | NW (6), SW (4) | 7 | **no — 100% at ring 4-7** |

Two structural findings drive the whole study:

- **The package center (ring 8-10, 36 balls) is 100% POWER.** No signal bank reaches past
  ring 7. The interior is pure power/ground distribution — no signal-vs-power routing
  contention at the die core; those balls need a straight via to a plane, not lateral
  escape (§3).
- **JTAG_SYSCTRL and SGMII are entirely interior (ring 4-7) with zero outer-ring
  presence.** These are silicon-fixed ball locations (System Controller and the MSS's own
  dedicated SGMII SERDES lanes, not the general-purpose XCVR bank) — the designer gets no
  choice here regardless of how little of each bank is used. This is the one true "forced
  depth" cost in the whole part, and it is small (23 balls) but non-negotiable.

### Demand tally (baseline ENT-NET-B; see §7 variants-plan and the growth deltas in §5/§7 here)

Demand items and where they must draw from (no dedicated "USB"/"I2C"/"CAN"/"QSPI"/"eMMC"
category exists in the cached ball map — confirmed by grep, zero hits — which is expected
for PolarFire SoC's MSS: those peripherals are pin-muxed onto the generic MSSIO bank by the
Libero pin planner, not fixed balls. That pin-mux step is what must confirm every MSSIO
number below before signoff.):

| Demand item | Signals | Draws from | Ring reachable by choice? |
|---|---|---|---|
| RGMII #1 (→ LAN9370 #1) | 12 (+~2 mgmt) | HSIO_BANK0 | yes, ring≤2 (31 avail) |
| RGMII #2 (→ LAN9370 #2) | 12 (+~2 mgmt) | GPIO_BANK1 (NE) | yes, ring≤2 (29 avail, NE) |
| pin-7 fabric GPIO ×8 (SYNC/FREEZE + heartbeat) | 8 | GPIO_BANK1 (NW or NE) | yes, ring≤2 |
| MSS-SGMII uplink (NET-B: 1 lane; MC/MCX: 2 lanes) | 6 / 10 | SGMII (fixed) | **no — ring 4-7** |
| QSPI (A/B firmware flash) | 6 | MSSIO | yes, but adds to the tight bank (below) |
| eMMC 8-bit (CLK/CMD/RST/DAT0-7) | 11 | MSSIO | yes, but adds to the tight bank |
| I2C (ADS7830, DETECT/rail-sense ADC) | 2 | MSSIO | yes |
| CAN TXD/RXD(+STB) | 3 | MSSIO | yes |
| misc GPIO (BOOT strap, WD heartbeat/alive/force-standby, RJ-11 relay drive) | ~6 | MSSIO | yes |
| JTAG (TCK/TDI/TDO/TMS/TRSTB + DEVRST_N/FF_EXIT_N/IO_CFG_INTF + SCK/SDI/SDO/SPI_EN/SS) | 13 (all of bank 3) | JTAG_SYSCTRL (fixed) | **no — ring 4-7** |

MSSIO subtotal: 6+11+2+3+6 = **28 of 38 balls**, before any MCX/USB delta (see below) — this
is the tightest bank in the budget, not SGMII or JTAG (which are fixed-depth but low-count).

**Real gap found, not guessed:** the cached ball map has no ball named for USB. PolarFire
SoC's MSS USB 2.0 OTG interface is a hard MSS peripheral, and the antmicro-sourced table
this CSV derives from evidently didn't isolate it as its own unit — meaning its pins are
either lumped into the generic MSSIO name set without a distinguishing label, or genuinely
absent from what this specific 250T-based board captured. **This is a hole in the ground
truth, flagged per the CSV's own provenance convention, not resolved by assumption.** It is
the single largest open item before sheet-02 capture (see §5, risk 2).

Total signal-only balls needed at baseline: RGMII×2 (28) + pin-7 (8) + SGMII (10) + MSSIO
cluster (28) = **74**, plus JTAG (13, mandatory) = **87 of 484** — roughly **18%** of the
package, confirming the prompt's framing that demand sits far below the full ball count.
Available choice-pool across the three signal-choice banks (182 balls total: 84+60+38) means
there is nearly 2.5x headroom over the 74-ball choice-demand, which is why the shallow-ring
placement strategy in §4 works.

## 2. Via/track feasibility at 0.8 mm pitch

**Geometry.** Ball pitch 0.8 mm, pad 0.4 mm (NSMD 0.5 mm mask opening) per the vendored
footprint. Two cases:

- **Direct-neighbor gap** (between two adjacent pads on the same row/column): edge-to-edge
  gap = 0.8 − 0.4 = **0.4 mm**. A single trace of width _t_ with clearance _c_ on each side
  needs _t + 2c ≤ 0.4 mm_. At the platform's own existing 4-mil-class rule (t=0.1 mm,
  c=0.1 mm): 0.1 + 0.2 = 0.3 mm ≤ 0.4 mm — **fits, with 0.1 mm to spare**, using ordinary
  (non-HDI) fab capability. At a tighter 3-mil-class rule (t=0.075 mm, c=0.075 mm): two
  traces could plausibly share one gap (2×0.15 = 0.30 mm ≤ 0.4 mm) but that is a genuinely
  tight fit worth a DFM confirm with the actual fab before relying on it.
- **Diagonal dog-bone via site** (the point equidistant from 4 surrounding ball centers):
  distance from that point to each ball center = 0.8 × √2⁄2 ≈ **0.566 mm**. For a via pad
  diameter _Dv_: clearance to the adjacent 0.4 mm ball pad = 0.566 − Dv⁄2 − 0.2. At a
  standard multilayer capability of Dv = 0.5 mm (0.3 mm drill, a routine — not premium —
  spec on most fabs including JLCPCB's standard multilayer tier): clearance = 0.566 − 0.25 −
  0.2 = **0.116 mm**, comfortably inside a 0.1 mm clearance rule. **A standard 0.3 mm
  drill / 0.5 mm pad via fits in the dog-bone gap at 0.8 mm pitch — no laser microvia
  required for the geometry itself.**

**The real constraint is not "does the via fit," it's "does a via there block a pass-through
trace that a deeper ball needs."** Each dog-bone cell can carry either one via (that ball's
own escape) or 1-2 pass-through traces for someone else's deeper signal, not both freely.
This is where **via-in-pad** earns its keep: for an outer-ring ball whose own via is dropped
straight into the (filled/capped) pad instead of the diagonal dog-bone gap, the surrounding
dog-bone cells stay entirely free for other signals' pass-through routing. Given the low
overall demand density (§1), most outer-ring balls used by our design will be genuinely
adjacent to unused (NC) balls, so channel contention is much lighter than a fully-populated
part would produce — but the JTAG+SGMII (+ MSSIO ring-3 spillover) cluster in the NW
quadrant is exactly the region where this matters, because it is genuinely dense (JTAG,
SGMII, and the shallow half of MSSIO all crowd the same quadrant).

**Comparison to the platform's existing netclasses** (per CLAUDE.md / the existing
`.kicad_dru` files): Power/GND vias run 0.8-0.9 mm pad / 0.4-0.5 mm drill, Signal traces run
0.22 mm, Sense vias run 0.6/0.3 mm. **None of these fit a BGA escape channel at 0.8 mm
pitch** — the existing 0.22 mm Signal netclass alone (0.22 + 2×0.1 = 0.42 mm) is already
over the 0.4 mm direct-neighbor gap. **This board needs a new, dedicated BGA-fanout
netclass** (recommend: track ≈0.10-0.13 mm, clearance ≈0.10 mm, via ≈0.5 mm pad / 0.3 mm
drill for the dog-bone sites, via-in-pad ≈0.45-0.5 mm pad / 0.2-0.25 mm drill filled+capped
for the bounded deep-ball set) — this is new scope for the ENT hub's `.kicad_dru`, not an
extension of an existing class, and should be flagged to whichever agent owns that file.

**Fab-class read:** 0.8 mm is not considered ultra-fine-pitch by most shops' own guidance
(many reserve mandatory HDI/laser-via requirements for ≤0.5 mm pitch BGAs); via-in-pad at
0.8-1.0 mm pitch is commonly offered as a routine add-on rather than a premium-tier-only
service. That reading is **not verified against an actual quote** for this program — flagged
as a DFM-confirm item (§5), not assumed, consistent with the repo's "flag, don't guess"
convention on unverified fab capability.

## 3. The 6-layer proposal: stackup assignment

Per the variants-plan (§5): `L1 sig/BGA fanout, L2 GND, L3 pwr, L4 pwr/sig, L5 GND, L6 sig`.
Read against the demand in §1:

- **L1 (component layer):** carries the shallow-ring (≤3) escape for RGMII×2, pin-7 GPIO×8,
  and most of the MSSIO cluster (QSPI/eMMC/I2C/CAN/misc), all via ordinary staggered
  dog-bone vias per §2. No via-in-pad needed here.
- **L2 / L5 (GND):** stitching vias from the ring 8-10 power/ground core and from the
  outer-ring GND balls in POWER; also the reference plane the SGMII/JTAG signal layer(s)
  need adjacent for controlled impedance.
- **L3 (pwr):** cannot be one solid plane — POWER carries at least a dozen distinct rails
  (VDD core 1.0/1.05, VDD18, VDD25, VDDA, VDDA25, VDDAUX1/2/4, VDDI0-6 per-bank IO rail,
  VDD_XCVR_CLK). L3 has to be a **stitched multi-region pour, split per rail**, following
  the same "high current = pours, split at need" practice CLAUDE.md already documents for
  the consumer modules — not a literal single plane.
- **L4 (pwr/sig, shared):** this is the layer that actually carries the study's one hard
  requirement — the SGMII differential pairs and the JTAG bus need an inner layer reachable
  from the NW quadrant with a plane close by for impedance control. Recommend L4's "sig"
  portion be **geographically scoped to the NW quadrant** (where JTAG+SGMII+MSSIO-ring-3
  live) and its "pwr" portion carry the quieter analog rails (VDDA/VDDA25/VDDAUX) elsewhere,
  so the two uses don't compete for the same real estate.
- **L6 (sig, bottom):** available as a second export layer for anything L1/L4 can't clear
  (e.g., the RGMII mgmt/MDIO pins, or a deep MSSIO spillover ball) via a through via — no
  blind/buried vias are assumed necessary given via-in-pad already covers the deep set.

**Power-ball fanout:** with the die core (ring 8-10, 36 balls) 100% POWER and no lateral
signal contention there, those balls take a straight via to the nearest plane/pour segment
for their rail — no escape-channel budget consumed. Decoupling for **interior** power balls
cannot be a local cap directly under the ball (no component-side room inside a populated
BGA shadow past ring ~1); it has to rely on the plane/pour itself plus a ring of bulk/local
caps placed just outside the package courtyard, which is standard practice for a part this
size and should be called out explicitly in the layout guide rather than assumed implicit.
Only the outermost ring (0-1) of POWER balls are candidates for a directly-adjacent local
cap.

**Verdict for this section: 6-layer OK, tight in the NW quadrant, conditional on L4's sig
area being reserved (not incidentally consumed by the pwr pours) and on the via-in-pad scope
in §2.**

## 4. Per-bank pin-assignment recommendations (feeding sheet-02 capture)

Ball-map quadrants are fixed by silicon; the only free variable is **which edge of the
board the package is oriented toward**. Reading the quadrant map against the variants-plan's
edge map (§4 there: front = 8×RJ-45 module ports + T1/LAN9370s; rear = uplink MagJack(s) +
RJ-11 + USB-C + EXT + power JST; interior = NanoKVM aux + JTAG + strap header + M3 mounts):

| Quadrant | Contents | Recommended facing |
|---|---|---|
| **SE** — HSIO_BANK0 (100%, all fabric high-speed IO) | RGMII #1 candidate | **Front edge** — toward the module-port / T1-switch side, shortest RGMII-to-LAN9370 run |
| **NE** — GPIO_BANK1 majority (56/84) | RGMII #2 + pin-7 fabric-GPIO mesh | **Front-adjacent** — pin-7 fans out point-to-point to all 8 front-edge RJ-45 ports anyway |
| **NW** — MSSIO (100%) + JTAG_SYSCTRL (100%) + SGMII (60%) | QSPI/eMMC/I2C/CAN/misc GPIO, the uplink SGMII lane(s), the JTAG/strap header | **Rear/interior edge** — SGMII short-run to the uplink PHY(s)+MagJack at the rear; JTAG/strap header lands in the interior near this quadrant per the variants-plan's own interior list |
| **SW** — MSS_DDR majority (84/88, likely NC if LIM-only), 40% of SGMII | quiet zone if DDR unpopulated | **Interior/mounting corner** — least routing pressure; a natural place for an M3 mount or the NanoKVM aux header keepout |

Recommendation for sheet-02: within each bank, **prefer ring ≤ 2 balls first, ring 3 only
if needed** (per the cumulative tables below), and reserve the ring 4-7 JTAG_SYSCTRL/SGMII
balls exactly as bonded out (no choice there).

Cumulative balls available by ring, the numbers sheet-02 should pin against:

```
GPIO_BANK1  NE (n=56): r0:11 r1:21 r2:29 r3:37 r4:42 r5:49 r6:53 r7:56
GPIO_BANK1  NW (n=28): r0:6  r1:12 r2:19 r3:24 r4:26 r5:28
HSIO_BANK0  SE (n=60): r0:12 r1:23 r2:31 r3:40 r4:46 r5:52 r6:57 r7:60
MSSIO       NW (n=38): r0:9  r1:17 r2:23 r3:29 r4:34 r5:37 r6:38
JTAG_SYSCTRL NW(n=13): r0:0  r1:0  r2:0  r3:0  r4:3  r5:5  r6:10 r7:13
SGMII       NW (n=6):  r0:0  r1:0  r2:0  r3:0  r4:1  r5:3  r6:5  r7:6
SGMII       SW (n=4):  r0:0  r1:0  r2:0  r3:0  r4:0  r5:1  r6:3  r7:4
```

Combined GPIO_BANK1+HSIO_BANK0+MSSIO balls available at ring ≤ 3, by quadrant: **NE 37, NW
53, SE 40** — each quadrant clears its own baseline demand (§1) with margin, before any
MCX/USB delta.

## 5. Risks + the 8-layer fallback

1. **DDR populated instead of LIM-only (variants-plan open row #4) is the dominant
   trigger.** MSS_DDR is 88 balls, entirely SW/ring 0-7, with real DDR byte-lane length- and
   skew-matching requirements that typically want 2 dedicated striplined signal layers on
   their own. Populating DDR on top of everything in §1 would very likely force 8+ layers —
   this study's "6-layer OK" verdict assumes LIM-only per the variants-plan baseline.
2. **USB OTG has no named ball in the cached map** (§1). Until Libero/pin-planner confirms
   where MSS USB lives, its true pin cost and depth are unknown. If it lands in the
   already-tight MSSIO bank (28/38 committed at baseline) it's absorbable; if it needs a
   dedicated differential pair outside the shallow-choice pool (i.e., forced into deep rings
   alongside JTAG/SGMII), it grows the mandatory-deep cluster and erodes the L4 margin in §3.
3. **SGMII lane exhaustion for MCX.** The SGMII bank has exactly 2 lanes (10 balls total).
   The variants-plan's MC tier already consumes **both** lanes for its dual-uplink PHYs
   (§7 there: "MC dual-uplink = 2 discrete DP83869HM PHYs, each with its own lane"). MCX's
   inter-SoC sync link is specced as "SGMII lane 2 or LVDS fabric pair" (§3 there) — but by
   the time MC's population is added, **lane 2 is already spoken for by the second uplink
   PHY**, so MCX's sync link is **forced onto the LVDS fabric-pair fallback**, not a free
   choice between the two. That fabric pair has to come out of GPIO_BANK1 or HSIO_BANK0's
   shallow-ring budget (§1), eating into the margin computed there — worth flagging to
   whoever finalizes the MCX population plan so it isn't discovered at layout time.
4. **MSSIO is the tightest bank, not the deepest.** 28 of 38 balls already committed at
   baseline (§1); MCX's extra 3-node CAN segment (private watchdog/SoC-A/SoC-B bus, §7 of
   the variants-plan) and any USB pins that land here push it toward 34-37/38. Recommend
   this bank get the first Libero pin-planner pass, since it has the least headroom of any
   bank in the whole study.
5. **The 095T-vs-250T ball-validity gap the CSV's own header already flags.** The cached
   table is sourced from a 250T-based design; Microchip states package/pin *compatibility*
   across the density ladder in this package, not that every bank bonds out identically on
   the smaller 095T die. If the real 095T bonds out fewer usable balls in GPIO_BANK1,
   HSIO_BANK0, or MSSIO than this table assumes, the shallow-ring headroom computed in §1/§4
   is optimistic. Recommend confirming against Microchip's official 095T Package Pin
   Assignment Table before sheet-02 freezes (the CSV notes the PPAT .xlsx downloads were
   Akamai-blocked in this environment — may need a support-portal/NDA request, an owner
   action, not something scriptable from here).
6. **Via-in-pad DFM is asserted, not quoted** (§2). If the chosen fab cannot do filled/capped
   via-in-pad at reasonable cost/lead-time for a low-volume ENT board, the bounded ~35-50
   ball deep cluster (JTAG+SGMII+MSSIO ring-3 spillover) has no fallback within 6 layers —
   that specific failure mode is the concrete trigger for either an 8-layer respin (more
   independent escape layers, no via-in-pad needed) or a premium/HDI fab partner instead of
   the platform's usual shop.
7. **Die orientation is a one-time decision that chassis/edge requirements can override.**
   The quadrant-to-edge recommendation in §4 assumes the front/rear/interior edge map in the
   variants-plan holds. If a downstream chassis constraint forces the LAN9370s or the uplink
   MagJack to the opposite edge from what this study recommends, the SGMII/RGMII runs get
   longer and cross more of the die, eating into the margin computed above — recommend the
   edge assignment be locked against this die-orientation study *before* sheet-02, since
   correcting it after layout starts is expensive.

## Summary for the caller

- **Verdict: 6-layer OK, with conditions** — via-in-pad on a bounded ~35-50-ball set
  (JTAG_SYSCTRL 13 + SGMII 10, both 100% fixed at ring 4-7 with zero shallow option, plus
  MSSIO's ring-3 spillover), and a reserved, geographically-scoped sig area on L4 for those
  two buses. Everything else (both RGMII buses, pin-7 GPIO×8, QSPI/eMMC/I2C/CAN/misc) fits
  at ring ≤ 3 by choice, on L1, with an ordinary staggered dog-bone via — because total
  demand (~87 of 484 balls, ~18%) sits far below any bank's population (182 balls across the
  three signal-choice banks alone).
- **New scope surfaced:** the existing platform Signal netclass (0.22 mm) does not fit a
  0.8 mm-pitch BGA escape channel; this board needs its own finer BGA-fanout netclass
  (~0.10-0.13 mm track/clearance) plus a bounded via-in-pad spec, both new `.kicad_dru` work
  for whoever owns that file.
- **Per-ring demand (full table in §1/§4);** headline: NE 37 / NW 53 / SE 40 balls available
  at ring ≤ 3 across the choice banks, against a baseline choice-demand of ~74.
- **Pin-assignment recommendation:** orient the package so SE (HSIO_BANK0) and NE
  (GPIO_BANK1 majority) face the front edge (module ports/T1 switches), NW (MSSIO + JTAG +
  60% of SGMII) faces the rear/interior (uplink PHY, JTAG/strap header), and SW (mostly
  MSS_DDR, quiet if LIM-only) tucks toward an interior mounting corner.
- **Real risks found, not hypothetical:** MSSIO bank has the least headroom of any bank
  (28/38 committed at baseline before MCX/USB deltas); MCX's sync link cannot actually
  choose "SGMII lane 2" since MC's dual-uplink already consumes both real lanes, forcing the
  LVDS-fabric-pair fallback; USB OTG has no identified ball in the cached map at all; the
  ball map's own 095T-vs-250T provenance gap could make the shallow-ring headroom optimistic
  if the real die bonds out fewer usable balls than the 250T-sourced table assumes.
- **8-layer fallback triggers:** DDR populated instead of LIM-only (dominant trigger); USB
  landing outside the shallow-choice pool; via-in-pad turning out not to be available from
  the chosen fab at reasonable cost/lead time; MCX/MC-Max growth exceeding the margin found
  here once its full population is finalized.
