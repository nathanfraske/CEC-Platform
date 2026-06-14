#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
#  cec_seat_bakeoff -- the 2-D {prompt VARIANT x MODEL} seat bake-off (owner ask 2026-06-13).
#
#  Mirrors cec_vlm_bakeoff.py, but for the TEXT seats of the full-stack loop (T1 intent manager,
#  T4 worker panel, T5 in-loop auditor) instead of the vision judge. For each seat we author several
#  PROMPT VARIANTS (current prose / terse-checklist / few-shot / decision-tree / json-skeleton-led) and
#  run EACH variant on a FIXED set of captured round-states across a pool of MODELS
#  {cec-worker-vision, deepseek-v4-flash, sonnet, opus}. Two signals per (seat, variant, model, case):
#
#    1. OBJECTIVE, deterministic (the PRIMARY decider): schema-conformance WITHOUT the scribe crutch,
#       plus seat-specific correctness -- real-ref & fence respect (T1), failure_class routing +
#       priceable-metric respect (T5), the safety never-accept-a-gate-fail invariant (T4) -- plus latency.
#    2. A MULTI-MODEL QUALITY JUDGE PANEL (the SECONDARY signal, to cut single-judge LLM bias):
#       LEAVE-ONE-OUT (a model never judges its own output), BLIND to producer identity, RUBRIC-anchored,
#       aggregated by MEDIAN + an inter-judge AGREEMENT report (high spread => defer to the objective).
#
#  HARDWARE: three heavy host-RAM local models (deepseek-v4 ~160GB, MiniMax/cec-manager ~102GB +~10.5min
#  cold boot, gpt-oss/cec-manager-fast) on ONE 5090 -> they CANNOT co-reside. Local producers/judges run
#  SEQUENTIALLY through the broker, BATCHING all of one model's calls into a single residency (amortize
#  the cold boot) then idle-reaping before the next. Cloud (sonnet/opus) runs concurrently off-box.
#
#  Subcommands:
#    produce  -- run every (seat, variant, model, case) -> produced/*.json   (host; broker + claude CLI)
#    judge    -- leave-one-out blind quality panel over the produced outputs -> judged/*.json
#    report   -- the variant x model matrix per seat + best-per-model + generalize-vs-overfit
#    show     -- print the full call transcript (what each model was asked + said)
#
#  Output dir: build/seat-bakeoff/ (gitignored). The harness is self-contained: it VENDORS the seat
#  schemas + the "current" prompt text (post prompt-tier-audit), so it does not depend on which
#  cec_fullstack is checked out -- the bake-off pins its own contracts for reproducibility.
import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
OUTDIR = os.path.join(ROOT, "build", "seat-bakeoff")
BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1").rstrip("/")

# ----------------------------------------------------------------- model pools --
# Producers we are choosing a default seat from + the variant authors we benchmark.
PRODUCERS = ["cec-worker-vision", "deepseek-v4-flash", "sonnet", "opus"]
# The quality-judge panel (leave-one-out): cloud + the distinct local families for family spread.
JUDGES = ["opus", "sonnet", "cec-worker", "cec-manager-fast", "deepseek-v4-flash", "cec-manager"]
CLOUD = {"sonnet", "opus", "haiku"}
# Local thinking models overrun a grammar-constrained reply -> empty content; judge non-thinking.
NOTHINK = {"cec-worker-vision", "cec-worker", "cec-worker-quality", "cec-worker-quality-vision",
           "cec-vision-judge"}
# Heavy host-RAM models that must run in their own broker residency (cold-boot amortized by batching).
HEAVY_LOCAL = {"deepseek-v4-flash", "cec-manager", "cec-manager-fast"}


def _is_cloud(m):
    return m in CLOUD or m.startswith("claude")


# ------------------------------------------------------------ vendored contracts --
INTENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "intents": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {
                "net": {"type": "string"},
                "layers": {"type": "array", "items": {"type": "string", "enum": ["F.Cu", "B.Cu"]}},
                "waypoints": {"type": "array", "maxItems": 4, "items": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                        "offset_mm": {"type": "array", "items": {"type": "number"},
                                      "minItems": 2, "maxItems": 2},
                        "between": {"type": "array", "items": {"type": "string"},
                                    "minItems": 2, "maxItems": 2}},
                    "additionalProperties": False}}},
            "required": ["net", "layers", "waypoints"], "additionalProperties": False}}},
    "required": ["reasoning", "intents"], "additionalProperties": False}

PANEL_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["accept", "repair", "escalate"]},
                   "reason": {"type": "string"}},
    "required": ["action", "reason"], "additionalProperties": False}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["accept", "repair", "escalate"]},
        "root_cause": {"type": "string"},
        "reasoning": {"type": "string"},
        "failure_class": {"type": "string",
                          "enum": ["routing", "placement", "scoring", "constraint", "none"]},
        "proposed_lever": {"type": ["object", "null"]},
        "scorer_penalty": {"type": ["object", "null"]},
        "manager_rule": {"type": ["string", "null"]}},
    "required": ["verdict", "root_cause", "reasoning", "failure_class",
                 "proposed_lever", "scorer_penalty", "manager_rule"],
    "additionalProperties": False}

PENALTY_METRIC = {"drc", "unconnected", "plane_signal_mm", "vias", "length", "max_T"}
FCLASS = ("routing", "placement", "scoring", "constraint", "none")
VERDICTS = ("accept", "repair", "escalate")
OWNED_LEVERS = ("router passes/opt_time, FR-02 waypoint intents (incl. routing an OFFENDING foreign "
                "signal net AROUND a sense corridor), bake_hints keepouts, GR-02 repair battery "
                "(shift/swap/via), power pours")

