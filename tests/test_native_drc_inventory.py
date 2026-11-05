"""Native category caps are a completeness problem, never a rule waiver."""
import copy
import pytest
import cec_native_drc_inventory as inventory


def report(kind='silk_overlap',count=0,opens=0,version='10.0.5'):
    return dict(kicad_version=version,violations=[dict(type=kind,items=[]) for _ in range(count)],
                unconnected_items=[dict(type='unconnected_items',items=[]) for _ in range(opens)])


@pytest.mark.parametrize('kind,count,opens,truncated',[
    ('silk_overlap',198,0,False),('silk_overlap',199,0,True),
    ('silk_over_copper',199,0,True),('shorting_items',199,0,True),
    ('clearance',199,0,False),('clearance',498,0,False),('clearance',499,0,True),
    ('silk_overlap',0,498,False),('silk_overlap',0,499,True),
    ('silk_overlap',0,0,False)])
def test_verified_category_and_extended_caps_are_reported_without_mutation(kind,count,opens,truncated):
    original=report(kind,count,opens);frozen=copy.deepcopy(original)
    result=inventory.assess(original)
    assert result['category_limits_checked'] and not result['errors']
    assert result['potentially_truncated'] is truncated
    assert result['reported_unconnected_count']==opens
    assert result['faults_suppressed']==0 and result['admission_unchanged']
    assert not result['release_authority'] and not result['full_native_inventory_proved']
    assert original==frozen


@pytest.mark.parametrize('version',['10.0.4','10.0.6','11.0.0',None,True,10.05,''])
def test_unverified_native_versions_remain_explicitly_unknown(version):
    result=inventory.assess(report(count=199,version=version))
    assert not result['category_limits_checked'] and result['errors']
    assert result['potentially_truncated'] is None and not result['release_authority']


@pytest.mark.parametrize('bad',[None,[],{},dict(kicad_version='10.0.5',violations=[],unconnected_items=None),
    dict(kicad_version='10.0.5',violations=[dict(type=None)],unconnected_items=[]),
    dict(kicad_version='10.0.5',violations=[],unconnected_items=[None])])
def test_missing_or_malformed_native_inventory_never_becomes_complete(bad):
    result=inventory.assess(bad)
    assert result['errors'] and not result['category_limits_checked']
    assert not result['full_native_inventory_proved'] and not result['release_authority']


def test_all_saturated_categories_remain_named_and_counts_are_not_clamped():
    data=report(count=200,opens=500)
    data['violations']+=report(kind='silk_over_copper',count=199)['violations']
    result=inventory.assess(data)
    assert result['reported_violation_counts']=={'silk_overlap':200,'silk_over_copper':199}
    assert {row['type'] for row in result['saturated_categories']}=={'silk_overlap','silk_over_copper','unconnected_items'}
    assert result['faults_suppressed']==0
