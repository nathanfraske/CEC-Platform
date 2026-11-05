# Stop recurring mating conflicts before a wave — 2026-09-20

## What changed

The paired-row compiler already repaired the bad body-only pitch producer,
but canonical campaigns could still enter setup/normalization before reaching
that refusal. The new source-bound dispatch gate consumes the same compiler
receipt before a campaign starts any worker. The direct full-pipeline entry
also journals this gate before route-authority setup or source normalization.

The resolver uses the declared root schematic, not candidate filenames or
hard-coded board exclusions. A declared interface needs one unambiguous,
positive compiler receipt; missing, ambiguous or false evidence refuses.
Boards without a declared paired row continue to their existing gates. A
positive compiler receipt is **not** a physical mating or fabrication pass.

Refusals retain the conflicting envelopes and available/required span. They
explicitly report `retryable_without_geometry_change=false` and require a
mating-contract or installed-envelope change. A changed seed or routing budget
cannot cure the conflict. The gate re-reads the current in-memory receipt on
each call; it does not permanently blacklist a board after its contract is
repaired. Production processes retain their existing immutable-engine checks.

## Physical repair is still pending

No PCB, schematic, footprint land, power bus, outline, or mating-span limit was
changed. EPS and ATX are **not repaired**. The conservative straight-row
compiler still requires 23.1 mm versus 21.0 mm available on EPS, and 42.3 mm
versus 38.9 mm available on ATX. This is a 2.1 / 3.4 mm span shortfall, not a
claim that all alternative arrangements are impossible or that the boards
must grow. Coordinated mating-span changes require an explicit decision under
the user's earlier no-growth constraint, followed by native and assembly checks.

## Validation

- Focused suite: 77 tests pass, including both real conflicting interfaces
  dispatching **zero workers**, unknown/synthetic naming, missing evidence,
  ambiguity, receipt mutation isolation, repaired-receipt re-evaluation, and
  direct-pipeline refusal before normalization or route-authority work.
- The broader run found one legacy test still expecting the refused ATX macro
  to bind. Its success case now uses a valid PCIe macro plus a synthetic
  auxiliary anchor; a separate test asserts the real ATX refusal leaves the
  anchor map unchanged. No production guard was weakened to satisfy a test.
  After that correction, all 83 full-pipeline tests pass. Combined with the
  201 passing tests and 41 subtests outside that file in the broader run, the
  selected regression set is **284 tests + 41 subtests passing**. Evidence:
  `build/mating-dispatch-broad-tests-20260920.xml` (retains the original stale
  test failure) and `build/mating-dispatch-full-pipeline-tests-20260920.xml`
  (complete corrected file rerun).
- Current six-board native replay:
  `build/mating-dispatch-suite-20260920/report.json`, using
  `build/safe-edge-next-inputs-20260920.json` (including repaired VHP edge input).
  EPS: 32 native pad-copper findings / 3 assembly findings, dispatch refused.
  ATX: 56 native pad-copper findings / 6 assembly findings, dispatch refused.
  These are report rows, not unique physical short counts. The other four
  boards retain zero pad-edge, pad-copper and assembly findings in this check;
  this does not clear their separate craft/routing/release blockers.
- All six PCB and source-hierarchy signatures remain unchanged. Historical
  PCIe2 control retains exact PCB hash, board-regression and probe parity.
  Core generic audit passes; no new routing or fabrication promotion occurred.

Do not run another unchanged EPS/ATX placement/routing wave to rediscover the
same geometry conflict, or present these unchanged boards as new candidates.
