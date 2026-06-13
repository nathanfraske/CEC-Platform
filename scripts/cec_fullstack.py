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
#   T5   AUDITOR (default DeepSeek-V4-Flash via broker; Sonnet one env var away)
#        proposes at most one penalty + one rule, under:
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
#   T6   VISION JUDGE (cec-worker-vision = the unified text+vision seat) on each
#        NEW Pareto finalist render (v2 facts-alongside protocol; structure/text only).
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
# OWNED LEVERS -- the corrected actuation-space owned-list (retrospective §2/§4, lesson 2).
# Single source of truth: fed to the auditor prompt AND the verifier actuation-space ctx so
# the generator and the gate share one definition of "a lever the loop can pull". A scorer-
# metric REWEIGHT is NOT in this set -- it only reorders the existing candidate population
# (lesson 4: selection cannot create candidates).
OWNED_LEVERS = ("router passes/opt_time, FR-02 waypoint intents (incl. routing an OFFENDING "
                "foreign signal net AROUND a sense corridor), bake_hints keepouts, GR-02 repair "
                "battery (shift/swap/via), power pours")
# UNIFIED SEAT MODEL (2026-06-11): cec-worker-vision is the cec-worker GGUF (Qwen3.6-35B-A3B) + an
# mmproj, so ONE resident 27 GB backend serves BOTH the text seats (T1/T4/verifier, thinking) AND
# the vision seat (T6, nothink via cec_vlm_bakeoff._NOTHINK). Pointing every local seat at it deletes
# the per-round worker<->vision swap; text quality == cec-worker by construction (same base), and it
# passed the CL-22 vision bakeoff 2/2. cec-vision-judge (Qwen3-VL-32B) leaves the hot path. The seat
# binding is owner-gated (cec-policy.json); these env knobs let it be split/reverted without a code edit.
WORKER_SEAT = os.environ.get("CEC_FS_WORKER_MODEL", "cec-worker-vision")
VISION_SEAT = os.environ.get("CEC_FS_VISION_MODEL", "cec-worker-vision")
# VISION GATING (owner 2026-06-13): the per-round VLM narrate produced only advisory anomaly flags
# (owner-ruled non-authoritative; geometry is owned by the deterministic checkers, CL-21) at real RAM/
# GPU/latency cost. So the VLM now fires ONLY on FINALISTS (the existing finalist path runs vision_judge);
# every round still gets the DETERMINISTIC pour-integrity facts (which feed the blocking gate + the item4
# corridor-avoid lever). Set CEC_FS_VISION_EVERY_ROUND=1 to restore per-round narration.
VISION_EVERY_ROUND = os.environ.get("CEC_FS_VISION_EVERY_ROUND", "0") == "1"
# Frozen known-good model-free copper render per board, for the deterministic render-diff the VLM
# NARRATES (owner ruling 2026-06-11). Render-diff is a REGRESSION tool -- it only has meaning for a
# board that IS known-good and is being REPROCESSED (toolchain/library/re-pour); diffing an
# in-development board (e.g. eps-8pin mid-routing-loop) against an arbitrary baseline measures drift,
# not defects. So this map holds ONLY genuinely-known-good boards (graduated-out-of-DRAFT / fab
# snapshots); a board absent here (the iterative loop case) runs the narration ANOMALY-ONLY, and its
# deterministic detection is the absolute DFM layer (cec_dfm_check) + the pour-integrity gate, which
# need no reference. No entry yet: the graduated boards (hub-standard / 12vhpwr-standard) get a frozen
# reference render when their regression check is wired; eps-8pin is mid-development -> intentionally absent.
VISION_REFERENCE = {}

# T5 AUDITOR SEAT (owner 2026-06-12): the deep local DeepSeek-V4-Flash (via the broker) is the DEFAULT
# auditor chair -- its deep rumination is the better auditor (it surfaced a planted spec inconsistency
# Sonnet/oss-120b omitted). Cloud Sonnet is ONE ENV VAR AWAY (CEC_FS_AUDITOR_MODEL=sonnet) for a
# latency-sensitive DAILY run. Resolution: explicit --auditor > CEC_FS_AUDITOR_MODEL env > V4-Flash default.
SONNET_AUDITOR = "sonnet"
# Cloud (claude-CLI) auditor seats vs the deep broker auditor: a model in CLOUD_AUDITORS routes to the
# claude CLI with --model <name> (+ --effort), anything else -> the broker (deepseek-v4-flash etc.).
# CEC_FS_AUDIT_EFFORT sets the CLI effort level (low|medium|high|xhigh|max) for the cloud auditor.
CLOUD_AUDITORS = {"sonnet", "opus"}
CLOUD_AUDIT_EFFORT = os.environ.get("CEC_FS_AUDIT_EFFORT")
DEEP_AUDITOR = os.environ.get("CEC_FS_DEEP_AUDITOR", "deepseek-v4-flash")
# DEEP-AUDITOR ENDPOINT (owner 2026-06-12): V4-Flash (~160 GB) cannot run under the WSL broker -- it pages
# at the 125 GB WSL2 ceiling (a live replay 502'd after 330 s). It runs via the WINDOWS-HOSTED workaround
# (full 192 GB physical, no WSL cap). Point ONLY the deep auditor there with CEC_FS_AUDITOR_URL=<win
# endpoint>/v1; the worker seats stay on the WSL broker. None -> _chat_json's default (the broker).
DEEP_AUDITOR_URL = os.environ.get("CEC_FS_AUDITOR_URL") or None


def resolve_auditor(cli_auditor, hours=None):
    # hours kept for signature/back-compat; the seat no longer keys on run length -- V4-Flash is the
    # default chair, Sonnet the explicit opt-in (the latency escape hatch).
    return cli_auditor or os.environ.get("CEC_FS_AUDITOR_MODEL") or DEEP_AUDITOR


