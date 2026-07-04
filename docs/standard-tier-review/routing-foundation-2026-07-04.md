# Routing foundation — stackup register + footprint needs audit (2026-07-04)

Scope: TODO.md 2026-07-04 07:50, part (b). Foundation only — **no `.kicad_sch` touched,
no routing run**. W6 (EPS/PCIe routing pass) stays owner-deferred pending
placement-corridor reconciliation. This doc + one additive library vendor pass
(`lib/vendor/Common_Mode_Choke.pretty/`, registered in five `fp-lib-table`s) are the
only changes; all figures below are measured from the committed `.kicad_pcb` /
`.kicad_pro` / `.kicad_dru` / `.kicad_sch` files with `kicad-cli 10.0.4`, not assumed.

The six consumer beta boards and the schematic/PCB pair used for measurement:

| Board | Schematic (beta-active) | PCB |
|---|---|---|
| Hub Standard | `hubs/hub-standard/hub-standard.kicad_sch` | routed |
| 24-pin ATX | `modules/atx-24pin-rev3/24pin-module.kicad_sch` | **layout not started** — PCB is a byte-identical copy of `atx-24pin-rev2`'s 90° "L" shrink-study, not a rev3 layout |
| EPS 8-pin | `modules/eps-8pin/eps8pin-module.kicad_sch` | placed, 0 copper |
| PCIe 2-port | `modules/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch` | placed, 0 copper |
| PCIe 3-port | `modules/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch` | placed, 0 copper |
| 12VHPWR Standard | `modules/12vhpwr-standard/12vhpwr-standard-module.kicad_sch` | routed, DRC-clean |

(`atx-24pin-rev2`/`-rev3` and `eps-8pin-rev2`/`pcie-*-rev2` naming is inconsistent across
families — see `docs/standard-tier-review/atx-24pin.md` §5 — the table above is the
schematic/PCB pair actually carrying the beta H3/H3a splice work today.)

## 1. Stackup register (named)

All six are 4-layer FR4, ENIG (except `atx-24pin`/`-rev3`, copper_finish "None" —
unrelated to this pass). Naming scheme: `CEC-4L-<role>-<outer-oz>OZ`.

| Board | Stackup name | Outer Cu | Inner Cu | Dielectric (pp/core/pp or core/pp/core) | Board thk (measured / general field) | Inner-layer roles |
|---|---|---|---|---|---|---|
| Hub Standard | `CEC-4L-HUB-SIG-1OZ` | 0.035mm (1oz) F/B | **0.0152mm** In1/In2 | 0.2104/1.065/0.2104 | 1.596 calc / 1.6062 general — **match** | In1=GND (net-tie labelled "GND"), In2=signal routing |
| 24-pin ATX (`-rev3`, PCB stale) | `CEC-4L-24PIN-PWR-1OZ` | 0.035mm (1oz) F/B | 0.035mm (1oz) In1/In2 | core/pp/core 0.48/0.48/0.48 | 1.6 calc / 1.6 general — match | In1=GND, In2=power routing (net-tie labelled "PWR": 12V/5V/3V3/5VSB share this layer) |
| 24-pin ATX (alpha, shipped, frozen — reference only) | n/a (out of beta scope) | 0.035mm F/B | 0.035mm In1/In2 | 0.48/0.48/0.48 | 1.6 calc / **1.74 general — mismatch** | same roles as rev3 |
| EPS 8-pin | `CEC-4L-CABLE-2OZ` | **0.07mm (2oz)** F/B | 0.035mm (1oz) In1/In2 | core/core/core 0.2/1.065/0.2 | 1.695 calc / **1.6 general — mismatch** | In1=GND, In2 labelled "12V" — **stale**, see §3 |
| PCIe 2-port | `CEC-4L-CABLE-2OZ` | 0.07mm F/B | 0.035mm In1/In2 | 0.2/1.065/0.2 | 1.695 calc / **1.6 general — mismatch** | same stale In2="12V" label |
| PCIe 3-port | `CEC-4L-CABLE-2OZ` | 0.07mm F/B | 0.035mm In1/In2 | 0.2/1.065/0.2 | 1.695 calc / **1.6 general — mismatch** | same stale In2="12V" label |
| 12VHPWR Standard | `CEC-4L-CABLE-2OZ` | 0.07mm F/B | 0.035mm In1/In2 | 0.2/1.065/0.2 | 1.695 calc / 1.695 general — **match** | In1=GND1, In2=GND2 — **correctly both-GND** (2026-06-14 fix already applied here) |

