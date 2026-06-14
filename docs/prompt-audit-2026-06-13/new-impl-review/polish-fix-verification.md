# New-impl Polish Fix Verification (commit 8d11c13)

Adversarial synthesis verification of the Opus-4.8 panel polish fixes
(H1 / M1 / M2 / M3 / L1 / L3 / L4 / L6). Live source `HEAD == 8d11c13`
(`git diff 8d11c13` empty for all touched files). All claims re-derived from the
live source, not the commit message.

## 1. Per-fix table

| Fix | Addresses finding | Regression | Test is real | Call |
|-----|-------------------|-----------|--------------|------|
| H1 | yes | none | yes | **SHIP** — prompt boundary now matches the run() gate exactly |
| M1 | **partial** | none | yes (but masks the real case) | **SHIP-WITH-FOLLOWUP** — fix correct locally, does not reach the cited board end-to-end |
| M2 | yes | none | yes | **SHIP** — pure helper, control-lane no-fire proven |
| M3 | yes | none | yes | **SHIP** — both gates enumerate all 3 suites |
| L1 | yes | none | yes | **SHIP** — coercion correctly placed after the no-verdict/error early-returns |
| L3 | yes | none | yes | **SHIP-WITH-FOLLOWUP** — header right at default; latent truncation count bug |
| L4 | yes | none | **absent** | **SHIP** — fix correct; no direct test (run()-only) |
| L6 | yes | none | yes | **SHIP** — dead tuple gone, `_PENALTY_METRIC` live |

## 2. Overall verdict

**SHIP-WITH-FIXES**

Single most important reason: **M1 does not address its own cited motivating case
end-to-end.** Independently confirmed — `_resolve_board_fence("12vhpwr-standard")`
returns `fence["refs"] == set()` (no `BOARD_PINNED_REFS` entry at
`cec_fullstack.py:1342-1344`; 0 kelvin pairs), so the M1 guard
`if not sense_refs and fence.get("refs")` (`cec_fullstack.py:821`) is **False** for
that board and the SENSE CORRIDOR still silently vanishes in production. The M1 test
masks this by hand-injecting `fence={"refs":{"RS1","U10"}}`
(`tests/test_prompt_audit_fixes.py:335`), which does not reflect the empty-refs fence
the resolver actually produces for 12vhpwr-standard. The fix is correct *where it
fires*; it just does not fire for the case it names. Nothing here is a regression or a
safety break, so this ships — but M1 needs a follow-up to be complete.

All other fixes are clean ships. No regression found in any of the 8 (A/B lane
integrity, fail-safe on broker/container error, the run() `t0_fired` row contract, and
the EI-07 errored-auditor-not-counted invariant are all preserved). Host suite is
green: see §3.

## 3. Completeness critique — what the per-fix verifiers got right/wrong

### Host suite (independently re-run)

```
python3 -W ignore -m unittest tests.test_prompt_audit_fixes \
        tests.test_auditor_dispatch tests.test_ei02_control_lane
```
**Ran 51 tests — OK** (0.005s, no pcbnew/GPU/broker/container; broker/container
errors are simulated and asserted on). Matches the M3 verifier.

### H1 prompt ↔ consumer contract — re-examined directly (verifier was correct)

I read both halves myself and they are consistent:

- **Prompt** (`_audit_prompt`, `cec_fullstack.py:1019-1027`): the placement bullet now
  states "this FIRES the deterministic T0 PLACEMENT ACTUATOR ... **ONLY when a Kelvin
  SENSE net is left unrouted (kelvin_ok=false)**", and explicitly says that for a
  "congested-corridor / no-routing-room placement failure where the gate is NOT a
  stranded sense net, T0 does not act."
- **Consumer** (`run()`, `cec_fullstack.py:1668`):
  `if _t0_should_fire(lane, placement_attr, kelvin_stall, rec["kelvin_ok"]):` →
  helper at `:282-284` = `lane=="augmented" and (placement_attr or kelvin_stall>=K)
  and not kelvin_ok`; then the inner guard `:1669-1671` only acts when a reason
  contains `/SENSEC`.
- **Consistency confirmed:** prompt "kelvin_ok=false" ≡ consumer `not kelvin_ok`;
  prompt "stranded sense net" ≡ the `/SENSEC` inner guard; the lane gate is correctly
  *omitted* from the prompt (the auditor does not pick the lane). No path steers a
  kelvin-passing or non-`/SENSEC` placement diagnosis into an actual T0 firing. The H1
  verifier's "yes/none/yes" is correct.

