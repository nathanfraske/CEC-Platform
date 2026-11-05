"""Existing connector channel requests carry no caller role or current waiver."""
import copy
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
import root_received_goal_scope_20261024 as goal_scope
from test_source_connector_feedthrough import fixture,child
from test_received_goal_scope import can_fixture


def row(ids=('first-land','second-land'),candidate='/actual/child',**extra):
    return dict(kind='source_connector_feedthrough',pad_uuids=list(ids),
        candidate=candidate,candidate_sha256='a'*64,**extra)


def printing():
    return dict(kind='print_context',candidate='/actual/print',
        candidate_sha256='b'*64,proposal='/actual/proposal')


def test_distinct_existing_channels_keep_four_phase_budget():
    phases=[row(),row(('other-a','other-b'),'/actual/second'),
        row(('third-a','third-b'),'/actual/third'),printing()]
    assert transaction.validate_phases(phases)==['source_connector_feedthrough']*3+['print_context']


@pytest.mark.parametrize('fault',['repeat','reverse','after_print','too_many','net','width','current',
    'barrel','publisher_role','missing','single','same','none','boolean','string','empty'])
def test_only_exact_distinct_Source_land_requests(fault):
    phases=[row()]
    if fault=='repeat':phases.append(row(candidate='/actual/retry'))
    elif fault=='reverse':phases.append(row(('second-land','first-land'),'/actual/reverse'))
    elif fault=='after_print':phases=[printing(),row()]
    elif fault=='too_many':phases=[row((str(i)+'a',str(i)+'b'),'/actual/'+str(i))for i in range(transaction.MAX_LOCAL_PHASES+1)]
    elif fault in('net','width','current','barrel','publisher_role'):phases[0][fault]=True
    elif fault=='missing':phases[0].pop('pad_uuids')
    else:phases[0]['pad_uuids']={'single':['a'],'same':['a','a'],'none':None,
        'boolean':True,'string':'ab','empty':['a','']}[fault]
    with pytest.raises((ValueError,TypeError)):transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_transaction_recompiles_actual_saved_channel(tmp_path,monkeypatch,quarter,back):
    source,root,ids,_=fixture(tmp_path,monkeypatch,quarter,back);candidate=child(source,tmp_path,back)
    phase=row(ids,str(candidate));phase['candidate_sha256']=force._hash(candidate)
    before=[p.read_bytes()for p in(source,candidate)]
    assert transaction.validate_phases([phase])==['source_connector_feedthrough']
    actual,proof=transaction.receive_phase(source,source,phase,str(root))
    assert actual==candidate and proof['ok']and proof['complete'],proof
    assert (proof['source_components'],proof['candidate_components'])==(3,2)
    assert proof['whole_shared_stage_still_required']is True
    assert [p.read_bytes()for p in(source,candidate)]==before
    forged=copy.deepcopy(phase);forged['pad_uuids']=[ids[0],ids[0]]
    with pytest.raises(ValueError):transaction.validate_phases([forged])


def scoped_fixture():
    r=can_fixture();r['phases'][0]=dict(kind='source_connector_feedthrough',receiving=dict(
        ok=True,complete=True,scope='Source_canonical_existing_plated_sideband_feedthrough',errors=[],
        whole_shared_stage_still_required=True,source_components=3,candidate_components=2,
        only_requested_existing_Source_islands_joined=True,added_native_uuids=['new-track'],
        actual_flashed_annular_contacts=[{},{}],
        independently_compiled_Source_scope=dict(Source_numbering_remap_only=True,
            publisher_numeric_pin_map_claimed=False),
        native_route_proposal_guard=dict(assessed=1,passed=1,refused=0,unknown=0,
            saved_native_or_whole_board_receiving_cached=False),
        exact_saved_additive_receiving=dict(ok=True,complete=True),
        whole_native_Source_partitions=dict(available=True,preserved=True),
        **{k:False for k in('ordinary_reclassification','quiet_reclassification','new_current_budget',
            'current_qualified','barrel_qualified','inherited_footprint_qualified','release_authority','routing_admitted')}))
    return r


def test_ledger_scope_is_explicit_existing_channel_not_barrel_or_footprint_qualification():
    r=scoped_fixture();before=copy.deepcopy(r);result=goal_scope.received_repair_scope(r)
    assert r==before and result['Source_owned_existing_plated_sideband_additions_explicit']
    assert not result['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not result['new_barrel_current_or_footprint_qualification']


@pytest.mark.parametrize('fault',['count','boolean','no_additions','annular','publisher','ordinary','barrel',
    'no_native_guard','no_literal','lost_partition','shared_gate','extra_phase','incomplete'])
def test_ledger_cannot_hide_unreceived_or_reclassified_copper(fault):
    r=scoped_fixture();p=r['phases'][0]['receiving']
    if fault=='count':p['candidate_components']=3
    elif fault=='boolean':p['candidate_components']=True
    elif fault=='no_additions':p['added_native_uuids']=[]
    elif fault=='annular':p['actual_flashed_annular_contacts']=[]
    elif fault=='publisher':p['independently_compiled_Source_scope']['publisher_numeric_pin_map_claimed']=True
    elif fault=='ordinary':p['ordinary_reclassification']=True
    elif fault=='barrel':p['barrel_qualified']=True
    elif fault=='no_native_guard':p['native_route_proposal_guard']['passed']=0
    elif fault=='no_literal':p['exact_saved_additive_receiving']['complete']=False
    elif fault=='lost_partition':p['whole_native_Source_partitions']['preserved']=False
    elif fault=='shared_gate':r['gates']['native']=False
    elif fault=='extra_phase':r['phases'].insert(1,dict(kind='ordinary_join',receiving=dict(ok=True,complete=True)))
    else:p['complete']=False
    with pytest.raises(ValueError):goal_scope.received_repair_scope(r)
