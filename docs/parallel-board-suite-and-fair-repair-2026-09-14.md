# Parallel board-suite continuation — 2026-09-14

## Current: ATX/Hub actual-size review and bounded ordinary corridor feedback

Read [size/spacing and corridor feedback](atx-hub-size-and-ordinary-relief-2026-09-20.md).
Use **`build/ordinary-relief-next-inputs-20260920.json`**; all six PCB inputs
remain unchanged. ATX is 82 × 95 mm, Hub 84 × 80 mm, and ATX's middle terminal
pitch is restored to its original 8 mm with 0.5 mm copper-envelope gaps. The
actual mated Hub still fails four port-access checks; joint compaction and
paired admission integration are required, not independent outline shrinking.
Ordinary power-corridor failures now produce bounded, electrically consistent
relief diagnostics. The completed 97-second EPS pass closed no blocker; final
read-only counterfactuals found no acceptable path even without movable
obstacles, pointing the next investigation toward fixed escape/topology/search.
282 tests plus two subtests pass, four skipped; six-board native replay and
historical PCIe2 control remain unchanged. No routing or fab promotion occurred.

## Historical: native assembly repair verified; compact EPS retained

Read [native assembly repair](native-assembly-repair-2026-09-20.md).
Use **`build/native-assembly-next-inputs-20260920.json`**. EPS now retains a
native-clean 88 × 40 mm output; ATX remains 82 × 95 mm and native-clean.
The old EPS regression was introduced by a later AABB-driven repair, not the
initial compact selection. Native assembly faults now survive craft/repair
projection, scoring and trial vetoes. 452 tests pass, with six-board physical
replay and historical PCIe2 control parity. Three EPS corridor failures and
three ATX admission blockers remain; neither has entered routing. Ordinary-layer
power-corridor relief feedback is the next diagnosed gap. No unchanged wave
is running and no release authority was granted.

## Historical: parent-owned mating repair published; daughter copper rebuilt

Read [parent-owned mating repair](parent-owned-mating-repair-2026-09-20.md).
The owner approved daughterboard changes. EPS/ATX original main pitches are
restored without enlarging main outlines; the daughters are now 30.25 × 18.5 mm
and 59.8 × 21.3 mm respectively. Four BETA geometry changes and two DRC-clean
daughter copper rebuilds have been published with backups and invalidated
release authority. Both daughters have zero hard DRC errors and zero opens;
warnings, thermal revalidation, measured mating fit, and physical keying remain.

**Use `build/parent-owned-next-inputs-20260920.json`.** It supersedes the old
safe-edge plan. Retain the clean 92 mm EPS seed, not the overlapping 88 mm trial.
ATX retains its developed 82 × 95 mm layout. Both passed current-source intake
but remain blocked before routing on corridor/ground-return/craft issues.
Six-board physical replay and the historical PCIe2 control pass unchanged.
No unchanged wave is running. Earlier no-authorization/no-CAD-change statements
below are historical and are superseded by this completed repair.

## Historical row-width budget: daughterboard decision was still needed

Read [paired-row outline budget](paired-row-outline-budget-2026-09-20.md).
The current owner authorized repair, not silent outline growth. A new generic
translation/edge-envelope calculation confirms the minimum screened EPS row
needs 30.10 mm versus 28 mm, and ATX including the signal companion needs
57.56 mm versus 54 mm. Exact restoration of EPS's earlier 7.75-mm pitch needs
30.25 mm. These are screening values, not release-qualified dimensions.
The owner was asked whether to permit minimal daughterboard growth while
keeping main-board outlines unchanged. No answer or physical change is assumed.
All current CAD, input-plan hashes and dispatch holds remain intact; six-board
native replay and the historical PCIe2 regression/control match. Do not confuse
better failure attribution with repair or run another unchanged held wave.

## User clarification: earlier main rows were compressed by the pipeline

Read [mating row regression history](mating-row-regression-history-2026-09-20.md).
Native before/current readback proves EPS pitch 7.75 -> 7.00 mm and ATX small
terminal pitch 8.00 -> 7.00 mm, with unchanged 7.50-mm copper width. This was
the September 11 alignment ECO, not the latest guard repair. The span shortfalls
below are relative to the compressed daughter patterns, not proof the original
main-board outlines must grow. Recover the established main clearance and
reconcile both mating halves jointly before proposing a dimension increase.
No unilateral restore, relaxed edge span, changed land, or unverified 3D
transform is authorized. CAD and the current hash-bound plan remain unchanged.

### Completed diagnostic: partial-leg roadmap does not close VHP USB

Read [local-fragment roadmap probe](local-fragment-roadmap-probe-2026-09-20.md).
A private proposal-only fallback after template failure produced no accepted
pair or retained copper. The deeper 20,000-state allowance exhausted P's 2,345
reachable states without timing out; N found a path. This is finite-domain
evidence, not proof no physical route exists. Do not integrate or repeat either
unchanged domain. No production scripts, current inputs, or publication state
changed. All source/hierarchy hashes and original native copper remain intact;
workers have ended. The initial VHP selector typo and completed isolated PCIe3
control probes are explicitly recorded. No unchanged images were republished.

## Current mating-overlap stop: no worker for an uncompiled shared row

Read [mating-conflict dispatch stop](mating-conflict-dispatch-stop-2026-09-20.md).
Campaigns now record the paired-geometry conflict before launching any worker;
the direct pipeline also checks before source normalization/route-authority
setup. Both use the shared declaration, not an EPS/ATX blacklist. The invalid
physical rows remain unrepaired pending the mating-span choice; do not claim
that fail-fast scheduling fixed the boards themselves. Native six-board replay
and historical PCIe2 hash/regression/probe parity pass. No input plan, source
CAD, routing, or fabrication status changed in this slice.

## Latest continuation: safe input handoff, recovery budget and return-hole work

Read [recovery finalization and return-hole snapshots](recovery-finalization-and-return-hole-snapshots-2026-09-20.md).
**Current next-input plan is now `build/safe-edge-next-inputs-20260920.json`.**
It advances only VHP to the independently proved edge-repaired placement,
SHA256 `e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`.
The input is explicitly journal-bound with fresh source/hierarchy signatures;
current-code physical admission passes again. Other five inputs and all
canonical BETA PCB/schematic files remain unchanged. Keep Hub's 174-pose history
and EPS/ATX's pending mating-span choice. No fabrication promotion is implied.

One actual full continuation ended at 445.281 seconds with **no new accepted
routes**. Source/physical gates passed, USB critical routing remained refused,
and the staged fallback repeated unadmitted geometry. Its final physical
measurement then exhausted the mere 34.812 seconds left. The working PCB is
byte-identical to the input. VHP retains 220 opens and C7's local-interconnect
deferral. Evidence: `build/verified-edge-continuation-20260920`.

Generic fix: critical recovery now shares the existing finalization reserve,
not only the later co-optimizer. Budget interruption cannot commit partial
receipts; genuine crashes still propagate. Generic performance fix: reuse the
existing scalar hole index within each immutable pair-return field, rebuilding
after each new barrel. Across 25 native fields/four eligible boards, all 1,331
seat queries and exact results match; native track enumeration falls from
**1,474 to 143**. This is not a whole-pipeline speedup or connectivity claim.

**297 tests + two subtests pass**, including real supervisor expiry and loaded
native-parent preservation. Six-board geometry and historical PCIe2 exact
hash/regression/probe parity pass; core audit passes, wider release remains
false. New VHP input recheck:
`build/edge-continuation-physical-current-20260920.json`. Cross-board work proof:
`build/return-hole-snapshot-cohort-20260920/report.json`.

