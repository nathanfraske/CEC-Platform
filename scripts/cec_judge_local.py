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
#     has gates_pass. That value includes the configured Kelvin, differential-pair, DRC, and
#     unconnected-ratline gates. We additionally downgrade an `accept` to `repair` if it is false.
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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

# cec_router / cec_score are imported LAZILY (inside make_manager/_context) -- they pull pcbnew, which
# is absent on the host. Keeping the module top pcbnew-free lets the LIFECYCLE + HTTP run on the host
# (where docker access lives) so the gate can start/stop the GPU server on demand.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# LLM access is BROKERED by default through the cec-llm-broker (/home/nathan/cec-llm-broker): a tiny
# OpenAI-compatible reverse proxy on :8080 that FIFO-SERIALIZES per upstream so this project and the
# OTHER LLM project on this single-GPU box don't thrash the 5090. It ROUTES BY MODEL NAME -- 'cec-judge'
# -> vLLM :8000 (worker), 'cec-manager' -> llama.cpp :8001 (the 235B manager) -- so pointing every call
# at the broker and keeping the model names is all it takes. Fail-fast: if the broker is down the client
# gets connection-refused and the judge fails safe to its deterministic/no_opinion path. Bypass straight
# to an upstream with CEC_VLLM_URL=http://localhost:8000/v1. Inside the routing container the broker is
# the host, so there CEC_VLLM_URL=http://host.docker.internal:8080/v1 (set in docker/compose.yaml).
BROKER_URL = os.environ.get("CEC_LLM_BROKER_URL", "http://localhost:8080/v1").rstrip("/")
VLLM_URL = (os.environ.get("CEC_VLLM_URL") or BROKER_URL).rstrip("/")
# 2026-06-09 model refresh: the volume/swarm tier default is now cec-worker (Qwen3.6-35B-A3B
# UD-Q4_K_M, llama.cpp :8002, 4 parallel slots) -- the broker BOOTS it on demand. The old vLLM
# 30B AWQ stays registered as cec-judge (CEC_VLLM_MODEL_NAME=cec-judge to use it). For MAX
# PER-CALL QUALITY over throughput, point the worker tier at the 27B dense:
#   CEC_VLLM_WORKER_MODEL=cec-worker-quality
# TIERING (2026-06-10 bench verdict): the IN-LOOP manager tier (panels/dispatch, interleaved with
# worker effort calls every route iteration) deliberately defaults to the SAME worker-class model --
# pointing it at a big manager would make the broker swap the 27GB worker and a big manager in and
# out EVERY iteration. The big models live in the OUT-OF-LOOP REVIEWER tier below.
MODEL = os.environ.get("CEC_VLLM_MODEL_NAME", "cec-worker-vision")  # unified text+vision seat: same
# weights as cec-worker + mmproj, so defaulting here keeps text-only callers off the OLD cec-worker
# service and prevents the 24 GB worker<->vision swap (PR #36 item 2). Override via CEC_VLLM_MODEL_NAME.
# Optional TIERING: workers (cheap, high-volume effort-sizing) can use a SMALLER served model than the
# managers (judgment). Defaults to the manager model -- the worker is ALREADY cheap (the manager model
# is a MoE 30B-A3B = 3B active params/token), so this only earns its keep if a bigger MANAGER model is
# brought up and a tiny worker model is served alongside it. Unset -> one model, zero extra VRAM.
WORKER_MODEL = os.environ.get("CEC_VLLM_WORKER_MODEL") or MODEL
WORKER_URL = (os.environ.get("CEC_VLLM_WORKER_URL") or VLLM_URL).rstrip("/")
# TIERED MANAGER: the (low-volume, high-stakes) MANAGER judgment can run on a SEPARATE, SMARTER server
# -- e.g. gpt-oss-120b / Qwen3-235B on a llama.cpp endpoint (experts in RAM) -- while the high-volume
# WORKER/dispatch calls stay on the fast vLLM. Unset -> the manager uses the same server/model as the
# workers (one model). This is the "big slow smart manager + small fast workers" split.
MANAGER_URL = (os.environ.get("CEC_VLLM_MANAGER_URL") or VLLM_URL).rstrip("/")
MANAGER_MODEL = os.environ.get("CEC_VLLM_MANAGER_MODEL") or MODEL
# OUT-OF-LOOP REVIEWER tier (corpus_fit_review: once per routed board, never inside the route loop).
# 2026-06-09 reasoning bench (6 runs, hard quantitative trap problem): gpt-oss-120b scored ~9.5/10
# COMPLETE in ONE call (3.7k tok / 172s; 22.3 tok/s warm; 9GB VRAM, experts in RAM so it coexists
# with the worker in page cache), while MiniMax-M2.7 truncated TWICE with EMPTY content (the whole
# budget burned in reasoning_content, at 8k AND 14k caps). So the bounded-JSON reviewer DEFAULTS to
# cec-manager-fast. The opt-in deep AUDITOR (CEC_VLLM_REVIEWER_MODEL=deepseek-v4-flash) is now
# DeepSeek-V4-Flash 284B -- owner directive 2026-06-11 RETIRED MiniMax-M2.7 (cec-manager) from THIS
# pipeline and replaced it with DeepSeek now that V4's deep-reasoning performance is established;
# the heavy cold load (~160 GB host-RAM mmap + WSL cache-drop preflight, see the broker entry) is
# the accepted cost of the deep tier. M2.7's broker backend is LEFT REGISTERED (other project may
# use it) but no CEC pipeline path points at it. The miner->scribe recovery + sampling floors below
# now protect the DeepSeek deep tier. An explicit CEC_VLLM_MANAGER_MODEL pin is honored second for
# back-compat (the pre-bench overnight driver pinned the deep manager that way).
REVIEWER_URL = (os.environ.get("CEC_VLLM_REVIEWER_URL") or MANAGER_URL).rstrip("/")
REVIEWER_MODEL = (os.environ.get("CEC_VLLM_REVIEWER_MODEL")
                  or os.environ.get("CEC_VLLM_MANAGER_MODEL") or "cec-manager-fast")
TIMEOUT = float(os.environ.get("CEC_VLLM_TIMEOUT", "300"))   # absorbs the cold first guided-JSON grammar compile
# Timeouts are a CEILING (a fast response returns immediately) -- set them generous so a long deep-tier
# generation is never timeout-cut mid-thought (owner 2026-06-13: a mid-process cut poisons every later pass).

# CLOUD-SEAT SHIM (owner ask 2026-06-13: an off-box "--seats cloud" fast-iteration mode + the seat
# bake-off). A model name in CLOUD_MODELS (or any "claude*") is NOT a broker model -- route it through
# the `claude -p` CLI instead of the broker, returning the same schema-shaped dict _chat_json yields.
# The CLI has no json_schema grammar, so we instruct JSON-only + parse + best-effort-validate; the
# caller (deterministic fallback) and the bake-off scorer treat a non-conforming reply as a failure.
CLOUD_MODELS = {m.strip() for m in os.environ.get("CEC_CLOUD_MODELS", "sonnet,opus,haiku").split(",")
                if m.strip()}
CLOUD_EFFORT = os.environ.get("CEC_CLOUD_EFFORT") or None       # high|max for the deep reasoning seats
CLOUD_CLI = os.environ.get("CEC_CLOUD_CLI", "claude")
MANAGER_TIMEOUT = float(os.environ.get("CEC_VLLM_MANAGER_TIMEOUT", "2400"))   # a big RAM-offload thinking manager is slow
# THINKING models reason before the JSON; an undersized token budget truncates mid-reason -> empty
# content -> JSON parse failure -> silent deterministic fallback (first measured on the retired
# Qwen3-235B-Thinking, re-measured on MiniMax-M2.7). The manager tier keeps its OWN generous-but-
# bounded budget, and _chat_json below adds the bench-verified recovery (2026-06-09): when `content`
# comes back EMPTY with the answer stranded in `reasoning_content` (M2.7's signature failure at 8k
# AND 14k caps -- a "think shorter" directive made it think LONGER), a second SCRIBE call
# transcribes the trace's conclusion under the json_schema grammar instead of falling back. That is
# the measured miner->scribe protocol (complete 9.5/10 answer in ~3.6k tok / ~5 min).
# 12000 (was 4096): max_tokens is a CEILING (short answers stop early, no cost), so size it for the DEEP
# tier -- a V4/Opus per-round audit reasons before the JSON and 4096 truncated it mid-reason. V4 ctx is
# 32768 so 12000 fits with margin; the verifier's V4 batch uses 14000. Env-overridable.
MANAGER_MAX_TOKENS = int(os.environ.get("CEC_VLLM_MANAGER_MAX_TOKENS", "12000"))
# WORKER budget (2026-06-09): was a hardcoded 400, sized for the NON-thinking 30B AWQ. The new
# worker tier (cec-worker 35B-A3B / cec-worker-quality 27B, Qwen3.6) THINKS before answering --
# a 400 cap truncates mid-reason -> empty content -> JSON parse fail -> silent deterministic
# fallback (the exact failure mode the manager budget fix documented). 1200 covers measured
# reasoning (trivial ask ~160 tokens; real verdicts a few hundred) with margin.
WORKER_MAX_TOKENS = int(os.environ.get("CEC_VLLM_WORKER_MAX_TOKENS", "3000"))   # 3000 (was 1200): headroom so a thinking worker never truncates a long JSON
# DEEP-TIER SAMPLING FLOORS: large reasoning models can verbatim decode-loop at temp <=0.1-0.2
# without a presence penalty (first seen on MiniMax-M2.7: watched it lock, 6x the same sentence).
# Applied to whatever is in CEC_VLLM_FLOOR_MODELS. Default now covers the DeepSeek-V4-Flash deep
# tier (defensive: it is a large reasoning model on the same heavy-thinking path); cec-manager kept
# so the clamp still protects M2.7 if invoked from outside this pipeline.
_FLOOR_MODELS = {m.strip() for m in
                 os.environ.get("CEC_VLLM_FLOOR_MODELS", "deepseek-v4-flash,cec-manager").split(",") if m.strip()}