# ------------------------------------------------------------------ fixed input --
# A realistic eps-8pin manifest + fence (the M1 sense corridor = RS*/U20/U21; U2 the CAN xcvr is fenced
# but NOT a sense part). net keys mix slash/bare like pcbnew; fence nets are slash-stripped.
MANIFEST = {
    "outline_mm": [96.0, 35.0],
    "refs": {
        "U10": {"xy": [10.0, 12.0], "v": "INA181"}, "U11": {"xy": [14.0, 12.0], "v": "INA181"},
        "U20": {"xy": [21.0, 10.0], "v": "INA238"}, "U21": {"xy": [25.0, 10.0], "v": "INA238"},
        "RS1": {"xy": [20.0, 8.0], "v": "shunt"}, "RS2": {"xy": [24.0, 8.0], "v": "shunt"},
        "U1": {"xy": [55.0, 18.0], "v": "ESP32-C6"}, "U2": {"xy": [60.0, 17.0], "v": "TJA1051"},
        "U3": {"xy": [70.0, 12.0], "v": "LP5907"}, "J1": {"xy": [90.0, 17.0], "v": "RJ45"},
        "J5": {"xy": [88.0, 28.0], "v": "USB-C"},
        "J_IN1": {"xy": [6.0, 5.0], "v": "MiniFitJr"}, "J_OUT1": {"xy": [6.0, 30.0], "v": "MiniFitJr"},
        "J_IN2": {"xy": [34.0, 5.0], "v": "MiniFitJr"}, "J_OUT2": {"xy": [34.0, 30.0], "v": "MiniFitJr"}},
    "net_refs": {
        "/SENSEC1_HI": ["RS1", "U20"], "/SENSEC1_LO": ["RS1", "U20"],
        "/SENSEC2_HI": ["RS2", "U21"], "/SENSEC2_LO": ["RS2", "U21"],
        "/CAN_H": ["U2", "J1"], "/CAN_L": ["U2", "J1"],
        "/I2C_SDA": ["U1", "U20", "U21"], "/I2C_SCL": ["U1", "U20", "U21"],
        "/THRESH": ["U1", "U10", "U11"], "/USB_D_P": ["U1", "J5"], "/USB_D_N": ["U1", "J5"],
        "+3V3": ["U1", "U3"], "GND": ["U1", "U2", "U3"], "/DETC1": ["U10", "U11"]}}
FENCE = {"nets": {"SENSEC1_HI", "SENSEC1_LO", "SENSEC2_HI", "SENSEC2_LO"},
         "refs": {"RS1", "RS2", "U20", "U21", "U2"}}
GRID = {"contested": ["/CAN_H", "/THRESH", "/I2C_SDA"]}
LR = {"scorer_penalties": {}, "manager_rules": [], "injections": [], "rejections": [],
      "diagnoses": [], "refuted_metrics": []}

# Each case = a captured round-state exercising a distinct decision. expect_* annotate the deterministic
# correctness target (NOT shown to the seat).
CASES = {
    "kelvin-fail": {
        "rec": {"gates_pass": False, "kelvin_ok": False, "diffpair_ok": True, "drc": 10,
                "unconnected": 3, "plane_signal_mm": 0.5, "max_T": 120, "n_fem_flags": 1,
                "objective": 5000.0, "params": {"passes": 32, "opt_time": 60},
                "reasons": ["/SENSEC2_LO unrouted (kelvin sense stranded)", "items_not_allowed U11"],
                "drc_loci": [{"type": "unconnected", "where": "/SENSEC2_LO"}],
                "fem_flags": ["thin-neck lane2"], "stub_summary": {"n_power_pours": 6}},
        "pourcheck": {"det_clipped_nets": ["/SENSEC2_HI"], "facts": {"/SENSEC2_HI": {"islands": 2}}},
        "intents_src": "model",
        "expect_fclass": {"placement", "routing"}, "expect_panel": {"repair", "escalate"},
        "expect_penalty_ok": False},     # no gate-passing candidate -> a scorer penalty is WRONG here
    "drc-residual": {
        "rec": {"gates_pass": False, "kelvin_ok": True, "diffpair_ok": True, "drc": 8,
                "unconnected": 2, "plane_signal_mm": 0.0, "max_T": 95, "n_fem_flags": 0,
                "objective": 1200.0, "params": {"passes": 38, "opt_time": 72},
                "reasons": ["LOGO1 B.Cu clearance", "J1 shield-tab unconnected"],
                "drc_loci": [{"type": "silk", "where": "LOGO1"}, {"type": "clearance", "where": "LOGO1"}],
                "fem_flags": [], "stub_summary": {"n_power_pours": 6}},
        "pourcheck": {"det_clipped_nets": []}, "intents_src": "model",
        "expect_fclass": {"routing", "constraint", "none"}, "expect_panel": {"repair", "escalate"},
        "expect_penalty_ok": False},
    "gate-pass": {
        "rec": {"gates_pass": True, "kelvin_ok": True, "diffpair_ok": True, "drc": 0,
                "unconnected": 0, "plane_signal_mm": 0.0, "max_T": 78, "n_fem_flags": 0,
                "objective": 600.0, "params": {"passes": 24, "opt_time": 40},
                "reasons": [], "drc_loci": [], "fem_flags": [], "stub_summary": {"n_power_pours": 6}},
        "pourcheck": {"det_clipped_nets": []}, "intents_src": "model",
        "expect_fclass": {"none", "scoring"}, "expect_panel": {"accept"},
        "expect_penalty_ok": True}}      # the only case where a scorer penalty is admissible (ranks finalists)

# ============================================================ SEAT VARIANTS ====
# Each seat exposes VARIANTS: {variant_name: build(case) -> [(item_label, system, user), ...]}.
# Most seats yield one item; the T4 panel yields one per lens (safety/finishing/progress). The "current"
# variant mirrors the live post-prompt-audit prompts; the others are format ideas under test.

