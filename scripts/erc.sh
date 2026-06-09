#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Electrical rule check for one board schematic.
#   usage: scripts/erc.sh <board.kicad_sch>
#   exit:  0 clean, 5 violations (see JSON report), other = tool error
#   env:   CEC_SEVERITY_FLAGS — extra kicad-cli severity args (e.g. --severity-error
#          to gate on errors only; check-all.sh sets this so the CI gate doesn't
#          fail on documented-benign warning noise). Default: all severities.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

sch="${1:-}"
[ -n "$sch" ] || { printf 'usage: %s <board.kicad_sch>\n' "$0" >&2; exit 2; }
need_file "$sch"
sch="$(abspath "$sch")"

report="$(out_dir_for "$sch")/erc.json"

rc=0
# shellcheck disable=SC2086  -- CEC_SEVERITY_FLAGS is deliberately word-split
"$CEC_KICAD" sch erc ${CEC_SEVERITY_FLAGS:-} --exit-code-violations --format json -o "$report" "$sch" || rc=$?
case "$rc" in
  0) printf 'ERC clean: %s\n' "$(board_name "$sch")" ;;
  5) printf 'ERC VIOLATIONS: %s — see %s\n' "$(board_name "$sch")" "$report" >&2 ;;
  *) printf 'ERC error (rc=%s): %s\n' "$rc" "$(board_name "$sch")" >&2 ;;
esac
exit "$rc"
