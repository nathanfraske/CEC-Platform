#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Contract teeth for the CEC fork Freerouting REST path (2026-07-22):
# scripts/cec_fr_server.py (job service around OUR pinned jar) + the
# cec_fr._run_freerouting_rest client. No java needed -- the job runner is
# replaced via the documented CEC_FR_SERVER_RUNNER test seam with tiny fake
# runners (success / route-verdict / infra) so what is pinned here is the
# CONTRACT: state machine, error_kind classification (route re-raises,
# infra falls back), SES round-trip, version guard, env forwarding, cancel.
# The real-jar byte-identity leg runs in-container (documented in the
# session notes; needs the fork jar + xvfb).
import base64
import json
import os
import shutil
import socket
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr_server as S                                     # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_runner(tmp, body):
    """A fake --exec-job runner: gets the jobdir as argv[1]."""
    p = os.path.join(tmp, "fake_runner.py")
    with open(p, "w") as fh:
        fh.write(textwrap.dedent(body))
    return p


RUNNER_OK = """
    import json, os, sys
    d = sys.argv[1]
    job = json.load(open(os.path.join(d, "job.json")))
    print("CEC_PASS 1 togo=5 failed=2", flush=True)
    with open(os.path.join(d, "out.ses"), "w") as fh:
        fh.write("(session fake)\\n(env %s)\\n" % json.dumps(job.get("env") or {}))
    with open(os.path.join(d, "result.json"), "w") as fh:
        json.dump({"ok": True, "fr_version": job.get("version"),
                   "jar_sha256": "cafe" * 16}, fh)
"""

RUNNER_ROUTE_FAIL = """
    import json, os, sys
    d = sys.argv[1]
    with open(os.path.join(d, "result.json"), "w") as fh:
        json.dump({"ok": False, "error": "CEC_PLATEAU_KILL: unrouted plateau "
                   "at togo/failed=(9, 3) (4 flat passes)",
                   "error_kind": "route"}, fh)
    sys.exit(3)
"""

RUNNER_INFRA_FAIL = """
    import sys
    sys.exit(4)   # crashes before writing result.json -> classified infra by rc
"""

RUNNER_SLOW = """
    import os, sys, time
    time.sleep(120)
"""


class _Server:
    """cec_fr_server on a free port with a chosen fake runner, as a context."""

    def __init__(self, runner_body, fr_version="1.7.0-cec2"):
        self.tmp = tempfile.mkdtemp(prefix="frrest_test_")
        self.port = _free_port()
        os.environ["CEC_FR_SERVER_RUNNER"] = _write_runner(self.tmp, runner_body)
        self.store = S.JobStore(os.path.join(self.tmp, "jobs"))
        self.workers = S.Workers(self.store, 2)
        handler = S.make_handler(self.store, self.workers,
                                 {"fr_version": fr_version, "workers": 2})
        from http.server import ThreadingHTTPServer
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.port}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        os.environ.pop("CEC_FR_SERVER_RUNNER", None)
        shutil.rmtree(self.tmp, ignore_errors=True)


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read().decode())


