"""Only a pad-free waypoint in one proved leaf may be retired with its edges."""
from unittest import mock
import pcbnew
import pytest
import cec_consumer_leaf_reconstruction as worker
import cec_supply_consumer_branch as consumer
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_supply_consumer_branch import fixture


def case(monkeypatch,tmp_path,angle=0,mirror=False):
    b,root,anchor,feed,old,trunk,group,_,rail,declaration,_=fixture(monkeypatch,tmp_path)
    feed.SetStart(pcbnew.VECTOR2I_MM(10,10));feed.SetEnd(pcbnew.VECTOR2I_MM(13,7))
    retained=feed.Duplicate();retained.m_Uuid.Clone(pcbnew.KIID())
    retained.SetStart(pcbnew.VECTOR2I_MM(13,7));retained.SetEnd(pcbnew.VECTOR2I_MM(15,5))
    b.Add(retained);group.AddItem(retained)
    inner=old.Duplicate();inner.m_Uuid.Clone(pcbnew.KIID());inner.SetLayer(pcbnew.In2_Cu)
    inner.SetStart(pcbnew.VECTOR2I_MM(7,5));inner.SetEnd(pcbnew.VECTOR2I_MM(10,10));inner.SetWidth(500000);b.Add(inner)
    vias=[]
    for xy in ((7,5),(10,10)):
        v=pcbnew.PCB_VIA(b);v.SetNet(root.GetNet());v.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        v.SetWidth(800000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);vias.append(v)
    marker=pcbnew.PCB_TRACK(b);marker.SetStart(pcbnew.VECTOR2I_MM(9,7));marker.SetEnd(pcbnew.VECTOR2I_MM(9,7))
    for item in [*b.GetFootprints(),*b.GetTracks(),marker]:
        if angle:item.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    # Mirror the geometry, not the independent declared stack-layer role.
    inner.SetLayer(pcbnew.In2_Cu)
    source=tmp_path/'leaf-source.kicad_pcb';loaded=field._save_field_snapshot(b,source);field._save_field_snapshot(loaded,source)
    net=str(root.GetNetname());budget=consumer.contract(b,force._uid(root),board_hint='synthetic')
    raw=dict(net=net,current_authority=rail,profile=budget['copper_profile'],
        required_by_layer_mm={k:max(.2,v) for k,v in budget['aggregate_required_by_layer_mm'].items()},
        routing_layers=['F.Cu','In2.Cu','B.Cu'],clearance_mm=.2)
    scope=dict(grouped_track_uuids=[force._uid(feed)],island_track_uuids=[force._uid(inner)],via_uuids=[force._uid(vias[-1])])
    # Map native source geometry, not assumed refdes positions, to an outer
    # two-stroke replacement through the same actual capacitor terminal.
    start=tuple(retained.GetStart());end=tuple(old.GetEnd())
    points=[start,tuple(marker.GetStart()),end]
    return source,scope,{'contracts':{net:raw}},points,declaration,net,force._uid(retained),force._uid(vias[0])


def child(source,scope,points,path):
    b=pcbnew.LoadBoard(str(source));proposal=worker.plan(b,source,board_hint='synthetic',**scope)
    face=next(t.GetLayer() for t in b.GetTracks() if force._uid(t)==scope['grouped_track_uuids'][0])
    worker.subtract(b,proposal);incoming=[]
    for start,end in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(b.GetNetcodeFromNetname(proposal['net']));t.SetLayer(face)
        t.SetWidth(proposal['full_budget_outer_widths_nm'][pcbnew.LayerName(face)]);t.SetStart(pcbnew.VECTOR2I(*start));t.SetEnd(pcbnew.VECTOR2I(*end));b.Add(t);incoming.append(force._uid(t))
    worker.assign(b,proposal,incoming);additive._ground_refill(b)
    candidate=force._copy_family(source,path);field._save_field_snapshot(b,candidate)
    return candidate,proposal,incoming


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('whole_feed',[False,True])
def test_native_waypoint_reconstruction_preserves_real_terminals_and_budgets(monkeypatch,tmp_path,angle,mirror,whole_feed):
    source,scope,catalog,points,_,net,retained,_=case(monkeypatch,tmp_path,angle,mirror)
    if whole_feed:
        scope['grouped_track_uuids'].append(retained)
        b=pcbnew.LoadBoard(str(source));edge=next(t for t in b.GetTracks() if force._uid(t)==retained)
        points=[tuple(edge.GetEnd()),points[-1]]
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        candidate,proposal,incoming=child(source,scope,points,tmp_path/'child')
        proof=worker.receive(source,candidate,board_hint='synthetic',**scope)
    assert proof['ok'] and proof['complete'],proof
    assert proposal['budget']['current_authority']['amps']==.5
    assert proposal['budget']['aggregate_current_authority']['amps']==3.
    assert proof['all_actual_terminals_and_surviving_native_partitions_preserved']
    assert proof['same_native_single_trunk_tap_and_current_budgets_reproved']
    assert set(proof['incoming_track_uuids'])==set(incoming)
    assert proof['new_barrels_added']==0 and not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['component_contact','external_track','another_group','retained_component_barrel',
    'wrong_island','unowned_group_extension','missing_policy','duplicate_cut','unknown_consumer'])
