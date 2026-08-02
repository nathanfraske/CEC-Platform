# CEC Platform PCB automation audit, 2026-08-01

> **Superseded evidence snapshot.** This report describes the first audit pass
> before the 2026-08-02 electrical, passive, SPICE, pour-bootstrap, candidate
> freshness, and documentation work. In particular, its ngspice availability,
> Hub repour, SPICE execution, and candidate status statements are no longer
> current. Use `beta-placement-passives-audit-2026-08-02.md` for the refreshed
> evidence and remaining blockers.

## Scope and evidence boundary

This audit started from `main` commit
`231b426930138457c1a9b2736cd47a056691b7d1`. The worktree contains the audit
repairs described here and has not been committed.

The reviewed surface includes:

- the top-level synthesis and release driver
- automatic placement, power-pour planning, and Freerouting integration
- all 15 BETA PCB files and all 11 BETA root schematics
- the six-layer stackup, via, and mezzanine manufacturing contracts
- the field electrical and thermal solver path
- the analog-cell, board-sanity, and backfeed SPICE harnesses
- the schematic MCP mutation and rollback gate

KiCad 10.0.4 generated fresh ERC and DRC evidence. The DRC sweep used
`--severity-all --all-track-errors --refill-zones`. Reports are stored under
`build/audit-final/drc-all-beta` and `build/audit-final/erc-all-beta`.

This is a software and CAD audit. No board was fabricated or bench-tested. A
passing software gate cannot establish connector fit, current capability,
thermal accuracy, contact resistance, fault behavior, or service life.

## Verdict

The repaired top-level entry point now invokes placement, pour, route, physics,
and release gates in the claimed order. The focused regressions pass, and the
reproduced tool, schema, geometry, and no-candidate failures now stop the run.
A real forced six-layer route passed. A real Hub run reached fresh placement
and strict repour, but did not produce a routed candidate within its budget.

No primary BETA PCB is ready for fabrication. The current layouts still have
357 error-severity DRC violations and 1,374 unconnected items in aggregate.
The checked-in Hub candidate has 5 DRC errors and 16 unconnected items. The
migrated ATX 24-pin candidate has 208 DRC errors and 117 unconnected items. The
current 12VHPWR field solve also fails configured temperature-rise and
current-density gates at the audited 50 A scenario.

The three output daughterboards are the only PCB files with zero error-level
DRC violations and zero unconnected items. That means they are CAD-clean under
the current rules, not that their stated hardware behavior has been validated.
They still require first-article fit, electrical, load, and thermal tests.

## Repairs completed

