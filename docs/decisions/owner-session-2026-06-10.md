# Owner decision session — 2026-06-10 (corpus session, decisions first)

THE resolvable artifact every decision-sourced entry and ledger record from this
session cites (owner ruling #14). Rulings verbatim from the owner, followed by
execution status. Branch: `claude/cl19-real-register`.

## Rulings (verbatim)

1. **Ruling 3 amendment (normalize):** ratify presentation-character canonicalization:
   strip markdown emphasis markers, map an enumerated typographic table (U+2010-family
   hyphens to ascii, curly quotes to straight, NBSP/ZWSP handled). NFC plus table, never
   NFKC. Bump verifier_version, re-run run-2's manifest for attribution. The paraphrase
   failures still fail, so this rescues nothing.
2. **Prompt hardening:** approved regardless of item 1 (verbatim-copy contract including
   markers). Contract clarification, never gold-tuning.
3. **Holdout extraction:** gallery README shows EVAL cases only; holdout by ID and pool
   tag, content solely in tests/holdout/; extend the CI grep to assert the gallery
   carries no holdout trace text. Do this before any further prompt iteration.
4. **Pin-hog relabel:** preserve the analyst's wrong +3V3/+5VSB attribution in the gold
   mechanism with the truth in the annotation, matching the ntc and ref3030 treatment.
   Fidelity labeling never sanitizes.
5. **Gate record:** after my labeling pass, sign eval_set_sha with grade: smoke into
   eval_gates.extractor; gate stays FAIL for the run-2 manifest.
6. **Decision 7:** ratify cec-verdict-core/1 as locked (it is already grammar-enforced
   in production use).
7. **Decision 21:** registry table ratified as written (or I'll send amendments
   separately); flip ratified: true.
8. **Decision 3:** GitHub Issues as the queue substrate.
9. **Decision 6:** deep-path budget, conservative start (pick numbers, e.g. a nightly
   token cap and wall-clock cap); changeable by PR.
10. **M2.7 formalization:** record my license ruling in policy (license_cleared: true,
    dated), since the analyst binding is now load-bearing.
11. **CAN naming:** board-manifest alias for rev2 now, rename queued as a rev3 erratum
    beside the R1 migration.
12. **CL-02 confirmation:** machine account and branch protection are live (or flag if
    not; nothing promotes until they are).
13. **Decisions 18 and 10**, if the minimal viable night is next: bank the MVN baseline
    on pinned 1.7.0, migrate to 2.2.4 immediately after as its own epoch; execution
    venue WSL2 with the end-to-end golden run before anything stacks on it.
14. **Session-specific instruction:** commit the corpus-session transcript (or hash it
    into the ledger) as the resolvable artifact every decision-sourced entry cites. A
    named human decision needs something to resolve to, and the session log is it.

## Execution status (agent, same session)

| # | Status |
|---|---|
| 1 | DONE — `cec_span_verify` v1.1.0: NFC → enumerated table (hyphen family, dashes, minus, curly quotes, NBSP family, zero-widths) → asterisk-emphasis strip (UNDERSCORES excluded: identifier-bearing) → ws-collapse. Property-tested. **Attribution re-run DEFERRED: GPU loaned to the owner's other test**; run-2 raws were 4000-char truncated, so attribution needs a re-run, queued for box return. |
| 2 | DONE — character-exact quoting contract in EXTRACT_PROMPT (markers kept, no ellision, no figure substitution). New prompt_sha ⇒ new manifest. |
| 3 | DONE — gallery rebuilt EVAL-only (holdout = ID + pool tag); leak assertion in the structural CI leg, teeth-verified on a planted slice. |
| 4 | DONE — pin-hog mechanism + evidence span now carry the analyst's wrong +3V3/+5VSB attribution verbatim; truth confined to notes. New `eval_set_sha cf7355a40534`. |
| 5 | STAGED — gate-record body (status fail, grade smoke, verifier 1.1.0, eval_set_sha cf7355a40534) ready; the policy write follows YOUR labeling pass over the gallery. |
| 6 | RECORDED — Decision 7 closed; ratification rides PR #29's SCHEMA.md approval. |
| 7 | DONE — `cec-policy.json` registry `ratified: true` (this session's edit; lands under your PR approval). |
| 8 | RECORDED — Decision 3: GitHub Issues; CL-07/CL-04/SB-02 build against it. |
| 9 | DONE — conservative deep-path budgets in policy (from tonight's measured batch: 8 calls / ~70 min / ~50K tokens): nightly wall-clock 90 min, output 80K tokens, max 12 deep calls; per-call 15 min / 12K tokens. Changeable by PR. |
| 10 | DONE — dated license ruling on the analyst binding (named decision 2026-06-10, this artifact). |
| 11 | DONE — `modules/atx-24pin-rev2/board-manifest.json` net aliases (CAN1_H→/CAN1_P, CAN1_L→/CAN1_N) consumed by the shared resolver; warning clears honestly; rev3 erratum recorded beside the R1 (DETECT 2.2k) migration. |
| 12 | CONFIRMED WITH CAVEAT — machine account LIVE (bot pushes verified). Branch protection LIVE but `required_approving_review_count: 0` + the observed CLEAN-state ambiguity mean the owned-path gate is NOT yet trustworthy for promotions. **Per your own ruling: nothing promotes until the count=1 fix lands** (the command is in PR #29's queue, item 8). |
| 13 | RECORDED — MVN: bank baseline on FR 1.7.0; 2.2.4 migration immediately after as its own AM-03 epoch; venue WSL2 with the end-to-end golden run first. |
| 14 | THIS FILE — committed; sha256 recorded in the ledger decision records; decision-sourced entries cite `docs/decisions/owner-session-2026-06-10.md`. |
