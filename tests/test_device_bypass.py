import unittest

import cec_device_bypass as bypass


class DeviceBypassTests(unittest.TestCase):
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
