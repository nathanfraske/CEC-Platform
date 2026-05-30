#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Design rule check for one board layout.
#   usage: scripts/drc.sh <board.kicad_pcb>
#   exit:  0 clean, 5 violations (see JSON report), other = tool error
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

pcb="${1:-}"
[ -n "$pcb" ] || { printf 'usage: %s <board.kicad_pcb>\n' "$0" >&2; exit 2; }
need_file "$pcb"
pcb="$(abspath "$pcb")"

report="$(out_dir_for "$pcb")/drc.json"

rc=0
"$CEC_KICAD" pcb drc --exit-code-violations --format json -o "$report" "$pcb" || rc=$?
case "$rc" in
  0) printf 'DRC clean: %s\n' "$(board_name "$pcb")" ;;
  5) printf 'DRC VIOLATIONS: %s — see %s\n' "$(board_name "$pcb")" "$report" >&2 ;;
  *) printf 'DRC error (rc=%s): %s\n' "$rc" "$(board_name "$pcb")" >&2 ;;
esac
exit "$rc"
