import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fix_esp32c6_symbol_types as fix


class TestEsp32C6SymbolTypes(unittest.TestCase):
    def test_pin_roles_are_mapped_from_the_datasheet(self):
        source = '''(kicad_symbol_lib
 (symbol "ESP32-C6-MINI-1-N4"
  (symbol "unit"
   (pin unspecified line (at 0 0 0) (name "3V3") (number "3"))
   (pin unspecified line (at 0 1 0) (name "NC") (number "4"))
   (pin unspecified line (at 0 2 0) (name "EN") (number "8"))
   (pin unspecified line (at 0 3 0) (name "IO20") (number "26")))))'''
        updated, changes = fix.update_text(source)
        self.assertEqual(changes, 4)
        self.assertIn("(pin power_in line", updated)
        self.assertIn("(pin no_connect line", updated)
        self.assertIn("(pin input line", updated)
        self.assertIn("(pin bidirectional line", updated)
        verified, remaining = fix.update_text(updated)
        self.assertEqual(verified, updated)
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
