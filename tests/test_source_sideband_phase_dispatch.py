"""Typed sideband dispatch/reporting; synthetic receipts are not admission.

Native cases invoke the real saved owners. Mocks below test dispatch arguments
only, never substitute for physical/current/field or whole16-gate evidence.
"""
import copy
from pathlib import Path

import pytest

import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
import root_received_goal_scope_20261024 as scopes
from test_received_goal_scope import can_fixture


FRONTIER='source_connector_native_frontier'
TAP='source_series_resistor_monitor_tap'
DIRECT='source_connector_feedthrough'


def row(kind=FRONTIER, pair=('first-land','second-land'), *, suffix='', **extra):
    result=dict(kind=kind,candidate='/actual/child'+suffix,candidate_sha256='a'*64)
    if kind==TAP:
        result.update(connector_pad_uuids=list(pair),target_pad_uuid='resistor-land'+suffix)
    else:
        result['pad_uuids']=list(pair)
        if kind==FRONTIER:result['access_uuids']=['retained-a'+suffix,'retained-b'+suffix]
    return dict(result,**extra)


def printing():
    return dict(kind='print_context',candidate='/actual/print',candidate_sha256='b'*64,proposal='/actual/print-proposal')


def test_distinct_channels_then_their_monitor_taps_keep_existing_six_phase_budget():
    phases=[row(),row(pair=('other-a','other-b'),suffix='2'),row(TAP,suffix='tap'),
            row(TAP,pair=('other-a','other-b'),suffix='tap2'),printing()]
    assert transaction.validate_phases(phases)==[FRONTIER,FRONTIER,TAP,TAP,'print_context']
    assert transaction.MAX_LOCAL_PHASES==6
    assert transaction.validate_phases([row(TAP),printing()])==[TAP,'print_context']
    assert transaction.validate_phases([row(DIRECT),row(TAP),printing()])==[DIRECT,TAP,'print_context']


@pytest.mark.parametrize('kind',[FRONTIER,TAP])
@pytest.mark.parametrize('key',['net','width','clearance','diameter','drill','points_nm','position_nm',
    'layer','amps','current','allow_locked','new_vias','allow_ground_fill','role','manufacturer',
    'timeout_s','lease_s','callback','proposal','receiving','ok'])
def test_adapter_has_no_geometry_role_current_or_cached_proof_fields(kind,key):
    value=row(kind);value[key]=True
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([value])


@pytest.mark.parametrize('kind',[FRONTIER,TAP])
@pytest.mark.parametrize('fault',['wrong_schema','missing','nonlist','empty','one','three','repeat',
    'empty_id','nonstring','whitespace','control','long','hash','path'])
def test_exact_literal_sideband_identity_schema(kind,fault):
    value=row(kind);field='access_uuids'if kind==FRONTIER else'connector_pad_uuids'
    if fault=='wrong_schema':value['kind']=TAP if kind==FRONTIER else FRONTIER
    elif fault=='missing':value.pop(field)
    elif fault=='hash':value['candidate_sha256']='not-a-sha'
    elif fault=='path':value['candidate']=''
    else:value[field]={'nonlist':'ab','empty':[],'one':['a'],'three':['a','b','c'],
        'repeat':['a','a'],'empty_id':['a',''],'nonstring':['a',True],
        'whitespace':['a',' b'],'control':['a','b\nq'],'long':['a','b'*129]}[fault]
    with pytest.raises((ValueError,TypeError)):transaction.validate_phases([value])


@pytest.mark.parametrize('fault',['pair','reverse','direct_then_frontier','frontier_then_direct',
    'tap_repeat','tap_target_repeat','tap_target_is_connector','connector_after_tap','after_print','over_budget'])
