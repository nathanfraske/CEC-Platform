# Opus-4.8 Panel Audit — NEW Implementations (2026-06-13)

## 1. VERDICT

**merge-with-fixes** — blockers: **0**. The diff (prompt-audit fixes P1–P6, merge fixes M1–M4, EI-02/07 lane work, and the new `ops/hooks/pre-push` + `ops/secrets/gh-bot.sh`) is structurally sound: every safety-critical path (T0 actuator consumer, panel gate-fail override, A/B lane isolation of fed-forward boards, handoff push) fails safe. No finding corrupts a routed board, leaks augmented state into a fed-forward signed baseline, or breaks a hard gate. The two issues most worth fixing before merge are a prompt that overpromises the T0 actuator (HIGH) and a pre-push hook that can hang on an interactive TTY (HIGH); both are one-to-few-line fixes. Everything else is medium/low hardening, observability, and test coverage.

Total findings confirmed: **21** (0 blockers, 2 high, 6 medium, 13 low). Rejected/not-real: **0**.

---

## 2. FINDINGS

### BLOCKERS

None.

---

### HIGH

#### H1 — P5a auditor prompt overpromises the T0 placement actuator (prompt-correctness)
- **File / location:** `scripts/cec_fullstack.py` — `_audit_prompt` lines 993–999 (prompt) vs `run()` T0 gate lines 1634–1645.
- **Issue:** The rewritten prompt tells the auditor to choose `failure_class=placement` for "a sense IC boxed against its shunt with no escape, a congested corridor, parts with no routing room" and asserts it "FIRES the T0 PLACEMENT ACTUATOR." But `run()`'s only consumer fires `gr02_repair` solely when `kelvin_ok` is FALSE **and** a `/SENSEC` reason token exists (line 1637 `if (placement_attr or kelvin_stall >= KELVIN_STALL_K) and not rec["kelvin_ok"]:`, line 1638 `blocked = next((r.split()[0] for r in rec.get("reasons", []) if "/SENSEC" in r), None)`, line 1640 `if blocked:`). So a congested-corridor / non-`/SENSEC` / kelvin-passing diagnosis the prompt explicitly steers toward results in **silent non-actuation with no log**. The OLD prompt (98efdfb) never promised the actuator fires; the P5a rewrite added the promise, so this gap is introduced/worsened by these commits. `cec_router.gr02_repair_battery` (cec_router.py:1078) is generic and self-discovers a blocked net — the restriction is purely `run()`'s gate.
- **Code evidence:** prompt 995–999 vs gate 1637–1640 above. No test asserts the firing path: `test_audit_prompt_leads_with_placement_actuator` (tests/test_prompt_audit_fixes.py:293) only greps the prompt string and uses `kelvin_ok=True`, which would NOT fire T0.
- **Fix:** Either (a) narrow the prompt so `failure_class=placement` is documented to actuate ONLY the Kelvin-sense GR-02 repair (when a `/SENSEC` net is unrouted) and that congested-corridor / no-routing-room blockages route via the deterministic corridor-avoid lever, not T0; or (b) broaden the gate to honor the prompt — when `placement_attr` and not `gates_pass`, derive `blocked` from the first unconnected/failing net (`gr02_repair_battery` already self-discovers via `_unconnected_net_set` when `blocked_net` is None) and log a "T0 placement diagnosis received but no actionable blocked net" line when it cannot act. Add a `run()`-level test driving the T0 branch with `failure_class=placement` + `kelvin_ok=False` + a `/SENSEC` reason (asserts `gr02_repair` called) and with `kelvin_ok=True` (asserts it is NOT, documenting the boundary).
- **Net (verdict):** prompt overpromise is new this commit; consumer fails safe (no actuation, no corruption) — cost is misleading steering. Practical severity ≈ medium, but listed HIGH per the original panel grade for the prompt/consumer contract mismatch.

