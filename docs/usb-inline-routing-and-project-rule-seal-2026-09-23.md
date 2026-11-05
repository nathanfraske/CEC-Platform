# Inline pair routing and exact project-rule handoff — 2026-09-23

Evidence root: `build/usb-constructive-20260923/`.

**Accepted result: 0 native DRC errors / 191 unconnected items, down from 199.**
USB is now complete through every connector, protector and MCU contact. Both
USB and the existing six-branch CAN network pass independent saved-board
physics and reference-plane checks. This is a critical-routing checkpoint,
not a fabrication candidate or authorization to ignore remaining power work.

## Scope and incumbent

The immutable starting checkpoint is
`build/hub-route-start-20260923/can-final-proof/board.kicad_pcb`, SHA256
`965e13b59b1597f887a0fa57bd08f39b8ea23354672dcfacb8d0e080e94a9fae`.
It has **0 native DRC errors / 199 unconnected items**, and all six CAN branches
are complete. This work preserves all 271 existing copper items, including
97 local-power items and the CAN return infrastructure. It neither expands the
outline nor changes the dead-bug mating arrangement or power budgets.

## Root causes and reusable repairs

1. **Inline topology was treated as a single Euclidean bank assignment.**
   The bounded bank-domain generator retains the incumbent assignment, individual
   station reversals and the all-reversed proposal, within an explicit cap. It
   preserves every actual P/N contact and does not swap polarity. Native guards
   and whole-chain qualification decide which proposal is usable.
2. **The constructive terminal solver skipped real inline legs.** Pre-existing
   package ties and multiple lands prevented the old fresh-complete-pair context
   from applying. The roadmap now recognizes actual legs of the inline physical
   chain (including alternative banks), but not invented virtual portals. The
   existing local coupling floor, hard physical clearance and final whole-pair
   coupling/skew checks remain in force.
3. **Guessed future launch rectangles could make both leg orders fail.** After
   the two reserved orders, a bounded atomic retry routes the short physical
   dependency first and makes the next leg respect its actual copper. Only
   internal proposed launch reservations are deferred. External power and other
   critical-route reservations are unchanged; any failed successor rolls back
   the entire new chain, including ground returns.
4. **An unrelated inherited local taper poisoned the trunk validator.** The
   assembled-graph callback included all existing pair copper, then required the
   trunk's nominal gap even between two unchanged fine-pitch fanout segments on
   another layer. Each legal trunk therefore inherited the same false failure.
   Incremental validation now requires full electrical spacing for every
   interaction involving the proposed trunk, and physical netclass clearance
   between unchanged local fanouts. Crossings, annular-land collisions, final
   native DRC, whole-pair ownership, coupling and skew are not waived. The
   default whole-graph check is unchanged.
5. **Native materialization could overwrite the executable project rules.**
   An older rotated diagnostic had a Default-only project, changing the USB gap
   from 0.34 mm to 0.25 mm. It is excluded from acceptance. Materialization now
   captures the explicit source `.kicad_pro` / `.kicad_dru`, verifies that the
   source did not change, and restores those exact bytes before qualification
   and final atomic publication. Unowned rule-file introduction is refused.
   Copper-free fresh sources may resolve a native Default-only project shell
   or missing custom-rule file from their explicit configuration, with those
   donor bytes also sealed. Routed/frozen sources never take that fallback.
   In-place rewrites are staged too, so they cannot overwrite the authority
   that the transaction is supposed to verify.
6. **Native tail cleanup was missing at the critical checkpoint handoff.** A
   local escape can join a package tie before reaching its nominal endpoint;
   that leaves a connected pair plus an unnecessary terminal tail. Native DRC
   caught one 0.1414 mm generated track in this trial. The reference handoff now
   reuses the existing exact-UUID monotonic cleanup, restricted to this
   transaction's new pair tracks. Every inherited item, via and non-pair net is
   preserved. Each mutation refills zones; independent checkpoint admission
   reruns connectivity, old/new pair physics and native score afterwards.

These are parameterized rules without board-name, reference-designator or
coordinate exceptions. Synthetic regressions cover renamed nets, translations,
rotations, reflection, physical clearance underruns, new-to-old crossings,
bank-domain bounds, exact rollback, source-policy changes and native-save rule
loss. The final combined targeted suite in `complete-final-tests.log` passes
**1,256 tests and five subtests**. Earlier overlapping suite counts are not added
to this count. A broader native rehydration test exposed the missing fresh-source
and in-place policy cases; both were repaired before this final passing run.

