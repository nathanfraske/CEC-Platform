# PR #56 (prompt-tier-audit) — Claude-Panel Merge Audit

## VERDICT

**merge-with-fixes** — 0 hard blockers, 2 high-severity defects that should be fixed before merge (the P4 fix is inert as shipped, and the new test guard is not wired into any gate), plus 1 high-severity scope/labeling issue to surface to the owner.

All 15 findings below were independently re-verified against the source on branch `claude/prompt-tier-audit` (live measurements where claimed). 0 findings rejected.

---

## BLOCKERS (0)

None. Nothing in this PR crashes, corrupts the signed-only control baseline at runtime, or breaks the deterministic route / Kelvin fence (those safety paths remain protected). The two high items below are "ships a no-op" and "ships a dead test," not "ships a fault."

---

## HIGH (4 findings — two distinct bugs + one scope issue)

### H1 — P4's locked-decision spine, fence, and "unratified" relabel never reach the spec-conformance verifier (truncated off by the unchanged 4000-char slice)

*(This is findings index 0 and index 4 — the same bug, same fix, reported by two passes. Merged here.)*

- **Where:** `scripts/cec_fullstack.py:1496-1500` builds `rules_excerpt`; consumed only by `scripts/cec_verifier.py:82` (`_slice_spec`, `ctx.get("rules_excerpt", "(none provided)")[:4000]`).
- **Bug:** The entire purpose of P4 is to feed the spec-conformance charter RATIFIED knowledge it currently lacks — the locked-decision spine (`LOCKED_DECISIONS_BRIEF`), the per-run fence, and the in-run standing rules *clearly relabeled as unratified*. But the excerpt is assembled corpus-first:
  ```python
  rules_excerpt = (CORPUS_BRIEF + "\n" + LOCKED_DECISIONS_BRIEF
                   + f"\nFENCE (never steer): nets={...}, "
                   + "\nIN-RUN STANDING RULES (unratified, this run only): " + json.dumps(...))
  ```
  and the only consumer truncates at `[:4000]`. The truncation cap was **not** changed in this merge — the diff swapped `rules_excerpt` from a small `json.dumps(manager_rules)` (which fit) to this large corpus-led string, while leaving `[:4000]` alone.
- **Code evidence (live-measured for eps-8pin):** `len(CORPUS_BRIEF)=8364`, `len(LOCKED_DECISIONS_BRIEF)=655`. `"LOCKED DECISIONS"` first appears at char 8365 of `rules_excerpt` → it, `"FENCE (never steer)"`, and `"IN-RUN STANDING RULES"` are **all absent** from `rules_excerpt[:4000]`. `CORPUS_BRIEF`'s own cap is `max_chars=13000`, so this degrades further as the corpus grows. The seat receives only the front ~half of the promoted corpus and none of what P4 exists to inject — it can still go dark with `empty_corpus` even though the locked decisions were "added." No test exercises `_slice_spec`/`rules_excerpt`, so it passes CI green while being inert for its core deliverable.
- **Fix:** Lead with the load-bearing, fixed-size content so truncation can only drop the (least-critical, growable) corpus tail: `rules_excerpt = LOCKED_DECISIONS_BRIEF + "\nFENCE..." + "\nIN-RUN STANDING RULES..." + "\n" + CORPUS_BRIEF`. **And/or** raise the `_slice_spec` cap to cover the realistic excerpt size (≥ ~10000) — `CORPUS_BRIEF` is already independently capped, so a generous slice is safe. Add a test asserting `"LOCKED DECISIONS"` survives `_slice_spec` truncation for a representative corpus size.

### H2 — The new prompt-audit test is not wired into any automated gate (CI or checklist)

- **Where:** `tests/test_prompt_audit_fixes.py` (whole file); `.github/workflows/kicad-checks.yml:74-78`; `scripts/checklist.sh:58-61`.
- **Bug:** Both gates run an **enumerated** unittest list, not `unittest discover`. CI runs `tests.test_cl03_compiler tests.test_measurement_claims_corpus tests.test_fault_phenomenology_corpus tests.test_stability_budget`; checklist runs only the three corpus-anchor modules. `test_prompt_audit_fixes` is in neither, and the merge diff adds it to neither — the only repo references are docs prose. The U5-hallucination guard / fenced-net / manifest-drop regression coverage is dead from CI's perspective the moment a human stops running it by hand.
- **Code evidence:** `grep -rn test_prompt_audit_fixes .github/ scripts/checklist.sh scripts/check-all.sh` → nothing. No `unittest discover` anywhere. The suite is host-runnable and green (no GPU/broker), so it belongs in the existing host leg.
- **Understated scope (worth flagging):** Many *other* host suites added in this merge are **also** absent from the enumerated list — `test_shadow`, `test_ei02_control_lane`, `test_fs_actuator`, `test_ei01_lever_vision`, `test_offending_net_intents`, etc. The merge adds tests but never expanded the CI invocation list for any of them.
- **Fix:** Add `tests.test_prompt_audit_fixes` (and the other new pcbnew-free / broker-monkeypatched host suites) to the unittest list in both `kicad-checks.yml` and `checklist.sh`.

