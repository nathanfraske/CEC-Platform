import pytest
from cec_stage_admission import native_geometry_nonregression as receive


def fault(kind,uid='native-id'):
    return dict(type=kind,items=[dict(uuid=uid)])


def report(*rows,opens=0):
    return dict(violations=list(rows),unconnected_items=[dict(index=i) for i in range(opens)])


def test_inherited_physical_debt_is_preserved_not_qualified():
    r=receive(report(fault('clearance'),opens=1),report(fault('clearance'),opens=1))
    assert r['ok'] and r['complete'] and r['new_physical_fault_ids']==[]
    assert not r['inherited_faults_qualified'] and not r['release_authority']


@pytest.mark.parametrize('kind',['courtyards_overlap','shorting_items','hole_clearance',
    'clearance','hole_to_hole','solder_mask_bridge','track_dangling','via_dangling',
    'copper_edge_clearance','unrecognized_future_native_fault'])
def test_new_geometry_fault_cannot_advance_a_successfully_constructed_board(kind):
    r=receive(report(),report(fault(kind)))
    assert not r['ok'] and r['complete'] and r['new_physical_fault_types']==[kind]
    assert r['errors'] and not r['release_authority']


@pytest.mark.parametrize('kind',['silk_overlap','silk_over_copper','silk_edge_clearance'])
def test_deferred_ink_is_separate_from_geometry_and_release(kind):
    r=receive(report(),report(fault(kind)))
    assert r['ok'] and r['complete'] and r['readable_fields_still_required']
    assert r['deferred_ink_fault_ids'] and not r['deferred_ink_is_fab_ready']


def test_lower_fault_count_cannot_hide_a_different_new_short():
    r=receive(report(fault('clearance','old1'),fault('clearance','old2')),
        report(fault('shorting_items','new')))
    assert not r['ok'] and r['new_physical_fault_types']==['shorting_items']


def test_a_successful_placement_may_not_increase_native_opens():
    r=receive(report(opens=1),report(opens=2))
    assert not r['ok'] and 'saved_native_opens_increased' in r['errors']


@pytest.mark.parametrize('bad',[None,{},dict(violations=[],unconnected_items=None),
    dict(violations=[dict(type='clearance',items=None)],unconnected_items=[]),
    dict(violations=[dict(type='',items=[])],unconnected_items=[])])
def test_missing_native_inventory_cannot_be_a_clean_result(bad):
    r=receive(report(),bad)
    assert not r['ok'] and not r['complete'] and r['errors']
