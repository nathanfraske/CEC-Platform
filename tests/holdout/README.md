# Held-out eval pool (CL-11)

The tuning-free complement to `tests/golden/`. **Goldens are frozen regression anchors and
are BURNED for tuning the moment a prompt or charter is adjusted against them** — the
framework's verify steps literally instruct adjusting against the goldens, so a separate
pool that tuning never touches is what keeps evaluation honest.

## Rules

- **Never tune against this pool.** No prompt, charter, threshold, or check parameter is
  adjusted to make a holdout case pass. A holdout case is consulted only when EVALUATING a
  candidate change (CL-19 extractor eval, CL-22 panel seat gating, CR-03 adoption replay).
- **Grown, not authored:** entries arrive from every adjudicated override (an owner verdict
  that contradicted a tier), every CL-13 bench label, and every escape — never invented.
  Each entry records its provenance (decision_id from the ledger, or the bench run).
- **Thin at first is correct.** An empty pool is honest; a padded one is not. The pool's
  size is itself a reported metric, never narrated past its N (the DF-04 floor discipline).
- Format mirrors `tests/golden/fixtures.json` (board state + expected flag IDs), one
  subdirectory per case, manifest in `holdout.json` once the first case lands.

## Why this directory exists empty

Created with CL-11 (2026-06-10) so the SPLIT exists before the first adjudicated override
arrives — capture cannot be retroactive (the DF-01 argument applied to eval data). The
first entries are expected from the wave-3 morning-bundle verdicts (CL-12) and the first
bench labels (CL-13/SB-06).
