# Smoke Tester — SNOUT (sub-board, damage/service spare #4)

The DUT-facing 24-pin male header on its own paddle, keyed 2×13 header pair to MAIN
(J_SNOUT). Exists for MECHANICAL DAMAGE only — bent pins, broken latch, a mangled DUT
connector chewing ours (cycle WEAR is ruled functionally irrelevant at this box's duty:
2.3 Ω / 115×-spec-death error-budget math, top README §2; decision #13 RULED keep-paddle,
owner sign-off 2026-07-25). Standard tin contacts. Also the production sub-assembly
convenience: the consigned Mini-Fit hand-solder lands on a $0.60 paddle, not the main board.

Structure: own KiCad project at Phase B (`snout.kicad_pro`) — see brick/README for the
no-literal-inheritance note (one KiCad project per PCB; the generator + platform lib are
the shared layer). Panelized with MAIN.
