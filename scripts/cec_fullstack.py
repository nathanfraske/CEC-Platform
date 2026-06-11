#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_fullstack -- the FULL-STACK pipeline driver: a model in every seat.
# ============================================================================
# Implements the README §8 full-stack night plan (docs/inloop-audit-2026-06-11)
# with the convergence lessons from the 2026-06-11 in-loop audit baked in.
# Per round:
#   T1   INTENT MANAGER (model, cec-worker): reads the GR-01 congestion grid +
#        the prior round's failures and EMITS the FR-02 relational waypoints --
#        replaces the static INTENTS dict (the model-managed assisted router).
#        Schema-constrained; falls back to the previous round's intents.
#   T2   ROUTE in-container (FR 1.7.0 + compiled intents + layer policy +
#        POWER POURS at import -- the wiring fixed this morning).
#   T3   SCORE + hard gates (cec_score; plane pricing on).
#   T3.5 FEM advisory (electrothermal solve on the poured candidate; max_T into
#        the record + Pareto axes; AM-04 debt -> advisory, never gates).
#   T4   WORKER PANEL (cec-worker, 3 lenses) votes accept/repair/escalate and
#        drives FR effort -- the manager actuator.
#   T5   SONNET AUDITOR proposes at most one penalty + one rule, under:
#          - the RULE CAP (10 standing rules; beyond -> consolidate or reject),
#          - the NOVELTY GATE (normalized dedup vs the standing ruleset --
#            stronger than the seat's own is_new self-report),
#          - the ACTUATION-SPACE CHECK: every proposal runs through the CL-24
#            verifier panel; an actuation-refuted proposal is NOT injected --
#            placement-class failures route to T0 instead of penalty inflation.
#   CL24 VERIFIER (cec_verifier): 3-charter adversarial panel on each auditor
#        proposal; Sonnet arbiter on contention; calibration recorded.
#   T0   PLACEMENT ACTUATOR (deterministic): on a placement-class attribution
#        or a Kelvin stall, run the GR-02 repair battery in-container on the
#        candidate (shift/layer-swap/via-insert + single-net reroute + DRC).
#   T6   VISION JUDGE (cec-vision-judge) on each NEW Pareto finalist render
#        (v2 facts-alongside protocol; structure/text only).
#   T7   BRIEFED REVIEWER (cec-manager-fast) corpus_fit_review on finalists.
#   T8   V4 DEEP BATCH AUDITOR every N rounds (owner 2026-06-11: a recurring
#        batch auditor, not morning-only). Serialized with routing; invited
#        to DECLINE (its measured value is restraint).
#   T9   LEDGER: every round ledgered; accepted injections logged as DF-01
#        ratification candidates -- NEVER auto-promoted (the set-in-stone
#        human-ratification boundary).
#
# Artifacts (permanent): docs/fullstack-run-<date>/ -- measurement.jsonl,
# intents/, findings/, verifier/, vision/, reviews/, live-rules.json, bundle.
#
# Usage:
#   python3 scripts/cec_fullstack.py --board eps-8pin --rounds 8     # the run-through
#   python3 scripts/cec_fullstack.py --board eps-8pin --hours 7      # a night
# ============================================================================
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_overnight_directed as ovd
import cec_verifier

RUN_DATE = os.environ.get("CEC_FS_DATE", time.strftime("%Y-%m-%d"))
PERM = os.path.join(ROOT, "docs", f"fullstack-run-{RUN_DATE}")
BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1")
V4_EVERY = int(os.environ.get("CEC_FS_V4_EVERY", "4"))
RULE_CAP = 10                                   # convergence lesson #3
PENALTY_MAX = 1000.0
KELVIN_STALL_K = 3                              # consecutive fails -> T0 escalation
# Completeness-over-speed (owner 2026-06-11): warm each model BEFORE its timed call so a
# cold start / GPU swap never makes the seat lose its own race, and give seats a budget
# wide enough to ride a swap. The last run's misses (intent manager 0/8, V4 0 live) were
# ALL swap-starvation, not logic. Slower, but every tier actually fires.
SEAT_TIMEOUT = int(os.environ.get("CEC_FS_SEAT_TIMEOUT", "600"))   # was 120-180 (lost the swap race)
WARM_TIMEOUT = int(os.environ.get("CEC_FS_WARM_TIMEOUT", "960"))   # > V4 ~7min cold start
PENALISABLE = ("drc", "unconnected", "length", "vias", "plane_signal_mm",
               "gate_fail", "kelvin_unrouted", "diffpair_unrouted", "max_T")

INTENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "intents": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {
                "net": {"type": "string"},
                "layers": {"type": "array", "items": {"type": "string",
                                                      "enum": ["F.Cu", "B.Cu"]}},
                "waypoints": {"type": "array", "maxItems": 4, "items": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                        "offset_mm": {"type": "array", "items": {"type": "number"},
                                      "minItems": 2, "maxItems": 2},
                        "between": {"type": "array", "items": {"type": "string"},
                                    "minItems": 2, "maxItems": 2},
                    },
                    "additionalProperties": False}},
            },
            "required": ["net", "layers", "waypoints"],
            "additionalProperties": False}},
    },
    "required": ["reasoning", "intents"],
    "additionalProperties": False,
}

