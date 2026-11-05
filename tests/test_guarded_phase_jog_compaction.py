"""Phase cleanup is construction-only and cannot borrow geometric authority."""
import math
import time
import pytest
from cec_route_quality import guarded_phase_jog_compaction as compact


def legs(points, width=239266):
    return [(a, b, width) for a, b in zip(points, points[1:])]


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
def test_parallel_diagonal_phase_jog_compacts_with_exact_endpoints(angle, mirror):
    def transform(p):
        x, y = p
        if mirror: x = -x
        for _ in range(angle // 90): x, y = -y, x
        return x + 7132719, y - 4205331
    source = legs([transform(p) for p in [(0, 0), (0, 300000),
        (200000, 500000), (200000, 560000), (700000, 1060000), (900000, 1060000)]])
    calls = []
    result = compact(source, lambda a, b, w: calls.append((a, b, w)) or True)
    assert len(result) == 3 and result[0][0] == source[0][0] and result[-1][1] == source[-1][1]
    assert all(w == 239266 for _, _, w in result)
    assert sum(math.dist(a, b) for a, b, _ in result) == pytest.approx(
        sum(math.dist(a, b) for a, b, _ in source))
    assert all(row in calls or row in source for row in result)
    assert len(source) == 5


@pytest.mark.parametrize('fault', ['blocked', 'unproved', 'width', 'expired', 'large', 'backtrack'])
def test_no_unguarded_or_unbounded_phase_move(fault):
    source = legs([(0, 0), (200000, 200000), (200000, 300000), (600000, 700000)])
    guard = lambda *_: True
    options = {}
    if fault == 'blocked': guard = lambda *_: False
    if fault == 'unproved': guard = lambda *_: 1
    if fault == 'width': source[1] = (*source[1][:2], 200000)
    if fault == 'expired': options['deadline_monotonic'] = time.monotonic() - 1
    if fault == 'large': options['max_shift_nm'] = 50000
    if fault == 'backtrack':
        source = legs([(0, 0), (200000, 200000), (200000, 100000), (600000, 500000)])
    assert compact(source, guard, **options) == source


def test_guard_can_refuse_first_phase_and_admit_second():
    source = legs([(0, 0), (200000, 200000), (200000, 300000), (600000, 700000)])
    result = compact(source, lambda a, b, w: a != (0, 0) or b != (0, 100000))
    assert result == legs([(0, 0), (600000, 600000), (600000, 700000)])


def test_merged_straight_run_requires_its_own_predicate():
    source = legs([(0, 0), (0, 300000), (200000, 500000),
        (200000, 560000), (700000, 1060000), (900000, 1060000)])
    result = compact(source, lambda a, b, w: math.dist(a, b) <= 1050000)
    assert len(result) == 3
    assert all(math.dist(a, b) <= 1050000 for a, b, _ in result)


@pytest.mark.parametrize('source', [[], [((0, 0), (0, 0), 200000)],
    [((0, 0), (1, 1), 0)], [((0, 0), (1, 1), True)],
    [((0, 0), (1, 1), 200000), ((2, 2), (3, 3), 200000)]])
def test_invalid_phase_input_refused(source):
    with pytest.raises(ValueError): compact(source, lambda *_: True)
