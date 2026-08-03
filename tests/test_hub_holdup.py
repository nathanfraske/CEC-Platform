import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_hub_holdup as holdup
import cec_beta_electrical_audit as audit
import cec_sch_gates


class TestHubHoldup(unittest.TestCase):
    def test_sudden_loss_budget_precedes_buck_dropout(self):
        result = holdup.model()
        self.assertGreater(result["sudden_loss_hold_ms"], 11.9)
        self.assertGreater(result["sudden_loss_margin_ms"], 1.9)
        self.assertGreater(result["trip_to_regulation_headroom_min_V"], 0.05)

    def test_detector_is_fast_and_threshold_is_bounded(self):
        result = holdup.model()
        self.assertGreater(result["trip_nominal_V"], 4.35)
        self.assertLess(result["trip_nominal_V"], 4.36)
        self.assertGreater(result["trip_min_V"], 4.05)
        self.assertLess(result["trip_max_V"], 4.67)
        self.assertLess(result["five_volt_step_crossing_us"], 25.0)

    def test_live_hub_topology_matches_the_model(self):
        schematic = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")
        _components, nets = audit.export_netlist(schematic)
        inventory = cec_sch_gates.inventory(schematic)
        findings = audit._check_hub_holdup(
            "hub-standard-rev2", inventory, audit.pin_map(nets))
        self.assertFalse([f for f in findings if f["severity"] == "BLOCKER"])
        self.assertTrue(any(f["code"] == "HOLDUP_SOURCE_DROPOUT_ORDER"
                            for f in findings))


if __name__ == "__main__":
    unittest.main()
