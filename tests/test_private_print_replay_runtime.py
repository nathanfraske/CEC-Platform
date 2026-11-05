"""Omit only unused temporary metadata, not actual saved context proof."""
import json
from pathlib import Path

import pytest
import cec_nonpolar_print_context as op
from test_nonpolar_print_context import fixture,planned


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_receiver_replays_bytes_without_unused_temporary_authority(tmp_path,monkeypatch,turn,back):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn,back)
    proposal=planned(source,table,ids)
    artifact=op.construct_private(source,proposal,tmp_path/'candidate')
    child=Path(artifact['candidate']);real=op.libraries.authority;calls=[]
    before={p:p.read_bytes()for p in(source,table,*library.glob('*'))}
    def observed(board,library_table):
        calls.append((Path(board).resolve(),Path(library_table).resolve()))
        return real(board,library_table)
    monkeypatch.setattr(op.libraries,'authority',observed)
    proof=op.receive(source,child,proposal)
    assert proof['ok']and proof['complete'],proof
    assert sum(p==child.resolve()for p,_ in calls)==1
    assert sum(p==source.resolve()for p,_ in calls)==2
    assert all(p in(source.resolve(),child.resolve())for p,_ in calls),calls
    assert all(p.read_bytes()==b for p,b in before.items())
    assert not proof['admitted']and not proof['release_authority']


@pytest.mark.parametrize('fault',['source','vendor','sidecar','extra_file','actual_context','metadata'])
def test_exact_reconstruction_still_refuses_changed_source_or_candidate(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch)
    proposal=planned(source,table,ids)
    artifact=op.construct_private(source,proposal,tmp_path/'candidate')
    child=Path(artifact['candidate'])
    if fault in('source','vendor','sidecar','extra_file'):
        path={'source':source,'vendor':library/'R_1206_3216Metric.kicad_mod',
            'sidecar':child.with_suffix('.kicad_dru'),'extra_file':child.parent/'unowned'}[fault]
        path.write_bytes((path.read_bytes()if path.exists()else b'')+b'\n# mutation\n')
    elif fault=='actual_context':
        (child.parent/'fp-lib-table').write_text(table.read_text())
    else:
        path=child.parent/'print-context.json';data=json.loads(path.read_text())
        data['admitted']=True;path.write_text(json.dumps(data))
    assert not op.receive(source,child,proposal)['ok']
