# Blade-interface fit-check memo (2026-07-04)

Paper half of the owner's condition on adopting the Keystone universal-entry
blade clip config (`output-daughterboard-study-2026-07-04.md` §8.9–§8.10,
config (i)). This is a **datasheet-vs-datasheet compatibility check**, not a
substitute for the physical sample check the study already calls out (gang
mating-force measurement + clip-cluster confirm-soak/thermal-cycle contact-R
trend). That physical gate remains the owner's, unstarted here.

Parts checked, all fetched 2026-07-04 from the manufacturer's own dimensioned
drawing (not marketing copy): Keystone dwg no. 3586 rev D (LCSC-hosted, C238113),
Keystone catalog M55 p.41 "2 IN 1 FUSE HOLDER" + p.53 "FEMALE PC QUICK-FIT
TERMINALS" tables (C352820), TE dwg C=63849 rev F1 (LCSC-hosted, C86469).
Cached at `lib/datasheets/Keystone_3586.pdf`, `Keystone_3557-2.pdf`,
`TE_63849-1.pdf`.

## 1. Accepted tab range (clip side)

Keystone's universal-entry family (3557 top-entry / 3577 bottom-entry / 3586
SMT top-&-side-entry / 3557-2's two "2 in 1" positions) is one clip design
built in several PCB-mount forms. The catalog's own table for CAT NO. 3557
(M55 p.53) states:

> **ACCEPTS TAB: .110 (2.8) to .250 (6.4) × .020 (.50) to .032 (.80)**

i.e. width .110″–.250″ (2.8–6.4 mm), thickness .020″–.032″ (0.51–0.81 mm).
Keystone's own 3586 product page (keyelco.com/product.cfm/product_id/314)
independently states the same width range ("accepts .110″(2.8) to
.250″(6.4) male tabs") for the SMT sibling — the three PCB-mount variants
share the same internal spring-clip geometry, so the same accepted range is
taken to apply to all of 3557 / 3577 / 3586 / 3557-2's two positions. This is
a **family-level inference**, not a per-P/N re-measurement of 3586 or
3557-2's own contact spring individually — flagged UNVERIFIED at that
resolution.

## 2. Tab geometry (TE 63849-1)

Per TE dwg C=63849 (sheet A3, rev F1):

- Blade width: **6.35 mm ± 0.08** (.250″ ± .003″)
- Blade thickness: **0.84 / 0.76 mm** (.033″ / .030″ — i.e. a 0.76–0.84 mm band)
- Material: brass; finish tin plate (≥0.00381 mm) over ≥0.00254 mm copper, OR
  tin plate (≥0.00381 mm) over ≥0.00127 mm nickel
- "SUPPLIED IN LOOSE PIECE"

## 3. Verdict: datasheet-compatible, with one tolerance note

**Width — clean match.** 6.35 mm nominal sits exactly at the clip family's
stated upper bound (6.4 mm / .250″); this is by design — the FASTON .250 tab
is the size class the "up to .250" clip rating is written for, not an edge
case.

**Thickness — compatible, but tight at the tab's upper tolerance.** The tab's
nominal/lower band (0.76–0.81 mm) sits inside the clip's stated 0.51–0.81 mm
(.020–.032″) range. The tab's *upper* tolerance limit, 0.84 mm, is **0.04 mm
(~5%) over** the clip's stated 0.80 mm (.032″) max. Quick-fit spring clips of
this class are compliant members with real engagement margin beyond a
catalog's nominal ceiling (the .032″ figure is itself Keystone's *standard*
tab-stock thickness, not a hard mechanical limit), so this is not read as a
blocking incompatibility — but it is exactly the kind of tight-tolerance
condition the owner's physical sample check should specifically exercise:
**measure insertion/extraction force and full seating at tabs drawn from the
high end of the 63849-1 thickness tolerance**, not just a nominal-thickness
sample.

**Material/plating — compatible.** Both sides are tin-finished brass (clip:
tin-nickel plate over brass per Keystone dwg; tab: tin over copper or tin
over nickel per TE dwg). Tin-on-tin at the mating surface avoids a
dissimilar-metal couple; this also matches the repo's general fretting-
corrosion caveat already on record for this config (§8.9(c) of the study) —
tin-tin friction joints are the classic fretting wear-out mode under thermal
cycling, which is why the study promotes the §5 sense-return monitor to
"recommended" for this config. That recommendation is reaffirmed here.

## 4. Seating depth / insertion

Keystone's 3586 drawing gives the clip's own body height (.282″/7.16 mm,
±.010″) and top-entry slot opening (.062″/1.57 mm) but does **not** publish a
"tab must insert to depth X" wipe-length figure on the one-page mechanical
dwg fetched. Catalog copy for the family only says the clip "holds fuse
securely, even after multiple insertions" and "accepts most Auto-Blade
Fuses" — no numeric engagement-length spec was found in this pass.
**UNVERIFIED**: full seating depth of a .250×.032 tab in the clip is not
independently confirmed from paper; this is the other half of the owner's
physical check (along with mating force).

