#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_overnight -- deadline-bounded overnight pipeline driver.
# ============================================================================
# Straddles the single-heavy-GPU-model limit of the one RTX 5090 by alternating two local tiers,
# with ALL model lifecycle BROKER-MEDIATED (cec-llm-broker :8080, a systemd unit -- requesting a
# model by name boots it on demand, swaps the GPU if another model holds it, queues the request
# through the cold load, and an idle reaper stops it later; NEVER compose up/down LLM services here):
#   * ROUTE blocks: the volume WORKER (cec-worker, Qwen3.6-35B-A3B) judges the per-region
#     accept/repair/escalate decisions while cec_router GENERATES CANDIDATES -- routing runs in the
#     `routing` container (it needs pcbnew; reaches the broker via host.docker.internal:8080); this
#     accumulates DecisionLogs in build/route/corpus.
#   * REVIEW blocks: the REVIEWER tier (cec_judge_local.REVIEWER_MODEL -- default cec-manager-fast
#     = gpt-oss-120b per the 2026-06-09 bench; CEC_VLLM_REVIEWER_MODEL=cec-manager for the MiniMax
#     M2.7 deep auditor) DEEP-REVIEWS the freshly-routed boards against their same-family corpus
#     (cec_judge_local.corpus_fit_review) -- run on the HOST (pcbnew-free), one
#     <corpus-log>-corpus-fit.json sidecar per route.
# Only the GPU model alternates (broker-arbitrated); the routing + freerouting containers stay up.
#
# The driver alternates ROUTE and REVIEW blocks, ending on a review, until a wall-clock deadline.
# Robust for unattended operation: every route/review/warm is wrapped, a failure is logged and the
# run continues. All output under build/overnight/.
#
#   python3 scripts/cec_overnight.py --hours 6.5
#   python3 scripts/cec_overnight.py --hours 0.2 --route-block 6 --review-block 6   # short shakeout
# ============================================================================
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE = ["docker", "compose", "-f", os.path.join(ROOT, "docker", "compose.yaml")]
BOARDS = ["eps-8pin", "pcie-8pin-2port", "pcie-8pin-3port"]
CORPUS_DIR = os.path.join(ROOT, "build", "route", "corpus")
OUT_DIR = os.path.join(ROOT, "build", "overnight")
REVIEW_DIR = os.path.join(OUT_DIR, "reviews")

# Everything goes through the broker -- liveness via its catalog (GET /models carries per-model
# `running` flags and answers even with nothing up), boot/swap by simply REQUESTING the model. The
# old direct :8000/:8001 probes + compose stop/start swaps targeted services that no longer exist
# (the 235B was retired and its compose `manager` service gutted 2026-06-09). cec_judge_local's own
# defaults already point at the broker; the review model is its REVIEWER_MODEL resolution.
BROKER = os.environ.get("CEC_LLM_BROKER_URL", "http://localhost:8080/v1").rstrip("/")
WORKER_MODEL = "cec-worker"

_LOGF = None


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _LOGF:
        _LOGF.write(line + "\n")
        _LOGF.flush()


def _sh(args, timeout=None):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(args, 124, e.stdout or "", (e.stderr or "") + "\n[timeout]")


