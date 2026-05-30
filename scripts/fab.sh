#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate a fab package (gerbers + drill + pick-and-place) for one layout into
# the gitignored build/ working dir. These are NOT release artifacts; copy the
# package to fab/<rev>/ only at a tagged release.
#
# If the board has a .kicad_jobset, prefer `kicad-cli jobset run` so settings
# match the GUI exactly (confirm flags with `kicad-cli jobset run -h`); this
# script does the documented gerbers/drill/pos export.
#   usage: scripts/fab.sh <board.kicad_pcb>
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
set -e

pcb="${1:-}"
[ -n "$pcb" ] || { printf 'usage: %s <board.kicad_pcb>\n' "$0" >&2; exit 2; }
need_file "$pcb"
pcb="$(abspath "$pcb")"

name="$(board_name "$pcb")"
out="$(out_dir_for "$pcb")"
gerbers="$out/gerbers"
mkdir -p "$gerbers"

jobset="$(find "$(dirname "$pcb")" -maxdepth 1 -name '*.kicad_jobset' | head -n1 || true)"
if [ -n "$jobset" ]; then
  printf 'note: %s defines a jobset (%s) — for release outputs prefer\n' "$name" "$(basename "$jobset")" >&2
  printf '      `kicad-cli jobset run` so settings match the GUI.\n' >&2
fi

"$CEC_KICAD" pcb export gerbers -o "$gerbers/" "$pcb"
"$CEC_KICAD" pcb export drill   -o "$gerbers/" "$pcb"
"$CEC_KICAD" pcb export pos     -o "$out/$name-pos.csv" "$pcb"

printf 'fab package: %s\n' "$out"
