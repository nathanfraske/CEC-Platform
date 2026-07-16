#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Run the `gh` CLI as nathanfraske-bot, NOT the owner's WSL-local gh login. The agent's GitHub API
# actions -- PR create/comment/edit, `gh api` (e.g. changing a PR base) -- otherwise authenticate as
# whoever `gh auth` is logged in as, which on this box is the OWNER. (Git *pushes* go through the bot
# credential helper; this is the gh-API equivalent.) Owner directive 2026-06-13: act as the bot, not me.
#
#   ./ops/secrets/gh-bot.sh pr comment 56 --body ...
#   ./ops/secrets/gh-bot.sh api repos/OWNER/REPO/pulls/56 -X PATCH -f base=...
#
# Sources the survives-WSL bot PAT (ops/secrets/load-secrets.sh, default /mnt/e/secrets/cec-bot.env)
# and refuses to fall back to the owner's login if the PAT is absent.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$DIR/load-secrets.sh" 2>/dev/null || true
if [ -z "${CEC_BOT_PAT:-}" ]; then
  echo "gh-bot: no CEC_BOT_PAT (${CEC_SECRETS_FILE:-/mnt/e/secrets/cec-bot.env}) -- refusing to run gh as the owner." >&2
  exit 1
fi
exec env GH_TOKEN="$CEC_BOT_PAT" GH_HOST=github.com gh "$@"
