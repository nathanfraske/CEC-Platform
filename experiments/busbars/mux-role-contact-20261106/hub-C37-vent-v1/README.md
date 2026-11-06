# Private Hub C37 vent study — not admitted

Immutable Hub source: `experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb`, SHA256 `c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db`.

Candidate SHA256: `4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992`.

Only C37 moves, from (73.5,49.6,90) to (73.5,49.7,90). All source family sidecars, authored tracks/vias, zone outlines, groups and other footprints are exact. The only other changed native item is supply-zone fc65fef1's genuinely native-refilled polygon payload. The initial native SaveBoard round trip normalized unrelated legacy source serialization; the final literal save preserves the source tree and imports only the genuine refill payloads. No copper is synthesized.

Saved-file checks: paired assembly passes with the recorded ATX seven poses and C51 at (18.3,50.237573,180); stack hash unchanged; all original C37 contact identities retained; both retained barrel/pad process checks pass. Native physical partitions preserve all 94 components, with zero demotions, using explicit old/new C37 pad identity bindings. This is connectivity evidence, not acceptance authority.

Native DRC: source and candidate each have **0 errors, 166 warnings, 0 unconnected items**. No added or removed type/severity/item-UUID signatures. Inherited warnings remain unqualified.

`receive.json` records a real refusal from the existing generic pose receiver using the actual `hub-standard-rev2` board hint. First refusal: unchanged locked group `0a18f6b6-26dd-5ffc-9aa1-910bfc79600a`, `CEC_READABLE_COMPONENT_REFERENCE_MAPPING:R35`, differs in the receiver's own native replay serialization. The literal candidate preserves this group exactly. This refusal was not waived. Independently, that receiver's ground-only refill scope does not establish authority for the necessary non-Ground supply fill change; the first observed error is a group, not a zone.

Correction to the earlier historical path-hint study: `board_hint` must be the actual board identity, not an arbitrary file path. Fresh `verify.json` uses `hub-standard-rev2` and resolves the existing `/+5V_HOLD` design basis to actual `/HOLD-UP + 3V3 REGULATOR/+5V_HOLD`: 0.5 A, geometry margin 1.25, complete source D1 to sink RJ_HOLD. Earlier path-hint `null` results are not evidence of absent current authority. This correction does not qualify the moved capacitor, barrels or fill capacity.

Read-only next-slice entry point: `cec_force_current.diagnose` with actual board hint can independently rederive the existing authority/rated graphs, and `cec_current_path_receiving.compare` can compare their terminal partitions. Its documented scope explicitly excludes zone/barrel certification. Existing signed-contour and capsule-zone receivers require their own positive newly materialized region records and do not fit this existing-zone refill. No inspected existing entry point alone grants this exact non-Ground refill plus pose transaction. A fresh exact scoped receiver remains required; do not use connectivity, unchanged DRC or the current graph comparison as a substitute.

Construction and every native constituent were externally bounded to ten seconds. Existing review boards were not changed. No current, routing, placement or release admission is claimed. Existing projected vent reservations still need exact source-bound replacement/receiving in the eventual combined transaction.
