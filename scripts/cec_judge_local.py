#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_judge_local -- local-vLLM realisation of the cec_router MANAGER judge tier (Thrust A).
# ============================================================================
# Wires a LOCAL vLLM OpenAI-compatible server (the Qwen3-Coder-30B-A3B AWQ judge on the workstation
# 5090) into cec_router's `manager=` slot, using vLLM GUIDED JSON constrained to the Verdict schema
# (docs/local-compute-exploration.md Thrust A: "the ~90% mechanical manager/worker volume runs local;
# cloud Opus stays for structural re-plan").
#
# FAIL-SAFE + HYBRID by construction:
#   * ANY failure (server down/loading, HTTP error, timeout, bad JSON) -> falls back to
#     cec_router.default_manager. A route NEVER breaks because the LLM is unavailable.
#   * the LLM CANNOT widen the safety envelope: route() only accepts when the best candidate already
#     has gates_pass (kelvin_ok + diffpair_ok), and we additionally downgrade an `accept` to `repair`
#     if the best candidate is not gate-passing. The hard gates + the independent DRC own correctness;
#     the LLM only chooses among already-safe outcomes (accept finishing-residual vs repair vs escalate).
#
#   from cec_judge_local import make_manager, available
#   route(board, spec, manager=make_manager(spec))     # if available() else the deterministic default
# ============================================================================
import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request

# cec_router / cec_score are imported LAZILY (inside make_manager/_context) -- they pull pcbnew, which
# is absent on the host. Keeping the module top pcbnew-free lets the LIFECYCLE + HTTP run on the host
# (where docker access lives) so the gate can start/stop the GPU server on demand.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# inside the routing container the server is reachable as the compose service `inference`;
# from the host it is http://localhost:8000. Override with CEC_VLLM_URL.
VLLM_URL = os.environ.get("CEC_VLLM_URL", "http://localhost:8000/v1").rstrip("/")
MODEL = os.environ.get("CEC_VLLM_MODEL_NAME", "cec-judge")     # --served-model-name in compose
TIMEOUT = float(os.environ.get("CEC_VLLM_TIMEOUT", "120"))   # absorbs the cold first guided-JSON grammar compile
TIER = "local:qwen3-coder-30b-awq"

# guided-JSON schema the server is constrained to (vLLM structured outputs)
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["accept", "repair", "escalate"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "reason"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the MANAGER judge tier in an automated PCB routing loop for the CEC power-telemetry "
    "platform. You are shown the scored Freerouting candidates for ONE region (best first) and must "
    "choose exactly ONE action.\n"
    "HARD RULES:\n"
    "1. `kelvin_ok` and `diffpair_ok` are HARD SAFETY GATES. NEVER choose `accept` unless the best "
    "candidate has gates_pass=true (both gates true).\n"
    "2. When gates_pass=true, a small residual `drc` and a couple of `unconnected` are normally "
    "finishing/cosmetic (silk, a decorative logo keepout, a shield-tab tie) -- prefer `accept`.\n"
    "3. If a hard gate is false (the sense pair or USB diff pair is not fully routed), choose "
    "`repair` -- the loop will bump Freerouting effort and re-route.\n"
    "4. If repairs have already run for several iterations with no improvement in drc/unconnected, "
    "choose `escalate` (a structural re-plan is needed).\n"
    "Reply ONLY with the JSON object {\"action\":..., \"reason\":...}. Keep the reason under 30 words."
)


def _post(path, payload, timeout=None):
    req = urllib.request.Request(VLLM_URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        return json.load(r)


def available(timeout=3):
    """True if the vLLM server answers /models (the judge is up). Cheap pre-check before wiring."""
    try:
        with urllib.request.urlopen(VLLM_URL + "/models", timeout=timeout) as r:
            return bool(json.load(r).get("data"))
    except Exception:
        return False


def chat_verdict(system, user, *, timeout=None):
    """One guided-JSON judge call -> the parsed verdict dict. Raises on any transport/parse error
    (the caller's make_manager() wraps this and falls back to the deterministic policy)."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "verdict", "schema": VERDICT_SCHEMA, "strict": True}},
    }
    resp = _post("/chat/completions", payload, timeout=timeout)
    return json.loads(resp["choices"][0]["message"]["content"])


def _context(region, scored, history, spec):
    """Pack the manager's decision context as JSON the judge reads (same metric shape as the
    DecisionLog) -- the top candidates + the best candidate's failing hard-gate reasons."""
    import cec_router
    import cec_score
    cands = [cec_router.DecisionLog._m(m) for _, m in scored[:4]]
    best = scored[0][1] if scored else None
    reasons = (cec_score.gate(best, cec_router.region_rules(region, spec))[1][:4]
               if best is not None else ["no candidate routed"])
    return json.dumps({
        "region": getattr(region, "name", "all"),
        "iteration": len(history) + 1,
        "prior_iterations": len(history),
        "candidates_best_first": cands,
        "best_candidate_gate_failures": reasons,
    }, indent=1)


