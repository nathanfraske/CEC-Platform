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
2. **Leaf-internal nets rename** to `/<sheetname>/NAME` — unavoidable, bounded, mappable.
3. **`verify_identity` (MCP) is name-aware** — it fails on renames. The conversion gate is
   the name-AGNOSTIC group compare (0 missing / 0 extra connectivity groups) plus an
   explicit, committed old→new rename map built by matching groups (bijection asserted).
4. **ent-common does NOT bus GND** (04-mcu carries 17 per-pin stamps) — the bused-GND ladder
   is new work; `build_leaf(layout=...)`'s `wires` + `consumed` + `power` fields are the
   supported mechanism (one shared helper, used by both the flat-board mutator and the
   composed leaves).
5. kicad-cli 10.0.4 + pcbnew are live in this container.

## Net-name policy (per converted board)

- **Inter-sheet nets**: hierarchical pins + root lanes; each lane carries a local label with
  the ORIGINAL bare name → net name preserved exactly (`/NAME`). Partitions are chosen so
  the tool-referenced nets (12vhpwr `/SENSEP*`, `/IN*_P/_N`, `/ISENSEP*`; eps/pcie
  `/SENSEC*_HI/_LO`) cross sheets naturally (connectors+shunts in the power-path block,
  sense amps in the sensing block) and therefore KEEP their names.
- **Leaf-internal nets**: rename to `/<leaf>/NAME`; consequences propagated mechanically:
  PCB net table/pads/zones, `.kicad_pro` netclass patterns, `.kicad_dru` — with a
  netclass-MEMBERSHIP-equality assert before/after.
- **Global power nets** (`+3V3`, `+5VSB`, `GND`, `VBUS`…): power symbols, names unchanged.

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
dropped DNP part); G3 rename map contains ONLY the allowed class (leaf-internal `/<leaf>/`
prefixes), committed per board; G4 ERC errors not increased, warning classes documented-benign;
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
