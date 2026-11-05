# Test responsibilities

The active model-directed control plane is covered by `test_agentic_*.py`,
the inspection/dashboard contracts, and the independent receiver backends.
The dedicated `model-directed-layout.yml` CI job exercises this current API;
it does not replace the existing physical, source, golden or firmware checks.

The repository also retains a large research/legacy regression corpus from
earlier placement and routing coordinators. Those tests remain discoverable:
they are not silently deleted, renamed out of collection, or marked passing
because a new orchestrator exists. Some encode obsolete fixture expectations
or require optional isolated interpreters. A full sweep is diagnostic until
its actual failures, skips and resource refusals are resolved.

Use `ops/cec_regression.py` for fresh, memory-bounded subprocess batches.
`--module` selects an explicit verification slice. `--module-python` assigns
an optional dependency lane, such as the isolated CadQuery interpreter.
`--keep-going-on-resource-refusal` can inventory the rest after a single
module exceeds its resource budget; it still records that module as unknown
and cannot produce a complete passing receipt. Partial interrupted XML is
never credited as a pass. Existing native constituent deadlines stay <=10 s.

`experiments/legacy_2026` contains provenance-recorded historical helpers
rescued from ignored build output. Only that finite tracked area is on the
normal test import path. New production source and tests must not depend on
arbitrary machine-local `build/` modules.

Native zero-open/error measurements, software test success, process geometry
and current/thermal/manufacturing qualification are separate claims. Synthetic
numerical contracts in a test are not production current or load ratings.
