"""Quiet fan-out is a strict typed phase, never arbitrary same-net routing."""
import copy
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_source_quiet_fanout import fixture,proposal,child


def row(root='source-input',peer='source-quiet-peer',candidate='/actual/child'):
    return dict(kind='measurement_quiet_fanout',pad_uuid=root,peer_pad_uuid=peer,
        candidate=candidate,candidate_sha256='a'*64)


@pytest.mark.parametrize('fault',['net','width','point','current','via','timeout','retirement',
    'missing_peer','same_peer','repeat','mixed_repeat','none','boolean','empty'])
def test_phase_cannot_supply_contact_role_geometry_or_repeat_budget(fault):
    phase=row();phases=[phase]
    extras=dict(net='/FORCE',width=1,point=[0,0],current=True,via=True,timeout=100,retirement=['unowned'])
    if fault in extras:phase[fault]=extras[fault]
    elif fault=='missing_peer':phase.pop('peer_pad_uuid')
    elif fault=='same_peer':phase['peer_pad_uuid']=phase['pad_uuid']
    elif fault=='repeat':phases.append(row(candidate='/actual/retry'))
    elif fault=='mixed_repeat':phases.append(dict(kind='isolated_measurement_join',pad_uuid=phase['pad_uuid'],
        candidate='/actual/retry',candidate_sha256='b'*64))
    else:phase['peer_pad_uuid']={'none':None,'boolean':True,'empty':''}[fault]
    with pytest.raises(ValueError):transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
def test_phase_independently_receives_actual_saved_source_quiet_tree(tmp_path,monkeypatch,quarter):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch,quarter)
    q=proposal(source,root,peer);assert q['complete'],q
    candidate=child(source,tmp_path,q)
    phase=row(root,peer,str(candidate));phase['candidate_sha256']=force._hash(candidate)
    assert transaction.validate_phases([phase])==['measurement_quiet_fanout']
    actual,proof=transaction.receive_phase(source,source,phase,'RENAMED_SOURCE')
    assert actual==candidate and proof['ok'] and proof['complete'],proof
    assert proof['exact_source_shunt_and_original_quiet_tree_retained']
    assert proof['saved_shared_quiet_tree']['exact_shunt_pad_uuid']==target
    assert not any(proof[k] for k in('routing_admitted','current_authority','kelvin_qualified','release_authority'))
    forged=copy.deepcopy(phase);forged['peer_pad_uuid']=target
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,forged,'RENAMED_SOURCE')


def test_nonmeasurement_phase_after_fanout_has_no_contact_transition_shortcut(tmp_path,monkeypatch):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch)
    phase=row(root,peer)
    ordinary=dict(kind='ordinary_reflow',net='actual-net',retired_track_uuids=['actual-source-track'],
        candidate='/actual/late-reflow',candidate_sha256='b'*64)
    printing=dict(kind='print_context',candidate='/actual/printed',candidate_sha256='c'*64,proposal='/actual/print-plan')
    with pytest.raises(ValueError):
        transaction.isolated_measurement_contact_transition(source,source,[phase,ordinary,printing],[],board_hint='RENAMED_SOURCE')


@pytest.mark.parametrize('whole_absolute',[False,True])
@pytest.mark.parametrize('comparison_pass',[False,True])
def test_shared_witness_changes_require_every_absolute_input_or_strict_peer_preservation(
        tmp_path,monkeypatch,whole_absolute,comparison_pass):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch)
    q=proposal(source,root,peer);joined=child(source,tmp_path,q)
    final=force._copy_family(joined,tmp_path/'print-boundary')
    phase=row(root,peer,str(joined));phase['candidate_sha256']=force._hash(joined)
    printing=dict(kind='print_context',candidate=str(final),candidate_sha256=force._hash(final),proposal='/test/print-boundary')
    actual=transaction.receive_phase
    def received(original,parent,phase,hint,**kw):
        if phase['kind']!='print_context':return actual(original,parent,phase,hint,**kw)
        assert parent==joined and final.read_bytes()==joined.read_bytes()
        return final,dict(ok=True,complete=True,scope='test_print_publication_boundary_only')
    monkeypatch.setattr(transaction,'receive_phase',received)
    raw=[dict(raw='unqualified_source_report'),dict(raw='unqualified_child_report')]
    before=copy.deepcopy(raw);seen=[]
    def absolute(first,last,net):
        assert [first,last]==before and net=='FORCE_A'
        return dict(ok=whole_absolute,applicable=True,checked=2 if whole_absolute else 1,
            expected_legs=[['first','p'],['second','p']])
    def compared(*reports,**kw):
        assert list(reports)==before
        assert kw['repair_legs']==(None if whole_absolute else[('RENAMED_INPUT_DEVICE','p','FORCE_A')])
        seen.append(kw)
        return dict(comparison_complete=True,same_evidence=comparison_pass,
            full_kelvin_qualification=False,release_authority=False)
    monkeypatch.setattr(transaction.sense,'admit_changed_net',absolute)
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',compared)
    result=transaction.isolated_measurement_contact_transition(source,final,[phase,printing],raw,board_hint='RENAMED_SOURCE')
    assert len(seen)==1 and result['same_evidence']is comparison_pass
    assert result['derived_input_scope']==('absolutely_verified_whole_cohorts'if whole_absolute else'newly_connected_legs_only')
    assert result['raw_parent_and_candidate_evidence_not_rewritten']and raw==before
