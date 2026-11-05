"""Prefix diagnostics cannot be mistaken for a final transaction receipt."""
import json
import time
from root_receive_local_transaction_20261022 import record_progress


def test_stage_journal_is_non_authoritative_even_after_all_prefix_gates(tmp_path):
    result=dict(baseline='source',baseline_sha256='source-hash',candidate='private',
        candidate_sha256='candidate-hash',gates={'native':True,'current':True},
        complete=True,ok=True,admitted=True,release_authority=True)
    record_progress(tmp_path,result,'final_candidate_print',time.monotonic())
    journal=json.loads((tmp_path/'progress.json').read_text())
    assert journal['finished_gates']==result['gates']
    assert journal['last_started_stage']=='final_candidate_print'
    assert not journal['receiving_complete']and not journal['admitted']and not journal['release_authority']
    assert not(tmp_path/'receiving.json').exists()
    assert result['complete']and result['release_authority']


def test_next_stage_replaces_only_the_non_authoritative_journal(tmp_path):
    result=dict(gates={});started=time.monotonic()
    record_progress(tmp_path,result,'current',started)
    result['gates']['current']=True
    record_progress(tmp_path,result,'field',started)
    journal=json.loads((tmp_path/'progress.json').read_text())
    assert journal['finished_gates']=={'current':True}
    assert journal['last_started_stage']=='field'
    assert journal['elapsed_s']>=0 and not journal['receiving_complete']
