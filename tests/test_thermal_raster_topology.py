"""Native-contact mesh recovery must not edit metal, bridge gaps or renew time."""
import hashlib
import math
import os
import time
from unittest import mock

import numpy as np
import pcbnew
import pytest

import cec_thermal2d as thermal
import cec_thermal_raster_topology as topology


@pytest.fixture(autouse=True)
def isolated_deadline():
    with mock.patch.object(thermal, '_SOLVE_DEADLINE', None):
        yield


def _board(quarter_turn=0, phase=(0., 0.), translation=(0., 0.), gap=False,
           foreign_bridge=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    net = pcbnew.NETINFO_ITEM(board, 'RENAMED_NATIVE_RAIL')
    board.Add(net)
    base = [((.521498, 1.0063), (1.021498, 1.0063), .2),
            ((1.021498, 1.0063), (1.021498, .1063), .2)]
    if gap:
        base = [((.125, .625), (.625, .625), .2),
                ((.875, .875), (1.375, .875), .2)]

    def move(point):
        x, y = point[0]-1, point[1]-1
        for _ in range(quarter_turn):
            x, y = -y, x
        return x+2+translation[0], y+2+translation[1]

    tracks, pads = [], []
    for a, b, width in base:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(*move(a)))
        track.SetEnd(pcbnew.VECTOR2I_MM(*move(b)))
        track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(round(width*1e6))
        track.SetNet(net)
        board.Add(track)
        tracks.append(track)
    if foreign_bridge:
        other = pcbnew.NETINFO_ITEM(board, 'FOREIGN')
        board.Add(other)
        bridge = pcbnew.PCB_TRACK(board)
        bridge.SetStart(tracks[0].GetEnd())
        bridge.SetEnd(tracks[-1].GetStart())
        bridge.SetWidth(200000)
        bridge.SetLayer(pcbnew.F_Cu)
        bridge.SetNet(other)
        board.Add(bridge)
    for ref, point in [('SOURCE_X', base[0][0]), ('LOAD_Y', base[-1][1])]:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        pad.SetNumber('91')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers)
        pad.SetSize(pcbnew.VECTOR2I(300000, 300000))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*move(point)))
        pad.SetNet(net)
        fp.Add(pad)
        pads.append(pad)
    # A zero-width edge is normalized to .1 mm by native saved reload. Use the
    # real width now and put its outer boundary on the intended grid origin.
    x0, y0 = phase[0]+translation[0]+.05, phase[1]+translation[1]+.05
    corners = [(x0, y0), (x0+4, y0), (x0+4, y0+4), (x0, y0+4)]
    for a, b in zip(corners, corners[1:]+corners[:1]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetWidth(100000)
        board.Add(edge)
    return board, tracks, pads


def _signature(board):
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    fmt = pcbnew.STRING_FORMATTER()
    io.FormatBoardToFormatter(fmt, board)
    return hashlib.sha256(fmt.GetString().encode()).hexdigest()


def _select(board, pitch=.25, **kwargs):
    return topology.select_grid(board, thermal,
        currents={'RENAMED_NATIVE_RAIL': 1.1},
        overrides={'RENAMED_NATIVE_RAIL':
            {'refs_src': ['SOURCE_X'], 'refs_sink': ['LOAD_Y']}},
        stackup={'F.Cu': 1., 'B.Cu': 1.}, grid_mm=pitch, **kwargs)


@pytest.mark.parametrize('quarter_turn', range(4))
@pytest.mark.parametrize('phase', [(0., 0.), (.0625, 0.), (0., .0625), (.0625, .0625)])
@pytest.mark.parametrize('pitch', [.25, .125])
def test_native_quarter_grid_phase_and_rotation_never_loses_contact(
        quarter_turn, phase, pitch):
    board, tracks, pads = _board(quarter_turn, phase)
    before = _signature(board)
    result = _select(board, pitch)
    assert result['complete'], result
    assert result['selected_pitch_mm'] in (.25, .125)
    assert result['attempts'][-1]['mismatched_nets'] == []
    assert _signature(board) == before
    assert all(t.GetWidth() == 200000 for t in tracks)
    assert result['refinement_changed_copper'] is False
    assert result['added_graph_shortcuts'] is False
    assert result['grid_convergence_verified'] is False
    assert result['numerical_qualification'] is False


def test_proven_broken_corner_is_refined_without_mask_painting():
    board, *_ = _board()
    result = _select(board)
    assert result['selected_pitch_mm'] == .125
    assert len(result['attempts']) == 2
    assert result['attempts'][0]['mismatched_nets'] == ['RENAMED_NATIVE_RAIL']
    assert result['attempts'][1]['mismatched_nets'] == []


@pytest.mark.parametrize('translation', [(173.125, -91.25), (-49.75, 232.875)])
def test_translated_renamed_native_fixture_is_not_coordinate_exception(translation):
    board, *_ = _board(translation=translation)
    result = _select(board)
    assert result['complete']
    assert result['selected_pitch_mm'] == .125


@pytest.mark.parametrize('foreign_bridge', [False, True])
def test_actual_same_net_gap_is_not_repaired_by_native_name_or_foreign_metal(foreign_bridge):
    board, *_ = _board(gap=True, foreign_bridge=foreign_bridge)
    before = _signature(board)
    result = _select(board)
    assert result['complete'] is False
    assert result['refusal'].startswith('native_terminal_disconnected:')
    assert result['attempts'] == []
    assert _signature(board) == before


def test_hole_or_pour_void_mask_stays_open_without_real_barrel():
    grid = thermal.Grid(0, 0, 4, 4, .25)
    copper = np.ones((grid.ny, grid.nx), dtype=bool)
    copper[:, 7:9] = False  # actual void across the conductor, not a graph edge
    original = copper.copy()
    labels = topology._component_labels({'F.Cu': copper}, {}, grid, None)
    assert labels['F.Cu'][4, 3] != labels['F.Cu'][4, 12]
    assert np.array_equal(copper, original)
    assert np.all(labels['F.Cu'][:, 7:9] == -1)
    assert thermal._solve_net_electrical({pcbnew.F_Cu: copper}, {},
        [(pcbnew.F_Cu, grid.idx(3, 4))], [(pcbnew.F_Cu, grid.idx(12, 4))],
        1., grid, {pcbnew.F_Cu: 1.}, {'F.Cu': 0.}, 25e-6) is None


@pytest.mark.parametrize('at_contact', [False, True])
def test_recovery_contact_cap_must_exclude_complete_native_drill_inventory(at_contact):
    board, tracks, _ = _board()
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('MECHANICAL_VOID')
    board.Add(fp)
    hole = pcbnew.PAD(fp)
    hole.SetNumber('')
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_CIRCLE)
    hole.SetDrillSize(pcbnew.VECTOR2I(400000, 400000))
    hole.SetSize(pcbnew.VECTOR2I(400000, 400000))
    hole.SetLayerSet(pcbnew.LSET.AllCuMask())
    hole.SetPosition(tracks[0].GetEnd() if at_contact else pcbnew.VECTOR2I_MM(3.5, 3.5))
    fp.Add(hole)
    before = _signature(board)
    result = _select(board)
    assert _signature(board) == before
    if at_contact:
        assert not result['complete']
        assert result['refusal'].startswith('lost_contact_intersects_actual_drill:')
        assert result['selected_pitch_mm'] is None
    else:
        assert result['complete']
        witness = result['attempts'][0]['nets']['RENAMED_NATIVE_RAIL'][
            'recovery_contact_witnesses'][0]
        assert witness['complete_drill_inventory_count'] == 1
        assert witness['cap_radius_nm'] == 100000
        assert witness['actual_hole_intersections'] == 0
        assert witness['geometry_only']
        assert witness['conductance_or_ampacity_qualified'] is False


