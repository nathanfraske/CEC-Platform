import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fix_esp32c6_boot_straps as fix


class TestFixEsp32C6BootStraps(unittest.TestCase):
    def test_remove_no_connect_removes_only_exact_pin(self):
        text = (
            '(no_connect (at 10 20) (uuid "a"))\n'
            '(no_connect (at 10 21) (uuid "b"))\n'
        )
        self.assertEqual(
            fix._remove_no_connect(text, 10.0, 20.0),
            '(no_connect (at 10 21) (uuid "b"))\n',
        )

    def test_remove_no_connect_rejects_missing_input(self):
        with self.assertRaisesRegex(RuntimeError, "expected one no-connect"):
            fix._remove_no_connect("", 10.0, 20.0)


if __name__ == "__main__":
    unittest.main()
