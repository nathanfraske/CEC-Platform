import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

EPS = os.path.join(
    ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")

try:
    import pcbnew
    import cec_constraints
    import cec_pour_clearance
    import cec_synth_pipeline
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False


def _copy_sidecars(source, destination):
    shutil.copy2(source, destination)
    for extension in (".kicad_pro", ".kicad_dru"):
        sibling = source[:-len(".kicad_pcb")] + extension
        if os.path.isfile(sibling):
            shutil.copy2(
                sibling, destination[:-len(".kicad_pcb")] + extension)


def _foreign_track_board(source, destination, *, locked=True):
    _copy_sidecars(source, destination)
    board = pcbnew.LoadBoard(destination)
    boxes, _allowed = cec_constraints._derive_pour_boxes(
        board, destination)
    _pour, layer, x0, x1, y0, y1 = boxes[0]
    foreign = next(
        net for net in board.GetNetInfo().NetsByNetcode().values()
        if net.GetNetname() == "GND")
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(
        int((x0 - 1.0) * 1e6), int(((y0 + y1) / 2.0) * 1e6)))
    track.SetEnd(pcbnew.VECTOR2I(
        int((x1 + 1.0) * 1e6), int(((y0 + y1) / 2.0) * 1e6)))
    track.SetWidth(int(0.25 * 1e6))
    track.SetLayer(layer)
    track.SetNet(foreign)
    track.SetLocked(bool(locked))
    board.Add(track)
    uuid = track.m_Uuid.AsString()
    pcbnew.SaveBoard(destination, board)
    return uuid


@unittest.skipUnless(HAVE, "pcbnew required")
class ExactCopperGeometryTests(unittest.TestCase):
    def test_concave_pour_reservation_preserves_empty_hook_pocket(self):
        rows = cec_constraints._exact_pour_rectangles([{
            "net": "/PWR", "layer": "F.Cu", "name": "hook",
            "polygon": [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0),
                        (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)],
        }])
        area = sum((row["x1"] - row["x0"])
                   * (row["y1"] - row["y0"]) for row in rows)

        self.assertAlmostEqual(area, 7.0)
        self.assertFalse(any(
            row["x0"] <= 3.0 <= row["x1"]
            and row["y0"] <= 3.0 <= row["y1"]
            for row in rows), rows)

    def test_clean_evacuation_is_noop_without_pcbnew_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            destination = os.path.join(directory, "destination.kicad_pcb")
            with open(source, "w", encoding="utf-8") as sink:
                sink.write("already clean")
            clean = {
                "applicable": True, "status": "ok",
                "n_tracks": 0, "n_vias": 0, "by_pour": {},
            }
            with mock.patch.object(
                    cec_pour_clearance, "inspect_file",
                    return_value=clean), mock.patch.object(
                        cec_pour_clearance.subprocess, "run") as run:
                report = cec_pour_clearance.evacuate_file(
                    source, destination, protected_nets=("/PWR",))

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["reason"], "already_clear")
            self.assertTrue(report["post_clean"])
            self.assertFalse(report["rolled_back"])
            run.assert_not_called()
            with open(destination, encoding="utf-8") as copied:
                self.assertEqual(copied.read(), "already clean")

    def test_full_track_width_catches_grazing_copper(self):
        box = (0.0, 10.0, 0.0, 10.0)
        centreline = ((-1.0, -0.10), (11.0, -0.10))
        self.assertTrue(cec_constraints._track_capsule_hits_box(
            *centreline, 0.15, box))
        self.assertFalse(cec_constraints._track_capsule_hits_box(
            *centreline, 0.05, box))

    def test_via_annulus_not_only_centre_is_measured(self):
        box = (0.0, 10.0, 0.0, 10.0)
        self.assertTrue(cec_constraints._circle_hits_box(
            -0.10, 5.0, 0.15, box))
        self.assertFalse(cec_constraints._circle_hits_box(
            -0.10, 5.0, 0.05, box))

    def test_actual_laid_zone_conviction_is_not_lost_when_corridor_is_clear(self):
        with mock.patch.object(
                cec_constraints, "foreign_on_pour_summary",
                return_value={
                    "applicable": True, "status": "ok", "n_tracks": 0,
                    "n_vias": 0, "tracks": [], "vias": [],
                    "by_pour": {},
                }), mock.patch.object(
                    cec_constraints, "laid_pour_incursion_summary",
                    return_value={
                        "applicable": True, "status": "ok", "n_parts": 0,
                        "n_tracks": 1, "n_vias": 0,
                        "items": [{
                            "kind": "track", "uuid": "laid-only-track",
                            "net": "/USB_D_P", "layer": "F.Cu",
                            "pour": "actual-zone:/SENSEC1_HI",
                        }],
                    }):
            summary = cec_pour_clearance._combined_summary("fixture.kicad_pcb")

        self.assertEqual((summary["n_tracks"], summary["n_vias"]), (1, 0))
        self.assertEqual(summary["tracks"][0]["uuid"], "laid-only-track")
        self.assertEqual(summary["tracks"][0]["sources"], ["laid"])


