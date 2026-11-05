"""Finishing discovery must use the same owned-runtime boundary as admission."""
from pathlib import Path
import pytest
import root_finish_macro_print_20261023 as finish


def test_discovery_captures_runtime_before_native_and_returns_preservation(monkeypatch):
    events=[];source=Path('/actual/private/board.kicad_pcb');out=Path('/outside/source-native.json')
    build=Path('/actual/native-build');runtime=Path('/outside/source-runtime')
    proof=dict(ok=True,complete=True);preserved=dict(generated=True,bytes_preserved=True)
    def native(*args,**kwargs):
        events.append(('native',args,kwargs));return proof
    def observe(candidate,directory,callback):
        events.append(('before_native_absence_and_start',candidate,directory))
        actual=callback();events.append(('quarantine_owned_runtime',actual));return actual,preserved
    monkeypatch.setattr(finish.native,'run',native);monkeypatch.setattr(finish.runtime,'observe',observe)
    assert finish.discover_native(source,out,build,runtime)==(proof,preserved)
    assert [e[0]for e in events]==['before_native_absence_and_start','native','quarantine_owned_runtime']
    assert events[1][1]==(source,out)and events[1][2]==dict(reporting_build=build,timeout_s=10.)


def test_preexisting_owner_lock_refuses_before_native_launch(monkeypatch):
    def refuse(*args):raise ValueError('typed_print_preexisting_runtime_lock_refused')
    monkeypatch.setattr(finish.runtime,'observe',refuse)
    monkeypatch.setattr(finish.native,'run',lambda *a,**k:pytest.fail('must not launch over another owner lock'))
    with pytest.raises(ValueError,match='preexisting_runtime_lock'):
        finish.discover_native(Path('/owner/board.kicad_pcb'),Path('/outside/report'),Path('/tool'),Path('/outside/runtime'))
