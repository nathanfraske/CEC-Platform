"""Final-seal transport preserves real Source binding, not worker authority.

The existing annotation comparator remains mandatory in the enclosing driver.
These worker-boundary tests do not pretend a fabricated packet qualifies ink.
"""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
import cec_force_current as force
from test_suite_annotation_epoch_preflight import driver
from test_ordinary_native_portals import fixture


@pytest.mark.parametrize('fault',[None,'crash','missing','refused','incomplete','truthy','source','request','timeout'])
def test_isolated_worker_is_bounded_and_every_failure_is_retained(tmp_path,monkeypatch,fault):
    source,board,net=fixture(tmp_path);out=tmp_path/'seal';out.mkdir()
    row=dict(path=str(source),sha256=force._hash(source));original=source.read_bytes()
    def run(command,**kw):
        assert kw['timeout']==60. and kw['stdout']==subprocess.PIPE
        assert kw['stderr']==subprocess.STDOUT and kw['text']is True
        assert 'timeout_s=10.'in command[2]
        request,result=map(Path,command[-2:]);actual=json.loads(request.read_text())
        assert actual==dict(path=str(source),board_hint='synthetic',row=row)
        if fault=='timeout':raise subprocess.TimeoutExpired(command,60.)
        proof=dict(ok=True,complete=True,scope='worker_transport_test_only')
        if fault=='refused':proof.update(ok=False,error='actual_native_refusal')
        if fault=='incomplete':proof['complete']=False
        if fault=='truthy':proof['ok']=1
        if fault!='missing':force._write(result,proof)
        if fault=='source':source.write_bytes(original+b'\n')
        if fault=='request':force._write(request,dict(forged=True))
        return SimpleNamespace(returncode=1 if fault=='crash'else 0,stdout='test worker output')
    monkeypatch.setattr(subprocess,'run',run)
    if fault:
        with pytest.raises((AssertionError,ValueError)):
            driver.isolated_final_typed(source,'synthetic',row,out)
        if fault not in('source','request'):
            q=json.loads((out/'typed-final-failure.json').read_text())
            assert q['complete']is q['admitted']is q['release_authority']is False
    else:
        q=driver.isolated_final_typed(source,'synthetic',row,out)
        assert q['scope']=='worker_transport_test_only'and q['ok']and q['complete']
    if fault!='source':assert source.read_bytes()==original