def _post(base, path, obj):
    req = urllib.request.Request(base + path, method="POST",
                                 data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _submit(base, env=None):
    return _post(base, "/v1/jobs", {
        "dsn_b64": base64.b64encode(b"(pcb fake)").decode(),
        "passes": 3, "opt_time": 5, "threads": 1, "seed": 7,
        "version": "1.7.0-cec2", "timeout": 30, "env": env or {}})


def _wait_state(base, jid, states, tries=100):
    for _ in range(tries):
        st = _get(base, f"/v1/jobs/{jid}")
        if st["state"] in states:
            return st
        time.sleep(0.1)
    raise AssertionError(f"job never reached {states}: {st}")


class TestServerContract(unittest.TestCase):
    def test_status_and_success_roundtrip_and_env_forwarding(self):
        sv = _Server(RUNNER_OK)
        try:
            st = _get(sv.base, "/v1/system/status")
            self.assertEqual(st["status"], "OK")
            self.assertEqual(st["backend"], "cec-fr-fork")
            self.assertEqual(st["fr_version"], "1.7.0-cec2")
            jid = _submit(sv.base, env={"CEC_FR_PLATEAU_KILL": "3",
                                        "CEC_FR_PLATEAU_FLOOR": "100",
                                        "NOT_ALLOWED": "x"})["id"]
            got = _wait_state(sv.base, jid, ("COMPLETED", "FAILED"))
            self.assertEqual(got["state"], "COMPLETED")
            self.assertEqual(got["jar_sha256"], "cafe" * 16)
            out = _get(sv.base, f"/v1/jobs/{jid}/output")
            ses = base64.b64decode(out["ses_b64"]).decode()
            self.assertIn("(session fake)", ses)
            self.assertIn("CEC_FR_PLATEAU_KILL", ses,
                          "allow-listed env must reach the job")
            self.assertIn("CEC_FR_PLATEAU_FLOOR", ses,
                          "the plateau floor must reach the job (2026-07-23)")
            self.assertNotIn("NOT_ALLOWED", ses,
                             "non-allow-listed env must be stripped")
            # progress surfaced
            self.assertIn("CEC_PASS", got.get("last_pass") or "")
        finally:
            sv.close()

    def test_route_verdict_classified(self):
        sv = _Server(RUNNER_ROUTE_FAIL)
        try:
            jid = _submit(sv.base)["id"]
            got = _wait_state(sv.base, jid, ("FAILED",))
            self.assertEqual(got["error_kind"], "route")
            self.assertIn("CEC_PLATEAU_KILL", got["error"])
        finally:
            sv.close()

    def test_infra_crash_classified(self):
        sv = _Server(RUNNER_INFRA_FAIL)
        try:
            jid = _submit(sv.base)["id"]
            got = _wait_state(sv.base, jid, ("FAILED",))
            self.assertEqual(got["error_kind"], "infra")
        finally:
            sv.close()

    def test_cancel_kills_running_job(self):
        sv = _Server(RUNNER_SLOW)
        try:
            jid = _submit(sv.base)["id"]
            _wait_state(sv.base, jid, ("RUNNING",))
            req = urllib.request.Request(sv.base + f"/v1/jobs/{jid}",
                                         method="DELETE")
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertTrue(json.loads(r.read().decode())["cancelled"])
            got = _wait_state(sv.base, jid, ("CANCELLED",))
            self.assertEqual(got["state"], "CANCELLED")
        finally:
            sv.close()

    def test_output_before_done_is_409(self):
        sv = _Server(RUNNER_SLOW)
        try:
            jid = _submit(sv.base)["id"]
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(sv.base + f"/v1/jobs/{jid}/output",
                                       timeout=10)
            self.assertEqual(cm.exception.code, 409)
            self.workers_cleanup = urllib.request.Request(
                sv.base + f"/v1/jobs/{jid}", method="DELETE")
            urllib.request.urlopen(self.workers_cleanup, timeout=10)
        finally:
            sv.close()


@unittest.skipUnless(os.environ.get("CEC_FR_REST_CLIENT_TESTS", "1") == "1",
                     "client tests disabled")
class TestClientContract(unittest.TestCase):
    """cec_fr._run_freerouting_rest against the fake-runner server. Imports
    cec_fr, which needs pcbnew -- skip on hosts without it (the container CI
    leg runs these; the server-side tests above run everywhere)."""

    @classmethod
    def setUpClass(cls):
        try:
            import cec_fr                                      # noqa: F401
        except Exception as e:                                 # noqa: BLE001
            raise unittest.SkipTest(f"cec_fr unimportable here ({e})")

    def _route(self, base, **kw):
        import cec_fr
        tmp = tempfile.mkdtemp(prefix="frrest_cli_")
        self.addCleanup(shutil.rmtree, tmp, True)
        dsn = os.path.join(tmp, "b.dsn")
        with open(dsn, "w") as fh:
            fh.write("(pcb fake)")
        ses = os.path.join(tmp, "b.ses")
        args = dict(passes=3, opt_time=5, threads=1, seed=7,
                    timeout=30, version="1.7.0-cec2")
        args.update(kw)
        return cec_fr._run_freerouting_rest(base, dsn, ses, **args), ses

    def test_success_writes_ses(self):
        # a pinless test version on BOTH sides: version guard quiet, sha pin
        # check skipped (no FR_RELEASES entry) -> the full round-trip completes.
        sv = _Server(RUNNER_OK, fr_version="0.0-test")
        try:
            ret, ses = self._route(sv.base, version="0.0-test")
            self.assertEqual(ret, ses)
            with open(ses) as fh:
                self.assertIn("(session fake)", fh.read())
        finally:
            sv.close()

    def test_jar_sha_pin_guard(self):
        # real pinned version both sides, but the fake runner reports a bogus
        # jar sha -> the epoch-integrity guard must refuse the result.
        import cec_fr
        if not (cec_fr.FR_RELEASES.get("1.7.0-cec2") or {}).get("jar_sha256"):
            self.skipTest("1.7.0-cec2 carries no sha pin in this tree")
        sv = _Server(RUNNER_OK)
        try:
            with self.assertRaises(cec_fr._RestUnavailable) as cm:
                self._route(sv.base)
            self.assertIn("epoch integrity", str(cm.exception))
        finally:
            sv.close()

    def test_version_mismatch_guard(self):
        import cec_fr
        sv = _Server(RUNNER_OK, fr_version="9.9-other")
        try:
            with self.assertRaises(cec_fr._RestUnavailable) as cm:
                self._route(sv.base)
            self.assertIn("fr_version", str(cm.exception))
        finally:
            sv.close()

    def test_route_verdict_reraises_runtimeerror(self):
        import cec_fr
        sv = _Server(RUNNER_ROUTE_FAIL)
        try:
            with self.assertRaises(RuntimeError) as cm:
                self._route(sv.base)
            self.assertIn("CEC_PLATEAU_KILL", str(cm.exception))
            self.assertNotIsInstance(cm.exception, cec_fr._RestUnavailable)
        finally:
            sv.close()

    def test_infra_failure_raises_unavailable(self):
        import cec_fr
        sv = _Server(RUNNER_INFRA_FAIL)
        try:
            with self.assertRaises(cec_fr._RestUnavailable):
                self._route(sv.base)
        finally:
            sv.close()

    def test_unreachable_server_raises_unavailable(self):
        import cec_fr
        with self.assertRaises(cec_fr._RestUnavailable):
            self._route(f"http://127.0.0.1:{_free_port()}")

    def test_rest_base_gating(self):
        import cec_fr
        old = {k: os.environ.get(k) for k in ("CEC_FREEROUTING_URL", "CEC_FR_REST")}
        try:
            os.environ.pop("CEC_FREEROUTING_URL", None)
            self.assertIsNone(cec_fr._rest_base())
            os.environ["CEC_FREEROUTING_URL"] = "http://x:1/"
            self.assertEqual(cec_fr._rest_base(), "http://x:1")
            os.environ["CEC_FR_REST"] = "0"
            self.assertIsNone(cec_fr._rest_base())
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
