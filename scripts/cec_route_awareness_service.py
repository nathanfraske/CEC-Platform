#!/usr/bin/env python3
"""Persistent, process-safe CUDA owner for route-awareness analysis.

Wave placement uses spawned pcbnew workers.  Letting every worker initialize
CuPy gives each process a CUDA context and memory pool, so otherwise independent
placement candidates compete for VRAM and repeatedly pay the context/kernel
startup cost.  This module owns one local Unix socket and one CUDA context for
the lifetime of a wave.  Small route problems remain local CPU work; only jobs
which the coordinated router has already admitted to CUDA are sent here.

The protocol is deliberately local and small: length-prefixed pickle over a
mode-0600 AF_UNIX socket.  The socket is created in a private mode-0700 /tmp
directory and is never exposed on a network interface.  Requests are processed
serially because concurrent CuPy jobs would defeat the single-owner memory
contract.  An exact-result LRU is byte bounded and the CuPy pool is released
after each job, retaining the context and compiled kernels without hoarding
VRAM from other applications.
"""

from __future__ import annotations

import argparse
import atexit
import collections
import hashlib
import os
import pickle
import shutil
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback


_HEADER = struct.Struct("!Q")
_MAX_MESSAGE = 512 * 1024 * 1024
_CLIENT_TIMEOUT_S = float(os.environ.get(
    "CEC_COORD_SERVICE_TIMEOUT_S", "900"))
_START_TIMEOUT_S = float(os.environ.get(
    "CEC_COORD_SERVICE_START_TIMEOUT_S", "30"))
_OWNED_PROCESS = None
_OWNED_DIR = None
_OWNED_LOG = None
_START_LOCK = threading.Lock()


def _recv_exact(sock, size):
    chunks = []
    left = int(size)
    while left:
        chunk = sock.recv(min(left, 1024 * 1024))
        if not chunk:
            raise EOFError("route-awareness service closed the socket")
        chunks.append(chunk)
        left -= len(chunk)
    return b"".join(chunks)


def _send_frame(sock, payload):
    if len(payload) > _MAX_MESSAGE:
        raise ValueError("route-awareness message exceeds 512 MiB")
    sock.sendall(_HEADER.pack(len(payload)))
    sock.sendall(payload)


def _recv_frame(sock):
    (size,) = _HEADER.unpack(_recv_exact(sock, _HEADER.size))
    if size > _MAX_MESSAGE:
        raise ValueError("route-awareness message exceeds 512 MiB")
    return _recv_exact(sock, size)


def _rpc(socket_path, request, *, timeout_s=None):
    payload = pickle.dumps(request, protocol=pickle.HIGHEST_PROTOCOL)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(_CLIENT_TIMEOUT_S if timeout_s is None else timeout_s)
        sock.connect(socket_path)
        _send_frame(sock, payload)
        response = pickle.loads(_recv_frame(sock))
    if not isinstance(response, dict):
        raise RuntimeError("malformed route-awareness response")
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "route-awareness request failed")
    return response.get("result")


def health(socket_path=None, *, timeout_s=2.0):
    """Return daemon state, or raise when the configured daemon is unavailable."""
    path = socket_path or os.environ.get("CEC_COORD_SERVICE_SOCKET")
    if not path:
        raise RuntimeError("CEC_COORD_SERVICE_SOCKET is not configured")
    return _rpc(path, {"op": "health"}, timeout_s=timeout_s)


def route_remote(conns, H, W, *, layer_names=None, **kwargs):
    """Run one already-admitted CUDA problem in the persistent daemon."""
    socket_path = os.environ.get("CEC_COORD_SERVICE_SOCKET")
    if not socket_path:
        raise RuntimeError("route-awareness service is not configured")
    params = (conns, int(H), int(W), tuple(layer_names or ()), kwargs)
    route_payload = pickle.dumps(params, protocol=pickle.HIGHEST_PROTOCOL)
    request_key = hashlib.sha256(route_payload).hexdigest()
    return _rpc(socket_path, {
        "op": "route",
        "key": request_key,
        "payload": route_payload,
    })


def _shutdown_owned():
    global _OWNED_PROCESS, _OWNED_DIR, _OWNED_LOG
    proc = _OWNED_PROCESS
    path = os.environ.get("CEC_COORD_SERVICE_SOCKET")
    if proc is not None and proc.poll() is None:
        try:
            _rpc(path, {"op": "shutdown"}, timeout_s=1.0)
            proc.wait(timeout=3.0)
        except Exception:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
    if _OWNED_LOG is not None:
        try:
            _OWNED_LOG.close()
        except Exception:
            pass
    if _OWNED_DIR:
        shutil.rmtree(_OWNED_DIR, ignore_errors=True)
    _OWNED_PROCESS = None
    _OWNED_DIR = None
    _OWNED_LOG = None


