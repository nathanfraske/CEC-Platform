#!/usr/bin/env python3
"""Minimal agentic tool-call loop over the cec-llm-broker: send tools, execute the model's
tool_calls, feed results back, loop until a final answer. Local tools only (no external API)."""
import json, subprocess, ast, operator, urllib.request, urllib.parse, os

BROKER = "http://localhost:8080/v1/chat/completions"
REPO = "/home/nathan/Deep-Emergent-Civ-Simulator"

# ---- safe local tools ----
_OPS = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul, ast.Div:operator.truediv,
        ast.Pow:operator.pow, ast.USub:operator.neg, ast.Mod:operator.mod, ast.FloorDiv:operator.floordiv}
def _safe_eval(node):
    if isinstance(node, ast.Constant): return node.value
    if isinstance(node, ast.BinOp): return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp): return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")
def calculator(expression): return str(_safe_eval(ast.parse(expression, mode="eval").body))
def search_repo(pattern):
    rg="rg"
    if os.path.exists(rg):
        r = subprocess.run([rg,"-n","--no-heading","-m","40",pattern,REPO,"-g","*.rs"], capture_output=True, text=True, timeout=30)
    else:
        r = subprocess.run(["grep","-rn","--include=*.rs","-m","40",pattern,REPO], capture_output=True, text=True, timeout=30)
    out = r.stdout.strip() or "(no matches)"
    return out[:2500]
def read_file(path, start_line=1, num_lines=40):
    full = os.path.realpath(os.path.join(REPO, path))
    if not full.startswith(REPO): return "error: path outside repo"
    try:
        lines = open(full, encoding="utf-8", errors="replace").read().splitlines()
    except Exception as e: return f"error: {e}"
    s=max(0,int(start_line)-1); return "\n".join(lines[s:s+int(num_lines)])[:2500]

import re as _re
def web_search(query):
    try:
        r = urllib.request.urlopen("http://localhost:8888/search?q="+urllib.parse.quote(query)+"&format=json", timeout=20)
        d = json.loads(r.read()); out=[]
        for it in d.get("results", [])[:6]:
            out.append(f"- {it.get('title','')[:100]}\n  {it.get('url','')}\n  {(it.get('content') or '')[:200]}")
        return "\n".join(out) or "(no results)"
    except Exception as e: return f"search error: {e}"
