"""Inner supply cuts retain the SAME explicit whole-load contract and joins."""
import copy
from unittest import mock
import pcbnew
import pytest
import cec_distributed_loop_retirement as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_distributed_loop_retirement import fixture


def inner_fixture(tmp_path,angle=0,mirror=False):
    source,b,q,catalog,*rest=fixture(tmp_path,angle,mirror);b.SetCopperLayerCount(6)
    contract=catalog['contracts'][q['net']]
    contract['routing_layers']=['F.Cu','In2.Cu','B.Cu'];contract['required_by_layer_mm']['In2.Cu']=.2
    for t in b.GetTracks():
        if force._uid(t) in q['track_uuids']:t.SetLayer(6)
    field._save_field_snapshot(b,source)
    return source,b,q,catalog,rest


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_inner_exact_saved_cut_requires_explicit_policy_and_retains_full_width_terminal_joins(tmp_path,angle,mirror):
    source,b,q,catalog,rest=inner_fixture(tmp_path,angle,mirror);before=source.read_bytes()
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.plan(b,source,**q)
        plan=op.plan(b,source,**q,allow_source_inner_layers=True)
        op.subtract(b,plan);child=force._copy_family(source,tmp_path/'received')
        additive._ground_refill(b);field._save_field_snapshot(b,child)
        r=op.receive(source,child,plan,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['source_contract_preserved'] and not r['current_qualified']
    assert source.read_bytes()==before and not r['release_authority']


@pytest.mark.parametrize('bad',['missing_face','under_full_load_floor','plane_face','unknown_policy',
    'changed_source_load','inferred_sharing','source_group'])
def test_inner_option_does_not_grant_missing_face_capacity_ownership_or_load_authority(tmp_path,bad):
    source,b,q,catalog,rest=inner_fixture(tmp_path);contract=catalog['contracts'][q['net']]
    selected=next(t for t in b.GetTracks() if force._uid(t)==q['track_uuids'][0]);flag=True
    if bad=='missing_face':contract['routing_layers'].remove('In2.Cu')
    elif bad=='under_full_load_floor':contract['required_by_layer_mm']['In2.Cu']=.3
    elif bad=='plane_face':
        selected.SetLayer(4);contract['routing_layers'].append('In1.Cu');contract['required_by_layer_mm']['In1.Cu']=.2
        plane=pcbnew.ZONE(b);plane.SetLayer(4);plane.Outline().NewOutline()
        for x,y in ((.1,.1),(21.9,.1),(21.9,21.9),(.1,21.9)):
            plane.Outline().Append(round(x*1e6),round(y*1e6))
        b.Add(plane)
    elif bad=='unknown_policy':flag=1
    elif bad=='changed_source_load':contract['current_authority'].pop('geometry_margin')
    elif bad=='inferred_sharing':contract['branch_sharing_assumed']=True
    else:
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(selected)
    original=field._field_snapshot_inventory(b)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.plan(b,source,**q,allow_source_inner_layers=flag)
    assert original==field._field_snapshot_inventory(b)


def test_worker_cannot_rebind_existing_outer_only_request_to_inner_policy_after_planning(tmp_path):
    source,b,q,catalog,rest=inner_fixture(tmp_path)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        plan=op.plan(b,source,**q,allow_source_inner_layers=True)
        forged=copy.deepcopy(plan);forged['allow_source_inner_layers']=False
        with pytest.raises(ValueError):op.subtract(b,forged)


def test_inner_policy_does_not_revoke_existing_outer_scope_when_outer_ground_pours_exist(tmp_path):
    source,b,q,catalog,*rest=fixture(tmp_path);b.SetCopperLayerCount(6);q['via_uuids']=[]
    plane=pcbnew.ZONE(b);plane.SetLayer(pcbnew.B_Cu);plane.Outline().NewOutline()
    for x,y in ((.1,.1),(21.9,.1),(21.9,21.9),(.1,21.9)):
        plane.Outline().Append(round(x*1e6),round(y*1e6))
    b.Add(plane)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        normal=op.plan(b,source,**q)
        explicit=op.plan(b,source,**q,allow_source_inner_layers=True)
    assert normal['source_tracks']==explicit['source_tracks']
    assert explicit['independent_saved_receiving_required'] and not explicit['current_qualified']
