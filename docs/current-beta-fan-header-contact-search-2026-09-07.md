# Current BETA fan header and contact-space placement search

2026-09-07. The fan header is populated in the current source and regenerated
placement. The PCB is still a placement-review artifact, not routing/fab approved.

## Version verification and the actual discrepancy

Ran `git fetch origin --prune`, inspected the current-BETA manifest, and compared
the current hierarchy against all fetched branch tips. No branch switch, merge
or overwrite of existing work was performed.

- Current handoff branch: `agent/pcb-pipeline-audit-repairs-20260801`, HEAD
  `069a4126ac4ad5ca7ab51012483491c31b0ac521`.
- Fresh `origin/main`: `b987ce5aed5e24282ef3b6c044e9be36957ac464`.
- Before this edit, `beta/12vhpwr-standard/01-input.kicad_sch` had the same Git
  blob in the working tree, main and handoff:
  `22a7f93b469148810a2a2321592a9b3f72d5c11e`.
- Current design authority remains the manifest-selected hierarchical
  `12vhpwr-standard-module.kicad_sch` plus its eleven child sheets. Stale root
  and older candidate PCBs were not used as netlist authority.

Evidence: `build/12vhpwr-fan-header-authority-20260907.json` records refreshed
remote commits, hierarchy blobs, alternate BETA schematic paths and working
differences before this edit. Existing local supply/decoupling edits were preserved.

J2 was already present in the hierarchy and in placement. Its native schematic
flag was `(dnp yes)`, its value included `(DNP)`, the tracking BOM marked DNP,
and the assembly BOM omitted it. The sheet note explicitly preserved a historical
optional-fan assembly decision. This was not a missing-header placement or an
old-board substitution. The prior response did not distinguish these states
clearly enough.

## Header change and verification

Per the owner's request, J2 is now `(dnp no)`, value `CEC_FAN_3P`, and included
once in both BOMs. Its unchanged sourced part is JST B3B-PH-K-S(LF)(SN),
LCSC C131339, with the existing three-pin vertical JST-PH footprint. The visible
sheet title is now `FAN CONTROL + TACH`; the note records the population decision
without preserving contradictory DNP instructions.

Native regenerated PCB verification:

| Item | Measured result |
| --- | --- |
| Reference | J2, exactly one instance |
| Position | x=48.5 mm, y=23.5 mm, rotation 90 degrees |
| Native assembly state | Fitted, included in BOM and position files |
| Pin 1 | `/01-input/FAN_RET`, switched return through Q1 |
| Pin 2 | `/FAN_12V`, pre-shunt 12 V feed |
| Pin 3 | `/01-input/FAN_TACH` |
| Courtyard | x=45.655..50.245 mm, y=19.455..27.545 mm |

The retained 58 x 80 placement has no pad/courtyard violations. Header connection
topology did not change. This is connectivity identity, not a claim its traces
are already routed. Tracking BOM retains 103 unique references; the assembly BOM
increases from 101 to 102. FL1 remains DNP. The spreadsheet workflow checked
before/after views, reference uniqueness, quantities and preservation of all
unrelated cell values without changing either CSV schema.

Native schematic ERC remains zero errors and 100 warnings. The actual fan model,
standoff, harness compatibility, powered-fan losses and airflow/temperature
qualification remain open. Fitting a header does not qualify cooling.

## Generic search slice

The coarse macro placement lattice can miss a legal cavity narrower than its
grid pitch. A new bounded contact-space fallback in `cec_cell_packing` subtracts
every macro member's obstacle-expanded forbidden region from the permissible
origin region, then samples cavity interiors and boundaries. It does not discard
satellites or reduce clearance to get a fit.

The adapter calls this only after the original lattice fails across its allowed
rotations. Existing legal lattice results remain unchanged. Original edge bands,
partitions, overhang limits and final courtyard checks still apply. The primitive
contains no product, net, refdes or coordinate repair rules. It is capped at 256
sites and 4096 member/obstacle exclusions per call; exceeding a budget refuses
the fallback, never truncates the obstacle list. It is not an exhaustive solver
or a proof that a failed board outline is impossible.

Validation includes a two-part synthetic macro in a 0.3 mm-wide legal-origin
band missed by the 1.5 mm grid, obstacle clearance for every returned member,
budget refusal, deterministic repeats, existing legal-result preservation and
native assembly-flag changes in both directions.

Read-only actual-geometry replay found seven legal sites for an illustrative
three-part group from the PCIe control, with all member/obstacle checks passing.
The equivalent Hub geometry replay found no site and refused. These are geometry
replays, not new electrical-grouping or board-closure claims. Neither board changed.
Evidence: `build/fan-header-contact-cross-board-20260907.json`.

## Bounded experiment result: no compaction win yet

One fresh strategy/seed was run on each of three outlines with three workers.
The placement stage took 166.6 seconds versus 158.0 seconds in the previous
experiment; this single comparison is not a controlled speed benchmark.

| Outline | Previous residual | New residual | Admission |
| --- | ---: | ---: | --- |
| 58 x 80 mm | 0 | 0 | Geometric baseline retained; nine decoupling findings |
| 58 x 72 mm | 11 | 12 | Rejected; MCU bounds/edge/courtyard failures |
| 58 x 64 mm | 19 | 19 | Rejected; MCU bounds/edge/courtyard failures |

The contact-space feature solves its synthetic failure class but does **not**
solve this board's compaction problem. The 72 mm rejected candidate worsened by
one residual. No failed candidate displaced the valid geometric baseline. No
detailed routing or fabrication promotion was started. Next work must address
joint row/macro/connector reservation and the remaining local supply cells,
not claim that a finer search alone solved the geometry.

455 tests passed, 13 skipped in the broader suite. After a formatting-only
cleanup, the 33 directly affected tests pass again. `git diff --check` is clean.
The archived PCIe score and its existing release-blocker details remain unchanged:
0 DRC, 0 unconnected, 615 tracks, 226 vias, 1242.073 mm trace length. Root/staging
12VHPWR, older 12VHPWR candidate, Hub candidate and archived PCIe hashes remain
unchanged. This is not a claim that the full pipeline is now generic or fab-ready.

Run evidence and no-model render:
`build/12vhpwr-fan-populated-contact-search-20260907/comparison.json` and
`02-placement/candidates/002/placement.png` beneath that run directory.
