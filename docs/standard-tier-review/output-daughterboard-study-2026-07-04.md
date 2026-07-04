# Output-connector daughterboard — engineering study (2026-07-04)

**STUDY ONLY — no spec, schematic, board, CLAUDE.md, or owner-queue file touched. Nothing here
is a ratified decision.** Supports the 2026-07-04 owner ruling recorded in
`SYNTHESIS-beta-plan.md` §D-5a: for 24-pin ATX, PCIe 8-pin (2-port, 3-port) and EPS 8-pin, the
output side becomes main board → inter-board connector → passive daughterboard (no components,
thick copper, all pin-mapping) → vertical PCB-mount header (MODDIY-sourced) or soldered pigtail
at a through-hole field, plus a sellable daughterboard+extension assembly. 12VHPWR is out of
scope (stays captive pigtail — melt-prone rationale, already locked). Chassis provides strain
relief. Where a claim could not be confirmed against a primary source it is marked **UNVERIFIED**.

## 1. Per-family current budget (the kill-check)

**Owner design basis (2026-07-04, authoritative — this section is anchored on these numbers, not
on this study's own earlier derivation).** Design around worst case with margin, but keep
**transients as transients and sustained as sustained** — do not fold transient peaks into the
continuous rating; rate the connector continuous for the sustained worst case (with margin), and
treat transients as separately validated thermal excursions.

- **EPS 8-pin:** 4×12V + 4×GND. Max **~13 A continuous per pin** (only brief transients run
  higher). Sustained worst case = 13 A × 4 pins = **~52 A/cable**. Official Intel EPS12V spec is
  336 W (~28 A) per connector; modern boards run **two** EPS connectors specifically because
  next-gen CPUs approach ~600 W and that load must split across two connectors. AWG-dependent —
  CEC's own extensions use 16 AWG.
- **PCIe 8-pin:** same ~13 A/pin theoretical, but only 3×12V pins → **~39 A/cable sustained worst
  case**. Official spec is 150 W (~12.5 A).
- **24-pin ATX:** unchanged from the panel's own convention — anchor on the **6 A/circuit ATX
  bar**, not the OQ-11 shunt figures (used below only as a cross-check).

**Margin policy proposed here (not yet ratified):** size the connector's **continuous** rating to
**≥125 % of the sustained worst case, at ≤30 °C rise** — the 30 °C figure aligns with this repo's
own existing electrothermal-gate convention (see the 12VHPWR thermal re-validation and the
fusing-via discussion elsewhere in `CLAUDE.md`), so a connector qualified at that condition maps
directly onto the same pass/fail language the rest of the platform already uses.

| Family / rail | Sustained worst case (owner basis) | ×1.25 margin target (continuous) | Transient (separate, non-continuous, thermal-mass-absorbed) |
|---|---|---|---|
| EPS, per cable | 52 A | **~65 A** | 75 A (OQ-11 sheet) |
| PCIe, per cable | 39 A | **~49 A** | 60–75 A (OQ-11 sheet) |
| 24-pin +12V (2 pins) | 12 A | 15 A | — |
| 24-pin +5V (5 pins) | 30 A | 37.5 A | — |
| 24-pin +3.3V (4 pins) | 24 A | 30 A | — |
| 24-pin +5VSB (1 pin) | 6 A | 7.5 A | — |
| 24-pin −12V (1 pin) | 6 A | 7.5 A (real draw negligible; not sensed by the 4×INA228 design) | — |

**Cross-check against this repo's own already-committed shunt design current** (OQ-11 sheet,
`docs/enterprise-requirements/ratification/oq-11-shunt-selection-2026-07-02.md`): EPS 55 A (0.5 mΩ,
`CSS2H-2512R-L500F`), PCIe 40 A (same MPN), 24-pin 12V/5V/3.3V 20 A/rail (2 mΩ,
`CSS2H-2512K-2L00F`), 5VSB 3 A (25 mΩ, `WSK2512R0250FEA`). These land within a few amps of the
owner's per-pin-derived sustained figures for EPS/PCIe (55 A vs. the 65 A margin target, 40 A vs.
49 A) — two independently derived numbers converging, a good sign. For 24-pin the two bases
diverge by rail: the shunt's flat 20 A/rail exceeds the margin-adjusted 12V target (15 A) but
falls short of the margin-adjusted 5V (37.5 A) and 3.3V (30 A) targets. **Recommendation: take
the higher of the two, per rail** — the connector must never be sized below what the shunt is
already engineered to pass. Effective per-rail connector target used in §2/§7: **12V 20 A, 5V
37.5 A, 3.3V 30 A, 5VSB 7.5 A**.

