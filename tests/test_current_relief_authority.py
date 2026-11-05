"""Fixed mechanical obstacles stay present in the placement relief oracle."""
from types import SimpleNamespace
from unittest.mock import patch

from shapely.geometry import box
import cec_pour_plan as planner


def test_exact_relief_search_finds_movable_detour_instead_of_deleting_fixed_terminal():
    records = [
        dict(owner='mechanical', kind='footprint', net='return', detail='barrel',
             geometry=box(9, 3, 11, 20)),
        dict(owner='cell-a', kind='footprint_body', net='logic', detail='body',
             geometry=box(7, 0, 9.5, 5)),
        dict(owner='cell-b', kind='footprint_body', net='logic', detail='body',
             geometry=box(10.5, 0, 13, 5)),
    ]
    region = box(0, 0, 20, 20)
    st = dict(region=region, reqw={'F.Cu':1.}, bundle=True,
              bundle_obstacle_records={'F.Cu':records})
    space = planner._LayerSpace(region, [row['geometry'] for row in records], .5)
    corridor = SimpleNamespace(ga=None, gb=None)
    endpoints = ((2., 10.), False, (), (18., 10.), False, ())
    with patch.object(planner, '_endpoints_for_layer', return_value=endpoints), \
            patch.object(planner, '_projection_aligned_pairs', return_value=[]):
        unbound = planner._corridor_relief_evidence(corridor, st, 'F.Cu', space)
        bound = planner._corridor_relief_evidence(corridor, st, 'F.Cu', space,
                                                 immovable_owners={'mechanical'})
    assert any(row['owners'] == ['mechanical'] for row in unbound['relief_sets'])
    assert bound['immovable_owners'] == ['mechanical']
    assert any(set(row['owners']) == {'cell-a','cell-b'} for row in bound['relief_sets'])
    assert all('mechanical' not in row['owners'] for row in bound['relief_sets'])
    assert all(row['owner'] != 'mechanical' for row in bound['ranked_candidates'])
    # A certificate proposes relocation; the original geometry remains blocked.
    assert planner._find_path(space, endpoints[0], endpoints[3])[0] is None


def test_nonplacement_geometry_cannot_be_removed_as_a_placement_relief_action():
    region = box(0, 0, 20, 20)
    records = [dict(owner='reserved-bus', kind='reserved_pour', net='other', detail='pour',
                    geometry=box(9, 0, 11, 20))]
    st = dict(region=region, reqw={'F.Cu':1.}, bundle=True,
              bundle_obstacle_records={'F.Cu':records}, placement_relief_refs={'logic-cell'})
    space = planner._LayerSpace(region, [records[0]['geometry']], .5)
    with patch.object(planner, '_endpoints_for_layer',
                      return_value=((2.,10.), False, (), (18.,10.), False, ())), \
            patch.object(planner, '_projection_aligned_pairs', return_value=[]):
        result = planner._corridor_relief_evidence(
            SimpleNamespace(ga=None,gb=None), st, 'F.Cu', space)
    assert result['immovable_owners'] == ['reserved-bus']
    assert result['relief_sets'] == [] and result['wide_relief_sets'] == []
    assert result['total_movable_owner_count'] == 0


def test_all_declared_pins_are_forwarded_independent_of_net_or_component_role():
    import cec_synth_pipeline as synth
    cfg = SimpleNamespace(pins={'mechanical-return':(1,2,0)},
                          params={'anchor_pins':{'power':(3,4,90)}})
    assert synth._placement_relief_fixed_refs(cfg) == {'mechanical-return','power'}
    assert synth._placement_relief_fixed_refs(None) is None
    assert synth._placement_relief_fixed_refs(SimpleNamespace()) == set()
