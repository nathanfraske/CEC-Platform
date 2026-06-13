#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stop hook (owner 2026-06-13): when the agent goes idle, let the DeepSeek-V4 seat pick up HANDED-OFF
# tasks IF V4 is up and the box is otherwise idle. run_idle() self-guards (v4-up + no heavy local run +
# single-runner lock), so this is a cheap no-op when the queue is empty or the box is busy. Detached so
# the hook returns instantly; a V4 task runs ~10 min in the background, using spare cycles.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-/home/nathan/CEC-Platform}"
PEND="$ROOT/docs/v4-queue/pending"
# fast no-op: nothing queued -> don't even spawn
[ -d "$PEND" ] && ls -A "$PEND" 2>/dev/null | grep -q . || exit 0
setsid nohup python3 "$ROOT/scripts/cec_v4_queue.py" run-idle >/dev/null 2>&1 </dev/null &
exit 0
