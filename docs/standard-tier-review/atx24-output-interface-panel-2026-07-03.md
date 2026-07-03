# 24-pin output-interface — design-panel record (2026-07-03)

_Trigger: owner rejected the long-captive-stub recommendation ("stub + a giant extension you
bought = cram"). Method: 5 independent champions (long stub / short stub / male+F-F / compact
proprietary / wildcard) → 3 adversarial lenses (case-geometry, reliability, product-support) →
scored synthesis vs the owner's ranked values (space ≻ quality ≻ openness ≻ revenue ≻ cost).
9 agents, all completed. This file is the verbatim synthesis; feeds D-5/D-5a._

## Scored matrix (1–5; weights: bulk ×6, quality ×5, openness ×4, revenue ×3, board-space ×2, risk ×4)

| Option | Bulk (both modes) | Quality / mated pairs | Openness | Accessory rev. | Board space | Risk | **Wtd /120** |
|---|---|---|---|---|---|---|---|
| **B** short stub (corrected → 12 cm) | 4 | 5 (2 pairs) | 5 | 3 | 5 | 3 | **100** |
| E configured/build-to-order stub | 4 | 5 (2) | 4 | 5 | 5 | 1 | 94 |
| A long stub (~25 cm) | 3 | 5 (2) | 5 | 3 | 5 | 2 | 90 |
| **C** male header + F-F (locked §2.8 incumbent) | 4 | 2 (3 pairs) | 3 | 5 | 3 | 4 | 83 |
| D Micro-Fit proprietary + pigtails | 4 | 1 | 2 | 4 | 4 | 1 | 61 |

**Kills from the adversarial pass:** D is DEAD — Micro-Fit 3.0 derates to ~3–3.5 A/ckt at 24
circuits (below the 6 A ATX ceiling), 43030 terminals cap at 20 AWG, no real 24-ckt alternative.
E's value is real but execution-killed (order-time length unknowable; per-order hand-soldered
high-current joints have no AOI; build-to-order can't hold a retail shelf) — survives only as
B's optional sleeved-stub variant built by the shop. A loses to B (fixed-long; wrong length =
whole-module exchange). C holds but is worst on the owner's #2 value: 3 mated pairs, and the
extra pair is UNMONITORED — the INA228s sense upstream of J4, so "the module monitors its own
extra joint" is circuit-false.

## Recommendation — Form B, corrected parameters

Soldered captive FEMALE stub, alpha wire-row construction, no board output connector:
- **Length 12 cm nominal (10–15 band)** — the refutes killed the 4–6 cm idea, not the
  architecture: the real behind-tray path needs ~8 cm fold-arc + plug body + strain-relief
  straight; 4 cm cannot reach, or seats the header under permanent side-load. 12 cm reaches
  from at/near the grommet; at-header direct leaves only ~4 cm slack.
- **Termination:** Molex 5557 24-ckt female + **5556 HCS (~9 A) terminals mandatory** on
  12V/5V/COM; 16 AWG heavy rails, 18 AWG rest.
- **Strain relief:** potted/clamped bar over the solder row, qualified to a WRITTEN spec
  (≥90 N pull, ≥500-cycle flex) — the one production upgrade the alpha lacks.
- Input unchanged (90° male Mini-Fit Jr 5569). Single black SKU; white/sleeved stub variants
  optional via the shop.

**Why this answers the cram objection:** the owner rejected concatenation in the SHOW chamber.
B defeats it twice: (a) direct users see ~zero visible cable (12 cm lives at/behind the header);
(b) extension users mate the extension to the stub BEHIND THE TRAY — only the pretty run enters
the chamber; the junction and surplus hide in the 20–25 mm channel. And B holds the interposer
minimum of 2 mated pairs vs C's 3.

## Runner-up and the flip

**C is the runner-up AND the currently-locked §2.8 form** — choosing B requires a §2.8 spec
revision (two male headers + F-F cable → one male header + soldered female stub). **The one
flip scenario:** if the real customer mix skews behind-tray/sleeved-enthusiast, or the owner
weights guaranteed accessory revenue + $10 cable-swap serviceability + all-machine-THT build
above mated-pair count and the stock-look chamber — C wins and avoids unwinding the lock.
(If C: ship 15 AND 30 cm in-box, color-key the identical headers, mandate HCS terminals,
publish the F-F spec to seed third-party supply, drop the false telemetry claim.)

## Owner bench questions (blocking items marked)