# The auditor output contract (mirrors the inline Sonnet JSON template). The broker path enforces it as a
# json_schema grammar; the Sonnet path asks for the same shape via the Write tool.
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
        "manager_rule": {"type": ["string", "null"]},
    },
    "required": ["verdict", "root_cause", "reasoning", "failure_class",
                 "proposed_lever", "scorer_penalty", "manager_rule"],
    "additionalProperties": False,
}

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


def _corpus_state(lr):
    """EI-01: knowledge-state pin for the measurement row (fail-safe to {} so a row always writes)."""
    try:
        import cec_ledger
        return cec_ledger.corpus_state(lr)
    except Exception:                                          # noqa: BLE001
        return {}


def _vision_required_unmet(pourcheck, geom_delta, threshold=3):
    """True only when the VLM was ATTEMPTED (not finalist-gated) yet produced no anomalies despite a
    pour-geometry shift >= threshold -- i.e. the vision seat was genuinely needed but DOWN. A gated round
    (run_vlm=False -> vlm_gated) is an intentional skip, never flagged as a seat outage."""
    vlm_attempted = not pourcheck.get("vlm_gated")
    vision_ran = "anomalies" in pourcheck
    return bool(vlm_attempted and geom_delta >= threshold and not vision_ran)


# ---- promoted-corpus brief: ratified knowledge for the manager panel + auditor (owner 2026-06-13) ----
# Owner directive: wire the T1 intent-manager + T4 worker-panel AND the T5 auditor to the PROMOTED
# corpus, so every model seat reasons against the same owner-signed knowledge the compiler/reviewer
# already use. PROMOTED ZONE ONLY (corpus/promoted/general) -- staging is excluded by construction, so
# an unratified draft can never steer a seat. Family-scoped + platform-wide entries; fail-safe to "".
CORPUS_BRIEF = ""                          # set once per run() from promoted_corpus_brief(board)
_CORPUS_BRIEF_CACHE = {}


def promoted_corpus_brief(board, max_chars=13000):
    """The WHOLE promoted corpus (owner 2026-06-13: 'the whole promoted corpus is added'). Every entry
    in corpus/promoted/general is included; an entry scoped to OTHER families is kept but tagged with its
    scope so the seat applies it with judgement (this-family entries carry no tag). Staging is excluded by
    construction. Fail-safe to ''."""
    if board in _CORPUS_BRIEF_CACHE:
        return _CORPUS_BRIEF_CACHE[board]
    import glob as _g
    lines, n_total, n_in = [], 0, 0
    try:
        for fp in sorted(_g.glob(os.path.join(ROOT, "corpus", "promoted", "general", "*.json"))):
            try:
                entries = json.load(open(fp))
            except Exception:                                       # noqa: BLE001
                continue
            for e in (entries if isinstance(entries, list) else [entries]):
                if not isinstance(e, dict):
                    continue
                n_total += 1
                fams = ((e.get("scope") or {}).get("families")) or []
                in_family = (not fams) or (board in fams)
                if in_family:
                    n_in += 1
                scope_tag = "" if in_family else f" [scope: {','.join(fams)}]"
                val, unit = e.get("value"), e.get("units") or ""
                if val is None:
                    vs = ""
                elif isinstance(val, (dict, list)):                 # param value-dicts: compact summary
                    vj = json.dumps(val, separators=(",", ":"))
                    vs = " = " + (vj[:150] + "…" if len(vj) > 150 else vj)
                else:
                    vs = f" = {val}{(' ' + unit) if unit else ''}"
                note = (e.get("notes") or "").split(". ")[0][:150]
                line = f"- [{e.get('id','?')}] ({e.get('kind','rule')}){scope_tag}{vs}: {note}"
                lines.append(line[:240])
    except Exception:                                               # noqa: BLE001
        pass
    brief = ""
    if lines:
        body = "\n".join(lines)
        if len(body) > max_chars:
            body = body[:max_chars] + "\n- ...(brief truncated)"
        brief = (f"RATIFIED CORPUS (the WHOLE promoted/general corpus, {n_total} owner-signed entries; "
                 f"{n_in} in scope for this {board} family, the rest tagged with their family scope -- "
                 "treat as authoritative, do not contradict or re-derive):\n" + body + "\n\n")
    _CORPUS_BRIEF_CACHE[board] = brief
    return brief


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
        # F+B-mirror-AWARE component count (SB-08 item 2): F.Cu islands stitched through the via field +
        # THT pads count as ONE; the blocking gate prefers this over the raw F.Cu island count.
        "import cec_score\n"
        f"comp=cec_score.sense_pour_components('/workspace/{rel}')\n"
        "for nn in Z: Z[nn]['components']=comp.get(nn)\n"
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