_FLOOR_TEMP = float(os.environ.get("CEC_VLLM_FLOOR_TEMP", "0.3"))
_FLOOR_PRESENCE = float(os.environ.get("CEC_VLLM_FLOOR_PRESENCE", "0.8"))
# miner->scribe recovery knobs. Trace tail cap: both manager-class services run --ctx-size 16384,
# so the scribe input must leave room for the system prompt + the 4k answer budget
# (36000 chars ~= 9k tokens; conclusions form at the trace END, so the TAIL is kept).
_AUTO_SCRIBE = os.environ.get("CEC_VLLM_AUTO_SCRIBE", "1") != "0"
_SCRIBE_TRACE_CHARS = int(os.environ.get("CEC_VLLM_SCRIBE_TRACE_CHARS", "36000"))
_SCRIBE_MAX_TOKENS = int(os.environ.get("CEC_VLLM_SCRIBE_MAX_TOKENS", "6000"))   # 6000 (was 4096): bounded by the 16384 manager ctx (9k trace tail + ~6k answer + system)
TIER = "local:cec-worker-vision"

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
    "1. NEVER choose `accept` unless the best candidate has gates_pass=true. This is the complete "
    "independent scorer contract, including configured Kelvin, differential-pair, DRC, and "
    "unconnected-ratline gates.\n"
    "2. Never waive a failed gate as finishing or cosmetic. Such findings require correction or an "
    "explicit disposition outside automatic route acceptance.\n"
    "3. If a hard gate is false (the sense pair or USB diff pair is not fully routed), choose "
    "`repair` -- the loop will bump Freerouting effort and re-route.\n"
    "4. If repairs have already run for several iterations with no improvement in drc/unconnected, "
    "choose `escalate` (a structural re-plan is needed).\n"
    "5. `plane_signal_mm` is signal copper routed ON a ground/power PLANE layer -- it breaks the "
    "return path under that net (ratified rule gnd-plane-continuity) and is already penalised in the "
    "objective. It is normally 0. NEVER `accept` a candidate with a non-zero `plane_signal_mm` when a "
    "lower-plane candidate is available; prefer `repair` so the router re-routes off the plane.\n"
    "Reply ONLY with the JSON object {\"action\":..., \"reason\":...}. Keep the reason under 30 words."
)


# X-CEC-Client lets the broker's /broker/stats + contention logs attribute requests to this project
# (vs the other LLM project sharing the GPU); harmless when talking straight to an upstream.
_CLIENT_HEADERS = {"Content-Type": "application/json", "X-CEC-Client": "CEC-Platform"}

# Ambient seat label for the per-seat stream recorder (cec_seat_stream). Resolution order in
# _chat_json: explicit seat= kwarg > this contextvar > the model name. Set it inside panel worker
# threads (contextvars do not auto-propagate across a ThreadPoolExecutor).
import contextvars as _ctxvars                                # noqa: E402
_SEAT = _ctxvars.ContextVar("cec_seat", default=None)


def set_seat(label):
    """Set the ambient seat for calls on THIS thread/context (returns the token to reset)."""
    return _SEAT.set(label)


def _post(path, payload, timeout=None, url=None):
    req = urllib.request.Request((url or VLLM_URL) + path, data=json.dumps(payload).encode(),
                                 headers=dict(_CLIENT_HEADERS), method="POST")
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        return json.load(r)


def _post_stream(path, payload, timeout=None, url=None, call=None):
    """SSE streaming POST: tees content + reasoning_content deltas to `call` (a cec_seat_stream.Call)
    as they arrive, then returns a SYNTHESIZED non-streaming response dict so _chat_json's downstream
    logic is unchanged. Raises on any transport error (caller falls back to the blocking _post, so the
    overnight is never at the mercy of streaming). Used only when CEC_STREAM_DIR is set."""
    p = dict(payload)
    p["stream"] = True
    req = urllib.request.Request((url or VLLM_URL) + path, data=json.dumps(p).encode(),
                                 headers=dict(_CLIENT_HEADERS), method="POST")
    content, reasoning, finish = [], [], None
    saw_frame = False
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        for raw in r:                                        # the response iterates by line
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            saw_frame = True
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ch = (json.loads(data).get("choices") or [{}])[0]
            except Exception:                                # noqa: BLE001 -- skip a malformed frame
                continue
            delta = ch.get("delta") or {}
            cd, rd = delta.get("content"), delta.get("reasoning_content")
            if cd:
                content.append(cd)
                if call:
                    call.delta(cd, "content")
            if rd:
                reasoning.append(rd)
                if call:
                    call.delta(rd, "reasoning")
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    if not saw_frame:
        # the server answered stream=true with a NON-SSE body (degraded broker, error JSON, or an
        # upstream that ignored stream): raise so _chat_json falls back to the blocking _post instead
        # of returning a synthesized EMPTY message that would mis-trigger the empty-content path.
        raise ValueError("non-SSE response to stream=true (no data: frames)")
    return {"choices": [{"message": {"content": "".join(content),
                                     "reasoning_content": "".join(reasoning)},
                         "finish_reason": finish}]}


def available(timeout=3, url=None):
    """True if the server at `url` (default VLLM_URL, i.e. the broker) answers /models (the judge is up).
    Cheap pre-check before wiring. NOTE: broker v2 serves the model CATALOG itself (it answers with
    nothing running and boots backends on demand), so through the broker this is a BROKER-liveness
    check only; talking straight to an upstream it is that model server's liveness."""
    try:
        req = urllib.request.Request((url or VLLM_URL) + "/models", headers={"X-CEC-Client": "CEC-Platform"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return bool(json.load(r).get("data"))
    except Exception:
        return False


def _is_cloud(model):
    """A model that lives off-box behind the `claude -p` CLI, not the broker."""
    m = (model or "").strip().lower()
    return m in CLOUD_MODELS or m.startswith("claude")


def _extract_json_obj(text):
    """Pull the first PARSEABLE balanced JSON object out of arbitrary model text (CLI replies may wrap it
    in prose / a markdown fence despite the instruction). Brace-matching so a nested object survives.
    CSS-2 (audit): a balanced-but-non-JSON brace span in prose BEFORE the real object (e.g. "{not json}")
    must not abort the scan -- on a json.loads failure of one span, keep scanning for the next top-level
    {...} instead of giving up."""
    import re
    start = 0
    while True:
        s = text.find("{", start)
        if s < 0:
            break
        depth, instr, esc = 0, False, False
        for i in range(s, len(text)):
            c = text[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
                continue
            if c == '"':
                instr = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:i + 1])
                    except Exception:                            # noqa: BLE001 -- not JSON, scan onward
                        break
        start = s + 1                                            # advance past this '{' and keep looking
    # no balanced object parsed -> last-resort greedy regex (best-effort on a trailing-truncated reply)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("cloud seat: no JSON object in reply")
    return json.loads(m.group(0))


def _chat_json_cloud(system, user, schema, *, name="out", model=None, effort=None, timeout=None,
                     seat=None, temperature=0.0, attempts=2):
    """Cloud-seat shim: run a cloud Claude model via `claude -p --model <m> [--effort <lvl>]
    --output-format json` and return schema-shaped JSON, so --seats cloud / the seat bake-off can use
    sonnet/opus without the local broker. The CLI occasionally returns a `result` with no parseable JSON
    object (an empty/prose reply) -- RETRY once, and on final failure raise WITH a raw snippet so the
    failure is diagnosable (a bare 'no JSON object' was undebuggable in the bake-off). Raises on
    transport/parse like _chat_json (callers fall back to the deterministic policy).
    NOTE (CSS-4): `temperature` is accepted for signature parity with _chat_json but is a NO-OP on the
    CLI path (the `claude -p` interface exposes no sampling temperature); off-box swarm diversity, if ever
    needed, must come from varying the prompt, not this arg."""
    eff = effort if effort is not None else CLOUD_EFFORT
    prompt = (system + "\n\n" + user + "\n\nRespond with ONLY a single JSON object that conforms to this "
              "JSON Schema (no prose, no markdown fence, no preamble):\n" + json.dumps(schema))
    cmd = [CLOUD_CLI, "-p", "--model", str(model)]
    if eff:
        cmd += ["--effort", str(eff)]
    # DISABLE the agentic tool loop -> a single fast COMPLETION (a seat call is a one-shot json verdict,
    # never an agent). Without this `claude -p` runs the full Claude Code harness and, on a substantial
    # prompt, spends minutes in a tool-using loop (or times out) -- measured: a placement prompt timed out
    # at 600s WITH tools, vs ~5s WITHOUT. Strict improvement for every cloud seat (judge/auditor/planner).
    cmd += ["--disallowedTools",
            "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,WebFetch,WebSearch,Task,TodoWrite,NotebookEdit"]
    cmd += ["--output-format", "json"]
    last = "no attempt"
    for _ in range(max(1, attempts)):
        try:
            r = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                               timeout=timeout or TIMEOUT)
        except subprocess.TimeoutExpired as e:
            raise ValueError("cloud seat timeout: %s" % e)
        except OSError as e:        # CSS-1 (audit): a spawn failure (missing/!x CLI) must not escape the
            last = "spawn: %s" % e  # retry loop -- record it and fall through to the unified raise below
            continue
        if r.returncode != 0:
            last = "exit %s: %s" % (r.returncode, (r.stderr or "")[:160])
            continue
        # `--output-format json` wraps the reply in a result envelope; fall back to raw stdout if not.
        text = r.stdout
        try:
            env = json.loads(r.stdout)
            if isinstance(env, dict) and "result" in env:
                text = env["result"]
        except Exception:                                        # noqa: BLE001
            pass
        try:
            return _extract_json_obj(text)
        except Exception as e:                                   # noqa: BLE001 -- retry, then surface raw
            last = "%s | raw=%r" % (e, (text or "")[:160])
    raise ValueError("cloud seat: no schema JSON after %d attempts (%s)" % (max(1, attempts), last))


