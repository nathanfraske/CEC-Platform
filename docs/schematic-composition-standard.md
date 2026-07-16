# Schematic composition standard (Nuand-derived)

_Owner ruling 2026-07-02/03: generated sheets read cluttered and non-uniform next to
the Nuand (bladeRF) reference schematics. This one-page standard codifies the
reference's composition rules; `scripts/cec_sch_compose.py` (+ `cec_sch_archetypes.py`)
implements them and `scripts/cec_sch_layout.py --check-overlaps` (pin-glyph-aware)
enforces the text-clearance half. Charter T4 row points here; update both in the same
change (charter discipline). Every rule is testable — cite the rule ID in review._

## Rules

- **S1. Edge-anchored off-sheet I/O.** Every off-sheet signal (hierarchical label)
  terminates a SHORT drawn horizontal run whose END carries the label — never a label
  floating mid-wire, never scattered mid-sheet. Labels gather in vertically aligned
  columns at the sheet's LEFT content edge (inputs) and RIGHT content edge (outputs),
  scannable top-to-bottom. Engine: `build_leaf(io_sides=...)` routes real Manhattan
  wires from the pin stubs to the columns (collision-checked; netlist-identity
  invariant). Test: every hier label's X within each sheet sits on one of ≤2 column
  X values; each column's labels share pitch-aligned Y.
- **S2. Horizontal flow bands.** A processing chain (jack → protection → regulator →
  load) sits on ONE shared Y baseline — pin-row aligned, not origin aligned; multiple
  chains stack as parallel horizontal bands. Main power path = one band across the top;
  the IC body hangs below the band; control/strap parts hang as a column under/left of
  their IC; status exits right at pin-row height (S1). No staircase diagonals.
  Engine: `Compose.place_pin()` (place a part BY a chosen pin's coordinate).
- **S3. Section captions.** Each functional block on a sheet carries a bold caption
  ("eFuse front (TPS26621) — ILIM 24.9k → 3.53A typ" style), reusing the block's real
  desc/BOM strings. Engine: `Compose.caption()`. One caption per block; captions never
  collide with content (the overlap gate sees them).
- **S4. Uniform repeated cells.** Decoupler/cap banks and repeated structures stamp on
  a fixed pitch as ONE neat row, rail named at the row head (power stamp) or captioned
  above. Engine: `cec_sch_archetypes.decoupler_bank` / `Compose.rail`.
- **S5. Ref/value placement.** One convention everywhere: Value directly UNDER
  Reference, both on the SAME side of the part (beside vertical passives, stacked above
  ICs and horizontal passives). Engine: `_emit_symbol2`; residuals resolved by
  `nudge_texts` (which never moves labels/pins).
- **S6. Pin-glyph clearance.** Symbol pin NAME and pin NUMBER glyphs are first-class
  text for collision purposes: no label, field, caption, or another pin's glyph may
  overlap them. Gate: `cec_sch_layout.py --check-overlaps` = 0 on every generated
  sheet. This also polices library authoring: a symbol body too narrow for its own
  opposing pin names fails here (fix the symbol, not the gate).
- **S7. PWR_FLAG anchor block.** ERC power-flag anchors form ONE tidy block at the
  content's bottom-left on a fixed pitch — never orphan islands in dead space.
  Engine: `_powerflag_anchors`.
- **S8. Rail discipline.** Repeat power-port stamps liberally at short local stubs
  (each subcircuit gets its own +3V3/GND stamp); a LONG drawn rail run is reserved for
  a single S2 flow band. Never run a rail wire across the sheet just to avoid a stamp.
- **S9. Content-to-page fit.** A sheet's composition occupies a sensible fraction of
  its page (KiCad has no A5: small blocks stay on A4 but take LARGER part spacing so
  the drawing breathes; dense blocks may take A3). Centering is the engine's job
  (`_center_shift`).
- **S10. On-sheet annotation.** (a) Computed-value notes beside parts ("ILIM 24.9k →
  3.53A typ"); (b) free-text design notes under blocks. Notes come from EXISTING
  desc/BOM-D strings — never invent new engineering claims at emit time. Engine:
  `Compose.note()`.
- **S11. Region accent frames (sparing).** A dashed frame + title MAY group a
  sub-function WITHIN a sheet (Nuand "XB VCCIO SELECTION" style) — only where one sheet
  genuinely carries two distinguishable sub-functions. It is an accent, NEVER a
  substitute for a real sheet (the owner's 2026-07-02 veto on dashed-frames-as-sheets
  stands; per-board checkers that forbid dashed frames on single-function sheets keep
  that meaning). Engine: `Compose.region()`.
- **S12. Allowed, not yet implemented:** on-sheet truth tables (Nuand D1/D0 & SEL
  tables) are an accepted pattern for mux/strap logic; no table emitter exists yet.
- **S13. Color (verified against pinned KiCad 10 kicad-cli SVG export).** Per-text
  `(color ...)` renders in our toolchain; captions/notes may use the reference's accent
  scheme (muted blue titles, dark-green notes). Electrical text (labels, refs, values)
  stays theme-default.

## Gate wiring

Per-sheet verification legs (both ENT generators): ERC benign-classes-only; netlist
node-set identity; `--check-overlaps` **0** (pin-glyph-aware — the S6 raised bar);
`cec_sch_lint.py` no new ERROR class. The renders (T0 tiles) are read against S1–S11
before a sheet set is called done.

## S-spread addendum (owner directive, 2026-07-03: "use more space for readability")
- Power-symbol glyphs (arrows/triangles) keep >=2.6mm separation from each other
  (`cec_sch_layout --check-wires` GLYPH-CLIP class); when a flag's zone is crowded, FLIP the
  flag to the wire's other side (the 180-degree remedy) or lengthen the stub — never let two
  glyphs interleave.
- No text (label, field, free text) lies along or across a wire or a power glyph
  (`--check-wires` classes); labels anchor at wire ends pointing AWAY.
- Space is free on a schematic sheet: when a region cannot satisfy these with nudges, SPREAD
  the parts. Readability outranks compactness (the owner's designation).
