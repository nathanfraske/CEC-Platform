SHIP-WITH-FIXES

# Adversarial audit — PR #56 (prompt-tier audit)

Scope: `scripts/cec_fullstack.py`, `scripts/cec_verifier.py`, `scripts/cec_overnight_directed.py`,
`scripts/checklist.sh`, `tests/test_prompt_audit_fixes.py`. Branch `origin/claude/prompt-tier-audit`,
base `98efdfb39`. All 27 tests in `tests/test_prompt_audit_fixes.py` pass on the branch.

## Verdict

**SHIP-WITH-FIXES.** No blocker, no high, no data-corruption or hard-gate breach. Every confirmed
finding is medium or low and either latent (not reachable by any wired board / production caller)
or self-correcting. The one finding worth landing before merge is the unconditional-fence
inconsistency (PG-1 / AB-3 — same line), because it is a one-line change that restores a
belt-and-suspenders safety invariant the rest of the codebase already relies on.

## Confirmed findings

All 8 findings confirmed; 0 refuted, 0 reclassified. Severity = true_severity.

### Medium (1)

| ID | File:loc | Issue | One-line fix |
|----|----------|-------|--------------|
| PG-1 | `cec_fullstack.py:892` | Net-fence drop is gated `if fence and _act.is_fenced(...)`. `is_fenced` protects every `/SENSEC*_(HI\|LO)` net **unconditionally** via regex, but the `if fence and` short-circuits it whenever `fence` is falsy (`{}`/`None`), so a future caller passing an empty fence silently loses all sense-net protection. Latent — the only production caller passes a truthy 2-key dict. | Drop the short-circuit: `if _act.is_fenced(net, fence or {}):` |

### Low (7)

| ID | File:loc | Issue | One-line fix |
|----|----------|-------|--------------|
| PG-2 | `cec_fullstack.py:854-855` | Waypoint few-shot example refs taken from `sorted(refs)` over the FULL inventory, so a fenced ref (RS*/U2) can sort into the example, contradicting the FENCE line in the same prompt. Validator strips it downstream — pure prompt-quality / wasted intent budget. | Pick example refs from `sorted(set(refs) - set(fence.get('refs',[]))) or sorted(refs)`. |
| PG-3 | `cec_fullstack.py:984-989, 1523-1528` | A malformed/`None` winning panel vote bypasses the `accept`-on-gate-fail guard (matches only the literal `"accept"`) and lands in the caller's `else`, **resetting** router effort to baseline `24/40` on a gate-failing round — opposite of repair. | Broaden guard: `if action not in ('repair','escalate') and not rec.get('gates_pass'): action='repair'`. |
| PG-4 | `cec_fullstack.py:831-834, 1587-1588` | Corridor M1 fallback and offending-net filter narrow by `is_sense_net` (regex) instead of the broader `is_fenced`; on a `/SENSEP*` board this could re-include a pinned CAN xcvr in the corridor hint or let a fenced net become an avoid-intent that bypasses `intent_manager` validation. No `/SENSEP` board is wired. | Filter both with `cec_fs_actuator.is_fenced(n, fence)`. |
| PG-5 | `cec_fullstack.py:506-509` | Non-in-family corpus brief header reports pre-truncation `n_total`/`n_in` regardless of truncation; under a small `max_chars` it could claim entries the seat never saw ("seat knows a rule it wasn't shown"). Prod always uses default `max_chars=13000`; full brief ≤8.4k so never truncates. | Count surviving `- [` lines in the truncated body and report `n_shown`, like the in-family path. |
| AB-1 | `cec_fullstack.py:1873, 1762, 1802` | `prev_v4_risk` carry is **ungated** (no `if lane`) while every other run-learned carry is `augmented`-only; the V4 batch window mixes a control round in, so control-round data feeds a risk scalar that steers future augmented rounds. PRE-EXISTING (byte-identical to base); A/B baseline itself never perturbed; escape delta is control-gated/rolled-back. | Gate the carry to `lane=='augmented'` and exclude control rows from `batch_for_v4`. Owner call; out of scope for #56. |
| AB-2 | `cec_fullstack.py:1701, 1780, 1732` | Finding-deltas built on rounds 1-3 (before the round-4 control) are silently overwritten unsettled because `last_control_metrics is None` skips the settlement block — no `rolled_back` Outcome row, so `DeltaLog.tally()` undercounts. PRE-EXISTING (byte-identical). End state correct (no ratchet); only the ledger tally is wrong. | Seed a synthetic round-0 signed-only baseline, OR emit an explicit `rolled_back` Outcome before overwrite (status-only mirror is insufficient). Owner call; out of scope. |
| AB-3 | `cec_fullstack.py:892` | Same defect as PG-1, viewed from the A/B lane: the unconditional sense-net fence is decoupled from fence truthiness. Latent — `_resolve_board_fence` always returns a truthy dict. | Same fix as PG-1: `_act.is_fenced(net, fence or {})`. |
| TCW-1 | `cec_verifier.py:_slice_spec` vs `tests/test_prompt_audit_fixes.py:153` | The P4 cap raise (`[:4000]→[:12000]`) is **untested**: the spine-surfaces test asserts only spine tokens (placed first, ~773 ch) which survive the old cap, so reverting the cap to 4000 still passes. The load-bearing ordering half IS covered. Cap change is benign-by-construction (more context, never less). | Optional: assert a corpus-tail marker past char 4000 reaches the seat through `_slice_spec`. |
| TCW-2 | `cec_verifier.py:~122-128, ~360-369` | P10 (actuation-effector set / `RECORDED-ONLY`) and P12 (T8 decline-vs-audit criteria) are pure prompt-string edits with **no test coverage** — mutation test confirms all 27 tests stay green after deleting both. Prompt-only; cannot break a gate. | Acceptable to leave uncovered; optional `assertIn` to document the contract. |

