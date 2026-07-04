# Section 2.8 revision — draft for owner sign-off (2026-07-04)

**STATUS: DRAFT ONLY. Nothing in this file is ratified.** No edit has been made to
`CEC-Platform-Ground-Truth-Spec.md`, any schematic, any board, `CLAUDE.md`, or
`docs/owner-queue.md`. This document proposes text that WOULD replace the affected paragraphs
of the spec's LOCKED Section 2.8, plus the owner decisions gating it. Sources:
`CEC-Platform-Ground-Truth-Spec.md` §2.8 (quoted verbatim below) and Document control;
`SYNTHESIS-beta-plan.md` §D-5a (owner ruling, 2026-07-04); `output-daughterboard-study-
2026-07-04.md` (engineering study); `atx24-output-interface-panel-2026-07-03.md` (prior panel)
— all three in `docs/standard-tier-review/`.

---

## 1. What changes, and why

The 2026-07-03 output-interface panel scored five candidate forms for the 24-pin module's
PSU-to-motherboard output (Form B short stub winning 100/120 over the LOCKED §2.8 incumbent
Form C at 83/120), but the owner left the call **open**, unsatisfied with any option as drafted
(`atx24-output-interface-panel-2026-07-03.md`, "STATUS: OPEN"). The next day the owner issued a
different ruling that supersedes the whole panel exercise for scope:

> **OWNER RULING (2026-07-04) — CONNECTOR DAUGHTERBOARD, scope 24-pin + PCIe + EPS output
> side:** instead of the board-mount male 90° output header, the main board carries an
> INTER-BOARD connector to a stood-up PASSIVE daughterboard (no components; minimal size,
> thick copper; all output pin-mapping/routing happens inside it), strain relief provided by
> the chassis ("we'll design that in"). The daughterboard is populated EITHER with a sourced
> PCB-mount VERTICAL header (owner sources from MODDIY — reputable) OR as a simple soldered
> pigtail at the through-holes. **OWNER ADDENDUM (same day):** the daughterboard assembly can
> itself be SOLD with an extension cable soldered at the through-hole points with strain
> relief — a productized daughterboard+extension assembly. (`SYNTHESIS-beta-plan.md` §D-5a)

