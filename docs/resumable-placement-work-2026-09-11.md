# Resumable placement work — 2026-09-11

## Scope and root cause

This slice repairs loss of placement work across bounded attempts. It does not
change electrical limits, grant routing admission, or declare a fabrication candidate.

Fresh placement runs materialization, exact route preflight, and iterative
repair inside temporary directories before returning to the full-pipeline
coordinator. A job can consume its entire budget there without publishing
`02-placement/board.kicad_pcb`. The previous PCIe 3-port pass demonstrated this:
720 seconds elapsed and there was no resumable placement output. A second gap
existed between finalist selection and the later craft-repair return.

Furthermore, authored power tracks are not evidence that residual routing is
complete. Arbitrary routed inputs correctly remain read-only, but a placement
resume needs verified provenance to distinguish its authored copper from such
an input. No board-specific reference or coordinate repair is added here.

## Implemented contract

- `cec_placement_checkpoint.Store` alternates two owned, flat slots. The complete
  PCB/project/route-authority family is copied and hashed before an atomic
  pointer switches to it. Failure before the switch leaves the previous
  complete checkpoint readable. An unowned nonempty directory or symlink slot
  is refused, not adopted or cleared.
- The default family budget is 64 MiB, with two slots per attempt. Known native
  sidecars are size-checked before copying; logs, meshes, and arbitrary directory
  contents are not copied. Old scratch contents are removed only from the
  inactive owned slot. These overwritten scratch generations are not retained;
  the previous active generation remains available.
- Each checkpoint binds the board family, exact board and sidecar hashes,
  schematic/policy/BOM/footprint/blueprint sources, phase, ranking evidence,
  derived pins, and outline. Source intake must pass before publication. Both
  `routing_admitted` and `release_accepted` are always false.
- Coordinator callbacks save materialized seeds before exact route probes,
  completed preflight results, outer-accepted route-placement improvements,
  and the selected finalist before the next craft epoch. Callbacks never enter
  worker-serialized configuration. A rejected inner proposal is not a recovery
  incumbent.
- Verified resumed placement inputs are saved before subsequent expensive
  operations. Unknown routed boards do not acquire placement-resume authority.
- `--continue-suite PATH/suite.json` explicitly selects the previous attempt.
  Stable source/engine provenance at that attempt's exit and current source
  hashes are required. Verified outputs are reused; attempts with no verified
  output explicitly start fresh. Running, stale, changed, or wrong-family
  evidence is refused. This is not a directory-name or modification-time search.
- Interrupted placement previews resolve the atomic checkpoint first, label
  its actual phase, and distinguish checkpoint verification from a completed
  stage journal. Invalid checkpoint evidence never falls back to another board.

Only geometric context is carried into a resumed configuration. Current policy,
source intake, exact protected-copper guards, physical placement checks, priority
route gates, residual routing, and release checks still run normally.

## Validation already completed

- Final focused suite: 184 passed, 13 optional tests skipped in 11.98 seconds.
  `build/placement-checkpoint-tests-20260911-final.log`.
- Wider boundary suite, including native full-pipeline tests and additional
  accepted/rejected-repair and storage tests: 103 passed, 131 deselected in
  61.68 seconds. This overlaps the focused suite; the counts are not additive.
  `build/checkpoint-full-boundaries-20260911.log`.
- Failure injection covers interruption during the PCB/sidecar copy, certificate
  publication, and pointer publication; stale source and project rules; family,
  path, and board changes; ownership; bounded storage; and rejection of weaker
  fallback provenance.
- Real KiCad recovery witnesses: a child process published a source-checked
  12VHPWR or Hub checkpoint, was terminated with SIGTERM, and a new process read
  and verified it. Both PCB files were byte-identical to their inputs. The
  12VHPWR witness retained all 199 protected power primitives. Hub had no
  applicable protected-prefix subset, so its proof is byte identity, not an
  invented protected-power count. End-to-end witness times were 1.83/1.77 seconds.
- Protected PCIe 2-port control: SHA-256
  `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`,
  zero DRC, zero opens, 615 tracks, 226 vias, 1242.073 mm. Score, constraints,
  route-quality and fabrication probe results match the prior control exactly.
  Existing differential-pair/release blockers remain; this is not renewed signoff.
- Generic-core audit passes. Existing wider debt remains: 23 physical-engine
  selectors and 380 runtime selectors. The whole pipeline is **not** being
  represented as fully generic. Summary: `build/checkpoint-validation-summary-20260911.json`.

## Bounded cross-board pass

`build/current-suite-20260911-c` explicitly continues suite B: five verified
placement outputs are continued, while PCIe 3-port starts fresh because B had
no resumable output. Six board jobs run concurrently, two placement workers
each, six craft trials, and a 720-second per-board ceiling. Detailed routing
is allowed only if admission gates pass. Python engine files are frozen for
the entire campaign so every job's provenance can be verified at exit.

