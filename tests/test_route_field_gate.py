"""Shared release-field evidence participates in route selection, not just review."""
from unittest import mock
import pytest
import cec_search_policy as policy
import cec_synth_pipeline as synth
import cec_route_field_finish as finish


@pytest.mark.parametrize('count',[0,1,7])
def test_oracle_uses_fresh_shared_checker(count):
    report=dict(ok=count==0,blocking_count=count,violations=['fault']*count)
    with mock.patch('cec_field_coupling.field_coupling_summary',return_value=report) as check:
        assert synth._oracle_field_coupling('fresh-route.kicad_pcb')==report
    check.assert_called_once_with('fresh-route.kicad_pcb')


@pytest.mark.parametrize('report',[{},dict(ok=True),dict(ok=True,blocking_count=1),
    dict(ok=False,blocking_count=0),dict(ok=True,blocking_count=False),
    dict(ok=False,blocking_count=-1)])
def test_missing_or_contradictory_field_evidence_fails_closed(report):
    with mock.patch('cec_field_coupling.field_coupling_summary',return_value=report):
        result=synth._oracle_field_coupling('new-route.kicad_pcb')
    assert result['ok'] is False and result['blocking_count'] is None and result['error']


def test_field_failure_is_part_of_full_oracle_conjunction():
    terms=dict.fromkeys(synth._ROUTE_ORACLE_GATE_TERMS,True)
    assert synth._route_oracle_accepts(terms)
    terms['field_coupling_ok']=False
    assert not synth._route_oracle_accepts(terms)


def _candidate(count,*,origin='trial',length=10):
    return dict(routed=origin+'.kicad_pcb',candidate_origin=origin,gate=False,
        gate_terms=dict(field_coupling_ok=count==0),
        gate_defect_counts=dict(field_coupling_ok=count),
        sort_key=[1,0,0,0,0,0,1000000],drc=0,unconnected=0,vias=10,length=length)


def test_polish_cannot_restore_defect_while_boolean_gate_is_still_false():
    baseline=_candidate(1,origin='incumbent',length=100)
    candidate=_candidate(2,length=1)
    assert policy.incumbent_gate_regressions(candidate,baseline)==['field_coupling_ok:defect_count']
    assert policy.select_candidate([baseline,candidate])==baseline


def test_partial_field_gain_outweighs_cosmetic_length():
    baseline=_candidate(2,origin='incumbent',length=10)
    candidate=_candidate(1,length=11)
    assert policy.select_candidate([baseline,candidate])==candidate


@pytest.mark.parametrize('count',[None,-1,'0',False,float('nan')])
def test_missing_or_invalid_candidate_count_cannot_replace_measured_parent(count):
    baseline=_candidate(2,origin='incumbent')
    candidate=_candidate(count,length=1)
    assert policy.select_candidate([baseline,candidate])==baseline


def test_generic_counts_do_not_trade_different_failure_classes():
    baseline=_candidate(2,origin='incumbent')
    baseline['gate_defect_counts']['different_physical_gate']=1
    candidate=_candidate(0)
    candidate['gate_defect_counts']['different_physical_gate']=2
    assert policy.select_candidate([baseline,candidate])==baseline


def test_count_improvement_still_cannot_lose_an_existing_gate():
    baseline=_candidate(2,origin='incumbent')
    baseline['gate_terms']['decouple_ok']=True
    candidate=_candidate(0)
    candidate['gate_terms']['decouple_ok']=False
    assert policy.select_candidate([baseline,candidate])==baseline


@pytest.mark.parametrize('drc,opens,count,expected',[(0,0,2,True),(1,0,2,False),
    (0,1,2,False),(0,0,0,False),(0,0,None,False),(0,0,True,False)])
def test_field_finishing_requires_closed_structural_route_and_measured_fault(drc,opens,count,expected):
    assert finish.eligible(dict(drc=drc,unconnected=opens,
        field_coupling=dict(ok=False,blocking_count=count))) is expected


def test_timed_out_worker_cannot_copy_partial_candidate_over_parent(tmp_path):
    board=tmp_path/'parent.kicad_pcb';board.write_text('parent bytes')
    row=dict(routed=str(board),drc=0,unconnected=0,field_coupling=dict(ok=False,blocking_count=2))
    with mock.patch('cec_operation_budget.run',side_effect=RuntimeError('deadline')):
        with pytest.raises(RuntimeError,match='deadline'):
            finish.apply(row,tmp_path/'work')
    assert board.read_text()=='parent bytes'
