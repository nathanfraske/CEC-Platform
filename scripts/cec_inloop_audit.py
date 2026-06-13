#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_inloop_audit -- the IN-LOOP self-correcting audit experiment.
# ============================================================================
# Owner reframe (2026-06-11, full record docs/inloop-audit-2026-06-11/README.md):
# a deep auditor run BLIND re-derived the human-in-the-loop findings (signal carved
# through the GND plane; the scorer not pricing it). Run the auditor IN-LOOP, feed
# its findings back into the scorer + manager tiers MID-RUN, and MEASURE:
#   does the loop CONVERGE TO A LOCAL MINIMUM (injected penalties inflate while the
#   physical metrics -- kelvin_ok / plane_signal_mm / drc -- plateau, and one board
#   repeats), or PRODUCE USABLE CORPUS ENTRIES (distinct, sourced, ratifiable
#   findings that actually move the physical metrics)?
#
# Auditor seat = HYBRID (owner): a SONNET agent audits EVERY round (spawned headless
# via `claude -p --model sonnet`, and -- per owner -- it PERSISTS ITS OWN reasoning +
# findings to findings/round-NNN-sonnet.json via the Write tool, no translation by the
# orchestrator); V4 (deepseek-v4-flash) does a DEEP CHECKPOINT every Nth round through
# the broker (its full reasoning persisted too).
#
# Injection surface = BOTH scorer weights + manager rules. GUARDRAIL (CLAUDE.md
# human-ratification boundary + DF-05 anti-ratchet): ADDITIVE-ONLY -- a scorer penalty
# may only be a NON-NEGATIVE cost that RAISES an existing weight (never lower it, never
# a negative weight that would REWARD the bad metric -- the self-test caught Sonnet
# proposing exactly that); a manager rule may only be ADDED. ADVISORY -- every accepted
# finding is logged as a DF-01 ratification CANDIDATE, NEVER auto-promoted; the human
# ratifies in the morning.
#
# Split compute: ROUTE+SCORE in the routing container (cec_overnight_directed worker);
# the SONNET auditor + V4 checkpoint + all bookkeeping run on the HOST. (CORRECTION
# 2026-06-11: the container CAN reach the broker -- the earlier "firewall gap" was curl
# missing from the image. The split stays as a choice: LLM orchestration host-side.)
#
# Usage:
#   python3 scripts/cec_inloop_audit.py --hours 7 --board eps-8pin
#   python3 scripts/cec_inloop_audit.py --shakeout            # 2 rounds, fast
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
import cec_overnight_directed as ovd          # route worker + pareto + ledger helpers

PERM = os.path.join(ROOT, "docs", "inloop-audit-2026-06-11")
FIND_DIR = os.path.join(PERM, "findings")
# Per-seat live-stream recorder (cec_seat_stream): default it to the run dir so the host-side seats
# (the corpus_fit_review reviewer, any host manager/panel) stream their thoughts to PERM/streams, which
# the live dashboard renders one section per seat. setdefault -> the operator can still override.
STREAM_DIR = os.path.join(PERM, "streams")
os.environ.setdefault("CEC_STREAM_DIR", STREAM_DIR)
LIVE_RULES_PATH = os.path.join(PERM, "live-rules.json")
MEASURE_PATH = os.path.join(PERM, "measurement.jsonl")
BUNDLE_PATH = os.path.join(PERM, "morning-bundle.json")

BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1")
V4_MODEL = "deepseek-v4-flash"
V4_EVERY = int(os.environ.get("CEC_INLOOP_V4_EVERY", "8"))   # deep checkpoint cadence
PENALTY_MAX = 1000.0                                          # runaway-inflation clamp

# derived metric keys the auditor may penalise (lower-is-better, all >= 0 cost)
def derived_metrics(rec):
    m = dict(rec)
    m["gate_fail"] = 0 if rec.get("gates_pass") else 1
    m["kelvin_unrouted"] = 0 if rec.get("kelvin_ok") else 1
    m["diffpair_unrouted"] = 0 if rec.get("diffpair_ok") else 1
    return m

