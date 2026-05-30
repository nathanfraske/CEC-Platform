#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Export the BOM, for cross-checking against the per-board target and the spec
# BOM summary (§8).
#   usage: scripts/bom.sh <board.kicad_sch>
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
set -e

sch="${1:-}"
[ -n "$sch" ] || { printf 'usage: %s <board.kicad_sch>\n' "$0" >&2; exit 2; }
need_file "$sch"
sch="$(abspath "$sch")"

csv="$(out_dir_for "$sch")/$(board_name "$sch")-bom.csv"
"$CEC_KICAD" sch export bom -o "$csv" "$sch"
printf 'bom: %s\n' "$csv"