def _chat_json(system, user, schema, *, name="out", temperature=0.0, max_tokens=None, timeout=None,
               model=None, url=None, nothink=False, seat=None, effort=None):
    """One guided-JSON call constrained to `schema` -> the parsed dict. Raises on any transport/parse
    error (callers wrap this and fall back to the deterministic policy). `temperature` > 0 gives a
    diverse reply for swarm replicas. `url`/`model` target a per-tier server (manager vs worker).
    Two bench-verified guards (2026-06-09): models in _FLOOR_MODELS get the sampling floors (the
    M2.7 decode-loop hazard), and an EMPTY `content` with the answer stranded in `reasoning_content`
    (a thinking overrun) is recovered by a SCRIBE transcription call instead of raising."""
    mdl = model or MODEL
    if _is_cloud(mdl):       # cloud seat -> claude CLI (no broker, no json_schema grammar)
        return _chat_json_cloud(system, user, schema, name=name, model=mdl, timeout=timeout,
                                seat=seat, temperature=temperature, effort=effort)
    payload = {
        "model": mdl,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        # None -> the worker budget (single chokepoint; manager callers pass MANAGER_MAX_TOKENS)
        "max_tokens": max_tokens if max_tokens is not None else WORKER_MAX_TOKENS,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": name, "schema": schema, "strict": True}},
    }
    if nothink:
        # Qwen3-VL / Qwen3.6 thinking models overrun a grammar-constrained reply and return EMPTY
        # content (measured 100% of schema'd calls); disable thinking when judging structured JSON.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if mdl in _FLOOR_MODELS:
        payload["temperature"] = max(temperature, _FLOOR_TEMP)
        payload["presence_penalty"] = _FLOOR_PRESENCE
    # Transport: when CEC_STREAM_DIR is set (a dashboard run), STREAM via SSE and tee per-seat deltas
    # to the recorder; on any streaming error fall back to the blocking POST so a model call never
    # depends on streaming working. When unset, this is byte-identical to the old blocking path.
    import cec_seat_stream as _stream
    resp = None
    if _stream.enabled():
        seat_name = seat or _SEAT.get() or mdl
        call = _stream.start(seat_name, model=mdl, role=name,
                             prompt_chars=len(system) + len(user), temperature=payload["temperature"])
        try:
            resp = _post_stream("/chat/completions", payload, timeout=timeout, url=url, call=call)
            call.end(ok=True)
        except Exception as e:                               # noqa: BLE001 -- degrade to blocking
            call.error(e)
            resp = None
    if resp is None:
        resp = _post("/chat/completions", payload, timeout=timeout, url=url)
    msg = resp["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:
        trace = (msg.get("reasoning_content") or "").strip()
        if trace and _AUTO_SCRIBE:
            return _scribe_json(trace, schema, name=name, model=mdl, url=url, timeout=timeout, seat=seat)
        raise ValueError("empty content (thinking overrun, no recoverable trace)")
    return json.loads(content)


SCRIBE_SYSTEM = (
    "You are a technical EDITOR. The user message is a reasoning trace that already contains a "
    "final conclusion. Transcribe ONLY that final conclusion as one JSON object conforming to the "
    "required schema. Do NOT re-derive, re-reason, extend, or second-guess the trace; extract and "
    "transcribe its answer exactly."
)


def _scribe_json(trace, schema, *, name="out", model=None, url=None, timeout=None, seat=None):
    """SCRIBE half of the bench-verified miner->scribe protocol (2026-06-09, 6-run bench): feed the
    harvested reasoning trace back to the SAME model as an EDITOR task at temp ~0.35 + presence
    penalty (the verified anti-loop knobs) under the json_schema grammar -> the JSON the miner call
    failed to emit. The trace is TAIL-capped to fit the 16k manager context."""
    payload = {
        "model": model or MODEL,
        "messages": [{"role": "system", "content": SCRIBE_SYSTEM},
                     {"role": "user", "content": "REASONING TRACE:\n" + trace[-_SCRIBE_TRACE_CHARS:]}],
        "temperature": max(0.35, _FLOOR_TEMP),
        "presence_penalty": _FLOOR_PRESENCE,
        "max_tokens": _SCRIBE_MAX_TOKENS,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": name, "schema": schema, "strict": True}},
    }
    import cec_seat_stream as _stream
    resp = None
    if _stream.enabled():
        call = _stream.start(seat or _SEAT.get() or (model or MODEL), model=model or MODEL,
                             role="scribe", prompt_chars=len(trace), temperature=payload["temperature"])
        try:
            resp = _post_stream("/chat/completions", payload, timeout=timeout, url=url, call=call)
            call.end(ok=True)
        except Exception as e:                               # noqa: BLE001 -- degrade to blocking
            call.error(e)
            resp = None
    if resp is None:
        resp = _post("/chat/completions", payload, timeout=timeout, url=url)
    content = (resp["choices"][0]["message"].get("content") or "").strip()
    if not content:
        raise ValueError("scribe call also returned empty content")
    return json.loads(content)


def chat_verdict(system, user, *, timeout=None, temperature=0.0, url=None, model=None, max_tokens=None,
                 seat=None):
    """One guided-JSON manager-verdict call -> {action, reason}. `max_tokens` defaults to the worker
    budget; manager-tier callers pass MANAGER_MAX_TOKENS so a thinking model's reasoning fits."""
    return _chat_json(system, user, VERDICT_SCHEMA, name="verdict", seat=seat,
                      temperature=temperature, timeout=timeout, url=url, model=model, max_tokens=max_tokens)


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
            v = chat_verdict(SYSTEM, user, url=MANAGER_URL, model=MANAGER_MODEL, timeout=MANAGER_TIMEOUT,
                             max_tokens=MANAGER_MAX_TOKENS, seat="manager")
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
#  TRUE AGENT SWARM -- the manager + worker + dispatch tiers as CONCURRENT, PERSPECTIVE-DIVERSE,
#  VOTED panels of local agents (the batched vLLM serves them in parallel). Wires into
#  cec_router.route(manager=, worker=) and cec_dispatch.agent_route(tiers=).
# ===========================================================================
# Each manager decision is judged by a PANEL of agents, each with a DISTINCT LENS, then voted --
# diversity catches failure modes a single judge misses, and the vote is conservative (an `accept`
# needs a true majority AND a gate-passing candidate; disagreement falls to the safer action).
MANAGER_LENSES = [
    ("safety", "You are the SAFETY lens of a routing MANAGER panel. Judge ONLY the hard safety gates: "
               "choose `accept` IFF the best candidate has gates_pass=true. This includes every "
               "configured DRC and unconnected-ratline gate. If false, choose `repair`. Never weigh "
               "cosmetics. Reply JSON {action,reason} (reason < 25 words)."),
    ("finishing", "You are the FINISHING lens of a routing MANAGER panel. A finishing diagnosis is "
                  "advisory only. Choose `accept` only when gates_pass=true. If gates_pass=false, "
                  "choose `repair`; do not waive the failed gate. JSON {action,reason}."),
    ("progress", "You are the PROGRESS lens of a routing MANAGER panel. Judge the trajectory across "
                 "iterations: if drc/unconnected are improving, `repair` (keep going); if they have "
                 "STALLED for two or more iterations with no improvement, `escalate` (structural re-plan); "
                 "if the best candidate already passes the gates cleanly, `accept`. JSON {action,reason}."),
]


def _escalate_corroborated(drc_trail, loci):
    """Deterministic guard so the structural lens can't over-escalate (verify pattern): escalate is
    justified by the METRICS, not just a lens's word -- the DRC has STALLED (>=3 identical recent
    values, FR's deterministic no-progress signature) OR a DRC locus shorts two DIFFERENT functional
    nets (a real cross-net fault more routing won't fix). A still-improving / merely-unrouted board
    does NOT corroborate -> the escalate is downgraded to repair."""
    import re
    trail = [d for d in (drc_trail or []) if isinstance(d, (int, float))]
    for lc in (loci or []):
        nets = re.findall(r"\[(/[^\]]+|\+[0-9A-Za-z_]+)\]", str(lc.get("where", "")))
        if len({n for n in nets if n != "GND"}) >= 2:
            return True
    return len(trail) >= 3 and len(set(trail[-3:])) == 1


def _vote(votes, valid_actions, *, accept_ok, accept_word="accept", escalate_word="escalate",
          repair_word="repair", escalate_lens=None, escalate_ok=True):
    """DIMENSION-AWARE aggregation of (lens, action, reason) votes -> (action, tally, picks). Each lens
    judges a DIFFERENT dimension, so a naive majority is wrong (only ONE lens is qualified to call
    escalate). Rules: (1) the `escalate_lens` is AUTHORITATIVE on escalate -- if it (or a majority)
    escalates, escalate, since it's the only lens judging structural/stall merit; (2) else accept only
    when accept_ok AND >=1 lens accepts AND none escalate AND accept is not outvoted by repair (the
    SAFETY lens owns the accept gate); (3) else repair. Conservative: ties favor the safer action."""
    valid = []
    for (ln, a, r) in votes:
        if a == accept_word and not accept_ok:
            a = repair_word          # SAFETY: never accept a non-gate-passing candidate
        if a == escalate_word and not escalate_ok:
            a = repair_word          # VERIFY: an uncorroborated escalate (lens over-fired) -> repair
        if a in valid_actions:
            valid.append((ln, a, r))
    if not valid:
        return None, Counter(), ""
    tally = Counter(a for (_, a, _) in valid)
    n = len(valid)
    by = {ln: a for (ln, a, _) in valid}
    picks = "; ".join(f"{ln}:{a}" for (ln, a, _) in valid)
    if (escalate_lens and by.get(escalate_lens) == escalate_word) or tally.get(escalate_word, 0) > n / 2:
        return escalate_word, tally, picks
    if accept_ok and tally.get(accept_word, 0) >= 1 and tally.get(escalate_word, 0) == 0 \
            and tally.get(accept_word, 0) >= tally.get(repair_word, 0):
        return accept_word, tally, picks
    return repair_word, tally, picks


def _panel(user_or_fn, lenses, schema, *, name, temps=None, max_workers=None, url=None, model=None,
           timeout=None, max_tokens=None, seat=None, effort=None):
    """Fire one judge per lens CONCURRENTLY at the (per-tier) server. `user_or_fn` is a user string
    (same for all) or a fn(lens_name)->user. `seat` is the panel's recorder section base; each member
    records under `<seat>:<lens>` so every panel member's thoughts get their own dashboard section.
    Returns [(lens_name, dict|None), ...]."""
    temps = temps or {}

    def one(idx_lens):
        idx, (lname, lsys) = idx_lens
        user = user_or_fn(lname) if callable(user_or_fn) else user_or_fn
        member_seat = ("%s:%s" % (seat, lname)) if seat else lname
        try:
            return (lname, _chat_json(lsys, user, schema, name=name, temperature=temps.get(idx, 0.0),
                                      url=url, model=model, timeout=timeout, max_tokens=max_tokens,
                                      seat=member_seat, effort=effort))
        except Exception as e:
            return (lname, {"error": type(e).__name__})

    with ThreadPoolExecutor(max_workers=max_workers or len(lenses)) as ex:
        return list(ex.map(one, list(enumerate(lenses))))


def make_manager_swarm(spec, *, panel=3, verbose=False, model=None, url=None, effort=None):
    """A TRUE manager SWARM for cec_router.route's manager= slot: `panel` concurrent local agents,
    each a distinct lens (safety / finishing / progress, cycled with temperature for replicas), voting
    on accept/repair/escalate. Fail-safe -> default_manager; cannot accept a non-gate-passing board.
    `model`/`url` override the broker default: pass a CLOUD model name (e.g. 'opus') and _chat_json
    auto-routes the panel through the `claude -p` shim (cec_seats picks it per the residency policy)."""
    import cec_router
    lenses = [MANAGER_LENSES[i % len(MANAGER_LENSES)] for i in range(max(1, panel))]
    temps = {i: (0.0 if i < len(MANAGER_LENSES) else 0.4) for i in range(len(lenses))}
    mgr_model, mgr_url = (model or MANAGER_MODEL), (url or MANAGER_URL)

    def manager(region, scored, history):
        try:
            user = _context(region, scored, history, spec)
            best = scored[0][1] if scored else None
            results = _panel(user, lenses, VERDICT_SCHEMA, name="verdict", temps=temps,
                             url=mgr_url, model=mgr_model, timeout=MANAGER_TIMEOUT,
                             max_tokens=MANAGER_MAX_TOKENS, seat="manager", effort=effort)
            votes = [(ln, (d or {}).get("action"), str((d or {}).get("reason", ""))) for ln, d in results]
            trail = [h["best"].drc for h in (history or []) if h.get("best") is not None] \
                + ([best.drc] if best is not None else [])
            esc_ok = _escalate_corroborated(trail, [])
            action, tally, picks = _vote(votes, ("accept", "repair", "escalate"),
                                         accept_ok=bool(best is not None and best.gates_pass),
                                         escalate_lens="progress", escalate_ok=esc_ok)
            if action is None:
                raise RuntimeError("no valid panel vote")
            # MANAGER-tier finer-grained repair: attach a part NUDGE if a part-congestion locus exists.
            edit = None
            if action == "repair" and scored:
                try:
                    nudge = cec_router.targeted_repair(scored[0][0].board, tier="manager")
                except Exception:
                    nudge = None
                if nudge:
                    edit = nudge
                    if verbose:
                        print(f"[swarm-mgr] +NUDGE {nudge['why']}")
            if verbose:
                print(f"[swarm-mgr] {getattr(region,'name','all')} panel={dict(tally)} -> {action}")
            return cec_router.Verdict(action, f"panel {dict(tally)} -> {action} | {picks}"[:240],
                                      tier=f"local-swarm-mgr({sum(tally.values())})", edit=edit)
        except Exception as e:
            fb = cec_router.default_manager(region, scored, history, spec)
            fb.tier = (fb.tier or "") + f" (swarm-fallback:{type(e).__name__})"
            return fb

    return manager


WORKER_SYS = (
    "You are a WORKER in a routing REPAIR swarm. The manager asked to repair a route whose hard gate "
    "failed (unrouted ratlines). Given the current Freerouting effort and the failure reason, propose "
    "NEW effort to clear it: more routing passes and/or more optimization seconds. Be decisive but "
    "bounded: passes 1..60, opt_time 1..120, and at least a real increase over current. Reply JSON "
    "{passes:int, opt_time:int, reason}."
)
WORKER_SCHEMA = {
    "type": "object",
    "properties": {"passes": {"type": "integer"}, "opt_time": {"type": "integer"},
                   "reason": {"type": "string"}},
    "required": ["passes", "opt_time", "reason"], "additionalProperties": False,
}


def make_worker_swarm(spec, *, fanout=3, verbose=False, model=None, url=None, effort=None):
    """A TRUE worker SWARM for cec_router.route's worker= slot: `fanout` concurrent agents each propose
    a repair effort (passes/opt_time), aggregated to a CONSENSUS (mean, bounded, > current). Fail-safe
    -> default_worker. `model`/`url` override the broker default: a CLOUD model name (e.g. 'sonnet')
    auto-routes the workers through the `claude -p` shim (cec_seats picks it per the residency policy)."""
    import cec_router
    wrk_model, wrk_url = (model or WORKER_MODEL), (url or WORKER_URL)

    def worker(region, verdict, state, history):
        # WORKER-tier finer-grained repair: try a TARGETED RIP-UP at the worst real DRC locus on the
        # current candidate first (reserve the conflict so FR re-routes that net), before a global bump.
        cand = getattr(state, "last_candidate", None)
        if cand and os.path.isfile(cand):
            try:
                ed = cec_router.targeted_repair(cand, tier="worker")
            except Exception:
                ed = None
            if ed:
                if verbose:
                    print(f"[swarm-wrk] RIP-UP {ed['why']}")
                return cec_router.Verdict("repair", f"swarm worker RIP-UP {ed['why']}",
                                          tier="local-swarm-wrk:ripup", edit=ed)
        cur_p, cur_o = int(state.fr.get("passes", 10)), int(state.fr.get("opt_time", 30))
        try:
            user = json.dumps({"current_passes": cur_p, "current_opt_time": cur_o,
                               "gate_failure_reason": str(verdict.reason)[:200],
                               "iteration": len(history) + 1})

            def one(i):
                try:
                    r = _chat_json(WORKER_SYS, user, WORKER_SCHEMA, name="effort", seat="worker:%d" % i,
                                   temperature=(0.0 if i == 0 else 0.5), model=wrk_model, url=wrk_url,
                                   effort=effort)
                    return (min(max(int(r["passes"]), 1), 60), min(max(int(r["opt_time"]), 1), 120))
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=fanout) as ex:
                props = [p for p in ex.map(one, range(fanout)) if p]
            if not props:
                raise RuntimeError("no worker proposal")
            P = max(cur_p + 1, min(60, round(sum(p for p, _ in props) / len(props))))
            O = max(cur_o + 1, min(120, round(sum(o for _, o in props) / len(props))))
            if verbose:
                print(f"[swarm-wrk] {len(props)} proposals -> passes={P} opt={O}")
            return cec_router.Verdict("repair", f"swarm worker({len(props)}) consensus passes={P} opt={O}",
                                      tier=f"local-swarm-wrk({len(props)})",
                                      edit={"type": "fr_params", "set": {"passes": P, "opt_time": O}})
        except Exception as e:
            fb = cec_router.default_worker(region, verdict, state, history, spec)
            fb.tier = (fb.tier or "") + f" (swarm-fallback:{type(e).__name__})"
            return fb

    return worker


