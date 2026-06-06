# Self-hosted routing — run the CPU-heavy compute on your own hardware

The automated routing system (`scripts/cec_fr.py` + `cec_score.py` + `cec_router.py`, see
`scripts/README-cec_pcb.md`) splits into two planes:

- **Control plane** — the LLM tiers (planning, judging, repairing). This is *remote inference*
  in a Claude session; it uses ~0 CPU and always runs remotely.
- **Compute plane** — the actual CPU drain: **Freerouting JVMs** (one per candidate) and
  **`kicad-cli` DRC**. These are plain local subprocesses, so they run wherever the workflow's
  steps execute.

This doc wires the **compute plane onto your hardware** via a **GitHub Actions self-hosted
runner** (`.github/workflows/route.yml`, *Route (self-hosted)*), so "route the board" runs on
your CPU and returns the routed candidate + decision log + render as artifacts — while you keep
triggering and reviewing from the web/phone/API. Works on **Windows, Linux, or macOS**.

## TL;DR — do I need to configure any PATHs?

**No.** Install the two dependencies and you're done — the launcher finds everything itself:

- **Windows:** install **KiCad 10** and a **JRE 21**. `scripts\route.ps1` auto-discovers KiCad's
  bundled `python.exe` (the only Python on Windows with `pcbnew`), `kicad-cli.exe`, and `java`,
  and assembles `PATH` for its own run. You do **not** edit system PATH. (Only edge case: if KiCad
  is installed somewhere nonstandard, set `KICAD_PYTHON` to its `python.exe`.) **No xvfb** — see
  the interactive-session note below.
- **Linux/macOS:** install KiCad 10 (+ `pcbnew`), a JRE 21, and (headless Linux only) `xvfb`.
  `python3 scripts/cec_router.py` runs directly; the prereqs step checks PATH and fails fast with
  hints if something's missing.

The Freerouting jar is **not** a PATH concern — `cec_fr.ensure_jar()` downloads the pinned
**v1.7.0** to `~/.cache/cec/` on first run (or set `CEC_FREEROUTING_JAR` to a local jar).

## Why this scales

A Freerouting run is one JVM at ~0.5 GB pinning one core; the practical ceiling is **one
candidate per core** (`cec_fr.generate_batch` caps `max_workers = min(seeds, nproc)`), and RAM is
rarely the limit. On your hardware the ceiling becomes *your* core count — an 8/16/32-core box
runs that many candidates in parallel, versus the few vCPU of a GitHub-hosted runner.

---

## Windows

### 1. Install (two things)

| Need | Why | Get it |
|---|---|---|
| **KiCad 10** (Windows installer) | bundles `python.exe` **with `pcbnew`** + `kicad-cli.exe` | kicad.org/download/windows |
| **JRE 21** | runs Freerouting | Adoptium Temurin 21 (adoptium.net) |

That's it — **no xvfb, no PATH editing, no separate Python.** Critically, do **not** try to use a
system / Microsoft-Store Python: on Windows `pcbnew` only imports from KiCad's *own* interpreter,
which `route.ps1` locates for you.

Verify locally any time:

```powershell
.\scripts\route-prereqs.ps1
```

### 2. The one Windows-specific catch: Freerouting needs a desktop session

There is no xvfb on Windows, and none is needed — Java uses the native Win32 display. But that
means Freerouting needs a **real interactive desktop session**. So register the self-hosted runner
to **run interactively, not as a background Session-0 service**:

- During runner setup, use **`run.cmd`** from a logged-in desktop session (don't `svc install` it
  as a service), **or** configure auto-logon + launch `run.cmd` via Task Scheduler set to
  *"Run only when user is logged on"*.
- A runner installed as a plain Windows **service** runs in Session 0 with no desktop and may fail
  Freerouting's AWT startup. Interactive is the reliable configuration.

(`-Djava.awt.headless=true` is *not* a workaround — Freerouting 1.7.0 touches screen APIs that
throw `HeadlessException` under it.)

### Keeping Freerouting from stealing focus

Because it needs a desktop, Freerouting's Java window appears while a route runs. The launcher
already starts it **minimized and without activation** (and with no console window) so it stays
out of the way. If your Windows still lets it flash to the foreground, set the per-user
**`ForegroundLockTimeout`** so Windows *refuses* focus-steals (it flashes the taskbar instead).
Run this once in the runner's session (applies immediately, no sign-out):

