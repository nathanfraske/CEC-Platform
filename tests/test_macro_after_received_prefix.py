"""Cooperative preclear never borrows a later macro's input repair scope."""
import copy
from pathlib import Path
import pcbnew
import pytest
from test_local_transaction_receiver import op, phase


def fixture(tmp_path):
    files={}
    for name in ('source','preclear','macro','final'):
        path=tmp_path/(name+'.kicad_pcb');pcbnew.SaveBoard(str(path),pcbnew.BOARD());files[name]=path
    def row(kind,name,**data):
        return dict(kind=kind,candidate=str(files[name]),candidate_sha256=op.force._hash(files[name]),**data)
    rows=[row('source_ordinary_barrel_reseat','preclear',via_uuid='11111111-1111-4111-8111-111111111111'),
        row('complete_macro','macro',options={}),
        row('print_context','final',proposal=str(tmp_path/'proposal.json'))]
    return files,rows


@pytest.mark.parametrize('fault',[None,'prefix_refused','prefix_incomplete','prefix_wrong_file',
    'prefix_hash','prefix_contacts_changed','macro_refused','source_evidence_changed','suffix_contacts_changed'])
def test_both_strict_boundaries_and_fresh_typed_prefix_are_mandatory(tmp_path,monkeypatch,fault):
    files,rows=fixture(tmp_path);calls=[]
    raw_source={'at':'source'};raw_prefix={'at':'prefix'};raw_macro={'at':'macro'};raw_final={'at':'final'}
    original=copy.deepcopy([raw_source,raw_final])
    def receive(source,parent,row,hint,**kw):
        calls.append(('prefix',source,parent,row['kind'],hint))
        return (files['source']if fault=='prefix_wrong_file'else files['preclear'],
            dict(ok=fault!='prefix_refused',complete=fault!='prefix_incomplete'))
    monkeypatch.setattr(op,'receive_phase',receive)
    def macro(source,child,**kw):
        calls.append(('macro',source,child,kw))
        return dict(ok=fault!='macro_refused',complete=True,
            raw_native_evidence=[raw_prefix,raw_macro])
    monkeypatch.setattr(op.macro_contact,'receive',macro)
    monkeypatch.setattr(op,'changed_native_nets',lambda *b:['ACTUAL'])
    monkeypatch.setattr(op,'contact_manifest',lambda *b:['NATIVE'])
    def strict(a,b,nets,manifest):
        calls.append(('strict',a,b,nets,manifest))
        expected=(a==raw_source and b==raw_prefix)or(a==raw_macro and b==raw_final)
        if a==raw_source and fault in ('prefix_contacts_changed','source_evidence_changed'):expected=False
        if a==raw_macro and fault=='suffix_contacts_changed':expected=False
        return dict(comparison_complete=True,same_evidence=expected)
    monkeypatch.setattr(op,'strict_contact_transition',strict)
    if fault=='prefix_hash':rows[0]['candidate_sha256']='0'*64
    if fault in ('prefix_refused','prefix_incomplete','prefix_wrong_file','prefix_hash'):
        with pytest.raises(ValueError):
            op.complete_macro_contact_transition(files['source'],files['final'],rows,original,board_hint='opaque-A')
        assert not any(r[0]=='macro'for r in calls)
        return
    result=op.complete_macro_contact_transition(files['source'],files['final'],rows,original,board_hint='opaque-A')
    assert original==[raw_source,raw_final]
    assert result['same_evidence']==(fault is None)
    if fault=='macro_refused':assert not any(r[0]=='strict'for r in calls)
    else:
        assert result['actual_macro_parent']==str(files['preclear'])
        assert result['strict_prefix_actual_modified_nets']==['ACTUAL']
        assert result['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']is True
        assert [r for r in calls if r[0]=='strict']==[
            ('strict',raw_source,raw_prefix,['ACTUAL'],['NATIVE']),
            ('strict',raw_macro,raw_final,['ACTUAL'],['NATIVE'])]
        assert calls[0][:3]==('prefix',files['source'],files['source'])
        assert calls[1][1:3]==(files['preclear'],files['macro'])


def test_missing_or_duplicate_macro_and_overlong_scope_are_not_composition_authority(tmp_path,monkeypatch):
    files,rows=fixture(tmp_path)
    monkeypatch.setattr(op,'receive_phase',lambda *a,**kw:pytest.fail('invalid scope reached a receiver'))
    for invalid in ([rows[0]],[rows[1],rows[1]],[rows[0],rows[0],rows[0],rows[1],rows[2]]):
        with pytest.raises(ValueError):
            op.complete_macro_contact_transition(files['source'],files['final'],invalid,[{},{}],board_hint='opaque-B')


def test_full_transaction_dispatches_macro_on_membership_not_only_first_phase():
    import ast
    tree=ast.parse(Path(op.__file__).read_text())
    dispatch=[n for n in ast.walk(tree)if isinstance(n,ast.IfExp)
        and isinstance(n.body,ast.Call)and isinstance(n.body.func,ast.Name)
        and n.body.func.id=='complete_macro_contact_transition']
    assert len(dispatch)==1
    assert isinstance(dispatch[0].test,ast.Compare)
    assert ast.unparse(dispatch[0].test)=="'complete_macro' in kinds"
    assert isinstance(dispatch[0].orelse,ast.IfExp)
    assert isinstance(dispatch[0].orelse.body,ast.Call)
    assert dispatch[0].orelse.body.func.id=='isolated_measurement_contact_transition'