1. **[BLOCKING] Strain-relief gate:** pull/flex/thermal-cycle the 12 cm stub at minimum bend
   radius with a heavy sleeved-extension cantilever load — the alpha solder row must survive
   with the production bar. Lock only on pass.
2. Terminal grade: confirm HCS 5556 clears 6 A/pin all-energized at ≤30 °C rise.
3. Case-fit survey: measure grommet-to-header on 6–8 reference cases to fix the 12 cm nominal
   + publish the compatibility note.
4. Customer-mix call (the B↔C flip): behind-tray/sleeved share vs black-and-done — the shop's
   sales data answers this.
5. Authorize the §2.8 spec revision if B is chosen.

---

## STATUS: OPEN — owner review (2026-07-03, post-panel)

The owner reviewed the matrix and is **not satisfied with any option as-is**; the decision is
LEFT OPEN. His recorded lean (not a ruling):
- **24-pin: VERY SHORT stub pigtail + extension bundled OPTIONALLY in the ORDER SYSTEM** (an
  order-time add-on, not a retail-shelf dependency — this materially weakens the panel's
  product-support objection to short-stub forms, since the extension ships in the same box when
  chosen). What the lean leaves live: the panel's case-geometry finding that a very short stub
  forces the module body to the header in direct mode and cannot make a behind-tray run — the
  bench case-fit survey (question 3) and the strain-relief gate (question 1) are what resolve
  whether "very short" works or the length creeps toward the 10–15 band.
- **12VHPWR: direct soldered pigtail CONFIRMED** (this is already the locked §2.8 form — the
  owner independently re-derived it from CONTACT-DEGRADATION concern on the melt-prone
  connector: no detachable junction in that power path, period). **NEW: white AND black pigtail
  VARIANTS as SKUs** — color must live in the captive assembly since no detachable aesthetic
  layer is possible there. Feeds D-7's pigtail spec (length/gauge/strain relief + now
  color/sleeving) and the SKU list.

## OWNER GROUND TRUTH + new option (2026-07-03, later same day)

- **Right-angle PCB-mount female 24-pin: DOES NOT EXIST** — owner has exhaustively hunted;
  only VERTICAL PCB-mount females exist. (Overrides any investigator claim to the contrary;
  the parts workflow's RA hunt is moot, its vertical-part catalog stays useful.)
- A vertical female directly on the main board is Z-prohibited (~35mm header+plug stack vs the
  20–25mm channel).
- **NEW OPTION (F): perpendicular daughtercard** — vertical female on a small PCB standing
  edge-on (the modular-PSU output-board pattern) = a manufactured 90° female. Interboard joint =
  edge-soldered through-slot tabs/castellations sized for rail currents (solder, not 24 hand
  crimps → machine-assemblable, AOI-able). Adds: tiny PCB + vertical female part. Deletes:
  24 crimped wires + housing loading + potted strain bar. Open engineering question: anchoring
  the plug mating force (slot-tab-into-main-board + foot). Candidate to beat BOTH the pigtail
  assembly (labor at volume) and the stub forms — evaluate at the D-5 respin alongside the
  owner's lean.

## Option F provenance update (owner, 2026-07-03, later)

The vertical PCB-mount female the owner's hunt found is an **unofficial Chinese DIY part**
(AliExpress-class channels): no MPN, no footprint, no spec sheet, no lot control. Under the
quality-first principle this is disqualifying for a sellable consumer power product (unknown
contact alloy/plating/temp-rise/housing flammability — on the melt-anxiety product line).
Decisive provenance contrast: the owner's crimp PIGTAIL assembly is built entirely from
genuine specified components (Molex 5557 housing + 5556 HCS 9A terminals + spec'd wire) —
the only custom element is labor. Realistic female-out hardware menu now:
1. **Crimp assembly** (interim/possibly permanent): full provenance today; weaknesses =
   hand labor at volume + no-AOI solder row (mitigated by the written strain-relief spec).
2. **COMMISSION the part** (production endgame if D-5 confirms female-out): tool a proper
   PCB-mount female (vertical for the daughtercard, or the right-angle Molex never made —
   the owner's original ideal, custom-made) at a connector house with real spec + lot
   control; plausibly low-$k tooling amortized over the MANDATORY module's volume.
3. **Batch-qualify the DIY part**: bench-derive a spec + incoming inspection; permanent
   supply fragility + silent-change re-qual risk — shop prototypes only, not the BOM.
Recommendation on record: 1 now, 2 as endgame; 3 never for the sellable BOM.
