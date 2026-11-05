# Repository module map

The active orchestration has one owner: `src/cec_pipeline/`. The root is not
an output workspace. Add new orchestration to the package; do not add another
dated repair runner or a second autonomous pipeline.

Legacy job retirement is recorded in `legacy-job-retirement-2026-11-05.json`.
The old wave workflows, wrappers, local manager and callback bridge are gone;
remaining old-named modules are import-only compatibility libraries, not
standalone jobs. Current board policy is declarative and no longer imports a
wave runner. Tests solely for removed job APIs retired with those APIs;
physical/material receiver tests and immutable controls remain.

| Directory | Role |
| --- | --- |
| `src/cec_pipeline` | Direct/MCP protocol, immutable intake, observation, explicit construction, receiver adapters, campaign state, review and regression orchestration |
| `scripts/cec_*.py` | Retained native CAD/physical-domain validators and compatibility backends; stable imports for the existing regression corpus |
| `ops` | Thin operator commands for publication, inspection, checkpoint export, regression and read-only repository audit |
| `beta` | Current nine-board design/BOM/policy sources; ARGB schematic draft is not part of the PCB closure suite |
| `checkpoints` | Pinned portable review controls and their exact native evidence, not manufacturing deliverables |
| `lib` | Shared symbols, footprints, part/process data and models |
| `tests`, `corpus`, `golden` | Regression code and explicit native fixtures; numerical fixture contracts are not hardware ratings |
| `experiments/legacy_2026` | Dated, provenance-recorded helper source recovered from ignored build output; not the production orchestration API |
| `docs` | Controlled specifications, current workflow documentation and clearly dated historical evidence |
| `firmware` | Firmware, with its own CI/build workflow |
| `.cec`, `tmp`, `output`, `out`, `build` | Ignored runtime/build output. Existing historical tracked controls are preserved for compatibility; new source must not be hidden here |

The active package separates geometry, connected cells, power construction,
native observations, receiving, execution, identities, campaigns, checkpoints,
library relocation, issue reporting, protocol and review selection. The two
`scripts/cec_agentic_*.py` files are compatibility launchers, not copies of
that implementation.

Moving every retained validator into new paths at once would break thousands
of established imports without improving its electrical contract. Those
backends remain explicit compatibility dependencies. Migrate a backend only
with its import shim and regression slice; do not confuse a rename with a
physical validation improvement.

## Durability and hygiene

Before consolidation, the dirty tree, binary working diff, untracked files and
ignored helper sources were archived outside the checkout. No user source,
Git history, historical board control or private artifact was discarded.
Runtime directories are ignored, not recursively erased.

The 57 recovered legacy helpers have original paths/hashes in
`experiments/legacy_2026/source-origins.json`. Tests import this finite tracked
area through `tests/conftest.py`, never arbitrary ignored `build/` contents.
The canonical regression runner binds current sources and portable controls;
an incomplete run or changed source epoch cannot claim a full pass.

Use `python3 ops/cec_repository_audit.py --output /outside/repo/inventory.json`
for a read-only path/category/dependency inventory. Do not stage generated
logs, cached jobs, KiCad locks/preferences, credentials or local inspection
indexes. Explicit checkpoint receipts and their native assets are intentional
versioned exceptions, with exact identities and qualification scope.

## Validation and review

Use the workbench for model-authored changes, `ops/cec_regression.py` for
memory-bounded tests, and the inspection viewer for per-layer visual review.
The existing CI and physical/current/Kelvin/assembly gates remain in place.
No clean DRC count authorizes fabrication or bypasses unresolved qualification.
