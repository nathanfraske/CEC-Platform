"""Skipped ablations are unknown, not proofs of impossible placement."""
from types import SimpleNamespace
from unittest.mock import patch
from shapely.geometry import box
import cec_pour_plan as planner


def probe(walls, *, fixed=(), cap=18):
    records=[dict(owner=name,kind='footprint',net='rail',detail='body',geometry=shape)
             for name,shape in walls]
    region=box(0,0,30,20)
    state=dict(region=region,reqw={'F.Cu':1.},bundle=True,
               bundle_obstacle_records={'F.Cu':records})
    space=planner._LayerSpace(region,[r['geometry'] for r in records],.5)
    endpoints=((2.,10.),False,(),(28.,10.),False,())
    with patch.object(planner,'_endpoints_for_layer',return_value=endpoints), \
         patch.object(planner,'_projection_aligned_pairs',return_value=[]):
        return planner._corridor_relief_evidence(SimpleNamespace(ga=None,gb=None),
            state,'F.Cu',space,immovable_owners=fixed,owner_cap=cap,max_cardinality=1)


def test_small_full_width_cut_does_not_claim_broad_failure():
    result=probe([('cell',box(14,0,16,20))])
    assert result['relief_sets'][0]['owners']==['cell']
    for scope in ('all_ranked','all_movable'):
        assert result[scope+'_removal_tested'] is False
        assert result[scope+'_removal_restores_path'] is None
        assert result[scope+'_removal_path'] is None


def test_actual_broad_failure_is_false_not_unknown():
    result=probe([('cell',box(7,0,9,20)),('fixed',box(20,0,22,20))],fixed={'fixed'})
    for scope in ('all_ranked','all_movable'):
        assert result[scope+'_removal_tested'] is True
        assert result[scope+'_removal_restores_path'] is False


def test_all_movable_can_succeed_beyond_ranked_universe():
    result=probe([('a',box(7,0,9,20)),('b',box(20,0,22,20))],cap=1)
    assert result['all_ranked_removal_tested'] is True
    assert result['all_ranked_removal_restores_path'] is False
    assert result['all_movable_removal_tested'] is True
    assert result['all_movable_removal_restores_path'] is True
    assert set(result['all_movable_removal_path']['owners'])=={'a','b'}


def test_successful_ranked_subset_does_not_fabricate_larger_test():
    result=probe([('a',box(7,0,9,20)),('b',box(20,0,22,20)),('c',box(14,17,16,19))],cap=2)
    assert result['all_ranked_removal_tested'] is True
    assert result['all_ranked_removal_restores_path'] is True
    assert result['all_movable_removal_tested'] is False
    assert result['all_movable_removal_restores_path'] is None
    assert result['all_movable_removal_path'] is None


def test_empty_movable_universe_was_not_tested():
    result=probe([('fixed',box(14,0,16,20))],fixed={'fixed'})
    assert result['total_movable_owner_count']==0
    assert result['all_ranked_removal_restores_path'] is None
    assert result['all_movable_removal_restores_path'] is None