```powershell
Set-ItemProperty 'HKCU:\Control Panel\Desktop' ForegroundLockTimeout 200000 -Type DWord
$sig = '[DllImport("user32.dll")] public static extern bool SystemParametersInfo(uint a, uint u, UIntPtr p, uint w);'
(Add-Type -MemberDefinition $sig -Name Focus -Namespace Win32 -PassThru)::SystemParametersInfo(0x2001,0,[UIntPtr]200000,3) | Out-Null
```

(Revert by setting the value back to `0`.) For **zero** on-screen windows, run the runner in a
separate logged-on session — e.g. a second local user you connect to over RDP and then
**disconnect** (not sign out): that session keeps its own virtual desktop alive, fully isolated
from your primary desktop, and the runner routes there without ever touching your screen.

### 3. Register the runner (label `cec-router`)

Repo **Settings → Actions → Runners → New self-hosted runner → Windows**, download, then:

```powershell
.\config.cmd --url https://github.com/nathanfraske/CEC-Platform --token <TOKEN> --labels cec-router
.\run.cmd            # interactive session -- keep this window open (or Task Scheduler, logged-on)
```

### 4. Run a route on Windows

- **From CI:** Actions → *Route (self-hosted)* → Run workflow (the Windows step calls `route.ps1`).
- **Locally** (same engine, no CI):
  ```powershell
  .\scripts\route.ps1 -Board eps-8pin -Seeds 0,1,2,3 -Passes 12 -OptTime 30 -Render
  ```

---

## Linux / macOS

### 1. Install

| Need | Why | Install (Debian/Ubuntu) |
|---|---|---|
| **KiCad 10** with python `pcbnew` | DSN/SES round-trip, board measure | `apt install kicad` |
| **`kicad-cli`** | DRC + render | ships with KiCad 10 |
| **java 17+ (21 rec.)** | Freerouting | `apt install openjdk-21-jre-headless` |
| **`xvfb`** (headless Linux only) | Freerouting runs headless under a virtual X | `apt install xvfb` |

> KiCad **major version must be 10** (forward-only `.kicad_*` format). Verify with
> `python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"` and `kicad-cli version`.
> `scripts/route-prereqs.sh` checks all of this.

### 2. Register the runner (label `cec-router`)

```bash
./config.sh --url https://github.com/nathanfraske/CEC-Platform --token <TOKEN> --labels cec-router
./run.sh            # or install as a service: sudo ./svc.sh install && sudo ./svc.sh start
```

On a desktop Linux with a real `$DISPLAY` the route uses it directly; on a headless server it
auto-wraps Freerouting in `xvfb-run` (so a Linux runner is fine as a service — no desktop needed,
unlike Windows).

### 3. Run a route

```bash
python3 scripts/cec_router.py --board eps-8pin --seeds 0,1,2,3 --passes 12 --opt-time 30 \
        --kmax 2 --max-iters 4 --out build/route/eps-8pin --render
```

---

## Triggering (any OS)

- **GitHub UI:** Actions → *Route (self-hosted)* → **Run workflow** — pick board + Freerouting
  effort (passes / opt-time / seeds) + loop knobs (kmax / max-iters).
- **API / `gh`:** `gh workflow run "Route (self-hosted)" -f board=eps-8pin -f passes=12 -f seeds=0,1,2,3`
- **From a Claude session:** ask it to dispatch the workflow (it drives GitHub via MCP) and read
  the resulting artifacts back.

## Outputs (uploaded as a run artifact)

Into `build/route/<board>/` (gitignored locally; uploaded as `route-<board>-<run_id>`):

- `<board>-routed.kicad_pcb` — the best routed candidate (real copper).
- `<board>-decision-log.json` — every iteration: candidates + metrics, the chosen one, the verdict
  + tier, the edit applied, and the final **independent DRC verdict** (replayable).
- `<board>-routed-top.png` — a top render.

Remember the verdict's **hard gates** (`kelvin_ok`, `diffpair_ok`) are the safety result — a
candidate can be useful (sense + diff pairs routed) while `gates_pass` is still false because
structural DRC isn't 0 yet; that's the loop's signal to keep iterating (more passes, keep-outs, or
a placement/plan change).

## Security note

Self-hosted runners execute the workflow's code on your machine. This workflow is
`workflow_dispatch`-only (manual), so it does not auto-run on arbitrary PRs. **Do not** make it
run automatically on `pull_request` from forks — a self-hosted runner on untrusted PR code is a
known risk. Keep it manual (or gate it on a trusted environment/approval).
