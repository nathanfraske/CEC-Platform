"""Package preclosure respects field rules before committing both members."""
import math

import pcbnew
import pytest

import cec_fr as fr
import cec_field_coupling as field
import cec_fab_profile as fab
from test_field_proposals import track, signature
from test_lastmile import _board


def fixture(angle=0, pair_names=("/DATA_A", "/DATA_B")):
    board = _board([], edge=(0, 0, 40, 40))
    for name in (*pair_names, "/quiet"):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("renamed-package")
    board.Add(fp)
    for index, (name, x, y) in enumerate((
            (pair_names[0], 10, 18), (pair_names[0], 14, 18),
            (pair_names[1], 10, 20), (pair_names[1], 14, 20)), 1):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(index))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        pad.SetNet(board.FindNet(name))
        fp.Add(pad)
    def rotate(point):
        # KiCad board coordinates have downward-positive Y.
        a = math.radians(-angle)
        x, y = point[0]-20, point[1]-20
        return (round(20+x*math.cos(a)-y*math.sin(a), 6),
                round(20+x*math.sin(a)+y*math.cos(a), 6))
    fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    retained = track(board, "/quiet", rotate((9, 22)), rotate((15, 22)), width=2)
    retained.SetLocked(True)
    board.BuildConnectivity()
    def resolver(net):
        return dict(name="HighSpeed" if net in pair_names else "Sensitive",
                    track_width=.2, diff_pair_width=.2, clearance=.2)
    return board, dict(p=pair_names[0], n=pair_names[1]), resolver


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("names", [("/DATA_A", "/DATA_B"), ("/USB_D_P", "/USB_D_N")])
def test_unshielded_direct_links_never_commit(angle, names):
    board, pair, resolver = fixture(angle, names)
    before = signature(board)
    result = fr.synthesize_same_footprint_links(board, max_mm=6,
        include_nets=set(names), pair_declarations=[pair], netclass_resolver=resolver,
        allow_maze=False, bridge_fast=True)
    assert result["pair_linked"] == 0
    assert result["field_guard"]["refused"] >= 1
    assert signature(board) == before
    assert field.field_coupling_summary("", board=board, _netclass_resolver=resolver)["ok"]


def test_unknown_field_evidence_is_not_permission(monkeypatch):
    board, pair, resolver = fixture()
    before = signature(board)
    monkeypatch.setattr(field, "assess_proposed_route", lambda *a, **k:
                        dict(complete=False, ok=None, reason="missing native field proof"))
    result = fr.synthesize_same_footprint_links(board, max_mm=6,
        include_nets={pair["p"], pair["n"]}, pair_declarations=[pair],
        netclass_resolver=resolver, allow_maze=False)
    assert not result["pair_linked"] and result["field_guard"]["unknown"] >= 1
    assert signature(board) == before


def test_pofv_ownership_is_exact_new_geometry_not_foreign_retained_vias(monkeypatch):
    board, pair, resolver = fixture()
    seen = []
    monkeypatch.setattr(fr, "group_local_pofv_signal_vias", lambda b, items: seen.extend(items))
    result = fr.synthesize_same_footprint_links(board, include_nets=set(),
                                               pair_declarations=[pair])
    assert seen == [] and result["local_pofv_signal_vias"] is None


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_two_row_shielded_fallback_has_native_local_ownership(monkeypatch, angle):
    board, pair, resolver = fixture(angle, ("/USB_D_P", "/USB_D_N"))
    board.SetCopperLayerCount(6)
    properties = board.GetProperties()
    properties["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
    board.SetProperties(properties)
    board.Add(pcbnew.NETINFO_ITEM(board, "GND"))
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    native_field = field.assess_proposed_route
    observed = []
    def isolated_field(b, tracks, *, proposed_vias=(), **kwargs):
        if not proposed_vias:
            return native_field(b, tracks, **kwargs)
        # Isolate the topology/ownership unit from fill construction. Real
        # refill/unknown/retained-aperture behavior has separate native tests.
        observed.append((tracks, proposed_vias))
        return dict(complete=True, ok=True, reason="isolated field unit")
    monkeypatch.setattr(field, "assess_proposed_route", isolated_field)
    result = fr.synthesize_same_footprint_links(board, max_mm=6,
        include_nets={pair["p"], pair["n"]}, pair_declarations=[pair],
        netclass_resolver=resolver, allow_maze=False, bridge_fast=True)
    assert result["pair_linked"] == 2 and observed
    assert result["field_guard"]["refused"] >= 1
    ownership = result["local_pofv_signal_vias"]
    assert ownership["added_vias"] == 4
    members = {v.m_Uuid.AsString() for g in board.Groups()
               if g.GetName() == fr.LOCAL_POFV_SIGNAL_VIA_GROUP for v in g.GetItems()}
    assert members.isdisjoint(before)
    assert len(members) == 4
    for via in board.GetTracks():
        if via.m_Uuid.AsString() in members:
            assert fab.local_pofv_via_decision(board, via)[0] and via.IsLocked()
    assert any(v["net"] == "GND" for _tracks, vias in observed for v in vias)
