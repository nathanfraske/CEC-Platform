"""Saved macro composition cannot borrow a later cell's repair authority.

These are native-file orchestration/descriptor tests, not fabricated
electrical qualification. The real single-macro and contact receivers have
their separate native tests; both must be called for each saved boundary.
"""
import copy
import uuid

import pcbnew
import pytest

from cec_native_items import create_empty_board
from test_local_transaction_receiver import op
import root_received_goal_scope_20261024 as scope


def chain(tmp_path,prefix=False):
    names=['source']+(['prefix']if prefix else [])+['one','two','cleanup','final']
    files={}
    for name in names:
        board=create_empty_board();text=pcbnew.PCB_TEXT(board);text.SetText(name)
        text.SetLayer(pcbnew.F_Fab);board.Add(text)
        path=tmp_path/(name+'.kicad_pcb');pcbnew.SaveBoard(str(path),board);files[name]=path
    def row(kind,name,**extra):
        path=files[name]
        return dict(kind=kind,candidate=str(path),candidate_sha256=op.force._hash(path),**extra)
    rows=([row('source_ordinary_barrel_reseat','prefix',via_uuid=str(uuid.uuid4()))]if prefix else [])
    rows.extend([row('complete_macro','one',options={}),row('complete_macro','two',options={}),
        row('source_class_ground_tail','cleanup',seed_uuid=str(uuid.uuid4()),allow_locked_track_uuids=[]),
        row('print_context','final',proposal=str(tmp_path/'print-proposal.json'))])
    return files,rows


def wire(monkeypatch,files,*,fault=None):
    calls=[]
    raw={name:dict(native=name,not_qualified=True)for name in files}
    def typed(source,parent,row,hint,**kw):
        calls.append(('typed',row['kind'],str(parent)))
        proof=dict(ok=True,complete=True)
        if fault=='typed_'+row['kind']:proof['ok']=False
        return row['candidate'],proof
    monkeypatch.setattr(op,'receive_phase',typed)
    def macro(parent,child,**kw):
        key=child.stem;prior=parent.stem
        calls.append(('macro',prior,key,kw))
        actual=copy.deepcopy(raw[prior])
        if fault=='intermediate_raw'and key=='two':actual['native']='borrowed-original'
        result=dict(ok=True,complete=True,comparison_complete=True,same_evidence=True,
            source_candidate_families_and_code_unchanged=True,
            raw_native_evidence=[actual,copy.deepcopy(raw[key])])
        if fault in('first_macro','second_macro')and key==('one'if fault=='first_macro'else'two'):
            result['same_evidence']=False
        if fault=='first_macro_unknown'and key=='one':result['complete']=False
        if fault=='raw_inventory'and key=='one':result['raw_native_evidence']=[]
        return result
    monkeypatch.setattr(op.macro_contact,'receive',macro)
    def strict(before,after,nets,manifest):
        calls.append(('strict',copy.deepcopy(before),copy.deepcopy(after),list(nets),list(manifest)))
        # Annotation/typed cleanup changes no copper here. The raw label for
        # final is intentionally the last native macro, not its file name.
        return dict(comparison_complete=True,same_evidence=before==after)
    monkeypatch.setattr(op,'strict_contact_transition',strict)
    return raw,calls


@pytest.mark.parametrize('prefix',[False,True])
def test_two_immediate_macros_receive_both_real_parents_and_keep_raw_link(tmp_path,monkeypatch,prefix):
    files,rows=chain(tmp_path,prefix);raw,calls=wire(monkeypatch,files)
    # Prefix and final annotation are strictly invariant contact boundaries.
    evidence=[copy.deepcopy(raw['prefix'if prefix else'source']),copy.deepcopy(raw['two'])]
    original=copy.deepcopy(evidence);bytes_before={k:p.read_bytes()for k,p in files.items()}
    result=op.complete_macro_contact_transition(files['source'],files['final'],rows,evidence,board_hint='RENAMED')
    assert result['comparison_complete']and result['same_evidence'],result
    macros=[c for c in calls if c[0]=='macro']
    assert [c[1:3]for c in macros]==[('prefix'if prefix else'source','one'),('one','two')]
    assert all(c[3]['timeout_s']==10. and c[3]['board_hint']=='RENAMED'for c in macros)
    strict=[c for c in calls if c[0]=='strict']
    assert len(strict)==3 and strict[1][1:3]==(raw['one'],raw['one'])
    assert strict[1][3:]==([],[])
    assert [p['kind']for p in result['independently_received_suffix_phases']]==[
        'source_class_ground_tail','print_context']
    assert result['all_immediate_Source_macro_boundaries_received']
    assert result['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']
    assert not result['full_kelvin_qualification']and not result['release_authority']
    assert evidence==original and bytes_before=={k:p.read_bytes()for k,p in files.items()}