**GND return, all families:** the same current returns via GND — budget matching contact count
for the return path, not a thinner "shared" GND (splitting return current across fewer/thinner
contacts than the source concentrates heat asymmetrically). 24-pin's 8 physical GND pins already
carry a real asymmetry worth flagging: aggregate source current across all rails at the effective
targets above (20+37.5+30+7.5 ≈ 95 A) returning through only 8 GND pins averages ~11.9 A/pin — the
daughterboard's own GND contact allocation should not inherit that asymmetry; size GND contacts to
the same per-contact rating as the source contacts, independent of the legacy 8-pin ATX GND count.

**Transient treatment (kept separate, per the owner's rule):** EPS 75 A and PCIe 60–75 A
transients are non-continuous, thermal-mass-absorbed events at the shunt (OQ-11 sheet). A
connector contact also has real thermal mass, so a contact continuous-rated below the transient
peak can plausibly still ride it out for the sub-second class of excursion this platform is built
to observe — but that is an assumption, not a bench-verified one, and is listed as an open item
in §7.

**Kill-check verdict, restated against these numbers:** every family surveyed in §2 clears the
margin-adjusted continuous targets (65 A EPS, 49 A PCIe, 20–37.5 A per 24-pin rail) with 2–5
contacts on a real board-to-board power-connector family — this is not the Form-D failure mode
(Micro-Fit 3.0 derating to 3–3.5 A/ckt, below even the *un*-margined 6 A ATX floor).

## 2. Inter-board connector candidates

All current ratings below are *manufacturer-published, derated* figures (not raw single-pin
"peak" marketing numbers) where stated; each is cited. "30 °C-rise" is called out explicitly
because it is this repo's own electrothermal gate convention (see e.g. the 12VHPWR thermal
re-validation and the fusing-via discussion in `CLAUDE.md`'s action items — the whole design
culture here targets a 30 °C rise ceiling), so a connector rated at exactly that condition maps
directly onto the repo's existing pass/fail language.