PENALISABLE = ("drc", "unconnected", "length", "vias", "plane_signal_mm",
               "gate_fail", "kelvin_unrouted", "diffpair_unrouted")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- live ruleset (persisted, additive-only) -------------------------------------------------------
def load_live_rules():
    if os.path.exists(LIVE_RULES_PATH):
        try:
            return json.load(open(LIVE_RULES_PATH))
        except Exception:                                      # noqa: BLE001
            pass
    # base scorer weights the auditor may only TIGHTEN (from cec_score.DEFAULT_WEIGHTS, the
    # ones that are pure additive costs -- balance/length sign-special excluded from raise-only)
    return {"scorer_penalties": {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0},
            "manager_rules": [], "injections": [], "rejections": []}


def save_live_rules(lr):
    os.makedirs(PERM, exist_ok=True)
    json.dump(lr, open(LIVE_RULES_PATH, "w"), indent=1)


def live_objective(rec, lr):
    """base objective + Σ injected additive penalties over the record's (derived) metrics."""
    m = derived_metrics(rec)
    base = rec.get("objective", 0.0)
    extra = 0.0
    for k, w in lr["scorer_penalties"].items():
        # the base objective already prices plane_signal_mm/drc/unconnected at the cec_score
        # defaults; only the AMOUNT ABOVE those defaults is "injected" extra cost
        default = {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0}.get(k, 0.0)
        extra += max(0.0, w - default) * float(m.get(k, 0) or 0)
    return round(base + extra, 2)


# ---- guardrail: apply findings additively ----------------------------------------------------------
def apply_findings(findings, lr, rnd, source):
    """Additive-only injection with the DF-05 anti-ratchet guardrail. Returns
    (n_accepted_penalty, n_accepted_rule, events)."""
    events, na_p, na_r = [], 0, 0
    for f in findings:
        sp = f.get("scorer_penalty")
        if isinstance(sp, dict) and sp.get("metric") in PENALISABLE:
            metric = sp["metric"]
            try:
                w = float(sp.get("weight"))
            except (TypeError, ValueError):
                events.append({"round": rnd, "source": source, "kind": "penalty",
                               "metric": metric, "action": "rejected:non_numeric_weight"})
                continue
            cur = lr["scorer_penalties"].get(metric, 0.0)
            if w < 0:                                          # would REWARD the bad metric
                events.append({"round": rnd, "source": source, "kind": "penalty", "metric": metric,
                               "proposed": w, "action": "rejected:negative_would_reward"})
                continue
            w = min(w, PENALTY_MAX)
            if w <= cur:                                       # not a tightening -> no-op
                events.append({"round": rnd, "source": source, "kind": "penalty", "metric": metric,
                               "proposed": w, "current": cur, "action": "noop:not_a_tightening"})
                continue
            lr["scorer_penalties"][metric] = w                 # RAISE only
            events.append({"round": rnd, "source": source, "kind": "penalty", "metric": metric,
                           "from": cur, "to": w, "action": "accepted:raised",
                           "rationale": str(sp.get("rationale", ""))[:300]})
            na_p += 1
        rule = f.get("manager_rule")
        if isinstance(rule, str) and len(rule.strip()) >= 12:
            norm = " ".join(rule.lower().split())
            if any(norm == " ".join(r.lower().split()) for r in lr["manager_rules"]):
                events.append({"round": rnd, "source": source, "kind": "rule",
                               "action": "noop:duplicate_rule", "rule": rule[:120]})
            else:
                lr["manager_rules"].append(rule.strip())
                events.append({"round": rnd, "source": source, "kind": "rule",
                               "action": "accepted:added", "rule": rule.strip()[:300]})
                na_r += 1
    lr["injections"].extend([e for e in events if e["action"].startswith("accepted")])
    lr["rejections"].extend([e for e in events if e["action"].startswith(("rejected", "noop"))])
    # DF-01 ledger candidates (advisory; NEVER auto-promoted)
    for e in events:
        if e["action"].startswith("accepted"):
            try:
                import cec_ledger
                cec_ledger.append(board="inloop-audit-candidate", mode="decision",
                                  verdict=f"ratification-candidate {e['kind']} {e.get('metric') or 'rule'}",
                                  extra=e)
            except Exception:                                  # noqa: BLE001
                pass
    return na_p, na_r, events