## Single most important fix before merge

**PG-1 / AB-3 — make sense-net fencing unconditional at `cec_fullstack.py:892`.**
Change `if fence and _act.is_fenced(net, fence):` → `if _act.is_fenced(net, fence or {}):`.
This is a one-line edit, the only **medium** finding, and it restores the belt-and-suspenders
guarantee the codebase already states it provides (the docstring at `cec_fullstack.py:1357` and
the actuator's own callers at `cec_fs_actuator.py:102,165` all rely on the unconditional regex
guard). It is currently safe only because the sole production caller passes a truthy fence — but
that is an accident of one call site, not an enforced invariant, and a locked §6.8 Kelvin template
is exactly what the fence exists to protect.

PG-3 is the strongest *optional* follow-on (broaden the panel `accept`-guard so a malformed vote
can't reduce effort on a failing round) — cheap, contained, and worth folding in. PG-2/PG-4/PG-5
are nice-to-haves. AB-1/AB-2 are pre-existing and explicitly out of scope for this PR — file them
for the owner, do not block #56 on them.

## #56 / #59 composition on main

No shared-file conflict observed. PR #56 is confined to the loop/prompt-tier surface
(`cec_fullstack.py`, `cec_verifier.py`, `cec_overnight_directed.py`, `checklist.sh`,
`tests/test_prompt_audit_fixes.py`, plus `docs/prompt-audit-2026-06-13/` and the CI YAML). No
`#59`/cloud-shim branch is present in this checkout to diff against directly, but per the stated
split the cloud shim is #59-only and the loop changes here are #56-only, so the two touch disjoint
files and **compose cleanly** — merge order is immaterial. (Caveat: this is asserted from the
file-set, not verified against a live #59 branch; if #59 turns out to edit any of the five script
files above, re-check `cec_fullstack.py` specifically, as it carries the bulk of #56's churn.)
