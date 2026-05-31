#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Vendor official KiCad (and third-party) parts INTO the repo so a plain clone
# is a full-parity, self-contained project — no dependency on a machine's global
# KiCad libraries. Everything is pinned to the KiCad library release in
# versions.env (KICAD_LIB_TAG), matching the pinned KiCad major version.
#
# Subcommands:
#   fetch                      Clone the official symbol/footprint/3D repos at the
#                              pinned tag into build/kicad-libs/ (gitignored cache).
#   add-symbol    <Lib>        Copy <Lib>.kicad_sym from the cache into lib/vendor/.
#   add-footprint <Lib>:<Fp>   Copy one footprint into lib/vendor/<Lib>.pretty/,
#                              vendor its 3D models into lib/3dmodels/, and rewrite
#                              the model paths to be ${KIPRJMOD}-relative.
#   add-3dmodel   <relpath>    Copy a model (path under the 3D repo) into lib/3dmodels/.
#   verify                     Check vendored/design files use ${KIPRJMOD}-relative
#                              paths only (no global ${KICAD*_DIR} or absolute paths).
#
# The cache under build/ is never committed; only the copies under lib/ are.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
set -e

CACHE="$CEC_BUILD/kicad-libs"
LIB_BASE="${KICAD_LIB_BASE:-https://gitlab.com/kicad/libraries}"
TAG="${KICAD_LIB_TAG:-10.0.0}"
VENDOR="$CEC_REPO_ROOT/lib/vendor"
MODELS="$CEC_REPO_ROOT/lib/3dmodels"

cmd_fetch() {
  mkdir -p "$CACHE"
  local repo
  for repo in kicad-symbols kicad-footprints kicad-packages3D; do
    if [ -d "$CACHE/$repo/.git" ]; then
      printf 'fetch: %s already cached (%s)\n' "$repo" "$CACHE/$repo"
    else
      printf 'fetch: cloning %s @ %s\n' "$repo" "$TAG"
      git clone --depth 1 --branch "$TAG" "$LIB_BASE/$repo.git" "$CACHE/$repo"
    fi
  done
  printf 'cache ready: %s\n' "$CACHE"
}

require_cache() {
  [ -d "$CACHE/$1/.git" ] || {
    printf 'error: %s not cached — run `%s fetch` first\n' "$1" "$0" >&2
    exit 2
  }
}

cmd_add_symbol() {
  local lib="${1:?usage: add-symbol <Lib>}"
  require_cache kicad-symbols
  local src="$CACHE/kicad-symbols/$lib.kicad_sym"
  [ -f "$src" ] || { printf 'error: symbol lib not found: %s\n' "$src" >&2; exit 2; }
  mkdir -p "$VENDOR"
  cp "$src" "$VENDOR/$lib.kicad_sym"
  printf 'vendored symbol lib: lib/vendor/%s.kicad_sym\n' "$lib"
  printf 'add to the board sym-lib-table (namespaced nickname so a global lib cannot shadow it):\n'
  printf '  (lib (name "cec-%s")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/%s.kicad_sym")(options "")(descr "Vendored, pinned"))\n' "$lib" "$lib"
}

cmd_add_3dmodel() {
  local rel="${1:?usage: add-3dmodel <relpath-under-packages3D>}"
  require_cache kicad-packages3D
  local src="$CACHE/kicad-packages3D/$rel"
  [ -f "$src" ] || { printf 'error: model not found: %s\n' "$src" >&2; exit 2; }
  mkdir -p "$MODELS/$(dirname "$rel")"
  cp "$src" "$MODELS/$rel"
  printf 'vendored 3D model: lib/3dmodels/%s\n' "$rel"
}

# Rewrite one model path in a footprint to a repo-relative one, vendoring the
# model file. Handles the common ${KICAD<n>_3DMODEL_DIR}/<rel> form.
vendor_model_in_footprint() {
  local fp_file="$1" model="$2" rel new
  rel="${model#*\}/}"                       # strip ${...}/ -> Connector_RJ/RJ45.wrl
  if [ "$rel" = "$model" ]; then
    printf 'note: non-standard 3D path left as-is: %s\n' "$model" >&2
    return 0
  fi
  if [ -f "$CACHE/kicad-packages3D/$rel" ]; then
    mkdir -p "$MODELS/$(dirname "$rel")"
    cp -n "$CACHE/kicad-packages3D/$rel" "$MODELS/$rel"
  else
    printf 'note: model not in 3D cache (rewriting path anyway): %s\n' "$rel" >&2
  fi
  new="\${KIPRJMOD}/../../lib/3dmodels/$rel"
  local pat rep
  pat="$(printf '%s' "$model" | sed 's/[][\\/.*^$]/\\&/g')"
  rep="$(printf '%s' "$new"   | sed 's/[&/\\]/\\&/g')"
  sed -i "s/$pat/$rep/g" "$fp_file"
}

