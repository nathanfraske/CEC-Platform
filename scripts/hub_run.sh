#!/usr/bin/env bash
# Launch a full Hub pipeline run (place -> route -> check) in the routing container AND auto-point
# the live dashboard at it -- in ONE command, with NO manual repoint.
#
#   bash scripts/hub_run.sh [OUT_DIR] [HOURS] [ROUTE_CANDIDATES] [SEATS]
#   # defaults: build/hub-full 1 2 auto ; panel port via CEC_PANEL_PORT (default 8095)
#   # SEATS = auto|cloud|local|off (or CEC_JUDGE env). auto: --hours>=2 -> local, else cloud
#   #   (owner policy: cloud or local on demand, defaulting to cloud; overnight-long -> local).
#
# How the auto-repoint works: the dashboard serves a STABLE symlink (build/hub-LIVE) and reads its
# files per-poll, so retargeting the symlink at the new run repoints the panel LIVE -- the dashboard
# never restarts. Every launch retargets the symlink, so the panel always follows the latest run.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-build/hub-full}"
HOURS="${2:-1}"
CANDS="${3:-2}"
SEATS="${4:-${CEC_JUDGE:-auto}}"      # cloud/local toggle (cec_seats); CEC_JUDGE env or 4th arg
PORT="${CEC_PANEL_PORT:-8095}"
LIVE="build/hub-LIVE"

mkdir -p "$OUT" build

# 1. AUTO-REPOINT: retarget the stable symlink the dashboard serves (relative within build/ so it
#    resolves on the host; the run writes to $OUT directly and never touches the symlink).
ln -sfn "$(realpath --relative-to=build "$OUT")" "$LIVE"
echo "panel: $LIVE -> $OUT"

# 2. Ensure the dashboard is up, pointed at the stable symlink (board render via the compose
#    'routing' service -> the panel MUST run with docker-group access, hence `sg docker`). If already
#    up it just follows the retargeted symlink.
if curl -sf "http://localhost:$PORT/" >/dev/null 2>&1; then
  echo "panel: already serving http://localhost:$PORT (symlink retargeted -> auto-followed)"
else
  GLOB="$(pwd)/$LIVE/hub-cand*.kicad_pcb,$(pwd)/$LIVE/route-cand*/*-routed.kicad_pcb"
  sg docker -c "setsid nohup python3 scripts/cec_dashboard.py --port $PORT \
    --run-dir $LIVE --board-glob '$GLOB' >build/hub-panel.log 2>&1 </dev/null &"
  sleep 1
  echo "panel: started http://localhost:$PORT  (run-dir=$LIVE)"
fi

# 3. Launch the run detached in the routing container (daemon-managed -> survives the session; the
#    script's own --hours budget exits cleanly, so NO outer `timeout` that would orphan the container).
#    --add-host + CEC_VLLM_URL make the broker (:8080 on the host) reachable for LOCAL seats; the
#    CEC_* envs forward the toggle/model/threshold overrides. NOTE: CLOUD seats shell `claude -p`,
#    which must be present in the cec/routing image -- if absent the run logs the degrade and falls
#    back to deterministic (visible, never silent). See docs/agentic-integration-forensics-2026-06-14.md.
VLLM_URL="${CEC_VLLM_URL:-http://host.docker.internal:8080}"
sg docker -c "docker rm -f hub-hour >/dev/null 2>&1 || true; \
  docker run -d --rm --name hub-hour --add-host=host.docker.internal:host-gateway \
  -e CEC_VLLM_URL='$VLLM_URL' -e CEC_JUDGE='${CEC_JUDGE:-}' \
  -e CEC_HUB_MANAGER_MODEL='${CEC_HUB_MANAGER_MODEL:-}' -e CEC_HUB_WORKER_MODEL='${CEC_HUB_WORKER_MODEL:-}' \
  -e CEC_OVERNIGHT_HOURS_MIN='${CEC_OVERNIGHT_HOURS_MIN:-}' \
  -v $(pwd):/work -w /work cec/routing:kicad10 \
  python3 -u scripts/hub_pipeline_run.py --hours $HOURS --route-candidates $CANDS --out $OUT --seats $SEATS"
echo "run: launched (container hub-hour, --hours $HOURS --route-candidates $CANDS --seats $SEATS --out $OUT)"
echo "watch: http://localhost:$PORT   |   tail -f $OUT/run.log"