def test_unproved_or_nonexclusive_source_cut_is_not_admissible(monkeypatch,tmp_path,fault):
    source,scope,catalog,_,declaration,net,retained,pad_via=case(monkeypatch,tmp_path)
    if fault=='missing_policy':declaration['params']['supply_consumer_allocations']=[]
    elif fault=='duplicate_cut':scope['island_track_uuids']*=2
    elif fault=='wrong_island':scope['island_track_uuids']=[retained]
    elif fault=='unowned_group_extension':scope['grouped_track_uuids'].append(scope['island_track_uuids'][0])
    elif fault=='retained_component_barrel':scope['via_uuids']=[pad_via]
    else:
        b=pcbnew.LoadBoard(str(source));via=next(t for t in b.GetTracks() if force._uid(t)==scope['via_uuids'][0])
        if fault=='component_contact':
            pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()=='IO');pad.SetPosition(via.GetPosition())
        elif fault=='external_track':
            t=pcbnew.PCB_TRACK(b);t.SetNet(via.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
            t.SetStart(via.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(10,12));b.Add(t)
        elif fault=='another_group':
            g=pcbnew.PCB_GROUP(b);g.SetName('unrelated owner');b.Add(g);g.AddItem(via)
        else:
            fp=next(fp for fp in b.GetFootprints() if fp.GetReference()=='NOT_A_U');fp.SetField('MPN','unknown component')
        field._save_field_snapshot(b,source)
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):worker.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',**scope)
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['thin','wrong_net','new_via','changed_survivor','changed_anchor','missing_group_member'])
def test_saved_child_cannot_acquire_unowned_geometry_or_drop_source_state(monkeypatch,tmp_path,fault):
    source,scope,catalog,points,_,net,retained,_=case(monkeypatch,tmp_path)
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        candidate,proposal,incoming=child(source,scope,points,tmp_path/'tampered')
        b=pcbnew.LoadBoard(str(candidate));edge=next(t for t in b.GetTracks() if force._uid(t)==incoming[0])
        if fault=='thin':edge.SetWidth(100000)
        elif fault=='wrong_net':edge.SetNetCode(b.GetNetcodeFromNetname('IO'))
        elif fault=='new_via':
            v=pcbnew.PCB_VIA(b);v.SetNetCode(edge.GetNetCode());v.SetPosition(edge.GetStart());v.SetWidth(800000);v.SetDrill(300000)
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='changed_survivor':next(t for t in b.GetTracks() if force._uid(t)==retained).SetWidth(300000)
        else:
            g=next(g for g in b.Groups() if force._uid(g)==proposal['group_scope']['group_uuid'])
            if fault=='changed_anchor':g.SetName(g.GetName().replace(proposal['anchor_uuid'],proposal['root_pad_uuid']))
            else:g.RemoveItem(edge)
        if fault=='wrong_net':
            # Deliberately malformed saved input must reach the independent
            # receiver; the production snapshot writer already refuses it.
            pcbnew.SaveBoard(str(candidate),b)
        else:field._save_field_snapshot(b,candidate)
        proof=worker.receive(source,candidate,board_hint='synthetic',**scope)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('value',[0,-1,161,True,float('inf'),float('nan')])
def test_source_work_limit_cannot_be_unbounded_or_boolean(monkeypatch,tmp_path,value):
    source,scope,catalog,_,_,_,_,_=case(monkeypatch,tmp_path)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError,match='source_work_limit'):
            worker.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',max_source_total_mm=value,**scope)


def test_explicit_larger_source_work_budget_changes_no_electrical_authority(monkeypatch,tmp_path):
    source,scope,catalog,_,_,_,_,_=case(monkeypatch,tmp_path)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        plans=[worker.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',max_source_total_mm=limit,**scope) for limit in (80.,160.)]
    assert plans[0]['budget']==plans[1]['budget']
    assert plans[0]['full_budget_outer_widths_nm']==plans[1]['full_budget_outer_widths_nm']
    assert plans[0]['exact_retired_uuids']==plans[1]['exact_retired_uuids']
    assert [p['source_total_length_work_ceiling_mm'] for p in plans]==[80.,160.]
