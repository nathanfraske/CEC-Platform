"""Geometry-only rejection must reach placement with the actual copper witness."""
from unittest.mock import patch
import copy

import pytest
import cec_precision_route as precision
import cec_route_preflight as preflight
import cec_probe_evidence as evidence
import cec_fr


@pytest.mark.parametrize('severity',['blocking','advisory'])
def test_separate_geometry_channel_reaches_caller_without_relaxing_gate(severity):
    witness=dict(type='non_octilinear_segment',uuid='synthetic-copper',net='/ARBITRARY',
        layer='In2.Cu',start_mm=[1.,2.],end_mm=[3.,5.],heading_deg=56.3099,
        heading_error_nm=1000000,severity=severity,locked=True)
    report=dict(pairs_ok=False,pairs={'routed':[],'refused':[]},kelvin={},
        route_quality=dict(ok=True,geometry_ok=False,blocking_count=0,issues=[],
                           non_octilinear_count=1,non_octilinear=[witness]))
    original=copy.deepcopy(report)
    with patch.object(precision,'precision_route_board',return_value=report), \
         patch.object(precision,'_pads_on_net',return_value=[('X17',)]), \
         patch.object(cec_fr,'owned_locked_nets',return_value=set()):
        result=preflight._probe_critical_pairs_on_board(object(),'synthetic.kicad_pcb')
    quality=result['route_quality']
    assert not result['pairs_ok'] and not result['critical_routes_ok']
    assert not quality['ok'] and not quality['geometry_ok']
    assert quality['error'] is None and quality['blocking_count']==1
    row=quality['refused'][0]
    assert row['uuid']==witness['uuid'] and row['start_mm']==witness['start_mm']
    assert row['end_mm']==witness['end_mm'] and row['refs']==['X17']
    assert row['severity']=='blocking' and row['reported_severity']==severity
    assert row['admission_gate']=='octilinear_geometry'
    assert preflight.critical_route_refusal_count(result)==1
    assert report==original


def test_opaque_false_without_witness_still_fails_closed():
    with patch.object(precision,'precision_route_board',return_value=dict(
            pairs_ok=False,pairs={},kelvin={},route_quality={'ok':True,'geometry_ok':False})), \
         patch.object(cec_fr,'owned_locked_nets',return_value=set()):
        result=preflight._probe_critical_pairs_on_board(object(),'synthetic.kicad_pcb')
    assert not result['critical_routes_ok']
    assert result['route_quality']['error']=='pairs_ok false without refusal evidence'


def test_compact_evidence_keeps_stall_and_resume_instead_of_only_positive_count():
    report=dict(portal_evidence=dict(minimum_screen_candidates=4,screened={
        'start:+1':dict(accepted=2,checked=9,completed_queries=8,domain_complete=False,resume_calls=6)},
        screen_schedule=dict(minimum_candidates=4,stalled_domains=['start:+1'],
            budget_exhausted=False,round_limit_reached=False,ready_groups=[0],visits=[{}]*500)))
    compact=evidence.compact_pair_search_trace(report)[0]
    assert compact['screened']['start:+1']['completed_queries']==8
    assert compact['screened']['start:+1']['resume_calls']==6
    assert not compact['screened']['start:+1']['domain_complete']
    assert compact['screen_schedule']['stalled_domains']==['start:+1']
    assert 'visits' not in compact['screen_schedule']
