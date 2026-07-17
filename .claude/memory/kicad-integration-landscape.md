---
name: kicad-integration-landscape
description: "Existing KiCad plugins/integrations relevant to the CEC pipeline (MCP servers, IPC API, schematic-gen libs) + which close our bottlenecks"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 81a82931-665b-45e0-be7f-270688523f61
---

Researched 2026-06-25 (web-verified). What exists that could integrate with our KiCad-10 / SWIG-pcbnew / Freerouting pipeline, mapped to our real gaps. Verify version compat before adopting — KiCad file format is forward-only.

**Official IPC API / `kicad-python` (kipy)** — pip `kicad-python`, KiCad-team maintained, protobuf-over-NNG socket, all platforms. Attaches to a RUNNING KiCad GUI (NOT headless until KiCad 11). PCB-editor only in 9/10 (schematic editor "future"); NO export in 9/10 (use kicad-cli). **Has `board.refill_zones(block=)` — closes our #1 handoff (the "Fill All Zones (B)" GUI step kicad-cli can't do).** Strategic: SWIG pcbnew is deprecated in its favor. Deployment wrinkle: socket is Windows-side where the GUI lives → run the kipy client on the Windows box (same pattern as route.ps1 / the self-hosted runner), not from WSL. Highest-value, lowest-risk prototype.

**Schematic-as-data libs** (replace our hand-spliced s-expr): `kicad-sch-api` (circuit-synth, v0.5.5, byte-exact, no-KiCad-install, junctions/wires/nets) and `kicad-skip` (psychogenic, REPL traversal, search by location/connection/type). `kiutils` is another option.
  - **VERIFIED 2026-06-25 (kicad-sch-api → KiCad 10 GENERATION WORKS):** installed in `.venv` (v0.5.5); a hierarchical root+child it wrote LOADS + ERCs in our `kicad-cli` 10.0.3 (format is forward-only, so its 7/8-flavored output opens in 10 fine). It exposes exactly the hierarchical primitives — `add_sheet` / `add_sheet_pin` (edge-based geometry) / `add_hierarchical_label` / `set_hierarchy_context` / `run_erc` / `export_netlist` — and handles the dangerous-to-hand-roll instance-path/sheet-pin s-expr. Our vendored symbols load via `get_symbol_cache().add_library_path("lib/cec.kicad_sym")` then `sch.components.add("cec:CEC_RJ45_8P8C_FTP", ...)` (libs: lib/cec.kicad_sym, lib/vendor/cec-power.kicad_sym, lib/vendor/cec-vendor.kicad_sym). STILL UNVERIFIED: round-trip READ of a KiCad-10-SAVED file (backward compat). **LIMITATION found 2026-06-25: reliable for hierarchical STRUCTURE (sheets load in KiCad 10), NOT for label-based CONNECTIVITY on our CUSTOM symbols** — it embeds correct `lib_symbols` pin geometry, but `get_component_pin_position`/`add_label(pin=)`/global-label-at-pin don't reliably map our symbols' pin NUMBERS to positions (`add_label(pin=("U1","8"))` shorted all 10 INA238 pins; global-label-at-pin formed no node). `connect_pins_with_wire`+`are_pins_connected` DO work same-sheet. → For the hierarchical sub-sheet generator, the recommended path is to hand-roll the sheet WRAPPER on cec_sch's PROVEN flat per-sheet emission (correct on real boards), not drive kicad-sch-api for wiring. See current-work-handoff (cec_sch_hier.py: partition + verify() netlist gate are keepers).

**Schematic generation (owner's stated priority):** KiCad has NO native schematic auto-layout (placement fully manual) — that's the hard part, not the render. `circuit-synth` (Claude-Code-native, Python hierarchical circuits → KiCad via kicad-sch-api, bidirectional import/modify/export, JSON IR) is the most aligned generator but inherits the 7/8 caveat. `tscircuit` has REAL schematic auto-layout (row/column packing) + circuit-to-svg, but it's a TS/React non-KiCad ecosystem (mine the algorithm, don't adopt wholesale).

**Visual self-review loop is available TODAY, no plugin:** `kicad-cli sch export svg|pdf` renders the schematic → Read the image → vision-review for overlaps/crossed wires/floating pins/ugly layout → nudge symbol `(at )` + re-render. The bottleneck is generation+layout, not rendering.

**MCP servers** (Claude-Desktop-oriented; we already exceed their depth with cec_router etc.): mixelpixx/KiCAD-MCP-Server (1.4k★, claims board EDITS), lamaalrajih/kicad-mcp (475★, kicad-cli analysis: DRC/BOM/netlist/render, read-only), circuit-synth/mcp-kicad-sch-api (sch edits), Seeed-Studio, Pablomonte. WATCH / mine for ideas, or wrap OUR pipeline as an MCP server later for portability. Trust caveat: third-party node/python driving KiCad.

**Fab/CI:** `KiBot` (KiCad 6–10, headless CI gerbers/drill/BOM/PDF/3D + DRC/ERC, docker) + `KiKit` (panelization) — mature, could augment our kicad-cli/jobset CI. `Fabrication-Toolkit` (bennymeg, official PCM JLCPCB plugin) — we already cover via the jlcpcb skill.

See [[convergence-blocker-mechanism-not-corpus]] (the routing-side gap is mechanism, separate from these schematic/handoff gaps).
