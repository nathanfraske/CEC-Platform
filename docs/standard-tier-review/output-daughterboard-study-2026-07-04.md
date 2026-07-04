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

| Candidate | Per-contact derated rating | Contacts for 24-pin 12V rail (20 A target) | Contacts for PCIe cable (49 A margin target) | Contacts for EPS cable (65 A margin target) | Stack height | Keying/captivation | Indicative cost (100 qty) | Survives 30 °C-rise culture? |
|---|---|---|---|---|---|---|---|---|
| **Samtec mPOWER UMPT/UMPS** (2 mm pitch blade) | 18 A single-contact max; **derates with adjacent loading** — ~12.9–13.2 A at 4 populated contacts, ~8.9–9.8 A at 10, all figures already **20% derated for 30 °C rise to max allowable temp** ([samtec.com/products/umps](https://www.samtec.com/products/umps), [umpt](https://www.samtec.com/products/umpt), datasheet F-224) | 2 (≈26 A) | 4 (≈52 A) | 5–6 (≈65–75 A) | Vertical or right-angle, multiple stack heights | UMPT offers **metal side-latching** or plastic-top variants — genuine positive latch available | Single-unit DigiKey ~$4–7/part (UMPS-04/UMPT-04 class); no 100-qty break found — **UNVERIFIED at volume** | Yes — rating is *already stated at* 30 °C rise |
| **Molex EXTreme Ten60Power / Ten60** | 50 A per blade headline; **split-blade terminal rated 30 A at 30 °C T-rise** (search-derived from Molex product-highlight copy; full PS-46436 PDF is image-encoded and did not extract textually — **rating cross-check UNVERIFIED against the primary PDF table**, only the marketing/product-page mirror) | 1 (marginal, no redundancy) / 2 recommended (60 A) | 2 (60 A) | 3 (90 A) | Vertical and right-angle, "hybrid power-and-signal" mixed housings | PCB polarizing pegs, guide modules (1.8–2.4 mm misalignment gatherability), **200 mate/unmate cycle rating** — no explicit screw-lock found, alignment-guide based | Not found in this pass — **UNVERIFIED** | Likely yes (30 A figure explicitly at 30 °C rise) but primary datasheet not confirmed |
| **TE MULTI-BEAM XLE / XL** | Up to 100 A/contact with 4 adjacent contacts; standard configs **80 A high-power contact / 20 A low-power contact**; 6-beam variant to 75 A ([te.com MULTI-BEAM HD/XLE/XL](https://www.te.com/en/products/connectors/power-connectors/intersection/multi-beam-xl-xle.html)) | 1 (80 A contact comfortably covers 20 A; oversized for this use) | 1 (oversized) | 1 (oversized; 80 A covers 65 A alone) / 2 recommended for redundancy | Vertical and right-angle; VITA 62 lineage (rugged, backplane-class) | Guide-pin/jackscrew alignment typical of VITA 62 card-cage hardware — **not obviously a simple daughterboard latch; likely over-engineered/oversized for a consumer product** | Not found — VITA 62 parts are typically quote-only, **UNVERIFIED**, expect higher unit cost than the other three | Yes on rating, but likely the wrong tool (rugged/backplane-class, not consumer-cost-appropriate) |
| **Amphenol PwrBlade** | Individual contact 48 A; **multi-contact configurations rated 30 A per power contact at 30 °C rise, still air** ([amphenol-cs.com PwrBlade datasheet](https://cdn.amphenol-cs.com/media/wysiwyg/files/documentation/datasheet/power/pwr_powerblade_system.pdf)) | 1 (marginal) / 2 recommended (60 A) | 2 (60 A) | 3 (90 A) | Vertical or right-angle header/receptacle, coplanar/backplane/mezzanine mounting | 1–20 power contacts + 0–148 signal contacts in one housing (genuinely hybrid) — mezzanine-mount variants exist matching this exact "stood-up daughterboard" geometry | Not found — **UNVERIFIED**, but Amphenol/FCI power connectors of this class are typically in the low-$ per-position range at volume based on comparable families | Yes — rating explicitly at 30 °C rise, matches repo convention directly |
| **Hirose MCN51** (press-fit) — **WITHDRAWN by the §8 cost pass: OBSOLETE** (DigiKey lists MCN51-30S3-PFA "This product is no longer manufactured"; Mouser lists MCN51-8S2-PFA non-stocked, scheduled for obsolescence) | **27 A per contact, UL-recognized/CSA-certified**, press-fit compliant-pin termination, 8/16/30-position bodies, vertical and right-angle ([hirose.com MCN51](https://www.hirose.com/product/en/products/MCN51)) | 1 (marginal) / 2 recommended (54 A) | 2 (54 A) | 3 (81 A) | Vertical/RA, 8/16/30 positions | Press-fit (compliant pin) mechanical retention into the PCB itself gives strong captivation on the daughterboard side; mating-side retention mechanism not confirmed — **UNVERIFIED** | n/a — obsolete (§8.1) | n/a — obsolete |
| **Cheap alternative — 2.54 mm dual-row header** | ~3 A/pin commonly cited (search consensus, e.g. Harwin/Amphenol BergStik-class parts; no single authoritative 30 °C-rise table found across manufacturers — **UNVERIFIED as a hard number**, treated per the study brief's own stated assumption) | 7 (21 A) | 17 (51 A) | 22 (66 A) | Standard 0.1″ pin field, many stack-height options | **Friction/housing-lock only on generic parts — no positive latch or screw** — this is the disqualifying weakness for "must not unseat/mis-seat" at these pin counts and currents | Very low, cents/position | Marginal — high pin count raises assembly/mis-seat risk faster than it saves cost, and no vendor 30 °C-rise table was found to hang a real margin number on |
| **Cheap alternative — 3.96 mm (0.156″) KK-396-class header** | **~7 A/pin** (search consensus across multiple 3.96 mm KK-396 listings; Molex's own `PS-08-50-001.pdf` datasheet exists but detailed per-pin derating table not extracted in this pass — **UNVERIFIED against the primary PDF**) | 3 (21 A) | 7 (49 A) | 10 (70 A) | Standard 0.156″ pin field | Same weakness as above — commodity single-row/dual-row housings are **friction-lock only**; no screw/latch variant found for this specific family | Very low, tens of cents/position | Same caveat — cheap and workable current-wise, but captivation is the open problem, not current |

The 12V-rail column is the representative (lowest-current) 24-pin case; scale contact counts by
~1.5× for 3.3V (30 A target) and ~1.9× for 5V (37.5 A target) at the same per-contact rating.

**Honest flag on the mated-pair count:** every candidate above **adds one full mated contact set
downstream of the shunts**, on every rail, that did not exist when the output was a single
male-header-plus-cable joint terminating directly at the connector the shunt already sees. This
is the same "mated pair" cost the atx24 panel scored against Form C (3 mated pairs vs Form B's 2)
— the daughterboard reintroduces a comparable count (main-board shunt → inter-board joint →
daughterboard → header/pigtail joint → cable = at minimum 2 joints downstream of the shunt, same
as Form C, not Form B's 1). §5 below is the mitigation this study was asked to assess for exactly
that reason.

**Overall §1/§2 kill-check verdict: a real connector exists at the owner's margin-adjusted design
bar for every family.** Samtec mPOWER, Molex Ten60Power, Amphenol PwrBlade, and Hirose MCN51 all
clear 20–37.5 A (24-pin, per rail), 49 A (PCIe), and 65 A (EPS) with 2–6 contacts and genuine
30 °C-rise-class derating — this is not the Form-D failure mode (Micro-Fit 3.0 derating to
3–3.5 A/ckt, below even the *un*-margined 6 A ATX floor). The open risk is not "does a connector
exist" — it is captivation/qualification detail (latch type, primary-datasheet confirmation,
100-qty pricing) that needs a real quote request before any part is locked in.

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

## 6. Daughterboard shape: per-cable vs. one wide board

A shape question specific to the multi-cable families: is there ONE inter-board connector/
daughterboard per cable, or ONE wide daughterboard spanning every cable on the module? (24-pin is
moot here — it is already architecturally "one wide" connector by ATX convention, all rails
through a single housing; this question only bites on EPS and both PCIe SKUs, where each cable is
today an independently shunted, independently Kelvin-sensed chain.)

- **Shape A — per-cable:** a separate small connector/daughterboard site per cable, each sized only
  to its own cable's margin target (EPS 65 A, PCIe 49 A, §1).
- **Shape B — one wide board:** a single connector/housing carrying the SUM of every cable's
  current on the module.

| | EPS (2 cables) | PCIe-2port (2 cables) | PCIe-3port (3 cables) |
|---|---|---|---|
| Shape A: contacts/site (PwrBlade/Ten60-class, 30 A/contact) | 3/polarity/site × 2 sites = **12 power contacts total** | 2/polarity/site × 2 sites = **8** | 2/polarity/site × 3 sites = **12** |
| Shape B: aggregate current in one housing | ~130 A (65×2) | ~98 A (49×2) | ~147 A (49×3) |
| Shape B: contacts (same nominal 30 A/contact figure) | 5/polarity = **10** | 4/polarity = **8** | 5/polarity = **10** |

Shape B's raw contact count looks similar to, or even slightly lower than, Shape A's — but that
comparison is **misleading**. Every family in §2 publishes per-contact ratings that **derate
further as more contacts are populated in the same housing** (mutual heating — Samtec's own table
is explicit: 18 A single-contact drops to ~13 A at 4 populated, ~9 A at 10). Shape B concentrates
every cable's contacts into one housing, so the real per-contact figure to use comes from a
higher-population row of that derating curve than Shape A's smaller per-cable housings ever reach
— Shape B's true contact count is higher than the naive same-per-contact-value math above
suggests, and its housing runs measurably hotter for the same total current than two or three
separate housings dissipating into separate board regions.

Shape B also **breaks fault isolation** (a single connector-body defect risks every cable on the
module at once) and cuts against the ruling's own sellable-assembly addendum — a customer or
service tech cannot replace one cable's daughterboard+extension independently if every cable's
copper is fused onto one shared board. Its one genuine advantage is fewer discrete parts: one
connector, one PCB, one chassis cutout/strain-relief interface instead of two or three.

**Recommendation: Shape A (per-cable), for EPS and both PCIe SKUs.** It avoids the hidden
mutual-heating margin loss Shape B introduces, preserves the per-cable independent Kelvin-sense
architecture already built into these modules, and is a direct match for the ruling's
"daughterboard+extension can itself be sold" addendum without re-litigating how to split a shared
board later. Shape B's one real edge (fewer chassis cutouts) is a mechanical/BOM-count trade for
the owner and chassis designer to weigh, not a current-capacity argument — flagged as an open item,
not resolved here.

## 7. Recommendation matrix

_**REVISED same day, twice: first by the §8 cost pass (owner: "~$5 per connector is a bit
high"), then by the §8.5 geometry revision (owner: "40 mm and 80 mm long cards are MASSIVE"),
which added the main-board FOOTPRINT GATE and killed the interim card-edge picks.** The premium
board-to-board families remain as the qualified fallback; Hirose MCN51 is withdrawn (obsolete,
§8.1). Current picks below = §8.5._

| Family | Recommended connector class (post-§8.5) | Power contacts/points (source + return) | Extra signal (sense-return + presence) | Projected daughterboard size | Open items for the owner |
|---|---|---|---|---|---|
| 24-pin ATX | **Posts+signal-header hybrid** (§8.5: screwed M3 power posts + one 2×5 2.54 mm header for PS_ON#/PWR_OK/−12 V/remote-sense/sense-returns). Conditional alternate: Amphenol HPCE card-edge (9 A/beam verified; pitch+price UNVERIFIED) if tool-less swap is worth premium. Commodity card-edge FAILS the footprint gate (§8.5(2)) | **10–12 posts** at the 25–30 A/joint generic estimate (**UNVERIFIED — bench**; REDCUBE-class bench upside → 6–8) | Rides the signal header (~free pins) | Small post-field card ≈ incumbent 24-pin header area; posts pour-native, zero edge, no mouth keepout | Post A/joint bench (now load-bearing for ALL families); HPCE pitch/price verify; −12 V rail-current check at pin-map time |
| PCIe 2-port | **Posts+header hybrid, Shape A** (2+2 posts/cable + 1×2–3 signal stub) — card-edge cannot reach the 5.4 A/mm gate at any price (§8.5(2)) | **8 posts** | 1–2 pins/cable | Two small post-field cards | Same post bench |
| PCIe 3-port | Same, ×3 cables | **12 posts** | ×3 | Three cards | Same |
| EPS 8-pin | **Posts+header hybrid, Shape A** (3+3/cable — unchanged pick, now with the whole-family rationale; the 7.2 A/mm gate is unreachable by any card-edge surveyed) | **12 posts** (bench upside → 2+2/cable) | 1 stub/cable | Two small post-field cards; posts double as chassis retention | Same post bench |

**Data that is thin and should not be treated as settled:** 100-qty pricing for every "real"
board-to-board power family (§2); the primary Molex Ten60 PDF current-derating table (the search
summary is corroborated only by product-page marketing copy, not the extracted PDF); Hirose
MCN51's mating-side captivation mechanism and its 30 °C-rise basis; whether the MODDIY "for PCB
Board" part's actual terminal alloy/plating clears any real current at all without a physical
sample (§3); the Shape A/B call for EPS/PCIe (§6, this study's recommendation, not ratified); the
125 %-margin policy itself (§1, proposed here, not yet an owner-ratified number); and the
transient-absorption assumption (§1) that a non-continuously-rated connector contact can safely
ride out the 60–75 A EPS/PCIe transient figures the way the shunt's thermal mass already does —
nothing here bench-verifies that.

**Owner-facing follow-ups this study surfaces (not resolved here):**
1. Ratify or revise the 125 %-margin policy (§1) — it is this study's proposal, not an existing
   owner number.
2. ~~Request real 100-qty quotes on Amphenol PwrBlade, Molex Ten60Power, and Hirose MCN51~~
   **superseded by §8**: MCN51 obsolete; PwrBlade/mPOWER priced and found too expensive as the
   default; quotes now only needed if the premium fallback is ever invoked.
3. Pull physical MODDIY "MIATX-PCB" samples and run the same bench battery already prescribed for
   the DIY vertical-female part in the atx24 panel record (pull force, mating cycles, current-rise,
   plating/contact-resistance trend) — do not treat MODDIY-sourced as pre-qualified.
4. Decide the Shape A/B call for EPS/PCIe (§6) explicitly.
5. Decide whether the sense-return option (§5) ships now, later, or not at all, and at what
   granularity (per-rail vs. single shared tap).
6. Get the chassis strain-relief geometry/force numbers so the daughterboard's through-hole joint
   spec (§4) can be finalized rather than defaulting to the panel's daughterboard-local figures.
7. §8 additions: card-edge current-sharing + plating bench; generic-post A/joint bench; the EPS
   edge-length vs. board-outline decision (§8.2a/§8.4).

---

## 8. COST PASS (2026-07-04, owner follow-up — same day)

_Owner: "~$5 per connector is a bit high if we're also adding the daughterboard sub-assembly to
the BOM." This section re-prices the §7 recommendations honestly (mated pairs, both sides) and
evaluates cheaper classes at the SAME electrical bar (§1: EPS ~65 A / PCIe ~49 A / 24-pin
per-rail continuous, ≤30 °C rise, keyed/key-able, captive-able)._

### 8.1 Verified pricing on the §7 premium recommendations

A mated board-to-board family needs a purchased part on **BOTH** boards — price the PAIR per
cable, not the side.

| Family | Verified price point | Pair per cable | Verdict |
|---|---|---|---|
| Samtec mPOWER | UMPT-04-01.5-G-V-S-W-TR (4-blade vertical header): **$3.44 @100** (DigiKey, 533 in stock; $4.76@1). Mating UMPS receptacle: $4.22–4.64 single-unit (DigiKey), 100-qty break not captured — same class assumed | **≈ $6.5–7/cable @100** | **$3.4+/side confirmed — over the owner's bar** as a per-cable default |
| Amphenol PwrBlade | 51915-051LF (31-pos R/A receptacle, 7 power + 24 signal): **$6.99 @33 / $6.40 @132** (DigiKey, 338 in stock; $8.95@1). Mating header not priced (the 2-pos 51939-198LF page is dead at DigiKey); smaller configs exist but were not captured at 100-qty | **≈ $10–13/cable @100 (est., UNVERIFIED header half)** | **$5+/side confirmed for the receptacle alone — over the bar** |
| Molex Ten60Power | Mouser product pages 403'd through the proxy; DigiKey pricing not surfaced | UNVERIFIED — family class comparable to PwrBlade or higher | Cannot be defended as the cost pick |
| Hirose MCN51 | DigiKey MCN51-30S3-PFA: **"Obsolete — this product is no longer manufactured"**; Mouser MCN51-8S2-PFA: non-stocked, scheduled for obsolescence | n/a | **WITHDRAWN** — dead family, removed from the recommendation regardless of price |

The owner's instinct is confirmed: the premium blade families are **$6.5–13 per cable-pair at
100-qty**, i.e. $13–26/module on EPS/PCIe-2 — on modules with $32–42 BOM targets, before the
daughterboard fab itself. They stay in §2 as the qualified fallback only.

### 8.2 Cheap alternative classes at the same electrical bar

**(a) CARD-EDGE — daughterboard as a gold-finger card (the standout).** Only ONE purchased part
per cable (the slot, on the main board); the daughterboard's half of the connector is bare
copper/plating = fab cost, ~pennies. Ratings, verified: **EDAC 307 series (0.156″/3.96 mm,
dual-readout): 5 A continuous per contact** ([edac.net/series/307](https://edac.net/series/307));
Sullins 0.156″ edgecards: **3 A per contact** (sullinscorp.com). Generic "805-series" 3.96 mm
solder-tail slots are ~$0.6–0.9/pc at small retail qty (AliExpress 10/$8.99; eBay/Amazon
equivalents) — LCSC carries a card-edge category with parts from ~$0.38 but the specific 3.96 mm
power-suitable SKU/rating was not pinned down this pass (**UNVERIFIED**; the one LCSC part
checked, TE 2041119-1 at $0.54@100, turned out to be an 0.8 mm mSATA socket — not applicable).
Contact math at the verified 5 A/contact, dual-readout (contacts both card faces, paralleled):
- **PCIe 49 A/cable:** 10 source + 10 GND = 2×10 positions ≈ **40 mm slot/cable** — fits both
  PCIe boards' edges (99/126 mm) in Shape A.
- **24-pin (95 A aggregate + returns):** ~2×20 positions ≈ **80 mm slot** — fits the ~87 mm
  board edge, barely.
- **EPS 65 A/cable:** 13+13 = 2×13 ≈ **58 mm slot/cable**; ×2 cables = ~116 mm — **does NOT fit
  the current 96 mm EPS outline** in Shape A (and Shape B's single 103 mm slot doesn't either).
  Card-edge on EPS requires a wider beta outline, a higher-rated (costlier) power-edge family, or
  falling to option (b).
Keying: polarizing key slot punched in the finger field (standard card-edge practice) — mis-seat
and reversal both blocked, free. Captivation: screw boss through the daughterboard into the
chassis/main-board standoff — matches the ruling's chassis-strain-relief assumption; the slot
never carries mechanical load. Plating: mated ONCE at factory then screwed down → low-cycle, so
ENIG fingers (JLCPCB standard option) are arguably sufficient; hard gold (30–50 µin, the
proper repeated-insertion finish per JLCPCB's own guidance,
[jlcpcb.com gold fingers](https://jlcpcb.com/help/article/jlcpcb-gold-fingers)) only if the
assembly is field-swappable. Hard-gold/bevel adder is quote-time (**UNVERIFIED**, order-level not
per-board). Qualification needed: per-contact rating of the actual purchased slot (EDAC's 5 A is
verified; an 805-clone's is NOT — same provenance discipline as the MODDIY finding), and a
30 °C-rise current-sharing bench across paralleled fingers (contact-resistance spread governs
sharing; the §5 sense-return finger is the free monitor for exactly this).

**(b) SOLDERED/SCREWED POWER POSTS — cheapest hardware, strongest captivation.** Brass standoffs
/ screw posts through plated holes on both boards; the fastener IS the retention and doubles as
the chassis strain-relief interface the ruling already assumes. Generic M3 brass standoff + 2
screws ≈ **$0.10–0.15/point at 100-qty** (LCSC-class hardware; **UNVERIFIED** exact SKU). No
manufacturer rating exists for generic standoffs-as-conductors — the qualified benchmark is
Würth REDCUBE (same topology, engineered): **THR M3–M5 rated 85 A, SMD to 70 A, M3 R/A 50 A**
([we-online.com REDCUBE](https://www.we-online.com/en/components/products/em/redcube_terminals),
Enrgtech 7466313R listing) — proving the screwed-PCB-joint topology carries this study's whole
bar per point when done right. REDCUBE pricing not captured (**UNVERIFIED**, believed $1.5–3/pc —
mid-tier, not the cheap play). The cheap play is the generic post at a conservative
**20–30 A/joint engineering estimate (UNVERIFIED — must be bench-derived: joint R, torque spec,
thermal cycling, vibration loosening/thread-locker)**. Counts at 25 A/joint est.: EPS 3+3
posts/cable; PCIe 2+2/cable; 24-pin ~6+6. Keying: asymmetric post pattern (free). Downside:
tool-required service (not tool-less), hand/machine screw assembly labor, and no native signal
contact (sense-return needs a separate cheap 1–2-pin header per site).

**(c) FASTON / 6.3 mm PCB tab pairs — WEAK, effectively killed by the verified rating.** The
verified figure found this pass is the TE **mini** 250 FASTON receptacle: **7 A continuous /
14 A intermittent** (TE 250-series mini FASTON datasheet/e-card via te.com). The 15–20 A/tab
folk figure for standard 250-series was NOT verified this pass (**UNVERIFIED**). At the verified
7 A, EPS needs 10+10 tabs/cable — absurd. Geometry is also wrong for board-to-board: FASTON
receptacles are wire-crimp parts; PCB-mount receptacles exist but multi-tab blind-mate alignment
is unmanaged. Tab hardware is genuinely cheap (TE 63824-1 class, reels of 10k; pennies-to-dimes)
but the class fails the bar. Dropped.

**(d) LCSC power-BTB clones (CJT/XFCN etc.).** CJT's catalog spans 0.5–50 A families and LCSC
distributes them, but this pass did not pin a specific board-to-board power-blade clone SKU with
a published derating at our bar (**UNVERIFIED — thin**). Same provenance discipline as the
MODDIY finding applies: existence of a cheap clone is not qualification. Worth one follow-up
LCSC catalog sweep only if card-edge and posts both fail their benches.

**(e) Many-parallel-pin headers.** 2.54 mm (~3 A/pin assumed): EPS needs 22+22 pins,
friction-only retention — fails captivation, no better than card-edge on any axis. 3.96 mm
KK-class (~7 A/pin, UNVERIFIED): wire-to-board family; no standard PCB-mount mating female for
BTB use. Neither undercuts (a)/(b). Dropped.

### 8.3 $/module at 100-qty (connector purchase + daughterboard fab delta; estimates marked)

Assumptions: small 2-layer 2 oz daughterboard ≈ **$1–1.5/board bare fab @100 (est., UNVERIFIED
— JLCPCB-class)**; card-edge slot ≈ $0.6–1.5 (verified retail band, 100-qty **UNVERIFIED**);
generic post-point ≈ $0.12 (**UNVERIFIED**); mPOWER pair $6.5–7/cable (verified basis, §8.1).
Sense-return contacts are ~free on card-edge (a finger), ~$0.10 on posts (pin header).

| Family | Shape | Card-edge (a) | Generic posts (b) | Premium pair (mPOWER, §8.1) |
|---|---|---|---|---|
| 24-pin ATX | one-wide (§6: 24-pin is inherently one-wide) | 1 slot + 1 board ≈ **$2.5–3** | 12 posts + 1 board ≈ **$2.5–3** | ~2× UMPT/UMPS-10-class pair + board ≈ **$13–16 (est.)** |
| EPS ×2 cables | A (per-cable) | 2 slots + 2 boards ≈ $3.5–5 — **but does not fit the 96 mm outline (§8.2a)** | 12 posts + 2 boards ≈ **$3.5–4.5** | 2 pairs + 2 boards ≈ **$16–17** |
| EPS ×2 | B (one-wide) | 1×103 mm slot — nonstandard length AND doesn't fit; dead | 12 posts + 1 board ≈ **$2.5–3.5** | n/a clean config |
| PCIe 2-port | A | 2 slots + 2 boards ≈ **$3.5–5** | 8 posts + 2 boards ≈ **$3.5–4** | 2 pairs + 2 boards ≈ **$16–17** |
| PCIe 2-port | B | 1×~76 mm slot + 1 board ≈ $2.5–3.5 (§6 derating/fault-isolation objections stand) | 8 posts + 1 board ≈ **$2.5–3** | n/a |
| PCIe 3-port | A | 3 slots + 3 boards ≈ **$5–7.5** | 12 posts + 3 boards ≈ **$5–6** | 3 pairs + 3 boards ≈ **$24–26** |
| PCIe 3-port | B | 1×~114 mm slot — near/over the practical slot-length ceiling; weak | 12 posts + 1 board ≈ **$3–4** | n/a |

Every cheap-class cell lands **$2.5–7.5/module** vs the premium class's **$13–26/module** — a
3–6× reduction, at the same §1 electrical bar, pending the named benches.

### 8.4 Cost-optimized recommendation (electrical bar held)

_**CHANGELOG (2026-07-04, later same day): the card-edge picks below are SUPERSEDED by §8.5** —
owner pushback: "40 mm and 80 mm long cards are MASSIVE — 40 mm is roughly the width of the
entire 24-pin connector." §8.5 adds the main-board FOOTPRINT GATE this cost pass lacked and
revises the picks. §8.4 is retained unedited for provenance._

- **24-pin ATX: card-edge, one slot** (EDAC 307-class, 5 A/contact verified), ~2×20 positions /
  ~80 mm. ≈$2.5–3/module. Fallback: posts (same cost) if the beta outline can't give the edge.
- **PCIe 2-port & 3-port: card-edge, Shape A (one slot per cable)**, 2×10 positions / ~40 mm per
  cable. ≈$3.5–7.5/module. The §6 per-cable arguments (derating, fault isolation, sellable
  per-cable assembly) all carry over.
- **EPS: screwed power posts, Shape A** (3+3 M3 per cable) — card-edge at the verified
  5 A/contact needs ~116 mm of edge the 96 mm board doesn't have. ≈$3.5–4.5/module. If the owner
  prefers one connector class across all four families: either grow the EPS beta outline to fit
  2×58 mm of slot, or qualify a higher-per-contact power-edge family (exists, e.g. Samtec
  HPCE-class — pricing likely back in the premium band, **UNVERIFIED**).
- **Qualification debt the cheap picks carry (must run before BOM lock):** (i) card-edge:
  purchased-slot rating provenance (EDAC verified / 805-clone NOT), paralleled-finger
  current-sharing at 30 °C rise, ENIG-vs-hard-gold call; (ii) posts: bench-derived A/joint,
  torque + thread-lock spec, thermal-cycle/vibration retention; (iii) both: the §5 sense-return
  becomes MORE valuable here (it monitors exactly the joint class being cost-reduced) — card-edge
  gets it for a free finger, posts need one cheap signal pin per site.
- MCN51 is withdrawn everywhere (obsolete). Premium blade families (mPOWER/PwrBlade/Ten60)
  remain the documented fallback if any cheap-class bench fails.

### 8.5 GEOMETRY REVISION (2026-07-04, owner pushback — same day)

_Owner: "40 mm and 80 mm long cards are MASSIVE — 40 mm is roughly the width of the entire
24-pin connector." Correct — and it defeats the ruling's win #1 (pours no longer forced around
the output pin field). This subsection adds the footprint gate, corrects the card-edge geometry
record, generalizes the §8.4 EPS posts pick into a posts+signal-header hybrid for all families,
and revises the recommendation. It supersedes §8.4's picks._

**(1) NEW FIRST-CLASS GATE — main-board footprint.** The inter-board interface's main-board
footprint (slot/post field + mating and routing keepouts) must not exceed the output connector
it replaces: **24-pin Mini-Fit Jr 24-ckt ≈ 51.6 × 9.8 mm (~506 mm²)**; **EPS/PCIe 2×4 ≈
18 × 9.8 mm (~176 mm²) per cable** (owner-supplied incumbents, consistent with the Molex
5569/45586-class drawings; each ALSO carries a cable-mouth clearance zone in front and a
pour-blocking THT pin field — counted below where it changes a verdict).

**(2) Card-edge geometry corrected — and it FAILS the gate.** For the record: **the §8.2a math
was ALREADY dual-readout** — "2×N positions" meant N positions of physical length with contacts
on BOTH card faces (2 contacts/position), per the verified EDAC 307 dual-readout construction
("dual row contacts that read both sides of daughter board," e.g. 307-044-520-202, 3.96 mm
spacing — [edac.net/series/307](https://edac.net/series/307), Newark listings). **No further
halving is available in this class.** The governing figure is linear ampacity: dual-readout
3.96 mm at the verified 5 A/contact = 2×5 A per 3.96 mm ≈ **2.5 A/mm of slot**; denser pitch
does NOT help (2.54 mm edgecards are rated lower — Sullins 0.100″ class ≈ 3 A/contact → 2×3/2.54
≈ **2.4 A/mm**, i.e. the pitch gain is cancelled by the rating drop). The gate demands: 24-pin
190 A / 51.6 mm = **3.7 A/mm**; PCIe 98 A / 18 mm = **5.4 A/mm**; EPS 130 A / 18 mm =
**7.2 A/mm**. Commodity card-edge (~2.4–2.5 A/mm) is **physically unable to clear the gate for
any family** — the §8.4 slot lengths (80/40/58 mm vs 51.6/18/18 mm incumbents) were the visible
symptom. Adjacent-finger loading at 30 °C rise would only push the real figure DOWN from the
nameplate (no adjacent-loading derate is published for EDAC/Sullins — the §8.4 bench item stands,
now moot for the commodity class). The ONE card-edge class that could clear the 24-pin gate:
**Amphenol HPCE (High Power Card Edge), verified 9 A per power beam with multiple contacts fully
energized at 30 °C rise still air** ([Amphenol HPCE datasheet via
Mouser](https://www.mouser.com/datasheet/2/18/1/pwr_hpce-2578367.pdf)) — beam pitch and 100-qty
price NOT captured this pass (**UNVERIFIED**), and the family is a premium server-power part, so
it survives only as a conditional for the 24-pin if tool-less daughterboard swap is worth paying
for. (The earlier "Samtec HPCE" attribution in §8.4 was wrong — HPCE is Amphenol ICC/FCI;
Samtec's power edgecard is the HSEC8-PV/Generate class, also premium.)

**(3) Posts + signal-header HYBRID, generalized to all families.** Screwed power posts carry the
rails; ONE small 2.54 mm signal header per module (or a 2–3-pin stub per cable) carries what
posts can't: the 24-pin's low-current standards circuits (**PS_ON#, PWR_OK, +3.3 V remote sense,
−12 V** — the −12 V rail is sub-ampere on modern PSUs, header-safe; **UNVERIFIED** exact rail
spec, flag at pin-map time) plus the §5 sense-returns. Arrangements at the 25–30 A/joint generic
M3 estimate (**UNVERIFIED — bench item**; Würth REDCUBE THR M3 at a verified 85 A proves the
topology's headroom, so a good bench plausibly HALVES these counts):

| Family | Posts (source + GND) | Signal header | Contiguous worst-case block (posts @ ~8 mm grid, Ø7 mm pads) | vs. gate |
|---|---|---|---|---|
| 24-pin | 12 V×1, 5 V×2, 3.3 V×1–2, 5VSB×1 + GND×5–6 = **10–12** | 2×5 (12.7×5 mm) | 2 rows × 5–6 = **~44×16 mm (~700 mm²)** raw | Raw block ≈ 1.2–1.4× the 506 mm² incumbent — **parity-to-over on raw area**; **CLEARS on effective footprint** (below) |
| EPS ×2 | 3+3 per cable = **12** | 1×3 per cable | per cable 2×3 = ~24×16 mm (~384 mm²) raw | Raw ≈ 2.2× the 176 mm²/cable incumbent; effective: clears |
| PCIe-2 | 2+2 per cable = **8** | 1×2–3 per cable | per cable 2×2 = ~16×16 mm (~256 mm²) raw | Raw ≈ 1.45×; effective: clears |
| PCIe-3 | 2+2 ×3 = **12** | ×3 | same per cable | same |

**The effective-footprint argument (why the hybrid clears the gate where raw mm² says parity):**
(a) post pads are **pour-native** — a post lands IN the rail pour it feeds, consuming zero area
the pour didn't already occupy, whereas the incumbent's 24-THT pin field is exactly the
pour-blocking obstacle the ruling's win #1 wants deleted; (b) posts consume **zero board edge**
and have **no cable-mouth keepout** (the mate is vertical, into the daughterboard standing above
— area under a stood-up daughterboard remains routable); (c) the posts ARE the captivation and
the chassis strain-relief interface (ruling assumption) — no separate screw boss needed, which
every other candidate adds on top of its raw footprint. On the gate as stated (footprint +
mating/routing keepouts), the hybrid is the only candidate that beats the incumbent for every
family; on raw contiguous mm² alone it is parity (24-pin @10 posts) to ~2× (EPS per-cable) — both
numbers stated so the owner is not sold an accounting trick. Bench upside is real: at a
REDCUBE-class-validated 40–50 A/joint, counts drop to ~6–8 (24-pin) / 2+2 (EPS) / 1+1–2+2
(PCIe), putting even the raw block under every gate.

**Hybrid pricing (100-qty, est. basis of §8.3):** 24-pin ≈ 10–12 post-sets ($1.2–1.4) + header
pair (~$0.25) + board ($1–1.5) ≈ **$2.5–3.2/module**. PCIe-2 ≈ **$2.9–3.5**; PCIe-3 ≈ **$4.3–5**;
EPS ≈ **$3.6–4.6**. (Post-set ~$0.12 **UNVERIFIED**, LCSC-class hardware.) Cheapest or
tied-cheapest column in the §8.3 table for every family.

**(4) Revised recommendation — both criteria explicit (cost AND footprint gate):**

| Family | Pick | Cost (est.) | Footprint vs. gate | Card-edge status |
|---|---|---|---|---|
| 24-pin ATX | **Posts+header hybrid** (10–12 posts + 2×5 header) | $2.5–3.2 | Effective: clears; raw block ~1.2–1.4× (bench-elastic downward) | Commodity: FAILS gate (needs 3.7 A/mm, has 2.5). **Conditional alternate: Amphenol HPCE** (9 A/beam verified) IF pitch/price verify AND owner values tool-less swap + free sense fingers — premium |
| EPS 8-pin | **Posts+header hybrid, Shape A** (3+3/cable) — unchanged from §8.4 | $3.6–4.6 | Effective: clears (7.2 A/mm gate is unreachable by any card-edge surveyed) | FAILS gate outright |
| PCIe 2-port | **Posts+header hybrid, Shape A** (2+2/cable) | $2.9–3.5 | Effective: clears | FAILS gate (needs 5.4 A/mm) |
| PCIe 3-port | Same, ×3 | $4.3–5 | Same | Same |

There is no genuine two-way trade to present for EPS/PCIe — commodity card-edge cannot reach
their A/mm gates at any price, so the hybrid wins on all three axes (cost, footprint, ampacity).
The only live trade is on the **24-pin**: hybrid (smallest effective footprint, best ampacity,
cheapest, tool-required service) vs. HPCE card-edge (tool-less daughterboard swap, free
sense-return fingers, keyed slot — at premium cost and two UNVERIFIEDs). Stated as a trade, not
forced, per the owner's brief.

**New/changed bench items from this revision:** (i) the generic-post A/joint bench is now
**the load-bearing qualification for every family** (it was EPS-only in §8.4) — joint R, torque
+ thread-lock, thermal-cycle/vibration retention, at ≤30 °C rise; (ii) verify HPCE beam pitch +
100-qty price before treating the 24-pin alternate as real; (iii) the −12 V/PS_ON/PWR_OK/remote
sense pin-map onto the signal header needs the ATX rail-current check at spec time.