@pytest.mark.parametrize('fault',['first_macro','second_macro','first_macro_unknown','intermediate_raw',
    'original_raw','final_raw','typed_source_class_ground_tail','typed_print_context','typed_source_ordinary_barrel_reseat'])
def test_no_refused_or_unknown_boundary_can_be_masked_by_a_later_macro(tmp_path,monkeypatch,fault):
    files,rows=chain(tmp_path,True);raw,calls=wire(monkeypatch,files,fault=fault)
    evidence=[copy.deepcopy(raw['prefix']),copy.deepcopy(raw['two'])]
    if fault=='original_raw':evidence[0]['native']='changed-original-debt'
    if fault=='final_raw':evidence[1]['native']='changed-final-debt'
    if fault.startswith('typed_'):
        with pytest.raises(ValueError,match='fresh_exact_typed_macro_chain_boundary_required'):
            op.complete_macro_contact_transition(files['source'],files['final'],rows,evidence,board_hint='OTHER')
    else:
        result=op.complete_macro_contact_transition(files['source'],files['final'],rows,evidence,board_hint='OTHER')
        assert result['same_evidence']is False
    if fault in('first_macro','first_macro_unknown','original_raw'):
        assert len([c for c in calls if c[0]=='macro'])==1


@pytest.mark.parametrize('fault',['duplicate','third','interposed','early_measurement','missing_print',
    'hash','wrong_final','hardlink','raw_inventory','code_changed'])
def test_finite_exact_chain_schema_and_live_files_are_mandatory(tmp_path,monkeypatch,fault):
    files,rows=chain(tmp_path);raw,calls=wire(monkeypatch,files,fault=fault)
    final=files['final']
    if fault=='duplicate':rows[1]=copy.deepcopy(rows[0])
    elif fault=='third':rows.insert(2,dict(rows[0],candidate=str(files['cleanup']),candidate_sha256=op.force._hash(files['cleanup'])))
    elif fault=='interposed':rows[1],rows[2]=rows[2],rows[1]
    elif fault=='early_measurement':rows[2]=dict(kind='isolated_measurement_join',candidate=str(files['cleanup']),
        candidate_sha256=op.force._hash(files['cleanup']),pad_uuid=str(uuid.uuid4()))
    elif fault=='missing_print':rows.pop()
    elif fault=='hash':rows[1]['candidate_sha256']='0'*64
    elif fault=='wrong_final':final=files['cleanup']
    elif fault=='hardlink':
        alias=tmp_path/'alias.kicad_pcb';alias.hardlink_to(files['one'])
        rows[1]['candidate']=str(alias)
        # Different hash literal avoids the duplicate-declaration branch,
        # but actual samefile identity must still refuse before receiving.
    elif fault=='code_changed':
        original=op.force._code_identity;count=0
        def changed():
            nonlocal count
            count+=1
            return original()if count==1 else {'changed':'epoch'}
        monkeypatch.setattr(op.force,'_code_identity',changed)
    with pytest.raises(ValueError):
        op.complete_macro_contact_transition(files['source'],final,rows,
            [raw['source'],raw['two']],board_hint='EXPLICIT')
    if fault not in('raw_inventory','code_changed'):assert not any(c[0]=='macro'for c in calls)


@pytest.mark.parametrize('kind',['source_class_ground_tail','source_ground_land_root_spur','source_ground_literal_endpoint_tail'])
@pytest.mark.parametrize('same_seed',[False,True])
def test_distinct_Source_ground_seeds_are_bounded_independent_boundaries(tmp_path,kind,same_seed):
    files,rows=chain(tmp_path)
    one=rows[2];one['kind']=kind
    two=dict(one,candidate=str(tmp_path/'different.kicad_pcb'),candidate_sha256='1'*64)
    if not same_seed:two['seed_uuid']=str(uuid.uuid4())
    rows.insert(3,two)
    assert len(rows)==5<=op.MAX_LOCAL_PHASES
    if same_seed:
        with pytest.raises(ValueError,match='repeated_Source_Ground_tail_seed_requires_separate_transaction'):
            op.validate_phases(rows)
    else:assert op.validate_phases(rows)==[p['kind']for p in rows]


