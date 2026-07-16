#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for the cec_judge_local bench-wiring (2026-06-10): the M2.7 SAMPLING FLOORS
# (temp floor + presence penalty for models in _FLOOR_MODELS), the miner->scribe EMPTY-CONTENT
# recovery (answer stranded in reasoning_content -> a second SCRIBE transcription call), the
# scribe trace TAIL cap, and the REVIEWER_MODEL env resolution order. Uses a local stub HTTP
# server -- no broker, no GPU, no pcbnew -- so it runs on the host AND in the routing container:
#
#   python3 -m unittest tests.test_judge_local_scribe -v
import importlib
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

# Isolation: the blocking-path tests must run with the per-seat recorder OFF. Pop CEC_STREAM_DIR so a
# leaked env can't route them through the streaming transport (TestStreaming sets it locally instead).
os.environ.pop("CEC_STREAM_DIR", None)

import cec_judge_local as J  # noqa: E402
import cec_seat_stream as S  # noqa: E402

SCHEMA = {"type": "object", "properties": {"action": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["action", "reason"], "additionalProperties": False}


class _Stub:
    """Scripted OpenAI-compatible /chat/completions stub: serves `responses` in order and records
    each request payload. A response is the `message` dict to return."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                msg = outer.responses[min(len(outer.requests) - 1, len(outer.responses) - 1)]
                out = json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


GOOD = {"content": json.dumps({"action": "accept", "reason": "gates pass"})}


class TestSamplingFloors(unittest.TestCase):
    def test_floor_applied_for_m27(self):
        s = _Stub([GOOD])
        try:
            J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url, temperature=0.0)
        finally:
            s.close()
        p = s.requests[0]
        self.assertEqual(p["temperature"], J._FLOOR_TEMP)          # 0.0 floored up
        self.assertEqual(p["presence_penalty"], J._FLOOR_PRESENCE)  # anti decode-loop

    def test_floor_keeps_higher_caller_temp(self):
        s = _Stub([GOOD])
        try:
            J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url, temperature=0.7)
        finally:
            s.close()
        self.assertEqual(s.requests[0]["temperature"], 0.7)         # max(), not overwrite

    def test_no_floor_for_fast_manager(self):
        s = _Stub([GOOD])
        try:
            J._chat_json("sys", "user", SCHEMA, model="cec-manager-fast", url=s.url, temperature=0.0)
        finally:
            s.close()
        p = s.requests[0]
        self.assertEqual(p["temperature"], 0.0)
        self.assertNotIn("presence_penalty", p)


class TestMinerScribe(unittest.TestCase):
    def test_overrun_recovers_via_scribe(self):
        trace = "long deliberation... therefore the verdict is accept because the gates pass."
        s = _Stub([{"content": "", "reasoning_content": trace}, GOOD])
        try:
            out = J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url,
                               max_tokens=4096)
        finally:
            s.close()
        self.assertEqual(out["action"], "accept")
        self.assertEqual(len(s.requests), 2)                        # miner + scribe, no more
        scribe = s.requests[1]
        self.assertEqual(scribe["model"], "cec-manager")            # SAME model, no swap
        self.assertIn("EDITOR", scribe["messages"][0]["content"])
        self.assertIn(trace, scribe["messages"][1]["content"])
        self.assertGreaterEqual(scribe["temperature"], 0.35)        # verified anti-loop knobs
        self.assertEqual(scribe["presence_penalty"], J._FLOOR_PRESENCE)
        self.assertEqual(scribe["max_tokens"], J._SCRIBE_MAX_TOKENS)
        self.assertEqual(scribe["response_format"]["type"], "json_schema")

    def test_overrun_without_trace_raises(self):
        s = _Stub([{"content": "", "reasoning_content": ""}])
        try:
            with self.assertRaises(ValueError):
                J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url)
        finally:
            s.close()
        self.assertEqual(len(s.requests), 1)                        # no scribe attempt

    def test_scribe_trace_tail_capped(self):
        head, tail = "H" * 60000, "the conclusion: accept."
        s = _Stub([{"content": "", "reasoning_content": head + tail}, GOOD])
        try:
            J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url)
        finally:
            s.close()
        user = s.requests[1]["messages"][1]["content"]
        self.assertTrue(user.endswith(tail))                        # tail kept (conclusions live there)
        self.assertLessEqual(len(user), J._SCRIBE_TRACE_CHARS + len("REASONING TRACE:\n"))

    def test_scribe_disabled_raises(self):
        s = _Stub([{"content": "", "reasoning_content": "thinking..."}])
        old = J._AUTO_SCRIBE
        J._AUTO_SCRIBE = False
        try:
            with self.assertRaises(ValueError):
                J._chat_json("sys", "user", SCHEMA, model="cec-manager", url=s.url)
        finally:
            J._AUTO_SCRIBE = old
            s.close()
        self.assertEqual(len(s.requests), 1)


class TestReviewerResolution(unittest.TestCase):
    """REVIEWER_MODEL order: explicit reviewer env > legacy manager pin > cec-manager-fast.
    Reloads the module under a patched env; the final reload restores the ambient state."""

    ENV = ("CEC_VLLM_REVIEWER_MODEL", "CEC_VLLM_MANAGER_MODEL", "CEC_VLLM_MODEL_NAME")

    def _resolve(self, **env):
        saved = {k: os.environ.pop(k, None) for k in self.ENV}
        os.environ.update({k: v for k, v in env.items() if v})
        try:
            return importlib.reload(J).REVIEWER_MODEL
        finally:
            for k in self.ENV:
                os.environ.pop(k, None)
                if saved[k] is not None:
                    os.environ[k] = saved[k]

    def test_resolution_order(self):
        self.assertEqual(self._resolve(), "cec-manager-fast")       # bench default
        self.assertEqual(self._resolve(CEC_VLLM_MANAGER_MODEL="cec-manager"),
                         "cec-manager")                             # legacy overnight pin honored
        self.assertEqual(self._resolve(CEC_VLLM_REVIEWER_MODEL="cec-worker-quality",
                                       CEC_VLLM_MANAGER_MODEL="cec-manager"),
                         "cec-worker-quality")                      # explicit reviewer wins
        importlib.reload(J)                                         # restore ambient module state


class _SSEStub:
    """OpenAI-compatible stub that STREAMS Server-Sent Events when the request asks for stream=true
    (else returns plain JSON -- the fallback path). `frames` are delta dicts emitted as data: lines."""

    def __init__(self, frames, stream_ok=True):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"                     # close after response -> client sees EOF

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                if body.get("stream") and stream_ok:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for fr in frames:
                        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": fr}]}) + "\n\n").encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                else:                                         # non-SSE JSON body (blocking / ignored-stream)
                    out = json.dumps({"choices": [{"message": {"content": json.dumps(
                        {"action": "accept", "reason": "blocking"})}, "finish_reason": "stop"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestStreaming(unittest.TestCase):
    """The CEC_STREAM_DIR streaming transport: SSE deltas are teed per-seat AND a non-SSE response
    degrades to the blocking _post. The recorder caches handles, so reset them per test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CEC_STREAM_DIR"] = self.tmp
        S._HANDLES.clear()

    def tearDown(self):
        for h in S._HANDLES.values():
            try:
                h.close()
            except Exception:
                pass
        S._HANDLES.clear()
        os.environ.pop("CEC_STREAM_DIR", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_streaming_parses_and_records_per_seat(self):
        frames = [{"reasoning_content": "weighing the gates"},
                  {"content": '{"action":'}, {"content": '"accept","reason":"ok"}'}]
        s = _SSEStub(frames)
        try:
            out = J._chat_json("sys", "user", SCHEMA, model="cec-worker-vision", url=s.url, seat="manager")
        finally:
            s.close()
        self.assertEqual(out["action"], "accept")             # assembled stream parses to the verdict
        self.assertTrue(s.requests[0].get("stream"))          # it actually streamed
        events = [json.loads(L) for L in open(os.path.join(self.tmp, "manager.jsonl"))]
        self.assertEqual(events[0]["kind"], "start")
        self.assertEqual(events[-1]["kind"], "end")
        deltas = [e for e in events if e["kind"] == "delta"]
        self.assertTrue(any(e["ch"] == "reasoning" for e in deltas))
        self.assertEqual("".join(e["d"] for e in deltas if e["ch"] == "content"),
                         '{"action":"accept","reason":"ok"}')

    def test_non_sse_response_falls_back_to_blocking(self):
        s = _SSEStub([], stream_ok=False)                     # ignores stream -> plain JSON
        try:
            out = J._chat_json("sys", "user", SCHEMA, model="cec-worker-vision", url=s.url, seat="worker:0")
        finally:
            s.close()
        self.assertEqual(out["action"], "accept")             # fallback returned the blocking result
        self.assertEqual(len(s.requests), 2)                  # streaming attempt + blocking fallback
        self.assertTrue(s.requests[0].get("stream"))
        self.assertNotIn("stream", s.requests[1])


if __name__ == "__main__":
    unittest.main()
