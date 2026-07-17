# Standard-tier board family — exhaustive design sheet (pipeline input)

_Owner ask (2026-07-16): the tester/ENT design-sheet treatment "for all the standard
boards." DERIVED VIEW — canonical: the spec (§2/§6), CLAUDE.md locked decisions, the
per-board READMEs/routing plans, `docs/standard-tier-review/*` (beta line), and the
MEASURED evidence records cited inline. These boards are the ALPHA line (validated
prototypes) — this sheet exists so the BETA revisions and every pipeline re-route obey
the same doctrine the alphas proved, plus the lessons they taught. Working-basis
numbers are tagged **[wb]**. **Pipeline of record: branch `claude/pipeline-consolidation`**
(netclass→DSN carriage, TPC pass-form, solver inventory per
`docs/pipeline-solver-roadmap.md` there) — §F cites its capabilities._

## A. Board census

| Board | State | Notes |
|---|---|---|
| `hubs/hub-standard` | alpha ROUTED + fab snapshot; beta rev2 route waves in flight on pipeline-consolidation (W9 keepout drop, WROOM edge seat) | S3-WROOM, 4 ports |
| `modules/atx-24pin` (rev3 beta) | beta line: INA238 reversion (v1.5.0), blade TB field landed | bulk-5VSB source |
| `modules/eps-8pin` | C6 + §6.13 placed, **ZERO copper — W6 routing pass owed** | 2-cable interposer |
| `modules/pcie-8pin-{2,3}port` | same state as EPS (W6) | 2/3-cable |
| `modules/12vhpwr-standard` | ROUTED + fab snapshot (proto-v1) | 6× per-pin INA240 |
| `modules/output-daughterboards/{atx24,eps,pcie}-out-db` | routed, DRC/ERC-clean, DRAFT (OQ-86 fit gate) | iteration-7 blade boards |

## B. Floorplan doctrine (zones)

**Cable/interposer modules (EPS, PCIe, 24-pin pattern) — the condensed-board doctrine
(proven on the committed boards; regenerators encode it):**
```
[CABLE COLUMN]  per-cable straight axis: J_IN (edge, body OVERHANGS, pads on-board)
                → in-line shunt → J_OUT/TB blade row; +12V/rail copper flows one
                direction down the column; columns never share sense nets (100 mm
                generator pitch lesson).
[SENSE BAND]    INA238 (+ INA181/TLV7011 §6.13 chain) HARD against its shunt's
                INNER edge — shunt oriented HI = upper terminal (corpus rule
                shunt-rotation-hi-upper-terminal; the PCIe kelvin failure class).
[CONTROL CORE]  MCU (C6) + CAN + LDO + flash/USB front end right of the columns;
                RJ-45 + USB-C mouths OUT the right edge.
[BLADE ROW]     TE 63969-1 receptacles (TB*) on the output side, per the ratified
                §2.8 daughterboard architecture; sense-tap TBs on their post-shunt
                nodes.
```
**12VHPWR Standard:** J3 header top-center (mouth overhang), SIX symmetric fanned
per-pin lanes at ~6 mm SENSE pitch (equal-length pairs), each lane: shunt → RC filter
(RFH/RFL 10 Ω + CF 470 nF at the INA) → INA240 (rot 90) → bypass, stacked straight
down; J4 captive-pigtail bottom (rot per the Molex 219116 mouth note); control core
right; NTC TH1 at the shunt row, TH2 ambient-far.
**Hub Standard:** ports left/front (J2-J5 FTP), LED chain + buffer between, front-end
power corner (TPS2121 cascade + hold-up can + LDO), WROOM at its beta edge seat
(antenna keepout DROPPED per W9 — no keepout on any beta board), service/KVM interior.
**Daughterboards (iteration 7):** two-band stack — output field band ABOVE a packed
single tab row at the bottom edge; blades point DOWN past the edge (board floats,
tab reaches); NO mounting holes (retention = clip insertion force, owner ruling).

