# Schematic drafting + MCP improvement plan — the codex-audit reconciliation (2026-07-22)

_The C2 synthesis of three gpt-5.6-sol (reasoning=high, read-only) audits the owner
commissioned: **A** = schematic design/structure vs cited industry standards; **B** = the
schematic MCP command surface; **C1** = the MCP readability/tuning area driven by A's
findings. Full reports (each ~0.5MB, kept verbatim): `build/codex-schstd-audit.out`,
`build/codex-mcp-audit.out`, `build/codex-mcptune-audit.out` (gitignored build/ — durable
copies belong to this doc's provenance; re-run prompts in the session job tmp). This doc is
the owner-consideration backlog those audits earn — per the standing MCP-GAP policy, every
proposed helper is surfaced here with its WHY. Nothing below is implemented yet._

## 0. Verified-now items (already actioned this session)

- **A rank-1 (ELECTRICAL, verified by re-running ERC)**: 19 `multiple_net_names` conflicts
  across tester 05-bank sheets (05a=6/05b=4/05c=4/05d=3/05e=2 — spot-verified 05b exactly 4).
  Semantic ambiguity, not cosmetics. FILED in FOLLOWUPS: 05-bank outputs treated unreleased
  until resolved at the `gen_tester_st.py` source; a `multiple_net_names` teeth-gate goes
  AHEAD of netlist-identity acceptance (identity preserves an already-wrong baseline).
- Both B and C1 independently confirmed the live-agent evidence: the mandated MCP path
  covers verification/cosmetics but forces scratch `cec_sch` scripts for the core edit verbs
  (today's two J6-split agents are the measured case).

## 1. The semantic-verb roadmap (from B) — owner consideration, ranked

B's verdict: "autonomy-blocking incomplete — the write surface is almost entirely cosmetic."
Proposed additions (full signatures + refusal contracts in the report):

| P | Verb | Why (measured) |
|---|---|---|
| P0 | `replace_components` (atomic composite: remove + add + remap + property copy, staged, expected-delta gated) | The J6 split IS this operation; four separate calls would recreate the partial-update hazard |
| P0 | `verify_restricted_diff` ("only these refs changed" vs a git baseline) | Both agents re-implemented it by hand today |
| P0 | `pin_net_map` (structured `{ref:{pin:net}}`) | Both agents parsed raw netlists for it |
| P0* | `add_components` / `remove_components` / `remap_pins` (the foundations under the composite) | Every splice since `splice_24pin_atxctl.py` |
| P1 | `sync_bom_outputs`, `ensure_fp_library`, `copy_component_properties`, `erc_diff`, `verify_schematic_change` (one-call bundle) | Each was a manual side-edit in today's runs |
| P2 | `render_refs` (ref-scoped crops), `symbol_pin_table` | Agents cropped/parsed by hand |

**Transaction model prerequisite (B)**: two explicit modes — identity-gated (cosmetic) vs
expected-delta-gated (intentional electrical) — replacing `_gated()`'s live-write/rollback.
B also found current defects to fix regardless: `_gated()` not exception-safe (partial write
survives a raising mutator), no lock (concurrent-caller clobber — cf. today's shared-tree
incident), `readability_pipeline` partial-commits on late-stage failure, no-op/failure can
report outer `ok:true`, `emit_symbol` hard-codes `in_bom/on_board/dnp` + no s-expr escaping.

## 2. The readability/tuning plan (from C1, driven by A) — owner consideration, ranked

C1 re-measured the 12 generated tester sheets: 84 text/pin-glyph overlaps, 261
text-wire/MISROT/GLYPH-CLIP findings, 49 off-sheet items, 161 bare crossings/1326 wires.
Its priority order (safety-dispositioned; details + teeth plan in the report):

1. **Make `readability_pipeline` one staged atomic transaction** with mandatory final
   overlap/wire/BOUNDS gates (foundation; also fixes B's partial-commit defect).
2. **`orient_power_glyphs`** (idempotent; kills 43 MISROT + 52 GLYPH-CLIP) — rotation at
   fixed origin = pure cosmetic.
3. **Body-aware `normalize_fields`** replacing fixed-offset `snap_values`; text height
   CALIBRATED from SVG measurements (charter rule) — attacks the 44 movable overlaps.
4. **`wrap_annotations` + `fit_sheet`** + printable-bounds commit gate — closes A rank-3
   (content plotted off-page: hub 14, EPS 21, tester 19+19 instances; the emitter places
   flag banks blind at `cec_sch.py:415` and picks paper before knowing the extent).
5. Fix the AOD4184A/fuse source-symbol glyph layouts + regenerate (the 40 overlaps field
   nudging cannot solve) — targeted regeneration only.
6. Final-extent paper-aware placement in the emitter (stops recurrence).
7. `crossing_scan` read-only MCP command (makes A rank-6 measurable).
8. `optimize_sheet_lanes` — high-risk, OUT of the default pipeline until teeth exist.
9. Golden render bands + GUI approval (the charter's top rung, prevents clean-but-ugly).

C1's boundary ruling (matches the charter): net renaming/scoping, hierarchy construction,
pin retyping, renumbering are NEVER smuggled into identity-preserving readability stages —
they wait for the expected-delta verbs.

## 3. Standards findings beyond the tooling (from A) — structural queue

- **Rank 2**: the tester set is not a genuine hierarchy (12 standalone roots, shared root
  UUID, `/TESTROOT` placeholder paths, fake page numbers) — parent composition + unique
  sheet UUIDs + root-derived ERC/netlist become release blockers. [Semantic; big.]
- **Rank 3**: sheet-bounds violations (see §2 item 4 for the cosmetic half; generator-time
  paper selection is the durable fix).
- Further ranks (pin electrical typing, net vocabulary, title-block/document control) are in
  the report with per-clause citations, each marked [verbatim-confident] or
  [recalled-verify] — the [recalled-verify] clauses need the licensed standard checked
  before being treated as contractual.
- A also delivered an "already at/above standard" list and charter-overrides list (where
  netlist-identity invariance and calibrate-don't-guess legitimately beat drafting norms).

## 4. Suggested execution order (if/when the owner GOes)

1. Transaction model + `_gated()` exception-safety (B) and the atomic pipeline (C1 #1) —
   one foundation, both audits demand it.
2. `verify_restricted_diff` + `pin_net_map` (small, immediately de-risks every agent run).
3. `replace_components` + foundations (unlocks agent autonomy for the next connector-class
   edit; today's J6 splice scripts become its test fixtures).
4. C1 items 2-4 (the pretty-pass: glyphs, fields, wrap/fit + bounds gate) with their teeth.
5. Tester bank `multiple_net_names` source fix + regeneration (already FOLLOWUPS'd).
6. The structural queue (§3) on its own clock.
