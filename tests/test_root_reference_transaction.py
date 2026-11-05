"""ROOT map re-seating is a narrow typed step, not a material waiver."""
import ast,importlib.util,json
from pathlib import Path
import pytest

WRAPPER=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_root_reference_transaction',WRAPPER)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def phase(kind='root_reference_seat'):
    q=dict(kind=kind,candidate='/private/child.kicad_pcb',candidate_sha256='a'*64)
    q.update(options={}if kind=='complete_macro'else None)if kind=='complete_macro'else q.update(proposal='/private/proposal.json')
    return q


def test_macro_root_seat_then_uniform_print_is_explicit_finite_chain():
    rows=[phase('complete_macro'),phase(),phase('print_context')]
    assert op.validate_phases(rows)==['complete_macro','root_reference_seat','print_context']


def test_exact_caption_preparation_then_new_map_is_four_received_phases_not_an_annotation_waiver():
    rows=[phase('complete_macro'),phase(),phase('reference_map'),phase('print_context')]
    assert op.validate_phases(rows)==['complete_macro','root_reference_seat','reference_map','print_context']
    # This remains a material-changing transaction; no Reference-only query
    # shortcut or imported same-material assertion can skip the real gates.
    assert op.reference_query_input_identity('missing','missing',rows,
        board_hint='opaque')is None


@pytest.mark.parametrize('rows',[[phase(),phase()],
    [phase('print_context'),phase()],
    [phase('reference_map'),phase()],
    [phase(),phase('reference_fields')]])
def test_no_repeated_or_implicit_reference_strategy(rows):
    with pytest.raises(ValueError):op.validate_phases(rows)


@pytest.mark.parametrize('key',['allowed_uuids','same_material','current_authority','external_success','native_waiver'])
def test_caller_claim_does_not_expand_phase_scope(key):
    row=phase();row[key]=True
    with pytest.raises(ValueError):op.validate_phases([row])


def test_exact_saved_parent_is_independently_received(tmp_path,monkeypatch):
    original=tmp_path/'original';parent=tmp_path/'parent';child=tmp_path/'child';proposal=tmp_path/'proposal.json'
    for p in(original,parent,child):p.write_text(p.name)
    payload=dict(board_hint='renamed_board',owner_uuid='opaque_owner',group_uuid='opaque_group')
    proposal.write_text(json.dumps(payload));row=phase()
    row.update(candidate=str(child),candidate_sha256=op.force._hash(child),proposal=str(proposal))
    seen=[]
    def receive(source,candidate,q):
        seen.append((source,candidate,q));return dict(ok=True,complete=True)
    monkeypatch.setattr(op.root_seats,'receive',receive)
    assert op.receive_phase(original,parent,row,'renamed_board')[0]==child
    assert seen==[(parent,child,payload)]
    with pytest.raises(AssertionError):op.receive_phase(original,parent,row,'wrong_board')


@pytest.mark.parametrize('proof',[{},dict(ok=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_incomplete_root_scope_cannot_advance(tmp_path,monkeypatch,proof):
    parent=tmp_path/'parent';child=tmp_path/'child';proposal=tmp_path/'proposal.json'
    for p in(parent,child):p.write_text(p.name)
    proposal.write_text(json.dumps(dict(board_hint='renamed')));row=phase()
    row.update(candidate=str(child),candidate_sha256=op.force._hash(child),proposal=str(proposal))
    monkeypatch.setattr(op.root_seats,'receive',lambda *a:proof)
    with pytest.raises(AssertionError):op.receive_phase(parent,parent,row,'renamed')


def test_macro_material_still_owes_every_real_parent_gate():
    tree=ast.parse(WRAPPER.read_text());calls={ast.unparse(n.func)for n in ast.walk(tree)if isinstance(n,ast.Call)}
    assert {'current.receive','sense.replay','sense.compare_contour_preservation',
        'returns.receive','stage.receive_intakes','native.run','stage.native_findings_delta'}<=calls
    assert 'root_seats.dependencies' in calls
    text=WRAPPER.read_text()
    assert 'all(v is True for v in g.values())' in text
    assert "g['all_phase_source_families_live']" in text
    assert "g['code_and_inputs_live']" in text
