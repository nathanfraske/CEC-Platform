# General electrical-rules corpus (SB-13)

The cross-project corpus, scoped per the addendum
(`docs/self-building-pipeline-addendum-2026-06-09.md`, SB-13/SB-14): **narrow on purpose**.
General electrical knowledge lives in authoritative external sources (IPC-2221/2152/7351,
fab capability pages, datasheets); transcribing it wholesale creates a drift problem this
repo has already paid for once. What belongs here is what no external source has:

- **Class A — pointer/parameter:** a citation to an authoritative source plus the inlined
  parameter values code needs, with retrieval date and re-verification cadence. Formulas
  stay in code (`dt_ipc` IS the IPC-2221 rule); the corpus holds its parameters,
  applicability conditions, and citations — never a prose restatement of the formula.
- **Class B — platform rule:** promoted from the project corpus
  (`scripts/constraints/corpus-extracted.json`) or extracted from the spec, carrying the
  spec-section source. Promotion is deliberate, one human review per entry.
- **Class C — calibrated:** measured constants citing the measurement `run_id` in the
  cec-runs ledger (SB-06). **Decision (owner, 2026-06-09): the corpus stays in the open
  repo for now; the open-vs-private question is revisited when Class C data starts
  accumulating.**
- **Class H — heuristic (prose):** judge-facing rationale, consumable by LLM tiers only.
  A heuristic NEVER becomes a deterministic gate by any path short of a human reclassifying
  the entry.

## Schema

One JSON array per domain file (`thermal.json`, `can.json`, ...), one object per entry:

```json
{
  "id": "thermal.k_ipc.external_1oz",
  "class": "A",
  "kind": "param",
  "scope": {"layer": "external"},
  "value": 0.048,
  "units": "ipc2221-k",
  "applies_to": ["physics"],
  "source": {"type": "standard", "ref": "IPC-2221 §6.2 fig 6-4", "date": "2026-06-09"},
  "status": "human_approved",
  "supersedes": null,
  "notes": "formula lives in cec_synth_pipeline.dt_ipc; this entry carries the parameter"
}
```

- `source.type` ∈ `standard | datasheet | fab | spec | decision | measurement`.
  **`"model"` is rejected by the linter** — model knowledge is not a source (the owner's
  standing rule: present real data; verify against datasheets).
- `status` lifecycle: `proposed → sim_validated → bringup_validated | human_approved →
  promoted → deprecated`. The constraint compiler emits BLOCKING artifacts from entries in
  the `promoted/` ZONE and ADVISORY (`ADV-`) artifacts from `staging/` — selection is by
  ZONE, never by the `status` string (`status: promoted` is the lifecycle marker, not the
  selector). `proposed` entries are judge-visible context, never compiled into hard gates.
- `applies_to` ∈ `physics | compiler | preflight | judge | informational`.
- Class C entries must cite a ledger `run_id` (`source.ref` containing `run:R-...`).

## Lint

`scripts/cec_corpus_lint.py` (wired into `scripts/checklist.sh`, so it runs in CI):
schema validation; **reject** entries with no source or `source.type: "model"`; stale-date
warnings per class cadence (A: 180 d, C: 365 d); duplicate id / duplicate (kind, scope)
conflict detection; `applies_to` vocabulary. It also validates the project corpus
(`scripts/constraints/corpus-extracted.json`): required fields, non-empty sources, unique
ids, and that every cited spec §section still resolves in
`CEC-Platform-Ground-Truth-Spec.md` (v1.1.0) — the mechanical half of SB-11.

## Anti-patterns (banned)

- Bulk LLM generation of electrical rules from model memory (linter-rejected).
- Transcribing standards charts wholesale into data — encode the formula, cite the chart.
- Letting a heuristic harden into a gate because a judge quoted it often.