def test_repeated_scope_or_reordered_authority_does_not_fund_retries(fault):
    rows=[row()]
    if fault=='pair':rows.append(row(suffix='2'))
    elif fault=='reverse':rows.append(row(pair=('second-land','first-land'),suffix='2'))
    elif fault=='direct_then_frontier':rows=[row(DIRECT),row(suffix='2')]
    elif fault=='frontier_then_direct':rows.append(row(DIRECT,suffix='2'))
    elif fault=='tap_repeat':rows=[row(TAP),row(TAP,suffix='2')]
    elif fault=='tap_target_repeat':rows=[row(TAP),row(TAP,pair=('x','y'),suffix='2',target_pad_uuid='resistor-land')]
    elif fault=='tap_target_is_connector':rows=[row(TAP,target_pad_uuid='first-land')]
    elif fault=='connector_after_tap':rows=[row(TAP),row(suffix='2')]
    elif fault=='after_print':rows=[printing(),row()]
    else:rows=[row(pair=(str(i)+'a',str(i)+'b'),suffix=str(i))for i in range(7)]
    with pytest.raises(ValueError):transaction.validate_phases(rows)


def saved_row(tmp_path,kind):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source dispatch bytes')
    child=tmp_path/'child.kicad_pcb';child.write_text('candidate dispatch bytes')
    value=row(kind,candidate=str(child),candidate_sha256=force._hash(child))
    return source,child,value


@pytest.mark.parametrize('kind',[FRONTIER,TAP,DIRECT])
def test_fixed_ten_second_dispatch_calls_only_its_existing_public_owner(tmp_path,monkeypatch,kind):
    source,child,value=saved_row(tmp_path,kind);calls=[]
    def invoke(label):
        def receive(*args,**kwargs):
            calls.append((label,args,kwargs));return dict(ok=True,complete=True,dispatch_only=True)
        return receive
    monkeypatch.setattr(transaction.connector_feedthrough,'receive',invoke(DIRECT))
    monkeypatch.setattr(transaction.connector_feedthrough,'receive_native_frontier',invoke(FRONTIER))
    monkeypatch.setattr(transaction.sideband_monitor_tap,'receive',invoke(TAP))
    transaction.validate_phases([value])
    actual,proof=transaction.receive_phase(source,source,value,'actual-Source')
    expected=dict(board_hint='actual-Source',timeout_s=10.)
    expected.update({k:value[k]for k in transaction.KINDS[kind]})
    assert actual==child and proof['dispatch_only']is True
    assert calls==[(kind,(source,child),expected)]


@pytest.mark.parametrize('kind',[FRONTIER,TAP])
@pytest.mark.parametrize('fault',['stale','same','hardlink','injected','missing'])
def test_bad_saved_identity_never_dispatches(tmp_path,monkeypatch,kind,fault):
    source,child,value=saved_row(tmp_path,kind)
    monkeypatch.setattr(transaction.connector_feedthrough,'receive_native_frontier',lambda *a,**k:pytest.fail('invalid frontier dispatched'))
    monkeypatch.setattr(transaction.sideband_monitor_tap,'receive',lambda *a,**k:pytest.fail('invalid tap dispatched'))
    if fault=='stale':child.write_text('changed')
    elif fault=='same':value.update(candidate=str(source),candidate_sha256=force._hash(source))
    elif fault=='hardlink':
        alias=tmp_path/'alias.kicad_pcb';alias.hardlink_to(source)
        value.update(candidate=str(alias),candidate_sha256=force._hash(alias))
    elif fault=='injected':value['current']=.1
    else:value['candidate']=str(tmp_path/'absent.kicad_pcb')
    with pytest.raises((AssertionError,ValueError,FileNotFoundError)):
        transaction.receive_phase(source,source,value,'actual-Source')