## 5. PCB retention and recommended anchor practice at 30 A

- **3586 (SMT, 1 electrical node, 3 solder pads — 2 legs + a support foot):**
  retention is solder-joint-only (no THT press-fit). At 30 A through 2 small
  SMD legs, do not rely on the minimum footprint pad area alone — extend
  copper into a filled pour/plane around and under the pads (matches this
  repo's established practice of routing high-current joints as poured
  copper, not thin traces, e.g. the EPS/PCIe/12VHPWR modules) and ensure the
  reflow profile suits the part's thermal mass. Consider a secondary
  mechanical anchor (chassis screw/bracket) per the study's "friction +
  chassis screws" retention doctrine, since solder alone is carrying both the
  mechanical clip-insertion reaction force and the current.
- **3557-2 (THT, 2 independent clip positions, 4 legs, 1.6 mm drill, 1.40 mm
  legs not specified but Keystone dwg calls the mounting hole .063″/1.6 mm):**
  wave/hand solder into a plated through-hole; catalog language ("maintains
  position during wave soldering") implies the legs are sized for a
  friction-retained placement prior to reflow, not a barbed interference fit.
  Route each leg's hole into the power pour directly — **no thermal-relief
  spokes** on a 30 A joint; a spoked thermal relief is a deliberate
  current bottleneck and defeats the point of using a rated clip.
- **63849-1 (THT tab, barbed shank, press-fit before solder):** TE's drawing
  shows an explicit barb geometry (the .070–.078″/1.78–1.98 mm dia barb
  detail) sized against a **1.40 mm ± 0.05 mm** hole — this is a real
  interference fit for mechanical retention ahead of soldering, which is why
  the footprint's drill was corrected to 1.40 mm (see below); oversizing this
  hole (as the raw EasyEDA/LCSC export did, at 1.6 mm) would defeat the
  press-fit retention that the part is designed around, leaving the joint to
  rely on solder alone during wave/hand assembly.
- **System-level:** the study's promoted §5 sense-return contact-resistance
  monitor is the recommended in-service check for this whole friction-joint
  family — reaffirmed, not re-derived, here.

## 6. Footprint corrections made during vendoring (recorded for traceability)

The as-pulled EasyEDA/LCSC exports were not trusted blindly (this repo has
been burned by exactly this class of error before — see the 45586 connector
row-pitch note in `CLAUDE.md`). Verified against the manufacturer drawings
above and corrected where they disagreed:

| Part | As-exported | Corrected to | Source |
|---|---|---|---|
| Keystone 3557-2, all 4 THT holes | 1.8 mm drill | **1.6 mm** (.063″) | Keystone catalog M55 p.41 |
| TE 63849-1, both THT holes | 1.6 mm drill | **1.40 mm** (⌀.055″ ± .002″) | TE dwg C=63849 |
| Keystone 3586 SMD pad width/pitch | 2.66 mm pads, 4.90 mm center spacing | **unchanged — verified correct** (.105″/2.66 mm pad width and the .260″/6.60 mm outer envelope both match the dwg exactly once the pad height is subtracted) | Keystone dwg 3586 rev D |

Pad *numbering* was also corrected to reflect true electrical topology (not a
dimensional issue, but load-bearing for anyone using these footprints): 3586's
3 SMD pads (2 legs + 1 support/anchor foot) now all carry pad `1` — one
electrical node. 3557-2's 4 THT pads were split `1`/`1`/`2`/`2` — **this part
is Keystone's "2 IN 1" dual-position fuse holder, i.e. it is two independent
clip receptacles in one housing, not a single universal clip** (contrast with
plain 3557/3577, which are single-position). Anyone reaching for "a
universal-entry THT blade clip" and expecting a 1-node part should use 3557 or
3577 instead of 3557-2, or use only one of 3557-2's two positions per node.
63849-1's 2 THT pads were already both numbered `1` as exported (correct — a
FASTON tab is one node with two mechanical feet).

## 7. Open items (owner gate, unchanged from the study)

1. Physical sample: gang mating-force measurement across a cluster of the
   clip's rated joint count, **specifically including tabs at the high end of
   the 63849-1 thickness tolerance** (0.84 mm).
2. Physical sample: clip-cluster confirm-soak + thermal-cycle contact-R trend
   (fretting-corrosion check).
3. Seating/engagement depth is not confirmed from any datasheet fetched in
   this pass — confirm on the physical sample alongside (1).

None of the above are resolved by this memo; they are the paper half only.
