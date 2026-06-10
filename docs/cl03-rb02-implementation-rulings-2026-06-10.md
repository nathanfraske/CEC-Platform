# CL-03 / RB-02 Implementation Rulings

Answers to the eight build questions, each with the framework rule it derives from,
the concrete build, and the verification that proves it. Two threads run through every
ruling and are worth internalizing before the per-item answers:

**Thread 1, consent integrity (RB-04):** promotion authorizes knowledge, never file
writes. Anything that mutates committed files or removes a blocking rule is a human act
riding a PR. The compiler's authority ends at build-time artifacts.

**Thread 2, capture cannot be retroactive (PC-01/DF-06):** anything that will someday be
evidence gets recorded from the first run, even if its consumer ships in a later wave.

Owner-gated items in this wave: the schema rev (Ruling 1's compile block plus Ruling 6's
`families` scope dimension) rides one PR for owner approval. Everything else below is
derivable from locked framework rules, cited per ruling.

---

## Ruling 1: Compilability contract → (a), with (c) as its present-tense consequence

**Decision.** The entry declares its own compilation via a machine-readable `compile`
block. An entry compiles iff it carries a valid block, and a block is valid only on a
structured entry (`kind: rule|param`, typed value, SCHEMA-shape scope). Absent or
invalid block means advisory-prose by construction: it compiles to a review-bundle note
and sits at review horizon in the pushdown table. The 258 prose rows therefore gain
compile blocks only at their promotion-time upgrade, which is already the plan of
record. Option (b) is rejected outright: a hand-maintained entry-to-template mapping in
code is corpus knowledge living outside the corpus, unprovenanced and untestable by
AM-02 fixtures, which recreates the exact two-sources-of-truth drift RB-02 exists to
kill. The one legitimate shape of (b)'s instinct survives inside (a): a
`checker_binding` target type binds an entry to an existing hand-authored Python
checker, with the binding living in the entry rather than in a code table.

**Block shape.**

```json
"compile": {
  "targets": [
    {
      "type": "dru_rule | netlist_assert | keep_apart | scorer_limit | param | netclass_min | checker_binding | review_note",
      "params": { }
    }
  ]
}
```

Horizon is computed, never declared: the compiler derives each target's horizon from
(target type, entry class) and validates against the RB-02 class caps (A/B hard entries
may reach generation and routing; C typically DRC and scorer; heuristic and prose never
below review). A declared horizon field would let an entry promote itself past its
class; computation makes that structurally impossible.

**Staging semantics that make shadow mode real.** A structured staging entry with a
valid compile block compiles to the advisory-mode version of its deterministic artifact
(the dru rule evaluated and reported as ADV, the netlist assert run as ADV). Prose
staging compiles to an ADV review note only. This distinction is the substance of
CL-04's future shadow records: structured staging entries accumulate real fire evidence,
prose entries accumulate nothing until upgraded.

**Build.** Schema rev PR adding the block, with the 5 structured general entries as the
exemplars. Compiler: parse, validate, derive horizon, emit.

**Verify.** Linter rejects a compile block on a prose entry and a class-violating
target. Compiler over the current tree emits exactly zero blocking artifacts (promoted/
is empty) and 263 advisory outputs, of which the 5 structured entries produce evaluable
advisory checks and 258 produce notes.

---

## Ruling 2: Registry reconciliation → (b) now, converging to (a) with (c)'s mechanism, per-row, human-merged

**Decision.** Phase 0 (now): REGISTRY stays the blocking set, untouched. The compiler
runs alongside and emits a **parity report** classifying every constraint three ways:
*matched* (registry row has a staging entry candidate as its corpus source),
*registry-orphan* (no corpus source exists; an entry must be drafted), *corpus-only*
(entry with no registry counterpart; becomes net-new enforcement at promotion). That
report is the owner's re-sign worklist, which is the framework's "flag to owner" line
made mechanical.

