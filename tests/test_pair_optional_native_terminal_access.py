"""Native layer access is reusable capability, not a mandatory routing face."""
import time
from unittest.mock import patch
import pcbnew
import pytest
import cec_precision_route as route
import cec_local_copper_cell as cell
from test_existing_pair_via_terminal_layers import via_fixture


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('sides', [('start',), ('end',), ('start', 'end')])
def test_explicit_alternative_keeps_physical_witness_but_requires_surface_transition(rotation, sides):
    b, pair, ends, pads, vias = via_fixture(rotation, 19., ('/OTHER_A', '/OTHER_B'))
    before = cell.copper_inventory(b)
    default = route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu')
    actual = route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu',
                                                surface_terminal_sides=sides)
    for side in ('start', 'end'):
        if side in sides:
            assert actual[side]['source_layer'] == 'F.Cu'
            assert not actual[side]['native_plated_access']
            assert actual[side]['native_plated_access_available']
            assert actual[side]['access_choice'] == 'explicit_surface_with_new_matched_transition'
            assert actual[side]['barrels'] == default[side]['barrels']
        else:
            assert actual[side] == default[side]
    assert cell.copper_inventory(b) == before


@pytest.mark.parametrize('bad', [None, False, 0, 'end', {'end'}, {}, ['end', 'end'], ['middle'], [1]])
def test_policy_is_bounded_explicit_and_never_truthiness_coerced(bad):
    b, pair, ends, pads, vias = via_fixture()
    before = cell.copper_inventory(b)
    with pytest.raises(ValueError, match='bounded_explicit_surface_terminal_sides_required'):
        route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu',
                                            surface_terminal_sides=bad)
    assert cell.copper_inventory(b) == before


@pytest.mark.parametrize('case', ['wrong_net', 'missing_partner', 'ambiguous', 'blind'])
def test_choice_does_not_invent_native_access_or_hide_a_bad_barrel(case):
    b, pair, ends, pads, vias = via_fixture()
    if case == 'wrong_net':
        vias[1].SetNetCode(b.GetNetcodeFromNetname('FOREIGN'))
    elif case == 'missing_partner':
        b.Remove(vias[1])
    elif case == 'ambiguous':
        duplicate = vias[1].Duplicate()
        duplicate.m_Uuid.Clone(pcbnew.KIID())
        b.Add(duplicate)
    else:
        vias[1].SetViaType(pcbnew.VIATYPE_BLIND)
    before = cell.copper_inventory(b)
    with pytest.raises(ValueError, match='surface_terminal_alternative_requires_positive_native_access'):
        route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu',
                                            surface_terminal_sides=('end',))
    assert cell.copper_inventory(b) == before


@pytest.mark.parametrize('source,middle', [('F.Cu', 'F.Cu'), ('F.Cu', 'In30.Cu'), ('In2.Cu', 'B.Cu')])
def test_new_transition_choice_requires_real_distinct_surface_faces(source, middle):
    b, pair, ends, pads, vias = via_fixture()
    with pytest.raises(ValueError, match='surface_terminal_alternative_requires_'):
        route._paired_native_terminal_layers(b, pair, ends, layer=source, middle_layer=middle,
                                            surface_terminal_sides=('end',))


@pytest.mark.parametrize('bad', [None, False, 0, {}])
def test_beam_does_not_drop_an_invalid_empty_policy(bad):
    b, pair, ends, pads, vias = via_fixture()
    with pytest.raises(ValueError, match='bounded_explicit_surface_terminal_sides_required'):
        route._route_coupled_via_portal_beam(b, pair, ends, middle_layer='B.Cu',
                                            surface_terminal_sides=bad)


@pytest.mark.parametrize('side', ['start', 'end'])
def test_surface_choice_reaches_ordinary_matched_field_and_rolls_back_on_refusal(side):
    b, pair, ends, pads, vias = via_fixture()
    before = cell.copper_inventory(b)
    fanins, fields = [], []

    def fanin(_board, _pair, points, **kwargs):
        fanins.append((points[0], kwargs['layer']))
        return dict(refused='synthetic local fanin refusal')

    def field(row, **kwargs):
        fields.append(row['side'])
        return dict(ok=True, reason=None, p_via={}, n_via={}, return_status='covered')

    with patch.object(route, '_route_paired_stub', side_effect=fanin), \
            patch.object(route, '_probe_matched_transition_field', side_effect=field):
        result = route._route_coupled_via_portal_beam(b, pair, ends, middle_layer='B.Cu',
            surface_terminal_sides=(side,), max_fanins_per_side=1, max_portal_pairs=1,
            deadline=time.monotonic()+3.)
    point = ends[0 if side == 'start' else 1]
    assert result.get('refused')
    assert (point, 'F.Cu') in fanins and fields and set(fields) == {side}
    assert result['portal_evidence']['terminal_layer_access'][side]['native_plated_access_available']
    assert cell.copper_inventory(b) == before


def test_default_and_explicit_empty_policy_remain_literal_compatible():
    b, pair, ends, pads, vias = via_fixture()
    default = route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu')
    assert default == route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu',
        middle_layer='B.Cu', surface_terminal_sides=[])
    assert all(row['native_plated_access'] and 'access_choice' not in row for row in default.values())


def test_prequalified_surface_throat_cannot_be_silently_reinterpreted():
    b, pair, ends, pads, vias = via_fixture()
    before = cell.copper_inventory(b)
    with pytest.raises(ValueError, match='prequalified_start_cannot_be_reclassified_as_surface_alternative'):
        route._route_coupled_via_portal_beam(b, pair, ends, middle_layer='B.Cu',
            surface_terminal_sides=('start',), start_prequalified={'center': (4, 10)})
    assert cell.copper_inventory(b) == before


@pytest.mark.parametrize('valid', [True, False])
def test_compact_trace_preserves_only_the_known_surface_choice(valid):
    import cec_probe_evidence
    b, pair, ends, pads, vias = via_fixture()
    access = route._paired_native_terminal_layers(b, pair, ends, layer='F.Cu', middle_layer='B.Cu',
                                                surface_terminal_sides=('end',))
    if not valid:
        access['end']['access_choice'] = 'unbounded arbitrary route permission'
    rows = cec_probe_evidence.compact_pair_search_trace({'portal_evidence': {'terminal_layer_access': access}})
    chosen = rows[0]['terminal_layer_access']['end']
    assert ('access_choice' in chosen) is valid
    assert ('native_plated_access_available' in chosen) is valid
    assert not chosen['native_plated_access'] and chosen['source_layer'] == 'F.Cu'
