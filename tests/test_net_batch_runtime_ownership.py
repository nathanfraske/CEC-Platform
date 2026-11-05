"""A worker report is not authority to remove pre-existing/foreign runtime."""
import importlib.util
import json
from pathlib import Path

import pytest
import cec_force_current as force
from test_typed_print_runtime import producer, write_lock

spec=importlib.util.spec_from_file_location('root_owned_net_batch',
    Path(__file__).resolve().parents[1]/'build/root_received_net_batch_20261023.py')
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def fake_job(source,attempt,*,fault=None):
    def run():
        attempt.mkdir()
        child=attempt/'candidate/board.kicad_pcb';child.parent.mkdir();child.write_text('saved child')
        source_proof=producer(source);child_proof=producer(child)
        write_lock(source);write_lock(child)
        if fault=='foreign_owner':write_lock(child,username='someone-else')
        elif fault=='failed_native':source_proof['ok']=False
        elif fault=='wrong_source':source_proof['command'][-1]=str(child)
        elif fault=='source_drift':source.write_text('changed Source')
        record=dict(candidate=str(child),candidate_sha256=force._hash(child),
            reports=dict(native_producers=dict(source=source_proof,candidate=child_proof)))
        if fault=='no_source_producer':del record['reports']['native_producers']['source']
        elif fault=='outside_child':record['candidate']=str(source)
        path=attempt/'receiving.json';force._write(path,record)
        digest=force._hash(path)
        if fault=='diagnostic_drift':digest='0'*64
        return dict(prefix_accepted=False,receiving_diagnostic=dict(path=str(path),sha256=digest))
    return run


def test_fresh_worker_source_and_child_runtime_are_preserved_without_changing_gate_result(tmp_path):
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();source.write_text('Source')
    attempt=tmp_path/'attempt';before=source.read_bytes()
    result=op.owned_runtime_stage(source,attempt,fake_job(source,attempt))
    assert not result['prefix_accepted'] and result['owned_native_runtime']['no_admission_authority']
    assert all(v['bytes_preserved']for v in result['owned_native_runtime']['preserved'].values())
    assert source.read_bytes()==before and not op.runtime.lock_path(source).exists()
    assert not op.runtime.lock_path(attempt/'candidate/board.kicad_pcb').exists()
    assert len(list(tmp_path.glob('*-owned-native-runtime/*/runtime-artifacts/*')))==2


def test_preexisting_source_lock_refuses_before_worker_or_output(tmp_path):
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();source.write_text('Source')
    write_lock(source);old=op.runtime.lock_path(source).read_bytes();called=[]
    with pytest.raises(ValueError,match='preexisting_runtime_lock'):
        op.owned_runtime_stage(source,tmp_path/'attempt',lambda:called.append(True))
    assert not called and op.runtime.lock_path(source).read_bytes()==old
    assert not (tmp_path/'attempt-owned-native-runtime').exists()


@pytest.mark.parametrize('fault',['foreign_owner','failed_native','wrong_source','source_drift',
    'no_source_producer','outside_child','diagnostic_drift'])
def test_unknown_producer_identity_or_owner_never_qualifies_runtime_removal(tmp_path,fault):
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();source.write_text('Source')
    attempt=tmp_path/'attempt'
    with pytest.raises(ValueError):
        op.owned_runtime_stage(source,attempt,fake_job(source,attempt,fault=fault))
    # Never remove the offending file. An earlier independently received
    # Source file may already have been preserved; there is no blanket sweep.
    if fault in ('foreign_owner','outside_child'):
        assert op.runtime.lock_path(attempt/'candidate/board.kicad_pcb').is_file()
    else:
        assert op.runtime.lock_path(source).is_file()


def test_incomplete_geometry_with_no_native_run_is_not_runtime_or_route_admission(tmp_path):
    source=tmp_path/'source/board.kicad_pcb';source.parent.mkdir();source.write_text('Source')
    attempt=tmp_path/'attempt'
    result=op.owned_runtime_stage(source,attempt,lambda:dict(prefix_accepted=False))
    assert not result['prefix_accepted']
    assert result['owned_native_runtime']['preserved']['source']['generated']is False
