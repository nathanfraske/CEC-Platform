# `candidate/`: the current best diagnostic board for this module

ONE board file, kept current by the wave (owner directive 2026-07-25: "the current
best should be placed into a candidate folder per board and kept current with only
one board ideally so we have a reference").

`<board>-candidate.kicad_pcb` (+ its `.kicad_pro` / `.kicad_dru` sidecars) is a COPY
of the best board the wave has ever published for this module, with `candidate.json`
recording where it came from and how it graded. Open it to see the real current
state of the layout without digging through `build/fresh-wave-*/`.

IMPORTANT: `candidate/` is a diagnostic-reference channel, not a release-acceptance
channel. A routed board remains here when its route gate fails so reviewers can see
and improve the best failure. `candidate.json` therefore records
`candidate_role: diagnostic-reference`, `release_accepted: false`, and the distinct
`route_gate_passed` result. Only the aggregate release pipeline may accept a board.

RULES the wave enforces on every publish:
  * SCHEMATIC FRESHNESS outranks score: a winner matching more of the CURRENT
    component signatures replaces the reference even on a worse score, and a
    staler board never replaces a fresher one. The signature covers value,
    footprint, and numbered-pad nets. `schematic_match` and `schematic_exact` in
    `candidate.json` record the result. A board that grades well but predates a
    schematic or footprint change is the worse reference;
  * otherwise it replaces this file only when the new winner BEATS the recorded
    `sort_key` (lower is better -- the same ranking the wave itself uses);
  * a board satisfying the CURRENT segmented-mezzanine geometry replaces one
    that violates it, independent of route score; an obsolete mechanical datum
    is stale in the same way an obsolete component signature is stale;
  * a routed winner always beats a placement-only one, and a placement-only winner
    NEVER overwrites a routed reference;
  * exactly one `.kicad_pcb` lives here -- stale board files are pruned.

`candidate.json` is also refreshable without publishing a board. Consumers that
use a candidate as a placement oracle or materialization template MUST require
`schematic_exact: true` after a current refresh. A stale candidate remains useful
for historical outline, connector, mount, and copper review, but it is not a
component-inventory or pin/net authority.

This is a REFERENCE, not the board of record: it is machine-written, so never hand-edit
it (edits are silently overwritten by the next better wave). The authoritative
schematic + the module's own project files stay in the parent directory.
