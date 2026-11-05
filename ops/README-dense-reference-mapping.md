# Dense component references

`cec_dense_reference_mapping.py` is opt-in annotation tooling. It consumes an
exact saved board and complete, uncapped native silkscreen findings. It never
grants placement, copper, BOM, current-budget, factory-rule or release authority.

For a bounded nearby cohort of conflicting references, it first tries a framed
local `REF MAP` chart with a leader and the actual relative courtyard layout.
If that finite search cannot fit, it tries opposite-face ghost courtyards at
the components' real positions, with readable references and short leaders
where an inside label cannot fit. A rectangular outline may use all four exact
corner brackets around openings; it cannot move or invent the component body.
Back text is native mirrored KiCad text, intended to read normally when viewed
from the back. Values and MPNs stay on the fabrication layers.

The declared factory profile supplies minimum glyph size, stroke, spacing and
edge clearance. Existing ink, pad/via lands, drill holes, substrate boundaries
and assembled bodies reserve space. Text is not shrunk to force a fit. An
unsupported or obstructed component is left untouched and reported, not silently
hidden. Failure of the finite chart search is not proof that no layout exists.

Opposite-face marks are native footprint children, so they follow later real
component moves, rotations and flips. A front chart and its component members
form a rigid native group. Existing group ownership is never overridden.
Rear children are not also placed in a board-level group: KiCad reloads that
unsupported membership as empty and drops it on the next save. Receiving now
requires a complete second native save to be identical. Unresolved Source
groups require a separately received repair, never silent normalization.
The original reference field and identity remain authoritative, hidden only
after a complete replacement is constructed. Source-exact receiving rejects
unowned changes to either annotations or the rest of the board and companions.

Example (run from the repository root, with a fresh output directory):

```sh
PYTHONPATH=scripts:build:ops /usr/bin/python3 ops/cec_dense_reference_mapping.py \
  --source SAVED/board.kicad_pcb --grade EXACT/diagnostics.json --hint BOARD_ID \
  --reporting-build NATIVE_REPORTING_BUILD --out FRESH_WORK
```

One run produces one bounded cohort, not an all-labels-clean certificate.
Receive the saved result, run full native DRC and whole-board invariants, and
inspect the actual front/back views before selecting it. Generic PCB text shape
conversion returns bounding rectangles; use native `TransformTextToPolySet`
glyphs for visual review. Do not mistake conservative collision envelopes for
the printed markings. Zero opens or fewer silk findings do not make a board
fabrication-ready.