def _broker_models():
    """The broker catalog: [{id, running, ...}] -- it answers even with nothing running."""
    try:
        req = urllib.request.Request(BROKER + "/models", headers={"X-CEC-Client": "CEC-Platform"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r).get("data") or []
    except Exception:
        return []


def model_running(model):
    return any(m.get("id") == model and m.get("running") for m in _broker_models())


def broker_warm(model, timeout):
    """Ensure `model` is live by REQUESTING it through the broker (a 1-token chat is the boot
    trigger; the broker swaps the GPU if another model holds it and queues the request through the
    cold load). Idempotent, and the only sanctioned way to start/swap an LLM backend."""
    if model_running(model):
        return True
    log(f"  broker warm -> {model} (cold load rides through, up to {timeout}s)")
    t0 = time.time()
    try:
        payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        req = urllib.request.Request(BROKER + "/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json",
                                              "X-CEC-Client": "CEC-Platform"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        log(f"  {model} ready in {time.time() - t0:.0f}s")
        return True
    except Exception as e:
        log(f"  !! {model} warm FAILED after {time.time() - t0:.0f}s ({type(e).__name__})")
        return False


def ensure_worker():
    """ROUTE blocks need the `routing` compute container up (kicad/pcbnew -- NOT an LLM service, so
    compose is fine for it) + the volume worker warm behind the broker."""
    _sh(COMPOSE + ["up", "-d", "routing"], timeout=180)
    return broker_warm(WORKER_MODEL, timeout=600)   # measured cold swap 90.7s; margin for arbitration


def ensure_manager():
    """REVIEW blocks need the REVIEWER model warm (cec-manager-fast ~6.5 min cold via the broker;
    a CEC_VLLM_REVIEWER_MODEL=cec-manager pin means M2.7 at ~10.5 min cold)."""
    import cec_judge_local
    return broker_warm(cec_judge_local.REVIEWER_MODEL, timeout=1200)


# ---- ROUTE phase -----------------------------------------------------------------------------------
def route_one(board, seed, passes, opt, per_route_timeout):
    """Run one cec_router route in the routing container with the worker swarm judge. Returns a dict."""
    out = f"build/overnight/route/{board}"
    cmd = COMPOSE + ["exec", "-T", "-e", "CEC_CORPUS_REVIEW=0", "routing",
                     "python3", "scripts/cec_router.py",
                     "--board", board, "--seeds", str(seed), "--passes", str(passes),
                     "--opt-time", str(opt), "--judge", "local", "--swarm", "3",
                     "--out", out, "--quiet"]
    t0 = time.time()
    r = _sh(cmd, timeout=per_route_timeout)
    dt = time.time() - t0
    verdict, corpus = None, None
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("verdict:"):
            try:
                verdict = json.loads(ln.split("verdict:", 1)[1].strip())
            except Exception:
                pass
        if "ARCHIVED" in ln:
            corpus = ln.split("ARCHIVED", 1)[1].strip()
    ok = r.returncode == 0 and verdict is not None
    res = {"board": board, "seed": seed, "passes": passes, "opt": opt, "elapsed_s": round(dt, 1),
           "ok": ok, "rc": r.returncode, "corpus": corpus,
           "gates_pass": (verdict or {}).get("gates_pass"), "drc": (verdict or {}).get("drc"),
           "unconnected": (verdict or {}).get("unconnected"), "objective": (verdict or {}).get("objective")}
    if not ok:
        res["err"] = (r.stderr or r.stdout or "")[-240:]
    return res


def route_block(end_ts, round0, per_route_timeout, manifest):
    if not ensure_worker():
        log("route block SKIPPED (worker unavailable)")
        return round0
    rnd = round0
    while time.time() < end_ts:
        board = BOARDS[rnd % len(BOARDS)]
        seed = rnd // len(BOARDS)
        passes = min(8 + 4 * (rnd // len(BOARDS)), 40)     # escalate Freerouting effort over the night
        opt = min(12 + 6 * (rnd // len(BOARDS)), 60)
        # don't start a route we can't finish before the block ends (+ a margin)
        if time.time() + min(per_route_timeout, 240) > end_ts:
            break
        try:
            res = route_one(board, seed, passes, opt, per_route_timeout)
        except Exception as e:
            res = {"board": board, "seed": seed, "ok": False, "err": f"{type(e).__name__}: {e}"}
        manifest["routes"].append(dict(res, t=time.strftime("%H:%M:%S")))
        log(f"  route {board} seed={seed} p{passes}/o{opt}: ok={res.get('ok')} "
            f"gates={res.get('gates_pass')} drc={res.get('drc')} unc={res.get('unconnected')} "
            f"obj={res.get('objective')} ({res.get('elapsed_s')}s)")
        _save_manifest(manifest)
        rnd += 1
    return rnd


# ---- REVIEW phase ----------------------------------------------------------------------------------
def _reviewed_set():
    os.makedirs(REVIEW_DIR, exist_ok=True)
    return {os.path.basename(p)[:-len("-corpus-fit.json")]
            for p in os.listdir(REVIEW_DIR) if p.endswith("-corpus-fit.json")}


def _pending_corpus():
    """Unreviewed corpus logs, NEWEST first, failed/None routes last (low value)."""
    import glob
    done = _reviewed_set()
    cand = []
    for p in glob.glob(os.path.join(CORPUS_DIR, "*.json")):
        stem = os.path.basename(p)[:-len(".json")]
        if stem in done:
            continue
        failed = os.path.basename(p).startswith("None-")
        cand.append((failed, -os.path.getmtime(p), p))
    cand.sort()
    return [p for _, _, p in cand]


def review_block(end_ts, manifest, review_timeout):
    if not ensure_manager():
        log("review block SKIPPED (manager unavailable)")
        return
    import cec_judge_local
    pend = _pending_corpus()
    log(f"  {len(pend)} corpus logs pending review")
    for p in pend:
        if time.time() + min(review_timeout, 300) > end_ts:
            log("  review block time budget reached")
            break
        stem = os.path.basename(p)[:-len(".json")]
        t0 = time.time()
        try:
            res = cec_judge_local.corpus_fit_review(p)
        except Exception as e:
            res = {"fit_classification": "no_opinion", "recommendation": "no_opinion",
                   "headline": f"driver error {type(e).__name__}", "_error": str(e)}
        sidecar = os.path.join(REVIEW_DIR, f"{stem}-corpus-fit.json")
        try:
            with open(sidecar, "w") as f:
                json.dump(res, f, indent=2)
        except Exception:
            pass
        rec = {"corpus": os.path.basename(p), "fit": res.get("fit_classification"),
               "rec": res.get("recommendation"), "conf": res.get("confidence"),
               "headline": res.get("headline"), "elapsed_s": round(time.time() - t0, 1),
               "t": time.strftime("%H:%M:%S")}
        manifest["reviews"].append(rec)
        log(f"  review {os.path.basename(p)[:40]}: {rec['fit']} / {rec['rec']} ({rec['conf']}) "
            f"[{rec['elapsed_s']}s] -- {str(rec['headline'])[:70]}")
        _save_manifest(manifest)


# ---- driver ----------------------------------------------------------------------------------------
def _save_manifest(manifest):
    manifest["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception:
        pass


def main(argv=None):
    global _LOGF
    ap = argparse.ArgumentParser(description="CEC overnight pipeline driver (broker-mediated worker/reviewer blocks)")
    ap.add_argument("--hours", type=float, default=6.5, help="total wall-clock budget")
    ap.add_argument("--route-block", type=float, default=80, help="minutes per route block")
    ap.add_argument("--review-block", type=float, default=40, help="minutes per review block")
    ap.add_argument("--final-review", type=float, default=45, help="minutes reserved for a final review")
    ap.add_argument("--per-route-timeout", type=int, default=1200, help="seconds cap per route")
    ap.add_argument("--review-timeout", type=int, default=1900, help="seconds cap per corpus review")
    a = ap.parse_args(argv)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    _LOGF = open(os.path.join(OUT_DIR, f"run-{stamp}.log"), "a")
    start = time.time()
    deadline = start + a.hours * 3600
    final_cut = deadline - a.final_review * 60
    manifest = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "hours": a.hours,
                "routes": [], "reviews": []}

    log(f"=== overnight start: {a.hours}h budget, route-block={a.route_block}m review-block={a.review_block}m "
        f"final-review={a.final_review}m ===")
    rnd = 0
    try:
        while time.time() < final_cut:
            rb_end = min(time.time() + a.route_block * 60, final_cut)
            log(f"--- ROUTE block until {time.strftime('%H:%M:%S', time.localtime(rb_end))} ---")
            rnd = route_block(rb_end, rnd, a.per_route_timeout, manifest)
            if time.time() >= final_cut:
                break
            vb_end = min(time.time() + a.review_block * 60, final_cut)
            log(f"--- REVIEW block until {time.strftime('%H:%M:%S', time.localtime(vb_end))} ---")
            review_block(vb_end, manifest, a.review_timeout)
        log("--- FINAL REVIEW block ---")
        review_block(deadline, manifest, a.review_timeout)
    except KeyboardInterrupt:
        log("interrupted")
    except Exception as e:
        log(f"DRIVER ERROR {type(e).__name__}: {e}")

    manifest["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    manifest["wall_s"] = round(time.time() - start, 0)
    nr = len(manifest["routes"])
    okr = sum(1 for r in manifest["routes"] if r.get("ok"))
    nv = len(manifest["reviews"])
    _save_manifest(manifest)
    log(f"=== overnight done: {nr} routes ({okr} ok), {nv} reviews, {manifest['wall_s']/3600:.1f}h ===")
    from collections import Counter
    fits = Counter(v.get("fit") for v in manifest["reviews"])
    log(f"  review verdicts: {dict(fits)}")


if __name__ == "__main__":
    main()