def test_thinner_contact_keeps_physical_width_and_convergence_unknown():
    board, tracks, _ = _board()
    for track in tracks:
        track.SetWidth(100000)
    before = _signature(board)
    result = _select(board)
    assert result['complete'], result
    assert result['selected_pitch_mm'] in (.125, .0625)
    assert _signature(board) == before
    assert not result['grid_convergence_verified']
    assert not result['local_material_conductance_qualified']


def test_missing_native_contact_face_is_not_made_by_terminal_snap():
    board, *_ = _board()
    result = topology.select_grid(board, thermal,
        currents={'RENAMED_NATIVE_RAIL': 1.1},
        overrides={'RENAMED_NATIVE_RAIL': {'refs_src': ['SOURCE_X'],
            'refs_sink': ['LOAD_Y'], 'source_layers': ['B.Cu']}},
        stackup={'F.Cu': 1., 'B.Cu': 1.}, grid_mm=.25)
    assert not result['complete']
    assert result['refusal'].startswith('native_terminal_face_unresolved:')


@pytest.mark.parametrize('limits,reason', [
    ({'max_attempts': 1}, 'topology_refinement_attempt_limit'),
    ({'max_grid_cells': 10}, 'topology_grid_cell_limit'),
    ({'max_estimated_bytes': 1000}, 'topology_working_memory_limit'),
    ({'max_net_nodes': 1}, 'topology_node_limit'),
    ({'min_pitch_mm': .2}, 'topology_minimum_pitch_limit'),
])
def test_bounded_refinement_exhaustion_is_unknown(limits, reason):
    board, *_ = _board()
    result = _select(board, limits=limits)
    assert result['complete'] is False
    assert result['status'] == 'unknown'
    assert result['refusal'] == reason
    assert result['selected_pitch_mm'] is None