def _refs_block(manifest):
    refs = manifest["refs"]
    ref_lines = ", ".join(f"{r}@({d['xy'][0]},{d['xy'][1]})[{d.get('v', '')}]"
                          for r, d in sorted(refs.items()))
    nr = json.dumps(manifest.get("net_refs", {}))[:1500]
    return ref_lines, nr


def _corridor_refs(manifest, fence):
    import cec_fr02 as _fr
    refs = manifest["refs"]
    on_sense = {r for n, rl in manifest.get("net_refs", {}).items() if _fr.is_sense_net(n) for r in rl}
    sr = [r for r in fence.get("refs", ()) if r in refs and r in on_sense]
    if not sr:
        sr = [r for r in fence.get("refs", ()) if r in refs]
    return sr


def _fence_line(fence):
    return ("FENCED -- never list these as a target net and never anchor to these refs: "
            f"nets={sorted(fence.get('nets', []))[:12]}, refs={sorted(fence.get('refs', []))}.\n")


# ----- T1 intent manager variants -----
def _t1_inputs(case):
    rec = case["rec"]
    ref_lines, nr = _refs_block(MANIFEST)
    sr = _corridor_refs(MANIFEST, FENCE)
    xs = [MANIFEST["refs"][r]["xy"][0] for r in sr]
    ys = [MANIFEST["refs"][r]["xy"][1] for r in sr]
    corridor = (f"refs {sr} span x[{min(xs)},{max(xs)}] y[{min(ys)},{max(ys)}] mm" if sr else "n/a")
    contested = GRID.get("contested", [])
    return rec, ref_lines, nr, corridor, contested


def t1_current(case):
    rec, ref_lines, nr, corridor, contested = _t1_inputs(case)
    sysm = ("You are the T1 INTENT MANAGER for the CEC routing loop. You emit FR-02 waypoint intents that "
            "steer the autorouter: each intent names a NET, the layers, and waypoints anchored to BOARD "
            "REFS (a ref, or 'between' two refs). Anchor ONLY to refs that exist on the board. Never "
            "target a fenced net or anchor solely to fenced refs. Route signal nets AROUND the sense "
            "corridor. Emit only intents that help THIS round's failure; an empty list is valid.")
    usr = (f"BOARD FOOTPRINTS (board {MANIFEST['outline_mm']} mm; anchor ONLY to these refs):\n{ref_lines}\n"
           f"NET->REFS:\n{nr}\n"
           f"SENSE CORRIDOR (route signal nets AROUND it): {corridor}.\n"
           + _fence_line(FENCE)
           + f"CONTESTED nets this round: {contested}\n"
           f"ROUND failing reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
           f"gates_pass={rec['gates_pass']} kelvin_ok={rec['kelvin_ok']} drc={rec['drc']}\n"
           "Emit reasoning + up to 4 intents.")
    return [("intent", sysm, usr)]


def t1_terse(case):
    rec, ref_lines, nr, corridor, contested = _t1_inputs(case)
    sysm = ("T1 INTENT MANAGER. Output FR-02 waypoint intents (net, layers, waypoints->refs).\n"
            "RULES (hard):\n"
            "- anchor ONLY to listed refs; unknown ref => the intent is dropped\n"
            "- never a fenced net/ref as a target\n"
            "- route signal AROUND the sense corridor\n"
            "- only intents that fix THIS round; [] is valid")
    usr = (f"REFS: {ref_lines}\nNET->REFS: {nr}\nCORRIDOR: {corridor}\n{_fence_line(FENCE)}"
           f"CONTESTED: {contested}\nREASONS: {json.dumps(rec.get('reasons', [])[:6])}\n"
           f"gates={rec['gates_pass']} kelvin={rec['kelvin_ok']} drc={rec['drc']}")
    return [("intent", sysm, usr)]


# ----- T5 auditor variants -----
def _t5_metrics(rec):
    m = {k: rec.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                                 "plane_signal_mm", "max_T", "n_fem_flags", "objective")}
    m["gate_fail"] = 0 if rec.get("gates_pass") else 1
    m["kelvin_unrouted"] = 0 if rec.get("kelvin_ok") else 1
    return m


def t5_current(case):
    rec = case["rec"]
    pc = case.get("pourcheck", {})
    sysm = ("You are the IN-LOOP AUDITOR for the CEC routing pipeline. Read the round context and emit "
            "ONLY the JSON the schema defines -- root_cause ALWAYS filled; scorer_penalty null unless a "
            "gate-passing candidate already exists.")
    usr = ("Your `failure_class` is what STEERS the loop -- choose it deliberately:\n"
           "- placement -> the route cannot close because of WHERE parts sit. ACTUATION BOUNDARY: this "
           "fires the deterministic T0 GR-02 repair ONLY when a Kelvin SENSE net is unrouted "
           "(kelvin_ok=false); a congested-corridor placement failure is recorded + ridden by the "
           "corridor-avoid lever + panel effort, not T0.\n"
           "- routing -> placement is fine, more/better routing can close it (the corridor-avoid lever "
           "fires from clipped nets; the panel bumps effort).\n"
           "- scoring -> price a metric ONLY if a gate-passing candidate ALREADY exists (a reweight only "
           "reorders existing candidates; it cannot create a better board).\n"
           "- constraint/none when apt.\n"
           f"ALLOWED LEVERS: {OWNED_LEVERS}.\n"
           f"Priceable metrics (a penalty on any other metric is rejected): {sorted(PENALTY_METRIC)}.\n\n"
           f"ROUND candidate:\n{json.dumps(_t5_metrics(rec), indent=1)}\n"
           f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
           f"FEM flags: {json.dumps(rec.get('fem_flags', [])[:4])}\n"
           f"POUR-INTEGRITY: clipped_nets={pc.get('det_clipped_nets')}\n"
           f"stub summary: {json.dumps(rec.get('stub_summary', {}))}\n"
           "root_cause ALWAYS filled; proposed_lever is ADVISORY only; scorer_penalty null unless a "
           "gate-passing candidate already exists.")
    return [("audit", sysm, usr)]