#### H2 — pre-push hook can HANG on an interactive TTY when no credential helper answers (resource)
- **File / location:** `ops/hooks/pre-push` (installed at `.git/hooks/pre-push`) — line 26: `who="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^username=//p')"`.
- **Issue:** The hook resolves the would-be push identity with `git credential fill` and **no `GIT_TERMINAL_PROMPT=0` guard**. In the exact failure mode the hook exists to catch — bot helper not wired (or wired but the PAT file at `/mnt/e/secrets` is unmounted so `git-credential-cec.sh` exits silently) AND the global `!gh auth git-credential` helper logged out — no helper supplies a username. With a real interactive terminal attached (owner/agent runs `git push` from a shell), git prints `Username for 'https://github.com':` and reads from `/dev/tty`, so the hook **blocks indefinitely** instead of cleanly aborting with the owner-refusal message. The hook's whole point is to fail closed; instead it wedges. Reproduced live under a pty.
- **Code evidence:** line 26 has no `GIT_TERMINAL_PROMPT=0`. Live pty test: `Username for 'https://github.com':` printed, call blocks on read; with `GIT_TERMINAL_PROMPT=0` the child exits fast (`fatal: ... terminal prompts disabled`), letting the hook fall through to its abort. Non-TTY case errors fast leaving `who=''`, which the existing `[ "$who" != "nathanfraske-bot" ]` abort handles.
- **Fix:** Run the probe non-interactively so a no-helper situation yields an empty username and the hook aborts cleanly: `who="$(printf '...' | GIT_TERMINAL_PROMPT=0 git credential fill 2>/dev/null | sed -n 's/^username=//p')"`. With prompting disabled, `who=''` falls through to the existing abort with its message.
- **Net (verdict):** REAL, reproduced live. Hang manifests only in the combined case (broken creds + interactive controlling terminal); non-interactive contexts (cron, session-end hook, CI) error fast. The session-end handoff push uses an `x-access-token:` URL (line 19) and exits before line 26, so it is unaffected. Practical severity ≈ medium (conditional), listed HIGH per the original grade because it defeats the hook's stated fail-closed purpose in its target failure mode. One-line fix.

---

### MEDIUM

#### M1 — M1-fix corridor silently vanishes when sense nets don't match `/SENSEC\d+_(HI|LO)$` (regression)
- **File / location:** `scripts/cec_fullstack.py` — `intent_manager()` lines 798–810 (M1 corridor block).
- **Issue:** The M1 fix narrowed the corridor source set to fence refs touching an `is_sense_net` net: `on_sense = {r for n, rl in net_refs if _fr.is_sense_net(n) for r in rl}` then `sense_refs = [r for r in fence['refs'] if r in refs and r in on_sense]`. `is_sense_net` only matches `/?SENSEC\d+_(HI|LO)$` (`cec_fr02._SENSE_NET_RE`). The OLD code computed the corridor from ALL fenced refs present in the manifest, so it produced a corridor regardless of net naming. For any board using a non-standard sense net name (e.g. `/SENSE_HI`, or the 12VHPWR `/SENSEP*`), `on_sense` is empty → `sense_refs` empty → **no SENSE CORRIDOR block emitted, silently**, with no log and no fallback. `intent_manager` is generic across boards.
- **Code evidence:** new 802–810 vs old `sense_refs = [r for r in fence.get('refs',()) if r in refs]`. `is_sense_net('/SENSEP1_HI')=False`, `('/SENSE_HI')=False`, `('/SENSEC1_HI')=True`. `corridor_block` built only `if sense_refs:` (810) with no `else`/log.
- **Latency note:** Only `eps-8pin` is wired in `cec_overnight_directed.BOARD_PCB`, and EPS uses `/SENSEC1_HI` (matches), so **no live board is affected today**. The regression is latent for any future board or renamed net.
- **Fix:** (a) fall back to all fenced refs present in the manifest when `on_sense` is empty (restores old behavior for non-standard naming); or (b) emit a log line when fence refs exist but `on_sense` filters them all out; or (c) drive the corridor from an explicit per-board `BOARD_SENSE_REFS`. At minimum, do not let the corridor disappear without a log.

