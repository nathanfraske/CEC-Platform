"""Optional pose proposals acquire only real bounded ordinary obstructions."""
import copy
import math

import pcbnew
import pytest
from shapely.geometry import Point

import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as complete
import cec_field_coupling as field
import cec_force_current as force
import cec_native_cell_pose_domains as domains
import cec_ordinary_route_receiving as ordinary
from test_complete_macro_cell import fixture as macro_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False,fault=None,extra=False,noncausal=False):
    source,parent,unused,initial=macro_fixture(tmp_path,monkeypatch,back=back)
    net='GND' if fault=='ground' else 'FOREIGN_DATA'
    if not parent.FindNet(net):parent.Add(pcbnew.NETINFO_ITEM(parent,net))
    y=24 if noncausal else 21
    edge=track(parent,net,(20,y),(28,y),width=.4 if fault=='wide' else .2)
    edge.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    if fault=='locked':edge.SetLocked(True)
    if fault=='mask':edge.SetHasSolderMask(True)
    if fault=='group':
        group=pcbnew.PCB_GROUP(parent);group.SetName('protected_source_group');parent.Add(group);group.AddItem(edge)
    ids={force._uid(edge)}
    if extra:
        second=track(parent,net,(20,y+.3),(28,y+.3),width=.2)
        second.SetLayer(edge.GetLayer());ids.add(force._uid(second))
    for x in (20,28):
        via=pcbnew.PCB_VIA(parent);via.SetNet(parent.FindNet(net));via.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(via)
    if quarter:
        for item in [*parent.GetFootprints(),*parent.GetTracks(),*parent.Zones()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    c,s=round(math.cos(math.radians(quarter*90))),round(math.sin(math.radians(quarter*90)))
    dx,dy=12*(c+s),12*(c-s)
    poses={fp.GetReference():[fp.GetPosition().x/1e6+dx,fp.GetPosition().y/1e6+dy,fp.GetOrientationDegrees()]
        for fp in parent.GetFootprints() if fp.GetReference() in initial['source_plan']['poses']}
    field._save_field_snapshot(parent,source);additive.bind_local_via_rule(parent,source)
    original=ordinary.eligible_nets
    # Explicit fixture electrical typing only; all native ownership,
    # clearance, construction and saved receiving remain real.
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**kw:
        original(*a,**kw)-{net} if fault=='unknown' else original(*a,**kw)|{net})
    options=dict(board_hint='opaque',max_shift_mm=20.,transport_source_barrels=True,
        frozen_target_refs=sorted(poses),radius_mm=.25,grid_mm=.25,max_candidates=8,max_results=1)
    return source,poses,ids,options


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_obstruction_is_acquired_only_after_opt_in_and_fresh_native_compilation(tmp_path,monkeypatch,quarter,back):
    source,poses,ids,options=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw=source.read_bytes()
    blocked=domains.propose(source,poses,**options)
    assert not blocked['offers'] and not blocked['ordinary_obstacle_reconstruction_proposals_enabled']
    result=domains.propose(source,poses,**options,allow_ordinary_obstacle_reconstruction=True)
    assert result['offers'],(result['domain_stages'],result['fresh_receiving'])
    offer=result['offers'][0];packet=offer['source_macro_packet']
    assert set(result['negotiable_source_ordinary_track_uuids'])>=ids
    assert set(offer['source_construction_options']['additional_obstacle_track_uuids'])==ids
    assert set(packet['explicit_additional_obstacle_track_uuids'])==ids
    ownership=[q for q in packet['additional_source_boundary_ownership'] if q['change']['uuid'] in ids]
    assert len(ownership)==len(ids)
    assert all(q['authority']['kind']=='positive_source_ordinary' and
        q['source_native_obstacle_ownership']['literal_foreign_native_conflicts'] for q in ownership)
    private,recompiled=compiler.compile(source,offer['poses'],**offer['source_construction_options'])
    assert recompiled==packet and source.read_bytes()==raw
    assert not result['routing_admitted'] and not result['fab_ready'] and not result['release_authority']


@pytest.mark.parametrize('fault',['unknown','ground','wide','locked','mask','group'])
def test_protected_or_untyped_source_stays_a_real_obstacle(tmp_path,monkeypatch,fault):
    source,poses,ids,options=fixture(tmp_path,monkeypatch,fault=fault);raw=source.read_bytes()
    result=domains.propose(source,poses,**options,allow_ordinary_obstacle_reconstruction=True)
    assert not result['offers'] and not ids&set(result['negotiable_source_ordinary_track_uuids'])
    assert source.read_bytes()==raw and not result['routing_admitted']