def make_manager(spec, *, verbose=False):
    """Return a cec_router `manager(region, scored, history)` backed by the local LLM, with a
    deterministic fallback. Drop straight into route(..., manager=make_manager(spec))."""
    import cec_router

    def _fallback(region, scored, history):
        return cec_router.default_manager(region, scored, history, spec)

    def manager(region, scored, history):
        try:
            user = _context(region, scored, history, spec)
            v = chat_verdict(SYSTEM, user)
            action = v.get("action", "repair")
            best = scored[0][1] if scored else None
            if action == "accept" and not (best is not None and best.gates_pass):
                action = "repair"            # SAFETY: never accept a non-gate-passing board
            if action not in ("accept", "repair", "escalate"):
                action = "repair"
            if verbose:
                print(f"[judge:local] {getattr(region,'name','all')} -> {action}: {v.get('reason','')[:80]}")
            return cec_router.Verdict(action, str(v.get("reason", ""))[:200], tier=TIER)
        except Exception as e:
            fb = _fallback(region, scored, history)
            fb.tier = (fb.tier or "") + f" (local-judge-fallback:{type(e).__name__})"
            if verbose:
                print(f"[judge:local] FALLBACK ({type(e).__name__}: {e}) -> {fb.action}")
            return fb

    return manager


def swarm_judge(contexts, *, max_workers=8, timeout=None):
    """Fire N judge calls CONCURRENTLY at the batched vLLM -- the local AGENT SWARM (Thrust A: one
    batched server serves the swarm, not many small servers). `contexts` is a list of user-message
    JSON strings; returns a list of verdict dicts (or {"error":...}) aligned with `contexts`. The
    batched server interleaves the concurrent requests, so wall-clock for N << N x single-call."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(user):
        try:
            return chat_verdict(SYSTEM, user, timeout=timeout)
        except Exception as e:
            return {"error": type(e).__name__}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_one, contexts))


# ===========================================================================
#  ON-DEMAND LIFECYCLE GATE -- spin the GPU server up only when needed, warm it, free VRAM after.
# ===========================================================================
# The vLLM server holds ~0.85 x VRAM for as long as it runs, so it is profile-gated in compose
# (never auto-started) and managed here. These shell out to `docker compose` -> run them on the HOST
# (the routing container has no docker socket). ensure_up() is idempotent (no-op if already serving).
def _compose(*args, capture=True):
    cf = os.path.join(ROOT, "docker", "compose.yaml")
    return subprocess.run(["docker", "compose", "-f", cf, *args], capture_output=capture, text=True)


def warmup(*, timeout=180, verbose=True):
    """Compile the guided-JSON grammar NOW (one tiny structured call) so the first real judge call is
    fast instead of paying the cold first-compile (which would otherwise time out -> a fallback)."""
    try:
        t0 = time.time()
        chat_verdict(SYSTEM,
                     '{"region":"warmup","iteration":1,"candidates_best_first":[],'
                     '"best_candidate_gate_failures":[]}', timeout=timeout)
        if verbose:
            print(f"[judge:gate] grammar warmup done in {time.time() - t0:.0f}s")
        return True
    except Exception as e:
        if verbose:
            print(f"[judge:gate] warmup skipped ({type(e).__name__})")
        return False


def ensure_up(*, warm=True, timeout=600, poll=4.0, verbose=True):
    """Bring the vLLM judge UP on demand and (warm=True) compile the grammar. Idempotent: if it is
    already serving, just warm. Returns True once /v1/models answers. Needs the host `docker` CLI."""
    if available(timeout=3):
        if warm:
            warmup(verbose=verbose)
        return True
    if not shutil.which("docker"):
        if verbose:
            print("[judge:gate] docker CLI not on PATH -> cannot autostart vLLM (start it manually)")
        return False
    if verbose:
        print("[judge:gate] starting vLLM inference service on demand (this holds ~0.85x VRAM while up)...")
    r = _compose("--profile", "inference", "up", "-d", "inference")
    if r.returncode != 0:
        if verbose:
            print("[judge:gate] compose up failed:", (r.stderr or "")[-300:])
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        if available(timeout=3):
            if verbose:
                print(f"[judge:gate] vLLM ready in {time.time() - t0:.0f}s")
            if warm:
                warmup(verbose=verbose)
            return True
        time.sleep(poll)
    if verbose:
        print(f"[judge:gate] vLLM not ready after {timeout}s (model still loading?)")
    return False


def shutdown(*, verbose=True):
    """Stop the vLLM service -> frees the GPU VRAM. Safe no-op if docker is absent / already stopped."""
    if not shutil.which("docker"):
        return False
    r = _compose("stop", "inference")
    if verbose:
        print("[judge:gate] vLLM stopped, VRAM freed" if r.returncode == 0 else "[judge:gate] stop failed")
    return r.returncode == 0


if __name__ == "__main__":
    # Host-side gate CLI: manage the on-demand GPU judge + a smoke test.
    import argparse
    ap = argparse.ArgumentParser(description="cec_judge_local -- local vLLM judge gate + smoke")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["up", "down", "warm", "status", "smoke"],
                    help="up=start+warm on demand, down=stop (free VRAM), warm, status, smoke=judge a fake candidate")
    ap.add_argument("--url", default=VLLM_URL)
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for the server to come up")
    a = ap.parse_args()
    VLLM_URL = a.url.rstrip("/")

    if a.cmd == "up":
        sys.exit(0 if ensure_up(timeout=a.timeout) else 1)
    if a.cmd == "down":
        sys.exit(0 if shutdown() else 1)
    if a.cmd == "warm":
        sys.exit(0 if warmup() else 1)
    if a.cmd == "status":
        print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
        sys.exit(0)
    # smoke: a gate-passing finishing-residual candidate -> expect accept
    print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
    if available():
        user = json.dumps({"region": "all", "iteration": 2, "prior_iterations": 1,
                           "candidates_best_first": [{"drc": 4, "unconnected": 2, "tracks": 556,
                               "vias": 84, "kelvin_ok": True, "diffpair_ok": True, "gates_pass": True}],
                           "best_candidate_gate_failures": []}, indent=1)
        print("verdict:", chat_verdict(SYSTEM, user))
