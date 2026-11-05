"""Input repair delegation derives actual native leg scope, never a waiver.

The native measurement receiver is real here. Print publication and the
absolute-evidence comparator are separate test boundaries; these consumer
tests make no whole-board or Kelvin qualification claim.
"""
import copy
import pcbnew
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_isolated_measurement_completion import case,child


def chain(tmp_path,monkeypatch,quarter=0):
    source,uid,target=case(tmp_path,monkeypatch,quarter)
    joined=child(source,tmp_path,uid,target)
    final=force._copy_family(joined,tmp_path/'printing')
    phases=[dict(kind='isolated_measurement_join',candidate=str(joined),
        candidate_sha256=force._hash(joined),pad_uuid=uid),
        dict(kind='print_context',candidate=str(final),candidate_sha256=force._hash(final),
            proposal=str(tmp_path/'print-boundary.json'))]
    real=transaction.receive_phase
    def receiving(original,parent,row,hint,**kw):
        if row['kind']!='print_context':return real(original,parent,row,hint,**kw)
        assert parent==joined and row['candidate']==str(final)
        assert parent.read_bytes()==final.read_bytes()
        return final,dict(ok=True,complete=True,scope='test_print_publication_boundary_only')
    monkeypatch.setattr(transaction,'receive_phase',receiving)
    return source,joined,final,phases


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('absolute_after',[False,True])
def test_fresh_native_leg_only_delegates_to_unchanged_absolute_after_comparator(tmp_path,monkeypatch,quarter,absolute_after):
    source,joined,final,phases=chain(tmp_path,monkeypatch,quarter)
    evidence=[dict(kind='raw_parent',unqualified=True),dict(kind='raw_child',unqualified_peer=True)]
    before=copy.deepcopy(evidence);files=[p.read_bytes()for p in(source,joined,final)];calls=[]
    def compare(*raw,**kw):
        assert list(raw)==before
        assert kw['repair_legs']==[('RENAMED_INPUT_DEVICE','p','FORCE_A')]
        assert kw['repair_nets']==['FORCE_A']and kw['modified_nets']==['FORCE_A']
        assert len(kw['native_copper_transforms'])==1
        assert kw['native_copper_transforms'][0]['net']=='FORCE_A'
        calls.append(kw)
        return dict(comparison_complete=True,same_evidence=absolute_after,
            full_kelvin_qualification=False,release_authority=False)
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',compare)
    q=transaction.isolated_measurement_contact_transition(source,final,phases,evidence,
        board_hint='RENAMED_SOURCE')
    assert len(calls)==1 and q['same_evidence']is absolute_after
    assert q['raw_parent_and_candidate_evidence_not_rewritten']
    assert q['actual_Source_derived_repair_legs']==[['RENAMED_INPUT_DEVICE','p','FORCE_A']]
    assert q['full_kelvin_qualification']is False
    assert evidence==before and [p.read_bytes()for p in(source,joined,final)]==files


@pytest.mark.parametrize('fault',['extra_leg','wrong_pad','wrong_endpoint','missing_print','unknown_phase'])
def test_no_caller_leg_scope_or_missing_saved_boundary(tmp_path,monkeypatch,fault):
    source,joined,final,phases=chain(tmp_path,monkeypatch)
    if fault=='extra_leg':phases[0]['repair_legs']=[['unowned','n','FORCE_B']]
    elif fault=='wrong_pad':phases[0]['pad_uuid']='unknown-input'
    elif fault=='wrong_endpoint':final=joined
    elif fault=='missing_print':phases.pop()
    else:phases.insert(0,dict(kind='ordinary_join',net='/ordinary',candidate='unknown',candidate_sha256='a'*64))
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',
        lambda *a,**kw:pytest.fail('No rejected scope may reach contact admission'))
    with pytest.raises((ValueError,AssertionError)):
        transaction.isolated_measurement_contact_transition(source,final,phases,[{},{}],board_hint='RENAMED_SOURCE')


def test_no_measurement_phase_never_changes_other_contact_comparators():
    phases=[dict(kind='ordinary_join',net='/actual/control',candidate='/actual/child',candidate_sha256='a'*64)]
    assert transaction.isolated_measurement_contact_transition('missing','missing',phases,[{},{}],board_hint='none')is None


@pytest.mark.parametrize('absolute_after',[False,True])
def test_cooperative_preclear_replays_both_scopes_then_real_input_before_absolute_comparison(
        tmp_path,monkeypatch,absolute_after):
    source,joined,final,phases=chain(tmp_path,monkeypatch)
    rated=force._copy_family(source,tmp_path/'rated-boundary')
    ordinary=force._copy_family(source,tmp_path/'ordinary-boundary')
    prefixes=[dict(kind='rated_branch',retired_track_uuids=['test-rated-boundary'],options={},
                   candidate=str(rated),candidate_sha256=force._hash(rated)),
              dict(kind='ordinary_reflow',net='/test/control',retired_track_uuids=['test-ordinary-boundary'],
                   candidate=str(ordinary),candidate_sha256=force._hash(ordinary))]
    real=transaction.receive_phase;calls=[]
    def receiving(original,parent,row,hint,**kw):
        calls.append(row['kind'])
        # Consumer-only boundaries: real rated/reflow physics have their own
        # native tests; no serialized success flag is an input to this API.
        if row['kind']in('rated_branch','ordinary_reflow'):
            return Path(row['candidate']),dict(ok=True,complete=True,
                scope='test_independent_public_preclear_receiver_boundary_only')
        return real(original,parent,row,hint,**kw)
    from pathlib import Path
    monkeypatch.setattr(transaction,'receive_phase',receiving)
    evidence=[dict(raw='before'),dict(raw='after')];saved=copy.deepcopy(evidence);seen=[]
    def compare(*raw,**kw):
        assert list(raw)==saved
        assert kw['repair_legs']==[('RENAMED_INPUT_DEVICE','p','FORCE_A')]
        seen.append(kw)
        return dict(comparison_complete=True,same_evidence=absolute_after,
                    full_kelvin_qualification=False,release_authority=False)
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',compare)
    result=transaction.isolated_measurement_contact_transition(source,final,prefixes+phases,evidence,
        board_hint='RENAMED_SOURCE')
    assert calls==['rated_branch','ordinary_reflow','isolated_measurement_join','print_context']
    assert len(seen)==1 and result['same_evidence']is absolute_after
    assert result['raw_parent_and_candidate_evidence_not_rewritten']and evidence==saved