## C. Per-component placement rules (rule → why → pipeline check)

**Sensing (all modules)**
1. **Shunt orientation: HI = upper terminal** toward its cable's IN side; sense IC on
   the INNER edge. Why: the measured PCIe kelvin_ok=FALSE failure (crossed taps
   strand SENSE on congested copper). Check: kelvin-sense-from-inner-pad +
   `gr02`/route HARD kelvin gate. [practice I.10]
2. **Four-wire Kelvin (§6.8)**: taps off the shunt pad INNER edges, matched pair,
   0.25 mm class, no load current in the sense path; taps sharing the force net are
   drawn as short stubs (netclass floor exempt — DRU precedent). Check: kelvin gate +
   `audit_kelvin_loops` loop-area advisory (pipeline roadmap). [practice I.10]
3. **INA240 input RC (12VHPWR)**: matched Rf ≤10 Ω (TI ceiling — gain/CMRR error
   grows past it), Cdiff at the INA pins, fc ≈17 kHz per §6.1. Check: BOM value lint
   + Analog spacing. [practice I.10]
4. **§6.13 detection chain (EPS/PCIe/beta-24-pin)**: shunt SENSE_HI → INA181A2 →
   TLV7011 → per-cable DET latch; comparator threshold RC (10 k/100 n) at the
   comparator; chain stays inside the sense band. Check: netlist chain assertion
   (generator-verified) + Analog class.
5. **Per-channel sense vs switching/power**: ≥2 mm, no parallel >10 mm — now
   MEASURED by `audit_crosstalk` (aggressor/victim proxy, pipeline roadmap).
   [practice I.3]

**Power path (modules)**
6. **High current = POURS, never traces** (the measured FR lesson: it routes 40 A
   nets at 0.2 mm); pours are laid AFTER route (pour-after-route ordering — pour-
   then-route measurably strands kelvin taps), mirrored F/B on cable boards with
   stitching fields. Check: high-current-pour-integrity + min-pour-cross-section +
   electrothermal gate. [practice I.1, I.2]
7. **Via fields at transitions**: current-split per via counted (0.5/0.9 mm ≈ 2 A
   class); the 12VHPWR FEM finding binds: the J3/J4 **GND barrel funnel is the real
   return constriction** — stitch the barrel fields and both inner GND fills; a
   sustained pin-hog puts the shunt-LO 6-via transition near its ceiling. Check:
   per-via split in `electrothermal_solve` + the 2.5D thermal gate. Evidence:
   12VHPWR FEM probe 2026-06-09 + model-debt fix 2026-06-13. [practice I.1]
8. **Thermal reliefs are FORBIDDEN on high-current joints** (blade tabs, shunt pads,
   power headers): solid (ZONE_CONNECTION_FULL) connects only. Why: MEASURED — eps
   dT 235→141 °C, pcie 117→70 °C when reliefs were removed (thermal-wave1 record).
   Check: netclass-geometry-conformance (CL-25) + thermal gate. [practice I.1]
9. **Thin inner-layer lane corridors**: a through-via's anti-pad SEVERS a lane
   narrower than its keepout diameter (measured `unconnected_items` on atx24-out-db;
   recorded in `route_atx24()`) — no foreign via may land on a thin lane; jog
   descents onto computed mid-gap columns. Check: DRC unconnected + the lane
   comments' assertions.
10. **Mini-Fit Jr power headers**: 87427 pegless — body overhangs the edge, THT
    tails are the retention; EPS pin map GND = pads 1-4 / +12 V = 5-8 (the corrected
    EPS12V standard orientation — regenerator-pinned). Check: CONFORMANCE pin-map
    suite.
11. **Blade interface (output side)**: TE 63969-1 receptacle hole pair runs ALONG
    the blade plane (wall normal, perpendicular to the row) — orientation is
    checker-asserted; pitches 4.2/4.7/5.2 by family; receptacle depth ≤4.0 mm is
    the #1 OQ-86 sample item. Sense-return TBs land on POST-SHUNT nodes (netlist-
    verified pattern TB<cable><idx>). Check: `check_output_daughterboards.py`
    (104-113 OKs incl. clip-fit + keying no-rigid-transform proofs).