**CLAUDE.md board-class doctrine check:** cable boards (EPS/PCIe/12VHPWR) should pour
12V on **both outers** + GND on **both inners**. 12VHPWR's `.kicad_pcb` layer labels
already say GND1/GND2 (correct). EPS/PCIe still carry the *stale generator hint*
`(6 "In2.Cu" power "12V")` from before the 2026-06-14 owner correction — the layer
purpose comment is wrong, not (yet) a real pour (0 zones filled on either board today).
**Routing-gate condition:** before any pour pass on EPS/PCIe, override this label to
GND (both inners), matching 12VHPWR's already-correct state. Hub/24-pin match the "one
GND inner + one routing inner" doctrine exactly (Hub's is a signal layer, 24-pin's is a
power-routing layer carrying all four rails — consistent with the CLAUDE.md exception
note for these two board classes).

**Copper-weight mismatches vs. the "2oz outer / 1oz inner" convention** (flagged, not
edited):
- **Hub Standard inner copper is 0.0152mm** — neither a standard 0.5oz (0.0175mm) nor
  1oz (0.035mm) JLCPCB offering. Reconcile before fab-quoting; likely an unintended
  stackup-wizard artifact rather than a deliberate thin-inner choice.
- **24-pin ATX (both `atx-24pin` and `-rev3`) is 1oz outer, not 2oz** — deviates from
  the repo's stated cable-board convention. This matters because the `HighCurrent`
  netclass (2.5mm track) and the In2 power-routing layer's ampacity assumptions should
  be checked against 1oz, not 2oz, IPC-2221 curves before routing rung-3/rail traces.

## 2. Netclass / `.kicad_dru` reconciliation (measured against the live `.kicad_pro`)

