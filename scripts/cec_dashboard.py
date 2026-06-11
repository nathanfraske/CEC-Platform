#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dashboard -- live run dashboard for the in-loop audit / overnight runs.
# ============================================================================
# Owner ask (2026-06-11): "a live metrics dashboard that shows the latest board,
# streaming thoughts from the entire pass, each step happening realtime."
# Realizes the standing live-viewer TODO in cec_reasoning_bakeoff.py: plain
# stdlib http.server + client polling, strictly READ-ONLY (plus one sanctioned
# side effect: rendering the newest candidate board to PNG, in-container).
#
# Panels:
#   * status header   -- run alive/PID/elapsed, round count, deadline
#   * step feed       -- run.log tail (route/audit/inject lines), realtime
#   * latest board    -- newest *.kicad_pcb in the run output, auto-rendered
#                        via the routing container's kicad-cli (bg thread)
#   * thoughts stream -- the newest auditor stream-json (claude -p
#                        --output-format=stream-json tee; text deltas parsed
#                        server-side) with fallback to the newest finding's
#                        full `reasoning` field; V4 checkpoint reasoning too
#   * convergence     -- measurement.jsonl series (pen_total vs physical
#                        metrics sparkline + last rows)
#   * injected rules  -- live-rules.json penalties + newest manager rules
#
# Usage:
#   python3 scripts/cec_dashboard.py [--port 8090] [--run-dir docs/inloop-audit-2026-06-11]
#   then open http://localhost:8090
# ============================================================================
import argparse
import glob
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE = ["docker", "compose", "-f", os.path.join(ROOT, "docker", "compose.yaml")]

CFG = {
    "run_dir": os.path.join(ROOT, "docs", "inloop-audit-2026-06-11"),
    "board_glob": os.path.join(ROOT, "build", "overnight-directed", "*.kicad_pcb"),
    "proc_pattern": "cec_inloop_audit.py|cec_overnight_directed.py",
    "plot_layers": "F.Cu,B.Cu,In1.Cu,In2.Cu,Edge.Cuts",
}
NOISE = re.compile(r"duplicate image handler|Debug:|Xvfb|_XSERV|xvfb-entry|wxWidgets")

_render = {"png": None, "board": None, "mtime": 0, "status": "idle", "ts": 0}


# ---------------------------------------------------------------- helpers
def _runfile(name):
    return os.path.join(CFG["run_dir"], name)


