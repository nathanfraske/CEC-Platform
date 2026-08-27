# Standard Beta bolted right-angle output-interconnect feasibility

> **Supersession note (2026-08-12):** this feasibility study records the
> pre-selection trade space. The later
> `standard-xfcn-terminal-integration-handoff-2026-08-12.md` is the prototype
> implementation authority. The TE blade scheme remains the production
> fallback until that handoff's owner-ratification and qualification gates pass.

**Date:** 2026-08-12  
**Decision status:** Planning research updated; no connector architecture change made.  
**Bottom line:** A one-bolt-per-polarity direct right-angle joint is mechanically
real and available in properly documented 100 A to 240 A catalog families. A
100 A part is sufficient for both the 65 A EPS and 48.75 A PCIe connector
targets. The problem is sourcing and system cost, not current capability: the
credible parts found are press-fit parts outside the normal JLCPCB assembly
flow, while the inexpensive LCSC-stocked SAMZO part is only rated 60 A and has
insufficient joint documentation for production adoption.

## 1. Scope and meaning of "current"

The PCB files below are the authorities declared by
`scripts/cec_beta_manifest.py` on 2026-08-12. Generated or historical boards
were not substituted for them.

| Product | Manifest-current main PCB | Manifest-current daughterboard |
|---|---|---|
| ATX 24-pin rev3 | `beta/atx-24pin-rev3/24pin-module.kicad_pcb` | `beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_pcb` |
| EPS 8-pin rev3 | `beta/eps-8pin-rev3/eps-8pin-rev3.kicad_pcb` | `beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_pcb` |
| PCIe 2-port | `beta/pcie-8pin-2port/candidate/pcie-8pin-2port-candidate.kicad_pcb` | `beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb` |
| PCIe 3-port | `beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_pcb` | Same per-cable PCIe daughterboard |

This inspection is a connector-envelope and electrical-rating study. It does
not sign off routing, board fabrication, or assembly.

## 2. Current-layout facts that constrain the answer

The live files do not presently describe a complete, mutually mateable blade
system across the line:

| Product | What is actually in the manifest-current PCB | Consequence |
|---|---|---|
| EPS | 96.1 x 40.1 mm outline; two Molex 87427 right-angle output headers at `(43.44, 38.20)` and `(65.16, 38.20)`. There is no main-board blade field. The separate 28.6 x 20.1 mm EPS daughterboard has six TE 63951-1 tabs at 4.7 mm pitch. | A bolted interface would be a redesign, not a footprint substitution. Four high-current sites, two per cable, fit the available output-edge length in principle. |
| PCIe 2-port | 86.6 x 47.7 mm outline; twelve TE 63969-1 receptacles, six per cable. Each cable field spans 23.5 mm at 4.7 mm pitch. The 31.1 x 20.1 mm daughterboard has six TE 63951-1 tabs at 5.2 mm pitch. | This is the only live main PCB with a blade field, but its 4.7 mm pitch does not match the live daughterboard's 5.2 mm pitch. The interface already requires correction. Two 16 mm-wide bolt terminals per cable need about 32 mm plus clearance, so expect a small daughterboard-width increase and local main-board component moves. |
| PCIe 3-port | 103.5 x 56.1 mm outline; three legacy Molex 45586 right-angle output headers. There is no main-board blade field. | A bolted interface is feasible only as a new placement. Six 16 mm terminals consume about 96 mm before inter-cable clearance, approximately the full board width. |
| ATX 24-pin | Ten TE 63969-1 receptacles are present, but there is no valid `Edge.Cuts` outline. `TB1` is at `(157.40, 56.00)` while `TB2` through `TB10` form a separate row around `y = 74.39`; their rail order also does not match the live daughterboard row. The 61.1 mm-wide daughterboard has ten tabs at 4.2 mm pitch. | Neither the existing blade pair nor a replacement can be called layout-feasible from this file. A five-terminal 60 A scheme would require about 80 mm in one row, larger than the present daughterboard even before the signal connector. |