12. **Daughterboard keying**: per ordered family pair, NO rigid transform seats one
    family's tab set as a subset of another's (the 1-D signature check FAILED
    measurably; the 2-D bipartite proof is the rule). Check: same checker, teeth
    verified (sabotaged pitch correctly fails).

**Interface + control (all boards)**
13. **RJ-45 FTP jack**: platform Kinghelm land; SH1/SH2 → GND both ends (§2.1
    both-end shielding ruling); DETECT 2.2 kΩ (Standard code) + PESD5V0S1BA at
    pin 8; pin 7 NC (consumer). Check: detect-resistor-code + CONFORMANCE pin table.
    [practice I.9]
14. **TJA1051T/3** at jack pins 3/6; no module termination (Hub split-term only).
    NOTE the pipeline's impedance audit MEASURED platform CAN at **91–105 Ω vs the
    120 Ω target** — fine at 500 k, but the 1 Mbps option's SI bench must see this
    number first (roadmap finding). Check: `audit_impedance` advisory. [practice I.8]
15. **USB 2.0 front end**: 90 Ω pair (audit-validated 91.3 Ω on the committed
    stackup), USBLC6 at the connector, CC 5.1 k pulldowns, VBUS ORing Schottky.
    Check: USB class gate + audit. [practice I.7]
16. **LED chain (Hub)**: SK6812 data buffered to 5 V (AHCT gate as buffer), 330 Ω
    series at the first LED, chain order matches refdes; aggregate current is a
    FIRMWARE cap (OQ-2) — layout only guarantees the 5 V copper class. Check: power
    class widths.
17. **Hub front end**: TPS2121 cascade per §2.9 (mux soft-start does inrush — no
    discrete inrush R), hold-up can clearance + polarity silk, supervisor at the
    LDO, rail-sense dividers to their ADC pins. Check: netlist assertions
    (hand-maintained board — no regeneration; gen script is guarded).
18. **24-pin specials**: J1.1 (RJ-45 VCC) is NO-CONNECT (locked §2.7 — parallel
    bulk-path hazard); MAIN_5V tap sits DOWNSTREAM of the 5 V shunt (OQ-13
    accounting); 5VSB shunt = 25 mΩ. Check: CONFORMANCE + netlist assertion.
19. **Fiducials**: 3× 1 mm/2 mm mask, board_only, corners + diagonal (12VHPWR
    precedent); values readable on F.SilkS (generator writes Value→silk). Check:
    DFM stage. [practice I.11]

## D. Routing standards (netclass table — the committed .kicad_pro precedents)

| Class | Nets | Width / rules |
|---|---|---|
| Power12V | per-cable force nets (/SENSEC*, /SENSEP*) | 2.5 mm trace floor where traced; POURS carry the real current; via 0.9/0.5; clearance 0.2 (VSSOP-10 entry precedent); no netclass floor on shared force+sense stubs (DRU exemption) |
| GND | GND | 0.5 mm, via 0.9/0.5, planes + stitching |
| Power | +3V3/+5VSB/VBUS | 0.5 mm, via 0.8/0.4; Hub trunk nets (+5VSB, /5VSB_RAW, /MAIN_5V_RAW, /+5V_HOLD) ≥1.0 mm (netclass-pattern-fix lesson: slash-prefixed patterns or the rule never fires) |
| Sense | IN*_P/N, ISENSE*, VRAIL_DIV | 0.25 mm matched pairs, via 0.6/0.3 |
| CAN | CAN_H/L | 0.25 mm coupled (measured 91–105 Ω — see §C.14) |
| USB | USB_D_P/N | 90 Ω diff, gap per stackup (validated 91.3 Ω) |
| Signal | I2C/THRESH/DET/EN/CC | 0.22 mm |
| SYNC7 | — | consumer pin-7 NC; class reserved (ENT sheet owns it) |

