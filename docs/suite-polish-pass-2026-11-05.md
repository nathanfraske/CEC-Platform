# Suite polish and fan-out research pass — 2026-11-05

This is a bounded design/refinement and tooling pass, not fabrication approval.
Three explicitly requested research/audit workers used GPT-6.1 Sol; the primary
frontier agent chose and visually inspected the actual board edits. No old wave
manager, model service, new browser tab, background model billing, or unbounded
optimizer was launched.

## Actual board changes

The starting immutable control is `review-20261105-atx-refinement`, receipt SHA
`33d752bae179fede25a4e90543d02c95bbcc6071bedcf26a6bc7925c1333f8a7`.

| Board | Accepted native change | Measured improvement / preserved limits |
| --- | --- | --- |
| PCIe two-port | Remove the EN pad-to-via square detour; use the same existing terminals with a 45-degree lead | 0.292307 mm less centerline; native 0 opens / 0 errors / 19 warnings / 0 exclusions |
| EPS | Shorten the In2.Cu USB mux-control detour without changing its source launch/arrival or top branch | 2.246022 mm less centerline; native 0 / 0 / 45 / 0; five inherited field-policy blockers remain |
| 12VHPWR | Bevel the EN corner and give P2–P6 plus the clear lower P1 bus real source-retaining chamfer45 contours | 0.146447 mm less signal centerline; power-contour findings 86 → 72 (14 fewer, 16.3%); native 0 / 0 / 105 / 0 |
| Hub, ATX, PCIe three-port, three output daughterboards | No placement/copper edit in this pass | Original PCB bytes retained; all retain native closure |

Total signal centerline reduction is **2.684776 mm**, not a claim of global
routing optimization. The 12VHPWR ordinary craft count remains 32 and its 60
non-octilinear observations remain; this pass does not finish its cosmetic
backlog. EPS/PCIe-two-port craft counts remain 33/11 despite locally better
routes. Aggregate counts cannot establish target issue clearance or prove no
replacement flaw; semantic issue/outcome receiving remains proposed.

The contours are actual saved native copper, never fictitious FEM slabs.
Original rated tracks remain; no conductor was narrowed, current margin
reduced, layer sharing assumed, or new barrel capacity credited. The declared
8.33-A lane load and deliberately larger 9.2-A routing budget plus its existing
margin were preserved as different source contracts, not forced equal.

One native-passing EPS bevel trial was **rejected visually** because retained
overlapping copper left a spur. Only the separate clean In2.Cu edit was kept.
Several tempting large straightening attempts were refused for real foreign
pads/vias, return-path/launch or contact constraints; none was waived. A batch
of independent power macros was refused because each requires its own received
transaction. No failed or partially checked candidate entered the review set.

## Generic defects found and addressed

1. The contour actor used a legacy current helper that incorrectly required
   source thermal load and routing budget to be numerically equal. It now uses
   the existing typed current authority and preserves both contracts.
2. Independent source-model replay compared Python tuples against JSON lists.
   Canonical JSON identities now compare the complete unchanged model; altered
   current-floor canaries still fail.
3. Contour replay demanded unrelated KiCad property-field reordering. It now
   replays only owned nodes and preserves every other literal source object;
   an unrelated reference visibility mutation still fails.
4. Assembly receiving compared category names, hiding replacement/worsened
   collisions. Typed native fault identities and signed margins replace that
   comparison; unknown/malformed evidence fails closed.
5. Free-text intent was part of failed-action identity. Stable action/context
   fingerprints now distinguish changed design from prose-only retry and
   corrected-context reevaluation; plateau signals are latest-source/board
   scoped and survive restart/history paging.
6. Hash-bound plots could show an unrelated corner and multi-layer proof was
   overwritten. Native material deltas now bind actual layers/regions; views
   accumulate; selection/publication receive exact pairs, hashes, inventories
   and actual SVG viewports. Conservative framing is evidence relevance, not
   proof of attention or physical qualification.
7. Publication reopened an explicitly based workspace against the default Git
   checkpoint. That could restore old untouched boards. Durable intake binding
   and explicit publication base checks are part of the integration fix, with
   source-change/reopen/mixed-base regression tests. The intermediate incorrect
   private composition was not published to the user's inspector. All three
   selected boards were preserved in the final composition.
8. The inspector selected only the first field receipt. A new candidate hash
   could therefore lose visible inherited field debt. All field reports are now
   verified and normalized, with exact candidate-SHA lookup; stale, incomplete,
   malformed and conflicting evidence refuses. Fresh EPS observation retains
   its five blockers without relabeling the old board's evidence. Multiple
   layer/crop plot pairs also survive checkpoint export and inspector display.

