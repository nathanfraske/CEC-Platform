#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Render a top-side image of a layout for a quick silk/placement look.
#   usage: scripts/render.sh <board.kicad_pcb>
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
set -e

pcb="${1:-}"
[ -n "$pcb" ] || { printf 'usage: %s <board.kicad_pcb>\n' "$0" >&2; exit 2; }
need_file "$pcb"
pcb="$(abspath "$pcb")"

png="$(out_dir_for "$pcb")/$(board_name "$pcb")-top.png"
"$CEC_KICAD" pcb render -o "$png" "$pcb"
printf 'render: %s\n' "$png"
