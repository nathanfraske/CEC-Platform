# Dense-area reference finishing

Use the established chart-first rule: retain readable component-side references
where they fit, otherwise try a small nearby, framed `REF MAP` with the actual
relative component arrangement and a clear leader. When that bounded chart
search does not fit, use the opposite silkscreen at the component's actual
projected position, with its courtyard and reference designator.

For a front-mounted component this is a **back-view readable** mark: native
KiCad B.SilkS text is mirrored in board coordinates and reads normally when
looking at the physical back. Do not reverse the reference string, move/flip the
component, or mirror its physical placement. Opposite-face outlines and text
are native footprint children so later genuine placement changes carry them
along. The hidden original Reference field remains authoritative. Values and
MPNs stay on the correct fabrication layer and in the BOM.

Use a complete outline where it clears actual openings. Exact four-corner
brackets and a short unambiguous leader are permitted by the existing owner;
they do not invent a larger body or move the component outline. Minimum glyph
size, stroke, mask/drill/land spacing and edge clearance come from the unchanged
declared fabrication profile. A failed placement must leave the original
reference visible, not silently discard it or shrink it below that profile.

## Bounded application

Run the source-bound mask-aware worker against a current native grade:

```sh
PYTHONPATH=scripts:build:ops /usr/bin/python3 \
  build/root_run_mask_guarded_reference_mapping_20261020.py \
  --source SAVED/board.kicad_pcb --grade CURRENT/diagnostics.json \
  --hint BOARD_ID --reporting-build NATIVE_REPORTING_BUILD \
  --maximum-components 6 --max-seeds 32 --out FRESH_COHORT
```

The seed domain is finite (at most 32). Its early entries may all be genuinely
blocked while a later component still has a valid rear seat; stopping at the
default 16 is not evidence that the rest cannot fit. Do not repeatedly run an
unchanged failed menu. Any broader search needs an explicit bounded domain.

After a received first cohort, the existing bounded runner can advance a small
number of additional cohorts with the same `--max-seeds 32` budget. It retains
the last passing child when the next worker refuses, fails DRC, or reaches its
deadline. An intermediate native-only intake is not a full-board grade.

Before selecting a result, independently replay every saved annotation phase
and native-mask witness; run complete uncapped native DRC and whole-board
current, connectivity, reference-copper, Ground-return, footprint/field,
dimension and mating preservation checks. Inspect native glyph polygons from
the actual back, not substitute font labels or text bounding rectangles. Bind
the dashboard resources to the exact saved board hash and publish headlessly.

These are ink-only changes. They grant no electrical, thermal, current-rating,
pair-performance or fabrication-release qualification and do not close
unrelated manufacturing debt. Keep unsupported/obstructed markings explicit.
