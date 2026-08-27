import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_power_budget as power


class TestPowerBudget(unittest.TestCase):
    def test_12vhpwr_component_sum_and_margin(self):
        result = power.budget("12vhpwr-standard")
        self.assertAlmostEqual(result["subtotal_mA"], 176.939, places=6)
        self.assertAlmostEqual(result["required_mA"], 212.3268, places=6)
        self.assertEqual(next(row for row in result["loads"]
                              if row["name"].startswith("INA240"))["quantity"], 6)

    def test_hub_component_sum_and_margin(self):
        result = power.budget("hub-standard-rev2")
        self.assertAlmostEqual(result["subtotal_mA"], 163.044805, places=6)
        self.assertAlmostEqual(result["required_mA"], 195.653766, places=6)

    def test_pcie_wireless_disabled_component_sums_and_margin(self):
        expected = {
            "pcie-8pin-2port": (168.96, 202.752),
            "pcie-8pin-3port": (170.70, 204.84),
        }
        for board, (subtotal, required) in expected.items():
            result = power.budget(board)
            self.assertAlmostEqual(result["subtotal_mA"], subtotal, places=6)
            self.assertAlmostEqual(result["required_mA"], required, places=6)
            self.assertLess(result["required_mA"], 250.0)

    def test_eps_wireless_disabled_component_sum_and_margin(self):
        result = power.budget("eps-8pin-rev3")
        self.assertAlmostEqual(result["subtotal_mA"], 167.31, places=6)
        self.assertAlmostEqual(result["required_mA"], 200.772, places=6)
        self.assertLess(result["required_mA"], 250.0)

    def test_margin_is_applied_once_to_whole_subtotal(self):
        for board in power.LOADS:
            result = power.budget(board)
            self.assertAlmostEqual(
                result["required_mA"],
                result["subtotal_mA"] * (1.0 + power.DESIGN_MARGIN),
                places=9,
            )


if __name__ == "__main__":
    unittest.main()
