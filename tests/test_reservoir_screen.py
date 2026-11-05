import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cec_reservoir_screen import discharge_ms, tolerance_aged_capacitance


class ReservoirScreenTest(unittest.TestCase):
    def setUp(self):
        self.args = dict(capacitance_f=.00376, start_v=4.15, floor_v=3.45,
                         input_power_w=.759597)

    def test_matches_energy_identity(self):
        a = self.args
        expected = .5 * a["capacitance_f"] * (
            a["start_v"] ** 2 - a["floor_v"] ** 2) / a["input_power_w"] * 1000
        self.assertAlmostEqual(discharge_ms(**a), expected, places=10)

    def test_leakage_matches_independent_closed_form(self):
        a, leak = self.args, .000752
        p, v0, v1 = a["input_power_w"], a["start_v"], a["floor_v"]
        expected = a["capacitance_f"] * (
            (v0-v1)/leak - p/leak**2 * math.log((p+leak*v0)/(p+leak*v1))) * 1000
        self.assertAlmostEqual(discharge_ms(**a, leakage_a=leak), expected, places=6)

    def test_esr_matches_independent_closed_form(self):
        a, resistance = self.args, .12
        p = a["input_power_w"]
        u0 = (a["start_v"] + math.sqrt(a["start_v"]**2-4*resistance*p))/2
        u1 = a["floor_v"]
        expected = a["capacitance_f"] * (
            (u0**2-u1**2)/(2*p) - resistance*math.log(u0/u1)) * 1000
        self.assertAlmostEqual(discharge_ms(**a, esr_ohm=resistance), expected, places=9)

    def test_losses_reduce_runtime_and_grid_converges(self):
        ideal = discharge_ms(**self.args)
        lossy = discharge_ms(**self.args, esr_ohm=.2, leakage_a=.001)
        self.assertLess(lossy, ideal)
        self.assertAlmostEqual(lossy, discharge_ms(
            **self.args, esr_ohm=.2, leakage_a=.001, intervals=8192), places=9)

    def test_multiplicative_aging(self):
        result = tolerance_aged_capacitance(
            nominal_f=.0047, initial_loss=.2, endurance_loss=.3)
        self.assertAlmostEqual(result, .002632)
        self.assertAlmostEqual(discharge_ms(**{**self.args, "capacitance_f": result}),
                               .7*discharge_ms(**self.args))

    def test_no_headroom(self):
        self.assertEqual(discharge_ms(**{**self.args, "start_v": 3.46}, esr_ohm=.2), 0)

    def test_invalid_inputs_are_not_silent_passes(self):
        for update in ({"esr_ohm": -1}, {"leakage_a": -1}, {"start_v": math.nan},
                       {"capacitance_f": 0}, {"input_power_w": 0},
                       {"intervals": 3}, {"esr_ohm": 100}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                discharge_ms(**{**self.args, **update})
        with self.assertRaises(ValueError):
            tolerance_aged_capacitance(nominal_f=.0047, initial_loss=.2, endurance_loss=1)


if __name__ == "__main__":
    unittest.main()