def vision_pour_check(rec, rnd, run_vlm=True):
    """T6 RE-ROLED (owner ruling 2026-06-11): the VISION seat NO LONGER judges pour integrity --
    detection is deterministic (pour_facts islands + the BLOCKING pour_integrity gate + the
    render-diff). The seat now only NARRATES the deterministic render-diff regions and runs an
    open-ended ANOMALY pass. It is NEVER fed the numeric facts (it parrots them, CL-21) and emits a
    FLAG, never a verdict. The lever + gate read the deterministic facts/det_clipped ONLY;
    narration/anomalies are advisory (auditor context + log), re-checked by determinism.

    VISION GATING (owner 2026-06-13): with run_vlm=False the DETERMINISTIC facts (which own integrity and
    feed the gate + item4 lever) still compute every round, but the advisory VLM narrate is SKIPPED --
    the per-round VLM only produced non-authoritative anomaly flags at real RAM/GPU cost. The VLM now
    fires on finalists (the vision_judge path) / when CEC_FS_VISION_EVERY_ROUND=1."""
    facts = pour_facts(rec["routed"])                              # DETERMINISTIC -- owns integrity
    det_clipped = sorted(n for n, v in facts.items()
                         if isinstance(v, dict) and (v.get("islands", 1) or 1) > 1)
    log(f"  T6 POUR (deterministic): {json.dumps(facts)}")
    base = {"facts": facts, "det_clipped_nets": det_clipped, "role": "narration+anomaly"}
    if not run_vlm:                                                # VISION-GATED: deterministic-only round
        base["vlm_gated"] = "non-finalist"
        return base
    png = _d("vision", f"pour-r{rnd}.png")
    # RENDER-HYGIENE PRECONDITION: the VLM is fed ONLY a model-free copper render -- never the 3D-body
    # render (kicad-cli rotated-footprint artifact -> false findings). No clean render -> SKIP.
    if not render_copper_zone(rec["routed"], png):
        log("  T6 NARRATE: VLM SKIPPED -- render_hygiene_pending (no model-free render)")
        base["skipped"] = "render_hygiene_pending"
        return base
    if not warm(VISION_SEAT):
        base["skipped"] = "vision seat down"
        return base
    # DETERMINISTIC detection layer the VLM narrates: render-diff vs a frozen known-good reference
    # (if one exists + image deps present). Absent -> anomaly-only narration.
    diff_regions = None
    ref = VISION_REFERENCE.get(rec.get("board", "eps-8pin"))
    try:
        import cec_render_diff as rdf
        if ref and os.path.exists(ref) and rdf._DEPS:
            d = rdf.render_diff(png, ref)
            diff_regions = d["regions"]
            base["diff_regions"] = diff_regions
            log(f"  T6 render-diff vs reference: {d['n_regions']} region(s)")
    except Exception as e:                                         # noqa: BLE001
        log(f"  T6 render-diff skipped: {type(e).__name__}: {e}")
    try:
        import cec_vision_narrate as vn
        out = vn.narrate(png, diff_regions, model=VISION_SEAT, max_tokens=700, timeout=SEAT_TIMEOUT,
                         ctx={"round": rnd, "check": "pour-narration"})
        base.update({"region_narration": out.get("region_narration", []),
                     "anomalies": out.get("anomalies", []), "note": out.get("note", "")})
        log(f"  T6 NARRATE: {len(base['region_narration'])} region note(s), "
            f"{len(base['anomalies'])} anomaly flag(s)"
            + (f" -- ANOMALIES: {base['anomalies']}" if base["anomalies"] else ""))
    except Exception as e:                                         # noqa: BLE001
        log(f"  T6 NARRATE vision error: {type(e).__name__}: {e}")
        base["error"] = f"{type(e).__name__}: {e}"
    return base


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
    """kicad-cli 3D render in-container -> host path under PERM. NOTE: this is the 3D-body raytrace
    render and carries the kicad-cli rotated-footprint artifact (false rotations/offsets absent in
    the GUI) -- it MUST NOT be fed to the VISION seat (see render_copper_zone + review item 3)."""
    rel_in = os.path.relpath(os.path.abspath(routed_host_path), ROOT)
    rel_out = os.path.relpath(os.path.abspath(out_png), ROOT)
    try:
        subprocess.run(ovd.COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "render",
                                      "-o", f"/workspace/{rel_out}", f"/workspace/{rel_in}"],
                       capture_output=True, text=True, timeout=300)
        return os.path.exists(out_png)
    except Exception:                                            # noqa: BLE001
        return False


def render_copper_zone(routed_host_path, out_png):
    """MODEL-FREE render for the VISION seat (review item 3 / render hygiene). Exports ONLY the
    copper + edge layers (no 3D bodies, no silk/fab) via kicad-cli SVG, then rasterizes to PNG, so
    the VLM reads copper + zone GEOMETRY and never the rotated-footprint 3D artifact. Returns True
    ONLY if a clean PNG was produced; False => the caller MUST skip the VLM with
    render_hygiene_pending. This is the precondition the code cannot violate: no model-free render,
    no VLM. (Rasterizer: rsvg-convert or ImageMagick `convert` in the routing container.)"""
    rel_in = os.path.relpath(os.path.abspath(routed_host_path), ROOT)
    svg = out_png.rsplit(".", 1)[0] + "-copper.svg"
    rel_svg = os.path.relpath(os.path.abspath(svg), ROOT)
    rel_out = os.path.relpath(os.path.abspath(out_png), ROOT)
    try:
        if os.path.exists(out_png):
            os.remove(out_png)                       # never fall back to a stale 3D render
        subprocess.run(ovd.COMPOSE + ["exec", "-T", "routing", "kicad-cli", "pcb", "export", "svg",
                                      "--layers", "F.Cu,B.Cu,Edge.Cuts", "--exclude-drawing-sheet",
                                      "--page-size-mode", "2",
                                      "-o", f"/workspace/{rel_svg}", f"/workspace/{rel_in}"],
                       capture_output=True, text=True, timeout=180)
        if not os.path.exists(svg):
            return False
        subprocess.run(ovd.COMPOSE + ["exec", "-T", "routing", "sh", "-c",
                                      f"rsvg-convert -o /workspace/{rel_out} /workspace/{rel_svg} "
                                      f"|| convert /workspace/{rel_svg} /workspace/{rel_out}"],
                       capture_output=True, text=True, timeout=120)
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
        out = jl._chat_json("You write routing intents as strict JSON.", CORPUS_BRIEF + user, INTENTS_SCHEMA,
                            name="intents", temperature=0.2, max_tokens=900, seat="manager:intent",
                            model=WORKER_SEAT, timeout=SEAT_TIMEOUT)
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
                    CORPUS_BRIEF + f"Round {rnd} candidate metrics: {json.dumps(m)}\n"
                    f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}",
                    PANEL_SCHEMA, name="panel", temperature=0.0 if i < 2 else 0.3,
                    seat="panel:" + lens.split()[0], max_tokens=300, model=WORKER_SEAT, timeout=SEAT_TIMEOUT)
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


