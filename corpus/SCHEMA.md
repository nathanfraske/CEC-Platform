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
    "net_families": [], "netclasses": [], "part_classes": [], "regions": []
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
                                      // rows carrying "migrated": true (the 258 legacy rows)
  "signoff": {                        // NEW: required in promoted/
    "by": "github-login", "date": "YYYY-MM-DD", "evidence": "link-or-ledger-ref"
  },
  "promotion": {                      // NEW: appended by the promotion PR
    "date": "YYYY-MM-DD", "shadow_record": "ref", "pr": 0
  },
  "supersedes": "id|null", "migrated": true
}
```

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