cmd_add_footprint() {
  local spec="${1:?usage: add-footprint <Lib>:<Footprint>}"
  local lib="${spec%%:*}" fp="${spec#*:}"
  [ "$lib" != "$spec" ] && [ -n "$fp" ] || { printf 'error: expected <Lib>:<Footprint>\n' >&2; exit 2; }
  require_cache kicad-footprints
  local src="$CACHE/kicad-footprints/$lib.pretty/$fp.kicad_mod"
  [ -f "$src" ] || { printf 'error: footprint not found: %s\n' "$src" >&2; exit 2; }
  local dest_dir="$VENDOR/$lib.pretty"
  mkdir -p "$dest_dir"
  local dest="$dest_dir/$fp.kicad_mod"
  cp "$src" "$dest"

  local model
  while IFS= read -r model; do
    [ -n "$model" ] && vendor_model_in_footprint "$dest" "$model"
  done < <(grep -oE '\(model "[^"]+"' "$dest" | sed -E 's/^\(model "//; s/"$//')

  printf 'vendored footprint: lib/vendor/%s.pretty/%s.kicad_mod\n' "$lib" "$fp"
  printf 'add to the board fp-lib-table (once per library; namespaced nickname so a global lib cannot shadow it):\n'
  printf '  (lib (name "cec-%s")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/%s.pretty")(options "")(descr "Vendored, pinned"))\n' "$lib" "$lib"
  printf 'verify the result opens cleanly in KiCad (check the 3D view).\n'
}

cmd_verify() {
  local status=0 hits
  hits="$(grep -RInE '\$\{KICAD[0-9]*_(3DMODEL|FOOTPRINT|SYMBOL)_DIR\}|"(/|[A-Za-z]:\\)' \
    --include='*.kicad_mod' --include='*.kicad_sym' --include='*.kicad_pcb' \
    --include='sym-lib-table' --include='fp-lib-table' \
    "$CEC_REPO_ROOT/lib" "$CEC_REPO_ROOT/hubs" "$CEC_REPO_ROOT/modules" 2>/dev/null || true)"
  if [ -n "$hits" ]; then
    printf 'FAIL: global or absolute paths found — vendor these for clone parity:\n%s\n' "$hits" >&2
    status=1
  else
    printf 'ok: vendored/design files use ${KIPRJMOD}-relative paths only\n'
  fi

  # Vendored-library nicknames must be namespaced (cec / cec-*). A bare stock
  # nickname (Package_SO, Resistor_SMD, Device, ...) can be shadowed by a
  # machine's global KiCad libraries on another PC — which is exactly what broke
  # the INA228 VSSOP-10 footprint lookup. Enforce the namespace so vendoring is
  # real isolation, not a coincidence of matching the global lib version.
  local collide
  collide="$(grep -RhoE '\(name "[^"]+"' \
      --include='sym-lib-table' --include='fp-lib-table' \
      "$CEC_REPO_ROOT/lib" "$CEC_REPO_ROOT/hubs" "$CEC_REPO_ROOT/modules" 2>/dev/null \
    | sed -E 's/.*name "([^"]+)".*/\1/' | sort -u | grep -vE '^cec($|-)' || true)"
  if [ -n "$collide" ]; then
    printf 'FAIL: un-namespaced library nicknames (prefix with cec- so global libs cannot shadow them):\n%s\n' "$collide" >&2
    status=1
  else
    printf 'ok: all library-table nicknames are namespaced (cec / cec-*)\n'
  fi
  return "$status"
}

sub="${1:-}"
shift || true
case "$sub" in
  fetch)         cmd_fetch "$@" ;;
  add-symbol)    cmd_add_symbol "$@" ;;
  add-footprint) cmd_add_footprint "$@" ;;
  add-3dmodel)   cmd_add_3dmodel "$@" ;;
  verify)        cmd_verify "$@" ;;
  *) printf 'usage: %s {fetch | add-symbol <Lib> | add-footprint <Lib>:<Fp> | add-3dmodel <rel> | verify}\n' "$0" >&2; exit 2 ;;
esac
