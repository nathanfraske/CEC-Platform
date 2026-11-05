"""Typed factory-proof reporting, not independent process qualification."""
import copy

import pytest

import root_received_goal_scope_20261024 as scope


def proof(extended=False):
    value=dict(new_factory_group_uuids=[]if extended else['factory'],
        extended_factory_group_uuids=['factory']if extended else[],
        factory_group_delta_uuids=['factory'],new_normal_vias=1,new_local_vias=1,
        Source_local_POFV_vias={'local-via':dict(diameter_nm=500000,drill_nm=200000,
            Source_profile='fixture-Source-profile',Source_clamped_menu_nm=[[500000,200000]],
            provenance='positive actual Source SMD containment')},
        bounded_receiving_stages=2,each_stage_lease_s=10.,composed_budget_s=20.,
        stage_timings_s=dict(Source_geometry_field=6.,independent_saved_replay_partitions=3.))
    added=['track','local-via','normal-via']
    saved=dict(added_native_uuids=added+([]if extended else['factory']))
    return value,added,saved


@pytest.mark.parametrize('extended',[False,True])
def test_new_group_and_extension_have_different_literal_added_sets(extended):
    q,added,saved=proof(extended);result=scope._received_local_monitor_factory_scope(q,added,saved)
    assert result['new_local_vias']==1 and result['new_normal_vias']==1
    assert result['no_barrel_current_or_manufacturing_qualification']is True


def test_live_tuple_menu_and_saved_json_list_menu_mean_the_same_geometry():
    q,added,saved=proof();q['Source_local_POFV_vias']['local-via']['Source_clamped_menu_nm']=[(500000,200000)]
    assert scope._received_local_monitor_factory_scope(q,added,saved)['Source_qualified_local_via_uuids']==['local-via']


@pytest.mark.parametrize('fault',['normal_includes_local','missing_local','stale_member','wrong_added_group',
    'missing_group_delta','new_and_extended_same','two_groups','unproved_smaller_via',
    'missing_provenance','no_Source_profile','bad_menu','expired_first','expired_second',
    'truthy_count','truthy_timing','one_stage','long_lease','missing_stage'])
def test_cannot_describe_unproved_factory_or_borrow_a_deadline(fault):
    q,added,saved=proof();local=q['Source_local_POFV_vias']['local-via']
    if fault=='normal_includes_local':q['new_normal_vias']=2
    elif fault=='missing_local':q['Source_local_POFV_vias']={}
    elif fault=='stale_member':q['Source_local_POFV_vias']={'not-in-added':local}
    elif fault=='wrong_added_group':saved['added_native_uuids']=added
    elif fault=='missing_group_delta':q['factory_group_delta_uuids']=[]
    elif fault=='new_and_extended_same':q['extended_factory_group_uuids']=['factory']
    elif fault=='two_groups':q['new_factory_group_uuids']+=['second']
    elif fault=='unproved_smaller_via':local['diameter_nm']=400000
    elif fault=='missing_provenance':local['provenance']=''
    elif fault=='no_Source_profile':local['Source_profile']=''
    elif fault=='bad_menu':local['Source_clamped_menu_nm']=[[True,200000]]
    elif fault=='expired_first':q['stage_timings_s']['Source_geometry_field']=10.01
    elif fault=='expired_second':q['stage_timings_s']['independent_saved_replay_partitions']=10.01
    elif fault=='truthy_count':q['new_local_vias']=True
    elif fault=='truthy_timing':q['stage_timings_s']['Source_geometry_field']=True
    elif fault=='one_stage':q['bounded_receiving_stages']=1
    elif fault=='long_lease':q['each_stage_lease_s']=20.
    else:del q['stage_timings_s']['Source_geometry_field']
    with pytest.raises(ValueError):scope._received_local_monitor_factory_scope(q,added,saved)
