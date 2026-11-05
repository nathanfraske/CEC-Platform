"""A declared tiny-span N/A is not an unknown or a changed detour policy."""
import copy,math
import pytest
import cec_pair_local_reference_refinement as op


def row(span=1.75):
    q=dict(kind='can',p='/new/CAN_H',n='/new/CAN_L',length_p_mm=2.5,length_n_mm=2.5,skew_mm=0.,
        endpoint_mst_p_mm=round(span,3),endpoint_mst_n_mm=round(span,3),
        detour_ratio_p=None if span<2 else 1.25,detour_ratio_n=None if span<2 else 1.25,
        detour_ratio_limit=2.,coupled_coverage_pct=80.,reference_coverage_pct=100.,violations=[],
        layers=['F.Cu'],vias_p=0,vias_n=0,endpoint_pofv_p=0,endpoint_pofv_n=0,
        route_transition_vias_p=0,route_transition_vias_n=0,missing_return_vias=[],
        transition_pair_spacing_mm=[],uncoupled_length_budget_mm=2.,stackups={'F.Cu':{'source':'synthetic'}},
        coupling_admission={'ok':True})
    q['detour_ratio_applicability']=dict(schema=1,method='native_terminal_mst_minimum_span',minimum_endpoint_mst_mm=2.,
        endpoint_mst_unrounded_mm=dict(p=span,n=span),applicable=dict(p=span>=2.,n=span>=2.))
    return q


@pytest.mark.parametrize('span',[0.,.001,1.75,1.9999996])
def test_existing_exact_tiny_span_policy_survives_rounding_and_real_shortening(span):
    a=row(span);b=copy.deepcopy(a);b['length_p_mm']=b['length_n_mm']=2.
    r=op.metric_progress(a,b,coupling={'ok':True,'complete':True})
    assert r['ok'] and r['explicitly_inapplicable_detour_members']==['p','n'] and r['missing_detour_authority_is_not_waived']


@pytest.mark.parametrize('fault',['missing','unknown_method','schema_bool','threshold','span_bool','span_nan','span_negative',
    'changed_span','at_boundary','above_boundary','applicable_int','false_applicability','rounded_span','missing_span',
    'one_numeric','unknown_extra_authority','missing_continuous','new_violation','new_skew'])
def test_unknown_changed_or_applicable_metric_cannot_be_relabelled_NA(fault):
    a=row();b=copy.deepcopy(a);coupling={'ok':True,'complete':True};q=b['detour_ratio_applicability']
    if fault=='missing':b.pop('detour_ratio_applicability')
    elif fault=='unknown_method':q['method']='caller_waiver'
    elif fault=='schema_bool':q['schema']=True
    elif fault=='threshold':q['minimum_endpoint_mst_mm']=3.
    elif fault=='span_bool':q['endpoint_mst_unrounded_mm']['p']=True
    elif fault=='span_nan':q['endpoint_mst_unrounded_mm']['p']=math.nan
    elif fault=='span_negative':q['endpoint_mst_unrounded_mm']['p']=-1.
    elif fault=='changed_span':q['endpoint_mst_unrounded_mm']['p']=1.5;b['endpoint_mst_p_mm']=1.5
    elif fault in ('at_boundary','above_boundary'):
        q['endpoint_mst_unrounded_mm']['p']=2. if fault=='at_boundary' else 2.1;b['endpoint_mst_p_mm']=q['endpoint_mst_unrounded_mm']['p']
    elif fault=='applicable_int':q['applicable']['p']=0
    elif fault=='false_applicability':q['applicable']['p']=True
    elif fault=='rounded_span':b['endpoint_mst_p_mm']=1.74
    elif fault=='missing_span':q['endpoint_mst_unrounded_mm'].pop('p')
    elif fault=='one_numeric':b['detour_ratio_p']=1.
    elif fault=='unknown_extra_authority':q['waive']=True
    elif fault=='missing_continuous':coupling=None
    elif fault=='new_violation':b['violations']=['bad']
    elif fault=='new_skew':b['skew_mm']=.01
    r=op.metric_progress(a,b,coupling=coupling);assert not r['ok'] and r['errors']


def test_both_missing_ratios_without_producer_authority_still_fail_closed():
    a=row();a.pop('detour_ratio_applicability');b=copy.deepcopy(a)
    r=op.metric_progress(a,b,coupling={'ok':True,'complete':True});assert not r['ok'] and {'detour_ratio_p','detour_ratio_n'}<=set(r['errors'])


@pytest.mark.parametrize('change',[0.,.01])
def test_applicable_numeric_detours_keep_original_nonworsening_gate(change):
    a=row(2.);b=copy.deepcopy(a);b['detour_ratio_p']+=change
    r=op.metric_progress(a,b,coupling={'ok':True,'complete':True});assert r['ok']==(change==0.)
    assert not r['explicitly_inapplicable_detour_members']
