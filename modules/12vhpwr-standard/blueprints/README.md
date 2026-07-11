# 12VHPWR sensing-cell blueprints

`sense-lane-rs4-b7.json` — the refined per-lane sensing cell (RS shunt + RFH/RFL
filter + CF + INA240 + bypass), derived from the hand lane-4 cell by the
cell-refinement loop (B7, 2026-07-11): textbook sense-disciplined Kelvin taps,
lane keepout, GND stitching vias, lint/mitre finishing, real-DRC copper-clean,
escape-probed (ISENSEP output clean on F.Cu; +3V3 via-fed per the source-board
idiom). Metrics vs hand: equal 5.4mm pitch, -21% length, taps 8.5/8.2mm skew
0.35. **DRAFT until the owner's stamps-first thermal measurement passes** — the
fresh-board pipeline (cec_fresh_wave blueprint_cells) stamps it 6x with its
internal copper laid + LOCKED.
