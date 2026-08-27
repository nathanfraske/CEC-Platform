"""Endpoint-level route residual signatures must be stable and useful."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_score  # noqa: E402


class UnconnectedSignatureTest(unittest.TestCase):
    def test_order_independent_endpoint_signature_and_distance(self):
        left = {"description": "Pad 1 [/USB_CC1] of R9 on F.Cu",
                "pos": {"x": 46.5, "y": 65.735}}
        right = {"description": "Pad A5 [/USB_CC1] of J_USB on F.Cu",
                 "pos": {"x": 48.7, "y": 67.805}}
        a = cec_score._unconnected_signature([{"items": [left, right]}])
        b = cec_score._unconnected_signature([{"items": [right, left]}])
        self.assertEqual(a, b)
        self.assertEqual(a[0]["nets"], ["/USB_CC1"])
        self.assertAlmostEqual(a[0]["distance_mm"], 3.0207, places=4)


if __name__ == "__main__":
    unittest.main()
