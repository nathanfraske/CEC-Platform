#!/usr/bin/env bash
# Launch a full Hub pipeline run (place -> route -> check) in the routing container AND auto-point
# the live dashboard at it -- in ONE command, with NO manual repoint.
#
#   bash scripts/hub_run.sh [OUT_DIR] [HOURS] [ROUTE_CANDIDATES]
#   # defaults: build/hub-full 1 2 ; panel port via CEC_PANEL_PORT (default 8095)
#
# How the auto-repoint works: the dashboard serves a STABLE symlink (build/hub-LIVE) and reads its
# files per-poll, so retargeting the symlink at the new run repoints the panel LIVE -- the dashboard
# never restarts. Every launch retargets the symlink, so the panel always follows the latest run.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-build/hub-full}"
HOURS="${2:-1}"
CANDS="${3:-2}"
PORT="${CEC_PANEL_PORT:-8095}"
LIVE="build/hub-LIVE"

mkdir -p "$OUT" build

# 1. AUTO-REPOINT: retarget the stable symlink the dashboard serves (relative within build/ so it
#    resolves on the host; the run writes to $OUT directly and never touches the symlink).
ln -sfn "$(realpath --relative-to=build "$OUT")" "$LIVE"
echo "panel: $LIVE -> $OUT"

# 2. Ensure the dashboard is up on the host, pointed at the stable symlink (board render via the
#    compose 'routing' service). If already up it just follows the retargeted symlink.
if curl -sf "http://localhost:$PORT/" >/dev/null 2>&1; then
  echo "panel: already serving http://localhost:$PORT (symlink retargeted -> auto-followed)"
else
  setsid nohup python3 scripts/cec_dashboard.py --port "$PORT" \
    --run-dir "$LIVE" \
    --board-glob "$(pwd)/$LIVE/route-cand*/*-routed.kicad_pcb" \
    >build/hub-panel.log 2>&1 </dev/null &
  sleep 1
  echo "panel: started http://localhost:$PORT  (run-dir=$LIVE)"
fi

# 3. Launch the run detached in the routing container (daemon-managed -> survives the session; the
#    script's own --hours budget exits cleanly, so NO outer `timeout` that would orphan the container).
sg docker -c "docker rm -f hub-hour >/dev/null 2>&1 || true; \
  docker run -d --rm --name hub-hour -v $(pwd):/work -w /work cec/routing:kicad10 \
  python3 -u scripts/hub_pipeline_run.py --hours $HOURS --route-candidates $CANDS --out $OUT"
echo "run: launched (container hub-hour, --hours $HOURS --route-candidates $CANDS --out $OUT)"
echo "watch: http://localhost:$PORT   |   tail -f $OUT/run.log"
