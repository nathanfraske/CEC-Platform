"""Exact coverage is electrical geometry, not refdes-specific polishing."""
from unittest import mock

import pcbnew
import pytest

import cec_collinear_copper as copper
import cec_route_quality as quality


def board():
    result = pcbnew.BOARD()
    for code, name in enumerate(("/unfamiliar/Z91", "/unfamiliar/Q17"), 1):
        result.Add(pcbnew.NETINFO_ITEM(result, name, code))
    return result


def track(b, start, end, width=0.2, *, layer=pcbnew.F_Cu, net=1, locked=False):
    item = pcbnew.PCB_TRACK(b)
    item.SetNetCode(net)
    item.SetLayer(layer)
    item.SetWidth(round(width*1e6))
    item.SetStart(pcbnew.VECTOR2I(*(round(v*1e6) for v in start)))
    item.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6) for v in end)))
    item.SetLocked(locked)
    b.Add(item)
    return item


def xy(item):
    return tuple((p.x/1e6, p.y/1e6) for p in (item.GetStart(), item.GetEnd()))


@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize("direction", [(1, 0), (0, -1), (-1, 1), (1, 1), (7, 3)])
@pytest.mark.parametrize("reverse", [False, True])
def test_partial_coverage_trims_existing_endpoint_without_changing_width(layer, direction, reverse):
    b = board()
    point = lambda distance: (13+direction[0]*distance, -5+direction[1]*distance)
    protected = track(b, point(0), point(1), 0.3, layer=layer, locked=True)
    a, z = (point(3), point(0)) if reverse else (point(0), point(3))
    moving = track(b, a, z, layer=layer)
    uid = moving.m_Uuid.AsString()
    result = copper.normalize(b)
    assert result["trimmed"] == 1 and result["removed"] == 0
    assert moving.GetWidth() == 200000 and moving.m_Uuid.AsString() == uid
    assert xy(moving) == ((point(3), point(1)) if reverse else (point(1), point(3)))
    assert xy(protected) == (point(0), point(1))
    assert copper.normalize(b)["changed"] is False


def test_full_coverage_chain_deletes_only_unlocked_duplicate_and_group_membership():
    b = board()
    track(b, (0, 0), (2, 0), 0.3, locked=True)
    track(b, (2, 0), (4, 0), 0.4, locked=True)
    victim = track(b, (1, 0), (3, 0))
    victim_uid = victim.m_Uuid.AsString()
    group = pcbnew.PCB_GROUP(b)
    b.Add(group)
    group.AddItem(victim)
    result = copper.normalize(b)
    assert result["removed"] == 1
    assert all(t.m_Uuid.AsString() != victim_uid for t in b.GetTracks())
    assert len(group.GetItems()) == 0
    assert copper.normalize(b)["changed"] is False


def test_partial_coverage_at_both_ends_preserves_the_middle():
    b = board()
    track(b, (-1, 0), (1, 0), 0.4)
    track(b, (3, 0), (5, 0), 0.3)
    moving = track(b, (0, 0), (4, 0))
    result = copper.normalize(b)
    assert result["trimmed"] == 1
    assert xy(moving) == ((1, 0), (3, 0))


@pytest.mark.parametrize("difference", ["width", "net", "layer", "offset", "angle", "locked", "protected", "scope", "excluded", "interior"])
def test_unproven_or_immutable_coverage_is_not_changed(difference):
    b = board()
    track(b, (0, 0), (1, 0), 0.3, locked=True)
    start, end = ((-1, 0), (2, 0)) if difference == "interior" else ((0, 0), (3, 0))
    if difference == "offset":
        start, end = (0, .000001), (3, .000001)
    if difference == "angle":
        end = (3, .000001)
    moving = track(b, start, end, 0.4 if difference == "width" else 0.2,
        net=2 if difference == "net" else 1,
        layer=pcbnew.B_Cu if difference == "layer" else pcbnew.F_Cu,
        locked=difference == "locked")
    args = {}
    if difference == "protected":
        args["protected_uuids"] = [moving.m_Uuid.AsString()]
    if difference == "scope":
        args["track_uuid_scope"] = []
    if difference == "excluded":
        args["exclude_nets"] = [moving.GetNetname()]
    assert copper.normalize(b, **args)["changed"] is False
    assert xy(moving) == (start, end)


