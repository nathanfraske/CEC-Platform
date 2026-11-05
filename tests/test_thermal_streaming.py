"""All copper still conducts heat; only unnecessary dense retention is removed."""
from unittest import mock

import numpy as np
import pcbnew
import pytest

import cec_thermal2d as th
import cec_thermal_raster_topology as topology


@pytest.fixture(autouse=True)
def deadline_isolation():
    with mock.patch.object(th, '_SOLVE_DEADLINE', None):
        yield


def _legacy_raster(board, grid, stackup, include_traces=True, area_injection=True):
    """Independent transcription of the pre-streaming production raster.

    Keep this all-net reference in tests only. In particular it deliberately
    retains every dense mask/width, including the old zone/pad alias semantics.
    """
    stds = dict(th.STD_CU_LAYERS)
    masks, zones, widths, pads = {}, {}, {}, {}
    copper = np.zeros((grid.ny, grid.nx), bool)
    klat = np.full((grid.ny, grid.nx), th.K_FR4 * th.T_BOARD)
    for (net, std), polygons in th._zone_polys(board, stds).items():
        mask = th._rasterize_polys(polygons, grid)
        if not mask.any():
            continue
        width = np.where(mask, 1., 0.)
        masks.setdefault(net, {})[std] = mask
        zones.setdefault(net, {})[std] = mask
        widths.setdefault(net, {})[std] = width
        copper |= mask
        klat[mask] += th.K_CU * stackup.get(std, 0.) * th.OZ_M * width[mask]
    if include_traces:
        for (net, std), segments in th._track_segs(board, stds).items():
            track_mask, track_width = th._rasterize_tracks(segments, grid)
            if not track_mask.any():
                continue
            previous_mask = masks.get(net, {}).get(std)
            previous_width = widths.get(net, {}).get(std)
            if previous_mask is None:
                merged_mask, merged_width = track_mask, track_width
                klat_add = track_width
            else:
                merged_mask = previous_mask | track_mask
                merged_width = np.maximum(previous_width,
                    np.where(track_mask & ~previous_mask, track_width, 0.))
                klat_add = np.where(track_mask & ~previous_mask, track_width, 0.)
            masks.setdefault(net, {})[std] = merged_mask
            widths.setdefault(net, {})[std] = merged_width
            copper |= merged_mask
            klat += th.K_CU * stackup.get(std, 0.) * th.OZ_M * klat_add
    pad_map = th._pad_cells(board, grid, stds, area=area_injection)
    for net, refs in pad_map.items():
        for cells in refs.get('__pads__', {}).values():
            for std, cell in cells:
                y, x = divmod(cell, grid.nx)
                pm = pads.setdefault(net, {}).get(std)
                if pm is None:
                    pm = np.zeros((grid.ny, grid.nx), bool)
                    pads[net][std] = pm
                pm[y, x] = True
                mask = masks.setdefault(net, {}).get(std)
                if mask is None:
                    mask = np.zeros((grid.ny, grid.nx), bool)
                    masks[net][std] = mask
                    widths.setdefault(net, {})[std] = np.zeros((grid.ny, grid.nx))
                if not mask[y, x]:
                    mask[y, x] = True
                    width = widths[net][std]
                    if width[y, x] <= 0:
                        width[y, x] = 1.
                        klat[y, x] += th.K_CU * stackup.get(std, 0.) * th.OZ_M
                    copper[y, x] = True
    layers = {}
    for by_layer in masks.values():
        for std, mask in by_layer.items():
            if std not in layers:
                layers[std] = mask.copy()
            else:
                layers[std] |= mask
    return dict(net_layer_mask=masks, net_zone_mask=zones, net_width_frac=widths,
        net_pad_mask=pads, pad_map=pad_map, copper_any=copper, klat=klat,
        layer_copper_mask=layers)