The connected-placement audit also found a **remaining** false refusal:
stationary owner footprints in recognized reference-map groups are rejected;
rotating mapped annotations additionally has producer/receiver transform
mismatch. No groups were unlocked/stripped and no pose was forced through.
Fixing source-authorized annotation transport is a separate generic slice,
not permission to move parts without restoring their owned connections.

The all-piece P1 contour was refused for enclosing a real foreign P2 launch.
One explicitly narrower, separately received lower-L edit succeeded. The
constrained upper winding remains original; it was not squared through nearby
copper or treated as an aesthetic clearance exception.

## Research conclusions and next implementation order

See [agentic research, code gaps and ten-task ladder](agentic-pcb-research-review-2026-11-05.md)
and [actual interfaces, stackups and physics methodology](pcb-physics-methodology-review-2026-11-05.md)
for primary, version-pinned sources and detailed applicability limits.

1. Bind a typed target outcome and semantic new-finding comparison to each
   edit; give the frontier complete local owner/port/return/obstacle packets.
   Preserve human functional rows/grids, not blind same-value alignment.
2. Repair recognized annotation transport with cardinal producer/receiver
   parity, then benchmark real decoupler/functional-row moves and their return
   lengths. A prettier grid must not worsen the electrical loop.
3. Enable complete source-bound USB/CAN pair and actual reference-continuity
   receiving for affected transactions; retain existing device-specific
   budgets and test plane slots, disconnected grounds and layer transitions.
4. Reconfirm the high-current supplier stackup; calibrate actual USB cross-
   sections and tolerances, then use selective PDN/analog parasitic models
   with real MPN/edge/load/noise inputs. No invented ripple/current budget.
5. Qualify the production CAN topology, assembly/thermal paths and process
   finishing separately. Curves, fences and guards are interface-dependent;
   none is a blanket substitute for reference continuity or impedance.
6. Measure useful received improvement per semantic attempt/hour, receiver
   false accepts and repeated identity/native-load overhead before adding
   compute or orchestration. The ten-task ladder is specified, not yet a fully
   executed autonomous-design benchmark.

The nine-PCB suite remains a native **0-opens / 0-errors** review control, not
an SI/PDN/EMC/current-sharing/thermal/mating/fabrication release. Existing 283
warnings and EPS field debt were retained explicitly. No manufacturing pack,
Gerbers, procurement substitutions or release authorization were produced.

Detailed private jobs, plots, XML and receipts are retained under
`C:/Users/Admin/Documents/CEC-Board-Reviews/suite-polish-20261105/`.
Portable controls and the final test/publication evidence are recorded with
the completed integration handoff; historical receiving is never relabelled
as a fresh physical qualification.

## Final integration evidence

- Portable nine-board receipt: `checkpoints/review-20261105-suite-polish/receipt.json`,
  SHA256 `78b1f266ab3773ed6322a7557d4e512f3133949a581c750a6f27153676d44a50`.
  All nine received fresh native checks in relocated library context: zero
  opens, errors or exclusions; 283 warnings retained. The earlier control is
  still immutable. The final publisher preserved all eight untouched board
  hashes, including the already-refined EPS and PCIe two-port candidates.
- Integration tests: **229 passed** in `current-control-tests.xml`, including
  the newly pinned real nine-board control, contour receiving and inspector
  cases. Physical backend replay: **653 passed**, zero failures/errors/skips,
  in `backend-integration.xml`; these sets overlap and must not be summed.
  JavaScript syntax validation passed. Source and dependency identities were
  unchanged over the completed backend run.
- Trackpad inspection manifest: SHA256
  `d3d8ba967640cf97e3c3babcd8bb7874cb38f4ce48e946b4ceeb6062ffaad953`,
  in the external `inspection-final` directory. Its complete offline bundle is
  4,205,980 bytes. The HTTP manifest reports the exact new portable receipt and
  EPS's **five recorded blockers; not admitted**. No board-view tab was opened.
- An idle-availability check found WSL stopped because its existing Windows
  keepalive task had stopped. That existing task was restarted; the enabled
  read-only system service remains the only CEC dashboard process. No old
  solver service was restarted or scheduled.

Research reports and proposed benchmark tasks are not a claim that all
specified future physics/agent features have been implemented. In particular,
complete-pair receiving, calibrated parasitic/PDN/channel evidence, semantic
craft outcomes and mapped-annotation placement remain separate next slices.
