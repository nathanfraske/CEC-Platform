# Mechanical terminal dispatch and per-pass board reviews

## Implemented

Electrical output-terminal discovery no longer licenses a particular physical
packing algorithm. `cec_synth_pipeline._is_power_terminal` retains the prior
electrical grouping, while `_is_blade` recognizes actual FASTON footprints.
The legacy blade-row packer refuses an unbound non-blade interface before it
mutates any anchors. A fully bound screw interface is excluded from blade slots,
including ground-return allocation and the associated shunt recentering.

This is a generic dispatch and authority rule, not a terminal-specific move.
An unknown screw interface must supply its mechanical macro rather than inherit
4.7 mm blade pitch and a zero-degree rotation. Synthetic renamed interfaces,
partial pin maps, bound screws and unbound real blades have regression tests.

The existing rigid-interface translation API now supports either horizontal
board edge. It derives the datum from rotated electrical pad copper, preserving
all relative contact positions and orientations. EPS's board-local policy binds
its existing `eps-main` contract at the bottom edge. It does not change that
contract's mating pitch or increase the outline. "Qualified" in the existing
API name does **not** constitute physical sample qualification: the XFCN
prototype release gates remain blocked.

## Per-pass reviews

Every completed `cec_board_suite` attempt now invokes `cec_pass_review` by
default. The publisher:

- Resolves only that attempt's explicit journaled board, checking its SHA-256.
  It never searches for the newest filename or substitutes a canonical/older
  board when an output is missing, altered or outside the attempt directory.
- Labels interrupted working placement separately from completed placement
  and detailed-route output. A route interrupted without a journaled output
  is not illustrated with its old placement and called routed.
- Makes an immutable archive snapshot with board-stem sidecars, native top
  and bottom views without component bodies, pass ID, stage, status and hash.
  Missing or failed renders get explicit status cards.
- Atomically publishes the dashboard catalog entry after its images exist.
  These are diagnostic previews, never replacements for routed review authority,
  and never fabricated DRC, thermal or manufacturing signoff results.
- Updates a gallery containing every selected main board after each job ends.
  `--review-dir` additionally mirrors the gallery and individual PNGs into a
  desktop-readable directory, addressing WSL image-path failures in chat.
  Gallery images have content-addressed filenames as well as a convenience
  alias; chat embeds use the immutable name to avoid stale-image caching.

The dashboard was restarted to load the new preview-status handling. HTTP 200
was checked from Windows for the root page and the first new pass's image;
the live catalog includes the new entry with `BLOCKED`, not `CLEAN`.

## Validation

- Expanded tests: **154 passed, 41 subtests passed, no skips**, in 55.37 s.
  See `build/terminal-pass-review-bounded-tests-20260911.log`. An earlier
  redundant run was interrupted after its linear-algebra library oversubscribed
  the CPU during the campaign; the final run limits BLAS/OpenMP to two threads.
  Campaign elapsed times are diagnostic, not a controlled speed benchmark.
- Generic-core audit passes, including the new publisher and suite coordinator.
  Existing legacy debt is unchanged: 23 physical-selector and 380 full-runtime
  findings. This is not a claim that the entire pipeline is already generic.
- Native EPS generator comparison: terminal nontext-bounding-box overlap pairs
  **9 -> 0**. All eight terminals retain the declared 270-degree orientation,
  and neighboring terminal origins are uniformly separated by the existing
  contract's 7.75 mm. This metric is not whole-board placement or route signoff.
  Evidence: `build/terminal-geometry-comparison-20260911.json` and
  `build/eps-terminal-fixed-generator-witness-20260911.kicad_pcb`.
  The completed EPS placement retains the same zero-overlap row and passes
  the whole-board courtyard check.
- Protected PCIe control: identical board hash, entire score, constraints,
  route-quality and fabrication reports against the previous replay. It still
  has 0 DRC / 0 opens / 615 tracks / 226 vias / 1242.073 mm track length.
  Existing broader release failures remain failures.
  Evidence: `build/terminal-pass-pcie-control-20260911.json`.

## Parallel pass and remaining work

`build/current-suite-20260911-b/suite.json` records six simultaneous main-board
attempts, six craft trials, four routing passes if admitted, two placement
workers per board and a 720-second per-job cap. Source and engine hashes are
checked on exit. The engine remains frozen while the cohort runs. Existing
12VHPWR power copper and the protected PCIe review control are not edited.

The prior pass is also published explicitly as `current-suite-20260911-a` for
comparison; its PCIe three-port attempt has a no-output card, not an old board.

Follow-up issues observed during this pass, not fixed by the terminal change:

1. Interrupted placement without its completed stage/prefix provenance can be
   classified conservatively as routed merely because it has copper. ATX's
   retained partial input consequently stays read-only and reports decoupler
   blockers rather than automatically resuming placement repair. Preserve
   copper safety, but carry explicit stage/ownership provenance across such
   checkpoints instead of inferring completion from tracks.
2. Fresh finalist evaluation and craft repair can consume the entire budget
   before writing a selected board into the durable output directory. A bounded
   checkpoint of the selected, explicitly unadmitted candidate is needed so
   subsequent attempts and reviewers do not lose the best evaluated seed.
3. EPS power-corridor feasibility, Hub critical-pair/power cooptimization and
   12VHPWR's CAN_INT/USB route preflight remain separate physical problems.
   Do not waive their gates based on the corrected screw row or a good render.

Final cohort outcomes are summarized in `compact-evidence.json` beside the
suite report and in the per-board `pass-review.json` files.

| Board | Attempt time | Retained result |
|---|---:|---|
| 12VHPWR | 536.8 s | Input unchanged; CAN_INT detour and USB portal deadline still refuse preflight |
| ATX 24-pin | 48.3 s | Input unchanged; decoupler placement blockers remain |
| EPS | 603.2 s | Corrected terminal row and clean courtyards retained; sensing order, decoupling and current corridors still block |
| Standard Hub | 477.2 s | Input unchanged; one declared critical-route refusal remains |
| PCIe two-port fresh candidate | 492.0 s | Decoupler violations 3 -> 0, assigned requirements 13/14 -> 14/14; current corridor `/SENSEC1_HI` still fails |
| PCIe three-port | 720.1 s | Budget exhausted before a selected placement artifact; explicit no-output review card |

All six source/hierarchy and engine checks passed at job exit. No candidate was
promoted and none entered detailed routing. PCIe two-port's placement gains
come from the existing generic craft repairs exercised by this pass, not an
isolated performance claim for the new terminal dispatch rule. After the cohort
finished, the gallery filename/cache handling was tightened and its related
tests rerun; no physical-design changes were made during the cohort.

The missing-selected-checkpoint problem is therefore a concrete next slice,
not a reason to repeat the same long fresh pass unchanged.