#### M2 — T0 actuator and shared `kelvin_stall` counter are NOT lane-gated (logic / A-B cleanliness)
- **File / location:** `scripts/cec_fullstack.py` — `run()` T0 block lines 1634–1645 (no lane guard); `kelvin_stall` at 1414/1479.
- **Issue:** Every other EI-02 steering effect in `run()` is lane-gated — corridor-avoid carry (`and lane == "augmented"`, 1456/1461), `pending_corridor_avoid` seeding (1543), `steer_lr` injection (`= lr if lane == "augmented" else None`, 1560), delta settlement (1662). But the T0 block (1634–1645) has **no `lane` check**, and `kelvin_stall` is a single run-wide counter incremented every round (1479) and reset to 0 when T0 fires (1645). So on a CONTROL (signed-only) round the auditor reading `lr_view` can return `failure_class=placement` and — if kelvin fails with a `/SENSEC` reason — `gr02_repair` runs and resets `kelvin_stall`, perturbing when T0 fires on a later AUGMENTED round, and the control row records `t0_fired=True` (1811), a non-clean A/B signal.
- **Code evidence:** 1479 `kelvin_stall = 0 if rec["kelvin_ok"] else kelvin_stall + 1` (no lane scope); 1637 fires on either lane; 1811 `"t0_fired": bool(t0)` on the lane-tagged row.
- **Bounding:** Bounded — gr02's board (`build/fullstack/gr02-r{rnd}.kicad_pcb`) is only logged + recorded as a boolean; the next round re-routes fresh from the committed floorplan via `ovd._exec_route_one`, so the route A/B comparison itself is not corrupted.
- **Fix:** Gate the T0 block on `lane == "augmented"` (mirroring `steer_lr` / `pending_corridor_avoid`), and either keep per-lane `kelvin_stall` counters or only increment/reset it on the augmented lane. At minimum, do not record `t0_fired=True` on a control row.

#### M3 — Directly-relevant new host suites wired into NEITHER gate (test-gap)
- **File / location:** `.github/workflows/kicad-checks.yml:74–79` and `scripts/checklist.sh:58–61`.
- **Issue:** The merge adds `tests.test_prompt_audit_fixes` to `kicad-checks.yml:79` but NOT to `checklist.sh` (which still runs only the three corpus-anchor modules). Both gates use an **enumerated** list (no `unittest discover`), and the two suites covering code this PR changes are absent from both: `test_auditor_dispatch.py` (auditor dispatch + deepseek path P5 touches) and `test_ei02_control_lane.py` (covers `lane_for`, which M4's `_lane_carry` composes with). Both are host-runnable and green (verified 46 tests across all three suites, 0.005s, no GPU/broker/pcbnew). So regression coverage for the exact subsystems under review runs only on manual invocation — which CLAUDE.md's WSL-ephemeral / disaster-recovery policy explicitly warns against relying on.
- **Code evidence:** `checklist.sh:58–61` lists only `test_measurement_claims_corpus`/`test_fault_phenomenology_corpus`/`test_stability_budget`. Per-suite grep: `test_auditor_dispatch` ci=NO checklist=NO; `test_ei02_control_lane` ci=NO checklist=NO.
- **Fix:** Add `tests.test_prompt_audit_fixes` to `checklist.sh:58–61`, and add the new pcbnew-free host suites (`test_auditor_dispatch`, `test_ei02_control_lane`, and the other broker-monkeypatched suites) to the enumerated list in both gates — or switch the host leg to `python3 -m unittest discover -s tests` so new suites are picked up automatically.

---

### LOW

> Grouped by area. All are real but non-shipping-defect (observability, hardening, parity, test design, dead code, environment edges). Severities reflect the panel's corrected grades.

#### Auditor / coercion (P5b)

**L1 — `_coerce_audit` covers only the cloud path; deepseek (default) path is unhardened (consistency).**
`scripts/cec_fullstack.py` — `_coerce_audit` (1055–1066) applied only at `sonnet_audit:1092`; `deepseek_audit` (1099–1124) checks only `if not isinstance(out, dict) or "verdict" not in out:` (1117), no enum validation, no `_coerce_audit`. The default overnight auditor is deepseek-v4-flash, so the P5b comment's "can't silently disable a load-bearing consumer" claim doesn't hold for the default path. *Misread to flag:* the finding's mechanism (scribe recovery emits ungrammared content) is FALSE — both `_chat_json` and `_scribe_json` apply `response_format: json_schema, strict: True` (cec_judge_local 258–259 / 315–316), so the enum is enforced on both. Risk is negligible (live consumer T0 fails safe on a non-`"placement"` value). **Fix:** wrap the `deepseek_audit` return (line 1124) in `_coerce_audit(out)` for parity.

**L2 — `_coerce_audit` makes a previously-uncounted malformed cloud dict count as a model anchor (regression / EI-07).**
`scripts/cec_fullstack.py` — `_coerce_audit` 1057–1065 → `real_anchor_ratio` 319 (called 1795). A loaded-but-`verdict`-less cloud dict previously gave falsy verdict at 319 (auditor anchor skipped); now `_coerce_audit` forces `verdict='repair'` with no `error` key, so 319's `audit.get('verdict') and not audit.get('error')` is truthy → the auditor counts as a model anchor, slightly lowering `real_anchor_ratio`. Narrow (only the loaded-but-verdictless dict; error-path dicts bypass coercion and still don't count; the protective `test_errored_auditor_not_counted` is unbroken). The new counting is arguably more correct. **Fix:** if exact metric parity matters, mark a coerced-from-missing verdict (e.g. `d['coerced']=True`) and exclude such anchors at 319; otherwise document the shift. Keep `_coerce_audit` — it correctly fixes a latent `AttributeError` for the non-dict cloud-output case (old `sj.get('scorer_penalty')` at 1563).

