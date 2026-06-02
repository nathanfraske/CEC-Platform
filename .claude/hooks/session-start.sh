#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SessionStart hook for Claude Code on the web: make kicad-cli available so ERC /
# DRC / netlist / BOM work in remote sessions. Thin wrapper around the reusable
# scripts/setup-kicad-cli.sh.
#
# Synchronous: on a cold container the session waits for the install (a few
# minutes); the post-hook container snapshot is then cached, so warm sessions
# hit the idempotent fast-path and skip it. Local (GUI) dev boxes are untouched.
set -uo pipefail

# Remote-only -- on a local machine the developer has their own KiCad install.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
bash "$root/scripts/setup-kicad-cli.sh" || true
exit 0
