#!/usr/bin/env bash
# claude-rc-tmux.sh <instance> -- run `claude remote-control` for project <instance> INSIDE a
# dedicated tmux server (socket: claude-rc, session: crc-<instance>) so the live bridge is
# attachable for inspection, while staying systemd-supervised: this wrapper foreground-waits on
# the session, so when `claude remote-control` exits the wrapper exits and systemd
# (Restart=always in claude-rc@.service) reups it. tmux survives terminal/console drops, so a
# dropped WSL console no longer orphans the bridge.
#
#   attach a live bridge:   tmux -L claude-rc attach -t crc-<instance>
#   list bridge sessions:   tmux -L claude-rc ls
#   detach without killing: Ctrl-b d
#
# Referenced by ~/.config/systemd/user/claude-rc@.service (ExecStart). Lives in the repo (ops/)
# so it is durable + rebuildable per the WSL-ephemeral policy.
set -u

inst="${1:?usage: claude-rc-tmux.sh <project-instance>}"
sock="claude-rc"
sess="crc-${inst}"
cdir="${HOME}/${inst}"
bin="/home/nathan/.local/bin/claude"

# Fresh session on each (re)start. `tmux -e` injects the per-instance env so the right project
# prefix is used even when another instance started the shared server first.
tmux -L "$sock" kill-session -t "$sess" 2>/dev/null || true
tmux -L "$sock" new-session -d -s "$sess" -c "$cdir" \
  -e "CLAUDE_REMOTE_CONTROL_SESSION_NAME_PREFIX=${inst}" \
  -e "PATH=${PATH}" \
  "exec '${bin}' remote-control"
# Ensure the window closes when the bridge exits (so we can detect it), regardless of ~/.tmux.conf.
tmux -L "$sock" set-option -t "$sess" remain-on-exit off 2>/dev/null || true

# Graceful stop: on SIGTERM/SIGINT (systemd ExecStop / `systemctl stop`) tear the session down.
trap 'tmux -L "$sock" kill-session -t "$sess" 2>/dev/null; exit 0' TERM INT

# Foreground-supervise the bridge: exit the instant the session/bridge ends so systemd reups it.
while tmux -L "$sock" has-session -t "$sess" 2>/dev/null; do
  sleep 5
done
exit 0
