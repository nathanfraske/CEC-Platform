"""Source/native macro integration, not a new current or fabrication grade.

The shared fixture uses actual canonical export and native geometry; only its
existing aggregate-current domain is synthetic and remains explicitly scoped.
"""
import copy,time
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_additional_aggregate_macro as aggregate
import cec_cell_escape_replan as escape
import cec_complete_cell_receiving as receiving
import cec_cell_macro_requests as compiler
import cec_force_current as force
from test_additional_aggregate_macro import fixture


def test_existing_minimum_and_additional_capacitor_keep_distinct_obligations(tmp_path,monkeypatch):
    source,root,parent,child,partial=fixture(tmp_path,monkeypatch)
    poses=copy.deepcopy(partial['poses'])
    selected=parent.FindFootprintByReference('EXISTING_FEED')
    poses[selected.GetReference()]=[selected.GetPosition().x/1e6,selected.GetPosition().y/1e6,selected.GetOrientationDegrees()]
    before=escape.row._source_binding(parent)
    plan=escape.prepare(parent,poses,board_hint=str(root))
    assert set(plan['selected_bypasses'])=={'EXISTING_FEED'}
    assert set(plan['additional_aggregate_capacitors'])=={'RENAMED_C'}
    requests=escape.obligations(parent,child,plan)
    extra=plan['additional_aggregate_capacitors']['RENAMED_C']
    owner=extra['source_locality_owner']['pad_uuid']
    assert 'local_supply:'+owner in requests
    local=requests['aggregate_cap_local:'+extra['footprint_uuid']]
    original=requests['local_supply:'+owner]
    assert original['b']['pad_uuid']!=local['b']['pad_uuid']
    assert local['b']['pad_uuid']==extra['supply_pad_uuid']and local['a']['pad_uuid']==owner
    assert local['source_maximum_same_surface_path_mm']==3.5
    assert requests['ground:'+extra['ground_pad_uuid']]['reach_mm']==.8
    assert extra['unchanged_selected_bypass_assignments']['AMP73:6:100n']=='EXISTING_FEED'
    assert before==escape.row._source_binding(parent)


def test_saved_pose_receiver_recovers_original_stationary_owner_not_worker_refs(tmp_path,monkeypatch):
    source,root,parent,child,partial=fixture(tmp_path,monkeypatch,routed=True)
    poses,moved=receiving._poses(parent,child,str(root))
    assert moved=={'RENAMED_C'}and set(poses)=={'RENAMED_C','AMP73'}
    old=parent.FindFootprintByReference('AMP73')
    assert poses['AMP73']==[old.GetPosition().x/1e6,old.GetPosition().y/1e6,old.GetOrientationDegrees()]
    assert not partial.get('routing_admitted',False)


def test_shared_saved_path_receiver_reobserves_additional_capacitor(tmp_path,monkeypatch):
    source,root,parent,child,partial=fixture(tmp_path,monkeypatch,routed=True)
    plan=escape.prepare(parent,partial['poses'],board_hint=str(root))
    requests=escape.obligations(parent,child,plan)
    incoming={force._uid(t)for t in child.GetTracks()}-{force._uid(t)for t in parent.GetTracks()}
    proofs=receiving._receive_paths(parent,child,requests,incoming,str(root),time.monotonic()+9.1,
        source_proposal=plan)
    additional=[q for q in proofs if q.get('kind')=='Source_additional_aggregate_capacitor_actual_saved_local_paths_and_returns']
    assert len(additional)==1 and additional[0]['independent_saved_paths']['complete']
    assert additional[0]['independent_saved_paths']['capacitors']['RENAMED_C']['actual_local_path_mm']<=3.5


def test_explicit_additional_reach_cannot_expand_the_ordinary_owner_bound(tmp_path,monkeypatch):
    source,root,parent,child,partial=fixture(tmp_path,monkeypatch)
    before=escape.row._source_binding(parent)
    plan=escape.prepare(parent,partial['poses'],board_hint=str(root),max_shift_mm=.5,
        aggregate_capacitor_max_shift_mm=6.)
    assert plan['max_shift_mm']==.5 and plan['aggregate_capacitor_max_shift_mm']==6.
    assert escape.complete_transport_shift_bound(plan)==6.
    forged=copy.deepcopy(plan);forged['aggregate_capacitor_max_shift_mm']=.5
    with pytest.raises(ValueError):escape.apply_private(parent,forged)
    assert before==escape.row._source_binding(parent)
    bad=copy.deepcopy(partial['poses']);bad['AMP73'][1]+=.6
    with pytest.raises(ValueError):
        escape.prepare(parent,bad,board_hint=str(root),max_shift_mm=.5,aggregate_capacitor_max_shift_mm=6.)
    assert before==escape.row._source_binding(parent)


@pytest.mark.parametrize('value',[True,0.,-1.,128.000001,float('nan'),float('inf')])
def test_explicit_additional_reach_remains_finite_and_128mm_bounded(value):
    with pytest.raises(ValueError):escape.aggregate_cap_shift_bound(value)


def test_explicit_additional_option_is_recompiled_not_a_packet_authority():
    assert compiler.packet_options(dict(explicit_native_macro_options=dict(aggregate_capacitor_max_shift_mm=64.)))==dict(aggregate_capacitor_max_shift_mm=64.)
    with pytest.raises(ValueError):compiler.packet_options(dict(explicit_native_macro_options=dict(aggregate_capacitor_max_shift_mm=True)))


@pytest.mark.parametrize('bound',[64.000001,80.,128.])
def test_larger_explicit_reach_is_only_transport_scope_not_owner_or_locality_authority(bound):
    assert escape.aggregate_cap_shift_bound(bound)==bound
    assert escape.complete_transport_shift_bound(dict(max_shift_mm=.5,aggregate_capacitor_max_shift_mm=bound))==bound
    assert escape.MAX_EXPLICIT_CELL_SHIFT_MM==32.


@pytest.mark.parametrize('face',[int(pcbnew.F_Cu),int(pcbnew.B_Cu)])
def test_Source_local_length_can_only_tighten_the_existing_limit(face):
    req=dict(kind='local_supply',a=dict(layers=[face]),b=dict(layers=[face]),
        source_maximum_same_surface_path_mm=3.5,source_required_surface_layer=face)
    assert escape.local_supply_path_limit(req,3.3,.5,.2)<=3.5
    assert escape.local_supply_path_limit(req,.2,.5,.2)==escape.cell._local_supply_limit_mm(.2,.5,.2)


@pytest.mark.parametrize('fault',['missing_bound','other_face','inner_face','increase','truthy','wrong_kind'])
def test_partial_or_broadened_Source_local_policy_is_refused(fault):
    face=int(pcbnew.F_Cu)
    req=dict(kind='local_supply',a=dict(layers=[face]),b=dict(layers=[face]),
        source_maximum_same_surface_path_mm=3.5,source_required_surface_layer=face)
    if fault=='missing_bound':del req['source_maximum_same_surface_path_mm']
    elif fault=='other_face':req['b']['layers']=[int(pcbnew.B_Cu)]
    elif fault=='inner_face':req['source_required_surface_layer']=int(pcbnew.In1_Cu)
    elif fault=='increase':req['source_maximum_same_surface_path_mm']=3.500001
    elif fault=='truthy':req['source_maximum_same_surface_path_mm']=True
    else:req['kind']='source_boundary'
    with pytest.raises(ValueError):escape.local_supply_path_limit(req,3.3,.5,.2)
