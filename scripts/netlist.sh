#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Export a connectivity netlist, for checking against the locked pin allocation
# table (e.g. pin 8 -> DETECT divider; pins 4/5 -> RS-485 only on Pro+).
#   usage: scripts/netlist.sh <board.kicad_sch>
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
set -e

sch="${1:-}"
[ -n "$sch" ] || { printf 'usage: %s <board.kicad_sch>\n' "$0" >&2; exit 2; }
need_file "$sch"
sch="$(abspath "$sch")"

net="$(out_dir_for "$sch")/$(board_name "$sch").net"
"$CEC_KICAD" sch export netlist -o "$net" "$sch"
printf 'netlist: %s\n' "$net"
