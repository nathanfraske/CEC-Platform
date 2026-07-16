# Rebase / corpus-governance verification — PR #56 (2026-06-13)

Reviewer note (relayed): *"branch is behind main and conflicts on the corpus tooling; forked from
cf950cc, lacks the 35-entry promotion at 5b47e32; the governance edits (cec_corpus_lint +138,
cec_corpus_compile +12, SCHEMA.md) overlap the promotion. Rebase onto 5b47e32, resolve, re-run the
corpus/governance/anchor suites to prove the 35 promoted entries survive the new lint (esp. revocation
and expiry)."*

## Finding: the rebase is ALREADY DONE — the snapshot was stale

| check | result |
|---|---|
| `git merge-base origin/main HEAD` | **5b47e32** (= `origin/main` tip) |
| `git log HEAD..origin/main` (commits we're behind by) | **empty** — HEAD is NOT behind main |
| parent of the EI-stack base `fa63d22` | **5b47e32** — the stack sits ON TOP of the promotion |
| `git merge-base --is-ancestor 5b47e32 HEAD` | **YES** — the 35-entry promotion is in this branch |
| conflict markers in `cec_corpus_lint.py` / `cec_corpus_compile.py` / `corpus/SCHEMA.md` | **none** |
| promoted entries present | **35** (4 json files under `corpus/promoted/general/`) |
| `gh pr view 56 --json mergeable` | **MERGEABLE** (and PR #55 too) |
| `mergeStateStatus` | **BLOCKED** = awaiting CODEOWNERS approval, NOT a conflict |

The EI stack (`fa63d22..98efdfb`) was rebased onto `5b47e32` before this branch (`claude/prompt-tier-audit`)
was cut, so no manual rebase is required. The reviewer reviewed a pre-rebase state.

## Semantic proof: the 35 promoted entries survive the NEW governance

Git can only prove the textual merge; the reviewer's real concern (do the 35 survive revocation /
staging-expiry / monotone-tightening?) is a runtime check. Run against the merged tree:

| suite | result |
|---|---|
| `cec_corpus_lint.py` | **0 errors**, 273 warnings (all benign "no fixture" on *staging* rows), 35 promoted ids recognized |
| `cec_corpus_compile.py validate` | **0 errors** |
| `cec_corpus_compile.py compile` | exit 0 (only pre-existing `can.*` ZERO-objects-on-Pro-boards scope warnings — not from this merge) |
| `cec_corpus_compile.py parity` | exit 0, tombstones empty |
| `tests/test_corpus_governance.py` (EI-05/06/07) | **22/22** — revocation (`test_revoking_root_refuses_entry_with_named_reason`, `test_compile_path_refuses_revoked_blocking_artifact`, `test_unrevoking_restores_compile`, `test_revocation_report_enumerates_dependents`, `test_stale_revocation_flagged`), expiry/dormancy (`test_crossing_nights_budget_is_dormant`, `test_crossing_appearances_budget_with_zero_corroboration_is_dormant`, `test_untainted_corroboration_clears_dormancy`, `test_passing_fixture_does_NOT_reset_budget`), monotone-tightening (`test_law_text_present`), promoted-scope (`test_promoted_entry_is_out_of_scope`) |
| `tests/test_am04_anchors.py` (anchor) | **8/8** |
| `tests/test_shadow.py` (EI-03) | **8/8** |
| `tests/test_corpus_intake_rules.py` | 17/17 |
| `cl25 / cec_policy / cl03 / fault / measurement / thermal` corpus suites | all OK |

**Conclusion:** PR #56 is conflict-free and up to date with main; the 35 promoted entries survive the new
revocation / expiry / monotone-tightening governance. No rebase action needed.

## Remaining owner action
The merge touches `corpus/SCHEMA.md` + the corpus tooling → **CODEOWNERS-gated**; `mergeStateStatus=BLOCKED`
is the required-approval gate. That is the owner's call (and the PR-scope decision: #56 currently carries the
full EI stack because its base is `main` and main is behind the stack — base it on `claude/overnight-corpus-preflight`
to review only the prompt-audit delta, or merge the stack as one).
