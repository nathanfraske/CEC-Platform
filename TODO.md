# TODO

The LIVE list of what the agent is ACTIVELY working on, in checkbox form. **APPEND-ONLY** — items are
never deleted; completed / obsolete ones stay as a timestamped history.

Format:
- `- [ ] [added YYYY-MM-DD HH:MM] <task>` — active
- `- [x] [added YYYY-MM-DD HH:MM · done YYYY-MM-DD HH:MM] <task>` — completed (left in place)
- `- [~] [added YYYY-MM-DD HH:MM · obsolete YYYY-MM-DD HH:MM → <tombstone>] <task>` — obsolete, with a
  tombstone pointing where it went (e.g. `FOLLOWUPS.md "<entry>"`, `PR #N`, `docs/owner-queue.md`, another line)

Distinct from FOLLOWUPS.md (deferred / non-blocking backlog) and docs/owner-queue.md (owner-action items).
Times are UTC.

## Active

- [x] [added 2026-06-13 23:25 · done 2026-06-13 23:33] Await DeepSeek new-impl audit → consolidate the Opus-4.8 + DeepSeek verdict (both merge-ready, 0 blockers; DeepSeek's 3 HIGHs = diff-only false positives)
- [x] [added 2026-06-13 23:33 · done 2026-06-14 00:10] new-impl polish fixes — #56 portion: H1 temper T0-overpromise prompt; M1 corridor fallback+log; M2 lane-gate T0/kelvin_stall (_t0_should_fire helper); M3 wire host suites into checklist.sh+CI; L3 in_family_only n_in; L4 progress history[:-1]; L1 deepseek_audit _coerce parity; L6 delete dead PENALISABLE (+6 tests; 159 host tests green)
- [x] [added 2026-06-14 00:10 · done 2026-06-14 00:30] new-impl polish fixes — #57 portion (claude/bot-push-guard, commit 70e176d): H2 pre-push GIT_TERMINAL_PROMPT=0 on the credential-fill probe (fail-closed, no-hang verified); L14 drop unused `root` var. Deferred pre-push LOWs L12/L13/L15/L16 → FOLLOWUPS.md (owner-scoped)
- [x] [added 2026-06-14 00:35 · done 2026-06-14 01:05] Adversarially verify the #56 polish fixes (wf_789eb5bc-b59, 8 skeptics + synth = SHIP-WITH-FIXES) → harden M1 (log even on empty fence) + L3 (header counts shown-under-truncation) + 2 tests; residuals (12vhpwr corridor siting, run()-level H1/L4 coverage, verifier worktree-isolation) → FOLLOWUPS. 161 host tests green
- [ ] [added 2026-06-13 23:25 · in progress 2026-06-14 01:20] Build `claude/seat-bakeoff` PR: cloud-seat shim → 2-D variant×model bake-off → 6-judge leave-one-out panel → de-overfit → data-chosen `--seats cloud` defaults (+ DeepSeek `--stream` live thinking). Owner: BUILD + RUN the full sweep.
- [x] [added 2026-06-14 04:33 · done 2026-06-14 04:50] Corridor-aware reseed placer **Phase 0** (docs/placement-strategy-2026-06-14.md): `build_corridor_model` + `corridor_cross_count` (cec_synth_pipeline) + the two missing checkers `shunt-inline-in-corridor` / `high-current-corridor-keepout` (cec_constraints) + `tests/test_corridor_model.py` (19 tests). PROVEN on committed eps-8pin: model reports ≥3 through-crossers (/DETC1,/THRESH,/I2C), /CAN_L=0; keepout checker has teeth (foreign track→FAIL). Wired into checklist host suite (134 green). Branch claude/placement-corridor.
- [x] [added 2026-06-14 04:50 · done 2026-06-14 05:25 · CLAIM RETRACTED 2026-06-14 06:00 → see audit-remediation line] Corridor-aware reseed placer **Phase 1a**: `Candidate.corridor_cross` + model build in synth_one + sort key `(residual, corridor_cross, hpwl)` + opt-in `proxy_reject(corridor_max=)`. ⚠ The "ranking alone breaks the ceiling" claim was a measurement artifact (degenerate bands) — RETRACTED by the audit; Phase 1a stands as honest rank-key plumbing only. Real ceiling-break = Phase 2 (corridor formation).
- [x] [added 2026-06-14 05:40 · done 2026-06-14 06:00] **AUDIT REMEDIATION** of Phase 0/1a (4 parallel skeptics, PR #60). BLOCKER confirmed + claim RETRACTED: synth winner's `cc=0` is a degenerate-band artifact (shunts land x~7.5 vs connectors x~30-43 → bands ~73mm/96mm, can't be straddled). Fixed: (1) band from connector+2-pad-shunt pads only, exclude INA SMD (matches derive_power_pours; reviewer A F-1, B F-4). (2) `formed`/degeneracy guard (`board_w`) → unformed corridors score 0 INERTLY not falsely-clean. (3) checker false-FAILs on 12VHPWR/24-pin (shared-bus → N/A, Phase-5 variant) + `_sense_nets` exclusion (reviewer B F-1/2/3/4 — 2 BLOCKERs). (4) determinism: sorted() set iteration in relative_place/anneal_macros (reviewer C F-2 — compact s6 now stable 0, was {0,1,2}). (5) tests: place_candidates production-sort (tautology, reviewer D F-1 BLOCKER) + via teeth + shunt-FAIL teeth + shared-bus-NA + multi-cable + no-kelvin + degenerate-guard; honest reframe (34 corridor / 159 host green). (6) doc claim retracted honestly. Deferred→FOLLOWUPS: seg-AABB exact, CI pcbnew wiring, parity re-freeze (owner).
- [ ] [added 2026-06-14 05:25] Corridor-aware reseed placer **Phase 2** (hardens it): anneal `corridor_penetration` soft term + HARD veto (no HOT/SENSITIVE body in a foreign band), `kelvin_inner_dist`/`hot_sensitive_overlap`/`current_axis_offset` terms, H3 shunt-rot270 stamp + the seed_anchors channel nudge (moved here from Phase 1), legalize_pack `forbidden` rects. Validate: ALL seeds land cc==0.

## Done / obsolete (history)

- [x] [added 2026-06-13 19:45 · done 2026-06-13 20:25] Prompt-tier audit (Claude panel + DeepSeek cross-check): catalog + 30 confirmed/3 rejected + punchlist
- [x] [added 2026-06-13 20:30 · done 2026-06-13 23:00] Implement prompt-audit fixes (P1-P12 incl. H1/M2/H2/M1/M3/M4/M5 + P5/P6) → PR #56 (20/20 host tests)
- [x] [added 2026-06-13 21:55 · done 2026-06-13 22:10] Bot-push guard hook + gh-bot wrapper (push/gh as the bot, not the owner) → PR #57
- [x] [added 2026-06-13 22:48 · done 2026-06-13 22:48] FOLLOWUPS SessionStart hook + FOLLOWUPS.md → PR #58
- [x] [added 2026-06-13 23:25 · done 2026-06-13 23:28] TODO SessionStart hook + TODO.md → PR #58
- [x] [added 2026-06-13 22:40 · done 2026-06-13 22:48] Render eps-8pin before/after board PNGs
