#!/usr/bin/env python3
"""cec_compute_mcp -- the CEC compute plane as callable tools (2026-07-14, owner GO,
shape at agent discretion).

ONE file, TWO consumers:

  1. MCP stdio server (Claude-side sessions):   python3 scripts/cec_compute_mcp.py
     Registered in .mcp.json as "cec-compute". Needs `pip install mcp`.
  2. Plain CLI (the cec-llm-broker worker agents -- they speak OpenAI tool calls,
     not MCP; cec_agent.py execs this):          python3 scripts/cec_compute_mcp.py \
                                                    --call <tool> --json '{...}'
     Prints the tool's JSON result on stdout. No mcp dependency on this path.

Design rails:
  * READ/COMPUTE ONLY -- no tool mutates the repo, a committed board, or tracker
    files. Outputs land in build/ (gitignored) or the dashboard feed.
  * Heavy compute (route/oracle) shells into the pinned routing container exactly
    the way the wave does (sg docker compose run); light verbs (drc/render/report
    reads) run host-side kicad-cli. A worker seat therefore CANNOT bypass the
    pinned toolchain.
  * Every tool returns JSON with an "ok" key; failures return {"ok": false,
    "error": ...} rather than raising, so a model loop never wedges on an
    exception trace.

Broker wiring: cec-llm-broker/cec_agent.py appends these as OpenAI tool schemas
(see TOOL_SCHEMAS below -- the broker imports nothing from this repo; it execs
the CLI). The schemas are exported verbatim by --schemas.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
COMPOSE = os.path.join(ROOT, "docker", "compose.yaml")


def _run(cmd, timeout=1800, cwd=ROOT):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def _in_container(py_code, timeout=1800):
    """Run a python snippet inside the pinned routing container (the compute plane)."""
    return _run(["sg", "docker", "-c",
                 "docker compose -f %s run --rm routing python3 -c %s"
                 % (COMPOSE, json.dumps(py_code))], timeout=timeout)


def _board_path(board):
    """Resolve a board argument: absolute path, repo-relative path, or module name."""
    if os.path.isfile(board):
        return board
    rp = os.path.join(ROOT, board)
    if os.path.isfile(rp):
        return rp
    for pat in (os.path.join(ROOT, "beta", board),          # beta/ FIRST (move 2026-07-22)
                os.path.join(ROOT, "modules", board),
                os.path.join(ROOT, "hubs", board)):
        if os.path.isdir(pat):
            pcbs = [f for f in os.listdir(pat) if f.endswith(".kicad_pcb")]
            if len(pcbs) == 1:
                return os.path.join(pat, pcbs[0])
    return None


# ------------------------------------------------------------------ tools
def tool_drc(board: str, severity_errors_only: bool = False) -> dict:
    """Run the real kicad-cli DRC on a board; returns violation counts by type."""
    p = _board_path(board)
    if not p:
        return {"ok": False, "error": f"board not found: {board}"}
    out = tempfile.mkstemp(suffix=".json")[1]
    code, _o, err = _run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, p],
                         timeout=300)
    try:
        d = json.load(open(out))
    except Exception:
        return {"ok": False, "error": f"drc produced no JSON ({err[-200:]})"}
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    from collections import Counter
    c = Counter()
    for v in d.get("violations", []):
        if severity_errors_only and v.get("severity") != "error":
            continue
        c[v["type"]] += 1
    return {"ok": True, "board": p, "unconnected": len(d.get("unconnected_items", [])),
            "violations_total": sum(c.values()), "by_type": dict(c)}


def tool_render(board: str, side: str = "top") -> dict:
    """Render a board to PNG (build/mcp-renders/); returns the image path."""
    p = _board_path(board)
    if not p:
        return {"ok": False, "error": f"board not found: {board}"}
    if side not in ("top", "bottom"):
        return {"ok": False, "error": "side must be top|bottom"}
    outdir = os.path.join(ROOT, "build", "mcp-renders")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "%s-%s-%d.png"
                       % (os.path.basename(p)[:-len(".kicad_pcb")], side, int(time.time())))
    code, _o, err = _run(["kicad-cli", "pcb", "render", "--side", side,
                          "--background", "opaque", "-o", out, p], timeout=300)
    if code != 0 or not os.path.isfile(out):
        return {"ok": False, "error": err[-300:]}
    return {"ok": True, "image": os.path.relpath(out, ROOT)}


def tool_score(board: str) -> dict:
    """Score a routed board with the pipeline's own gate metrics (kelvin/diffpair/DRC/unconn).
    Runs in the pinned routing container."""
    p = _board_path(board)
    if not p:
        return {"ok": False, "error": f"board not found: {board}"}
    rel = os.path.relpath(p, ROOT)
    code, out, err = _in_container(
        "import sys,json; sys.path.insert(0,'scripts'); import cec_score; "
        "m=cec_score.score(%r); "
        "print('CEC_JSON '+json.dumps({'kelvin_ok':bool(m.kelvin_ok),"
        "'diffpair_ok':bool(m.diffpair_ok),'drc':m.drc,'unconnected':m.unconnected,"
        "'tracks':m.tracks,'vias':m.vias,'drc_types':dict(m.drc_types)}))" % rel,
        timeout=600)
    for line in out.splitlines():
        if line.startswith("CEC_JSON "):
            return {"ok": True, "board": rel, **json.loads(line[len("CEC_JSON "):])}
    return {"ok": False, "error": (err or out)[-300:]}


def tool_route(board: str, passes: int = 8, opt: int = 10, seed: int = 0) -> dict:
    """Route a PLACED board copy with the pinned Freerouting fork (locked copper
    protected, owned nets excluded, keepouts baked -- the standard recipe) and score
    it. Output board lands in build/mcp-routes/. Heavy: minutes."""
    p = _board_path(board)
    if not p:
        return {"ok": False, "error": f"board not found: {board}"}
    rel = os.path.relpath(p, ROOT)
    outdir = "build/mcp-routes"
    os.makedirs(os.path.join(ROOT, outdir), exist_ok=True)
    out_rel = "%s/%s-r%d.kicad_pcb" % (outdir,
                                       os.path.basename(p)[:-len(".kicad_pcb")],
                                       int(time.time()))
    code, out, err = _in_container(
        "import sys,os,json; sys.path.insert(0,'scripts'); "
        "os.environ['CEC_FR_SEED_AXIS']='1'; "
        "import cec_fr, cec_cell_extract, cec_score; "
        "prot=sorted(cec_cell_extract.locked_nets(%r)); "
        "cand=cec_fr.route_once(%r, %r, passes=%d, opt_time=%d, seed=%d, "
        "protect_nets=prot, timeout=1500); "
        "m=cec_score.score(%r); "
        "print('CEC_JSON '+json.dumps({'ok':bool(getattr(cand,'ok',False)),"
        "'routed':%r,'kelvin_ok':bool(m.kelvin_ok),'diffpair_ok':bool(m.diffpair_ok),"
        "'drc':m.drc,'unconnected':m.unconnected}))"
        % (rel, rel, out_rel, int(passes), int(opt), int(seed), out_rel, out_rel),
        timeout=1800)
    for line in out.splitlines():
        if line.startswith("CEC_JSON "):
            return json.loads(line[len("CEC_JSON "):])
    return {"ok": False, "error": (err or out)[-300:]}


def tool_wave_report(board: str = "12vhpwr-standard", n: int = 3) -> dict:
    """The last n fresh-wave reports for a board (best label/sort_key/criticals)."""
    import glob
    reps = sorted(glob.glob(os.path.join(
        ROOT, "build", "fresh-wave-loop", board, "*wave-report.json")))[-int(n):]
    if not reps:
        return {"ok": False, "error": f"no wave reports for {board}"}
    out = []
    for r in reps:
        d = json.load(open(r))
        b = d.get("best") or {}
        out.append({"ts": d.get("ts"), "best": b.get("label"), "gate": b.get("gate"),
                    "unconnected": b.get("unconnected"), "drc": b.get("drc"),
                    "unconn_critical": b.get("unconn_critical"),
                    "sort_key": b.get("sort_key")})
    return {"ok": True, "board": board, "waves": out}


def tool_worklog(title: str, detail: str = "", image: str = "") -> dict:
    """Post a line (optionally with an image path) to the owner's dashboard feed."""
    sys.path.insert(0, HERE)
    try:
        import cec_worklog
        cec_worklog.log(str(title)[:200], tag="agent",
                        detail=str(detail)[:2000], image=(image or None))
        return {"ok": True}
    except Exception as e:                                     # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