DISPATCH_LENSES = [
    ("safety", "You are the SAFETY lens of a candidate-judge SWARM tier. `accept` IFF the best candidate "
               "has gates_pass=true, including all configured DRC and ratline gates; else "
               "`request_more` (route harder). "
               "Reply JSON {action,reason}."),
    ("finishing", "You are the FINISHING lens. A finishing diagnosis cannot waive gates_pass. "
                  "Choose `accept` only when gates_pass=true; otherwise choose `request_more`. "
                  "JSON {action,reason}."),
    ("structural", "You are the STRUCTURAL lens. Choose `escalate` (defer UP a tier for a re-plan) ONLY "
                   "when more Freerouting passes won't help: the best candidate has a REAL fault between "
                   "two DIFFERENT functional nets (a genuine short/clearance per the gate_note -- NOT a "
                   "finishing LOGO/shield/same-footprint item), OR drc/unconnected have NOT improved "
                   "across the prior `history` rounds (stalled). Otherwise `request_more` (still improving) "
                   "or `accept` only when gates_pass=true. Budget-exhaustion is handled by the loop, "
                   "not you -- escalate on the MERITS. JSON {action,reason}."),
]
DISPATCH_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["accept", "request_more", "escalate"]},
                   "reason": {"type": "string"}},
    "required": ["action", "reason"], "additionalProperties": False,
}


def make_dispatch_swarm_tier(*, panel=3, tier_name="local-haiku-swarm", verbose=False):
    """A cec_dispatch decide(JudgeContext)->Verdict SWARM tier (the parallel 'Haiku swarm' rung of
    agent_route): `panel` concurrent diverse-lens agents vote accept/request_more/escalate. Fail-safe
    -> cec_dispatch.det_haiku."""
    import cec_dispatch
    lenses = [DISPATCH_LENSES[i % len(DISPATCH_LENSES)] for i in range(max(1, panel))]
    temps = {i: (0.0 if i < len(DISPATCH_LENSES) else 0.4) for i in range(len(lenses))}

    def decide(ctx):
        try:
            cands = ctx.candidates or []
            best = cands[0] if cands else None
            hist = [{"round": i, "drc": h.get("best_drc"), "unconnected": h.get("best_unconnected"),
                     "verdict": h.get("verdict")} for i, h in enumerate(ctx.history or [])]
            user = json.dumps({"candidates_best_first": cands[:4], "budget_left": ctx.budget_left,
                               "history_drc_trail": hist, "gate_note": ctx.gate_note}, default=str)
            results = _panel(user, lenses, DISPATCH_SCHEMA, name="verdict", temps=temps,
                             url=MANAGER_URL, model=MANAGER_MODEL, timeout=MANAGER_TIMEOUT,
                             max_tokens=MANAGER_MAX_TOKENS, seat="dispatch")
            votes = [(ln, (d or {}).get("action"), str((d or {}).get("reason", ""))) for ln, d in results]
            trail = [h.get("best_drc") for h in (ctx.history or [])] + [(best or {}).get("drc")]
            esc_ok = _escalate_corroborated(trail, (best or {}).get("drc_loci"))
            action, tally, picks = _vote(votes, ("accept", "request_more", "escalate"),
                                         accept_ok=bool(best and best.get("gates_pass")),
                                         repair_word="request_more", escalate_lens="structural",
                                         escalate_ok=esc_ok)
            if action is None:
                return cec_dispatch.det_haiku(ctx)
            if verbose:
                print(f"[swarm-tier:{tier_name}] panel={dict(tally)} -> {action}")
            if action == "accept":
                return cec_dispatch.Verdict("accept", seed=(best or {}).get("seed"),
                                            reason=f"swarm {dict(tally)} | {picks}"[:200], tier=tier_name)
            if action == "escalate":
                return cec_dispatch.Verdict("escalate", reason=f"swarm {dict(tally)}"[:200], tier=tier_name)
            opt = (ctx.history[-1].get("params", {}).get("opt_time", 12) if ctx.history else 12)
            return cec_dispatch.Verdict("request_more", params={"opt_time": int(opt * 1.6)},
                                        reason=f"swarm {dict(tally)} | {picks}"[:200], tier=tier_name)
        except Exception:
            return cec_dispatch.det_haiku(ctx)

    decide.tier_name = tier_name
    return decide


