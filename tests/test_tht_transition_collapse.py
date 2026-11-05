#!/usr/bin/env python3
"""Regression for redundant through-hole-pad layer-transition dogbones."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("pcbnew required") from exc

import cec_fr  # noqa: E402


class TestPTHTransitionCollapse(unittest.TestCase):
    def setUp(self):
        self.board = pcbnew.CreateEmptyBoard()
        self.net = pcbnew.NETINFO_ITEM(self.board, "/SIG")
        self.board.Add(self.net)

    @staticmethod
    def _pos(x, y):
        return pcbnew.VECTOR2I_MM(x, y)

    def _pad(self, *, pth=True):
        footprint = pcbnew.FOOTPRINT(self.board)
        footprint.SetReference("J1")
        footprint.SetPosition(self._pos(5, 5))
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(self._pos(1.8, 1.8))
        pad.SetPosition(footprint.GetPosition())
        if pth:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(self._pos(0.9, 0.9))
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
        else:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(self.net)
        footprint.Add(pad)
        self.board.Add(footprint)
        return pad

    def _track(self, start, end, layer):
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(self._pos(*start))
        track.SetEnd(self._pos(*end))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(self.board.GetLayerID(layer))
        track.SetNet(self.net)
        self.board.Add(track)
        return track

    def _via(self, x=7, y=5):
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(self._pos(x, y))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(self.board.GetLayerID("F.Cu"),
                         self.board.GetLayerID("B.Cu"))
        via.SetNet(self.net)
        self.board.Add(via)
        return via

    def test_pth_barrel_replaces_redundant_via_without_moving_geometry(self):
        self._pad(pth=True)
        stub = self._track((5, 5), (7, 5), "F.Cu")
        continuation = self._track((7, 5), (12, 8), "B.Cu")
        self._via()

        result = cec_fr.collapse_redundant_pth_transitions(self.board)

        self.assertEqual(result["removed"], 1, result)
        self.assertEqual(stub.GetLayer(), continuation.GetLayer())
        self.assertEqual(sum(t.GetClass() == "PCB_VIA"
                             for t in self.board.GetTracks()), 0)
        self.assertEqual((stub.GetStart(), stub.GetEnd()),
                         (self._pos(5, 5), self._pos(7, 5)))

    def test_smd_pad_cannot_waive_the_layer_transition(self):
        self._pad(pth=False)
        self._track((5, 5), (7, 5), "F.Cu")
        self._track((7, 5), (12, 8), "B.Cu")
        self._via()

        result = cec_fr.collapse_redundant_pth_transitions(self.board)

        self.assertEqual(result["removed"], 0, result)
        self.assertEqual(sum(t.GetClass() == "PCB_VIA"
                             for t in self.board.GetTracks()), 1)


class TestPTHFanoutCollapse(TestPTHTransitionCollapse):
    def fanout(self, *, locked=False):
        pad = self._pad(pth=True)
        stubs = [self._track((5,5),(7,5),layer) for layer in ("F.Cu","B.Cu")]
        trunks = [self._track((7,5),(12,5),"F.Cu"),
                  self._track((7,5),(7,9),"B.Cu")]
        via = self._via();via.SetLocked(locked)
        for track in stubs+trunks:
            track.SetLocked(locked)
        return pad,via,stubs,trunks

    def track_records(self):
        return {item.m_Uuid.AsString():(int(item.GetLayer()),item.GetWidth(),
            (item.GetStart().x,item.GetStart().y),(item.GetEnd().x,item.GetEnd().y),
            item.IsLocked(),item.GetNetname()) for item in self.board.GetTracks()
            if item.GetClass() == "PCB_TRACK"}

    def test_four_branch_pth_fanout_retires_via_only_without_net_propagation(self):
        _pad,_via,_stubs,_trunks = self.fanout()
        old = self.track_records()
        with mock.patch.object(pcbnew.BOARD,"BuildConnectivity",
                side_effect=AssertionError("global net propagation forbidden")):
            result = cec_fr.collapse_redundant_pth_transitions(self.board)
        self.assertEqual(result["removed"],1,result)
        self.assertEqual(self.track_records(),old)
        self.assertEqual(sum(item.GetClass()=="PCB_VIA" for item in self.board.GetTracks()),0)

    def test_locked_via_needs_explicit_private_retirement_authority(self):
        self.fanout(locked=True)
        old = self.track_records()
        held = cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(held["removed"],0)
        self.assertEqual(held["refused"][0]["reason"],"locked_retirement_authority_missing")
        permitted = cec_fr.collapse_redundant_pth_fanout_vias(self.board,allow_locked=True)
        self.assertEqual(permitted["removed"],1,permitted)
        self.assertTrue(permitted["detail"][0]["was_locked"])
        self.assertEqual(self.track_records(),old)

    def test_importer_does_not_recreate_remote_pth_fanout_via(self):
        self.fanout()
        self.assertEqual(cec_fr.collapse_redundant_pth_fanout_vias(self.board)["removed"],1)
        replay = cec_fr.synthesize_missing_layer_junction_vias(self.board)
        self.assertEqual(replay["added"],0,replay)
        self.assertEqual(replay["pth_fanout_junctions_waived"],1,replay)

    def test_every_incident_layer_needs_direct_plated_contact(self):
        _pad,_via,stubs,_trunks=self.fanout()
        cec_fr._discard_items(self.board,[stubs[1]])
        result=cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(result["removed"],0)
        self.assertEqual(result["refused"][0]["reason"],"local_plated_fanout_unproved")

    def test_layer_mask_on_nonplated_pad_cannot_supply_witness(self):
        pad,_via,_stubs,_trunks=self.fanout()
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        result=cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(result["removed"],0)

    def test_partial_via_is_not_a_supported_retirement_candidate(self):
        self.board.SetCopperLayerCount(6)
        _pad,via,_stubs,_trunks=self.fanout()
        via.SetViaType(pcbnew.VIATYPE_BLIND)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
        result=cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(result["removed"],0)
        self.assertEqual(result["refused"][0]["reason"],"unsupported_via_span")

    def test_same_net_zone_keeps_independent_barrel_ownership(self):
        self.fanout()
        zone=pcbnew.ZONE(self.board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(self.net)
        zone.Outline().NewOutline()
        for x,y in ((6,4),(8,4),(8,6),(6,6)):
            zone.Outline().Append(self._pos(x,y))
        self.board.Add(zone)
        result=cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(result["removed"],0)
        self.assertEqual(result["refused"][0]["reason"],"same_net_zone_ownership")

    def test_explicit_current_domain_protects_arbitrarily_named_signal(self):
        self.fanout()
        with mock.patch("cec_current_topology.board_current_domains",return_value={"/SIG":{}}):
            result=cec_fr.collapse_redundant_pth_fanout_vias(self.board)
        self.assertEqual(result["removed"],0)
        self.assertEqual(result["refused"][0]["reason"],"specialized_topology_owned")

    def test_declared_sensitive_or_power_roles_are_not_retired(self):
        for role in ("USB","Power","Kelvin","Analog","Clock"):
            with self.subTest(role=role):
                self.setUp();self.fanout()
                result=cec_fr.collapse_redundant_pth_fanout_vias(self.board,
                    netclass_resolver=lambda _net:dict(name=role))
                self.assertEqual(result["removed"],0)
                self.assertEqual(result["refused"][0]["reason"],"specialized_topology_owned")

    def test_bounded_refusal_does_not_mutate_board(self):
        self.fanout()
        before=self.track_records()
        result=cec_fr.collapse_redundant_pth_fanout_vias(self.board,timeout_s=0)
        self.assertEqual(result["removed"],0)
        self.assertEqual(result["stop"],"deadline")
        self.assertEqual(before,self.track_records())
        for options in ({"allow_locked":1},{"max_vias":True},{"max_vias":300},{"timeout_s":-1}):
            with self.assertRaises(ValueError):
                cec_fr.collapse_redundant_pth_fanout_vias(self.board,**options)


if __name__ == "__main__":
    unittest.main()