atexit.register(_shutdown_owned)


def ensure_service(*, enabled=True):
    """Start one daemon for this process tree and export its socket to workers.

    An explicitly configured, healthy socket is reused.  This lets an outer
    unattended manager keep the same CUDA context across several wave calls.
    Otherwise the service follows the parent wave lifetime and is cleaned up at
    exit.  No service is started when CEC_COORD_SERVICE=0.
    """
    global _OWNED_PROCESS, _OWNED_DIR, _OWNED_LOG
    if not enabled or os.environ.get("CEC_COORD_SERVICE", "1") == "0":
        return {"enabled": False, "reason": "disabled"}
    configured = os.environ.get("CEC_COORD_SERVICE_SOCKET")
    if configured:
        try:
            return {"enabled": True, "reused": True, **health(configured)}
        except Exception:
            if _OWNED_PROCESS is None:
                # A stale inherited path must not poison a new wave.
                os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
    with _START_LOCK:
        if _OWNED_PROCESS is not None and _OWNED_PROCESS.poll() is None:
            return {"enabled": True, "reused": True, **health()}
        service_dir = tempfile.mkdtemp(prefix="cec-route-gpu-")
        os.chmod(service_dir, 0o700)
        socket_path = os.path.join(service_dir, "route.sock")
        log_path = os.path.join(service_dir, "service.log")
        log_handle = open(log_path, "a", encoding="utf-8")
        env = os.environ.copy()
        env["CEC_COORD_SERVICE_SERVER"] = "1"
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--serve", socket_path],
            stdin=subprocess.DEVNULL, stdout=log_handle, stderr=log_handle,
            start_new_session=True, env=env)
        _OWNED_PROCESS = proc
        _OWNED_DIR = service_dir
        _OWNED_LOG = log_handle
        os.environ["CEC_COORD_SERVICE_SOCKET"] = socket_path
        deadline = time.monotonic() + _START_TIMEOUT_S
        last_error = None
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                state = health(socket_path, timeout_s=1.0)
                return {"enabled": True, "reused": False, **state}
            except Exception as exc:  # daemon may still be warming CUDA
                last_error = exc
                time.sleep(0.1)
        try:
            log_handle.flush()
            with open(log_path, "r", encoding="utf-8", errors="replace") as src:
                tail = src.read()[-4000:]
        except Exception:
            tail = ""
        _shutdown_owned()
        raise RuntimeError(
            "route-awareness service failed to start: %s%s" % (
                last_error or "process exited", ("\n" + tail) if tail else ""))


class _RouteServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(self, path, handler):
        self.started = time.time()
        self.jobs = 0
        self.cache_hits = 0
        self.failures = 0
        self.last_compute_s = None
        self.last_pool_bytes = 0
        self.cache = collections.OrderedDict()
        self.cache_bytes = 0
        self.cache_limit = max(0, int(float(os.environ.get(
            "CEC_COORD_SERVICE_CACHE_MB", "64")) * 1024 * 1024))
        self.prewarm_s = None
        self.gpu = {}
        super().__init__(path, handler)
        os.chmod(path, 0o600)

    def state(self):
        return {
            "pid": os.getpid(),
            "socket": self.server_address,
            "uptime_s": round(time.time() - self.started, 3),
            "prewarm_s": self.prewarm_s,
            "jobs": self.jobs,
            "cache_hits": self.cache_hits,
            "failures": self.failures,
            "cache_entries": len(self.cache),
            "cache_bytes": self.cache_bytes,
            "cache_limit_bytes": self.cache_limit,
            "last_compute_s": self.last_compute_s,
            "last_pool_bytes": self.last_pool_bytes,
            "gpu": dict(self.gpu),
        }

    def cache_get(self, key):
        value = self.cache.pop(key, None)
        if value is not None:
            self.cache[key] = value
            self.cache_hits += 1
        return value

    def cache_put(self, key, value):
        if not self.cache_limit or len(value) > self.cache_limit:
            return
        old = self.cache.pop(key, None)
        if old is not None:
            self.cache_bytes -= len(old)
        self.cache[key] = value
        self.cache_bytes += len(value)
        while self.cache and self.cache_bytes > self.cache_limit:
            _old_key, old_value = self.cache.popitem(last=False)
            self.cache_bytes -= len(old_value)