PLACEMENT_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["accept", "refine", "escalate"]},
                   "reason": {"type": "string"}},
    "required": ["action", "reason"], "additionalProperties": False,
}
PLACEMENT_LENSES = [
    ("constraints", "You are the CONSTRAINTS lens of a PLACEMENT panel. The board's HARD placement "
                    "constraints (Kelvin sense IC within 5mm of its shunt; every IC's power/GND pin able "
                    "to escape; shunt inline in the J_IN->J_OUT corridor; RJ-45/DETECT/CAN pinmap) MUST "
                    "hold. Given hard_fails/strong_fails, choose `accept` if there are NO hard fails, else "
                    "`refine` (a local placement-refinement pass can fix it). JSON {action,reason}."),
    ("density", "You are the DENSITY/DFM lens of a PLACEMENT panel. Judge courtyard_overlaps (MUST be 0 -- "
                "a real short risk) and the placement density. `refine` if courtyard_overlaps>0 or the "
                "layout is clearly too dense to route; else `accept`. JSON {action,reason}."),
    ("routability", "You are the ROUTABILITY/structural lens of a PLACEMENT panel. Will this placement "
                    "ROUTE? `escalate` (regenerate a DIFFERENT placement candidate, or change the design) "
                    "ONLY if it is structurally unroutable -- e.g. a sense IC boxed so its power/GND can't "
                    "escape (hard_fail ic-power-ground-connected), or no channel for the control->sense "
                    "spine. Otherwise `refine` (locally fixable) or `accept` (clean). JSON {action,reason}."),
]


def make_placement_swarm(*, panel=3, verbose=False):
    """A PLACEMENT swarm -- the SAME diverse-lens voted panel idea applied to PLACEMENT candidates.
    decide(metrics)->{action,tally,reason}: judges a placement's constraint-check metrics ->
      accept   (placement is good; route it),
      refine   (a local placement-refinement pass; the routing analog of 'repair'),
      escalate (regenerate a DIFFERENT placement candidate [lever 1] or a human design change [lever 2]).
    Dimension-aware (routability owns escalate, corroborated by a real hard_fail; constraints owns accept,
    only with no hard_fails). Fail-safe to a deterministic call on error."""
    lenses = [PLACEMENT_LENSES[i % len(PLACEMENT_LENSES)] for i in range(max(1, panel))]
    temps = {i: (0.0 if i < len(PLACEMENT_LENSES) else 0.4) for i in range(len(lenses))}

    def decide(metrics):
        hard = metrics.get("hard_fails") or []
        try:
            user = json.dumps(metrics, default=str)
            results = _panel(user, lenses, PLACEMENT_SCHEMA, name="verdict", temps=temps,
                             url=MANAGER_URL, model=MANAGER_MODEL, timeout=MANAGER_TIMEOUT,
                             max_tokens=MANAGER_MAX_TOKENS, seat="placement")
            votes = [(ln, (d or {}).get("action"), str((d or {}).get("reason", ""))) for ln, d in results]
            action, tally, picks = _vote(votes, ("accept", "refine", "escalate"),
                                         accept_ok=(not hard), repair_word="refine",
                                         escalate_lens="routability", escalate_ok=bool(hard))
            if action is None:
                action = "refine"
            if verbose:
                print(f"[swarm-place] {metrics.get('board','?')} {dict(tally)} -> {action}")
            return {"action": action, "tally": dict(tally), "reason": picks[:200]}
        except Exception as e:
            return {"action": ("escalate" if hard else "accept"),
                    "reason": f"fallback ({type(e).__name__})", "tally": {}}

    return decide


def differentiated_test(*, panel=3, verbose=True):
    """PROVE (or disprove) that the swarm makes DISTINCT, correct calls -- the open question from the
    Opus-team stress test (identical-outcome boards couldn't show it). Feeds the dispatch swarm three
    contexts whose CORRECT answer differs and checks it returns accept / request_more / escalate:
      * accept-now           : clean, gate-passing, drc=0           -> accept
      * real-repair          : a hard gate fails, but improving      -> request_more
      * structural-escalate  : gates 'pass' yet a REAL cross-net short, STALLED at drc=40 -> escalate
    Returns {scenario: {expected, got, ok, reason}}. Needs the vLLM server up."""
    import cec_dispatch
    GN = cec_dispatch.GATE_NOTE
    tier = make_dispatch_swarm_tier(panel=panel)

    def cand(**kw):
        b = dict(seed=0, params={}, board="b", drc=0, unconnected=0, kelvin_ok=True, diffpair_ok=True,
                 gates_pass=True, tracks=500, vias=80, drc_types={}, drc_loci=[], unconn_nets=[])
        b.update(kw)
        return b

    scen = {
        "accept-now": ("accept", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN, history=[],
            candidates=[cand(gates_pass=True)])),
        "real-repair": ("request_more", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN,
            history=[{"verdict": "request_more", "best_drc": 22, "best_unconnected": 26}],   # improving 26->14
            candidates=[cand(drc=12, unconnected=14, kelvin_ok=False, gates_pass=False,
                             drc_types={"clearance": 12},
                             drc_loci=[{"where": "unrouted sense pair SENSEC1_HI/SENSEC1_LO", "type": "clearance"}],
                             unconn_nets=["/SENSEC1_HI", "/SENSEC1_LO"])])),
        "structural-escalate": ("escalate", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN,
            history=[{"verdict": "request_more", "best_drc": 40, "best_unconnected": 8},
                     {"verdict": "request_more", "best_drc": 40, "best_unconnected": 8},
                     {"verdict": "request_more", "best_drc": 40, "best_unconnected": 8}],   # STALLED at 40
            candidates=[cand(drc=40, unconnected=8, gates_pass=False, drc_types={"shorting_items": 40},
                             drc_loci=[{"where": "clearance: +3V3 track to /USB_DP via < 0.1mm [+3V3] [/USB_DP]",
                                        "type": "shorting_items"}], unconn_nets=[])])),
    }
    out = {}
    for name, (exp, ctx) in scen.items():
        v = tier(ctx)
        ok = (v.action == exp)
        out[name] = {"expected": exp, "got": v.action, "ok": ok, "reason": str(v.reason)[:160]}
        if verbose:
            print(f"  [{'OK' if ok else 'XX'}] {name:21s} expected={exp:13s} got={v.action:13s}  {str(v.reason)[:80]}")
    n = sum(1 for r in out.values() if r["ok"])
    if verbose:
        print(f"  -> {n}/{len(out)} distinct scenarios judged correctly by the local swarm")
    return out


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


# ===========================================================================
#  CORPUS-FIT REVIEWER (Thrust A, deep tier) -- a LOW-FREQUENCY, OUT-OF-LOOP advisory pass on the
#  REVIEWER-tier model (default cec-manager-fast = gpt-oss-120b per the 2026-06-09 bench; set
#  CEC_VLLM_REVIEWER_MODEL=deepseek-v4-flash for the DeepSeek-V4-Flash deep auditor, which
#  auto-recovers via miner->scribe -- M2.7 retired from this pipeline, owner 2026-06-11). Runs ONCE per fully-routed board, AFTER route() finalizes + the hard gates +
#  independent DRC have decided correctness. It feeds the model a per-FAMILY statistics DIGEST distilled
#  from the accumulated DecisionLog corpus + the freshly-routed board's log, and asks "does this board
#  FIT the patterns its same-family precedents embody?" -- producing a precedent-referenced critique.
#  ALL numeric work (robust MAD/median z-scores, envelope, direction, gate-flips) is done in Python
#  FIRST; the slow thinking model only reasons over the compact pre-computed evidence (never hand math).
#  FAIL-SAFE + ADD-ONLY: any error/timeout/thin-corpus -> a benign no_opinion / insufficient_precedent
#  result; it is a SIDECAR advisory artifact, never fed back into route()'s accept/repair/escalate path
#  or the hard gates, and a post-parse CODE CLAMP suppresses any "fits" on a gate-false board. The
#  per-region gate stays on the fast 30B worker; this is the deep reviewer only.
# ===========================================================================
import re as _re
import glob as _glob
from statistics import median as _median

_CF_METRICS = ["objective", "drc", "unconnected", "tracks", "vias", "length", "elapsed_s", "decisions"]
_CF_NOTE_K = _re.compile(r"K=(\d+)")
_CF_NOTE_FR = _re.compile(r"fr=\{[^}]*'passes':\s*(\d+)[^}]*'opt_time':\s*(\d+)")