| Board | Netclasses (name: track / via dia/drill / clearance) | `.kicad_dru` present? |
|---|---|---|
| Hub Standard | Default 0.2/0.6-0.3/0.2; CAN 0.25/0.6-0.3/0.2; Power 1.0/0.8-0.4/0.2; USB 0.2/0.6-0.3/0.2 (diff gap 0.13) | yes |
| 24-pin ATX (`-rev3`) | Default; CAN 0.25; HighCurrent 2.5/0.9-0.5/0.2; Power **1.5**/0.9-0.5/0.2; USB | none committed |
| 24-pin ATX (alpha) | same classes, Power track **1.0** (rev3 bumped it to 1.5) | yes |
| EPS 8-pin | Default; Power12V 2.5/0.9-0.5/0.2; GND 0.5/0.9-0.5/0.2; Power 0.5/0.8-0.4/0.2; Signal 0.22; CAN 0.25/0.6-0.3/**0.25**; USB 0.25 | yes |
| PCIe 2-port | identical class table to EPS | yes |
| PCIe 3-port | identical class table to EPS | yes |
| 12VHPWR Standard | Power12V 2.5/0.9-0.5/**0.25**; Sense 0.25/0.6-0.3/0.2 (diff 0.25/0.2); GND 0.5; Power 0.5/0.8-0.4; CAN 0.25/0.6-0.3/0.2; USB 0.25 | **none committed** |

Mismatches found (flagged for the owning agents, nothing silently edited):
- **12VHPWR Standard has no `.kicad_dru`** — every sibling board backs its `Power`
  netclass default with an explicit `track_width (min ...)` DRC rule (the repo's own
  documented reason: a netclass default is *only* a routing default and DRC will not
  independently flag an under-width trace without the rule). 12VHPWR is the one cable
  board that is already fully routed and DRC-clean per CLAUDE.md — that clean result
  was measured **without** this floor rule active. Recommend authoring
  `12vhpwr-standard-module.kicad_dru` mirroring the EPS/PCIe pattern (Power min 0.5mm;
  explicit no-floor note on `/SENSEP*` for the same Kelvin-stub reason) before treating
  the board as production-locked.
- **24-pin ATX `-rev3` has no `.kicad_dru`** — expected at this stage (PCB layout not
  started), but the DRU must be authored (not silently regenerated — `24pin-module.kicad_dru`
  under `atx-24pin/` is the alpha's file and is NOT auto-applied to `-rev3`'s own project
  dir) before the rev3 layout pass begins.
- **Power12V clearance diverges within the cable-board family**: EPS/PCIe use 0.2mm,
  12VHPWR uses 0.25mm. Flag for reconciliation — may be an intentional Kelvin-geometry
  difference (12VHPWR's INA240 pitch vs. EPS/PCIe's INA238/181), not a defect, but the
  three should agree or the difference should be documented as deliberate.
- **Hub Standard has no dedicated `GND` netclass** (falls to `Default`, 0.2mm/0.6-0.3 via)
  — every other board with a GND-bearing plane gives GND its own 0.5mm/0.9-0.5 class.
  Lower severity since Hub's GND is already a single filled zone, but inconsistent with
  the platform pattern.
- **24-pin ATX alpha vs. `-rev3`**: alpha's `.kicad_dru` (`modules/atx-24pin/24pin-module.kicad_dru`)
  is the only committed DRU for the 24-pin family; it correctly documents *why* the
  high-current rail nets carry no per-track width floor (ampacity comes from the In2.Cu
  pour, not the track). This reasoning still applies to `-rev3` and should be copied
  forward, not re-derived, when `-rev3`'s own DRU is authored.

## 3. Routing-gate conditions to carry into W6

1. **Enclosed-boundary thermal note (beta-lock-register §J2).** The 12VHPWR
   72.95°C/ΔT22.95 electrothermal PASS assumes a **metal-case** conduction path (TIM on
   shunts + M3 mounts); still-air/no-case is 151°C, and a printed shell is *worse* than
   open air (insulator + blocks convection). §J2 explicitly extends this to EPS/PCIe:
   "verify at their W6 electrothermal gates with the enclosed boundary condition, not
   open-air" — EPS/PCIe are asserted to "run cool" only under an *open-air* assumption
   today. **Gate condition: no EPS/PCIe routing pass should be scored against an
   open-air thermal target; re-run the electrothermal gate under the enclosed-case
   boundary before accepting a routed candidate.**
2. **12VHPWR production-bar items** (proto is DRC-clean and fab-direction; these are
   production-rev deltas, not proto blockers, per CLAUDE.md action item 4):
   - High-current lanes are single-layer-per-segment (HI on F.Cu / LO on B.Cu) rather
     than the recommended paralleled F.Cu+B.Cu **mirror** — thermal passes as-built, so
     this is a margin improvement, not a fix, but should be the production-rev default.
   - The 12V F→B transition vias are measured 0.6mm/0.3mm, **below** the board's own
     `Power12V` netclass spec of 0.9mm/0.5mm — enlarge to match the netclass for
     production.
3. **Stale In2 "12V" layer label on EPS/PCIe** (§1) — correct before pouring; 12VHPWR
   already carries the correct GND1/GND2 labels and is the reference state.

## 4. Footprint needs audit

Method: parsed every non-power-symbol component in the six schematics above (421 line
audit script output, kept off-repo in the scratch dir), resolved each `Footprint`
property against `lib/cec*.pretty` and `lib/vendor/*.pretty`. Full result: **every
placed component footprint on all six boards resolves to a real, existing `.kicad_mod`
file** except the two gaps below. The H3/H3a common-protection suite (USBLC6-2SC6 ESD,
FB1/FB2 ferrite-bead-or-0R lands, the 0R CAN bypass positions, the persist-on-fault
parts TLV7011/TPS61040/TPS563201+L2 on Hub, the 12VHPWR fan header J2, and the 24-pin
RS4 WSK2512 4-terminal Kelvin land) were **already fully vendored** by the schematic
agent(s) before this pass — nothing needed sourcing there.

| Part | Board(s) | Status | Detail |
|---|---|---|---|
| **FL1 (CAN CMC)** | atx-24pin-rev3, eps-8pin, pcie-2port, pcie-3port, 12vhpwr-standard | **needs-drawing → now vendored (additive)** | `Footprint` property is empty on all five. OQ-83. |
| **J3/J4 (ATX-24 power headers)** | atx-24pin-rev3 only | **mismatch — flag, not silently fixed** | Schematic cites `Molex_Mini-Fit_Jr_5569-24A2_2x12_P4.20mm_Horizontal`; only the `-24A1` suffix is vendored (`lib/vendor/Connector_Molex.pretty/`). Alpha and `-rev2` both correctly cite `-24A1`; `-rev3` alone drifted to `-24A2` (likely a typo introduced during the rev3 splice, not a deliberate part change — no accompanying MPN/sourcing note explains an A1→A2 change). **Action for the schematic-owning agent:** revert to `-24A1` (matches the vendored land + alpha/rev2 precedent), or if A2 is a deliberate packaging-variant switch, vendor that footprint and document why. Not fixed here since it is a `.kicad_sch` edit. |

### FL1 CAN CMC — part convergence gap (OQ-83), and what was vendored

The five boards do **not** agree on a candidate part:
- `atx-24pin-rev3` + `eps-8pin`: TDK **ACT45B-510-2P-TL003**, LCSC **C76584**, SMD-4P
  4.5×3.2mm, 51µH/line, CAN-bus rated, ~177k LCSC stock verified 2026-07-03 — explicitly
  noted in `atx-24pin-rev3` as "matches the EPS/PCIe boards' choice for platform
  consistency."
- `pcie-8pin-2port`/`-3port`: generic `Value="CMC"`, no MPN/LCSC annotated — the
  "platform consistency" note above appears aspirational rather than yet propagated to
  the PCIe boards' own instance properties.
- `12vhpwr-standard`: a **different** part, TDK **ACT1210L-101-2P-TL00**, LCSC
  **C307643**, 1210 body — not the same footprint family as ACT45B.

Since `eps-8pin`/`atx-24pin-rev3` already carry a real LCSC number for the leading
candidate (C76584) in the schematic, the vendoring precondition is met. Vendored via
`easyeda2kicad` (already installed, v1.0.1) from LCSC C76584, upgraded to KiCad-10
format with `kicad-cli fp upgrade`, and validated (`kicad-cli fp export svg` — plots
cleanly, no dangling 3D reference left in the file):

- `lib/vendor/Common_Mode_Choke.pretty/CMC_SMD4P_L4.5xW3.2mm.kicad_mod` (new pretty
  library; provenance + the ACT1210L platform-divergence note baked into `descr`).
- Registered as nickname `cec-Common_Mode_Choke` in the `fp-lib-table` of the five
  boards that carry FL1 (**not** Hub Standard, which has no FL1 position) —
  `atx-24pin-rev3`, `eps-8pin`, `pcie-8pin-2port`, `pcie-8pin-3port`,
  `12vhpwr-standard`.
- **Not** wired to any `Footprint` property — that assignment plus the platform
  convergence decision (ACT45B vs. ACT1210L; recommend ACT45B given the 2-board
  precedent + verified stock) is a schematic-owning-agent / owner action, deliberately
  left undone here (no `.kicad_sch` touched).
- No 3D model vendored (not fetched in this pass) — a placeholder-free footprint is
  preferable to a dangling model path; add a STEP file when convenient.

## 5. Prioritized GET-LIST

1. **OQ-83 part convergence** (owner/schematic action): pick one CMC MPN
   platform-wide — ACT45B-510-2P-TL003 (C76584) is the better-evidenced candidate
   (2-board precedent, verified 177k stock) vs. 12VHPWR's ACT1210L-101-2P-TL00
   (C307643). Footprint for ACT45B is now vendored and ready to assign.
2. **Assign the FL1 `Footprint` property** on all five boards once (1) is decided —
   schematic edit, out of this agent's scope.
3. **Fix or confirm the atx-24pin-rev3 J3/J4 footprint name** (`-24A2` vs. the vendored
   `-24A1`) — schematic edit, out of this agent's scope.
4. **Author `.kicad_dru` for `12vhpwr-standard`** (currently routed with no committed
   floor-rule file) and for `atx-24pin-rev3` (before its layout pass starts).
5. **Reconcile the stale EPS/PCIe In2 "12V" layer label to GND** before any pour pass.
6. **Reconcile copper-weight/board-thickness mismatches**: Hub Standard's 0.0152mm
   inner copper, the 24-pin family's 1oz-outer vs. the platform's 2oz-outer cable-board
   convention, and the stale `general.thickness` field on `atx-24pin` (alpha),
   `eps-8pin`, `pcie-8pin-2port`, `pcie-8pin-3port` (all read 1.6mm vs. a computed
   ~1.695–1.6mm actual stackup sum — cosmetic/paperwork only, not DRC-relevant, but
   worth correcting before fab paperwork is generated).
7. **12VHPWR production-bar items** (§3.2) — carry into the production-rev punchlist,
   not proto-blocking.
