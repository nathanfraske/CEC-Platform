import unittest

import cec_device_bypass as bypass


class DeviceBypassTests(unittest.TestCase):
    def test_reference_affinity_uses_complete_repeated_channel_key(self):
        self.assertTrue(bypass.reference_affinity("C30", "U30"))
        self.assertTrue(bypass.reference_affinity("C65VSB1", "U65VSB1"))
        self.assertFalse(bypass.reference_affinity("C65V1", "U75V1"))
        self.assertFalse(bypass.reference_affinity("C75VSB1", "U75V1"))

    def test_tja1051t3_requires_distinct_vcc_and_vio_bypass_cells(self):
        ground = list(bypass.requirements_for_value("TJA1051T/3"))
        rail_to_rail = list(
            bypass.rail_to_rail_requirements_for_value("TJA1051T/3"))

        self.assertEqual(
            [(pin, kind) for pin, kind, _distance, _source in ground],
            [("3", "100n")])
        self.assertEqual(
            [(pin, return_pin, kind) for pin, return_pin, kind,
             _distance, _source in rail_to_rail],
            [("5", "3", "100n")])

    def test_tps2121_pin_roles_require_local_hf_capacitors(self):
        requirements = list(bypass.requirements_for_value("TPS2121RUXR"))

        self.assertEqual(
            [(pin, kind) for pin, kind, _distance, _source in requirements],
            [("7", "local-hf"), ("2", "local-hf"),
             ("1", "local-hf")])
        self.assertTrue(bypass.kind_compatible("local-hf", 100e-9))
        self.assertTrue(bypass.kind_compatible("local-hf", 1e-6))
        self.assertFalse(bypass.kind_compatible("local-hf", 10e-6))


if __name__ == "__main__":
    unittest.main()