# ---- the SONNET auditor: spawned headless, persists its OWN findings file ---------------------------
def _audit_prompt(rec, lr, rnd, out_path):
    m = derived_metrics(rec)
    metrics = {k: m.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                                     "length", "vias", "plane_signal_mm", "objective",
                                     "gate_fail", "kelvin_unrouted")}
    return (
        "You are the IN-LOOP routing AUDITOR for the CEC eps-8pin power-telemetry board. A directed "
        "Freerouting candidate was just produced and scored. Judge it and propose at most ONE additive "
        "scorer penalty and at most ONE manager rule that would improve FUTURE rounds.\n\n"
        f"THIS CANDIDATE (round {rnd}):\n{json.dumps(metrics, indent=1)}\n"
        f"per-net plane copper (mm of signal on a GND/power PLANE layer -- should be 0): "
        f"{json.dumps(rec.get('detail', {}).get('net_plane_mm', {}) if isinstance(rec.get('detail'), dict) else {})}\n"
        f"failing reasons: {json.dumps(rec.get('reasons', [])[:6])}\n"
        f"directed stub summary: {json.dumps(rec.get('stub_summary', {}))}\n\n"
        f"CURRENT INJECTED SCORER PENALTIES (you may only RAISE these or add a new one; a penalty is a "
        f"NON-NEGATIVE cost per unit of a lower-is-better metric -- a negative weight would REWARD the bad "
        f"metric and WILL be rejected): {json.dumps(lr['scorer_penalties'])}\n"
        f"STANDING MANAGER RULES you previously established ({len(lr['manager_rules'])}): "
        f"{json.dumps(lr['manager_rules'][-8:])}\n\n"
        f"Penalisable metric keys: {list(PENALISABLE)}. Verdict must be accept|repair|escalate "
        f"(repair if a hard gate fails and effort should increase; accept only if gates pass and quality "
        f"is good; escalate if stuck).\n"
        f"If the candidate is already clean OR you have nothing genuinely NEW to add, say so explicitly "
        f"(set scorer_penalty and manager_rule to null) -- do NOT invent redundant findings.\n\n"
        f"Use the Write tool to write ONLY this JSON object to the file {out_path} :\n"
        '{"verdict":"accept|repair|escalate","reasoning":"<your full reasoning>",'
        '"is_new_finding":true|false,'
        '"scorer_penalty":{"metric":"<one of the keys>","weight":<number>=0>,"rationale":"..."}|null,'
        '"manager_rule":"<imperative rule>"|null}\n'
        "Then reply DONE."
    )


def sonnet_audit(rec, lr, rnd, timeout=240):
    out_path = os.path.join(FIND_DIR, f"round-{rnd:03d}-sonnet.json")
    os.makedirs(FIND_DIR, exist_ok=True)
    prompt = _audit_prompt(rec, lr, rnd, out_path)
    # stdout = stream-json event tee -> the live dashboard tails this for realtime
    # "thoughts" (owner ask 2026-06-11); the findings JSON stays agent-written via Write.
    stream_path = os.path.join(FIND_DIR, f"round-{rnd:03d}-sonnet.stream.jsonl")
    try:
        with open(stream_path, "w") as sfh:
            subprocess.run(["claude", "-p", "--model", "sonnet", "--allowedTools", "Write",
                            "--output-format", "stream-json", "--verbose",
                            "--include-partial-messages"],
                           input=prompt, text=True, stdout=sfh, stderr=subprocess.DEVNULL,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"verdict": "repair", "reasoning": "sonnet timeout", "error": "timeout"}
    for _ in range(3):                                         # small grace for the file write
        if os.path.exists(out_path):
            try:
                return json.load(open(out_path))
            except Exception:                                  # noqa: BLE001
                time.sleep(1)
        else:
            time.sleep(1)
    return {"verdict": "repair", "reasoning": "no sonnet findings file", "error": "no_file"}


# ---- V4 deep checkpoint (broker; OPPORTUNISTIC + probe-only; persists full reasoning) ---------------
def _win_gateway():
    """WSL default gateway = the Windows host (broker.host() resolves 'windows-host' the same way)."""
    try:
        out = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            if line.startswith("default"):
                return line.split()[2]
    except Exception:                                          # noqa: BLE001
        pass
    return "127.0.0.1"


