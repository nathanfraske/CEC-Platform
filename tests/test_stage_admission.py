import json
import os
import sys
import unittest
from types import SimpleNamespace


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cec_stage_admission as admission


def metric(*, drc=0, unconnected=0, nets=(), faults=(), kelvin=True,
           diffpair=True, endpoint_hash=""):
    violations = []
    for kind, uuids in faults:
        violations.append({
            "type": kind,
            "items": [{"uuid": uuid} for uuid in uuids],
        })
    return SimpleNamespace(
        drc=drc, unconnected=unconnected,
        kelvin_ok=kelvin, diffpair_ok=diffpair,
        detail={
            "unconn_nets": list(nets),
            "structural_violations": violations,
            "unconn_signature_sha256": endpoint_hash,
        })


class StageAdmissionTests(unittest.TestCase):
    def test_rejects_lower_count_drc_debt_swap(self):
        before = metric(
            drc=2, unconnected=3, nets=("/OPEN",),
            faults=(("clearance", ("old-a", "old-b")),
                    ("track_dangling", ("old-c",))))
        after = metric(
            drc=1, unconnected=2, nets=("/OPEN",),
            faults=(("shorting_items", ("new-a", "new-b")),))

        result = admission.evaluate(before, after, require_strict=True)

        self.assertFalse(result["accepted"])
        self.assertEqual(result["decision"],
                         "new_structural_drc_identity")
        self.assertEqual(len(result["new_structural_drc_identities"]), 1)

    def test_rejects_lower_count_connectivity_debt_swap(self):
        before = metric(unconnected=4, nets=("/OLD", "/KEEP"))
        after = metric(unconnected=3, nets=("/NEW", "/KEEP"))

        result = admission.evaluate(before, after, require_strict=True)

        self.assertFalse(result["accepted"])
        self.assertEqual(result["decision"], "new_unconnected_nets")
        self.assertEqual(result["new_unconnected_nets"], ["/NEW"])

    def test_accepts_strict_subset_closure(self):
        before = metric(
            drc=1, unconnected=3, nets=("/A", "/B"),
            faults=(("clearance", ("a", "b")),))
        after = metric(drc=0, unconnected=2, nets=("/A",))

        result = admission.evaluate(before, after, require_strict=True)

        self.assertTrue(result["accepted"])
        self.assertEqual(result["decision"],
                         "strict_structural_improvement")

    def test_cosmetic_stage_must_preserve_open_net_identity(self):
        before = metric(unconnected=2, nets=("/A", "/B"))
        after = metric(unconnected=2, nets=("/A",))

        result = admission.evaluate(
            before, after, preserve_unconnected=True)

        self.assertFalse(result["accepted"])
        self.assertIn("unconnected_identity_changed", result["reasons"])

    def test_endpoint_reselection_is_telemetry_not_a_false_rejection(self):
        before = metric(unconnected=1, nets=("/A",), endpoint_hash="old")
        after = metric(unconnected=1, nets=("/A",), endpoint_hash="new")

        result = admission.evaluate(
            before, after, preserve_unconnected=True)

        self.assertTrue(result["accepted"])
        self.assertTrue(result["unconn_endpoint_signature_changed"])

    def test_pre_route_contract_allows_only_named_temporary_debt(self):
        before = metric()
        after = metric(
            drc=1, unconnected=1, nets=("GND",),
            faults=(("via_dangling", ("new-via",)),))

        accepted = admission.evaluate(
            before, after, allow_unconnected_growth=True,
            allowed_new_unconnected_nets=("GND",),
            allowed_new_drc_types=("via_dangling",))
        refused = admission.evaluate(
            before, after, allow_unconnected_growth=True,
            allowed_new_unconnected_nets=("/SOMETHING_ELSE",),
            allowed_new_drc_types=("via_dangling",))

        self.assertTrue(accepted["accepted"])
        self.assertFalse(refused["accepted"])
        self.assertEqual(refused["decision"], "new_unconnected_nets")

    def test_legacy_mapping_and_reason_precedence_remain_compatible(self):
        identity = json.dumps(
            ["clearance", "uuid", ["old"]], separators=(",", ":"))
        before = {
            "drc": 1, "unconnected": 1, "unconn_nets": ["/A"],
            "kelvin_ok": True, "diffpair_ok": True,
            "structural_drc_identities": [identity],
        }
        after = {**before, "drc": 0, "unconnected": 2}

        self.assertEqual(
            admission.accepts(before, after, require_strict=True),
            (False, "unconnected_regressed"))


if __name__ == "__main__":
    unittest.main()
