import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sync_assembly_state as sync


class TestAssemblyStateSync(unittest.TestCase):
    def test_only_attr_tokens_change(self):
        board = '''(kicad_pcb
  (footprint "X:R"
    (layer "F.Cu")
    (property "Reference" "L2" (at 0 0 0))
    (attr smd)
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))
)'''
        updated, changed = sync.synchronize_text(
            board, {"L2": {"dnp": True, "in_bom": False}})
        self.assertEqual(changed, ["L2"])
        self.assertEqual(
            updated,
            board.replace("(attr smd)", "(attr smd exclude_from_bom dnp)"),
        )
        verified, remaining = sync.synchronize_text(
            updated, {"L2": {"dnp": True, "in_bom": False}})
        self.assertEqual(verified, updated)
        self.assertEqual(remaining, [])

    def test_bom_included_dnp_keeps_only_dnp_token(self):
        board = '''(kicad_pcb
  (footprint "X:J"
    (property "Reference" "J6P" (at 0 0 0))
    (attr through_hole exclude_from_bom)
  )
)'''
        updated, _ = sync.synchronize_text(
            board, {"J6P": {"dnp": True, "in_bom": True}})
        self.assertIn("(attr through_hole dnp)", updated)
        self.assertNotIn("exclude_from_bom", updated)

    def test_crlf_noop_is_not_reported_as_an_assembly_change(self):
        board = (
            '(kicad_pcb\r\n'
            '  (footprint "X:R"\r\n'
            '    (property "Reference" "R1" (at 0 0 0))\r\n'
            '    (attr smd)\r\n'
            '  )\r\n'
            ')\r\n'
        )
        updated, changed = sync.synchronize_text(
            board, {"R1": {"dnp": False, "in_bom": True}})
        self.assertEqual(updated, board)
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