| Area | Reproduced defect | Repair and current evidence |
| --- | --- | --- |
| Top-level synthesis | Placement was deferred, a local name shadowed the release-gate function, earlier flags could be lost, and a proposed repair could be counted as completed without changing the board | A normal synthesis run invokes placement, materializes its result, records residual and dimensions, and carries every blocking flag into the final verdict. An explicit board is validation-only unless replacement placement is requested. Action requests remain blocking until a changed board passes fresh checks. Eleven direct pipeline tests pass. |
| KiCad input gates | Tool failures, invalid JSON, stale fixed-name netlists, draft-board ERC skips, and a broken netclass checker could appear clean | ERC, DRC, netlist export, and netclass geometry now require complete evidence. Draft boards do not skip ERC. Temporary files are unique and removed. Tool, parse, and checker failures block release. The router intake uses the shared Windows KiCad resolver and refuses missing schematics, missing checkers, malformed output, and checker exceptions. |
| Route verdict | A board with a general open net could pass if Kelvin and differential-pair checks passed; the dispatcher could accept a model-selected candidate whose complete gate was false; an empty batch crashed on an uninitialized best-candidate variable | Any remaining unconnected item now blocks `cec_score`, the dispatcher, and the independent route verdict. Stackup, through-via, actual laid-pour, mezzanine, ERC, and DRC results are part of the final decision. Empty batches return a controlled failed verdict. |
| Secondary cascade | `cec_cascade.py` treated DRC as finishing, ignored ratlines in route acceptance, reused a stale verdict if saved-board rescoring failed, supplied an unreviewed transient profile, and could ignore failure of a requested via-field mutation | The cascade now requires the complete fresh saved-board verdict, zero structural DRC, zero unconnected items, clean placement, and the steady-state field solver. Rescoring and requested via-field failures block. Transient input is refused until a reviewed transient solver and profile exist. Seven negative tests pass. |
| Automatic placement | The available placer was not connected to the advertised flow; one current EPS case retained residual 2 | The placer is called by the top-level flow. Optional corner mounts may be dropped when occupied, but the shared H1 datum may not. The current EPS rev3 materialization has residual 0, and all 62 corridor tests pass. |
| Pour planning | Equal partitioning ignored unequal currents, order affected allocation, nets could overlap, missing current could use a guessed width, and a failed minimum-width solve could fall back to the old rectangles | Slabs are deterministic, disjoint, and current-proportional. Nonpositive or absent required current is rejected. Minimum-width, missing-anchor, and allocation failures raise a blocking error. The router cannot restore raw overlapping rectangles. The laid-zone checker uses KiCad effective shapes, actual track and via dimensions, and excludes only declared plane layers. The expanded pour, power-layer, and force-rail suite passes 183 tests with 3 intentional skips. |
| Router runtime | The local `1.7.0-cec2` pin could not be downloaded, Java discovery differed between wrappers, and the route prerequisites described a stale JAR | The fork is rebuilt from upstream Freerouting 1.7.0 commit `ba0b23e89858bbfe7113df38f9de8dab090a0079` plus `scripts/patches/freerouting-1.7.0-cec2.patch`. The reviewed JAR SHA-256 is `149cebd88169be77f5ddc7e1d50284451204f10c088e5d7380859ab0395b7ce5`, reproduced twice. All entry points resolve the same Java 17 runtime and hash-check the JAR. |
| Six-layer routing | The router and DSN exporter did not carry the new layer policy end to end | F.Cu, In2.Cu, In3.Cu, and B.Cu are signal-capable. In1.Cu and In4.Cu are exported as power planes and excluded from ordinary trace routing. A real forced route placed `/SIG` on In3.Cu only, with zero vias and zero unconnected items. |
| Hub standalone runner | It used an old four-layer reference, could publish the best failing attempt, did not bind the parent schematic, let invalid pours continue, dropped the worker timeout, and crashed when every seed failed | It now uses the six-layer BETA reference, binds the parent schematic, strips and regenerates pours in isolated KiCad processes, requires every acceptance term, keeps best attempts separate, and exits nonzero without an accepted board. Worker timeouts are divided across the remaining run window. A live run stopped four seeds at 52 seconds and exited cleanly at 272 seconds inside a 288-second window. |
| Via-in-pad | Legacy code rejected every via touching a pad and had no manufacturing authority; one force-rail test also approximated a rectangular pad as a circle and falsely reported a real 0.15 mm edge gap as overlap | Only a board declaring a known POFV profile may place a same-net through via fully inside an SMD pad. Drill, annular ring, net, pad containment, and through-board type are checked centrally. Different-net and through-hole-pad collisions remain blocked. The force-rail regression now asks KiCad's effective-shape collider about the actual pad geometry. |
| Mezzanine | The segmented connector and optional mount language did not express the latest assembly decision | J6P, J6C, and J6D remain the selected segmented scheme. Hub and 24-pin candidates now share the same fitted H1 M2 ground lug. The mating gate checks location, GND net, plating, dimensions, exposed contact faces, and board-to-board coincidence. |
| FEM integration | The top-level path could solve with no applied sources, silently drop nets, ignore ambient selection, or fall back without a blocking result | The selected stackup and cooling configuration now reach the field solver. Every requested current is accounted for. Absent and dropped configured nets block the result. The probe validates its inputs and runs the same physics gates as the pipeline. |
| SPICE | Windows selected the GUI executable, duplicate device names stopped parsing, a leaf sheet could be netlisted, and empty or failed simulations could pass | Windows accepts only a console ngspice executable, launches it without a window, finds the project root, uses unique deck and element names, rejects empty output and nonzero exits, and removes temporary files. The backfeed harness is local-or-configurable and uses the available NumPy trapezoidal integration API. |
| Schematic MCP | A mutator exception or false result could leave changed files and still report success; Windows paths and provisioning were broken | The gate snapshots the root and reachable sibling sheets, restores them on mutation or connectivity failure, rejects an explicit false result, uses UTF-8 and subprocess timeouts, and normalizes Git paths. `.mcp.json` now invokes `python`, with `mcp>=1.29,<2` and `starlette<0.48`. A live stdio session listed 18 tools from server version 1.29.0. |

## Adopted six-layer stackups

### High-current modules and ATX 24-pin