def t5_decision_tree(case):
    rec = case["rec"]
    pc = case.get("pourcheck", {})
    sysm = ("You are the CEC IN-LOOP AUDITOR. Emit ONLY the schema JSON. root_cause ALWAYS filled.")
    usr = ("Pick failure_class with this decision tree:\n"
           "1. gates_pass==true? -> failure_class=none (or scoring, ONLY to rank a finalist). STOP.\n"
           "2. kelvin_ok==false (a /SENSEC sense net unrouted)? -> failure_class=placement "
           "(this is the ONLY case that fires the T0 GR-02 repair). STOP.\n"
           "3. residual DRC is finishing/cosmetic (logo/shield-tab) or congestion? -> failure_class=routing. STOP.\n"
           "4. a locked design constraint blocks it? -> failure_class=constraint.\n"
           "scorer_penalty: null UNLESS gates_pass already (then a metric in "
           f"{sorted(PENALTY_METRIC)} may rank finalists). proposed_lever: advisory, from {OWNED_LEVERS}.\n\n"
           f"ROUND candidate:\n{json.dumps(_t5_metrics(rec), indent=1)}\n"
           f"reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
           f"clipped_nets={pc.get('det_clipped_nets')}  fem={json.dumps(rec.get('fem_flags', [])[:4])}")
    return [("audit", sysm, usr)]


# ----- T4 worker panel variants (three lenses; the seat decision = modal action, safety overrides accept) -----
_PANEL_FIELD = (" Return JSON: field \"action\" in {accept,repair,escalate} + a one-line \"reason\".")


def _t4_lenses_current(case):
    rec = case["rec"]
    gates = {k: rec.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "plane_signal_mm")}
    reasons = rec.get("reasons", [])[:6]
    return [
        ("safety",
         "You are the SAFETY lens of a routing panel. The hard gates are ALREADY computed -- do NOT "
         "recompute. accept ONLY if gates_pass is true; else repair if more effort could close the gate; "
         "escalate if structural." + _PANEL_FIELD,
         f"GATE STATE: {json.dumps(gates)}\nfailing reasons: {json.dumps(reasons)}"),
        ("finishing",
         "You are the FINISHING lens. Gates are the safety lens's job. Judge whether the residual DRC is "
         "finishing/cosmetic (a decorative logo, a shield-tab tie) or structural. accept if finishing-only; "
         "repair if more effort clears it; escalate if structural." + _PANEL_FIELD,
         f"drc={rec.get('drc')} unconnected={rec.get('unconnected')}\n"
         f"DRC loci: {json.dumps(rec.get('drc_loci', [])[:12])}\nreasons: {json.dumps(reasons)}"),
        ("progress",
         "You are the PROGRESS lens. Judge the trajectory: is effort still buying improvement? accept if "
         "converged; repair if still improving; escalate if ramped with no movement." + _PANEL_FIELD,
         f"this round: objective={rec.get('objective')} drc={rec.get('drc')} "
         f"params={json.dumps(rec.get('params', {}))}")]


def t4_current(case):
    return _t4_lenses_current(case)


def t4_terse(case):
    rec = case["rec"]
    gates = {k: rec.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "plane_signal_mm")}
    reasons = rec.get("reasons", [])[:6]
    return [
        ("safety", "SAFETY lens. accept IFF gates_pass; else repair (effort can close) | escalate "
         "(structural). Gates are precomputed." + _PANEL_FIELD,
         f"gates={json.dumps(gates)} reasons={json.dumps(reasons)}"),
        ("finishing", "FINISHING lens. residual cosmetic (logo/shield)? accept. effort clears? repair. "
         "structural? escalate." + _PANEL_FIELD,
         f"drc={rec.get('drc')} loci={json.dumps(rec.get('drc_loci', [])[:12])}"),
        ("progress", "PROGRESS lens. converged? accept. improving? repair. stalled-with-ramp? escalate."
         + _PANEL_FIELD,
         f"obj={rec.get('objective')} drc={rec.get('drc')} params={json.dumps(rec.get('params', {}))}")]


SEATS = {
    "t1": {"schema": INTENTS_SCHEMA, "variants": {"current": t1_current, "terse": t1_terse}},
    "t4": {"schema": PANEL_SCHEMA, "variants": {"current": t4_current, "terse": t4_terse}},
    "t5": {"schema": AUDIT_SCHEMA, "variants": {"current": t5_current, "decision-tree": t5_decision_tree}},
}

# ===================================================== minimal schema validator ==
def schema_ok(obj, schema):
    """Structural validation (enough for conformance scoring; no jsonschema dependency)."""
    t = schema.get("type")
    if isinstance(t, list):
        return any(schema_ok(obj, {**schema, "type": tt}) for tt in t)
    if t == "object":
        if not isinstance(obj, dict):
            return False
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in obj:
                return False
        if schema.get("additionalProperties") is False:
            if any(k not in props for k in obj):
                return False
        return all(schema_ok(obj[k], props[k]) for k in obj if k in props)
    if t == "array":
        if not isinstance(obj, list):
            return False
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            return False
        it = schema.get("items")
        return all(schema_ok(e, it) for e in obj) if it else True
    if t == "string":
        return isinstance(obj, str) and (obj in schema["enum"] if "enum" in schema else True)
    if t == "number":
        return isinstance(obj, (int, float)) and not isinstance(obj, bool)
    if t == "null":
        return obj is None
    return True