PANEL_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["accept", "repair", "escalate"]},
                   "reason": {"type": "string"}},
    "required": ["action", "reason"], "additionalProperties": False,
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _d(*parts):
    p = os.path.join(PERM, *parts)
    os.makedirs(os.path.dirname(p) if "." in os.path.basename(p) else p, exist_ok=True)
    return p


# ---- broker choreography: warm a model BEFORE its timed call (completeness > speed) ----------------
def warm(model, timeout=None):
    """Ensure `model` is resident before a timed seat call. Already-running -> instant; else a
    1-token request rides the broker's cold-start/swap (the broker queues it through the start),
    so the subsequent real call hits a warm model instead of losing its own timeout to the swap.
    Returns True if up. Fail-safe: False (caller falls back), never raises."""
    import urllib.request
    base = BROKER.rsplit("/v1", 1)[0]
    try:
        reg = json.load(urllib.request.urlopen(base + "/broker/models", timeout=10))
        if (reg.get("models", {}).get(model) or {}).get("running"):
            return True
    except Exception:                                            # noqa: BLE001
        pass
    body = {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
    try:
        req = urllib.request.Request(BROKER + "/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "X-CEC-Client": "fs-warm"})
        urllib.request.urlopen(req, timeout=timeout or WARM_TIMEOUT)
        log(f"  warmed {model}")
        return True
    except Exception as e:                                       # noqa: BLE001
        log(f"  warm({model}) failed: {type(e).__name__}: {e}")
        return False


# ---- in-container helpers (pcbnew lives there) ------------------------------------------------------
def _exec_py(code, timeout=300):
    """Run a python snippet in the routing container; return (rc, stdout)."""
    r = subprocess.run(ovd.COMPOSE + ["exec", "-T", "routing", "python3", "-c", code],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout


def pour_facts(routed_host_path):
    """Deterministic POUR-INTEGRITY anchor (in-container). For each 12V power-pour net
    (SENSEC*_HI/_LO) on F.Cu: filled-copper ISLAND COUNT (a healthy pour is ONE solid island;
    a pour CLIPPED by a signal trace routed across it fragments into 2+), filled AREA mm^2, and
    the count of FOREIGN F.Cu tracks crossing the pour's bbox (the 'runs' doing the clipping).
    This is the number the vision pass is grounded against (CL-21 facts-alongside)."""
    rel = os.path.relpath(os.path.abspath(routed_host_path), ROOT)
    code = (
        "import sys, json, pcbnew; sys.path.insert(0,'/workspace/scripts')\n"
        f"b=pcbnew.LoadBoard('/workspace/{rel}')\n"
        "Z={}\n"
        "for z in b.Zones():\n"
        "    nn=z.GetNetname()\n"
        "    if not (nn.endswith('_HI') or nn.endswith('_LO')): continue\n"
        "    if not z.IsOnLayer(pcbnew.F_Cu): continue\n"
        "    try:\n"
        "        sp=z.GetFilledPolysList(pcbnew.F_Cu); isl=sp.OutlineCount(); ar=sp.Area()/1e12\n"
        "    except Exception:\n"
        "        isl=-1; ar=-1.0\n"
        "    bb=z.GetBoundingBox()\n"
        "    Z[nn]={'islands':isl,'area_mm2':round(ar,2),'foreign_cross':0,\n"
        "           '_bb':[bb.GetLeft(),bb.GetTop(),bb.GetRight(),bb.GetBottom()]}\n"
        "for t in b.GetTracks():\n"
        "    if t.GetClass()!='PCB_TRACK' or t.GetLayer()!=pcbnew.F_Cu: continue\n"
        "    tn=t.GetNetname(); s=t.GetStart(); e=t.GetEnd()\n"
        "    for nn,z in Z.items():\n"
        "        if tn==nn or tn.endswith('GND'): continue\n"
        "        l,tp,r,bm=z['_bb']\n"
        "        if min(s.x,e.x)<=r and max(s.x,e.x)>=l and min(s.y,e.y)<=bm and max(s.y,e.y)>=tp:\n"
        "            z['foreign_cross']+=1\n"
        "out={nn:{k:v for k,v in z.items() if k!='_bb'} for nn,z in Z.items()}\n"
        "print('POUR_JSON='+json.dumps(out))\n")
    try:
        rc, o = _exec_py(code, timeout=180)
        for ln in o.splitlines():
            if ln.startswith("POUR_JSON="):
                return json.loads(ln[len("POUR_JSON="):])
    except Exception as e:                                       # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    return {}


def vision_pour_check(rec, rnd):
    """T6 (owner ask 2026-06-11): a VISION model verifies the 12V power pours EVERY round and
    STATES clipping loudly. The pours are getting clipped by routed traces; this surfaces it
    repeatedly (deterministic island count + the VLM's read), into the log + a per-round
    artifact + the measurement row + the auditor context. Warmed before the call."""
    facts = pour_facts(rec["routed"])
    det_clipped = sorted(n for n, v in facts.items()
                         if isinstance(v, dict) and (v.get("islands", 1) or 1) > 1)
    log(f"  T6 POUR (deterministic): {json.dumps(facts)}")          # re-stated #1: the numbers
    png = _d("vision", f"pour-r{rnd}.png")
    if not render_board(rec["routed"], png):
        return {"skipped": "render failed", "det_clipped_nets": det_clipped, "facts": facts}
    if not warm("cec-vision-judge"):
        return {"skipped": "vision seat down", "det_clipped_nets": det_clipped, "facts": facts}
    schema = {"type": "object", "properties": {
        "pours_intact": {"type": "boolean"},
        "clipped_nets": {"type": "array", "items": {"type": "string"}},
        "detail": {"type": "string"}},
        "required": ["pours_intact", "clipped_nets", "detail"], "additionalProperties": False}
    text = (
        "You are verifying the F.Cu copper of a routed CEC eps-8pin power interposer. The large "
        "rectangular copper fills flanking the shunt resistors are the 12V POWER POURS (nets "
        "SENSEC1_HI / SENSEC1_LO / SENSEC2_HI / SENSEC2_LO). Your ONE job: are those pours INTACT, "
        "or are they CLIPPED/interrupted by signal traces routed across them?\n\n"
        "DETERMINISTIC FACTS extracted from the board file (trust these over any visual estimate; "
        "you are reading STRUCTURE, not measuring): " + json.dumps(facts) + "\n"
        "A HEALTHY pour is ONE solid island (islands=1) with no foreign trace crossing it. "
        "islands>1 or foreign_cross>0 means a 'run' (signal trace) was routed THROUGH the pour and "
        "fragmented it. For each pour net, confirm intact vs clipped and describe the crossing "
        "trace(s) you see. Reply ONLY the JSON object.")
    try:
        import cec_vlm_bakeoff as vb
        out = vb._chat("cec-vision-judge", text, png, schema=schema, max_tokens=700,
                       timeout=SEAT_TIMEOUT, ctx={"round": rnd, "check": "pour-integrity"})
        if isinstance(out, str):
            out = json.loads(out)
        out["det_clipped_nets"] = det_clipped
        out["facts"] = facts
        # re-stated #2: the vision verdict, loud
        verb = "INTACT" if out.get("pours_intact") and not out.get("clipped_nets") else "CLIPPED"
        log(f"  T6 POUR-CHECK (vision): {verb}  clipped={out.get('clipped_nets')} "
            f"-- {str(out.get('detail',''))[:120]}")
        return out
    except Exception as e:                                       # noqa: BLE001
        log(f"  T6 POUR-CHECK vision error: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}", "det_clipped_nets": det_clipped, "facts": facts}


def congestion_grid(board):
    """GR-01 grid on the committed board (in-container; once per run -- demand is
    placement-derived). Returns {hotspots, contested} or {} on failure."""
    pcb = os.path.relpath(ovd.BOARD_PCB[board], ROOT)
    code = (
        "import sys, json; sys.path.insert(0, '/workspace/scripts')\n"
        "import cec_router\n"
        f"g = cec_router.gr01_congestion_grid('/workspace/{pcb}')\n"
        "def clean(o):\n"
        "    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}\n"
        "    if isinstance(o, (list, tuple, set)): return [clean(v) for v in o]\n"
        "    return o if isinstance(o, (str, int, float, bool, type(None))) else str(o)\n"
        "print('GRID_JSON=' + json.dumps(clean(g)))\n")
    try:
        rc, out = _exec_py(code)
        for ln in out.splitlines():
            if ln.startswith("GRID_JSON="):
                return json.loads(ln[len("GRID_JSON="):])
    except Exception as e:                                       # noqa: BLE001
        log(f"  grid error: {e}")
    return {}


def render_board(routed_host_path, out_png):
    """kicad-cli render in-container -> host path under PERM."""
    rel_in = os.path.relpath(os.path.abspath(routed_host_path), ROOT)
    rel_out = os.path.relpath(os.path.abspath(out_png), ROOT)
    try:
        subprocess.run(ovd.COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "render",
                                      "-o", f"/workspace/{rel_out}", f"/workspace/{rel_in}"],
                       capture_output=True, text=True, timeout=300)
        return os.path.exists(out_png)
    except Exception:                                            # noqa: BLE001
        return False


def gr02_repair(routed_host_path, blocked_net, rnd):
    """T0 placement-actuator rung that is wired today: the deterministic GR-02
    repair battery on the blocked net, in-container, then rescore. Returns a
    result dict (claim settles by DRC in the same run -- Grade 2)."""
    rel = os.path.relpath(os.path.abspath(routed_host_path), ROOT)
    out_rel = f"build/fullstack/gr02-r{rnd}.kicad_pcb"
    code = (
        "import sys, json; sys.path.insert(0, '/workspace/scripts')\n"
        "import cec_router, cec_score, os\n"
        "os.makedirs('/workspace/build/fullstack', exist_ok=True)\n"
        f"res = cec_router.gr02_repair_battery('/workspace/{rel}', '/workspace/{out_rel}',\n"
        f"                                     blocked_net={blocked_net!r})\n"
        f"m = cec_score.score('/workspace/{out_rel}')\n"
        "out = {'repair': {k: (str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v)\n"
        "                  for k, v in (res or {}).items()},\n"
        "       'rescored': {'kelvin_ok': m.kelvin_ok, 'drc': m.drc, 'unconnected': m.unconnected}}\n"
        "print('GR02_JSON=' + json.dumps(out, default=str))\n")
    try:
        rc, out = _exec_py(code, timeout=600)
        for ln in out.splitlines():
            if ln.startswith("GR02_JSON="):
                d = json.loads(ln[len("GR02_JSON="):])
                d["board"] = out_rel
                return d
    except Exception as e:                                       # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    return {"error": "no GR02_JSON"}


# ---- T1: the intent manager (the model-managed assisted router) -------------------------------------
def intent_manager(board, grid, prev_intents, last_rec, rnd):
    """A worker-model seat WRITES the FR-02 intents for this round from the GR-01
    grid + the last round's failures. Valid waypoint keys only; falls back to the
    previous intents on any error (the route never waits on a model)."""
    failures = []
    if last_rec:
        failures = last_rec.get("reasons", [])[:6]
    user = (
        "You are the ROUTING INTENT MANAGER for the CEC %s board. Each round you may direct "
        "up to 4 nets through relational waypoints (FR-02): the router LOCKS a stub through "
        "each waypoint and routes the rest around it. Use this to route contested/failing nets "
        "AROUND the sense regions (shunt Kelvin windows) instead of through them.\n\n"
        "GR-01 CONGESTION GRID (hotspots + contested nets, route-first order):\n%s\n\n"
        "LAST ROUND failures: %s\n"
        "LAST ROUND intents: %s\n\n"
        "Waypoint forms: {\"ref\": \"U2\", \"offset_mm\": [dx, dy]} (relative to a footprint) or "
        "{\"between\": [\"U2\", \"U1\"]} (midpoint). Only F.Cu/B.Cu (plane layers are denied to the "
        "router). Prefer keeping I2C/CAN OUT of the mid-board shunt corridor. Reply the JSON object."
        % (board, json.dumps(grid)[:4000], json.dumps(failures), json.dumps(prev_intents)[:1500]))
    try:
        import cec_judge_local as jl
        out = jl._chat_json("You write routing intents as strict JSON.", user, INTENTS_SCHEMA,
                            name="intents", temperature=0.2, max_tokens=900,
                            model="cec-worker", timeout=SEAT_TIMEOUT)
        intents = out.get("intents") or []
        ok = [i for i in intents if i.get("net") and i.get("waypoints")]
        if ok:
            return ok, out.get("reasoning", "")[:400], "model"
    except Exception as e:                                       # noqa: BLE001
        log(f"  intent-manager fallback: {type(e).__name__}: {e}")
    return prev_intents, "fallback to previous intents", "fallback"


# ---- T4: worker panel (3 lenses) ---------------------------------------------------------------------
_LENSES = ("safety (hard gates: kelvin, diffpair, plane integrity)",
           "finishing (DRC count, dangling copper, cosmetics vs structure)",
           "progress (is effort spend still buying improvement?)")


def worker_panel(rec, rnd):
    votes = []
    m = {k: rec.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "drc",
                                 "unconnected", "plane_signal_mm", "max_T", "objective")}
    try:
        import cec_judge_local as jl
        for i, lens in enumerate(_LENSES):
            try:
                d = jl._chat_json(
                    f"You judge a routed PCB candidate through ONE lens: {lens}. "
                    "accept only if hard gates pass AND your lens is satisfied; repair if more "
                    "router effort could fix it; escalate if stuck/structural.",
                    f"Round {rnd} candidate metrics: {json.dumps(m)}\n"
                    f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}",
                    PANEL_SCHEMA, name="panel", temperature=0.0 if i < 2 else 0.3,
                    max_tokens=300, model="cec-worker", timeout=SEAT_TIMEOUT)
                votes.append((lens.split()[0], d.get("action"), d.get("reason", "")[:120]))
            except Exception:                                    # noqa: BLE001
                continue
    except Exception:                                            # noqa: BLE001
        pass
    if not votes:                                                # deterministic fallback
        return ("accept" if rec.get("gates_pass") else "repair"), [("fallback", None, "")]
    tally = {}
    for _, a, _r in votes:
        tally[a] = tally.get(a, 0) + 1
    action = max(tally, key=tally.get)
    if action == "accept" and not rec.get("gates_pass"):
        action = "repair"                                        # a panel cannot accept a gate-fail
    return action, votes