#### Corpus / prompt briefs

**L3 — `in_family_only` brief advertises `n_total` (35) but body has only the in-family subset (6), no omission marker (prompt-correctness).**
`scripts/cec_fullstack.py` — `promoted_corpus_brief()` 488–491. On `in_family_only=True` the header reads "RATIFIED CORPUS (35 owner-signed entries; 6 in scope ...)" while the body holds only 6 `- [` lines (29 off-family dropped), verified live. A generation seat may read "35 owner-signed entries," not see a dropped off-family rule, and conclude it doesn't exist. **Fix:** use `n_in` instead of `n_total` in the header on this branch, or append "(only the N in-family entries shown; M off-family omitted)."

#### Panel redesign (P6)

**L4 — Progress lens trajectory includes the current round twice (prompt-correctness).**
`scripts/cec_fullstack.py` — `_panel_prompts()` 907–909 + `run()` 1474/1482. `records.append(rec)` (1474) precedes `worker_panel(rec, rnd, history=records)` (1482), so `history[-3:]`'s last element is the current `rec`, while the progress message also has an explicit "this round: ..." line — the current round appears twice, and on round 1 the trajectory is just the single current round (no cross-round signal). Weakens the P6 decorrelation the progress lens exists for. **Fix:** pass `history=records[:-1]`, or drop the redundant "this round" line.

**L5 — Panel redesign drops `max_T` from every lens input; finishing/progress can accept a gate-failing board (regression — informational/not-a-bug).**
`scripts/cec_fullstack.py` — `worker_panel`/`_panel_prompts` 901–958 vs old `m` dict; `run()` actuation 1482–1489. No lens now receives `max_T`, and only the safety lens is gate-anchored. **Confirmed safe:** the return contract `(action, votes)` is identical, the empty-vote deterministic fallback is byte-identical, and the final clamp `if action=='accept' and not rec.gates_pass: action='repair'` is preserved, so `run()`'s actuation (repair +8/+12, escalate +14/+20, else 24/40) never bumps effort on a falsely-accepted gate-fail. This is the intended P6 redesign — **no fix required for the safety/actuation path.** Optionally: feed `max_T`/`n_fem_flags` to the progress lens if thermal should still influence effort, and consider letting a finishing/progress `escalate` override an accept tally so a decorrelated structural signal isn't out-voted 2-1 on a gate-passing board.

#### Phantom-lever / dead-code (P5d)

**L6 — `PENALISABLE` is now dead-but-defined in `cec_fullstack` (consistency — dead-code half real; cross-module half a misread).**
`scripts/cec_fullstack.py` line 78 (def) + 1193 (comment only); live gate uses `if metric not in _PENALTY_METRIC: ... rejected:not_priceable`. No live consumer of `PENALISABLE` remains — dead code / maintenance trap. *Misread to flag:* the finding's central consistency claim that `cec_inloop_audit.py` "retains the exact phantom-lever bug P5d removed" is INCORRECT — `cec_inloop_audit` uses a different backend (`live_objective` + `derived_metrics`, lines 71–73/111–121) that genuinely consumes `gate_fail`/`kelvin_unrouted`/`diffpair_unrouted`, so `PENALISABLE` is NOT a phantom lever there. The two auditors are not inconsistent in the way claimed. **Fix:** delete the dead `PENALISABLE` tuple from `cec_fullstack.py` (or repoint its comment to `_PENALTY_METRIC`).