class _RouteHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            raw = _recv_frame(self.request)
            request = pickle.loads(raw)
            op = request.get("op")
            if op == "health":
                result = self.server.state()
            elif op == "shutdown":
                result = {"shutting_down": True, **self.server.state()}
                threading.Thread(
                    target=self.server.shutdown, daemon=True).start()
            elif op == "route":
                result = self._route(request)
            else:
                raise ValueError("unknown route-awareness operation %r" % op)
            response = {"ok": True, "result": result}
        except Exception as exc:  # keep daemon alive; fail this one request
            self.server.failures += 1
            response = {
                "ok": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc(limit=12),
            }
        _send_frame(self.request, pickle.dumps(
            response, protocol=pickle.HIGHEST_PROTOCOL))

    def _route(self, request):
        key = request.get("key")
        payload = request.get("payload")
        if not isinstance(key, str) or not isinstance(payload, bytes):
            raise ValueError("malformed route request")
        if hashlib.sha256(payload).hexdigest() != key:
            raise ValueError("route request checksum mismatch")
        cached = self.server.cache_get(key)
        if cached is not None:
            result = pickle.loads(cached)
            result["route_awareness_service"] = {
                **result.get("route_awareness_service", {}),
                "cache_hit": True,
                "pid": os.getpid(),
            }
            return result
        conns, H, W, layer_names, kwargs = pickle.loads(payload)
        import cec_coord_router
        t0 = time.perf_counter()
        result = cec_coord_router.route_problem(
            conns, H, W, backend="gpu", layer_names=layer_names,
            _service_bypass=True, **kwargs)
        compute_s = time.perf_counter() - t0
        pool = cec_coord_router._cp.get_default_memory_pool()
        self.server.last_pool_bytes = int(pool.total_bytes())
        # Preserve the CUDA context and compiled kernel cache but return bulk
        # route tensors to the system so a local inference model keeps headroom.
        pool.free_all_blocks()
        try:
            cec_coord_router._cp.get_default_pinned_memory_pool().free_all_blocks()
        except Exception:
            pass
        self.server.jobs += 1
        self.server.last_compute_s = round(compute_s, 6)
        result["route_awareness_service"] = {
            "used": True,
            "cache_hit": False,
            "pid": os.getpid(),
            "compute_s": round(compute_s, 6),
            "pool_bytes_before_release": self.server.last_pool_bytes,
        }
        cached_value = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
        self.server.cache_put(key, cached_value)
        return result


def _prewarm(server):
    import cec_coord_router
    cp = cec_coord_router._cp
    if cp is None:
        raise RuntimeError("CuPy is unavailable; cannot start CUDA route service")
    t0 = time.perf_counter()
    dev = cp.cuda.Device(0)
    dev.use()
    free_bytes, total_bytes = cp.cuda.runtime.memGetInfo()
    props = cp.cuda.runtime.getDeviceProperties(0)
    name = props.get("name", b"CUDA device")
    if isinstance(name, bytes):
        name = name.decode("utf-8", "replace")
    # Exercise the real relaxation/descent path, not only a trivial CUDA op.
    cec_coord_router.route_problem(
        [("/__prewarm_a", (0, 1, 1), (3, 5, 6)),
         ("/__prewarm_b", (3, 1, 6), (0, 5, 1))], 7, 8,
        backend="gpu", L=4, iters=2, max_sweeps=24,
        cost_mode="fixed", chunk_min=1, _service_bypass=True)
    cp.cuda.Stream.null.synchronize()
    pool = cp.get_default_memory_pool()
    pool.free_all_blocks()
    server.prewarm_s = round(time.perf_counter() - t0, 6)
    server.gpu = {
        "device": 0,
        "name": name,
        "total_bytes": int(total_bytes),
        "free_bytes_at_start": int(free_bytes),
    }


def serve(socket_path):
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = _RouteServer(socket_path, _RouteHandler)
    try:
        _prewarm(server)
        def _signal_shutdown(*_args):
            # BaseServer.shutdown must not run in the serve_forever thread.
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, _signal_shutdown)
        signal.signal(signal.SIGINT, _signal_shutdown)
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", metavar="SOCKET")
    parser.add_argument("--health", metavar="SOCKET")
    args = parser.parse_args(argv)
    if args.serve:
        serve(args.serve)
        return 0
    if args.health:
        print(health(args.health))
        return 0
    parser.error("one of --serve or --health is required")


if __name__ == "__main__":
    raise SystemExit(main())
