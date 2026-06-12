#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec-llm-broker -- on-demand local-LLM model orchestrator (v2).
# ============================================================================
# A tiny OpenAI-compatible reverse proxy on 0.0.0.0:8080 that puts ONE registry
# (models.json) in front of every local-LLM backend on this box, so the CEC
# pipeline and any other project never thrash the single RTX 5090 by hand.
#
# What it does (the v2 "model orchestrator" contract documented in the CEC
# CLAUDE.md, rebuilt from spec 2026-06-12 after the WSL reinstall wiped the
# original /home/nathan/cec-llm-broker):
#
#   * ROUTE BY MODEL NAME. A request's JSON "model" field selects a registry
#     entry; the broker proxies to that backend's host port and rewrites the
#     alias to the backend's actual served name.
#   * START ON DEMAND. If the selected backend is not up, the broker starts it
#     (docker compose --profile <p> up -d <svc>) and polls its health URL.
#   * GPU/VRAM ARBITRATION. Before starting a backend it checks vram_gb against
#     gpu_budget_gb summed over what is already running on the GPU; if it would
#     overflow, it EVICTS the least-recently-used GPU backend(s) first -- after
#     letting their in-flight generations finish (drain) -- then starts.
#   * CATALOG ALWAYS ANSWERS. GET /v1/models lists the FULL registry (with a
#     per-model `running` flag) even with nothing up -- so a client can probe
#     broker liveness and discover models without booting anything.
#   * IDLE REAPER. A background thread stops any backend idle longer than
#     idle_stop_s (default 1800 s), freeing GPU + RAM automatically.
#   * RIDE-THROUGH. Concurrent requests for a cold model block on the SAME
#     start (a per-alias lock), then proceed once it is ready -- nobody double-
#     starts and nobody 503s during a 10-minute cold load.
#
# Fail-safe: any backend that will not come up surfaces as an error to the
# client, whose own deterministic fallback then takes over (cec_judge_local).
#
# Stdlib only (http.server + urllib + subprocess + threading) so it runs as a
# bare systemd unit with no venv. Python 3.11+.
# ============================================================================
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.environ.get("CEC_BROKER_REGISTRY", os.path.join(HERE, "models.json"))
HOST = os.environ.get("CEC_BROKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("CEC_BROKER_PORT", "8080"))
# Upstream host the backends publish their ports on (compose maps them to the host).
UPSTREAM_HOST = os.environ.get("CEC_BROKER_UPSTREAM_HOST", "127.0.0.1")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ----------------------------------------------------------------------------
#  Registry
# ----------------------------------------------------------------------------
class Registry:
    def __init__(self, path):
        self.path = path
        with open(path) as f:
            cfg = json.load(f)
        self.gpu_budget_gb = float(cfg.get("gpu_budget_gb", 30))
        self.idle_stop_s = float(cfg.get("idle_stop_s", 1800))
        self.compose_file = cfg.get("compose_file")
        self.cold_load_timeout = float(cfg.get("cold_load_timeout_s", 1200))
        self.drain_timeout = float(cfg.get("drain_timeout_s", 180))
        self.models = cfg["models"]            # alias -> entry dict
        for alias, m in self.models.items():
            m.setdefault("served", alias)
            m.setdefault("health", "/health")
            m.setdefault("vram_gb", 0)
            m.setdefault("backend", "llama")
            m.setdefault("service", alias)
            # managed=False -> an EXTERNAL backend the broker proxies but does not
            # start/stop (e.g. a Windows-native llama-server). host: where it lives;
            # "windows-host" resolves to the WSL default gateway (the Windows host).
            m.setdefault("managed", True)
            m.setdefault("host", None)

    def get(self, alias):
        return self.models.get(alias)


# ----------------------------------------------------------------------------
#  Backend lifecycle + GPU arbitration
# ----------------------------------------------------------------------------
class Manager:
    def __init__(self, reg):
        self.reg = reg
        self._gate = threading.RLock()                 # guards arbitration / running-set
        self._start_locks = {}                          # alias -> Lock (ride-through)
        # per-alias runtime state
        self.running = {}                               # alias -> {"since": ts}
        self.last_used = {}                             # alias -> ts
        self.active = {}                                # alias -> in-flight request count
        self.stats = {"requests": 0, "starts": 0, "evictions": 0, "by_client": {}}
        for alias in reg.models:
            self.active[alias] = 0
        # Reconcile with anything already up (broker restart shouldn't double-start).
        self._reconcile_running()

    # ---- docker compose helpers -------------------------------------------
    def _compose(self, *args, timeout=None):
        cmd = ["docker", "compose", "-f", self.reg.compose_file, *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def host(self, alias):
        """Resolve the upstream host for an alias. 'windows-host' -> WSL default
        gateway (the Windows host, which can change across WSL restarts)."""
        h = self.reg.get(alias).get("host")
        if not h:
            return UPSTREAM_HOST
        if h == "windows-host":
            try:
                out = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=3).stdout
                for line in out.splitlines():
                    if line.startswith("default"):
                        return line.split()[2]
            except Exception:
                pass
            return UPSTREAM_HOST
        return h

    def _health_ok(self, alias, timeout=3):
        m = self.reg.get(alias)
        url = f"http://{self.host(alias)}:{m['port']}{m['health']}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return 200 <= r.status < 300
        except Exception:
            return False

    def _reconcile_running(self):
        # On boot, mark any backend whose health already answers as running.
        for alias in self.reg.models:
            if self._health_ok(alias, timeout=2):
                self.running[alias] = {"since": time.time()}
                self.last_used[alias] = time.time()
                log(f"reconcile: {alias} already up")

    def is_running(self, alias):
        return alias in self.running

    def catalog(self):
        now = int(time.time())
        data = []
        for alias, m in self.reg.models.items():
            data.append({
                "id": alias,
                "object": "model",
                "created": now,
                "owned_by": "cec-llm-broker",
                "running": alias in self.running,
                "served": m.get("served"),
                "port": m.get("port"),
                "vram_gb": m.get("vram_gb"),
                "backend": m.get("backend"),
                "managed": m.get("managed", True),
                "host": m.get("host"),
            })
        return {"object": "list", "data": data}

    # ---- start / stop ------------------------------------------------------
    def _start_lock(self, alias):
        with self._gate:
            lk = self._start_locks.get(alias)
            if lk is None:
                lk = threading.Lock()
                self._start_locks[alias] = lk
            return lk

    def _gpu_load_excluding(self, exclude):
        return sum(self.reg.get(a)["vram_gb"] for a in self.running if a not in exclude)

    def _evict_for(self, alias):
        """Stop LRU GPU backends until `alias` fits within gpu_budget_gb. Caller holds _gate."""
        need = self.reg.get(alias)["vram_gb"]
        budget = self.reg.gpu_budget_gb
        # Candidates to evict: running GPU backends, least-recently-used first.
        while self._gpu_load_excluding({alias}) + need > budget:
            gpu_running = [a for a in self.running
                           if self.reg.get(a)["vram_gb"] > 0 and a != alias
                           and self.reg.get(a)["managed"]]   # external backends: count load, never evict
            if not gpu_running:
                break
            victim = min(gpu_running, key=lambda a: self.last_used.get(a, 0))
            log(f"arbitrate: {alias} needs {need}GB; evicting LRU {victim} "
                f"({self.reg.get(victim)['vram_gb']}GB) to fit budget {budget}GB")
            self._stop(victim, reason="evicted")
            self.stats["evictions"] += 1

    def _drain(self, alias):
        """Wait (bounded) for in-flight requests on `alias` to finish before stopping it."""
        t0 = time.time()
        while self.active.get(alias, 0) > 0 and time.time() - t0 < self.reg.drain_timeout:
            time.sleep(0.5)

    def _stop(self, alias, reason=""):
        """Stop a backend. Caller holds _gate."""
        m = self.reg.get(alias)
        # Let in-flight generations finish; release the gate while draining so other
        # requests are not blocked, then re-check before the actual stop.
        if self.active.get(alias, 0) > 0:
            self._gate.release()
            try:
                self._drain(alias)
            finally:
                self._gate.acquire()
        try:
            self._compose("stop", m["service"], timeout=120)
        except Exception as e:
            log(f"stop {alias} compose error: {e}")
        self.running.pop(alias, None)
        log(f"stopped {alias}" + (f" ({reason})" if reason else ""))

    def ensure_up(self, alias):
        """Boot `alias` on demand, arbitrating the GPU. Returns True once healthy."""
        m = self.reg.get(alias)
        if m is None:
            return False
        # External backend (e.g. Windows-native): we don't start/stop it, just
        # proxy if it answers. Tracked as running for the catalog, never evicted/reaped.
        if not m["managed"]:
            ok = self._health_ok(alias, timeout=5)
            with self._gate:
                if ok:
                    self.running.setdefault(alias, {"since": time.time()})
                    self.last_used[alias] = time.time()
                else:
                    self.running.pop(alias, None)
            return ok
        # Fast path: already running + healthy.
        if alias in self.running and self._health_ok(alias):
            self.last_used[alias] = time.time()
            return True
        # Ride-through: one starter per alias; everyone else waits on it.
        with self._start_lock(alias):
            if alias in self.running and self._health_ok(alias):
                self.last_used[alias] = time.time()
                return True
            with self._gate:
                if m["vram_gb"] > 0:
                    self._evict_for(alias)
                log(f"start {alias}: compose --profile {m.get('profile', m['service'])} up -d {m['service']}")
                profile = m.get("profile")
                args = []
                if profile:
                    args += ["--profile", profile]
                args += ["up", "-d", m["service"]]
                r = self._compose(*args, timeout=300)
                if r.returncode != 0:
                    log(f"start {alias} FAILED: {(r.stderr or '')[-400:]}")
                    return False
                self.stats["starts"] += 1
            # Poll health (outside the gate -- a cold load can take minutes).
            t0 = time.time()
            while time.time() - t0 < self.reg.cold_load_timeout:
                if self._health_ok(alias):
                    with self._gate:
                        self.running[alias] = {"since": time.time()}
                        self.last_used[alias] = time.time()
                    log(f"{alias} ready in {time.time() - t0:.0f}s")
                    return True
                time.sleep(3)
            log(f"{alias} not healthy after {self.reg.cold_load_timeout:.0f}s")
            return False

    # ---- request accounting ------------------------------------------------
    def begin(self, alias, client):
        with self._gate:
            self.active[alias] = self.active.get(alias, 0) + 1
            self.last_used[alias] = time.time()
            self.stats["requests"] += 1
            if client:
                self.stats["by_client"][client] = self.stats["by_client"].get(client, 0) + 1

    def end(self, alias):
        with self._gate:
            self.active[alias] = max(0, self.active.get(alias, 0) - 1)
            self.last_used[alias] = time.time()

    # ---- idle reaper -------------------------------------------------------
    def reap_loop(self):
        while True:
            time.sleep(30)
            now = time.time()
            for alias in list(self.running):
                if not self.reg.get(alias)["managed"]:
                    continue                       # external backend: not ours to stop
                if self.active.get(alias, 0) > 0:
                    continue
                idle = now - self.last_used.get(alias, now)
                if idle > self.reg.idle_stop_s:
                    with self._gate:
                        if alias in self.running and self.active.get(alias, 0) == 0:
                            log(f"idle reap: {alias} idle {idle/60:.0f}min > "
                                f"{self.reg.idle_stop_s/60:.0f}min")
                            self._stop(alias, reason="idle")


# ----------------------------------------------------------------------------
#  HTTP front end
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    manager = None       # set in main()

    def log_message(self, *a):
        pass             # quiet; we do our own logging

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _norm(self, path):
        # Accept both /v1/... and /... (clients use a /v1 base URL).
        p = path.split("?", 1)[0]
        if p.startswith("/v1/"):
            p = p[3:]
        return p

    def do_GET(self):
        p = self._norm(self.path)
        if p in ("/models", "/v1/models"):
            self._send_json(self.manager.catalog())
        elif p in ("/health", "/"):
            self._send_json({"status": "ok", "service": "cec-llm-broker"})
        elif p in ("/broker/stats", "/stats"):
            mgr = self.manager
            self._send_json({
                "running": {a: {"since": int(v["since"]), "active": mgr.active.get(a, 0),
                                "idle_s": int(time.time() - mgr.last_used.get(a, time.time()))}
                            for a, v in mgr.running.items()},
                "gpu_budget_gb": mgr.reg.gpu_budget_gb,
                "gpu_used_gb": mgr._gpu_load_excluding(set()),
                "idle_stop_s": mgr.reg.idle_stop_s,
                "stats": mgr.stats,
            })
        else:
            self._send_json({"error": {"message": f"no such GET route: {p}"}}, status=404)

    def do_POST(self):
        p = self._norm(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            self._send_json({"error": {"message": "invalid JSON body"}}, status=400)
            return
        alias = payload.get("model")
        mgr = self.manager
        m = mgr.reg.get(alias)
        if m is None:
            self._send_json({"error": {"message": f"unknown model '{alias}'. "
                             f"GET /v1/models for the catalog."}}, status=404)
            return
        client = self.headers.get("X-CEC-Client", "")
        if not mgr.ensure_up(alias):
            self._send_json({"error": {"message": f"backend '{alias}' did not come up"}}, status=503)
            return
        # Rewrite alias -> the backend's actual served name, then proxy.
        payload["model"] = m.get("served", alias)
        body = json.dumps(payload).encode()
        url = f"http://{mgr.host(alias)}:{m['port']}/v1{p}"
        mgr.begin(alias, client)
        try:
            self._proxy(url, body)
        finally:
            mgr.end(alias)

    def _proxy(self, url, body):
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            upstream = urllib.request.urlopen(req, timeout=None)
        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return
        except Exception as e:
            self._send_json({"error": {"message": f"upstream error: {e}"}}, status=502)
            return
        # Stream the upstream response straight through (covers SSE stream=true).
        self.send_response(upstream.status)
        ctype = upstream.headers.get("Content-Type", "application/json")
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                chunk = upstream.read(8192)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.write(b"0\r\n\r\n")
        except Exception:
            pass


def main():
    if not shutil.which("docker"):
        log("WARNING: docker CLI not on PATH -- on-demand start will fail")
    reg = Registry(REGISTRY_PATH)
    mgr = Manager(reg)
    Handler.manager = mgr
    threading.Thread(target=mgr.reap_loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"cec-llm-broker v2 on {HOST}:{PORT} | registry={REGISTRY_PATH} | "
        f"{len(reg.models)} models | gpu_budget={reg.gpu_budget_gb}GB | "
        f"idle_stop={reg.idle_stop_s/60:.0f}min")
    for alias in reg.models:
        log(f"  registered: {alias} -> :{reg.get(alias)['port']} "
            f"({reg.get(alias)['vram_gb']}GB, {reg.get(alias)['backend']})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")


if __name__ == "__main__":
    main()
