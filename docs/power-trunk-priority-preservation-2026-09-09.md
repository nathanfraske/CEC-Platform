# Power-trunk priority: regression, cause and correction

## Confirmed regression

The visible fourth front-side input bus was displaced 3.5 mm sideways in
`12vhpwr-route-ready-v6-20260909`, not newly altered in the following V8 slice.
V8 inherited V6's copper geometry exactly. The change followed a capacitor
seat exchange: C9 was placed at the vacated C24 position, rotated 180 degrees.
Its foreign pad occupied the straight bus corridor. The force-lane constructor
then used its legacy hook-descent fallback and still reported all six lanes
successfully built. A same-count constructor gate did not preserve the route.

`build/power-bus-forensic-20260909.json` contains normalized track/via comparisons
across the saved September 7 and September 9 checkpoints. The affected input
net lost two straight-path primitives and gained four hook primitives in V6.
Other earlier reconstruction differences are retained in that report rather
than being attributed to this particular change.

## Generic protection added

- A resumed `Candidate` captures a primitive-subset contract for substantial
  locked current trunks. Discovery uses locked copper geometry, not board,
  reference, net-name or part-number selectors. Fully connected narrow local
  links do not freeze an entire shared rail merely because they are locked.
- The contract is a dataclass field, so replacement/copy and worker transport
  retain it. Every materialization checks actual coordinates, layers, widths
  and via geometry; same counts or same length cannot conceal a detour.
- The full placement stage also checks its original contract before writing
  any resumed authored-prefix checkpoint and at final admission. Later repair
  phases cannot silently certify modified trunks as a new baseline.
- The legacy input hook-descent fallback is removed. A foreign component in
  that reserved corridor now produces a placement refusal instead of moving
  the high-current bus around the component.

This is protection for existing locked track/via trunks. It does not replace
the separate frozen-pour geometry contract or declare that every legacy
pipeline module is now generalized. Deliberately replacing the entire layout
remains a distinct workflow, not an ordinary placement resume.

## Corrected checkpoint

`build/12vhpwr-power-priority-restored-20260909/trial-00/board.kicad_pcb`

The restoration probe takes V5's pre-detour power contract and V8's current
placement as explicit inputs. It discovers the interfering capacitor from
foreign-pad/copper intersections and samples bounded free-space contact sites
and orthogonal rotations. No hard-coded repair displacement or target-ref
selector is used by that search. Its first proposal rotates the capacitor
90 degrees at the **same coordinates**; no board growth, connector movement or
other component change is needed. All 199 protected power primitives match
the pre-detour contract, including both sides of the board.

- Placement craft admission: pass; no deferred local-access item in this probe.
- Native DRC: 12 -> 12; opens: 246 -> 246.
- Tracks: 417 -> 415; vias: 12 -> 12.
- Total track length: 844.0186 -> 837.8186 mm (6.2 mm detour removed).
- All current hierarchical schematic and protected control hashes unchanged.
- All previous bypass-link placement improvements retained.
- Board SHA-256: `0301b45303a891f7c8d3a58e74cf85dbc476c46f83c25e7243b8b9b91a8f5cde`.

The board is a **placement checkpoint, not routing-admitted or fabrication
approved**. The CAN/USB priority-route probes have not been rerun for this
corrected checkpoint. The DRC and open counts must not be hidden by the
improved picture.

## Regression evidence

- `build/power-priority-tests-20260909.log`: 293 passed (craft, decoupler,
  parallel-link and primitive-contract suites).
- `build/power-priority-stage-tests-20260909.log`: 83 passed (full-pipeline and
  contract suites). These selections overlap; do not sum as unique tests.
- `build/power-priority-rehydration-test-20260909.log`: focused native replay
  initially exposed the rehydrated materializer's early-return path bypassing
  the newly added end guard. The guard now also executes at that return. The
  combined final suite reruns this negative test: actual rehydration must
  enforce the trunk contract, while ordinary narrow-link reconstruction
  remains supported.
- `build/power-priority-final-tests-20260909.log`: combined suite after the
  early-return correction, including the actual rehydration negative test:
  **372 passed** in 98.27 seconds.
- `build/power-priority-production-resume-20260909.log`: corrected 12VHPWR
  checkpoint rehydrated and rematerialized through production code; all 199
  protected primitives and the complete power-net geometry signature remain
  identical. The temporary replay board is not promoted or retained.
- `build/power-priority-pcie-regression-20260909.json`: immutable PCIe control
  retains 0 DRC, 0 opens, 615 tracks, 226 vias, 1242.073 mm and its existing
  broader release blockers. Full release acceptance remains false, unchanged.
- `build/12vhpwr-power-priority-restored-20260909/closeout.json`: final identity,
  primitive-preservation, score, source and PCIe comparison evidence.

Continue subsequent placement/routing work from this corrected checkpoint,
not V8's inherited detour. Keep both historical inputs unmodified for audit.
