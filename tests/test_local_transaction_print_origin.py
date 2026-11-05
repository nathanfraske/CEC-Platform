"""Explicit origin replay dispatch, never an old print grade or qualification.

Dispatch-only spies below test argument selection, not hardware acceptance.
The native-family case runs real print planning, construction and complete
fresh-origin family replay; only its synthetic config/identity catalog is
provided, and all original-parent receiving gates remain mandatory.
"""
import copy
import json
from pathlib import Path
import types

import pytest

import cec_force_current as force
import cec_chained_annotation_transition as origin
import cec_native_library_context as libraries
import cec_nonpolar_print_context as printing
import cec_received_private_stage as stage
import cec_synth_pipeline as synth
import root_receive_local_transaction_20261022 as transaction


def phase(**extra):
    return dict(kind='print_context',candidate='/actual/print.kicad_pcb',candidate_sha256='a'*64,
                proposal='/actual/print-proposal.json',**extra)


@pytest.mark.parametrize('value',[False,True])
def test_origin_replay_is_one_explicit_boolean_not_context_authority(value):
    assert transaction.validate_phases([phase(replay_origin=value)])==['print_context']


@pytest.mark.parametrize('value',[None,0,1,'true',[],{},float('nan')])
def test_nonboolean_replay_policy_is_refused(value):
    with pytest.raises(ValueError): transaction.validate_phases([phase(replay_origin=value)])


@pytest.mark.parametrize('key',['new_context','old_context','authority','receiving','ok','timeout_s',
    'grade','library_table','assembly_instance','allow_stale_source'])
def test_opt_in_does_not_admit_context_grade_or_work_overrides(key):
    row=phase(replay_origin=True);row[key]=True
    with pytest.raises(ValueError): transaction.validate_phases([row])


def test_six_phase_cap_and_print_last_are_unchanged():
    rows=[dict(kind='ordinary_join',net='/n'+str(i),candidate='/actual/'+str(i),
               candidate_sha256='b'*64) for i in range(5)]+[phase(replay_origin=True)]
    assert transaction.MAX_LOCAL_PHASES==6
    assert transaction.validate_phases(rows)==['ordinary_join']*5+['print_context']
    with pytest.raises(ValueError): transaction.validate_phases(rows+[phase()])
    with pytest.raises(ValueError): transaction.validate_phases([phase(replay_origin=True),rows[0]])
    with pytest.raises(ValueError): transaction.validate_phases([phase(),phase(replay_origin=True)])


@pytest.mark.parametrize('value',[False,True])
def test_print_replay_flag_does_not_extend_nonprint_operators(value):
    row=dict(kind='ordinary_join',net='/N',candidate='/actual/ordinary',candidate_sha256='a'*64,
             replay_origin=value)
    with pytest.raises(ValueError): transaction.validate_phases([row])


def dispatch_files(tmp_path,replay):
    original=tmp_path/'original.kicad_pcb';parent=tmp_path/'actual-parent.kicad_pcb'
    child=tmp_path/'actual-print.kicad_pcb';proposal=tmp_path/'proposal.json'
    for path in (original,parent,child): path.write_text(path.name)
    proposal.write_text(json.dumps(dict(board_hint='fixture')))
    row=dict(phase(),candidate=str(child),candidate_sha256=force._hash(child),proposal=str(proposal))
    if replay is not None: row['replay_origin']=replay
    return original,parent,child,proposal,row


@pytest.mark.parametrize('replay',[None,False,True])
def test_initial_postnative_and_final_helpers_choose_same_public_api_and_comparer(tmp_path,monkeypatch,replay):
    original,parent,child,proposal,row=dispatch_files(tmp_path,replay)
    transaction.print_dependencies();calls=[];compares=[]
    # Dispatch contract only. This deliberately has no hardware-grade claim.
    report=dict(ok=True,complete=True,scope_only=True,admitted=False,release_authority=False)
    def receive(label):
        def call(*args,**kwargs): calls.append((label,args,kwargs));return copy.deepcopy(report)
        return call
    monkeypatch.setattr(transaction.print_transition,'receive_row',receive('direct'))
    monkeypatch.setattr(transaction.print_origin,'receive_print_row',receive('origin'))
    def compare(label):
        def call(left,right): compares.append((label,left,right));return left==right
        return call
    monkeypatch.setattr(transaction.print_transition,'same_replay',compare('direct'))
    monkeypatch.setattr(transaction.print_origin,'same_print_replay',compare('origin'))
    instance={'role':'actual-parent-instance'}
    selected,first=transaction.receive_phase(original,parent,row,'fixture',assembly_instance=instance)
    assert selected==child
    for _ in range(2):
        live=transaction.receive_print_phase(parent,row,'fixture',instance)
        assert transaction.same_print_phase(live,first,row)
    label='origin' if replay is True else 'direct'
    declaration=dict(source=dict(path=str(parent),sha256=force._hash(parent)),
        proposal=dict(path=str(proposal),sha256=force._hash(proposal)))
    assert calls==[(label,(child,declaration),dict(board_hint='fixture',assembly_instance=instance,timeout_s=10.))]*3
    assert [r[0] for r in compares]==[label,label]


