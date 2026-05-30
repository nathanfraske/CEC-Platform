#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# CI sweep: run ERC over every schematic and DRC over every layout that has
# placed parts. Boards with no placed symbols/footprints (skeleton stubs) are
# skipped — there is nothing to check yet — so a young repo stays green until
# real design content lands. Exits nonzero if any populated board reports
# violations or a tool error.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status=0
found=0

# Electrical rule check over schematics that contain symbols.
while IFS= read -r -d '' f; do
  found=1
  rel="${f#"$CEC_REPO_ROOT"/}"
  if [ -e "$(dirname "$f")/DRAFT" ]; then
    printf 'skip ERC (DRAFT marker): %s\n' "$rel"
    continue
  fi
  if ! grep -q '(symbol' "$f" 2>/dev/null; then
    printf 'skip ERC (no placed symbols): %s\n' "$rel"
    continue
  fi
  "$CEC_SCRIPTS_DIR/erc.sh" "$f" || status=1
done < <(find "$CEC_REPO_ROOT" \( -path '*/build' -o -path '*/.git' \) -prune -o \
         -type f -name '*.kicad_sch' -print0)

# Design rule check over layouts that contain footprints.
while IFS= read -r -d '' f; do
  found=1
  rel="${f#"$CEC_REPO_ROOT"/}"
  if [ -e "$(dirname "$f")/DRAFT" ]; then
    printf 'skip DRC (DRAFT marker): %s\n' "$rel"
    continue
  fi
  if ! grep -q '(footprint' "$f" 2>/dev/null; then
    printf 'skip DRC (no placed footprints): %s\n' "$rel"
    continue
  fi
  "$CEC_SCRIPTS_DIR/drc.sh" "$f" || status=1
done < <(find "$CEC_REPO_ROOT" \( -path '*/build' -o -path '*/.git' \) -prune -o \
         -type f -name '*.kicad_pcb' -print0)

if [ "$found" -eq 0 ]; then
  printf 'check-all: no .kicad_sch or .kicad_pcb files yet — nothing to check.\n'
fi
exit "$status"
