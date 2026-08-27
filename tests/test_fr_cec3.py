#!/usr/bin/env python3
"""Regression teeth for the large-DSN Freerouting parser repair."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr  # noqa: E402


class FreeroutingCec3ContractTest(unittest.TestCase):
    def test_cec3_is_default_and_hash_pinned(self):
        self.assertEqual(
            cec_fr.FR_VERSION,
            os.environ.get("CEC_FR_VERSION", "1.7.0-cec3"))
        release = cec_fr.FR_RELEASES["1.7.0-cec3"]
        self.assertEqual(
            release["jar_sha256"],
            "202136e7e73d5aa3e2a852bab186f71b67289a4068dee0804cb9c7b2efd8c7f7")
        self.assertTrue(release["supports_seed"])
        self.assertTrue(release["supports_noecho"])
        self.assertTrue(release["supports_progress"])

    def test_incremental_patch_refills_instead_of_raising_fixed_ceiling(self):
        path = os.path.join(
            ROOT, "scripts", "patches", "freerouting-1.7.0-cec3.patch")
        with open(path, encoding="utf-8") as handle:
            patch = handle.read()
        self.assertIn("ensureStringInput", patch)
        self.assertIn("zzReader.read", patch)
        self.assertIn("new char[Math.max(zzBuffer.length * 2, index + 1)]",
                      patch)
        self.assertNotIn("ZZ_BUFFERSIZE =", patch)


if __name__ == "__main__":
    unittest.main()