def test_expired_lease_does_not_enter_native_inventory_or_renew():
    board, *_ = _board()
    deadline = time.monotonic()-1
    with mock.patch.object(topology, '_native_plan', side_effect=AssertionError('called')):
        result = _select(board, deadline=deadline)
    assert not result['complete']
    assert result['refusal'] == 'topology_preflight_deadline'
    assert result['preflight_deadline_monotonic'] == deadline


def test_each_refinement_uses_original_deadline():
    board, *_ = _board()
    deadline = time.monotonic()+10
    deadlines = []
    original = topology._raster

    def observe(*args):
        deadlines.append(args[-1])
        return original(*args)

    with mock.patch.object(topology, '_raster', side_effect=observe):
        result = _select(board, deadline=deadline)
    assert result['complete']
    assert deadlines == [deadline, deadline]


def test_mutated_native_geometry_cannot_reuse_prior_contact_or_epoch():
    board, tracks, _ = _board()
    original = topology._raster

    def mutate(*args):
        raster = original(*args)
        tracks[0].SetWidth(150000)
        return raster

    with mock.patch.object(topology, '_raster', side_effect=mutate):
        result = _select(board)
    assert not result['complete']
    assert result['refusal'] == 'native_geometry_changed_during_topology_preflight'
    assert result['selected_pitch_mm'] is None


def test_refinement_cannot_extend_hard_work_limits():
    board, *_ = _board()
    with pytest.raises(ValueError, match='hard bound'):
        _select(board, limits={'max_attempts': 99})


def test_solver_never_discards_partially_disconnected_required_terminals():
    g = thermal.Grid(0, 0, 5, 3, 1.)
    m = np.zeros((3, 5), bool)
    m[0, :] = True
    m[2, 0] = True
    assert thermal._solve_net_electrical({0: m}, {}, [(0, 0), (0, 10)], [(0, 4)],
        1., g, {0: 1.}, {'F.Cu': 0.}, 25e-6) is None


def test_duplicate_pad_cells_do_not_erase_current_and_joule_balances():
    g = thermal.Grid(0, 0, 4, 2, 1.)
    m = np.ones((2, 4), bool)
    result = thermal._solve_net_electrical({0: m}, {}, [(0, 0), (0, 0)], [(0, 3)],
        1.1, g, {0: 1.}, {'F.Cu': 0.}, 25e-6)
    assert result is not None
    ledger = result['accounting']
    assert ledger['represented_source_A'] == pytest.approx(1.1)
    assert ledger['represented_sink_A'] == pytest.approx(1.1)
    q, _, _, watts = thermal._joule_from_solution(result, g, oz_by_layer={0: 1.})
    assert watts == pytest.approx(ledger['terminal_work_W'], rel=1e-10)
    assert sum(a.sum()*g.cell_area_m2 for a in q.values()) == pytest.approx(watts)