DRU seeds: pour-integrity, min-pour-cross-section, kelvin-from-inner-pad ARMED;
Kelvin-stub track exemption on shared force+sense nets; CL-25 classes incl.
netclass-geometry-conformance; 12VHPWR production note: enlarge the 12 V F↔B
transition vias 0.6/0.3 → 0.9/0.5 at the production rev (proto erratum, README).

## E. Stackup per board (the owner's 2026-06-14 board-class ruling)

| Board class | Stackup |
|---|---|
| Cable boards (EPS/PCIe/12VHPWR + out-dbs) | 4L 1.6 mm, 2 oz outer/1 oz inner; **12 V on BOTH outers (mirrored pours), GND on BOTH inners**; band-crossing foreign signals stagger F.Cu vs B.Cu so the un-cut mirror always carries |
| 24-pin | 4L; ONE inner solid GND + ONE inner POWER-ROUTING layer (multi-rail exception) |
| Hub Standard | 4L; ONE inner solid GND + ONE inner SIGNAL layer |

## F. Pipeline gates (branch `claude/pipeline-consolidation` capabilities — cite the roadmap)

1. HARD gates: kelvin_ok + diffpair_ok (cec_score) — never judged deterministically
   alone; manager-tier review per the CLAUDE.md routing rule.
2. ERC 0 / DRC severity-error 0; DRAFT discipline; intake gate (cec_router).
3. **Route form: TPC pass-form** (`two_pass_corridor` — lock kelvin/pairs as
   protect, rip foreign, notched reservation, re-pour; measured foreign-through-pour
   48→0) + **netclass carriage into the FR DSN** (405ba7c9) — the "FR ignores
   widths" era rule (§C.6) still stands for high current: pours carry amps.
4. Solvers: 2.5D thermal GATING (mirage guard armed; known nondeterminism defect —
   double-solve confirm until root-caused); analytic electrothermal (serial min-cut,
   per-via split — the 2026-06-13 model-debt fixes are load-bearing); ADVISORY:
   `audit_impedance` (Hammerstad-Jensen), `audit_kelvin_loops`, `audit_crosstalk`;
   GND-fanout synthesizer (impedance-reducing only); SPICE pilot (`cec_spice`,
   ngspice) for hold-up/front-end curves — SPICE provenance is always labeled
   (persist-contract discipline).
