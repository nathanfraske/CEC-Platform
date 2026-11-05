"""Worker failure telemetry cannot discharge any of the real admission gates."""
import hashlib
import json
import pytest
import cec_received_private_stage as stage


def saved(tmp_path,value):
    p=tmp_path/'receiving.json';p.write_text(json.dumps(value));return p


def test_finite_proposal_refusal_remains_distinct_from_electrical_gates(tmp_path):
    p=saved(tmp_path,dict(gates={},reason='finite_proposal_incomplete',ok=True))
    r=stage.receiving_diagnostic(p)
    assert r['reason']=='finite_proposal_incomplete'
    assert r['sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert r['reported_gate_count']==0 and not r['complete_admission_gate_set_present']
    assert not r['admission_authority']
    assert not stage.admitted({})


@pytest.mark.parametrize('value',[False,None,1,'true',{}])
def test_unknown_truthy_or_failed_reported_gate_is_not_positive(tmp_path,value):
    r=stage.receiving_diagnostic(saved(tmp_path,dict(gates={'native':value,'parity':True})))
    assert r['failed_or_unknown_reported_gates']==['native']
    assert not r['complete_admission_gate_set_present']
    assert not stage.admitted({'native':value,'parity':True})


@pytest.mark.parametrize('value',[{},[],dict(gates=[]),dict(gates={'':True}),
    dict(gates={},reason=True),dict(gates={},reason='x'*1025)])
def test_malformed_receiving_report_cannot_supply_diagnostic(tmp_path,value):
    with pytest.raises(ValueError):stage.receiving_diagnostic(saved(tmp_path,value))


def test_complete_report_diagnostics_still_cannot_publish_on_stale_parent(tmp_path):
    gates={k:True for k in ('operator','invariants','field','ground_returns',
        'source_intake','candidate_intake','parity','native','craft','source_live')}
    r=stage.receiving_diagnostic(saved(tmp_path,dict(gates=gates)))
    assert r['complete_admission_gate_set_present'] and not r['admission_authority']
    result=stage.publish(dict(gates=gates),tmp_path/'publication.json',live=lambda:False)
    assert not result['prefix_accepted'] and not (tmp_path/'publication.json').exists()


def test_report_content_change_changes_evidence_not_a_cached_result(tmp_path):
    p=saved(tmp_path,dict(gates={},reason='finite_proposal_incomplete'))
    a=stage.receiving_diagnostic(p)
    p.write_text(json.dumps(dict(gates={'native':False},reason='actual_native_failure')))
    b=stage.receiving_diagnostic(p)
    assert a['sha256']!=b['sha256'] and b['reason']=='actual_native_failure'
    assert b['failed_or_unknown_reported_gates']==['native']