def v4_up():
    """Reachability pre-check against the broker catalog (GET /v1/models), then a direct 3s health
    GET on V4's own host:port. NEVER asks the broker to START it -- a cold start pins ~160GB host
    RAM + ~7min, which would starve the WSL2 routing container over a 7h run. If V4 is down, the
    checkpoint cleanly SKIPS. Matches the rebuilt broker contract: external backends carry
    host ('windows-host' -> WSL gateway) + port, NOT an 'upstream' URL, and the catalog route is
    /v1/models (the old /broker/models + m['upstream'] schema is gone)."""
    import urllib.request
    try:
        base = BROKER.rsplit("/v1", 1)[0]
        reg = json.load(urllib.request.urlopen(base + "/v1/models", timeout=5))
        m = next((x for x in reg.get("data", []) if x.get("id") == V4_MODEL), None)
        if not m:
            return False
        host = m.get("host") or "127.0.0.1"
        if host == "windows-host":
            host = _win_gateway()
        url = f"http://{host}:{m.get('port')}{m.get('health', '/health')}"
        with urllib.request.urlopen(url, timeout=3) as h:
            return h.status == 200
    except Exception:                                          # noqa: BLE001
        return False


def v4_checkpoint(rec, lr, rnd, timeout=1800):
    import urllib.request
    out_path = os.path.join(FIND_DIR, f"round-{rnd:03d}-v4.json")
    if not v4_up():
        json.dump({"round": rnd, "skipped": "v4 not running (opportunistic checkpoint)"},
                  open(out_path, "w"), indent=1)
        return {"skipped": True}
    m = derived_metrics(rec)
    metrics = {k: m.get(k) for k in ("gates_pass", "kelvin_ok", "drc", "unconnected", "length",
                                     "vias", "plane_signal_mm", "objective", "gate_fail")}
    prompt = (
        "You are the DEEP CHECKPOINT auditor (run every several rounds) for the CEC eps-8pin directed-"
        "routing loop. A fast auditor proposes penalties/rules each round; you provide the deep view. "
        f"Candidate round {rnd}: {json.dumps(metrics)}. Injected penalties so far: "
        f"{json.dumps(lr['scorer_penalties'])}. Standing rules: {json.dumps(lr['manager_rules'][-6:])}. "
        "Is the loop making real physical progress, or inflating penalties / repeating one board (a local "
        "minimum)? Propose at most ONE additive penalty (weight >= 0) and one rule ONLY if genuinely new. "
        "End your answer with a single line: FINDINGS_JSON={\"scorer_penalty\":{...}|null,"
        "\"manager_rule\":\"...\"|null,\"local_minimum_risk\":\"low|medium|high\"}"
    )
    payload = {"model": V4_MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 9000, "temperature": 0.3, "presence_penalty": 0.8}
    t0 = time.time()
    import cec_seat_stream as _stream
    _call = _stream.start("v4-checkpoint", model=V4_MODEL, role="deep-checkpoint", prompt_chars=len(prompt))
    try:
        req = urllib.request.Request(BROKER + "/chat/completions", json.dumps(payload).encode(),
                                     {"Content-Type": "application/json", "X-CEC-Client": "inloop-v4-checkpoint"})
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        msg = d["choices"][0]["message"]
        content, reasoning = msg.get("content") or "", msg.get("reasoning_content") or ""
        # raw (non-streaming) call -> record the whole reasoning+answer as one block on the v4 seat
        _call.delta(reasoning, "reasoning")
        _call.delta(content, "content")
        _call.end(ok=True)
    except Exception as e:                                     # noqa: BLE001
        _call.error(e)
        json.dump({"round": rnd, "error": f"{type(e).__name__}: {e}"}, open(out_path, "w"), indent=1)
        return {"error": str(e)}
    findings = {}
    mt = re.search(r"FINDINGS_JSON=(\{.*\})", (content + "\n" + reasoning).replace("\n", " "))
    if mt:
        try:
            findings = json.loads(mt.group(1))
        except Exception:                                      # noqa: BLE001
            pass
    rec_out = {"round": rnd, "wall_s": round(time.time() - t0, 1), "content": content,
               "reasoning_content": reasoning, "parsed_findings": findings}
    json.dump(rec_out, open(out_path, "w"), indent=1)         # full reasoning persisted (no translation)
    return findings


