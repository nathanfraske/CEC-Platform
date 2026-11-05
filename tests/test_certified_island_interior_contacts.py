"""Opt-in exact source-track interiors, not new routing/terminal authority.

Private PCIe37→36 THRESH receipt df400055c94c392322a7ca289903d2d6c6d3024405017fa6cd8f721dd90634f3
motivates the generic domain; it is historical evidence, never fixture authority.
"""
from unittest.mock import patch
import math

import pcbnew
import pytest
import cec_certified_island_access as access
import cec_native_track_ports as ports


def fixture(angle=0, flipped=False):
    from test_local_copper_cell import native_cell
    board,fps,internal,external,pad,track=native_cell(names=('ALPHA','BETA'),net_name='/RENAMED_ORDINARY')
    long_track=track((5,5),(15,5))
    remote=pad('UNCONNECTED_OWNER',18,8)
    barrel=pcbnew.PCB_VIA(board);barrel.SetPosition(pcbnew.VECTOR2I_MM(15,5))
    barrel.SetWidth(pcbnew.FromMM(.6));barrel.SetDrill(pcbnew.FromMM(.3))
    barrel.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);barrel.SetNet(internal[0].GetNet());board.Add(barrel)
    # Nearby same-net track has no physical contact with the selected island.
    disconnected=track((5,7),(15,7))
    origin=pcbnew.VECTOR2I_MM(5,5)
    if flipped:
        for fp in board.GetFootprints():fp.Flip(origin,False)
        for item in board.GetTracks():item.Flip(origin,False)
    if angle:
        for fp in board.GetFootprints():fp.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        for item in board.GetTracks():item.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    source=next(iter(fps[0].Pads()));target=next(iter(remote.Pads()))
    return board,[(p,p.GetPosition().x,p.GetPosition().y)for p in (source,target)],long_track,barrel,disconnected


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('flipped',[False,True])
def test_optin_interior_reserved_before_aliases_exact_native_and_source_unchanged(angle,flipped):
    import cec_local_copper_cell as cell
    board,sources,long_track,_,disconnected=fixture(angle,flipped);code=sources[0][0].GetNetCode()
    before=cell.copper_inventory(board)
    baseline=access.plan(board,code,sources,limit=6,class_width_nm=220000)
    assert baseline==access.plan(board,code,sources,limit=6,class_width_nm=220000,interior_contacts=False)
    assert all(e['kind']!='track_contact'for r in baseline['candidates']for e in r['endpoints'])
    with patch.object(pcbnew.BOARD,'BuildConnectivity',side_effect=AssertionError('source net mutation')), \
         patch.object(pcbnew.BOARD,'GetConnectivity',side_effect=AssertionError('cached graph')):
        got=access.plan(board,code,sources,limit=6,class_width_nm=220000,interior_contacts=True)
    assert len(got['candidates'])<=6
    assert got['candidates'][0]['endpoints'][0]['kind']=='track_contact'
    items={t.m_Uuid.AsString():t for t in board.GetTracks()}
    contacts=[e for row in got['candidates']for e in row['endpoints']if e['kind']=='track_contact']
    assert contacts
    for e in contacts:
        item=items[e['uuid']];point=tuple(round(e[k]*1e6)for k in ('x_mm','y_mm'))
        assert e['uuid']!=disconnected.m_Uuid.AsString()
        assert ports.on_centerline(item,point)
        assert min(math.dist(point,(end.x,end.y))for end in (item.GetStart(),item.GetEnd()))>=220000
        assert math.dist(point,(sources[0][1],sources[0][2]))<=8e6+1e-6
    tier=got['interior_contact_tier'];assert tier['reserved_limit']<=2 and tier['max_sites_per_track']==4
    assert tier['routing_authority'] is False and tier['geometry_only'] is True
    assert tier['pair_distance_bound_mm']==25 and tier['local_shift_bound_mm']==8
    assert cell.copper_inventory(board)==before


def test_remote_existing_access_keeps_first_tier_then_interiors():
    board,sources,_,barrel,_=fixture();code=sources[0][0].GetNetCode()
    got=access.plan(board,code,sources,limit=6,class_width_nm=220000,
        interior_contacts=True,existing_access_shift_mm=16)
    assert got['candidates'][0]['endpoints'][0]['uuid']==barrel.m_Uuid.AsString()
    assert any(e['kind']=='track_contact'for row in got['candidates'][1:3]for e in row['endpoints'])


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_optin_must_be_explicit_bool(value):
    board,sources,_,_,_=fixture()
    with pytest.raises(ValueError,match='bounded island'):
        access.plan(board,sources[0][0].GetNetCode(),sources,interior_contacts=value)


@pytest.mark.parametrize('width',[0,-1,True,.22,'220000'])
def test_interior_width_is_positive_literal_native_integer(width):
    board,sources,_,_,_=fixture()
    with pytest.raises(ValueError):access.plan(board,sources[0][0].GetNetCode(),sources,
        interior_contacts=True,class_width_nm=width)


def test_zero_limits_pair_shift_inventory_and_stale_identity():
    board,sources,_,_,_=fixture();code=sources[0][0].GetNetCode()
    assert access.plan(board,code,sources,limit=0,interior_contacts=True)['candidates']==[]
    assert access.plan(board,code,sources,max_items=1,interior_contacts=True)['refusal']=='island_inventory_budget_exhausted'
    assert access.plan(board,code,sources,max_shift_mm=0,interior_contacts=True)['interior_contact_tier']['proposed_pairs']==0
    assert not access.plan(board,code,sources,max_mm=.1,interior_contacts=True)['candidates']
    assert access.plan(board,code,[(sources[0][0],0,0),sources[1]],interior_contacts=True)['refusal']=='source_point_not_live'


def test_bad_port_sampler_cannot_create_offline_or_end_alias_contacts():
    board,sources,track,_,_=fixture();code=sources[0][0].GetNetCode()
    a=track.GetStart()
    with patch.object(ports,'sites',return_value=[(a.x+1,a.y),(a.x+500000,a.y+1)]):
        got=access.plan(board,code,sources,interior_contacts=True,class_width_nm=220000)
    assert not any(e['kind']=='track_contact'for r in got['candidates']for e in r['endpoints'])


def test_wrong_net_and_non_octilinear_material_do_not_gain_authority():
    board,sources,track,_,_=fixture();code=sources[0][0].GetNetCode();uid=track.m_Uuid.AsString()
    foreign=pcbnew.NETINFO_ITEM(board,'/FOREIGN');board.Add(foreign);track.SetNet(foreign)
    got=access.plan(board,code,sources,interior_contacts=True)
    assert all(e['uuid']!=uid for row in got['candidates']for e in row['endpoints'])
    track.SetNet(sources[0][0].GetNet());track.SetEnd(pcbnew.VECTOR2I_MM(15,5.001))
    got=access.plan(board,code,sources,interior_contacts=True)
    assert all(e['uuid']!=uid or e['kind']!='track_contact'for row in got['candidates']for e in row['endpoints'])


def test_geometrically_identical_other_board_source_is_not_identity():
    board,sources,_,_,_=fixture()
    other,other_sources,_,_,_=fixture()
    assert (sources[0][1],sources[0][2])==(other_sources[0][1],other_sources[0][2])
    got=access.plan(board,sources[0][0].GetNetCode(),[other_sources[0],sources[1]],
        interior_contacts=True)
    assert got['refusal']=='source_not_live_on_target_net'