### H3 — PR titled "prompt-tier-audit" actually merges the entire EI backbone (9 commits / 50 files / 6573 insertions) — scope/labeling, surface to owner

- **Where:** branch `claude/prompt-tier-audit`, commits `e735de5..fa63d22`.
- **Issue:** The reviewable prompt-audit change is a **single commit** (`e735de5`, touching `cec_fullstack.py` + `cec_verifier.py` + the one new test). The other 8 commits (EI-02 control lane, EI-03 shadow aggregator, EI-05/06/07 governance, V4 panel seat + idle queue, dashboard per-seat streaming, overnight watchdog, item-4 actuator harness) are **not on main** and ride in under a "prompt-tier-audit" title. An owner approving "the prompt audit" would unknowingly merge 6573 insertions of EI infrastructure.
- **Evidence:** `git rev-list --count main..branch` = 9; `git diff --stat` = "50 files changed, 6573 insertions(+), 143 deletions(-)"; `git merge-base --is-ancestor` confirms `4727d2d / fa63d22 / 1755b2c / 2e95bc0 / bb0f4bd / 98efdfb` are all not on main.
- **Severity note:** The task framing says the EI stack was pre-reviewed, so this is a **pr-hygiene / labeling** concern, not a code defect. (See "PR base scope" note at the bottom.)
- **Fix:** Confirm with the owner that PR #56 is intended to land the full EI backbone + the prompt delta together, and either retitle/relabel to reflect the real scope, or rebase so the pre-reviewed EI commits land via their own already-approved PR and #56 carries only `e735de5`. At minimum, enumerate the 9 commits in the PR body so the approver sees the true blast radius.

---

## MEDIUM (5 findings)

### M1 — SENSE CORRIDOR span is computed from the full fence, which includes U2 (the CAN transceiver) → corridor inflated, model told to route CAN around its own source pin

