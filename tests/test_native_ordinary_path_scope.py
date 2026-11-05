"""Agent-decided paths remain bounded geometry, never contact authority."""
import pytest
from root_native_ordinary_path_scope_20261012 import points


@pytest.mark.parametrize('turns', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_multi_edge_backtrack_replacement_is_exact_and_source_independent(turns, mirror):
    path = [(0, 0), (250000, -250000), (250000, -3250000)]
    out = []
    for x, y in path:
        if mirror: x = -x
        for _ in range(turns): x, y = -y, x
        out.extend((x + 9000000, y + 5000000))
    assert points(out) == [tuple(out[i:i+2]) for i in range(0, len(out), 2)]


@pytest.mark.parametrize('values', [[], [0, 0], [0, 0, 1], [0, 0, 0, 0],
    [0, 0, 10000, 5000], [0, 0, 10000, 10001], [False, 0, 10000, 0],
    [0, 0, float('nan'), 0], [0, 0, 2000000001, 0],
    [0, 0, 10000, 0, 0, 0], list(range(66))])
def test_invalid_or_noncanonical_path_refused(values):
    with pytest.raises(ValueError): points(values)
