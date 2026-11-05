"""Typed consumers preserve public receiving and raw absolute evidence."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_monitor_divider_ground_return import fixture as ground_fixture
from test_quiet_input_pad_cleanup import fixture as cleanup_fixture


def phase(kind, **values):
    return dict(kind=kind,candidate='/explicit/private/child',candidate_sha256='a'*64,**values)


def chain():
    return [phase('quiet_input_pad_cleanup',input_pad_uuid='actual-input',peer_pad_uuid='actual-peer'),
        phase('measurement_quiet_fanout',pad_uuid='actual-input',peer_pad_uuid='actual-peer'),
        phase('print_context',proposal='/explicit/print-proposal')]


@pytest.mark.parametrize('kind',['monitor_divider_ground_return','quiet_input_pad_cleanup'])
@pytest.mark.parametrize('extra',['net','width_nm','current','retired_track_uuids','allow_owned_locked','timeout_s'])
def test_identity_only_stage_schema_has_no_caller_authority(kind,extra):
    rows=chain() if kind=='quiet_input_pad_cleanup' else [phase(kind,pad_uuid='actual-return')]
    rows[0][extra]=True
    with pytest.raises(ValueError):transaction.validate_phases(rows)


@pytest.mark.parametrize('fault',['missing_fanout','intervening_reflow','wrong_input','wrong_peer',
    'cleanup_after_fanout','repeat','same_input_peer'])
def test_cleanup_cannot_authorize_unrelated_later_input_or_a_free_standing_cut(fault):
    rows=chain()
    if fault=='missing_fanout':rows.pop(1)
    elif fault=='intervening_reflow':rows.insert(1,phase('ordinary_reflow',net='/control',retired_track_uuids=['old']))
    elif fault=='wrong_input':rows[1]['pad_uuid']='other-input'
    elif fault=='wrong_peer':rows[1]['peer_pad_uuid']='other-peer'
    elif fault=='cleanup_after_fanout':rows[0],rows[1]=rows[1],rows[0]
    elif fault=='repeat':rows.insert(0,copy.deepcopy(rows[0]))
    else:rows[0]['peer_pad_uuid']=rows[0]['input_pad_uuid']
    with pytest.raises(ValueError):transaction.validate_phases(rows)


@pytest.mark.parametrize('bottom',[False,True])
def test_monitor_dispatch_calls_real_independent_saved_receiver(tmp_path,monkeypatch,bottom):
    source,uid=ground_fixture(tmp_path,monkeypatch,bottom=bottom)
    q=transaction.monitor_ground.plan(source,board_hint='renamed-source',ground_pad_uuid=uid)
    made=transaction.monitor_ground.construct_private(source,q,tmp_path/'private')
    candidate=Path(made['candidate'])
    row=dict(kind='monitor_divider_ground_return',pad_uuid=uid,candidate=str(candidate),candidate_sha256=force._hash(candidate))
    assert transaction.validate_phases([row])==['monitor_divider_ground_return']
    actual,proof=transaction.receive_phase(source,source,row,'renamed-source')
    assert actual==candidate and proof['ok'] and proof['complete']
    assert proof['physical']['child_ground_components']==proof['physical']['source_ground_components']-1
    assert not proof['routing_admitted'] and not proof['current_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('quarter',range(4))
def test_cleanup_dispatch_calls_real_native_union_receiver(tmp_path,monkeypatch,quarter):
    board,_,source,args=cleanup_fixture(tmp_path,monkeypatch,quarter)
    q=transaction.quiet_pad_cleanup.plan(board,source,**args)
    child=force._copy_family(source,tmp_path/'private')
    transaction.quiet_pad_cleanup.construct_private(source,child,q)
    row=dict(kind='quiet_input_pad_cleanup',input_pad_uuid=args['input_pad_uuid'],peer_pad_uuid=args['peer_pad_uuid'],
        candidate=str(child),candidate_sha256=force._hash(child))
    actual,proof=transaction.receive_phase(source,source,row,args['board_hint'])
    assert actual==child and proof['ok'] and proof['complete']
    assert proof['physical_copper_union_unchanged'] is True
    assert proof['current_authority'] is proof['electrical_retirement_authority'] is False


@pytest.mark.parametrize('absolute_pass',[False,True])
def test_cleanup_owns_no_repair_leg_and_never_rewrites_raw_absolute_packets(tmp_path,monkeypatch,absolute_pass):
    board,_,source,args=cleanup_fixture(tmp_path,monkeypatch)
    q=transaction.quiet_pad_cleanup.plan(board,source,**args)
    cleaned=force._copy_family(source,tmp_path/'cleaned')
    transaction.quiet_pad_cleanup.construct_private(source,cleaned,q)
    joined=force._copy_family(cleaned,tmp_path/'test-fanout-boundary')
    final=force._copy_family(joined,tmp_path/'test-print-boundary')
    rows=[dict(kind='quiet_input_pad_cleanup',input_pad_uuid=args['input_pad_uuid'],peer_pad_uuid=args['peer_pad_uuid'],
            candidate=str(cleaned),candidate_sha256=force._hash(cleaned)),
        dict(kind='measurement_quiet_fanout',pad_uuid=args['input_pad_uuid'],peer_pad_uuid=args['peer_pad_uuid'],
            candidate=str(joined),candidate_sha256=force._hash(joined)),
        dict(kind='print_context',proposal='/test/print',candidate=str(final),candidate_sha256=force._hash(final))]
    real=transaction.receive_phase;calls=[]
    def receive(original,parent,row,hint,**kwargs):
        calls.append(row['kind'])
        if row['kind']=='quiet_input_pad_cleanup':return real(original,parent,row,hint,**kwargs)
        if row['kind']=='print_context':return final,dict(ok=True,complete=True)
        # Consumer boundary ONLY: the actual fanout receiver and canonical
        # role compiler have separate native tests. This is not admission.
        demand=dict(pad_uuid=args['input_pad_uuid'],net='actual-quiet-net',source_segment=dict(
            net='actual-quiet-net',leg='n',start=dict(ref='fresh-manufacturer-input')))
        return joined,dict(ok=True,complete=True,exact_source_shunt_and_original_quiet_tree_retained=True,
            independently_compiled_source_scope=dict(complete=True,peer_pad_uuid=args['peer_pad_uuid'],
                source_request=dict(complete=True,pad_uuid=args['input_pad_uuid'],request=dict(demand=demand))))
    monkeypatch.setattr(transaction,'receive_phase',receive)
    raw=[dict(raw='unaltered-parent',unknown=True),dict(raw='unaltered-final',unknown=True)];before=copy.deepcopy(raw);seen=[]
    def compare(first,last,legs,modified,manifest):
        assert [first,last]==before
        assert legs==[('fresh-manufacturer-input','n','actual-quiet-net')]
        seen.append((modified,manifest))
        return dict(comparison_complete=True,same_evidence=absolute_pass,full_kelvin_qualification=False,release_authority=False)
    monkeypatch.setattr(transaction.received_contact,'_compare_input_repairs',compare)
    result=transaction.isolated_measurement_contact_transition(source,final,rows,raw,board_hint=args['board_hint'])
    assert calls==['quiet_input_pad_cleanup','measurement_quiet_fanout','print_context']
    assert len(seen)==1 and result['same_evidence'] is absolute_pass and raw==before
    assert result['actual_Source_derived_repair_legs']==[['fresh-manufacturer-input','n','actual-quiet-net']]
    assert result['raw_parent_and_candidate_evidence_not_rewritten']