- **Where:** `scripts/cec_fullstack.py:776-781` (corridor block); fed by `BOARD_PINNED_REFS["eps-8pin"]` at `1214` via `resolve_fence`.
- **Bug:** The corridor span is `[r for r in fence.get("refs", ()) if r in refs]`, but `fence['refs'] = ('RS1','RS2','U20','U21','U2')` where **U2 is the CAN transceiver** (the line's own comment: `CAN xcvr (U2)`), not a sense component. On the committed EPS board U2@(60.0,12.0) while the real sense refs span x[17.8,45.8]; including U2 stretches the advertised "SENSE CORRIDOR" to x[17.8,60.0] — ~14 mm of extra width into the CAN/ESP region. The prompt then says "route signal nets AROUND it" *and* "prefer keeping I2C/CAN OUT of the sense corridor," while CAN_H/CAN_L must connect **to** U2's pads — self-contradictory steering injected into every T1 round (both lanes).
- **Impact:** Bounded — the deterministic route and the Kelvin fence are still protected, so this degrades steering quality, not safety. Medium is correct.
- **Fix:** Compute the corridor from sense-only refs. Add a dedicated `BOARD_SENSE_REFS = {'RS1','RS2','U20','U21'}` for the corridor span while keeping U2 in the *fence* (for the no-waypoint-anchor guard). The fence (refs you may not anchor to) and the corridor (the sense window to route around) are two different concepts and should not share the transceiver pin.

### M2 — Unknown-net guard uses strict string membership without the slash-normalization the rest of the pipeline applies

*(Findings index 1 and index 3 describe the same guard; merged. The two passes split on severity — see note.)*

- **Where:** `scripts/cec_fullstack.py:822` (`known_nets = set(manifest.get("net_refs", {})) or None`) and `830-833` (`if known_nets is not None and net not in known_nets: ... dropped.append(net)`).
- **Bug:** `net_refs` keys come from `pad.GetNetname()`, which is mixed-form — local nets are slash-prefixed (`/CAN_H`, `/I2C_SDA`), global/power nets are bare (`GND`, `+3V3`, `+5VSB`) (verified directly in `beta/eps-8pin/eps8pin-module.kicad_pcb`). This is the **only** net-membership test in the codebase that does *not* normalize: `cec_fs_actuator.is_fenced` does `t.lstrip('/') in fence['nets']`; `cec_fr02` lstrips at lines 243/323/415; `cec_facts._net_match` exists precisely for this (sheet-path prefix, fnmatch, KiCad `Net-(J1-CAN1_H)` auto-name unwrap). If the model emits an equivalent-but-different form (drops a slash, or uses a spec name like `/CAN1_H` from the injected corpus instead of the board auto-name), the intent is silently dropped *and* appended to `dropped`, which the next augmented round's prompt feeds back as "do NOT use them again" — self-reinforcing.
- **Mitigation (why not high):** The manifest NET→REFS block and the GR-01 grid both feed the model the same `GetNetname()` form, so a copy-faithful model matches; a dropped net still routes freely (only loses its directed stub). Worst case is degraded steering plus a noisy re-prompt, not a functional/safety break. I grade this **medium** overall (the original index-3 verdict downgraded to low on the mitigation; index-1 held medium — medium is the defensible middle, given the self-reinforcing `dropped` feedback raises the cost beyond a one-time miss).
- **Fix:** Normalize before the membership test, reusing the established pattern: match against `known_nets` via `cec_facts._net_match`, or at minimum `known_nets = {n for k in manifest['net_refs'] for n in (k, k.lstrip('/'))}`. Do not add a net to `dropped` unless it fails the *normalized* match.

### M3 — `board_manifest()` (the foundation of the U5 fix) has zero test coverage

- **Where:** `scripts/cec_fullstack.py:636-666`; consumed by `run()` at line 1302.
- **Gap:** P1's headline is that T1 waypoints anchor to refs that EXIST because `board_manifest()` supplies the real placed-footprint inventory. The tests verify `intent_manager` when *handed* a static `MANIFEST` dict, but `board_manifest()` itself — the `MANIFEST_JSON=` line-parsing (`for ln in out.splitlines(): if ln.startswith("MANIFEST_JSON=")`) and the empty-`{}` fail-safe — is never exercised, exactly where a real bug would hide (multiple `MANIFEST_JSON` lines, malformed JSON, missing line, exception). The container pcbnew code-string can't run on host, but the parsing/fallback contract `run()` depends on is host-testable.
- **Fix:** Add a host test that monkeypatches the module-level `fs._exec_py` to return representative `(rc, out)` tuples (a good `MANIFEST_JSON` line, a garbage line, an exception) and asserts the parsed dict in the good case and `{}` in the degraded/error cases.

### M4 — The P3 A/B-integrity fix (lane-gated `intents_aug` carry-forward) is untested — a regression here silently corrupts the control baseline

- **Where:** `scripts/cec_fullstack.py:1344-1351`.
- **Gap:** P3 is the merge's stated A/B-integrity fix: on an augmented round `prev_intents=intents_aug` and `intents_aug`/`prev_dropped_aug` are updated; on a control round `prev_intents=seed_intents` and neither aug state is touched, so augmented-learned waypoints never leak into the signed-only baseline. `lane_for` is unit-tested (`test_ei02_control_lane.py`), but the **new gating** that maps lane → which prev-state to feed/update is not. An accidental edit (updating `intents_aug` on a control round) would leak augmented waypoints into the signed baseline and pass every existing test — making the entire A/B comparison dishonest.
- **Fix:** Extract the lane→prev-state selection into a tiny helper (or test `run()` with a stubbed `intent_manager`) and assert: (a) augmented round feeds `intents_aug` and updates it + `prev_dropped_aug`; (b) control round feeds `seed_intents` and does NOT mutate `intents_aug`/`prev_dropped_aug`.

### M5 — `promoted_corpus_brief(in_family_only=...)` ordering/truncation/cache-key (P7) is untested despite a non-trivial correctness claim

- **Where:** `scripts/cec_fullstack.py:419-471`.
- **Gap:** P7 promises in-family entries are ordered FIRST so truncation drops the off-family tail (never an in-family layout rule), `in_family_only=True` drops off-family entirely, and the cache key changed from `board` to `(board, in_family_only)`. A board-only key would return the wrong brief for the second caller in `run()` (`CORPUS_BRIEF` vs `CORPUS_BRIEF_GEN` would collide). None of this is exercised — no fixture corpus, no ordering assertion, no truncation/drop test. Verified live the two briefs are genuinely distinct (8364 vs 1542 chars) and cache under two keys, so the logic is correct today but unprotected.
- **Fix:** Add a test with a tiny temp corpus (one in-family + one off-family entry; point ROOT/glob at a tmp dir or monkeypatch `glob`) asserting: `in_family_only=True` omits the off-family entry; the default keeps it with the in-family line ordered first; and the cache returns distinct strings for the two `in_family_only` values.

---

## LOW (5 findings)

- **L1 — Comment claims `CORPUS_BRIEF` briefs the T8 batch auditor, but `v4_batch_audit` never receives it.** `scripts/cec_fullstack.py:414` (`# full brief (auditor T5/T8)`), `:1262` (`# full (auditor T5 / batch T8)`), log at `:1266`. `CORPUS_BRIEF` is consumed only by T5 (`:1020`) and the P4 verifier excerpt (`:1496`); the T8 call at `:1668` passes `{"penalties":..., "rules":...}` with no corpus. Doc/log-only — no behavior depends on it. **Fix:** correct the comments/log to "T5 only," or actually pass the corpus into `v4_batch_audit`'s ctx/system (minding its own `[:6000]` truncation).

- **L2 — In-family-only brief advertises `n_total` entries but the body only contains the `n_in` subset.** `scripts/cec_fullstack.py:466-469`. With `in_family_only=True` the header reads `RATIFIED CORPUS (35 owner-signed entries; 6 in scope for this eps-8pin family ...)` while showing only the 6, dropping the "the rest tagged with their family scope" suffix — no omission marker, mildly misleads the generation seat. **Fix:** report the in-family count as the total on that branch, or append "(only the N in-family shown)."

- **L3 — The placed-footprint inventory (`ref_lines`) is the one T1 prompt block with no size cap.** `scripts/cec_fullstack.py:771-772` — unbounded `", ".join(...)` over every footprint, while siblings are capped (`net_refs[:1500]`, `grid[:3000]`, `prev_intents[:1200]`). ~1.4 KB for eps-8pin (49 footprints) today, but scales linearly (~300 footprints → ~8 KB) and the function is generic across boards. Latent, not a current break. **Fix:** cap it like the siblings — `ref_lines = ref_lines[:4000]`, or limit the count with a `...(N more)` marker.

- **L4 — Dead no-op expression statement in a test with a misleading comment.** `tests/test_prompt_audit_fixes.py:95` — `self._run.__self__  # no-op to keep the stub set in setUp`. A bare attribute access whose value is discarded; the stub is installed by `setUp()` regardless (AST-confirmed `Expr(Attribute(...))`; tests pass with the line removed). **Fix:** delete the line.

- **L5 — Trivial 43-byte run-log committed as a tracked artifact.** `docs/prompt-audit-2026-06-13/v4-run.log` — single line `[cec_v4_task] -> v4-findings.json (1634.3)`, no review value distinct from `v4-findings.json` (no secrets/absolute paths). Siblings `v4-prompt.txt`/`v4-system.txt` are defensible provenance. **Fix:** drop the run-log; optionally gitignore `*-run.log` under `docs/`.

---

## Rejected / not-real (appendix)

None. All 15 reported findings were verified as real against the source on branch `claude/prompt-tier-audit`, with live measurements confirming the two highest-stakes claims (P4 truncation: `CORPUS_BRIEF=8364` chars, locked decisions begin at offset 8365, all dropped by the unchanged `[:4000]` slice; corridor: U2 = CAN transceiver inflates the span by ~14 mm). Two pairs of findings are the same underlying bug reported twice (index 0 ≡ index 4 → merged into H1; index 1 ≡ index 3 → merged into M2) — not rejected, deduplicated.

## PR base / scope note

PR #56's true blast radius is **9 commits / 50 files / 6573 insertions**, of which only the top commit `e735de5` is the prompt-tier-audit delta. The remaining 8 are the EI backbone (control lane, shadow aggregator, governance, V4 seat + idle queue, dashboard streaming, overnight watchdog, actuator harness), none of which is on `main`. This is the H3 finding — surfaced as a hygiene/labeling concern (the task framing says the EI stack was pre-reviewed) and must be confirmed with the owner before merge so the approver sees the real scope.
