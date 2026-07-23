#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Refresh this rev2 variant's schematic from the canonical atx-24pin board.
#
# atx-24pin-rev2 shares ONE circuit with ../atx-24pin; only the PCB layout
# differs (right-angle J4). The schematic here is a synced COPY -- the canonical
# source of truth is ../atx-24pin/24pin-module.kicad_sch. Edit it there, run this
# to refresh the copy, then "Tools -> Update PCB from Schematic" in this board.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../atx-24pin/24pin-module.kicad_sch"
dst="$here/24pin-module.kicad_sch"
[ -f "$src" ] || { echo "canonical schematic not found: $src" >&2; exit 1; }
cp -v "$src" "$dst"
echo "Synced. Now run 'Tools -> Update PCB from Schematic' in the rev2 board."
