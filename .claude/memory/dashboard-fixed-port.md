---
name: dashboard-fixed-port
description: Always reuse ONE fixed dashboard port (8090) — kill the old instance first; never increment the port.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6a1b6a2a-dfb9-4421-89b6-0ca014fb9552
---

The owner called out incrementing the cec_dashboard port (8096→8097→8098→8099) across launches instead of reusing one. ALWAYS run the dashboard on a single fixed port (8090, the documented `--port` default) and kill the prior instance before relaunching; point whatever you're working on at that same port.

**Why:** lingering dashboards pile up and it's confusing which one is current; one stable URL is what the owner watches.

**How to apply:** kill with the BRACKET TRICK to avoid the self-match `exit 144` — `pkill -f "[c]ec_dashboard.py"` (a plain `pkill -f cec_dashboard.py` matches the killing shell's own command line and kills itself → exit 144, the flakiness I kept dodging). Then relaunch `python3 scripts/cec_dashboard.py --port 8090 --run-dir <current-run>` via run_in_background, and confirm HTTP 200 on 8090.