# ---- T5: the Sonnet auditor (rule cap + novelty + actuation handled by caller) ------------------------
def sonnet_audit(rec, lr, rnd, timeout=240, pourcheck=None):
    out_path = _d("findings", f"round-{rnd:03d}-sonnet.json")
    m = dict(rec)
    m["gate_fail"] = 0 if rec.get("gates_pass") else 1
    m["kelvin_unrouted"] = 0 if rec.get("kelvin_ok") else 1
    metrics = {k: m.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "drc",
                                     "unconnected", "plane_signal_mm", "max_T", "n_fem_flags",
                                     "objective", "gate_fail", "kelvin_unrouted")}
    # POUR-CLIP signal fed to the auditor (owner: state and RE-STATE it) so it can propose the
    # keepout / re-pour fix instead of letting the clip pass silently.
    pour_line = ""
    if pourcheck:
        pour_line = (f"POUR-INTEGRITY (vision + deterministic): clipped_nets="
                     f"{pourcheck.get('clipped_nets') or pourcheck.get('det_clipped_nets')}, "
                     f"facts={json.dumps(pourcheck.get('facts', {}))[:400]}\n")
    prompt = (
        "You are the IN-LOOP AUDITOR for the CEC routing pipeline (full-stack run). Constraints "
        "you operate under, learned from the last run converging to a local minimum:\n"
        f"- RULE CAP: at most {RULE_CAP} standing manager rules. Currently {len(lr['manager_rules'])}. "
        "At the cap you may only propose a CONSOLIDATION (one rule replacing several) or nothing.\n"
        "- ACTUATION: propose a penalty ONLY if a lever in the loop (router effort, intents, "
        "keepouts, GR-02 repair) can actually move that metric. A placement-class blockage must be "
        "attributed as failure_class=placement, NOT priced.\n"
        "- NOVELTY: a rephrase of an existing rule will be rejected by a deterministic gate.\n\n"
        f"ROUND {rnd} candidate:\n{json.dumps(metrics, indent=1)}\n"
        f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
        f"FEM flags: {json.dumps(rec.get('fem_flags', [])[:4])}\n"
        f"{pour_line}"
        f"stub summary: {json.dumps(rec.get('stub_summary', {}))}\n\n"
        f"Current injected penalties: {json.dumps(lr['scorer_penalties'])}\n"
        f"Standing rules ({len(lr['manager_rules'])}): {json.dumps(lr['manager_rules'][-6:])}\n"
        f"Penalisable keys: {list(PENALISABLE)}\n\n"
        f"Use the Write tool to write ONLY this JSON to {out_path} :\n"
        '{"verdict":"accept|repair|escalate","reasoning":"...","failure_class":'
        '"routing|placement|scoring|constraint|none",'
        '"scorer_penalty":{"metric":"...","weight":<number>,"rationale":"..."}|null,'
        '"manager_rule":"..."|null}\nThen reply DONE.')
    try:
        with open(_d("findings", f"round-{rnd:03d}-sonnet.stream.jsonl"), "w") as sfh:
            subprocess.run(["claude", "-p", "--model", "sonnet", "--allowedTools", "Write",
                            "--output-format", "stream-json", "--verbose",
                            "--include-partial-messages"],
                           input=prompt, text=True, stdout=sfh, stderr=subprocess.DEVNULL,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"verdict": "repair", "error": "timeout"}
    for _ in range(3):
        if os.path.exists(out_path):
            try:
                return json.load(open(out_path))
            except Exception:                                    # noqa: BLE001
                time.sleep(1)
        time.sleep(1)
    return {"verdict": "repair", "error": "no_file"}


