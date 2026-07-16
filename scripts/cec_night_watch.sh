#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_night_watch -- overnight watchdog for the cec_fullstack run (owner ask 2026-06-13:
# "monitor for a while and fix any issues"). Every 5 min it LOGS a health line and, if the
# run or dashboard has cleanly DIED (absent 2 consecutive checks), RELAUNCHES it with the
# same env. It does NOT touch V4/broker (Windows-native / external) -- those are logged only.
# Self-terminates after ~8 h. Read docs/fullstack-run-<date>/watchdog.log in the morning.
#
# Launch (needs docker group for the relaunch):
#   sg docker -c 'setsid nohup bash scripts/cec_night_watch.sh </dev/null >/dev/null 2>&1 &'
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-/home/nathan/CEC-Platform}"
cd "$ROOT" || exit 0
RUN_DIR="$ROOT/docs/fullstack-run-${CEC_FS_DATE:-$(date +%F)}"   # today's run dir (was hardcoded stale)
WLOG="$RUN_DIR/watchdog.log"
GW="$(ip route 2>/dev/null | awk '/default/{print $3}')"
RUN_PAT='cec_fullstack[.]py --board'
DASH_PAT='cec_dashboard[.]py'
run_miss=0; dash_miss=0; run_done=0

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$WLOG"; }

relaunch_run() {
  # PHANTOM-RELAUNCH GUARD (2026-06-13): a clean completion logs a "DONE:" line and writes bundle.json.
  # The watchdog can't otherwise tell normal completion from a crash, so it once resurrected a FINISHED
  # run (a fresh daytime run from round 1). If the run already completed, never relaunch -- and latch
  # run_done so a deliverable is produced exactly once.
  if grep -qE '^\[[0-9:]+\] DONE:' "$RUN_DIR/run.log" 2>/dev/null; then
    log "run already COMPLETED (DONE marker present) -- NOT relaunching (phantom-relaunch guard)"
    run_done=1
    return
  fi
  log "RELAUNCH run (absent 2 checks) ..."
  CEC_STREAM_DIR="$RUN_DIR/streams" CEC_VLLM_REVIEWER_MODEL=cec-worker-vision \
    setsid nohup python3 -u scripts/cec_fullstack.py --board eps-8pin --hours 7 \
    >> "$RUN_DIR/run.log" 2>&1 </dev/null &
}
relaunch_dash() {
  log "RELAUNCH dashboard ..."
  setsid nohup python3 scripts/cec_dashboard.py --port 8095 --run-dir "$RUN_DIR" \
    >> "$RUN_DIR/dashboard.log" 2>&1 </dev/null &
}

log "watchdog START (8h); run_pat='$RUN_PAT' gw=$GW"
for i in $(seq 1 96); do
  sleep 300
  # --- liveness ---
  if pgrep -f "$RUN_PAT" >/dev/null 2>&1; then run_miss=0; run_up=1; else run_miss=$((run_miss+1)); run_up=0; fi
  if pgrep -f "$DASH_PAT" >/dev/null 2>&1; then dash_miss=0; dash_up=1; else dash_miss=$((dash_miss+1)); dash_up=0; fi
  # --- progress ---
  round="$(grep -oE -- '--- round [0-9]+' "$RUN_DIR/run.log" 2>/dev/null | tail -1)"
  age=$(( $(date +%s) - $(stat -c %Y "$RUN_DIR/run.log" 2>/dev/null || date +%s) ))
  # --- resources ---
  gpu="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null | tr -d ' ')"
  ram="$(powershell.exe -NoProfile -Command "\$m=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory; 'committed='+[math]::Round(\$m.CommittedBytes/1GB)+'/'+[math]::Round(\$m.CommitLimit/1GB)+'GB avail='+[math]::Round(\$m.AvailableMBytes/1024,1)+'GB'" 2>/dev/null | tr -d '\r')"
  v4="$(curl -s -m4 "http://$GW:8007/health" -o /dev/null -w '%{http_code}' 2>/dev/null)"
  warn=""
  [ "$age" -gt 2400 ] && warn="$warn STALL(${age}s_no_log)"
  [ "$run_up" = 0 ] && warn="$warn RUN_DOWN"
  [ "$v4" != "200" ] && warn="$warn V4_$v4"
  log "run=$run_up dash=$dash_up | ${round:-pre-round} log_age=${age}s | gpu=${gpu} ram=${ram} v4=${v4}${warn:+ ||WARN:$warn}"
  # --- self-heal (clean death only; never resurrect a COMPLETED run) ---
  [ "$run_miss" -ge 2 ] && [ "$run_done" = 0 ] && { relaunch_run; run_miss=0; }
  [ "$dash_miss" -ge 2 ] && { relaunch_dash; dash_miss=0; }
done
log "watchdog END (8h elapsed)"