# ---- driver -----------------------------------------------------------------------------------------
def _findings_list(d):
    """normalise a single auditor dict into the apply_findings list form."""
    out = []
    if d.get("scorer_penalty") or d.get("manager_rule"):
        out.append({"scorer_penalty": d.get("scorer_penalty"), "manager_rule": d.get("manager_rule")})
    return out


def run(board, hours, shakeout):
    os.makedirs(FIND_DIR, exist_ok=True)
    import shutil
    _sdir = os.environ.get("CEC_STREAM_DIR", STREAM_DIR)      # fresh per-seat streams each run -- the
    shutil.rmtree(_sdir, ignore_errors=True)                 # recorder appends, so clear stale runs first
    os.makedirs(_sdir, exist_ok=True)
    deadline = time.time() + hours * 3600.0
    lr = load_live_rules()
    records, seen, rnd = [], set(), 0
    passes, opt_time = 18, 30        # adaptive effort (repair -> bump)
    log(f"IN-LOOP AUDIT: board={board} hours={hours} v4_every={V4_EVERY} "
        f"start penalties={lr['scorer_penalties']}")
    try:
        subprocess.run(ovd.COMPOSE + ["up", "-d", "routing"], capture_output=True, timeout=180)
    except Exception as e:                                     # noqa: BLE001
        log(f"  warn: routing up: {e}")

    while time.time() < deadline:
        rnd += 1
        log(f"--- round {rnd} (~{(deadline-time.time())/60:.0f} min left) passes={passes} opt={opt_time} ---")
        try:
            rec = ovd._exec_route_one(board, rnd, passes=passes, opt_time=opt_time)
            if rec.get("error"):
                log(f"  route error: {rec['error']}"); continue
            sha = rec.get("sha")
            rec["live_objective"] = live_objective(rec, lr)
            records.append(rec)
            repeat = bool(sha and sha in seen)
            if sha:
                seen.add(sha)
            log(f"  routed: gates={'PASS' if rec['gates_pass'] else 'FAIL'} kelvin={rec['kelvin_ok']} "
                f"plane={rec['plane_signal_mm']}mm drc={rec['drc']} unconn={rec['unconnected']} "
                f"base_obj={rec['objective']} live_obj={rec['live_objective']} repeat={repeat}")

            # SONNET auditor every round (self-persists findings file)
            sj = sonnet_audit(rec, lr, rnd)
            verdict = sj.get("verdict", "repair")
            log(f"  sonnet: verdict={verdict} new={sj.get('is_new_finding')} "
                f"-- {str(sj.get('reasoning',''))[:90]}")
            na_p, na_r, events = apply_findings(_findings_list(sj), lr, rnd, "sonnet")

            # V4 deep checkpoint every V4_EVERY rounds
            v4_find, v4_risk = {}, None
            if rnd % V4_EVERY == 0 and time.time() < deadline:
                log(f"  v4 deep checkpoint (round {rnd})...")
                v4_find = v4_checkpoint(rec, lr, rnd)
                v4_risk = v4_find.get("local_minimum_risk")
                p2, r2, ev2 = apply_findings(_findings_list(v4_find), lr, rnd, "v4")
                na_p += p2; na_r += r2; events += ev2
                log(f"  v4: local_minimum_risk={v4_risk} accepted_penalty={p2} rule={r2}")

            save_live_rules(lr)
            # adapt effort from the verdict (the manager-tier actuator)
            if verdict == "repair" and not rec["gates_pass"]:
                passes = min(passes + 6, 60); opt_time = min(opt_time + 10, 90)
            elif verdict == "escalate":
                passes = min(passes + 12, 60); opt_time = min(opt_time + 20, 120)
            elif verdict == "accept":
                passes, opt_time = 18, 30        # reset (explore a fresh region)

            # MEASUREMENT row (the convergence series)
            penalty_total = round(sum(lr["scorer_penalties"].values()), 2)
            row = {"round": rnd, "ts": time.strftime("%H:%M:%S"), "sha": sha, "repeat": repeat,
                   "passes": passes, "opt_time": opt_time, "verdict": verdict,
                   "gates_pass": rec["gates_pass"], "kelvin_ok": rec["kelvin_ok"],
                   "plane_signal_mm": rec["plane_signal_mm"], "drc": rec["drc"],
                   "unconnected": rec["unconnected"], "base_objective": rec["objective"],
                   "live_objective": rec["live_objective"], "penalty_total": penalty_total,
                   "n_rules": len(lr["manager_rules"]),
                   "accepted_penalty": na_p, "accepted_rule": na_r,
                   "n_rejected_or_noop": sum(1 for e in events if not e["action"].startswith("accepted")),
                   "sonnet_is_new": sj.get("is_new_finding"), "v4_local_min_risk": v4_risk}
            with open(MEASURE_PATH, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            ovd.ledger_round(board, rec, len(ovd.pareto_frontier(records)))
        except Exception as e:                                 # noqa: BLE001
            log(f"  round {rnd} FAILED: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
        if shakeout and rnd >= 2:
            log("shakeout: stop after 2 rounds"); break

    _finalize(board, records, lr, rnd)


def _finalize(board, records, lr, rnd):
    """Convergence verdict + morning bundle."""
    rows = []
    if os.path.exists(MEASURE_PATH):
        rows = [json.loads(L) for L in open(MEASURE_PATH) if L.strip()]
    front = ovd.pareto_frontier(records)
    # convergence heuristic over the last min(10, n) rows
    tail = rows[-10:]
    verdict = "inconclusive"
    if len(tail) >= 4:
        pen = [r["penalty_total"] for r in tail]
        planes = [r["plane_signal_mm"] for r in tail]
        kelvin = [1 if r["kelvin_ok"] else 0 for r in tail]
        new = sum(1 for r in tail if r.get("sonnet_is_new"))
        repeats = sum(1 for r in tail if r.get("repeat"))
        pen_rising = pen[-1] > pen[0]
        phys_flat = (max(planes) == min(planes)) and (max(kelvin) == min(kelvin))
        if pen_rising and phys_flat and new <= 1:
            verdict = "local_minimum"          # penalties inflate, physics flat, no new findings
        elif (kelvin[-1] > kelvin[0]) or (planes[-1] < planes[0]) or new >= 3:
            verdict = "productive"             # physical metrics moved / distinct findings keep coming
        elif repeats >= len(tail) - 1:
            verdict = "stalled_repeating"
    usable = [e for e in lr["injections"]]     # distinct accepted findings = ratification candidates
    bundle = {"board": board, "rounds": rnd, "candidates": len(records),
              "convergence_verdict": verdict, "pareto_finalists": len(front),
              "final_penalties": lr["scorer_penalties"], "n_manager_rules": len(lr["manager_rules"]),
              "n_usable_ratification_candidates": len(usable),
              "usable_candidates": usable[-40:], "rejections_noops": len(lr["rejections"]),
              "pareto_front": [{k: r.get(k) for k in ("round", "objective", "live_objective", "drc",
                                "unconnected", "plane_signal_mm", "kelvin_ok")} for r in front],
              "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(bundle, open(BUNDLE_PATH, "w"), indent=1)
    log(f"DONE: {rnd} rounds. CONVERGENCE={verdict}. {len(usable)} usable ratification candidates, "
        f"{len(lr['manager_rules'])} rules, {len(front)} Pareto finalists -> {BUNDLE_PATH}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="cec_inloop_audit -- in-loop self-correcting audit experiment")
    ap.add_argument("--board", default="eps-8pin", choices=sorted(ovd.BOARD_PCB))
    ap.add_argument("--hours", type=float, default=7.0)
    ap.add_argument("--shakeout", action="store_true", help="2 rounds, fast")
    a = ap.parse_args(argv)
    if a.shakeout:
        a.hours = min(a.hours, 1.0)
    run(a.board, a.hours, a.shakeout)


if __name__ == "__main__":
    main()