# ---- guardrail + novelty + injection -----------------------------------------------------------------
def _norm_text(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split())


def novelty_ok(rule, lr):
    """Deterministic novelty gate (lesson #2): token-set Jaccard vs every standing
    rule; >=0.6 overlap = a rephrase, rejected."""
    cand = set(_norm_text(rule).split())
    if not cand:
        return False
    for r in lr["manager_rules"]:
        ex = set(_norm_text(r).split())
        if ex and len(cand & ex) / len(cand | ex) >= 0.6:
            return False
    return True


def inject(finding, lr, rnd, source, verifier_final):
    """Additive-only injection with rule cap + novelty + verifier gate. Every
    accepted item -> DF-01 ratification candidate (never auto-promoted)."""
    events = []
    sp = finding.get("scorer_penalty")
    if isinstance(sp, dict) and sp.get("metric") in PENALISABLE:
        metric, ok = sp["metric"], True
        try:
            w = float(sp.get("weight"))
        except (TypeError, ValueError):
            w, ok = None, False
        if verifier_final == "refute":
            events.append({"kind": "penalty", "metric": metric,
                           "action": "rejected:verifier_refuted"})
        elif not ok or w < 0:
            events.append({"kind": "penalty", "metric": metric,
                           "action": "rejected:invalid_or_negative"})
        else:
            cur = lr["scorer_penalties"].get(metric, 0.0)
            w = min(w, PENALTY_MAX)
            if w <= cur:
                events.append({"kind": "penalty", "metric": metric,
                               "action": "noop:not_a_tightening"})
            else:
                lr["scorer_penalties"][metric] = w
                events.append({"kind": "penalty", "metric": metric, "from": cur, "to": w,
                               "action": "accepted:raised",
                               "rationale": str(sp.get("rationale", ""))[:300]})
    rule = finding.get("manager_rule")
    if isinstance(rule, str) and len(rule.strip()) >= 12:
        if verifier_final == "refute":
            events.append({"kind": "rule", "action": "rejected:verifier_refuted",
                           "rule": rule[:120]})
        elif len(lr["manager_rules"]) >= RULE_CAP:
            events.append({"kind": "rule", "action": "rejected:rule_cap", "rule": rule[:120]})
        elif not novelty_ok(rule, lr):
            events.append({"kind": "rule", "action": "rejected:novelty_gate", "rule": rule[:120]})
        else:
            lr["manager_rules"].append(rule.strip())
            events.append({"kind": "rule", "action": "accepted:added", "rule": rule.strip()[:300]})
    for e in events:
        e.update({"round": rnd, "source": source})
        key = "injections" if e["action"].startswith("accepted") else "rejections"
        lr[key].append(e)
        if e["action"].startswith("accepted"):
            try:
                import cec_ledger
                cec_ledger.append(board="fullstack-candidate", mode="decision",
                                  verdict=f"ratification-candidate {e['kind']}", extra=e)
            except Exception:                                    # noqa: BLE001
                pass
    return events


