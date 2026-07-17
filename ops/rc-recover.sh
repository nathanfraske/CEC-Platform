#!/usr/bin/env bash
# rc-recover.sh [instance] -- recover a hung/zombied Claude remote-control bridge (the remote UI
# shows agents "connected" but they are unresponsive). Cleanly restarts the systemd-managed RC
# service(s), which tear down the stale bridge + its tmux session and relaunch fresh under tmux.
#
# Run from a LOCAL terminal, NOT from inside the zombied remote session (a self-guard warns you).
#
#   ops/rc-recover.sh                  # restart every claude-rc@* user service
#   ops/rc-recover.sh CEC-Platform     # restart just that instance
set -u

filter="${1:-}"

echo "[rc-recover] current RC services:"
systemctl --user --no-pager list-units 'claude-rc@*' 2>/dev/null || true
echo

# Self-guard: warn if this shell descends from a live RC bridge (restarting it kills us).
pid=$$
while [ "${pid:-0}" -gt 1 ]; do
  cmd=$(ps -o cmd= -p "$pid" 2>/dev/null || true)
  case "$cmd" in
    *"claude remote-control"*)
      echo "[rc-recover] WARNING: this shell descends from a live RC bridge (pid $pid)."
      echo "             Restarting will drop THIS session -- run from a local terminal instead."
      read -r -p "             Continue anyway? [y/N] " ans
      [ "${ans:-N}" = "y" ] || { echo "[rc-recover] aborted."; exit 1; }
      break;;
  esac
  pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
done

units=$(systemctl --user list-units 'claude-rc@*' --no-legend --plain 2>/dev/null | awk '{print $1}')
[ -n "$filter" ] && units=$(printf '%s\n' $units | grep -F -- "$filter" || true)
if [ -z "${units// /}" ]; then
  echo "[rc-recover] no matching claude-rc@* units."
  exit 0
fi

for u in $units; do
  echo "[rc-recover] restarting $u ..."
  systemctl --user restart "$u" && echo "  -> $(systemctl --user is-active "$u")"
done
echo "[rc-recover] done. attach a live bridge with:  tmux -L claude-rc attach -t crc-<project>"
