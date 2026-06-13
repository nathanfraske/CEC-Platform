#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_seat_stream -- per-seat reasoning recorder for the live dashboard.
# ============================================================================
# Owner ask (2026-06-13): the live dashboard should show REAL streaming output
# in a SEPARATE SECTION PER SEAT, so every manager and panel has its thoughts
# recorded -- not just the single auditor stream.
#
# A "seat" is one model role in a pass: `manager`, a panel lens
# (`manager-panel:safety`), `worker`, `reviewer`, the `auditor`, etc. Each model
# call opens a Call, streams its content + reasoning_content deltas as they
# arrive, and closes -- appended as NDJSON to `$CEC_STREAM_DIR/<seat>.jsonl`.
# The dashboard discovers `*.jsonl` in that dir and renders one live-tailing
# section per seat.
#
# ZERO-IMPACT WHEN OFF: with CEC_STREAM_DIR unset every entry point is a no-op,
# so the production overnight path is byte-identical unless a dashboard run opts
# in by setting CEC_STREAM_DIR (cec_judge_local then also switches to streaming
# transport). Every write is wrapped -- a recorder failure NEVER propagates into
# a model call.
#
# Event shapes (one JSON object per line in <seat>.jsonl):
#   {"ts", "seat", "kind":"start", "call":<id>, "model","role","phase",
#    "prompt_chars","temperature"}
#   {"ts", "seat", "kind":"delta", "call":<id>, "ch":"content"|"reasoning", "d":<text>}
#   {"ts", "seat", "kind":"end",   "call":<id>, "ok":bool, "content_chars",
#    "reasoning_chars", "ms", "note"?}
# ============================================================================
import json
import os
import threading
import time

_LOCK = threading.Lock()
_HANDLES = {}                 # seat -> open append file handle
_CALLN = [0]                  # global monotonic call id


def _dir():
    return os.environ.get("CEC_STREAM_DIR") or ""


def enabled():
    return bool(_dir())


def _safe_seat(seat):
    s = "".join(c if (c.isalnum() or c in "-_.:") else "_" for c in str(seat or "unknown"))
    return s.replace(":", "__") or "unknown"   # ':' -> '__' so it's filename-safe, reversible by the UI


def _handle(seat):
    """Cached per-seat append handle. Caller holds _LOCK."""
    h = _HANDLES.get(seat)
    if h is None:
        d = _dir()
        os.makedirs(d, exist_ok=True)
        h = open(os.path.join(d, _safe_seat(seat) + ".jsonl"), "a", buffering=1, encoding="utf-8")
        _HANDLES[seat] = h
    return h


def _emit(seat, obj):
    if not enabled():
        return
    try:
        obj.setdefault("ts", time.time())
        obj["seat"] = seat
        with _LOCK:
            _handle(seat).write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:                                  # noqa: BLE001 -- never break a model call
        pass


class _Null:
    """Returned when recording is disabled; all methods are no-ops."""
    call = 0

    def delta(self, *a, **k):
        pass

    def end(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class Call:
    """One model call's recorded stream. Use .delta() as tokens arrive and .end() to close."""

    def __init__(self, seat, **meta):
        self.seat = seat
        with _LOCK:
            _CALLN[0] += 1
            self.call = _CALLN[0]
        self._t0 = time.time()
        self._c = 0
        self._r = 0
        ev = {"kind": "start", "call": self.call}
        ev.update({k: v for k, v in meta.items() if v is not None})
        _emit(seat, ev)

    def delta(self, text, ch="content"):
        if not text:
            return
        if ch == "reasoning":
            self._r += len(text)
        else:
            self._c += len(text)
        _emit(self.seat, {"kind": "delta", "call": self.call, "ch": ch, "d": text})

    def end(self, ok=True, note=None):
        _emit(self.seat, {"kind": "end", "call": self.call, "ok": bool(ok),
                          "content_chars": self._c, "reasoning_chars": self._r,
                          "ms": int((time.time() - self._t0) * 1000), "note": note})

    def error(self, msg):
        _emit(self.seat, {"kind": "end", "call": self.call, "ok": False, "note": str(msg)[:300],
                          "content_chars": self._c, "reasoning_chars": self._r,
                          "ms": int((time.time() - self._t0) * 1000)})


def start(seat, **meta):
    """Open a recorded call for `seat`. Returns a no-op handle when recording is off."""
    if not enabled():
        return _Null()
    return Call(seat, **meta)


def list_seats(stream_dir=None):
    """Seat names present in the stream dir (the UI's section list), newest-active first."""
    d = stream_dir or _dir()
    out = []
    if d and os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.endswith(".jsonl"):
                p = os.path.join(d, fn)
                out.append((fn[:-6].replace("__", ":"), os.path.getmtime(p)))
    return [s for s, _ in sorted(out, key=lambda x: -x[1])]