Profile `jlcpcb_6l_pofv_high_current` uses the 1.6 mm JLCPCB
`JLC06162H-3313` buildup.

| Layer | Pipeline role | Finished copper used by the models |
| --- | --- | ---: |
| F.Cu | Signal and power | 0.0700 mm |
| In1.Cu | Ground reference plane | 0.0152 mm |
| In2.Cu | Signal routing | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground reference plane | 0.0152 mm |
| B.Cu | Signal and power | 0.0700 mm |

### Hub

Profile `jlcpcb_6l_pofv_signal` uses the 1.6 mm JLCPCB
`JLC06161H-3313` buildup. The Hub does not use the high outer copper weight.

| Layer | Pipeline role | Finished copper used by the models |
| --- | --- | ---: |
| F.Cu | Signal | 0.0350 mm |
| In1.Cu | Ground reference plane | 0.0152 mm |
| In2.Cu | Signal routing | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground reference plane | 0.0152 mm |
| B.Cu | Signal | 0.0350 mm |

The inner-layer thickness is deliberately 15.2 µm, not the nominal 17.5 µm
often associated with 0.5 oz copper. JLCPCB documents that finished 0.5 oz
inner copper on 4 to 8 layer boards is 15.2 µm. At equal length, material,
current, and resistance target, width scales inversely with thickness. Relative
to 34.8 µm copper, the exact geometry multiplier is `34.8 / 15.2 =
2.289473684`. The synthetic field regression also produces 2.289 times the
Joule loss when width is left unchanged.

That ratio is not a final trace-width value. Impedance and current-carrying
geometry still require per-net calculation, the selected JLC buildup, the
actual return-plane relationship, and first-article thermal validation.

JLCPCB's current calculator guide also says its controlled-impedance calculator
supports 1 oz external copper, not 2 oz external copper. Impedance-controlled
nets on the high-current profile should therefore use In2.Cu against In1.Cu
where practical, or use geometry explicitly confirmed by JLCPCB for the chosen
2 oz outer buildup. A 1 oz external result must not be copied onto the 2 oz
outer layers.

## Through vias, layer transitions, and cost

Plated through via-in-pad is useful here. It removes the escape stub beside an
SMD land, gives the router more legal layer transitions, and is especially
helpful around the segmented mezzanine and dense 24-pin fanout. The implemented
contract follows JLCPCB's published POFV envelope of 0.20 to 0.50 mm drill and
at least 0.05 mm annular ring. The pipeline also requires full same-net SMD-pad
containment and emits KiCad filling and capping attributes.

JLCPCB states that POFV is the free default for 6 to 20 layer boards. It uses
epoxy filling followed by copper capping. This means the selected through-board
POFV process should not add a separate via-in-pad charge under the published
offer, although the six-layer board and other order options still determine
the total quote.

Blind and buried layer-to-layer vias could reduce through-via keepout on layers
they do not need to cross. They are not a usable JLCPCB option for this release.
JLCPCB's current capability table says blind and buried vias are not supported
and only through holes are made. Because there is no JLCPCB option to quote,
this audit does not invent a cost delta. Using blind or buried vias would mean
qualifying another fabricator and obtaining a real quote, and it would add
fabrication steps and stackup-specific design rules. The recommended path is to
use the free through-board POFV process first.

Official manufacturing references:

