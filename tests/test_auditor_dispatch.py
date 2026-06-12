"""Host tests for the T5 auditor seat dispatch (owner 2026-06-12): Sonnet daily / DeepSeek overnight.
No GPU, no `claude` CLI -- the Sonnet and broker backends are stubbed; we test the selector + routing +
the broker path's schema call and failure handling."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cec_fullstack as fs  # noqa: E402
import cec_judge_local as jl  # noqa: E402


def _rec():
    return {"gates_pass": False, "kelvin_ok": True, "diffpair_ok": True, "drc": 3, "unconnected": 2,
            "max_T": 90, "objective": 1.0, "reasons": ["x"], "fem_flags": [], "stub_summary": {}}


def _lr():
    return {"scorer_penalties": {"drc": 50.0}, "manager_rules": [], "injections": [], "rejections": [],
            "diagnoses": [], "refuted_metrics": []}


class TestResolveAuditor(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CEC_FS_AUDITOR_MODEL", None)

    def tearDown(self):
        os.environ.pop("CEC_FS_AUDITOR_MODEL", None)

    def test_default_is_deepseek_regardless_of_run_length(self):
        # V4-Flash is the default chair for BOTH overnight and daily (owner 2026-06-12)
        self.assertEqual(fs.resolve_auditor(None, 6.5), fs.DEEP_AUDITOR)
        self.assertEqual(fs.resolve_auditor(None, None), fs.DEEP_AUDITOR)
        self.assertEqual(fs.resolve_auditor(None), fs.DEEP_AUDITOR)   # hours optional

    def test_sonnet_is_one_env_var_away(self):
        os.environ["CEC_FS_AUDITOR_MODEL"] = "sonnet"
        self.assertEqual(fs.resolve_auditor(None, None), "sonnet")

    def test_explicit_overrides_default(self):
        self.assertEqual(fs.resolve_auditor("sonnet", 6.5), "sonnet")

    def test_env_overrides_default_but_not_explicit(self):
        os.environ["CEC_FS_AUDITOR_MODEL"] = "envmodel"
        self.assertEqual(fs.resolve_auditor(None, 6.5), "envmodel")
        self.assertEqual(fs.resolve_auditor("cli", 6.5), "cli")   # explicit still wins


class TestAuditDispatch(unittest.TestCase):
    def test_sonnet_model_routes_to_sonnet_audit(self):
        called = {}
        orig_s, orig_d = fs.sonnet_audit, fs.deepseek_audit
        fs.sonnet_audit = lambda *a, **k: called.setdefault("seat", "sonnet") or {"verdict": "accept"}
        fs.deepseek_audit = lambda *a, **k: called.setdefault("seat", "deepseek") or {"verdict": "accept"}
        try:
            fs.audit(_rec(), _lr(), 1, "sonnet")
            self.assertEqual(called["seat"], "sonnet")
        finally:
            fs.sonnet_audit, fs.deepseek_audit = orig_s, orig_d

    def test_nonsonnet_model_routes_to_deepseek_audit(self):
        called = {}
        orig_s, orig_d = fs.sonnet_audit, fs.deepseek_audit
        fs.sonnet_audit = lambda *a, **k: called.setdefault("seat", "sonnet") or {"verdict": "accept"}
        fs.deepseek_audit = lambda *a, **k: called.setdefault("seat", "deepseek") or {"verdict": "accept"}
        try:
            fs.audit(_rec(), _lr(), 1, "deepseek-v4-flash")
            self.assertEqual(called["seat"], "deepseek")
        finally:
            fs.sonnet_audit, fs.deepseek_audit = orig_s, orig_d


class TestDeepseekAuditPath(unittest.TestCase):
    def setUp(self):
        # redirect artifact writes to a temp dir so the test never clobbers committed run findings
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_perm = fs.PERM
        fs.PERM = self._tmp.name
        os.makedirs(os.path.join(fs.PERM, "findings"), exist_ok=True)

    def tearDown(self):
        fs.PERM = self._orig_perm
        self._tmp.cleanup()

    def test_broker_call_uses_schema_and_model_and_returns_dict(self):
        captured = {}

        def stub_chat_json(system, user, schema, *, name="out", temperature=0.0, max_tokens=None,
                           timeout=None, model=None, **kw):
            captured.update(schema=schema, model=model, name=name)
            return {"verdict": "repair", "root_cause": "rc", "reasoning": "r",
                    "failure_class": "routing", "proposed_lever": None,
                    "scorer_penalty": None, "manager_rule": None}

        orig = jl._chat_json
        jl._chat_json = stub_chat_json
        try:
            out = fs.deepseek_audit(_rec(), _lr(), 1, model="deepseek-v4-flash")
        finally:
            jl._chat_json = orig
        self.assertEqual(out["verdict"], "repair")
        self.assertEqual(out["root_cause"], "rc")
        self.assertIs(captured["schema"], fs.AUDIT_SCHEMA)       # the contract schema is enforced
        self.assertEqual(captured["model"], "deepseek-v4-flash")  # the right seat is targeted

    def test_broker_error_degrades_to_repair(self):
        def boom(*a, **k):
            raise RuntimeError("broker down")
        orig = jl._chat_json
        jl._chat_json = boom
        try:
            out = fs.deepseek_audit(_rec(), _lr(), 1, model="deepseek-v4-flash")
        finally:
            jl._chat_json = orig
        self.assertEqual(out["verdict"], "repair")               # fail-safe, never raises into the loop
        self.assertIn("broker down", out["error"])


if __name__ == "__main__":
    unittest.main()