def fetch_url(url):
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (research-agent)"})
        html=urllib.request.urlopen(req, timeout=25).read().decode("utf-8","replace")
        text=_re.sub(r"<[^>]+>"," ", _re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ", html))
        text=_re.sub(r"\s+"," ", text)
        return text[:3000]
    except Exception as e: return f"fetch error: {e}"

TOOLS_IMPL = {"calculator":calculator, "search_repo":search_repo, "read_file":read_file, "web_search":web_search, "fetch_url":fetch_url}
# ---- CEC compute tools (2026-07-14, additive; the Deep-Emergent tools above are untouched) ----
# Worker seats call the CEC compute plane through the CEC repo's own CLI (single source of
# truth: scripts/cec_compute_mcp.py -- same functions the MCP server exposes). Gated on the
# repo existing so this file stays portable.
CEC_REPO = "/home/nathan/CEC-Platform"
def _cec_call(tool, **kw):
    import subprocess, json as _j
    try:
        r = subprocess.run(["python3", CEC_REPO+"/scripts/cec_compute_mcp.py",
                            "--call", tool, "--json", _j.dumps(kw)],
                           capture_output=True, text=True, timeout=1900, cwd=CEC_REPO)
        return (r.stdout.strip().splitlines() or ["{}"])[-1][:3000]
    except Exception as e:
        return _j.dumps({"ok": False, "error": str(e)[:200]})
if os.path.isdir(CEC_REPO):
    for _t in ("drc", "render", "score", "route", "wave_report", "worklog"):
        TOOLS_IMPL["cec_"+_t] = (lambda _name: (lambda **kw: _cec_call(_name, **kw)))(_t)

TOOLS = [
 {"type":"function","function":{"name":"calculator","description":"Evaluate an arithmetic expression.",
   "parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}},
 {"type":"function","function":{"name":"search_repo","description":"ripgrep the codebase; returns file:line matches.",
   "parameters":{"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]}}},
 {"type":"function","function":{"name":"read_file","description":"Read a slice of a repo file (path relative to repo root).",
   "parameters":{"type":"object","properties":{"path":{"type":"string"},"start_line":{"type":"integer"},"num_lines":{"type":"integer"}},"required":["path"]}}},
 {"type":"function","function":{"name":"web_search","description":"Search the web (SearXNG); returns title/url/snippet for the top results.",
   "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
 {"type":"function","function":{"name":"fetch_url","description":"Fetch a web page and return its readable text (truncated).",
   "parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}},
]
if os.path.isdir(CEC_REPO):
    import subprocess as _sp, json as _j2
    try:
        _sch=_j2.loads(_sp.run(["python3", CEC_REPO+"/scripts/cec_compute_mcp.py","--schemas"],
                               capture_output=True,text=True,timeout=20).stdout)
        TOOLS += _sch
    except Exception:
        pass



import re as _re2
def _parse_text_tool_calls(content):
    """Fallback: parse tool calls the model emitted as TEXT (Qwen <tool_call><function=..> format)."""
    calls=[]
    for m in _re2.finditer(r"<tool_call>(.*?)</tool_call>", content or "", _re2.DOTALL):
        blk=m.group(1)
        fn=_re2.search(r"<function=([\w\-]+)>", blk)
        if not fn: continue
        args={}
        for pm in _re2.finditer(r"<parameter=([\w\-]+)>\s*(.*?)\s*</parameter>", blk, _re2.DOTALL):
            args[pm.group(1)]=pm.group(2).strip()
        calls.append({"id":f"txt{len(calls)}","function":{"name":fn.group(1),"arguments":json.dumps(args)}})
    return calls

def _call(messages, model, temp, max_tokens=700):
    body=json.dumps({"model":model,"messages":messages,"tools":TOOLS,"temperature":temp,"max_tokens":max_tokens}).encode()
    req=urllib.request.Request(BROKER,data=body,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=600) as r: return json.loads(r.read())["choices"][0]["message"]

def run_agent(task, model="qwythos-mtp-q8", temp=0, max_turns=6, max_tokens=700):
    messages=[{"role":"user","content":task}]; trace=[]
    for turn in range(max_turns):
        msg=_call(messages, model, temp, max_tokens)
        tcs=msg.get("tool_calls") or []
        content=msg.get("content") or ""
        if not tcs and "<tool_call>" in content:
            tcs=_parse_text_tool_calls(content)
        if not tcs:
            return (content or msg.get("reasoning_content","")[-600:]), trace
        messages.append({"role":"assistant","content":msg.get("content") or "","tool_calls":tcs})
        for tc in tcs:
            fn=tc["function"]["name"]; args=json.loads(tc["function"].get("arguments") or "{}")
            try: result=TOOLS_IMPL[fn](**args)
            except Exception as e: result=f"tool error: {e}"
            trace.append(f"  [tool] {fn}({args}) -> {result[:120].replace(chr(10),' ')}")
            messages.append({"role":"tool","tool_call_id":tc.get("id",""),"name":fn,"content":result})
    return "(max turns reached)", trace

if __name__=="__main__":
    import sys
    task = sys.argv[1] if len(sys.argv)>1 else (
      "Using the tools, count how many times the function name `arrhenius_rate` appears in the codebase, "
      "and name the file where it is DEFINED (the `pub fn arrhenius_rate` line). Then state the count and the file.")
    model = sys.argv[2] if len(sys.argv)>2 else "qwythos-mtp-q8"
    print(f"TASK: {task}\nMODEL: {model}\n")
    ans, trace = run_agent(task, model)
    print("TOOL-CALL TRACE:"); print("\n".join(trace) if trace else "  (no tools called)")
    print(f"\nFINAL ANSWER:\n{ans[:900]}")
