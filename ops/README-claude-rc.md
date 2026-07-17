# Claude session survivability (remote-control + interactive)

Fixes the failure mode where a Claude remote-control ("RC") session goes idle / cannot reconnect
and the remote UI still shows agents "connected" but unresponsive — you open a new session while the
old one is a zombie bridge.

**Root framing:** never let the *session* be load-bearing. The heavy work is already decoupled
(detached `setsid nohup` runs + `cec_night_watch.sh` watchdog + the `cec-llm-broker` systemd unit),
which is why a 7h run survived a disconnect. These pieces make the *session host* as survivable as
the work.

## Pieces

| Piece | What it does | Where |
|---|---|---|
| `claude-rc@.service` | systemd **user** unit, `Restart=always` — auto-reups the headless RC bridges | `~/.config/systemd/user/` (canonical copy here in `ops/`) |
| `claude-rc-tmux.sh` | systemd `ExecStart` wrapper — runs each bridge **inside a dedicated tmux server** (socket `claude-rc`, session `crc-<project>`) so it survives console drops and is attachable; foreground-waits so systemd still supervises + reups | `ops/` |
| `claude-session.sh` | launches/​re-attaches the **interactive** `claude` you type in, inside tmux — a dropped terminal no longer kills the agent | `ops/` |
| `rc-recover.sh` | recovers a hung/zombied bridge — cleanly restarts the systemd RC service(s) (tears down the stale bridge + tmux session, relaunches) | `ops/` |

## Use

```bash
# interactive session that survives a terminal/WSL-console drop:
ops/claude-session.sh                 # start or re-attach (session claude-CEC-Platform)
#   detach (agent keeps running): Ctrl-b d ; re-attach: re-run the same command

# inspect a live headless bridge:
tmux -L claude-rc attach -t crc-CEC-Platform      # Ctrl-b d to detach
tmux -L claude-rc ls

# recover a zombied bridge (run from a LOCAL terminal, not the dead remote session):
ops/rc-recover.sh                     # all instances
ops/rc-recover.sh CEC-Platform        # one instance
```

## Applying the unit change

`systemctl --user daemon-reload` has been run, so the new `ExecStart` (through the tmux wrapper)
is **live on the next restart/boot** of each instance. To apply immediately without waiting for a
WSL restart:

```bash
systemctl --user restart claude-rc@CEC-Platform.service claude-rc@CEC_AutoDiagnoser.service
# (or: ops/rc-recover.sh)   -- this drops any in-flight remote session on those instances
```

## WSL networking (mirrored) — DEFERRED, owner call

Mirrored networking (`networkingMode=mirrored` in `%UserProfile%\.wslconfig`) would help the
network-change case (Wi-Fi/VPN/sleep-resume leaving a stale NAT lease), BUT this box's `.wslconfig`
is tuned for the compute plane (`localhostForwarding=true`, 176 GB for the WSL-resident DeepSeek
seat) and the broker (:8080) ↔ Windows-host LLM (:8007) ↔ Docker-container topology depends on the
current NAT semantics. Mirrored mode overrides `localhostForwarding` and changes how all three
reach each other — a real risk to overnight routing runs. tmux + auto-reup + `rc-recover.sh` fix
the RC-survival problem **without** touching networking, so mirrored is left OFF pending an owner
decision + a post-`wsl --shutdown` reachability test (broker curl, container → broker, broker → :8007).

## Durability (WSL-ephemeral policy)

These scripts + the unit live in the repo (`ops/`) so they survive a distro rebuild. Follow-up:
commit them to `main` and add an install step to `ops/provision.sh` (copy `claude-rc@.service` →
`~/.config/systemd/user/`, `systemctl --user enable claude-rc@<project>`). Until then they exist on
disk in the always-present main checkout (`/home/nathan/CEC-Platform/ops/`), which survives a WSL
*restart* (not a rebuild).
