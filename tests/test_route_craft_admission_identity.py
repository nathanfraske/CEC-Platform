"""No removed old craft defect pays for an introduced different notch."""
import copy
import pytest
import cec_received_private_stage as stage


def report(issues=(),non45=()):
    return dict(issue_count=len(issues),issues=list(issues),non_octilinear_count=len(non45),
        non_octilinear=list(non45))


@pytest.mark.parametrize('change',['type','net','layer','uuid','position','duplicate','non45_swap'])
def test_equal_or_lower_counts_cannot_trade_away_a_new_native_craft_finding(change):
    issue=dict(type='covered_backtrack',net='/OLD',layer='F.Cu',track_uuids=['a','b'],at_mm=[1.,2.])
    child=copy.deepcopy(issue)
    if change=='type':child['type']='reverse_diagonal_jog'
    elif change=='net':child['net']='/NEW'
    elif change=='layer':child['layer']='B.Cu'
    elif change=='uuid':child['track_uuids']=['c','d']
    elif change=='position':child['at_mm'][0]+=.01
    elif change=='duplicate':
        before=report([issue,dict(issue,net='/REMOVED')]);after=report([issue,issue])
    elif change=='non45_swap':
        before=report(non45=[dict(uuid='old',angle_deg=13.)]);after=report(non45=[dict(uuid='new',angle_deg=13.)])
    if change not in('duplicate','non45_swap'):before=report([issue]);after=report([child])
    old=copy.deepcopy((before,after));proof=stage.route_craft_delta(before,after)
    assert proof['ok'] is False
    assert proof['introduced_issues'] or proof['introduced_non_octilinear']
    assert (before,after)==old


@pytest.mark.parametrize('removed',[False,True])
def test_identical_inherited_findings_can_remain_without_being_qualified(removed):
    issue=dict(type='reverse_diagonal_jog',track_uuids=['retained'],at_mm=[1.,2.])
    before=report([issue]);after=report([] if removed else[issue])
    proof=stage.route_craft_delta(before,after)
    assert proof['ok'] is True
    assert not proof['inherited_craft_qualified']
    assert not proof['introduced_issues'] and not proof['introduced_non_octilinear']
