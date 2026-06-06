# Self-hosted routing — run the CPU-heavy compute on your own hardware

The automated routing system (`scripts/cec_fr.py` + `cec_score.py` + `cec_router.py`, see
`scripts/README-cec_pcb.md`) splits into two planes:

- **Control plane** — the LLM tiers (planning, judging, repairing). This is *remote inference*
  in a Claude session; it uses ~0 CPU and always runs remotely.
- **Compute plane** — the actual CPU drain: **Freerouting JVMs** (one per candidate) and
  **`kicad-cli` DRC**. These are plain local subprocesses, so they run wherever the workflow's
  steps execute.

This doc wires the **compute plane onto your hardware** via a **GitHub Actions self-hosted
runner**, so "route the board" runs on your CPU and returns the routed candidate + decision log
+ render as artifacts — while you keep triggering and reviewing from the web/phone/API.

The workflow is `.github/workflows/route.yml` (`Route (self-hosted)`).

## Why this scales

The GitHub-hosted side of this repo's CI is a small ephemeral box (a few vCPU). A Freerouting
run is one JVM at ~0.5 GB pinning one core; the practical ceiling is **one candidate per core**.
On a self-hosted runner the ceiling becomes *your* core count — an 8/16/32-core workstation runs
that many candidates in parallel (`cec_fr.generate_batch` already caps `max_workers = min(seeds,
nproc)`), and RAM is rarely the limit (~0.5 GB/runner).

## 1. Prerequisites on the runner machine

Install once (the workflow's first step, `scripts/route-prereqs.sh`, checks these and fails fast
with hints if any are missing):

| Need | Why | Install (Debian/Ubuntu) |
|---|---|---|
| **KiCad 10** with python `pcbnew` | DSN/SES round-trip, board measure | `apt install kicad` (or use the `kicad/kicad:10.0` image) |
| **`kicad-cli`** | DRC + render | ships with KiCad 10 |
| **java 17+ (21 rec.)** | Freerouting | `apt install openjdk-21-jre-headless` |
| **`xvfb`** | Freerouting runs headless under a virtual X | `apt install xvfb` |
| **python3** | the scripts | usually present |

> KiCad **major version must be 10** to match the repo's `.kicad_*` files (forward-only format).
> Verify: `python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"` and `kicad-cli version`.

The Freerouting jar is fetched automatically (`cec_fr.ensure_jar()` downloads the pinned **v1.7.0**
to `~/.cache/cec/`). To skip the download, drop a jar somewhere and set the repo/org Actions
variable **`CEC_FREEROUTING_JAR`** to its path (or place it at `/tmp/fr_1.7.0.jar`). v1.7.0 is the
pinned version — 1.9.0 does **not** run headless.

## 2. Register the runner (label `cec-router`)

On the repo: **Settings → Actions → Runners → New self-hosted runner**, follow the download/configure
steps on your machine, and give it the label the workflow targets:

```bash
# during ./config.sh, add the label (in addition to the defaults):
./config.sh --url https://github.com/nathanfraske/CEC-Platform --token <TOKEN> --labels cec-router
# then run it (foreground, or install as a service):
./run.sh            # or: sudo ./svc.sh install && sudo ./svc.sh start
```

The workflow uses `runs-on: [self-hosted, cec-router]`, so the job lands only on a runner carrying
both labels. Register the runner on the beefy machine you want the routing to use.

## 3. Run a route

- **GitHub UI:** Actions → *Route (self-hosted)* → **Run workflow**, pick the board + Freerouting
  effort (passes / opt-time / seeds) + loop knobs (kmax / max-iters).
- **API / `gh`:** `gh workflow run "Route (self-hosted)" -f board=eps-8pin -f passes=12 -f seeds=0,1,2,3`
- **From a Claude session:** ask it to dispatch the workflow (it drives GitHub via the MCP tools)
  and read the resulting artifacts back.

Locally, the same entry point is just:

```bash
python3 scripts/cec_router.py --board eps-8pin --seeds 0,1,2,3 --passes 12 --opt-time 30 \
        --kmax 2 --max-iters 4 --out build/route/eps-8pin --render
```

## 4. Outputs (uploaded as a run artifact)

Into `build/route/<board>/` (gitignored locally; uploaded as `route-<board>-<run_id>`):

- `<board>-routed.kicad_pcb` — the best routed candidate (real copper).
- `<board>-decision-log.json` — every iteration: candidates + metrics, the chosen one, the
  verdict + tier, the edit applied, and the final **independent DRC verdict** (replayable).
- `<board>-routed-top.png` — a top render.

The job summary also prints the final verdict (gates + DRC + counts). Remember the verdict's
**hard gates** (`kelvin_ok`, `diffpair_ok`) are the safety result — a candidate can be useful
(sense + diff pairs routed) while `gates_pass` is still false because structural DRC isn't 0 yet;
that's the loop's signal to keep iterating (more passes, keep-outs, or a placement/plan change).

## Security note

Self-hosted runners execute the workflow's code on your machine. This workflow is
`workflow_dispatch`-only (manual), so it does not auto-run on arbitrary PRs. **Do not** make it
run automatically on `pull_request` from forks — a self-hosted runner on untrusted PR code is a
known risk. Keep it manual (or gate it on a trusted environment/approval).