def _native_fixture(seed=0):
    """Mixed zone/track/pad overlap, foreign copper and multiple native layers."""
    rng = np.random.default_rng(seed)
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    names = ['POWER_RENAMED', 'IDLE_RENAMED', 'OTHER_UNPOWERED', 'PADS_ONLY']
    for index, name in enumerate(names):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        for layer_index, layer in enumerate(layers):
            ox, oy = map(float, rng.uniform(-.1, .1, size=2))
            if index < 3:
                zone = pcbnew.ZONE(board)
                zone.SetNet(net)
                zone.SetLayer(layer)
                poly = pcbnew.SHAPE_POLY_SET()
                outline = poly.NewOutline()
                # Native concave linear fill, no rectangular-bbox approximation.
                points = [(1, 1), (4, 1), (4, 2), (3, 2), (3, 4), (1, 4)]
                for x, y in points:
                    poly.Outline(outline).Append(round((x+ox)*1e6), round((y+oy)*1e6))
                zone.Outline().Append(poly)
                zone.SetFilledPolysList(layer, poly)
                zone.SetIsFilled(True)
                board.Add(zone)
                for a, b, width in [((2, 2), (5.5, 2), .17),
                                     ((5.5, 2), (5.5, 5.5), .41)]:
                    track = pcbnew.PCB_TRACK(board)
                    track.SetNet(net)
                    track.SetLayer(layer)
                    track.SetWidth(round(width*1e6))
                    track.SetStart(pcbnew.VECTOR2I_MM(a[0]+ox, a[1]+oy))
                    track.SetEnd(pcbnew.VECTOR2I_MM(b[0]+ox, b[1]+oy))
                    board.Add(track)
            for pad_index, xy in enumerate([(1.5, 1.5), (5.5, 5.5), (6.5, 3.25)]):
                fp = pcbnew.FOOTPRINT(board)
                fp.SetReference(f'N{index}_L{layer_index}_P{pad_index}')
                board.Add(fp)
                pad = pcbnew.PAD(fp)
                pad.SetNumber('PAD_NAME_NOT_SPECIAL')
                pad.SetNet(net)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT if pad_index % 2 else pcbnew.PAD_SHAPE_CIRCLE)
                lset = pcbnew.LSET()
                lset.AddLayer(layer)
                pad.SetLayerSet(lset)
                pad.SetSize(pcbnew.VECTOR2I_MM(.7, .7))
                pad.SetPosition(pcbnew.VECTOR2I_MM(xy[0]+ox, xy[1]+oy))
                fp.Add(pad)
        # A single real PTH pad contributes on every enabled layer, exercising
        # the original per-pad cross-layer iteration/addition order as well.
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(f'THROUGH_{index}')
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        pad.SetNumber('T')
        pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.35, .35))
        pad.SetSize(pcbnew.VECTOR2I_MM(.75, .75))
        pad.SetPosition(pcbnew.VECTOR2I_MM(6.7+ox, 6.1+oy))
        fp.Add(pad)
    return board, names


def _assert_dict_arrays_equal(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in actual.items():
        if isinstance(value, dict):
            _assert_dict_arrays_equal(value, expected[key])
        else:
            np.testing.assert_array_equal(value, expected[key])


@pytest.mark.parametrize('seed', range(16))
@pytest.mark.parametrize('active_kind', ['one', 'none', 'all'])
def test_random_native_material_and_active_graph_exactly_equal_legacy(seed, active_kind):
    board, names = _native_fixture(seed)
    active = {names[0]} if active_kind == 'one' else set(names) if active_kind == 'all' else set()
    # Odd grid dimensions exercise packbits padding without synthetic metal.
    grid = th.Grid(-.13, -.07, 8., 7.9, .25 if seed % 2 else .125)
    stackup = {'F.Cu': 1., 'B.Cu': 1.3, 'In1.Cu': .5, 'In2.Cu': .7}
    before = topology._native_epoch(board)
    old = _legacy_raster(board, grid, stackup)
    new = th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS), stackup, active)
    assert topology._native_epoch(board) == before
    for key in ['klat', 'copper_any']:
        np.testing.assert_array_equal(new[key], old[key])
    _assert_dict_arrays_equal(new['layer_copper_mask'], old['layer_copper_mask'])
    for key in ['net_layer_mask', 'net_width_frac', 'net_zone_mask', 'net_pad_mask']:
        _assert_dict_arrays_equal(new[key], {n: v for n, v in old[key].items() if n in active})
    assert new['pad_map'] == old['pad_map']
    assert set(new['inactive_packed']) == set(names) - active
    for net, by_layer in new['inactive_packed'].items():
        for std, packed in by_layer.items():
            assert packed.nbytes == (grid.n+7)//8
            np.testing.assert_array_equal(th._unpack_copper_mask(packed, grid),
                                          old['net_layer_mask'][net][std])
    T = np.arange(grid.n, dtype=float).reshape(grid.ny, grid.nx) + 37.
    expected = {n: float(T[np.logical_or.reduce(list(lm.values()))].max())
                for n, lm in old['net_layer_mask'].items()}
    assert th._stream_per_net_max_temperature(T, new, grid) == expected
    assert new['retention']['peak_inactive_unpacked_layers'] <= 4


@pytest.mark.parametrize('include_traces,area', [(False, True), (True, False), (False, False)])
def test_existing_trace_and_pad_injection_switches_are_unchanged(include_traces, area):
    board, names = _native_fixture(91)
    grid = th.Grid(0, 0, 8, 8, .25)
    stackup = {'F.Cu': 1., 'B.Cu': 0., 'In1.Cu': .5, 'In2.Cu': .5}
    old = _legacy_raster(board, grid, stackup, include_traces, area)
    new = th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS),
        stackup, {names[0]}, include_traces, area)
    np.testing.assert_array_equal(new['klat'], old['klat'])
    np.testing.assert_array_equal(new['copper_any'], old['copper_any'])
    _assert_dict_arrays_equal(new['layer_copper_mask'], old['layer_copper_mask'])