def test_wider_narrow_branch_is_not_removed_by_longer_thin_track():
    b = board()
    track(b, (0, 0), (4, 0), 0.2, locked=True)
    wider = track(b, (0, 0), (1, 0), 0.3)
    assert copper.normalize(b)["changed"] is False
    assert wider.GetWidth() == 300000


def test_duplicate_precedence_keeps_locked_not_arbitrary_uuid():
    b = board()
    victim = track(b, (0, 0), (2, 2))
    survivor = track(b, (2, 2), (0, 0), locked=True)
    uid = survivor.m_Uuid.AsString()
    report = copper.normalize(b)
    assert report["removed"] == 1
    assert [t.m_Uuid.AsString() for t in b.GetTracks()] == [uid]


def test_native_quality_advisory_clears_without_waiving_detector():
    b = board()
    track(b, (0, 0), (1, 0), 0.3, locked=True)
    track(b, (0, 0), (3, 0))
    assert quality.analyze_board(b)["advisory_count"] == 1
    copper.normalize(b)
    assert quality.analyze_board(b)["advisory_count"] == 0


def test_bounded_mutation_and_empty_scope_are_real_limits():
    b = board()
    for y in range(4):
        track(b, (0, y), (1, y), .3, locked=True)
        track(b, (0, y), (3, y))
    assert copper.normalize(b, max_changes=0)["changed"] is False
    assert copper.normalize(b, max_changes=2)["trimmed"] == 2
    assert copper.normalize(b, track_uuid_scope=[])["changed"] is False
    assert copper.normalize(b)["trimmed"] == 2


@pytest.mark.parametrize("value", [-1, 1.5, True, None])
def test_invalid_change_cap_fails_closed(value):
    with pytest.raises(ValueError):
        copper.normalize(board(), max_changes=value)


def test_nontrack_objects_are_never_read_as_straight_lines():
    b = mock.Mock()
    items = []
    for kind in ("PCB_ARC", "PCB_VIA"):
        item = mock.Mock()
        item.GetClass.return_value = kind
        items.append(item)
    b.GetTracks.return_value = items
    b.Groups.return_value = []
    assert copper.normalize(b)["changed"] is False
    for item in items:
        item.GetStart.assert_not_called()


def test_randomized_capsule_union_and_locked_inventory_are_preserved():
    import random
    rng = random.Random(63191)
    for direction in ((1, 0), (1, -1), (3, 7)):
        b = board()
        for _ in range(30):
            a, z = sorted(rng.sample(range(-8, 12), 2))
            track(b, (a*direction[0], a*direction[1]),
                (z*direction[0], z*direction[1]), rng.choice((.15, .2, .3, .5)),
                locked=rng.random() < .2)
        def inventory():
            return [(xy(t), t.GetWidth()/1e6, t.IsLocked(), t.m_Uuid.AsString())
                    for t in b.GetTracks()]
        def contains(rows, point):
            for ((a, z), width, _, _) in rows:
                dx, dy = z[0]-a[0], z[1]-a[1]
                t = max(0., min(1., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
                if (point[0]-a[0]-t*dx)**2+(point[1]-a[1]-t*dy)**2 <= (width/2)**2:
                    return True
            return False
        before = inventory()
        copper.normalize(b)
        after = inventory()
        assert {r for r in before if r[2]} == {r for r in after if r[2]}
        for _ in range(1000):
            distance = rng.uniform(-9, 13)
            point = (distance*direction[0]+rng.uniform(-.3, .3),
                     distance*direction[1]+rng.uniform(-.3, .3))
            assert contains(before, point) == contains(after, point)
        assert copper.normalize(b)["changed"] is False