5. SB-08 golden before merging scripts/** changes; CL-25 audit classes + CL-11
   golden fixtures; corpus lint.
6. Known-open beta items this sheet inherits (not new): W6 EPS/PCIe routing pass
   (zero copper today), Hub J_USB hole_clearance CI red (D-11 owner decision),
   24-pin J_SIG 1×4 rework deferred (D.6), OQ-86 fit gate on the out-dbs.

## G. Mechanical / assembly

- Connector bodies may OVERHANG their edge; pads stay on-board (87427/RJ-45/USB-C
  precedents). Blade assembly drops vertically; board floats 12.41 mm at 1 mm tip
  clearance (iteration-7 numbers); gang-insertion is a FEATURE (owner mating-force
  ruling) — chassis strain relief on the cable side (OQ-87 numbers owed).
- §6.6 enclosed-product thermal: TIM under EPS/PCIe/12VHPWR shunt rows + M3 mounts
  as chassis couplings (the 12VHPWR pass condition: maxT 72.95 °C WITH case cooling
  vs 151 °C still-air — the case is part of the design).
- JLC assembly: Basic/Extended lines per BOM; Mini-Fit Jr + 12V-2x6 consigned THT;
  silk values on F.SilkS; cosmetic silk hits documented per board README, never
  silently waived.

## H. Per-board deltas + known-open

- **Hub Standard**: hand-maintained schematic (generator GUARDED); beta = W9 keepout
  drop + rev2 route waves (pipeline branch); supercap stays OUT at Standard (study
  verdict: DNP boost ladder remains the Standard hedge).
- **24-pin rev3 (beta)**: INA238 ×4 (v1.5.0 reversion), TB field per iteration 7
  (TB10 /SENSE3V3_LO etc.), Mini-Fit Jr PSU side is CORRECT (§2.8), rev2 erratum
  (J1.1 parallel path) documented for prototypes.
- **EPS/PCIe**: W6 full routing pass through the pipeline = the open deliverable;
  netclasses/.kicad_dru seeding per §D before route.
- **12VHPWR Standard**: production-rev items (via enlarge, mirror-pour margin, OQ-11
  MPN write-in) per its README; sideband taps R10-13 land per §6.1.
- **out-dbs**: fit gate (OQ-86) then fab; per-family README keying notes binding.

## I. Industry best practices — routing + placement, with citations

**I.1 Current capacity + thermal — IPC-2152** (the platform's corpus Class-A anchor;
supersedes IPC-2221 charts for current). Applied: §C.6-8 pour/via doctrine; the
electrothermal solver's k-params. Internal evidence: the AM-04 anchor set + the
segment-sum→min-cut model-debt fix (2026-06-13) — the solver now measures the
BOTTLENECK cut, which is what IPC data actually describes.
**I.2 Copper pours + returns — Ott, *Electromagnetic Compatibility Engineering*
(Wiley 2009) ch. 16-17.** Return current flows under its trace; splits force loops.
Applied: both-inners-GND on cable boards, stagger-the-mirror rule, §C.5 spacing.
**I.3 Crosstalk spacing — Ott ch. 4/16 + Bogatin, *Signal and Power Integrity —
Simplified* (3rd ed.).** The ≥2 mm/no-long-parallel rules are geometry proxies —
now measured by `audit_crosstalk` instead of trusted.
**I.4 Controlled impedance — IPC-2141A.** USB/CAN/Sense class geometry; the
pipeline's Hammerstad-Jensen audit implements it closed-form (USB validated +1.4 %;
CAN 91-105 Ω finding logged).
**I.5 Land patterns + courtyards — IPC-7351B.** The generators' courtyard/DRC
discipline; rotated-pad angle normalization (CLAUDE.md placement rules).
**I.6 Via protection — IPC-4761.** Type VII only where via-in-pad is unavoidable
(not used on Standard boards today; daughterboard lane vias are open through-vias by
design).
**I.7 USB 2.0 — USB-IF spec ch. 7** (90 Ω ±15 %, no series ferrites on D± — §6.14
platform posture).
**I.8 CAN — TI SLLA270** (stub/topology discipline; split termination at ONE point —
the Hub — is the platform lock §3.1).
**I.9 ESD placement — IEC 61000-4-2 + vendor (Nexperia PESD) datasheet guidance**:
clamp at the CONNECTOR pin with minimal stub — the platform pin-8 pattern (§2.4
locked, D2-D5 precedent).
**I.10 Current-sense layout — TI INA238/INA228/INA240 datasheet layout sections**
(Kelvin from inner pads, matched sense traces, filter at the amplifier, Rf ≤10 Ω on
INA240). Applied §C.1-4; mechanized as the kelvin checkers + loop-area audit.
**I.11 Fiducials + assembly DFM — IPC-7351B/JLCPCB assembly rules** (3-point
fiducials, courtyard clearances, Basic-part preference for cost/availability — the
platform sourcing discipline).
**I.12 Pass-form routing — industry pass-order practice (TI/ADI/Cadence/Altium-class
guidance, synthesized in `docs/pass-form-plan.md` on the pipeline branch):** route
the precision/critical nets first with locked copper, fill bulk after — implemented
as TPC; this sheet's §C.1/§C.6 ordering rules are its per-net expression.


## K. Assembly-grade protocols (owner ask 2026-07-17: self-audit + industry standards)

**K.0 SELF-AUDIT RECORD (what this sheet was missing or thin on, found
2026-07-17):** (a) fiducials had one thin line (§C.19) with no clear-zone,
asymmetry, or local-fiducial doctrine; (b) NO silkscreen protocol — while
every routed board carries "documented cosmetic silk hits," i.e. the gap
had visible symptoms; (c) placement rules were per-component with no
industry placement ORDER/grid/orientation protocol; (d) grounding was
current-centric (§C.7) with no RF stitching pitch or edge-band ruling;
(e) decoupling existed as generator behavior (auto_cluster) with no
geometry protocol; (f) no consolidated DFM/fabbability floor list;
(g) the Hub's large SMD electrolytic had only "clearance + polarity
silk" (§C.17) — no reflow/edge/lifetime/AOI rules; (h) CONFLICT found:
the generator unconditionally writes Value→silk (§C.19) which IS the
documented cosmetic-silk-hit source on dense clusters — K.3 supersedes
with a conditional policy (FOLLOWUPS: regenerator change at beta).

**K.1 Placement protocol (order + grid).** Place in this order: (1) FIXED
mechanical — connectors at ruled edges (mouth-overhang rules §G), mounts,
fiducials; (2) CRITICAL analog cells as rigid stamps (shunt+sense §C.1-4);
(3) MCU/core; (4) DECOUPLING at pins (before any general passive); (5)
bulk/filters at rail entries; (6) remaining passives clustered to owners
(auto_cluster ownership = the mechanized form); (7) silk/fiducial pass.
Grid: 0.5 mm coarse / 0.25 mm fine; passives aligned in rows/columns
(paste + AOI); courtyard-to-courtyard ≥0.25 mm (JLC assembly floor 0.2);
consigned/hand-solder THT gets ≥2 mm iron access; parts >5 mm tall keep
≥1.5 mm from fine-pitch neighbors (AOI shadow cone); NOTHING
flex-sensitive within 3 mm of a depanel line, and MLCCs near any
board/depanel edge orient their long axis PARALLEL to that edge ≥1 mm in
(flex-crack rule, practice I.15). Check: courtyard DRC + a
cap-to-edge-orientation lint [wb new corpus row].

**K.2 Rotation/orientation.** Library parts follow IPC-7351B
zero-orientation; boards use 0/90/180/270 ONLY (no odd angles on
Standard). POLARIZED parts (electrolytics, tants, diodes where routing
allows) share ONE polarity direction per axis per board — AOI operators
and rework techs read a board, not a part. ICs keep pin-1 in ≤2
quadrants per board. Rotated footprints normalize pad-angle fields
(CLAUDE.md rule). JLC CPL rotation corrections are TRACKED per footprint
in each fab README — the platform has eaten easyeda-export rotation
mismatches before; the correction table is part of the board, not tribal
memory. Check: CPL-rotation table presence at fab-snapshot lint [wb].

**K.3 Silkscreen protocol (dense areas).** Refdes ALWAYS: ≥0.8 mm text,
≥0.15 mm stroke (JLC legibility floor class), never over pads, bare
copper, or fiducial clear zones (IPC-A-610 legibility). In DENSE
clusters, drop VALUES FIRST — values live on F.Fab + the assembly
drawing; refdes moves adjacent-outside the cluster, reading in ≤2
orientations per board. NEVER dropped, ever: polarity marks, pin-1
indicators, connector pin labels, warning marks — and polarity/pin-1
marking must extend BEYOND the part outline (marking under a can or
body is invisible after assembly). DNP parts get the platform DNP silk
convention. This SUPERSEDES the unconditional Value→silk generator
behavior (K.0.h): Value renders on silk only where it fits un-clipped —
fit-tested at generation, not documented-as-cosmetic after. Check:
silk-over-pad DRC + a value-fit test in the regenerators [FOLLOWUPS].

**K.4 Fiducial protocol.** 3 global fiducials per assembled side: 1.0 mm
copper dot, 2.0 mm mask opening, ≥3 mm copper/silk CLEAR zone, placed
ASYMMETRICALLY (L-arrangement — three corners, never four, never
symmetric: symmetry leaves a 180° vision ambiguity), ≥5 mm from board
edges, never under parts. Double-sided assembly (none today on
Standard) would carry 3 per side. Panelized fab adds 3 PANEL fiducials
on the rails. LOCAL fiducial pair recommended beside ≤0.5 mm-pitch
fields — our VSSOP-10 (0.5 mm) sits exactly at the boundary: JLC does
not require it; beta cable boards ADD one local fiducial at the INA
field where room allows [wb]. The 12VHPWR precedent (FID1 TR / FID2 BR
/ FID3 lower-center) already satisfies the asymmetry rule — now it is a
rule, not a precedent. Check: DFM stage fiducial assertions (count,
clear zone, asymmetry) [wb new].

**K.5 Decoupling protocol.** Per-pin allocation, smallest-C CLOSEST:
100 nF 0402 within ~1.5 mm pad-to-pad of its pin; connection order is
PAD → CAP → VIA (never pin → via → cap — the via steals the loop);
TWO vias to the plane per cap where room (shared vias between caps
FORBIDDEN); LOOP AREA is the metric (Ott ch. 11 / Bogatin PDN: above
self-resonance the loop inductance IS the capacitor). Bulk caps at rail
entries; one bulk per rail per board minimum. The auto_cluster
ownership engine implements WHO owns WHOM; this protocol binds the
GEOMETRY. Check: decoupler-adjacency lint (cap-to-pin distance per
class) [wb new corpus row].

**K.6 Grounding arrays, stitching, and the edge-band RULING.** Stitching
grid: ≤10 mm general via grid tying outer GND copper to the inner
plane(s); ≤5 mm along the board PERIMETER and around any plane slot;
every connector shield tab (SH1/SH2) gets ≥2 vias within 2 mm (the
λ/20 basis at our fastest Standard content lands near 7 mm — 5 mm
perimeter / 10 mm field satisfies it with margin, practice I.2/I.3).
EDGE BAND RULING (the owner's question, answered per board class):
**Hub Standard: YES** — perimeter GND band ≥0.5 mm on both outers,
stitched ≤5 mm, tied to all four M3 chassis pads AND the four jacks'
SH tabs (rationale: four cable entries + the chassis bond + handling
ESD; the band contains inner-plane edge fringe and gives the FTP
shields one low-inductance ring). **Cable modules: NO** — their outers
are 12 V pour real estate (a band would cost §C.6 cross-section) and
their inner GND PAIR is already the outermost inner copper on both
sides = the edge fringe is GND-to-GND; instead: inner-plane edge
setback ≥0.3 mm + the ≤5 mm perimeter stitching between the two GND
inners where the pours allow. **24-pin: stitch-only** (one GND inner +
one power-routing inner leaves no clean band budget); **out-dbs: no**
(passive slabs). Check: stitching-pitch audit + band-presence assertion
on the Hub beta [wb new].

**K.7 DFM / fabbability floors (fab of record: JLCPCB; design floors
deliberately above capability floors).** Trace/space: capability 0.09;
DESIGN floor 0.127 signal (we run ≥0.22). Drill: capability 0.2; design
≥0.3. Annular: ≥0.15 (we run 0.2+). Copper-to-edge ≥0.3 mm. Mask web
≥0.2 mm else gang the opening. Teardrops ON for THT-heavy boards
(KiCad 10 native) [wb pipeline flag]. No acute copper junctions <30°
(acid-trap class). STENCIL: 1:1 apertures except pads >2 mm² get
60–80 % windowpane (shunt pads, e-cap pads, blade tabs — anti-bead,
anti-float); 0402 anti-tombstone: both terminals see BALANCED thermal
copper (a 0402 with one terminal in pour gets symmetric entry — never
a relief exception conflict, §C.8 governs only high-current joints and
no 0402 is one). Via tenting: tent signal vias; LEAVE OPEN thermal/
current fields (§C.7). Copper balance: the cable boards' mirrored pours
already balance warp; oddform boards check layer balance at fab review.
Panelization: V-cut for rectangular boards, mouse-bite for notched
outlines (daughterboards); keep-away 1 mm from V-cut / 2 mm tooling
holes; the K.1 MLCC-parallel rule binds along depanel lines.
Single-side SMT assembly stays the Standard-tier default — do not
migrate parts to B side without a cost/AOI review. Check: DFM stage +
fab-README capability table per snapshot.

**K.8 Large SMD electrolytic bulk caps (the Hub C1 class — Ymin VKMI
4700 µF/16 V V-chip; any future V-chip ≥10 mm can).** (1) LAND: vendor
drawing exactly — the plastic base pads carry the mechanical load; no
"improved" hand edits. (2) REFLOW: large V-chip cans are
reflow-limited — vendor profile governs (typ. peak ≤250 °C, bounded
time-above-liquidus, commonly rated ONE pass): board schedules
single-pass reflow; rework near the can is hand/selective only [wb:
pull the exact Ymin VKM profile at the beta BOM pass]. (3) PLACEMENT:
≥5 mm from any board edge, ≥3 mm from any V-cut (base-weld flex),
polarity silk extending beyond the can (K.3), polarity direction
uniform with the board's polar axis (K.2). (4) LIFETIME: electrolyte
is Arrhenius — every 10 °C cooler ≈ doubles life; place ≥10 mm from
the LDO/WROOM hot zone and OUT of enclosed-case hot pockets; the §6.6
enclosed thermal model tags C1's local ambient explicitly [wb thermal
gate tag]. (5) MECHANICAL: multi-gram can — adhesive dot is the
shipping-shock option, decided at proto shake test [wb]. (6) AOI: a
~21 mm can shadows — fine-pitch parts stay ≥2 mm outside its
inspection cone or camera-side. (7) ENCLOSURE: ≥2 mm clearance above
the scored (vent) end — never pot or press the vent. (8) SOURCING:
confirm reel/tray packaging + the JLC large-nozzle line at order.
Check: edge/V-cut distance lint + thermal-tag presence [wb new].

**Citations added for K (extends §I):**
**I.13 IPC-A-610** (acceptability: silk legibility, polarity marking
visibility) — K.3's floor. **I.14 IPC-CM-770E + J-STD-001** (component
mounting + soldering process classes) — K.1/K.7 process basis.
**I.15 MLCC flex-crack vendor guidance (Murata/KEMET app-note class)** —
the K.1/K.7 parallel-to-edge + depanel keep-away rules. **I.16 SMD
aluminum-electrolytic reflow + lifetime — vendor datasheet/app-note
class (Ymin VKM series spec; Würth/Panasonic eiCap reflow guidance;
Arrhenius 10-°C rule)** — K.8. **I.17 JLCPCB published capability pages**
(the fab-of-record floors in K.7) + **IPC-7351B zero-orientation** (K.2).

## J. Open items on this sheet

1. Every **[wb]** + the §F.6 inherited open list (W6, D-11, J_SIG, OQ-86/87).
2. CAN 91-105 Ω vs 120 Ω: bench relevance only at the 1 Mbps option — carry to that
   SI bench gate (roadmap finding).
3. 2.5D thermal nondeterminism root-cause (pipeline FOLLOWUPS) — until then,
   double-solve confirm stays mandatory on gating runs.
4. This sheet lives on the firmware/tester branch; the pipeline of record is
   `claude/pipeline-consolidation` — reconcile at the next merge (FOLLOWUPS).
5. OQ-11 shunt MPN write-ins on EPS/PCIe BOMs (W2) before their fab snapshots.
6. K-section mechanization [wb set]: value-fit silk test + CPL-rotation table lint
   + decoupler-adjacency lint + fiducial assertions + stitching/band audit +
   e-cap edge/thermal-tag lint (new corpus rows); Hub beta picks up the K.6
   perimeter band at its rev2 layout wave; local fiducial on beta cable boards.
7. C1 reflow-profile pull (Ymin VKM) + adhesive-dot shake decision at proto (K.8).
