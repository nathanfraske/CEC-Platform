#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Repo-hygiene checks that do not need kicad-cli:
#   1. No retired Mini-Fit Jr footprints in any KiCad design file.
#   2. Library tables use project-relative paths (${KIPRJMOD}), not absolutes.
# Exits nonzero if any check fails. (Markdown docs may mention Mini-Fit Jr as
# history; only design files are scanned.)
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status=0

printf '==> no Mini-Fit Jr in design files\n'
mf_hits="$(grep -RInE 'mini[_ -]?fit' \
  --include='*.kicad_sch' --include='*.kicad_pcb' --include='*.kicad_mod' \
  --include='*.kicad_sym' --include='fp-lib-table' \
  "$CEC_REPO_ROOT" 2>/dev/null || true)"
if [ -n "$mf_hits" ]; then
  printf 'FAIL: Mini-Fit Jr reference in design files (must be RJ-45 8P8C):\n%s\n' "$mf_hits" >&2
  status=1
else
  printf '  ok: none found\n'
fi

printf '==> library tables use ${KIPRJMOD} (no absolute paths)\n'
lt_files="$(find "$CEC_REPO_ROOT" \( -path '*/build' -o -path '*/.git' \) -prune -o \
  -type f \( -name 'sym-lib-table' -o -name 'fp-lib-table' \) -print 2>/dev/null)"
if [ -z "$lt_files" ]; then
  printf '  ok: no library tables yet\n'
else
  bad=0
  while IFS= read -r lt; do
    [ -n "$lt" ] || continue
    # any (uri "...") entry that does not reference a ${...} path variable
    hits="$(grep -nE '\(uri[[:space:]]' "$lt" 2>/dev/null | grep -v '\${' || true)"
    if [ -n "$hits" ]; then
      printf 'FAIL: non-relative library uri in %s:\n%s\n' "$lt" "$hits" >&2
      bad=1
    fi
  done <<< "$lt_files"
  if [ "$bad" -eq 0 ]; then
    printf '  ok: all entries project-relative\n'
  else
    status=1
  fi
fi

printf '==> corpus provenance lint (SB-13/14: no sourceless or model-sourced entries)\n'
if command -v python3 >/dev/null 2>&1; then
  python3 "$CEC_SCRIPTS_DIR/cec_corpus_lint.py" || status=1
else
  printf '  skip: python3 not available\n'
fi

printf '==> policy-as-code load assertions (CL-10: bindings usable, DF-05/07 firewall clean)\n'
if command -v python3 >/dev/null 2>&1; then
  python3 "$CEC_SCRIPTS_DIR/cec_policy.py" validate || status=1
else
  printf '  skip: python3 not available\n'
fi

printf '==> library + 3D-model paths are in-repo (clone parity)\n'
glob_hits="$(grep -RInE '\$\{KICAD[0-9]*_(3DMODEL|FOOTPRINT|SYMBOL)_DIR\}' \
  --exclude-dir=build --exclude-dir=.git \
  --include='*.kicad_mod' --include='*.kicad_sym' --include='*.kicad_pcb' \
  --include='sym-lib-table' --include='fp-lib-table' \
  "$CEC_REPO_ROOT" 2>/dev/null || true)"
if [ -n "$glob_hits" ]; then
  printf 'FAIL: machine-global KiCad paths found — vendor these for clone parity:\n%s\n' "$glob_hits" >&2
  status=1
else
  printf '  ok: no global KiCad path variables in design files\n'
fi

exit "$status"