#### Test coverage

**L7 — `_coerce_audit` tested in isolation; its load-bearing call site (`sonnet_audit` reading the cloud JSON file) is untested (test-gap).**
`tests/test_prompt_audit_fixes.py` 279–284 calls the pure helper; `sonnet_audit` (the only caller, `cec_fullstack.py:1092`) is never invoked by any test (only stubbed in `test_auditor_dispatch.py:53,64`). Deleting the `_coerce_audit(...)` wrapper at 1092 would fail no test. The path fails safe (sonnet_audit returns repair on timeout/no_file; out-of-enum only mis-steers), and the cloud auditor is the opt-in non-default seat. **Fix:** add a host test that monkeypatches `subprocess.run` to write a bogus-enum JSON to `out_path` and asserts `sonnet_audit()` returns a coerced dict.

**L8 — M3 `board_manifest` test covers only good-line + raises; the malformed-JSON and missing-line branches are untested (test-gap).**
`tests/test_prompt_audit_fixes.py` 192–208 vs `cec_fullstack.py` 681–688. Three degraded paths reach `return {}`: `_exec_py` raises (tested), garbage `MANIFEST_JSON=` line (untested), no manifest line (untested). The M3 finding's own fix named all three cases. All converge on the same fail-safe `return {}` (T1 degrades to ungrounded prompt, never blocks). **Fix:** add the two missing cases via the existing `fs._exec_py` monkeypatch.

**L9 — P6 panel redesign tested at `_panel_prompts` layer only; `worker_panel` itself untested (test-gap).**
`tests/test_prompt_audit_fixes.py` 249–273. `worker_panel` (`cec_fullstack.py:936–958`) — the function `run()` actually calls (1482) — holds the `nothink=True` flag, the majority tally, the history-forwarding, and the gate-fail override `if action=='accept' and not rec.get('gates_pass'): action='repair'` (956–957), none regression-guarded. `jl._chat_json` is monkeypatchable, so it's host-testable. **Fix:** add a test asserting (a) history forwards into the prompts, (b) a unanimous accept with `gates_pass=False` is overridden to repair, (c) the tally picks the modal action.

**L10 — M4 invariant test re-implements `run()`'s lane update rather than driving `run()` (test-gap).**
`tests/test_prompt_audit_fixes.py` 211–214 / 216–228. The invariant test re-implements `run()`'s update inline (`if lane=='augmented': intents_aug = list(model_out[rnd])`) rather than driving `run()`, so an accidental control-round mutation of `intents_aug`/`prev_dropped_aug` (cec_fullstack.py:1449–1451) would pass every test and leak augmented waypoints into the signed baseline. Also unmodeled: `run()` captures `intents_aug` (1450) BEFORE the corridor-avoid augmentation (1456–1458). The `_lane_carry` helper itself IS directly tested. **Fix:** extract the lane-update block (1444–1451) into a tiny helper and test that, or drive `run()` with a stubbed `intent_manager`.

**L11 — Dead no-op expression statement with a misleading comment (style).**
`tests/test_prompt_audit_fixes.py:116` — `self._run.__self__  # no-op to keep the stub set in setUp` is a bare attribute access whose value is discarded; `setUp()` (45–57) installs the stub unconditionally. Test passes identically without it. **Fix:** delete line 116.

#### pre-push hook / secrets (new files)

**L12 — Guard checks the HTTPS credential helper even for SSH `github.com` remotes (security — downgraded medium→low).**
`ops/hooks/pre-push` lines 21–22/26. An SSH URL like `git@github.com:...` matches `*github.com*` and the hook then resolves identity via the HTTPS credential helper — unsound two ways: (1) helper-wired → allows a push reporting `nathanfraske-bot` that SSH does not actually enforce; (2) helper-not-wired → false-blocks a valid SSH push. The repo standardizes on HTTPS+PAT and no SSH remote is in use, so it doesn't currently fire. **Fix:** restrict case 2 to `https://*github.com*|http://*github.com*) : ;; *) exit 0 ;;`, or explicitly skip `git@`/`ssh://` URLs.

