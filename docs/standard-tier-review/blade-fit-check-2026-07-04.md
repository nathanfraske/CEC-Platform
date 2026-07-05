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

---

## Addendum, 2026-07-05: connector-form change — TE 63849-1 → TE 63951-1 (right-angle/flat)

**Per-CLAUDE.md-convention dated addendum — the text above (Sec.1–7) is left
unedited (no-silent-rewrite); this section is the new record.** Same-day
context: the owner ruled earlier on 2026-07-05 that the daughterboards
should stand perpendicular to the main board with the (then-vendored)
TE 63849-1 tab pointing its blade OUT of the board's face, side-entering the
Keystone clip — that state is what Sec.1–7 above and the boards' first
2026-07-05 revision describe. **Later the same day the owner refined this
further**: the blade should instead be an **IN-PLANE FLAT tab** — "so the
blade can come out at a 90" — hanging below the board's own bottom edge, in
the standing board's own plane, so the whole daughterboard **drops
vertically** into the clip's **top-entry** slot, rather than sliding in
horizontally from the side. The owner uploaded **TE 1217061-1** (a
.187-series FASTON flat PCB tab; TE dwg C=1217061, App Spec 114-2115) as the
worked example of the target geometry, cached at
`lib/datasheets/TE_1217061-1_FASTON_187_flat_PCB_tab.pdf`.

### A.1 Why a NEW part, not just a re-orientation of 63849-1

