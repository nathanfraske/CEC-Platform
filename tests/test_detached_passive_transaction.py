"""Detached first-phase scope is not whole-parent transaction admission."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
import cec_force_current as force
import cec_detached_ordinary_passive_translation as op
from test_detached_ordinary_passive_translation import fixture

def wrapper():
    directory=Path(__file__).resolve().parents[1]/'build'
    if str(directory)not in sys.path:sys.path.insert(0,str(directory))
    operations=directory.parent/'ops'
    if str(operations)not in sys.path:sys.path.insert(0,str(operations))
    spec=importlib.util.spec_from_file_location('detached_transaction_fixture',
        directory/'root_receive_local_transaction_20261022.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('fault',[None,'proposal','child'])
def test_real_saved_receive_phase_and_unowned_mutations(tmp_path,fault):
    module=wrapper();source,root,uid=fixture(tmp_path)
    q=op.plan(source,board_hint=str(root),footprint_uuid=uid,at_nm=[12000000,11000000])
    child=op.write_private(source,tmp_path/'child'/source.name,q)
    proposal=tmp_path/'proposal.json'
    if fault=='proposal':q['at_nm'][0]+=1
    if fault=='child':
        child.write_text(child.read_text().replace('RENAMED_R','FORGED_REFERENCE',1))
    proposal.write_text(json.dumps(q))
    row=dict(kind='detached_passive_translation',candidate=str(child),
        candidate_sha256=force._hash(child),proposal=str(proposal))
    module.validate_phases([row])
    if fault:
        with pytest.raises(AssertionError):module.receive_phase(source,source,row,str(root))
    else:
        selected,r=module.receive_phase(source,source,row,str(root))
        assert selected==child and r['ok']and r['complete'],r
        assert r['whole_parent_current_field_ground_contact_native_intake_parity_and_stack_still_required']
        assert not r['release_authority']

def test_detached_scope_must_be_first_and_does_not_expand_four_phase_cap():
    module=wrapper()
    detached=dict(kind='detached_passive_translation',candidate='private.kicad_pcb',
        candidate_sha256='a'*64,proposal='proposal.json')
    ordinary=dict(kind='ordinary_join',candidate='route.kicad_pcb',
        candidate_sha256='b'*64,net='/renamed')
    module.validate_phases([detached,ordinary])
    with pytest.raises(ValueError,match='must_be_first'):module.validate_phases([ordinary,detached])
    with pytest.raises(ValueError):module.validate_phases([detached,ordinary,ordinary,ordinary,ordinary])
