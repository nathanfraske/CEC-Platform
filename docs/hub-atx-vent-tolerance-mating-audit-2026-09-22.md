# Hub / ATX vent, tolerance and mating audit - 2026-09-22

## Decision

**Later repair:** the [dead-bug contact repair](hub-atx-deadbug-contact-repair-2026-09-22.md)
corrects all 18 contacts in a separate mechanical pair and integrates the contact
check and whole-stack fabrication withholding. The input-specific findings below
are retained as the before-state. Access and full assembly qualification remain open.

**Do not release the stack yet.** The accepted two-cap planar clearance proposal
is still useful and need not be discarded. A 22 mm board-face gap has plausible
vent and insertion margin. However, the native mating arrays fail, the existing
origin-only checker falsely passes them, four access envelopes fail, and several
actual production tolerances are not specified. No active ECAD, BOM, copper,
standoff or stack-contract file was changed by this audit.

This is a calculation and native-geometry audit, not a physical assembly test.

## Bound inputs and tests

- ATX clearance candidate:
  `build/atx-two-cap-clearance-20260921/ATX-two-cap-clearance-PLACEMENT-ONLY.kicad_pcb`,
  SHA256 `13e9728d04c008ae8bead8a57314a7c5c7d8dad6c7377b940a922fa6f194d121`.
- Retained Hub:
  `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`,
  SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
- The capacitor positions and other proposed Hub translations are from
  `build/hub-two-cap-fit-20260921/fit-result.json`. The two caps are a proposed
  ECO; the retained native Hub still contains its old single C1. Do not confuse
  the proposed 17 mm cap envelope with the old native part's 21 mm height.
- Both retained source hashes and hierarchy signatures were rechecked; the
  accepted ATX candidate hash was checked before and after the audit.
- Receipt: `build/hub-atx-stack-qualification-20260922/screen.json`.
- Read-only driver: `tmp/check_hub_atx_stack_20260922.py`.
- New board-independent diagnostic library: `scripts/cec_stack_fit_screen.py`.
- `PYTHONPATH=scripts .venv/bin/python -m pytest -q tests/test_stack_fit_screen.py tests/test_assembly_access.py`:
  **25 tests pass**. Synthetic tests reject aligned origins with mirrored contact
  errors, wrong net roles, duplicated IDs, affine scaling used to fake mating,
  over/under-insertion and unknown dimensional bounds. These are diagnostic
  screens, **not an integrated production release gate**.

## 1. Vent clearance: conditional geometric pass, not supplier qualification

