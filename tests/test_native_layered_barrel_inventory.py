"""Read-only blocker reports use actual lands without erasing full-depth holes."""
import time

import pcbnew
import pytest

import cec_cell_row_rebuild as cells
import cec_force_current as force
import cec_native_barrel_blockers as blockers
from test_native_layered_via_guard import fixture
from test_field_proposals import track


def inspect(board, via, **overrides):
    args = dict(diameter_nm=3600000, drill_nm=300000, clearance_nm=200000,
        deadline=time.monotonic()+3., native_padstack_via=via)
    args.update(overrides)
    return blockers.inventory(board, via.GetNetCode(), tuple(via.GetPosition()), **args)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
def test_inventory_matches_every_actual_land_and_preserves_source(rotation, mirror):
    board, via = fixture(rotation)
    if mirror:
        # Exact reflection of coordinates, not a layer flip or changed shape.
        for item in [via, *board.GetTracks()]:
            if item.GetClass() == 'PCB_VIA':
                x, y = tuple(item.GetPosition()); item.SetPosition(pcbnew.VECTOR2I(25000000-x, y))
            else:
                sx, sy = tuple(item.GetStart()); ex, ey = tuple(item.GetEnd())
                item.SetStart(pcbnew.VECTOR2I(25000000-sx, sy))
                item.SetEnd(pcbnew.VECTOR2I(25000000-ex, ey))
    before = cells._source_binding(board)
    result = inspect(board, via)
    assert result['inventory_complete'] and result['native_guard_clear']
    assert len(result['layer_rows']) == 6
    assert sorted(result['actual_native_land_diameters_nm'].values()) == [600000]*4+[3600000]*2
    assert not any(row['blockers'] for row in result['layer_rows'])
    assert result['source_unchanged'] and before == cells._source_binding(board)
    assert not any(result[k] for k in ('retirement_authorized', 'current_authority',
        'routing_admitted', 'no_path_proved', 'release_authority'))


@pytest.mark.parametrize('layer,offset', [(pcbnew.F_Cu, 1.), (pcbnew.B_Cu, 1.),
    (pcbnew.In1_Cu, .4), (pcbnew.In2_Cu, .4), (pcbnew.In3_Cu, .4), (pcbnew.In4_Cu, .4)])
def test_real_collision_is_reported_on_its_actual_face(layer, offset):
    board, via = fixture()
    other = track(board, '/foreign', (9, 10-offset), (11, 10-offset), layer=layer)
    result = inspect(board, via)
    assert result['inventory_complete'] and not result['native_guard_clear']
    row = next(r for r in result['layer_rows'] if r['layer'] == board.GetLayerName(layer))
    assert force._uid(other) in {hit['uuid'] for hit in row['blockers']}
    assert row['actual_land_diameter_nm'] == (3600000 if layer in (pcbnew.F_Cu, pcbnew.B_Cu) else 600000)


@pytest.mark.parametrize('fault', ['maximum', 'drill', 'net', 'inner_floor', 'blind', 'mode'])
def test_invalid_template_never_becomes_a_complete_empty_inventory(fault):
    board, via = fixture(); args = {}
    if fault == 'maximum': args['diameter_nm'] = 3500000
    elif fault == 'drill': args['drill_nm'] = 400000
    elif fault == 'net': via.SetNetCode(0)
    elif fault == 'inner_floor': board.GetDesignSettings().m_ViasMinSize = 700000
    elif fault == 'blind': via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault == 'mode': via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    with pytest.raises(ValueError): inspect(board, via, **args)


def test_full_depth_bore_still_blocks_an_overlapping_hole():
    board, via = fixture()
    hole = pcbnew.PCB_VIA(board); hole.SetPosition(via.GetPosition())
    hole.SetWidth(600000); hole.SetDrill(300000); hole.SetNetCode(via.GetNetCode())
    hole.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(hole)
    result = inspect(board, via)
    assert not result['native_guard_clear'] and result['inventory_complete']


def test_uniform_legacy_diagnostic_remains_conservative():
    board, via = fixture()
    old = inspect(board, via, native_padstack_via=None)
    new = inspect(board, via)
    assert not old['native_guard_clear'] and new['native_guard_clear']
    assert old['actual_native_land_diameters_nm'] is None
    assert all(row['actual_land_diameter_nm'] == 3600000 for row in old['layer_rows'])