## Measurements

The final pre-fix normal transaction (`native-atomic/report.json`) spent
**509.93 seconds** and rolled back the incomplete USB pair. Its last dependency
order built the short leg but rejected every long-leg trunk.

After the incremental-geometry fix, the same isolated dependency order
(`long-scope/report.json`) constructs both legs in **8.98 seconds**, with
81.2% measured coupling on the short surface leg and 98.3% on the long inner-layer
leg. Whole-chain diagnostic qualification passes: **2.528 mm skew against the
existing 3.81 mm limit**, and member detours approximately 1.20x / 1.21x against
2.0x. That isolated test is diagnostic, not a substitute for the automatic
transaction or saved-board admission.

The fresh rotated pose is produced by the generic placement-feedback proposal,
not a manually edited pad coordinate. `rotation-sealed/placement-proof.json`
records **0 DRC / 199 opens** before USB routing and the unchanged declared USB
geometry: **0.20 mm width, 0.34 mm gap, 0.20 mm clearance**. The original CAN
checkpoint remains immutable.

The normal automatic transaction (`native-scoped/report.json`) then succeeds in
**185.02 seconds**, including the bounded failed first bank and the leg-order
retries. The 8.98-second isolated measurement is not advertised as full pipeline
runtime. The production engine and source remained unchanged during that run.

The first saved-board proof correctly rejected **1 DRC / 191 opens** because of
the native dangling-tail warning; it was not published. After the generic native
handoff cleanup, `usb-clean-final-proof/checkpoint.json` accepts **0 DRC / 191
opens**, preserves every parent copper item, and verifies both complete pairs.
Fresh-fill baseline comparison attributes all eight closed opens to routing,
not stale-zone refill. Final saved USB skew is **2.3865 mm / 3.81 mm**, and CAN
skew remains **3.0669 mm / 4.0 mm**. See `final-metrics.json` beside the checkpoint.

## Regression control

`pcie2-final-regression.json` retains **0 DRC / 0 opens**, 749 tracks, 197 vias
and 1199.913 mm copper on the PCIe two-port control. Its two existing independent
release findings remain: the RS1 pad-2 Kelvin departure direction and one CAN
branch's 80% adjacent-ground coverage against 95%. Full release acceptance is
still false; those findings have not been concealed or waived.

## Full-pipeline continuation and next blocker

The bounded two-candidate continuation is in `residual-start/`. Source intake
passes in 13.49 s, placement admission in 30.33 s, and routing preflight in
97.54 s. The detailed-route stage runs both candidates, but **neither reaches
broad autorouting**: both stop at `local_power_prefix`, because local PI/Kelvin
and the exact power plan do not coexist. Their failed-candidate 9999 counts are
sentinels, not measured board DRC counts.

The retained failure stack identifies a proposed VCC_P1 power-via field blocked
by foreign track copper, ending in `replacement_lattice_exhausted`. It also
records derived power reservations overlapping retained CAN tracks. This is a
power/critical-route ownership and landing-path integration problem, not proof
that more random routing seeds are needed. No additional residual route is
accepted; the final selected incumbent stays **0 DRC / 191 opens**. Fabrication
remains withheld, including the separate hardware/source qualification gates.
The bounded run has ended; no unattended wave is left running.

Next work is a generic, exact power-landing replan that preserves the admitted
critical prefix, rather than evacuating protected CAN to satisfy a provisional
power reservation. Do not claim the new prefix satisfies that still-open gate.

## Published checkpoint and source integrity

Accepted board:
`build/usb-constructive-20260923/usb-clean-final-proof/board.kicad_pcb`

SHA256: `3a41e9c2f0d76753815d29d8eb13dc548377bbb86e92d5f9f34b687752b84818`.

Dashboard:
`http://localhost:8090/?id=20260923-hub-usb-can-verified-3a41e9c2f0`.

The archive contains models-off top/bottom renders and all six copper-layer
plots, produced from that exact board hash. The inner-layer USB route is visible
with `&panel=plot2`; the ordinary top render cannot show that inner copper.
Fresh Windows GET checks returned HTTP 200 for the page and all eight image/
layer endpoints, and the archive API lists this ID.
The final metric receipt confirms the original Hub/ATX placements, the original
CAN checkpoint, active mating manifest and PCIe control hashes are unchanged.

Approximately 82 MB of bounded diagnostic artifacts were retained for this
slice. No outline enlargement, current-budget change, weakened clearance, new
fabrication waiver or board-specific coordinate repair was used.