def test_unobstructing_ordinary_source_edge_is_not_gratuitously_retired(tmp_path,monkeypatch):
    source,poses,ids,options=fixture(tmp_path,monkeypatch,noncausal=True);raw=source.read_bytes()
    result=domains.propose(source,poses,**options,allow_ordinary_obstacle_reconstruction=True)
    assert result['offers'],result['fresh_receiving']
    assert not set(result['offers'][0]['source_construction_options']['additional_obstacle_track_uuids'])&ids
    assert source.read_bytes()==raw


def test_insufficient_explicit_reconstruction_budget_does_not_silently_expand(tmp_path,monkeypatch):
    source,poses,ids,options=fixture(tmp_path,monkeypatch,extra=True);raw=source.read_bytes()
    result=domains.propose(source,poses,**options,allow_ordinary_obstacle_reconstruction=True,max_obstacle_tracks=1)
    assert not result['offers'] and source.read_bytes()==raw
    assert any(q.get('ordinary_obstacle_acquisition_refusal')=='native_pose_ordinary_obstacle_count_bound'
        for q in result['domain_stages'])


@pytest.mark.parametrize('back',[False,True])
def test_acquired_edge_requires_full_routing_and_independent_saved_receiving(tmp_path,monkeypatch,back):
    source,poses,ids,options=fixture(tmp_path,monkeypatch,back=back);raw=source.read_bytes()
    offered=domains.propose(source,poses,**options,allow_ordinary_obstacle_reconstruction=True)
    assert offered['offers'],offered['fresh_receiving']
    offer=offered['offers'][0];construction=offer['source_construction_options']
    private,packet=compiler.compile(source,offer['poses'],**construction)
    additive._ground_refill(private)
    proof=complete.screen(source,private,packet,board_hint='opaque',cooperative_conflict_negotiation=True)
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'),proof.get('selection'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'UNADMITTED-ordinary-obstacle-rebuild')
    field._save_field_snapshot(private,child);additive.bind_local_via_rule(private,child)
    received=complete.receive(source,child,**construction)
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok'] and source.read_bytes()==raw
    assert not received['fab_ready'] and not received['release_authority']


@pytest.mark.parametrize('invalid',[None,1,'yes',[]])
def test_reconstruction_option_is_strict_and_requires_complete_native_macro_receiving(invalid):
    with pytest.raises(ValueError):
        domains.propose('missing',{'opaque':[0,0,0]},board_hint='opaque',
            allow_ordinary_obstacle_reconstruction=invalid)


def test_ordinary_obstacle_option_cannot_be_used_without_complete_macro_receiving():
    with pytest.raises(ValueError,match='requires_complete_macro_receiving'):
        domains.propose('missing',{'opaque':[0,0,0]},board_hint='opaque',
            allow_ordinary_obstacle_reconstruction=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_required_supply_options_reach_fresh_pose_compilation_without_virtual_copper(tmp_path,monkeypatch,quarter,back):
    from test_macro_supply_departure import fixture as supply_fixture
    source,parent,poses,request=supply_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw=source.read_bytes()
    result=domains.propose(source,poses,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=sorted(poses),radius_mm=.25,max_candidates=8,max_results=1,
        allow_octilinear_rotations=True,required_supply_departures=[request])
    assert result['offers'],result['fresh_receiving']
    offer=result['offers'][0];options=offer['source_construction_options']
    assert options['required_supply_departures']==[request] and options['allow_octilinear_rotations'] is True
    assert offer['source_macro_packet']['required_supply_departure_columns']
    assert offer['complete_routing_and_independent_saved_receiving_still_required']
    assert not result['routing_admitted'] and source.read_bytes()==raw


@pytest.mark.parametrize('angle',[0,45,90,180,270])
def test_world_signal_offset_is_not_rotated_a_second_time_with_the_owner(angle):
    from shapely import affinity
    rigid=Point(3,4);offset=(125000,-500000)
    member=dict(kind='copper',native_world_signal_offset_nm=offset,
        geometry=affinity.translate(rigid,offset[0]/1e6,offset[1]/1e6))
    result=domains._rotated_member(member,angle,(1,2))
    expected=affinity.translate(affinity.rotate(rigid,-angle,origin=(1,2)),offset[0]/1e6,offset[1]/1e6)
    assert result['geometry'].distance(expected)<.000001 and member['geometry'].equals_exact(
        affinity.translate(rigid,offset[0]/1e6,offset[1]/1e6),1e-12)
