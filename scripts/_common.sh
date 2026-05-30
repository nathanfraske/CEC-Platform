#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Shared helpers for the CEC kicad-cli wrapper scripts. Source this; don't run it.
# shellcheck shell=bash

set -uo pipefail

CEC_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEC_REPO_ROOT="$(cd "$CEC_SCRIPTS_DIR/.." && pwd)"
CEC_KICAD="$CEC_SCRIPTS_DIR/kicad-cli.sh"
CEC_BUILD="$CEC_REPO_ROOT/build"

# board_name <path> : filename with directory and extension stripped
board_name() {
  local f
  f="$(basename -- "$1")"
  printf '%s' "${f%.*}"
}

# abspath <path> : absolute path (file need not be readable, but dir must exist)
abspath() {
  if [ -d "$1" ]; then
    (cd "$1" && pwd)
  else
    printf '%s/%s' "$(cd "$(dirname -- "$1")" && pwd)" "$(basename -- "$1")"
  fi
}

# need_file <path> : exit 2 unless path is a regular file
need_file() {
  if [ ! -f "$1" ]; then
    printf 'error: file not found: %s\n' "$1" >&2
    exit 2
  fi
}

# out_dir_for <design-path> : ensure and print build/<board_name>
out_dir_for() {
  local d="$CEC_BUILD/$(board_name "$1")"
  mkdir -p "$d"
  printf '%s' "$d"
}
