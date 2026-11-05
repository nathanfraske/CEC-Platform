"""Reclassify only an exclusive native waypoint; full rated faces remain real."""
from unittest import mock
import pcbnew
import pytest
import cec_consumer_leaf_reconstruction as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_consumer_leaf_reconstruction import case


def make(monkeypatch,tmp_path,angle=0,mirror=False):
    source,scope,catalog,points,_,net,retained,pad_via=case(monkeypatch,tmp_path,angle,mirror)
    b=pcbnew.LoadBoard(str(source));edge=next(t for t in b.GetTracks() if force._uid(t)==retained)
    outer=edge.GetLayer();keeper_at=edge.GetStart();start=edge.GetEnd()
    old_via=next(t for t in b.GetTracks() if force._uid(t)==scope['via_uuids'][0])
    keeper=pcbnew.PCB_VIA(b);keeper.SetNetCode(b.GetNetcodeFromNetname(net));keeper.SetPosition(keeper_at)
    keeper.SetWidth(800000);keeper.SetDrill(300000);keeper.SetViaType(pcbnew.VIATYPE_THROUGH)
    keeper.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(keeper)
    extra=pcbnew.PCB_TRACK(b);extra.SetNetCode(keeper.GetNetCode());extra.SetLayer(pcbnew.In2_Cu);extra.SetWidth(500000)
    extra.SetStart(keeper_at);extra.SetEnd(old_via.GetPosition());b.Add(extra)
    scope['grouped_track_uuids'].append(retained);scope['island_track_uuids'].append(force._uid(extra))
    scope['retained_waypoint_via_uuids']=[force._uid(keeper)]
    catalog['contracts'][net]['routing_layers'].append('In3.Cu')
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proposal=worker.plan(b,source,board_hint='synthetic',**scope)
    worker.subtract(b,proposal)
    def point(x,y):
        dummy=pcbnew.PCB_TRACK(b);dummy.SetStart(pcbnew.VECTOR2I_MM(x,y));dummy.SetEnd(pcbnew.VECTOR2I_MM(x,y))
        if angle:dummy.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:dummy.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        return dummy.GetStart()
    new_via=pcbnew.PCB_VIA(b);new_via.SetNetCode(b.GetNetcodeFromNetname(net));new_via.SetPosition(point(9,5))
    new_via.SetWidth(300000+proposal['full_budget_routing_widths_nm']['In3.Cu']);new_via.SetDrill(300000)
    new_via.SetViaType(pcbnew.VIATYPE_THROUGH);new_via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(new_via)
    incoming=[];power=[]
    for a,z,layer in (((15,5),(13,7),outer),((13,7),(11,7),pcbnew.In3_Cu),((11,7),(9,5),pcbnew.In3_Cu),((9,5),(7,5),outer)):
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(new_via.GetNetCode());t.SetStart(point(*a));t.SetEnd(point(*z));t.SetLayer(layer)
        t.SetWidth(proposal['full_budget_routing_widths_nm'][pcbnew.LayerName(layer)]);b.Add(t);incoming.append(force._uid(t))
        if layer==pcbnew.In3_Cu:power.append(force._uid(t))
    worker.assign(b,proposal,incoming,[force._uid(new_via)]);additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'rated-portal-child');field._save_field_snapshot(b,child)
    return source,child,scope,catalog,force._uid(new_via),power,pad_via


OPTIONS=dict(allow_rated_layer_bridges=True,allow_rated_replacement_inner_layers=True)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_source_portal_and_new_full_inner_web_replay_without_load_split(monkeypatch,tmp_path,angle,mirror):
    source,child,scope,catalog,via_uid,_,_=make(monkeypatch,tmp_path,angle,mirror);frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.receive(source,child,board_hint='synthetic',**scope,**OPTIONS)
    assert proof['ok'] and proof['complete'],proof
    assert proof['retained_source_waypoint_barrels_reclassified']==scope['retained_waypoint_via_uuids']
    assert proof['new_barrels_added']==1 and proof['incoming_via_uuids']==[via_uid]
    web=proof['new_actual_supply_contact_webs'][0]
    assert web['ok'] and 'In3.Cu' in web['actual_contact_layers']
    assert web['source_width_by_contact_layer_nm']['In3.Cu']>web['source_width_by_contact_layer_nm']['B.Cu' if mirror else 'F.Cu']
    assert proof['source_scope']['budget']['current_authority']['amps']==.5
    assert proof['source_scope']['budget']['aggregate_current_authority']['amps']==3.
    assert not proof['new_barrel_ampacity_credited'] and not proof['release_authority']
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['component_portal','retired_portal','omitted_portal','outer_only','thin_power',
    'undersized_inner_web','changed_keeper','ground_face','boolean_rated'])
def test_portal_annotation_cannot_grant_current_copper_or_ownership(monkeypatch,tmp_path,fault):
    source,child,scope,catalog,via_uid,power,pad_via=make(monkeypatch,tmp_path);frozen=source.read_bytes()
    options=dict(OPTIONS);b=pcbnew.LoadBoard(str(child))
    if fault=='component_portal':scope['retained_waypoint_via_uuids']=[pad_via]
    elif fault=='retired_portal':scope['retained_waypoint_via_uuids']=scope['via_uuids'][:]
    elif fault=='omitted_portal':scope['retained_waypoint_via_uuids']=[]
    elif fault=='outer_only':options=dict(allow_outer_layer_bridges=True)
    elif fault=='boolean_rated':options['allow_rated_layer_bridges']=1
    elif fault=='thin_power':next(t for t in b.GetTracks() if force._uid(t)==power[0]).SetWidth(200000)
    elif fault=='ground_face':next(t for t in b.GetTracks() if force._uid(t)==power[0]).SetLayer(pcbnew.In1_Cu)
    elif fault=='undersized_inner_web':next(t for t in b.GetTracks() if force._uid(t)==via_uid).SetWidth(600000)
    else:next(t for t in b.GetTracks() if force._uid(t)==scope['retained_waypoint_via_uuids'][0]).SetWidth(900000)
    field._save_field_snapshot(b,child)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.receive(source,child,board_hint='synthetic',**scope,**options)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert source.read_bytes()==frozen