def test_streamed_copper_keeps_small_thermal_reference_solution_exact():
    board, names = _native_fixture(44)
    grid = th.Grid(0, 0, 8, 8, .5)
    stackup = {'F.Cu': 1., 'B.Cu': 1., 'In1.Cu': .5, 'In2.Cu': .5}
    old = _legacy_raster(board, grid, stackup)
    new = th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS), stackup, set())
    Q = np.zeros_like(old['klat'])
    Q[7:9, 7:9] = .1/(4*grid.cell_area_m2)
    a = th._thermal_solve(old['klat'], Q, grid, 50., h_eff=15., nonlinear=False, backend='cpu')
    b = th._thermal_solve(new['klat'], Q, grid, 50., h_eff=15., nonlinear=False, backend='cpu')
    np.testing.assert_array_equal(a, b)
    assert not new['net_layer_mask'] and new['copper_any'].any()
    assert np.any(new['klat'] > th.K_FR4 * th.T_BOARD)


def test_memory_reservation_counts_inactive_material_as_packed_not_missing():
    grid = th.Grid(0, 0, 20, 20, .125)
    pairs = {(f'NET{i}', layer) for i in range(120) for layer in ['F.Cu', 'B.Cu']}
    currents = {'NET0': 1.}
    result = topology._working_memory_reservation(grid, pairs, currents,
                                                  ['F.Cu', 'B.Cu'], topology.LIMITS)
    assert result['geometry_pairs'] == 240
    assert result['active_dense_pairs'] == 2
    assert result['inactive_packed_pairs'] == 238
    assert result['inactive_packed_occupancy_bytes'] == ((grid.n+7)//8)*238
    assert result['active_dense_electrical_bytes'] == grid.n*20*2
    assert result['stream_temporary_bytes'] >= grid.n*(128+2)
    assert result['total_bytes'] < grid.n*(128+20*len(pairs))+grid.n*2*400
    all_active = topology._working_memory_reservation(grid, pairs,
        {f'NET{i}': 1. for i in range(120)}, ['F.Cu', 'B.Cu'], topology.LIMITS)
    assert all_active['active_dense_electrical_bytes'] == grid.n*20*len(pairs)
    assert all_active['total_bytes'] > result['total_bytes']


def test_component_only_screen_is_still_memory_bounded_before_raster():
    board, _ = _native_fixture(2)
    with mock.patch.object(th, '_board_geometry', return_value=(0, 0, 8, 8)):
        result = topology.select_grid(board, th, currents={}, overrides={},
            stackup={'F.Cu': 1., 'B.Cu': 1.}, grid_mm=.25,
            limits={'max_estimated_bytes': 1000})
    assert not result['complete']
    assert result['refusal'] == 'topology_working_memory_limit'
    assert result['working_memory_reservation']['inactive_packed_pairs'] > 0
    assert result['working_memory_reservation']['active_dense_pairs'] == 0


def test_streaming_does_not_renew_expired_deadline():
    board, _ = _native_fixture()
    grid = th.Grid(0, 0, 8, 8, .25)
    with mock.patch.object(th, '_SOLVE_DEADLINE', -1):
        with pytest.raises(th.TimeBudgetExceeded):
            th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS), {}, set())


def test_raster_deadline_is_incomplete_before_temperature_not_a_cool_pass(tmp_path):
    board, _ = _native_fixture(5)
    path = tmp_path/'synthetic-copper.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    before = path.read_bytes()
    with mock.patch.object(th, '_stream_copper_rasters', side_effect=th.TimeBudgetExceeded):
        with mock.patch.object(th, '_thermal_solve', side_effect=AssertionError('called')):
            result = th.solve_board_thermal(str(path), net_currents={},
                stackup_oz={'F.Cu': 1., 'B.Cu': 1.}, grid_mm=.25,
                time_budget_s=30, ambient=50.)
    assert result.meta['operation_complete'] is False
    assert result.meta['field_computed'] is False
    assert result.meta['budget_exhausted'] is True
    assert result.meta['budget_phase'] == 'copper_raster'
    assert result.meta['thermal_iterations_completed'] == 0
    assert result.meta['operation_refusal'] == 'copper_raster_deadline'
    assert path.read_bytes() == before


def test_unnamed_zone_is_counted_and_still_conducts_without_an_electrical_net():
    board, _ = _native_fixture(7)
    for zone in board.Zones():
        zone.SetNetCode(0)
    grid = th.Grid(0, 0, 8, 8, .25)
    stackup = {'F.Cu': 1., 'B.Cu': 1., 'In1.Cu': .5, 'In2.Cu': .5}
    old = _legacy_raster(board, grid, stackup)
    new = th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS), stackup, set())
    assert '' in new['inactive_packed']
    assert ('', 'F.Cu') in topology._geometry_pairs(board, th)
    np.testing.assert_array_equal(new['klat'], old['klat'])
    np.testing.assert_array_equal(new['copper_any'], old['copper_any'])
