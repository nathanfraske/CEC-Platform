"""Only JSON's literal key/array changes are neutral for request identity."""
import json
import time
from unittest.mock import patch

import pytest
import cec_request_wire_identity as wire


def canonical(value):
    return wire.canonical(value, deadline=time.monotonic() + 2.)


def test_json_key_array_boundary_and_map_order_are_neutral():
    original = {'current': {0: 700000, 2: 900000}, 'point': (10, -20),
                'source': {'retained': True, 'amps': .123}}
    serialized = json.loads(json.dumps(original, allow_nan=False))
    assert canonical(original) == canonical(serialized)
    assert canonical({'a': 1, 'b': 2}) == canonical({'b': 2, 'a': 1})


@pytest.mark.parametrize('old,new', [
    (1, True), (0, False), (1, 1.), (0., -0.), (1, '1'),
    ([1, 2], [2, 1]), ({'width': 700000}, {'width': 700001}),
    ({'source': 'qualified'}, {'source': 'asserted'}),
    ({'proof': True}, {'proof': True, 'extra': 'ignored?'}),
])
def test_every_nonrepresentation_change_retains_distinct_identity(old, new):
    assert canonical(old) != canonical(new)


@pytest.mark.parametrize('value', [
    {0: 'native', '0': 'forged'}, {True: 'bool-key'}, {None: 'null-key'},
    {1.5: 'float-key'}, {'x': float('nan')}, {'x': float('inf')},
    {'x': {1, 2}}, {'x': object()}, {'x': 1 << 4097},
])
def test_ambiguous_nonfinite_or_nonliteral_input_is_rejected(value):
    with pytest.raises(ValueError):
        canonical(value)


@pytest.mark.parametrize('value', [
    [None] * 65537, {'text': 'x' * 1048577},
])
def test_structure_and_text_are_bounded(value):
    with pytest.raises(ValueError, match='bounded_request_wire'):
        canonical(value)


def test_cycles_and_excessive_depth_are_not_silently_stringified():
    value = []; value.append(value)
    with pytest.raises(ValueError, match='bounded_request_wire_structure'):
        canonical(value)


def test_deadline_covers_derivation_and_final_serialization():
    with pytest.raises(ValueError, match='deadline'):
        wire.canonical({'x': 1}, deadline=time.monotonic() - 1.)
    with patch.object(wire.time, 'monotonic', side_effect=[0., 0., 0., 2.]):
        with pytest.raises(ValueError, match='deadline'):
            wire.canonical({'x': 1}, deadline=1.)
