#!/usr/bin/env bash
# claude-session.sh [project] -- start or re-attach a persistent tmux session running the
# INTERACTIVE `claude` agent, so a dropped terminal / WSL console does not kill the agent.
# This is the survivability fix for the session you TYPE in (the RC systemd units cover the
# headless remote bridges; this covers the local interactive session).
#
#   first run / re-attach:   ops/claude-session.sh            # session claude-CEC-Platform
#   another project:         ops/claude-session.sh CEC_AutoDiagnoser
#   detach (agent keeps running):  Ctrl-b d
#   the terminal/WSL console drops? just re-run the same command to re-attach.
set -u

proj="${1:-CEC-Platform}"
sess="claude-${proj}"
cdir="${HOME}/${proj}"

if tmux has-session -t "$sess" 2>/dev/null; then
  echo "[claude-session] re-attaching to existing session '${sess}'"
  exec tmux attach -t "$sess"
fi

if [ ! -d "$cdir" ]; then
  echo "[claude-session] project dir not found: ${cdir}" >&2
  exit 1
fi
echo "[claude-session] starting '${sess}' in ${cdir}"
exec tmux new-session -s "$sess" -c "$cdir" "claude"