def test_real_entrypoint_refines_before_temperature_iteration_and_preserves_file(tmp_path):
    board, *_ = _board()
    path = tmp_path/'native-corner.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    before = path.read_bytes()
    grids = []

    def temperature(_k, _q, grid, ambient, **kw):
        grids.append(grid.grid_mm)
        return np.full((grid.ny, grid.nx), ambient+1.)

    with mock.patch.object(thermal, '_thermal_solve', side_effect=temperature):
        result = thermal.solve_board_thermal(str(path),
            stackup_oz={'F.Cu': 1., 'B.Cu': 1.},
            net_currents={'RENAMED_NATIVE_RAIL': 1.1},
            src_sink_override={'RENAMED_NATIVE_RAIL':
                {'refs_src': ['SOURCE_X'], 'refs_sink': ['LOAD_Y']}},
            grid_mm=.25, time_budget_s=30, rho_T=False, backend='cpu',
            component_power={'SOURCE_X': .25})
    assert grids == [.125]
    assert result.nets_dropped == {}
    assert result.meta['operation_complete'] is True
    assert result.meta['electrical_accounting']['RENAMED_NATIVE_RAIL']['energy_conserved']
    assert result.meta['numerical_qualification'] is False
    assert result.meta['spatial_heat_evidence']['copper_integral_W'] == pytest.approx(
        result.meta['copper_joule_W'])
    assert result.meta['spatial_heat_evidence']['component_integral_W'] == pytest.approx(.25)
    assert result.component_heat_density.sum()*(result.grid_mm*1e-3)**2 == pytest.approx(.25)
    assert path.read_bytes() == before


def test_unknown_refinement_never_starts_thermal_or_claims_completed_cool_field(tmp_path):
    board, *_ = _board()
    path = tmp_path/'bounded-corner.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    with mock.patch.object(thermal, '_thermal_solve', side_effect=AssertionError('called')):
        result = thermal.solve_board_thermal(str(path),
            stackup_oz={'F.Cu': 1., 'B.Cu': 1.},
            net_currents={'RENAMED_NATIVE_RAIL': 1.1},
            src_sink_override={'RENAMED_NATIVE_RAIL':
                {'refs_src': ['SOURCE_X'], 'refs_sink': ['LOAD_Y']}},
            grid_mm=.25, time_budget_s=30, raster_topology_limits={'max_attempts': 1})
    assert result.meta['operation_complete'] is False
    assert result.meta['thermal_iterations_completed'] == 0
    assert result.meta['field_computed'] is False
    assert result.nets_dropped == {'RENAMED_NATIVE_RAIL': 'topology_refinement_attempt_limit'}


def test_parent_lease_includes_preflight_and_is_not_renewed_after_it(tmp_path):
    board, *_ = _board()
    path = tmp_path/'parent-lease.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    with mock.patch.dict(os.environ, {'CEC_OPERATION_DEADLINE_EPOCH': str(time.time()-1)}):
        with mock.patch.object(thermal, '_thermal_solve', side_effect=AssertionError('called')):
            result = thermal.solve_board_thermal(str(path),
                stackup_oz={'F.Cu': 1., 'B.Cu': 1.},
                net_currents={'RENAMED_NATIVE_RAIL': 1.1},
                src_sink_override={'RENAMED_NATIVE_RAIL':
                    {'refs_src': ['SOURCE_X'], 'refs_sink': ['LOAD_Y']}},
                grid_mm=.25, time_budget_s=300)
    assert not result.meta['operation_complete']
    assert result.meta['budget_exhausted']
    assert result.meta['raster_topology']['refusal'] == 'topology_preflight_deadline'


def test_refined_mesh_does_not_resample_grid_shaped_cooling_silently(tmp_path):
    board, *_ = _board()
    path = tmp_path/'spatial-cooling.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    with mock.patch.object(thermal, '_thermal_solve', side_effect=AssertionError('called')):
        result = thermal.solve_board_thermal(str(path),
            stackup_oz={'F.Cu': 1., 'B.Cu': 1.},
            net_currents={'RENAMED_NATIVE_RAIL': 1.1},
            src_sink_override={'RENAMED_NATIVE_RAIL':
                {'refs_src': ['SOURCE_X'], 'refs_sink': ['LOAD_Y']}},
            grid_mm=.25, time_budget_s=30, additional_h_W_m2K=np.zeros((17, 17)))
    assert not result.meta['operation_complete']
    assert result.meta['operation_refusal'] == 'grid_shaped_boundary_requires_explicit_reprojection'


def test_straight_sheet_resistance_matches_analytical_chain():
    g = thermal.Grid(0, 0, 10, 2, 1.)
    mask = np.zeros((2, 10), bool)
    mask[0, :] = True
    sol = thermal._solve_net_electrical({0: mask}, {}, [(0, 0)], [(0, 9)],
        1.1, g, {0: 1.}, {'F.Cu': 0.}, 25e-6)
    expected_R = 9 * thermal.RHO_CU / thermal.OZ_M
    assert sol['accounting']['terminal_work_W'] == pytest.approx(1.1**2*expected_R)
    assert sol['accounting']['kirchhoff_relative_residual'] < 1e-10