# ---- T6/T7: finalist events ---------------------------------------------------------------------------
def vision_judge(routed, rec, rnd):
    """v2 facts-alongside protocol: facts ride with the render; structure/text only."""
    png = _d("vision", f"finalist-r{rnd}.png")
    if not render_board(routed, png):
        return {"skipped": "render failed"}
    facts = {k: rec.get(k) for k in ("kelvin_ok", "diffpair_ok", "drc", "unconnected",
                                     "plane_signal_mm", "max_T")}
    text = ("FACTS (deterministic, trust these over visual estimates -- you judge STRUCTURE "
            "and TEXT only, never geometry): %s\nThis is a routed CEC eps-8pin interposer "
            "candidate. Report: (1) any structural oddity (component text/refs, missing/odd "
            "regions, obvious copper anomalies); (2) whether the visible structure is consistent "
            "with the facts. 3 bullets max." % json.dumps(facts))
    try:
        import cec_vlm_bakeoff as vb
        out = vb._chat("cec-vision-judge", text, png, max_tokens=500, timeout=600)
        return {"png": os.path.relpath(png, PERM), "review": out if isinstance(out, str) else str(out)}
    except Exception as e:                                       # noqa: BLE001
        return {"skipped": f"{type(e).__name__}: {e}"}


def briefed_review(rec):
    try:
        import cec_judge_local as jl
        return jl.corpus_fit_review(rec["log"])
    except Exception as e:                                       # noqa: BLE001
        return {"skipped": f"{type(e).__name__}: {e}"}


