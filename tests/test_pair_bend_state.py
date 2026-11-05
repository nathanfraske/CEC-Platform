import math
import pytest
from cec_pair_bend_state import advance, run_caps


@pytest.mark.parametrize('heading', range(8))
@pytest.mark.parametrize('turn', (-1, 1))
def test_adjacent_same_sense_miters_keep_positive_inner_run(heading, turn):
    caps = run_caps(.125, .400004)
    target = (heading + turn) % 8
    for steps in range(caps[heading]):
        assert advance(heading, turn, steps, target, caps) is None
    assert advance(heading, turn, caps[heading], target, caps) == (turn, 1)
    length = caps[heading] * .125 * (math.sqrt(2) if heading % 2 else 1)
    assert length > .400004 * math.tan(math.pi / 8)


@pytest.mark.parametrize('heading', range(8))
def test_opposite_turn_does_not_inherit_same_sense_retreat(heading):
    caps = run_caps(.1, .54)
    assert advance(heading, 1, 1, (heading - 1) % 8, caps) == (-1, 1)


def test_grid_scaling_and_long_run_state_are_bounded():
    assert run_caps(.125, .400004) == (2, 1, 2, 1, 2, 1, 2, 1)
    assert run_caps(.5, .400004) == (1,) * 8
    caps = run_caps(.125, .400004)
    state = (1, 0)
    for _ in range(1000):
        state = advance(0, *state, 0, caps)
    assert state == (1, 2)


@pytest.mark.parametrize('rotation', range(8))
def test_synthetic_micro_zigzag_is_rejected_before_offset(rotation):
    # NE -> E -> SE with only .125 mm of E was the direction-only bug.
    caps = run_caps(.125, .400004)
    ne, east, se = ((v + rotation) % 8 for v in (7, 0, 1))
    state = advance(ne, 0, 1, east, caps)
    result = advance(east, *state, se, caps)
    if east % 2 == 0:
        assert result is None
        state = advance(east, *state, east, caps)
        assert advance(east, *state, se, caps) == (1, 1)
    else:
        # A diagonal grid edge is sqrt(2) longer and genuinely fits.
        assert result == (1, 1)


@pytest.mark.parametrize('bad', (0, -1, float('inf'), float('nan'), True, '0.2'))
def test_invalid_geometry_fails_closed(bad):
    with pytest.raises(ValueError):
        run_caps(bad, .4)
    with pytest.raises(ValueError):
        run_caps(.125, bad)


def test_extreme_geometry_and_invalid_state_are_not_unbounded_search():
    with pytest.raises(ValueError):
        run_caps(.001, 100)
    caps = run_caps(.125, .4)
    assert advance(0, 0, 0, 2, caps) is None
    with pytest.raises(ValueError):
        advance(0, 0, 3, 0, caps)
    with pytest.raises(ValueError):
        advance(False, 0, 0, 0, caps)
