import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'review_suite_baseline', Path(__file__).resolve().parents[1]/'ops/cec_review_suite_baseline.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_plan():
    return ({'schema': 1, 'boards': [
        {'board': 'one', 'path': 'one.kicad_pcb', 'sha256': 'a'*64},
        {'board': 'draft', 'path': None, 'sha256': None}]},
        [{'board': 'one', 'pcb': 'one.kicad_pcb'}, {'board': 'draft', 'pcb': None}])


def test_complete_explicit_suite():
    plan, projects = fixture_plan()
    assert len(module.validate_plan(plan, projects)) == 2


@pytest.mark.parametrize('omitted', [['draft'], []])
def test_explicit_goal_scope_does_not_hide_inventory(omitted):
    plan, projects = fixture_plan()
    plan['out_of_scope'] = omitted
    assert len(module.validate_plan(plan, projects)) == 2


@pytest.mark.parametrize('omitted', [['one', 'draft'], ['old-one'], ['draft', 'draft']])
def test_no_empty_or_unknown_goal_scope(omitted):
    plan, projects = fixture_plan()
    plan['out_of_scope'] = omitted
    with pytest.raises(ValueError): module.validate_plan(plan, projects)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'unbound', 'hidden_pcb'])
def test_no_silent_selection_or_absent_board_pass(change):
    plan, projects = fixture_plan()
    if change == 'missing': plan['boards'].pop()
    elif change == 'duplicate': plan['boards'].append(copy.deepcopy(plan['boards'][0]))
    elif change == 'unknown': plan['boards'][0]['board'] = 'old-one'
    elif change == 'unbound': plan['boards'][0]['sha256'] = None
    else: plan['boards'][0].update(path=None, sha256=None)
    with pytest.raises(ValueError): module.validate_plan(plan, projects)


def test_native_errors_not_hidden_by_zero_scored_drc():
    producer = {'ok': True, 'complete': True}
    raw = {'unconnected_items': [], 'violations': [{'severity': 'error'}], 'scored_drc': 0}
    assert not module.routing_term(producer, raw, {'ok': True})


@pytest.mark.parametrize('cause', ['incomplete', 'stale_source', 'opens', 'missing_opens', 'missing_violations'])
def test_fail_closed_readiness(cause):
    producer, raw, intake = {'ok': True, 'complete': True}, {'unconnected_items': [], 'violations': []}, {'ok': True}
    if cause == 'incomplete': producer['complete'] = False
    elif cause == 'stale_source': intake['ok'] = False
    elif cause == 'opens': raw['unconnected_items'] = [{}]
    elif cause == 'missing_opens': raw.pop('unconnected_items')
    else: raw.pop('violations')
    assert not module.routing_term(producer, raw, intake)


def test_warning_is_visible_but_not_renamed_native_error():
    assert not module.routing_term({'ok': True, 'complete': True},
        {'unconnected_items': [], 'violations': [{'severity': 'warning'}]}, {'ok': True},
        route_quality={'craft_ok':True,'power_contour_review_ok':True})


@pytest.mark.parametrize('cause',[None,'ordinary_jog','power_blob','missing_craft','truthy_craft',
    'missing_contour','missing_quality','warning','excluded','ignored'])
def test_full_suite_goal_requires_all_native_findings_and_whole_copper_craft(cause):
    producer={'ok':True,'complete':True};intake={'ok':True}
    raw={'unconnected_items':[],'violations':[],'excluded_violations':[],'ignored_checks':[]}
    craft={'craft_ok':True,'power_contour_review_ok':True}
    if cause=='ordinary_jog':craft['craft_ok']=False
    elif cause=='power_blob':craft['power_contour_review_ok']=False
    elif cause=='missing_craft':craft.pop('craft_ok')
    elif cause=='truthy_craft':craft['craft_ok']=1
    elif cause=='missing_contour':craft.pop('power_contour_review_ok')
    elif cause=='missing_quality':craft=None
    elif cause=='warning':raw['violations']=[{'severity':'warning'}]
    elif cause=='excluded':raw['excluded_violations']=[{}]
    elif cause=='ignored':raw['ignored_checks']=['clearance']
    assert module.routing_term(producer,raw,intake,route_quality=craft) is (cause is None)


def test_actual_kicad_severity_all_schema_needs_no_invented_exclusions_array():
    raw={'unconnected_items':[],'violations':[],'ignored_checks':[],
        'included_severities':['error','warning','exclusion']}
    assert module.routing_term({'ok':True,'complete':True},raw,{'ok':True},
        route_quality={'craft_ok':True,'power_contour_review_ok':True})