@pytest.mark.parametrize('kind',[FRONTIER,TAP])
@pytest.mark.parametrize('failed',[dict(ok=False,complete=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_refused_or_incomplete_public_owner_cannot_be_relabelled(tmp_path,monkeypatch,kind,failed):
    source,child,value=saved_row(tmp_path,kind)
    owner=transaction.sideband_monitor_tap if kind==TAP else transaction.connector_feedthrough
    name='receive'if kind==TAP else'receive_native_frontier'
    monkeypatch.setattr(owner,name,lambda *a,**k:copy.deepcopy(failed))
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,value,'actual-Source')


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('barrel',[False,True])
def test_native_frontier_phase_recompiles_source_access(tmp_path,monkeypatch,quarter,barrel):
    from test_source_connector_frontier import frontier_fixture
    source,hint,ids,child,access=frontier_fixture(tmp_path,monkeypatch,quarter=quarter,barrel=barrel,back=bool(quarter%2))
    value=row(pad_uuids=ids,access_uuids=access,candidate=str(child),candidate_sha256=force._hash(child))
    before=[p.read_bytes()for p in(source,child)]
    actual,proof=transaction.receive_phase(source,source,value,str(hint))
    assert actual==child and proof['ok']and proof['complete']
    assert proof['retained_native_frontier_contacts']['new_barrels']==0
    assert before==[p.read_bytes()for p in(source,child)]
    receipt=can_fixture();receipt['phases'][0]=dict(kind=FRONTIER,receiving=proof)
    described=scopes.received_repair_scope(receipt)
    assert described['Source_connector_native_frontier_additions_explicit']is True
    assert described['new_normal_monitor_vias']==0


def test_native_connector_phase_refuses_a_new_via(tmp_path,monkeypatch):
    from test_source_connector_frontier import frontier_fixture
    source,hint,ids,child,access=frontier_fixture(tmp_path,monkeypatch,child_fault='newvia')
    value=row(pad_uuids=ids,access_uuids=access,candidate=str(child),candidate_sha256=force._hash(child))
    with pytest.raises(AssertionError,match='only_authored_actual_channel_feedthrough_tracks'):
        transaction.receive_phase(source,source,value,str(hint))


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('planes',[False,True])
def test_native_monitor_phase_normal_vias_and_exact_ground_replay_are_distinct(tmp_path,monkeypatch,quarter,planes):
    from test_source_sideband_monitor_tap import fixture,child as make_child
    data=fixture(tmp_path,monkeypatch,quarter=quarter,mode='two_vias',planes=planes)
    source,hint,ids,target,*_=data;child=make_child(data,tmp_path)
    value=row(TAP,connector_pad_uuids=ids,target_pad_uuid=target,candidate=str(child),candidate_sha256=force._hash(child))
    before=[p.read_bytes()for p in(source,child)]
    actual,proof=transaction.receive_phase(source,source,value,str(hint))
    assert actual==child and proof['new_normal_vias']==2
    assert proof['exact_saved_additive_receiving']['existing_ground_fill_matches_independent_native_replay']is True
    assert len(proof['generated_Ground_fill_changes_requiring_independent_replay'])==(2 if planes else 0)
    assert before==[p.read_bytes()for p in(source,child)]
    report=can_fixture();report['phases'][0]=dict(kind=TAP,receiving=proof)
    described=scopes.received_repair_scope(report)
    assert described['new_normal_monitor_vias']==2
    assert described['new_current_or_Kelvin_or_barrel_or_voltage_qualification']is False


def channel(pair):
    return dict(requested_pad_uuids=list(pair),Source_numbering_remap_only=True,
                publisher_numeric_pin_map_claimed=False,current_authority=False)


def proof(kind=FRONTIER,pair=('first-land','second-land'),target='monitor-land'):
    value=dict(ok=True,complete=True,errors=[],whole_shared_stage_still_required=True,
        added_native_uuids=['new-track'],
        native_route_proposal_guard=dict(assessed=1,passed=1,refused=0,unknown=0,
            saved_native_or_whole_board_receiving_cached=False),
        exact_saved_additive_receiving=dict(ok=True,complete=True,added_native_uuids=['new-track'],
            existing_ground_fill_matches_independent_native_replay=True,replayed_ground_uuids=[]),
        whole_native_Source_partitions=dict(available=True,preserved=True),
        **{k:False for k in('ordinary_reclassification','quiet_reclassification','new_current_budget',
            'current_qualified','barrel_qualified','inherited_footprint_qualified','release_authority','routing_admitted')})
    if kind==FRONTIER:
        value.update(scope='Source_canonical_existing_native_frontier_sideband_feedthrough',
            source_components=3,candidate_components=2,only_requested_existing_Source_islands_joined=True,
            independently_compiled_Source_scope=channel(pair),
            retained_native_frontier_contacts=dict(complete=True,new_barrels=0,
                original_barrels_used_for_physical_access_only=True,
                every_old_native_partition_and_exact_Source_additive_receiving_required=True,
                old_barrel_capacity_credited=False,new_current_budget=False,current_qualified=False,
                barrel_qualified=False,release_authority=False,
                actual_contacts=[dict(source_access_uuid='access'+str(i),source_kind='PCB_TRACK',
                    source_connector_island_index=i,layer=0,positive_native_contact_nm2=100,
                    actual_drill_subtracted=False)for i in(0,1)]))
    else:
        value.update(scope='Source_typed_digital_sideband_monitor_tap',source_components=2,candidate_components=1,
            only_requested_monitor_island_joined=True,new_normal_vias=0,voltage_qualified=False,
            independently_compiled_Source_scope=dict(scope='Source_typed_digital_sideband_monitor_tap',
                connector_pad_uuids=list(pair),connector_channel=channel(pair),target_pad_uuid=target,
                retained_backbone_uuids=list(pair),current_authority=False,
                GPIO_application_mode_or_high_impedance_assumed=False),
            actual_front_monitor_contacts=[dict(uuid='new-track',area_nm2=100)],
            actual_Source_backbone_contacts=[dict(incoming_uuid='new-track',retained_uuid=pair[0],
                retained_class='PAD',layer=0,area_nm2=100)],
            generated_Ground_fill_changes_requiring_independent_replay=[])
    return value


def report(kind=FRONTIER):
    value=can_fixture();value['phases'][0]=dict(kind=kind,receiving=proof(kind));return value


def test_report_five_phase_cohort_never_becomes_ordinary_or_qualification():
    value=report();pairs=[('a','b'),('c','d')]
    value['phases']=[*[dict(kind=FRONTIER,receiving=proof(FRONTIER,p))for p in pairs],
        *[dict(kind=TAP,receiving=proof(TAP,p,'target'+str(i)))for i,p in enumerate(pairs)],value['phases'][-1]]
    before=copy.deepcopy(value);result=scopes.received_repair_scope(value)
    assert value==before and len(result['exact_received_Source_boundaries'])==4
    assert result['Source_connector_native_frontier_additions_explicit']
    assert result['Source_series_resistor_monitor_taps_explicit']
    assert result['all_actual_parent_gates_passed']
    assert not result['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not result['new_current_or_Kelvin_or_barrel_or_voltage_qualification']


@pytest.mark.parametrize('kind',[FRONTIER,TAP])
@pytest.mark.parametrize('fault',['wrong_scope','count_bool','no_progress','extra_copper','source_role',
    'new_current','qualified','no_additive','additive_ids','no_ground_replay','no_partition','unknown_guard',
    'cached','field_gate','current_gate','contact_gate','unreceived','extra_phase'])
def test_report_retains_every_independent_parent_and_saved_boundary_gate(kind,fault):
    value=report(kind);p=value['phases'][0]['receiving']
    if fault=='wrong_scope':p['scope']='ordinary'
    elif fault=='count_bool':p['candidate_components']=True
    elif fault=='no_progress':p['candidate_components']=p['source_components']
    elif fault=='extra_copper':p['added_native_uuids'].append('orphan')
    elif fault=='source_role':
        fresh=p['independently_compiled_Source_scope'];fresh=(fresh['connector_channel']if kind==TAP else fresh)
        fresh['current_authority']=True
    elif fault=='new_current':p['new_current_budget']=True
    elif fault=='qualified':p['barrel_qualified']=True
    elif fault=='no_additive':p['exact_saved_additive_receiving']['complete']=False
    elif fault=='additive_ids':p['exact_saved_additive_receiving']['added_native_uuids']=[]
    elif fault=='no_ground_replay':p['exact_saved_additive_receiving']['existing_ground_fill_matches_independent_native_replay']=False
    elif fault=='no_partition':p['whole_native_Source_partitions']['preserved']=False
    elif fault=='unknown_guard':p['native_route_proposal_guard']['unknown']=1
    elif fault=='cached':p['native_route_proposal_guard']['saved_native_or_whole_board_receiving_cached']=True
    elif fault in('field_gate','current_gate','contact_gate'):
        value['gates'][{'field_gate':'field','current_gate':'current','contact_gate':'contact_kelvin_preservation'}[fault]]=False
    elif fault=='unreceived':p['complete']=False
    else:value['phases'].insert(1,dict(kind='ordinary_join',receiving=dict(ok=True,complete=True)))
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


@pytest.mark.parametrize('fault',['newvia','capacity','incomplete','same_island','missing_access',
    'zero_contact','boolean_contact','nan_contact','hole','invented_pad','identity_conflict'])
def test_connector_frontier_report_requires_real_positive_two_island_access(fault):
    value=report();p=value['phases'][0]['receiving']['retained_native_frontier_contacts'];r=p['actual_contacts']
    if fault=='newvia':p['new_barrels']=1
    elif fault=='capacity':p['old_barrel_capacity_credited']=True
    elif fault=='incomplete':p['complete']=False
    elif fault=='same_island':r[1]['source_connector_island_index']=0
    elif fault=='missing_access':r.pop()
    elif fault in('zero_contact','boolean_contact','nan_contact'):
        r[0]['positive_native_contact_nm2']={'zero_contact':0,'boolean_contact':True,'nan_contact':float('nan')}[fault]
    elif fault=='hole':r[0].update(source_kind='PCB_VIA',actual_drill_subtracted=False)
    elif fault=='invented_pad':r[0].update(source_kind='PAD',actual_drill_subtracted=True)
    else:r.append(dict(r[0],source_connector_island_index=1))
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


@pytest.mark.parametrize('fault',['target_connector','backbone_target','pair_mismatch','gpio_mode','voltage',
    'via_bool','three_vias','zero_front','wrong_backbone','zero_backbone','unknown_ground','duplicate_ground'])
def test_monitor_report_never_borrows_gpio_or_ground_or_barrel_authority(fault):
    value=report(TAP);p=value['phases'][0]['receiving'];fresh=p['independently_compiled_Source_scope']
    if fault=='target_connector':fresh['target_pad_uuid']='first-land'
    elif fault=='backbone_target':fresh['retained_backbone_uuids'].append('monitor-land')
    elif fault=='pair_mismatch':fresh['connector_pad_uuids']=['x','y']
    elif fault=='gpio_mode':fresh['GPIO_application_mode_or_high_impedance_assumed']=True
    elif fault=='voltage':p['voltage_qualified']=True
    elif fault=='via_bool':p['new_normal_vias']=True
    elif fault=='three_vias':p['new_normal_vias']=3
    elif fault=='zero_front':p['actual_front_monitor_contacts'][0]['area_nm2']=0
    elif fault=='wrong_backbone':p['actual_Source_backbone_contacts'][0]['retained_uuid']='unknown'
    elif fault=='zero_backbone':p['actual_Source_backbone_contacts'][0]['area_nm2']=0
    elif fault=='unknown_ground':p['generated_Ground_fill_changes_requiring_independent_replay']=['unreplayed-zone']
    else:p['generated_Ground_fill_changes_requiring_independent_replay']=['zone','zone']
    with pytest.raises(ValueError):scopes.received_repair_scope(value)