[Attempt review](http://localhost:8090/?id=pass-verified-edge-continuation-20260920-12vhpwr-standard-4e74d71338)
shows the unchanged checkpoint, correctly marked budget exhausted/not fab
signoff. Both images inspected and served HTTP 200. Do not present the same
board as new routing progress. All workers finished; free space remains above
the 16-GiB floor.

Next: a real generic matched-pair station/return-construction improvement,
followed by affected-board replay. Staged USB refused asymmetric layers/vias,
two missing returns, 94% reference coverage (95% required), and 16.5% coupling
(80% required). Do not repeat the unchanged fallback or the cleared edge wave.
The budget fix is independently tested, not yet a claimed successful full
board pass. EPS/ATX stay held rather than rerunning their known overlaps.

## Latest verified continuation: retained evidence and VHP edge closure

Read [scoped evidence and native edge closure](noncontact-evidence-and-native-edge-closure-2026-09-19.md).
This supersedes the prototype restriction below. Source/member-bound retention
of construction reports is implemented; unchanged negative observations remain
visible. Strict non-contact craft fallback now defaults on, with an explicit
opt-out. It grants no copper ownership, and unsupported/attached moves still
refuse. Native edge-progress screening and bounded cardinal-first proposals
prevent spending the expensive craft budget on unchanged edge faults.

**371 tests pass.** Six-board replay and historical PCIe2 hash/regression/probe
parity pass. Source-bound retention is independently exercised across the four
eligible boards; EPS/ATX remain held before repair. All canonical source and
hierarchy hashes are unchanged. Evidence:
`build/noncontact-evidence-final-suite-20260919/report.json` and
`build/noncontact-retention-cohort-20260919/report.json`.

Private VHP output:
`build/noncontact-evidence-placement-20260919/12vhpwr-standard/board.kicad_pcb`,
SHA256 `e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`.
**All 3 edge faults cleared; placement physical gate passes; all 506 original
copper items and the entire other native board are unchanged.** Independent
full DRC preserves every other raw issue count and all pair results. There are
still **220 opens and the C7 local-interconnect deferral**. Not fab-ready and
not promoted; the canonical VHP replay correctly still shows its old 3 faults.

[Front/back dashboard review](http://localhost:8090/?id=pass-20260919-noncontact-edge-repair-12vhpwr-standard-2feaf0c43f).
Mirrors are under
`C:/Users/Admin/Documents/CEC-Board-Reviews/noncontact-edge-repair-20260919/12vhpwr-standard/`.
Both images were inspected; dashboard and immutable PNGs return HTTP 200 from
Windows localhost. The blocked label refers to remaining routing/release work.

Next: explicitly rebind this verified VHP output before the deferred local
interconnect and priority routing. Do not rerun the cleared edge batch. Keep
`build/additive-first-next-inputs-20260917.json`, the Hub's 174-pose history,
and the EPS/ATX pending mating-span choice unchanged. No silent geometry/span
increase or unchanged failed interface wave. All workers finished; ~64 GiB free.

## Previous continuation: non-contact proposal materializer, not yet automatic

Read [non-contact placement prototype](noncontact-placement-prototype-2026-09-19.md).
The new generic native materializer proves that detached SMD pose changes
retain the entire rest of the board, without claiming or deleting existing
routes. It rejects old/new pad, trace and via contact, zone-coupled layers,
holes, locks and boundary changes. Save/reload and whole-board inverse-pose
proofs cover native side effects. Wrapped-angle comparison is repaired.

**Do not enable automatic fallback yet.** The experimental
`placement_noncontact_resume` parameter defaults false and no board policy
enables it. Scoped blueprint/rail evidence retention is not implemented;
blindly carrying those construction receipts would be unsafe. One bounded
VHP experiment accepted zero moves and left the source/copy byte-identical.
Its anonymous-path current-policy error is a harness issue: direct canonical
inspection resolves all six input chains. Do not repeat that experiment or
report its missing policy as new physical board debt.

**358 focused tests and a final 25-test native/protocol subset pass.** Six-board
regression: `build/noncontact-placement-final-suite-20260919/report.json`.
All source/hierarchy signatures and historical PCIe2 hash/regression/probes
match. Core generic audit passes; wider release debt remains. All workers
finished, approximately 64 GiB free. No candidate promotion or new gallery.

Next bounded work: source/member-bound construction-evidence handoff, explicit
policy identity and cheap native edge-progress screening before costly craft
trials. Keep `build/additive-first-next-inputs-20260917.json`, the Hub's
174-pose history, and EPS/ATX's pending mating-span choice unchanged.

## Latest slice: native pad-edge admission and bounded proposals

Read [native pad-edge placement](native-pad-edge-placement-2026-09-19.md).
The placement gate no longer omits pad-to-edge/cutout clearance. Existing
central qualifications remain visible, and footprint-owned cutouts are not
given futile rigid translation proposals. Complete-cell, fixed-anchor,
native, craft and frozen-copper gates remain mandatory.

**301 tests pass.** Final six-board replay:
`build/pad-edge-final-suite-20260919/report.json`. Source/hierarchy hashes and
historical PCIe2 hash/regression/probes match. The three known VHP edge faults
now correctly block placement admission. This is a gate repair, not physical
board progress; other geometry/craft debts remain.

One bounded VHP repair refused before trials because the placement prefix
does not cover **228 existing Kelvin copper items**. Source and working copy
remain byte-identical. Receipt:
`build/pad-edge-placement-20260919/ownership-refusal.json`. Do not rerun that
transaction unchanged or discard/adopt the copper without qualified ownership.
Next independent work is route-owned local repair/preservation, not another
identical wave. The linked note also records existing mounting-edge waiver
debt; central qualification is not new physical qualification.

All workers finished; approximately 64 GiB is free. No promotion or new board
image. Keep `build/additive-first-next-inputs-20260917.json` and the Hub's
174-pose history. EPS/ATX remain held pending the mating-span/arrangement
choice below; do not silently widen them or spend unchanged routing waves.

## Latest slice: repair the producer of shorted mating rows

Read [paired row generation repair](paired-row-generation-repair-2026-09-19.md).
The shared row solver now combines the installed copper on both mating halves
with the existing body/tolerance budgets before generating either half. It
redistributes available slack without growth; infeasible rows cannot generate
a new body-only pitch or reach the PCB writer. This fixes the producer, but
does **not** claim the existing ATX/EPS boards are physically corrected.

Their locked straight-row spans remain incompatible with this envelope policy;
the owner has been asked whether minimum mating-span changes are allowed or
alternative arrangements/parts must be evaluated within the old span. Do not
silently expand boards, shrink lands, or repeat unchanged failed waves.

**138 tests plus 41 subtests pass**, including native saved-board overlap-to-
clearance repair on both halves. Six-board regression and historical PCIe2
hash/probe parity pass. No PCB or schematic was changed or promoted. Evidence:
`build/paired-row-compiler-suite-20260919/report.json`.

## Latest slice: exact physical power reservations clear one real return

Read [exact power reservation placement](exact-power-reservation-placement-2026-09-19.md).
The generic guard now retires obsolete raster halos only after complete exact
power admission, retaining every final pour, future bridge neighborhood,
explicit/unknown reservation and conservative incomplete-state behavior.
Hub local-return refusals reduce **two to one**: U7.1/C15 now constructs with
qualified local copper. U7.7/C27 still fails. Existing copper and all frozen
power geometry remain unchanged. This is not yet routing or fab admission.

**340 tests and three subtests pass.** Complete production replay:
`build/exact-power-reservation-suite-20260919/report.json`. All six canonical
source/hierarchy hashes and historical PCIe2 regression/probes match. Independent
saved-native checks preserve the original copper and find zero foreign copper
crossings in Hub/PCIe2/PCIe3 protected pours. VHP's checker is N/A for this source,
not a newly passing proof. Core generic audit passes; wider debt remains 23/380.

One 16-trial Hub batch accepted no placement and revisited no old pose. Latest
history is **174 poses** at
`build/exact-reservation-placement-20260919-qualified/hub-standard-rev2/board.placement-search.json`.
Use that history, not the older 158-pose receipt. All workers are finished;
approximately 64 GiB remains free. Keep canonical
`build/additive-first-next-inputs-20260917.json`. Other routing/interface debts
are unchanged. No new candidate, canonical promotion or unchanged-board image.

Do not integrate the blanket future-mask omission counterfactual: it places
vias through actual power copper. The newly repeated fine-ray diagnostic also
fails to clear the remaining cell; do not repeat it unchanged. Next work is
constructive complete-cell surface access at the fixed owner, or an explicitly
qualified upstream transaction, not more identical placement waves.

## Latest continuation: finer native return sampling is not the missing fix

Read [refined native return domain](refined-native-return-domain-2026-09-19.md).
A bounded private ablation tested **2,880** additional straight-ray via seats
over the full existing 1.5 mm reach, using unchanged native admission and the
existing two compact process geometries. No Hub return domain succeeded; every
sample retained a via-spot obstruction. Do not integrate or rerun this unchanged
refinement. This is not a mathematical no-path proof.

Complete cohort: `build/refined-return-domain-20260919/report.json`. All six
canonical source/hierarchy hashes and historical PCIe2 control results match.
Production scripts stayed unchanged; no new candidate, promotion or image.
Keep the canonical plan and **158-pose** history from the section below.
Hub remains at two real return blockers; all other route/interface debts remain.
All workers finished. Next: constructive ground-access ownership/dependency
repair and complete-cell handling of late intents, not more unchanged waves.

## Latest slice: return-feasible references and electrical contact placement

Read [return-feasible placement domain](return-feasible-placement-domain-2026-09-19.md).
The Hub now has **two craft blockers instead of three**. This removes an
internally contradictory ideal-placement reference; it is not a new route or
a physical PCB change. The old reference's 2.912 mm return violated the hard
2.500 mm return limit. The generic coupled reference solve now supplies a
1.420 mm shortest feasible supply target, with the same 0.250 mm margin.
The actual C2 supply/return distances remain 1.275/2.417 mm and its native
cell construction passes. Both U7 ground-return construction failures remain.

The new bounded electrical/courtyard contact proposer supplements the lattice.
One new Hub pose passes the frozen-power guard but fails native craft checks;
it is not promoted. Latest Hub work history is **158 poses** at
`build/contact-seating-suite-20260919-qualified/hub-standard-rev2/board.placement-search.json`.
Do not seed the older 157-pose receipt or retry the unchanged new rejection.

Final six-board replay: `build/contact-seating-suite-20260919-qualified`.
All canonical source/hierarchy hashes and historical PCIe2 control probes match.
Keep `build/additive-first-next-inputs-20260917.json`. PCIe2's five opens,
PCIe3's critical-route debt, VHP's C7 deferral and EPS/ATX interface holds remain.
No new board image, canonical promotion or fab signoff is claimed.
Core audit (now including the new solver) passes; broader inventory remains
23 physical / 380 runtime findings. Focused tests: **366 pass**. Wider suite:
**1,104 pass, 19 skipped, three passing subtests, two EPS integration failures**.
See the linked note for negative constructor studies and the existing EPS
residual/late-intent ownership failures. Next: constructive frozen-owner
return access, not more unchanged waves.

## Latest slice: rotate the capacitor about its supply pad

Read [fixed-supply return rotation](fixed-supply-return-rotation-2026-09-19.md).
The generic return-placement family now offers native-evidence-bound capacitor
rotations that expose ground while keeping the supply terminal fixed. No power
bus, via rule, current assumption or placement admission gate is relaxed.
**982 tests and two subtests pass.**

Final complete cohort: `build/supply-pivot-suite-20260919-final`. All six
canonical source/hierarchy hashes and the historical PCIe2 control match.
Three new proposals on a hash-bound PCIe3 diagnostic descendant produce two
physical/craft survivors. The 180-degree choice clears its return blocker with
no deferral; saved-native proof shows 1.92 mm return displacement, exactly fixed
supply pad, unchanged other terminals/copper and unchanged power reservations.
Both survivors still have **11 Kelvin refusals**. This is constructive placement
progress on a private descendant, **not a canonical or routed improvement**.
Do not replay those unchanged critical-routing failures.

Verified body-free diagnostic preview, clearly `placement | BLOCKED`:
`pass-20260919-supply-pivot-placement-diagnostic-pcie-8pin-3port-edde6e3142`.
Windows mirror: `C:/Users/Admin/Documents/CEC-Board-Reviews/supply-pivot-20260919/pcie-8pin-3port/`.
Both views were inspected and served HTTP 200. No release authority or promotion.

Hub's three blockers remain; fixed U7/C15 terminal evidence suppresses this new
free-capacitor domain. Keep its **157-pose** history unchanged at
`build/coupled-placement-suite-20260919-v2/hub-standard-rev2/board.placement-search.json`.
Other canonical boards, PCIe2's five opens, VHP's deferred local interconnect and
EPS/ATX interface holds are unchanged. Keep
`build/additive-first-next-inputs-20260917.json`. Core generic audit passes;
broader inventory remains 23 physical / 380 runtime. All workers completed.

Next: fixed-owner access transaction/proof for Hub and joint critical-input
access inside the PCIe3 electrical/power domains. A bend-only constructor
ablation found no new bent-path solution; do not weaken its independent gates.
The initial replay had harness-only direct-primary/optional-authority handling
errors; use the complete final cohort above. Approximately 64 GiB free.

## Latest slice: native electrical locality inside placement search

Read [native electrical placement domain](native-electrical-placement-domain-2026-09-19.md).
The shared dependency context and bounded legalizer now preserve individual
sense-input range, terminal ordering, and detector locality during primary and
collateral movement. Existing native contracts supply the identities and limits;
no new load assumptions or board-specific coordinates are introduced. Ordinary
craft and route-preflight primary menus are filtered before finite trial quotas.
This is a non-regression search domain, not a waiver of existing electrical debt.

**878 tests and two subtests pass.** Concurrent six-board replay:
`build/placement-relations-suite-20260919`. All canonical source/hierarchy hashes
and the historical PCIe2 control match. The same 35-primary PCIe3 domain now
yields three native physical trials instead of ten, rejecting 44 electrically
regressing beam shifts early. Zero late frozen-power rejections are retained.
The prior physically passing but worse-routing candidates are no longer emitted.
The three remaining variants fail pour-territory or local ground-return checks;
**no board is promoted and no routed-connectivity improvement is claimed**.

Hub's three craft blockers, 12VHPWR's deferred local interconnect, PCIe2's five
opens, and EPS/ATX interface holds remain unchanged. Keep canonical
`build/additive-first-next-inputs-20260917.json` and Hub's **157-pose** history at
`build/coupled-placement-suite-20260919-v2/hub-standard-rev2/board.placement-search.json`.
No unchanged Hub search batch was repeated. All workers completed; no new images.
Core generic audit passes; broader inventory remains 23 physical / 380 runtime.

Next: constructive local-ground-return geometry and electrically feasible pose
generation. Direct atomic child/grandchild variants retain full native craft
gates but do not yet all have this slice's early electrical filtering. Do not
rerun the three rejected PCIe3 variants or claim the entire pipeline is closed.

## Latest slice: electrically complete, fixed-power-aware collateral placement

Read [coupled placement and frozen search](coupled-placement-and-frozen-search-2026-09-19.md).
The production bounded legalizer now carries transitive detector/amplifier,
paired-station and owner/bypass groups inside its search. Missing/fixed members
cannot be split off, and fixed-primary proposals are rejected before evicting
neighbors. Early route feedback includes joint terminal moves through the fair
sampler. Craft and route-preflight callers use the same dependency context.

Search and commit share the actual frozen body/via reservations. Native
consumer-pad collision witnesses also guide tangent generation; body-over-inner-
bus permission is not a pad-contact waiver. Every native transform is restored,
power remains unchanged, and full physical/craft/routing gates still apply.
**854 tests and two subtests pass.**

Final concurrent six-board replay:
`build/coupled-placement-suite-20260919-final`. All canonical sources/hierarchies
and the historical PCIe2 control match. Core generic audit passes; broader
inventory remains 23/380. PCIe3's 35-primary domain now produces ten variants
with **zero late frozen-power rejections**, versus 28 previously. Fifteen fixed-
primary moves are rejected up front. Two physical survivors worsen Kelvin
refusals to 12 and are NOT promoted. Eight variants were tested under the initial
quota; `build/coupled-placement-tail-20260919` checks only the two deferred ones.
Both tail variants fail craft checks; all ten are now accounted for. Deliberate
primary moves still need electrical locality constraints as well as collateral
group closure. No existing/native copper changed in either tail trial.
No fab-ready board or new dashboard winner is claimed.

Hub ran two new 16-pose batches, revisiting none, with no accepted improvement.
Its three blockers remain. **The latest Hub history is now 157 poses:**
`build/coupled-placement-suite-20260919-v2/hub-standard-rev2/board.placement-search.json`.
Seed that history next time, not the older 125/141-pose receipts. The final cohort
does read-only Hub checks, not a third identical search batch. Keep canonical
`build/additive-first-next-inputs-20260917.json` and EPS/ATX interface holds.

Initial cohort's PCIe3 worker had a harness-only import error; it was retried
separately with the correct copper-inventory import. Use the final complete
cohort above, not the initial report containing that worker error.
Next: preserve critical terminal reachability/order under collateral movement,
and failure-directed Hub local-return geometry. Do not rerun the known 12-refusal
placements unchanged. Approximately 64 GiB free; no canonical board edits.
All workers have finished; the dashboard remains available on port 8090.

## Latest slice: bounded macro search retains its final frontier

Read [macro terminal frontier](macro-terminal-frontier-2026-09-19.md).
The shared legalizer used to discard successes generated on its last permitted
expansion. It now recognizes those goals without another expansion or weaker
gates. Six new synthetic/native regressions reproduce and cover the boundary.
**817 tests and two subtests pass** in the final broad run.

Concurrent six-board replay: `build/macro-frontier-suite-20260919`. On PCIe3's
35 previously colliding joint-terminal moves, bounded geometric variants rise
21→29. **None is admitted**: 28 fail exact frozen-power placement; the last fails
the existing detector/amplifier distance limit (8.5 mm versus 8 mm). This is
search coverage, not additional routed connectivity. Frozen envelopes were
checked after this diagnostic beam, not supplied to it. Pair-station completion
was applied in the harness; remaining production route-preflight integration
is not claimed done. No board/image promoted.

An unrelated negative-test failure was traced to native `SaveBoard` merging
the deliberately shorted fixture's via nets before testing. Native-only ablation
reproduces it; direct native serialization preserves both nets in 500 fixtures.
Test snapshots now assert net identity and retain overlapping/non-touching
clearance cases. Production serialization is unchanged; a general pre/post
connectivity-integrity boundary remains follow-up work, not a waived failure.

All canonical source/hierarchy hashes and the newer historical PCIe2 control
remain unchanged. Core generic audit passes; full inventory remains 23/380.
Keep `build/additive-first-next-inputs-20260917.json`, Hub's 125-pose history and
EPS/ATX interface holds. Next: fixed-power-aware collateral generation with
complete electrical dependencies, alongside changed Hub/VHP escape domains.
Do not rerun this same exhausted 35-proposal domain. No route workers remain;
approximately 64 GiB free.

## Latest slice: joint terminal range and launch-aware placement

Read [joint terminal range and approach](joint-terminal-range-and-approach-2026-09-19.md).
The existing production adapter now handles within-range wrong-launch demands
and jointly preserves both input approaches while moving complete device/bypass
cells. Directional halfplanes constrain both analytic and native-cavity proposals;
live pad identity binding and all downstream authority gates remain mandatory.
**493 tests and two subtests pass.** No board/ref/coordinate special case.

Concurrent six-board replay: `build/terminal-approach-suite-20260919`. PCIe3's
48 proposals yield five physical survivors; four reduce Kelvin refusals 11→10.
Four bounded full priority trials preserve all three pair constructors. Independent
saved-native proof in `build/terminal-approach-native-proof-20260919` verifies
valid reached inputs 1→2, partial-board opens 243→242, unchanged two dangling-via
DRCs, unchanged pair geometry and original frozen power polygons. The moved
cell's Kelvin branch is regenerated; do not claim all old private copper stayed.
Pair reference planes and ten missing inputs still fail admission. **No promotion.**

Important evidence correction: the priority harness's locked-only prefix/pair
checks were N/A on its unlocked private input; use the native-proof directory's
all-copper comparison, not those booleans. Earlier postflight directories are
superseded by that self-contained proof (spawned-worker output forwarding fixed).

All six canonical sources/hierarchies and the newer historical PCIe2 control
receipt remain unchanged, including its existing sideways-Kelvin blocker. Core
generic audit passes; full audit remains 23 physical / 380 runtime issues.
Hub/VHP blockers and EPS/ATX coupled-interface holds are unchanged. Keep canonical
`build/additive-first-next-inputs-20260917.json` and Hub's 125-pose history.
No workers left running; about 64 GiB free. Do not rerun these 48 proposals or
four compiler trials unchanged. Next: cooperative cavity recovery for joint
terminal cells, alongside changed Hub/VHP local-return and USB escape geometry.

## Latest slice: independent native Kelvin departure proof

Read [native Kelvin departure checking](native-kelvin-departure-checking-2026-09-17.md).
The production constraint now proves actual pad exit and input contact, rather
than accepting a near-pad inward endpoint. Its source-cut native graph preserves
voltage-only branches while rejecting sideways/backward current-input launches.
**438 tests and two subtests pass**, including 53 new-module tests. All six current
sources/hierarchies remain unchanged; current PCIe2's four terminal trees pass.
Rejected PCIe3 prefixes remain rejected; no new board/winner was promoted.

Important new control finding: the immutable historical PCIe2 archive has a
sideways RS1.2 departure reaching U10.9 (INA238 IN-), not Vbus. This is an existing
defect newly detected, not changed copper. Full score/DRC/opens, route-quality,
fab and board hash match; only one additional Kelvin constraint blocker appears.
See `build/kelvin-departure-control-20260917/comparison.json`. Do not claim old
blanket probe parity or waive the finding. Future parity can compare the current
receipt while retaining its explicit difference from the older baseline.

Concurrent checker replay: `build/kelvin-departure-production-cohort-20260917`.
N/A/missing contacts are not whole-board passes. Next: joint range/inward terminal
cell repair, then new Hub/VHP escape geometry; no unchanged wave reruns. Preserve
the canonical manifest below, Hub 125-pose history and EPS/ATX interface hold.
No workers left running; core generic audit passes, full audit remains 23/380.

## Latest slice: Kelvin fallback admission exposes wrong-direction launches

Read [Kelvin candidate and launch admission](kelvin-candidate-and-launch-admission-2026-09-17.md).
The shared generator now applies the same octilinear, own-net-only copper,
pending-tap and power-reservation guards to every branch. Sense taps must
actually depart inward from the shunt, not start at its inner edge then run
back through the force pad. The first orthogonal-only trial was insufficient
and is retained as **rejected diagnostic evidence**, not a winner.
**897 tests and 16 subtests pass** in the final combined regression run.

Final concurrent replay: `build/kelvin-launch-suite-20260917`. PCIe3 retains
all three pair constructors and now has `pairs_ok=true`, zero generated raw
diagonals, but **11 Kelvin refusals** (seven prior range + four newly exposed
launch/placement defects). One of five previously generated tap paths remains;
the 87-item prefix is not progress in connectivity and is not admitted.
Independent native proof preserves all prior pair geometry and still rejects
missing reference planes: `build/kelvin-launch-postflight-20260917`.
PCIe2/Hub/VHP Kelvin probes add no copper; current gates/control/source hashes
remain unchanged. EPS/ATX remain held for the interface choice.

Next: exact independent shunt-pad departure checking, then joint range/inward
terminal-cell repair. Do not merely replace wrong-direction diagonals with 90s;
do not replay unchanged USB/boundary domains. Keep canonical manifest below,
Hub 125 poses, all current/load/fabrication authority and pending interface
decision. No board/image promoted; no routing workers left running.

## Latest slice: positive-frontier continuation produces a new PCIe3 pair

Read [positive portals and geometry evidence](positive-portal-frontier-and-geometry-evidence-2026-09-17.md).
The generic screen can now resume beyond a positive first phase, stops unchanged
maximum-quantum work as **stalled, not exhausted**, and widens a rejected whole
edge's beam within the existing transaction/deadline/refill limits. **852 tests
and 16 subtests pass.** The six-board concurrent replay preserves all sources and
historical PCIe2 control parity: `build/positive-frontier-suite-20260917`.

PCIe3 now constructs CAN_J1 on the surface: all 68 previous prefix copper
geometries remain, plus 24 CAN tracks and two return vias. Compiler wall time
was 15.045 s (prior receipt 194.867 s; not a controlled benchmark). This is
**constructor progress, not complete admission**: two inherited Kelvin diagonal
tracks, seven Kelvin endpoint/range refusals and absent filled reference planes
still prevent promotion. The previously opaque geometry failure is now projected
with exact copper/endpoint witnesses. Independent saved-native proof is in
`build/positive-frontier-postflight-20260917`.

Hub and VHP still refuse their USB legs; PCIe2 stays five-open; EPS/ATX remain
pending the interface choice. The experimental boundary beam now genuinely
reaches three start/four end positives without the old 64-round stall, but all
whole-edge trials still fail. Do not repeat that domain. Next: generic Kelvin
construction and placement dependency repair, plus changed Hub/VHP escape
geometry. Keep the canonical manifest below and Hub's 125 poses. No board/image
promoted; workers finished. Core audit passes, full-pipeline audit still fails
with 23 physical / 380 runtime issues.

## Latest investigation: narrow escape windows and positive-frontier continuation

Read [boundary-informed portals](boundary-informed-portals-2026-09-17.md).
The new parameterized boundary helper is **experimental and NOT wired into
production**. It preserves the original portal domain and all native guards.
PCIe3 gets 24 new boundary proposals and two locally qualified transitions;
one complete edge has 86.4% coupling and clean graph/route quality but fails
the unchanged N-member detour limit (2.228009 > 2.0). Exact rollback; no board
gain. VHP has no future reservations, so the unchanged reservation-only trial
was skipped. Its separate materialized-copper-envelope experiment adds 105
proposals but still expires at 120 s without a qualified whole edge.

Both experiments preserve all six sources/hierarchies and the historical
control. Private two/four-wide beam wrappers exposed a **positive-frontier
resume limitation**: completed-query counts repeat to the 64-round cap; they
did not establish exhaustion of a genuinely deeper beam. Do not repeat those
wrappers. Next slice: resumable positive domains, no-progress termination and
consumer-directed end selection after whole-edge refusal, then validate any
boundary-domain integration across boards without losing fast-path successes.

The production refusal wording is also corrected: clearance is mm, not ohms;
observed corridor conflicts are not an all-candidates proof or a promise of
fallback success. **96 focused tests pass** (overlap with prior 486).
Final unchanged-source/control replay: `build/boundary-final-parity-20260917`.
All workers finished; no board or preview promoted. Keep the same canonical
manifest below, Hub's 125 poses and EPS/ATX's pending interface choice.

## Latest slice: via-aware paired fan-in and parent-screen acceleration

Read [paired terminal via envelopes and screening](paired-terminal-via-envelope-and-screening-2026-09-17.md).
An exact PCIe3 replay isolated a real composition defect: the chosen fan-in
and via field were individually clear but the P trace infringed the N via
land when combined. The generic local search now reserves both destination
via lands and proves the emitted fan-in/transition union before selecting it.
An independent immutable-parent rejection screen reduces repeated native
clearance work without granting copper admission. **486 tests + two subtests
pass**. No power, process, interface, dimension or source-board change.

**Corrected edge replay completed:**
`build/terminal-via-envelope-suite-v2-20260917`. Two native refused-edge
constructors ran with four other-family gates and historical PCIe2 control.
No new route: PCIe3 73.6 s, VHP 98.2 s, zero retained copper. The former
late-invalid PCIe3 fan-in no longer enters selection; a complete legal one
has not been found. All six sources/control match; PCIe2 remains five-open.
The first adapter run failed before board work because child processes used
the previous output directory; its receipt is retained.

**Full production priority compiler replay completed:**
`build/via-envelope-priority-suite-20260917`: Hub, PCIe3 and VHP concurrently,
with the other three family gates and historical control. All six source/
hierarchy hashes and historical control match. Hub and VHP still refuse USB
(74.762 / 68.239 s); PCIe3 still refuses CAN_J1 and Kelvin (194.867 s).
Its 68 recreated copper objects exactly match the prior private prefix, not
new progress. No board/image was promoted and **all workers finished**.
The dashboard GET returns 200; about 64 GiB remains. Core audit passes but
the inherited full-pipeline audit still has 23 physical / 380 runtime issues.
Do not repeat these exact endpoint menus or the unchanged staged seed. Next
work is escape-domain / upstream placement co-design using the measured
frozen-power and return-field constraints, retaining all priority copper. Keep
`build/additive-first-next-inputs-20260917.json` authoritative until the new
outputs have complete independent qualification. EPS/ATX interface direction
remains pending and Hub history remains 125 poses.

## Latest follow-through: nested pair failure reaches the oracle

The wrapper-level failure receipt was still being dropped by its caller:
`route_oracle_grade` raised on a refused fallback before saving the attempts.
The oracle now retains the nested report through final blocker evidence, stage
trace and causal chain, and clears stale per-attempt locals. No route/admission
policy changed. See the follow-through section in
[return dependencies and surface escape](return-dependency-trace-and-surface-escape-2026-09-17.md).

**59 focused tests pass**. `build/pair-handoff-suite-20260917/report.json` replays
the saved native PCIe3/VHP receipts through the actual production branch and
failure handlers, with all three evidence paths matching. Six source/hierarchy
identities and historical PCIe2 control parity remain unchanged. This is not a
new routing pass. No workers or new board/image; canonical inputs and all
physical blockers remain as below. Do not repeat exhausted seeds for this
logging-only change. Next work remains paired corridor/transition construction
and Hub's upstream fixed-terminal/local-return dependency.

## Current slice: return-dependency evidence, actual surface escape and scoped pair repair

Read [return dependencies and surface escape](return-dependency-trace-and-surface-escape-2026-09-17.md).
The Hub's missing ground-return proposals are now traced to **fixed frozen-power
terminals**, not stale poses or a missing solver. Production round/final
certificates retain bounded, reason-coded proposal refusals. Do not remove those
fixed constraints or spend another identical placement wave on them.

The neighbor escape sampler also now uses actual unique SMD copper membership,
fixing a loaded-native B.Cu/F.Cu misclassification. **528 combined regression tests pass**.
Concurrent current-suite replay preserves every source, current gate and the
historical PCIe2 control. No current-board connectivity gain is claimed; PCIe2
remains five-open. Complete receipt:
`build/feedback-surface-suite-20260917/completed-report.json`.

**Completed diagnostic and production replay:**
`build/priority-tier-continuation-20260917/completed-report.json` and
`build/priority-tier-scope-verify-20260917/report.json`. Both existing staged
pair fallbacks actually ran and remain refused by independent pair physics.
PCIe3 left one CAN member unrouted; VHP USB failed matched transitions, local
returns, reference-plane coverage and coupling. Do not repeat the same seed or
assume merely reaching the detailed router will resolve these.

This exposed two generic wrapper defects, now fixed: tier failure receipts were
lost on later rejection, and a requested USB-only return repair could realign
unrelated CAN copper. Exact saved-native comparison proves VHP outside-target
changes **6 -> 0** (PCIe3 stays 0); corrected scope retains all pre-existing
copper in those finishing steps. Full independent all-pair admission remains.
Sources/hierarchies and historical PCIe2 control match. **No workers remain and
no board/image was promoted.** Keep `build/additive-first-next-inputs-20260917.json`
authoritative; EPS/ATX interface direction remains pending and Hub history
remains 125 poses. Next work is paired corridor/transition construction and Hub's
upstream fixed-terminal/local-return dependency, not unchanged waves.

The 15-minute review heartbeat is verified ACTIVE and still follows this ledger.
The dashboard returns HTTP 200 from Windows. Storage remains about 64 GiB free.

## Previous slice: paired-interface decision pending; compact pair A/B complete

Read [interface decision and compact pair probe](interface-decision-and-compact-pair-probe-2026-09-17.md).
Fresh canonical native inspection confirms EPS/ATX terminal pad-copper holds.
The user has been asked to choose limited paired-interface growth or fixed-size
alternative-terminal investigation. **No answer/authority is assumed.** Do not
change either interface half, outline, pinout or qualified pad geometry meanwhile.

The compact-ground frontier completed without a board gain: 16 new poses,
30 legal variants, 171.433 s. **Hub history is now 125 poses** at
`build/compact-ground-frontier-20260917/hub-standard-rev2/board.placement-search.json`.
All source/copper/physical/control checks match. Do not repeat that domain.

**Completed: `build/compact-pair-portal-domain-20260917`**, a private, unadmitted
compact-signal-via A/B hypothesis on PCIe3 and VHP, with historical control.
Neither board improved: VHP retained USB refusal (68.131 / 68.032 s); PCIe3
retained CAN_J1 and separate Kelvin failures (143.401 / 144.565 s). No signal
vias survived either compact trial. All six sources, engine and historical
control parity match. **No workers remain; do not integrate the override or
repeat this domain.** This is NOT a production via-minimum change or a candidate. Keep
**`build/additive-first-next-inputs-20260917.json`** authoritative; no board or
review image is promoted. See `build/current-interface-decision-basis-20260917.json`
for the refreshed mechanical evidence.

## Previous slice: compact local ground geometry validated; no board admission

Read [compact local ground dogbones](compact-local-ground-dogbones-2026-09-17.md).
The constructor now uses the existing, explicitly declared compact POFV dogbone
domain with native live-owner requalification, exact rollback and unchanged
current/clearance/power guards. Both ordinary and compact ground stubs now use
the actual unique SMD copper layer instead of unreliable `PAD.GetLayer()`.
Measured compact rejection seats feed the generic rigid placement proposals.
**332 selected regression tests pass**. No new manufacturing process was added.

`build/compact-ground-suite-20260917` completed: all six source hierarchies and
the historical control match, physical gates remain unchanged, core passes,
legacy debt remains 23 / 380. Standalone native local-ground probes qualify new
small dogbones on multiple boards, but the full Hub probe correctly still
refuses two cells because of frozen future-power reservations; its third craft
hold is unchanged. Standalone geometry success is not a board improvement.

**Completed: `build/compact-ground-frontier-20260917`**. One 16-proposal Hub round
used the new measured compact-seat domain and imported 109 previously visited
poses. All 16 selected poses were new; 30 legal variants produced no accepted
improvement. It finished in 171.433 s with all three craft holds, exact source
copper/pairs and source hierarchy unchanged. Other-family physical checks and
historical control parity pass. No workers remain; do not repeat this domain.
The next continuation should import the new history from this cohort. Keep
**`build/additive-first-next-inputs-20260917.json`** authoritative. No new board
or image is currently promoted; EPS/ATX coupled-interface holds remain.

## Previous slice: bounded native pair-order transactions validated; no admission

Read [native pair-order transactions](native-pair-order-transactions-2026-09-17.md).
The generic engine can retry a connected shared-series group once in refused-
first order, using only its explicitly NEW copper and exact native rollback.
All group members must qualify before adoption; source power/copper and other
pair coverage remain fixed. Final v2 defers within-group synthetic launch boxes
to actual complete-group routing, retaining all physical and outside-group
guards. **596 tests + two subtests pass**; loaded-native success, rejection,
return-via/group rollback and source-mutation tests are included.

First concurrent cohort completed without admission: PCIe3 eight critical
refusals after an exact 108.385-second rollback, VHP one, Hub one plus three
craft holds. Six-family physical/source checks and historical PCIe2 control
match; core passes, legacy debt 23 / 380. `build/pair-order-suite-20260917` is
complete. Final v2 cohort also completed under
**`build/pair-order-joint-suite-20260917`**: PCIe3 still has eight critical
refusals in 152.285 seconds; the 68.386-second atomic retry qualified CAN only,
then restored exact copper/groups. No transaction was adopted. Source/hierarchy
and engine identity, unchanged physical gates and historical control parity
pass. EPS/ATX remain held, not physically admitted. All workers are finished;
do not repeat the unchanged ordering domain. Approximately 64 GiB remains free.

**Keep `build/additive-first-next-inputs-20260917.json`** authoritative. No new
board or image has been promoted. Ground-pad readback also confirms the Hub's
0.20 mm mux ground lands cannot contain the approved 0.30 mm minimum via land;
the pad-centre refusal is real. Next independent domain is qualified compact
local dogbones versus the generator's ordinary 0.60 / 0.30 mm fallback, using
existing process/topology/current rules—not a pad/clearance or power-budget
waiver. EPS/ATX mating holds and 109 / 64 placement histories remain unchanged.

## Previous slice: native shared-series launch contracts; no board promotion

Read [shared-series launch contracts](shared-series-launch-contracts-2026-09-17.md).
Future-pair reservation now replaces a shared broad box with qualified native
outward member launches when possible, matches the actual end rather than box
containment, and retains the remote endpoint. No geometry is moved. Bounded
cross-pair ownership/qualification evidence survives both preflight projections.
**575 tests + two subtests pass**; native renamed/translated/rotated, B.Cu,
obstruction, protected-power and short-leg regressions are included.

Concurrent full native probes yield **no admission**: PCIe3 eight critical
refusals, VHP one, Hub one in the priority diagnostic plus three craft holds.
An in-memory PCIe3 owner-segment replay verifies both later member launches
remain clear after generation; this is NOT complete successor-pair routing.
All six sources/hierarchies, physical gates and historical PCIe2 control match.
Core generalization passes; legacy debt remains 23 / 380, release false.

**Keep `build/additive-first-next-inputs-20260917.json`** and its five-open PCIe2
archive authoritative. No new board/image is promoted. All workers finished;
~64 GiB remains free. Evidence: `build/shared-series-suite-20260917/report.json`
and `build/shared-series-final-verify-20260917/report.json`.

Next domain: a jointly qualified shared-station transition field or bounded
transactional ordering of connected pair segments. Local 1 mm straight escapes
do not protect the entire matched signal/return-via field. Do not merely
lengthen that reservation or rerun the unchanged probes. Reuse native field
qualification and rollback of explicitly NEW copper; never unlock source
power. Continue independent owned-local-return work and coupled EPS/ATX mating
geometry. Existing 109 / 64 Hub/PCIe3 pose history remains authoritative for
ordering; no new placement samples were spent in this slice.

## Previous slice: paired plated-terminal layer access; no board promotion

Read [native paired-terminal layer access](native-paired-terminal-layer-access-2026-09-17.md).
The paired portal fallback now uses actual PTH layer spans at each end, routing
that fan-in on the chosen signal layer without inventing redundant signal
vias. The SMD end retains its matched signal/return-via checks, and native PTH
return qualification remains mandatory downstream. No existing copper moves.
Native positive/negative, translated and renamed tests pass; per-end access
witnesses survive bounded diagnostic projection. **508 tests + two subtests pass**.

Three concurrent current-board priority probes completed with **no admission**:
PCIe3 eight critical refusals, VHP one, and Hub one in the priority diagnostic
while its three separate craft blockers remain. All six source/hierarchy
hashes, current physical gates, protected copper and historical PCIe2 control
match. Core generalization passes; legacy debt remains 23 / 380.

**Keep `build/additive-first-next-inputs-20260917.json`** and its five-open PCIe2
archive authoritative. No new board/image is promoted. All workers finished;
~64 GiB remains free and the existing heartbeat stays active. Do not rerun the
same probes on a timer. Evidence: `build/native-pair-layer-suite-20260917/report.json`
and `build/native-pair-layer-final-verify-20260917/report.json`.

Next hypothesis: direction-aware shared split-series launch contracts or
transactional pair ordering. Current future-pair reservation code suppresses
broad boxes at shared series supports; native pad clearance alone does not
reserve outgoing launch space, and the remaining PCIe3 SMD end is blocked by
earlier adjacent-pair copper. Inspect/extend the existing scheduler and
reservation helpers, not one-off passive moves. Continue the independent
owned-local-return and EPS/ATX coupled-mating domains without relaxing guards.

## Current result: additive-first coordinator verified, PCIe2 eight to five opens

Read [additive-first suite progress](additive-first-suite-progress-2026-09-17.md).
**Use `build/additive-first-next-inputs-20260917.json` now.** Only PCIe2 advances
to `build/board-archive/20260917-additive-pcie2-5-open-032ee2c1a066/board.kicad_pcb`,
SHA `032ee2c1a06644b8dc1ced7cc927d90f2e71af69f5a994a5ed5b48352ce0ffbd`.
Adjacent `oracle.json` is the current five-open residual, not the earlier eight
or nine-open surveys. Three sequential closures add 29 tracks/two vias while
preserving all existing copper, poses, zones, identities and semantic rules.
Independent native/physical/quality/fabrication non-regression passes; top and
bottom body-free previews are published and HTTP-verified. **Still not fab-ready.**

The new generic additive stage runs before expensive whole-net probes and
displacement. Tests also fixed shortlist starvation and short-budget history.
An actual coordinator replay caught scratch-copy metadata invalidating the
source survey; v56 now freshly measures the scratch family, never forges a
binding. Production reproduction closes 8 -> 7 in 25.168 s. **524 tests and eight
subtests pass**; all six sources/hierarchies and historical PCIe2 control match.
Legacy generalization debt remains 23 physical / 380 runtime findings.

Concurrent Hub and PCIe3 searches completed: Hub 32 NEW poses, no adoption,
three blockers; PCIe3 16 NEW poses/eight critical probes, no adoption, eight
refusals with incomplete probes explicitly inconclusive. Latest matching
ordering receipts are in `build/additive-frontier-continue-20260917/<board>/`
at **109 / 64** visited poses. VHP and the EPS/ATX coupled-interface holds remain
unchanged. Do not relaunch these same placement samples or the exhausted
five-open additive domain; preserve the current copper/authority guards.

All workers finished. The existing heartbeat remains active; ~64 GiB free.
Next: owned endpoint/support-group access and specialized priority-station
work, alongside the coupled EPS/ATX terminal copper-envelope/mating solution.
Evidence: `build/additive-frontier-continue-20260917/report.json`,
`build/additive-final-independent-20260917/report.json`, and
`build/additive-production-verify-v56-20260917/report.json`.

## Current result: native island attachment closes one open, without moving anything

Read [certified island access and neck-down parity](certified-island-access-and-neckdown-parity-2026-09-17.md).
PCIe2 improves **0 DRC / 9 opens -> 0 / 8** and clears the independent stranded
IC-supply finding. Three additive tracks / 4.815 mm, no vias; every existing
copper object, footprint pose, electrical identity and semantic rule remains
unchanged. The successful direct route is selected over the equally scoring
via-move alternative. All other board inputs/holds are unchanged.

**Use `build/island-access-next-inputs-20260917.json` now.** Its PCIe2 archive is
`build/board-archive/20260917-island-access-pcie2-eight-open-89dfc287a297/board.kicad_pcb`,
SHA `89dfc287a2974b35eb4367b337207f014036c8c56ffc86d86a680c42c9a8301b`.
Adjacent `oracle.json` contains fresh hash-bound eight-open residuals. The
earlier nine-open manifest is historical, not the continuation.

Generic v53 fixes: a bounded native same-island attachment portfolio reuses the
existing exact router/ranking, never an unrelated same-net island; explicit
new-neckdown qualification and shared elongated-pad locality bounds repair a
generator/recovery discrepancy. The first trial's new width DRC was rejected,
then fixed without changing the existing 1.5-mm cap or semantic rules.

Evidence: `build/island-attachment-contract-suite-20260917/report.json` and
`build/island-candidate-independent-v2-20260917/report.json`. Fresh independent
score/constraints/route-quality/fab comparisons pass non-regression. All six
source/hierarchy checks and historical PCIe2 control match. **504 tests and
eight subtests pass**; broader legacy generic debt stays 23 / 380.

New body-free top/bottom previews are published and HTTP-verified on dashboard
ID `20260917-island-access-pcie2-eight-open-89dfc287a297`, with Windows copies in
`CEC-Board-Reviews/island-access-20260917/pcie-8pin-2port/`. This remains a partial
route, not fab signoff; no thermal solve or hardware qualification is claimed.

All workers have finished. Next: bounded additive alternatives for the
remaining current certified component pairs, plus the other boards' separate
owned-priority/local-return and coupled-mating domains. Do not restart the old
via menu, stale nine-open oracle, or unchanged placement batches. The existing
heartbeat remains active; ~65 GiB remains free.

## Current slice: exact pair scope, real search expansion; suite reviewed

Read [certified pair via repair and suite review](certified-pair-via-repair-and-suite-review-2026-09-17.md).
Revision v51 preserves certified via-target pairs, distinct-pair task identity,
inner/outer timeout agreement, and a genuinely broader final local-seat search.
**414 selected regression tests pass.** Native before/after via experiments,
concurrent four-family physical checks, two interface holds and historical
PCIe2 control show **no newly admitted route or placement**. PCIe2 remains
0 DRC / nine opens. The local transaction completes in 22.202 s versus the
preceding 95.015 s watchdog failure; this is not a full-wave speed claim.

Completed evidence: `build/expanded-pair-suite-20260917/report.json` and final
v51 planner/source/control replay
`build/pair-scoped-native-review-v2-20260917/report.json`. All six canonical
sources/hierarchies remain exact. The expanded direct pair fails even without
moving the via, and both expanded moved-via probes complete without a route.
Do not rerun this exhausted domain. No board/render is promoted.

Keep **`build/frozen-priority-next-inputs-20260916.json`** authoritative.
Hub retains its three physical/craft blockers; PCIe3 and VHP retain their
recorded eight/one priority refusals. EPS/ATX remain held for coupled terminal
copper envelopes and mating/route-authority repair. No unrelated source,
budget, power bus, dimension or interface constraint was changed.

Next: coordinated endpoint access/owned support-group repair and bounded
same-island attachment alternatives, after inspecting existing mechanisms;
in parallel, resolve the separate coupled main/daughterboard envelope domain
without unverified physical assumptions. Do not launch unchanged placement
batches or silently drop ownership guards. The final planner found no new
untested via pair from this input. All current workers are finished; the
existing 15-minute review/repair heartbeat remains active. Wider legacy generic
debt is still 23 physical / 380 runtime findings, not a fabrication release.

## Current slice: explicit owned motion; newly recovered native repair domains

Read [owned copper motion and recovered domains](owned-copper-motion-and-recovered-domain-2026-09-17.md).
The footprint transaction now reissues only already-proven generated members
after a bounded declared move/removal. Full native inventory/property checks
run before publication; failed board/receipt writes restore both old artifacts.
Final routing provenance retains valid completed mutation receipts.
**528 tests pass in 141.10 s**; four-family native scope/rollback replay,
two interface holds and historical PCIe2 regression pass. The private native
perturbation fixture is not a candidate and must not be published.

Six explicit verified producer links recover **370 generated locked objects**
in the unchanged current PCIe2 geometry, not blanket lock authority. Evidence:
`build/recovered-route-lineage-v2-20260917/report.json`. The final private
`stage-06.kicad_pcb` has the exact current canonical SHA. Native planning exposes
one NEW via-repair domain and one NEW branch-negotiation domain, both on the
same detector-net obstacle to a 3V3 connection. Old footprint menus were not
rerun. Other older locked objects remain unproven.

**Completed bounded work:** `build/recovered-domain-transactions-20260917/`
tested the two new domains concurrently. No adoption: branch close timed out
twice (51.548 s total); both via re-seats succeeded, but each following whole-net
completion timed out after 45 s (95.015 s total). These are incomplete searches,
not geometric no-path proofs. Both outputs remain identical at 0 DRC / nine
opens; all six sources/hierarchies and engine identities are unchanged. No
new board or preview is admitted. All workers have finished.

Next concrete audit/fix: the via planner drops the exact endpoint pair from
its input certificate, then its executor asks `_lastmile_worker` to rediscover
the entire target net. Forward and probe the exact certified pair first, with
per-pair progress evidence and existing whole-board admission. Test whether
that verified scope loss explains the measured timeouts; do not assume it does,
repeat the same whole-net attempt, or relabel a timeout as no-path.

For private continuation of these new repair domains, carry the matching
receipt from `build/recovered-route-lineage-v2-20260917/stage-06.kicad_pcb`;
its board hash is exactly current. Other boards retain their existing holds;
no unchanged Hub/P3 batch was relaunched. Canonical continuation remains
`build/frozen-priority-next-inputs-20260916.json`.

## Current slice: placement batch complete; durable generated-copper provenance

Read [generated-copper lineage](generated-copper-lineage-2026-09-16.md).
The Hub/PCIe3 continuation **finished with no admitted improvement**: Hub keeps
three craft blockers after 32 new sampled poses; PCIe3 keeps eight priority
refusals after 16 new poses/four pair probes, with unfinished probes explicitly
inconclusive. Their latest matching ordering receipts are now **77 / 48** in
`build/safe-frontier-continuation-20260916/<board>/board.placement-search.json`.
Keep `build/frozen-priority-next-inputs-20260916.json`; no changed geometry or
new preview is promoted. Do not launch another identical batch on a timer.

The new generic producer receipt preserves exact generated-item provenance
across board renames and routed continuations; the route oracle writes it
before certificate repair and after copper finishing. Repair now refuses an
unrelated/empty baseline instead of authorizing every disjoint locked UUID.
It carries only native identity/geometry-matching claims, not route acceptance.
Changed inherited items still need the next explicit owned-mutation receipt.

Native final replay: `build/route-copper-lineage-replay-v2-20260916/report.json`.
All six source/hierarchy identities and historical PCIe2 control are unchanged.
The recorded PCIe2 producer boundary recovers 22 currently **unlocked** added
items in a private receipt, not the 1,111 earlier locked items. No current-board
group move becomes authorized by this result. No blanket unlock was used.
Final broad regression: **518 tests pass in 140.75 s**. Evidence:
`build/route-copper-lineage-final-v2-tests-20260916.log`.
All native/test workers have finished. No board campaign is running and no
unchanged placement batch was relaunched. About 65 GiB remains free.

Next constructive work: explicit group/branch owned mutation and reconnection,
plus verified earlier producer lineage if it can actually be recovered.
Current guards/holds remain: PCIe2/VHP require routed-copper ownership; Hub/P3
are not route-admitted; EPS/ATX require coupled mating/copper-envelope repair.
Legacy generic debt is still 23 / 380, not full generic/fab qualification.

## Current slice: bounded local copper motion; two safe frontiers continuing

Read [bounded local-cell copper](bounded-local-cell-copper-2026-09-16.md).
Certificate group moves now preserve complete short, unbranched internal
track chains instead of ripping the ends off every bent local route. Native
foreign-contact/ownership checks and a before-write exact copper inventory
guard keep unrelated routes intact. **171 tests pass**; native current-suite
discovery plus historical PCIe2 regression is unchanged. No actual current
board has advanced from this primitive: nearly all existing copper is locked,
and no generated-item authority has been invented. Next constructive routed
work requires verified copper lineage and full group reconnection/admission.

**Active bounded continuation:** `build/safe-frontier-continuation-20260916/`
runs Hub and PCIe3 concurrently, seeded from their matching 45/32-pose receipts.
Keep shared engine files frozen until both finish; inspect `report.json` for
completion. PCIe2/VHP retain the routed-copper ownership guard; EPS/ATX retain
the coupled-interface holds. This is not six simultaneous routing waves.
Keep **`build/frozen-priority-next-inputs-20260916.json`** authoritative until
an independently reviewed improvement is admitted. No changed board/render
has been promoted in this slice.

## Current result: suite reviewed; destructive copper rebuild blocked (September 16)

Read [the placement copper ownership boundary](placement-copper-ownership-boundary-2026-09-16.md)
and [resumable placement search](resumable-placement-search-2026-09-16.md).
The concurrent four-family transactions have **finished**. No new board is
admitted. PCIe3 stays eight priority refusals after 16 different sampled poses;
Hub stays three craft blockers after 32 distinct poses beyond 13 recorded
legacy poses; VHP stays one USB refusal after 12 pair probes. EPS/ATX keep their
paired-interface holds. All sources/hierarchies and pass engine stayed exact.

The apparent PCIe2 forecast gain was **rejected**, not retained: its placement
materializer preserved only a critical/power prefix while deleting 996 other
track/via objects. Actual opens rose 9 -> 168 and three craft failures appeared.
Canonical PCIe2 remains 0 DRC / nine opens. The new generic materialization
guard checks every native track/arc/via against explicit retained ownership,
before any write. Read-only geometry inspection remains available. The same
guard protects 228 existing 12VHPWR Kelvin traces outside that prefix. Native
four-family replay plus both holds and the historical control pass in
`build/placement-copper-ownership-replay-v2-20260916/report.json`.

**Keep `build/frozen-priority-next-inputs-20260916.json`.** Do not use the
changed PCIe2 diagnostic as a routing seed. No unchanged render is new progress.
The newest safe search-order receipts are in
`build/priority-frontier-suite-20260916/<board>/board.placement-search.json`:
PCIe3 has 32 visited proposals, Hub 45 recorded proposals (legacy coverage is
partial). When staging the next private continuation, carry the matching
byte-bound receipt so it does not restart the same first batch. Do not edit
immutable original checkpoints to inject it. Ordinary full-pipeline artifact
copy/continuation now carries newly generated search receipts automatically.

Next constructive slice: a **route-owned local group/copper transaction** for
partially routed inputs, not the placement reconstruction path. Preserve all
unrelated copper, reconnect the explicitly owned local group, and require
whole-board DRC/connectivity/physical/power/pair non-regression. VHP's Kelvin
ownership needs actual qualification before adding it to any preserved set;
do not infer it just from net names or lock bits. Hub/P3 may continue safe
prefix-only/open placement exploration with the recorded frontier. Do not
repeat exhausted single-obstacle PCIe2 menus. EPS/ATX still need coordinated
mating copper-envelope repair within their existing dimension/span limits.

The review/repair heartbeat remains active and the dashboard returns HTTP 200
from Windows. **485 tests and 16 subtests pass in 138.98 s**, in
`build/placement-copper-ownership-final-tests-20260916.log`. All repair,
qualification and regression workers from this slice have finished. Legacy
generic audit debt stays 23 / 380; this is not full pipeline generic/fabrication
qualification. About 65 GiB remains free, above the 16-GiB floor.

## Current slice: resumable fair priority frontier (September 16)

Read [resumable placement search](resumable-placement-search-2026-09-16.md).
Priority repair no longer confuses one unsuccessful finite sample with the
whole funded neighborhood. It uses least-visited sampling while preserving
critical-owner reservations, frozen-plan screening and exact admission.
Both priority and craft now retain small byte-bound search-ordering sidecars
across unchanged pipeline continuations. These are not cached geometric proofs;
changed PCB bytes discard them, and incomplete probes never become failures.

**350 tests pass** in `build/priority-frontier-final-tests-20260916.log`.
Initial integration failures were mock-fixture call contracts/missing dummy
files; optional-history handling and assertions were corrected, and the full
suite was rerun. No physical/design rule was relaxed.

**Completed concurrent transactions:**
`build/priority-frontier-suite-20260916/`, from the unchanged
`build/frozen-priority-next-inputs-20260916.json` cohort. Four current families
run bounded native work, with a historical PCIe2 regression and two explicit
EPS/ATX paired-interface holds. Priority uses 16 trials / two rounds / four
workers; Hub craft uses 16 trials / two rounds. The old PCIe3 16 scheduled poses
and only the Hub's actually retained legacy pose records seed ordering; missing
legacy pose identities are not invented. These are diagnostic transactions,
not new completed full routing waves. Keep shared engine files unchanged until
all workers finish, independently review any changed result, and only publish
changed geometry with truthful routing/admission status.

The previous finalization integration pass **completed in 458.071 s** at
21:53:13Z. Both finish leases remained within budget; source/engine identities
stayed exact. PCIe3 remains eight critical refusals and byte-identical to its
input. Four pair probes completed; five were deferred by the bounded probe
share. No finalist was fully evaluated. Its published BLOCKED placement is
not a new board improvement and must not be presented as one.

## Current slice: whole-transaction finalization budget (September 16, 21:45Z)

Read [placement finalization reserve](placement-finalization-reserve-2026-09-16.md).
The complete priority cooptimization loop now shares a shortened work deadline,
so nested power/physical/priority operations cannot spend the finalization
reserve. Budget stops restore the last fully measured composition. Optional
late fiducial finishing has the same lease and native artifact-family rollback;
crashes/integrity failures remain errors. Structured operation failures survive
the authority exception boundary. No physical/design limit changed.

**138 tests pass**, plus **110 in the overlapping final focused suite**.
Concurrent four-family native expired-lease replay and historical PCIe2 control
pass; the two interface holds persist. All six source/hierarchy identities are
unchanged, with legacy debt still 23 / 380. This validates scheduling/rollback,
not a new routing improvement.

**Completed full integration pass:**
`build/finalization-reserve-full-pass-20260916/suite.json`.
It starts only the newly improved checkpoint family (PCIe3) from
**`build/frozen-priority-next-inputs-20260916.json`**, not the unapproved
power-replanned board. Four workers / 16 trials / 450-second priority operation /
900-second campaign. Source intake and placement execution completed, but the
eight-refusal priority gate remains blocked. Do not duplicate this pass. Other board
families' exhausted menus were not restarted. Inspect completed results and
both finalization-budget receipts before updating continuation or announcing
progress. Both reserve receipts record `budget_exhausted=false`. The canonical
eight-refusal placement remains unadmitted and output bytes are unchanged.

## Current result: priority gain without moving the power plan (September 16, 21:17Z)

Read [frozen-plan priority boundary](frozen-plan-priority-boundary-2026-09-16.md).
The bounded production transaction finished: PCIe3 **10 -> 8 priority refusals**
in 329.747 s. A fresh saved-PCB priority measurement independently reproduces
eight. Current source/electrical intake, physical placement, exact power,
original-plan independence, saved copper and qualified-pair checks pass.
Pours, corridors, vias and power terminals are unchanged. This is a genuine
20% refusal reduction, unlike the earlier power-replanned diagnostic.

**New canonical continuation manifest:**
**`build/frozen-priority-next-inputs-20260916.json`**. Only PCIe3 advances, to
the authenticated unadmitted priority checkpoint under
`build/frozen-priority-production-probe-20260916/pcie-8pin-3port/02-placement/checkpoints/slot-0/`.
SHA `58c66a712f5a54e211a05f3ebb2f673913fe2507b2226dced593543f8e9fa4db`.
It remains placement-only, with eight critical refusals: **not routed, not
routing-admitted, not fab-ready**. Do not use the earlier changed-power-plan
checkpoint. The old six source PCBs/hierarchies and prior plan are untouched.

**495 tests pass** across the focused and broader suites. The broader first
attempt exposed a scratch pytest launcher missing its spawn main guard; the
corrected full rerun passes 327 tests. Concurrent current-family controls and
historical PCIe2 regression pass; legacy debt remains 23 / 380. The production
menu screened 693 of 1,949 power-dependent proposals before the 16-trial quota,
spending 8.229 s on that screen. This is a shared rule, not a refdes ECO.

[New body-free placement review](http://localhost:8090/?id=20260916-frozen-plan-priority-pcie-8pin-3port-58c66a712f5a)
is published and visually inspected. Catalog identity and image HTTP 200 are
verified from Windows; in-app open is queued. Receipt:
`build/frozen-priority-production-probe-20260916/independently-reviewed.json`.
There are no remaining solver/test workers. The review/repair heartbeat remains
active. Next fix the complete power-reconstruction/finalization budget boundary
and investigate the other remaining generic blocker classes; do not restart
unchanged exhausted waves. PCIe2 remains 0 DRC / nine opens, Hub three craft
blockers, 12VHPWR one USB refusal; EPS/ATX retain their coupled-interface holds.

## Current slice: freeze planned copper before priority trials (September 16, 21:05Z)

Read [frozen-plan priority boundary](frozen-plan-priority-boundary-2026-09-16.md).
Priority repair now carries the same native frozen-plan domain as craft repair,
screens it before the routing trial quota, checks compound co-repairs, and uses
atomic PCB/sidecar commit with rollback. It cannot silently replace its power
plan. **168 tests pass**; concurrent four-family current native/physical replay,
two interface holds and historical PCIe2 control pass. The old unapproved
eight-refusal checkpoint is correctly rejected. PCIe3's 48 joint proposals
produce five plan-independent proposals, one courtyard-clean. This is a guard
and search-efficiency improvement, not a measured reduction in route refusals.

**Active bounded production probe:**
`build/frozen-priority-production-probe-20260916/`. One priority-repair round
only where new proposals apply; 16 trials / four workers / 600-second operation
budget. Broader regressions: `build/frozen-priority-regression-tests-20260916.log`.
Do not edit shared scripts or duplicate a run while workers remain active.
Keep **`build/priority-coopt-next-inputs-20260916.json`**. No canonical boards
changed or promoted. Next independently inspect the probe, then address the
full-stage power reconstruction/finalization budget gap. Other family blockers
and the paired EPS/ATX interface holds remain unchanged.

## Current result: joint terminal pass stopped; protected-plan boundary exposed (September 16, 20:32Z)

Read the final section of [joint terminal reach placement](joint-terminal-reach-placement-2026-09-16.md).
The bounded pass has **finished**, not left routing unattended: 1165.897 s,
placement failed at a post-power physical measurement after campaign budget
exhaustion. Its retained first-round checkpoint records 10 -> 8 priority
refusals; a later seven-refusal trial was not fully validated. The eight-refusal
checkpoint is reviewed/published as blocked placement, never a routed board.

**Do not promote it or advance the canonical cohort.** Saved PCB copper is
preserved but the original frozen power-plan guard rejects the move; generated
pour geometry changed. Fresh checkpoint physical/exact-new-power checks pass,
which does not waive original-bus preservation. Receipt:
`build/terminal-range-checkpoint-reviewed-20260916.json`.

The detector/bypass rotation defect was then repaired generically with the
shared rigid-cell transform and a fixed-follower guard. **315 tests pass**;
the previously failing four orientations are green. Current four-family native
replay, two interface holds and historical PCIe2 control pass in
`build/terminal-range-replay-v3-20260916/report.json`. All six current source and
hierarchy signatures are unchanged; legacy debt remains 23 / 380. No remaining
campaign, replay or test workers; the existing review heartbeat remains active.

Keep **`build/priority-coopt-next-inputs-20260916.json`**. Next fix the generic
frozen-plan screening/compound-commit boundary and bound power reconstruction
with its post-authority finalization budget. A saved-board prefix does not
protect power geometry held only in a sidecar. Do not repeat the old waves or
start from the unapproved checkpoint. PCIe2 remains 0 DRC / 9 opens; Hub/VHP
priority/craft and EPS/ATX coupled-interface holds remain unchanged.

## Current slice: joint terminal reach and obstacle-aware placement (September 16, 20:08Z)

**20:22Z follow-up:** first round measures 10 -> 8 priority refusals, but the
authority rebuild changed planned power geometry. Original-plan dry-run rejects
the moved consumer. This is not an unchanged-bus improvement and is **not yet
approved as the next canonical input**. The second bounded round is running.
The linked document also records four newly reproduced, deliberately red
detector/bypass rotation tests awaiting repair once all native workers exit.

Read [joint terminal reach placement](joint-terminal-reach-placement-2026-09-16.md).
The reusable proposal engine now preserves both current-sense terminal reach
and non-crossing order while rotating whole local groups. Its optional packing
domain intersects native obstacle-free space with both reach discs. Physical,
frozen-power, craft and routing admission remain unchanged; no power bus moves.

**381 tests pass, 13 skip**. Concurrent four-family native replay plus EPS/ATX
holds and historical PCIe2 control completed. All six sources/hierarchies are
unchanged. The new menu found one PCIe3 proposal that clears courtyard and
frozen-power checks but still fails detector/driver locality. It is private
negative evidence, not routing admission. Other family gates are unchanged.

**Active canonical pass:** `build/terminal-range-joint-pass-20260916/suite.json`.
Only PCIe3 has applicable new proposals; it starts from the canonical source
and uses the full bounded pipeline/co-repair, not the scratch trial PCB.
Do not duplicate the pass or edit shared scripts until workers finish.
Keep `build/priority-coopt-next-inputs-20260916.json` until independent final
qualification. No board or new dashboard review is accepted yet.

## Current slice: certificate relocation stops report actual frontier (September 16, 19:32Z review)

Read [certificate relocation frontier](certificate-relocation-frontier-2026-09-16.md).
The next eight genuinely unvisited foreign-support poses ran in two bounded
transactions (six / two). No geometry was adopted; **PCIe2 stays 0 DRC / 9 opens**.
The first of those calls exposed another generic reporting defect: the existing
six-pose nonproductive-prefix guard returned `candidate_exhausted` with two
generated proposals unvisited. Reports now distinguish work budgets from
finite-menu exhaustion and publish primary generated/skipped/scheduled/unvisited
counts. No search order, bound, geometry or acceptance rule changed; v45 stays.

**295 tests / eight subtests pass**. Native four-family proposal enumeration
and historical PCIe2 regression pass in
`build/certificate-frontier-replay-v2-20260916/report.json`; this is not four new
route runs. All six source/hierarchy identities and frozen engine verify.
EPS/ATX remain held. Legacy audit debt remains 23 physical / 380 runtime.
The earlier enumeration harness failed to match JSON-list/dataclass-tuple target
identities; V2 corrects and explicitly asserts history accounting.

`build/endpoint-launch-transaction-v4-20260916/report.json` now truthfully
records 12 generated poses, ten skipped prior attempts, two newly scheduled,
zero unvisited. No repeat occurred. **Do not rerun that single-obstruction menu**;
no-path is still not proved, and no copper unlock authority was added.

Keep **`build/priority-coopt-next-inputs-20260916.json`**. No new preview or
canonical board exists. Next constructive work needs a complete owned-cell /
multi-obstacle transaction or a different proposal domain; inspect PCIe3's
recorded range-improving finalist craft failures and coupled return repair
before another full wave. Preserve the approved reach and power/mating guards.
All workers from this slice are finished. About 65 GiB remains free; the
existing review heartbeat stays active and unchanged-board status stays quiet.

## Current slice: real launch layers and preserved foreign-blocker pair (September 16, 19:04Z review)

Read [native endpoint launch and foreign-blocker routing](native-endpoint-launch-and-foreign-blocker-routing-2026-09-16.md).
Two generic defects are repaired: a hypothetical inner-layer ray no longer
hides a sealed SMD surface launch, and moving a foreign-net obstruction now
retains the original signal pair instead of looking for that signal on the
obstacle's pads. Native existing THT/via connectivity remains respected.
Revision is `2026-09-16-native-launch-and-foreign-blocker-pair-v45`.

**250 tests / eight subtests pass**. Concurrent four-family geometry replay
and historical PCIe2 regression pass in
`build/endpoint-launch-replay-v3-20260916/report.json`; EPS/ATX retain explicit
interface holds. Hub/PCIe3/VHP each have eight geometry samples, not eight new
failed routes or full passes. All six sources/hierarchies and the frozen engine
match. Legacy generalization debt remains 23 physical / 380 runtime.

The resulting newly exposed PCIe2 foreign-support transaction tried four
poses in 13.751 s. Three were rejected by native DRC preflight. The fourth now
reaches the correct route search (previously a missing-pad implementation
failure), but still finds no exact clear path. See
`build/endpoint-launch-transaction-v2-20260916/report.json`.
**No geometry is adopted; PCIe2 remains 0 DRC / 9 opens.** Do not retry those
same four poses or infer unlock authority for preserved copper. Other families
have no new applicable foreign-blocker target in this slice. No new preview.

Keep **`build/priority-coopt-next-inputs-20260916.json`**. The next constructive
step requires verified multi-obstacle/complete-cell ownership and replay, or
genuinely unvisited placement proposals. Existing priority/craft and paired
interface holds remain. Do not restart unchanged exhaustive searches or treat
scratch routes as admitted boards. All slice workers are finished; the existing
15-minute review heartbeat remains active. Dashboard is Windows HTTP 200;
approximately 65 GiB remains free.

## Current slice: final scalar routing respects shared pair identity (September 16, 18:17Z review)

Read [ordinary completion ownership](ordinary-completion-pair-ownership-2026-09-16.md).
The scalar-completion heuristic incorrectly included a real CAN branch pair
on both PCIe boards and an internal CAN pair on VHP. It now consumes the same
live pair/device-input identity as specialized routing. No current design
limit or physical guard was loosened and no board-specific exception was added.

**97 tests / eight subtests pass**, including loaded-native scalar dispatch.
Concurrent four-family native replay plus two preserved EPS/ATX interface holds
passes in **`build/ordinary-completion-ownership-replay-20260916/report.json`**.
Each affected CAN pair is excluded; native DRC/open outcomes versus the prior
bounded diagnostic, protected copper, poses and qualified pairs are unchanged.
Historical PCIe2 hash/regression/probes, all six source/hierarchy identities
and the frozen engine match. Legacy audit debt stays 23 physical / 380 runtime.

The preceding qualified short-signal-dogbone experiment completed without any
additional closure on four families and was **not integrated**. Its small
scratch routes are not canonical candidates or full-pass results. No replay,
test or full-campaign worker remains. Dashboard is Windows HTTP 200; 65 GiB free.

Keep **`build/priority-coopt-next-inputs-20260916.json`**. No canonical geometry
advances and no duplicate preview/full wave is justified by this dispatch fix.
Next work must isolate a constructive multi-obstacle endpoint or complete-cell
repair; the earlier single-cell regeneration and expanded local-via domains
are already exhausted bounded experiments, not a reason to repeat them.

## Current slice: distinguish sampled failure from exhaustion (September 16, 17:38Z review)

Read [finite craft frontier](craft-proposal-frontier-continuation-2026-09-16.md).
The finer local-return seat experiment completed without a whole-board gain
and was not integrated. Investigation then found a shared scheduling defect:
the first failed sampled craft batch stopped the whole caller-funded search
despite unvisited proposals. The correction keeps the incumbent unchanged and
uses only remaining bounded rounds/epochs, preserving native/monotonic gates.

The combined updated suite passed **361 tests** in 163.12 s. Native replay and
fresh independent verification are **complete**, with no remaining workers.
Use **`build/craft-frontier-qualified-20260916.json`**, not the original
diagnostic harness's failed field-name assertion. Hub explores 32 distinct
poses in two bounded rounds (133.910 / 123.798 s), rather than stopping after
16; **zero accepted moves and the same three blockers**. Both PCIe families
retain craft-clean unchanged PCBs. VHP retains its clean physical gate and
explicit C7 route-stage deferral; its absent frozen state makes frozen-domain
solver replay inapplicable, not permission to relax authored-power protection.

Fresh physical/score, applicable exact-power, copper and pair checks pass with
the same blocked/admitted statuses. All six canonical source/hierarchy hashes,
engine and historical PCIe2 board/regression/probes remain exact. EPS/ATX retain
their interface hold. Initial harness errors and negative experiments are
retained rather than counted as passes. This corrects search accounting but
does **not** close a board. Next work should address a demonstrated endpoint or
complete local-cell dependency, not restart the same 32 unsuccessful proposals.

Canonical plan remains `build/priority-coopt-next-inputs-20260916.json`.
No new full-board pass, route admission, promotion or fab-ready board is
claimed. No unchanged waves or previews are being recycled as progress.

## Latest completion: retained PCIe3 placement verified (September 16, 17:12Z review)

The corrected full pass finished **16:57:37Z**, in **604.387 s**. Its placement
stage completed normally and retained the measured improvement; the next
stage remains blocked by the same ten important-route refusals. The complete
round-budget check declined a second round requiring 625.946 s with 600.852 s
remaining. This is successful bounded finalization, not a timeout or routing
closure. No campaign worker remains.

Independent native physical/exact-power/copper/pair checks pass. A fresh full
priority replay reproduces the entire ordered objective exactly. Both body-free
views were inspected and Windows HTTP 200 verified:
[new blocked placement review](http://localhost:8090/?id=pass-priority-coopt-durability-pass-20260916-pcie-8pin-3port-acdebc87d1).
SHA **21109c06887d...**, 83 footprints, zero tracks/vias, one zone. Receipt:
`build/priority-coopt-durability-pass-qualified-20260916.json`.

The new immutable continuation cohort is
**`build/priority-coopt-next-inputs-20260916.json`**. Only PCIe3 advances from a
journal-verified full placement, not a private probe. The other five rows and
all current-BETA source/hierarchy hashes are unchanged. The ordered improvement
reduces forecast overflow 192369 -> 191536 and obstacle crossings 105 -> 102;
lower-ranked residual overuse worsens 29 -> 48. Ten refusals remain. No routing
or fab authority is granted, and no unchanged full wave is relaunched.

Work rotated back to the shared local-ground boundary. The bounded PRIVATE
experiment `tmp/sibling_return_probe_20260916.py` is now **complete**, with no
remaining workers. Use **`build/sibling-return-probe-v2-20260916/report.json`**.
V1 inadvertently reused the process-local craft cache and did not exercise its
replacement constructor; it is not valid A/B evidence. V2 clears that diagnostic
cache and records actual constructor calls (PCIe2 26, PCIe3 40, Hub 54, VHP 32).

The experiment constructs an unvisited nearby same-package/same-layer/same-net
ground portal only after ordinary return search fails, retaining existing
native link/via/process/power checks and rollback. Across four concurrent
family probes, **zero alternate portals were accepted and no gate improved**.
Hub's adjacent U7 GND 3/4 peers are 0.500001 mm apart, but both still fail native
barrel/pad qualification; the other ground return meets frozen +5VSB territory.
There is no evidence that adding this extra production search would help, so it
was **not implemented**. All six source/hierarchy and shared engine hashes stay
unchanged; EPS/ATX remain interface-held. No diagnostic board is promoted.

Next investigation should distinguish discrete return-seat search coverage from
actual placement/power-domain conflicts using bounded, native-checked geometry
witnesses. Do not assume a failed radial menu proves impossibility, and do not
relax process minima, 1.5 mm return reach, frozen buses or release gates. Hub
still has three craft blockers; VHP retains its one priority-pair refusal and
deferred local cell. Rotate shared work across these classes rather than
launching another unchanged PCIe3 wave. The current canonical plan remains
`build/priority-coopt-next-inputs-20260916.json`; no full campaign is running.

## Current slice: priority work retention qualified (September 16)

The 15:55Z PCIe3 full pass below **failed at 16:15:10Z**, after two accepted
placement rounds and a third-round budget exhaustion. Ten priority refusals
remain; no routed or fab candidate was produced. Its accepted states were
temporary-only, so the dashboard correctly retained the unchanged seed.
Read [priority cooptimization durability](priority-cooptimization-durability-2026-09-16.md).

The generic outer loop now budgets complete rounds plus finalization and
durably checkpoints strictly improved, physically measured incumbents. Only
explicit operation budget exhaustion is handled as a bounded stop; integrity
failures still propagate. **168 tests passed**, plus concurrent native
checkpoint/interruption replay across PCIe2, PCIe3, Hub and 12VHPWR. Fresh
physical outcomes, protected copper, qualified pairs and historical PCIe2
control results are unchanged. All six source/hierarchy hashes are exact.
Receipt: `build/priority-coopt-durability-qualified-20260916.json`.

One changed-engine full pass started at **16:47:21Z** (worker PID 1037680,
shell session 13448). Launcher:
`tmp/priority_coopt_durability_pass_20260916.py`, output
`build/priority-coopt-durability-pass-20260916`. Check journal/process state
before launching or editing shared engine files. Do not duplicate it. It uses the canonical PCIe3
source and unchanged four-worker / 16-trial / 1200-second job limits. Do not
repeat unchanged exhausted work on other families; EPS/ATX remain interface-held.
Keep `build/bound-return-next-inputs-20260916.json` until independently verifying
the new full-pass output. Static legacy debt stays 23 physical / 380 runtime.

## Current pass: production return recovery qualified (September 16, 15:55Z)

Read [post-authority return recovery](post-authority-return-recovery-2026-09-16.md).
The real production recovery accepted its private placement in 197.62 s.
Independent fresh native physical/exact-power/copper/pair verification passes;
four-family physical parity, historical PCIe2 parity and all six canonical
source/hierarchy signatures pass. **165 tests passed**. Receipt:
`build/post-authority-return-qualified-20260916.json`. Static legacy debt stays
23 physical / 380 runtime; the new module has zero findings.

This clears the newly introduced return dependency, **not routing closure**:
ten priority refusals remain and the checked output contains no tracks/vias.
Forecast overflow improves 192369 -> 191536, but lower-ranked residual-overuse
metrics worsen 29 -> 48. Both sides of that ordered-objective tradeoff are
recorded; no acceptance policy was changed and no private board was promoted.

Historical launch record (now failed; see the current slice above):
`build/post-authority-return-pass-20260916`, launcher
`tmp/post_authority_return_pass_20260916.py`. It uses the bound-return canonical
PCIe3 input, four workers, 16 trials, 600-second priority / 1200-second job
limits and 16-GiB floor. Do not duplicate it or edit shared production scripts.
The journal confirms start **15:55:21Z**, PID 1011334, shell session 55166;
these identify this launch, not a substitute for checking live state.
The other five canonical inputs remain unchanged; their unchanged exhausted
waves were not repeated. EPS/ATX remain coupled-interface-held.

Its prepared verifier `tmp/verify_post_authority_return_pass_20260916.py`
requires a completed journal-verified board and is **not applicable** to the
actual failed seed-checkpoint result. Do not use it to bless a temporary
candidate or treat the intentionally changed engine as unexplained drift. Keep
`build/bound-return-next-inputs-20260916.json` meanwhile. The private recovery
placement is not a routed/fab candidate. If the full pass still stops on nine
Kelvin range failures plus CAN_J1, investigate the group-placement proposal
domain rather than repeating ordinary routing or relaxing the 9 mm limit.

Read-only preparation from the preceding roadmap pass adds a more precise
lead: its two Kelvin proposals actually reduced scoped refusals 10 -> 9 but
failed final craft. One violates the HI/LO terminal-order rule after rotation;
the other loses local supply access and intrudes into frozen pour territory.
Existing co-repair accepted neither. Thus not all nine range defects are
unproposed or unsearched. Next inspect the NEW completed-pass certificates
before changing the joint range/orientation/power-domain generator. The old
evidence is `endpoint-roadmap-pass-20260916/.../operation-priority-power-replan-o62s9plc/completion.json`,
under `ordinary_report.rounds[0].finalist_craft_rejected` and
`critical_probe_trials`; those witnesses are not assertions about a future
winning placement. No extra wave or producer edit was made for this review.

## Current slice: bounded post-authority return recovery (September 16, 15:33Z)

Read [post-authority return recovery](post-authority-return-recovery-2026-09-16.md).
The private native probe found a missing scheduling boundary: the existing
generic frozen-domain craft solver can clear the return failure introduced by
power rebuilding without changing that rebuilt power geometry. Fresh physical
gates pass; full priority refusals stay ten, with a modest ordered congestion
improvement. This is a constructive prototype, not board closure or promotion.

The shared one-shot boundary is implemented with exact/native checks and full
rollback, plus synthetic and loaded-native tests. **Validation is running**:
`build/post-authority-return-replay-20260916`, launcher
`tmp/post_authority_return_replay_20260916.py` (shell session 40582); session
88977 is the focused tests, not the native replay. Identify active native processes by
the launcher and its operation journals. Do not duplicate the run or edit
shared scripts. Tests: `build/post-authority-return-tests-v2-20260916.log`.
The focused tests are now complete: **165 passed** in 115.14 s, one existing
KiCad SWIG deprecation warning. Native replay is still running; initial PCIe2,
PCIe3 and Hub physical gate comparisons pass. Do not infer the production
trial result from those non-regression checks.
Native replay covers four families, the historical PCIe2 control and one real
production recovery; EPS/ATX retain their coupled-interface hold. All six
canonical inputs remain `build/bound-return-next-inputs-20260916.json`.

Next: verify test/replay completion, engine/source identities, the exact
recovered authority and full priority comparison. Only then decide whether a
changed-domain canonical pass is justified. Do not publish the private probe
as a candidate or count its unchanged ten priority failures as closure.

## Latest correction: telemetry no longer rejects placement (September 16, 15:03Z)

Read [placement identity output boundary](placement-identity-output-boundary-2026-09-16.md).
The unknown mutation below is now reproduced: only the supervisor's periodic
stack log changed. Its output bytes were incorrectly hashed as design input.
The shared correction excludes only declared diagnostic sink bytes, preserves
all real authority guards, and retains precise identity deltas through failure
reports. **290 tests pass**; eight fresh concurrent native checks across PCIe2,
PCIe3, Hub and VHP retain gate parity, including deliberate mid-check log
updates. Historical PCIe2 board/regression/probes match; all six canonical
source/hierarchy hashes and the frozen replay engine remain unchanged.

Receipt: `build/identity-output-qualified-20260916.json`. The real supervised
reproduction now gets past the false rejection and correctly rejects both
power proposals at the U3.5 local ground-return gate. No accepted geometry or
route-count improvement, no new board promotion, and no new gallery candidate.
All validation workers are finished; keep the bound-return canonical cohort.
Next shared solver work is coordinated local power/return reconstruction and
Kelvin group placement. EPS/ATX retain their existing coupled-interface hold.
About 65 GiB remains free. Legacy generic-audit debt stays 23 physical / 380
runtime findings; this is not full-pipeline or fabrication signoff.

## Latest completion: roadmap full pass remains placement-blocked (September 16, 14:29Z review)

The changed-domain pass finished at **14:13:43Z** (345.628 s). No worker remains.
Read the completion section in [roadmap integration](endpoint-roadmap-integration-2026-09-16.md).
`build/endpoint-roadmap-pass-qualified-20260916.json` verifies journal/output,
source/engine and all six source/hierarchy hashes. Fresh physical placement
checks pass, but output is **byte-identical** to the canonical PCIe3 input:
83 footprints, zero tracks/vias, one zone. The production solver's **11 -> 10**
priority reduction reproduces, but no placement change was accepted. This is
not a routed or fab-ready board. Both body-free views are visually inspected;
the immutable dashboard review is HTTP 200 and Windows copies are present.

Remaining PCIe3 blockers are **nine Kelvin placement-range violations**
(11.15–20.53 mm versus the existing 9 mm maximum) plus CAN_J1. More ordinary
routing cannot repair the physical distance violations. Repair ran four exact
probes and deferred three by the unchanged full-probe share; it reported
`critical_probe_budget_inconclusive`, not impossibility. Two power trials failed:
one introduced a post-authority U3.5 ground-return blockage; the other reported
`placement inputs changed during evaluation`. The latter is an integrity
failure, not an overlap. Its reduced trial record dropped the before/after
identity certificates, so its precise mutation is not yet known.

Next generic slice: retain compact identity-change evidence through coordinator
failure boundaries, then reproduce that disposable trial to identify its actual
changed role. Continue coupled local-power/return and Kelvin group-placement
work without weakening guards or fixed buses. Keep
`build/bound-return-next-inputs-20260916.json`; no board was promoted and no
unchanged full pass was restarted. Other families retain their existing status.
Review: `http://localhost:8090/?id=pass-endpoint-roadmap-pass-20260916-pcie-8pin-3port-5725b7ee9f`.

## Current production slice: complete-pair roadmap qualified (September 16, 14:08Z)

Read [complete-local-pair roadmap integration](endpoint-roadmap-integration-2026-09-16.md).
The source-derived bounded roadmap is now in the production precision router,
scoped to fresh complete physical pairs, with unchanged native guards and
final admission. **449 tests + two subtests pass**. Four current-family native
physical A/B reports match; historical PCIe2 hash/regression/probes match;
all six input/hierarchy signatures remain unchanged. New module static findings
are zero; existing full-pipeline debt remains 23 physical / 380 runtime findings.
Receipt: `build/endpoint-roadmap-qualified-20260916.json`.

Actual production priority replay gives PCIe3 **11 -> 10** failures, VHP **1 -> 1**.
The production selected N path differs from the prototype and qualifies using
the existing split-terminal absolute uncoupled-length budget; do not claim its
sampled coupling is 64.5%. The linked note records the exact 26.3%/3.151253 mm
measurement and unchanged 6.609231 mm local allowance. No full-board acceptance
or canonical geometry promotion has occurred.

One justified changed-domain full pass is **running**:
`build/endpoint-roadmap-pass-20260916`, started **14:07:55Z**. It runs PCIe3 with
four workers, 16 trials, 600-second priority / 1,200-second job limits and a
16-GiB disk floor. Inspect its live process and journal; **do not duplicate it
or edit shared scripts**. All other families retain the current bound-return
cohort; their unchanged exhausted waves were not restarted. When this pass
finishes, independently verify output/source/engine identity and native gates,
then inspect the new body-free review. Keep the canonical plan until qualified.
The first replay-harness JSON-vs-live equality error is corrected in **v2**;
use `build/endpoint-roadmap-replay-v2-20260916/report.json`, not the failed v1.

## Latest prototype: native roadmap finds the missing CAN paths (September 16)

Read [guarded endpoint roadmap prototype](endpoint-roadmap-prototype-2026-09-16.md).
The finite-domain lead now has a constructive result: a bounded exact-guard
octilinear roadmap finds PCIe3's local CAN paths at **1.113318x** detour and
**64.5%** sampled coupling. Returning the proposal to native priority preflight
reduces its refusal count **11 -> 10** (CAN_J1 and nine Kelvin routes remain).
Concurrent VHP remains **1 -> 1**. Both workers finished; all six canonical
source/hierarchy signatures and the production engine are unchanged.

Receipt: `build/joint-escape-roadmap-probe-20260916/report.json`. Ten prototype
tests pass, including saved/reloaded native foreign-copper preservation.
This is **not production-integrated or full-board-admitted progress**: no
canonical input, gallery, or board has changed. Keep the bound-return input
plan. Do not restart the exhausted slide-only experiment or an unchanged full
cohort. Next: bounded complete-local-pair integration with fast-path retention,
full contract/native rollback tests, historical PCIe2 control and cross-family
replay before any new board pass. Scope the contract correctly for physical
endpoints versus unfinished portal legs. The linked note records prototype
limits, source-bound evidence, and the remaining qualification work.

## Latest investigation: joint endpoint domain closed (September 16, 13:14Z)

Read [joint endpoint complete-contract counterfactual](joint-endpoint-domain-2026-09-16.md).
The canonical PCIe3 CAN domain is three P / 27 N paths, minimum P detour
2.071166x; the earlier six/32 and 2.176366x witness below came from a retained
diagnostic board, not this canonical source. A bounded native-clear internal
run translation yields 1.977756x, but actual private pipeline admission then
correctly rejects insufficient coupling. PCIe3 remains eleven important-route
failures and VHP one. All six sources/hierarchies and engine remain unchanged.

Exhaustive replay of all 594 expanded local combinations finds **zero** passing
the existing coupling contract; 17 pass detour. This is a missing joint coupled
candidate domain, not a reason to change weights, relax limits, or repeat the
same run. All workers are finished; no production integration or geometry
promotion. Keep `build/bound-return-next-inputs-20260916.json` and current
gallery. Next bounded slice: obstacle-derived shared corridor proposals with
complete local pair contracts, synthetic traps/split endpoints, then source-
bound PCIe3/VHP and historical PCIe2 regression. Existing independent final
checks stay mandatory. Hub local-power dependencies and EPS/ATX authority
holds remain separate. No unchanged full wave was started.

## Latest completion: six-board return-escape pass qualified (September 16, 12:43Z)

`build/return-escape-suite-20260916` completed at **12:26:26Z** after a 12:09:34Z
start. All workers are finished. The prepared independent verifier has now run:
`build/return-escape-suite-qualified-20260916.json`. Every source/hierarchy and
the shared engine remained unchanged; all published declared outputs are
journal/hash verified. EPS/ATX are explicitly partial placement, not admitted.

**No accepted closure gain.** PCIe2, PCIe3, Hub and VHP outputs are byte-identical
to their canonical inputs. PCIe2's fresh independent score is 0 DRC / 9 opens,
747 tracks, 386 vias and 1,654.3125 mm, with protected copper, qualified pairs
and local cells passing. The new incumbent rule has now been exercised by a real
full router pass, not only replay: `winner_origin=incumbent`, unchanged finishing.
Hub retains three craft blockers; PCIe3 eleven important-route failures; VHP one.
EPS/ATX retain fixed terminal pad conflicts and unadmitted interface ECOs.

All six top previews have been visually inspected across the live turn and this
completion review, plus PCIe2 and VHP bottom views. The immutable final gallery is
`C:/Users/Admin/Documents/CEC-Board-Reviews/return-escape-suite-20260916/all-boards-e45cb26876eb6c26.png`.
Dashboard Windows HTTP 200 is verified. PCIe2 review:
`http://localhost:8090/?id=pass-return-escape-suite-20260916-pcie-8pin-2port-c468158e8e`.
No scratch counterfactual was published as a candidate, no board was promoted,
and about 66 GiB remains free. Keep **`build/bound-return-next-inputs-20260916.json`**.
Do not repeat this unchanged full cohort or the closed local-cell order probes.

Next useful bounded solver investigation: inspect the actual **joint endpoint
escape** candidate domain for PCIe3's CAN witness (six P / 32 N native-clear
paths, selected maximum member detour 2.176366). The completed ribbon-order probe
does not test that generator. Record per-member minimum lengths and complete
pair admission constraints before deciding whether a new obstacle-derived
octilinear visibility domain is justified; merely changing weights or relaxing
the 2.0 ratio is not. Continue coupled local-power/neighbor-access work across
families, and keep EPS/ATX mechanical authority held pending the existing choice.
The monitor stays active but quiet on unchanged state; this full-pass completion
and its verified gallery are reported once.

## Current continuation: escape-aware local returns (September 16, 12:10Z)

Read [neighbouring pin escape preservation](return-escape-awareness-2026-09-16.md).
The shared return generator now ranks its unchanged finite dogbone domain by
loss of native-clear nearby pin exits; all electrical/fab/ownership gates remain
unchanged. **166 tests pass**. Concurrent four-family physical A/B replay and the
historical PCIe2 control are in `build/return-escape-replay-v2-20260916`.
The replay is complete: four full physical reports match, all historical control
probes/regression match, and existing generalization findings remain unchanged.
The new module is explicitly included in the static audit and has no findings.
Receipt: `build/return-escape-qualified-20260916.json`. No source board or
hierarchy was edited. This is prevention/qualification progress, not closure.

The complete-cell diagnostic is closed: all six producer-bound copper items and
11 direct external contacts were retained by reconstruction, but both orders
remain 0 DRC / 9 opens. A second counterfactual attempted the soft-start route
before reconstructing the cell and still refused. The adjacent resistor/pin/
track and reserved power are additional causes; isolated return replacement is
not a justified closure fix. See v2/v3 receipts in the linked note; do not repeat.

The user's renewed all-board request is being exercised as one bounded concurrent
campaign, `build/return-escape-suite-20260916`, launcher
`tmp/return_escape_suite_20260916.py`. Inspect its journal/live process: do not
duplicate it or change shared scripts during workers. Six jobs, four workers
each, 16 trials, 600-second priority / 1,200-second job limits, 16 GiB disk floor.
Review and qualify outputs as they finish; no geometry is automatically promoted.
EPS/ATX stay interface-held; no new mechanical authority has arrived. Retain
`build/bound-return-next-inputs-20260916.json` unless independently qualified
campaign evidence supports a new continuation.

Live review at 12:15Z: EPS (77.45 s), Hub (252.50 s) and ATX (270.69 s) have
finished. Their top body-free previews were visually inspected. EPS/ATX retain
fixed terminal-pad shorts; Hub is byte-identical to its canonical input and
retains three craft blockers. PCIe2 is in detailed routing; PCIe3/VHP are still
in placement/priority qualification. No full-pass closure gain is claimed.
Dashboard Windows HTTP 200 is verified. Full-suite verifier is prepared at
`tmp/verify_return_escape_suite_20260916.py`; run only after `finished_utc` exists,
then inspect remaining top/bottom previews and consolidate the actual outcome.
The existing 15-minute monitor is active and has been viewed through the app.
Do not create a duplicate monitor or restart this campaign. About 66 GiB remains
free. All diagnostic cell-order probes are complete; no generic unlock actuator
was integrated. Next causal repair must include neighbouring access dependencies,
not merely repeat the isolated GND-cell counterfactual.

## Latest continuation: bounded pair-order counterfactual closed (September 16, 11:30Z)

Read [pair ordering and ownership lead](pair-ribbon-order-counterfactual-2026-09-16.md).
Two simultaneous disposable short-pair proposal-order probes completed:
PCIe3 retained diagnostic 11 -> 11 priority failures in 87.258 s; current VHP
1 -> 1 in 76.835 s. The finite candidate sets and all admission gates were
unchanged. This prototype is **not integrated**, and no full wave or geometry
promotion follows. Evidence: `build/pair-ribbon-cost-probe-20260916/report.json`.
All six canonical source/hierarchy hashes and the shared engine are unchanged.

PCIe3's overlong CAN proposal actually comes from the separate joint-endpoint
escape domain, not a selected ribbon; the exact member detour remains 2.176366x.
Do not repeat ribbon reordering or the already exhausted early-detour-only test.
VHP remains an exact physical access dependency, not a missing permission to
use an unqualified through via or move a fixed bus.

A separate current PCIe2 refusal again identifies the regulator soft-start
escape blocked by a generated local GND return. Its via/track occur in the old
producer lineage screen. Next useful ownership slice is a fresh **whole-cell**
producer/source/pad/shared-dependency binding and bounded atomic reconstruction
test, not isolated UUID deletion or arbitrary via shrinking. The linked note
records exact evidence locations and the existing netclass restriction.

All probe workers finished. Keep **`build/bound-return-next-inputs-20260916.json`**
and the current dashboard / gallery; no changed board exists to republish.
EPS/ATX mechanical direction remains unanswered and no interface changes are
authorized by this diagnostic. Stay quiet on these unchanged board results.

## Latest continuation: retain the real routed incumbent (September 16, 11:04Z)

Read [fresh incumbent selection](route-incumbent-selection-2026-09-16.md).
The previously identified selection defect is now corrected generically.
Canonical route ensembles include a fresh, read-only, identity-bound grade of
their routed input. Previously passing gates cannot be traded away; safety and
connectivity precede via / length costs, and exact ties retain the incumbent.
Missing or changed baseline evidence fails closed. The explicit routing seed
budget is unchanged; zero-track placements are not treated as routed incumbents.

Finishing-only improvements remain available on disposable copies. A changed
incumbent finish must preserve protected copper / qualified pairs and win a
fresh complete-oracle comparison; failure retains the untouched graded family.
No route, load, thermal, current, mechanical or fab limit was weakened.
**149 tests pass** in 111.56 seconds, with one existing KiCad SWIG warning:
`build/route-incumbent-final-tests-20260916.log`. This includes loaded-native
artifact mutation and finishing rollback / admission controls.

The native concurrent replay completed with all six source/hierarchy identities
unchanged. Four current-family physical reports retain exact parity: Hub/VHP
tie controls, PCIe3 zero-track inapplicability, and the real PCIe2 coordinator
selection replay. EPS/ATX remain explicitly interface-held. The first diagnostic
wrongly asserted that PCIe3 must have tracks; production correctly skipped that
placement and the corrected **v2** diagnostic passes. Use
`build/route-incumbent-replay-v2-20260916/report.json`.

PCIe2 now automatically keeps the existing **386 vias / 1,654.31 mm** instead of
the previous proposal's **387 vias / 1,656.95 mm**, with both at **0 DRC / 9 opens**
and identical failed gate terms. The selected PCB is byte-identical to the
canonical incumbent, and protected copper / qualified pairs pass. This is a
fresh native grade and coordinator replay of the real previous candidate, not
a new router wave or closure improvement. The full historical PCIe2 control,
all probes, regression and generalization reports remain exactly unchanged.
Consolidated receipt: `build/route-incumbent-qualified-20260916.json`.

All workers finished; about 66 GiB is free. Keep
**`build/bound-return-next-inputs-20260916.json`** and the existing six-board gallery.
No geometry was promoted and no unchanged cohort was restarted. Next physical
work remains complete priority / power-cell dependencies, plus paired terminal
fit within the user's dimensional authority. EPS/ATX direction remains unanswered;
do not expand spans, shrink lands or move only one mating half. The existing
monitor stays active, quiet on unchanged state, and must not re-run this completed
selection replay or treat it as routing progress.

## Latest continuation: complete collateral pair stations (September 16)

Read [collateral station eviction](collateral-pair-station-eviction-2026-09-16.md).
Local legalization now propagates secondary translations through complete
router-derived pair stations before exact admission, or refuses conflicting,
missing or fixed members. No electrical or physical rule is relaxed. **444
combined tests pass**; four concurrent native-family replays retain complete physical
parity and all six source/hierarchy identities are unchanged. The complete
historical PCIe2 control's physical probes and regression remain identical;
generalization findings are unchanged, with the new helper added to its audit
inventory (explicitly checked, not silently normalized away).

The PCIe3 counterfactual keeps both split-station resistors together and clears
local craft after power rebuild, but still reports 11 important-route failures.
The 2.176366 CAN_H detour remains above 2.0. Do not promote that diagnostic,
waive the detour limit or broaden a post-power retry loop on this result alone.
Evidence: `build/station-eviction-qualified-comparison-20260916.json`.

**The concurrent full-suite campaign is complete** under the live user's explicit
all-board request: `build/station-eviction-suite-20260916`, launcher
`tmp/station_eviction_suite_20260916.py`, log
`build/station-eviction-suite-20260916.log`. Six jobs / four workers per board,
16 trials, 600-second priority / 1,200-second job bounds, 16 GiB free-space floor.
It ran from 10:10:06Z to 10:27:07Z. **No accepted closure gain.** Hub, PCIe3 and
VHP final PCBs are byte-identical to their incumbents (3 craft, 11 priority and
1 priority blocker respectively). EPS/ATX retain fixed terminal pad shorts and
only partial-placement reviews. PCIe2 has 0 DRC / 9 opens, 749 tracks / 387 vias /
1,656.9508 mm; protected copper, qualified pairs and native local cells pass.
It adds one via and 2.6383 mm versus its incumbent, so it is not adopted.
Independent receipt: `build/station-eviction-suite-qualified-20260916.json`.
All six source/hierarchy identities and engine signatures remain unchanged.

All previews published; all six top views and PCIe2 bottom were inspected.
Windows gallery: `CEC-Board-Reviews/station-eviction-suite-20260916/all-boards.png`.
Keep **`build/bound-return-next-inputs-20260916.json`**. The Hub's preceding
canonical 4 -> 3 gain is already verified/adopted there; this cohort adds none.
All workers/tests/diagnostics finished; about 66 GiB remains free. No unchanged
cohort relaunch is justified. The existing monitor should stay quiet for unchanged
state and follow the newly identified work rather than repeating these waves.

Next evidence-backed generic fix: include a freshly graded incoming routed
artifact in ensemble selection and break otherwise-equal failing grades by
unnecessary copper costs. `build/route-incumbent-compare-20260916/report.json`
proves complete oracle ranks/gate terms equal while the prior proposal adds
copper; `_route_stage` currently compares only newly generated candidates.
This selection repair is **not implemented yet**. A separate early short-pair
detour qualification experiment still leaves 11 failures, so do not integrate
it as a claimed closure fix or expand the post-power retry loop on that result.
EPS/ATX dimensional/terminal direction was asked asynchronously; no new mechanical
authority has been received and no paired interface was changed.

## Latest continuation: complete bound return geometry, Hub substage gain (September 16)

Read [complete bound return context](bound-return-reservations-2026-09-16.md).
Production craft proposals now use the native guard's complete power projection
only when its file identity matches the measured evidence. Truncated first-hit
certificates no longer hide the next tile. No physical gate or ownership limit
was relaxed. **310 tests pass**, including loaded-native checks. Four concurrent
native-family replays retain physical parity; EPS/ATX stay interface-held. All
six source/hierarchy signatures and the complete historical PCIe2 control remain
unchanged. Receipt: `build/bound-return-qualified-comparison-20260916.json`.

The production-equivalent Hub screen commits **4 -> 3 craft blockers**, with
frozen pours/vias/corridors/owned pins unchanged and independent copper-prefix/
qualified-pair checks passing. Use `build/bound-return-hub-screen-v2-20260916`.
V1 omitted the frozen search domain, proposed an owned-cell rotation and was
correctly rolled back; do not claim that diagnostic's lower count as admitted.

PCIe3's new return repair clears its newly introduced local-cell blocker and
survives power rebuild, but a passive eviction perturbs a differential-pair
station: full priority qualification returns to 11 critical failures. No global
gain, no promotion. Next generic work must preserve/co-optimize complete pair
stations during local eviction, alongside complete owned-cell power replacement
where needed; do not loosen the detour gate or independently move frozen owners.

**Bounded canonical Hub pass completed:** `build/bound-return-hub-pass-20260916`,
launcher `tmp/bound_return_hub_pass_20260916.py`, log
`build/bound-return-hub-pass-20260916.log`. Four workers, sixteen trials,
600-second priority and 1,200-second job limits; 16 GiB free-space floor.
The 260-second ordinary pass reproduced **4 -> 3** blockers. Independent fresh
physical measurement agrees with the journal, and protected copper, qualified
pairs and all five frozen power fields pass. All six source/hierarchy identities
remain unchanged. Receipt: `build/bound-return-hub-pass-qualified-20260916.json`.
The journal-selected output SHA is
`de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
Use the immutable new continuation plan **`build/bound-return-next-inputs-20260916.json`**;
only its Hub input changes. This is a blocked-placement continuation, not route
or fabrication admission. Do not repeat an unchanged wave at this plateau.
The dashboard review is `pass-bound-return-hub-pass-20260916-hub-standard-rev2-d09e8de6de`;
top/bottom Windows previews are in `CEC-Board-Reviews/bound-return-hub-pass-20260916`.
Dashboard returned HTTP 200; the bottom preview was inspected as well. All full
pass workers are finished. Subsequent collateral-pair repair tests/replays are
recorded separately; inspect live processes before editing shared scripts.

## Latest continuation: union-aware return exits; no accepted geometry (September 16)

Read [return reservation unions](return-reservation-union-2026-09-16.md).
The exact PCIe3 witness exposes exits from one raster reservation tile entering
its neighbour. Generic axial interval-union proposals now avoid that known
union, preserve real gaps/concavities and keep existing full-cell ownership,
move budgets and exact admission gates. Native evidence has 25 such traps among
68 portal/rotation domains. This is proposal correctness, not board closure.

The unchanged 16-trial craft counterfactual accepts zero moves before and after
the fix (20 -> 22 legal evaluated variants). The existing post-power repair
hook was **not** expanded to invoke another known-unproductive loop. A retained
moved finalist reveals a third frozen tile absent from the original truncated
refusal samples. Next: supply the same complete identity-bound reservation set
used by `cec_power_guard_geometry.reservations` to the proposal generator; do
not substitute the body-pour projection or waive a via conflict. Evidence:
`build/return-union-refused-finalist-20260916/report.json`.

Four native family replays have complete physical-report parity; EPS/ATX remain
interface-held. All six sources/hierarchies and the historical PCIe2 control's
complete probe/regression/generalization reports are unchanged. Receipt:
`build/return-union-qualified-comparison-20260916.json`. **343 tests pass** in
510.18 seconds, including the loaded-native cell/frozen-domain suites. Log:
`build/return-union-tests-20260916.log`. All workers are finished; 66 GiB remains
free. No board adopted, full wave repeated or preview republished. Keep
`build/route-finish-next-inputs-20260916.json` and the current gallery.

## Latest continuation: causal-owner fairness, six concurrent full passes (September 16, 08:22Z)

Read [causal-owner fairness and full-pass results](causal-owner-probe-fairness-2026-09-16.md).
The bounded selector previously divided slots by alternative evidence group,
allowing one owner's variants to starve other causal owners. It now allocates
owner quotas first, then preserves within-owner evidence diversity and reserves.
No board/refdes/coordinate special case or admission waiver was introduced.
**233 tests pass, 13 legacy skips.** Same native population / same 16-trial budget:
four -> ten causal owners and zero -> nine intended Kelvin-range proposals.
Receipt: `build/owner-menu-ab-20260916.json`.

All six canonical jobs ran concurrently, with four workers per board and bounded
600-second priority / 1,200-second job allowances. They finished; **no accepted
closure gain**. PCIe2 remains 0 DRC / 9 opens, but adds one via and 2.6383 mm,
so retain its earlier incumbent. PCIe3's provisional 11 -> 10 critical gain was
rolled back because rebuilt power reservations fail U3.5's ground-return gate.
Hub retains four local-cell blockers; VHP retains one USB-pair refusal with its
278 protected items intact. EPS/ATX retain fixed terminal pad conflicts and only
partial-placement previews. Full receipt and all per-board evidence:
`build/owner-fairness-suite-20260916/suite.json`.

PCIe3's identical-PCB/different-power-state refusal is reproduced with the real
coordinator wrapper in `build/owner-power-boundary-forensic-v2-20260916/report.json`.
V1 omitted caller state rebinding and must not be used to dismiss the live
failure. Retained before/after families allow the next geometric obstruction
audit without another full wave. Complete cell dependency repair is not done.
Do not waive the rejection or unlock copper by labels/path UUIDs alone.

All six source/hierarchy identities and the protected historical PCIe2 control's
complete probe/regression/generalization payloads are unchanged. Independent
receipt: `build/owner-fairness-qualified-comparison-20260916.json`. This is control
parity, not fresh fab approval. Keep `build/route-finish-next-inputs-20260916.json`;
no new candidate is adopted and no unchanged cohort relaunch is authorized by
this result. The live user's continuation authorized this new-engine pass only.

Twenty full-row signed transverse main/mate counterfactuals find **no paired fit**.
Use `build/full-row-transverse-screen-v4-20260916/report.json`, not earlier partial
screens: v4 adds necessary off-board pad containment to native DRC. ATX's current
unadmitted staging input lacks a closed outline. No interface ECO, isolated mate
movement, pad shrink, envelope growth or routing admission follows from this test.

All previews are on the dashboard with blocked stages and hashes; the Windows
gallery is `CEC-Board-Reviews/owner-fairness-suite-20260916/all-boards.png`.
All six tops and PCIe2 bottom were inspected. Next work is the exact power/cell
obstruction and complete-pair terminal ordering, plus an audit of incumbent
comparison at route selection, not a repeat of unchanged waves. All workers
finished; the existing heartbeat remains active and should stay quiet for an
unchanged/non-actionable state.

## Latest continuation: exact local-copper proof, richer witness not integrated (September 16)

Read [exact local proof and witness screen](exact-local-copper-proof-and-witness-screen-2026-09-16.md).
The shared local path helper still defaulted to 60 um snapping for supply and
shared returns, although immediate-GND callers had already opted into 1 nm.
Native negative controls reproduce fictitious local paths across real gaps.
All callers now use native resolution; coarse override requests fail closed.
No locality, fabrication, current or ownership limit was relaxed.

**477 tests pass**, 140.14 s. Four concurrent native before/after local-cell
audits retain identical complete reports; EPS/ATX remain interface-held. Use
`build/local-copper-proof-replay-v2-20260916/report.json`: v1's compact refusal
counter queried an absent field, although its full payloads were correct.
All six source/hierarchy identities and the entire historical PCIe2 control are
unchanged. Receipt: `build/local-copper-proof-qualified-comparison-20260916.json`.

A richer exact-junction/path-UUID prototype gains **zero cells in 61 actual
supply queries**, and is slower on PCIe2. It is kept only in
`tmp/local_copper_path_witness_20260916.py`, not integrated into the production
hot path. It grants no unlock authority. Do not repeat that exhausted screen.

All workers finished; 66 GiB is free. No geometry promoted or preview republished.
Keep `build/route-finish-next-inputs-20260916.json`. Next work must address actual
priority/local-cell dependencies or paired EPS/ATX fit, not another unchanged
wave or further tuning of these proofs. Complete-cell source/dependency binding
and atomic qualified replacement are still unfinished; do not remove tracks by
label or by isolated UUID-path evidence. Existing heartbeat remains active.

## Latest continuation: filtered terminal placement coverage (September 16, 07:12Z)

Read [filtered terminal placement demands](filtered-terminal-placement-demands-2026-09-16.md).
The real placement hook and cheap search now consume complete filtered paths,
not only direct shunt/IC shared nets. VHP terminal-order coverage is **0 -> 6
relations / 24 actual same-net segments**. Full/cheap metrics agree and all six
currently have zero demand crossings. No fictitious conductor bridges a series
resistor. This is corrected search coverage, not new routed copper or closure.

**461 tests pass**, 138.29 s; loaded-native front/back/rotation, stale identity,
multi-stage and crossed-rotation regressions are included. Four native families
were replayed concurrently, then through the actual production craft hook;
EPS/ATX retain their interface holds. Direct relations and existing craft
verdicts remain unchanged. All six source/hierarchy signatures and the complete
protected PCIe2 control are identical. Final receipt:
`build/filtered-terminal-qualified-comparison-20260916.json`.

All workers finished; 66 GiB is free. No board promoted or preview republished.
Keep `build/route-finish-next-inputs-20260916.json`; no unchanged wave is justified
by this newly passing coverage alone. Next work must return to physical owned
cell/priority access or coupled EPS/ATX geometry, not repeat the VHP search or
polish these already-passing filtered paths. No filter-specific new rotation
search or local-cell unlock authority was added. Existing heartbeat remains active.

## Latest continuation: per-plan hole index and work-stop repair (September 16)

Read [per-plan hole index and honest work stopping](per-plan-hole-index-and-work-stop-2026-09-16.md).
The previously proposed exact hole lookup is now implemented. A scalar spatial
snapshot is rebuilt for each read-only bridge plan; native exact legality and
first-blocker evidence are unchanged. All 541 warm native/indexed queries match.
PCIe2's measured guard batch is about 39 times faster, not its whole router.

Fixed-work replay also exposed outer last-mile loops spinning after the inner
search budget had stopped. They now stop immediately and report work exhaustion
as an unproved search outcome, separately from wall timeout. No new production
quota is introduced. The PCIe3 diagnostic falls from about 60.2 seconds and
thousands of futile refusals to 0.919 seconds and one explicit budget refusal.

**445 tests and eight subtests pass.** Final receipt:
`build/hole-snapshot-qualified-tests-20260916.log`. Four concurrent fixed-work
family replays have exact score/copper/zone parity; EPS/ATX remain interface-held.
All six source/hierarchy identities and the historical PCIe2 control's PCB,
complete regression and probes are unchanged. Only generality metadata differs.
Receipt: `build/hole-snapshot-qualified-comparison-20260916.json`.

**Do not promote the timed probe:** the equal-wall-time VHP diagnostic worsens
by one open (189 -> 190). More search is not automatically a better board. PCIe2
gets more search but remains 0 DRC / 9 opens. No new candidate is admitted, no
full wave or preview republished. Keep `build/route-finish-next-inputs-20260916.json`.

All test/control/replay workers are finished; about 66 GiB is free. Do not repeat
identical timed probes or keep tuning this query kernel. Next physical work is
owned priority/local-cell access and coupled EPS/ATX geometry, not moving preserved
buses or one mating half. Existing deterministic scopes now stop honestly;
incumbent scoring must reject worse time-limited outputs. Heartbeat remains active.

## Latest continuation: exact new-hole pairs and measured endpoint cost (September 16)

Read [proposed-hole spacing and endpoint work](new-hole-pair-spacing-and-endpoint-work-2026-09-16.md).
The remaining fixed 0.85 mm pair refusal is replaced by actual proposed drill
radii plus the board hole gap. The old spacing survives only as a soft search
preference, keeping existing viable candidates ahead of new compact fallbacks.
An initial global reordering worsened VHP's bounded diagnostic by two opens;
it was not admitted, and stable preference tiers remove that regression.

**414 tests and eight subtests pass.** Four native old/new family replays retain
source poses/copper; EPS/ATX remain interface-held. Final VHP/Hub/PCIe2 metrics
are identical; PCIe3's one-open timed difference is not an attributed gain.
The historical PCIe2 control is completely identical, not just its board hash.
Receipts: `build/new-hole-pair-qualified-suite-20260916/report.json` and
`build/new-hole-pair-qualified-comparison-20260916.json`.

**Next measured work:** `build/endpoint-work-profile-20260916/report.json` shows
PCIe2's 15.111 s profiled attempt spends 12.838 s in 2,839 via-legality calls,
before ever ranking a complete seat pair. Stub mazes account for under a second.
Investigate exact per-plan existing-hole snapshots/spatial lookup and repeated
native enumeration, with mutation/lifetime guards; don't simply raise budgets.
No such optimization is implemented yet. Physical/mechanical peer-board holds
remain separate; do not move only one mating half or change preserved buses.

All workers finished. No new admitted board, full wave or preview. Keep
`build/route-finish-next-inputs-20260916.json`; the existing heartbeat stays active.

## Latest continuation: shared current binding and consumer parity (September 16)

Read [current authority binding and consumer parity](current-authority-binding-and-consumer-parity-2026-09-16.md).
The missing VHP current-name mapping is repaired generically. Native source/sink
authority now binds absent names with ambiguity/collision checks; routing and FEM
consume the same selected terminal banks. The width gate refuses resolver errors
instead of silently dropping the current map. Declared route-current/margin
provenance survives renamed or already-normalized configuration keys.

`build/current-binding-qualified-suite-20260916/report.json` checks four families
concurrently, with all six immutable source/hierarchy identities retained.
VHP current-domain coverage is **15 -> 16/16**; routing/thermal identities and
hint-versus-path width contracts agree. This reveals a real lane-six width/path
refusal, not a new placement or route pass. Other native gate verdicts remain;
EPS/ATX stay interface-held. No electrical budgets or bus geometry changed.

Final tests: **466 tests and four subtests pass**, 142.61 seconds,
`build/current-binding-complete-tests-20260916.log`.
Final control: `build/current-binding-qualified-control-20260916.json`; receipt
`build/current-binding-control-comparison-20260916.json`. Read these completion
receipts before further changes if this turn was interrupted. Control PCB hash,
complete regression and all probes match; only generalization metadata differs.
All test/control/replay workers have finished. The earlier
452-test pass is superseded by the complete suite including provenance and
thermal profile/geometry regressions. Do not sum overlapping test counts.

Keep `build/route-finish-next-inputs-20260916.json`; no new candidate is admitted
or preview republished. 8090 responds; the existing 15-minute heartbeat is active.
No unchanged long wave is justified by an identity-only repair. Continue physical
dependency work across the suite, not the exhausted dogbone/cell-budget ablations.

## Latest continuation: filtered sense proof and current-name gap (September 16, 05:15Z review)

Read [filtered sense lineage and current-name coverage](filtered-sense-lineage-and-current-name-gap-2026-09-16.md).
The shared adjacency checker now resolves actual typed series-filter paths
instead of choosing the nearest shunt in board X. All six VHP input channels
resolve; native alignment is measured in their actual shunt frame. Existing
limits remain unchanged. 434 tests and two subtests pass, including loaded
front/back/arbitrary-rotation and old false-pass controls. Four concurrent native
family replays retain their gate verdicts; EPS/ATX stay interface-held. Historical
PCIe2 board/probes are unchanged; only core-audit metadata differs.

**New confirmed gap, next priority:** configured VHP `/SENSEP6_HI` is absent
after the approved pre-shunt fan net became `/FAN_12V`. Its existing 8.33 A
contract and J3->RS6 authority uniquely identify that actual net, but the current
domain resolver silently skips it (15/16 configured domains). This mapping is
not repaired yet; do not claim all thermal consumers omit the load until their
actual call paths are audited. Preserve the approved budget and bus. Implement
unique native endpoint resolution with ambiguity/conflict guards and shared
consumer proof before any affected wave.

No new placement/route is admitted, no long-wave/replay worker remains, and
no preview is republished. Keep `build/route-finish-next-inputs-20260916.json`;
all six source/hierarchy guards hold and about 67 GiB is free. The filtered
critical-terminal-order placer still needs actual multi-segment path integration;
the completed slice is the independent topology/alignment gate, not that placer.

## Latest continuation: exact current-input placement authority (September 16, 04:42Z review)

Read [terminal pin identity and local-domain probes](terminal-pin-contract-and-local-domain-probes-2026-09-16.md).
Full and cheap placement scoring were selecting same-net VBUS instead of IN-
on current PCIe monitors. Both now use the existing shared device-pin contract,
with explicit fail-closed missing-geometry behavior. Five actual PCIe endpoint
selections are corrected across the two families. No current crossing count or
recommended orientation changes; this is a correctness repair, not closure.

397 integrated tests pass; the overlapping nineteen-test contract suite also
passes an added old-false-pass negative control. Four current families replayed
concurrently, with EPS/ATX correctly interface-held. All six source/hierarchy
guards and the complete historical PCIe2 control remain unchanged. Three private
local-domain alternatives (qualified small dogbones, alternate ground pins,
16x supply-search work) did not improve any complete cell and were not adopted.

No new placement/route is admitted, no duplicate wave is running, and no
identical image is republished. Keep `build/route-finish-next-inputs-20260916.json`.
8090 and retained review hashes were verified; about 67 GiB is free. A newly
measured coverage gap is filtered INA240 sense topology on VHP: direct HI/LO
anchor discovery omits it. Follow the actual series-filter chain; do not treat
its differential filter capacitor as a shunt. Other physical board holds stay
active; do not repeat the three exhausted counterfactuals.

## Latest continuation: qualified endpoint process alternatives (September 16, 03:50Z review)

Read [endpoint POFV domain and inline ablation](endpoint-pofv-domain-and-inline-ablation-2026-09-16.md).
The precision endpoint fallback now tries the already-declared local process
floor after preferred-geometry qualification fails. Partial new barrels roll
back before retry; inherited copper, ordinary via minima, all-layer clearance
and the shared deadline remain binding. **244 tests and two subtests pass**.

Four concurrent current-family old/new pair probes show unchanged final native
geometry/poses/DRC/connectivity; EPS/ATX retain their interface refusal. VHP's
connector endpoint qualification now reaches inner routing, which still fails;
its MCU through-via is blocked by actual locked B.Cu power-path copper at both
allowed dimensions. This is not a solved route or permission to reroute the bus.
Removing future-inline hints in a separate counterfactual did not solve it and
was not integrated. The historical PCIe2 control remains unchanged.

No new reviewed candidate or full routing gain; no duplicate wave launched.
All six canonical source/hierarchy signatures remain valid. Keep
**`build/route-finish-next-inputs-20260916.json`**. No replay/control workers
remain. Next consume exact fixed-copper access evidence or advance the other
independent board dependencies, not another unchanged pair-domain ablation.

## Latest continuation: full PCIe3 verification completed (September 16, 03:27Z review)

The owned-prefix fix survives canonical placement preflight: critical-route
failures decrease **12 -> 11**, specifically route-quality refusals **1 -> 0**.
Nine Kelvin reach failures and two CAN pair refusals remain. Local craft passes,
but no placement move is admitted and detailed routing does not begin. The
output is still exact **400ffdd8635e**; this is a repaired USB qualification
defect, not a new routed layout or fabrication closure.

`build/covered-prefix-followup-suite-20260916/suite.json` finished blocked after
**659.227 seconds**, with source, hierarchy and engine unchanged. No owned
pipeline worker remains. The immutable review is journal/hash/API verified and
both body-free panels were visually inspected:
`pass-covered-prefix-followup-suite-20260916-pcie-8pin-3port-effa868feb`.
It is explicitly labeled BLOCKED / placement / NOT FAB SIGNOFF.

Receipt: **`build/covered-prefix-followup-completion-20260916.json`**. All six
current source/hierarchy signatures still match the canonical plan; the plan
remains **`build/route-finish-next-inputs-20260916.json`**. PCIe2's 0 DRC / 9 opens,
Hub's local-cell holds, VHP's USB escape hold and EPS/ATX's coupled-interface holds
are unchanged, not new native passes. Approximately 66 GiB remains free.
Do not repeat this exhausted PCIe3 pass. Rotate to independent physical
dependency work; do not spend another cohort merely reconfirming these holds.

## Latest continuation: PCIe3 USB prefix blocker repaired (September 16, 02:44Z review)

Read [owned-prefix normalization and rejected fan-in experiment](owned-covered-prefixes-and-fanin-ablation-2026-09-16.md).
The precision pair normalizer could not remove a narrow long leg's redundant
overlap with wider package-closure prefixes. A generic, exact, writable-UUID
trim now preserves the physical copper union and explicit junctions. The current
PCIe3 selected USB probe changes **pairs_ok false -> true**, retaining zero DRC,
48 tracks and 246 opens in that private partial diagnostic. This is not full-board
closure. Other native pair results and the historical PCIe2 control are unchanged.
**219 tests plus two subtests pass**, including loaded/native authority cases.

The separate obstacle-derived local fan-in prototype found no new solved pair
and was not integrated. Do not repeat that unchanged domain as another wave.

**New canonical verification is running:**
`build/covered-prefix-followup-suite-20260916/suite.json`, explicit PCIe3
**400ffdd8635e**, four workers, eight trials, 480-second priority/900-second job
bounds. Check live processes/journal before edits or dispatch; do not duplicate
the pass. The other five retain their holds; current six-source plan remains
**`build/route-finish-next-inputs-20260916.json`** until verified completion.

## Latest continuation: live pair-copper probe indexes (September 16, 02:20Z review)

Read [pair-probe copper lifetime](pair-probe-copper-lifetime-2026-09-16.md).
Shared portal caches incorrectly retained opposite-member track/via shapes
across distinct local solves. The solver now rebuilds those indexes once per
local solve, retaining fixed-package caching and every exact physical gate.
**24 loaded-native old-cache negative controls reproduce stale clearance**;
the combined suite passes **177 tests and two subtests**.

Four current-family old/new pair probes and independent native comparisons
have identical copper/poses/DRC/connectivity and pair/Kelvin results. EPS/ATX
retain their interface-ECO refusal. Historical PCIe2 control is unchanged.
This correctness defect is not claimed to cause the current board holds;
there is no new routed/fab candidate and no duplicate wave is justified.

Keep **`build/route-finish-next-inputs-20260916.json`**. All replay/control
workers are complete; no full cohort runs. A distinct next physical domain
is obstacle-derived **local fan-in bends** (not previously exhausted portal
seat offsets), or the other boards' power/mating dependencies. Do not turn
these unchanged replay outcomes into a claim of board progress.

## Latest continuation: failed-step inputs retained (September 16, 02:04Z)

Read [exact failure-input evidence](fab-failure-input-evidence-2026-09-16.md).
Root cause of the missing forensic input: isolated fab failures lost their
temporary pre-step board, leaving only an error string and a different winner.
The generic transaction now retains hash-bound, bounded pre-step files plus
child command/status/stack on failure; successful trials add no durable storage.
The original native -11 is **not reproduced or claimed fixed**.

**71 tests pass**, including a loaded-native crash fixture, every fab substep,
concurrent quota and no-regression coverage. Four current families concurrently
completed five variants each with no crashes; native source/pose/power guards
pass. EPS/ATX retain admission refusals. Historical PCIe2 control is unchanged.
PCIe3's private fill reports 254 -> 223 opens but still zero tracks: do not call
that routing progress or promote it. No new reviewed board or closure result.

Canonical plan remains **`build/route-finish-next-inputs-20260916.json`**; no full
cohort or diagnostic workers remain running. Do not rerun waves for this logging
patch alone. Return next to a distinct physical priority-access, power-dependency
or coupled-interface cause, preserving all existing dimensions and budgets.

## Latest continuation: verified route finish and duplicate lifetime (September 16, 01:26Z review)

The scheduled follow-up finished in **426.955 seconds** and reached independent
signoff, instead of dying at 600 seconds. PCIe2 now retains a journal-verified
**0 DRC / 9-open** routed continuation, SHA **10cf3682c1d7**. The earlier 10-to-9
gain survives the complete pipeline; scheduling itself did not create it.
All local cells pass, but connectivity, route craft and other release gates
remain. **Not fab-ready; no Gerbers issued.** Body-free top/bottom previews are
verified on the dashboard under
`pass-route-finish-budget-suite-20260916-pcie-8pin-2port-dde3edbe34`.

Two generic duplicate-cleanup defects are fixed: different-width coincident
tracks no longer count as exact duplicates, and permanent cleanup uses native
lifetime-safe disposal. **56 tests pass**, with legacy negative controls. Four
current-board native replays preserve DRC/connectivity, poses and power prefix;
EPS/ATX retain their admission refusals, not claimed native passes. Historical
PCIe2 regression/probes are unchanged. One earlier fab variant segfault remains
unreproduced; these fixes are not claimed to explain it.

Canonical continuation plan: **`build/route-finish-next-inputs-20260916.json`**.
No full cohort is running; identical retries remain unauthorized. Other boards
retain distinct craft, priority-routing or coupled-interface holds. Read the
[completed validation and next holds](route-finish-budget-and-transverse-screen-2026-09-16.md).
Earlier sections below are historical, not the live run state.

## Latest continuation: route finish starvation and wider mating domain (September 16)

Read [finish-time scheduling and native transverse screen](route-finish-budget-and-transverse-screen-2026-09-16.md).
The nine-open PCIe2 follow-up passed intake, placement and preflight, but exhausted
its 600-second job before the route oracle returned. A 221.586-second optional
certificate repair ignored the enclosing deadline and gained no DRC/open-count
improvement. No journal-qualified route winner exists; no intermediate is promoted.

Generic repairs now fund optional certificate work with a final-qualification
reserve and dispatch route seeds in measured, funded worker cohorts. Completed
candidates are retained, unfunded seeds explicitly deferred, and watchdog leases
are not renewed. **296 tests pass initially; 151 overlapping final tests pass**
after the watchdog refinement. Protected PCIe2 control and all six input identities
remain unchanged. This is scheduling repair, not a new connectivity claim.

Active canonical verification: `build/route-finish-budget-suite-20260916`, same
explicit PCIe2 input **1e5755748bcc** and same 600-second cap. Inspect its live
process and journal; do not edit shared scripts, duplicate it, or call it completed
in advance. It will publish only a trustworthy completed/checkpoint result.

A separate 24-case current-source native pair screen finds that ±8 mm transverse
offset clears the tested EPS/ATX T340 pairs at unchanged edge-axis pitch; the ATX
mixed pair clears at ±6 mm. These are **pair-only diagnostics**, not qualified
mating geometry, a complete row, outline fit or permission to change one half.
No dimensions, lands, source placements or 3D transforms changed; EPS/ATX remain
held. Retain `build/copper-curve-next-inputs-20260915.json` and the other holds.

## Latest continuation: exact drill-seat domain (September 16)

Read [exact hole spacing and cell ablations](exact-drill-seat-domain-2026-09-16.md).
Removed a generic 0.85 mm offset-seat halo that discarded legal dogbones before
the existing native drill/assembly/all-layer copper checks. **171 tests and
eight subtests pass**; loaded-native old-halo controls reproduce the defect.
Six-source private replay and the protected historical PCIe2 regression pass
their stated checks. Neither checks nor fixed power geometry were relaxed.

The bounded residual replay finds a PCIe2 **10 -> 9 open** candidate with zero
DRC and all local cells passing. The old solver finds it too, so this is not
attributed to the hole-domain patch. It is diagnostic only until the canonical
`build/exact-hole-residual-followup-20260916` finishes all normal gates. That
explicit follow-up has a 600-second job bound and preserves the original six
sources. Do not edit shared scripts while its process or descendants run.

Four other recorded-cell-removal trials plus three controls close zero gaps;
they confer no production unlock authority. Hub, VHP and PCIe3 remain at their
separate craft/priority holds, and EPS/ATX at coupled interface holds. No new
board is fab-ready and no partial diagnostic is published as a full pass.
Retain `build/copper-curve-next-inputs-20260915.json` until verified completion.

## Latest continuation: exact local refusal cost reduced (September 15, 23:48Z)

Read [local pair-search cost and producer evidence](local-ribbon-refusal-cost-2026-09-15.md).
The shared local solver now stops collecting discarded verbose evidence after
four witnesses when the same exact physical predicates already reject a row.
Native VHP A/B visits 37,834 -> 57,434 ribbon candidates at essentially the same
pair wall time; local solve time falls 35.42 -> 30.70 s. **The pair still fails**:
this is measured search efficiency, not closure or a reason for an unchanged wave.

**285 tests plus two subtests pass.** Six-source old/new private pair replay,
independent native geometry/DRC/connectivity comparison and the historical PCIe2
control show no regression. All source/hierarchy identities are unchanged.
Read `build/ribbon-prefilter-suite-replay-20260915/native-comparison-v3.json`;
earlier comparison versions omitted scalar fields and are superseded. No
diagnostic output was promoted or falsely published as a completed board pass.

Actual hash-bound PCIe2 producer evidence now identifies 64 generated items
across 14 cells; thirteen recorded item sets are unchanged, containing eleven
of the current 60 immutable blockers. Evidence is in
`build/local-cell-producer-lineage-screen-20260915.json`. This still grants
**no unlock authority**; durable complete-cell dependency receipts and qualified
replacement are the next distinct repair. Do not replace the whole baseline
with an older board or unlock tracks merely by group label.

No live cohort remains. Keep `build/copper-curve-next-inputs-20260915.json`,
including Hub ab70's plateau flag and the five other explicit lineages.
Existing mechanical/priority/craft holds remain; no unchanged Hub retry.

## Latest continuation: VHP obstacle-contact ablation rejected (September 15, 23:18Z)

Read [the bounded VHP portal ablation](vhp-portal-contact-ablation-2026-09-15.md).
Baseline, added obstacle-contact seats, and a contact-first diagnostic all
still refuse the current USB pair. Added seats do reach native field checks,
but clear transition fields do not yield complete package fan-ins. No source
geometry, production engine, or selected board lineage changed; do not merge
the prototype or repeat an unchanged full wave. No new board was promoted.

`build/vhp-portal-contact-coverage-20260915/conclusion.json` independently
verifies all six retained source/hierarchy identities, copper/pose rollback of
all four private trials, and unchanged historical PCIe2 control bytes. Workers
have exited; no full cohort is running. The explicit retained input plan stays
`build/copper-curve-next-inputs-20260915.json` with Hub ab70 and its plateau flag.
Other boards keep their distinct holds, not a false all-boards-routing claim.
Next investigate actual paired-fan-in coverage, PCIe2 complete-cell ownership,
PCIe3 terminal ordering, or coupled EPS/ATX fit. No unchanged Hub retry.

## Latest continuation: Hub plateau observed; exact arc guard repaired (September 15, 22:46Z)

Read [curve identity and Hub plateau](copper-curve-identity-and-hub-plateau-2026-09-15.md).
The Hub continuation finished **22:23:20Z**, exact output **ab70d2fca1f5**,
still four hard craft blockers. Its two small C28 moves do not justify another
unchanged pass. All descendants are gone and guards pass. Review
`pass-return-continuation-suite-20260915-hub-standard-rev2-7272998437` is
API-verified and visually inspected, explicitly placement/BLOCKED.

Shared copper signatures/prefix guards now preserve native arc midpoints, not
just chords. Six old-encoder negative controls reproduce the defect; **212
integration tests pass**, six-family native replay preserves source identities,
and the historical PCIe2 regression is unchanged. All current inputs are arc-free:
this is integrity hardening, not improved routing. No new wave is justified by
this guard alone. Durable complete-local-cell ownership is still NOT implemented.

Explicit retained inputs: `build/copper-curve-next-inputs-20260915.json`.
Native evidence: `build/copper-curve-final-suite-replay-20260915/report.json`.
No live cohort at this receipt. Keep the other five lineages and their existing
independent holds. Next advance actual PCIe2 inherited-cell ownership, VHP USB
escape, PCIe3 terminal ordering/reach, or coupled EPS/ATX geometry; do not revert
to another Hub-only distance-tweak loop. Shared scripts may now be edited only
after verifying no newer process has started.

## Latest continuation: Hub blocker reduced; six-board native inventory (September 15, 22:11Z)

The return-orientation full pass finished **22:11:38Z** with guards true and
all workers gone. Hub **6028ba320d41** has **four craft blockers, down from five**:
U3/C2's local return now constructs, but its supply proximity and U7's three
returns still fail. It remains placement/BLOCKED, not routed. Published review
`pass-return-orientation-followup-suite-20260915-hub-standard-rev2-c8632683d9`
is API-verified and visually inspected. See the updated
[return-orientation receipt](return-orientation-feedback-2026-09-15.md).

Fresh parallel six-family native inventory and explicit next inputs:
`build/continued-suite-inventory-20260915/report.json` and `inputs.json`.
Only Hub advances to the verified 6028 source; all five other source identities
are retained. PCIe2 still has ten opens and passing local cells; PCIe3 local
cells pass with its existing priority hold; VHP retains C7 local access and USB
escape debt. EPS/ATX native pad faults reaffirm the coupled-interface hold.
No fabrication or new global-routing result is claimed.

Canonical next live/finished journal:
`build/return-continuation-suite-20260915/suite.json`. It is ONE bounded full
continuation of the improved Hub (24 trials, four workers, 1200 s). Check that
journal and descendants before shared engine edits or dispatch. If hard blocker
count does not improve, do not keep looping on distance-only C28 movements.
Rotate to independent PCIe2 complete-cell ownership, VHP escape, PCIe3 terminal
ordering, or coupled EPS/ATX fit. Preserve all existing dimensions and authority
gates. The unchanged other boards were audited concurrently, not falsely
reported as new routing waves.

## Latest continuation: return-macro orientations (September 15)

Read [return-orientation feedback](return-orientation-feedback-2026-09-15.md).
The rigid-range PCIe3 pass finished **21:34:27Z**, unchanged `400ffdd8635e`,
still 12 critical-route refusals. Its reviewed placement is BLOCKED, not routed.
Do not repeat it. Shared return feedback now tries rigid IC/assigned-bypass
quarter turns before measured reservation exits. 189 tests, six-family native
replay, 537 native Hub pad checks and the historical PCIe2 control pass. Native
Hub probes clear some local refusals but neither passes whole-board admission.

Canonical affected full-pass journal:
`build/return-orientation-followup-suite-20260915/suite.json`.
Check its current state and process tree before edits or dispatch. It uses
explicit current Hub `ce61d1a11de3`, four workers and the usual bounded budget.
Other families retain their distinct ownership/escape/terminal-order/interface
holds; observe or investigate them independently, without duplicating exhausted
cohorts. No fixed bus, schematic, load budget or mating geometry changed.

## Latest continuation: search-domain full pass completed (September 15, 20:58Z)

Read [rigid local-cell rotation](rigid-local-cell-rotation-2026-09-15.md) for
the repaired producer, native fixtures and cross-board evidence. The affected
follow-up journal is `build/rigid-range-followup-suite-20260915/suite.json`;
check its current state before any shared edits or dispatch. The dispatcher
has started after **388 tests**, six-family native replay and the protected
PCIe2 regression passed. Do not launch another copy. After observing this pass,
rotate development back to the independent PCIe2 local-ownership or Hub/VHP
complete-cell access work instead of repeating a PCIe3-only campaign.

The cohort finished 20:58:12Z, with all descendants gone. It restored exact
PCIe3 **400ffdd8635e** and still has 12 critical-route failures: no admitted
board progress. Source/hierarchy/engine guards pass. Its immutable BLOCKED
placement review is published, API-verified and visually inspected:
`pass-search-domain-followup-suite-20260915-pcie-8pin-3port-df32ef18c6`.
Do not rerun this unchanged. The newly reachable rotated Kelvin finalist breaks
C10's bypass geometry (6.31-mm violation): the range generator rotates only
the owner while translating its unrotated follower, and predicts pad rotation
with the opposite sign to KiCad. The shared complete-cell transform is now
implemented, and native replay checks all 568 transformed pad positions.

## Latest continuation: native repair and measured search domain (September 15)

Read [native repair and placement search domain](native-repair-and-placement-search-domain-2026-09-15.md).
Eight certificate-discard loops now use safe native deletion, with repeated
loaded-board worker tests. Measured endpoint moves are bounded by the actual
candidate outline instead of an arbitrary default 6-mm step cap; explicit caps,
fixed followers and all physical/power/route admission remain binding.
377 tests plus 16 subtests passed (13 older Hub-fixture tests unavailable). Six-family
native replay passes source/engine guards, protected PCIe2 regression unchanged.
PCIe3 range proposals increase 26 -> 52 for nine real refusals, not yet closure.

Affected full-pass journal: `build/search-domain-followup-suite-20260915/suite.json`.
Check it and live descendants before shared engine edits or another dispatch.
Started 20:44:02Z, child PID 449107, 1200-second cap. The second round reaches
new >6-mm Kelvin moves; one reduces scoped Kelvin refusals 9 -> 8 but fails craft.
The first operation's 12 -> 11 pair gain still needs post-power acceptance.
No final routing or fabrication improvement is claimed while this pass runs.
Other families retain the documented independent holds. Durable complete-cell
ownership for PCIe2 is still unfinished; no global unlock permission was added.

## Latest continuation: fresh final residuals and ownership screen (September 15, 20:04Z)

Read [final residual evidence](final-residual-evidence-2026-09-15.md).
Implemented source-bound, fresh native final-PCB endpoint surveys; both repair
feedback consumers and the dispatcher prefer these over stale import attempts.
SMD/THT layer-access semantics and a scorer-consistency release gate are tested.
209 tests passed (four opt-in legacy router tests skipped), six-family parallel
native replay/plan screening passed; protected PCIe2 regression is unchanged.
Latest read-only evidence: `build/final-residual-suite-replay-v4-20260915/report.json`.
No new geometry, routed wave, or fab candidate is claimed; no workers remain.

Fresh PCIe2 evidence covers all ten opens. All 60 named immutable track blockers
already exist in its journal-verified placed baseline; 18 have endpoint-neckdown
labels. Generated-unlock eligibility is currently UUID absence from `placed`,
so inherited local copper does not receive that permission. Next investigate
**durable, qualified local-cell ownership across continuations**, not global
unlocking or another unchanged wave. Read the caveats and safe-native-disposal
warning in the linked receipt. The other five families retain independent holds.

## Latest continuation: placement probe coverage completed (September 15, 19:24Z)

Read [placement probe coverage](placement-probe-coverage-2026-09-15.md).
The local-length Hub/VHP cohort finished **18:52:56Z**, neither into routing.
Hub made two 0.05-mm moves but still has five craft failures; VHP is unchanged.
Both completed reviews are verified on the dashboard and visually inspected.

Generic scheduling now separates complete return macros from single-cap moves
and favors untried poses across bounded craft rounds/epochs without caching
admission or excluding retries. 286 tests, six-family native replay and the
protected PCIe2 regression pass. Latest journal is
`build/probe-coverage-followup-suite-20260915/suite.json`, finished **19:24:42Z**:
return probes rose from 1+1 repeated attempt to 4+5, all 24 selected proposals
untried, but final PCB is exact de4a again and **five blockers remain**. The
217.49-s worker and descendants are gone; guards pass; verified review is
`pass-probe-coverage-followup-suite-20260915-hub-standard-rev2-cf17c31f74`.
Do not repeat this cohort unchanged. Other boards retain independent holds.
Read the linked receipt for distinct next work and the need to refresh PCIe2
failure certificates against its final 905f PCB before more owned-escape work.

## Latest continuation: local-length search and Hub/VHP replay (18:40Z)

Read [local-route length search](local-route-length-search-2026-09-15.md).
The prior PCIe3 cohort finished **18:10:41Z**, correctly rejecting all three
post-power craft regressions and restoring exact 400ff. No routing progress;
do not repeat it. A new optional length-aware local/bridge/maze search passed
340 integration tests, 168 final focused tests, six-family native replay and
unchanged historical PCIe2 regression. Counts overlap. Extra fixed-layout
CPU effort up to 65536 steps did not clear Hub/VHP; defaults were not raised.

Newest canonical experiment journal:
`build/local-length-followup-suite-20260915/suite.json`, **Hub and VHP**
concurrently, 1200-second board caps. Its purpose is to test the new shorter-
path choice on placement proposals, not repeat fixed-layout extra effort.
Check live journals/processes before edits or dispatch; do not duplicate it.
If it plateaus, move to coordinated cell seating or EPS/ATX coupled fit.
All source/board and release holds remain unchanged; older live/no-live
statements below are historical.

## Latest continuation: post-power physical admission (September 15, 17:49Z)

Read [priority/power physical boundary](priority-authority-physical-boundary-2026-09-15.md)
first. The probe-lease cohort finished **17:24:11Z**, with 12 -> 11 priority
refusals but a **new local-craft failure**, so do not promote its 6e58 placement
over the explicit 400ff source. Native ablation proves old-vs-rebuilt power
authority, not PCB serialization, caused the craft disagreement. The generic
post-rebuild physical check now joins the existing rollback/alternate-move
transaction. 203 tests plus 16 subtests pass; six-family native local replay
and protected PCIe2 control preserve their gates and hashes.

Newest canonical follow-up journal:
`build/authority-physical-followup-suite-20260915/suite.json`.
Check it and live processes before changing shared engines or launching work;
all older live/no-live claims below are historical. Hub/VHP local access,
EPS/ATX coupled mechanical admission and better PCIe2 input 905f remain held
as documented. After this affected-stage replay, rotate development to those
other generic blocker classes rather than another unchanged PCIe3 retry.

## Latest continuation: coupled local-cell ordering and geometry

The frozen-via cohort finished **16:09:13Z**, all workers gone and guards
passed. PCIe2 remains **0 DRC / 10 opens**, now 386 vias / 1631.710 mm: four
more vias and 58.859 mm more length without connectivity improvement. Review
SHA c6debcd28b2e is published and verified, but **retain explicit 905f as the
better continuation input**; do not automatically promote a newer worse route.

Read `coupled-cell-search-2026-09-15.md` for the implemented next generic slice:
bounded process-qualified via choices and whole-cell supply/return ordering,
transactional copper/group rollback, and tentative-vs-inherited provenance.
957 broad tests, 382 follow-up integration tests and unchanged protected PCIe2
control. Native six-family replay preserves source/hierarchy and guard holds.
PCIe3's last local craft failure clears; its actual local pre-route transaction
passes **0 DRC / 254 -> 175 opens**, not a whole-board routing result.

The canonical cohort `build/coupled-cell-followup-suite-20260915/suite.json`
**finished 16:43:45Z**, all descendants gone, all source/hierarchy/engine guards
passed. PCIe3 remains byte-identical **400ffdd8635e** with craft/local-cell gates
passing, but **12 important-route failures stop main routing**: nine Kelvin
reach, two pair routes, one USB backtrack. The bounded priority and power
replans accepted no move. Its immutable BLOCKED placement preview is verified
on the dashboard and Windows mirror; exact ID and image hash are linked above.

No campaign is live as of 16:46Z. Retain the six explicit current inputs in
`build/locked-reconcile-inputs-20260915.json`; do not seed from native diagnostic
copies or repeat unchanged exhausted waves. Next generic search gap: Kelvin
range correction proposals skip every witness requiring more than the default
6 mm move budget, while some current deficits exceed 11 mm. Audit the reach
authority and qualify bounded coordinated relocation/progressive repair,
without weakening frozen buses or simply relaxing the 9 mm gate. Hub's five
failures, VHP's local/critical escape and EPS/ATX interface holds remain.

**Historical 16:41Z:** dispatched **16:39:06Z**, PCIe3 PID **357064**, parent session
**85297**. Intake passed; placement now runs `priority-measure` after clearing
the local-cell blocker. Main routing has not started yet. 68 GiB free. No
shared script edits until the cohort and descendants finish. The linked
document also records the unchanged PCIe2 geometry holds and a generic
dogbone-angle producer inconsistency to qualify in a later slice.

## Latest continuation: frozen via replay identity

The cleanup follow-up finished **15:14:11Z** with no eligible route: both
PCIe2 seeds stopped before routing because existing frozen field vias collided
with themselves in the reseater. Native forensics proves this also caused
56 of the last 61 extra vias. Read `frozen-via-replay-identity-2026-09-15.md`.

Exact existing-instance reuse is implemented and tested: **947 tests pass**,
plus 18 focused tests including the additional producer-boundary case. Three
native family field replays are idempotent; two unmocked full PCIe2 prefix
compiles pass exact admission and produce byte-identical 905f boards. Six
family source/hierarchy checks and the protected PCIe2 control are unchanged.
No surplus vias were deleted and no new routed/fab result is claimed.

Next affected-stage cohort: `build/frozen-via-followup-suite-20260915/suite.json`,
from explicit `build/locked-reconcile-inputs-20260915.json`. Inspect this journal
and live descendants before editing engines or starting another wave.
Hub/PCIe3 keep their five/one local-craft failures, VHP its critical escape
hold, EPS/ATX their coupled-interface geometry holds. Do not repeat those
unchanged runs. All launch/PID observations below are historical.

**15:54Z:** current cohort started **15:46:32Z**, PCIe2 PID **328958**, parent
session **75545**. Placement/preflight pass, former local-power-prefix failure
now passes with exact SHA 905f, 0 DRC / 10 opens. First backend pass completed;
import/cleanup is active. Keep shared engines fixed until all descendants exit.
Next read-only findings are in `local-cell-ordering-investigation-2026-09-15.md`:
PCIe3's tentative supply track blocks its own later ground return. A scoped
return-first / declared-minimum POFV experiment completes the cell, but has
not passed whole-board pipeline admission. Hub remains unchanged.

## Latest continuation: downstream cleanup ownership and provenance

The locked-connectivity cohort finished **14:37:54Z**, all descendants gone
and input/engine guards passed. Selected PCIe2 **seed 0** is **0 DRC / 10
opens**, down from 12, SHA 905f961c6257. The last log's 12-open result is seed 1,
not the winner. Hub/PCIe3 remain at five/one craft failures. No fab admission.

Read `locked-copper-cleanup-provenance-2026-09-15.md` for exact metrics,
verified final reviews and the next generic repair: downstream cleanup still
duplicated the weak ownership test and layer/net-blind echo matching. Native
connectivity, full exact echo identity and source provenance now govern it.
**828 tests pass**, follow-up 252 integration tests pass, four native cleanup
replays are unchanged; EPS/ATX refuse their unadmitted interface authority.
The protected PCIe2 control is unchanged. No repeated Hub/PCIe3 placement wave.

Next bounded affected-stage cohort:
`build/locked-reconcile-followup-suite-20260915/suite.json`, explicit
`build/locked-reconcile-inputs-20260915.json`, from the 905f current winner.
Inspect live processes before editing shared scripts or dispatching anything.
All older live/PID observations below are historical.

Dispatched **15:10:23Z**, PCIe2 PID **318752**, parent session **12464**;
exact input 905f961c6257..., placement passed 31.6 s, now route preflight.
68 GiB free. Keep engines fixed until this job and descendants finish.

## Latest continuation: native whole-net connectivity admission

The frozen-domain cohort finished **13:39:42Z**. Hub retained two real moves,
but five local-craft failures remain; PCIe3 retained its one-failure placement.
Read `locked-net-connectivity-admission-2026-09-15.md` for a proved generic
router exclusion defect: separate locked stubs were considered a complete net.
Current PCIe2 +5VSB and I2C_SDA islands were therefore skipped by completion.
The native locked-subgraph and stale-claim boundary fixes pass **816 tests**,
six-family replay, and unchanged protected PCIe2 regression/control probes.

Next bounded three-board canonical replay:
`build/locked-connectivity-followup-suite-20260915/suite.json`, explicit
`build/locked-connectivity-inputs-20260915.json`. Inspect its current journal
and processes; do not edit shared engines or duplicate live jobs. VHP and
EPS/ATX retain their separate escape/mechanical holds. No new fab admission.
Older launch/PID paragraphs below are historical.

**14:21Z observation:** this cohort started **14:15:31Z** (parent session
67571). Hub/PCIe3 completed at five/one craft failures; Hub retained two more
small moves, PCIe3 unchanged. **PCIe2 PID 271059 is routing**, after placement
29.05 s and preflight 147.74 s. Its actual DSN now retains all +5VSB/I2C_SDA
terminals. Do not edit shared scripts until it and descendants finish.
The linked document records verified previews and a read-only next-slice
finding: 36/104 coarse demands replan already complete locked copper.

## Latest continuation: frozen placement search domain

`search-budget-followup-suite-20260915` finished **13:06:09Z**. PCIe3 retained
a verified repair (SHA 400ffdd8635e...), reducing local-access failures two
to one without the scoring drift; Hub rolled incompatible moves back.
The next generic fix carries the unchanged frozen-power movement contract
into proposal selection and worker checks. **555 tests pass**; six-family
native replay and the protected PCIe2 control pass their stated checks.

Read `frozen-placement-search-domain-2026-09-15.md` for exact evidence and
verified current dashboard previews. The next bounded concurrent cohort is
`build/frozen-domain-followup-suite-20260915/suite.json`, using explicit
`build/frozen-domain-inputs-20260915.json`. No new board is routed or released;
EPS/ATX mechanical holds remain. Older launch/PID sections are historical.

## Latest continuation: placement certificate parity

See `placement-certificate-parity-2026-09-15.md` before acting on older launch
records. The return-seat cohort is finished. A retained PCIe3 reproduction
proved a 0.75-s search cutoff changed the admission key on identical geometry;
generic bounded-work and evidence-retention repairs passed 540 tests and
seven-artifact fast/full/fast native parity. The protected PCIe2 control is
unchanged. Follow `build/search-budget-followup-suite-20260915/suite.json`
for the bounded concurrent Hub/PCIe3 follow-up. No new board is released,
and EPS/ATX mechanical holds remain intact.

## Latest continuation: sampled return evidence and actual terminal ownership

`local-return-feedback-suite-20260915` **finished 11:43:09Z**; its PIDs and
descendants are gone. PCIe3 retains a real generic placement repair (SHA
`13bce847b16a...`), clearing one local-return obstruction. Two remain. Hub
rolls incompatible proposals back to its exact b7cc input and zero frozen
snapshot mismatches. Neither has an admitted route/fab result.

The next generic slice retains bounded actual failed via-seat geometry,
fairly distributes exit proposals across owners, and distinguishes positively
declared fixed current terminals from unowned consumers using exact native
pad/layer contact proofs. Native diagnostic PCIe3 trial reduces two decoupler
failures to one with zero foreign track/via incursions; it is **not promoted**
or used as a pipeline seed. **450 tests pass**, and historical PCIe2 hash,
regression/all probes remain exact. Core 68 modules/zero violations;
380 broader runtime findings remain.

[Full evidence, negative trials, reviews and remaining blockers](sampled-return-seats-and-consumer-ownership-2026-09-15.md).
**Active canonical cohort** dispatched **12:20:44Z**:
`build/return-seat-feedback-suite-20260915/suite.json`, Hub PID **186583** /
PCIe3 PID **186582**, parent session **43233**. Explicit current input plan:
`build/return-seat-inputs-20260915.json`; harness
`tmp/return_seat_followup_20260915.py`. 1800-s board/2100-s parent bounds,
two workers per board, 16-GiB free floor (68 GiB free). Keep shared engines
fixed until all descendants finish. Do not restart unchanged VHP/PCIe2 waves
or route mechanically held EPS/ATX. Older active paragraphs are historical.

**12:23Z observation:** PCIe3 PID 186582 has exited after 63.83 s; placement
failed at 52.263 s with `placement craft diagnostic-mode admission drift` in
`_certify_craft_incumbent` (cached expected one local craft failure, fresh
certification two). Source/hierarchy/engine guards pass. No candidate was
promoted. Hub PID **186583 remains live**, in round two. Do not edit shared
code until Hub and descendants finish. Next investigate exact fast/full
certificate parity and retain both artifacts on failure; the current
TemporaryDirectory removes the failing certification board. Timed local
search is a hypothesis, not a proved cause. Do not restart PCIe3 identically.

## Latest continuation: exhausted local returns now enter placement repair

The prior `frozen-pi-followup-suite-20260915` **finished 11:08:09Z**. Its PIDs
121771/121772 and descendants are gone. Hub and PCIe3 both stopped at placement;
there is no new routed output. PCIe3 incorrectly skipped craft repair because
already-exhausted ground-return failures were deferred to routing. Hub's two
local proposals could not synchronize frozen power, so its b363 proposal is
not a qualified advancement and must not become the continuation input.

Three generic changes now route exhausted native certificates back to
placement, generate bounded axis exits for via/power conflicts with rigid
owned-decoupler cells, and roll back the entire placement-authority family
when frozen-power synchronization is refused. Native six-family replay gives
18 Hub / eight PCIe3 proposals; PCIe2 local PI passes. Historical PCIe2 hash,
regression and every probe remain unchanged. Core audit: 68 modules / zero
violations; 380 broader runtime findings remain.

[Evidence, scope and known remaining blockers](local-return-feedback-and-frozen-commit-2026-09-15.md).
Next harness: `tmp/local_return_followup_20260915.py`. It deliberately retains
the exact prior input plan, not the failed Hub proposal. **373 tests passed**
in 94.93 s. The new cohort was dispatched **11:39:42Z**, journal
`build/local-return-feedback-suite-20260915/suite.json`, Hub PID **153173** /
PCIe3 PID **153174**, both running. Session 54378; 1800-s board bounds,
2100-s parent bound, 16-GiB free floor (68 GiB free). Do not edit shared
engines or duplicate jobs while these or their descendants remain live.
Older active-cohort paragraphs below are historical, not live status.

## Latest continuation: full-cell frozen authority now enforced before routing

`build/qualified-escape-suite-20260915/suite.json` **completed 10:26:17Z**;
its former PIDs 95993/95994 and descendants are gone. Sources/hierarchy/engine
guards pass. Hub passed placement and route preflight, but both route seeds
stopped at the local-power-prefix barrier. Seven track-incursion reports were
a layer-mapping bug (In3.Cu incorrectly mapped to F.Cu); three GND vias really
crossed the inner power region. VHP retained its identical input and one USB
refusal. There is no new eligible routed output, and no fab admission.

Generic fixes now resolve all enabled copper layers without a top-layer
fallback, enforce exact full frozen polygons alongside clipped planning hints,
and keep committed power visible during both local-PI generation and placement
qualification. The retained failure now correctly reports **0 tracks / 3 vias**.
Native generation refuses and rolls back the four affected Hub cells in 5.15 s;
those constraints are now visible to placement instead of being discovered
after a long pass. No copper geometry or design budget was changed.

**486 tests plus three subtests pass**; separate checker suite 83 pass / one
skip. Native cross-board audit preserves all sources, reports three PCIe3
local-access failures and passing PCIe2 local PI, and retains the existing
EPS/ATX holds. Historical PCIe2 SHA/regression/all probes are unchanged. Core
audit has 67 modules / zero violations; 380 runtime findings remain.
[Forensics, repairs, exact evidence and caveats](frozen-pi-layer-authority-2026-09-15.md).

**Active canonical Hub + PCIe3 cohort**, started **11:00:31Z**:
`build/frozen-pi-followup-suite-20260915/suite.json`, Hub PID **121771**, PCIe3
PID **121772**. Both journals and live processes were checked. Harness:
`tmp/frozen_pi_followup_20260915.py`, bounded placement repair under the new
shared gate. Input plan: `build/frozen-pi-followup-inputs-20260915.json`.
Hub is selected explicitly
from its hash-verified completed placement stage, not from an absent routed
winner. Do not restart VHP's identical exhausted USB wave or the mechanically
held EPS/ATX boards. Two workers per board, 1800-s board bounds, 1200-s priority
allowance, explicit 480-s pair effort, 2100-s parent process-group bound and
16-GiB free floor (68 GiB free at dispatch). Standard completed-stage/pass
review publication remains enabled. Do not edit shared scripts or duplicate
the cohort while either job or any descendant remains. Older sections below
are historical, not evidence that an old campaign is still running.

## Latest continuation: local/global escape handoff repaired and bound replay passes

The previous canonical two-board cohort **completed 09:27:02Z**. Its former
PIDs 69367/69368 and all descendants are gone. Both saved changed placements
pass pads/courtyards/craft/constraints and retain source/hierarchy/engine guards.
Hub accepted its power repair and reached zero pair refusals; one critical
global edge remained. VHP priority pair refusals fell **2 -> 1**, leaving USB.
Current saved output SHAs: Hub `a2861bb5d1140e0c7785b844235da4395d1085eae3921e1b4043f7173ce89c8c`;
VHP `3af185f38201c8f9e0b08a3f85204cc40b61e4998fe588b7d82902a3ce32293a`.

Generic repair: compose independently proved local escape edges with alternative
real global terminals, then renegotiate the full workload once. Exact endpoint
identity, unchanged obstacles/layers and strict no-lost-connection admission
are mandatory. Native Hub A/B with its **actual frozen-pour authority** changes
critical global failures **1 -> 0**, without editing copper or placement. This
is planning progress, not fewer physical opens or fab admission. All five
available native adapters replay; ATX fails closed on its missing power-state
sidecar. Protected historical PCIe2 SHA/regression/all probes remain exact.
Implementation, test evidence and limitations:
[Qualified local/global escape](qualified-local-global-escape-2026-09-15.md).

Latest completed-pass gallery (visually checked):
`C:/Users/Admin/Documents/CEC-Board-Reviews/pair-pad-guard-suite-20260915/all-boards-09f5ecfca51d22b1.png`.
[Hub](http://localhost:8090/?id=pass-pair-pad-guard-suite-20260915-hub-standard-rev2-66d0bdd1a7)
and [VHP](http://localhost:8090/?id=pass-pair-pad-guard-suite-20260915-12vhpwr-standard-12787be458)
are explicitly BLOCKED placements, not newly routed/fab boards. Windows-facing
dashboard `/api/archive` was verified HTTP 200 this turn.

**Active canonical two-board follow-up**, started **10:05:19Z**:
`build/qualified-escape-suite-20260915/suite.json`, VHP PID 95993 / Hub PID
95994. Both start from the exact completed outputs named above, selected by
`cec_board_suite.continuation_inputs`, not diagnostic branches. Full current
source/lineage plan: `build/qualified-escape-suite-inputs-20260915.json`.
**10:22Z observation:** Hub placement completed successfully in **888.025 s**
and entered `route_preflight` at **10:21:12Z**. Its canonical placement now
passes pads, courtyards, craft, mechanical/placement constraints and priority
feasibility. Pair refusals, Kelvin refusals, route-quality refusals and critical
global failures are all zero. The generic escape retry was used on both
`+5V_SYS` and `PSU_5V_KVM`; this is not a one-net waiver. Changed output SHA:
`b7cc3990f31341ab71b73fcf0131a20831e38cd1ffaf64dff0ee23dd406d54da`.

The completed placement was journal/hash/source/engine verified, published and
visually inspected. Its native partial-board score is **12 DRC / 242 opens**;
this is admission progress, not a new reduction in physical opens. Review:
[Hub admitted placement](http://localhost:8090/?id=qualified-escape-suite-20260915-hub-standard-rev2-placement-b7cc3990f313).
Windows image:
`C:/Users/Admin/Documents/CEC-Board-Reviews/qualified-escape-suite-20260915-hub-standard-rev2-placement-b7cc3990f313/render.png`.
Dashboard archive presence was confirmed from Windows. Receipt lives in
`build/qualified-escape-suite-20260915/completed-stage-reviews.json`.

VHP remains in bounded priority repair for its remaining USB dependency.
Both main processes remain live; no completed detailed route is claimed.
Keep shared scripts fixed until both jobs AND their descendants end.

Dispatch harness `tmp/qualified_escape_cohort_20260915.py` required the bound
native proof, **230 passing integrated tests** and unchanged PCIe2 control.
Core anti-overfit: 66 modules / zero violations; 380 runtime findings remain.
Bounds: two workers per board, 1800 s each, 1200-s priority allowance, explicit
480-s pair effort, 16-GiB free floor, 2100-s parent hard bound. Standard
hash-verified completed-stage/pass publication remains enabled. Do not duplicate
this campaign or call the superseded jobs below active.

While these run, inspect other-board evidence read-only. PCIe3 still needs joint
Kelvin/current-corridor repair, EPS/ATX retain coupled mating gates (ATX also
lacks the required sibling power state), and PCIe2 retains its protected
incumbent. Do not restart those unchanged failures as a claim of concurrency.

## Latest continuation: canonical handoff passes; portal pad guard implemented

VHP canonical follow-up **completed 08:44:09Z**, elapsed 1674.755 s. No live
descendants remained before shared edits. The improved output is retained,
SHA `722d7a6e4e1754e25b755ac9b8625b41f4070f6294384551b2f651038bdb23d6`.
The actual outer checkpoint now accepts the proof-bound replacement without
missing protected copper. Pads/courts/craft/constraints pass; **two priority
refusals still block placement admission and routing**. Source/hierarchy and
engine guards pass. The journal-verified changed placement was published and
visually inspected; no fabrication gain is claimed.

Between runs, two generic repairs were implemented: exact opposite-member pad
checks at portal orientation selection, bounded collision feedback and final
post-cleanup checks; and explicit tested/untested broad-removal diagnostics.
The latter supersedes the incorrect PCIe3 conclusion below. **1,318 tests plus
79 subtests pass**, four skipped; nine generalization tests also pass. All 275
existing source pair segments and 24 final VHP pair segments pass the new
native guard; the retained Hub short is detected. PCIe2 control SHA/probes are
unchanged. Core anti-overfit passes 65 modules; whole-runtime legacy findings
remain. Detailed implementation and limits:
[Coupled pad authority and counterfactual evidence](coupled-pad-authority-and-counterfactual-evidence-2026-09-15.md).

The Hub replay **completed in 124.462 s and admitted the full CAN prefix**:
6/6 edges, independent pair physics and all parent-copper/placement proofs
pass. Opens 254 -> 242; comparative DRC remains 12 -> 12, with no new
structural DRC identity. The earlier short and mask bridge are absent. This
is not whole-board/fab admission. Sources, retained input and engine remained
unchanged. Verified, visually inspected preview:
[Hub qualified CAN prefix](http://localhost:8090/?id=20260915-hub-padguard-6edge-qualified-prefix).
SHA `d59a12e1c5961c1b3dc5e5668b00de4eefcc6e39be930c86b99b65cb1b124aac`.

**Active canonical two-board follow-up:**
`build/pair-pad-guard-suite-20260915/suite.json`, started **08:57:52Z**, Hub PID
69367, VHP PID 69368. Both inputs come from explicit completed journals via
`cec_board_suite.continuation_inputs`, not mtime or older roots. VHP starts
from the newly retained `722d7a6e...` output; Hub from its unchanged canonical
`032f2702...` output, NOT the diagnostic branch. Full source/lineage plan:
`build/padguard-suite-inputs-20260915.json`. The bounded benchmark effort is
480 s per pair for both families, two workers each, 1800-s board bounds,
1200-s priority operation bounds and 16-GiB free floor. This is an explicit
effort experiment, not a permanent Hub-specific rule. Shared scripts remain
fixed until both jobs and their descendants finish. Publish each completed
stage/pass honestly and do not duplicate this campaign.

PCIe3 needs joint Kelvin/current-
corridor closure using its positive full-width cut witness. EPS/ATX coupled
mating gates remain held, and PCIe2's incumbent remains protected.

## Latest continuation: ownership transition implemented and replayed

The stale-owner repair below is now implemented generically as a proof-bound
`.priority-replacements.json` artifact record, shared by signal and power-terminal
repair. Copy, snapshot/rollback, source signatures and evidence-cache identities
carry it with the board. The original owner and final copper/pair guards remain
intact. **1,132 tests plus 38 subtests pass**. Native retained-case replay now
passes the previously failing outer consumer without changing accepted copper;
a 1 µm protected-power edit remains rejected. All six current source families
remain exact, and historical PCIe2 SHA/regression/all probes are unchanged.
See [implementation, evidence and limits](priority-replacement-ownership-receipt-2026-09-15.md).

The prior cohort and all native test descendants are complete. **Active VHP
canonical follow-up**, started 08:14:38Z, board PID 47233:
`build/priority-receipt-suite-20260915/suite.json`. It checks the affected
producer-to-checkpoint chain. Check journal AND processes before duplicate
dispatch or shared engine edits.

**Completed bounded Hub diagnostic**, started 08:20:38Z, former PID 50085:
`build/hub-budget-probe-20260915-final/report.json`. It replays one exact retained
post-power construction input with 480 s instead of 240 s pair effort, keeping
all 514 frozen pour reservations and every native acceptance gate. It has a
630 s operation allowance / 660 s hard process-group bound and cannot promote
a board. It completed in **126.47 s**: the native local-first order constructed
**6/6 CAN tree edges**, versus 1/6 at the prior effort. Pair physics, full CAN
connectivity, parent copper, placements, source hierarchy and engine signature
all pass. The whole candidate remains **rejected**: the pipeline's comparative
native electrical score rises from 12 to 14 DRC, with opens 254 to 242. New
identities are one short and one mask bridge between a generated CAN_L track
and J2 pad 3 CAN_H. Full raw CLI DRC also reports existing broader fabrication
and assembly issues; the comparative score is not complete fab qualification.

Read-only `short-forensic.json` confirms the existing `_partner_pads_clear`
helper rejects this final segment at the unchanged 0.2 mm clearance. Thus the
helper can detect the conflict, but this route path or a later transform did
not enforce it on the final geometry. That exact producer/transform boundary
is **not yet root-caused or repaired**. This is the next Hub generic guard-
coverage/regression target, alongside funding meaningful escape-search slices;
do not simply increase every wave's budget or manually edit this track.

Published and visually inspected partial diagnostic (not an admitted board):
[Hub six-edge diagnostic](http://localhost:8090/?id=20260915-hub-budget-probe-6edge-rejected).
Image: `C:/Users/Admin/Documents/CEC-Board-Reviews/20260915-hub-budget-probe-6edge-rejected/render.png`.
Board SHA `487a5d5d0a8991904e934a7ce35dca0eff533d1ef0f062cf20b579a4a6e8bd46`.

This was an effort ablation, not an identical failed full-wave retry.
The first harness invocation failed before native construction because its
signature list included an absent optional sidecar; final harness filters
existing files and uses a fresh directory. Do not edit shared scripts while
the VHP run or its descendants remain. Hub probe descendants were checked gone.

### Important correction to PCIe3 diagnosis

The earlier claim that removing every movable obstacle failed was **not
supported**. `_corridor_relief_evidence` skips broad removal checks once a
small cut succeeds, but serializes the unperformed checks as `false`. The
actual retained PCIe3 failure contains a successful, full-required-width
6.311234-mm removal witness for U20, not a narrower-path exception. Its two
proposals moved U20/C20 for Kelvin range but still obstructed that corridor.
`wide_relief_sets` means larger owner cardinality, NOT greater copper width.

Repository consumers use the positive `relief_sets`/`wide_relief_sets` witnesses;
search found no automatic consumer of the two ambiguous boolean fields. This
is a real diagnostic/reporting defect and an incorrect interpretation, not
evidence that the router knowingly accepted bad copper. **Next generic slice:**
explicit tested/pass/fail/not-tested counterfactual evidence, synthetic tests
for skipped/successful/failed broad searches, and review of any output summaries.
Then jointly satisfy the positive current-corridor witness and Kelvin cell
range; do not assume fixed terminals make the case impossible.

Bounded failure digest (no geometry changes):
`build/priority-receipt-suite-20260915/other-board-blockers.json`.
The digest uses `ordinary_relief_sets` and `larger_cardinality_relief_count`;
an earlier inspection-harness label incorrectly implied differing widths and
has been corrected without changing retained native evidence.
The two Hub native orders stop at J2--J3 and J6C--U2, with budget-limited escape
searches; three alternate layered trees also refuse. Counted nested refusal
messages may repeat the same evidence and are NOT unique geometric failures.

EPS/ATX mating gates and PCIe2 incumbent remain held. No new final board or fab
admission is claimed by the retained replay alone.

## Latest continuation: accepted replacement rejected by stale outer ownership

The corrected three-board cohort **completed at 07:33:52Z**. Journals and
processes confirm no live cohort descendants remain. VHP elapsed 1253.104 s,
Hub 681.836 s, PCIe3 238.217 s. Every published output equals its input;
source/hierarchy and engine guards pass. No final placement or routing gain is
claimed. The VHP intermediate repair really was accepted, but the parent then
raised at `checkpoint_authored_prefix`: its original exact-copper prefix still
required the replaced CAN geometry (18 H / 14 L primitives missing), even
though the new pair remained connected and independently physics-qualified.
This is stale **geometry ownership**, not merely a count or UUID mismatch.

Next implement the generic proof-bound ownership transition across this
consumer boundary; do NOT recapture the entire board or skip the final guard.
The receipt must bind the original contract, explicitly released qualified
pair closure, preserved power/other-pair/return copper, and actual accepted
replacement artifact. Adoption and rollback must remain atomic with the board
payload, including subsequent mechanical finishers and outer-round retries.
Both priority-route replan and power-terminal repair entrypoints need the same
mechanism. Add missing/stale/rejected/foreign receipt and changed-power native
regressions, replay the retained failing consumer, and check historical PCIe2
before another canonical cohort. No such transition fix has been implemented
yet; the original guard still fails closed.

Exact accepted diagnostic (not source authority):
`build/qualified-topology-suite-20260915-final/12vhpwr-standard/02-placement/operation-priority-power-replan-e_q7b9x3/candidate/power-replan-finalists/finalist-zx856g88`.
Its enclosing report has the measured winner, typed release evidence and
complete reconstruction proof. The outer failure is journaled in
`12vhpwr-standard/pipeline-state.json` / `pipeline.log` under that same suite.
Final previews: `all-boards-ddbc194fa1f081fb.png` in the suite and Windows review
directory; all are honestly BLOCKED placements, not new routed/fab boards.
Do not rerun this unchanged cohort. Hub 1/6-tree and PCIe3 reserved-current-
territory root causes below remain separate follow-up targets; EPS/ATX mating
gates and protected PCIe2 control remain held.

## Latest continuation: qualified topology selection and native lifetime

The retained VHP CAN_INT replay now passes independent critical-prefix proof:
coupling **33.3% to 66.7%**, skew **3.876134 to 3.034187 mm**, four fewer opens
and no added DRC. The source, placements and parent copper remain unchanged;
this is NOT whole-board/fab admission. Selection now runs the existing full
qualification before stopping at a connected topology, allowing the next
bounded order to succeed. A loaded-copper stress test also exposed unsafe
Python-owned disposal. All 16 precision cleanup sites and temporary-prefix
restoration now use the existing native-disposal helper, with loaded-object
regression coverage. **959 tests and 33 subtests pass**. Native six-board roundtrips preserve 1,411 copper items;
historical PCIe2 SHA/regression/all probes remain identical. See
[the exact evidence, limits and cancellation record](qualified-topology-selection-and-native-lifetime-2026-09-15.md).

`build/qualified-topology-suite-20260915/suite.json` is **complete, not live**:
Hub/VHP intentionally stopped for the native lifetime fix; PCIe3 completed
blocked. Coordinator finished 07:04:16Z and all descendants were checked gone
before shared edits. Final corrected retained replay also completed (38.514 s,
proof passes).

**Completed corrected cohort:** `build/qualified-topology-suite-20260915-final/suite.json`,
started **07:11:50Z**, VHP PID 18713 / Hub PID 18714 / PCIe3 PID 18715,
three jobs / two workers per board, unchanged 1200-s priority and 1800-s board
bounds, 16-GiB free floor. Finished 07:33:52Z; those PIDs are no longer live.
Check journal AND processes before any new dispatch. Immutable previews published
as each pass completed. EPS/ATX mating gates and historical PCIe2 control
remain held; no new fabrication qualification is claimed.

**07:29 continuation check:** Hub and PCIe3 have finished blocked, outputs
identical to inputs and source/engine guards true (681.836 s / 238.217 s).
Their immutable body-free previews were inspected; no route gain is claimed.
VHP is still live. Its canonical `operation-priority-power-replan-e_q7b9x3`
checkpoint now has `current_trial.priority_dependency_rebuild.ok=true`,
`reason=pair_dependency_rebuilt`, physical and post-authority physical checks
true. The native CAN_INT checkpoint passes independent physics and preserves
parent copper: 66.7% whole-pair coverage, 3.034187-mm skew, 3 DRC / 224 opens
versus 3 / 228 before. Full candidate measurement remains pending; do not
promote the branch checkpoint as the board winner. The 97.1% worker log refers
to a local portal ribbon, NOT whole-pair coverage.

Next root-cause targets after this cohort ends: Hub's two physical-valid
replacement trials both stop at 1/6 CAN tree edges. PCIe3's two offers fail
`power_body_clearance` because exact derived current territory cannot route
`/SENSEC1_HI`, **not** because a body-collision row was found (that list is
empty). Trace the reserved-copper/terminal-field path obstruction rather than
blind component reseating or another unchanged wave. No shared code was
changed during this live check.

**Same-check update:** the VHP power-replan worker has now completed (293.365 s)
with `changed=true`, `accepted_count=1`, and
`stop_reason=power_replan_candidate_accepted`. Full trial reason:
`strict_post_power_authority_improvement`; rebuild and physical checks pass.
The resulting priority evidence still has **two critical-route refusals**, so
this is an accepted intermediate repair, not complete placement/routing or
fabrication admission. Parent PID 18713 continues subsequent placement checks.
Read the final report in the above operation directory; the earlier pending
checkpoint status is superseded by this completed worker result.

## Latest continuation: retained support before menu truncation

The PCIe3 ribbon cohort and extra-link diagnostic completed without an
admitted board. Both extra VHP placements passed physical checks and built
2/2 pair-tree edges, but failed final coupling. The producer's early beam
cutoff discarded additional supported candidates. A generic bounded ordered
selector now applies the necessary retained-copper predicate before the joint
menu cap. Native replay: **2 → 10** supported offers, same 32-slot cap,
256-check bound and 26 power anchors fixed. 352 tests / 18 subtests pass;
historical PCIe2 SHA/regression/all probes unchanged. See
[the implemented slice and exact limitations](retained-support-before-menu-truncation-2026-09-15.md).

**Completed canonical follow-up:** `build/supported-menu-suite-20260915/suite.json`,
started 2026-09-15T06:09:17Z and finished 06:27:48Z, VHP elapsed 1063.912 s.
No admitted output; hashes unchanged. The supported menu is wired through:
333 joint choices, 256 checked, 10 retained; later full physical/reconstruction
gates still refuse both funded offers. Check journal AND processes before
dispatch or shared-script edits; never duplicate it. Earlier octilinear
PCIe3 and link-support diagnostic jobs are complete. Hub/PCIe3 have no
applicable source-owned two-link group, so their unchanged waves are not
repeated for this selector slice. EPS/ATX mating gates and PCIe2 control hold.
Next examine whole-pair coupling failure propagation and shared-corridor
construction, not a relaxed gate or an endless rerun of the same routes.

## Latest continuation: correlated octilinear ribbon proposals

The cumulative three-board cohort completed with no changed/admitted output.
The new generic ribbon fallback constructs shared nominal-pitch trunks and
45-degree fan-in, avoiding the old generator's arbitrary-angle candidates.
316 tests / 18 subtests pass; protected PCIe2 SHA/regression/probes unchanged.
Six-board native-contact audit produces candidates for PCIe2/PCIe3; the exact
VHP retained case is unchanged, so no closure gain is claimed for it. See
[the implementation and native evidence](octilinear-pair-ribbons-and-supported-menu-audit-2026-09-15.md).

**Follow-ups:** canonical PCIe3 in `build/octilinear-ribbon-suite-20260915/suite.json`
and bounded VHP diagnostic in `build/link-support-replay-20260915/`.
Both now complete: PCIe3 cohort started 2026-09-15T05:40:46Z, coordinator
3285778 / board 3285780, finished 05:44:52Z; diagnostic parent 3286094 /
native worker 3286095 also finished, with no admitted output.
The latter tests two existing placement offers hidden below early menu
truncation: native screening found 2 survivors in the first 32, 10 in the
first 256. This is diagnostic-only; no production menu/acceptance relaxation
or source nudge. Check both journals AND processes before shared script
edits or duplicate dispatch. All earlier cumulative/owned-anchor/ribbon
retained-case jobs are complete. EPS/ATX mating gates and PCIe2 control remain.

## Latest continuation: cumulative pair-escape objective

The owned-anchor cohort completed without a new admitted board. A retained
native 12VHPWR case exposed compounded per-leg mismatch: the generic joint
escape objective now includes already-constructed signed copper length.
The replay improves whole-pair skew from 4.450497 to 3.876134 mm (4.0-mm
limit unchanged), then correctly rejects insufficient coupling. Post-solve
menu auditing found no coupled choice among the last branch's 35 legal
combinations; next address correlated candidate generation, not a relaxed
gate or another cosmetic score weight. See
[the repair, tests and native evidence](cumulative-pair-escape-skew-2026-09-15.md).

269 tests / 18 subtests pass; historical PCIe2 SHA/regression/all probes
unchanged; six native source families / 16 pairs checked without mutations.
**Completed canonical follow-up:** `build/cumulative-escape-suite-20260915/suite.json`,
started 2026-09-15T05:06:01Z, coordinator PID 3261625; initial board PIDs
3261629 (12VHPWR), 3261630 (Hub), 3261631 (PCIe3); finished
2026-09-15T05:24:41Z with no new admitted board.
Hub, 12VHPWR and PCIe3 ran concurrently. Check this journal AND live processes
before launch or shared script edits; do not duplicate the cohort. EPS/ATX
remain at the paired mating gate, PCIe2 at 0 DRC / 12 opens in its latest
partial route. No unchanged PCIe2/EPS/ATX routing campaign is repeated.
All `owned-anchor-suite` and retained diagnostic jobs are complete.

## Latest continuation: owned signal-anchor replacement handoff

The probe-refill cohort completed: PCIe3 measured seven probes instead of four,
12VHPWR four instead of two; neither admitted a new board. Native failure
evidence showed that the early frozen-anchor screen discarded owned signal
placement proposals before they could reach atomic pair reconstruction.
Complete attachment witnesses, typed bounded replacement offers and an early
retained-power/return check now connect those stages. Six-board native audit:
44 anchors classified; all 26 power anchors kept fixed. See
[the generic handoff and native evidence](owned-anchor-replacement-handoff-2026-09-15.md).

The bounded `owned-anchor-context-replay-20260915` diagnostic completed:
one proposal failed follower locality, the other connected both pair-tree
edges but failed whole-pair skew (4.450497 mm against 4.0 mm), with no
promotion. The incorrect compiled-sidecar requirement is fixed; required
reservation binding remains strict. Final tests: 245 passed / 19 subtests;
protected PCIe2 regression and final six-board source audit unchanged.

**Completed canonical cohort:** `build/owned-anchor-suite-20260915/suite.json`, Hub
and 12VHPWR concurrently, started 2026-09-15T04:30:03Z. Coordinator PID 3242103,
initial board PIDs 3242106 and 3242107; finished 2026-09-15T04:49:02Z with no
admitted output. Check live processes AND journals before
any shared engine edit or duplicate dispatch. The diagnostic is no longer
running. No unchanged PCIe3 or PCIe2 wave was repeated for this anchor slice;
EPS/ATX remain at the coupled mating gate with existing span limits in force.
The `probe-cohort-refill-suite`, `owned-anchor-handoff-replay` and
`owned-anchor-screen-replay` jobs are complete. No new admitted board yet.

## Latest continuation: fixed-share probe cohort refills

The exact-power diagnostic exhausted its bounded 583.797-second allowance
inside corridor-alternative search; it proved no legal result and promoted
nothing. Its sources/engine remained unchanged. The next generic scheduling
repair addresses a separately measured defect: completed probes returned
unused time, but the producer never reconsidered its initially deferred jobs.
Fixed-share refills now fund only new slots at unchanged per-pair effort,
retain final-check reserves and reuse the same worker pool. Integrated tests:
226 passed, 15 subtests; protected PCIe2 SHA/regression/all probes unchanged.
See [the scheduling slice](probe-cohort-refill-2026-09-15.md).

**Completed canonical cohort:** `build/probe-cohort-refill-suite-20260915/suite.json`,
started 2026-09-15T03:35:18Z, PCIe3 and 12VHPWR concurrently. Coordinator PID
3217861, initial board PIDs 3217864 and 3217865. Check journals AND processes
before any shared engine edit or duplicate launch. Immutable body-free reviews
are published per completed pass, not failed scratch trials. EPS/ATX remain
at the coupled mating gate, Hub at committed-power pair reconstruction and
PCIe2 at 0 DRC / 12 opens in its latest continuation. They were not needlessly
rerun for an inapplicable scheduling slice. No new admitted board is claimed.

## Latest continuation: bounded power-replan handoff

The probe-scope producer completed with no admitted placement: eight early
claimed improvements became one, with no losing full finalist. The remaining
handoff lost its detailed power-replan failure stack in the outer journal.
The shared isolated/budgeted handoff now preserves it and guards the complete
source artifact family. Integrated tests: 213 passed, 15 subtests; protected
PCIe2 regression and all six source families unchanged. See
[the replay, exact trial failures and limits](bounded-power-replan-and-failure-stack-2026-09-15.md).

**Completed diagnostic:** `build/exact-territory-probe-20260915/probe.json`,
testing full exact-power realization for a preflight-only territory refusal.
Budget exhausted, sources/engine unchanged, no promotion authority.
`probe-scope-suite-20260915` and `power-replan-isolation-replay-20260915`
are complete; no unchanged Hub/VHP cohort was duplicated. EPS/ATX span limits
remain in force pending the nonblocking question about a coupled wider ECO.

## Latest continuation: exact finalist rejection attribution

The reservation-index cohort completed with all three inputs unchanged and
blocked. PCIe3 lost its exact finalist/key evidence at temporary cleanup, so
the next shared slice records the decisive ranking field and bounded,
hash-verified diagnostic board bundles without changing acceptance. See
[the repair and validation](exact-finalist-attribution-2026-09-15.md).

The diagnostic `build/finalist-evidence-replay-20260915/operation.json` completed:
early 10 critical refusals became 12 at full authority, against baseline 11.
Partial probes omitted USB quality and a moved component's second CAN pair.
Generic scope/accounting fixes passed 280 tests and unchanged PCIe2 control.
The A/B diagnostic `build/probe-scope-replay-20260915/` completed: corrected
early count 12 exactly matches full authority; all 46 native component/pair
scope checks across six boards passed, with all sources unchanged.
**Completed canonical follow-up:** `build/probe-scope-suite-20260915/suite.json`,
PCIe3 only (the reproduced affected current failure), 350.461 s, no admitted
placement. Hub/12VHPWR unchanged exhausted blockers were
not repeated for an inapplicable slice; EPS/ATX mating guards remain. The
three-board `reservation-index-suite-20260915` is no longer running.

## Latest continuation: exact reservation-query acceleration

The committed-power cohort completed without an admitted board. Hub now
honored its frozen reservations but exhausted the pair-search budget; stack
samples exposed repeated linear reservation scans. The generic spatial index
preserves exact tests and witness order, with 2.85–6.74x measured query speedup
across twelve real-board layer datasets, 340 tests and an unchanged PCIe2
control. See [the evidence and limits](reservation-index-and-suite-replay-2026-09-15.md).

**Current follow-up:** `build/reservation-index-suite-20260915/suite.json`,
Hub/PCIe3/12VHPWR concurrently. Check journals and processes before any launch
or shared engine edit. EPS/ATX remain at the coupled interface gate.

## Latest continuation: committed-power pair reconstruction

The nested-budget cohort completed without a new admitted placement. Hub did
construct and independently qualify a CAN pair, but exact re-admission found
it crossing committed power reservations. The constructor/recovery path now
binds those reservations explicitly and local escape search honors them during
enumeration. See [the forensic and shared repair](committed-power-pair-reconstruction-2026-09-15.md).

**Completed cohort:** `build/committed-power-suite-20260915/suite.json`,
Hub/12VHPWR/PCIe3 concurrently after 299 integrated tests and unchanged PCIe2
control checks. Check the journal and processes before any launch or shared
engine edit. EPS/ATX remain at the coupled interface gate.

## Latest continuation: nested operation budget repair

The preceding three-board cohort has completed without an admitted placement.
Hub reached actual pair reconstruction but exhausted its old outer repair
budget; 12VHPWR and PCIe3 retained their priority-route refusals. See
[the shared root cause, repair and validation](nested-operation-budget-and-suite-review-2026-09-14.md).

**Completed cohort:** `build/nested-budget-suite-20260914/suite.json` tested
Hub, 12VHPWR and PCIe3 concurrently after 306 integrated tests passed.
Check that journal and live processes before any launch or shared engine
edit. The preceding `priority-plated-suite` is no longer active. EPS/ATX mating
guards and the historical PCIe2 control remain unchanged.

## Latest continuation: atomic priority dependencies and plated power pins

**Completed cohort:** `build/priority-plated-suite-20260914/suite.json` tested
Hub, 12VHPWR and PCIe3 concurrently from their explicit current inputs,
without admitting a new placement. See the newer continuation
above before launching anything.

Generic pair-dependency replacement, fair retry budgets, retained exact-power
failure artifacts and scoped PTH local power preclosure are implemented. The
retained Hub diagnostics gained two required connections with zero added vias
and all six frozen power domains connected, but still require signal-pair
reconstruction before any placement can be admitted. See
[the complete slice and evidence](priority-dependency-and-plated-power-preclosure-2026-09-14.md).

The preceding PCIe2 full pass completed at 0 DRC / 12 opens and reached final
signoff without closing another connection. Its verified partial-route review
is linked in the new report. EPS and ATX remain held at the coupled interface
geometry gate. No failed diagnostic was promoted and no mating guard bypassed.

## Latest continuation: exact copper echo reconciliation

The local-via route follow-up is complete and failed both candidates at import
sanitation: exact newly added copies of original Kelvin copper created a
topology failure that structural DRC cleanup did not remove. The generic fix
now passes both archived imports at 0 DRC / 12 opens with Kelvin/pair topology
preserved. Six-board no-op replay, four applicable real-board echo injections,
112 tests and the unchanged historical PCIe2 control are documented in
[the forensic and verification report](exact-copper-echo-import-and-suite-replay-2026-09-14.md).

**Completed journal:** `build/copper-echo-route-followup-20260914/suite.json`.
This canonical producer replay reached final signoff at 0 DRC / 12 opens.
It used the same admitted local-via source, not an old board. See the newer
active cohort above before any launch. The other boards retained their
recorded placement/interface blockers; unchanged exhausted waves were not
repeated in this slice.

## Latest continuation: local-via reconstruction

The six-board repair-stage replay is complete at
`build/local-via-rebuild-suite-20260914-c/receipt.json`. PCIe2 improved from
one invalid via/pad overlap to zero and nine dimension failures to seven,
retaining 0 DRC / 12 opens. Other boards were unchanged or held at their
existing interface-intake gates; these were not six new routed passes.
See [the generic repair and evidence](local-via-owner-rebuild-and-suite-review-2026-09-14.md).

The bounded canonical PCIe2 follow-up at
`build/local-via-route-followup-20260914/suite.json`, from exact input SHA
`82f98e64bc47ad32e7e7333c669b4944db56b97d3c2a89d11a964a3cddd692ba`,
completed without an eligible output. See the newer continuation above.
The known other-board failures are not grounds
for repeating their unchanged exhausted waves. Current native review:
[PCIe2 local-via reconstruction](http://localhost:8090/?id=20260914-pcie2-local-via-rebuilt).

## Campaign history (completed)

The user requested simultaneous advancement, observation and shared repair
across the board suite. `build/parallel-suite-20260914-a/suite.json` is the
coordinator ledger. All six manifest wave boards launched concurrently:

- PCIe2: latest admitted local-via repair of the journal-verified routed winner.
- PCIe3: verified `pcie3-body-via-lookahead-suite-20260914` placement.
- Hub: verified `hub-certified-resume-suite-20260914` placement.
- 12VHPWR: verified `seam-prefix-suite-20260914` placement checkpoint.
- EPS rev3 and ATX 24-pin rev3: manifest source boards, normalized from their
  authoritative schematic hierarchy in working copies before placement.

Explicit source paths, SHA256 values and complete hierarchy signatures are
in `build/parallel-suite-inputs-20260914.json`. Prior journal lineage was
validated before launch; the PCIe2 normalization report is bound to its
verified parent hash and admitted output hash. No old-file search fallback
or source/candidate promotion was performed.

All six boards passed source intake. PCIe2 retained the exact current candidate
through placement admission and then entered detailed routing. The remaining
five were still in placement work at the initial observation. Consult the
live ledger for later outcomes; this note is not a completion claim.

## Bounded compute and storage

- Six concurrent board processes, two placement/probe workers per board.
- Two sequential route candidates per board; one route worker per board.
- 12 craft trials, two craft rounds, one epoch per pass; eight route passes.
- 1800-second per-board wall budget, including a 1200-second explicit
  priority-repair operation ceiling, still capped by the campaign deadline.
- Two BLAS/OpenMP threads; Java gets two active processors and a 2 GiB heap.
- At least 16 GiB free storage required at launch; disposable trials use the
  existing bounded-cleanup pipeline.

At launch WSL had 32 logical CPUs, about 26 GiB available RAM and 72 GiB free.
An early live observation showed GPU activity on the RTX 4080 Laptop GPU,
roughly 6.5 GiB VRAM use, and ample RAM/disk headroom.

Launch helpers: `tmp/prepare_parallel_suite_20260914.py` and
`tmp/run_parallel_suite_20260914.py`. The campaign runs the canonical
`cec_board_suite` / `cec_full_pipeline` entry points, not a second router.

## Generic repair scheduling correction

The preceding residual run spent its whole 240-second budget in eight early
via-relocation searches: seven worker timeouts at 25 seconds and one at the
remaining allowance. The error evidence exists in the nested sweep ledger;
an empty top-level attempt array did not mean no work occurred.

The generic correction in `cec_certificate_repair`:

1. The entire early via sweep receives at most 60 seconds or one quarter of
   remaining transaction time, shared across its targets.
2. Every in-flight child is capped by that local deadline and the enclosing
   transaction deadline; the parent deadline is restored on all exits.
3. Two consecutive worker timeouts stop that local strategy, preserving its
   evidence and leaving later routing strategies eligible.
4. Via target completion uses the existing coordinated atomic-close allowance
   instead of an unrelated hard-coded 25-second limit. The local stage ceiling
   remains authoritative, so increasing a child allowance cannot starve the
   rest of the portfolio.

No geometry, current, connectivity or fabrication admission rule changed.
Tests: `build/parallel-suite-fairness-tests-20260914.log`, **160 passed**.
The immutable historical PCIe2 control's four probes and board hash equal
the immediately preceding stricter-control report:
`build/parallel-suite-fairness-control-20260914.json`. Its pre-existing broader
release failures remain; equality is regression protection, not fab approval.

An additional bounded native residual replay is recorded separately under
`build/fair-via-residual-resume-20260914`; it must not be mistaken for a new
full-board campaign result.

That replay finished in 240.067 seconds with no adopted geometry: 0 DRC and
17 opens remain. It started 12 attempts: two congestion-via relocations, eight
broad canonical closures and two atomic negotiations. Previously only eight
via probes consumed the entire budget. This demonstrates restored portfolio
coverage, not improved connectivity.

## First-pass failures and forensic evidence

The partial previews are diagnostic, never manufacturing candidates.

- EPS: four unique terminal pairs short (TB11/TB13, TB12/TB14,
  TB21/TB23, TB22/TB24).
- ATX: three unique terminal pairs short (TB1/TB2, TB1/TB5, TB2/TB4).
  Repeated native rows across layers are not additional unique collisions.
- All seven pairs have a closest pad-center separation of 1.5 mm in the
  original source, normalized copy and generated placement. Therefore fresh
  placement did not introduce these shorts. The compiled mating pitch matches
  the daughterboard pattern but does not provide adequate main-board pad
  clearance. Body-envelope matching alone is insufficient. Preserve dimensions
  and mating contracts; do not independently spread one mating half or shrink
  the footprint lands to make the electrical screen pass.
- The source/normalization/placement comparison is in
  `build/parallel-suite-20260914-a/fixed-interface-forensic.json`.
- PCIe3: native courtyard/pad geometry and craft pass, but priority-route
  admission retains 11 refusals (nine Kelvin, one pair and one route-craft).
  The pair certificate records CAN_H at 2.05x endpoint-MST span against the
  declared 2.00x limit. No threshold was relaxed.
- 12VHPWR: physical placement and protected power pass, but two priority-pair
  refusals remain. Evidence includes native pad-tree escape refusal,
  flow-through coupled-corridor refusal and exhausted bounded portal searches.
  No accepted placement move was found. These are not completed routes.

PCIe2 passed placement and route preflight, then both route seeds failed at
the local power-prefix barrier. The narrow cause is rematerialization:
`_compile_post_priority_power_state` calls the additive pour path on a board
already containing its admitted power zones. Zone count rose from 16 to 20,
with four new `zones_intersect` identities. The exact gate caught the defect;
the broad "local PI/Kelvin and exact power do not coexist" message alone does
not explain it. The nested `local-power-prefix/exact-state.json` does.

An isolated draft replay used the existing generic
`replace_generated_power_pours(..., managed_nets=frozen_nets)` at that boundary.
It passed the full local PI/Kelvin/power/reference-plane barrier in 31.844 s,
with 0 DRC / 17 opens before and after, preserved source, parent copper,
placements and qualified pairs. Every layer/net outline-union symmetric
difference was exactly 0.0 mm2 and the zone-domain set was unchanged.
Evidence: `build/prefix-replacement-draft-20260914/report.json`.
This is initially a diagnostic draft, not a production qualification; the
shared engine remains frozen until the current cohort finishes.

Four synthetic regression cases in
`tests/test_frozen_power_rematerialization.py` reproduce the old failure across
different net names, translations, outer layers and both accepting/refusing
native gates. Their initial failing receipt is
`build/frozen-prefix-red-tests-20260914.log`.
The in-memory draft integration passes 53 tests plus three subtests, recorded
in `build/frozen-prefix-draft-tests-20260914.log`; this does not alter active
processes' imported modules or the on-disk production engine.

Cross-board native primitive replay on PCIe3 created the 19 previously
unmaterialized declared power zones (0 DRC, 208 opens; not route closure).
Its second materialization retained all 19 identities, all zone declarations
and all tracks/vias. Both source files remained unchanged. Receipts:
`build/parallel-prefix-pcie3-primitive-20260914/report.json` and
`build/parallel-prefix-pcie3-repeat-20260914/report.json`.

During the Hub pass, locally accepted signal-placement trials were rolled back
by the independent post-move power authority. The inspected refusal is a
required VCC_P1 over-under bridge at cell (19,24) with no legal via site after
pad/ledger exclusions, recorded in
`hub-standard-rev2/02-placement/operation-ensure-authority-zq68tyal/report.json`.
That is a materialization failure, not evidence of signal-routing closure.
The next generic efficiency target is early exact bridge-site feasibility
before spending the full precision-pair budget on a trial. Do not waive the
late authority gate or keep a locally improved but unrealizable placement.

## Integrated correction and follow-up

The six-board cohort finished with all source and engine signatures unchanged.
No complete routing/placement admission improvement was retained. Elapsed
seconds were PCIe2 316.43, PCIe3 395.02, Hub 1570.21, 12VHPWR 947.38,
EPS 303.09, ATX 301.96. Hub retained its incumbent after three outer rounds;
its final gate has one priority-route refusal, two critical reachability
failures and the exact power-bridge refusal above.

After all jobs exited, the frozen-domain replacement fix was integrated into
`cec_synth_pipeline._compile_post_priority_power_state`, with its replacement
receipt persisted on both acceptance and refusal. Production tests:
**213 passed plus three subtests**, in
`build/parallel-prefix-integrated-tests-20260914.log`. `git diff --check` passes.

The unmodified production code then passed the full native local-prefix replay
in 29.016 seconds. Source, parent copper, placements, qualified pairs and local
PI remained valid; 0 DRC / 17 opens and zero area difference on every zone
layer/net are retained. Receipt:
`build/prefix-replacement-production-20260914/report.json`.
The protected historical control's four probes and board hash match the
pre-fix receipt exactly (`build/frozen-prefix-control-20260914.json` versus
`build/parallel-suite-fairness-control-20260914.json`). This preserves its
0 DRC / 0 opens as well as its documented pre-existing broader release failures.

A new canonical production follow-up is running only the board whose blocker
this correction addresses: `build/parallel-prefix-followup-20260914/suite.json`,
launched by `tmp/pcie2_prefix_followup_20260914.py`. It retains the same explicit
current PCIe2 input hash and the bounded policy. Do not launch a duplicate job
or repeat unchanged failed passes for other families. Their next work remains
joint interface correction, priority-pair access and early bridge-site proof.

Final all-board first-pass gallery:
`C:/Users/Admin/Documents/CEC-Board-Reviews/parallel-suite-20260914-a/all-boards-d8928a86a1777b01.png`.
PCIe2's blank route panel means the first attempt produced no journal-eligible
route output; it does not mean its separately verified retained placement was
lost. No older board was substituted.

## Observation and continued work

The app heartbeat `cec-board-suite-review-and-repair` is active every 15 minutes
in the current task. It checks live jobs, reviews new artifacts, performs
bounded generic repairs and continues measured passes where appropriate.
It stays quiet on unchanged running state and reports meaningful changes,
review artifacts, regressions, completion or required user decisions.

Shared engine files stay fixed while this cohort runs. Investigate and record
failures as boards finish; apply and test shared engine changes between cohorts
so a running job cannot silently combine different code revisions.

The standard suite publisher creates immutable, body-free top/bottom reviews
and a content-addressed all-board gallery as each full attempt completes.
`tmp/review_completed_stages_20260914.py` also publishes **explicitly completed,
hash-verified stage outputs** before the full attempt finishes. It records them
in `completed-stage-reviews.json` and never labels a placement as a newly
completed route. PCIe2's first placement view is byte-identical to its input;
it is retained progress, not a new layout improvement.

Desktop review directory:
`C:/Users/Admin/Documents/CEC-Board-Reviews/parallel-suite-20260914-a`.
Per-stage previews have separate immutable directory names under the same
`CEC-Board-Reviews` parent.

Keep the computer and app running for local scheduled checks, as described in
the [official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## Follow-up completed and checker corrected

The PCIe2 follow-up above has now finished; it is no longer running. Its selected
partial route has **0 DRC / 12 opens**, versus **0 DRC / 17 opens** at input.
Source and engine signatures stayed unchanged during its 1323.142-second run.
The final hash-verified, body-free review is available at
[the completed-pass dashboard](http://localhost:8090/?id=pass-parallel-prefix-followup-20260914-pcie-8pin-2port-0b5e39545b).
It is blocked, not fab-ready; Gerbers were withheld.

Between cohorts, a generic saved-artifact signoff bug was fixed: legal short
fragments created on a disposable normalization copy could incorrectly exempt
their whole original tracks by UUID. Signoff now requires full-original bounded
neckdown coverage, independent of lock state. Corrected native counts are nine
minimum-dimension violations at input and nine at the selected winner, with no
new violation identities. The existing final repair stage removed the two
additional via-dimension failures in the intermediate candidate.

Validation: **298 tests plus three subtests passed**; the historical PCIe2
control's four probes and hash are exactly unchanged. No board-suite jobs remain
running. Do not re-run unchanged failed boards or this checker-only correction
as a full physical wave. Continue the affected physical blocker classes above.
Detailed evidence and next-work boundaries:
[Prefix follow-up and original-track proof](prefix-followup-and-original-neckdown-proof-2026-09-14.md).

**September 15 continuation index:** Later completed work and current-source
holds are in [coupled local-cell search](coupled-cell-search-2026-09-15.md).
The newest follow-up is [complete-probe lease dispatch](probe-lease-dispatch-repair-2026-09-15.md),
with journal `build/probe-lease-followup-suite-20260915/suite.json`.
Read that journal and process tree before starting any campaign; the older
"latest" and "no jobs running" statements below describe September 14 only.

## Exact bridge feedback slice completed

The generic over-under planner now probes the complete current-sized bridge
field set before final realization, feeds located refusals back into a copied
transition mask, and makes at most eight alternate searches. Exhaustion still
aborts the whole power-authority transaction; it cannot silently omit a failed
rail. Structured net/terminal/via-count evidence is retained for placement repair.

Final native parallel probes: Hub remains refused after the same VCC_P1 field
failure and one alternate search, now identifying F1 pin 1; PCIe3 fresh exact
power compilation passes. No board geometry was promoted. 349 tests plus three
subtests pass, and historical PCIe2 control probes/hash remain unchanged.
No suite jobs remain running. The next target is power-terminal escape/placement
repair driven by this evidence before unrelated expensive pair trials, not an
unchanged Hub full-wave retry. See
[exact power-bridge feedback](power-bridge-search-feedback-2026-09-14.md).

## Power-terminal dependency stage and active canonical follow-up

The structured power failure now drives the existing placement proposal and
power-replan transaction. It validates live terminal identity/position, protects
fixed anchors and complete follower cells, tests power before pair routing and
remeasures physical placement after power compilation. Its default isolated
budget is 12 trials / 240 seconds / one invocation per placement pass. The hook
also covers authority failures encountered after a signal-placement move.
Unresolved typed bridge dependencies no longer trigger unrelated pair retries.

Native Hub replay: 43 proposals, 12 selected, 64.573 seconds, zero admitted moves
and zero pair evaluations. Nine trials collided with frozen copper, two failed
power compilation and one failed physical placement. The source remains exact.
PCIe3's non-applicable adapter is a no-op. Test receipts: 360 integrated tests
and a separate overlapping 102-test full-pipeline suite pass; the historical
PCIe2 control and all four probes remain unchanged. The core anti-overfit gate
has 57 modules and zero violations (broader legacy findings remain).

**Latest completed job:** `build/hub-power-terminal-followup-20260914/suite.json`.
It finished blocked in 109.521 seconds (95.0-second placement), versus the
earlier 1570.21-second failed Hub pass. The 12 power-first trials retained the
exact input; zero pair evaluations were spent on those rejected proposals and
unrelated pair-repair rounds were skipped. This is about 93% lower failed-pass
runtime, not routing closure or a general router speedup. Source, hierarchy
and engine signatures stayed unchanged. No board-suite job remains running.
The [verified unchanged Hub placement](http://localhost:8090/?id=pass-hub-power-terminal-followup-20260914-hub-standard-rev2-bcb7f9c09e)
is published as BLOCKED / NOT FAB SIGNOFF. Do not repeat this unchanged failure.

After reviewing this pass, rotate development to the coordinated EPS/ATX
main/daughterboard terminal geometry rather than another Hub-only loop. Details:
[Power-terminal dependency repair](power-terminal-dependency-repair-2026-09-14.md).
