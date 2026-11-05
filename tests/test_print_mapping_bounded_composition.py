"""Composition is not permission to extend any native constituent's lease."""
import copy
import pytest
import cec_print_context_transition as op


def fixture():
    # Shape-only comparator tests. These flags are not scope or authority;
    # the public receiver must independently produce every real subproof.
    return dict(ok=True,complete=True,source_identity={'sha256':'actual-source'},
        candidate_identity={'sha256':'actual-child'},
        bounded_composition=dict(kind='reconstruction_then_saved_scope_then_identity_live',
            per_constituent_limit_s=10.,aggregate_limit_s=30.,
            whole_check_is_not_a_single_ten_second_phase=True),
        timings_s=dict(source_reconstruction=6.,saved_native_comparison=5.,identity_live=2.,aggregate=13.),
        operator_scope=dict(ok=True,complete=True,actual_material='exact-not-skip-authority',
            bounded_composition=dict(kind='source_reconstruction_then_saved_native_comparison',
                per_constituent_limit_s=10.,aggregate_limit_s=20.),
            timings_s=dict(source_reconstruction=5.8,saved_native_comparison=5.,aggregate=10.8)))


def test_three_fresh_bounded_constituents_compare_without_timing_as_identity():
    a=fixture();b=copy.deepcopy(a)
    b['timings_s'].update(source_reconstruction=6.2,saved_native_comparison=4.8,identity_live=1.8,aggregate=12.8)
    b['operator_scope']['timings_s'].update(source_reconstruction=6.,saved_native_comparison=4.8,aggregate=10.8)
    assert op.same_replay(a,b)
    b['operator_scope']['actual_material']='different'
    assert not op.same_replay(a,b)


@pytest.mark.parametrize('fault',['outer-reconstruction','outer-saved','outer-identity','outer-sum',
    'outer-limit','outer-infinity','outer-missing','inner-reconstruction','inner-saved','inner-sum',
    'inner-limit','inner-missing','inner-boolean','inner-unreceived','inner-mismatch','unreceived','changed-source'])
def test_no_extended_constituent_or_modified_proof_can_hide_in_an_aggregate(fault):
    a=fixture();b=copy.deepcopy(a);times=b['timings_s'];inner=b['operator_scope']
    if fault.startswith('outer-')and fault.split('-',1)[1]in('reconstruction','saved','identity'):
        key={'reconstruction':'source_reconstruction','saved':'saved_native_comparison','identity':'identity_live'}[fault.split('-',1)[1]]
        times[key]=10.;times['aggregate']=sum(v for k,v in times.items()if k!='aggregate')
    elif fault=='outer-sum':times['aggregate']+=.1
    elif fault=='outer-limit':b['bounded_composition']['per_constituent_limit_s']=20.
    elif fault=='outer-infinity':times['aggregate']=float('inf')
    elif fault=='outer-missing':times.pop('saved_native_comparison')
    elif fault in('inner-reconstruction','inner-saved'):
        key='source_reconstruction'if fault.endswith('reconstruction')else'saved_native_comparison'
        inner['timings_s'][key]=10.;inner['timings_s']['aggregate']=sum(v for k,v in inner['timings_s'].items()if k!='aggregate')
    elif fault=='inner-sum':inner['timings_s']['aggregate']+=.1
    elif fault=='inner-limit':inner['bounded_composition']['per_constituent_limit_s']=20.
    elif fault=='inner-missing':inner.pop('timings_s')
    elif fault=='inner-boolean':inner['timings_s']['source_reconstruction']=True
    elif fault=='inner-unreceived':inner['ok']=False
    elif fault=='inner-mismatch':
        inner['timings_s']['saved_native_comparison']+=.1;inner['timings_s']['aggregate']+=.1
    elif fault=='unreceived':b['complete']=False
    else:b['source_identity']['sha256']='other'
    assert not op.same_replay(a,b)
