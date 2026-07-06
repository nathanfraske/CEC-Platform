# Enterprise requirements register — format

_Phase 1 of `docs/enterprise-mc-requirements-plan-2026-07-01.md`. Status of this doc: ACTIVE
(it defines the schema; the registers it governs are all DRAFT until owner ratification)._

## Register set

| File | Scope |
|---|---|
| `hub-enterprise-requirements.md` | The PolarFire enterprise Hub, both variants |
| `module-requirements-common.md` | Requirements shared by ALL enterprise module families |
| `module-requirements-24pin.md` | 24-pin ATX family deltas |
| `module-requirements-eps.md` | EPS 8-pin family deltas |
| `module-requirements-pcie.md` | PCIe 8-pin family deltas (2-port + 3-port) |
| `module-requirements-12vhpwr.md` | 12VHPWR family deltas (Std/Pro ladder) |
| `module-conformance-matrix.md` | EXISTING shipped/planned SKUs vs the enterprise Hub (backward compat) |

New-module candidates (tamper research §3a of the plan) stay in the plan until the owner
adopts them; on adoption each gets its own `module-requirements-<family>.md`.

## Requirement ID

`REQ-<UNIT>-<VARIANT>-<NNN>`

- **UNIT**: `HUB`, `MOD` (common to all module families), `24PIN`, `EPS`, `PCIE`, `HPWR`.
- **VARIANT**: `COMMON` (both postures), `AIR` (air-gapped only), `NET`
  (networked-but-hardened only). Requirements whose placement awaits the D-ENT-6
  variant↔tier mapping are tagged `COMMON` with gate `D-ENT-6`.
- **NNN**: sequential within a register, never reused; retired IDs are tombstoned in place
  (strikethrough + reason), not deleted.

## Requirement fields

Each requirement is one table row: **ID | Requirement | Trace | Verify | Gate**.

- **Requirement** — a single testable SHALL statement (rationale lives in the section
  preamble, not the row).
- **Trace** — spec § / OQ / plan § / research-report § that motivates or constrains it.
  `audit` = `research/customer-integration-audit-2026-07-01.md`;
  `tamper` = `research/tamper-module-roadmap-2026-07-02.md`.
- **Verify** — `I` inspection, `A` analysis, `T` test, `D` demonstration (combinations
  allowed, e.g. `A+T`).
- **Gate** — the owner decision (D-ENT-#) or OQ that must clear before the requirement can
  leave DRAFT, `Phase-N` for a scheduled owner act, `EU-entry` for obligations that bind
  only on a decision to place product on the EU market (owner ruling 2026-07-02: deferred,
  kept open), or `—` when none.

## Status lifecycle

`DRAFT → PROPOSED → RATIFIED` per register **section** (tracked in each section header),
not per row — rows churn too fast in Phase 1. Ratification is the owner's Phase-3/4 act;
nothing in these registers overrides the spec: where a register row and
`CEC-Platform-Ground-Truth-Spec.md` disagree, the spec wins and the row is a proposal.

## Locked-platform carry-ins

Rows that restate a LOCKED spec decision are marked `[LOCKED §x.y]` in the Trace column.
They are in the register so per-unit conformance is checkable in one place; they are NOT
re-decidable here.

## Lint

`scripts/cec_req_lint.py` checks: ID format/uniqueness, every Trace spec-§ reference
resolves against the spec file, Verify vocabulary, and Gate references a known D-ENT-# /
OQ-#. Run from repo root: `python3 scripts/cec_req_lint.py`.
