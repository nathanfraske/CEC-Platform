"""A strict RC phase rederives the saved operator, never a worker receipt."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rc_return_pivot_receiving as receiving
import root_receive_local_transaction_20261022 as transaction
from test_rc_return_pivot import fixture


def phase(candidate):
    return dict(kind='rc_return_pivot',candidate=str(candidate),candidate_sha256=force._hash(candidate))


@pytest.mark.parametrize('rotation,back,ref',[(0,False,'FILTER_X'),(90,False,'ARBITRARY_RC'),
    (180,True,'RENAMED_RETURN'),(270,True,'OTHER_FILTER')])
def test_actual_saved_rc_phase_freshly_rederives_public_source_operator(tmp_path,monkeypatch,rotation,back,ref):
    source,candidate,_=fixture(tmp_path,rotation=rotation,back=back,ref=ref)
    row=phase(candidate);assert transaction.validate_phases([row])==['rc_return_pivot']
    before=[p.read_bytes()for p in(source,candidate)];calls=[];original=receiving.receive
    def fresh(parent,child,**options):
        calls.append((Path(parent),Path(child),dict(options)))
        return original(parent,child,**options)
    monkeypatch.setattr(receiving,'receive',fresh)
    child,result=transaction.receive_phase(source,source,row,'synthetic')
    assert child==candidate.resolve()and result['ok']and result['complete']and result['errors']==[]
    assert calls==[(source,candidate.resolve(),dict(board_hint='synthetic',timeout_s=10.))]
    assert result['source_opens']==1 and result['opens']==0
    assert len(result['pivots'])==1 and result['pivots'][0]['ref']==ref
    assert result['pivots'][0]['uuid']==force._uid(pcbnew.LoadBoard(str(source)).FindFootprintByReference(ref))
    assert result['original_native_conductor_and_terminal_partitions_preserved']
    assert result['independent_pose_and_additive_replay']['ok']
    assert not result['power_authority']and not result['release_authority']and not result['placement_authority_transferred']
    assert before==[p.read_bytes()for p in(source,candidate)]


@pytest.mark.parametrize('key,value',[('owner_uuid','invented'),('pad_uuid','invented'),
    ('role','ordinary'),('budget_a',.001),('return_reach_mm',10.),('timeout_s',30.),
    ('receipt',{'ok':True,'complete':True}),('power_authority',True),('options',{})])
def test_no_external_role_owner_budget_reach_or_success_flag_in_rc_phase(key,value):
    row=dict(kind='rc_return_pivot',candidate='/actual/saved/board.kicad_pcb',candidate_sha256='a'*64)
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([dict(row,**{key:value})])


def test_repeated_source_owner_requires_a_new_independent_transaction(tmp_path):
    source,candidate,ref=fixture(tmp_path);row=phase(candidate)
    assert ref==pcbnew.LoadBoard(str(source)).FindFootprintByReference(ref).GetReference()
    with pytest.raises(ValueError,match='repeated_local_operator'):
        transaction.validate_phases([row,dict(row)])


def test_rc_phase_cannot_follow_print_or_exceed_explicit_phase_cap():
    pivot=dict(kind='rc_return_pivot',candidate='/saved/rc',candidate_sha256='a'*64)
    printed=dict(kind='print_context',candidate='/saved/print',candidate_sha256='b'*64,proposal='/saved/proposal.json')
    with pytest.raises(ValueError,match='typed_print_context_must_be_last'):
        transaction.validate_phases([printed,pivot])
    joined=[dict(kind='ordinary_join',net='/unrelated_'+str(i),candidate='/saved/'+str(i),candidate_sha256='c'*64)for i in range(transaction.MAX_LOCAL_PHASES)]
    assert transaction.validate_phases([*joined[:3],pivot])==['ordinary_join']*3+['rc_return_pivot']
    with pytest.raises(ValueError,match='finite_one_to_six'):
        transaction.validate_phases([*joined,pivot])


@pytest.mark.parametrize('fault',['anchor','part','old_copper','rule','source_connected_ground'])
def test_saved_rc_phase_does_not_trust_old_success_receipt(tmp_path,fault):
    source,candidate,ref=fixture(tmp_path)
    prior=receiving.receive(source,candidate,board_hint='synthetic')
    assert prior['ok']and prior['complete']
    if fault=='rule':candidate.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "unsafe" (constraint clearance (min 0mm)))\n')
    else:
        path=source if fault=='source_connected_ground'else candidate
        board=pcbnew.LoadBoard(str(path));fp=board.FindFootprintByReference(ref)
        if fault=='anchor':fp.Move(pcbnew.VECTOR2I_MM(.01,0))
        elif fault=='part':fp.SetValue('10nF')
        elif fault=='old_copper':next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK').SetWidth(250000)
        else:
            from test_field_proposals import track
            p=fp.FindPadByNumber('2');track(board,'GND',(p.GetPosition().x/1e6,p.GetPosition().y/1e6),(10,15))
        field._save_field_snapshot(board,path)
    # Rebind only the actual saved hash: an earlier true receipt is never an
    # input and cannot authorize the now-mutated Source or child geometry.
    row=phase(candidate)
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,row,'synthetic')


def test_rc_phase_hash_is_the_actual_saved_boundary(tmp_path):
    source,candidate,_=fixture(tmp_path);row=phase(candidate);row['candidate_sha256']='0'*64
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,row,'synthetic')


def test_connector_feedthrough_schema_survives_rc_registration():
    row=dict(kind='source_connector_feedthrough',candidate='/saved/connector',candidate_sha256='a'*64,pad_uuids=['source-a','source-b'])
    assert transaction.validate_phases([row])==['source_connector_feedthrough']
