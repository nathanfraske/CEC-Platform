import copy
import pytest
from shapely import affinity
from shapely.geometry import box, Polygon
from cec_translation_context_window import relevant_fixed
from cec_cell_packing import pack_context_translations


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', (False, True))
def test_full_swept_extent_preserves_all_possible_blockers(quarter, mirror):
    def pose(g):
        if mirror: g = affinity.scale(g, xfact=-1, origin=(0, 0))
        return affinity.rotate(g, quarter*90, origin=(0, 0))
    moving = dict(geometry=pose(box(0, 0, 1, 1)), context='unknown')
    group = {'arbitrary':dict(members=[moving], bounds=(-2, -2, 2, 2))}
    live = dict(geometry=pose(box(2.9, .1, 3.1, .8)), arbitrary='retained')
    far = dict(geometry=box(100, 100, 101, 101), context='unknown')
    kept, receipt = relevant_fixed(group, [live, far], clearance=.15)
    assert kept == [live] and kept[0] is live
    assert receipt['excluded_fixed_members'] == 1 and not receipt['admission_authority']


@pytest.mark.parametrize('gap', [0., .15])
def test_boundary_touch_and_clearance_retained_without_role_exemption(gap):
    groups = {'g':dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,2,0))}
    touching = dict(geometry=box(3+gap,0,4+gap,1), layer='other', context='peer')
    assert relevant_fixed(groups, [touching], clearance=gap)[0] == [touching]


def test_large_distant_inventory_no_longer_consumes_local_packing_bound():
    groups = {'g':dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,0,0))}
    fixed = [dict(geometry=box(100+i,100,101+i,101)) for i in range(4200)]
    before = copy.deepcopy(groups)
    kept, r = relevant_fixed(groups, fixed)
    assert not kept and r['excluded_fixed_members'] == 4200
    assert groups == before and len(fixed) == 4200
    assert pack_context_translations(groups, kept, interferes=lambda a,b:True)['ok']
    # The production primitive applies the same safe window automatically.
    assert pack_context_translations(groups, fixed, interferes=lambda a,b:True)['ok']


def test_large_live_inventory_does_not_expand_local_search_bound():
    groups = {'g':dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,0,0))}
    fixed = [dict(geometry=box(0,0,1,1)) for _ in range(4097)]
    with pytest.raises(ValueError, match='context packing member inventory bound'):
        pack_context_translations(groups, fixed, interferes=lambda a,b:True)


def test_distant_invalid_shape_not_hidden_by_automatic_spatial_reduction():
    groups = {'g':dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,0,0))}
    fixed = [dict(geometry=box(100,100,101,101)) for _ in range(4100)]
    fixed[-1]['geometry'] = Polygon()
    with pytest.raises(ValueError, match='valid_translation_window_geometry'):
        pack_context_translations(groups, fixed, interferes=lambda a,b:True)


@pytest.mark.parametrize('change', [
    {'bounds':(0,0,-1,0)}, {'bounds':(0,0,float('nan'),0)},
    {'bounds':(False,0,1,0)}, {'members':[]}, {'members':[dict(geometry=Polygon())]},
    {'members':[dict(geometry=Polygon([(0,0),(1,1),(1,0),(0,1)]))]},
])
def test_invalid_inputs_refuse_even_when_far(change):
    row = dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,1,1))
    row.update(change)
    with pytest.raises(ValueError): relevant_fixed({'g':row}, [])


def test_expired_window_cannot_discard_unchecked_geometry(monkeypatch):
    import cec_translation_context_window as module
    ticks = iter([0,11])
    monkeypatch.setattr(module.time, 'monotonic', lambda:next(ticks))
    with pytest.raises(ValueError, match='deadline'):
        relevant_fixed({'g':dict(members=[dict(geometry=box(0,0,1,1))], bounds=(0,0,0,0))}, [])


def test_every_group_member_sweep_retained_not_just_preferred_site():
    groups = {'g':dict(members=[dict(geometry=box(0,0,1,1)),dict(geometry=box(20,0,21,1))],
                       bounds=(-2,0,3,0), preferred=(0,0))}
    obstacles = [dict(geometry=box(23.5,0,24.5,1)),dict(geometry=box(-1.5,0,-.5,1))]
    assert relevant_fixed(groups, obstacles)[0] == obstacles
