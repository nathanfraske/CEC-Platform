SHIP-WITH-FIXES

# Adversarial audit — PR #59 (`claude/seat-bakeoff`)

**Scope:** cross-model seat bake-off harness (`scripts/cec_seat_bakeoff.py`, 945 LoC new), the cloud-seat shim added to `scripts/cec_judge_local.py`, and the bake-off tests (`tests/test_seat_bakeoff.py`). Head: `c23ea10`.

**Verdict basis:** No blocker, no high, no data-corruption or hard-gate break. All findings are confined to an internal **research/seat-selection bake-off harness** whose output is gitignored and never on the routing / corpus / golden-gate critical path. The system stays fail-safe end-to-end (every cloud-shim caller falls back to the deterministic policy). The two **medium** scorer mis-grades and the two **medium** test gaps are real and degrade the very measurement the PR exists to make, so they should be fixed before merge — hence SHIP-WITH-FIXES, not SHIP.

I independently reproduced the load-bearing claims on the branch source: the 18-test suite passes; BT-1's marquee test still passes with the OVERFIT/generalizes threshold **inverted** (genuine tautology); F1/F2/F4/F5 scorer mis-grades reproduce exactly; the cloud shim raises a bare `FileNotFoundError` (not the promised diagnostic `ValueError`) when the `claude` CLI is absent.

## Confirmed findings (refuted/not-a-bug dropped)

13 confirmed (CSS-3 dropped as not-a-bug — the "best-effort-validate" comment is accurate: conformance is enforced downstream by the scorer's `schema_ok` and the fail-safe `make_manager`).

| ID | Sev | Title | One-line fix |
|----|-----|-------|--------------|
| F1 | medium | `score_t1` gives a FALSE 1.0 to an intent that anchors one waypoint into a **fenced** sense ref (only all-fenced is caught) | Replace the `all(r in frefs ...)` guard with `any(...)` — flag a fence violation if **any** waypoint ref is fenced (matches the harness's own per-ref `_fence_line`). |
| F2 | medium | `score_t1` awards full credit to **no-op** intents (`waypoints: []`) the real seat discards | In the per-intent loop, don't count an intent toward `valid` unless it has ≥1 usable waypoint ref. |
| BT-1 | medium | Report generalize/overfit test is a tautology — passes with **inverted threshold** AND with a zeroed mean | Parse per-variant lines: assert A→`generalizes` / B→`OVERFIT-prone` and assert the printed means (A≈0.875, B≈0.575). |
| BT-2 | medium | The local **scribe-rescue** path (a load-bearing objective signal) has **no test** | Monkeypatch the transport to return empty `content` + JSON in `reasoning_content`; assert `parsed!=None`, `scribe=True`, and `_produce_one` sets `scribe_used=True`. |
| CSS-1 | low | Non-`TimeoutExpired` subprocess errors (missing CLI, `PermissionError`) escape the retry loop and bypass the diagnostic raw-snippet path | Broaden the inner catch to `(subprocess.TimeoutExpired, OSError)` so spawn failures retry and surface the unified `ValueError`. |
| CSS-2 | low | `_extract_json_obj` locks onto the **first** balanced brace-pair; a balanced non-JSON span in prose before the real object makes `json.loads` raise | On a `json.loads` failure of a balanced span, keep scanning for the next top-level brace-pair instead of returning/raising on the first. |
| CSS-4 | low | `temperature` is accepted by the cloud shim but **never applied** — swarm-replica diversity is silently lost on a cloud seat | Document `temperature` as a no-op on the CLI path (or drop the param); vary the prompt seed if off-box diversity is ever needed. |
| F3 | low | Quality-judge leave-one-out is exact-string only — `cec-worker` can judge same-family `cec-worker-vision` | Skip on a family key (`cec-worker*`), not the raw model string, or document that family overlap is accepted (panel is the secondary signal). |
| F4 | low | `schema_ok` ignores `minItems`, so a scribe-rescued degenerate waypoint (`between:['U10']`) passes structural validation | Add `if 'minItems' in schema and len(obj) < schema['minItems']: return False` in the array branch. |
| F5 | low | `score_t5` allows `failure_class='none'` on the gate-**failing** `drc-residual` case, contradicting the harness's own decision-tree prompt | Drop `'none'` from `drc-residual`'s `expect_fclass` (leave `{'routing','constraint'}`). |
| F6 | low | `report()` raises `FileNotFoundError` instead of the intended "no results" when neither `produced/` nor `judged/` exists | Guard with `if not os.path.isdir(src): print('no results...'); return` before `os.listdir(src)`. |
| BT-3 | low | `score_t4` scores an **empty** lens list as `schema_ok=True, correctness=0.5` (vacuous-`all([])`); latent today | Guard with `if not out_items or not all(each_ok): return schema-fail/0.0`; test the empty-list and all-None panel paths. |
| BT-4 | low | Untested scorer penalty branches: T1 `unknown_nets` (corr=0.0) and T5 `lever_ok=False` (−0.1) | Add a T1 unknown-non-fenced-net case (→corr 0.0) and a T5 off-topic-lever case (→`lever_ok=False`, corr<1.0). |
| BT-5 | low | `_extract_json_obj` brace-matcher's distinguishing behavior (first complete object) is untested — committed inputs pass under a naive greedy regex too | Assert `_extract_json_obj` on "object + braced trailing prose" returns the **first** object only. |

## The single most important thing to fix before merge

**Fix the two `score_t1` mis-grades together — F1 (fence) + F2 (no-op intent).** T1 correctness is the PR's stated **primary** decider for production seat/prompt selection, and both defects pull in the same dangerous direction: a model is rewarded for emitting an intent that either steers a stub **into** the Kelvin/sense corridor the fence protects (F1) or actuates **nothing** that the real seat would keep (F2). Both make the bake-off prefer a prompt/seat that the live `intent_manager` contract would reject, weakening the exact axis the harness is built to validate. The fix is two one-line changes (`all`→`any`; require ≥1 usable waypoint) and is low-risk. **BT-1** should ride along — without it, a future revert of the generalize/overfit threshold lands silently green.

(If you want to merge faster: F1/F2/BT-1/BT-2 are the four mediums; everything else is low-severity polish and fail-safe, safe to defer behind a follow-up.)

## #56 / #59 composition on main

**Conflict outcome: clean.** `git merge-tree --write-tree origin/claude/prompt-tier-audit origin/claude/seat-bakeoff` returns exit 0 with **zero** conflict markers — the two PRs auto-merge.

**But the prompt's premise ("no shared file; loop changes are #56-only") is imprecise.** Three scripts are touched by **both** PRs:
- `scripts/cec_fullstack.py`
- `scripts/cec_overnight_directed.py`
- `scripts/cec_verifier.py`

The overlaps edit different lines within shared regions (e.g. both touch `cec_verifier.py:55`, but the rest of #56's `cec_verifier` hunks — `VERDICT_SCHEMA`, `CHARTERS` — don't collide with #59's), so git's 3-way merge resolves them without markers. Correctly stated: the **cloud shim** (`cec_judge_local.py`) and the **bake-off harness** (`cec_seat_bakeoff.py`) are indeed #59-only; the loop/intent-seat fixes are #56-led but **not** file-disjoint. **Whichever PR merges second should be re-tested (run the affected test suites) after rebase**, since the auto-merged `cec_fullstack.py` / `cec_overnight_directed.py` / `cec_verifier.py` will be a textually-merged composite neither branch was tested against. No manual conflict resolution is required.
