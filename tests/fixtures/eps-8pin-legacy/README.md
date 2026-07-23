# eps-8pin LEGACY test fixture (frozen 2026-07-07)

The pre-beta committed eps-8pin board (merge-base 3a8af24 of the beta arc and the
placement-corridor branch) — the EXACT artifact the corridor-model / keepout /
placer tests were written against. The live `beta/eps-8pin` is the BETA board
(hierarchical C6 schematic, TB blade fields, placeholder PCB), so geometry-bound
tests point HERE instead. Never edit; regenerating a new baseline means writing a
NEW fixture, not mutating this one. (Deliberately NOT under tests/golden/** — that
tree is CODEOWNERS-gated for the SB-08 bands; this is an ordinary test fixture.)