def _proc_info():
    try:
        out = subprocess.run(["pgrep", "-af", CFG["proc_pattern"]],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        for ln in out.splitlines():
            pid, _, cmd = ln.partition(" ")
            if "cec_dashboard" in cmd:
                continue
            et = subprocess.run(["ps", "-p", pid, "-o", "etime="],
                                capture_output=True, text=True, timeout=5).stdout.strip()
            return {"alive": True, "pid": int(pid), "elapsed": et, "cmd": cmd[:120]}
    except Exception:                                              # noqa: BLE001
        pass
    return {"alive": False}


def _log_tail(n=80):
    p = _runfile("run.log")
    if not os.path.exists(p):
        return []
    try:
        with open(p, "rb") as fh:                                 # cheap tail: last ~64KB
            fh.seek(max(0, os.path.getsize(p) - 65536))
            txt = fh.read().decode("utf-8", "replace")
        lines = [L for L in txt.splitlines() if L.strip() and not NOISE.search(L)]
        return lines[-n:]
    except Exception:                                             # noqa: BLE001
        return []


def _measurement(n=400):
    p = _runfile("measurement.jsonl")
    rows = []
    if os.path.exists(p):
        for L in open(p):
            try:
                rows.append(json.loads(L))
            except Exception:                                     # noqa: BLE001
                pass
    return rows[-n:]


def _live_rules():
    p = _runfile("live-rules.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p))
        return {"penalties": d.get("scorer_penalties", {}),
                "n_rules": len(d.get("manager_rules", [])),
                "n_accepted": len(d.get("injections", [])),
                "n_rejected": len(d.get("rejections", [])),
                "last_rules": d.get("manager_rules", [])[-3:]}
    except Exception:                                             # noqa: BLE001
        return {}


def _latest(globpat):
    files = glob.glob(globpat)
    return max(files, key=os.path.getmtime) if files else None


def _latest_finding():
    """Newest auditor finding (sonnet or v4) with its full reasoning."""
    out = {}
    for kind, pat in (("sonnet", "round-*-sonnet.json"), ("v4", "round-*-v4.json")):
        f = _latest(os.path.join(CFG["run_dir"], "findings", pat))
        if not f:
            continue
        try:
            d = json.load(open(f))
        except Exception:                                         # noqa: BLE001
            continue
        out[kind] = {"file": os.path.basename(f),
                     "verdict": d.get("verdict"), "is_new": d.get("is_new_finding"),
                     "reasoning": (d.get("reasoning") or d.get("reasoning_content")
                                   or d.get("content") or "")[:6000],
                     "scorer_penalty": d.get("scorer_penalty") or
                                       (d.get("parsed_findings") or {}).get("scorer_penalty"),
                     "manager_rule": (d.get("manager_rule") or
                                      (d.get("parsed_findings") or {}).get("manager_rule") or "")[:400],
                     "local_minimum_risk": (d.get("parsed_findings") or {}).get("local_minimum_risk"),
                     "mtime": os.path.getmtime(f)}
    return out


def _stream_text(off):
    """Incremental text from the NEWEST auditor stream-json file (claude -p
    --output-format=stream-json tee). Extracts assistant text + tool intents."""
    f = _latest(os.path.join(CFG["run_dir"], "findings", "*.stream.jsonl"))
    if not f:
        return {"file": None, "off": 0, "text": ""}
    size = os.path.getsize(f)
    if off > size:                                                 # new file rotated in
        off = 0
    chunks = []
    with open(f, "rb") as fh:
        fh.seek(off)
        raw = fh.read(262144)
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:                                         # noqa: BLE001
            continue
        # partial text deltas (stream_event) and complete assistant messages
        e = ev.get("event") or {}
        delta = (e.get("delta") or {})
        if delta.get("type") in ("text_delta", "thinking_delta"):
            chunks.append(delta.get("text") or delta.get("thinking") or "")
        elif ev.get("type") == "assistant":
            for blk in ((ev.get("message") or {}).get("content") or []):
                if blk.get("type") == "text":
                    chunks.append("\n" + blk.get("text", "") + "\n")
                elif blk.get("type") == "tool_use":
                    chunks.append(f"\n[tool: {blk.get('name')}]\n")
    return {"file": os.path.basename(f), "off": off + len(raw), "text": "".join(chunks)}


# ---------------------------------------------------------------- board render thread
def _render_loop():
    """Produce BOTH views of the newest candidate: the raytraced PNG (render) AND the
    layer PLOT SVG (kicad-cli pcb export svg, copper layers + edge -- the owner's
    'plotted board' ask: actual track geometry, inspectable, zoomable)."""
    png_host = _runfile("dashboard-board.png")
    svg_host = _runfile("dashboard-board.svg")
    while True:
        try:
            newest = _latest(CFG["board_glob"])
            if newest and os.path.getmtime(newest) > _render["mtime"]:
                _render.update(status="rendering", board=os.path.basename(newest))
                rel = os.path.relpath(newest, ROOT)
                r = subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "render",
                                              "--side", "top",
                                              "-o", f"/workspace/{os.path.relpath(png_host, ROOT)}",
                                              f"/workspace/{rel}"],
                                   capture_output=True, timeout=180)
                p = subprocess.run(COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "export",
                                              "svg", "--layers", CFG["plot_layers"],
                                              "--page-size-mode", "2", "--exclude-drawing-sheet",
                                              "-o", f"/workspace/{os.path.relpath(svg_host, ROOT)}",
                                              f"/workspace/{rel}"],
                                   capture_output=True, timeout=120)
                ok_png = r.returncode == 0 and os.path.exists(png_host)
                ok_svg = p.returncode == 0 and os.path.exists(svg_host)
                if ok_png or ok_svg:
                    _render.update(png=png_host if ok_png else _render["png"],
                                   svg=svg_host if ok_svg else _render.get("svg"),
                                   mtime=os.path.getmtime(newest), status="ok", ts=time.time())
                else:
                    _render.update(status=f"render-failed png_rc={r.returncode} svg_rc={p.returncode}")
        except Exception as e:                                    # noqa: BLE001
            _render.update(status=f"err:{type(e).__name__}")
        time.sleep(10)


# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):                                    # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                             # noqa: N802
        path, _, q = self.path.partition("?")
        params = dict(p.split("=", 1) for p in q.split("&") if "=" in p)
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            bundle = None
            if os.path.exists(_runfile("morning-bundle.json")):
                try:
                    b = json.load(open(_runfile("morning-bundle.json")))
                    bundle = {k: b.get(k) for k in ("rounds", "convergence_verdict",
                              "n_usable_ratification_candidates", "n_manager_rules", "pareto_finalists")}
                except Exception:                                 # noqa: BLE001
                    pass
            self._json({"ts": time.time(), "run": _proc_info(),
                        "measurement": _measurement(), "rules": _live_rules(),
                        "log": _log_tail(), "finding": _latest_finding(),
                        "board": {"name": _render["board"], "status": _render["status"],
                                  "rendered_ts": _render["ts"]},
                        "bundle": bundle, "run_dir": CFG["run_dir"]})
        elif path == "/api/stream":
            self._json(_stream_text(int(params.get("off", 0))))
        elif path in ("/board.png", "/board.svg"):
            key, ctype = (("png", "image/png") if path.endswith("png")
                          else ("svg", "image/svg+xml"))
            p = _render.get(key)
            if p and os.path.exists(p):
                body = open(p, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": f"no {key} yet"}, 404)
        else:
            self._json({"error": "not found"}, 404)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>CEC live run</title><style>
body{background:#101418;color:#cfd8dc;font:13px/1.45 ui-monospace,Menlo,monospace;margin:0}
.grid{display:grid;grid-template-columns:1.1fr 1fr 1fr;grid-template-rows:auto 1fr 1fr;gap:8px;padding:8px;height:97vh;box-sizing:border-box}
.card{background:#161c22;border:1px solid #263238;border-radius:8px;padding:8px;overflow:auto;min-height:0}
h2{font-size:12px;color:#80cbc4;margin:0 0 6px;text-transform:uppercase;letter-spacing:1px}
#hdr{grid-column:1/4;display:flex;gap:24px;align-items:center}
.ok{color:#a5d6a7}.bad{color:#ef9a9a}.warn{color:#ffcc80}.dim{color:#607d8b}
#log,#thoughts{white-space:pre-wrap;word-break:break-word;font-size:12px}
#board img{max-width:100%;border-radius:4px}
table{border-collapse:collapse;width:100%}td,th{padding:1px 6px;text-align:right;font-size:11px}
th{color:#80cbc4;position:sticky;top:0;background:#161c22}
canvas{width:100%;height:90px;background:#0d1117;border-radius:4px}
.pill{background:#263238;border-radius:10px;padding:2px 10px;margin-right:6px}
</style></head><body><div class="grid">
<div class="card" id="hdr"><h2 style="margin:0">CEC live run</h2><span id="status"></span><span id="bundle"></span></div>
<div class="card"><h2>step feed (realtime)</h2><div id="log"></div></div>
<div class="card" id="board"><h2>latest board <span id="bstat" class="dim"></span>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="bmode='png';bswap()">render</button>
<button class="pill" style="cursor:pointer;border:0;color:#cfd8dc" onclick="bmode='svg';bswap()">plot</button></h2>
<img id="bimg" src="/board.png" onerror="this.style.display='none'"></div>
<div class="card"><h2>auditor thoughts (live)</h2><div id="thoughts"></div></div>
<div class="card" style="grid-column:1/3"><h2>convergence — pen_total (orange) vs drc (blue), kelvin band (red=fail)</h2>
<canvas id="spark" width="900" height="90"></canvas><div style="max-height:230px;overflow:auto"><table id="mt"></table></div></div>
<div class="card"><h2>injected ruleset</h2><div id="rules"></div></div>
</div><script>
let soff=0, thoughtsBuf="", bmode='svg';
function bswap(){const im=document.getElementById('bimg');im.style.display='block';
 im.src='/board.'+bmode+'?t='+(window._bts||0);}
async function tick(){
 try{
  const s=await (await fetch('/api/state')).json();
  const r=s.run||{};
  document.getElementById('status').innerHTML=
   `<span class="pill ${r.alive?'ok':'bad'}">${r.alive?'RUNNING pid '+r.pid+' ('+(r.elapsed||'')+')':'NOT RUNNING'}</span>`+
   `<span class="pill">rounds: ${s.measurement.length}</span><span class="pill dim">${s.run_dir.split('/').pop()}</span>`;
  document.getElementById('bundle').innerHTML = s.bundle?
   `<span class="pill warn">FINAL: ${s.bundle.convergence_verdict} | usable ${s.bundle.n_usable_ratification_candidates} | rules ${s.bundle.n_manager_rules} | finalists ${s.bundle.pareto_finalists}</span>`:'';
  document.getElementById('log').textContent=(s.log||[]).slice(-40).join('\n');
  const el=document.getElementById('log'); el.scrollTop=el.scrollHeight;
  // board
  document.getElementById('bstat').textContent=`${s.board.name||''} ${s.board.status||''}`;
  if(s.board.rendered_ts && s.board.rendered_ts>(window._bts||0)){window._bts=s.board.rendered_ts; bswap();}
  // thoughts: prefer live stream, fallback to latest finding reasoning
  const st=await (await fetch('/api/stream?off='+soff)).json();
  if(st.file){ if(st.off<soff){thoughtsBuf="";} soff=st.off; thoughtsBuf+=st.text;
    document.getElementById('thoughts').textContent='['+st.file+']\n'+thoughtsBuf.slice(-8000);}
  else{ const f=s.finding||{}; let t='';
    if(f.sonnet) t+=`[${f.sonnet.file}] verdict=${f.sonnet.verdict} new=${f.sonnet.is_new}\n${f.sonnet.reasoning}\n\nrule: ${f.sonnet.manager_rule||'-'}\n`;
    if(f.v4) t+=`\n=== V4 checkpoint [${f.v4.file}] risk=${f.v4.local_minimum_risk} ===\n${(f.v4.reasoning||'').slice(0,3000)}`;
    document.getElementById('thoughts').textContent=t||'(no findings yet)';}
  const th=document.getElementById('thoughts'); th.scrollTop=th.scrollHeight;
  // rules
  const ru=s.rules||{};
  document.getElementById('rules').innerHTML=
   `<b>penalties</b>: ${JSON.stringify(ru.penalties||{})}<br><b>rules</b>: ${ru.n_rules||0} | accepted ${ru.n_accepted||0} | rejected/noop ${ru.n_rejected||0}<br><br>`+
   ((ru.last_rules||[]).map(x=>'• '+x.slice(0,180)).join('<br><br>'));
  // measurement table + sparkline
  const m=s.measurement||[];
  const cols=['round','verdict','kelvin_ok','plane_signal_mm','drc','unconnected','penalty_total','live_objective','n_rules','sonnet_is_new'];
  document.getElementById('mt').innerHTML='<tr>'+cols.map(c=>'<th>'+c.replace(/_/g,' ')+'</th>').join('')+'</tr>'+
   m.slice(-14).reverse().map(r=>'<tr>'+cols.map(c=>{let v=r[c];let cl='';
     if(c==='kelvin_ok')cl=v?'ok':'bad'; if(c==='verdict')cl=v==='accept'?'ok':(v==='escalate'?'warn':'');
     return `<td class="${cl}">${v}</td>`}).join('')+'</tr>').join('');
  const cv=document.getElementById('spark').getContext('2d'); cv.clearRect(0,0,900,90);
  if(m.length>1){const W=900,H=90,n=m.length;
   const mx=Math.max(...m.map(r=>r.penalty_total)),md=Math.max(...m.map(r=>r.drc));
   m.forEach((r,i)=>{const x=i*W/(n-1);
     if(!r.kelvin_ok){cv.fillStyle='rgba(239,83,80,.12)';cv.fillRect(x-W/(n-1)/2,0,W/(n-1)+1,H);}});
   cv.strokeStyle='#ffb74d';cv.beginPath();m.forEach((r,i)=>{const x=i*W/(n-1),y=H-4-(r.penalty_total/mx)*(H-10);i?cv.lineTo(x,y):cv.moveTo(x,y)});cv.stroke();
   cv.strokeStyle='#64b5f6';cv.beginPath();m.forEach((r,i)=>{const x=i*W/(n-1),y=H-4-(r.drc/md)*(H-10);i?cv.lineTo(x,y):cv.moveTo(x,y)});cv.stroke();}
 }catch(e){document.getElementById('status').innerHTML='<span class="pill bad">dashboard error: '+e+'</span>';}
}
tick(); setInterval(tick,2000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="CEC live run dashboard (read-only)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--run-dir", default=CFG["run_dir"])
    ap.add_argument("--board-glob", default=CFG["board_glob"])
    a = ap.parse_args()
    CFG["run_dir"] = os.path.abspath(a.run_dir)
    CFG["board_glob"] = a.board_glob
    threading.Thread(target=_render_loop, daemon=True).start()
    print(f"dashboard: http://localhost:{a.port}  (run_dir={CFG['run_dir']})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
