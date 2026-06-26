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

**Schematic-as-data libs** (replace our hand-spliced s-expr): `kicad-sch-api` (circuit-synth, v0.5.4 Nov-2025, byte-exact, no-KiCad-install, junctions/wires/nets) and `kicad-skip` (psychogenic, REPL traversal, search by location/connection/type). BOTH target KiCad **7/8** format — KiCad-9/10 compat UNVERIFIED, must test on a real CEC board before trusting. `kiutils` is another option.

**Schematic generation (owner's stated priority):** KiCad has NO native schematic auto-layout (placement fully manual) — that's the hard part, not the render. `circuit-synth` (Claude-Code-native, Python hierarchical circuits → KiCad via kicad-sch-api, bidirectional import/modify/export, JSON IR) is the most aligned generator but inherits the 7/8 caveat. `tscircuit` has REAL schematic auto-layout (row/column packing) + circuit-to-svg, but it's a TS/React non-KiCad ecosystem (mine the algorithm, don't adopt wholesale).

**Visual self-review loop is available TODAY, no plugin:** `kicad-cli sch export svg|pdf` renders the schematic → Read the image → vision-review for overlaps/crossed wires/floating pins/ugly layout → nudge symbol `(at )` + re-render. The bottleneck is generation+layout, not rendering.

**MCP servers** (Claude-Desktop-oriented; we already exceed their depth with cec_router etc.): mixelpixx/KiCAD-MCP-Server (1.4k★, claims board EDITS), lamaalrajih/kicad-mcp (475★, kicad-cli analysis: DRC/BOM/netlist/render, read-only), circuit-synth/mcp-kicad-sch-api (sch edits), Seeed-Studio, Pablomonte. WATCH / mine for ideas, or wrap OUR pipeline as an MCP server later for portability. Trust caveat: third-party node/python driving KiCad.

**Fab/CI:** `KiBot` (KiCad 6–10, headless CI gerbers/drill/BOM/PDF/3D + DRC/ERC, docker) + `KiKit` (panelization) — mature, could augment our kicad-cli/jobset CI. `Fabrication-Toolkit` (bennymeg, official PCM JLCPCB plugin) — we already cover via the jlcpcb skill.

See [[convergence-blocker-mechanism-not-corpus]] (the routing-side gap is mechanism, separate from these schematic/handoff gaps).
