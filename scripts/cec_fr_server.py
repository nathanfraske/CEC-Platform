#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""cec_fr_server -- the CEC Freerouting REST service, backed by OUR fork jar.

Owner directive (2026-07-22): the REST path must serve the CEC fork ("we are on a
custom cec jar that makes vital corrections"), NOT the official freerouting 2.x
API image -- 1.7.0 predates freerouting's own API server entirely, the official
2.2.4 REST image is a different router with measured blockers on our boards
(12vhpwr GND normalize-hang, no seed-diversity axis), and its API demands
freerouting.app accounts. So this is a thin job service of our own: every job is
executed by `cec_fr.run_freerouting` itself in a subprocess, which means the
ENTIRE local contract rides along unchanged -- the hash-pinned fork jar
(FR_RELEASES resolution), the seed axis (CEC_FR_SEED_AXIS), -noecho, -maxstall,
the external plateau-kill (CEC_FR_PLATEAU_KILL streaming CEC_PASS lines), the
xvfb wrapping, and the process-group tree-kill on timeout. Same route in, same
route out: with equal params+env the SES is byte-identical to a local run (the
fork's determinism guarantee), so REST-vs-local is an infrastructure choice, not
an epoch change. The version is client-pinned per job and hash-verified
server-side.

API (JSON; no auth -- compose-internal / LAN service):
  GET    /v1/system/status        server + fork-version + job counters
  POST   /v1/jobs                 {dsn_b64, name?, passes, opt_time, threads,
                                   seed?, version?, timeout, env?{allow-listed
                                   CEC_FR_* knobs}} -> {id, state}
  GET    /v1/jobs/<id>            {id, state, error, error_kind, elapsed_s,
                                   last_pass, log_size}
  GET    /v1/jobs/<id>/log?offset=N   raw log text from byte N (live progress)
  GET    /v1/jobs/<id>/output     {ses_b64} once COMPLETED (409 before)
  DELETE /v1/jobs/<id>            cancel (process-group kill)

States: QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED.
error_kind: "route" = a legitimate route verdict (FR nonzero exit, route
timeout, plateau-kill, missing SES) -- the client RE-RAISES it so wave/oracle
semantics are unchanged; "infra" = server-side breakage -- the client falls
back to the local jar, loudly.

Run:  python3 scripts/cec_fr_server.py --host 0.0.0.0 --port 37864 \
          --data /mnt/freerouting/jobs --workers 4
Test seam: CEC_FR_SERVER_RUNNER=<script> replaces the job-runner command
(test-only; documented in tests/test_fr_rest.py).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# env knobs a client may forward into its job (allow-list -- never arbitrary env)
ENV_ALLOW = ("CEC_FR_SEED_AXIS", "CEC_FR_NOECHO", "CEC_FR_MAXSTALL",
             "CEC_FR_PLATEAU_KILL", "CEC_FR_PLATEAU_FLOOR",
             "CEC_FR_PLATEAU_GRACES")

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


# ---------------------------------------------------------------------------
# job store -- one directory per job, state as small json files (crash-honest:
# a server restart shows the last durable state, never invents progress)
# ---------------------------------------------------------------------------
class JobStore:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.lock = threading.Lock()

    def jdir(self, jid):
        return os.path.join(self.root, jid)

    def create(self, req: dict) -> str:
        jid = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        d = self.jdir(jid)
        os.makedirs(d)
        with open(os.path.join(d, "in.dsn"), "wb") as fh:
            fh.write(base64.b64decode(req["dsn_b64"]))
        job = {k: req.get(k) for k in ("name", "ses_name", "passes", "opt_time",
                                       "threads", "seed", "version", "timeout")}
        job["env"] = {k: str(v) for k, v in (req.get("env") or {}).items()
                      if k in ENV_ALLOW}
        with open(os.path.join(d, "job.json"), "w") as fh:
            json.dump(job, fh, indent=1)
        self.set_state(jid, {"state": "QUEUED", "queued_at": time.time()})
        return jid

    def set_state(self, jid, patch):
        with self.lock:
            st = self.get_state(jid) or {}
            st.update(patch)
            tmp = os.path.join(self.jdir(jid), "state.json.tmp")
            with open(tmp, "w") as fh:
                json.dump(st, fh, indent=1)
            os.replace(tmp, os.path.join(self.jdir(jid), "state.json"))
            return st

    def get_state(self, jid):
        try:
            with open(os.path.join(self.jdir(jid), "state.json")) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def counters(self):
        c = {"QUEUED": 0, "RUNNING": 0, "COMPLETED": 0, "FAILED": 0, "CANCELLED": 0}
        try:
            jids = os.listdir(self.root)
        except OSError:
            jids = []
        for j in jids:
            st = self.get_state(j)
            if st and st.get("state") in c:
                c[st["state"]] += 1
        return c


# ---------------------------------------------------------------------------
# worker pool -- each job runs in a SUBPROCESS (--exec-job) so per-job env is
# isolated and cancel is a clean process-group kill (the run_freerouting inside
# owns its own FR tree-kill; killing the runner's group takes the JVM with it)
# ---------------------------------------------------------------------------
class Workers:
    def __init__(self, store: JobStore, n: int):
        self.store = store
        self.q: "queue.Queue[str]" = queue.Queue()
        self.procs: dict[str, subprocess.Popen] = {}
        self.plock = threading.Lock()
        for i in range(n):
            threading.Thread(target=self._loop, name=f"fr-worker-{i}",
                             daemon=True).start()

    def submit(self, jid):
        self.q.put(jid)

    def cancel(self, jid) -> bool:
        with self.plock:
            p = self.procs.get(jid)
        if p is not None and p.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(p.pid, signal.SIGKILL)
                else:
                    p.kill()
            except OSError:
                pass
            self.store.set_state(jid, {"state": "CANCELLED",
                                       "error": "cancelled by client",
                                       "error_kind": "infra",
                                       "ended_at": time.time()})
            return True
        st = self.store.get_state(jid)
        if st and st.get("state") == "QUEUED":
            self.store.set_state(jid, {"state": "CANCELLED",
                                       "error": "cancelled while queued",
                                       "error_kind": "infra",
                                       "ended_at": time.time()})
            return True
        return False

    def _loop(self):
        while True:
            jid = self.q.get()
            st = self.store.get_state(jid)
            if not st or st.get("state") != "QUEUED":
                continue                                # cancelled while queued
            d = self.store.jdir(jid)
            runner = os.environ.get("CEC_FR_SERVER_RUNNER")   # test seam only
            cmd = ([sys.executable, runner, d] if runner
                   else [sys.executable, os.path.abspath(__file__),
                         "--exec-job", d])
            log = open(os.path.join(d, "run.log"), "ab", buffering=0)
            try:
                p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=(os.name == "posix"))
            except OSError as e:
                self.store.set_state(jid, {"state": "FAILED",
                                           "error": f"runner spawn failed: {e}",
                                           "error_kind": "infra",
                                           "ended_at": time.time()})
                log.close()
                continue
            with self.plock:
                self.procs[jid] = p
            self.store.set_state(jid, {"state": "RUNNING", "pid": p.pid,
                                       "started_at": time.time()})
            p.wait()
            log.close()
            with self.plock:
                self.procs.pop(jid, None)
            st = self.store.get_state(jid) or {}
            if st.get("state") == "CANCELLED":
                continue
            # the runner writes result.json itself; trust it, else classify by rc
            res = {}
            try:
                with open(os.path.join(d, "result.json")) as fh:
                    res = json.load(fh)
            except (OSError, ValueError):
                pass
            if res.get("ok"):
                self.store.set_state(jid, {"state": "COMPLETED",
                                           "jar_sha256": res.get("jar_sha256"),
                                           "fr_version": res.get("fr_version"),
                                           "ended_at": time.time()})
            else:
                self.store.set_state(jid, {
                    "state": "FAILED",
                    "error": res.get("error") or f"runner exited {p.returncode} "
                                                 f"with no result.json",
                    "error_kind": res.get("error_kind")
                                  or ("infra" if p.returncode != 3 else "route"),
                    "ended_at": time.time()})


# ---------------------------------------------------------------------------
# the per-job runner (subprocess entry): imports cec_fr and runs the REAL thing
# ---------------------------------------------------------------------------
def exec_job(jobdir):
    with open(os.path.join(jobdir, "job.json")) as fh:
        job = json.load(fh)
    for k, v in (job.get("env") or {}).items():
        if k in ENV_ALLOW:
            os.environ[k] = v
    sys.path.insert(0, SCRIPTS)
    result = {"ok": False}
    try:
        import cec_fr
        v = job.get("version") or cec_fr.FR_VERSION
        # route under the CLIENT's ses basename (FR embeds it as the session name;
        # matching it makes the REST SES byte-identical to a local run), then
        # normalize to out.ses for the fixed output endpoint.
        ses_name = os.path.basename(job.get("ses_name") or "out.ses") or "out.ses"
        ses = os.path.join(jobdir, ses_name)
        cec_fr.run_freerouting(
            os.path.join(jobdir, "in.dsn"), ses,
            passes=int(job.get("passes") or 10),
            opt_time=int(job.get("opt_time") or 30),
            threads=int(job.get("threads") or 1),
            seed=job.get("seed"),
            timeout=int(job.get("timeout") or 600),
            version=v)
        if ses_name != "out.ses":
            import shutil
            shutil.copyfile(ses, os.path.join(jobdir, "out.ses"))
        jar = cec_fr.ensure_jar(version=v)
        result = {"ok": True, "fr_version": v,
                  "jar_sha256": cec_fr._sha256(jar)}
        rc = 0
    except RuntimeError as e:      # run_freerouting's verdicts: timeout/exit/SES/plateau
        result = {"ok": False, "error": str(e), "error_kind": "route"}
        rc = 3
    except Exception as e:                                     # noqa: BLE001
        result = {"ok": False, "error": f"{type(e).__name__}: {e}",
                  "error_kind": "infra"}
        rc = 4
    with open(os.path.join(jobdir, "result.json"), "w") as fh:
        json.dump(result, fh, indent=1)
    return rc


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def make_handler(store: JobStore, workers: Workers, meta: dict):
    class H(BaseHTTPRequestHandler):
        server_version = "cec-fr-server/1"

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):                     # quiet 200s
            if "/system/status" not in (args[0] if args else ""):
                sys.stderr.write("[fr-server] " + (fmt % args) + "\n")

        def do_GET(self):
            path, _, q = self.path.partition("?")
            if path == "/v1/system/status":
                c = store.counters()
                return self._json(200, {"status": "OK", "backend": "cec-fr-fork",
                                        **meta, "jobs": c})
            m = re.fullmatch(r"/v1/jobs/([\w-]+)", path)
            if m:
                st = store.get_state(m.group(1))
                if st is None:
                    return self._json(404, {"error": "no such job"})
                d = store.jdir(m.group(1))
                out = {"id": m.group(1), "state": st.get("state"),
                       "error": st.get("error"), "error_kind": st.get("error_kind"),
                       "jar_sha256": st.get("jar_sha256"),
                       "fr_version": st.get("fr_version")}
                t0 = st.get("started_at")
                out["elapsed_s"] = round(time.time() - t0, 1) if t0 and \
                    st.get("state") == "RUNNING" else None
                try:
                    lg = os.path.join(d, "run.log")
                    out["log_size"] = os.path.getsize(lg)
                    with open(lg, "rb") as fh:
                        tail = fh.read()[-4000:].decode(errors="replace")
                    for ln in reversed(tail.splitlines()):
                        if "CEC_PASS " in ln:
                            out["last_pass"] = ln.strip()
                            break
                except OSError:
                    out["log_size"] = 0
                return self._json(200, out)
            m = re.fullmatch(r"/v1/jobs/([\w-]+)/log", path)
            if m:
                off = 0
                mo = re.search(r"offset=(\d+)", q or "")
                if mo:
                    off = int(mo.group(1))
                try:
                    with open(os.path.join(store.jdir(m.group(1)), "run.log"),
                              "rb") as fh:
                        fh.seek(off)
                        chunk = fh.read(256 * 1024)
                except OSError:
                    chunk = b""
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
                return
            m = re.fullmatch(r"/v1/jobs/([\w-]+)/output", path)
            if m:
                st = store.get_state(m.group(1))
                if st is None:
                    return self._json(404, {"error": "no such job"})
                if st.get("state") != "COMPLETED":
                    return self._json(409, {"error": f"job is {st.get('state')}"})
                try:
                    with open(os.path.join(store.jdir(m.group(1)), "out.ses"),
                              "rb") as fh:
                        return self._json(200, {"ses_b64":
                                                base64.b64encode(fh.read()).decode()})
                except OSError as e:
                    return self._json(500, {"error": f"output read failed: {e}"})
            return self._json(404, {"error": "unknown endpoint"})

        def do_POST(self):
            if self.path.partition("?")[0] != "/v1/jobs":
                return self._json(404, {"error": "unknown endpoint"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n).decode())
                if not req.get("dsn_b64"):
                    raise ValueError("dsn_b64 required")
            except (ValueError, KeyError) as e:
                return self._json(400, {"error": f"bad request: {e}"})
            jid = store.create(req)
            workers.submit(jid)
            return self._json(201, {"id": jid, "state": "QUEUED"})

        def do_DELETE(self):
            m = re.fullmatch(r"/v1/jobs/([\w-]+)", self.path.partition("?")[0])
            if not m:
                return self._json(404, {"error": "unknown endpoint"})
            if store.get_state(m.group(1)) is None:
                return self._json(404, {"error": "no such job"})
            return self._json(200, {"cancelled": workers.cancel(m.group(1))})

    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=37864)
    ap.add_argument("--data", default=os.path.join(
        os.environ.get("TMPDIR") or "/tmp", "cec_fr_server_jobs"))
    ap.add_argument("--workers", type=int,
                    default=int(os.environ.get("CEC_FR_SERVER_WORKERS") or 0)
                    or min(4, os.cpu_count() or 1))
    ap.add_argument("--exec-job", metavar="JOBDIR",
                    help="(internal) run one job in this dir and exit")
    args = ap.parse_args(argv)

    if args.exec_job:
        sys.exit(exec_job(args.exec_job))

    # fork-version metadata for /status, WITHOUT importing pcbnew in the server
    # process: read FR_VERSION the same way cec_fr does (env override wins).
    meta = {"fr_version": os.environ.get("CEC_FR_VERSION", cec_fr.FR_VERSION),
            "workers": args.workers}
    store = JobStore(args.data)
    workers = Workers(store, args.workers)
    srv = ThreadingHTTPServer((args.host, args.port),
                              make_handler(store, workers, meta))
    print(f"[fr-server] cec fork REST service on {args.host}:{args.port} "
          f"fr_version={meta['fr_version']} workers={args.workers} "
          f"data={args.data}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
