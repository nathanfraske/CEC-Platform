import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_normalize_verified_lcsc_parts as normalize


class TestVerifiedLcscNormalization(unittest.TestCase):
    def test_selected_order_code_controls_vendor_identity(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:ESD")
    (at 1 2 0)
    (property "Reference" "D1" (at 1 2 0))
    (property "Value" "PESD5V0S1BA" (at 1 2 0))
    (property "Footprint" "x" (at 1 2 0))
    (property "Datasheet" "nexperia" (at 1 2 0) (effects (hide yes)))
    (property "Manufacturer" "Nexperia" (at 1 2 0) (effects (hide yes)))
    (property "MPN" "PESD5V0S1BA" (at 1 2 0) (effects (hide yes)))
    (property "LCSC" "C5261083" (at 1 2 0) (effects (hide yes)))
  )
)'''
        first, refs = normalize.normalize_text(text)
        second, refs2 = normalize.normalize_text(first)
        self.assertEqual(refs, ["D1"])
        self.assertEqual(refs2, [])
        self.assertEqual(first, second)
        self.assertIn('(property "Manufacturer" "HXY MOSFET"', first)
        self.assertNotIn('"Nexperia"', first)
        self.assertIn('C5261083.pdf', first)

    def test_unknown_order_code_is_not_inferred(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:ESD")
    (at 1 2 0)
    (property "Reference" "D1" (at 1 2 0))
    (property "Value" "PESD5V0S1BA" (at 1 2 0))
    (property "Footprint" "x" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
    (property "Manufacturer" "Owner choice" (at 1 2 0) (effects (hide yes)))
    (property "LCSC" "C999999" (at 1 2 0) (effects (hide yes)))
  )
)'''
        repaired, refs = normalize.normalize_text(text)
        self.assertEqual(refs, [])
        self.assertEqual(repaired, text)

    def test_exact_orderable_suffix_is_preserved(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:LP5907")
    (at 1 2 0)
    (property "Reference" "U1" (at 1 2 0))
    (property "Value" "LP5907MFX-3.3" (at 1 2 0))
    (property "Footprint" "x:SOT-23-5" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
    (property "Manufacturer" "" (at 1 2 0) (effects (hide yes)))
    (property "MPN" "LP5907MFX-3.3" (at 1 2 0) (effects (hide yes)))
    (property "LCSC" "C80670" (at 1 2 0) (effects (hide yes)))
  )
)'''
        repaired, refs = normalize.normalize_text(text)
        self.assertEqual(refs, ["U1"])
        self.assertIn('(property "MPN" "LP5907MFX-3.3/NOPB"', repaired)
        self.assertIn('(property "Manufacturer" "Texas Instruments"', repaired)

    def test_exact_connector_footprint_can_control_identity(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:Connector")
    (at 1 2 0)
    (property "Reference" "J1" (at 1 2 0))
    (property "Value" "TO-HUB-PWR" (at 1 2 0))
    (property "Footprint" "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
  )
)'''
        repaired, refs = normalize.normalize_text(text)
        self.assertEqual(refs, ["J1"])
        self.assertIn('(property "Manufacturer" "JST"', repaired)
        self.assertIn('(property "MPN" "S2B-XH-A(LF)(SN)"', repaired)
        self.assertIn('(property "LCSC" "C157931"', repaired)

    def test_verified_capacitor_code_repairs_identity(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:C_Small")
    (at 1 2 0)
    (property "Reference" "C1" (at 1 2 0))
    (property "Value" "1uF" (at 1 2 0))
    (property "Footprint" "x:C_0603_1608Metric" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
    (property "Manufacturer" "Samsung" (at 1 2 0) (effects (hide yes)))
    (property "MPN" "CL10B105KO8NNNC" (at 1 2 0) (effects (hide yes)))
    (property "LCSC" "C15849" (at 1 2 0) (effects (hide yes)))
  )
)'''
        repaired, refs = normalize.normalize_text(text)
        self.assertEqual(refs, ["C1"])
        self.assertIn('(property "MPN" "CL10A105KB8NNNC"', repaired)
        self.assertIn('(property "Manufacturer" "Samsung"', repaired)

    def test_verified_capacitor_package_mismatch_is_not_hidden(self):
        expected = normalize.VERIFIED["C96446"]
        self.assertEqual(expected["MPN"], "CL10A106MA8NRNC")
        self.assertNotEqual(expected["MPN"], "CL21A106KAYNNNE")
        self.assertEqual(
            normalize.VERIFIED["C23630"]["MPN"],
            "CL10A225KO8NNNC",
        )
        self.assertEqual(normalize.VERIFIED["C17168"]["MPN"],
                         "0402WGF0000TCE")
        self.assertEqual(normalize.VERIFIED["C545549"]["Manufacturer"],
                         "UMW")


if __name__ == "__main__":
    unittest.main()