# ---- the driver ---------------------------------------------------------------------------------------
def run(board, rounds, hours):
    os.makedirs(PERM, exist_ok=True)
    deadline = time.time() + hours * 3600.0 if hours else None
    lr = {"scorer_penalties": {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0},
          "manager_rules": [], "injections": [], "rejections": []}
    vs = cec_verifier.VerifierSession()
    log(f"FULL-STACK: board={board} rounds={rounds or '∞'} hours={hours or '-'} "
        f"v4_every={V4_EVERY} verifier_budget={vs.budget} rule_cap={RULE_CAP}")
    subprocess.run(ovd.COMPOSE + ["up", "-d", "routing"], capture_output=True, timeout=180)

    grid = congestion_grid(board)
    log(f"GR-01 grid: {len(grid.get('hotspots', []))} hotspots, "
        f"contested={[c if isinstance(c, str) else c.get('net') for c in grid.get('contested', [])][:6]}")
    json.dump(grid, open(_d("gr01-grid.json"), "w"), indent=1)

    records, intents, rnd = [], ovd.INTENTS[board], 0
    passes, opt_time, kelvin_stall, finalists_seen = 24, 40, 0, set()
    batch_for_v4 = []
    while True:
        rnd += 1
        if rounds and rnd > rounds:
            break
        if deadline and time.time() > deadline:
            break
        log(f"--- round {rnd}/{rounds or '∞'} passes={passes} opt={opt_time} ---")
        try:
            # PHASE worker: warm cec-worker so T1/T4/verifier hit a RESIDENT model instead of
            # losing their timeout to a cold start / swap (the last run's 0/8 intent failures).
            warm("cec-worker")
            # T1 intent manager
            last = records[-1] if records else None
            intents, why, src = intent_manager(board, grid, intents, last, rnd)
            ipath = _d("intents", f"round-{rnd:03d}.json")
            json.dump(intents, open(ipath, "w"), indent=1)
            log(f"  T1 intents[{src}]: {[i['net'] for i in intents]} -- {why[:80]}")

            # T2/T3/T3.5 route + score + FEM (in-container)
            rec = ovd._exec_route_one(board, rnd, passes=passes, opt_time=opt_time,
                                      intents_file=ipath)
            if rec.get("error"):
                log(f"  route error: {rec['error']}")
                continue
            records.append(rec)
            log(f"  T2-3.5: gates={'PASS' if rec['gates_pass'] else 'FAIL'} "
                f"kelvin={rec['kelvin_ok']} drc={rec['drc']} plane={rec['plane_signal_mm']} "
                f"pours={rec.get('stub_summary', {}).get('n_power_pours')} "
                f"max_T={rec.get('max_T')} fem_flags={rec.get('n_fem_flags')}")
            kelvin_stall = 0 if rec["kelvin_ok"] else kelvin_stall + 1

            # T4 worker panel -> effort actuation
            action, votes = worker_panel(rec, rnd)
            log(f"  T4 panel: {action} ({[(v[0], v[1]) for v in votes]})")
            if action == "repair":
                passes, opt_time = min(passes + 8, 60), min(opt_time + 12, 100)
            elif action == "escalate":
                passes, opt_time = min(passes + 14, 60), min(opt_time + 20, 120)
            else:
                passes, opt_time = 24, 40

            # T6 POUR-INTEGRITY vision check -- EVERY round (owner: pours are getting clipped by
            # runs; state and RE-STATE it). Swaps to the vision seat; warmed inside.
            pourcheck = vision_pour_check(rec, rnd)
            json.dump(pourcheck, open(_d("vision", f"pour-r{rnd:03d}.json"), "w"),
                      indent=1, default=str)
            pour_clipped_nets = sorted(set((pourcheck.get("clipped_nets") or []) +
                                           (pourcheck.get("det_clipped_nets") or [])))

            # T5 auditor (host Sonnet; SEES the pour-clip) -> CL-24 verifier -> guarded injection
            sj = sonnet_audit(rec, lr, rnd, pourcheck=pourcheck)
            vres, events = None, []
            if sj.get("scorer_penalty") or sj.get("manager_rule"):
                warm("cec-worker")           # verifier seats are worker calls; vision swapped it out
                ctx = {"rules_excerpt": json.dumps(lr["manager_rules"]),
                       "evidence": json.dumps({k: rec.get(k) for k in
                                               ("drc", "kelvin_ok", "plane_signal_mm",
                                                "unconnected", "reasons")}),
                       "levers": "router passes/opt_time, FR-02 waypoint intents, bake_hints "
                                 "keepouts, GR-02 repair battery (shift/swap/via), power pours",
                       "metrics": json.dumps([{k: r.get(k) for k in ("round", "drc", "kelvin_ok")}
                                              for r in records[-6:]])}
                vres = vs.verify({"issue": sj.get("reasoning", "")[:600],
                                  "scorer_penalty": sj.get("scorer_penalty"),
                                  "manager_rule": sj.get("manager_rule")}, ctx)
                vfinal = vres.final if vres else "uncertain"
                json.dump({"round": rnd, "final": vfinal,
                           "contention": vres.contention if vres else None,
                           "verdicts": vres.verdicts if vres else None,
                           "arbiter": vres.arbiter if vres else None},
                          open(_d("verifier", f"round-{rnd:03d}.json"), "w"), indent=1, default=str)
                events = inject(sj, lr, rnd, "sonnet", vfinal)
                log(f"  T5+CL24: auditor={sj.get('verdict')} fc={sj.get('failure_class')} "
                    f"verifier={vfinal}{' CONTENTION' if vres and vres.contention else ''} "
                    f"-> {[e['action'] for e in events]}")
            else:
                log(f"  T5: auditor={sj.get('verdict')} (no proposals)")

            # T0 placement actuator: actuation-refuted-as-placement OR kelvin stall
            t0 = None
            placement_attr = (sj.get("failure_class") == "placement") or (
                vres and any(v.get("failure_class") == "placement"
                             for v in vres.verdicts.values()))
            if (placement_attr or kelvin_stall >= KELVIN_STALL_K) and not rec["kelvin_ok"]:
                blocked = next((r.split()[0] for r in rec.get("reasons", [])
                                if "/SENSEC" in r), None)
                if blocked:
                    log(f"  T0 GR-02 repair on {blocked} (stall={kelvin_stall}, "
                        f"placement_attr={placement_attr})...")
                    t0 = gr02_repair(rec["routed"], blocked, rnd)
                    log(f"  T0 result: {json.dumps(t0.get('rescored', t0))[:140]}")
                    kelvin_stall = 0

            # frontier + finalist events (T6 vision + T7 reviewer)
            front = ovd.pareto_frontier(records)
            new_finalists = [r for r in front if r["sha"] not in finalists_seen]
            for f in new_finalists:
                finalists_seen.add(f["sha"])
                log(f"  NEW FINALIST r{f['round']} -> T6 vision + T7 reviewer")
                vj = vision_judge(f["routed"], f, f["round"])
                json.dump(vj, open(_d("vision", f"review-r{f['round']}.json"), "w"),
                          indent=1, default=str)
                rv = briefed_review(f)
                json.dump(rv if isinstance(rv, dict) else {"review": str(rv)},
                          open(_d("reviews", f"corpus-fit-r{f['round']}.json"), "w"),
                          indent=1, default=str)

            # T8 V4 deep batch auditor every N rounds (owner: recurring, not morning-only)
            v4 = None
            batch_for_v4.append({"round": rnd, "metrics": {k: rec.get(k) for k in
                                 ("gates_pass", "kelvin_ok", "drc", "plane_signal_mm", "max_T")},
                                 "panel": action, "injections": [e["action"] for e in events]})
            if rnd % V4_EVERY == 0:
                log(f"  T8 V4 batch audit ({len(batch_for_v4)} rounds; warming V4)...")
                warm("deepseek-v4-flash", WARM_TIMEOUT)   # was idle-reaped last run -> both 502
                v4 = vs.v4_batch_audit(batch_for_v4,
                                       {"penalties": lr["scorer_penalties"],
                                        "rules": lr["manager_rules"]})
                json.dump(v4, open(_d("findings", f"round-{rnd:03d}-v4batch.json"), "w"),
                          indent=1, default=str)
                if v4.get("findings"):
                    for f in v4["findings"]:
                        if f.get("ratifiable"):
                            inject({"manager_rule": f.get("issue")}, lr, rnd, "v4", "support")
                log(f"  T8: risk={v4.get('local_minimum_risk')} declined={v4.get('declined')} "
                    f"findings={len(v4.get('findings', []))}")
                batch_for_v4 = []

            # T9 measurement + ledger
            row = {"round": rnd, "ts": time.strftime("%H:%M:%S"), "sha": rec.get("sha"),
                   "intents_src": src, "passes": passes, "opt_time": opt_time,
                   "panel": action, "gates_pass": rec["gates_pass"],
                   "kelvin_ok": rec["kelvin_ok"], "drc": rec["drc"],
                   "unconnected": rec["unconnected"],
                   "plane_signal_mm": rec["plane_signal_mm"], "max_T": rec.get("max_T"),
                   "n_pours": rec.get("stub_summary", {}).get("n_power_pours"),
                   "objective": rec["objective"], "verifier_final": vres.final if vres else None,
                   "verifier_spent": vs.spent, "n_rules": len(lr["manager_rules"]),
                   "t0_fired": bool(t0), "n_finalists": len(front),
                   "pour_clipped": bool(pour_clipped_nets), "pour_clipped_nets": pour_clipped_nets,
                   "pour_vision": (pourcheck.get("pours_intact") if "pours_intact" in pourcheck
                                   else pourcheck.get("skipped") or pourcheck.get("error")),
                   "v4_risk": (v4 or {}).get("local_minimum_risk")}
            with open(_d("measurement.jsonl"), "a") as fh:
                fh.write(json.dumps(row) + "\n")
            json.dump(lr, open(_d("live-rules.json"), "w"), indent=1)
            ovd.ledger_round(board, rec, len(front))
        except Exception as e:                                   # noqa: BLE001
            log(f"  round {rnd} FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    front = ovd.pareto_frontier(records)
    # T7 VALIDATION PASS: if no Pareto finalist ever triggered the briefed reviewer, exercise it
    # once on the best-objective candidate so the full stack is genuinely validated end-to-end.
    end_review = None
    if records and not finalists_seen:
        best = min(records, key=lambda r: r.get("objective", 1e18))
        log(f"  T7 end-of-run validation review on best candidate r{best['round']} "
            f"(obj={best.get('objective')})...")
        warm("cec-manager-fast")
        end_review = briefed_review(best)
        json.dump(end_review if isinstance(end_review, dict) else {"review": str(end_review)},
                  open(_d("reviews", "end-of-run-best.json"), "w"), indent=1, default=str)
    pour_clip_rounds = [json.loads(l)["round"] for l in open(_d("measurement.jsonl"))
                        if l.strip() and json.loads(l).get("pour_clipped")] \
        if os.path.exists(_d("measurement.jsonl")) else []
    bundle = {"board": board, "rounds": rnd if not rounds else min(rnd, rounds),
              "records": len(records),
              "gate_passing": sum(1 for r in records if r["gates_pass"]),
              "pareto_finalists": len(front),
              "pour_clipped_rounds": pour_clip_rounds,
              "pour_clip_summary": (f"pours clipped by routed traces in {len(pour_clip_rounds)}/"
                                    f"{len(records)} rounds -- needs a notched-corridor keepout or "
                                    f"re-pour-after-route" if pour_clip_rounds else
                                    "no pour clipping detected"),
              "end_of_run_review": bool(end_review),
              "final_penalties": lr["scorer_penalties"],
              "n_rules": len(lr["manager_rules"]), "rules": lr["manager_rules"],
              "injections": lr["injections"], "rejections": len(lr["rejections"]),
              "verifier": {"spent": vs.spent, "budget": vs.budget,
                           "charter_status": {c: vs.cal.status(c) for c in cec_verifier.CHARTERS}},
              "front": [{k: r.get(k) for k in ("round", "objective", "drc", "unconnected",
                                               "plane_signal_mm", "max_T", "kelvin_ok")}
                        for r in front],
              "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(bundle, open(_d("bundle.json"), "w"), indent=1)
    log(f"DONE: {len(records)} candidates, {bundle['gate_passing']} gate-passing, "
        f"{len(front)} finalists, {len(lr['manager_rules'])} rules "
        f"(cap {RULE_CAP}), verifier {vs.spent}/{vs.budget} -> {PERM}")
    return bundle


def main(argv=None):
    ap = argparse.ArgumentParser(description="cec_fullstack -- every tier, a model in every seat")
    ap.add_argument("--board", default="eps-8pin", choices=sorted(ovd.BOARD_PCB))
    ap.add_argument("--rounds", type=int, default=None, help="bounded run-through")
    ap.add_argument("--hours", type=float, default=None, help="deadline-bounded night")
    a = ap.parse_args(argv)
    if not a.rounds and not a.hours:
        a.rounds = 8
    run(a.board, a.rounds, a.hours)


if __name__ == "__main__":
    main()
