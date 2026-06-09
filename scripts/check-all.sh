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

# R-03 (agentic-pipeline review): a board that has SHIPPED -- any fab/<board>-* snapshot
# exists -- is ALWAYS checked, DRAFT marker or not. Before this rule every design dir
# carried DRAFT, so the CI ERC/DRC gate checked ZERO boards while two of them had fabbed
# gerbers in fab/. A DRAFT marker on a fabbed board would hide exactly the divergences
# the gate exists to surface.
fabbed() {  # $1 = board file -> 0 if a fab snapshot exists for its board dir
  local board
  board="$(basename "$(dirname "$1")")"
  compgen -G "$CEC_REPO_ROOT/fab/$board-*" >/dev/null 2>&1
}

# The CI gate fails on ERROR-level violations only. The hand-maintained boards carry
# documented-benign WARNING noise (lib_symbol_mismatch generator cache, silk overlaps,
# the two pre-existing off-grid PWR_FLAG stamps) -- gating on warnings makes the sweep
# permanently red and the signal indistinguishable from noise. Warnings still land in
# the JSON reports under build/ for review; run erc.sh/drc.sh directly (no env) for the
# all-severities interactive check.
export CEC_SEVERITY_FLAGS="--severity-error"

# Static connectivity audit (no kicad-cli): catches dangling wires/labels/
# no-connects and off-grid points in the generated schematics. Runs even for
# DRAFT boards, since it is a generator regression guard, not an ERC pass.
if command -v python3 >/dev/null 2>&1; then
  printf '==> schematic connectivity audit\n'
  python3 "$CEC_SCRIPTS_DIR/audit-sch.py" || status=1
fi

# Electrical rule check over schematics that contain symbols.
while IFS= read -r -d '' f; do
  found=1
  rel="${f#"$CEC_REPO_ROOT"/}"
  if [ -e "$(dirname "$f")/DRAFT" ]; then
    if fabbed "$f"; then
      printf 'ERC despite DRAFT (fab snapshot exists): %s\n' "$rel"
    else
      printf 'skip ERC (DRAFT marker): %s\n' "$rel"
      continue
    fi
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
    if fabbed "$f"; then
      printf 'DRC despite DRAFT (fab snapshot exists): %s\n' "$rel"
    else
      printf 'skip DRC (DRAFT marker): %s\n' "$rel"
      continue
    fi
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
