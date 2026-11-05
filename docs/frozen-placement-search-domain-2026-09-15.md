# Frozen placement search-domain repair

Continuation of `placement-certificate-parity-2026-09-15.md`. This is a
generic placement-search ownership repair, not permission to change buses.

## Completed preceding cohort

`build/search-budget-followup-suite-20260915/suite.json` finished **13:06:09Z**.
Source/hierarchy/engine signatures are unchanged; PIDs 221139/221140 and
descendants have exited. The scheduling-sensitive scoring exception did not
recur.

- **PCIe3** retained one full craft repair. Its output SHA is
  `400ffdd8635e82b35773cf8377729d8f559628ea5b668445fad05be5384266c8`,
  with local-access failures **two to one** and a matching 83-placement frozen
  state. It remains blocked at placement by the last required ground return;
  there is no routed result or fab approval. Wall time 146.81 s.
- **Hub** proposed two repairs, then transactionally rolled both back because
  they moved frozen +5VSB dependencies. The exact b7cc3990 input remains;
  accepted count zero, no fake improved incumbent. Wall time 191.14 s.

The failure was staged too late: ordinary frozen-placement repair did not
carry the power-owned movement domain into proposal selection. A low craft
score could therefore spend the bounded quota on a move that the final
ownership guard would certainly reject.

## Generic change and limits

`cec_frozen_placement_domain` binds the current PCB and complete frozen state
by content hash. It verifies baseline pose identity before searching, derives
fixed terminals from the existing declared-terminal/native-pad ownership
proof, and passes those fixed references into **every** craft proposal family.
The fixed-root/compound-move filter runs before the fair trial quota. No
product, refdes or coordinate exceptions are in this engine.

Every worker checks the proposed native footprint poses against the same
power-independence rule used at final commit, before materializing or grading
the trial. Final certification checks again, and the existing transactional
commit guard remains independent. The rule's dry-run mode restores in-memory
poses and never writes PCB or state. Stale authority, population/face/outline
changes and frozen-terminal movement fail closed. This is not a coupled power
replanner and cannot grant an interface ECO permission.

Worker failures now retain bounded structured failure samples in evaluation
runtime reports instead of collapsing all ownership refusals into an opaque
materialization failure. The frozen-domain report is also retained in each
craft epoch, including the exact fixed-reference reasons and state hash.

## Validation

- `build/frozen-domain-final-tests-20260915.log`: **555 passed**, plus eight
  subtests, 90.63 s. Includes native dry-run/commit equivalence, source/pose
  restoration, stale-hash, actual contact, worker pre-materialization refusal,
  fixed-compound budget pruning, full pipeline, local PI and routing tests.
- `build/frozen-domain-suite-replay-20260915/report.json`: all six current
  source inputs unchanged; engine unchanged. ATX correctly refuses its
  unavailable required power authority. EPS retains its mechanical/placement
  holds; 12VHPWR retains its separate local-access/USB obligations.
- Hub's sampled-return population is **48 proposals -> 24 retained**, with
  all 24 retained proposals passing native power independence. PCIe3's four
  proposals include **one** native-power-independent candidate. These are
  search-domain proofs, **not complete electrical/craft admission**.
- Native protected-pour replay finds **zero foreign tracks / zero foreign
  vias** in the current Hub, PCIe2 and improved PCIe3 artifacts.
- `build/frozen-domain-control-comparison-20260915.json`: historical protected
  PCIe2 PCB SHA, entire board-regression object and every audit probe exactly
  unchanged. Only the generalization inventory differs; prior strict release
  failures are not waived.
- `build/frozen-domain-generality-20260915.json`: **71 core modules / zero
  core violations**, **380 broader runtime findings** remain.

## Verified current pass reviews

Port 8090 `/api/archive` contains both immutable entries:

- `pass-search-budget-followup-suite-20260915-pcie-8pin-3port-07787c328f`
- `pass-search-budget-followup-suite-20260915-hub-standard-rev2-e82f2dcee6`

Both are labeled **BLOCKED / placement / NOT FAB SIGNOFF**. Native body-free
panels were visually inspected. The final gallery is
`C:/Users/Admin/Documents/CEC-Board-Reviews/search-budget-followup-suite-20260915/all-boards-6c7b87ea65a398db.png`,
SHA `6c7b87ea65a398db63b254a448bd3b798222d54bb965f7638725a1249b669a2f`.
The b6bd7df9 gallery was an intermediate PCIe3-only completion with Hub still
running; do not use it as the final pass view.

## Next bounded cohort

Harness `tmp/frozen_domain_followup_20260915.py`; output
`build/frozen-domain-followup-suite-20260915/suite.json`. Explicit input plan
`build/frozen-domain-inputs-20260915.json` verifies completed placement journal
hashes, including PCIe3's actual 400ff result. No diagnostic or old routed
fallback is used.

Hub and PCIe3 run concurrently, two workers each, 12 trials/two craft rounds,
one epoch, eight routing passes only on placement admission, 600-s board
budget, 120-s priority allowance and 16-GiB free floor. Preserve other
incumbents and EPS/ATX coupled-interface holds. Inspect processes and the
current journal before editing engines or dispatching another job.

Dispatched **13:36:30Z**: Hub PID **249784**, PCIe3 PID **249783**, parent
session **26365**. Both passed source intake and entered placement. Hub's
round-one population is 2288 (previous 3404), selected 12; PCIe3 starts from
the verified one-failure incumbent. These are launch/proposal observations,
not new accepted-geometry claims. WSL free space remains 68 GiB.