**L13 — `x-access-token` allow-rule trusts ANY token-in-URL push, not specifically the bot's (security).**
`ops/hooks/pre-push:19` — `case "$url" in *x-access-token:*@github.com*) exit 0 ;;` bypasses the bot-identity check for any token URL, including `x-access-token:OWNER_PAT@github.com`. The threat model is accidental fallback to the owner's gh login; an owner-PAT-in-URL is a deliberately constructed string and the owner is trusted, and the session-end handoff legitimately relies on this allow-rule. **Fix (optional):** gate case 1 on an explicit `CEC_BOT_PUSH=1` env var set only around the PAT-URL push, instead of pattern-matching any token URL.

**L14 — Dead variable `root` assigned but never used (style).**
`ops/hooks/pre-push:15` — `root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"` is computed (subshell + git on every push) and never referenced. New dead code in a security-sensitive file. **Fix:** delete line 15.

**L15 — Handoff's gh-fallback push is now silently blocked when the bot PAT is absent (regression).**
`.claude/hooks/session-end.sh:125` (`git push -q origin ... || true`) under the new pre-push guard. When `CEC_BOT_PAT` is absent, the fallback's plain `origin` URL (no `x-access-token:`) misses the allow-case, resolves to the owner via `git credential fill`, and the hook aborts (exit 1); `2>/dev/null` + `|| true` swallow it, so the durable handoff is silently NOT pushed — the precise WSL-ephemeral failure the handoff policy exists to prevent. Scoped to no-PAT only (the bot-PAT path at line 121 carries `x-access-token:` which the hook allows); normal deployment sources the PAT. Arguably the intended owner-directive tradeoff. **Fix:** when `CEC_BOT_PAT` is absent, log a loud warning that the handoff cannot be pushed (PAT missing, owner-push refused). Do NOT add `--no-verify` (that would defeat the guard).

**L16 — New `gh-bot.sh` sources the secrets file as shell — code-exec vector if the file is world-writable (security).**
`ops/secrets/gh-bot.sh` (new) dot-sources `load-secrets.sh`, which `set -a; . "$CEC_SECRETS_FILE"; set +a` executes the file as shell. `/mnt/e/secrets/cec-bot.env` is `-rwxrwxrwx` (drvfs default) → injection vector for any local user. The new code does not leak the PAT (passes it via `exec env GH_TOKEN=...`); its only added exposure is one more execution path over the source-as-shell pattern, which itself pre-dates this diff (introduced in 47ce5d4, already sourced by session-end/git-credential-cec/provision). The perms are a drvfs environment artifact largely out of the new code's control. **Fix:** parse the file as `KEY=VALUE` instead of sourcing it (e.g. `CEC_BOT_PAT=$(sed -n 's/^CEC_BOT_PAT=//p' "$file")`); document the world-writable drvfs caveat in `ops/secrets/README.md`.

---

## 3. Rejected / not-real appendix

No findings were rejected as not-real. All 21 candidate findings were confirmed against the code. Two contained internal **misreads** that were corrected without changing the real (low-severity) core, and are flagged inline above:

- **L1 (P5b deepseek parity):** the stated mechanism — that the miner→scribe recovery emits ungrammared content — is FALSE; both the primary `_chat_json` call and `_scribe_json` apply `response_format: json_schema, strict: True`. The parity nit (default deepseek path not run through `_coerce_audit`) is the real, minor residue.
- **L6 (phantom-lever consistency):** the cross-module claim that `cec_inloop_audit.py` "retains the exact phantom-lever bug" is INCORRECT; that module's `live_objective`/`derived_metrics` backend genuinely consumes the gate-derived metrics, so `PENALISABLE` is not a phantom lever there. Only the `cec_fullstack` dead-code half is real.

Additionally, **L5 (panel drops `max_T`)** is confirmed-accurate as an observation but is explicitly the intended P6 redesign with the safety/actuation/return-contract path fully preserved — it is an informational note, not a defect, and requires no fix on the safety path.
