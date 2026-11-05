import math
from unittest import mock

import pytest
import cec_pair_banks as banks
import cec_precision_route as precision


@pytest.mark.parametrize("angle", [0, 37, 90, 180, 270])
@pytest.mark.parametrize("reverse", [False, True])
def test_parallel_banks_independent_of_rotation_translation_and_pad_order(angle, reverse):
    def transform(point):
        x, y = point
        theta = math.radians(angle)
        return (x * math.cos(theta) - y * math.sin(theta) + 134,
                x * math.sin(theta) + y * math.cos(theta) - 82)
    ps = [transform(p) for p in ((0, 0), (0, 2))]
    ns = [transform(p) for p in ((1, 0), (1, 2))]
    if reverse:
        ns.reverse()
    order = banks.ordered_banks(ps, ns)
    assert order == ((1, 0) if reverse else (0, 1))


@pytest.mark.parametrize("ps,ns", [
    ([(0, 0), (0, 1)], [(0, .5), (0, -.5)]),
    ([(0, 0)], [(1, 0), (1, 2)]),
    ([(0, 0), (0, 0)], [(1, 0), (1, 2)]),
    ([(0, 0), (0, 2)], [(1, 0), (2, 0)]),
    ([(0, 0), (float("nan"), 2)], [(1, 0), (1, 2)]),
])
def test_ambiguous_or_invalid_fields_are_not_banks(ps, ns):
    assert banks.ordered_banks(ps, ns) is None


@pytest.mark.parametrize("station", [(10, 5), (55, -30), (-40, 60)])
@pytest.mark.parametrize("names", [("A", "B", "C"), ("X9", "Q88", "Z2")])
def test_displaced_station_never_turns_single_contact_endpoint_into_branch(station, names):
    chip, connector, inline = names
    x, y = station
    pads = {
        "SIG_P": [(chip, "a", (0, 0), None),
                  (connector, "x", (20, 0), None),
                  (connector, "y", (20, 1), None),
                  (inline, "a", (x, y), None),
                  (inline, "b", (x, y + 2), None)],
        "SIG_N": [(chip, "b", (0, 1), None),
                  (connector, "z", (20, .5), None),
                  (connector, "w", (20, -.5), None),
                  (inline, "c", (x + 1, y), None),
                  (inline, "d", (x + 1, y + 2), None)],
    }
    with mock.patch.object(precision, "_pads_on_net",
                           side_effect=lambda board, net: pads[net]):
        legs, stations = precision._flow_through_pair_legs(
            object(), {"p": "SIG_P", "n": "SIG_N"})
    assert stations == [inline]
    assert len(legs) == 2
    # The two native station banks each appear once in the external chain.
    ends = [point for leg in legs for point in leg]
    for point in ((x, y), (x, y + 2), (x + 1, y), (x + 1, y + 2)):
        assert ends.count(point) == 1