Phase 1 (per promotion): the promotion PR for an entry that supersedes a registry row
carries, in the same human-merged diff, the entry's state change **and** the registry
row's tombstone (`superseded_by: <entry-id>`, excluded from blocking). For
`checker_binding` targets, the Python code stays and authority moves to the entry. The
answer to the transition question is therefore: yes, "(b) until further notice," and
retirement is **never automatic**. Removing a blocking rule is exactly as consequential
as adding one, so it rides the same consent gate (RB-04). End state: the registry file
is generated rows and tombstones only, with a CI assertion ("every active blocking
constraint cites a promoted entry") flipped on by the owner at a date of their choosing,
never by a background process.

**Build.** Parity report in the compile step; `corpus_id` and `superseded_by` fields on
registry rows; lint: a ratified row whose matched entry has promoted but which lacks
`corpus_id` is a warning, escalating to error after a grace window.

**Verify.** Parity report golden against the current 34 rows (30 ratified) commits as a
fixture; a synthetic promotion PR in a test branch shows the entry flip and tombstone in
one diff; lint fires on a crafted promoted-but-unlinked pair.

---

## Ruling 3: Materialization → build-time artifacts; committed-file writes stay human-only

**Decision.** Promotion authorizes the knowledge; it does not authorize the compiler to
touch committed board files. All compiled output lands in a gitignored
`build/corpus-compiled/<board>/` tree: `assembled.kicad_dru` (committed hand rules
merged with compiled fragments), `netlist_asserts.json`, `keep_apart.json`,
`scorer_limits.json`, `params.json`. Every compiled rule carries an entry-id and
content-hash annotation (a `; corpus: <entry-id> <hash>` comment in dru text, a field in
JSON). Files, never in-memory: artifacts must be hashable, diffable, and attachable to
ledger manifests and judge bundles, and in-memory output defeats all three.

**DRC consumption.** KiCad reads the `.kicad_dru` colocated with the board, so the check
harness stages the board copy plus the assembled dru into the build tree and runs DRC on
the staged copy. The committed tree is never mutated by any check invocation, asserted
in the harness.

**The human convenience path.** If the owner wants a compiled rule visible in the GUI
while hand-routing, a human-run write command (the `write=True` pattern already in use)
materializes a **marked generated section** into the committed dru. That copy is
explicitly a convenience; the build-time assembly stays authoritative, and lint flags a
committed generated section that drifts from current compiled output (stale-copy
detection, Ruling 8).

**Rationale chain.** A compiler with committed-write authority can corrupt every board
in one buggy run; generated sections as the primary mechanism create a mutable committed
surface agents write to, against the spirit of CL-02 even when CODEOWNERS-guarded; and
the boards currently on HOLD or ordered need their committed artifacts frozen.

**Verify.** A full compile leaves `git status` clean. The staged-DRC path produces
identical results to a manual colocated-dru run on one fixture board. The stale-copy
lint fires on a deliberately drifted generated section.

---

## Ruling 4: ADV wiring → a `binding` field on Flag; enforcement at aggregation points; per-fire ledgering from day one

**Decision.** Add `binding: "gate" | "advisory"` plus `entry_id` to Flag, with
namespaced ids `ADV-<entry-id>`. Not a `Kind.ADVISORY` (bindingness is orthogonal to a
flag's kind; an advisory netlist assert and an advisory distance check are different
kinds) and never riding `conf` (the agent's instinct is correct: confidence and
bindingness are different dimensions and conflating them poisons both). Default
`binding: gate` for all existing flags preserves back-compat.

**"Never blocks" is enforced where blocking happens, never by trusting producers:**
`human_signoff`'s blocking count filters `binding == gate`; every cascade pass/fail
predicate filters `binding == gate`; the intake gate reports ADV and gates on gate-class
only. Belt and suspenders: any code path that halts on flags asserts no advisory flag
reached its input set, so a future consumer cannot accidentally block on ADV.

**Surfaces this wave:** `cec_constraints.run()`/report (ADV section), the intake gate,
the `cec_synth_pipeline` cascade (ADV carried through to candidate reports),
`cec_router.route()` decision logs, and the ledger.

**Ledgering: per-fire, now.** Capture cannot be retroactive (PC-01); deferring to CL-04
means shadow evidence starts at wave 3 instead of accumulating from the first advisory
run. Mechanics per AM-06: per-fire events `{entry_id, board, candidate_hash, run_id,
locus, ts, binding}` batched into one per-run sidecar JSONL, hash recorded in the ledger
line, written through the run's single ledger appender. This satisfies per-fire
granularity and batched IO simultaneously.

**Verify.** A board producing only ADV fires auto-signs and passes the cascade (unit
test). A crafted gate flag still blocks. The sidecar round-trips: fires written, hash in
ledger, aggregation script reconstructs per-entry counts.

---

## Ruling 5: Pushdown this wave → ship table plus horizon classification, fixture validation wired-and-latched; netclass emission sanctioned as intent, enforced at DRC

**Decision.** Ship the table generation and horizon classification now. Fixture
validation is not "wired-but-vacuous," it is **wired-and-latched**: the compiler refuses
to emit a *blocking* artifact for any entry lacking a passing AM-02 fixture, enforced at
compile rather than only at lint. Since promoted/ is empty, the latch is vacuously
satisfied today, and it becomes load-bearing automatically at the first promotion, which
forces fixture authoring into the re-sign flow by construction rather than by
discipline. Advisory artifacts require no fixture; shadow mode is itself their evidence
gathering.

**Horizon vocabulary: confirmed exactly as proposed.** generation = board generators and
netclass file authoring; placement = cec_place and keep-apart directives; routing =
copper synthesizer reservations and corridors; DRC = dru plus the netclass-geometry
checker; review = bundle notes. Class caps per Ruling 1 apply on top.

**Netclass nuance: sanctioned, with its enforcement honestly labeled.** Conflict
resolution 3 stands: enforcement never relies on the autorouter honoring netclasses. But
`.kicad_pro` netclass minima are real for the GUI router, for human hand-routing, and as
intent documentation, and emitting them is nearly free. So `netclass_min` is a
generation-stage target whose pushdown row carries `enforced_by: netclass-geometry
checker (DRC horizon)`. The honest representation of such an entry is two rows: intent
propagated at generation, enforcement at DRC. Nobody reading the table should ever
conclude that netclass emission is enforcement.

**Verify.** Table generates over current staging: 263 rows at review horizon (zero
fixtures, zero promoted). A synthetic promoted entry without a fixture is refused at
compile with a named reason; the same entry with a passing fixture compiles. A
`netclass_min` row shows the dual horizon annotation.

---

## Ruling 6: Scope → (a), strict SCHEMA-shape to compile; single shared resolver; unscoped means zero coverage

**Decision.** SCHEMA-shape scope (facts dimensions) is required to compile. Ad-hoc
shapes (`net_pair`, `site: hub`, `bus`, `tiers`) stay advisory-only until promotion-time
normalization, which is where the re-sign flow already puts the upgrade work. A tolerant
resolver is rejected because it creates a second scope language the RB-01 blind-map
complement cannot compute over, and compiler tolerance becomes permanent since nothing
would ever force normalization.

**Normalization guidance for the 5 general entries:** `net_pair` normalizes to the
net_families pair form; `bus` and `tiers` normalize to net_families or part_classes as
appropriate; `site: hub` is a family binding, which needs a `families` scope dimension
added in the same schema rev PR as Ruling 1 (per-board compilation binds family scope
naturally: an entry scoped `families: [hub]` compiles only when compiling hub-family
boards).

**Per-board binding:** resolve scope against board facts through one shared resolver
owned by the facts module, reusing the existing conventions (cec_score pair derivation,
`_sense_nets`, netclass patterns). No per-checker re-derivation; every tier argues over
identical facts (CL-23). Unscoped or inexpressible compiles to a review note only, zero
coverage per RB-01, confirmed. The compile report records each entry's per-board
resolution counts, and an entry resolving to zero objects on a board it claims to cover
is a lint warning, since that is either a scope bug or a board gap and both deserve
eyes.

**Verify.** Each of the 5 entries' normalized scope resolves to a nonzero object set on
its intended board fixture; an `site: hub` entry resolves to zero targets when compiling
a non-hub board and that is correct, not a warning; a deliberately misscoped entry
triggers the zero-resolution warning.

---

## Ruling 7: Params → compiled artifact with promoted-only binding; staging deltas surface as advisory; promoted-vs-hand conflicts are lint errors

**Decision.** The compiler emits `params.json` (Ruling 3 tree). Resolution order in
`_param()` and physics gates: compiled-promoted value if present, else the registry hand
value. While the registry is the bootstrap authority (Ruling 2 phase 0), hand values
govern because nothing promoted exists. A param entry's promotion PR is where the hand
value reconciles (the registry param row tombstones in the same diff), so a promoted
param coexisting with a differing still-active hand value should be impossible, and lint
treats it as an **error**: that is a reconciliation the promotion PR skipped.

A **staging** param differing from the active value is an **advisory delta**: surfaced
in the compile report and as an ADV fire ("staging proposes k=X against active Y,
source: ..."), never silently ignored (it is exactly shadow mode for numbers) and never
an error (staging has no authority to conflict with anything).

**Verify.** `_param()` precedence unit test across all three states (hand only, promoted
only, both with tombstone). The lint error fires on a crafted promoted-vs-active
conflict. A staging delta appears in the compile report and the ADV stream and changes
no computed value.

---

## Ruling 8: CI split confirmed; lint regenerates and validates annotations, plus scans committed files for generated-section drift

**Decision.** The split is confirmed: the compile step is pcbnew-free, host-runnable,
and lives in `checklist.sh` (fast leg); fixture and board validation live in the
container leg (`kicad-checks.yml`). Two additions. First, **compiler determinism is
asserted in CI**: the fast leg compiles twice and diffs, byte-identical required (sorted
iteration, stable hashing), and the artifact tree carries a manifest (corpus tree hash,
compiler version) for ledger provenance. Second, the lint rule runs as **both halves**,
because they catch different failures:

- *Regenerate-and-validate:* lint compiles fresh and validates the output, every
  blocking artifact's entry-id annotations must resolve to promoted entries with
  complete signoff. Fresh regeneration is authoritative because output derives directly
  from corpus state; committed build trees do not exist (gitignored).
- *Committed-file scan:* every marked generated section in a committed `.kicad_dru`
  (the Ruling 3 convenience path) must match current compiled output and cite promoted
  entry ids; drift or unpromoted citations fail lint.

**Verify.** The double-compile diff is empty in CI. A crafted blocking artifact citing a
staging entry fails lint in the regenerate leg. A drifted committed generated section
fails the scan leg. The container leg runs fixture validation green on the
zero-fixture tree (vacuous) and red on a deliberately broken synthetic fixture.

---

## Wave test checklist (all must exist before merge)

1. Advisory-never-blocks: ADV-only board auto-signs; gate flag still blocks.
2. Compiler determinism: double-run byte-identical.
3. Fixture latch: promoted-without-fixture refused; promoted-with-fixture compiles.
4. Scope resolver: zero-resolution warning; family scoping correct across boards.
5. Params precedence and conflict lint: three-state matrix plus crafted conflict.
6. Parity report golden over the current 34 registry rows.
7. ADV sidecar round-trip: per-fire events, ledger hash, aggregation reconstruction.
8. Lint both halves: staging-cited blocking artifact rejected; drifted committed
   generated section rejected.
9. Committed-tree immutability: full compile plus full check run leaves `git status`
   clean.
