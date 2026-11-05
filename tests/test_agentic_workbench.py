"""Model construction never substitutes for independent physical admission."""

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cec_agentic_design as design
import cec_agentic_workbench as workbench


class AlgebraTests(unittest.TestCase):
    def test_doglegs_are_exact_canonical_and_bounded_under_all_symmetries(self):
        for rotation in range(4):
            for mirror in (False, True):

                def transform(p):
                    x, y = p
                    if mirror:
                        x = -x
                    for _ in range(rotation):
                        x, y = -y, x
                    return [x + 1234567, y - 2345678]

                a, b = transform([0, 0]), transform([8000000, 3000000])
                variants = design.direct_paths(a, b, minimum_phase_nm=200000)
                self.assertEqual(len(variants), 2)
                for points in variants:
                    self.assertEqual(points[0], a)
                    self.assertEqual(points[-1], b)
                    self.assertEqual(
                        design.path(points, minimum_phase_nm=200000), points
                    )

    def test_path_refuses_noncanonical_hard_90_retrace_and_invalid_units(self):
        invalid = [
            [[0, 0], [3, 2]],
            [[0, 0], [4, 0], [4, 4]],
            [[0, 0], [4, 0], [0, 0]],
            [[0, 0], [True, 0]],
            [[0, 0], [1.5, 0]],
            [[0, 0], [2000000001, 0]],
        ]
        for points in invalid:
            with self.subTest(points=points), self.assertRaises(ValueError):
                design.path(points)

    def test_no_hidden_float_or_subwidth_phase_waiver(self):
        self.assertEqual(
            design.direct_paths([0, 0], [1000000, 1], minimum_phase_nm=200000), []
        )
        with self.assertRaises(ValueError):
            design.path([[0, 0], [10, 10]], minimum_phase_nm=True)

    def test_alignment_is_explicit_deterministic_and_preserves_owner_inputs(self):
        fps = [
            dict(ref="C_ANY1", uuid="1", side="F", rotation_deg=0),
            dict(ref="C_ANY2", uuid="2", side="F", rotation_deg=90),
        ]
        before = copy.deepcopy(fps)
        row = design.alignment(
            fps,
            references=["C_ANY2", "C_ANY1"],
            axis="y",
            origin_nm=[1234567, 2345678],
            pitch_nm=1250000,
        )
        self.assertEqual(row[0]["at_nm"], [1234567, 2345678])
        self.assertEqual(row[1]["at_nm"], [1234567, 3595678])
        self.assertEqual(row[0]["rotation_deg"], 90)
        self.assertEqual(fps, before)

    def test_alignment_cannot_silently_mix_sides_or_references(self):
        fps = [
            dict(ref="A", uuid="1", side="F", rotation_deg=0),
            dict(ref="B", uuid="2", side="B", rotation_deg=0),
        ]
        with self.assertRaises(ValueError):
            design.alignment(
                fps, references=["A", "B"], axis="x", origin_nm=[0, 0], pitch_nm=1000000
            )
        for refs in (["A", "missing"], ["A", "A"]):
            with self.assertRaises(ValueError):
                design.alignment(
                    fps, references=refs, axis="x", origin_nm=[0, 0], pitch_nm=1000000
                )

    def test_polygon_only_accepts_bounded_cardinal_or_45_geometry(self):
        rect = [[0, 0], [10000000, 0], [10000000, 5000000], [0, 5000000]]
        self.assertEqual(design.polygon(rect), rect)
        with self.assertRaises(ValueError):
            design.polygon([[0, 0], [10, 3], [10, 10], [0, 10]])
        with self.assertRaises(ValueError):
            design.polygon(
                [[0, 0], [6, 0], [6, 6], [2, 2], [2, 6], [0, 6], [4, 2], [0, 2]]
            )

    def test_unknown_power_or_pair_cannot_become_ordinary_from_a_hint(self):
        world = dict(
            ordinary_nets=["arbitrary-control"],
            tracks=[],
            vias=[],
            footprints=[],
            zones=[],
            sha256="a" * 64,
        )
        for net in ("GND", "+5V", "USB_D_P", "arbitrary-control"):
            points = [
                [0, 0],
                [2000000, 0],
                [4000000, 2000000],
                [6000000, 0],
                [10000000, 0],
            ]
            for i, (a, b) in enumerate(zip(points, points[1:])):
                world["tracks"].append(
                    dict(
                        kind="PCB_TRACK",
                        uuid=net + str(i),
                        net=net,
                        layer=0,
                        width_nm=200000,
                        a=a,
                        b=b,
                        grouped=False,
                        locked=True,
                    )
                )
        rows = design.chains(world)
        self.assertTrue(rows)
        self.assertEqual({r["net"] for r in rows}, {"arbitrary-control"})
        self.assertEqual(world["tracks"][0]["a"], [0, 0])


