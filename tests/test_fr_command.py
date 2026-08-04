#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr


class TestFreeroutingDisplayIsolation(unittest.TestCase):
    def test_parallel_linux_route_gets_unique_display_and_auth_file(self):
        with tempfile.TemporaryDirectory() as workdir, \
                mock.patch.object(cec_fr.sys, "platform", "linux"), \
                mock.patch.object(cec_fr.shutil, "which",
                                  return_value="/usr/bin/xvfb-run"), \
                mock.patch.object(cec_fr, "_fr_engine",
                                  return_value=["java", "-jar", "fr.jar"]), \
                mock.patch.object(cec_fr.os, "getpid", return_value=4217), \
                mock.patch.dict(os.environ, {"CEC_FR_USE_DISPLAY": ""}):
            command = cec_fr._fr_command(
                "fr.jar", "input.dsn", "output.ses", 7, 30, 1,
                version="1.7.0", workdir=workdir)

        self.assertEqual(command[:5],
                         ["xvfb-run", "-a", "-n", "5217", "-f"])
        self.assertEqual(command[5],
                         os.path.join(workdir, ".cec-fr-xauth-4217"))
        self.assertEqual(command[6:9], ["java", "-jar", "fr.jar"])


if __name__ == "__main__":
    unittest.main()
