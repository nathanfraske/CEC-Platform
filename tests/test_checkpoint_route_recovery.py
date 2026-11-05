import pytest
import cec_checkpoint_route_recovery as recovery


def row(uid, a, b, *, net='rail', layer=0):
    return dict(uuid=uid, net=net, layer=layer, start_nm=list(a), end_nm=list(b), width_nm=200000)


def key(point, *, net='rail', layer=0):
    return (net, layer, *point)


def test_only_complete_chain_between_explicit_anchors():
    rows = [row('a', (0,0), (5,0)), row('b', (5,0), (8,3)), row('c', (8,3), (10,3))]
    result = recovery.chains(rows, {key((0,0)), key((10,3))})
    assert len(result) == 1
    assert result[0]['points_nm'] == [(0,0), (5,0), (8,3), (10,3)]
    assert recovery.chains(rows, {key((0,0))}) == []


def test_native_anchor_splits_degree_two_chain():
    rows = [row('a', (0,0), (5,0)), row('b', (5,0), (10,0))]
    result = recovery.chains(rows, {key(p) for p in [(0,0), (5,0), (10,0)]})
    assert len(result) == 2
    assert all(len(r['rows']) == 1 for r in result)


def test_branch_and_loop_not_fabricated_as_complete_chain():
    rows = [row('a', (0,0), (5,0)), row('b', (5,0), (10,0)), row('c', (5,0), (5,5))]
    assert recovery.chains(rows, {key((0,0)), key((10,0))}) == []
    loop = [row('a', (0,0), (5,0)), row('b', (5,0), (5,5)), row('c', (5,5), (0,0))]
    assert recovery.chains(loop, set()) == []


def test_net_layer_identity_cannot_merge():
    rows = [row('a', (0,0), (5,0)), row('b', (5,0), (10,0), layer=2),
            row('c', (5,0), (10,0), net='foreign')]
    assert recovery.chains(rows, {key((0,0)), key((10,0))}) == []


def test_exact_rigid_cardinal_transform_only():
    points = [(0,0), (5,0), (5,10)]
    output, proof = recovery.rigid_path(points, (20,20), (10,25))
    assert output == [(20,20), (20,25), (10,25)]
    assert proof == dict(quarter_turns=1, shift_nm=[20,20])
    assert recovery.rigid_path(points, (20,20), (30,40)) == (None, None)


@pytest.mark.parametrize('bad', [
    [row('same', (0,0), (5,0)), row('same', (5,0), (10,0))],
    [row('zero', (0,0), (0,0))],
    [row('fractional', (0.1,0), (5,0))],
])
def test_ambiguous_or_inexact_chain_refused(bad):
    with pytest.raises(ValueError):
        recovery.chains(bad, {key((0,0)), key((10,0))})
