#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Source this (don't run it). Exports CEC_BOT_PAT from the Windows-side, survives-
# WSL secrets file (default /mnt/e/secrets/cec-bot.env). See ops/secrets/README.md.
# Fail-soft: a missing file is not an error -- callers fall back to the WSL-local
# gh credential (and should warn that that copy is disposable).
# shellcheck shell=bash

CEC_SECRETS_FILE="${CEC_SECRETS_FILE:-/mnt/e/secrets/cec-bot.env}"
if [ -f "$CEC_SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$CEC_SECRETS_FILE"; set +a
fi
export CEC_BOT_PAT="${CEC_BOT_PAT:-}"
