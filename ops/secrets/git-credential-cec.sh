#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Git credential helper -- authenticates git as the nathanfraske-bot account using
# the survives-WSL bot PAT (ops/secrets/, default /mnt/e/secrets/cec-bot.env), so
# pushes never depend on the WSL-local gh login (WSL-ephemeral state policy).
#
# Wire it (repo-local, resets the inherited gh helper for github.com):
#   git config --local credential.https://github.com.helper ""
#   git config --local --add credential.https://github.com.helper \
#       "$PWD/ops/secrets/git-credential-cec.sh"
#
# Only answers `get` for github.com, and only if the PAT is present; otherwise it
# stays silent so git falls through to the next helper. Never prints the token to
# anything but git's stdin contract.
set -uo pipefail
[ "${1:-}" = "get" ] || exit 0

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/load-secrets.sh" 2>/dev/null || true
[ -n "${CEC_BOT_PAT:-}" ] || exit 0

# Read git's request (protocol/host on stdin); only serve github.com.
host=""
while IFS='=' read -r k v; do [ "$k" = "host" ] && host="$v"; [ -z "$k" ] && break; done
case "$host" in
  github.com|"") : ;;
  *) exit 0 ;;
esac

printf 'username=%s\n' "${CEC_BOT_USER:-nathanfraske-bot}"
printf 'password=%s\n' "$CEC_BOT_PAT"
