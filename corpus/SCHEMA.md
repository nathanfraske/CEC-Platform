# CEC corpus — zones, entry schema, lifecycle (CL-01, reconciled 2026-06-10)

One entry schema, two zones. This contract reconciles the closed-loop framework
(docs/closed-loop-implementation-list.md, CL-01/05/06/18 + AM-02) with the ALREADY-BUILT
SB-13 lifecycle that `scripts/cec_corpus_lint.py` enforces and the seeded entries carry.
Where the framework doc and the as-built vocabulary disagreed, the as-built vocabulary won
(framework rule 1: re-verify against the tree; do not take the document's word).

## Zones

| Zone | Path | Writable by | Compiles into |
|---|---|---|---|
| **staging** | `corpus/staging/**` | agents (any tier) | ADVISORY checks only — flag namespace `ADV-<id>`; can never block, never auto-sign-deny, never count toward `human_signoff`'s blocking flags |
| **promoted** | `corpus/promoted/**` | human only (CODEOWNERS + branch protection: owner's GitHub-verified approval) | blocking artifacts (DRC fragments, netlist assertions, keep-apart tables, scorer limits) |

Promotion MOVES an entry file between zones without changing its `id`. Demotion,
supersession, and scope correction are human-only by the same gate (they edit `promoted/**`).

## Lifecycle (SB-13 `status`, KEPT — the framework's `state` vocabulary maps onto it)

```
proposed -> sim_validated -> bringup_validated | human_approved -> deprecated
```

- Framework `promoted`   ≡ `status: human_approved` + a complete `signoff` block + residence in `corpus/promoted/`
- Framework `draft`/`under-review` ≡ `proposed`/`sim_validated` in `corpus/staging/`
- Framework `superseded` ≡ `deprecated` + the existing `supersedes`/`superseded_by` pointer fields
- Zone/status consistency is lint-enforced: an entry in `promoted/` MUST be `human_approved`
  with `signoff`; a `human_approved`+`signoff` entry SHOULD be in `promoted/` (lint warns —
  the gap is legitimate only between owner approval and the promotion PR landing).

## Classes (AS-BUILT taxonomy — the framework doc's letters were inverted; corrected here)

| Class | Meaning | Source requirement (lint-enforced) |
|---|---|---|
| **A** | pointer/parameter citing an EXTERNAL authoritative standard | `source.type: standard` (IPC-2221, IPC-2152, CEM…), resolvable ref |
| **B** | spec-derived platform rule | `source.type: spec` and the §ref MUST resolve in the CURRENT spec version (the framework's "CL-06 Class A routing exception" binds HERE: a new Class B assertion implies a spec revision FIRST — the corpus is never a side channel for amending the spec) |
| **C** | measured on this project's hardware/runs | `source.type: measurement` citing a ledger run id |
| **H** | heuristic prose | never compiles into deterministic gates (existing lint rule); hardens only via the RB-02 horizon cap (review-time only) |

## Entry schema (superset of SB-13; new blocks marked NEW)

```jsonc
{
  "id": "stable-kebab-id",            // never changes across zone moves
  "class": "A|B|C|H",
  "status": "proposed|sim_validated|bringup_validated|human_approved|deprecated",
  "rule": "...the assertion...",      // (extracted-corpus rows keep their full original fields)
  "scope": {                          // RB-01: coverage DECLARED in facts dimensions only
    "net_families": [], "netclasses": [], "part_classes": [], "regions": [],
    "families": [],                   // NEW (CL-03 Ruling 6): board-family applicability --
                                      // "hub" / "module" / specific board names; per-board
                                      // compilation binds family scope naturally
    "vendor": [],                     // NEW (ruling D2, 2026-06-10): fab/assembly house the
                                      // entry is scoped to -- VENDOR-pile entries ONLY
    "service_tier": []                // NEW (D2): vendor service tier; requires vendor
  },                                  // inexpressible => unscoped => counts as ZERO coverage
  "source": {                         // provenance is mandatory; model output is NOT a source
    "type": "standard|datasheet|fab|spec|decision|measurement",
    "ref": "...", "date": "YYYY-MM-DD"
  },
  "rationale_trace": "ledger-hash",   // NEW, optional (CL-18): analyst trace as derivation
                                      // context ONLY — lint REJECTS source fields resolving
                                      // to a model artifact (already enforced)
  "fixture": "path-or-inline",        // NEW (AM-02): minimal failing fixture that makes the
                                      // entry fire. REQUIRED for new entries; WARN-only for
                                      // rows carrying "migrated": true (the 258 legacy rows).
                                      // CLASS-H EXEMPTION (ruling D1, 2026-06-10): AM-02
                                      // attaches to MECHANISMS and H has none, so a firing
                                      // fixture is impossible by construction -- fixture-less
                                      // H is legal. CLASS-scoped, never entry-scoped: a class
                                      // upgrade or a compile block re-engages the requirement
                                      // automatically (lint) and the CL-03 Ruling 5 latch
                                      // bites as if the entry were new. H may carry an
                                      // optional FUTURE-fixture pointer (the incident that
                                      // burned you seeds the AM-02 fixture at checker_binding
                                      // time -- which was always the plan).
  "signoff": {                        // NEW: required in promoted/
    "by": "github-login", "date": "YYYY-MM-DD", "evidence": "link-or-ledger-ref"
  },
  "promotion": {                      // NEW: appended by the promotion PR
    "date": "YYYY-MM-DD", "shadow_record": "ref", "pr": 0
  },
  "supersedes": "id|null", "migrated": true,

  "compile": {                        // NEW (CL-03 Ruling 1): the entry declares its own
    "targets": [                      // compilation. Valid ONLY on a structured entry
      {                               // (kind: rule|param, typed non-null value, SCHEMA-shape
        "type": "dru_rule",           // scope). Absent/invalid => advisory-prose by
        "params": {}                  // construction: review-bundle note, review horizon.
      }
    ]
  }
}
```

## Compile block (CL-03 / RB-02 rulings, 2026-06-10)

- **Target types:** `dru_rule | netlist_assert | keep_apart | scorer_limit | param |
  netclass_min | checker_binding | review_note`. `checker_binding` binds the entry to an
  existing hand-authored Python checker (`params: {module, checker}`) — the binding lives
  in the entry, never in a code-side mapping table.
- **Horizon is COMPUTED, never declared** — derived from (target type, entry class) and
  validated against the RB-02 class caps (A/B hard entries may reach generation/routing;
  C typically DRC/scorer; heuristic & prose never below review). A declared horizon field
  would let an entry promote itself past its class.
- **Zone semantics:** promoted + valid block + passing AM-02 fixture ⇒ BLOCKING artifact
  (the fixture latch is enforced at compile — a promoted entry without a passing fixture
  is refused with a named reason). Staging + valid block ⇒ the ADVISORY-mode version of
  the same deterministic artifact (`ADV-<entry-id>` namespace — evaluated and reported,
  never blocking). Staging prose ⇒ ADV review note only. This distinction is what makes
  CL-04 shadow mode real: structured staging entries accumulate fire evidence, prose
  accumulates nothing until upgraded.
- **`netclass_min` is intent, not enforcement** (conflict resolution 3: the autorouter
  ignores netclasses): it emits at generation horizon with
  `enforced_by: netclass-geometry-conformance (DRC horizon)` — the pushdown table carries
  BOTH rows so nobody reads netclass emission as enforcement.
- **Materialization (Ruling 3):** all compiled output lands in gitignored
  `build/corpus-compiled/` — promotion authorizes the KNOWLEDGE, never committed-file
  writes. The only committed materialization is the human-run convenience write
  (marked generated section; lint flags drift against current compiled output).
- Compiler: `scripts/cec_corpus_compile.py` (host-runnable, pcbnew-free, deterministic —
  double-compile byte-identical is a CI assertion).

## Verdict core — Decision 7, two-layer lock (CL-19 Ruling 2, ratified in this PR)

**Layer one (locked, `cec-verdict-core/1`):** the per-candidate verdict core — what the
extractor produces, what RB-03 ratifies, what the CL-19 gold schema labels. **Layer two**
(the CL-12 bundle wrapper: bundle id, cross-candidate ranking, judge manifest, novel-flag
list) wraps the core and is NEVER touched by gold labels, so wrapper evolution cannot
burn the eval set. The CL-22 finding contract and the DF-06 claim/hook shape unify here:
a finding's `verification_hook` IS its DF-06 hook.

```jsonc
{
  "schema": "cec-verdict-core/1",
  "subject": {"board": "", "candidate_hash": "", "run_id": ""},
  "verdict": {"value": "accept | hold | escalate | no_conclusion",
              "basis_spans": []},      // CL-15 conclusions-section rule
  "findings": [{
      "id": "F1",
      "locus": {"refs": [], "nets": [], "region": null},
      "mechanism": "",
      "severity": "info | warn | block-candidate",
      "verification_hook": {"type": "check | fixture | bench | datasheet",
                            "ref": ""},   // the DF-06 closed vocabulary
      "evidence_spans": []
  }],
  "drafted_entry_refs": [],
  "confidence": 0.0
}
```

Span rules: `scripts/cec_span_verify.py` (ONE implementation, imported by the eval and
the CL-15 production path) — NFC, whitespace-collapsed, trimmed, case-SENSITIVE exact
substring; prose spans ≥ 20 normalized chars; locus identifiers exempt from the floor
but must appear as exact tokens AND resolve against board facts via the shared resolver.
`no_conclusion` is the CL-15 legal outcome — synthesis on a no-conclusion trace is a
zero-tolerance eval failure.

## Vendor scope (ruling D2, 2026-06-10)

- **What vendor scope resolves against:** the board manifest's `fab_target` block
  (`board-manifest.json`: `{"vendor": "...", "service_tier": "..."}`), read by the ONE
  shared resolver (`cec_facts.resolve_scope`). A board with **no declared fab target**
  resolves vendor entries to **zero coverage — review-note only**, honest per RB-01.
  This matters because vendor entries can carry geometric compile targets (a vendor
  minimum silk width is a perfectly good dru_rule) that are **conditional on where the
  board is going**. A declared target that mismatches is a resolved non-match.
- **Pile separation is mechanical (lint-enforced):** an entry carrying `vendor`/
  `service_tier` may not `applies_to: physics` and may not live in a `*-physics.json`
  file — physics-of-PCB lessons generalize and carry NO vendor key; an entry that
  genuinely mixes both **splits into two**. `service_tier` without `vendor` is an error.
- **Drafting note (not a gate):** vendor entries pin their observation date in
  `source.date` — capability pages drift and an undated vendor rule rots invisibly
  (lint warns).

## Standing rules carried from the framework

- Trace-to-corpus (CL-18): a drafted entry cites the datasheet/spec/measurement the trace
  POINTED AT; the trace attaches as `rationale_trace`. Heuristic-prose entries acquire a
  valid source only at the owner's signature (`source.type: decision`).
- Conflict detection (CL-05): a staging entry whose scope overlaps a promoted entry with a
  contradictory assertion is lint-flagged and cannot be promoted while the conflict stands.
- The blocking compiler consumes ONLY promoted entries (CL-03). Until the corpus→artifact
  compiler lands (wave 2), the hand-maintained `scripts/cec_constraints.py` registry remains
  the blocking set; the registry-from-corpus derivation is tracked in the wave plan.
```