# ============================================================ transport ========
_TRANSCRIPT = {"path": None}


def _t_log(rec):
    p = _TRANSCRIPT["path"]
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _call_local(model, system, user, schema, max_tokens=1200, timeout=2700, ctx=None):
    """Broker call with the json_schema grammar. Returns (parsed|None, secs, raw, reasoning, scribe,
    err). scribe=True means content came back EMPTY and the JSON was rescued from the reasoning trace
    (a thinking overrun -- counts as a schema-conformance FAILURE in the objective score)."""
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0.0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "seat", "schema": schema, "strict": True}}}
    if model in NOTHINK:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(BROKER + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-CEC-Client": "seat-bakeoff"})
    base = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, **(ctx or {}),
            "prompt": system + "\n----\n" + user}
    t0 = time.time()
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception as e:                                       # noqa: BLE001
        dt = round(time.time() - t0, 1)
        _t_log({**base, "secs": dt, "error": "%s: %s" % (type(e).__name__, e)})
        return None, dt, "", None, False, "%s: %s" % (type(e).__name__, e)
    dt = round(time.time() - t0, 1)
    msg = resp["choices"][0]["message"]
    raw = (msg.get("content") or "")
    reasoning = msg.get("reasoning_content") or None
    parsed, scribe, err = None, False, None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception as e:                                   # noqa: BLE001
            err = "parse: %s" % e
    elif reasoning:                                              # thinking-overrun rescue (= conformance fail)
        m = re.search(r"\{.*\}", reasoning, re.S)
        if m:
            try:
                parsed, scribe = json.loads(m.group(0)), True
            except Exception as e:                               # noqa: BLE001
                err = "rescue-parse: %s" % e
        else:
            err = "empty content, no recoverable JSON"
    else:
        err = "empty content"
    _t_log({**base, "secs": dt, "usage": resp.get("usage", {}), "content": raw,
            "reasoning": reasoning, "scribe": scribe, "error": err,
            "finish_reason": resp["choices"][0].get("finish_reason")})
    return parsed, dt, raw, reasoning, scribe, err


def _call_cloud(model, system, user, schema, timeout=600, ctx=None):
    import cec_judge_local as jl
    base = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, **(ctx or {}),
            "prompt": system + "\n----\n" + user}
    t0 = time.time()
    try:
        parsed = jl._chat_json_cloud(system, user, schema, model=model, timeout=timeout)
        dt = round(time.time() - t0, 1)
        _t_log({**base, "secs": dt, "content": json.dumps(parsed), "scribe": False, "error": None})
        return parsed, dt, json.dumps(parsed), None, False, None
    except Exception as e:                                       # noqa: BLE001
        dt = round(time.time() - t0, 1)
        _t_log({**base, "secs": dt, "error": "%s: %s" % (type(e).__name__, e)})
        return None, dt, "", None, False, "%s: %s" % (type(e).__name__, e)


def call(model, system, user, schema, max_tokens=1200, timeout=2700, ctx=None):
    if _is_cloud(model):
        return _call_cloud(model, system, user, schema, timeout=min(timeout, 600), ctx=ctx)
    return _call_local(model, system, user, schema, max_tokens=max_tokens, timeout=timeout, ctx=ctx)


# ============================================================ deterministic scorers ==
def _norm_net(n):
    return str(n or "").lstrip("/").upper()


def score_t1(out, case):
    """real-ref respect + fence respect + net validity over the emitted intents."""
    checks = {"schema_ok": False, "n_intents": 0, "unknown_refs": [], "unknown_nets": [],
              "fence_violations": []}
    if not (isinstance(out, dict) and schema_ok(out, INTENTS_SCHEMA)):
        return {"schema_ok": False, "correctness": 0.0, "checks": checks}
    checks["schema_ok"] = True
    refs = set(MANIFEST["refs"])
    known_nets = {_norm_net(n) for n in MANIFEST["net_refs"]} | {_norm_net(n) for n in GRID["contested"]}
    fnets = {_norm_net(n) for n in FENCE["nets"]}
    frefs = set(FENCE["refs"])
    intents = out.get("intents", [])
    checks["n_intents"] = len(intents)
    valid = 0
    for it in intents:
        ok = True
        if _norm_net(it.get("net")) not in known_nets:
            checks["unknown_nets"].append(it.get("net")); ok = False
        if _norm_net(it.get("net")) in fnets:
            checks["fence_violations"].append(it.get("net")); ok = False
        wps = it.get("waypoints", []) or []
        wp_refs = []
        for w in wps:
            if isinstance(w, dict):
                if w.get("ref"):
                    wp_refs.append(w["ref"])
                wp_refs += list(w.get("between", []) or [])
        for r in wp_refs:
            if r not in refs:
                checks["unknown_refs"].append(r); ok = False
        if wp_refs and all(r in frefs for r in wp_refs):
            checks["fence_violations"].append("all-fenced-wp:" + str(it.get("net"))); ok = False
        valid += 1 if ok else 0
    # correctness: clean intents (no unknown ref/net, fence-respecting). An empty list is acceptable
    # (1.0) -- not steering is valid -- but a kelvin-fail case rewards >=1 valid steering intent.
    if intents:
        corr = valid / len(intents)
    else:
        corr = 0.6 if case.get("rec", {}).get("kelvin_ok") is False else 1.0
    return {"schema_ok": True, "correctness": round(corr, 3), "checks": checks}