This deletes the second board-mount output header (24-pin's J4) and the CEC-supplied
female-to-female bridging cable §2.8 currently mandates, replacing both with **main board →
inter-board connector → passive daughterboard → (vertical header | pigtail | sellable
daughterboard+extension assembly)**. It folds in the same-day design-basis numbers (§D-5a
"OWNER DESIGN-BASIS NUMBERS") and is gated on a kill-check — "per-circuit current through the
inter-board pair per family" — which `output-daughterboard-study-2026-07-04.md` ran and passed
(§7: "a real connector exists at the owner's margin-adjusted design bar for every family").

**12VHPWR is explicitly unchanged** — the ruling names only 24-pin, PCIe, and EPS; 12VHPWR's
captive soldered pigtail stands on its already-locked contact-degradation rationale
(re-confirmed by the owner 2026-07-03: "direct soldered pigtail CONFIRMED... no detachable
junction in that power path, period"). **Input side is unchanged on every module** — every
PSU-side board-mount male header (J3 on 24-pin, the per-cable input header on EPS/PCIe) is
untouched, and the spec's gender convention (board headers male, cable ends female) stands.

**A finding beyond the ruling's stated scope:** the LOCKED §2.8 text locks an output-side form
for the 24-pin and 12VHPWR — it does **not** lock one for EPS or PCIe. The as-built EPS/PCIe
boards carry a generalized version of the 24-pin's two-male-header pattern per cable
(`gen-module-pcb.py`'s shared template, per `CLAUDE.md`'s "Interposer-module PCB floorplans"
item), but that was never written into §2.8 itself. The 2026-07-04 ruling scopes EPS/PCIe into
the daughterboard change as though an existing lock already covered them — it did not. This
draft closes that pre-existing gap in the same pass (§2 adds explicit EPS/PCIe paragraphs)
rather than silently inheriting the unlocked assumption. Flagged for owner awareness, not a
blocker to sign-off.

---

## 2. Proposed replacement text

### 2.8 as currently LOCKED (quoted verbatim — this is what changes)

> ### 2.8 Module power-path connectors (PSU side): interposer cabling (LOCKED, repo v1.6; folded in v3.2)
>
> Separate from the universal RJ-45 module-to-Hub interface (Sections 2.1 to 2.7), each sensing module is a power-path interposer: PSU rail current enters the module, passes through its shunts, and continues to the load. The PSU-side connectors are module-specific (not universal) and are locked per module as follows.
>
> **24-pin ATX module, two male headers; female-to-female output cable required.** Gender convention for this spec: the board-mounted headers are **male** (pin-side), and a cable end that plugs onto a header is **female** (socket/receptacle), so the PSU's own 24-pin cable is the female inserting connector. The module carries two Molex Mini-Fit Jr (5569 family) 24-circuit **male headers**: one on the PSU side (input, J3) and one on the motherboard side (output, J4). No board-mount **female** 24-pin ATX receptacle exists as a standard part, so the module cannot present a female socket on either side; both connectors are therefore male, the same gender as the motherboard's own 24-pin header.
> - Input: the PSU's existing 24-pin cable (a female receptacle housing) plugs directly onto the module input header. No new cable is needed here.
> - Output: the motherboard's 24-pin connector is also a male header, so the module output (male) and the motherboard (male) cannot be joined by an ordinary PSU-style cable, which is female on only one end. The run from the module output to the motherboard requires a dedicated **female-to-female 24-pin ATX bridging cable**, a female receptacle on each end, since each end plugs onto a male header (the module output and the motherboard). No standard off-the-shelf product carries a female on both ends, so CEC must supply this cable as a platform SKU.
>
> **12VHPWR modules (Standard and Pro), connectors soldered to the board.** [unchanged — see §2 below]
>
> Hot-plug scope (added v3.8): [unchanged]
>
> **Kit-cable and custom-female-pigtail direction (D-1 partial, PROPOSED, v1.3.0; does NOT unlock this section).** [superseded — see below]

### 2.8 as PROPOSED (replacement, pending owner sign-off)

The intro paragraph is unchanged. Per-module paragraphs:

> **24-pin ATX module — input unchanged, output superseded by the connector-daughterboard
> architecture (PROPOSED, owner ruling 2026-07-04, D-5a; supersedes the v1.6 output form folded
> in v3.2).** Gender convention unchanged: board-mounted headers are **male** (pin-side); a
> cable end that plugs onto a header is **female** (socket/receptacle).
>
> - **Input (J3, PSU side): unchanged.** A Molex Mini-Fit Jr (5569 family) 24-circuit **male
>   header**; the PSU's existing cable plugs directly onto it. No new cable needed here.
> - **Output (motherboard side): superseded.** The module no longer carries a second
>   board-mount male header (J4) or a CEC-supplied female-to-female bridging cable. Output
>   rails instead cross an **inter-board connector** to a **passive daughterboard** — no active
>   or passive components beyond the connector body and its fan-out copper, sized to the
>   Section 6.4 current class, thick copper by design — stood off the main board and
>   mechanically secured (strain relief included) by the chassis. Populated EITHER with a
>   PCB-mount vertical female ATX header (customer's own cable plugs in) OR a soldered pigtail
>   at the same through-hole field, optionally as a sellable daughterboard-plus-extension
>   assembly (owner addendum, same ruling). Connector class, contact allocation, daughterboard
>   shape, and header-vs-pigtail default are OWNER DECISIONS — see §§3–4, OQ-86–89.
>
> **EPS 8-pin and PCIe 8-pin modules — output side now explicitly locked (PROPOSED; closes the
> pre-existing gap noted in Section 1).** Prior text did not lock an EPS/PCIe PSU-side
> connector form; the as-built boards generalize the 24-pin's paired-male-header pattern per
> cable. This entry brings EPS/PCIe under the same rule as the 24-pin, applied **per cable**:
>
> - **Input: unchanged.** A board-mount male Mini-Fit Jr header per cable; the PSU's cable
>   plugs directly onto it.
> - **Output: superseded**, identically to the 24-pin — one inter-board connector and one
>   passive daughterboard **per cable** (not one wide daughterboard spanning every cable — see
>   decision box (b)), each sized to that cable's own current class (Section 6.4).
>
> **12VHPWR modules (Standard and Pro) — UNCHANGED.** Connectors remain soldered directly to
> the board (no detachable pass-through header, no bridging cable, no daughterboard); explicitly
> OUT OF SCOPE for the 2026-07-04 ruling — the melt-prone-connector / contact-degradation
> rationale for a captive soldered joint, re-confirmed by the owner 2026-07-03, stands
> unrevised. [Sideband pass-through and soldered-joint strain-relief text: unchanged.]
>
> Hot-plug scope (added v3.8): unchanged — the PSU-side power path, daughterboard included, is
> not hot-pluggable under load.
>
> **Kit-cable and custom-female-pigtail direction — SUPERSEDED.** The D-1 custom-female-pigtail
> direction (a female pigtail that would "effectively create a board-mount female header") is
> realized here as the daughterboard's soldered-pigtail option, not a retrofit onto the old
> male-J4 form it was weighed against. Original note preserved for provenance in Section 11.

---

## 3. Design-basis block (owner numbers, 2026-07-04)

Owner-stated, `SYNTHESIS-beta-plan.md` §D-5a "OWNER DESIGN-BASIS NUMBERS":

- **EPS 8-pin:** 4×12V + 4×GND, **~13 A continuous per pin** sustained (brief transients run
  higher) → sustained worst case **~52 A/cable**.
- **PCIe 8-pin:** same ~13 A/pin theoretical, only 3×12V pins → sustained worst case
  **~39 A/cable**.
- **Intel EPS12V rationale:** official EPS12V spec is 336 W (~28 A)/connector; modern boards
  run **two** EPS connectors because next-gen CPUs approach ~600 W and that load must split
  across two — cited by the owner as why a single connector's official rating is not the
  platform's own per-cable design ceiling.
- **24-pin ATX:** anchor on the **6 A/circuit ATX bar** (panel convention), not the OQ-11 shunt
  figures, used only as a cross-check (study §1).
- **Design rule (owner):** design to worst case **with margin**, but keep **transients as
  transients and sustained as sustained** — never fold a transient peak into the continuous
  rating; validate transient survival separately. All figures AWG-dependent; CEC's own
  extensions use 16 AWG.

---

## 4. Owner decision boxes

Each states the study's recommendation where one exists. None is ratified.

**(a) Margin policy.**
[ ] Ratify: connector **continuous rating ≥125% of sustained worst case, at ≤30 °C rise**
(study-recommended, §1) — 30 °C matches this repo's own electrothermal-gate convention
(12VHPWR thermal re-validation, `CLAUDE.md` action item 4). Under this policy: EPS ~65 A, PCIe
~49 A; 24-pin per-rail (cross-checked against OQ-11 shunt design currents, taking the higher of
the two bases per rail) 12V 20 A / 5V 37.5 A / 3.3V 30 A / 5VSB 7.5 A. **Not yet ratified**
(study §7).

**(b) Daughterboard shape — per-cable vs. one-wide-per-board.**
[ ] Ratify: **Shape A, per-cable** (study-recommended, §6) for EPS and both PCIe SKUs (moot for
24-pin, already "one wide" by ATX convention). Per-contact ratings derate further as more
contacts populate one housing (mutual heating — e.g. Samtec's published curve, 18 A
single-contact down to ~9 A at 10 populated), so Shape B's lower-looking contact count is
misleading — its true margin is worse than Shape A's. Shape B also breaks fault isolation (one
connector-body defect risks every cable at once) and cuts against the sellable-assembly
addendum (no independent per-cable swap on a shared board). Shape B's one real edge — fewer
chassis cutouts — is a mechanical/BOM trade, not a current-capacity argument.

**(c) Inter-board connector default class — COST PASS LANDED (study §8, 2026-07-04); ratify
the per-family picks below.**
[ ] Ratify the electrical bar: **~30 A per power contact at ≤30 °C rise** at the study's
contact counts (unchanged), AND pick from the study §8.6 three-way (commodity card-edge is
ELIMINATED by the footprint gate — §8.5: ~2.4–2.5 A/mm at any pitch vs 3.7–7.2 demanded;
premium blades stay demoted at $13–26/module, MCN51 OBSOLETE):

**§8.6 REVISED PICKS (owner sourcing pass, 2026-07-04):**
- **EPS + PCIe: RATED screw-in board-to-board terminals** — Würth REDCUBE WP-THRBU
  74650094 (M4 through-hole bushing: conductor + standoff + threaded retention in ONE
  part), **85 A VERIFIED at datasheet conditions, $2.86 @100, in stock** — 2 per cable +
  a small signal stub. ~$12–19/module. **This DELETES the load-bearing M3-joint bench
  item** (reduces to incoming QC + torque process control). Smallest footprint, screws =
  chassis retention, quality-first delta over generic M3 stated in the study.
- **24-pin: pursue HPCE vertical/mezzanine** (~$7–10; ONE part carries power AND the
  PS_ON/PWR_OK/−12V/sense circuits — deletes the signal header; tool-less). Gate
  re-derivation at real pitch (dual-edge 2.54 mm ≈ 7.1 A/mm): 24-pin CLEARS (~35–40 mm vs
  51.6 gate); PCIe MARGINAL; EPS FAILS ~1.4×. Two UNVERIFIEDs stand: beams-per-position
  mapping (image-encoded datasheet) and right-size SKU supply (the one orderable-now
  vertical SKU, 10114587-003LF $9.15/230-stock, reads ~144 A vs the 190 A need; R/A SKUs
  are tray-MOQ-1080/zero-stock/12-wk). Card fingers need 30 µin hard gold.
  **Committed fallback: REDCUBE 6-point** ($18–19/module).
- **Generic M3 hardware demoted** to an optional cost-down AFTER a bench derivation
  ($2.5–5/module; 20–30 A/joint UNVERIFIED estimate) — no longer the pick.
- HONEST COST PICTURE vs the original ~$5 ceiling: verified-ampacity terminals land at
  $12–19/module. The cheap number ($2.5–5) exists only bench-gated. The owner chooses
  which side of that trade each family sits on (quality-first principle: surface the
  delta, default to quality).

| Family | Power contacts per polarity | Basis |
|---|---|---|
| EPS (per cable, Shape A) | **3** | 65 A target ÷ 30 A/contact, rounded up |
| PCIe (per cable, Shape A) | **2** | 49 A target ÷ 30 A/contact, rounded up |
| 24-pin, per rail (+ matching GND) | 12V 2 / 3.3V 3 / 5V 4 / 5VSB 2 | scaled from the study's §2 footnote (12V baseline ×1.5 for 3.3V, ×1.9 for 5V); **derived, approximate**, ~16–20 contacts total across power+GND |

GND sized to match source-contact count per rail, not a thinner shared return (study §1).

**(d) MODDIY vertical female header status.**
[ ] Ratify: **prototype-approved; sellable-BOM pending bench qualification.** MODDIY's
"MIATX-PCB" (SKU CO261) is a confirmed, orderable PCB-mount vertical female across
24-pin/EPS/PCIe (study §3) — but carries **no manufacturer name, no MPN, no datasheet, no
published current rating**, the same provenance-UNVERIFIED DIY category the 2026-07-03 panel
already disqualified for the sellable BOM ("Option F provenance update"). Flipping §2.8's old
"no board-mount female part exists" premise here needs the panel's own prescribed battery —
pull force, mating-cycle life, current-rise, plating trend — none run yet; usable today for
bring-up samples only.

**(e) Sense-return contact option.**
[ ] Decide: ship now / later / not at all, at what granularity (study §5, not resolved there).
Proposal: one extra low-current signal contact per sensed rail, wired from the daughterboard's
output copper (downstream of the mated joint) to a resistor divider **on the main board**
feeding a spare ADC — zero added components on the daughterboard (same pattern as Hub
Standard's MAIN_5V_SENSE/5VSB_SENSE dividers). **Catches** a slowly degrading joint (rising
contact resistance grows ΔV between the existing shunt-side sense and this downstream tap at
constant load current). **Can't catch** a single failed contact among parallel contacts on one
rail (shared-node tap sees the lumped result), sudden disconnection (already DETECT-covered),
or a true differential Kelvin read (single-ended tap conflates rail-/return-side resistance —
full Kelvin needs a downstream GND-side tap too, doubling contacts, an open cost/value call).

**(f) Chassis strain-relief numbers.**
[ ] Owner to supply: pull force (N) and flex-cycle count for the chassis-provided strain relief
the ruling assigns ("we'll design that in"). Placeholder: the panel's qualified target for this
joint class, **≥90 N pull, ≥500-cycle flex** (bench question 1) — derived for a
*daughterboard-local* potted bar (study §4); the ruling moves relief to the chassis instead,
which may lower the daughterboard's own joint load, but default to the same floor until the
chassis spec exists.

---

## 5. New OQ proposals (continuing from OQ-85; PROPOSED)

**OQ-86: Inter-board connector MPN lock (24-pin / EPS / PCIe output daughterboard).** Lock the
platform connector family/MPN per the LANDED cost pass (study §8.4: card-edge for 24-pin/PCIe,
screwed power posts for EPS; premium blades demoted to qualified fallback), gated on the box-(c)
qualification debt (slot-rating provenance, paralleled-finger current-sharing bench at 30 °C
rise, ENIG-vs-hard-gold, post torque/thermal-cycle bench) and ratifying the margin policy (4(a))
and daughterboard shape (4(b)) that set contact count.
See `output-daughterboard-study-2026-07-04.md` §2, §7, §8.

**OQ-87: Daughterboard mechanical and chassis interface.** Define stand-off/mounting geometry,
keying/captivation against mis-seat, stack height under the enclosed-product boundary (couples
to J1/J2, `beta-lock-register-2026-07-03.md` §J), and the box-(f) strain-relief numbers.
Interacts with OQ-86 (connector stack height).

**OQ-88: Bench-qualification protocol for the daughterboard build.** Define the qualification
battery for (1) the inter-board connector once OQ-86 narrows candidates (pull force,
mating-cycle life, thermal rise at rated current) and (2) the MODDIY-class vertical female
header if box (d) moves toward sellable-BOM use. Neither battery has been run.

**OQ-89: Sellable daughterboard-plus-extension assembly SKU definition.** Define the SKU(s):
per-family count (24-pin ×1, EPS ×2, PCIe ×2 or ×3, per Shape A), length/gauge/strain-relief
spec (parallel to D-7's 12VHPWR pigtail SKU work), color/sleeving options, and whether it
replaces or supplements the D-1 kit's cable-SKU count. Retirement of the LOCKED-today F-F
24-pin bridging-cable SKU (superseded above) is a direct consequence, recorded here, not
silently dropped.

**Effect on OQ-82 if signed:** moves from open-at-the-architecture-level to **resolved at the
architecture level** by the 2026-07-04 ruling, superseding the panel's Form A–E menu; remaining
sub-questions continue as OQ-86–89. This draft does not itself edit OQ-82's text.

---

## 6. Impact table

**No board, schematic, library, `CLAUDE.md`, or `docs/owner-queue.md` file is touched by this
draft.** Below is what happens only after sign-off, so the downstream scope is visible first.

| Area | Directory / file | What changes, if ratified |
|---|---|---|
| 24-pin ATX module | `modules/atx-24pin/` | Remove J4; add inter-board connector + daughterboard project; rev3 scope grows (D-5/D-5a critical path) |
| EPS / PCIe modules | `modules/eps-8pin/`, `modules/pcie-8pin-2port/`, `modules/pcie-8pin-3port/` | Remove per-cable output headers (J_OUT*); add per-cable inter-board connector + daughterboard sites (Shape A, pending 4(b)); rides the W6 routing wave already queued |
| 12VHPWR (Standard, Pro) | `modules/12vhpwr-standard/`, `modules/12vhpwr-pro/` | **No change** — out of scope |
| Daughterboard artifacts, fab, enclosure | new dir TBD; `fab/<board>-*`; J1/J2 work (`beta-lock-register-2026-07-03.md` §J) | Repo-layout decision not made here; fab output follows the existing beta-naming convention once a board exists; enclosure gains the stand-off/keying/strain-relief interface (OQ-87) |
| D-1 kit SKUs | `SYNTHESIS-beta-plan.md` §D-1 | LOCKED-today F-F 24-pin bridging cable retired/replaced by the daughterboard+extension assembly (OQ-89); JST 5VSB Hub-feed cable unaffected |
| Ground-truth spec | `CEC-Platform-Ground-Truth-Spec.md` §2.8, §10, §11 | The actual edit this draft proposes — not made until sign-off |
| `CLAUDE.md`, `docs/owner-queue.md` | — | Both need their own follow-up updates once ratified (not touched here) |

## Version-bump proposal

**Proposed: v1.3.0 → v1.4.0 (MINOR), not v2.0.0 (MAJOR).**

The spec's versioning rule (Document control) reserves MAJOR for a change that "breaks a
connector pinout, a wire protocol, an interface, or cross-tier compatibility." A literal reading
could call this MAJOR — it does redefine a LOCKED connector interface. Case for MINOR:

1. **Direct precedent, alpha/beta lineage preserves compatibility.** v1.3.0 changed a physical
   connector arrangement (Hub Standard's two 2-pin feeds consolidated into one 3-pin JST
   S3B-XH-A, §2.7/§2.9) as a MINOR bump — beta-lineage beside a preserved alpha, not a break to
   cross-tier compatibility. This revision lands the same way: nothing existing "breaks," since
   the F-F-bridging-cable form was never fielded at the daughterboard's expense.
2. **Cross-tier interface untouched; stays PROPOSED.** Scoped entirely to the PSU-side
   power-path interposer connectors — separate, in the spec's own words, "from the universal
   RJ-45 module-to-Hub interface"; no pin, DETECT, or CAN change. Section 4's boxes and Section
   5's OQs are unresolved, so MINOR also matches how this document has always folded a PROPOSED
   architecture into a controlled baseline (v1.1.0 Appendix D, v1.2.0 §13, v1.3.0 itself).

Proposed Section 11 entry text (for insertion upon sign-off, not inserted here):

> **1.4.0 (TBD, controlled).** OUTPUT-SIDE CONNECTOR-DAUGHTERBOARD ARCHITECTURE. Supersedes the
> v1.6 §2.8 output form (two board-mount male headers plus a CEC-supplied female-to-female
> bridging cable) for the 24-pin ATX, EPS 8-pin, and PCIe 8-pin (2-port, 3-port) modules: output
> rails now cross an inter-board connector (class pending a cost pass) to a passive
> daughterboard (no components, thick copper), chassis-strain-relieved, populated with a
> vertical female header or soldered pigtail, optionally sold as a daughterboard-plus-extension
> assembly (owner ruling `SYNTHESIS-beta-plan.md` §D-5a, 2026-07-04; study
> `output-daughterboard-study-2026-07-04.md`). Also closes a gap: EPS/PCIe output connectors,
> previously unlocked by §2.8, are now specified under the same rule, per cable. 12VHPWR
> unchanged (captive soldered pigtail); input-side connectors on every module unchanged. New
> OQ-86 through OQ-89; OQ-82 resolved at the architecture level. Range extended to OQ-1–89.