# ---- T5: the in-loop auditor (Sonnet daily / DeepSeek overnight) -------------------------------------
def _audit_prompt(rec, lr, rnd, pourcheck=None, intents_src="model"):
    """Build the shared auditor prompt CORE (role + constraints + round data + schema explanation),
    minus the per-backend output instruction. Returns (core_prompt, out_path)."""
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
        pour_line = (f"POUR-INTEGRITY (deterministic, OWNS detection): clipped_nets="
                     f"{pourcheck.get('det_clipped_nets')}, "
                     f"facts={json.dumps(pourcheck.get('facts', {}))[:400]}\n")
        anoms = pourcheck.get("anomalies")
        if anoms:       # advisory VLM flags -- re-check before acting, never authoritative
            pour_line += f"VISION ANOMALY FLAGS (advisory, re-check; not a verdict): {anoms}\n"
    # PRIOR REFUTES this run, threaded back in (lesson 6) so the auditor does not re-derive a
    # class the verifier already killed. Compact: kind+metric/rule-head+reason-class.
    prior_refutes = [{"kind": e.get("kind"), "metric": e.get("metric"),
                      "rule": (e.get("rule") or "")[:60]}
                     for e in lr.get("rejections", [])[-8:]
                     if "refuted" in e.get("action", "") or "tripwire" in e.get("action", "")]
    refuted_metrics = sorted(set(lr.get("refuted_metrics", [])))
    prompt = (
        "You are the IN-LOOP AUDITOR for the CEC routing pipeline (full-stack run). Constraints "
        "you operate under, learned from the last run converging to a local minimum:\n"
        f"- ALLOWED LEVERS (the ONLY things the loop can pull): {OWNED_LEVERS}.\n"
        "- A SCORER-METRIC REWEIGHT IS NOT A LEVER. It only reorders the candidates that already "
        "exist; it cannot create a better board. If the real fix needs generation (a different "
        "route / placement / keepout / waypoint), name THAT lever in `proposed_lever` and leave "
        "`scorer_penalty` null. Only price a metric when a gate-passing candidate ALREADY exists "
        "and pricing is needed to rank it first.\n"
        f"- DO NOT RE-PROPOSE A REFUTED CLASS: scorer reweights on {refuted_metrics or '[]'} have "
        "already been refuted this run and will be auto-rejected by a deterministic tripwire. "
        "Switch lever class instead.\n"
        f"- RULE CAP: at most {RULE_CAP} standing manager rules. Currently {len(lr['manager_rules'])}. "
        "At the cap propose only a CONSOLIDATION or nothing.\n"
        "- ACTUATION: a placement/structural-density blockage must be attributed "
        "failure_class=placement, NOT priced.\n"
        "- NOVELTY: a rephrase of an existing rule is rejected by a deterministic gate.\n\n"
        f"ROUND {rnd} candidate:\n{json.dumps(metrics, indent=1)}\n"
        # GENERATION SOURCE (review item 5): a fallback round ran on crude fixed-offset waypoints,
        # not the model's intents -- a degraded GENERATION, its own hazard class. The auditor must
        # judge such a board as fallback-generated, NOT mistake a worse board for a scorer/rule issue.
        + (f"GENERATION SOURCE: intents_src={intents_src}"
           + (" -- THIS ROUND RAN ON FALLBACK INTENTS (degraded generation: crude fixed-offset "
              "waypoints, not the model's plan). A worse board here may be the fallback, not a "
              "scorer/rule problem -- prefer failure_class=routing/placement over a penalty.\n"
              if intents_src == "fallback" else "\n"))
        + f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
        f"FEM flags: {json.dumps(rec.get('fem_flags', [])[:4])}\n"
        f"{pour_line}"
        f"stub summary: {json.dumps(rec.get('stub_summary', {}))}\n\n"
        f"Current injected penalties: {json.dumps(lr['scorer_penalties'])}\n"
        f"Standing rules ({len(lr['manager_rules'])}): {json.dumps(lr['manager_rules'][-6:])}\n"
        f"Prior refutes this run (do not repeat the class): {json.dumps(prior_refutes)}\n"
        f"Penalisable keys: {list(PENALISABLE)}\n\n"
        "SCHEMA -- `root_cause` is your bankable diagnosis (ALWAYS fill it; it is kept even if the "
        "lever is refused). `proposed_lever` is VERIFIER-CONTEXT-ONLY today: it is recorded and the "
        "verifier judges its actuation-space, but it has NO direct effector -- the corridor-avoidance "
        "lever fires DETERMINISTICALLY from pour_clipped_nets, not from this field. `scorer_penalty` "
        "is for ranking only and must be null unless a gate-passing candidate already exists.\n")
    return prompt, out_path


_AUDIT_JSON_TEMPLATE = (
    '{"verdict":"accept|repair|escalate","root_cause":"<diagnosis, always filled>",'
    '"reasoning":"...","failure_class":"routing|placement|scoring|constraint|none",'
    '"proposed_lever":{"lever":"<one of the ALLOWED LEVERS>","target":"<net/ref/region>",'
    '"detail":"..."}|null,'
    '"scorer_penalty":{"metric":"...","weight":<number>,"rationale":"..."}|null,'
    '"manager_rule":"..."|null}')


