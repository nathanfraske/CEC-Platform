"""Native whole-graph teeth for non-acute backwards diagonal route notches."""
import math
from pathlib import Path
import tempfile
import time
import unittest

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_route_quality as quality
import cec_staged_fr as staged


class ReverseDiagonalJogTests(unittest.TestCase):
    def board(self, points, *, layer=0, net_name='/arbitrary_scalar', width=200000):
        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, net_name, 1)
        board.Add(net)
        tracks = []
        for a, b in zip(points, points[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetNet(net); t.SetLayer(layer); t.SetWidth(width)
            t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*b))
            t.SetLocked(True); board.Add(t); tracks.append(t)
        return board, tracks

    def jogs(self, board, **kwargs):
        return [r for r in quality.analyze_board(board, **kwargs)['issues']
                if r['type'] == 'reverse_diagonal_jog']

    def test_all_copper_faces_rotations_reflections_and_renamed_nets(self):
        points = [(0, 0), (300000, 300000), (100000, 500000), (2100000, 2500000)]
        for face in (0, 4, 6, 8, 10, 2):
            for turn in range(4):
                for mirror in (False, True):
                    def transform(p):
                        x, y = p
                        if mirror: x = -x
                        for _ in range(turn): x, y = -y, x
                        return x+20000000, y+20000000
                    with self.subTest(face=face, turn=turn, mirror=mirror):
                        name = f'/independent_{face}_{turn}_{mirror}'
                        b, edges = self.board(list(map(transform, points)), layer=face, net_name=name)
                        before = [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges]
                        report = quality.analyze_board(b, critical_nets={name})
                        self.assertFalse(report['ok']); self.assertFalse(report['craft_ok'])
                        self.assertTrue(report['geometry_ok'])
                        self.assertEqual(report['reverse_diagonal_jog_count'], 1)
                        issue = self.jogs(b)[0]
                        self.assertEqual(set(issue['track_uuids']), {t.m_Uuid.AsString() for t in edges})
                        self.assertFalse(issue['retirement_or_shortcut_authorized'])
                        self.assertEqual(before, [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges])

    def test_scope_does_not_discard_retained_neighbor_graph(self):
        b, edges = self.board([(0, 0), (300000, 300000), (100000, 500000), (2100000, 2500000)])
        for edge in edges:
            self.assertEqual(len(self.jogs(b, track_uuid_scope={edge.m_Uuid.AsString()})), 1)
        self.assertFalse(self.jogs(b, track_uuid_scope={'not-present'}))

    def test_direction_insertion_order_and_source_heading_do_not_hide_jog(self):
        b, edges = self.board([(0, 0), (300000, 300000), (100000, 500000), (2100000, 2500000)])
        for t in edges:
            a, z = pcbnew.VECTOR2I(*t.GetStart()), pcbnew.VECTOR2I(*t.GetEnd())
            t.SetStart(z); t.SetEnd(a)
        self.assertEqual(len(self.jogs(b)), 1)

    def test_subdividing_any_or_all_runs_cannot_hide_same_copper_notch(self):
        alternatives = [
            [(0,0), (300000,300000), (200000,400000), (100000,500000), (2100000,2500000)],
            [(0,0), (100000,100000), (300000,300000), (100000,500000), (1100000,1500000), (2100000,2500000)],
            [(0,0), (100000,100000), (300000,300000), (200000,400000), (100000,500000), (1100000,1500000), (2100000,2500000)],
        ]
        for points in alternatives:
            with self.subTest(points=points):
                b, edges = self.board(points)
                result = self.jogs(b)
                self.assertEqual(len(result), 1)
                self.assertEqual(set(result[0]['track_uuids']), {t.m_Uuid.AsString() for t in edges})
                for edge in edges:
                    self.assertEqual(len(self.jogs(b, track_uuid_scope={edge.m_Uuid.AsString()})), 1)

    def test_existing_quantized_heading_policy_does_not_crash_exact_optimizer(self):
        points = [(0,0), (300000,300001), (100000,500001), (2100000,2500001)]
        legs = [(a,b,200000) for a,b in zip(points,points[1:])]
        self.assertTrue(quality._reverse_diagonal_jog(*points))
        b, _ = self.board(points)
        self.assertEqual(len(self.jogs(b)), 1)
        self.assertEqual(quality.guarded_corner_shortcuts(legs, lambda *args: True), legs)

    def test_single_right_angle_and_forward_phase_offset_are_not_this_pattern(self):
        for points in ([(0,0), (300000,300000), (100000,500000)],
                       [(0,0), (300000,300000), (500000,300000), (1000000,800000)],
                       [(0,0), (300000,300000), (500000,500000), (1000000,1000000)]):
            with self.subTest(points=points): self.assertFalse(self.jogs(self.board(points)[0]))

    def test_branch_does_not_hide_motif_but_foreign_net_or_layer_is_not_joined(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        b, edges = self.board(points)
        branch = edges[0].Duplicate(); branch.m_Uuid.Clone(pcbnew.KIID())
        branch.SetStart(pcbnew.VECTOR2I(*points[1])); branch.SetEnd(pcbnew.VECTOR2I(900000,300000)); b.Add(branch)
        self.assertEqual(len(self.jogs(b)),1)
        self.assertFalse(self.jogs(b)[0]['retirement_or_shortcut_authorized'])
        for mode in ('net','layer'):
            b, edges = self.board(points)
            if mode == 'layer': edges[-1].SetLayer(2)
            else:
                net = pcbnew.NETINFO_ITEM(b, '/other', 2); b.Add(net); edges[-1].SetNet(net)
            self.assertFalse(self.jogs(b))

    def test_actual_pad_containment_not_large_footprint_box_controls_exception(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        b, edges = self.board(points)
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('X_UNKNOWN'); b.Add(fp)
        p = pcbnew.PAD(fp); p.SetNumber('1'); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I(1000000,1000000))
        p.SetLayerSet(p.SMDMask()); p.SetNet(edges[0].GetNet())
        p.SetPosition(pcbnew.VECTOR2I(10000000,10000000)); fp.Add(p)
        self.assertEqual(len(self.jogs(b)), 1)
        p.SetPosition(pcbnew.VECTOR2I(*points[1]))
        self.assertFalse(self.jogs(b))

    def land(self, board, track, at, size, *, drilled=False):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('RENAMED_NATIVE_LAND'); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('renamed')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if drilled else pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I(*size))
        layers = pcbnew.LSET(); layers.AddLayer(track.GetLayer())
        pad.SetLayerSet(layers); pad.SetNet(track.GetNet())
        pad.SetPosition(pcbnew.VECTOR2I(*at))
        if drilled: pad.SetDrillSize(pcbnew.VECTOR2I(500000, 500000))
        fp.Add(pad)
        return pad

    def test_one_contained_bend_never_hides_exposed_notch_on_any_face(self):
        source = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        for face in (0,4,6,8,10,2):
            for turn in range(4):
                for mirror in (False,True):
                    def transform(p):
                        x,y = p
                        if mirror: x = -x
                        for _ in range(turn): x,y = -y,x
                        return x+20000000,y-30000000
                    with self.subTest(face=face,turn=turn,mirror=mirror):
                        points = list(map(transform,source))
                        board, tracks = self.board(points,layer=face,net_name='/renamed_exterior_notch')
                        self.land(board,tracks[0],points[1],(100000,100000))
                        report = quality.analyze_board(board)
                        self.assertEqual(report['reverse_diagonal_jog_count'],1)
                        self.assertFalse(report['craft_ok'])

    def test_full_fixed_width_middle_and_both_incident_caps_required(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        for widths in ((200000,200002,200000), (200002,200000,200000),
                       (200000,200000,200002), (200000,800000,200000)):
            with self.subTest(widths=widths):
                board, tracks = self.board(points)
                for track,width in zip(tracks,widths): track.SetWidth(width)
                # For 200um strokes the middle and endpoint disks touch this
                # exact native rectangle. Two extra nm of width expose 1nm.
                self.land(board,tracks[0],(200000,400000),(400000,400000))
                self.assertEqual(len(self.jogs(board)),1)

    def test_native_whole_notch_containment_survives_mixed_width_and_transforms(self):
        source = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        for face in (0,4,6,8,10,2):
            for turn in range(4):
                for mirror in (False,True):
                    def transform(p):
                        x,y = p
                        if mirror: x = -x
                        for _ in range(turn): x,y = -y,x
                        return x-40000000,y+70000000
                    with self.subTest(face=face,turn=turn,mirror=mirror):
                        points = list(map(transform,source))
                        board, tracks = self.board(points,layer=face,net_name='/renamed_absorbed_notch')
                        for track,width in zip(tracks,(100000,300000,500000)): track.SetWidth(width)
                        self.land(board,tracks[0],transform((200000,400000)),(1600000,1600000))
                        before = [(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),t.IsLocked()) for t in tracks]
                        self.assertFalse(self.jogs(board))
                        self.assertEqual(before,[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),t.IsLocked()) for t in tracks])

    def test_drilled_nominal_land_is_not_full_notch_absorption_evidence(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        board, tracks = self.board(points)
        self.land(board,tracks[0],(200000,400000),(1600000,1600000),drilled=True)
        self.assertEqual(len(self.jogs(board)),1)

    def test_closed_native_boundary_and_odd_width_have_no_rounding_waiver(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        for width,expected in ((200000,0),(200001,1)):
            with self.subTest(width=width):
                board, tracks = self.board(points,width=width)
                self.land(board,tracks[0],(200000,400000),(400000,400000))
                self.assertEqual(len(self.jogs(board)),expected)

    def test_round_land_bbox_and_centerline_are_not_capsule_containment(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        for size,expected in ((400000,1),(1600000,0)):
            with self.subTest(size=size):
                board, tracks = self.board(points)
                pad = self.land(board,tracks[0],(200000,400000),(size,size))
                pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                self.assertEqual(len(self.jogs(board)),expected)

    def test_subdivided_middle_uses_each_actual_width(self):
        points = [(0,0),(300000,300000),(200000,400000),(100000,500000),(2100000,2500000)]
        board, tracks = self.board(points)
        tracks[2].SetWidth(600000)
        self.land(board,tracks[0],(200000,400000),(400000,400000))
        self.assertEqual(len(self.jogs(board)),1)

    def test_saved_literal_and_stage_scope_catch_notch_without_touching_old_copper(self):
        b, edges = self.board([(0,0), (300000,300000), (100000,500000), (2100000,2500000)])
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'board.kicad_pcb'); pcbnew.SaveBoard(path,b)
            keep = {edges[0].m_Uuid.AsString(), edges[1].m_Uuid.AsString()}
            report = staged._route_quality_stage_worker(path, ['/arbitrary_scalar'], keep)
            self.assertEqual(report['refused_nets'], ['/arbitrary_scalar'])
            self.assertEqual(report['removed_generated_items'], 1)
            self.assertEqual({t.m_Uuid.AsString() for t in pcbnew.LoadBoard(path).GetTracks()}, keep)

    def test_complete_new_proposal_refused_with_retained_neighbors_without_mutation(self):
        b, edges = self.board([(0,0), (300000,300000), (100000,500000)])
        before = {t.m_Uuid.AsString() for t in b.GetTracks()}
        result = quality.assess_proposed_route(b, [dict(net='/arbitrary_scalar', layer=0,
            width_nm=200000, start_nm=[100000,500000], end_nm=[2100000,2500000])],
            deadline=time.monotonic()+5)
        self.assertTrue(result['complete']); self.assertFalse(result['ok'])
        self.assertTrue(any(r['type']=='reverse_diagonal_jog' for r in result['issues']))
        self.assertEqual(before, {t.m_Uuid.AsString() for t in b.GetTracks()})

    def test_unsaved_guarded_compaction_shortens_exact_width_and_keeps_outer_endpoints(self):
        points = [(0,0), (300000,300000), (100000,500000), (2100000,2500000)]
        legs = [(a,b,200000) for a,b in zip(points,points[1:])]
        calls=[]
        made = quality.guarded_corner_shortcuts(legs, lambda a,b,w: calls.append((a,b,w)) or True)
        self.assertEqual(made[0][0], points[0]); self.assertEqual(made[-1][1], points[-1])
        self.assertTrue(all(w==200000 and quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b,w in made))
        self.assertLess(sum(math.dist(a,b) for a,b,w in made), sum(math.dist(a,b) for a,b,w in legs))
        self.assertLess(len(made), len(legs)); self.assertTrue(calls)
        self.assertEqual(quality.guarded_corner_shortcuts(legs, lambda *args: False), legs)
        changed_width = [legs[0], (*legs[1][:2],300000), legs[2]]
        self.assertEqual(quality.guarded_corner_shortcuts(changed_width, lambda *args: True), changed_width)
        self.assertEqual(quality.guarded_corner_shortcuts(legs, lambda *args: True,
            deadline_monotonic=time.monotonic()-1), legs)


if __name__ == '__main__': unittest.main()
