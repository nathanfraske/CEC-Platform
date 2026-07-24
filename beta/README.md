# CEC beta line — the authoritative board versions

Single source of truth for which directory is the CURRENT beta version of each
Standard-line board. This exists because the versioning got tangled once: when the
beta schematics were reworked (hierarchical sheets, ESP32-C6, the §6.13 front end),
the new work landed in the plain-named directories while the older `-rev2` copies
were left behind. Because `-rev2` reads as "newer," it was not obvious which
directory was current. It is now.

**Rule:** for any beta-line change, edit only the directory marked authoritative
below (each carries a `BETA` marker file). Never edit a `-rev2` or alpha copy for
the beta line. The stale copies carry a `SUPERSEDED` marker.

> **PHYSICAL MOVE EXECUTED 2026-07-22** (owner directive: "the BETA line in its own
> directory... no further confusion on where the latest ones are" — supersedes the
> earlier defer-the-move note). The live beta lineage now LIVES in `beta/<board>/`
> (depth-preserved: 2-deep like `modules/<board>/`, so every `${KIPRJMOD}/../../lib`
> path resolves unchanged; the out-daughterboards keep depth 3 under
> `beta/output-daughterboards/`). The rule is now brutally simple: **if it's in
> `beta/`, it's the latest; everything under `modules/`/`hubs/` is alpha or
> history.** Verification of the move: normalized netlists BYTE-IDENTICAL pre/post
> for all 11 moved boards (only path metadata differs), zero stale toolchain refs
> (60-file sweep + 11 composed-path fixes + 3 resolvers: `cec_router.find_board`,
> `cec_facts.board_catalog`, `cec_synth_pipeline.Config.load` — all scan `beta/`
> first), full checklist green, SB-08 golden unchanged.

## Authoritative beta boards (edit these)

| Board | Directory | MCU | State | Markers |
|---|---|---|---|---|
| 24-pin ATX | `beta/atx-24pin-rev3` | ESP32-C6-MINI-1 | INA238 beta, DRAFT | BETA |
| EPS 8-pin | `beta/eps-8pin` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| PCIe 8-pin 2-port | `beta/pcie-8pin-2port` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| PCIe 8-pin 3-port | `beta/pcie-8pin-3port` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| 12VHPWR Standard | `beta/12vhpwr-standard` | ESP32-S3-MINI-1 | hierarchical, fab-ready | BETA |
| ARGB Standard | `beta/argb-standard` | ESP32-S3-MINI-1 | beta, DRAFT | BETA |
| Hub Standard | `beta/hub-standard-rev2` | ESP32-S3-WROOM-1 | rev2 schematic, layout via waves | BETA |
| EPS 8-pin rev3 | `beta/eps-8pin-rev3` | ESP32-C6-MINI-1 | SENSEC 40A decision OWNER-GATED | BETA (gated) |
| Smoke Tester | `beta/smoke-tester` | NONE (pure analog, by design) | sketch-stage: README spec + assets + BOM, no capture yet (owner standup 2026-07-24) | BETA + DRAFT |

(`hubs/hub-standard` remains the shipped fab-ready ALPHA baseline — the hub row's
promotion to `hub-standard-rev2` was executed 2026-07-22 with the physical move: the
2026-07-17 note deferred it to "the owner's call at the rev2 layout wave," and the
owner's no-confusion directive plus all current hub work targeting rev2 constitute
that call. Flagged in the session report for veto.)

Output daughterboards (per the D-5a architecture, also beta and authoritative):
`beta/output-daughterboards/atx24-out-db`, `.../eps-out-db`, `.../pcie-out-db`.

## Superseded (do not edit; kept only as history)

| Stale directory | Superseded by | Why |
|---|---|---|
| `modules/eps-8pin-rev2` | `beta/eps-8pin` | old flat schematic, fewer parts, never fabbed |
| `modules/pcie-8pin-2port-rev2` | `beta/pcie-8pin-2port` | same |
| `modules/pcie-8pin-3port-rev2` | `beta/pcie-8pin-3port` | same |
| `hubs/hub-rev2` | `hubs/hub-standard` | DRAFT, fewer parts, superseded |

Each carries a `SUPERSEDED` marker. None was ever fabbed. Safe to delete once you
confirm you want them gone; git history keeps them.

## Hub rev2 line (NOT superseded — the merged-in pipeline branch's hub revision)

`beta/hub-standard-rev2` (DRAFT) is the **rev2 Hub Standard schematic** finalized
2026-07-15 on `claude/pipeline-consolidation` and merged 2026-07-17: F1–F4 per-port
polyfuses, D8/D9 SMAJ5.0A power-entry TVS, C18–21 DETECT filters, the J6 column-paired
mezzanine header (DNP THT — since split into the J6P/J6C/J6D structural segments,
2026-07-22), D-11 DRU exception. Committed layout is unstarted; the wave pipeline
synthesizes its layouts (first-ever routed hubs landed 2026-07-20/22). PROMOTED into
the authoritative table 2026-07-22 (see the table note). Do NOT confuse it with
`hubs/hub-rev2` in the superseded table — that is an older, unrelated June regen.

## Alpha / ordered prototypes (keep as history, not part of the beta line)

- `modules/atx-24pin` — alpha, the validated prototype (INA228).
- `modules/atx-24pin-rev2` — the ordered rev2 prototype (INA228, physically built).

These are the alpha lineage. Per the alpha/beta convention they are never overwritten
or edited for beta work; the beta 24-pin is `atx-24pin-rev3`.

## Other tiers (not Standard beta, listed so they are not mistaken for it)

`hubs/hub-pro`, `hubs/hub-enterprise`, `modules/12vhpwr-pro`, `modules/ent-common`,
`modules/ent-kvm-carrier`.

## Move record (2026-07-22)

The deferred physical move was executed per this file's own recipe: `git mv` of the
9 authoritative dirs (+`eps-8pin-rev3`), a guarded longest-first reference sweep (60
files; `(?!-rev)` lookaheads protect the `-rev2` superseded siblings), 11
composed-path fixes (`os.path.join(ROOT, "modules", board)` forms the sweep cannot
see), and `beta/`-first search order in the three resolvers. Proofs: 11/11
normalized-netlist identity, zero stale refs in scripts/tests/.github/ops, checklist
green, golden signature unchanged. The superseded/alpha directories deliberately did
NOT move — history stays where it happened.
