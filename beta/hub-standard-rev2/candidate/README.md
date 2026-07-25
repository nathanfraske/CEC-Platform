# `candidate/` — the current best routed board for this module

ONE board file, kept current by the wave (owner directive 2026-07-25: "the current
best should be placed into a candidate folder per board and kept current with only
one board ideally so we have a reference").

`<board>-candidate.kicad_pcb` (+ its `.kicad_pro` / `.kicad_dru` sidecars) is a COPY
of the best board the wave has ever published for this module, with `candidate.json`
recording where it came from and how it graded. Open it to see the real current
state of the layout without digging through `build/fresh-wave-*/`.

RULES the wave enforces on every publish:
  * it replaces this file only when the new winner BEATS the recorded `sort_key`
    (lower is better -- the same ranking the wave itself uses);
  * a routed winner always beats a placement-only one, and a placement-only winner
    NEVER overwrites a routed reference;
  * exactly one `.kicad_pcb` lives here -- stale board files are pruned.

This is a REFERENCE, not the board of record: it is machine-written, so never hand-edit
it (edits are silently overwritten by the next better wave). The authoritative
schematic + the module's own project files stay in the parent directory.
