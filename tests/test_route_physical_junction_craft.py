"""A branch, nominal pad, or footprint box cannot hide exposed route craft."""
import time
import unittest

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_route_quality as quality


class PhysicalJunctionCraftTests(unittest.TestCase):
    def board(self, points, face=0):
        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, '/arbitrary_renamed_control', 1)
        board.Add(net)
        tracks = [self.track(board, net, a, b, face) for a, b in zip(points, points[1:])]
        return board, net, tracks

    def track(self, board, net, a, b, face=0, width=200000):
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(net); track.SetLayer(face); track.SetWidth(width)
        track.SetStart(pcbnew.VECTOR2I(*a)); track.SetEnd(pcbnew.VECTOR2I(*b))
        track.SetLocked(True); board.Add(track)
        return track

    def pad(self, board, net, at, size, face=0, footprint=None):
        if footprint is None:
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference('RENAMED'); board.Add(footprint)
        pad = pcbnew.PAD(footprint); pad.SetNumber(str(len(list(footprint.Pads()))+1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(*size)); pad.SetPosition(pcbnew.VECTOR2I(*at))
        layers = pcbnew.LSET(); layers.AddLayer(face); pad.SetLayerSet(layers)
        pad.SetNet(net); footprint.Add(pad)
        return pad, footprint

    def transforms(self, points):
        for face in (0,4,6,8,10,2):
            for turn in range(4):
                for mirror in (False, True):
                    def transform(p):
                        x,y = p
                        if mirror: x=-x
                        for _ in range(turn): x,y=-y,x
                        return x+20000000,y+20000000
                    yield face, turn, mirror, transform, list(map(transform,points))

    def test_image_pattern_not_hidden_by_branch_tiny_pad_or_footprint_box(self):
        source = [(0,0),(1000000,0),(800000,200000),(2000000,1400000)]
        for face,turn,mirror,transform,points in self.transforms(source):
            for mode in ('branch','tiny_pad','footprint_box'):
                with self.subTest(face=face,turn=turn,mirror=mirror,mode=mode):
                    board,net,tracks = self.board(points,face)
                    if mode == 'branch':
                        self.track(board,net,points[1],transform((1000000,-1000000)),face)
                    elif mode == 'tiny_pad':
                        self.pad(board,net,points[1],(10000,10000),face)
                    else:
                        _,fp = self.pad(board,net,transform((0,-1000000)),(10000,10000),face)
                        self.pad(board,net,transform((2000000,1000000)),(10000,10000),face,fp)
                    before=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
                            for t in board.GetTracks()]
                    report=quality.analyze_board(board,critical_nets={net.GetNetname()},
                        track_uuid_scope={tracks[1].m_Uuid.AsString()})
                    self.assertFalse(report['craft_ok'])
                    self.assertFalse(report['ok'])
                    self.assertTrue(any(row['type'] in ('acute_backtrack','acute_branch_junction')
                                        for row in report['issues']))
                    self.assertEqual(before,[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
                                              for t in board.GetTracks()])

    def test_diagonal_notch_cannot_be_hidden_by_retained_branch_at_either_bend(self):
        source=[(0,0),(300000,300000),(100000,500000),(2100000,2500000)]
        for face,turn,mirror,transform,points in self.transforms(source):
            for bend in (1,2):
                with self.subTest(face=face,turn=turn,mirror=mirror,bend=bend):
                    board,net,tracks=self.board(points,face)
                    target=(1300000,300000) if bend==1 else (-900000,500000)
                    self.track(board,net,points[bend],transform(target),face)
                    report=quality.analyze_board(board,critical_nets={net.GetNetname()},
                        track_uuid_scope={tracks[1].m_Uuid.AsString()})
                    self.assertEqual(report['reverse_diagonal_jog_count'],1)
                    self.assertFalse(report['craft_ok'])

    def test_full_native_pad_disk_not_center_membership_absorbs_acute_launch(self):
        points=[(0,0),(1000000,0),(800000,200000)]
        for width,expected in ((200000,True),(200001,False)):
            with self.subTest(width=width):
                board,net,tracks=self.board(points)
                for track in tracks:track.SetWidth(width)
                self.pad(board,net,points[1],(200000,200000))
                report=quality.analyze_board(board)
                self.assertEqual(report['craft_ok'],expected)

    def test_a_contained_first_bend_does_not_absorb_exposed_middle_capsule(self):
        points=[(0,0),(1000000,0),(800000,200000),(2000000,1400000)]
        for size,at,expected in ((201000,points[1],False),
                                 (1000000,(900000,100000),True)):
            with self.subTest(size=size):
                board,net,_=self.board(points)
                self.pad(board,net,at,(size,size))
                report=quality.analyze_board(board)
                self.assertEqual(report['craft_ok'],expected)

    def test_clean_tee_and_forty_five_fork_are_not_backtracks(self):
        for points,branch in (([(0,0),(1000000,0),(2000000,0)],(1000000,1000000)),
                              ([(0,0),(1000000,0),(2000000,1000000)],(2000000,-1000000))):
            board,net,_=self.board(points)
            self.track(board,net,points[1],branch)
            self.assertTrue(quality.analyze_board(board)['craft_ok'])

    def test_positive_native_cap_contact_cannot_hide_beyond_endpoint_alias_radius(self):
        source=[(0,0),(1000000,0),(800000,200000),(2000000,1400000)]
        for face,turn,mirror,transform,points in self.transforms(source):
            with self.subTest(face=face,turn=turn,mirror=mirror):
                board,net,tracks=self.board(points,face)
                tracks[1].SetStart(pcbnew.VECTOR2I(*transform((950000,50000))))
                self.assertTrue(tracks[0].GetEffectiveShape(face).Collide(tracks[1].GetEffectiveShape(face),0))
                report=quality.analyze_board(board,critical_nets={net.GetNetname()},
                    track_uuid_scope={tracks[1].m_Uuid.AsString()})
                self.assertFalse(report['craft_ok'])
                contacts=[row for row in report['issues'] if row['type']=='offset_acute_contact']
                self.assertEqual(len(contacts),1)
                self.assertTrue(contacts[0]['native_copper_contact_checked'])
                self.assertFalse(contacts[0]['endpoint_alias_invented'])
                self.assertFalse(contacts[0]['retirement_or_shortcut_authorized'])

    def test_noncontacting_other_layer_or_other_net_caps_are_not_a_native_join(self):
        for mode in ('gap','layer','net'):
            with self.subTest(mode=mode):
                board,net,tracks=self.board([(0,0),(1000000,0)])
                other=net
                if mode=='net':other=pcbnew.NETINFO_ITEM(board,'/other',2);board.Add(other)
                start=(700000,300000) if mode=='gap' else (950000,50000)
                self.track(board,other,start,(800000,200000),2 if mode=='layer' else 0)
                self.assertFalse(any(row['type'].startswith('offset_')
                                     for row in quality.analyze_board(board)['issues']))

    def test_remote_connected_loop_cannot_hide_a_local_native_cap_notch(self):
        board,net,tracks=self.board([(20000000,20000000),(21000000,20000000)])
        self.track(board,net,(20950000,20050000),(20800000,20200000))
        self.track(board,net,(20800000,20200000),(22000000,21400000))
        remote=[(20000000,20000000),(19000000,20000000),(19000000,23000000),
                (23000000,23000000),(23000000,21400000),(22000000,21400000)]
        for a,b in zip(remote,remote[1:]):self.track(board,net,a,b)
        report=quality.analyze_board(board)
        self.assertFalse(report['craft_ok'])
        self.assertTrue(any(row['type']=='offset_acute_contact' for row in report['issues']))

    def test_tee_at_a_subdivided_middle_or_outer_run_cannot_hide_the_notch(self):
        for points,anchor,end in (
            ([(0,0),(300000,300000),(200000,400000),(100000,500000),(2100000,2500000)],
             (200000,400000),(1200000,400000)),
            ([(0,0),(100000,100000),(300000,300000),(100000,500000),(2100000,2500000)],
             (100000,100000),(1100000,100000))):
            board,net,_=self.board(points)
            self.track(board,net,anchor,end)
            report=quality.analyze_board(board)
            self.assertGreaterEqual(report['reverse_diagonal_jog_count'],1)

    def test_notch_can_end_at_internal_middle_tee_without_retiring_the_continuation(self):
        source=[(0,0),(300000,300000),(100000,500000),(-100000,700000)]
        for face,turn,mirror,transform,points in self.transforms(source):
            with self.subTest(face=face,turn=turn,mirror=mirror):
                board,net,tracks=self.board(points,face)
                self.track(board,net,transform((100000,500000)),transform((2100000,2500000)),face)
                before={track.m_Uuid.AsString()for track in board.GetTracks()}
                report=quality.analyze_board(board)
                self.assertEqual(report['reverse_diagonal_jog_count'],1)
                self.assertFalse(report['craft_ok'])
                self.assertEqual(before,{track.m_Uuid.AsString()for track in board.GetTracks()})

    def test_offset_contact_work_exhaustion_is_not_a_clean_result(self):
        board,net,_=self.board([(0,0),(1000000,0)])
        for _ in range(600):self.track(board,net,(0,0),(1000000,0),width=2000000)
        rows=[quality._track_row(track)for track in board.GetTracks()]
        _,aliases=quality._native_junction_inventory(rows)
        with self.assertRaisesRegex(ValueError,'route_contact_pair_work_bound'):
            quality._offset_cap_contact_inventory(board,rows,aliases,critical=set(),scope=set(),
                pad_absorbs_notch=lambda *args:False,min_open_angle_deg=89.)

    def test_normal_short_connected_corners_do_not_invent_an_opposite_cap_join(self):
        for points in ([(0,0),(50000,0),(100000,50000)],
                       [(0,0),(50000,0),(50000,50000)],
                       [(0,0),(10000,10000),(50000,50000),(100000,50000)]):
            for face,turn,mirror,transform,moved in self.transforms(points):
                with self.subTest(points=points,face=face,turn=turn,mirror=mirror):
                    board,_,_=self.board(moved,face)
                    report=quality.analyze_board(board)
                    self.assertTrue(report['craft_ok'])
                    self.assertFalse(report['issues'])

    def test_proposal_cannot_use_retained_branch_to_hide_image_pattern(self):
        board,net,tracks=self.board([(0,0),(1000000,0),(800000,200000)])
        self.track(board,net,(1000000,0),(1000000,-1000000))
        before={t.m_Uuid.AsString() for t in board.GetTracks()}
        result=quality.assess_proposed_route(board,[dict(net=net.GetNetname(),layer=0,
            width_nm=200000,start_nm=[800000,200000],end_nm=[2000000,1400000])],
            deadline=time.monotonic()+5)
        # The proposed edge's far end may be innocent, but the complete same-net
        # retained graph still contains an exposed acute bend in its new run.
        self.assertTrue(result['complete'])
        self.assertFalse(result['ok'])
        self.assertEqual(before,{t.m_Uuid.AsString() for t in board.GetTracks()})


if __name__=='__main__':unittest.main()