CORPUS_FIT_SCHEMA = json.loads(r'''{"type":"object","additionalProperties":false,"required":["fit_classification","recommendation","confidence","family","headline","gate_consistency","metric_band","trajectory","residual_treatment","outlier_metrics","matched_precedents","violated_precedents","concerns","critique"],"properties":{"fit_classification":{"type":"string","enum":["in_distribution","fits_with_concerns","outlier","gate_regression","insufficient_precedent","no_opinion"]},"recommendation":{"type":"string","enum":["accept_as_consistent","review_recommended","investigate_regression","no_opinion"]},"confidence":{"type":"string","enum":["low","medium","high"]},"family":{"type":"string"},"headline":{"type":"string","maxLength":200},"gate_consistency":{"type":"object","additionalProperties":false,"required":["kelvin_ok","diffpair_ok","gates_pass","flips"],"properties":{"kelvin_ok":{"type":"string","enum":["matches_family","improved_vs_family","regressed_vs_family","no_family_precedent"]},"diffpair_ok":{"type":"string","enum":["matches_family","improved_vs_family","regressed_vs_family","no_family_precedent"]},"gates_pass":{"type":"string","enum":["matches_family","improved_vs_family","regressed_vs_family","no_family_precedent"]},"flips":{"type":"array","maxItems":4,"items":{"type":"string","maxLength":200}}}},"metric_band":{"type":"string","enum":["in_band","better_than_band","worse_than_band","no_band"]},"trajectory":{"type":"object","additionalProperties":false,"required":["shape","coherent","detail"],"properties":{"shape":{"type":"string","enum":["converged","stable_plateau","repair_then_escalate","thrash","gave_up_early","single_shot","no_candidate","unknown"]},"coherent":{"type":"boolean"},"detail":{"type":"string","maxLength":400}}},"residual_treatment":{"type":"string","enum":["consistent","more_lenient_than_family","more_aggressive_than_family","novel_residual","na"]},"outlier_metrics":{"type":"array","maxItems":10,"items":{"type":"object","additionalProperties":false,"required":["metric","new_value","family_median","robust_z","direction","verdict"],"properties":{"metric":{"type":"string","enum":["objective","drc","unconnected","tracks","vias","length","elapsed_s","decisions"]},"new_value":{"type":"number"},"family_median":{"type":"number"},"robust_z":{"type":"number"},"direction":{"type":"string","enum":["improvement","regression","neutral"]},"verdict":{"type":"string","enum":["in_band","mild_outlier","strong_outlier","envelope_breach"]}}}},"matched_precedents":{"type":"array","maxItems":8,"items":{"type":"object","additionalProperties":false,"required":["precedent_id","axis","note"],"properties":{"precedent_id":{"type":"string"},"axis":{"type":"string","enum":["gate","metric","trajectory","residual","objective"]},"note":{"type":"string","maxLength":240}}}},"violated_precedents":{"type":"array","maxItems":8,"items":{"type":"object","additionalProperties":false,"required":["precedent_id","axis","note"],"properties":{"precedent_id":{"type":"string"},"axis":{"type":"string","enum":["gate","metric","trajectory","residual","objective"]},"note":{"type":"string","maxLength":240}}}},"concerns":{"type":"array","maxItems":10,"items":{"type":"object","additionalProperties":false,"required":["severity","kind","detail"],"properties":{"severity":{"type":"string","enum":["info","low","medium","high"]},"kind":{"type":"string","enum":["gate_regression","metric_outlier","best_regression","novel_residual","lenient_residual","convergence_thrash","environment_only","suspiciously_better","insufficient_data"]},"detail":{"type":"string","maxLength":300}}}},"critique":{"type":"string","maxLength":1400}}}''')

CORPUS_FIT_SYSTEM = (
    "You are the CORPUS-FIT REVIEWER for the CEC power-telemetry PCB auto-routing pipeline. You run "
    "ONCE per fully-routed board, on a slow deep-reasoning local model, AFTER the fast per-region "
    "routing loop and the independent DRC have already decided correctness. You are an AUDITOR, not a "
    "gatekeeper. Take all the reasoning time you need in your thinking block, then emit exactly one JSON object.\n\n"
    "YOUR JOB: given (a) a per-FAMILY statistics DIGEST distilled from the accumulated corpus of past "
    "routes, (b) a SUMMARY + decision-trajectory of one freshly-routed board, (c) a PRE-COMPUTED "
    "EVIDENCE block (robust-z scores, envelope flags, direction labels, gate-flip flags, "
    "regression-vs-best deltas -- all already calculated in Python), and (d) a few citable same-family "
    "exemplar trajectories -- judge whether this board's final metrics AND its decision trajectory FIT "
    "the patterns its SAME-FAMILY precedents embody, and write a precedent-referenced critique.\n\n"
    "CRITICAL BOUNDARIES:\n"
    "1. You are ADVISORY and NON-BLOCKING. The hard safety gates (kelvin_ok, diffpair_ok -> gates_pass) "
    "and the independent DRC own correctness and already ran BEFORE you. You NEVER endorse overriding a "
    "failed gate, NEVER widen the safety envelope, NEVER recommend shipping an unsafe board, NEVER relax "
    "a ratified constraint. You only ADD a precedent-consistency opinion a human reads.\n"
    "2. Judge ONLY within the board's own FAMILY (eps-8pin / pcie-8pin-2port / pcie-8pin-3port / failed). "
    "Metrics differ enormously across families (an eps-8pin objective ~4257 vs a pcie-2port ~20654 is "
    "NORMAL family difference, NOT a defect). Never compare a board to a different family's numbers.\n"
    "3. The EVIDENCE block is AUTHORITATIVE -- computed deterministically. Do NOT recompute statistics "
    "by hand. Reason about what the numbers MEAN, weigh them together, and decide.\n\n"
    "WHAT THE DATA MEANS: A DecisionLog has `final` (gates_pass, kelvin_ok, diffpair_ok, drc, "
    "unconnected, tracks, vias, length, objective, and `reasons` naming what blocked) and an ordered "
    "trajectory of per-iteration entries (chosen-candidate metrics + verdict action/tier/reason + the "
    "Freerouting effort fr={passes,opt_time} and rip-up count K). gates_pass is the complete configured "
    "contract: Kelvin topology, differential pairs, DRC, and unconnected-ratline completion. A failed "
    "gate cannot be waived as finishing or cosmetic by this reviewer. objective "
    "is a ranking score, LOWER is better, only for gate-passing candidates. `repair` bumps Freerouting "
    "effort; `escalate` after a Kmax stall is the SANCTIONED structural re-plan (repair x N then "
    "escalate-on-stall is COHERENT).\n\n"
    "HOW TO JUDGE FIT, in priority order:\n"
    "1. GATE CONSISTENCY (dominates). Compare each hard gate to the family modal. A flip to WORSE (an "
    "eps-8pin returning kelvin_ok=false where every eps peer is true) is the highest-severity non-fit -> "
    "fit_classification=gate_regression, recommendation at most investigate_regression, NEVER accept. A "
    "flip to BETTER (a pcie family that historically failed kelvin now passes it) is a notable POSITIVE "
    "deviation -- say whether it looks like real progress or a scope/measurement change, recommend a "
    "human confirm; it is NOT a violation.\n"
    "2. METRIC BAND (robust outliers). Use the precomputed robust_z + envelope flags. |z|<=3 in-band; "
    "3<|z|<=6 mild; |z|>6 strong. DIRECTION MATTERS -- every metric is lower-is-better, so an outlier in "
    "the GOOD direction (drc BELOW the family minimum) is a candidate IMPROVEMENT, not a regression; "
    "never flag a better board as a defect (metric_band=better_than_band, flag for confirmation). "
    "IMPORTANCE: drc/unconnected/objective + the gate flags reflect real layout quality. tracks/vias/"
    "length are secondary structural variation. elapsed_s and decisions are ENVIRONMENT/PROCESS signals "
    "(wall-clock + loop thrash) -- an outlier there is a convergence/thrash or environment_only concern, "
    "NEVER a layout regression.\n"
    "3. TRAJECTORY COHERENCE. Read the entries in order. Coherent = monotone-ish improvement, or a "
    "stable plateau then accept, or repair x N -> escalate-after-stall. Incoherent = drc/unconnected "
    "oscillating; Freerouting effort + rip-up K ramping across many iterations with ZERO metric movement "
    "(thrash); accepting while still improving (gave_up_early); or escalating where peers converged.\n"
    "4. RESIDUAL TREATMENT (your highest-value call). Did this run accept a residual the corpus "
    "previously REPAIRED for the same signature (more_lenient_than_family), keep grinding repairs PAST "
    "the established finishing floor (more_aggressive_than_family), or accept a reasons[] string never "
    "seen as acceptable in the family (novel_residual)? Name the precedent id and signature.\n"
    "5. RATIFIED-RULE CONFORMANCE. If a `ratified_design_rules` field is present, it is the platform's "
    "RATIFIED routing/layer/plane rule corpus (each an id + statement). The experiential digest tells you "
    "how this board compares to PAST runs; these rules tell you what is CORRECT regardless of precedent. "
    "A board can beat the family objective while VIOLATING a ratified rule -- the headline metrics and the "
    "scorer will not catch it, you must. In particular `gnd-plane-continuity`: signal copper routed ON a "
    "ground/power plane layer breaks the return path (watch `plane_signal_mm` / per-net plane copper in "
    "the summary); a board that 'wins' by carving the plane is NOT a better engineering result. When you "
    "flag a ratified-rule violation, CITE THE RULE ID, set fit_classification accordingly, and recommend "
    "at most investigate_regression -- never let a precedent-statistics 'fit' launder a rule violation.\n\n"
    "DISCIPLINE: compare LIKE WITH LIKE (same family first). Distinguish genuine drift from benign "
    "expected variation: a finishing residual at the family floor, or the known-open pcie kelvin gap, is "
    "`info` severity, NOT a concern. Reserve `high` for a gate regression, a novel structural residual, "
    "or a strong bad-direction metric outlier. If the family has fewer than min_peers usable precedents "
    "(you are told the count), set fit_classification=insufficient_precedent, confidence=low, do NOT "
    "assert a regression on thin evidence. A failed/null route is a trivial non-fit. CITE SPECIFICS: "
    "every concern and the critique must name precedent ids, iteration numbers, and metric values; "
    "populate matched_precedents and violated_precedents. The coverage_note says what evidence was "
    "elided -- if precedent is thin, lower confidence rather than bluffing.\n\n"
    "CLASSIFICATION RUBRIC (in order): gate_regression (any hard-gate flip to worse) > outlier (strong "
    "|z|>6 or bad-direction envelope breach in drc/unconnected/objective, OR a residual no peer "
    "accepted, OR material thrash) > fits_with_concerns (only mild outliers, environment-only outliers, "
    "improvement-direction deviations, or minor wobble) > in_distribution (all meaningful metrics "
    "in-band, gates match family, trajectory coherent) > insufficient_precedent (family n < min_peers) > "
    "no_opinion. Emit EXACTLY ONE JSON object conforming to the provided schema (it is grammar-"
    "constrained). Keep `critique` a tight, evidence-cited paragraph. Reason as long as you need first; "
    "only the JSON is parsed."
)


