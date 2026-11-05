"""A real RC pose/ground repair is not unchanged copper or factory approval."""
import copy
import pytest
import root_received_goal_scope_20261024 as scope
from test_received_goal_scope import can_fixture


def fixture():
    r=can_fixture();r['phases'][0]=dict(kind='rc_return_pivot',receiving=dict(
        ok=True,complete=True,scope='isolated_rc_ground_pivot_receiving',errors=[],
        new_native_faults=[],new_native_field_blockers=[],source_opens=27,opens=26,
        original_native_conductor_and_terminal_partitions_preserved=True,
        source_candidate_and_code_unchanged=True,physical_placement=dict(ok=True),pivots=[{}],
        release_authority=False,power_authority=False,routing_admitted=False,placement_authority_transferred=False,
        independent_pose_and_additive_replay=dict(ok=True,complete=True,
            original_power_and_terminal_geometry_exact=True,original_power_copper_and_supply_anchors_exact=True,
            existing_ground_fill_matches_independent_native_replay=True,added_native_uuids=['actual-ground-via'])))
    return r


def test_all_actual_parent_gates_and_explicit_placement_scope_stay_mandatory():
    r=fixture();before=copy.deepcopy(r);q=scope.received_repair_scope(r)
    assert before==r and q['Source_owned_RC_placement_and_local_ground_additions_explicit']
    assert not q['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not q['new_current_or_Kelvin_qualification']


@pytest.mark.parametrize('fault',['no_reduction','boolean','error','field','partition','epoch','body',
    'power','exact','supply','fill','no_addition','no_pivot','extra_phase','whole_gate'])
def test_unreceived_RC_pivot_cannot_be_reported_as_suite_progress(fault):
    r=fixture();p=r['phases'][0]['receiving'];exact=p['independent_pose_and_additive_replay']
    if fault=='no_reduction':p['opens']=27
    elif fault=='boolean':p['opens']=True
    elif fault=='error':p['new_native_faults']=[{}]
    elif fault=='field':p['new_native_field_blockers']=['new']
    elif fault=='partition':p['original_native_conductor_and_terminal_partitions_preserved']=False
    elif fault=='epoch':p['source_candidate_and_code_unchanged']=False
    elif fault=='body':p['physical_placement']['ok']=False
    elif fault=='power':p['power_authority']=True
    elif fault=='exact':exact['complete']=False
    elif fault=='supply':exact['original_power_copper_and_supply_anchors_exact']=False
    elif fault=='fill':exact['existing_ground_fill_matches_independent_native_replay']=False
    elif fault=='no_addition':exact['added_native_uuids']=[]
    elif fault=='no_pivot':p['pivots']=[]
    elif fault=='extra_phase':r['phases'].insert(1,dict(kind='ordinary_join',receiving=dict(ok=True,complete=True)))
    else:r['gates']['current']=False
    with pytest.raises(ValueError):scope.received_repair_scope(r)