def sonnet_audit(rec, lr, rnd, timeout=240, pourcheck=None, intents_src="model",
                 model="sonnet", effort=None):
    """Cloud claude-CLI auditor (DAILY / latency). Spawns `claude -p --model <model> [--effort <lvl>]`,
    Write-tool -> out_path. model defaults to sonnet; pass model='opus' + effort='max' for a deep cloud
    auditor test. (Kept the historical name; routes any CLOUD_AUDITORS member.)"""
    core, out_path = _audit_prompt(rec, lr, rnd, pourcheck, intents_src)
    prompt = (core + f"Use the Write tool to write ONLY this JSON to {out_path} :\n"
              + _AUDIT_JSON_TEMPLATE + "\nThen reply DONE.")
    cmd = ["claude", "-p", "--model", model]
    if effort:
        cmd += ["--effort", effort]
    cmd += ["--allowedTools", "Write", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages"]
    log(f"  T5 cloud auditor: {model}" + (f" effort={effort}" if effort else ""))
    try:
        with open(_d("findings", f"round-{rnd:03d}-sonnet.stream.jsonl"), "w") as sfh:
            subprocess.run(cmd, input=prompt, text=True, stdout=sfh, stderr=subprocess.DEVNULL,
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


def deepseek_audit(rec, lr, rnd, model=None, timeout=900, pourcheck=None, intents_src="model"):
    """Deep LOCAL auditor (OVERNIGHT / throughput) via the broker -- DeepSeek-V4-Flash by default. Uses
    cec_judge_local._chat_json (json_schema grammar + miner->scribe recovery for the deep reasoner), so
    no `claude` CLI / no Write tool. Writes the SAME out_path the Sonnet path does, for artifact parity."""
    import cec_judge_local as jl
    model = model or DEEP_AUDITOR
    core, out_path = _audit_prompt(rec, lr, rnd, pourcheck, intents_src)
    system = ("You are the IN-LOOP AUDITOR for the CEC routing pipeline. Read the round context and emit "
              "ONLY the JSON object the schema defines -- root_cause ALWAYS filled; scorer_penalty null "
              "unless a gate-passing candidate already exists.")
    try:
        out = jl._chat_json(system, CORPUS_BRIEF + core, AUDIT_SCHEMA, name="audit", temperature=0.0,
                            max_tokens=jl.MANAGER_MAX_TOKENS, timeout=timeout, model=model,
                            url=DEEP_AUDITOR_URL)            # Windows-hosted V4 endpoint if set, else broker
    except Exception as e:                                       # noqa: BLE001
        return {"verdict": "repair", "error": f"deepseek_audit: {type(e).__name__}: {e}"}
    if not isinstance(out, dict) or "verdict" not in out:
        return {"verdict": "repair", "error": "deepseek_audit: no verdict"}
    try:
        with open(out_path, "w") as fh:
            json.dump(out, fh, indent=1)
    except Exception:                                            # noqa: BLE001
        pass
    return out


def audit(rec, lr, rnd, model, *, timeout=None, pourcheck=None, intents_src="model"):
    """Dispatch the T5 auditor by seat model (resolve_auditor() picks it once per run):
    a CLOUD_AUDITORS member ('sonnet'/'opus') -> cloud claude CLI; anything else -> the deep broker
    auditor (overnight). Opus gets a longer default timeout (deep effort runs slower)."""
    if model in CLOUD_AUDITORS:
        return sonnet_audit(rec, lr, rnd, timeout=timeout or (900 if model == "opus" else 240),
                            pourcheck=pourcheck, intents_src=intents_src,
                            model=model, effort=CLOUD_AUDIT_EFFORT)
    return deepseek_audit(rec, lr, rnd, model=model, timeout=timeout or 900,
                          pourcheck=pourcheck, intents_src=intents_src)


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


# Fact classes the auditor may cite -> the evidence-bundle key that must carry them. The
# citable set and the bundle set are ONE contract (lesson 9/10): if the auditor cites a class
# the bundle lacks, the provenance seat refutes a TRUE fact. bundle_gaps() is the contract check.
_FACT_CLASSES = {"island": "pour_facts", "foreign_cross": "pour_facts",
                 "foreign cross": "pour_facts", "copper": "pour_facts", "pour": "pour_facts",
                 "fem": "fem_flags", "thermal": "fem_flags", "over-temp": "fem_flags",
                 "max_t": "max_T"}


def bundle_gaps(finding, evidence):
    """Which fact classes the finding cites that the evidence bundle does not carry (empty/absent).
    Empty list = the bundle is complete for what the auditor said."""
    text = json.dumps(finding).lower()
    gaps = set()
    for kw, key in _FACT_CLASSES.items():
        if kw in text and not evidence.get(key):
            gaps.add(key)
    return sorted(gaps)


def inject(finding, lr, rnd, source, verifier_final):
    """Additive-only injection with rule cap + novelty + verifier gate. Every
    accepted item -> DF-01 ratification candidate (never auto-promoted)."""
    events = []
    # BANK THE DIAGNOSIS (lesson 3): root_cause persists even when the lever is refused, so a
    # good causal trace is not discarded with a bad fix. Deduped by normalized text.
    rc = (finding.get("root_cause") or "").strip()
    if rc and len(rc) >= 12:
        seen = {_norm_text(d["root_cause"]) for d in lr.setdefault("diagnoses", [])}
        if _norm_text(rc) not in seen:
            lr["diagnoses"].append({"round": rnd, "source": source, "root_cause": rc[:400]})
    sp = finding.get("scorer_penalty")
    if isinstance(sp, dict) and sp.get("metric") in PENALISABLE:
        metric, ok = sp["metric"], True
        try:
            w = float(sp.get("weight"))
        except (TypeError, ValueError):
            w, ok = None, False
        if metric in lr.setdefault("refuted_metrics", []):
            # KNOB TRIPWIRE (lesson 5): a scorer-metric reweight already refuted this run --
            # cycling or rising -- is auto-rejected with no verifier spend. Forces a lever change.
            events.append({"kind": "penalty", "metric": metric,
                           "action": "rejected:knob_tripwire"})
        elif verifier_final == "refute":
            lr["refuted_metrics"].append(metric)
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
                                  live_rules=lr,            # EI-01: pin the INJECTION boundary itself
                                  verdict=f"ratification-candidate {e['kind']}", extra=e)
            except Exception:                                    # noqa: BLE001
                pass
    return events


# ---- T6/T7: finalist events ---------------------------------------------------------------------------
def vision_judge(routed, rec, rnd):
    """v2 facts-alongside protocol: facts ride with the render; structure/text only."""
    png = _d("vision", f"finalist-r{rnd}.png")
    # RENDER-HYGIENE PRECONDITION (PR #36 item 3): the finalist judge gets the SAME treatment as the
    # pour check -- a model-free copper/zone render only, never the 3D-body artifact. No clean render
    # -> skip with render_hygiene_pending. (Structure/text review still benefits: the rotated-footprint
    # silk is exactly the "structural oddity" that would false-fire this seat.)
    if not render_copper_zone(routed, png):
        log("  T6 FINALIST JUDGE SKIPPED -- render_hygiene_pending (no model-free render)")
        return {"skipped": "render_hygiene_pending"}
    facts = {k: rec.get(k) for k in ("kelvin_ok", "diffpair_ok", "drc", "unconnected",
                                     "plane_signal_mm", "max_T")}
    text = ("FACTS (deterministic, trust these over visual estimates -- you judge STRUCTURE "
            "and TEXT only, never geometry): %s\nThis is a routed CEC eps-8pin interposer "
            "candidate. Report: (1) any structural oddity (component text/refs, missing/odd "
            "regions, obvious copper anomalies); (2) whether the visible structure is consistent "
            "with the facts. 3 bullets max." % json.dumps(facts))
    try:
        import cec_vlm_bakeoff as vb
        out = vb._chat(VISION_SEAT, text, png, max_tokens=500, timeout=600)
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
def run(board, rounds, hours, auditor=None):
    os.makedirs(PERM, exist_ok=True)
    deadline = time.time() + hours * 3600.0 if hours else None
    auditor_model = resolve_auditor(auditor, hours)            # default DeepSeek-V4-Flash; Sonnet via env
    global CORPUS_BRIEF                                          # owner 2026-06-13: brief T1/T4/T5 with promoted corpus
    CORPUS_BRIEF = promoted_corpus_brief(board)
    n_brief = CORPUS_BRIEF.count("\n- ") if CORPUS_BRIEF else 0
    log(f"promoted-corpus brief: {n_brief} ratified entrie(s) in scope for {board} -> T1 intent / T4 panel / T5 auditor")
    lr = {"scorer_penalties": {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0},
          "manager_rules": [], "injections": [], "rejections": [],
          "diagnoses": [], "refuted_metrics": []}
    vs = cec_verifier.VerifierSession(model=WORKER_SEAT)
    log(f"FULL-STACK: board={board} rounds={rounds or '∞'} hours={hours or '-'} "
        f"auditor={auditor_model} v4_every={V4_EVERY} verifier_budget={vs.budget} rule_cap={RULE_CAP}")
    subprocess.run(ovd.COMPOSE + ["up", "-d", "routing"], capture_output=True, timeout=180)
    # WARM-AT-START (owner 2026-06-12): a deep BROKER auditor (V4-Flash ~7 min cold load) is warmed up
    # front so the FIRST round's auditor call never loses its own race. Sonnet (claude CLI) needs no
    # warming; a Windows-hosted auditor (CEC_FS_AUDITOR_URL set) keeps its own residency, so the broker-
    # warm is skipped there. Fail-safe: a warm miss just means the first call eats the cold load.
    if auditor_model not in CLOUD_AUDITORS and not DEEP_AUDITOR_URL:
        log(f"warming auditor seat {auditor_model} at start (deep cold load)...")
        try:
            warm(auditor_model, timeout=WARM_TIMEOUT)
        except Exception as e:                                  # noqa: BLE001
            log(f"  auditor warm miss ({type(e).__name__}); first call will cold-load")
    elif DEEP_AUDITOR_URL:
        log(f"auditor seat {auditor_model} on Windows endpoint {DEEP_AUDITOR_URL} (broker-warm skipped)")

    grid = congestion_grid(board)
    log(f"GR-01 grid: {len(grid.get('hotspots', []))} hotspots, "
        f"contested={[c if isinstance(c, str) else c.get('net') for c in grid.get('contested', [])][:6]}")
    json.dump(grid, open(_d("gr01-grid.json"), "w"), indent=1)

    records, intents, rnd = [], ovd.INTENTS[board], 0
    passes, opt_time, kelvin_stall, finalists_seen = 24, 40, 0, set()
    batch_for_v4 = []
    prev_pour_sig = None              # (sum islands, sum foreign_cross) -- pour-geometry delta guard
    pending_corridor_avoid = []       # item 4: offending-net avoid-intents carried to the next round
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
            warm(WORKER_SEAT)
            # T1 intent manager
            last = records[-1] if records else None
            intents, why, src = intent_manager(board, grid, intents, last, rnd)
            # Item 4 lever: carry last round's OFFENDING-net corridor-avoidance intents in, so the
            # foreign signal nets that clipped the pours route AROUND the corridor THIS round (the
            # untried lever -- r3 only waypointed the victim Kelvin nets).
            if pending_corridor_avoid:
                have = {i["net"] for i in intents}
                intents = intents + [i for i in pending_corridor_avoid if i["net"] not in have]
                log(f"  T1 + corridor-avoid (offending): "
                    f"{[i['net'] for i in pending_corridor_avoid]}")
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

            # T6 POUR-INTEGRITY check -- deterministic facts EVERY round (owner: pours are getting clipped;
            # state and RE-STATE it). The advisory VLM narrate is GATED to finalists (owner 2026-06-13);
            # CEC_FS_VISION_EVERY_ROUND=1 restores per-round narration. Deterministic facts feed the gate
            # + the item4 corridor-avoid lever regardless.
            pourcheck = vision_pour_check(rec, rnd, run_vlm=VISION_EVERY_ROUND)
            json.dump(pourcheck, open(_d("vision", f"pour-r{rnd:03d}.json"), "w"),
                      indent=1, default=str)
            # DETERMINISTIC-ONLY (owner ruling 2026-06-11): the corridor-avoid lever + pour gate fire
            # from det_clipped_nets (pour_facts), NEVER the VLM -- the VLM only narrates/anomaly-flags.
            pour_clipped_nets = pourcheck.get("det_clipped_nets") or []

            # SCORER HOTFIX (retrospective lesson 7): re-rank with the pour-aware, gate-gated
            # objective. While gates fail, DRC earns NO credit and pour integrity (island excess +
            # sense-corridor copper) is the first-class differentiator -- so the loop cannot shave
            # DRC by fragmenting the pours. This becomes rec["objective"] for the frontier + best pick.
            import cec_score
            _pf = pourcheck.get("facts", {}) or {}
            islands_excess = sum(max(0, (v.get("islands", 1) or 1) - 1)
                                 for v in _pf.values() if isinstance(v, dict))
            sense_copper = sum((v.get("area_mm2", 0) or 0)
                               for v in _pf.values() if isinstance(v, dict))
            rec["islands_excess"] = islands_excess
            rec["sense_copper"] = round(sense_copper, 2)
            # BLOCKING pour-integrity gate (review item 2): kelvin_ok checks connectivity and is BLIND
            # to fragmentation (it passed the round-4 board at 3 islands). A sense pour split into >1
            # island fails the gate -> gates_pass forced False so the board can't be accepted/finalist.
            # Golden dry-run was CLEAN (tests/golden/pour-integrity-dryrun.json), so it merges here.
            pour_ok, pour_reasons = cec_score.pour_integrity_ok(_pf)
            rec["pour_integrity_ok"] = pour_ok
            if not pour_ok and rec.get("gates_pass"):
                log(f"  POUR-INTEGRITY GATE FAIL -> gates_pass forced False: {pour_reasons}")
                rec["gates_pass"] = False
                rec.setdefault("reasons", []).append("pour_integrity: " + "; ".join(pour_reasons))
            rec["objective_base"] = rec.get("objective", 0.0)
            rec["objective"] = round(cec_score.objective_v2(
                gates_pass=rec["gates_pass"], drc=rec["drc"], islands_excess=islands_excess,
                sense_copper=sense_copper, base=rec.get("objective", 0.0)), 2)

            # Item 4: if a sense corridor clipped, prepare OFFENDING-net avoidance intents for the
            # NEXT round -- route the contested SIGNAL nets (not sense, not power) around the clipped
            # corridor. Geometry from cec_fr02.clipped_corridor_rects (in-container; safe no-op host).
            pending_corridor_avoid = []
            if pour_clipped_nets:
                import cec_fr02
                corridors = cec_fr02.clipped_corridor_rects(rec["routed"], pour_clipped_nets)
                contested = [c if isinstance(c, str) else c.get("net")
                             for c in grid.get("contested", [])]
                offending = [n for n in contested if n and not cec_fr02.is_sense_net(n)
                             and not str(n).startswith(("GND", "+"))]
                pending_corridor_avoid = cec_fr02.offending_net_intents(corridors, offending)
                if pending_corridor_avoid:
                    log(f"  item4: next-round corridor-avoid for "
                        f"{[i['net'] for i in pending_corridor_avoid]} around {list(corridors)}")

            # T5 auditor (Sonnet daily / DeepSeek overnight; SEES the pour-clip) -> CL-24 verifier -> guarded injection
            sj = audit(rec, lr, rnd, auditor_model, pourcheck=pourcheck, intents_src=src)
            vres, events, miss, vt = None, [], [], None
            sp = sj.get("scorer_penalty") if isinstance(sj.get("scorer_penalty"), dict) else {}
            has_rule = bool(sj.get("manager_rule"))
            tripwired = sp.get("metric") in lr.get("refuted_metrics", [])
            if sp or has_rule:
                if tripwired and not has_rule:
                    # KNOB TRIPWIRE pre-check (lesson 5 + lesson 1): a refuted-metric reweight with
                    # nothing else to judge is auto-rejected with NO verifier spend.
                    events = inject(sj, lr, rnd, "sonnet", "tripwire")
                    vt = "tripwire"
                    # Review item 6: a tripwired round must NOT masquerade as a null verifier row --
                    # write a minimal stub so the verifier/ artifact + the measurement row say "tripwire".
                    json.dump({"round": rnd, "final": "tripwire", "verdict_type": "tripwire",
                               "note": "refuted-metric reweight auto-rejected; no verifier spend",
                               "scorer_penalty": sj.get("scorer_penalty"),
                               "root_cause": sj.get("root_cause")},
                              open(_d("verifier", f"round-{rnd:03d}.json"), "w"), indent=1, default=str)
                    log(f"  T5 TRIPWIRE: refuted metric '{sp.get('metric')}' re-proposed -> "
                        f"auto-reject, no verifier spend -> {[e['action'] for e in events]}")
                else:
                    warm(WORKER_SEAT)       # verifier seats are worker calls; vision swapped it out
                    # BUNDLE COMPLETENESS (lesson 9/10): the verifier's evidence bundle must carry
                    # every fact class the auditor was permitted to cite (pour facts, FEM, max_T) or
                    # the provenance seat refutes TRUE facts. Built from the SAME facts.
                    evidence = {k: rec.get(k) for k in ("drc", "kelvin_ok", "plane_signal_mm",
                                                        "unconnected", "max_T", "reasons")}
                    evidence["fem_flags"] = (rec.get("fem_flags") or [])[:6]
                    evidence["pour_facts"] = pourcheck.get("facts", {})
                    evidence["pour_clipped_nets"] = pour_clipped_nets
                    miss = bundle_gaps(sj, evidence)
                    if miss:
                        log(f"  ! bundle-completeness gap (auditor cited, bundle lacked): {miss}")
                    ctx = {"rules_excerpt": json.dumps(lr["manager_rules"]),
                           "evidence": json.dumps(evidence),
                           "levers": OWNED_LEVERS,
                           "metrics": json.dumps([{k: r.get(k) for k in ("round", "drc", "kelvin_ok")}
                                                  for r in records[-6:]])}
                    vres = vs.verify({"issue": sj.get("reasoning", "")[:600],
                                      "root_cause": sj.get("root_cause"),
                                      "scorer_penalty": sj.get("scorer_penalty"),
                                      # proposed_lever is verifier-context-only (review item 4): the
                                      # panel judges its actuation-space, but no effector reads it --
                                      # corridor-avoidance fires deterministically from pour_clipped_nets.
                                      "proposed_lever": sj.get("proposed_lever"),
                                      "manager_rule": sj.get("manager_rule")}, ctx)
                    vfinal = vres.final if vres else "uncertain"
                    vt = getattr(vres, "verdict_type", None)
                    json.dump({"round": rnd, "final": vfinal,
                               "verdict_type": getattr(vres, "verdict_type", None),
                               "live_seats": getattr(vres, "live_seats", None),
                               "dark_seats": getattr(vres, "dark_seats", None),
                               "contention": vres.contention if vres else None,
                               "verdicts": vres.verdicts if vres else None,
                               "arbiter": vres.arbiter if vres else None,
                               "bundle_gaps": miss},
                              open(_d("verifier", f"round-{rnd:03d}.json"), "w"), indent=1, default=str)
                    events = inject(sj, lr, rnd, "sonnet", vfinal)
                    log(f"  T5+CL24: auditor={sj.get('verdict')} fc={sj.get('failure_class')} "
                        f"verifier={vfinal}/{getattr(vres, 'verdict_type', '?')}"
                        f"{' CONTENTION' if vres and vres.contention else ''} "
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

            # VISION-REQUIRED guard (lesson 9): when pour geometry moves materially between rounds
            # but the vision seat did not run, the round's pour verdict rests on the deterministic
            # facts alone -- flag it so scoring credit / promotion treats it as unverified.
            _pf = pourcheck.get("facts", {}) or {}
            pour_sig = (sum((v.get("islands", 1) or 1) for v in _pf.values() if isinstance(v, dict)),
                        sum((v.get("foreign_cross", 0) or 0) for v in _pf.values() if isinstance(v, dict)))
            geom_delta = (abs(pour_sig[0] - prev_pour_sig[0]) + abs(pour_sig[1] - prev_pour_sig[1])
                          if prev_pour_sig else 0)
            vision_required_unmet = _vision_required_unmet(pourcheck, geom_delta)   # gated != seat-down
            if vision_required_unmet:
                log(f"  ! VISION-REQUIRED unmet: pour-geometry delta={geom_delta} but vision seat down")
            prev_pour_sig = pour_sig

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
                   "pour_integrity_ok": rec.get("pour_integrity_ok"),    # blocking gate (item 2)
                   # re-roled seat: narration/anomaly flags (advisory), not a verdict
                   "pour_vision": (pourcheck.get("anomalies") if "anomalies" in pourcheck
                                   else pourcheck.get("skipped") or pourcheck.get("error")),
                   "vision_required_unmet": vision_required_unmet,
                   "verdict_type": vt,                       # "tripwire" on a tripwired round (item 6)
                   "v4_risk": (v4 or {}).get("local_minimum_risk"),
                   "corpus_state": _corpus_state(lr)}        # EI-01: knowledge state at round time
            with open(_d("measurement.jsonl"), "a") as fh:
                fh.write(json.dumps(row) + "\n")
            json.dump(lr, open(_d("live-rules.json"), "w"), indent=1)
            ovd.ledger_round(board, rec, len(front), live_rules=lr)
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
              "corpus_state": _corpus_state(lr),        # EI-01: make the run deliverable self-describing
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
    ap.add_argument("--auditor", default=None,
                    help="T5 auditor seat model. Default: DeepSeek-V4-Flash (the deep chair). Sonnet is "
                         "one env var away (CEC_FS_AUDITOR_MODEL=sonnet) for a latency-sensitive run; "
                         "--auditor overrides both.")
    a = ap.parse_args(argv)
    if not a.rounds and not a.hours:
        a.rounds = 8
    run(a.board, a.rounds, a.hours, auditor=a.auditor)


if __name__ == "__main__":
    main()
