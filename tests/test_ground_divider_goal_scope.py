"""Shape-only ledger consumers: these dictionaries are NOT native proof."""
import copy
import pytest
import root_received_goal_scope_20261024 as scope
from test_received_goal_scope import can_fixture


def fixture():
    # No file, manufacturer, plane, physical current or native qualification
    # is proved here. The real ledger must separately bind every live saved
    # receipt, exact Source/code epoch and all sixteen original-parent gates.
    r=can_fixture();yes=dict(ok=True,complete=True)
    exact=dict(yes,original_power_and_terminal_geometry_exact=True,
        original_power_copper_and_supply_anchors_exact=True,
        existing_ground_fill_matches_independent_native_replay=True)
    pad='actual-Source-lower-ground-pad';via='actual-received-in-pad-entry'
    references=[['actual-ground-reference-a',4],['actual-ground-reference-b',10]]
    entry=dict(yes,errors=[],retired_track_uuids=[],modified_nets=['GND'],new_holes=1,
        saved_return_witness_mm=0,every_source_native_partition_identical=True,
        original_parts_poses_barrels_rules_and_power_copper_unchanged=True,
        proposal=dict(pad_uuid=pad,use_existing_local_pad_rule=True,
            existing_local_pad_rule={'source':'actual-Source','group':'CEC_LOCAL_POFV_SIGNAL_VIA'},
            ops=[['via',[1000000,2000000],200000,300000]]),
        added_native_uuids=[via],actual_saved_reference_contacts=references,
        independent_additive_receiving=dict(exact),all_source_known_returns=dict(yes),
        fab_ready=False,current_qualified=False,release_authority=False)
    branch=dict(yes,scope='fresh_source_reference_divider_ground_span',errors=[],
        source_candidate_hierarchy_and_code_unchanged=True,
        no_ground_current_budget_or_public_small_span_width_waiver=True,
        no_new_holes_or_part_pose_group_rule_or_power_copper_changes=True,
        every_source_native_partition_preserved=True,
        same_source_entry_contacts_to_each_saved_ground_reference_preserved=True,
        source_cut_partition_preservation=dict(preserved=True),
        contact_kernels=dict(all_old_native_contact_kernels_fully_covered=True),
        native_field_delta=dict(no_new_blockers=True),
        source_owner=dict(kind='fresh_source_closed_reference_divider_ground_span',
            ground_pad_uuid=pad,source_entry_via_uuid=via,source_reference_contacts=references,
            inferred_ground_current_budget=False,current_qualified=False,release_authority=False),
        independent_additive_receiving=dict(exact),all_source_known_returns=dict(yes),
        current_qualified=False,routing_admitted=False,release_authority=False)
    joined=dict(yes,scope='ordinary_saved_additive_native_join',errors=[],
        source_ordinary_scope_independently_recompiled=True,source_components=2,candidate_components=1,
        added_native_uuids=['actual-ordinary-new-track'],routing_admitted=False,
        current_qualified=False,release_authority=False)
    printed=r['phases'][-1]
    r['phases']=[dict(kind='existing_local_ground_entry',receiving=entry),
        dict(kind='source_divider_ground_span',receiving=branch),
        dict(kind='ordinary_join',receiving=joined),printed]
    return r