class ProtocolTests(unittest.TestCase):
    class FakeWorkbench:
        def boards(self):
            return dict(ok=True, boards=[], release_authority=False)

        def stage(self, **kw):
            return dict(
                ok=False, error="unknown independent proof", release_authority=False
            )

    def exchange(self, messages):
        inp = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        out = io.StringIO()
        workbench.serve(self.FakeWorkbench(), inp, out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_mcp_handshake_discovery_and_direct_tool_have_identical_results(self):
        msgs = [
            dict(
                jsonrpc="2.0",
                id=1,
                method="initialize",
                params={"protocolVersion": "2025-06-18"},
            ),
            dict(jsonrpc="2.0", method="notifications/initialized"),
            dict(jsonrpc="2.0", id=2, method="tools/list"),
            dict(
                jsonrpc="2.0",
                id=3,
                method="tools/call",
                params={"name": "boards", "arguments": {}},
            ),
        ]
        replies = self.exchange(msgs)
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("independent", replies[0]["result"]["instructions"])
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertEqual(names, set(workbench.TOOL_PARAMETERS))
        self.assertNotIn("shell", names)
        self.assertEqual(
            replies[2]["result"]["structuredContent"],
            workbench.dispatch(self.FakeWorkbench(), "boards", {}),
        )

    def test_uninitialized_or_unknown_methods_do_not_run_tools(self):
        replies = self.exchange(
            [
                dict(jsonrpc="2.0", id=1, method="tools/list"),
                dict(jsonrpc="2.0", id=2, method="arbitrary/exec"),
            ]
        )
        self.assertTrue(all("error" in r for r in replies))

    def test_unexpected_parameters_cannot_grant_source_or_command_authority(self):
        with self.assertRaises(ValueError):
            workbench.dispatch(self.FakeWorkbench(), "boards", {"shell": "bad"})
        with self.assertRaises(ValueError):
            workbench.dispatch(self.FakeWorkbench(), "stage", {"board": "anything"})

    def test_compact_tool_evidence_preserves_nested_refusal_not_large_success_payload(
        self,
    ):
        record = dict(
            complete=True,
            candidate_sha256="a" * 64,
            result=dict(
                ok=False,
                complete=False,
                errors=["ordinary replay refused"],
                nested=dict(ok=False, complete=False, errors=["deadline"]),
                interactions=[dict(blocking=False, large="x" * 100000)],
            ),
        )
        compact = workbench.evidence_summary(record)
        self.assertFalse(compact["result"]["ok"])
        self.assertLess(len(json.dumps(compact)), 2000)
        self.assertIn("deadline", compact["result"]["failure_stack"][1]["errors"])

    def test_running_evidence_cannot_be_reported_as_complete(self):
        compact = workbench.evidence_summary(
            dict(complete=False, status="running", message="pending")
        )
        self.assertFalse(compact["complete"])
        self.assertEqual(compact["status"], "running")

    def test_unknown_missing_or_incomplete_gate_never_reports_a_pass(self):
        for row in (
            {},
            dict(complete=True),
            dict(complete=True, result=dict(ok=None, complete=False)),
            dict(complete=True, result=dict(ok=True, complete=False)),
            dict(complete=False, result=dict(ok=True, complete=True)),
        ):
            self.assertFalse(workbench.check_passed(row))
        self.assertTrue(
            workbench.check_passed(
                dict(complete=True, result=dict(ok=True, complete=True))
            )
        )

    def test_source_and_code_epoch_are_mandatory_before_cached_tool_reads(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source = p / "source.kicad_pcb"
            source.write_text("unchanged")
            table = p / "fp-lib-table"
            table.write_text("unchanged table")
            token = "a" * 24
            jobdir = p / token
            jobdir.mkdir()
            record = dict(
                source=str(source),
                source_sha256=workbench.inspection.sha(source),
                source_family=workbench.family(source),
                code_identity=workbench.code_identity(),
                footprint_table=str(table),
                footprint_table_sha256=workbench.inspection.sha(table),
            )
            workbench.inspection.write_json(jobdir / "job.json", record)
            w = object.__new__(workbench.Workbench)
            w.workspace = p
            self.assertEqual(w._job(token)[1], record)
            table.write_text("changed table")
            with self.assertRaisesRegex(ValueError, "library_table"):
                w._job(token)
            table.write_text("unchanged table")
            source.write_text("changed source")
            with self.assertRaisesRegex(ValueError, "source_family"):
                w._job(token)

    def test_job_tokens_cannot_traverse(self):
        w = object.__new__(workbench.Workbench)
        for token in ("../source", "x" * 24, "A" * 24, True, None):
            with self.assertRaises(ValueError):
                w._job(token)


class NativeConstructionTests(unittest.TestCase):
    def test_explicit_native_geometry_shortens_a_rotated_synthetic_corridor(self):
        from test_source_guided_ordinary_detour import fixture
        import pcbnew
        import cec_ordinary_route_receiving as ordinary

        for face in (pcbnew.F_Cu, pcbnew.B_Cu):
            with tempfile.TemporaryDirectory() as d:
                source, _hint, _gid, ids, _net = fixture(Path(d), face=face)
                candidate = Path(d) / "candidate" / "board.kicad_pcb"
                candidate.parent.mkdir()
                encoded = source.read_bytes()
                request = dict(
                    operations=[
                        dict(
                            kind="replace_chain",
                            track_uuids=ids,
                            allow_locked_track_uuids=ids,
                            points_nm=[
                                [9000000, 16000000],
                                [11000000, 16000000],
                                [12000000, 17000000],
                                [20000000, 17000000],
                                [21000000, 16000000],
                                [23000000, 16000000],
                            ],
                        )
                    ]
                )
                made = workbench._construct(source, candidate, request, "synthetic")
                self.assertTrue(
                    made["visible_material_delta"]["exposed_copper_changed"]
                )
                self.assertGreater(made["changes"][0]["saved_centerline_mm"], 1.0)
                self.assertEqual(source.read_bytes(), encoded)
                proof = ordinary.receive(
                    source,
                    candidate,
                    retired_track_uuids=ids,
                    allow_locked_track_uuids=ids,
                    board_hint="synthetic",
                    timeout_s=5.0,
                )
                self.assertTrue(proof["ok"], proof)

    def test_no_exposed_copper_claim_for_a_chamfer_hidden_under_a_real_pad(self):
        import pcbnew
        import cec_field_coupling as field
        from test_lastmile import _board
        from test_field_proposals import track

        with tempfile.TemporaryDirectory() as d:
            b = _board([(6, 11, "CONTROL")], edge=(0, 0, 15, 15))
            pad = next(iter(next(iter(b.GetFootprints())).Pads()))
            pad.SetSize(pcbnew.VECTOR2I_MM(4, 4))
            old = []
            for a, z in zip([(4, 10), (6, 10), (6, 12)], [(6, 10), (6, 12), (8, 12)]):
                old.append(track(b, "CONTROL", a, z, width=0.2))
            source = Path(d) / "source.kicad_pcb"
            field._save_field_snapshot(b, source)
            old_ids = [str(t.m_Uuid.AsString()) for t in old]
            from cec_native_items import discard_items

            discard_items(b, old)
            new = []
            points = [(4, 10), (5.75, 10), (6, 10.25), (6, 11.75), (6.25, 12), (8, 12)]
            for a, z in zip(points, points[1:]):
                new.append(track(b, "CONTROL", a, z, width=0.2))
            child = Path(d) / "child.kicad_pcb"
            field._save_field_snapshot(b, child)
            result = workbench.visible_delta(
                source, child, old_ids, [str(t.m_Uuid.AsString()) for t in new]
            )
            self.assertFalse(result["exposed_copper_changed"], result)


class ReviewPublicationTests(unittest.TestCase):
    def test_each_selected_board_retains_its_own_native_plot_identity(self):
        # Synthetic orchestration only, never a CAD/manufacturing qualification.
        import cec_publish_agentic_review as publisher

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = []
            jobs = {}
            counts = dict(opens=0, errors=0, warnings=0, exclusions=0)
            for name in ("alpha", "beta"):
                folder = root / name
                folder.mkdir()
                source = folder / "parent.kicad_pcb"
                source.write_text(name + " parent")
                child = folder / "child.kicad_pcb"
                child.write_text(name + " child")
                native = folder / "native.json"
                native.write_text(
                    json.dumps(
                        dict(
                            violations=[], unconnected_items=[], excluded_violations=[]
                        )
                    )
                )
                row = dict(
                    board=name,
                    path=str(source),
                    sha256=workbench.inspection.sha(source),
                    result=str(native),
                    result_sha256=workbench.inspection.sha(native),
                    counts=counts,
                    complete=True,
                )
                rows.append(row)
                path = folder / "job.json"
                path.write_text("{}")
                candidate_sha = workbench.inspection.sha(child)
                data = dict(
                    board=name,
                    token=name,
                    source_sha256=row["sha256"],
                    request={"intent": name + " explicit design"},
                )
                verdict = dict(
                    ok=True,
                    candidate=str(child),
                    candidate_sha256=candidate_sha,
                    native_counts=counts,
                    saved_centerline_mm=0.25,
                )
                workbench.inspection.write_json(
                    folder / "selected.json",
                    dict(
                        selected=True,
                        candidate_sha256=candidate_sha,
                        model_visual_review=name + " synthetic native review",
                    ),
                )
                hashes = {}
                for side in ("before", "after"):
                    plot = folder / (side + "-F-Cu.svg")
                    plot.write_text("<svg>" + name + " " + side + "</svg>")
                    hashes[plot.name] = workbench.inspection.sha(plot)
                workbench.inspection.write_json(
                    folder / "render-proof.json",
                    dict(
                        source_sha256=row["sha256"],
                        candidate_sha256=candidate_sha,
                        code_identity=workbench.code_identity(),
                        plot_hashes=hashes,
                    ),
                )
                workbench.inspection.write_json(
                    folder / "native_candidate.json",
                    dict(
                        result=dict(
                            report=str(native), report_sha256=row["result_sha256"]
                        )
                    ),
                )
                jobs[name] = (path, data, verdict)
            receipt = root / "parent.json"
            workbench.inspection.write_json(receipt, dict(complete=True, boards=rows))
            fake = type("FakeWorkbench", (), {})()
            fake.receipt = dict(boards=rows)
            fake.manifest = dict(
                source_receipt=str(receipt),
                source_receipt_sha256=workbench.inspection.sha(receipt),
            )
            fake._job = lambda token: jobs[token][:2]
            fake.verdict = lambda token: jobs[token][2]
            with patch.object(publisher.workbench, "Workbench", return_value=fake):
                result = publisher.publish(root, ["alpha", "beta"], root / "published")
            for child in result["selected_children"]:
                assert (
                    child["model_visual_review"]
                    == child["board"] + " synthetic native review"
                )
                assert (
                    child["work_order"]["intent"] == child["board"] + " explicit design"
                )
                for plot in child["reviewed_native_plots"].values():
                    self.assertEqual(
                        workbench.inspection.sha(plot["path"]), plot["sha256"]
                    )
                    self.assertIn(child["board"], Path(plot["path"]).parent.name)
            published = json.loads(Path(result["receipt"]).read_text())
            for row in published["boards"]:
                assert Path(row["producer"]).parent == Path(row["result"]).parent
                assert (
                    "producer_source_path" not in row
                    and "measured_source_path" not in row
                )


if __name__ == "__main__":
    unittest.main()
