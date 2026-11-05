"""Exact Ground-link dispatch; no new contact/current/qualification scope."""
import copy
import uuid
from pathlib import Path

import pcbnew
import pytest

from test_local_transaction_receiver import op
from test_redundant_source_ground_link import saved
from test_bounded_macro_contact_chain import chain, wire, described_chain
from test_received_goal_scope import fixture as described_single
import root_received_goal_scope_20261024 as scope


KIND='redundant_source_ground_link'
LIMITS=(10.,10.,10.,10.)


def row(ids=None, candidate='/explicit/link.kicad_pcb', digest='a'*64):
    return dict(kind=KIND,candidate=str(candidate),candidate_sha256=digest,
        track_uuids=[str(uuid.uuid4())]if ids is None else ids)


def printing():
    return dict(kind='print_context',candidate='/explicit/print.kicad_pcb',
        candidate_sha256='f'*64,proposal='/explicit/print.json')


@pytest.mark.parametrize('ids',[None,True,False,'uuid',{},(),set(),[],[True],[False],[''],
    [' leading'],['trailing '],['x\n'],['x'*129],['same','same'],['x']*9])
def test_only_bounded_distinct_literal_track_list_is_accepted(ids):
    value=row();value['track_uuids']=ids
    with pytest.raises(ValueError):op.validate_phases([value])


@pytest.mark.parametrize('key',['timeout_s','receiving_phase_timeouts_s','proposal','proof',
    'callback','width','current','net','board_hint','allow_locked_track_uuids',
    'source_authority','source_family','release_authority','window','skip_returns'])
def test_no_caller_authority_or_lease_override(key):
    value=dict(row(),**{key:True})
    with pytest.raises(ValueError,match='schema'):
        op.validate_phases([value])
    with pytest.raises(ValueError,match='schema'):
        op.receive_phase(Path('/not/read'),Path('/not/read'),value,'synthetic')


def test_disjoint_links_keep_six_phase_cap_and_print_last():
    assert op.validate_phases([row([str(uuid.uuid4())for _ in range(8)])])==[KIND]
    values=[row()for _ in range(5)]+[printing()]
    assert op.validate_phases(values)==[KIND]*5+['print_context']
    assert op.MAX_LOCAL_PHASES==6
    with pytest.raises(ValueError):op.validate_phases(values+[row()])
    with pytest.raises(ValueError):op.validate_phases([printing(),row()])
    with pytest.raises(ValueError,match='disjoint'):
        op.validate_phases([row(['same']),row(['same'])])
    with pytest.raises(ValueError,match='disjoint'):
        op.validate_phases([row(['a','b']),row(['c','b'])])


@pytest.mark.parametrize('other_kind',['full_current_planar_reflow','ordinary_reflow',
    'source_rc_elbow_reflow','source_local_bypass_return',
    'source_ground_land_root_spur','source_ground_literal_endpoint_tail'])
@pytest.mark.parametrize('reverse',[False,True])
def test_link_never_repeats_other_declared_cut_seed_or_span(other_kind,reverse):
    other=dict(kind=other_kind,candidate='/explicit/other.kicad_pcb',candidate_sha256='b'*64)
    if other_kind=='source_rc_elbow_reflow':
        other.update(pad_uuid='pad',span_uuids=['same','other1','other2'])
    elif other_kind=='source_local_bypass_return':
        other.update(pad_uuid='pad',track_uuid='same')
    elif other_kind.startswith('source_ground_'):
        other.update(seed_uuid='same',allow_locked_track_uuids=[])
    else:
        other['retired_track_uuids']=['same']
        if other_kind=='ordinary_reflow':other['net']='SOURCE_ORDINARY'
    rows=[row(['same']),other]
    if reverse:rows.reverse()
    with pytest.raises(ValueError,match='disjoint'):
        op.validate_phases(rows)