def score_t5(out, case):
    checks = {"schema_ok": False, "fclass": None, "fclass_ok": False, "penalty_ok": True,
              "root_cause_filled": False, "lever_ok": True}
    if not (isinstance(out, dict) and schema_ok(out, AUDIT_SCHEMA)):
        return {"schema_ok": False, "correctness": 0.0, "checks": checks}
    checks["schema_ok"] = True
    fc = out.get("failure_class")
    checks["fclass"] = fc
    checks["fclass_ok"] = fc in case["expect_fclass"]
    checks["root_cause_filled"] = bool((out.get("root_cause") or "").strip())
    sp = out.get("scorer_penalty")
    if sp not in (None, {}):
        metric = sp.get("metric") if isinstance(sp, dict) else None
        # a penalty is admissible ONLY on a gate-passing case AND on a priceable metric
        checks["penalty_ok"] = bool(case["expect_penalty_ok"] and metric in PENALTY_METRIC)
    lever = out.get("proposed_lever")
    if isinstance(lever, dict) and lever.get("lever"):
        # advisory, but a lever should reference an owned actuation (loose keyword check)
        checks["lever_ok"] = any(k in str(lever.get("lever", "")).lower()
                                 for k in ("pass", "opt", "waypoint", "intent", "keepout", "pour",
                                           "gr-02", "gr02", "repair", "route", "via", "shift", "swap"))
    score = (0.45 * checks["fclass_ok"] + 0.25 * checks["penalty_ok"]
             + 0.2 * checks["root_cause_filled"] + 0.1 * checks["lever_ok"])
    return {"schema_ok": True, "correctness": round(score, 3), "checks": checks}


def _panel_decide(items_out):
    """Mirror worker_panel: modal action, safety can't accept a gate-fail (applied by caller via case)."""
    actions = [o.get("action") for o in items_out if isinstance(o, dict) and o.get("action")]
    if not actions:
        return None
    tally = {}
    for a in actions:
        tally[a] = tally.get(a, 0) + 1
    return max(tally, key=tally.get)


def score_t4(out_items, case):
    """out_items = the per-lens dicts in lens order (safety, finishing, progress). Correctness grades
    (a) the SAFETY LENS itself -- it must not accept a gate-fail; the worker_panel override is a
    deterministic backstop, NOT an excuse for an unsafe lens call -- and (b) the aggregate (post-override)
    panel action vs the case's expected action."""
    each_ok = [isinstance(o, dict) and schema_ok(o, PANEL_SCHEMA) for o in out_items]
    checks = {"schema_ok": all(each_ok),
              "lens_actions": [o.get("action") if isinstance(o, dict) else None for o in out_items]}
    if not all(each_ok):
        return {"schema_ok": False, "correctness": 0.0, "checks": checks}
    safety_lens = out_items[0].get("action") if out_items else None     # lenses ordered safety-first
    action = _panel_decide(out_items)
    if action == "accept" and not case["rec"]["gates_pass"]:
        action = "repair"                                      # the worker_panel safety override
    checks["panel_action"] = action
    checks["safety_lens_ok"] = not (case["rec"]["gates_pass"] is False and safety_lens == "accept")
    checks["action_ok"] = action in case["expect_panel"]
    score = 0.5 * checks["action_ok"] + 0.5 * checks["safety_lens_ok"]
    return {"schema_ok": True, "correctness": round(score, 3), "checks": checks}


SCORERS = {"t1": score_t1, "t4": score_t4, "t5": score_t5}


# ============================================================ producer runner ===
def _d(*p):
    path = os.path.join(OUTDIR, *p)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _produce_one(seat, variant, model, cid):
    case = CASES[cid]
    items = SEATS[seat]["variants"][variant](case)
    schema = SEATS[seat]["schema"]
    outs, secs, scribes, errs = [], [], [], []
    for label, system, user in items:
        parsed, dt, raw, reasoning, scribe, err = call(
            model, system, user, schema, ctx={"seat": seat, "variant": variant, "case": cid,
                                               "item": label})
        outs.append(parsed)
        secs.append(dt)
        scribes.append(scribe)
        if err:
            errs.append("%s:%s" % (label, err))
    # score
    if seat == "t4":
        sc = score_t4(outs, case)
    else:
        sc = SCORERS[seat](outs[0] if outs else None, case)
    rec = {"seat": seat, "variant": variant, "model": model, "case": cid,
           "outputs": outs, "latency_s": round(sum(secs), 1), "scribe_used": any(scribes),
           "errors": errs, "score": sc}
    return rec


def produce(seats, variants, models, cases, tag=""):
    _TRANSCRIPT["path"] = _d("transcript%s.jsonl" % tag)
    _t_log({"run_start": time.strftime("%Y-%m-%d %H:%M:%S"), "phase": "produce",
            "seats": seats, "variants": variants, "models": models, "cases": cases})
    print("[transcript] %s" % _TRANSCRIPT["path"])
    # Build the work list, grouped so local heavy models run all their work in one residency.
    work = [(s, v, m, c) for m in models for s in seats for v in variants
            if v in SEATS[s]["variants"] for c in cases]
    cloud_work = [w for w in work if _is_cloud(w[2])]
    local_work = [w for w in work if not _is_cloud(w[2])]
    results = []

    def run_and_save(w):
        s, v, m, c = w
        print("  produce %s/%s/%s/%s" % (s, v, m, c))
        r = _produce_one(s, v, m, c)
        json.dump(r, open(_d("produced", "%s__%s__%s__%s.json" % (s, v, m, c)), "w"), indent=1)
        return r
    # cloud: concurrent (off-box, no residency contention)
    if cloud_work:
        print("=== cloud producers (%d calls) ===" % len(cloud_work))
        with ThreadPoolExecutor(max_workers=int(os.environ.get("CEC_BAKEOFF_CLOUD_WORKERS", "4"))) as ex:
            results += list(ex.map(run_and_save, cloud_work))
    # local: sequential, grouped by model (one residency per model -> amortize cold boot)
    for m in [x for x in models if not _is_cloud(x)]:
        mw = [w for w in local_work if w[2] == m]
        if not mw:
            continue
        print("=== local producer %s (%d calls, one residency) ===" % (m, len(mw)))
        for w in mw:
            results.append(run_and_save(w))
    json.dump({"results": [r["score"] | {"seat": r["seat"], "variant": r["variant"],
                                         "model": r["model"], "case": r["case"],
                                         "latency_s": r["latency_s"], "scribe_used": r["scribe_used"],
                                         "errors": r["errors"]} for r in results]},
              open(_d("produce-summary%s.json" % tag), "w"), indent=1)
    print("produced %d outputs -> %s" % (len(results), _d("produced")))
    return results


