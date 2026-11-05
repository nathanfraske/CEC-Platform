# Paired fan-in / via-land co-design and immutable-parent screening

## Measured root causes

`build/endpoint-geometry-forensic-20260917/report.json` checked the exact refused
pair endpoints on both canonical sources and saved precision prefixes, with
the complete bound power authority. It deliberately stopped before downstream
routing; endpoint eligibility is not route or board admission.

- PCIe3's resistor-end pad-origin via intersects the B.Cu `/SENSEC3_HI`
  reservation. The same refusal exists before and after earlier CAN routing.
- VHP's MCU USB pad-origin via intersects the existing locked 2.5 mm B.Cu
  `/SENSEP6_LO` track. The protection-array end can contain a via, but this does
  not qualify a complete mixed transition, coupling, or reference-return path.
- Native THT layer access already works; it was not changed again.

More importantly, the focused PCIe3 inner-layer constructor selected a fan-in
and transition which passed separately but failed together. Exact replay at
`build/combined-portal-forensic-20260917/report.json` shows both signal seats
clear on the parent. After just that endpoint's fan-in is emitted, its P trace
infringes the N via land. Adding the other endpoint is not needed to reproduce
the failure. This is a constituent-composition defect, not permission to move
or penetrate a priority power bus.

## Generic implementation

`cec_precision_route._route_paired_stub` now accepts an optional matched
destination-via land diameter. Each member sees the opposite destination land
as an exact native geometric obstacle while enumerating routes. The virtual
land never emits copper or grants fabrication permission. It only reserves
space for the already-declared transition geometry. Existing callers without
via destinations retain their previous domain; native THT access adds no new
signal vias. The local partner-copper cache remains invocation-local.

The portal constructor supplies this geometry to both screening and final
fan-in reconstruction. Before yielding a local candidate, it re-proves the
signal barrels and ground-return field with that actual fan-in present. This
combined proof does not use an immutable-parent snapshot. Refusals retain the
specific combined-transition witness. Complete edge, pair physics, protected
copper and whole-board admission remain independent and mandatory.

The separate performance fix adds an exact immutable-parent signal-seat
pre-screen. It can reject a blocked field before creating temporary barrels.
Both member witnesses are retained. Passing it still invokes the ordinary
sequential native insertions, which see the newly added partner and enforce
drill/copper clearance, followed by the full ground-return field. The snapshot
is local to one beam and is used only after exact rollback to its parent.

## Evidence and limits

- `build/focused-pair-portal-20260917/report.json`: baseline native inner-layer
  constructor probes, each with a 120-second deadline and profiler enabled.
  PCIe3 spent 23.6 of 30.0 seconds in transition-field work; VHP spent 108.6 of
  120.2 seconds there. Neither emitted a retained route.
- `build/transition-parent-suite-20260917/report.json`: parent-screen-only
  replay, PCIe3 27.6 seconds and VHP 99.1 seconds, both still refused. These are
  observed profiled runs, not a repeated controlled benchmark or connectivity
  improvement. VHP progressed beyond its former deadline failure to a finite
  candidate refusal; that is not a proof of physical impossibility.
- New loaded-native, translated/rotated front/back fixtures reproduce a
  trace-clear/via-illegal fan-in and show a legal alternative with the virtual
  lands. Additional native tests compare cached and exhaustive screening on
  front, inner and back copper and check mutual barrel interference after a
  positive parent screen. No new width, clearance, drill, process or load
  budget has been introduced.
- `build/terminal-via-envelope-broad-20260917.log`: **485 tests and two subtests
  pass**, 19.52 seconds. This overlaps the earlier 477-test screening suite.
- `build/terminal-via-envelope-final-tests-20260917.log`: **486 tests and two
  subtests pass**, 19.47 seconds, including an additional production-beam
  call-chain regression proving individually clear pieces cannot bypass the
  combined proof. This is the final selected-suite count, not additive totals.
- The first combined replay adapter did not pass its new output path into
  spawned processes. Workers refused existing directories before board work;
  its failed receipt is retained at `build/terminal-via-envelope-suite-20260917`.
  The corrected adapter passes the destination explicitly to each process.

## Completed edge replay and current compiler replay

`build/terminal-via-envelope-suite-v2-20260917` is the completed corrected concurrent
cohort: two real native refused-edge probes, four other-family gate checks,
and the historical PCIe2 control. These are diagnostic edge constructions,
not a complete board routing or fabrication pass. Both edges remain refused;
PCIe3 took 73.6 seconds, VHP 98.2 seconds, with zero retained copper added.
PCIe3's former late trace/via failure no longer enters the selected beam:
the stricter local construction searches more candidates and still finds no
qualified resistor-end transition. This is not a speedup over the invalid
early winner, nor a connectivity improvement. All six source/hierarchy hashes
and historical PCIe2 control remain unchanged; PCIe2 still has five opens.
Core generalization audit passes; broader legacy debt is not thereby closed.

`build/via-envelope-priority-suite-20260917` completed the actual full priority
compiler on Hub, PCIe3 and VHP concurrently, alongside the other three current
board gates and the historical control. This includes production scheduling,
flow-through and earlier-pair interactions that an isolated edge cannot prove.
No board improved its connectivity in this pass:

| Board | Observed result |
| --- | --- |
| PCIe2 | Physical gate passes; five opens remain; source/copper unchanged. |
| PCIe3 | CAN_J1 and separate Kelvin refusals remain; compiler 194.867 s. |
| VHP | USB flow-through leg 2 remains refused; compiler 68.239 s. |
| Hub | USB flow-through leg 1 remains refused; compiler 74.762 s; three existing craft holds remain. |
| EPS / ATX | Still held by the pending paired-interface ECO decision. |

PCIe3 recreated 68 copper objects in its private compiler prefix, but
`pcie3-prefix-comparison.json` proves their exact net/layer/geometry equals the
previous prefix. They are **not 68 new routing improvements**. Hub and VHP added
zero copper. All six canonical source/hierarchy identities and historical
PCIe2 board/hash/probe parity match. No new preview or candidate was promoted.
All workers finished. The dashboard GET returned HTTP 200 from Windows;
these diagnostics use about 57 MiB and approximately 64 GiB remains free.

The generic core gate passes; the broader inherited audit still reports
23 physical and 380 runtime violations, with `full_pipeline_generic=false`
and `release_ok=false`. These changes do not certify the whole legacy engine.
Next work is a constraint-aware local escape domain / upstream placement
co-design around the measured frozen power boundaries and return fields.
Do not rerun these exact fixed endpoint menus or the unchanged staged seed.

Keep `build/additive-first-next-inputs-20260917.json` authoritative. Do not
promote an isolated edge or rerun unchanged domains merely to keep CPUs busy.
EPS/ATX retain their pending paired-interface decision; Hub retains its frozen
power-terminal/local-return dependency and 125-pose history. No schematic,
footprint, power geometry, outline, connector pinout or interface was changed
in this slice.