The [Lelon 2017 application guide](https://www.lelon.com.tw/upload/guides/149628798151.pdf),
printed page 8, explicitly specifies **3 mm minimum pressure-relief clearance
for 18-35 mm diameter cases**. The complete relevant page and table were visually
reviewed. The current [2026 catalog](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf),
printed page 85, repeats the vent-clearance instruction but omits the numeric
table in the reviewed published PDF. The 3 mm value is therefore a documented
manufacturer **historical screening requirement**, not newly confirmed current
VZH approval. Obtain current confirmation for VZH472M1CTR-1816 before release.

For the accepted 17 mm maximum-height capacitors and a 22 mm nominal gap:

- Nominal space to bare opposing ATX: **5 mm**.
- Margin over the historical 3 mm vent requirement: **2 mm before assembly
  seating, local board bow, gap variation and other tolerances**.
- One proposed acceptance allocation is local board-face separation
  **21.5-22.5 mm everywhere relevant**, plus **0-0.2 mm cap seating lift**.
  Under those assumptions minimum free space is **4.3 mm**, or **1.3 mm margin**.
  Those numbers are proposed assembly limits, not measured production bounds.

The 1.2 mm lateral component guard remains clear in the accepted ATX candidate.
The current candidate has no front-side pour outlines intersecting the projected
can disks; it is unrouted and unfilled, so this is not final copper/mask evidence.
Lelon also warns against wiring/circuitry over the vent. Keep its discharge path
unobstructed and review final traces, exposed copper, coatings, housing and wiring;
do not treat a footprint-only rule area as a complete vent-safety certificate.

Local gap is not guaranteed merely by buying a nominal 22 mm spacer. Board
flatness after assembly, support placement, clamp loading and seating matter.
The [JLC warpage discussion](https://jlcpcb.com/blog/prevent-pcb-warping) explains
why nonzero bow/twist must be considered; it is not a contractual guarantee that
this assembly meets the proposed +/-0.5 mm local-gap allocation. No arbitrary
global bow percentage has been converted into an asserted local clearance.

## 2. Z engagement: 22 mm is plausible; the existing 18 mm hardware is not

The [Samtec TSW series print, revision DS](https://suddendocs.samtec.com/prints/tsw-xxx-xx-xxx-x-xx-xxx-mkt.pdf),
sheets 2 and 6, gives lead style -17 a **0.620 inch post**, with explicit
**+/-0.008 inch** post tolerance. That is **15.748 +/-0.2032 mm**. Header body
height is 0.100 inch / 2.54 mm **REF**, not an independently toleranced limit.

The [SSQ series print, revision BH](https://suddendocs.samtec.com/prints/ssq-1xx-xx-xxx-x-xx-xxx-xx-x-mkt.pdf),
sheet 1, gives socket body height **0.335 inch / 8.509 mm REF**. Its general
title-block tolerance must not silently be applied to a reference dimension.
The [SSW/SSQ catalog](https://suddendocs.samtec.com/catalog_english/ssw_th.pdf)
specifies **3.68-6.35 mm insertion**. All connectors are assumed properly seated
on the inward PCB faces; floating a connector is not a permitted workaround.

Nominal insertion = 15.748 + 2.540 + 8.509 - local board gap = **26.797 - gap**.

| Nominal gap | Nominal insertion | Cap-to-bare-PCB space | Screen |
| --- | --- | --- | --- |
| 18 mm | 8.797 mm | 1 mm | Over-insertion and insufficient vent clearance |
| 21 mm | 5.797 mm | 4 mm | Nominally inside insertion range |
| 22 mm | 4.797 mm | 5 mm | Nominally inside insertion range |
| 23 mm | 3.797 mm | 6 mm | Only 0.117 mm nominal under-insertion margin |

The drawing post tolerance alone consumes 0.2032 mm of insertion allowance.
The following is a **proposed tolerance allocation**, not supplier certification:

| Term | Proposed bounded input |
| --- | --- |
| Local inward PCB face gap, including bow/support effects | 21.5-22.5 mm |
| Header housing height variation | +/-0.1 mm, requires supplier bound |
| Socket seat-to-mouth height variation | +/-0.1 mm, requires supplier bound |
| Header post tolerance | +/-0.2032 mm, explicit print dimension |
| Header and socket seating lift | 0-0.1 mm each, requires assembly process control |
| Capacitor seating lift | 0-0.2 mm, requires assembly process control |

Interval arithmetic gives insertion **3.8938-5.9002 mm**, leaving **0.2138 mm**
to under-insertion and **0.4498 mm** to over-insertion. This is feasible but
not unlimited margin. The vendor-bound calculation intentionally remains
`complete=false` while REF housing and assembly bounds are unavailable.

The existing mechanical contract still specifies **18 mm / M2.5** hardware:
Harwin R25-1001802 and a 2.7 mm lug hole. The [actual Harwin product](https://www.harwin.com/products/R25-1001802)
confirms that identity. It is neither a 22 mm spacer nor the owner's intended
M2 hardware. Select the exact M2 support/screw/washer stack and engagement depth
together; do not substitute a new scalar while leaving the old BOM/holes.

## 3. X/Y mating: fails, independently of capacitor choice

The assembly datum fit is x_ATX = 86 - x_Hub, y_ATX = y_Hub + 9.8 mm.
The contact-level readback finds:

| Connector | Contacts with no geometric mate within 0.05 mm | Maximum same-number offset |
| --- | --- | --- |
| J6P | 4 / 6 | 10.16 mm |
| J6C | 6 / 8 | 15.24 mm |
| J6D | 2 / 4 | 5.08 mm |

The 0.05 mm criterion is a **CAD registration check**, not a qualified allowance
for PCB drilling, contact float, pin sway or manufacturing variation.

![Native contact mismatch](../build/hub-atx-stack-qualification-20260922/contact-registration.png)

Root cause: the vendored socket footprints use the same numbered pad-array
handedness as the headers. The generator/checker mirrors the footprint origin
and rotation, but does not reflect the entire numbered contact pattern. Pin 1
and pin 2 align while subsequent columns run the wrong way. In-plane rotation
alone cannot reconcile the handedness of all correspondingly numbered contacts.
This does not mean the Samtec parts cannot mate; it means the current PCB
placement/pin mapping has not implemented that mating correctly.

`cec_constraints._chk_mezzanine_segment_contract` returned **True on both
native boards** during this replay. It compares origin, angle, footprint token
and pin-role list separately. Its assumption that those checks imply physical
coincidence is false. The separate schematic electrical audit likewise checks
pin roles, not paired physical registration. This explains the false confidence;
zero single-board placement DRC never proved an assembled pair.

A diagnostic reflection of each socket field makes all same-number contacts
coincident, but it introduces Hub courtyard conflicts: J6P with C10, J6C with
RJ45 J2, and J6D with RJ45 J4/J5. No such change was applied. The fix needs a
**joint header/socket placement and pin-map solve** with the capacitor reserves,
ports and force-bus constraints retained, not a blind footprint flip or larger
board gap. Samtec's [recommended SSQ PCB layout](https://suddendocs.samtec.com/prints/ssq-1xx-xx-xx-x-xx-xxx-xx-xx.pdf)
confirms pitch/hole arrangement but does not approve this project's logical
numbering; an explicit contact correspondence table is still necessary.

## 4. Other mating/tolerance findings

- **Four access failures** against the current 80 mm Hub contour: TB6 and TB9
  have only 0.105 mm top clearance versus the existing 1.2 mm requirement;
  J_SIG1 has -6.315 mm and J3 -5.195 mm signed clearance (overlap). These are
  courtyard/access failures, not automatically confirmed body collisions.
  The old contract's 74 mm Hub comments cannot certify the present 80 mm board.
  Check bodies, plug/latch/tool swept volumes and the owner requirement for
  headers outside the Hub; do not grow the boards automatically.
- **Outward socket tails:** SSQ -03 uses a nominal 10.0076 mm solder tail. Both
  native PCBs are 1.6 mm thick, leaving approximately **8.41 mm outside the Hub**
  before solder/process tolerance. This does not increase internal stack height.
  Evaluate a suitable shorter-tail socket variant, e.g. -01's 2.64 mm nominal
  tail, instead of undocumented trimming; qualify solder protrusion/process first.
- **Hole qualification:** native mezzanine holes are 1.00 mm; Samtec's recommended
  SSQ layout specifies 1.02 mm. This small nominal difference is not by itself
  proof of failed fit, but finished-hole tolerance, square pin envelope, plating
  and solder process must be reconciled rather than assumed compliant.
- **Lateral tolerance is still unqualified:** the TSW print allows up to 2 degrees
  post sway; 15.748 mm times tan(2 degrees) is about 0.55 mm tip displacement.
  This is not a demand to allocate that independently in every axis, but it shows
  why ideal pad coincidence is not proof of self-alignment. Contact capture,
  hole/seat true position and simultaneous insertion of three rigid fields need
  a drawing-based tolerance chain and assembly fixture/sample check.
- **3D model coverage:** all six native mezzanine footprints have zero model
  instances. A render with no visible connector collision cannot establish fit.
- **RJ45/body and cable clearance:** intersecting opposing courtyards identified
  previously remain unresolved. The exact supplied jack drawing revision, mating
  plug/latch envelope and adjacent ATX JST/USB assemblies still need body-level
  checks. Low-profile opposite parts must not be assumed height zero.

## Bounded next repair sequence

1. Correct the physical contact correspondence/handedness and derive joint
   connector seats from complete contact geometry; integrate the new paired
   checker into admission before regenerating routes. Preserve the existing
   ATX cap-clearance candidate as an immutable baseline.
2. Select/document the M2 support and screw stack; obtain connector REF-dimension
   and current VZH vent confirmation. Establish measurable local-gap and seating
   limits instead of claiming proposed allocations are factory guarantees.
3. Recheck access, jack bodies, tails, masks and vent discharge paths on the
   jointly repaired pair; then route, DRC, and qualify a physical fit sample.

No messages were sent to suppliers, parts ordered, active production policies
changed, or repaired assembly claimed in this audit.
