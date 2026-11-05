"""Caller-proved owner exemptions must neither erase cavities nor leak to caps."""
import math

import pytest

from cec_cell_packing import contact_translation_sites
import cec_terminal_range as reach
from test_terminal_range import native_fixture


@pytest.mark.parametrize('bounds', [(-1,-1,1,1), (-1,0,1,0)])
def test_member_specific_obstacle_keeps_owner_endpoint_and_satellite_clear(bounds):
    parts=[(0,0,2,2),(4,0,5,1)]
    region=(0,0,3,3)
    assert not contact_translation_sites(parts,bounds=bounds,obstacles=[region])
    sites=contact_translation_sites(parts,bounds=bounds,clearance=.1,
        member_obstacles=[[],[region]])
    assert sites
    assert all(x+parts[1][0]>region[2]+.1 for x,y in sites)
    # An ordinary global body collision still constrains every member.
    assert not contact_translation_sites(parts,bounds=bounds,obstacles=[region],
        member_obstacles=[[],[]])


def test_specific_obstacles_count_toward_same_finite_work_budget():
    assert not contact_translation_sites([(0,0,1,1)],bounds=(-2,-2,2,2),
        member_obstacles=[[(5,5,6,6)]*3],max_exclusions=2)
    with pytest.raises(ValueError,match='one obstacle collection'):
        contact_translation_sites([(0,0,1,1)],bounds=(-2,-2,2,2),member_obstacles=[])
    with pytest.raises(ValueError,match='finite and ordered'):
        contact_translation_sites([(0,0,1,1)],bounds=(-2,-2,2,2),
            member_obstacles=[[(0,0,float('nan'),2)]])


def provider_sites(board,candidate,members,regions):
    provider=reach.native_cavity_provider(board,candidate,'owner',members,
        max_translation_mm=40,reserved_regions=regions)
    return provider(0,[(-20,-4),(-20,4)],8.7)


@pytest.mark.parametrize('flipped',[False,True])
def test_native_owner_net_exemption_does_not_apply_to_supply_bypass(tmp_path,flipped):
    source,board,candidate,rows,details=native_fixture(tmp_path,flipped)
    before=source.read_bytes()
    # Isolate the body/ownership contract. The separate two-net test below
    # proves that an endpoint exemption cannot excuse a foreign copper pad.
    owner=board.FindFootprintByReference('owner')
    pads=list(owner.Pads())
    pads[1].SetNet(pads[0].GetNet())
    side='B.Cu' if flipped else 'F.Cu'
    region=dict(net='renamed_a',layer=side,box=[0,0,60,40])
    assert provider_sites(board,candidate,['owner'],[region])
    # The bypass carries supply, not the sensed force net. Its entire body
    # stays reserved even though the owner is an intentional rail endpoint.
    assert not provider_sites(board,candidate,['owner','bypass'],[region])
    explicit=dict(region,exempt_refs=['owner','bypass'])
    assert not provider_sites(board,candidate,['owner','bypass'],[explicit])
    assert not provider_sites(board,candidate,['owner'],[dict(region,exempt_refs=[])])
    assert source.read_bytes()==before


@pytest.mark.parametrize('explicit',[False,True])
def test_endpoint_body_exemption_never_licenses_another_net_copper_land(tmp_path,explicit):
    source,board,candidate,rows,details=native_fixture(tmp_path)
    region=dict(net='renamed_a',layer='F.Cu',box=[0,0,60,40])
    if explicit:region['exempt_refs']=['owner']
    assert not provider_sites(board,candidate,['owner'],[region])


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_cavity_witnesses_leave_each_foreign_pad_outside_unchanged_copper(tmp_path,angle):
    import pcbnew
    source,board,candidate,rows,details=native_fixture(tmp_path)
    region=dict(net='renamed_a',layer='F.Cu',box=[0,9.5,60,10.5],clearance_mm=.2)
    provider=reach.native_cavity_provider(board,candidate,'owner',['owner'],
        max_translation_mm=40,reserved_regions=[region])
    origin=candidate.P['owner'][:2]
    target=[reach.rotate_board_point(pair,origin,angle) for pair in [(30,12),(30,8)]]
    centres=[(10-p[0],y-p[1]) for p,y in zip(target,[8,12])]
    sites=provider(angle,centres,8.7)
    assert sites
    foreign=next(p for p in board.FindFootprintByReference('owner').Pads()
                 if p.GetNetname()=='renamed_b')
    bb=foreign.GetBoundingBox()
    corners=[reach.rotate_board_point((x/1e6,y/1e6),origin,angle)
             for x in (bb.GetLeft(),bb.GetRight()) for y in (bb.GetTop(),bb.GetBottom())]
    for dx,dy in sites:
        x0,x1=min(p[0] for p in corners)+dx,max(p[0] for p in corners)+dx
        y0,y1=min(p[1] for p in corners)+dy,max(p[1] for p in corners)+dy
        assert y1<9.5-.199 or y0>10.5+.199 or x1<-.199 or x0>60.199


def test_native_wrong_face_and_all_layer_contracts_are_distinct(tmp_path):
    source,board,candidate,rows,details=native_fixture(tmp_path)
    region=dict(net='foreign',layer='B.Cu',box=[0,0,60,40])
    assert provider_sites(board,candidate,['owner'],[region])
    assert not provider_sites(board,candidate,['owner'],[dict(region,all_layers=True)])


@pytest.mark.parametrize('fault',[{}, {'box':[0,0,math.inf,20]},
    {'box':[0,0,60,40],'clearance_mm':float('nan')},
    {'box':[0,0,60,40],'clearance_mm':-1}])
def test_incomplete_relevant_reservation_is_not_dropped(tmp_path,fault):
    source,board,candidate,rows,details=native_fixture(tmp_path)
    with pytest.raises(ValueError,match='reservation'):
        provider_sites(board,candidate,['owner'],[dict(net='foreign',**fault)])