# ============================================================ judge panel ======
JUDGE_SCHEMA = {"type": "object", "properties": {
    "score": {"type": "integer"}, "rationale": {"type": "string"}},
    "required": ["score", "rationale"], "additionalProperties": False}

RUBRICS = {
    "t1": ("Rate 1-5 how good this set of FR-02 routing INTENTS is for the round: do the intents anchor "
           "to plausible refs, respect the sense corridor, avoid steering fenced/sense nets, and target "
           "the round's actual failure? 5=expert, 1=useless/harmful."),
    "t4": ("Rate 1-5 the panel lens decisions for this round: are accept/repair/escalate calls justified "
           "by the gate state and trajectory, with a crisp reason? A gate-fail accepted = 1."),
    "t5": ("Rate 1-5 this auditor verdict: is the failure_class the right STEERING choice for the round, "
           "is root_cause a bankable diagnosis, is a scorer_penalty proposed ONLY when a gate-passing "
           "candidate exists, and is the proposed_lever sane? 5=expert root-cause+steer, 1=misleading."),
}


def _judge_prompt(seat, produced):
    rubric = RUBRICS[seat]
    case = CASES[produced["case"]]
    # BLIND: never reveal the producer model. Present the round + the output to judge.
    body = json.dumps(produced["outputs"], indent=1)[:2500]
    sysm = ("You are an impartial reviewer of one CEC routing-loop seat output. Score ONLY on the rubric. "
            "You do NOT know which model produced it. Return integer score 1-5 + a one-line rationale.")
    usr = (rubric + "\n\nROUND CONTEXT (the seat saw a version of this):\n"
           f"gates_pass={case['rec']['gates_pass']} kelvin_ok={case['rec']['kelvin_ok']} "
           f"drc={case['rec']['drc']} reasons={json.dumps(case['rec'].get('reasons', [])[:5])} "
           f"clipped={case.get('pourcheck', {}).get('det_clipped_nets')}\n\n"
           f"SEAT OUTPUT TO SCORE:\n{body}\n\nReturn {{\"score\": <1-5>, \"rationale\": \"...\"}}")
    return sysm, usr


def judge(tag="", judges=None, run_dir=None):
    judges = judges or JUDGES
    pdir = os.path.join(run_dir or OUTDIR, "produced")
    produced = [json.load(open(os.path.join(pdir, f))) for f in sorted(os.listdir(pdir))
                if f.endswith(".json")]
    _TRANSCRIPT["path"] = _d("judge-transcript%s.jsonl" % tag)
    print("[judge] %d outputs x %d judges (leave-one-out, blind)" % (len(produced), len(judges)))
    # accumulate judge scores onto each produced record
    scores = {id(p): [] for p in produced}
    # batched residency: run ALL of one judge's calls before moving to the next local judge.
    cloud_judges = [j for j in judges if _is_cloud(j)]
    local_judges = [j for j in judges if not _is_cloud(j)]

    def judge_with(j):
        print("=== judge %s ===" % j)
        for p in produced:
            if p["model"] == j:                                 # LEAVE-ONE-OUT: never judge own output
                continue
            sysm, usr = _judge_prompt(p["seat"], p)
            parsed, dt, raw, reasoning, scribe, err = call(
                j, sysm, usr, JUDGE_SCHEMA, max_tokens=400,
                ctx={"judge": j, "seat": p["seat"], "variant": p["variant"],
                     "producer": "HIDDEN", "case": p["case"]})
            if isinstance(parsed, dict) and isinstance(parsed.get("score"), int):
                sc = max(1, min(5, parsed["score"]))
                scores[id(p)].append({"judge": j, "score": sc,
                                      "rationale": (parsed.get("rationale") or "")[:200]})
    if cloud_judges:
        with ThreadPoolExecutor(max_workers=int(os.environ.get("CEC_BAKEOFF_CLOUD_WORKERS", "4"))) as ex:
            list(ex.map(judge_with, cloud_judges))
    for j in local_judges:                                      # sequential -> one residency each
        judge_with(j)
    for p in produced:
        js = scores[id(p)]
        vals = [s["score"] for s in js]
        p["judge"] = {"votes": js, "n": len(vals),
                      "median": statistics.median(vals) if vals else None,
                      "mean": round(statistics.mean(vals), 2) if vals else None,
                      "agreement_iqr": (round(_iqr(vals), 2) if len(vals) >= 2 else None)}
        json.dump(p, open(_d("judged", "%s__%s__%s__%s.json" % (
            p["seat"], p["variant"], p["model"], p["case"])), "w"), indent=1)
    print("judged -> %s" % _d("judged"))
    return produced