Accordingly, "fits the current layout" means **credible with bounded local
redesign** for PCIe 2-port, **new interface placement** for EPS/PCIe 3-port, and
**not yet decidable** for ATX 24-pin.

## 3. Electrical sizing basis

The platform's existing rule requires connector continuous rating of at least
125% of sustained worst-case current. The stored design basis is 52 A sustained
per EPS cable and 39 A sustained per PCIe cable:

| Cable | Sustained design basis | 125% connector target per polarity |
|---|---:|---:|
| EPS 8-pin | 52 A | 65.00 A |
| PCIe 8-pin | 39 A | 48.75 A |

The current TE 63969-1 receptacle is treated in the project at 22.9 A per joint,
so three joints per polarity provide 68.7 A. That explains the current six-site
per-cable blade field.

For ATX, the present allocation is based on 6 A per ATX circuit. Consolidating
same-voltage contacts into one terminal gives five electrical nodes: `+12V`,
`+5V`, `+3V3`, `+5VSB`, and common `GND`. A single 60 A ground terminal is only
acceptable if the simultaneous rail envelope remains at or below 48 A; the
currently documented approximately 36 A sum does, but that operating envelope
would have to remain explicit.

## 4. What the perpendicular bolted joint actually is

For a purpose-designed right-angle power element, the intended stack is:

1. The metal power element is press-fit or soldered into the horizontal main
   PCB at its edge. Its threaded axis points horizontally toward the upright
   daughterboard.
2. The daughterboard has a clearance hole aligned to that thread and a defined
   high-current copper clamp land. The screw passes through the daughterboard
   and threads into the metal power element.
3. A manufacturer-approved washer/spring-washer stack and controlled torque
   clamp the daughterboard current land to the terminal face. The metal face to
   copper land is the separable current joint; the screw primarily supplies
   clamp force.
4. A bracket, card guide, or standoff fixes the 90-degree board relationship and
   takes cable insertion and handling loads. The current terminal should not be
   treated as the daughterboard's only hinge or structural support.

This is not permission to put a clearance hole through an ordinary copper pour
and tighten a screw against unsupported FR-4. The clamp-land geometry, exposed
finish, washer stack, torque, and any copper backer or compression limiter must
be designed as a contact system. Würth explicitly identifies its WP-RATR family
for high-current board-to-board connections and angled PCB assembly, and gives
the 7461101 a 0.5 N*m tightening torque. That is the correct mechanical class.

There are three useful variants:

- **Threaded right-angle element:** screw through the daughterboard into the
  element. This is the simplest direct implementation for this project.
- **Clearance-hole right-angle element:** a bolt passes through both the
  daughterboard and the terminal and is retained by a nut. This avoids a small
  internal thread but needs rear tool access.
- **Two vertical terminals plus a bent copper link:** each board receives a
  cheap vertical power element and a separate L-shaped copper strap connects
  them. LCSC has many suitable vertical terminals, but this is no longer a
  single-component joint and adds a custom busbar, two fastener stacks, and
  more assembly labor.

## 5. Candidate parts

Inventory and prices are snapshots from LCSC or the cited distributor on
2026-08-12 and must be refreshed at order time.

