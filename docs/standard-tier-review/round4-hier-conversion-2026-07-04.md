# Round 4 — hierarchical conversion of the module boards (plan of record, 2026-07-04)

Owner directive (TODO.md 2026-07-04 10:20): (1) multi-sheet division APPROVED, "readability
over all else"; (2) GND arrays bused to one link on ALL boards; (3) full rearrange on every
board except hub + 24-pin; (4) COST: sonnet/haiku subagents only, no render-read loops —
deterministic checkers are the judge, generator-code-once, ONE final render per board.

Strategy (session ruling, commit 4731ae0): stop agent-polishing flat sheets. CONVERT the four
module boards (eps-8pin, pcie-8pin-2port, pcie-8pin-3port, 12vhpwr-standard) to the
hierarchical composed form (one functional block per literal sheet via `cec_sch_compose`, the
ent-common worked example) — items 1–3 become true BY CONSTRUCTION. Hub + 24-pin-rev3 keep
their flat form and get the GND-ladder bus mutation only.

## Measured facts the design rests on (2026-07-04, this session)

1. **Root local labels win the net name.** Probe on a scratch copy of ent-common: adding a
   local label `CAN_H` on a root lane renamed the spanning net to `/CAN_H` exactly (its
   unlabeled sibling stayed `/01-power/CAN_L`). So inter-sheet nets keep their flat names
   verbatim when the thin parent's lanes carry local labels with the original bare names.
   **Name-pin probe (1-endpoint case) also verified**: leaf hierarchical label + root sheet
   pin + labeled root stub took `/04-mcu/FLASH_CS` → `/FLASH_CS` (leaf-prefixed name gone
   from the netlist). Both halves of the zero-rename policy are measured, not assumed.
2. **Leaf-internal nets rename** to `/<sheetname>/NAME` — unavoidable, bounded, mappable.
3. **`verify_identity` (MCP) is name-aware** — it fails on renames. The conversion gate is
   the name-AGNOSTIC group compare (0 missing / 0 extra connectivity groups) plus an
   explicit, committed old→new rename map built by matching groups (bijection asserted).
4. **ent-common does NOT bus GND** (04-mcu carries 17 per-pin stamps) — the bused-GND ladder
   is new work; `build_leaf(layout=...)`'s `wires` + `consumed` + `power` fields are the
   supported mechanism (one shared helper, used by both the flat-board mutator and the
   composed leaves).
5. kicad-cli 10.0.4 + pcbnew are live in this container.

## Net-name policy (per converted board) — ZERO-RENAME (tightened 2026-07-04 19:45)

- **Inter-sheet nets**: hierarchical pins + root lanes; each lane carries a local label with
  the ORIGINAL bare name → net name preserved exactly (`/NAME`). Partitions are chosen so
  the tool-referenced nets cross sheets naturally: eps/pcie `/SENSEC*_HI/_LO` cross
  connectors↔sensing; 12vhpwr uses a FLOW partition (12V input+fan / lanes: shunts+RC
  filters / 12V output / INA240 sensing / …) so `/SENSEP*_HI/_LO`, `/IN*_P/_N`,
  `/ISENSEP*`, `/FAN_12V` are all genuine 2-endpoint lanes and KEEP their names.
- **Residual leaf-internal NAMED nets** (eps ~8: DETAMPC*, THRESH, EN, GPIO0, USB_CC*…):
  **name-pinned** — force-exported through a sheet pin and terminated at root on a short
  stub carrying a LOCAL label with the original name (probe-verified naming). Net keeps
  `/NAME` exactly. Result: **the rename map is EMPTY on every board** — the routed 12vhpwr
  PCB keeps every net name byte-identical, netclass patterns untouched, downstream fnmatch
  consumers (cec_score/cec_fr/corpus checkers) unaffected.
- **Global power nets** (`+3V3`, `+5VSB`, `GND`…): power symbols, names unchanged.
- `unconnected-(REF-Pin-PadN)` auto-nets: expected to regenerate identically (same
  ref/pin); any deviation is logged and exempted from the empty-map assert, never silently.
- The reconcile tool's rename machinery therefore runs as a VERIFICATION GATE
  (assert-empty) + remains available if a future partition deliberately renames.
- Note (pre-existing, not this pass): 12vhpwr lane-6 pre-shunt HI is already named
  `/FAN_12V` (beta fan-header splice) — preserved as-is.

## PCB reconciliation (the sync hazard)

Regeneration changes symbol UUIDs and sheet paths → every footprint's `(path …)` link breaks,
and renamed nets go stale on pads/tracks. `scripts/cec_pcb_reconcile.py` fixes both headlessly
(relink by ref from the new sch's uuid chains; rename nets per the group-matched map), then
verifies: pcbnew round-trip, full DRC parity vs the pre-conversion baseline (12vhpwr: 0
unconnected / 0 schematic-parity / cosmetic-silk-only — CI-gated, not DRAFT), and
schematic-parity where kicad-cli supports it. EPS/PCIe PCBs are placement-only (0 copper) —
low risk, same procedure. `fab/` snapshots are frozen alpha artifacts — untouched.

## Gates (every converted board; deterministic, no vision reads)

G1 group-identity exact (name-agnostic) vs HEAD flat baseline; G2 symbol-inventory equality
(direct sch parse: ref→lib/part/value/footprint/**DNP**/all props — netlist alone can hide a
dropped DNP part); G3 rename map EMPTY (zero-rename policy above; unconnected-* deviations
logged+exempted, never silent); G4 ERC errors not increased, warning classes documented-benign;
G5 text-overlap + wire-collision gates 0-or-waivered (pin-glyph bar); G6 NEW region-containment
+ sheet-bounds checkers pass; G7 netclass membership equality after pattern updates;
G8 prose preservation (every engineering text string from the flat sheet carried or explicitly
waived); G9 PCB reconciled + DRC parity; G10 ONE final render per board for the owner;
G11 BOM equality (sorted by ref) old vs new.

## Sequencing

Wave 1 (parallel): [T] checker/mutator toolkit + GND bus applied to hub + 24pin-rev3;
[R] cec_pcb_reconcile.py. Wave 2: [E] compose lane-label extension + `gen-module-beta.py`
(parametric cable-i2c family) proven on EPS. Wave 3: PCIe×2 (driver reruns) + [H] 12vhpwr
(own driver; strictest gates, converted LAST). Wave 4: reconcile PCBs, adversarial
verification sweep, renders, docs, commit.

Out of scope (unchanged): W6 routing (owner-deferred), the stale 2026-06-24
`*-rev2` sectioned-regen experiment dirs (pre-beta, superseded by this pass — flagged in
FOLLOWUPS for owner cleanup), hub/24pin full rearrange (owner exempted).
