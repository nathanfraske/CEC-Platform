#!/usr/bin/env python3
"""Transactional autorouter-import sanitation regressions."""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as synth  # noqa: E402


def metric(*, drc, unconnected, violations=(), nets=(), kelvin=True,
           diffpair=True):
    kinds = {}
    for row in violations:
        kind = str(row.get("type") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return SimpleNamespace(
        drc=drc, unconnected=unconnected, drc_types=kinds,
        kelvin_ok=kelvin, diffpair_ok=diffpair,
        detail={
            "structural_violations": list(violations),
            "unconn_nets": list(nets),
            "kelvin_topology_faults": [],
            "route_topology_fault_nets": [],
        })


def violation(kind, *uuids):
    return {
        "type": kind,
        "description": kind,
        "items": [{"uuid": uuid, "description": uuid} for uuid in uuids],
    }


class RouteImportSanitationTest(unittest.TestCase):
    def _paths(self, directory):
        baseline = os.path.join(directory, "baseline.kicad_pcb")
        candidate = os.path.join(directory, "candidate.kicad_pcb")
        with open(baseline, "wb") as sink:
            sink.write(b"baseline")
        with open(candidate, "wb") as sink:
            sink.write(b"candidate")
        return baseline, candidate

    def test_removes_only_generated_items_named_by_new_drc(self):
        baseline_metric = metric(drc=0, unconnected=8, nets=["/OPEN"])
        imported_metric = metric(
            drc=1, unconnected=4, nets=["/OPEN"],
            violations=[violation("clearance", "prefix", "generated")])
        clean_metric = metric(drc=0, unconnected=5, nets=["/OPEN"])
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = self._paths(directory)
            with mock.patch.object(
                    synth.cec_score, "score",
                    side_effect=[baseline_metric, imported_metric,
                                 clean_metric]), \
                    mock.patch.object(
                        synth, "_remove_structural_dangling_uuids_isolated",
                        return_value={
                            "removed": [{"uuid": "generated",
                                         "kind": "clearance",
                                         "net": "/SIG"}]}) as remove:
                report, result = synth._sanitize_imported_route_transactionally(
                    candidate, baseline, {"generated"})

        self.assertTrue(report["accepted"], report)
        self.assertEqual(report["removed_count"], 1)
        self.assertIs(result, clean_metric)
        targets = remove.call_args.args[1]
        self.assertEqual(targets, [{"uuid": "generated",
                                    "kind": "clearance"}])
        self.assertTrue(remove.call_args.kwargs["refill_zones"])

    def test_new_fault_without_generated_owner_fails_closed(self):
        baseline_metric = metric(drc=0, unconnected=8, nets=["/OPEN"])
        imported_metric = metric(
            drc=1, unconnected=4, nets=["/OPEN"],
            violations=[violation("shorting_items", "prefix-a",
                                  "prefix-b")])
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = self._paths(directory)
            with mock.patch.object(
                    synth.cec_score, "score",
                    side_effect=[baseline_metric, imported_metric,
                                 baseline_metric]), \
                    mock.patch.object(
                        synth, "_remove_structural_dangling_uuids_isolated") \
                    as remove:
                report, _result = synth._sanitize_imported_route_transactionally(
                    candidate, baseline, {"generated"})
            with open(candidate, "rb") as source:
                restored = source.read()

        self.assertFalse(report["accepted"])
        self.assertTrue(report["rolled_back"])
        self.assertEqual(report["reason"], "unowned_new_structural_drc")
        self.assertEqual(restored, b"candidate")
        remove.assert_not_called()

    def test_topology_regression_rolls_back_even_after_drc_cleanup(self):
        baseline_metric = metric(drc=0, unconnected=8, nets=["/OPEN"])
        imported_metric = metric(
            drc=1, unconnected=4, nets=["/OPEN"],
            violations=[violation("clearance", "generated")])
        broken_metric = metric(
            drc=0, unconnected=9, nets=["/OPEN", "/NEW"], kelvin=False)
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = self._paths(directory)
            with mock.patch.object(
                    synth.cec_score, "score",
                    side_effect=[baseline_metric, imported_metric,
                                 broken_metric, baseline_metric]), \
                    mock.patch.object(
                        synth, "_remove_structural_dangling_uuids_isolated",
                        return_value={
                            "removed": [{"uuid": "generated",
                                         "kind": "clearance"}]}):
                report, _result = synth._sanitize_imported_route_transactionally(
                    candidate, baseline, {"generated"})
            with open(candidate, "rb") as source:
                restored = source.read()

        self.assertFalse(report["accepted"])
        self.assertIn("kelvin_gate_regressed",
                      report["admission"]["reasons"])
        self.assertEqual(restored, b"candidate")

    def test_newly_stranded_net_is_completed_inside_same_transaction(self):
        baseline_metric = metric(drc=0, unconnected=8, nets=["/OPEN"])
        imported_metric = metric(
            drc=1, unconnected=3, nets=["/OPEN"],
            violations=[violation("clearance", "generated")])
        stranded_metric = metric(
            drc=0, unconnected=5, nets=["/OPEN", "/STRANDED"])
        repaired_metric = metric(drc=0, unconnected=4, nets=["/OPEN"])
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = self._paths(directory)
            with mock.patch.object(
                    synth.cec_score, "score",
                    side_effect=[baseline_metric, imported_metric,
                                 stranded_metric, repaired_metric]), \
                    mock.patch.object(
                        synth, "_remove_structural_dangling_uuids_isolated",
                        return_value={
                            "removed": [{"uuid": "generated",
                                         "kind": "clearance"}]}), \
                    mock.patch.object(
                        synth, "_repair_route_import_open_nets_isolated",
                        return_value={"schema": 1, "generated_count": 2}) \
                    as repair:
                report, result = synth._sanitize_imported_route_transactionally(
                    candidate, baseline, {"generated"})

        self.assertTrue(report["accepted"], report)
        self.assertIs(result, repaired_metric)
        repair.assert_called_once_with(candidate, ["/STRANDED"])
        self.assertEqual(report["repair"]["generated_count"], 2)


if __name__ == "__main__":
    unittest.main()
