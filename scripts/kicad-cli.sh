#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Thin wrapper around kicad-cli. Prefers a local kicad-cli on PATH; otherwise
# runs the official KiCad Docker image. All other scripts call through this one.
#
# Keep the toolchain on KiCad 10 (10.0.x series): the .kicad_* format is
# forward-only, so a board saved in 10 will not open in 9. Match the container
# major version to the local install.
#
# Override the image with KICAD_IMAGE (default kicad/kicad:10.0). The official
# KiCad images are published on Docker Hub (kicad/kicad) and GHCR
# (ghcr.io/kicad/kicad) and ship kicad-cli.
set -euo pipefail

# Pinned toolchain versions (single source of truth).
_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
[ -f "$_dir/../versions.env" ] && . "$_dir/../versions.env"
KICAD_IMAGE="${KICAD_IMAGE:-kicad/kicad:10.0}"

if command -v kicad-cli >/dev/null 2>&1; then
  exec kicad-cli "$@"
fi

if command -v docker >/dev/null 2>&1; then
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  exec docker run --rm \
    -u "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -v "$repo_root:$repo_root" \
    -w "$PWD" \
    --entrypoint kicad-cli \
    "$KICAD_IMAGE" "$@"
fi

printf 'error: neither kicad-cli nor docker found on PATH.\n' >&2
printf '       install KiCad 10 (kicad-cli) or Docker, or set KICAD_IMAGE.\n' >&2
exit 127