TOOLS = {"drc": tool_drc, "render": tool_render, "score": tool_score,
         "route": tool_route, "wave_report": tool_wave_report, "worklog": tool_worklog}

# OpenAI tool schemas for the broker's cec_agent loop (exported via --schemas).
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "cec_drc", "description": "Run real KiCad DRC on a CEC board (path or module name); returns violation counts by type.",
        "parameters": {"type": "object", "properties": {
            "board": {"type": "string", "description": "board path or module name, e.g. beta/eps-8pin or a build/ candidate path"},
            "severity_errors_only": {"type": "boolean"}}, "required": ["board"]}}},
    {"type": "function", "function": {
        "name": "cec_render", "description": "Render a CEC board to PNG; returns the image path (repo-relative).",
        "parameters": {"type": "object", "properties": {
            "board": {"type": "string"}, "side": {"type": "string", "enum": ["top", "bottom"]}},
            "required": ["board"]}}},
    {"type": "function", "function": {
        "name": "cec_score", "description": "Gate metrics for a routed board: kelvin_ok, diffpair_ok, structural DRC, unconnected.",
        "parameters": {"type": "object", "properties": {"board": {"type": "string"}},
                       "required": ["board"]}}},
    {"type": "function", "function": {
        "name": "cec_route", "description": "Route a placed board with the pinned Freerouting fork and score it (minutes; heavy).",
        "parameters": {"type": "object", "properties": {
            "board": {"type": "string"}, "passes": {"type": "integer"},
            "opt": {"type": "integer"}, "seed": {"type": "integer"}}, "required": ["board"]}}},
    {"type": "function", "function": {
        "name": "cec_wave_report", "description": "Last n fresh-wave reports for a board (best candidate, unconnected, criticals).",
        "parameters": {"type": "object", "properties": {
            "board": {"type": "string"}, "n": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "cec_worklog", "description": "Post a note (optional image path) to the owner's dashboard activity feed.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "detail": {"type": "string"},
            "image": {"type": "string"}}, "required": ["title"]}}},
]


def main():
    ap = argparse.ArgumentParser(description="CEC compute tools: MCP server or --call CLI")
    ap.add_argument("--call", help="tool name (drc|render|score|route|wave_report|worklog)")
    ap.add_argument("--json", default="{}", help="JSON kwargs for --call")
    ap.add_argument("--schemas", action="store_true",
                    help="print the OpenAI tool schemas for the broker agent")
    a = ap.parse_args()
    if a.schemas:
        print(json.dumps(TOOL_SCHEMAS, indent=1))
        return
    if a.call:
        fn = TOOLS.get(a.call.replace("cec_", ""))
        if not fn:
            print(json.dumps({"ok": False, "error": f"unknown tool {a.call}"}))
            sys.exit(1)
        try:
            print(json.dumps(fn(**json.loads(a.json))))
        except Exception as e:                                 # noqa: BLE001
            print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        return
    # MCP stdio mode
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("cec-compute")
    for name, fn in TOOLS.items():
        mcp.tool(name="cec_" + name)(fn)
    mcp.run()


if __name__ == "__main__":
    main()