### What the per-fix verifiers MISSED or got wrong

1. **L4 "order-fragile suite / one FAILURE" claim is WRONG.** The L4 (and L6)
   verifiers asserted that `test_m1_corridor_falls_back_when_no_sensec_match` FAILS in
   full-file order due to cross-test state leakage, contradicting the commit's "159
   green" claim. I could **not reproduce this**: full-file `tests.test_prompt_audit_fixes`
   ran **25 tests OK on 5/5 consecutive runs** and the 3-suite run is 51 OK. The
   "order-fragile" residual is a false alarm — likely a stale/dirty working tree in
   that verifier's environment. The suite is stable.

2. **M1 residual is the real story and the M1 verifier got it right** — but the H1/M2
   verifiers, by declaring the overall picture clean, under-weighted that M1's cited
   case (12vhpwr-standard) is not actually covered end-to-end. I independently
   confirmed empty `fence["refs"]` for that board (§2). This is the one finding that
   moves the verdict off a clean SHIP.

3. **L3 latent truncation count bug confirmed (verifier was right, and it is real).**
   The header counts `n_in` = lines fed into `body` (`cec_fullstack.py:500-502`), but
   truncation slices `body` by **characters** at `:495-496`. I reproduced it directly:
   `promoted_corpus_brief("eps-8pin", max_chars=400, in_family_only=True)` → header
   reports `n_in=6` but only **2** complete `- [` entry lines survive (mismatch). Not
   reachable in production today (default `max_chars=13000`; largest in-family brief is
   12vhpwr-standard at **2661 chars**, eps-8pin **1538**), and the L3 test only
   exercises the default-size path, so it would not catch this. Latent, low priority,
   but worth a FOLLOWUPS line.

4. **L4 has no direct test (verifier correct).** The de-duplication invariant
   (`worker_panel(..., history=records[:-1])`, `cec_fullstack.py:1513`) is only exercised
   through run(), which needs a broker+container. The fix is correct by inspection
   (`records.append(rec)` at `:1503` precedes the call; the slice excludes only the
   just-appended `rec`, which `_panel_prompts` re-supplies as "this round" at `:954-955`),
   but no host test asserts it.

5. **L6 deletion verified live, independently:** `hasattr(cec_fullstack,"PENALISABLE")
   == False`, `_PENALTY_METRIC` present. M3 wiring verified live: all three suites in
   `scripts/checklist.sh:65-67` and `.github/workflows/kicad-checks.yml:79-81`.

### Residual gaps → FOLLOWUPS.md lines

- **[M1] 12vhpwr-standard SENSE CORRIDOR still vanishes silently in production.**
  `_resolve_board_fence("12vhpwr-standard")` yields empty `fence["refs"]`
  (`cec_fullstack.py:1342-1344` has no entry; 0 kelvin pairs), so the M1 fallback guard
  `and fence.get("refs")` (`cec_fullstack.py:821`) is False. Fix: add a
  `BOARD_PINNED_REFS["12vhpwr-standard"]` entry (its RS*/INA240 sense refs) **or**
  broaden the M1 fallback to derive sense refs from `manifest.net_refs` when the fence
  is empty; then change the M1 test to drive a fence produced by `_resolve_board_fence`
  rather than a hand-injected `{"refs":{"RS1","U10"}}`.
- **[L3] Latent header/shown count mismatch under truncation on the `in_family_only`
  path.** Header `n_in` counts lines fed in, not lines surviving the char-slice
  (`cec_fullstack.py:495-502`). Reproduced at `max_chars=400` (header 6, shown 2). Fix:
  trim `body` to a whole-line boundary before computing the header, or count surviving
  `- [` lines; add a truncated-`in_family_only` test asserting `header == shown`.
- **[L4] No host test for the worker_panel history de-dup invariant**
  (`cec_fullstack.py:1513`). Add a `_panel_prompts`-level assertion that the current
  round (`rec`) appears 0 times in the trajectory when `history=records[:-1]`, mirroring
  the existing `PanelRedesign` tests.
- **[H1 coverage]** No run()-level firing test asserting `gr02_repair` IS called for a
  `/SENSEC` + `kelvin_ok=False` augmented round and NOT for `kelvin_ok=True`. The
  extracted `_t0_should_fire` helper is unit-tested, but the `/SENSEC` inner guard
  (`cec_fullstack.py:1671`) is not asserted end-to-end. Low priority (guard is
  pre-existing and unchanged).