@pytest.mark.parametrize('prefix_pass',[False,True])
@pytest.mark.parametrize('absolute_after',[False,True])
def test_macro_and_real_measurement_suffix_keep_independent_saved_authority(
        tmp_path,monkeypatch,prefix_pass,absolute_after):
    # The actual native measurement receiver is exercised. Only the macro
    # boundary, print publication and final evidence comparator are mocked;
    # these consumer tests confer no whole-board or Kelvin qualification.
    import test_measurement_contact_transaction as measurement
    transaction=measurement.transaction
    boundary,joined,final,suffix=measurement.chain(tmp_path,monkeypatch)
    original=transaction.force._copy_family(boundary,tmp_path/'original')
    preclear=transaction.force._copy_family(boundary,tmp_path/'preclear')
    rows=[dict(kind='source_ordinary_barrel_reseat',candidate=str(preclear),
               candidate_sha256=transaction.force._hash(preclear),via_uuid='source-barrel'),
          dict(kind='complete_macro',candidate=str(boundary),
               candidate_sha256=transaction.force._hash(boundary),options={}),*suffix]
    raw=[dict(at='original'),dict(at='final',unqualified_peer=True)]
    original_raw=copy.deepcopy(raw);before=[p.read_bytes()for p in(original,preclear,boundary,joined,final)]
    before_macro=dict(at='preclear');after_macro=dict(at='macro',unqualified_peer=True);calls=[]
    real=transaction.receive_phase
    def receiving(source,parent,row,hint,**kw):
        calls.append(('phase',source,parent,row['kind']))
        if row['kind']=='source_ordinary_barrel_reseat':
            assert source==original and parent==original
            return preclear,dict(ok=True,complete=True)
        assert source==boundary
        return real(source,parent,row,hint,**kw)
    monkeypatch.setattr(transaction,'receive_phase',receiving)
    def macro(source,child,**kw):
        assert source==preclear and child==boundary
        calls.append(('macro',))
        return dict(ok=True,complete=True,raw_native_evidence=[before_macro,after_macro])
    monkeypatch.setattr(transaction.macro_contact,'receive',macro)
    def strict(a,b,nets,manifest):
        assert a==raw[0]and b==before_macro
        calls.append(('strict_prefix',))
        return dict(comparison_complete=True,same_evidence=prefix_pass)
    monkeypatch.setattr(transaction,'strict_contact_transition',strict)
    def compare(*evidence,**kw):
        assert list(evidence)==[after_macro,raw[1]]
        assert kw['repair_legs']==[('RENAMED_INPUT_DEVICE','p','FORCE_A')]
        assert kw['repair_nets']==kw['modified_nets']==['FORCE_A']
        calls.append(('absolute_after',))
        return dict(comparison_complete=True,same_evidence=absolute_after,
                    full_kelvin_qualification=False,release_authority=False)
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',compare)
    result=transaction.complete_macro_contact_transition(original,final,rows,raw,board_hint='RENAMED_SOURCE')
    assert result['comparison_complete']is True
    assert result['same_evidence']is(prefix_pass and absolute_after)
    assert result['macro_boundary_to_final_comparison']=='fresh_typed_measurement_absolute_after'
    assert 'strict_macro_boundary_to_final'not in result
    received=result['independently_received_measurement_suffix']
    assert received['actual_Source_derived_repair_legs']==[['RENAMED_INPUT_DEVICE','p','FORCE_A']]
    assert received['raw_parent_and_candidate_evidence_not_rewritten']is True
    assert result['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']is True
    assert [c[3]for c in calls if c[0]=='phase']==[
        'source_ordinary_barrel_reseat','isolated_measurement_join','print_context']
    assert sum(c[0]=='strict_prefix'for c in calls)==sum(c[0]=='absolute_after'for c in calls)==1
    assert not result['full_kelvin_qualification']and not result['release_authority']
    assert raw==original_raw
    assert before==[p.read_bytes()for p in(original,preclear,boundary,joined,final)]


@pytest.mark.parametrize('fault',['missing_print','unknown_suffix','caller_leg','wrong_endpoint'])
def test_macro_never_expands_measurement_suffix_schema(tmp_path,monkeypatch,fault):
    import test_measurement_contact_transaction as measurement
    transaction=measurement.transaction
    boundary,joined,final,suffix=measurement.chain(tmp_path,monkeypatch)
    original=transaction.force._copy_family(boundary,tmp_path/'original')
    macro=dict(kind='complete_macro',candidate=str(boundary),
               candidate_sha256=transaction.force._hash(boundary),options={})
    if fault=='missing_print':suffix.pop()
    elif fault=='unknown_suffix':suffix.insert(0,dict(kind='reference_fields',candidate=str(boundary),
        candidate_sha256=transaction.force._hash(boundary),proposal=str(tmp_path/'not-measurement.json')))
    elif fault=='caller_leg':suffix[0]['repair_legs']=[['unowned','p','FORCE_A']]
    else:final=joined
    monkeypatch.setattr(transaction.macro_contact,'receive',lambda *a,**kw:
        dict(ok=True,complete=True,raw_native_evidence=[{},{}]))
    monkeypatch.setattr(transaction,'strict_contact_transition',lambda *a,**kw:
        dict(comparison_complete=True,same_evidence=True))
    monkeypatch.setattr(transaction.sense,'compare_repaired_preservation',
        lambda *a,**kw:pytest.fail('invalid suffix reached contact repair comparator'))
    with pytest.raises((ValueError,AssertionError)):
        transaction.complete_macro_contact_transition(original,final,[macro,*suffix],[{},{}],board_hint='RENAMED_SOURCE')
