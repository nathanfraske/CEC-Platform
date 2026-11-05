"""Frozen physical geometry is retained; whole-net ownership is not bypassed."""
import json
import pcbnew
import pytest
import cec_force_current as force
from test_force_current import authority, fixture


def source_fixture(tmp_path, *, rotated=False, renamed=False, incomplete=True):
    source = tmp_path/'native.kicad_pcb'
    row = fixture(source, narrow=False, monitor=False, open_path=incomplete,
                  rotated=rotated, renamed=renamed)
    state = source.with_suffix('.pourfirst-state.json')
    state.write_text(json.dumps(dict(schema=3, frozen_nets=[row['net']],
        prelaid=True, placement_scope='complete')))
    return source, row, state


def capability(source, row, **kwargs):
    board = pcbnew.LoadBoard(str(source))
    with authority(row['net'], source=row['source'], sink=row['sink']):
        return force.force_route_operation_admission(board, [row['net']],
            board_hint='synthetic-current-fixture', authority_path=str(source),
            immutable_nets=kwargs.pop('immutable_nets', ()), **kwargs)


@pytest.mark.parametrize('rotated,renamed', [(False, False), (True, True)])
def test_explicit_additive_mode_can_complete_an_incomplete_prelaid_prefix(tmp_path, rotated, renamed):
    source, row, state = source_fixture(tmp_path, rotated=rotated, renamed=renamed)
    family = force._family(source)
    result = capability(source, row, complete_frozen_prefix=True)
    assert result['eligible']
    proof = result['incomplete_frozen_prefix_additions'][row['net']]
    assert proof['eligible'] and proof['native_copper_count'] > 0
    assert not proof['original_copper_mutation_authorized']
    assert not proof['state_mutation_authorized'] and not proof['current_qualified']
    assert force._family(source) == family


def test_default_keeps_original_whole_net_refusal(tmp_path):
    source, row, state = source_fixture(tmp_path)
    result = capability(source, row)
    assert not result['eligible']
    assert result['refusals'][row['net']]['reason'] == 'immutable_net_addition_forbidden'


def test_caller_whole_net_owner_cannot_be_overridden_even_when_native_net_is_open(tmp_path):
    source, row, state = source_fixture(tmp_path)
    result = capability(source, row, immutable_nets=[row['net']], complete_frozen_prefix=True)
    assert not result['eligible']
    assert 'caller_or_external' in result['incomplete_frozen_prefix_additions'][row['net']]['reason']


def test_external_freeze_owner_cannot_be_overridden(tmp_path, monkeypatch):
    source, row, state = source_fixture(tmp_path)
    external = tmp_path/'external.json'; external.write_bytes(state.read_bytes())
    monkeypatch.setenv('CEC_POURFIRST_STATE', str(external))
    result = capability(source, row, complete_frozen_prefix=True)
    assert not result['eligible']


@pytest.mark.parametrize('changes', [dict(prelaid=False), dict(placement_scope='partial')])
def test_planning_or_partial_freeze_is_not_additive_completion_authority(tmp_path, changes):
    source, row, state = source_fixture(tmp_path)
    data = json.loads(state.read_text()); data.update(changes); state.write_text(json.dumps(data))
    assert not capability(source, row, complete_frozen_prefix=True)['eligible']


def test_native_complete_net_does_not_gain_addition_permission(tmp_path):
    source, row, state = source_fixture(tmp_path, incomplete=False)
    result = capability(source, row, complete_frozen_prefix=True)
    assert not result['eligible']
    assert result['incomplete_frozen_prefix_additions'][row['net']]['reason'] == 'native_whole_net_completion_is_not_missing'


@pytest.mark.parametrize('value', [1, None, 'yes'])
def test_completion_mode_requires_an_explicit_boolean(tmp_path, value):
    source, row, state = source_fixture(tmp_path)
    with pytest.raises(ValueError, match='explicit_boolean'):
        capability(source, row, complete_frozen_prefix=value)