| Part | Form and rating | Sourcing snapshot | Engineering disposition |
|---|---|---|---|
| [SAMZO 1216120350M6, C39833008](https://www.lcsc.com/product-detail/C39833008.html) | Direct right-angle, six THT legs, M6, 16 x 12 mm PCB envelope, 60 A, brass/tin, -25 to 85 C | 100 shown in stock; $0.7927 at 100, $0.7324 at 500, $0.7048 at 1,000 | **Best PCIe cost candidate.** One per polarity meets 48.75 A. It misses the EPS 65 A target by 5 A. Published evidence is thin: no usable torque, contact-resistance, temperature-rise, current-derating, or bolted-PCB-stack qualification was found. Treat 60 A as a screening rating, not production proof. |
| [Keystone 8199, C3029551](https://www.lcsc.com/product-detail/C3029551.html) | Horizontal screw terminal, six THT legs, 6-32 thread, 30 A | 20 shown in stock; $0.7423 at 100, $0.6962 at 500, $0.6746 at 1,000 | Exact mechanical class, but too low in current to reduce EPS contact count and physically bulky when multiplied. Manufacturer confirms 30 A. Not worthwhile. |
| [Würth 74622103 WP-RAFE](https://www.we-online.com/en/components/products/REDCUBE_PRESS-FIT_RIGHT_ANGLED_EDGE_POSITION) | Edge-position right-angle press-fit, M3, 7 mm wide, six pins, 130 A at 20 C, 0.5 N*m torque | No LCSC listing found. Mouser showed 1,148 in stock; $3.23 at 100, $3.05 at 250, $2.88 at 500 | **Best documented direct candidate.** One per polarity meets EPS and PCIe. Compact and cheaper than the other documented families, but not cost competitive with blades and requires a controlled press-fit process. |
| [Würth 7461101 WP-RATR](https://www.we-online.com/en/components/products/WP-RATR_TWO-ROWS) | Right-angle press-fit, M3, 7 mm wide, six pins, 100 A, 0.5 N*m torque; explicitly specified for wire-to-board and board-to-board use | No LCSC listing found. Mouser showed 11,640 in stock; $4.32 at 100 and $3.76 at 500 | **Clearest answer to the proposed geometry.** One per polarity meets both targets. Active with a stated production lifetime over ten years, but costs more than WP-RAFE. |
| Würth 7461063 / 7461103 / 7461106 WP-RATR | Same direct family in 160 A M4, 160 A M5, and 240 A M6 threaded versions, 9 mm or 13 mm wide | Active manufacturer catalog; no LCSC listing found | Confirms that current capability is not the limitation. These are unnecessary electrical overkill unless the final mechanical stack needs the larger thread or contact face. |
| [TE/ERNI 225701-E PowerElement](https://www.te.com/en/product-225701-E.html) | Right-angle M5 press-fit power tap, 16 PCB pins, 160 A | TE calls it active but not currently available; no useful LCSC or authorized-distributor stock found | Electrically and mechanically suitable as a second-source class, but its present availability makes it a poor production selection. |
| [Amphenol PwrMAX Ortho 10132640-001LF / 10132644-002LF](https://www.amphenol-cs.com/product-series/pwrmax-ortho-power.html) | True blind-mating orthogonal plug/receptacle pair, two 100 A power contacts plus two signal contacts, press-fit | Plug is listed at LCSC as C3643068 but is out of stock. DigiKey showed about 693 plugs at $26.83 at 50; the mating half was about $23.58 | **No bolt through the daughterboard.** This is the cleanest removable connector architecture, with one high-power contact for `+12V` and one for `GND`, but roughly $50 per cable pair makes it economically unsuitable for Standard. |
| Würth 74622104 WP-RAFE | Direct right-angle press-fit, M4, 9 mm wide, twelve pins, 180 A | No LCSC listing found | Electrically excessive and still more expensive/larger than 74622103 for this application. |
| LCSC SAMZO 75/80/120 A vertical terminals, including C32710810, C47121901, and C47121895 | Vertical threaded PCB terminals | Stocked and inexpensive | Excluded from the requested direct right-angle comparison. They create a parallel-board stack unless a separate copper angle/busbar is added, so they are not a single-component 90-degree board-to-board joint. |

LCSC stock does not establish JLCPCB assembly-library status. The JLCPCB
assembly-library search did not confirm any of the direct power elements above.
The documented Würth, TE, and Amphenol parts are press-fit components requiring
controlled insertion tooling, and every bolted option still requires downstream
manual daughterboard installation and torquing. Even if JLCPCB globally sources
the part, it should presently be budgeted as post-PCBA mechanical assembly, not
ordinary native placement.

## 6. Contact count and component-cost comparison

The following is connector component cost only for a 100-module build. It
excludes screws, washers, thread locking, daughterboard support, manual assembly,
and any board-area or fab-price change.

The blade baseline uses the current TE 63969-1 LCSC reference price of $0.2628
at 1,000 plus the TE 63951-1 tab price of $0.1111 at 500, or approximately
$0.3739 per complete joint. The main-side TE part is currently out of stock at
LCSC, so this is a price baseline rather than a buyable LCSC BOM today.

| Product | Current blade sites | Blade component cost/module | 30 A Keystone sites / cost | 60 A SAMZO sites / cost | 130 A WP-RAFE sites / cost | 100 A WP-RATR sites / cost |
|---|---:|---:|---:|---:|---:|---:|
| EPS 2-cable | 12 | $4.49 | 12 / $8.10 | 4 / $3.17, **fails 65 A target** | 4 / $12.20 | 4 / $17.28 |
| PCIe 2-port | 12 | $4.49 | 8 / $5.57 | 4 / $3.17 | 4 / $12.20 | 4 / $17.28 |
| PCIe 3-port | 18 | $6.73 | 12 / $8.10 | 6 / $4.39 | 6 / $17.28 | 6 / $22.56 |
| ATX 24-pin | 10 | $3.74 | 6 / $4.18 | 5 / $3.66 | 5 / $14.40 | 5 / $18.80 |

The SAMZO part saves about $1.32 per PCIe 2-port module and $2.34 per PCIe
3-port module in connector components. That margin is small enough that four or
six screws/washers, controlled-torque labor, and added mechanical support can
erase it. The cost case is therefore **same-order or modestly cheaper**, not a
large guaranteed system saving.

The expanded search therefore changes the capability conclusion but not the
cost conclusion: there are multiple proper one-terminal-per-polarity parts, but
the documented direct choices add roughly $8 to $13 per two-cable EPS/PCIe
module before screws, support hardware, and press-fit processing. The only
component-level saving remains the lightly documented 60 A SAMZO option on
PCIe.

## 7. Board-by-board feasibility verdict

### EPS: no for the LCSC direct-right-angle option

- One 60 A SAMZO terminal per polarity does not meet the 65 A target.
- Two 60 A terminals per polarity would pass but returns to eight sites per
  two-cable module, increases width, and loses most of the simplicity/cost case.
- One Würth 130 A WP-RAFE terminal per polarity is compact and credible, but its
  approximately $12.20 connector cost is about $7.71 above the blade baseline,
  before bolts and press-fit processing.
- The 100 A WP-RATR family also meets the target and is explicitly advertised
  for the proposed board-to-board geometry, but costs still more.
- The live EPS main PCB still has legacy output headers, so any choice is a new
  interface placement.

**Recommendation:** retain the blade architecture for Standard EPS. For a
premium serviceability-driven variant, use the 130 A WP-RAFE rather than an
undocumented commodity terminal; choose the 100 A WP-RATR only if its exact
geometry packages better in the mechanical model.

### PCIe: feasible as a controlled prototype

- The 60 A SAMZO part meets the 48.75 A target with one `+12V` and one `GND`
  terminal per cable.
- Two 16 mm bodies consume about 32 mm per daughterboard versus the present
  31.1 mm board width. A few millimetres of width/clearance should solve this.
- On the PCIe 2-port main board, a 12 mm-deep terminal body reaches about 4 mm
  farther inward than the current blade receptacle field. C3, R2, C8 and nearby
  service-power parts make this a local re-placement task, not a drop-in swap.
- PCIe 3-port has enough total edge length only narrowly: six bodies consume
  about 96 mm before cable-to-cable clearance on a 103.5 mm-wide board. A small
  outline increase or staggered grouping is likely.
- The live PCIe 2-port blade pitch is already inconsistent with the live
  daughterboard, so a connector-interface edit is needed regardless.

**Recommendation:** if positive bolted retention is desirable, model the 7 mm
WP-RAFE/WP-RATR geometry first. A low-cost PCIe coupon may use four
`C39833008` terminals, but it is a screening experiment rather than the
documented reference implementation. Do not promote either to the Standard BOM
until the qualification gate in section 8 passes.

### ATX 24-pin: defer

- Five 60 A sites could carry the four positive rails plus common ground under
  the documented current envelope, and their approximately $3.66 component cost
  is nearly identical to the blade baseline.
- A single row is about 80 mm wide before clearance and the signal connector,
  versus the current 61.1 mm daughterboard.
- Five 7 mm-wide WP-RAFE or WP-RATR terminals occupy 35 mm before spacing, so
  the expanded search removes the earlier width objection for a documented
  high-current solution. Their connector cost is approximately $14.40 or
  $18.80 per module, however, versus the $3.74 blade reference.
- The manifest-current main PCB has no valid outline and its existing blade
  sites do not form a mateable row, so a present-layout fit conclusion would be
  invented.

**Recommendation:** do not select the ATX connector until its current output
edge and daughterboard geometry are reconciled. Re-evaluate a five-terminal
7 mm Würth pattern during that interface rebuild if bolt retention is worth an
approximately $11 to $15 connector premium. The SAMZO pattern is wider and is
not presently a cost win after hardware and labor.

## 8. Qualification gate for any bolted prototype

Before adoption, require all of the following:

1. An exact manufacturer drawing and traceable part specification, not only the
   LCSC catalog fields, including recommended hole/pad geometry, maximum PCB
   thickness, bolt torque, terminal material/plating, and current-rating test
   condition.
2. One terminal per polarity tested at the platform target current, not merely
   the sustained cable current: 48.75 A for PCIe or 65 A for EPS. Record terminal
   body, solder/press-fit, PCB copper, and bolted-interface temperature rise.
3. Four-wire joint-resistance measurement before and after thermal cycling,
   vibration/handling, and repeated torque service. This is a connector-joint
   measurement and does not change the project's two-terminal shunt design.
4. A mechanical support or standoff that prevents the upright daughterboard
   from applying continuous bending moment to terminal solder joints/pins.
5. Defined screw, washer or spring-washer stack, torque, locking method, tool
   access, polarity-proof spacing, and assembly inspection mark.
6. Current sharing is not credited between parallel terminals unless each path
   is geometrically symmetric and current sharing is measured.

Failure of any gate returns the design to the TE blade architecture.

## 9. Sources

- [TE Connectivity 63969-1 product record](https://www.te.com/en/product-63969-1.html)
  and [LCSC C2961150 price/stock record](https://www.lcsc.com/product-detail/C2961150.html).
- [TE Connectivity 63951-1 / LCSC C591344](https://www.lcsc.com/product-detail/C591344.html).
- [Keystone 8199 manufacturer record](https://www.keyelco.com/product.cfm/product_id/1552)
  and [LCSC C3029551](https://www.lcsc.com/product-detail/C3029551.html).
- [SAMZO 1216120350M6 / LCSC C39833008](https://www.lcsc.com/product-detail/C39833008.html).
- [Würth WP-RAFE right-angle REDCUBE family](https://www.we-online.com/en/components/products/REDCUBE_PRESS-FIT_RIGHT_ANGLED_EDGE_POSITION)
  and [Mouser 74622103 stock/pricing](https://www.mouser.com/ProductDetail/Wurth-Elektronik/74622103).
- [Würth WP-RATR right-angle two-row REDCUBE family](https://www.we-online.com/en/components/products/WP-RATR_TWO-ROWS),
  [7461101 datasheet](https://www.we-online.com/components/products/datasheet/7461101.pdf),
  and [Mouser 7461101 stock/pricing](https://www.mouser.com/ProductDetail/Wurth-Elektronik/7461101).
- [TE/ERNI 225701-E 160 A right-angle PowerElement](https://www.te.com/en/product-225701-E.html).
- [Amphenol PwrMAX Ortho family](https://www.amphenol-cs.com/product-series/pwrmax-ortho-power.html),
  [10132640-001LF plug](https://www.amphenol-cs.com/product/10132640001lf.html),
  and [LCSC C3643068 listing](https://www.lcsc.com/product-detail/C3643068.html).
