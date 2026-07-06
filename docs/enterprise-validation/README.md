# Enterprise requirements verification validation

This directory holds the **requirements-verification matrix**: a machine-generated
cross-reference tying every REQ ID in the 6 enterprise requirements registers
(`docs/enterprise-requirements/*.md`) to a named verification artifact (bench spec,
FMEA template, process doc, or a generic inspection/analysis/test/demonstration
bucket) and a lifecycle status (`planned` / `drafted` / `executed`).

- **Generator**: `scripts/cec_req_verify_matrix.py` — parses the registers (same
  file discovery + row regex as `cec_req_lint.py`, imported directly) and renders
  `verification-matrix.md` from `verification-map.json`.
- **`verification-map.json`**: the human-maintained map. Each entry is
  `{"artifacts": [...], "status": ..., "statement_hash": ...}`, keyed by REQ ID.
  Edit this file, not the generated matrix, to change an artifact assignment.
- **`verification-matrix.md`**: generated output — one row per REQ (verify tags,
  mapped artifact(s), status, statement-hash prefix), plus map-hygiene and bucket
  counts. Regenerate with `python3 scripts/cec_req_verify_matrix.py`.

## `--check` — the rot-detection contract

`python3 scripts/cec_req_verify_matrix.py --check` exits 1 if:
1. any REQ ID in the registers has no `verification-map.json` entry (unmapped),
2. any map entry's REQ ID no longer exists in any register (orphan — a retired
   or renamed ID that needs a human edit to the map), or
3. a mapped REQ's live statement text hashes differently than the
   `statement_hash` stored in the map (**verify-tag rot**: the REQ was reworded
   or re-scoped since someone last reviewed its artifact assignment).

## `--freeze` — re-stamping after review

`python3 scripts/cec_req_verify_matrix.py --freeze` re-stamps `statement_hash`
for every REQ present in both the registers and the map, to the REQ's current
text hash. Run it only after a human has actually re-read the reworded
requirement and confirmed the artifact assignment still holds — never as a
reflex to silence `--check`.

## Not yet wired into `checklist.sh`

This is deliberate: `--check` is new and unreviewed. The orchestrator wires it
into `checklist.sh` after a human reviews the seed map
(`verification-map.json`, seeded 2026-07-02, all 114 REQs at `status: planned`).
