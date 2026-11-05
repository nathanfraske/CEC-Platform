"""An existing source fault is repair input, never a new current exemption."""
from unittest import mock
import pcbnew
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
from test_rated_medium_supply_rebuild import fixture


def repair_fixture(tmp_path,rotation=0,mirror=False,face=pcbnew.F_Cu):
    source,child,uid,net,catalog=fixture(tmp_path,rotation,mirror,face)
    old=pcbnew.LoadBoard(str(source));edge=next(t for t in old.GetTracks() if force._uid(t)==uid)
    edge.SetLayer(pcbnew.In2_Cu);field._save_field_snapshot(old,source)
    catalog['contracts'][net]['routing_layers'].append('In3.Cu')
    return source,child,uid,net,catalog


def checker(catalog,*,missing=False,new_fault=False):
    def check(board,path,options):
        rows=[]
        for t in board.GetTracks():
            if t.GetClass()!='PCB_TRACK' or t.GetLayer()!=pcbnew.In2_Cu:continue
            net=str(t.GetNetname());c=catalog['contracts'][net]
            rows.append(dict(type='keepout',reserve='pour_or_widen',uuid=force._uid(t),net=net,
                layer='In2.Cu',actual_mm=t.GetWidth()/1e6,
                required_mm=c['required_by_layer_mm']['In2.Cu'],current_authority=c['current_authority']))
        if not rows and new_fault:
            net=next(iter(catalog['contracts']));c=catalog['contracts'][net]
            rows.append(dict(type='keepout',reserve='pour_or_widen',uuid='unrelated-new-fault',net=net,
                layer='F.Cu',actual_mm=.2,required_mm=.4773698,current_authority=c['current_authority']))
        if not rows:return True,'no synthetic current faults',[]
        if missing:return False,'incomplete producer',[]
        rows.append(dict(type='current_debt_inventory',schema=1,complete=True,
            trace_fault_count=len(rows),domain_fault_count=0,violation_count=len(rows)))
        return False,'explicit synthetic complete native current faults',rows
    return check


OPTIONS=dict(allow_rated_layer_bridges=True,allow_rated_source_inner_layers=True,
    repair_undersized_source=True,max_source_width_mm=1.,max_replacement_width_mm=1.)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_source_underrated_inner_can_only_be_replaced_at_complete_outer_load(tmp_path,rotation,mirror,face):
    source,child,uid,net,catalog=repair_fixture(tmp_path,rotation,mirror,face);original=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}):
        default=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            **dict(OPTIONS,repair_undersized_source=False))
        received=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],**OPTIONS)
        composed=chain.receive(source,child,board_hint='synthetic',phases=[dict(kind='rated_branch',
            candidate=str(child),retired_track_uuids=[uid],**OPTIONS)])
    assert not default['ok']
    assert received['ok'] and received['complete'] and composed['ok'] and composed['complete'],(received,composed)
    debt=received['strict_source_current_fault_repair']
    assert debt['before_fault_objects']==1 and debt['after_fault_objects']==0
    assert not debt['new_faults'] and not debt['worsened_faults']
    assert received['source_proposal']['exact_source_current_fault_keys']==[['trace',net,uid,'In2.Cu']]
    assert not received['current_authority'] and not received['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['incomplete_native_inventory','new_current_fault','narrow_replacement',
    'inner_replacement','plane_source','source_group','no_inner_scope','no_bridge_scope',
    'boolean_mode','already_rated_source','no_source_contract'])
def test_fault_repair_scope_does_not_waive_ratings_or_native_proof(tmp_path,fault):
    source,child,uid,net,catalog=repair_fixture(tmp_path);options=dict(OPTIONS)
    if fault in ('plane_source','source_group','already_rated_source'):
        b=pcbnew.LoadBoard(str(source));old=next(t for t in b.GetTracks() if force._uid(t)==uid)
        if fault=='plane_source':old.SetLayer(pcbnew.In1_Cu)
        elif fault=='already_rated_source':old.SetLayer(pcbnew.F_Cu)
        else:
            group=pcbnew.PCB_GROUP(b);group.SetName('independent-owner');b.Add(group);group.AddItem(old)
        field._save_field_snapshot(b,source)
    if fault in ('narrow_replacement','inner_replacement'):
        b=pcbnew.LoadBoard(str(child));edge=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
        if fault=='narrow_replacement':edge.SetWidth(477369)
        else:edge.SetLayer(pcbnew.In2_Cu)
        field._save_field_snapshot(b,child)
    if fault=='no_inner_scope':options['allow_rated_source_inner_layers']=False
    if fault=='no_bridge_scope':options['allow_rated_layer_bridges']=False
    if fault=='boolean_mode':options['repair_undersized_source']=1
    if fault=='no_source_contract':catalog={'contracts':{}}
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog,
                missing=fault=='incomplete_native_inventory',new_fault=fault=='new_current_fault')}):
        result=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],**options)
    assert not result['ok'] and result['errors'],result
