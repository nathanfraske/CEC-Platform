import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fix_eps_rev3_bom_fields as fix


class TestEpsRev3BomRepair(unittest.TestCase):
    def test_swaps_only_structurally_reversed_fields(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:R")
    (at 1 2 0)
    (property "Reference" "R1" (at 1 2 0))
    (property "Value" "10k" (at 1 2 0))
    (property "Footprint" "x" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
    (property "Manufacturer" "C25744" (at 1 2 0) (effects (hide yes)))
    (property "MPN" "0402WGF1002TCE" (at 1 2 0) (effects (hide yes)))
    (property "LCSC" "UNI-ROYAL" (at 1 2 0) (effects (hide yes)))
  )
)'''
        repaired, refs = fix.repair_text(text)
        self.assertEqual(refs, ["R1"])
        self.assertIn('(property "Manufacturer" "UNI-ROYAL"', repaired)
        self.assertIn('(property "LCSC" "C25744"', repaired)

    def test_backfill_is_idempotent(self):
        text = '''(kicad_sch
  (lib_symbols)
  (symbol
    (lib_id "x:J")
    (at 1 2 0)
    (property "Reference" "J_IN1" (at 1 2 0))
    (property "Value" "C1 PSU" (at 1 2 0))
    (property "Footprint" "cec-Connector_Molex:Molex_Mini-Fit_Jr_87427-0802_2x04_P4.20mm_RA" (at 1 2 0))
    (property "Datasheet" "" (at 1 2 0) (effects (hide yes)))
  )
)'''
        first, refs = fix.repair_text(text)
        second, refs2 = fix.repair_text(first)
        self.assertEqual(refs, ["J_IN1"])
        self.assertEqual(refs2, [])
        self.assertEqual(first, second)
        self.assertIn('(property "MPN" "87427-0802"', first)
        self.assertIn('(property "Manufacturer" "Molex"', first)


if __name__ == "__main__":
    unittest.main()