All six jobs terminated with source/hierarchy and Python-engine hashes unchanged.
No board reached residual detailed routing or fabrication admission.

| Board | Attempt time | Retained result |
|---|---:|---|
| 12VHPWR | 529.2 s | PCB byte-identical; all 199 protected primitives preserved; two declared critical-route refusals remain |
| ATX 24-pin | 277.2 s | Reported decoupler violations 12 -> 9; strict gate still refuses two supply-proximity violations |
| EPS | 182.2 s | Reported decoupler violations 3 -> 1; current-corridor failures remain on three nets |
| Standard Hub | 466.2 s | PCB byte-identical; one critical-route refusal; 12/12 repair probes timed out |
| PCIe 2-port fresh-pipeline candidate | 185.9 s | Decoupler violations stay zero; only a fiducial moves 0.5 mm; `/SENSEC1_HI` corridor still fails |
| PCIe 3-port | 720.1 s, capped | Retained an outer-accepted round: critical-route refusals 11 -> 10, remaining critical-pair edges 3 -> 1; placement residual 1 -> 0 |

These reported preflight metrics are not final DRC/open counts. In particular,
12VHPWR's unchanged board reports one deferred `local-cell-access` need after
priority evaluation; its craft gate explicitly permits that pre-route repair.
Its blocking gate is the two critical-route refusals, not a physical board edit.
ATX's reduced aggregate count also includes two new proximity findings; fewer
reported violations is partial progress, not a claim of every constraint improving.

PCIe 3-port's first completed preflight checkpoint was SHA-256
`965b6405dfa48d4219f65661c6048f76752e1e1dc3348692e61a19df74e0efc6`.
The accepted-round checkpoint was
`8e4a7c148507a917466b87a31b8ed45adb734c771f213c75eb9fd78ae6e69d0b`.
Both survive in the two slots, and the atomic pointer selects the latter.
The old pass had no retained output at the same 720-second cap. This demonstrates
work retention, not an isolated routing-speed benchmark.

A separate 120-second real pipeline recovery test then consumed the accepted
PCIe 3-port checkpoint through `--input-board --allow-derived-input`, without
replacement-placement flags. Source intake passed, the new process recognized
the checkpoint and persisted the identical SHA-256 in its own store, and the
new bounded attempt terminated during placement with that input unchanged.
This verifies actual restart wiring, not just certificate parsing; it does not
claim placement completion. Evidence:
`build/checkpoint-actual-resume-20260911/resume-witness.json`.

The campaign directory retains about 38 MiB, including about 4.5 MiB across all
checkpoint slots; approximately 74 GiB remains free in WSL. The six dashboard
image endpoints and the root page returned HTTP 200 from Windows.

Gallery: `build/current-suite-20260911-c/all-boards-b5128a06e5a15df2.png`, mirrored
to `C:/Users/Admin/Documents/New project/review-output/current-suite-20260911-c/`.
`compact-evidence.json` and `suite.json` contain the detailed per-board evidence
and exact dashboard links. The protected routed PCIe control is separate from
the fresh-pipeline PCIe placement shown in this gallery.

## Limits and next diagnostic target

These are **placement artifact checkpoints**, not suspended processes or a
serialized solver frontier. A resumed attempt still recomputes the required
native evidence. They prevent losing a completed placement to a later timeout;
they do not themselves fix an inaccessible pad, power corridor, or failed pair.

Atomic publication protects against process interruption. It is not a tested
power-loss/disk-controller durability guarantee. There is one coordinator writer
per attempt. Completed attempts are immutable; a new pass owns a different store.

Next work must use the completed pass's first failed owner and rejection evidence,
not a manual component move or a larger board by default. Repeated exact search
should eventually retain a source-and-engine-keyed rejected/accepted frontier,
but only after proving its decisions are safe to reuse across attempts.

The completed Hub attempt exposes a concrete scheduling defect: 16 proposed
moves yielded 12 legal critical-route probes, but **all 12** recorded
`pair_search_budget_exhausted: true`. The budget allocator divided 176.35 seconds
over six two-worker batches, reducing a requested 120-second per-pair solve to
29.39 seconds; observed child wall times were about 30.4–31.0 seconds. No trial
reached full evaluation. The resulting `no_critical_route_improving_legal_trial`
is therefore not geometric infeasibility proof. The next generic slice should
admit fewer adequately funded exact probes, distinguish inconclusive timeout
from measured rejection, and carry the unexplored frontier into later attempts.
Do not count these timed-out candidates as proven bad or solve this by enlarging
the Hub outline. Evidence is the first round in
`build/current-suite-20260911-c/hub-standard-rev2/02-placement/operation-priority-repair-nf6iphpw/report.json`.