def _cf_load(x):
    """Accept a DecisionLog instance, a {final,entries} dict, or a path to such JSON. Stamps _src."""
    if isinstance(x, str):
        d = json.load(open(x))
        if isinstance(d, dict):
            d.setdefault("_src", os.path.basename(x))
        return d
    if isinstance(x, dict):
        return x
    return {"final": getattr(x, "final", None), "entries": list(getattr(x, "entries", []) or [])}


def cf_family_of(log):
    """Board family = basename(final.board) minus the trailing -routed (+ .kicad_pcb). Failed/null or
    unparseable -> 'failed', with the corpus filename '<fam>-route-...' as the fallback."""
    try:
        board = (log.get("final") or {}).get("board") if isinstance(log, dict) else None
    except Exception:
        board = None
    if board:
        base = os.path.basename(str(board))
        base = _re.sub(r"\.kicad_pcb$", "", base)
        base = _re.sub(r"-routed$", "", base)
        if base:
            return base
    src = (log.get("_src", "") if isinstance(log, dict) else "") or ""
    m = _re.match(r"(.+?)-route-", src)
    fam = m.group(1) if m else ""
    return "failed" if fam in ("", "None", "none") else _re.sub(r"-routed$", "", fam)


def _cf_is_failed(log):
    fin = (log or {}).get("final") or {}
    v = fin.get("verdict") or {}
    return (fin.get("board") in (None, "", "null")) or ("drc" not in v)


def _cf_same_run(a, b):
    if a.get("_src") and b.get("_src"):
        return a["_src"] == b["_src"]
    fa, fb = (a.get("final") or {}), (b.get("final") or {})
    return (fa.get("board") == fb.get("board") and fa.get("elapsed_s") == fb.get("elapsed_s")
            and fa.get("decisions") == fb.get("decisions"))


def _cf_id(log):
    src = (log.get("_src", "") if isinstance(log, dict) else "") or ""
    m = _re.search(r"-route-\d{8}T(\d{6})-(\d+)", src)
    fam = cf_family_of(log)
    if m:
        return f"{fam}#{m.group(1)}"
    return f"{fam}#{(log.get('final') or {}).get('elapsed_s', '?')}"


def _cf_metric_vec(log):
    fin = (log or {}).get("final") or {}
    v = fin.get("verdict") or {}
    out = {}
    for m in _CF_METRICS:
        out[m] = fin.get(m) if m in ("elapsed_s", "decisions") else v.get(m)
    return out


def _cf_mad(xs, med):
    return _median([abs(x - med) for x in xs]) if xs else 0.0


def _cf_trajectory(entries):
    steps = []
    for e in entries or []:
        ch = e.get("chosen") or {}
        note = e.get("note") or ""
        k = _CF_NOTE_K.search(note)
        fr = _CF_NOTE_FR.search(note)
        ver = e.get("verdict") or {}
        steps.append({"it": e.get("iteration"), "action": ver.get("action"), "tier": ver.get("tier"),
                      "drc": ch.get("drc"), "unconnected": ch.get("unconnected"),
                      "gates_pass": ch.get("gates_pass"),
                      "K": int(k.group(1)) if k else None,
                      "fr_passes": int(fr.group(1)) if fr else None,
                      "fr_opt": int(fr.group(2)) if fr else None})
    return {"n": len(steps), "actions": [s["action"] for s in steps],
            "drc_trail": [s["drc"] for s in steps], "steps": steps}


def cf_new_summary(log):
    fin = (log or {}).get("final") or {}
    v = fin.get("verdict") or {}
    return {"id": _cf_id(log), "family": cf_family_of(log),
            "metrics": _cf_metric_vec(log),
            "gates": {g: v.get(g) for g in ("kelvin_ok", "diffpair_ok", "gates_pass")},
            "final_reasons": v.get("reasons") or [],
            "trajectory": _cf_trajectory(log.get("entries"))}


def cf_family_digest(peers):
    mvecs = [_cf_metric_vec(p) for p in peers]
    metrics = {}
    for m in _CF_METRICS:
        xs = [mv[m] for mv in mvecs if isinstance(mv.get(m), (int, float)) and not isinstance(mv.get(m), bool)]
        if xs:
            med = _median(xs)
            metrics[m] = {"median": round(med, 3), "mad": round(_cf_mad(xs, med), 4),
                          "min": min(xs), "max": max(xs), "best": min(xs), "n": len(xs)}
    gates = {}
    for g in ("kelvin_ok", "diffpair_ok", "gates_pass"):
        vals = [((p.get("final") or {}).get("verdict") or {}).get(g) for p in peers]
        vals = [v for v in vals if isinstance(v, bool)]
        t = sum(1 for v in vals if v)
        gates[g] = {"true": t, "false": len(vals) - t, "modal": (t >= (len(vals) - t)) if vals else None}
    rc = Counter()
    for p in peers:
        for r in (((p.get("final") or {}).get("verdict") or {}).get("reasons") or []):
            rc[r] += 1
    decs = [(p.get("final") or {}).get("decisions") for p in peers
            if isinstance((p.get("final") or {}).get("decisions"), (int, float))]
    return {"n": len(peers), "metrics": metrics, "gates": gates,
            "modal_terminal_reasons": [r for r, _ in rc.most_common(3)],
            "convergence": {"median_decisions": _median(decs) if decs else None}}


def cf_compute_evidence(newsum, digest):
    ev = {"metrics": [], "gate_flips": []}
    nm = newsum["metrics"]
    for m, d in digest["metrics"].items():
        x = nm.get(m)
        if not isinstance(x, (int, float)) or isinstance(x, bool):
            continue
        med, mad = d["median"], d["mad"]
        z = (x - med) / (1.4826 * mad) if mad > 0 else (0.0 if x == med else (6.0 if x > med else -6.0))
        breach = (x < d["min"] or x > d["max"]) and d["n"] >= 3
        direction = "neutral" if abs(z) <= 1e-4 else ("improvement" if x < med else "regression")
        az = abs(z)
        verdict = ("envelope_breach" if breach else "strong_outlier" if az > 6
                   else "mild_outlier" if az > 3 else "in_band")
        ev["metrics"].append({"metric": m, "new_value": x, "family_median": med, "robust_z": round(z, 2),
                              "direction": direction, "verdict": verdict,
                              "regression_vs_best": round(x - d["best"], 3)})
    for g, gd in digest["gates"].items():
        modal, nv = gd["modal"], newsum["gates"].get(g)
        if modal is None or nv is None:
            flip = "no_family_precedent"
        elif nv == modal:
            flip = "matches_family"
        elif nv and not modal:
            flip = "improved_vs_family"
        else:
            flip = "regressed_vs_family"
        ev["gate_flips"].append({"gate": g, "new": nv, "family_modal": modal, "flip": flip})
    return ev


def _cf_compact(log):
    v = ((log.get("final") or {}).get("verdict")) or {}
    td = _cf_trajectory(log.get("entries"))
    return {"id": _cf_id(log),
            "final": {k: v.get(k) for k in ("gates_pass", "kelvin_ok", "diffpair_ok", "drc",
                                            "unconnected", "objective", "tracks", "vias")},
            "reasons": v.get("reasons") or [], "actions": td["actions"],
            "drc_trail": td["drc_trail"], "decisions": (log.get("final") or {}).get("decisions")}


def cf_budget_exemplars(peers, new, ctx_tokens, max_exemplars):
    newm = _cf_metric_vec(new)

    def gate_pass(p):
        return bool(((p.get("final") or {}).get("verdict") or {}).get("gates_pass"))

    def has_escalate(p):
        return "escalate" in _cf_trajectory(p.get("entries"))["actions"]

    def near(p):
        pm = _cf_metric_vec(p)
        return abs((pm.get("drc") or 0) - (newm.get("drc") or 0)) + \
            abs((pm.get("unconnected") or 0) - (newm.get("unconnected") or 0))

    ranked = sorted(peers, key=lambda p: (0 if gate_pass(p) else 1, 0 if has_escalate(p) else 1, near(p)))
    budget = ctx_tokens * 4 * 0.7
    out, used = [], 0
    for p in ranked[:max_exemplars]:
        card = _cf_compact(p)
        s = len(json.dumps(card))
        if out and used + s > budget:
            break
        out.append(card)
        used += s
    coverage = (f"included {len(out)}/{len(peers)} same-family exemplars verbatim; "
                f"{max(0, len(peers) - len(out))} summarized only in the digest")
    return out, coverage


def _cf_other_families(cdir, exclude):
    c = Counter()
    for p in _glob.glob(os.path.join(cdir, "*.json")):
        try:
            L = _cf_load(p)
        except Exception:
            continue
        f = cf_family_of(L)
        if f != exclude:
            c[f] += 1
    return dict(c)


def _cf_skeleton(fam, fc, rec, conf, headline, critique, concerns=None):
    return {"fit_classification": fc, "recommendation": rec, "confidence": conf, "family": fam,
            "headline": headline,
            "gate_consistency": {"kelvin_ok": "no_family_precedent", "diffpair_ok": "no_family_precedent",
                                 "gates_pass": "no_family_precedent", "flips": []},
            "metric_band": "no_band",
            "trajectory": {"shape": "unknown", "coherent": True, "detail": "reviewer did not run"},
            "residual_treatment": "na", "outlier_metrics": [], "matched_precedents": [],
            "violated_precedents": [], "concerns": concerns or [], "critique": critique}


