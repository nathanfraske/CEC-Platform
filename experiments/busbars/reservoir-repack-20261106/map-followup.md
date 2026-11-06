# Actual paired geometry and the next coordinated cell

The working source is now the independently received ATX `1512d4f...`, not the
older partial-overlap capacitor-via source. The Hub, stack and reviewed selector
are unchanged. These studies do not save or admit a repacked board.

The exact native map exposed two reasons not to reuse earlier nominal trials:

- The moved U6 courtyard ends at y49.095, not the earlier pad/body approximation.
- A rotated C51 enters Hub C37's actual projected body/vent region. At minimum
  stack gap, body separation is 1.3 mm but the required vent gap is 3 mm.
  The resulting -1.7 mm vent margin is a real rejection, not a direct-body clash.

The map-derived seven-part proposal in `geometry-map-derived-seven.json` passes
both native courtyards and the matched-Hub screen. C51 keeps its source 180-degree
orientation and moves only -0.2 mm in X and Y. Its original Ground via remains
fully contained. C54's proposed centered 0.50/0.30 mm Ground via passes as well.

C55's centered Ground via hits actual saved 3V3 copper. Moving it off-center
cannot work with **all** original copper retained: the mux's old B.Cu diagonal
occupies the entire remaining legal center region. `MUX-diagonal-ownership.json`
then proves from fresh Source/manufacturer roles and actual native contacts that
this diagonal is U6's output network, the device being reconstructed. It is not
an unrelated obstacle. That proof does not itself authorize deleting the track.

On a disposable in-memory board with only that diagonal omitted, the conditional
C55 entry at (20.50, 50.54) mm passes native containment, all-layer 0.20 mm spacing,
holes, edges and rule checks. All 3V3 copper remains. The 0.50/0.30 mm via has a
0.010 mm native pad-containment margin. This is a verified conditional seat, not
a saved connection or permission to cut its blocking conductor.

Next: reconstruct the complete mux output path with the original current basis
(3 A, 1.25 geometry margin, 0.477370 mm native width), restoring both segment
boundaries at (16,47) and (22,53) mm and every original terminal. Rebuild the wired
C55 supply and immediate Ground branches in the same coordinated operation.
The proposed full-width IN1 route is 3.487447 mm against the unchanged 3.5 mm
locality bound; its remaining front blockers are the old C55 Ground tail.
Prove its exclusive retirement instead of silently removing it.

No further blind pose sweep, new bus-bar placement, pour window, current waiver,
X/Y compaction or assembled-Z qualification follows from these reports.
