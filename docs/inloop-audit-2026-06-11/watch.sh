#!/usr/bin/env bash
# Live dashboard for the in-loop audit run. Usage:
#   bash docs/inloop-audit-2026-06-11/watch.sh          # one snapshot
#   watch -n10 'bash docs/inloop-audit-2026-06-11/watch.sh'   # refresh every 10s
cd "$(dirname "$0")" || exit 1
PID=$(pgrep -f "cec_inloop_audit.py --hours" | head -1)
echo "=== run: ${PID:-NOT RUNNING} ($(ps -p "$PID" -o etime= 2>/dev/null | xargs) elapsed) | $(wc -l < measurement.jsonl 2>/dev/null) rounds ==="
echo "--- last activity ---"
grep -E "round [0-9]|routed:|sonnet:|v4:" run.log 2>/dev/null | grep -vE "duplicate image|Debug:|Xvfb|_XSERV|xvfb" | tail -4
echo "--- convergence series (kelvin/plane = physical; pen_total = injected penalties) ---"
python3 - <<'PY'
import json, os
if os.path.exists("measurement.jsonl"):
    print(f"{'rnd':>3} {'verdict':>8} {'kelvin':>6} {'plane':>5} {'drc':>3} {'pen_total':>9} {'rules':>5} {'new?':>5} {'v4risk':>6}")
    for L in open("measurement.jsonl"):
        r = json.loads(L)
        print(f"{r['round']:>3} {r['verdict']:>8} {str(r['kelvin_ok']):>6} {r['plane_signal_mm']:>5} "
              f"{r['drc']:>3} {r['penalty_total']:>9} {r['n_rules']:>5} {str(r.get('sonnet_is_new')):>5} "
              f"{str(r.get('v4_local_min_risk')):>6}")
PY
echo "--- injected ruleset ---"
python3 -c "import json,os;d=json.load(open('live-rules.json')) if os.path.exists('live-rules.json') else {'scorer_penalties':{},'manager_rules':[],'injections':[],'rejections':[]};print('penalties:',d['scorer_penalties']);print('rules:',len(d['manager_rules']),'accepted:',len(d['injections']),'rejected/noop:',len(d['rejections']))" 2>/dev/null
