"""Synthetic consumer boundary tests; no hardware/contact qualification."""
import copy
import pytest
from test_local_transaction_receiver import op
from test_macro_after_received_prefix import fixture


@pytest.mark.parametrize('extra',[{}, {'purpose':'ground_island_join'}, {'repair_legs':[]},
    {'position_nm':[1,2]}, {'timeout_s':20}, {'current_qualified':True}])
def test_local_window_identity_only_schema(extra):
    row=dict(kind='source_local_return_window',candidate='/a.kicad_pcb',
        candidate_sha256='a'*64,pad_uuid='native-pad',**extra)
    if extra:
        with pytest.raises(ValueError):op.validate_phases([row])
    else:assert op.validate_phases([row])==['source_local_return_window']


@pytest.mark.parametrize('accepted',[False,True])
def test_dispatch_owns_fresh_public_local_return_purpose(tmp_path,monkeypatch,accepted):
    source,parent,child=[tmp_path/n for n in ('source','parent','child')]
    for p in (source,parent,child):p.write_text(p.name)
    row=dict(kind='source_local_return_window',candidate=str(child),
        candidate_sha256=op.force._hash(child),pad_uuid='native-pad')
    calls=[]
    def receive(*a,**kw):
        calls.append((a,kw));return dict(ok=accepted,complete=True)
    monkeypatch.setattr(op.ground_window,'receive',receive)
    if accepted:assert op.receive_phase(source,parent,row,'renamed')[0]==child
    else:
        with pytest.raises(AssertionError):op.receive_phase(source,parent,row,'renamed')
    assert calls==[((parent,child),dict(board_hint='renamed',pad_uuid='native-pad',
        purpose='local_return_completion',timeout_s=10.))]


@pytest.mark.parametrize('fault',[None,'proof_false','incomplete','missing_raw','wrong_source_raw',
    'wrong_child_raw','first_link_false','second_link_false','dependency_refused'])
def test_single_window_links_both_raw_endpoints_without_macro_authority(tmp_path,monkeypatch,fault):
    files,rows=fixture(tmp_path)
    rows[0]=dict(kind='source_local_return_window',candidate=str(files['preclear']),
        candidate_sha256=op.force._hash(files['preclear']),pad_uuid='native-pad')
    raw=[{'at':'caller-source'},{'at':'final'}];saved=copy.deepcopy(raw)
    before={'at':'macro-source'};after={'at':'macro-child'};calls=[]
    monkeypatch.setattr(op,'receive_phase',lambda *a,**kw:(files['preclear'],dict(ok=True,complete=True)))
    monkeypatch.setattr(op.macro_contact,'receive',lambda *a,**kw:
        dict(ok=True,complete=True,raw_native_evidence=[before,after]))
    monkeypatch.setattr(op,'changed_native_nets',lambda *a:['actual-net'])
    monkeypatch.setattr(op,'contact_manifest',lambda *a:['actual-transform'])
    def checked(*a,**kw):
        calls.append(('checked',a,kw))
        if fault=='dependency_refused':raise ValueError('fresh_dependency_changed')
        r=dict(ok=fault!='proof_false',complete=fault!='incomplete',same_evidence=True,
            raw_native_evidence=[raw[0],before])
        if fault=='missing_raw':r.pop('raw_native_evidence')
        if fault=='wrong_source_raw':r['raw_native_evidence'][0]={'at':'forged-source'}
        if fault=='wrong_child_raw':r['raw_native_evidence'][1]={'at':'forged-child'}
        return r
    monkeypatch.setattr(op.window_contact,'receive',checked)
    def strict(a,b,nets,manifest):
        calls.append(('strict',a,b,nets,manifest))
        ok=(a==b)or(a==after and b==raw[1])
        if a==raw[0]and fault=='first_link_false':ok=False
        if b==before and fault=='second_link_false':ok=False
        return dict(comparison_complete=True,same_evidence=ok)
    monkeypatch.setattr(op,'strict_contact_transition',strict)
    if fault in ('proof_false','incomplete','missing_raw','dependency_refused'):
        with pytest.raises((ValueError,KeyError)):
            op.complete_macro_contact_transition(files['source'],files['final'],rows,raw,board_hint='renamed')
    else:
        r=op.complete_macro_contact_transition(files['source'],files['final'],rows,raw,board_hint='renamed')
        assert r['same_evidence']is(fault is None)
        assert r['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']is True
        links=[c for c in calls if c[0]=='strict']
        assert links[0][3:]==([],[])and links[1][3:]==([],[])
    assert calls[0]==('checked',(files['source'],files['preclear']),
        dict(board_hint='renamed',pad_uuid='native-pad',operation='ground_local_return',timeout_s=10.))
    assert raw==saved


def test_multiple_window_prefixes_keep_original_strict_comparison(tmp_path,monkeypatch):
    files,rows=fixture(tmp_path)
    prefix=dict(kind='source_local_return_window',candidate=str(files['preclear']),
        candidate_sha256=op.force._hash(files['preclear']),pad_uuid='p')
    rows=[prefix,dict(prefix,kind='source_ordinary_barrel_reseat',via_uuid='q'),*rows[1:]]
    rows[1].pop('pad_uuid')
    monkeypatch.setattr(op,'receive_phase',lambda *a,**kw:(files['preclear'],dict(ok=True,complete=True)))
    monkeypatch.setattr(op.macro_contact,'receive',lambda *a,**kw:
        dict(ok=True,complete=True,raw_native_evidence=[{'at':'macro-source'},{'at':'macro-child'}]))
    monkeypatch.setattr(op.window_contact,'receive',lambda *a,**kw:pytest.fail('multi-prefix acquired special proof'))
    monkeypatch.setattr(op,'changed_native_nets',lambda *a:['actual'])
    monkeypatch.setattr(op,'contact_manifest',lambda *a:['native'])
    calls=[]
    def strict(*args):calls.append(args);return dict(comparison_complete=True,same_evidence=False)
    monkeypatch.setattr(op,'strict_contact_transition',strict)
    r=op.complete_macro_contact_transition(files['source'],files['final'],rows,[{},{}],board_hint='renamed')
    assert r['same_evidence']is False
    assert calls[0][2:]==(['actual'],['native'])