@pytest.mark.parametrize('quarter',[0,1])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_public_dispatch_rederives_real_saved_native_link(tmp_path,monkeypatch,quarter,face):
    source,child,args,proposal,context=saved(tmp_path,quarter=quarter,face=face)
    value=row(args['track_uuids'],child,op.force._hash(child))
    assert op.validate_phases([value])==[KIND]
    actual=op.redundant_ground_link.receive;calls=[]
    def observed(*positional,**kwargs):
        calls.append((positional,copy.deepcopy(kwargs)))
        return actual(*positional,**kwargs)
    monkeypatch.setattr(op.redundant_ground_link,'receive',observed)
    before=source.read_bytes(),child.read_bytes()
    selected,proof=op.receive_phase(source,source,value,'synthetic')
    assert selected==child and proof['ok']and proof['complete'],proof
    assert calls==[((source,child),dict(board_hint='synthetic',track_uuids=args['track_uuids'],
        timeout_s=10.,receiving_phase_timeouts_s=LIMITS))]
    assert proof['retired_track_uuids']==sorted(args['track_uuids'])
    assert proof['exact_opaque_Source_subtraction']and proof['exact_native_Source_subtraction']
    assert proof['every_Source_native_partition_preserved']
    assert proof['all_Source_known_return_witnesses_preserved']
    assert proof['bounded_composition']['stage_limits_s']==list(LIMITS)
    assert all(0<=v<10 for v in proof['stage_timings_s'].values())
    assert not proof['current_qualified']and not proof['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('samefile',[False,True])
def test_same_source_and_hardlink_are_not_saved_boundaries(tmp_path,monkeypatch,samefile):
    source=tmp_path/'source.kicad_pcb';source.write_text('unchanged Source')
    child=source
    if samefile:
        child=tmp_path/'alias.kicad_pcb';child.hardlink_to(source)
    calls=[]
    monkeypatch.setattr(op.redundant_ground_link,'receive',lambda *a,**kw:calls.append(kw))
    with pytest.raises((ValueError,AssertionError)):
        op.receive_phase(source,source,row(['id'],child,op.force._hash(child)),'synthetic')
    assert not calls


def test_wrong_saved_child_hash_stops_before_public_receiver(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    calls=[]
    monkeypatch.setattr(op.redundant_ground_link,'receive',lambda *a,**kw:calls.append(kw))
    with pytest.raises(AssertionError):
        op.receive_phase(source,source,row(['id'],child,'0'*64),'synthetic')
    assert not calls


@pytest.mark.parametrize('complete',[False,True])
def test_refused_or_incomplete_public_receiving_never_passes(tmp_path,monkeypatch,complete):
    source=tmp_path/'source.kicad_pcb';source.write_text('Source')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    monkeypatch.setattr(op.redundant_ground_link,'receive',
        lambda *a,**kw:dict(ok=not complete,complete=complete))
    with pytest.raises(AssertionError):
        op.receive_phase(source,source,row(['id'],child,op.force._hash(child)),'synthetic')


def test_actual_unowned_saved_delta_is_not_dispatched_as_received(tmp_path):
    source,child,args,proposal,context=saved(tmp_path)
    child.write_text(child.read_text().replace('(width 0.5)','(width 0.49)',1))
    with pytest.raises(AssertionError):
        op.receive_phase(source,source,row(args['track_uuids'],child,op.force._hash(child)),'synthetic')


@pytest.mark.parametrize('position',['prefix','suffix','both'])
@pytest.mark.parametrize('fault',[None,'typed','original_raw','final_raw','middle_raw'])
def test_two_macro_chain_keeps_typed_link_and_all_strict_raw_links(tmp_path,monkeypatch,position,fault):
    files,rows=chain(tmp_path,prefix=True)
    if position in('prefix','both'):rows[0]=row(['prefix-cut'],files['prefix'],op.force._hash(files['prefix']))
    if position in('suffix','both'):rows[3]=row(['suffix-cut'],files['cleanup'],op.force._hash(files['cleanup']))
    wire_fault='typed_'+KIND if fault=='typed'else'intermediate_raw'if fault=='middle_raw'else None
    raw,calls=wire(monkeypatch,files,fault=wire_fault)
    evidence=[copy.deepcopy(raw['prefix']),copy.deepcopy(raw['two'])]
    if fault=='original_raw':evidence[0]['native']='unowned-original-debt'
    if fault=='final_raw':evidence[1]['native']='unowned-final-debt'
    if fault=='typed':
        with pytest.raises(ValueError,match='fresh_exact_typed'):
            op.complete_macro_contact_transition(files['source'],files['final'],rows,evidence,board_hint='RENAMED')
    else:
        result=op.complete_macro_contact_transition(files['source'],files['final'],rows,evidence,board_hint='RENAMED')
        assert result['same_evidence']is(fault is None),result
        if fault is None:
            typed=[c for c in calls if c[0]=='typed'and c[1]==KIND]
            assert len(typed)==(2 if position=='both'else 1)
            assert len([c for c in calls if c[0]=='strict'])==3
            assert result['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']
            assert not result['full_kelvin_qualification']and not result['release_authority']


def described(position,macros):
    receipt=described_single()if macros==1 else described_chain()
    if position=='prefix':
        phase=dict(kind=KIND,candidate='prefix',candidate_sha256='prefix-sha',receiving=dict(ok=True,complete=True))
        receipt['phases'].insert(0,phase)
        relation=receipt['reports']['clipped']
        relation.update(independently_received_prefix_phases=[copy.deepcopy(phase)],
            actual_macro_parent='prefix',macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True)
        if macros==2:
            entry=relation['macro_boundaries'][0]
            entry.update(source='prefix',source_sha256='prefix-sha')
            for proof in (receipt['phases'][1]['receiving'],entry['macro']['saved_macro_receiving']):
                proof.update(source_sha256='prefix-sha',source_macro_packet=dict(source='prefix',source_sha256='prefix-sha'))
            for entry in relation['macro_boundaries']:entry['phase_index']+=1
    else:
        phase=dict(kind=KIND,candidate='cleanup',candidate_sha256='cleanup-sha',receiving=dict(ok=True,complete=True))
        receipt['phases'].insert(-1,phase)
        if macros==2:
            receipt['reports']['clipped']['independently_received_suffix_phases'].insert(0,copy.deepcopy(phase))
    return receipt


@pytest.mark.parametrize('macros',[1,2])
@pytest.mark.parametrize('position',['prefix','suffix'])
@pytest.mark.parametrize('fault',[None,'kind','typed','raw_link','gate'])
def test_descriptor_only_names_new_bounded_kind_after_unchanged_gates(macros,position,fault):
    receipt=described(position,macros)
    target=receipt['phases'][0 if position=='prefix'else -2]
    if fault=='kind':target['kind']='arbitrary_Ground_retirement'
    elif fault=='typed':target['receiving']['complete']=False
    elif fault=='gate':receipt['gates']['contact_kelvin_preservation']=False
    elif fault=='raw_link':
        relation=receipt['reports']['clipped']
        proof=relation['source_evidence_match']if macros==1 else relation['macro_boundaries'][0]['source_evidence_match']
        proof['same_evidence']=False
    if fault:
        with pytest.raises(ValueError):scope.received_repair_scope(receipt)
    else:
        before=copy.deepcopy(receipt);result=scope.received_repair_scope(receipt)
        assert result['all_actual_parent_gates_passed']
        assert result['inherited_kelvin_uncertainty_not_newly_qualified']
        assert receipt==before


def test_standalone_ground_link_is_not_new_goal_scope_authority():
    receipt=described_single()
    receipt.update(release_authority=False,current_qualified=False,full_kelvin_qualification=False,
        factory_qualified=False,thermal_qualified=False)
    receipt['phases'][0]=dict(kind=KIND,receiving=dict(ok=True,complete=True))
    with pytest.raises(ValueError,match='unknown_received_repair_scope'):
        scope.received_repair_scope(receipt)


def test_ground_link_does_not_borrow_measurement_repair_allowlist():
    phases=[row(),dict(kind='isolated_measurement_join',candidate='/explicit/quiet.kicad_pcb',
        candidate_sha256='b'*64,pad_uuid='input'),printing()]
    with pytest.raises(ValueError,match='exact_typed_measurement_endpoint_then_print'):
        op.isolated_measurement_contact_transition('/not/read','/not/read-either',phases,[],board_hint='NO_ALIAS')
