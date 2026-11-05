import unittest

import cec_device_bypass as bypass


class DeviceBypassTests(unittest.TestCase):
    def test_positive_native_capacitor_identity_supports_renamed_imports(self):
        self.assertTrue(bypass.capacitor_identity('arbitrary_bypass',
            'Capacitor_SMD:C_0603_1608Metric'))
        self.assertTrue(bypass.capacitor_identity('renamed_reservoir',
            'Capacitor_THT:CP_Radial_D5.0mm_P2.00mm'))
        self.assertTrue(bypass.capacitor_identity('C_legacy_import', 'unknown'))
        self.assertFalse(bypass.capacitor_identity('renamed_resistor',
            'Resistor_SMD:R_0603_1608Metric'))
        self.assertFalse(bypass.capacitor_identity('arbitrary_part',
            'NotCapacitor_SMD:C_0603_1608Metric'))
        # The permissive unitless value parser is not capacitor identity.
        self.assertEqual(bypass.capacitance_f('2200'),2200)
        self.assertFalse(bypass.capacitor_identity('R2200',
            'Resistor_SMD:R_0603_1608Metric'))

    def test_augmenting_chain_preserves_displaced_owners(self):
        got = bypass.distinct_assignment({
            "RAIL_A": [("CAP_A", 1), ("CAP_B", 2)],
            "RAIL_B": [("CAP_A", 3)],
        }, ["RAIL_A", "RAIL_B"])
        self.assertEqual(got, {"RAIL_A": ("CAP_B", 2),
                               "RAIL_B": ("CAP_A", 3)})

    def test_matching_is_bounded_by_edges_not_python_recursion_limit(self):
        edges = {i: [(i, i), (i+1, i+1)] for i in range(1500)}
        edges[1500] = [(0, 0)]
        got = bypass.distinct_assignment(edges, range(1501))
        self.assertEqual(len(got), 1501)
        self.assertEqual(len({cap for cap, _ in got.values()}), 1501)

    def test_matching_does_not_invent_missing_compatibility(self):
        got = bypass.distinct_assignment({"A": [("C", 1)],
                                          "B": [("C", 2)], "D": []},
                                         ["A", "B", "D"])
        self.assertEqual(got, {"A": ("C", 1)})

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

    def test_tps2121_local_ceramics_do_not_have_an_invented_value_ceiling(self):
        requirements = list(bypass.requirements_for_value("TPS2121RUXR"))

        self.assertEqual(
            [(pin, kind) for pin, kind, _distance, _source in requirements],
            [("7", "local-ceramic"), ("2", "local-ceramic"),
             ("1", "local-ceramic")])
        self.assertTrue(bypass.kind_compatible("local-ceramic", 10e-6))
        self.assertFalse(bypass.kind_compatible("local-ceramic", 0))
        self.assertFalse(bypass.local_bypass_technology("470uF", "Capacitor_SMD:CP_Elec_6.3x7.7"))
        # The separate project HF rule remains available for devices that
        # actually request it; this is not a global relaxation of bypasses.
        self.assertTrue(bypass.kind_compatible("local-hf", 100e-9))
        self.assertTrue(bypass.kind_compatible("local-hf", 1e-6))
        self.assertFalse(bypass.kind_compatible("local-hf", 10e-6))

    def test_esp32_s3_wroom_requires_hf_and_local_bulk_cells(self):
        requirements = list(
            bypass.requirements_for_value("ESP32-S3-WROOM-1-N16R8"))

        self.assertEqual(
            [(pin, kind) for pin, kind, _distance, _source in requirements],
            [("2", "100n"), ("2", "at-least-10u")])

    def test_explicit_bypass_owner_parses_reference_and_pin(self):
        self.assertEqual(
            bypass.declared_owner({"BypassOwner": "U65VSB1.6"}),
            ("U65VSB1", "6"))
        self.assertIsNone(bypass.declared_owner({}))
        self.assertEqual(
            bypass.declared_owner({"BypassOwner": "not a reference"}),
            ("not a reference", ""))


if __name__ == "__main__":
    unittest.main()
