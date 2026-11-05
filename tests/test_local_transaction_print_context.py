"""Last-only print phase; no library context authority in transaction JSON."""
import importlib.util
from pathlib import Path
import pytest

P=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_print_transaction',P)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)

def phase(kind='print_context'):
    row=dict(kind=kind,candidate='/private/child.kicad_pcb',candidate_sha256='a'*64)
    row.update(options={}if kind=='complete_macro'else None)if kind=='complete_macro'else row.update(proposal='/private/proposal.json')
    return row

def test_macro_reference_then_print_is_finite_typed_order():
    rows=[phase('complete_macro'),phase('reference_fields'),phase()]
    assert op.validate_phases(rows)==['complete_macro','reference_fields','print_context']

@pytest.mark.parametrize('rows',[[phase(),phase('complete_macro')],[phase(),phase('reference_fields')],[phase(),phase()]])
def test_print_is_last_only(rows):
    with pytest.raises(ValueError):op.validate_phases(rows)

@pytest.mark.parametrize('key',['new_context','old_context','authority','external_success'])
def test_print_schema_has_no_context_or_worker_proof(key):
    row=phase();row[key]={}
    with pytest.raises(ValueError):op.validate_phases([row])

def test_phase_uses_actual_parent_and_matched_source_assembly(tmp_path,monkeypatch):
    source=tmp_path/'original.kicad_pcb';parent=tmp_path/'reference.kicad_pcb';child=tmp_path/'print.kicad_pcb';q=tmp_path/'proposal.json'
    for p in(source,parent,child,q):p.write_text(p.name)
    row=phase();row.update(candidate=str(child),candidate_sha256=op.force._hash(child),proposal=str(q))
    op.print_dependencies();seen={};instance={'role':'typed-parent'}
    def receive(candidate,declaration,**kw):
        seen.update(candidate=candidate,declaration=declaration,**kw)
        return dict(ok=True,complete=True,scope_only=True)
    monkeypatch.setattr(op.print_transition,'receive_row',receive)
    actual,proof=op.receive_phase(source,parent,row,'renamed',assembly_instance=instance)
    assert actual==child and proof['ok']
    assert seen['declaration']==dict(source=dict(path=str(parent),sha256=op.force._hash(parent)),proposal=dict(path=str(q),sha256=op.force._hash(q)))
    assert seen['assembly_instance']==instance and seen['timeout_s']==10.
