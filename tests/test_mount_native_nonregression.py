"""DRC does not have to warn about every literal library-coordinate drift."""
import copy
import pytest
from cec_source_mount_stitch_reconcile import native_nonregression


def report():
    return dict(violations=[dict(type='silk_overlap',severity='warning',
        description='inherited',items=[dict(uuid='annotation',pos=dict(x=1.,y=2.))])],
        unconnected_items=[],excluded_violations=[])


def test_identical_complete_findings_do_not_require_a_warning_to_disappear():
    a=report();r=native_nonregression(a,copy.deepcopy(a))
    assert r['ok'] and not r['inherited_findings_qualified']


@pytest.mark.parametrize('fault',['new_warning','equal_count_substitution','changed_geometry',
    'inherited_error','exclusion_before','exclusion_after','open_increase'])
def test_no_new_defect_or_inherited_error_is_hidden_by_count_policy(fault):
    a=report();b=copy.deepcopy(a)
    if fault=='new_warning':b['violations'].append(copy.deepcopy(b['violations'][0]))
    elif fault=='equal_count_substitution':b['violations'][0]['type']='different_issue'
    elif fault=='changed_geometry':b['violations'][0]['items'][0]['pos']['x']=1.01
    elif fault=='inherited_error':
        a['violations'][0]['severity']='error';b=copy.deepcopy(a)
    elif fault=='exclusion_before':a['excluded_violations']=[dict(type='ignored')]
    elif fault=='exclusion_after':b['excluded_violations']=[dict(type='ignored')]
    else:b['unconnected_items']=[dict(items=[])]
    assert not native_nonregression(a,b)['ok']


def test_genuine_warning_removal_is_still_accepted():
    a=report();b=copy.deepcopy(a);b['violations']=[]
    assert native_nonregression(a,b)['ok']