def described_chain():
    from test_received_goal_scope import fixture
    receipt=fixture();base=copy.deepcopy(receipt['phases'][0]['receiving'])
    receipt.update(scope_source='source',scope_source_sha256='source-sha')
    def physical(parent,sha,child_sha):
        result=copy.deepcopy(base)
        result.update(source_sha256=sha,candidate_sha256=child_sha,
            source_candidate_families_and_code_unchanged=True,
            source_macro_packet=dict(source=parent,source_sha256=sha))
        return result
    one=physical('source','source-sha','one-sha');two=physical('one','one-sha','two-sha')
    receipt['phases']=[dict(kind='complete_macro',candidate='one',candidate_sha256='one-sha',receiving=one),
        dict(kind='complete_macro',candidate='two',candidate_sha256='two-sha',receiving=two),receipt['phases'][-1]]
    positive=dict(comparison_complete=True,same_evidence=True)
    entries=[]
    for index,(parent,sha,child,child_sha,physical_proof)in enumerate([
            ('source','source-sha','one','one-sha',one),('one','one-sha','two','two-sha',two)]):
        contact=dict(ok=True,complete=True,**positive,errors=[],full_kelvin_qualification=False,release_authority=False,
            source_candidate_families_and_code_unchanged=True,saved_macro_receiving=copy.deepcopy(physical_proof))
        entries.append(dict(phase_index=index,source=parent,source_sha256=sha,candidate=child,candidate_sha256=child_sha,
            macro=contact,source_evidence_match=copy.deepcopy(positive),strict_prefix_actual_modified_nets=[],
            strict_prefix_native_copper_transforms=[]))
    receipt['reports']['clipped']=dict(scope='bounded_immediate_Source_macro_contact_chain',**positive,
        source='source',source_sha256='source-sha',candidate='last',candidate_sha256='last-sha',
        macro_boundaries=entries,independently_received_prefix_phases=[],
        independently_received_suffix_phases=[copy.deepcopy(receipt['phases'][-1])],
        strict_macro_boundary_to_final=copy.deepcopy(positive),
        all_immediate_Source_macro_boundaries_received=True,source_candidate_families_and_code_unchanged=True,
        macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True,
        full_kelvin_qualification=False,release_authority=False)
    return receipt


def test_descriptor_explicitly_records_both_macros_without_new_qualification():
    receipt=described_chain();before=copy.deepcopy(receipt)
    result=scope.received_repair_scope(receipt)
    assert result['independently_received_immediate_Source_macro_count']==2
    assert result['no_later_macro_authority_applied_to_earlier_boundary']
    assert result['inherited_kelvin_uncertainty_not_newly_qualified']
    assert receipt==before


@pytest.mark.parametrize('fault',['gate','macro_count','order','parent','parent_sha','child_sha','raw_link',
    'transformed_link','contact_failed','old_source_relabel','second_physical','new_qualification',
    'missing_final','suffix_unreceived','suffix_count','qualified_relation','qualified_macro','incomplete_relation'])
def test_descriptor_cannot_relabel_a_single_receipt_as_a_verified_macro_chain(fault):
    receipt=described_chain();relation=receipt['reports']['clipped'];entries=relation['macro_boundaries']
    if fault=='gate':receipt['gates']['current']=False
    elif fault=='macro_count':entries.pop()
    elif fault=='order':entries.reverse()
    elif fault=='parent':entries[1]['source']='source'
    elif fault=='parent_sha':entries[1]['source_sha256']='source-sha'
    elif fault=='child_sha':entries[0]['candidate_sha256']='two-sha'
    elif fault=='raw_link':entries[1]['source_evidence_match']['same_evidence']=False
    elif fault=='transformed_link':entries[1]['strict_prefix_native_copper_transforms']=[{'borrowed':True}]
    elif fault=='contact_failed':entries[1]['macro']['ok']=False
    elif fault=='old_source_relabel':entries[1]['macro']['saved_macro_receiving']['source_macro_packet']['source']='source'
    elif fault=='second_physical':receipt['phases'][1]['receiving']['all_original_surviving_native_partitions_preserved']=False
    elif fault=='new_qualification':entries[1]['macro']['saved_macro_receiving']['current_qualified']=True
    elif fault=='missing_final':relation.pop('strict_macro_boundary_to_final')
    elif fault=='suffix_unreceived':relation['independently_received_suffix_phases'][0]['receiving']['complete']=False
    elif fault=='suffix_count':relation['independently_received_suffix_phases']=[]
    elif fault=='qualified_relation':relation['full_kelvin_qualification']=True
    elif fault=='qualified_macro':entries[0]['macro']['full_kelvin_qualification']=True
    else:relation['source_candidate_families_and_code_unchanged']=False
    with pytest.raises(ValueError):scope.received_repair_scope(receipt)