63849-1 is confirmed (independently, both from its own TE drawing C=63849
and from three separate distributor listings — Future Electronics,
RS Components, Amazon/TE catalog copy) to be a **"straight" mount-style**
tab: its blade is co-axial with the leg-insertion axis (a one-piece straight
stamping, per TE dwg C=63849's own profile view), so it stands perpendicular
to the PCB once soldered — it cannot simply be rotated in the footprint to
become a flat, in-plane tab; the mechanical part itself is the wrong shape.
1217061-1's own drawing (dwg C=1217061, "TAB, FASTON, 4.75 [.187] SERIES")
shows the opposite: its blade continues FLAT off the same plane the two
mounting legs bend down from, at a genuine .187 (4.75 mm) width — the
"right-angle"/flat family Keystone-and-TE terminology distinguishes from
"straight." A NEW part search was required to find the SAME flat geometry
at the .250 (6.35 mm) width class the ratified joint-count math (spec
§2.8 v1.4.0) was sized on — swapping to 1217061-1's own .187 width directly
would under-size every joint and force a recompute (and regrowth) of all
three boards, which this addendum's hunt was explicitly tasked to avoid if
a .250 alternative exists.

### A.2 Hunt record — every .250-class candidate checked, and its style

All confirmed against either TE's own product page/customer drawing or an
authorized distributor's own parametric "Orientation"/"Mount Style" field —
not inferred from marketing copy alone:

| Part | Style (confirmed) | Source |
|---|---|---|
| 63849-1 | Straight | TE dwg C=63849 rev F1; Future Electronics ("straight mount angle") |
| 1217125-1 | Straight | TE product page (te.com/en/product-1217125-1.html) |
| 1217126-1 | Straight | TE product page |
| 1217169-1 | Straight | TE product page (te.com/en/product-1217169-1.html), dwg ENG_CD_1217169_B1 |
| 62409-1 | Straight | Amazon/TE catalog copy ("Straight Non-Insulated PCB Tab Terminal") |
| 2376579-2 / 2376582-2 / 2376591-2 / 2376595-2 | Straight | TE's own 2025 "250 FASTON PCB Tab Terminals" flyer (`te.com/.../250-faston-pcb-tab-terminals-flyer.pdf`) + individual TE product pages — TE's newest (Ni-underplated) .250 tab line is straight-only |
| 63969-1 | N/A — a **receptacle** (female), not a tab | RS Components — wrong gender, disregarded |
| **63951-1** | **Right angle (flat)** | **TE dwg C=63951 rev L2** ("TAB, FASTON, 6.35 [.250] SERIES", App Spec 114-2115) + TE product page ("Terminal Orientation: Right Angle") + RS Components ("Orientation: Angled"; the RS-hosted datasheet file is literally named `Terminal TAB 6.35mm pcb r/a Faston` — "r/a" = right angle) |

**TE 63951-1 is the pick.** Confirmed via its own primary manufacturer
drawing (`lib/datasheets/TE_63951-1.pdf`, TE dwg C=63951 rev L2, cage code
00779, same drafting lineage — JR RUTH / MS FEHER / G PORTA — as both
63849-1 and 1217061-1), not just a distributor's paraphrase:

| Dimension | 1217061-1 (.187, owner's example) | 63849-1 (.250, superseded) | **63951-1 (.250, PICKED)** |
|---|---|---|---|
| Style | Right angle (flat) | Straight | **Right angle (flat)** |
| Blade width | 4.75 mm (.190/.184) | 6.35 mm ± 0.08 | **6.35 mm ± 0.08** |
| Blade thickness | 0.83/0.77 mm | 0.84/0.76 mm | **0.83/0.77 mm** |
| Leg pitch | 5.08 mm ± 0.08 | 5.08 mm ± 0.08 | **5.08 mm ± 0.08 (identical)** |
| PCB hole dia | 1.40 mm ± 0.05 | 1.40 mm ± 0.05 | **1.40 mm ± 0.05 (identical)** |
| Recurring "7.92 mm" figure | present | present | **present** |
| Material/finish | Brass, tin/nickel | Brass, tin/copper or nickel | **Brass, tin over nickel** |
| App Spec | 114-2115 | 114-2115 | **114-2115 (same as both)** |
| Packaging | Reeled | Loose piece | **Reeled** |
| LCSC | not checked (not needed — .250 already found) | C86469 | **C591344, in stock (4,345 units at time of check), $0.099–$0.164/unit by quantity break — within the $0.04–0.30/part class** |

The recurring **7.92 mm** figure (present on all three drawings regardless
of blade width — 4.75/6.35/6.35 mm) is read, as in the original Sec.1–7
memo, as a family-wide dimension tied to the shared 5.08 mm leg/hole
geometry rather than to blade width — now cross-confirmed across a THIRD
independent drawing (63951-1's own), not just the original two. This is why
the boards' existing `TAB_PITCH` values (8.9/8.6/8.2 mm) and the whole
no-subset-seating keying proof carry over **unchanged and re-verified**
(not just assumed) — see `scripts/check_output_daughterboards.py`'s clean
run after the swap.

**Current rating**: no standalone per-tab UL rating exists on TE's own dwg
C=63951 either (same situation as 63849-1) — rating is set by the mating
clip/receptacle, unchanged reasoning from Sec.1 of the original memo above.

### A.3 Keystone 3586 clip — does a VERTICAL TOP-ENTRY drop still fit?

Re-examined Keystone dwg 3586 (already cached, `lib/datasheets/Keystone_3586.pdf`)
specifically for the entry-direction question this addendum adds (Sec.1–7
above already covers width/thickness/plating compatibility, unchanged by
the tab swap since 63951-1 shares 63849-1's blade class):

- The part is named **"SM UNIVERSAL AUTO FUSE CLIP"** — its mechanical
  ancestry is a standard automotive blade-fuse holder, whose native,
  defining use case IS a straight vertical drop (a fuse's flat blade legs
  press straight down into a split spring contact). The drawing's own front
  view shows the slot opening squarely at the **top** (0.062″/1.57 mm wide)
  with the internal fork/spring contact directly beneath it. Top-entry is
  therefore not a secondary or marginal mode for this clip — it is the
  mode its whole design is descended from.
- This reaffirms (does not newly discover) what the original Sec.1 already
  recorded: the family (3557/3577/3586/3557-2) is documented as accepting
  entry "from the top or the side." A vertical drop uses the SAME internal
  spring geometry the side-entry mode already relies on — no new spring
  contact behavior is introduced.
- **Slot width vs. blade thickness**: the 1.57 mm top-slot opening
  comfortably clears the blade's 0.77–0.83 mm thickness (roughly 2×
  clearance) — not a binding constraint either way.
- **Blade travel depth — the one number that changed with this addendum**:
  the clip's own body height is **7.16 mm** (0.282″, Keystone dwg 3586,
  unchanged from Sec.4 above). This daughterboard's own new tab geometry
  gives a blade hang-length of **6.89 mm** past the board's own edge (see
  each board's README "Mating geometry", computed from
  `scripts/gen-output-daughterboard.py`'s `_TAB_FAR_Y`/`_TAB_NEAR_Y`
  constants) — a computed **~0.27 mm shortfall** versus the clip's full
  body height, assuming ZERO standoff between the daughterboard's own edge
  and the main-board clip row. **This is not asserted as a pass or a
  fail** — full engagement/seating depth was already UNVERIFIED from paper
  in Sec.4/Sec.7 above (no manufacturer figure for how far a tab must
  travel into the clip for reliable contact, as opposed to the clip's
  total body height), and that remains true here; this addendum only adds
  the other half of the comparison (the tab's own reach) so the owner's
  physical fit-check has a complete numeric picture. If OQ-87's
  daughterboard standoff spec ends up wanting the two boards' edges further
  apart, that directly subtracts from the 6.89 mm figure — a real
  interaction worth resolving in the SAME physical pass as seating depth,
  not two separate checks.

### A.4 Board state after this addendum

All three families (`atx24-out-db`, `eps-out-db`, `pcie-out-db`) regenerated
on TE 63951-1 via `scripts/gen-output-daughterboard.py <family> --force`:
board sizes essentially unchanged (81.1×16.6 / 52.9×14.6 / 34.5×14.6 mm —
within 0.1 mm of the perpendicular-tab revision, since the new footprint's
near-leg shoulder band was deliberately measured at the same 7.92 mm family
width and a comparable ~2 mm near-side offset). ERC 0 errors, DRC 0 errors/0
unconnected on all three, `check_output_daughterboards.py` fully green
(including the geometric no-subset-seating proof, re-verified against the
new tab's actual coordinates). New library assets:
`cec-vendor:TE_63951-1_FASTON_Tab` /
`cec-Connector_Blade:TE_63951-1_FASTON_Tab_250x032_RA_THT` (LCSC C591344),
vendored from `lib/datasheets/TE_63951-1.pdf`. TE_63849-1 remains vendored
(unreferenced, harmless). Full per-board detail in each family's own
README "Posture"/"Mating geometry"/"Verification"/"Library assets" sections.

### A.5 Open items carried forward (unchanged in kind, restated for this geometry)

1. Physical sample: gang mating-force + full-seating-depth measurement —
   NOW including the vertical-drop direction specifically (Sec.A.3), not
   just the side-entry direction Sec.7 above was scoped to.
2. Physical sample: clip-cluster confirm-soak + thermal-cycle contact-R
   trend (fretting-corrosion check) — unchanged, still open.
3. The 6.89 mm vs. 7.16 mm blade-reach-vs-clip-depth comparison (Sec.A.3) —
   resolve together with OQ-87's standoff spec on the same physical sample.
4. The "8.89 mm" TE attribute this addendum reads as "blade reach from the
   leg row" is a single-datum interpretation (TE's own structured product
   page, cross-checked against the raw drawing's position for that figure
   but not re-derived from an independent third source) — worth a
   confirming glance at TE's raw drawing coordinates before treating 6.89 mm
   as load-bearing beyond a planning-level estimate.

None of the above are resolved by this addendum; they remain the owner's
physical gate, same as Sec.7.
