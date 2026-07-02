# Schematic-quality charter — generated ≈ hand-authored

_Owner directive (2026-07-02): stand up every tooling investment that closes the gap
between generated schematics and hand-authored ones; this charter is the plan of record
and is injected by a SessionStart hook — READ IT before any schematic-generation work.
Status column is live; update it in the same change that lands a tool._

## The gap, named

Hand-authored sheets have: natural part orientation; decouplers wired AT their IC;
left-to-right signal flow (inputs left, outputs right, power top, GND down); labels only
for genuine long hauls; no text collisions; minimal wire crossings; consistent stubs and
junction hygiene. Generated sheets (pre-charter) had: everything at rotation 0, all
connectivity by net-label aliasing, grid-dump placement, colliding text. ERC and netlist
assertions prove ELECTRICAL truth; this charter is about the READABILITY half.

## Non-negotiable principles

1. **Netlist-identity invariance** — cosmetic tooling NEVER changes connectivity; every
   tool proves the flattened netlist (via `kicad-cli sch export netlist`) is identical
   before/after. The verification protocol's electrical legs stay the load-bearing gate.
2. **Teeth first** — a checker is trusted only after it demonstrably FAILS on a real bad
   example (the cec_golden/AM-02 discipline).
3. **Calibrate, don't guess** — text metrics, spacing constants, and pin math are
   measured against real kicad-cli output (SVG export / netlist round-trips), never
   assumed.
4. **The GUI stays the top rung** — tools approach hand quality; a human finishing pass
   remains legitimate. Tools must leave sheets GUI-editable (standard s-expr, no exotic
   structures).

## The tool ladder

| # | Tool | What it does | Status |
|---|---|---|---|
| T1 | `scripts/cec_sch_layout.py` | Rotation-aware placement (round-trip-verified pin math); `wire_adjacent` real Manhattan wires for local pairs; `place_decouplers` (netlist-derived IC ownership, wired not labeled — ports cec_pcb's auto_cluster concept); text-collision detect + deterministic nudge; `--check-overlaps` CLI gate | BUILDING (2026-07-02) |
| T2 | `scripts/cec_sym_audit.py` | Symbol pin-TYPE auditor: scans .kicad_sym libs for Unspecified/suspicious electrical types (easyeda pulls are loose here — weakens ERC), name-heuristic proposals (VDD*/VSS*→power, *_N/*_P pairs, EN/CS inputs…), report + reviewed-fix mode. Gate: run on cec-ent-* BEFORE sheet-02 capture (a mistyped power pin hides best on a 484-ball part) | BUILDING (2026-07-02) |
| T3 | `scripts/cec_sch_lint.py` | Schematic STYLE linter (KLC-informed): 4-way junctions, off-grid endpoints (bit this repo before — the #FLG200 ERC), dangling wire ends, label-orientation vs wire direction, stub-length consistency, PWR_FLAG hygiene, wire-crossing COUNT as a tracked metric. Joins the per-sheet verification protocol next to ERC | BUILDING (2026-07-02) |
| T4 | Composition engine (extends T1) | Sheet archetypes + flow: netlist-DAG left-to-right ordering (sources left, loads right, rails top, GND bottom); per-block templates (regulator, transceiver, connector, sensor chain); pin-side selection + net ordering to MINIMIZE crossings; bus notation for grouped signals (RGMII/QSPI/SDIO) | SCOPED — starts when T1 integrates into gen_hub_enterprise |
| T5 | `scripts/cec_sch_golden.py` | Golden sheets: freeze owner-approved renders + metric bands (overlap count, crossing count, ERC class census, net identity); regen regression detection; before/after DIFF RENDERS per change for human review | SCOPED — after first owner-approved sheet set |
| T6 | VLM render-review seat | Render → vision-judge readability critique loop (the platform's existing cec-vision-judge culture; measured strength: structure/text reading). WORKSTATION-side only (broker seats; owner-gated binding per cec-policy); cloud sessions use the deterministic checkers | SCOPED — workstation; owner seat-binding gate |

## Wiring into the verification protocol

The ENT hub per-sheet gate (SCHEMATIC-PLAN.md §2) grows two legs when T1–T3 land:
5. `cec_sch_layout.py --check-overlaps` ≤ threshold (target 0).
6. `cec_sch_lint.py` clean (style classes triaged like ERC: real vs documented-benign).
Sheet 02 additionally gates on the T2 pin-type audit of `cec-ent-compute`/all cec-ent libs.

## Standing integration order

T1+T2+T3 land → integrate T1 into `hubs/hub-enterprise/gen_hub_enterprise.py` (regenerate
01a-g, netlist-identity proven) → adopt gates 5/6 → T4 on the next-captured sheets → T5
once the owner approves a sheet set → T6 on the workstation.
