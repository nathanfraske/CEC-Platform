#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# CI sweep: run ERC over every schematic and DRC over every layout in the repo.
# Exits nonzero if any board reports violations or a tool error. With no boards
# yet, it is a clean no-op.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status=0
found=0

while IFS= read -r -d '' f; do
  found=1
  "$CEC_SCRIPTS_DIR/erc.sh" "$f" || status=1
done < <(find "$CEC_REPO_ROOT" \( -path '*/build' -o -path '*/.git' \) -prune -o \
         -type f -name '*.kicad_sch' -print0)

while IFS= read -r -d '' f; do
  found=1
  "$CEC_SCRIPTS_DIR/drc.sh" "$f" || status=1
done < <(find "$CEC_REPO_ROOT" \( -path '*/build' -o -path '*/.git' \) -prune -o \
         -type f -name '*.kicad_pcb' -print0)

if [ "$found" -eq 0 ]; then
  printf 'check-all: no .kicad_sch or .kicad_pcb files yet — nothing to check.\n'
fi
exit "$status"
