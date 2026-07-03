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
| T0 | `scripts/cec_sch_render.py` | The SELF-ANALYSIS render substrate: kicad-cli SVG → preinstalled chromium → per-sheet overview + high-DPI tile PNGs + manifest — the orchestrator READS the tiles directly (proven: CP2→IN2 verified by eye on the cascade sheet, 2026-07-03). Provisioned by setup-kicad-cli.sh (pip playwright, never `playwright install`); `.mcp.json` also registers the official Playwright MCP for interactive sessions | **LANDED 2026-07-03** |
| T1 | `scripts/cec_sch_layout.py` | Rotation-aware placement (round-trip-verified pin math); `wire_adjacent` real Manhattan wires for local pairs; `place_decouplers`/`wire_decouplers` (netlist-derived IC ownership via `derive_owners`, wired not labeled — ports cec_pcb's auto_cluster concept); text-collision `text_bbox`/`detect_overlaps`/`nudge_texts` (calibrated against a real `kicad-cli sch export svg` textLength measurement — Newstroke runs ~1.02x font-size/char, not the ~0.75x a monospace guess would give); `--check-overlaps`/`--nudge`/`--demo` CLI. Rotation convention (standard CCW on Y-up local coords, applied before the Y-flip) empirically validated by round-tripping a rotated R_Small through `kicad-cli sch export netlist` at 0/90/180/270 (a sign error swaps pin 1/2 — a real discriminating test, not a tautology). Teeth: `tests/test_sch_layout.py` (11/11 — rotation round-trip all 4 angles, wire_adjacent close/far, decoupler adjacency + derive_owners balancing/signal-coupling, font calibration vs measured SVG, overlap detect+nudge, and the eps-8pin real-collision check: 38 pairs found, SENSEC*/VBUS labels colliding with GND ports — evidence for the module's whole thesis, that board is NOT touched). `build_demo()` produces `build/sch-layout-demo.kicad_sch` (IC + 4 wired decouplers + a real-wired divider chain + tapped filter cap), ERC-error-clean and overlap-free after its own nudge pass. GOTCHA recorded in the module: a `PWR_FLAG` INSTANCE alone is not enough — its lib_symbols definition must also be embedded, or KiCad silently reports the pin "Unspecified" and the flag never satisfies ERC's driven-pin check. Not yet integrated into any generator (additive/standalone per the owner's constraint) | **LANDED 2026-07-03** |
| T2 | `scripts/cec_sym_audit.py` | Symbol pin-TYPE auditor: scans .kicad_sym libs for Unspecified/suspicious electrical types (easyeda pulls are loose here — weakens ERC), name-heuristic proposals (VDD*/VSS*→power, *_N/*_P pairs, EN/CS inputs…), report + reviewed-fix mode. Gate: run on cec-ent-* BEFORE sheet-02 capture (a mistyped power pin hides best on a 484-ball part) | **LANDED 2026-07-03** — real s-expr parser (not regex-on-file, `_tokenize`/`parse_sexpr`, verified to recover every pin incl. the full 484 on MPFS095T_FCVG484); teeth in `tests/test_sym_audit.py` (9/9: a mistyped-VDD/unspecified-GND fixture + two calibration regressions caught mid-build on the real libs — a W25Q256JVFIQ quad-mode pin and a DP83TC814S-Q1 MDIO open_collector, both would have been false HIGH-confidence asserts). `--fix` writes a before/after review log first and only ever touches HIGH-confidence pins; **not invoked on cec-ent-\* in this pass** (report-only, per the sheet-02 gate contract). Real findings across the four cec-ent-\* libs: 191 high / 40 medium / 168 low — every non-`unspecified` HIGH mismatch (4 total) is on `cec-ent-compute:MPFS095T_FCVG484` (SPI_EN, DEVRST_N, MSS_DDR_CS0, MSS_DDR_CS1, all bulk-typed `bidirectional`; the CS pair's proposal carries an orientation caveat since MPFS is the DDR bus master, where a real CS is normally an output not an input). `hubs/hub-enterprise/lib-local.kicad_sym` audited read-only: already clean. |
| T3 | `scripts/cec_sch_lint.py` | Schematic STYLE linter (KLC-informed): 4-way junctions, off-grid endpoints (bit this repo before — the #FLG200 ERC), dangling wire ends, label-orientation vs wire direction, stub-length consistency, PWR_FLAG hygiene, wire-crossing COUNT as a tracked metric. Joins the per-sheet verification protocol next to ERC | **LANDED 2026-07-03** — SL-01..09 (9 checks; ERROR: 01/03, WARN: 02/04/05/06/09, METRIC: 07/08), a generic s-expr direct-children walk (handles this repo's mixed pretty-printed/single-line files uniformly, no line-oriented regex), reuses `cec_sch.carve`/`cec_sch_layout.rotate_local`/`_extract_at` read-only. Teeth: `tests/test_sch_lint.py` (4 synthetic fixtures — off-grid endpoint, 4-way junction, dangling wire, 0-error clean sheet — all pass). Real 3-board comparison (read-only): hub-standard (hand baseline, 259 wires) = SL-01:2 (the known #FLG200/#FLG201, exact match to CLAUDE.md), SL-04:29, SL-08:11, SL-09:3, others 0; eps-8pin (generated, 204 wires) = SL-01:0, SL-04:17, SL-09:31 (a real generated-vs-hand gap: 15%/wire vs hand's 1.2%/wire — matches the charter's named "grid-dump placement" gap), SL-08:0 (generator's fixed STUB constant is perfectly consistent by construction, hand-finishing is not); hub-enterprise root+17 leaves (WIP, read-only) = SL-01/02/03/05/06/08: 0, SL-04:52, SL-09:9. One calibration bug caught and fixed pre-ship (charter principle 3): SL-06's "missing PWR_FLAG" half first flagged every plain signal label as a "supply net" (0 real positives, all noise) and separately over-fired per-leaf on hub-enterprise because power-symbol nets are project-global in real KiCad, not per-file — fixed by scoping the check to actual power-port symbol names only, and by promoting the "missing" half to a project-wide pass over the whole hierarchical walk (duplicate-flag detection stays per-file, matching this repo's own adjacent-stamp convention). SL-09 deliberately excludes sheet-box/free-text positions from the paper-frame check (measured false-fire source, not a real finding) and SL-01 deliberately excludes them from the grid check (they use a legitimate whole-mm page-margin convention, not the wiring grid) — both are documented calibration decisions in the module header, not board bugs. |
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
