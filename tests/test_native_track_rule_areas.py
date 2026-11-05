"""Actual-width traces must respect native track permission on both search paths."""
import pcbnew
import pytest

import cec_fr as fr
import cec_native_rule_areas as areas
from test_native_via_rule_areas import board_area


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('footprint',[False,True])
@pytest.mark.parametrize('cached',[False,True])
def test_track_keepout_uses_native_polygon_and_full_width_capsule(layer,footprint,cached):
    b,n,z=board_area(layer=layer,footprint=footprint)
    start,end=pcbnew.VECTOR2I_MM(3.95,5),pcbnew.VECTOR2I_MM(3.95,8)
    assert not fr._tap_foreign_clear(b,start,end,200000,layer,0,{n.GetNetCode()},
        foreign_cache={} if cached else None)
    assert fr._tap_foreign_clear(b,pcbnew.VECTOR2I_MM(3.8,5),pcbnew.VECTOR2I_MM(3.8,8),
        200000,layer,250000,{n.GetNetCode()},foreign_cache={} if cached else None)
    # .25 mm copper clearance must not invent a .25 mm keepout setback.
    assert not areas.track_conflict(b,start,end,200000,pcbnew.B_Cu if layer!=pcbnew.B_Cu else pcbnew.F_Cu)


@pytest.mark.parametrize('cached',[False,True])
def test_holes_and_concavities_are_not_blocked_by_bbox(cached):
    b,n,z=board_area();z.Outline().NewHole(0)
    for x,y in ((5,5),(5,8),(8,8),(8,5)):
        z.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y),0,0)
    assert fr._tap_foreign_clear(b,pcbnew.VECTOR2I_MM(6,6),pcbnew.VECTOR2I_MM(7,7),
        200000,pcbnew.F_Cu,.2e6,{n.GetNetCode()},foreign_cache={} if cached else None)


@pytest.mark.parametrize('rule,tracks,layer',[(False,True,pcbnew.F_Cu),
    (True,False,pcbnew.F_Cu),(True,True,pcbnew.F_Fab)])
def test_track_permission_not_via_or_fabrication_layer(rule,tracks,layer):
    b,n,z=board_area(rule=rule,layer=layer);z.SetDoNotAllowTracks(tracks)
    assert not areas.track_conflict(b,pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(6,6),
        200000,pcbnew.F_Cu)


def test_search_diagnostics_name_actual_keepout_without_own_net_exemption():
    b,n,z=board_area();z.SetNet(n)
    zones,copper=fr._identified_foreign_shape_indexes(b,pcbnew.F_Cu,{n.GetNetCode()})
    hits=fr._snapshot_foreign_blockers(pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(6,6),
        200000,0,zones,copper)
    assert hits[0]['kind']=='native_track_rule_area' and hits[0]['uuid']==z.m_Uuid.AsString()


def test_invalid_native_track_rule_area_fails_closed():
    b,n,z=board_area();z.Outline().RemoveAllContours()
    with pytest.raises(ValueError):fr._tap_foreign_clear(b,pcbnew.VECTOR2I_MM(5,5),
        pcbnew.VECTOR2I_MM(6,6),200000,pcbnew.F_Cu,0,{n.GetNetCode()},foreign_cache={})