@pytest.mark.parametrize('replay',[False,True])
@pytest.mark.parametrize('refusal',[dict(ok=False,complete=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_public_refusal_or_incomplete_print_cannot_be_relabelled(tmp_path,monkeypatch,replay,refusal):
    original,parent,child,proposal,row=dispatch_files(tmp_path,replay)
    transaction.print_dependencies()
    module=transaction.print_origin if replay else transaction.print_transition
    name='receive_print_row' if replay else 'receive_row'
    monkeypatch.setattr(module,name,lambda *a,**kw:copy.deepcopy(refusal))
    with pytest.raises(AssertionError): transaction.receive_phase(original,parent,row,'fixture')


def native_family(tmp_path,monkeypatch):
    from test_nonpolar_print_context import fixture,planned
    source,table,ids,_library=fixture(tmp_path,monkeypatch,turn=90,back=True)
    proposal=planned(source,table,ids)
    artifact=printing.construct_private(source,proposal,tmp_path/'actual-native-print')
    child=Path(artifact['candidate']);qpath=child.parent/'print-proposal.json'
    # No suite-wide audit is claimed by this fixture. Both identity contexts
    # are derived from the actual native table, never a caller context blob.
    monkeypatch.setattr(synth.Config,'load',lambda hint:types.SimpleNamespace(dir=source.parent))
    def identity(path,hint,instance):
        return dict(source=str(Path(path).resolve()),assembly=instance,
            native_library_authority=stage.stable(libraries.authority(path,table)))
    monkeypatch.setattr(stage,'identity',identity)
    row=dict(phase(replay_origin=True),candidate=str(child),candidate_sha256=force._hash(child),proposal=str(qpath))
    return source,child,row


def test_real_native_origin_is_replanned_and_complete_saved_family_reconstructed(tmp_path,monkeypatch):
    source,child,row=native_family(tmp_path,monkeypatch)
    before={str(p):p.read_bytes() for root in (source.parent,child.parent) for p in root.rglob('*') if p.is_file()}
    selected,proof=transaction.receive_phase(source,source,row,'renamed')
    assert selected==child and proof['ok']is True and proof['complete']is True,proof
    assert proof['independent_origin_recompiled'] and proof['all_original_selected_parent_gates_still_required']
    assert not proof['admitted'] and not proof['release_authority'] and not proof['full_kelvin_qualification']
    assert proof['bounded_composition']['per_constituent_limit_s']==10.
    assert set(proof['timings_s'])=={'origin_plan','origin_construct','origin_compare','identity_live'}
    assert all(0<=value<10. for value in proof['timings_s'].values())
    assert before=={str(p):p.read_bytes() for root in (source.parent,child.parent) for p in root.rglob('*') if p.is_file()}
    assert transaction.same_print_phase(proof,copy.deepcopy(proof),row)
    forged=copy.deepcopy(proof);forged['new_library_context']={'caller':'authority'}
    assert not transaction.same_print_phase(proof,forged,row)
    slow=copy.deepcopy(proof);slow['timings_s']['origin_plan']=10.
    assert not transaction.same_print_phase(proof,slow,row)


@pytest.mark.parametrize('fault',['metadata','proposal','physical_family','wrong_parent'])
def test_real_origin_replay_refuses_forged_context_or_inexact_family(tmp_path,monkeypatch,fault):
    source,child,row=native_family(tmp_path,monkeypatch)
    parent=source
    if fault=='metadata': (child.parent/'print-context.json').write_text('{}')
    elif fault=='proposal':
        proposal=Path(row['proposal']);value=json.loads(proposal.read_text())
        value['old_library_context']={'forged':'context'};proposal.write_text(json.dumps(value))
    elif fault=='physical_family': (child.parent/'unowned-file.txt').write_text('not an exact Source print descendant')
    else:
        parent=tmp_path/'wrong-parent.kicad_pcb';parent.write_text('not the actual origin')
    with pytest.raises(AssertionError): transaction.receive_phase(source,parent,row,'renamed')
