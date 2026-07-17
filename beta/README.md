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

> Note on layout: the boards are NOT physically moved into this folder. They stay in
> `modules/` and `hubs/` because ~40 toolchain references (gen-modules, the SB-08
> golden regression, CI, checkers) are wired to those paths, and moving the dirs
> would break them and collide with in-flight edits. This manifest plus the
> `BETA`/`SUPERSEDED` markers give the same unambiguity with zero toolchain risk. A
> physical move into `beta/<board>/` (depth-preserved, all refs updated) is a clean
> follow-up if desired — see the bottom of this file.

## Authoritative beta boards (edit these)

| Board | Directory | MCU | State | Markers |
|---|---|---|---|---|
| 24-pin ATX | `modules/atx-24pin-rev3` | ESP32-C6-MINI-1 | INA238 beta, DRAFT | BETA |
| EPS 8-pin | `modules/eps-8pin` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| PCIe 8-pin 2-port | `modules/pcie-8pin-2port` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| PCIe 8-pin 3-port | `modules/pcie-8pin-3port` | ESP32-C6-MINI-1 | hierarchical beta, DRAFT | BETA |
| 12VHPWR Standard | `modules/12vhpwr-standard` | ESP32-S3-MINI-1 | hierarchical, fab-ready | BETA |
| ARGB Standard | `modules/argb-standard` | ESP32-S3-MINI-1 | beta, DRAFT | BETA |
| Hub Standard | `hubs/hub-standard` | ESP32-S3-WROOM-1 | fab-ready | BETA |

Output daughterboards (per the D-5a architecture, also beta and authoritative):
`modules/output-daughterboards/atx24-out-db`, `.../eps-out-db`, `.../pcie-out-db`.

## Superseded (do not edit; kept only as history)

| Stale directory | Superseded by | Why |
|---|---|---|
| `modules/eps-8pin-rev2` | `modules/eps-8pin` | old flat schematic, fewer parts, never fabbed |
| `modules/pcie-8pin-2port-rev2` | `modules/pcie-8pin-2port` | same |
| `modules/pcie-8pin-3port-rev2` | `modules/pcie-8pin-3port` | same |
| `hubs/hub-rev2` | `hubs/hub-standard` | DRAFT, fewer parts, superseded |

Each carries a `SUPERSEDED` marker. None was ever fabbed. Safe to delete once you
confirm you want them gone; git history keeps them.

## Hub rev2 line (NOT superseded — the merged-in pipeline branch's hub revision)

`hubs/hub-standard-rev2` (DRAFT) is the **rev2 Hub Standard schematic** finalized
2026-07-15 on `claude/pipeline-consolidation` and merged 2026-07-17: F1–F4 per-port
polyfuses, D8/D9 SMAJ5.0A power-entry TVS, C18–21 DETECT filters, the J6 column-paired
mezzanine header (DNP THT), D-11 DRU exception. Layout is UNSTARTED (the wave-7 route
run died with its session; relaunch owed). It is neither in the authoritative table
above nor superseded — the table's `hubs/hub-standard` row remains the shipped
fab-ready baseline, and `hub-standard-rev2` is the beta-line successor **whose
promotion into the authoritative row is the owner's call at the rev2 layout wave**.
Recorded here 2026-07-17 so the -rev2 name-reads-newer trap this manifest exists to
prevent cannot recur (do NOT confuse it with `hubs/hub-rev2` in the superseded table
— that is an older, unrelated June regen).

## Alpha / ordered prototypes (keep as history, not part of the beta line)

- `modules/atx-24pin` — alpha, the validated prototype (INA228).
- `modules/atx-24pin-rev2` — the ordered rev2 prototype (INA228, physically built).

These are the alpha lineage. Per the alpha/beta convention they are never overwritten
or edited for beta work; the beta 24-pin is `atx-24pin-rev3`.

## Other tiers (not Standard beta, listed so they are not mistaken for it)

`hubs/hub-pro`, `hubs/hub-enterprise`, `modules/12vhpwr-pro`, `modules/ent-common`,
`modules/ent-kvm-carrier`.

## If you want the physical move later

Move each authoritative dir to `beta/<name>/` at the repo root (2 levels deep, same
as `modules/<name>/`, so the `${KIPRJMOD}/../../lib` paths still resolve), then
find-replace the ~40 references (`modules/<name>` and `hubs/<name>`) across
`scripts/`, `tests/`, `.github/`, and `gen-modules.py`, and re-run the checker +
SB-08 golden to confirm nothing broke. Do it from a clean tree (no in-flight edits).
