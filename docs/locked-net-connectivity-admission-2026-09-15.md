# Whole-net connectivity is not pad access

## Completed placement cohort

`build/frozen-domain-followup-suite-20260915/suite.json` finished **13:39:42Z**.
Its Hub/PCIe3 processes and descendants have exited. Source, hierarchy and
engine signatures passed. Hub retained **two adjustments without rollback**,
SHA `eab81afc6d0d155539a365450fd05bff37832d17243ae36d4613d1f930360b25`,
but still has **five** local-craft failures. The C27/U7 local-access distance
improved 1.38 to 1.28 mm; this is not clearance or complete-return admission.
PCIe3 retained the identical `400ffdd8635e82b35773cf8377729d8f559628ea5b668445fad05be5384266c8`
one-failure placement. No board reached routing or fab admission in that cohort.

Current body-free previews were visually inspected; port 8090 archive includes
`pass-frozen-domain-followup-suite-20260915-hub-standard-rev2-a58be4104a` and
`pass-frozen-domain-followup-suite-20260915-pcie-8pin-3port-d8cb2771e7`.
Final two-board gallery SHA
`4147009b385b8a30ce82fff9fdf824fadd40a0b8ad9e39287590fe8b548a5ac6`,
file `C:/Users/Admin/Documents/CEC-Board-Reviews/frozen-domain-followup-suite-20260915/all-boards-4147009b385b8a30.png`.

## Proved defect and why it persisted

The shared `cec_fr.owned_locked_nets_board` checked only that every physical
pad touched some locked copper. It did **not** require those separate stubs
to connect to each other. This predicate feeds critical-prefix admission,
DSN whole-net exclusion, keepouts and completed-net suppression during import.
Some downstream pair checkpoints independently rejected disconnected stubs,
but ordinary-net exclusion did not share their stronger proof. Two regression
tests explicitly preserved the weak upstream result and tested only a later
pair-specific refusal. That localized defense left the generic defect intact.

Native read-only reproduction:
`build/locked-connectivity-probe-20260915.json`, exact PCIe2 partial winner
SHA `fbaa5161199590c28ad54062d3eb6c4d8470b1684469b27a75700ce01956a1e7`.
The old predicate marked `+5VSB` and `/I2C_SDA` complete despite separate native
pad islands. Both also appear in that candidate's `completion_report.completed_nets`
and final unconnected-net report. The 12 openings include two +5VSB gaps and
one I2C_SDA gap. This proves incorrect repair exclusion for these two nets;
it does **not** explain the other nine openings or prove a legal path exists.

## Generic fix

`cec_locked_net_ownership` builds a private native connectivity graph from
physical pads and locked tracks/vias only. Every terminal **and locked copper
item** must belong to one component before granting whole-net ownership.
Mutable bridges and pours cannot supply missing locked ownership. Native arc
geometry, mid-track contact, actual via layer spans, duplicate pads and plated
barrels are retained, not approximated by endpoint distance or arc chords.

Explicit completion claims are independently revalidated on the full native
board before backend routing and after import/fill. This permits separately
admitted plane-connected nets while reopening disconnected stale claims.
Reopening does **not** unlock their protected prefixes. Structured certificates
and demoted claims are retained in route parameters/import reports. Evidence
errors fail closed. Current/spacing/width rules and all physical sources remain
unchanged. Final native DRC/connectivity and release gates remain mandatory.