def _cf_no_opinion(fam, reason):
    return _cf_skeleton(fam, "no_opinion", "no_opinion", "low",
                        "corpus-fit reviewer unavailable; no precedent opinion",
                        "reviewer unavailable; no opinion rendered.",
                        [{"severity": "info", "kind": "insufficient_data", "detail": str(reason)[:300]}])


def _cf_failed(fam):
    return _cf_skeleton(fam, "no_opinion", "no_opinion", "low",
                        "route failed (no board); precedent-fit not applicable",
                        "Route produced no board (board=null); nothing to compare against precedent.",
                        [{"severity": "info", "kind": "insufficient_data", "detail": "failed route / board=null"}])


def _cf_insufficient(fam, n, new):
    gp = ((new.get("final") or {}).get("verdict") or {}).get("gates_pass")
    return _cf_skeleton(fam, "insufficient_precedent", "no_opinion", "low",
                        f"only {n} same-family precedent(s) (< min); gates-only, no regression asserted",
                        f"Family '{fam}' has {n} usable precedent(s), below the minimum to judge "
                        f"precedent-fit. Absolute gates_pass={gp}; no regression asserted on thin evidence.",
                        [{"severity": "info", "kind": "insufficient_data", "detail": f"{n} same-family peers"}])


def _cf_clamp(out, new, digest):
    """POST-PARSE SAFETY CLAMP: a gate-false board can NEVER read as in_distribution/fits_with_concerns
    or accept_as_consistent, regardless of what the model emitted. Pulls the family-modal gate-flip
    facts from the deterministic evidence so a model error cannot understate a real gate regression."""
    if not isinstance(out, dict):
        return _cf_no_opinion(cf_family_of(new), "bad_model_output")
    gp = ((new.get("final") or {}).get("verdict") or {}).get("gates_pass")
    if gp is False:
        flips = cf_compute_evidence(cf_new_summary(new), digest)["gate_flips"]
        regressed = any(f["flip"] == "regressed_vs_family" for f in flips
                        if f["gate"] in ("kelvin_ok", "diffpair_ok"))
        if out.get("fit_classification") in ("in_distribution", "fits_with_concerns"):
            out["fit_classification"] = "gate_regression" if regressed else "outlier"
        if out.get("recommendation") == "accept_as_consistent":
            out["recommendation"] = "investigate_regression" if regressed else "review_recommended"
    return out


def corpus_fit_review(new_log, corpus_dir=None, *, min_peers=3, verbose=False):
    """Deep precedent-fit review of one routed board against its same-family corpus. Returns a
    schema-conforming dict (advisory; fail-safe to no_opinion). Runs OUTSIDE the per-region loop."""
    try:
        import cec_router
        cdir = corpus_dir or cec_router.CORPUS_DIR
    except Exception:
        cdir = corpus_dir or os.path.join(ROOT, "build", "route", "corpus")
    ctx_tokens = int(os.environ.get("CEC_CORPUS_CTX", "12000"))
    max_exemplars = int(os.environ.get("CEC_CORPUS_EXEMPLARS", "6"))
    window = int(os.environ.get("CEC_CORPUS_WINDOW", "200"))
    # The corpus-fit review is the HEAVIEST reasoning task (digest + exemplars + the new board's full
    # summary) AND the slowest, so it gets its OWN generous, low-frequency budget, well above the
    # per-region MANAGER_* knobs (a 600s/4096 verdict budget truncates it mid-reason). It runs once
    # per board, out of loop. Budget headroom by reviewer: cec-manager-fast (oss-120b, 22.3 tok/s
    # warm, ~6.5 min cold via the broker) finishes single-call well inside 1800s; cec-manager (M2.7,
    # 12.9 tok/s warm, ~10.5 min cold) may add the scribe second call -- still inside 1800s warm.
    # (Historical: the retired 235B measured a thorough review at 1157s @ ~4.3 tok/s.)
    cf_timeout = float(os.environ.get("CEC_CORPUS_TIMEOUT", "2700"))        # 2700 (was 1800): room for a deep V4 review at the ceiling
    cf_max_tokens = int(os.environ.get("CEC_CORPUS_MAX_TOKENS", "12000"))   # 12000 (was 6144): a deep precedent review must not truncate
    try:
        new = _cf_load(new_log)
        fam = cf_family_of(new)
        if _cf_is_failed(new):
            return _cf_failed(fam)
        peers = []
        for p in sorted(_glob.glob(os.path.join(cdir, "*.json"))):
            try:
                L = _cf_load(p)
            except Exception:
                continue
            if cf_family_of(L) == fam and not _cf_is_failed(L) and not _cf_same_run(L, new):
                peers.append(L)
        peers = peers[-window:]
        if len(peers) < min_peers:
            return _cf_insufficient(fam, len(peers), new)
        # Through the broker this is a BROKER-liveness check (the catalog answers even with nothing
        # running; the reviewer model is then booted on demand by the call itself). Talking straight
        # to an upstream it remains the old model-liveness short-circuit.
        if not available(url=REVIEWER_URL):
            return _cf_no_opinion(fam, "reviewer_down")
        digest = cf_family_digest(peers)
        newsum = cf_new_summary(new)
        evidence = cf_compute_evidence(newsum, digest)
        exemplars, coverage = cf_budget_exemplars(peers, new, ctx_tokens, max_exemplars)
        payload = {"focus_family": fam, "family_precedent_count": digest["n"], "min_peers": min_peers,
                   "family_digest": digest, "new_board": newsum, "precomputed_evidence": evidence,
                   "precedent_exemplars": exemplars,
                   "other_families_in_corpus": _cf_other_families(cdir, fam),
                   "coverage_note": coverage,
                   "notes": "All metrics lower-is-better. robust_z/flags/evidence are precomputed; "
                            "reason about meaning, do not recompute."}
        # CORPUS WIRING (FR-04 lesson, 2026-06-11): the experiential digest above tells the reviewer
        # how this board compares to PAST runs, but NOT whether it honours the platform's RATIFIED
        # DESIGN RULES. The blind/briefed bake-off showed a board can beat the scorer's objective while
        # violating a ratified rule (signal carved through the GND plane) -- a blind judge and the
        # scorer both miss it; a briefed judge catches it. Feed the routing/layer/plane-relevant
        # ratified rule subset (cec_facts.corpus_briefing) so this seat can flag exactly that.
        if os.environ.get("CEC_CORPUS_BRIEFING", "1") != "0":
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import cec_facts
                brief, binfo = cec_facts.corpus_briefing(
                    fam, max_chars=int(os.environ.get("CEC_CORPUS_BRIEFING_CHARS", "9000")))
                if brief:
                    payload["ratified_design_rules"] = brief
                    if verbose:
                        print(f"[corpus-fit] briefing wired: {binfo}")
            except Exception as _be:                                 # noqa: BLE001
                if verbose:
                    print("[corpus-fit] briefing skipped:", type(_be).__name__, _be)
        user = json.dumps(payload, indent=1, sort_keys=True)
        out = _chat_json(CORPUS_FIT_SYSTEM, user, CORPUS_FIT_SCHEMA, name="corpus_fit", seat="reviewer",
                         url=REVIEWER_URL, model=REVIEWER_MODEL, timeout=cf_timeout,
                         max_tokens=cf_max_tokens)
        return _cf_clamp(out, new, digest)
    except Exception as e:
        if verbose:
            print("[corpus-fit] error:", type(e).__name__, e)
        try:
            fam = cf_family_of(_cf_load(new_log))
        except Exception:
            fam = "unknown"
        return _cf_no_opinion(fam, type(e).__name__)


if __name__ == "__main__":
    # Host-side gate CLI: manage the on-demand GPU judge + a smoke test.
    import argparse
    ap = argparse.ArgumentParser(description="cec_judge_local -- local vLLM judge gate + smoke")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["up", "down", "warm", "status", "smoke", "diff-test", "corpus-fit"],
                    help="up=start+warm, down=stop (free VRAM), warm, status, smoke=judge a fake candidate, "
                         "diff-test=prove the swarm differentiates accept/repair/escalate, "
                         "corpus-fit=deep precedent-fit review of a routed board's DecisionLog")
    ap.add_argument("--url", default=VLLM_URL)
    ap.add_argument("--corpus-file", help="DecisionLog JSON to corpus-fit review (default: newest in build/route/corpus)")
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for the server to come up")
    a = ap.parse_args()
    VLLM_URL = a.url.rstrip("/")

    if a.cmd == "up":
        sys.exit(0 if ensure_up(timeout=a.timeout) else 1)
    if a.cmd == "down":
        sys.exit(0 if shutdown() else 1)
    if a.cmd == "warm":
        sys.exit(0 if warmup() else 1)
    if a.cmd == "diff-test":
        if not available():
            print("vLLM down -- run 'up' first")
            sys.exit(2)
        res = differentiated_test(panel=3)
        sys.exit(0 if all(r["ok"] for r in res.values()) else 1)
    if a.cmd == "corpus-fit":
        f = a.corpus_file
        if not f:
            cands = sorted(_glob.glob(os.path.join(ROOT, "build", "route", "corpus", "*.json")))
            f = cands[-1] if cands else None
        if not f:
            print("no --corpus-file given and none found in build/route/corpus/")
            sys.exit(2)
        print(f"corpus-fit reviewing {f} (reviewer {REVIEWER_URL} / {REVIEWER_MODEL})", file=sys.stderr)
        res = corpus_fit_review(f, verbose=True)
        print(json.dumps(res, indent=2))
        sys.exit(0)
    if a.cmd == "status":
        print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
        print(f"manager (in-loop): {MANAGER_URL} / {MANAGER_MODEL} | "
              f"reviewer (out-of-loop): {REVIEWER_URL} / {REVIEWER_MODEL}")
        sys.exit(0)
    # smoke: a gate-passing finishing-residual candidate -> expect accept
    print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
    if available():
        user = json.dumps({"region": "all", "iteration": 2, "prior_iterations": 1,
                           "candidates_best_first": [{"drc": 4, "unconnected": 2, "tracks": 556,
                               "vias": 84, "kelvin_ok": True, "diffpair_ok": True, "gates_pass": True}],
                           "best_candidate_gate_failures": []}, indent=1)
        print("verdict:", chat_verdict(SYSTEM, user))