def _iqr(vals):
    s = sorted(vals)
    n = len(s)
    q1 = statistics.median(s[:n // 2])
    q3 = statistics.median(s[(n + 1) // 2:])
    return q3 - q1


# ============================================================ report ===========
def report(run_dir=None):
    jdir = os.path.join(run_dir or OUTDIR, "judged")
    pdir = os.path.join(run_dir or OUTDIR, "produced")
    src = jdir if os.path.isdir(jdir) and os.listdir(jdir) else pdir
    recs = [json.load(open(os.path.join(src, f))) for f in sorted(os.listdir(src)) if f.endswith(".json")]
    if not recs:
        print("no results in %s" % src)
        return
    # aggregate per (seat, variant, model) across cases
    agg = {}
    for r in recs:
        k = (r["seat"], r["variant"], r["model"])
        a = agg.setdefault(k, {"corr": [], "schema": [], "lat": [], "scribe": 0, "judge": [], "n": 0})
        a["corr"].append(r["score"]["correctness"])
        a["schema"].append(1.0 if r["score"]["schema_ok"] else 0.0)
        a["lat"].append(r["latency_s"])
        a["scribe"] += 1 if r.get("scribe_used") else 0
        a["n"] += 1
        jm = (r.get("judge") or {}).get("median")
        if jm is not None:
            a["judge"].append(jm)
    seats = sorted({k[0] for k in agg})
    lines = ["# Seat bake-off results\n",
             "Objective metrics are the PRIMARY decider; the judge median is the secondary quality "
             "signal (defer to objective when judge agreement is low / IQR high).\n"]
    for seat in seats:
        lines.append("\n## Seat %s\n" % seat)
        lines.append("| variant | model | schema%% | correctness | scribe | latency s | judge med |")
        lines.append("|---|---|---|---|---|---|---|")
        rows = sorted([(k, v) for k, v in agg.items() if k[0] == seat],
                      key=lambda kv: (-_mean(kv[1]["corr"]), _mean(kv[1]["lat"])))
        for (s, var, mdl), v in rows:
            jm = _mean(v["judge"]) if v["judge"] else None
            lines.append("| %s | %s | %d%% | %.2f | %d/%d | %.0f | %s |" % (
                var, mdl, round(100 * _mean(v["schema"])), _mean(v["corr"]),
                v["scribe"], v["n"], _mean(v["lat"]),
                ("%.1f" % jm) if jm is not None else "-"))
        # best variant per model + generalize vs overfit
        lines.append("\n**Per-model best variant (by correctness):**")
        models = sorted({k[2] for k in agg if k[0] == seat})
        for mdl in models:
            mr = [(var, _mean(v["corr"])) for (s, var, m2), v in agg.items()
                  if s == seat and m2 == mdl]
            if mr:
                best = max(mr, key=lambda x: x[1])
                lines.append("- %s: **%s** (%.2f)" % (mdl, best[0], best[1]))
        # which variant GENERALIZES (best mean across models) vs is overfit (high variance across models)
        lines.append("\n**Variant generalization (mean correctness across models / spread):**")
        for var in sorted({k[1] for k in agg if k[0] == seat}):
            per = [_mean(v["corr"]) for (s, vv, m2), v in agg.items() if s == seat and vv == var]
            if per:
                spread = round(max(per) - min(per), 2)
                lines.append("- %s: mean %.2f, spread %.2f %s" % (
                    var, _mean(per), spread, "(OVERFIT-prone)" if spread >= 0.34 else "(generalizes)"))
    out = "\n".join(lines)
    dst = _d("report.md")
    open(dst, "w").write(out)
    print(out)
    print("\nwrote %s" % dst)


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


# ============================================================ show / CLI =======
def show(tag="", model=None, seat=None):
    path = _d("transcript%s.jsonl" % tag)
    if not os.path.exists(path):
        print("no transcript at %s" % path)
        return
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "run_start" in r:
            print("\n##### run %s phase=%s" % (r["run_start"], r.get("phase")))
            continue
        if model and model != r.get("model"):
            continue
        if seat and seat != r.get("seat"):
            continue
        hdr = "%s | %s/%s/%s/%s | %ss%s" % (r.get("model"), r.get("seat"), r.get("variant"),
                                            r.get("case"), r.get("item"), r.get("secs"),
                                            " | SCRIBE" if r.get("scribe") else
                                            (" | ERR" if r.get("error") else ""))
        print("\n" + "=" * 90 + "\n" + hdr + "\n" + "=" * 90)
        if r.get("error"):
            print("ERROR:", r["error"])
        if r.get("reasoning"):
            print("--- REASONING ---\n" + r["reasoning"][:4000])
        print("--- SAID ---\n" + (r.get("content") or "(empty)")[:3000])


def main():
    ap = argparse.ArgumentParser(description="CEC 2-D {variant x model} seat bake-off")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("produce", help="run (seat,variant,model,case) generations via broker + cloud CLI")
    pp.add_argument("--seats", default="t1,t4,t5")
    pp.add_argument("--variants", default="current,terse,decision-tree")
    pp.add_argument("--models", default=",".join(PRODUCERS))
    pp.add_argument("--cases", default=",".join(CASES))
    pp.add_argument("--tag", default="")
    jp = sub.add_parser("judge", help="leave-one-out blind quality panel over the produced outputs")
    jp.add_argument("--judges", default=",".join(JUDGES))
    jp.add_argument("--tag", default="")
    jp.add_argument("--run-dir", default=None)
    rp = sub.add_parser("report", help="variant x model matrix + best-per-model + generalize/overfit")
    rp.add_argument("--run-dir", default=None)
    sp = sub.add_parser("show", help="print the call transcript")
    sp.add_argument("--tag", default="")
    sp.add_argument("--model", default=None)
    sp.add_argument("--seat", default=None)
    a = ap.parse_args()
    if a.cmd == "produce":
        produce([s for s in a.seats.split(",") if s], [v for v in a.variants.split(",") if v],
                [m for m in a.models.split(",") if m], [c for c in a.cases.split(",") if c], tag=a.tag)
    elif a.cmd == "judge":
        judge(tag=a.tag, judges=[j for j in a.judges.split(",") if j], run_dir=a.run_dir)
    elif a.cmd == "report":
        report(run_dir=a.run_dir)
    elif a.cmd == "show":
        show(a.tag, a.model, a.seat)


if __name__ == "__main__":
    main()