| Candidate | Per-contact derated rating | Contacts for 20 A (24-pin rail) | Contacts for 40 A (PCIe cable) | Contacts for 55 A (EPS cable) | Stack height | Keying/captivation | Indicative cost (100 qty) | Survives 30 °C-rise culture? |
|---|---|---|---|---|---|---|---|---|
| **Samtec mPOWER UMPT/UMPS** (2 mm pitch blade) | 18 A single-contact max; **derates with adjacent loading** — ~12.9–13.2 A at 4 populated contacts, ~8.9–9.8 A at 10, all figures already **20% derated for 30 °C rise to max allowable temp** ([samtec.com/products/umps](https://www.samtec.com/products/umps), [umpt](https://www.samtec.com/products/umpt), datasheet F-224) | 2 (≈26 A) | 4 (≈52 A) | 5 (≈65 A) | Vertical or right-angle, multiple stack heights | UMPT offers **metal side-latching** or plastic-top variants — genuine positive latch available | Single-unit DigiKey ~$4–7/part (UMPS-04/UMPT-04 class); no 100-qty break found — **UNVERIFIED at volume** | Yes — rating is *already stated at* 30 °C rise |
| **Molex EXTreme Ten60Power / Ten60** | 50 A per blade headline; **split-blade terminal rated 30 A at 30 °C T-rise** (search-derived from Molex product-highlight copy; full PS-46436 PDF is image-encoded and did not extract textually — **rating cross-check UNVERIFIED against the primary PDF table**, only the marketing/product-page mirror) | 1 (marginal, no redundancy) / 2 recommended (60 A) | 2 (60 A) | 2 (60 A) | Vertical and right-angle, "hybrid power-and-signal" mixed housings | PCB polarizing pegs, guide modules (1.8–2.4 mm misalignment gatherability), **200 mate/unmate cycle rating** — no explicit screw-lock found, alignment-guide based | Not found in this pass — **UNVERIFIED** | Likely yes (30 A figure explicitly at 30 °C rise) but primary datasheet not confirmed |
| **TE MULTI-BEAM XLE / XL** | Up to 100 A/contact with 4 adjacent contacts; standard configs **80 A high-power contact / 20 A low-power contact**; 6-beam variant to 75 A ([te.com MULTI-BEAM HD/XLE/XL](https://www.te.com/en/products/connectors/power-connectors/intersection/multi-beam-xl-xle.html)) | 1 (80 A contact comfortably covers 20 A; oversized for this use) | 1 (oversized) | 1 (oversized, no redundancy — use 2) | Vertical and right-angle; VITA 62 lineage (rugged, backplane-class) | Guide-pin/jackscrew alignment typical of VITA 62 card-cage hardware — **not obviously a simple daughterboard latch; likely over-engineered/oversized for a consumer product** | Not found — VITA 62 parts are typically quote-only, **UNVERIFIED**, expect higher unit cost than the other three | Yes on rating, but likely the wrong tool (rugged/backplane-class, not consumer-cost-appropriate) |
| **Amphenol PwrBlade** | Individual contact 48 A; **multi-contact configurations rated 30 A per power contact at 30 °C rise, still air** ([amphenol-cs.com PwrBlade datasheet](https://cdn.amphenol-cs.com/media/wysiwyg/files/documentation/datasheet/power/pwr_powerblade_system.pdf)) | 1 (marginal) / 2 recommended (60 A) | 2 (60 A) | 2 (60 A) | Vertical or right-angle header/receptacle, coplanar/backplane/mezzanine mounting | 1–20 power contacts + 0–148 signal contacts in one housing (genuinely hybrid) — mezzanine-mount variants exist matching this exact "stood-up daughterboard" geometry | Not found — **UNVERIFIED**, but Amphenol/FCI power connectors of this class are typically in the low-$ per-position range at volume based on comparable families | Yes — rating explicitly at 30 °C rise, matches repo convention directly |
| **Hirose MCN51** (press-fit) | **27 A per contact, UL-recognized/CSA-certified**, press-fit compliant-pin termination, 8/16/30-position bodies, vertical and right-angle ([hirose.com MCN51](https://www.hirose.com/product/en/products/MCN51)) | 1 (marginal) / 2 recommended (54 A) | 2 (54 A) | 2–3 (54–81 A) | Vertical/RA, 8/16/30 positions | Press-fit (compliant pin) mechanical retention into the PCB itself gives strong captivation on the daughterboard side; mating-side retention mechanism not confirmed — **UNVERIFIED** | Not found — **UNVERIFIED** | Rating basis (30°C rise) not explicitly stated in the material found — **flag for datasheet confirmation** |
| **Cheap alternative — 2.54 mm dual-row header** | ~3 A/pin commonly cited (search consensus, e.g. Harwin/Amphenol BergStik-class parts; no single authoritative 30 °C-rise table found across manufacturers — **UNVERIFIED as a hard number**, treated per the study brief's own stated assumption) | 7 (24 A) | 14 (48 A) | 19 (57 A) | Standard 0.1″ pin field, many stack-height options | **Friction/housing-lock only on generic parts — no positive latch or screw** — this is the disqualifying weakness for "must not unseat/mis-seat" at these pin counts and currents | Very low, cents/position | Marginal — high pin count raises assembly/mis-seat risk faster than it saves cost, and no vendor 30 °C-rise table was found to hang a real margin number on |
| **Cheap alternative — 3.96 mm (0.156″) KK-396-class header** | **~7 A/pin** (search consensus across multiple 3.96 mm KK-396 listings; Molex's own `PS-08-50-001.pdf` datasheet exists but detailed per-pin derating table not extracted in this pass — **UNVERIFIED against the primary PDF**) | 3 (21 A) | 6 (42 A) | 8 (56 A) | Standard 0.156″ pin field | Same weakness as above — commodity single-row/dual-row housings are **friction-lock only**; no screw/latch variant found for this specific family | Very low, tens of cents/position | Same caveat — cheap and workable current-wise, but captivation is the open problem, not current |

**Honest flag on the mated-pair count:** every candidate above **adds one full mated contact set
downstream of the shunts**, on every rail, that did not exist when the output was a single
male-header-plus-cable joint terminating directly at the connector the shunt already sees. This
is the same "mated pair" cost the atx24 panel scored against Form C (3 mated pairs vs Form B's 2)
— the daughterboard reintroduces a comparable count (main-board shunt → inter-board joint →
daughterboard → header/pigtail joint → cable = at minimum 2 joints downstream of the shunt, same
as Form C, not Form B's 1). §5 below is the mitigation this study was asked to assess for exactly
that reason.

**Overall §1/§2 kill-check verdict: a real connector exists at the repo's design bar for every
family.** Samtec mPOWER, Molex Ten60Power, Amphenol PwrBlade, and Hirose MCN51 all clear 20 A
(24-pin), 40 A (PCIe), and 55 A (EPS) with 2–5 contacts and genuine 30 °C-rise-class derating —
this is not the Form-D failure mode (Micro-Fit 3.0 derating to 3–3.5 A/ckt, below even the lower
6 A ATX floor). The open risk is not "does a connector exist" — it is captivation/qualification
detail (latch type, primary-datasheet confirmation, 100-qty pricing) that needs a real quote
request before any part is locked in.

## 3. MODDIY verification

**MODDIY does sell a PCB-mount vertical header across all three families in scope**, under one
product line: **"Special Mini Low-Profile ATX Power GPU PCIE Connector for PCB Board"**
(SKU `CO261`, product code `MIATX-PCB`,
[moddiy.com/products/5689](https://www.moddiy.com/products/5689/Special-Mini-Low-Profile-ATX-Power-GPU-PCIE-Connector-for-PCB-Board.html)),
$1.99/unit at single-piece pricing, listed under MODDIY's **"ATX Power Housing Connectors
Female"** category. Confirmed selectable variants on that one product page: **ATX 24-Pin
(Black), CPU/EPS 8-Pin (Black), PCIE 8-Pin (Black), PCIE 6-Pin (Black), PCIE 8-Pin (White)** — so
yes, 24-pin ATX and EPS 8-pin and PCIe 8-pin PCB-mount female headers are all real, currently
orderable SKUs from this vendor. Stated spec text: "Type: Standard ATX Power Connector, Color:
Black, Pitch Size: 4.2mm, Terminal: Build-in", and the listing's own keyword text references
"Standard ATX 5557 4.2mm" and "5557-6P, 5557-8P, 5557-24P" — i.e., it reuses the same pitch and
housing family as the genuine Molex 5557 ATX housing, with (per the listing) built-in PCB solder
tails instead of the usual crimp-pin-and-wire construction. MODDIY separately sells the same
"for PCB Board" concept for 12VHPWR ("ATX 3.0 PCIe Gen 5 12VHPWR MicroFit 3.0 16 Pin Power
Connector for PCB") — out of scope here, but corroborates this is a real, maintained product line
at this vendor, not a one-off listing.

**This does confirm existence** of a board-mount female 24-pin ATX / EPS 8-pin / PCIe 8-pin
receptacle as an orderable part — which is, on its face, exactly the fact that would overturn
the §2.8 premise ("no board-mount female 24-pin ATX receptacle exists as a standard part").

**But this is very likely the same risk class already investigated and rejected in this repo's
own record.** `atx24-output-interface-panel-2026-07-03.md`'s "Option F provenance update" found
the owner's own hunt for a vertical PCB-mount female turned up only an **"unofficial Chinese
DIY part (AliExpress-class channels): no MPN, no footprint, no spec sheet, no lot control"**,
explicitly disqualified under the quality-first principle for a sellable consumer power product.
The MODDIY "MIATX-PCB" part shows every symptom of the same category: **no manufacturer name, no
MPN, no datasheet, no published current rating, no plating/alloy spec, no lot-control statement**
— MODDIY is a modding-parts *reseller* (14 years in the PC-modding accessory market per their own
marketing copy), not a connector manufacturer, and nothing in the listing identifies who actually
molds/stamps this part. "Reputable *reseller*" is not the same claim as "qualified component" —
the owner's stated sourcing plan ("MODDIY — reputable") should be read as **reputable as a
storefront to buy samples from**, not as a substitute for the bench qualification the panel
already prescribed for exactly this part category ("batch-qualify the DIY part: bench-derive a
spec + incoming inspection; permanent supply fragility + silent-change re-qual risk — shop
prototypes only, not the BOM").

**Recommendation, consistent with the panel's existing menu:** treat the MODDIY part as
**existence-confirmed, provenance-UNVERIFIED**. It is usable today for prototyping/sample
daughterboards (the "for PCB Board" female genuinely appears to solve the geometry/gender
problem for a bring-up unit) but should not be treated as closing the §2.8 premise for the
*sellable* BOM until physical samples are pulled and bench-qualified (pull force, current-rise,
plating integrity, mating-cycle life) — the same open item the panel already flagged, now simply
re-surfaced against a second storefront selling the same class of part.

## 4. Pigtail / extension-assembly through-hole field

Generic PCB-assembly practice (not vendor-specific; flagged where no manufacturer source backs a
number):

- **Wire gauge / hole sizing** (design-practice guidance, **UNVERIFIED against a specific
  manufacturer spec** — this is standard through-hole-solder sizing, not sourced to one part):
  16 AWG bare/tinned conductor ≈ 1.29 mm OD → recommend **drill ≈ 1.6–1.8 mm, annular pad ≈
  3.0–3.5 mm OD**; 18 AWG bare ≈ 1.02 mm OD → **drill ≈ 1.3–1.5 mm, pad ≈ 2.5–3.0 mm OD**. Err
  toward the oversized end of each range: these joints see sustained cantilever/flex load (the
  panel's own finding), so a generous annular ring buys both solder wicking and mechanical
  strength, the same logic already applied to this repo's high-current shunt/via geometry
  elsewhere.
- **Pitch:** recommend the **same 4.2 mm pitch as the standard Molex 5557/5559 ATX/EPS/PCIe
  family** (also MODDIY's own "for PCB Board" pitch, §3) rather than 2.54 mm or 3.96 mm. Two
  reasons: (1) it lets ONE daughterboard artwork serve both build paths in §6 — the same
  through-hole footprint either gets a MODDIY-class vertical header soldered onto it, or gets bare
  wire hand-soldered into the same holes with the header simply unpopulated; (2) 4.2 mm gives
  materially more clearance for 16–18 AWG **insulated** wire OD (≈1.6–2.4 mm) during hand soldering
  under a clamped strain-relief bar than a tighter 2.54/3.96 mm field would, where adjacent
  insulated conductors would crowd or require a staggered/zigzag row.
- **Strain-relief bar interface:** the prior-art numbers are the panel's own qualified target for
  this exact class of joint — **≥90 N pull, ≥500-cycle flex**
  (`atx24-output-interface-panel-2026-07-03.md`, bench question 1). General industry strain-relief
  literature corroborates the *order of magnitude* (historical cable strain-relief pull-test
  standards have moved from roughly 20 lbf/1 min toward ~60 lbf/5 min in some references — 60 lbf
  ≈ 267 N — **UNVERIFIED as directly applicable to this joint class**, cited only to show the
  panel's 90 N figure is a plausible, not arbitrary, target for a smaller-gauge multi-wire
  application). **Important scope nuance:** the panel derived its bar+numbers for a
  *daughterboard-local* potted/clamped bar; the 2026-07-04 ruling instead assigns strain relief to
  the **chassis** ("we'll design that in"), which may reduce the cantilever load the daughterboard
  joints themselves see if the chassis anchors the cable close by — but until the chassis
  mechanical spec exists, the daughterboard's own through-hole joints should still be designed to
  the same ≥90 N/≥500-cycle floor as a conservative default, not weakened on the assumption the
  chassis will fully absorb the load.
- **One field, two (really three) uses:** because the vertical-header footprint's own solder tails
  land in the identical through-holes a hand-soldered wire would use, a single daughterboard
  layout serves: (a) **header-populated** — customer's own standard ATX/EPS/PCIe cable plugs onto
  the vertical female, no CEC-supplied cable; (b) **factory pigtail** — same holes, header
  unpopulated, short wire run soldered in with the strain-relief bar, direct-connect only; (c)
  **sellable daughterboard+extension assembly** — same holes, wire run soldered in with the bar,
  terminating in a standard female housing so the extension is itself extension-compatible (the
  gender-logic finding already on record: female-out mates with nothing else needed). One bare-PCB
  SKU, three build variants downstream of it.

## 5. Sense-return option

The module's own current/voltage sensing (INA228/INA238/INA240, per `CLAUDE.md` §6.1) sits on the
**main board, upstream of the inter-board joint**. Everything downstream — the joint's contact
resistance, the daughterboard's own copper, the header/pigtail joint, the cable — is electrically
invisible to that telemetry today: a joint that degrades (oxidation, fretting corrosion, thermal
cycling loosening a crimp/press-fit/latch over years) shows up to the customer as heat or voltage
sag at the load, never as a number CEC's own sensors report.

**Proposal:** one (or one-per-rail) additional **low-current signal contact** on the same
inter-board connector, wired from the **daughterboard's output copper — physically downstream of
the mated joint** — back to a resistor divider **on the main board** feeding a spare ADC channel.
This adds **zero components to the daughterboard** (consistent with the ruling's "no components"
passive-daughterboard mandate: the divider, any ESD/filter cap, and the ADC all live on the main
board, same pattern as the existing MAIN_5V_SENSE/5VSB_SENSE dividers on Hub Standard or the
12VHPWR VRAIL_DIV divider). Cost: one extra contact per sensed rail on the connector (cheap —
every hybrid family in §2 explicitly supports mixed power+signal positions in one housing) plus
one divider per sensed rail on the main board.

**What it catches:** a slowly degrading joint — the delta between the shunt-side voltage (already
sensed) and this new downstream-sensed voltage grows over time even at constant load current,
which is the signature of rising contact resistance specifically at the joint, distinguishable
from a load-current increase (which would move the *existing* current sensor's reading too, in
proportion, not just this one). Tracking ΔV/I over time is a standard predictive-maintenance
signal for exactly the failure class a newly introduced mated pair creates.

**What it can't catch:** (a) a single failed contact among several *parallel* power contacts on
the same rail — current simply redistributes to the surviving contacts, and since all contacts on
a rail typically tie to one shared plane/net on both boards, the single sense tap sees the
lumped/shared-node result, not which specific contact failed; (b) sudden total disconnection —
that already shows up as an immediate under-voltage/DETECT-class event the existing sensing
catches, so this adds nothing new there; (c) a fully differential four-wire read of the joint
itself — a single-ended downstream tap (referenced to the main board's own GND, not a matching
downstream GND tap) conflates rail-side and return-side joint resistance into one lumped number.
A true Kelvin-quality read would need a downstream GND-side tap too, which doubles the added
contact count; whether that is worth it is an open cost/value call for the owner, not resolved
here.

## 6. Recommendation matrix

| Family | Recommended connector class | Power contacts (source + return) | Extra signal (sense-return + presence) | Projected daughterboard size | Open items for the owner |
|---|---|---|---|---|---|
| 24-pin ATX | Amphenol PwrBlade or Molex Ten60Power (30 A/contact @ 30 °C rise class) | ~2/rail × 4 rails (12V, 5V, 3.3V, 5VSB) + matching GND = **~16–18 contacts** | 1–4 (per sensed rail) | Small — connector body + fan-out to the chosen output footprint; comparable to the existing mezzanine/J6 precedent footprint, well under the current 24-pin board area | Real 100-qty quote (none of the four "real" families had confirmed volume pricing in this pass); confirm per-rail vs. shared-GND contact allocation against the actual 8-GND-pin ATX asymmetry noted in §1 |
| PCIe 2-port | Same family, **2 separate per-cable connector sites** (or 2 isolated contact groups in one housing) | 2/cable × 2 cables = **~8 contacts** | 1–2/cable | Two small connector zones, one per cable — mirrors the existing per-cable independent Kelvin-sense architecture | Confirm per-cable vs. one-shared-housing architecture (this study recommends per-cable separation to avoid compounding mutual-heating derates in one housing; not yet ratified) |
| PCIe 3-port | Same, ×3 cables | ~12 contacts | 1–3 | Three zones, same reasoning | Same as above, ×3 |
| EPS 8-pin | Higher-current member of the list (TE Multi-Beam 80 A high-power contact, or 2× Amphenol PwrBlade/Molex Ten60 per polarity) — EPS carries the highest repo design bar of the three (55 A/cable) | 2/cable × 2 cables = **~8 contacts**, sized to the highest per-contact rating available | 1–2/cable | Two small zones, same per-cable logic as PCIe | Confirm the 55 A design bar is the right target vs. accepting more margin loss at the connector; TE Multi-Beam is likely over-specified/costly for a consumer part — Amphenol/Ten60/Hirose are the more cost-appropriate picks pending real quotes |

**Data that is thin and should not be treated as settled:** 100-qty pricing for every "real"
board-to-board power family (§2); the primary Molex Ten60 PDF current-derating table (the search
summary is corroborated only by product-page marketing copy, not the extracted PDF); Hirose
MCN51's mating-side captivation mechanism and its 30 °C-rise basis; whether the MODDIY "for PCB
Board" part's actual terminal alloy/plating clears any real current at all without a physical
sample (§3); the per-cable-vs-shared-housing architecture call for EPS/PCIe (this study's
recommendation, not ratified); and the transient-absorption assumption (§1) that a
non-continuously-rated connector contact can safely ride out the 60–75 A EPS/PCIe transient
figures the way the shunt's thermal mass already does — nothing here bench-verifies that.

**Owner-facing follow-ups this study surfaces (not resolved here):**
1. Request real 100-qty quotes on Amphenol PwrBlade, Molex Ten60Power, and Hirose MCN51 in the
   contact counts above, before any part gets written into a BOM.
2. Pull physical MODDIY "MIATX-PCB" samples and run the same bench battery already prescribed for
   the DIY vertical-female part in the atx24 panel record (pull force, mating cycles, current-rise,
   plating/contact-resistance trend) — do not treat MODDIY-sourced as pre-qualified.
3. Decide the EPS/PCIe per-cable-vs-shared-housing architecture (§6) explicitly.
4. Decide whether the sense-return option (§5) ships now, later, or not at all, and at what
   granularity (per-rail vs. single shared tap).
5. Get the chassis strain-relief geometry/force numbers so the daughterboard's through-hole joint
   spec (§4) can be finalized rather than defaulting to the panel's daughterboard-local figures.