- [JLCPCB free POFV announcement and design limits](https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv)
- [JLCPCB via and pad-hole process note](https://jlcpcb.com/help/article/difference-and-tolerance-explanation-between-via-and-pad-holes)
- [JLCPCB manufacturing capability table](https://jlcpcb.com/capabilities/Capabilities?type=1)
- [JLCPCB impedance calculator guide](https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator)

## Hub pour evidence

The checked-in Hub candidate still contains the legacy overlapping slab set.
Its priority-9 `/5VSB_RAW` zone fills about 4,132.42 mm2. The other filled
rail zones range from about 1.84 to 73.28 mm2. That is fill-order ownership,
not a defensible current allocation, so the checked-in zones remain stale.

The repaired allocator reads these current inputs from the existing Hub
thermal configuration:

| Rail | Existing input | Diagnostic allocation share |
| --- | ---: | ---: |
| `+5VSB` | 3.0 A | 0.301652 |
| `/5VSB_RAW` | 3.0 A | 0.296697 |
| `/MAIN_5V_RAW` | 2.0 A | 0.199249 |
| `/VCC_P1` | 0.5 A | 0.050601 |
| `/VCC_P2` | 0.5 A | 0.050751 |
| `/VCC_P3` | 0.5 A | 0.050601 |
| `/VCC_P4` | 0.5 A | 0.050450 |

These are existing model inputs, not newly approved design currents. They need
owner validation against the Hub load budget before release.

On the checked-in placement, diagnostic mode produces 13 tentative polygons,
an allocation-share sum of 1.0, and exactly 0.0 mm2 of cross-net polygon
overlap. It also reports that `+5VSB`, `/5VSB_RAW`, `/MAIN_5V_RAW`, and
`/VCC_P2` cannot maintain the existing 1.2 mm minimum-width invariant. The
same four rails fail at 0.8, 0.6, 0.4, 0.3, and 0.2 mm raster resolution, so
this is not a coarse-grid artifact. Normal mode now refuses that result.

A fresh automatic `dataflow/s1` placement at 88.1 by 70.1 mm did pass strict
repour and materialized seven rails as seven disjoint polygons. This proves the
new placement and pour stages can clear the checked-in pour geometry holdup.
That placement still has residual 4 and is not a release candidate.

The actual laid-pour gate is now active in normal constraint runs and in both
route acceptance paths. It no longer treats the Hub's declared internal power
plane as a reserved routing pour. On the current ATX candidate, it reports 271
foreign pads, 93 foreign tracks, and 45 vias inside outer segmented power-pour
outlines. Those are blocking geometry findings, not internal-plane false
positives.

## Segmented mezzanine and M2 ground lug

The segmented scheme remains authoritative. J6P, J6C, and J6D retain their
shared mating positions and assigned pin roles.

H1 is now a required, fitted M2 metric fastener on both boards. Each board uses
a 2.2 mm plated hole with a 4.4 mm GND land, exposed on both outer contact
faces. Conductive hardware therefore supplies a supplemental inter-board ground
bond and mechanical support. It does not replace the normal GND contacts in the
three connector segments and is not the sole normal current-return path.

The CAD gate proves geometry and net assignment only. Hardware finish, washer
style, torque, and acceptable bond resistance have not been invented. They
remain production inputs that must come from supplier data or measurements.
The first article needs a four-wire ground-bond resistance check before and
after the planned peel, shake, and thermal-cycle work.

## BETA schematic results

The 11 root schematics contain 6 error-severity ERC findings and 1,240
warnings.

| Project | ERC errors | Warnings | Error type |
| --- | ---: | ---: | --- |
| 12VHPWR Standard | 0 | 98 | None at error severity |
| ARGB Standard | 0 | 123 | None at error severity |
| ATX 24-pin rev3 | 1 | 435 | Input pin not driven |
| EPS 8-pin | 1 | 114 | Input pin not driven |
| EPS 8-pin rev3 | 2 | 98 | Input pin not driven; pin not connected |
| Hub Standard rev2 | 0 | 114 | None at error severity |
| ATX output daughterboard | 0 | 5 | None at error severity |
| EPS output daughterboard | 0 | 2 | None at error severity |
| PCIe output daughterboard | 0 | 2 | None at error severity |
| PCIe 2-port | 1 | 117 | Input pin not driven |
| PCIe 3-port | 1 | 132 | Input pin not driven |

An error-free ERC row is not a functionality result. The warnings and the PCB
results still require disposition.

## BETA PCB results

| PCB | DRC errors | Warnings | Unconnected | Main error types |
| --- | ---: | ---: | ---: | --- |
| 12VHPWR base | 74 | 73 | 15 | Track width 70; hole clearance 4 |
| 12VHPWR candidate | 11 | 530 | 47 | Copper-edge clearance 6; hole clearance 4; clearance 1 |
| ATX 24-pin base | 7 | 125 | 235 | Hole clearance 4; intersecting zones 2; invalid outline 1 |
| ATX 24-pin candidate | 208 | 569 | 117 | Hole clearance 49; shorts 49; mask bridges 38; intersecting zones 24; clearance 22; edge clearance 12; courtyard classes 14 |
| EPS candidate | 6 | 488 | 14 | Hole clearance 4; track width 2 |
| EPS base | 6 | 27 | 193 | Hole clearance 4; edge clearance 2 |
| EPS rev3 base | 10 | 272 | 158 | Hole clearance 4; edge clearance 3; courtyard overlap 3 |
| Hub rev2 candidate | 5 | 537 | 16 | Hole clearance 4; edge clearance 1 |
| ATX output daughterboard | 0 | 21 | 0 | None at error severity |
| EPS output daughterboard | 0 | 8 | 0 | None at error severity |
| PCIe output daughterboard | 0 | 6 | 0 | None at error severity |
| PCIe 2-port candidate | 13 | 489 | 9 | Hole clearance 4; clearance 4; track width 3; mask bridge 2 |
| PCIe 2-port base | 6 | 198 | 154 | Hole clearance 4; mask bridge 1; short 1 |
| PCIe 3-port candidate | 5 | 503 | 231 | Hole clearance 4; courtyard overlap 1 |
| PCIe 3-port base | 6 | 240 | 185 | Hole clearance 4; mask bridge 1; short 1 |
| **Total** | **357** | **4,086** | **1,374** | Release blocked |

The corrected segmented connector and H1 seating expose old copper and
placement conflicts on the 24-pin candidate. Those 208 errors are not suitable
for a local waiver or hand edit. The board needs a fresh placement and routing
iteration under the new contract. The Hub's fresh placement can satisfy strict
repour, but the best bounded trial retained placement residual 4 and produced
no routed candidate. The generated probe artifact is diagnostic only and does
not replace the checked-in board.

Other BETA completeness findings remain material:

- ARGB Standard has no PCB in its BETA directory.
- Smoke Tester has documentation and BOM material but no schematic capture or
  PCB.
- Hub Standard rev2 has a candidate PCB but no board-of-record PCB.
- CAD-clean daughterboards still have open physical-fit and thermal validation
  work in their project records.

## Real router evidence

The direct router path uses Temurin Java 17.0.20+8 from the repository build
runtime and the hash-verified `1.7.0-cec2` JAR.

`scripts/probes/route_6layer_smoke.py` constructs a real six-layer
`JLC06162H-3313` board. It blocks F.Cu, In2.Cu, and B.Cu across the route and
exports In1.Cu and In4.Cu as power planes. The only legal ordinary signal path
is In3.Cu. The actual Java route produced:

```text
stackup gate: pass
through-via gate: pass
/SIG tracks: In3.Cu = 1, every other copper layer = 0
vias: 0
unconnected: 0
result: pass
```

This proves that layer metadata survives board generation, DSN export,
Freerouting, SES import, and final connectivity checking. It does not prove
that any current full BETA board can be routed cleanly. Eighteen route-oracle
gate tests pass, with four intentional real-router skips in that unit suite.
The earlier opt-in aggregate real-board route-oracle run exceeded five minutes
and was terminated. It is not counted as a pass.

The bounded Hub trial repeated its three placement results deterministically,
strictly repoured the best placement, and launched four real Freerouting seeds.
Each seed hit the newly propagated 52-second worker limit. The runner exited at
272 seconds inside its 288-second window, reported no accepted route, and left
no Java process behind. The run also exposed the empty-candidate `g_best`
initialization bug; that path is repaired and now has a direct regression test.

## Field electrical and thermal evidence

The field model is a rasterized multi-layer electrical and steady-state thermal
solver. It is not a conventional finite-element mesh, and its own result marks
the calibration as `uncalibrated`.

The current 12VHPWR candidate was solved at 50 A total, balanced as
8.333333333 A on each of six lanes, with 50 A return current, 50 °C enclosed
passive ambient, the production metal-case/TIM/M3 cooling label, CPU backend,
and a coarse 1.0 mm grid. Every requested net was present and injected.

Measured solver output:

```text
maximum temperature: 90.2 C
maximum rise: 40.2 C
Joule loss: 7.068404 W
injection: complete, no absent or dropped net
```

The run failed the configured gates. `/SENSEP1_HI` reached 119.048 A/mm2
against the configured 100 A/mm2 limit. All six low-side legs,
`/SENSEP1_LO`, `/SENSEP2_LO`, `/SENSEP3_LO`, `/SENSEP4_LO`,
`/SENSEP5_LO`, and `/SENSEP6_LO`, plus GND exceeded the configured 30 °C rise
limit. The maximum absolute temperature remained below the separate configured
105 °C limit.

The complete injection makes this a valid automated rejection. The coarse grid
and uncalibrated thermal boundary mean the numeric temperature is not accurate
enough for a production claim. It identifies where copper and return geometry
must improve, then the result must be checked again at a finer grid and on a
first article.

## SPICE status

The process and deck contracts are repaired and covered by 16 focused tests.
The repeated Windows `ngspice 46 Parse` window cannot recur through the checked
runner because it never selects `ngspice.exe`; only an explicit or discovered
console binary is accepted, and it is launched with no window.

This host currently has neither `ngspice_con.exe` nor a running Docker ngspice
service. Therefore this audit does not claim a current end-to-end SPICE
simulation. The tests prove executable selection, root-schematic selection,
deck uniqueness, stale-output rejection, nonzero-exit handling, empty-output
handling, and aggregate failure behavior. A full simulation remains required
after a console ngspice installation is supplied.

The analog-cell and backfeed decks are behavioral verification models. Even
when run, they validate the equations encoded in those decks, not vendor
semiconductor behavior or the assembled PCB.

## Schematic MCP status

The transaction and host-compatibility defects are repaired. Three destructive
negative tests prove rollback of root and child sheets on exception or
connectivity change, and rejection of a mutator that returns false. A live
stdio initialization on this host reported server `cec-schematic`, MCP version
1.29.0, and 18 available tools.

This proves startup, tool discovery, and the tested transaction boundary. It
does not prove that every possible schematic edit is electrically correct.
Every mutation still needs the normal ERC, netlist, identity, and review gates.

## Verification matrix

| Check | Result |
| --- | --- |
| Host SPICE, pipeline, MCP, thermal CLI, FEM input, DFM, and physics gate tests | 47 passed |
| KiCad six-layer, FEM profile, mezzanine, slab, injection, cascade, dispatch, laid-pour, and Hub fail-closed tests | 70 passed |
| Corpus parity and cross-platform determinism tests | 18 passed |
| Router intake and checker evidence tests | 13 passed |
| Route-oracle gate tests | 18 passed, 4 intentional real-route skips |
| Thermal calibration and blocking-authority anchor tests | 15 passed |
| Placement corridor suite | 62 passed |
| Expanded pour, power-layer, and force-rail suite | 183 passed, 3 skipped |
| Real six-layer Freerouting smoke | 1 passed; In3-only signal route, zero unconnected |
| Fresh BETA ERC sweep | Completed, 6 errors and 1,240 warnings |
| Fresh BETA DRC sweep | Completed, 357 errors, 4,086 warnings, 1,374 unconnected |
| Live 12VHPWR 50 A field probe | Complete injection, physics gate failed as intended |
| Live schematic MCP stdio initialization | Passed, 18 tools listed |
| Bounded full Hub diagnostic | Strict repour passed; four route seeds timed out; no accepted route; clean exit in 272 seconds |
| Aggregate real-board route oracle | Timed out after 304 seconds, not a pass |
| Full live SPICE simulation | Not run, console engine unavailable |

The focused suites are not a claim that every repository test passed. Complete
unittest discovery was not rerun to completion during this repair pass.

## Remaining release work

1. Validate the Hub rail-current table above and replace the unresolved
   `L2 = TBD (rung-3 bench)` value with a measured or supplier-backed part
   selection. No value was invented during this audit.
2. Reduce the Hub placement residual from 4 to 0, then run a longer strict
   placement, repour, and route iteration. The bounded 288-second diagnostic
   proved repour but was insufficient for Freerouting to finish any seed.
3. Run a fresh ATX 24-pin placement, repour, and route iteration under the
   adopted stackup and segmented mating contract. Clear the reported actual
   outer-pour incursions as part of that iteration.
4. Resolve every error-severity DRC item and every unacceptable unconnected
   item on all primary BETA layouts.
5. Resolve the six BETA ERC errors and disposition warnings that represent real
   symbol, footprint, or connectivity drift.
6. Improve the 12VHPWR high-side P1 and return copper, then rerun the field
   model at finer resolution and validate it against a loaded first article.
7. Install or provide a console ngspice engine and run the complete analog,
   board-sanity, and backfeed suites.
8. Complete the missing ARGB and Smoke Tester CAD deliverables or correct their
   published status.
9. Select the M2 hardware finish, washer scheme, torque, and acceptable bond
   resistance from supplier data or measured samples.
10. Perform first-article mating, four-wire ground-bond, power, load, fault,
   thermal, peel, shake, and thermal-cycle tests before any functionality or
   fabrication-ready claim.

No unspecified trace width, impedance geometry, fastener torque, contact
resistance, thermal correction factor, or blind-via price was invented in this
audit.