The API behavior was checked against installed KiCad 10 bindings and
[KiCad's native connectivity implementation](https://docs.kicad.org/doxygen/connectivity__data_8cpp_source.html).
`GetConnectedItems` performs a native connectivity-cluster search; the private
graph uses `Add` without mutating the original board's item set.

## Verification

- `build/locked-connectivity-final-tests-20260915.log`: **816 passed plus 25
  subtests**, 104.40 s. Includes loaded native disconnected stubs, mutable and
  locked bridges, THT contacts, blind-via span negatives, arcs versus chords,
  duplicate physical lands, zone-only bridges, route/import stale claims,
  read-only serialization and existing craft/route suites.
- `build/locked-connectivity-suite-replay-20260915/report.json`: six current
  board families, exact verified stage lineage, unchanged input/hierarchy/
  engine hashes. All locked-complete nets are independently connected in the
  full native board. PCIe2 reopens exactly the two stale claims above.
  Counts of connected nets in placement boards are **not route completion**.
- `build/locked-connectivity-control-comparison-20260915.json`: protected
  historical zero-open PCIe2 SHA, complete regression object and all probes
  unchanged. Only generalization inventory changed; its pre-existing strict
  release failures remain, not waived.
- `build/locked-connectivity-generality-20260915.json`: **72 core modules,
  zero core violations**; **380 broader runtime findings** remain.

## Next bounded parallel replay

`tmp/locked_connectivity_followup_20260915.py` runs Hub, PCIe3 and PCIe2 in
separate canonical pipeline processes, three jobs/two workers each. Inputs
are explicit journal/hash-verified artifacts in
`build/locked-connectivity-inputs-20260915.json`; PCIe2 uses the actual current
partial routed winner, not the historical regression control or an old preview.
12 trials/two craft rounds/one epoch; eight route passes on admission;
1500-s board bounds, 120-s priority allowance, 16-GiB free floor (68 GiB free).

Observe `build/locked-connectivity-followup-suite-20260915/suite.json` and
descendants before editing shared engines or dispatching another job. VHP's
coupled escape failure and EPS/ATX's coupled terminal geometry holds are not
cleared by this change. Their six-family checks remain visible; unchanged
expensive failed waves are not automatically restarted. No output is promoted
or granted fab approval by this harness.

### Live observation at 14:21Z

Dispatched **14:15:31Z**, parent session **67571**. Hub PID **271058** finished
in 197.66 s with another two retained adjustments (SHA
`ce61d1a11de36b52f248c2fc86071e1f10aa24299eef8a085cb2fd31aca0fe3d`), still five
local-craft failures. PCIe3 PID **271057** finished in 92.53 s with unchanged
400ff geometry and one failure. Their source/hierarchy/engine guards pass.
Do not re-run these exhausted placement populations without a new repair class.

**PCIe2 PID 271059 remains live in precision/detailed routing**. Placement
passed in 29.05 s and route preflight in 147.74 s. There is no new final DRC/
open count yet. The live backend input `/tmp/cec_fr_once_hq_4b8yz/board.dsn`
has SHA `510d956b5e995eaae99470a80f607e1c1d16700f6331409f718fe6d2137ec867`;
its network section retains all **10 +5VSB pads and four I2C_SDA pads**.
This verifies the two falsely completed nets are actually offered to routing,
not just changed in a report. The temporary DSN may disappear at job cleanup.

Current immutable review IDs:
`pass-locked-connectivity-followup-suite-20260915-hub-standard-rev2-e5da398f8f`
and `pass-locked-connectivity-followup-suite-20260915-pcie-8pin-3port-51965f9792`.
Both were checked in `/api/archive`; body-free gallery was visually inspected:
`C:/Users/Admin/Documents/CEC-Board-Reviews/locked-connectivity-followup-suite-20260915/all-boards-bba47cd5db5bce98.png`,
SHA `bba47cd5db5bce982315ae1682699646f3e47fc8d215535cbf740909c48b2e00`.
It explicitly labels PCIe2 **running / no current-pass preview yet**, not an
old board as a new result. Replace this reference with the final hash-bound
gallery only after the entire cohort finishes.

### Next generic performance investigation, not implemented during this cohort

`build/retained-connection-demand-probe-20260915.json` proves the current
PCIe2 input supplies 116 coarse demands, 104 after existing pair exclusion,
of which **36 are already completely connected by locked copper**. Profiling
caught the live process in `cec_coord_router.route_negotiated`; the preflight
spent 147.74 s. This is unnecessary work eligibility, not yet a measured
runtime speedup from a fix. Source SHA remains exact.

Next test moving the exact *retained ownership* qualification ahead of coarse
search, keeping original locked copper as foreign occupancy and retaining
all stackup/terminal index mappings. Do not simply exclude every connected
mutable net: a later stage might remove its bridge. A new generic slice must
prove preservation authority, disconnected-negative cases, six-family replay
and unchanged control before claiming a performance improvement. Separate
placement-return failures still need a legal complete-cell placement domain;
the 0.9/0.5-mm GND via policy was observed, not changed or declared mistaken.
