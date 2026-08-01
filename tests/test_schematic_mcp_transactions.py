#!/usr/bin/env python3
"""Transactional safety checks for the schematic MCP mutator wrapper."""

import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class _FastMCP:
    def __init__(self, _name):
        pass

    def tool(self):
        return lambda fn: fn

    def run(self):
        pass


fake_fastmcp = types.ModuleType("mcp.server.fastmcp")
fake_fastmcp.FastMCP = _FastMCP
fake_server = types.ModuleType("mcp.server")
fake_server.fastmcp = fake_fastmcp
fake_mcp = types.ModuleType("mcp")
fake_mcp.server = fake_server
with mock.patch.dict(sys.modules, {
        "mcp": fake_mcp, "mcp.server": fake_server,
        "mcp.server.fastmcp": fake_fastmcp}):
    MCP = importlib.import_module("cec_sch_mcp")


class SchematicMcpTransactionTest(unittest.TestCase):
    def _files(self, directory):
        root = os.path.join(directory, "root.kicad_sch")
        child = os.path.join(directory, "child.kicad_sch")
        for path, text in ((root, "root-before\n"),
                           (child, "child-before\n")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        return root, child

    def test_mutator_exception_restores_root_and_sibling_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, child = self._files(directory)

            def mutator():
                with open(root, "w", encoding="utf-8") as handle:
                    handle.write("root-damaged\n")
                with open(child, "w", encoding="utf-8") as handle:
                    handle.write("child-damaged\n")
                raise RuntimeError("controlled failure")

            groups = {frozenset({("U1", "1"), ("R1", "1")}): "SIG"}
            with mock.patch.object(MCP, "_project_sheets",
                                   return_value=[root, child]), \
                    mock.patch.object(MCP, "_netlist_groups",
                                      return_value=groups):
                result = MCP._gated(root, mutator)

            self.assertFalse(result["ok"])
            self.assertTrue(result["rolled_back"])
            with open(root, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "root-before\n")
            with open(child, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "child-before\n")

    def test_explicit_false_result_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root, child = self._files(directory)

            def mutator():
                with open(root, "w", encoding="utf-8") as handle:
                    handle.write("changed\n")
                return False

            groups = {frozenset({("U1", "1")}): "SIG"}
            with mock.patch.object(MCP, "_project_sheets",
                                   return_value=[root, child]), \
                    mock.patch.object(MCP, "_netlist_groups",
                                      return_value=groups):
                result = MCP._gated(root, mutator)

            self.assertFalse(result["ok"])
            self.assertTrue(result["rolled_back"])
            with open(root, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "root-before\n")

    def test_connectivity_delta_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root, child = self._files(directory)
            before = {frozenset({("U1", "1"), ("R1", "1")}): "SIG"}
            after = {frozenset({("U1", "1")}): "SIG"}

            def mutator():
                with open(root, "w", encoding="utf-8") as handle:
                    handle.write("changed\n")
                return 1

            with mock.patch.object(MCP, "_project_sheets",
                                   return_value=[root, child]), \
                    mock.patch.object(MCP, "_netlist_groups",
                                      side_effect=[before, after]):
                result = MCP._gated(root, mutator)

            self.assertFalse(result["ok"])
            self.assertTrue(result["rolled_back"])
            with open(root, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "root-before\n")


if __name__ == "__main__":
    unittest.main()
