import json
import pytest
from cec_fr_bounded_transcript import Transcript

def test_timeout_partial_output_persists_and_cumulative_updates_do_not_duplicate(tmp_path):
    t=Transcript(tmp_path/'logs',max_bytes=4096,context={'dsn':'bound.dsn','ses':'bound.ses'})
    t.capture(b'parser\nCEC_PASS pass=1\n',b'warning\n')
    t.capture(b'parser\nCEC_PASS pass=1\nnet-current\n',b'warning\n')
    t.finish('timeout')
    assert (t.directory/'stdout.log').read_bytes().count(b'CEC_PASS')==1
    assert json.loads((t.directory/'manifest.json').read_text())['termination']=='timeout'

def test_transcript_head_tail_bounded_and_unknown_admission_never_inferred(tmp_path):
    t=Transcript(tmp_path/'logs',max_bytes=4096);t.capture('A'*5000+'TAIL','E'*10000)
    assert (t.directory/'stdout.log').stat().st_size<=4096
    assert (t.directory/'stderr.log').stat().st_size<=4096
    assert (t.directory/'stdout.log').read_text().endswith('TAIL')
    assert json.loads((t.directory/'manifest.json').read_text())['strict_SES_receiving_required']is True
    with pytest.raises(ValueError):Transcript(tmp_path/'bad',max_bytes=True)

def test_same_retry_parent_gets_unique_attempts_and_keeps_old_receipts(tmp_path):
    first=Transcript(tmp_path/'retry');first.capture('first','');first.finish('timeout')
    second=Transcript(tmp_path/'retry')
    assert first.directory!=second.directory and (first.directory/'stdout.log').read_text()=='first'

def test_default_directory_outside_owned_scratch(monkeypatch,tmp_path):
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path/'durable'))
    t=Transcript();assert str(t.directory).startswith(str(tmp_path/'durable'))
    assert 'scratch'not in str(t.directory)

def test_cleanup_missing_output_preserves_partial_evidence(tmp_path):
    t=Transcript(tmp_path/'logs');t.capture(b'pass-partial',b'error-partial');t.capture(None,None);t.finish('timeout')
    assert (t.directory/'stdout.log').read_bytes()==b'pass-partial'
    assert (t.directory/'stderr.log').read_bytes()==b'error-partial'

def test_throttle_never_evaluates_expensive_join_until_due(monkeypatch,tmp_path):
    import cec_fr_bounded_transcript as m
    clock=[0.0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0])
    t=Transcript(tmp_path/'logs');calls=[]
    def provider():calls.append(1);return 'capture'
    for _ in range(10000):assert t.capture_if_due(provider,provider)is False
    assert calls==[]
    clock[0]=1.0;assert t.capture_if_due(provider,provider)is True and len(calls)==2
