"""Measured obstruction order cannot weaken whole-cell atomic receiving."""
from shapely.geometry import box
import pytest
import cec_cell_packing as packing


def fixture():
    return {'a':dict(members=[dict(geometry=box(0,0,1,1),board=0)],bounds=(0,0,3,3)),
            'b':dict(members=[dict(geometry=box(1.5,0,2.5,1),board=0)],bounds=(0,0,3,3))}


@pytest.mark.parametrize('order',[('a','b'),('b','a')])
def test_complete_reordered_replay_remains_atomic_and_does_not_mutate_inputs(order):
    groups=fixture();original=[m['geometry'].wkb for r in groups.values() for m in r['members']]
    def explicit(a,b):return a['board']==b['board']
    r=packing.pack_context_translations(groups,[],interferes=explicit,group_order=order)
    assert r['ok'] and set(r['translations'])==set(groups) and not r['admission_authority']
    assert original==[m['geometry'].wkb for row in groups.values() for m in row['members']]
    assert all('_context_bounds' not in m for row in groups.values() for m in row['members'])


@pytest.mark.parametrize('order',[['a'],['a','a'],['a','unknown'],'ab',True])
def test_partial_duplicated_or_unknown_orders_cannot_drop_cells(order):
    with pytest.raises(ValueError):
        packing.pack_context_translations(fixture(),[],interferes=lambda a,b:True,group_order=order)


def test_broad_phase_retains_close_different_net_and_clearance_conflicts():
    groups=fixture();groups['b']['members'][0]['geometry']=box(1.1,0,2.1,1)
    groups['a']['bounds']=groups['b']['bounds']=(0,0,0,0)
    r=packing.pack_context_translations(groups,[],interferes=lambda a,b:True,clearance=.2,group_order=['b','a'])
    assert not r['ok'] and r['translations']=={} and not r['admission_authority']