@unittest.skipUnless(HAVE and os.path.isfile(EPS),
                     "pcbnew + EPS board required")
class PourClearanceEvacuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp)
        self.source = os.path.join(self.temp, "source.kicad_pcb")
        self.destination = os.path.join(self.temp, "clean.kicad_pcb")
        self.uuid = _foreign_track_board(EPS, self.source, locked=True)

    def test_public_regions_preserve_checker_authority(self):
        regions = cec_constraints.high_current_pour_regions(EPS)
        board = pcbnew.LoadBoard(EPS)
        boxes, _allowed = cec_constraints._derive_pour_boxes(board, EPS)
        self.assertEqual(len(regions), len(boxes))
        self.assertEqual(
            {(row["net"], row["layer"], row["x0"], row["x1"],
              row["y0"], row["y1"]) for row in regions},
            {(net, board.GetLayerName(layer), x0, x1, y0, y1)
             for net, layer, x0, x1, y0, y1 in boxes})

    def test_region_geometry_is_independent_of_launch_environment(self):
        saved = os.environ.get("CEC_SHUNT_GAP")
        try:
            os.environ["CEC_SHUNT_GAP"] = "0"
            off = cec_constraints.high_current_pour_regions(EPS)
            os.environ["CEC_SHUNT_GAP"] = "1"
            on = cec_constraints.high_current_pour_regions(EPS)
        finally:
            if saved is None:
                os.environ.pop("CEC_SHUNT_GAP", None)
            else:
                os.environ["CEC_SHUNT_GAP"] = saved
        self.assertEqual(off, on)

    def test_isolated_inspection_matches_direct_canonical_check(self):
        isolated = cec_pour_clearance.inspect_file(self.source)
        direct = cec_constraints.foreign_on_pour_summary(self.source)
        self.assertEqual(
            (isolated["status"], isolated["n_tracks"],
             isolated["n_vias"], isolated["by_pour"]),
            (direct["status"], direct["n_tracks"],
             direct["n_vias"], direct["by_pour"]))

    def test_exact_locked_primitive_is_evacuated_without_mutating_source(self):
        before = cec_constraints.foreign_on_pour_summary(self.source)
        self.assertGreaterEqual(before["n_tracks"], 1)

        report = cec_pour_clearance.evacuate_file(
            self.source, self.destination)

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["post_clean"], report)
        self.assertIn(self.uuid, {
            row["uuid"] for row in report["removed_items"]})
        self.assertEqual(report["removed_locked_count"], 1)
        self.assertIn("GND", report["removed_nets"])
        self.assertEqual(
            cec_constraints.foreign_on_pour_summary(
                self.destination)["n_tracks"], 0)
        self.assertGreaterEqual(
            cec_constraints.foreign_on_pour_summary(
                self.source)["n_tracks"], 1)

    def test_explicit_protected_net_refuses_and_rolls_back(self):
        report = cec_pour_clearance.evacuate_file(
            self.source, self.destination, protected_nets=("GND",))

        self.assertFalse(report["ok"])
        self.assertTrue(report["rolled_back"])
        self.assertEqual(report["reason"],
                         "protected_net_intrudes_high_current_pour")
        self.assertGreaterEqual(
            cec_constraints.foreign_on_pour_summary(
                self.destination)["n_tracks"], 1)

    def test_failure_publication_rechecks_and_sanitizes_artifact(self):
        published, report = cec_synth_pipeline._sanitize_failure_artifact(
            self.source, self.temp, "early route refusal")

        self.assertTrue(report["ok"], report)
        self.assertNotEqual(os.path.abspath(self.source), published)
        self.assertEqual(report["published_artifact"], published)
        summary = cec_constraints.foreign_on_pour_summary(published)
        self.assertEqual((summary["n_tracks"], summary["n_vias"]), (0, 0))
        self.assertGreaterEqual(
            cec_constraints.foreign_on_pour_summary(
                self.source)["n_tracks"], 1)


if __name__ == "__main__":
    unittest.main()