def test_exact_received_entry_divider_signal_print_is_explicit_physical_repair_not_new_qualification():
    r=fixture();before=copy.deepcopy(r);result=scope.received_repair_scope(r)
    assert r==before and len(r['gates'])==16
    assert result['scope']=='independently_received_Source_divider_Ground_preparation_and_ordinary_join'
    assert result['Source_owned_full_class_Ground_span_and_existing_rule_entry_explicit']
    assert result['Source_ordinary_signal_additions_explicit']and result['no_public_Ground_width_or_current_rule_relaxed']
    assert result['parts_pinouts_and_board_outline_preserved']and result['all_actual_parent_gates_passed']
    assert not result['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not result['new_current_or_Kelvin_qualification']
    assert result['inherited_kelvin_uncertainty_not_newly_qualified']


@pytest.mark.parametrize('gate',list(fixture()['gates']))
@pytest.mark.parametrize('fault',['missing','false','truthy'])
def test_each_actual_parent_gate_is_required_literal_true(gate,fault):
    r=fixture()
    if fault=='missing':r['gates'].pop(gate)
    else:r['gates'][gate]=False if fault=='false'else 1
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('fault',['no_entry','no_span','no_join','no_print','swapped',
    'ordinary_role_for_span','another_after_print','wrong_print_path','wrong_print_hash'])
def test_only_exact_four_received_Source_operations_then_final_print_are_describable(fault):
    r=fixture();p=r['phases']
    if fault.startswith('no_'):p.pop({'no_entry':0,'no_span':1,'no_join':2,'no_print':3}[fault])
    elif fault=='swapped':p[1],p[2]=p[2],p[1]
    elif fault=='ordinary_role_for_span':p[1]['kind']='ordinary_join'
    elif fault=='another_after_print':p.append(copy.deepcopy(p[2]))
    elif fault=='wrong_print_path':p[-1]['candidate']='another-board'
    else:p[-1]['candidate_sha256']='another-sha'
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('phase',range(4))
@pytest.mark.parametrize('field',['ok','complete'])
def test_every_saved_phase_remains_independently_received(phase,field):
    r=fixture();r['phases'][phase]['receiving'][field]=False
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('field',['release_authority','current_qualified','full_kelvin_qualification','factory_qualified','thermal_qualified'])
def test_outer_review_cannot_claim_current_Kelvin_factory_thermal_or_release_qualification(field):
    r=fixture();r[field]=True
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('phase,field',[(0,'fab_ready'),(0,'current_qualified'),(0,'release_authority'),
    (1,'current_qualified'),(1,'routing_admitted'),(1,'release_authority'),
    (2,'current_qualified'),(2,'routing_admitted'),(2,'release_authority')])
def test_individual_guarded_phases_do_not_grant_new_qualification(phase,field):
    r=fixture();r['phases'][phase]['receiving'][field]=True
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('fault',['entry_cut','entry_net','extra_hole','nonzero_return','entry_partition',
    'entry_parts','new_rule','wrong_Source_pad','missing_entry_pad','contact_kernel','span_partition',
    'span_waiver','span_changes','span_epoch','span_field','wrong_span_role','inferred_current',
    'each_Source_plane_missing','each_Source_plane_false'])
def test_Source_ground_entry_full_class_span_and_each_saved_reference_stay_mandatory(fault):
    r=fixture();entry=r['phases'][0]['receiving'];branch=r['phases'][1]['receiving'];owner=branch['source_owner']
    if fault=='entry_cut':entry['retired_track_uuids']=['old-copper']
    elif fault=='entry_net':entry['modified_nets']=['GND','/POWER']
    elif fault=='extra_hole':entry['new_holes']=2
    elif fault=='nonzero_return':entry['saved_return_witness_mm']=.01
    elif fault=='entry_partition':entry['every_source_native_partition_identical']=False
    elif fault=='entry_parts':entry['original_parts_poses_barrels_rules_and_power_copper_unchanged']=False
    elif fault=='new_rule':entry['proposal']['use_existing_local_pad_rule']=False
    elif fault=='wrong_Source_pad':owner['ground_pad_uuid']='unrelated-pad'
    elif fault=='missing_entry_pad':entry['proposal'].pop('pad_uuid')
    elif fault=='contact_kernel':branch['contact_kernels'].pop('all_old_native_contact_kernels_fully_covered')
    elif fault=='span_partition':branch['every_source_native_partition_preserved']=False
    elif fault=='span_waiver':branch['no_ground_current_budget_or_public_small_span_width_waiver']=False
    elif fault=='span_changes':branch['no_new_holes_or_part_pose_group_rule_or_power_copper_changes']=False
    elif fault=='span_epoch':branch['source_candidate_hierarchy_and_code_unchanged']=False
    elif fault=='span_field':branch['native_field_delta']['no_new_blockers']=False
    elif fault=='wrong_span_role':branch['scope']='ordinary_saved_additive_native_join'
    elif fault=='inferred_current':owner['inferred_ground_current_budget']=True
    elif fault=='each_Source_plane_missing':branch.pop('same_source_entry_contacts_to_each_saved_ground_reference_preserved')
    else:branch['same_source_entry_contacts_to_each_saved_ground_reference_preserved']=False
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('phase',[0,1])
@pytest.mark.parametrize('guard',['independent_additive_receiving','all_source_known_returns'])
@pytest.mark.parametrize('field',['ok','complete'])
def test_exact_Ground_saved_replay_and_known_returns_cannot_be_missing_or_incomplete(phase,guard,field):
    r=fixture();r['phases'][phase]['receiving'][guard].pop(field)
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('phase',[0,1])
@pytest.mark.parametrize('field',['existing_ground_fill_matches_independent_native_replay',
    'original_power_and_terminal_geometry_exact','original_power_copper_and_supply_anchors_exact'])
def test_Source_ground_fill_and_immutable_supply_geometry_require_actual_additive_guard(phase,field):
    r=fixture();r['phases'][phase]['receiving']['independent_additive_receiving'][field]=False
    with pytest.raises(ValueError):scope.received_repair_scope(r)


@pytest.mark.parametrize('fault',['no_reduction','negative','zero','boolean','missing_tracks','untyped',
    'wrong_role','error','parent_contact'])
def test_ordinary_join_requires_actual_independent_reduction_after_Ground_preparation(fault):
    r=fixture();p=r['phases'][2]['receiving']
    if fault=='no_reduction':p['candidate_components']=p['source_components']
    elif fault=='negative':p['candidate_components']=-1
    elif fault=='zero':p['candidate_components']=0
    elif fault=='boolean':p['candidate_components']=True
    elif fault=='missing_tracks':p['added_native_uuids']=[]
    elif fault=='untyped':p['source_ordinary_scope_independently_recompiled']=False
    elif fault=='wrong_role':p['scope']='source_typed_quiet_analog_requests'
    elif fault=='error':p['errors']=['unreceived native material']
    else:r['reports']['clipped']['comparison_complete']=False
    with pytest.raises(ValueError):scope.received_repair_scope(r)
