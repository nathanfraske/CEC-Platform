"""Lazy layer arrays preserve the frozen eager field equations exactly."""
from unittest import mock

import numpy as np
import pytest

import cec_thermal2d as th


def eager_joule(sol, grid, width_frac=None, oz_by_layer=None):
    """Frozen pre-fix implementation, retained only as a differential control."""
    V = sol['V']; nodes = sol['nodes']; sheetR = sol['sheetR']
    width_frac = width_frac or {}
    oz_by_layer = oz_by_layer or {}
    q, total, maxK, maxJ = {}, 0., 0., 0.
    for a, b, R, lid in sol['links']:
        dV = V[a] - V[b]
        I_link = dV / R
        P = I_link * I_link * R
        total += P
        for nd in (a, b):
            l2, c = nodes[nd]
            iy, ix = divmod(c, grid.nx)
            q.setdefault(l2, np.zeros((grid.ny, grid.nx)))
            q[l2][iy, ix] += .5 * P / grid.cell_area_m2
        if lid is not None:
            K = abs(I_link) / grid.cell_m
            if K > maxK:
                maxK = K
            oz = oz_by_layer.get(lid, 1.)
            t_cu = max(oz, 1e-6) * th.OZ_M
            ia, _ = nodes[a]; ya, xa = divmod(nodes[a][1], grid.nx)
            yb, xb = divmod(nodes[b][1], grid.nx)
            wfa = wfb = 1.
            wm = width_frac.get(lid)
            if wm is not None:
                wfa = wm[ya, xa] if wm[ya, xa] > 0 else 1.
                wfb = wm[yb, xb] if wm[yb, xb] > 0 else 1.
            t_eff = t_cu * max(min(wfa, wfb), 1e-3)
            J = K / t_eff
            if J > maxJ:
                maxJ = J
    return q, maxK/1e3, maxJ/1e6, total


def eager_current(sol, grid, width_frac=None, oz_by_layer=None,
                  total_current_A=0., net=''):
    """Frozen eager spatial-map equations, including all barrel records."""
    V, nodes = sol['V'], sol['nodes']
    width_frac, oz_by_layer = width_frac or {}, oz_by_layer or {}
    maps, records = {}, []
    denom = max(abs(float(total_current_A)), 1e-12)
    for a, b, R, lid in sol['links']:
        dV = float(V[a] - V[b])
        current = dV / R
        abs_current = abs(current)
        la, ca = nodes[a]; lb, cb = nodes[b]
        ya, xa = divmod(ca, grid.nx); yb, xb = divmod(cb, grid.nx)
        x_mm = grid.xmin + ((xa+xb)/2.+.5)*grid.grid_mm
        y_mm = grid.ymin + ((ya+yb)/2.+.5)*grid.grid_mm
        power_W = current*current*R
        if lid is None:
            records.append(dict(net=net, kind='barrel',
                layer='%s->%s' % (th.STD_CU_LAYERS.get(la, str(la)),
                                  th.STD_CU_LAYERS.get(lb, str(lb))),
                x_mm=x_mm, y_mm=y_mm, current_A=abs_current,
                current_share=abs_current/denom, joule_W=power_W,
                J_A_per_mm2=None, effective_width_mm=None))
            continue
        wm = width_frac.get(lid)
        wfa = wfb = 1.
        if wm is not None:
            wfa = float(wm[ya, xa]) if wm[ya, xa] > 0 else 1.
            wfb = float(wm[yb, xb]) if wm[yb, xb] > 0 else 1.
        frac = max(min(wfa, wfb), 1e-3)
        width_mm = grid.grid_mm*frac
        thickness_mm = max(float(oz_by_layer.get(lid, 1.)), 1e-6)*th.OZ_M*1e3
        area_mm2 = max(width_mm*thickness_mm, 1e-12)
        J = abs_current/area_mm2
        std = th.STD_CU_LAYERS.get(lid, str(lid))
        field = maps.setdefault(std, np.zeros((grid.ny, grid.nx)))
        field[ya, xa] = max(field[ya, xa], J)
        field[yb, xb] = max(field[yb, xb], J)
        records.append(dict(net=net, kind='sheet', layer=std, x_mm=x_mm, y_mm=y_mm,
            orientation='x' if ya == yb else 'y', current_A=abs_current,
            current_share=abs_current/denom, joule_W=power_W, J_A_per_mm2=J,
            effective_width_mm=width_mm, copper_thickness_mm=thickness_mm))
    return maps, records


def graph_fixture(seed=0, repeats=1, grid=None):
    rng = np.random.default_rng(seed)
    grid = grid or th.Grid(-1.125, 7.25, 3.125, 10.875, .125)
    # Real graph schema: planar edges and physical-layer barrel edges.
    nodes = [(layer, cell) for layer in (0, 4, 2)
             for cell in (grid.idx(2, 2), grid.idx(3, 2), grid.idx(3, 3))]
    links = []
    for offset, layer in ((0, 0), (3, 4), (6, 2)):
        links += [(offset, offset+1, .003, layer),
                  (offset+1, offset+2, .007, layer)]
    links += [(1, 4, .011, None), (4, 7, .013, None)]
    # Repetitions stress allocation count, not a proposed physical PCB graph.
    sol = dict(nodes=nodes, links=links*repeats, V=rng.normal(0, .01, len(nodes)), sheetR={})
    widths = {layer: rng.choice([0., 1e-4, .2, .7, 1.], size=(grid.ny, grid.nx))
              for layer in (0, 4, 2)}
    return grid, sol, widths, {0: 1., 4: .5, 2: 1.3}


def same_maps(a, b):
    assert a.keys() == b.keys()
    for layer in a:
        assert a[layer].dtype == b[layer].dtype == np.dtype('float64')
        np.testing.assert_array_equal(a[layer], b[layer])


@pytest.mark.parametrize('seed', range(12))
@pytest.mark.parametrize('reverse', [False, True])
def test_exact_sheet_barrel_width_and_record_parity(seed, reverse):
    grid, sol, widths, oz = graph_fixture(seed, repeats=3)
    if reverse:
        sol['links'] = [(b, a, resistance, layer)
                        for a, b, resistance, layer in reversed(sol['links'])]
    original_v = sol['V'].copy()
    original_links = list(sol['links'])
    old = eager_joule(sol, grid, widths, oz)
    new = th._joule_from_solution(sol, grid, widths, oz)
    same_maps(old[0], new[0])
    assert old[1:] == new[1:]
    old_j = eager_current(sol, grid, widths, oz, 1.1, 'RENAMED')
    new_j = th._current_field_from_solution(sol, grid, widths, oz, 1.1, 'RENAMED')
    same_maps(old_j[0], new_j[0])
    assert old_j[1] == new_j[1]
    np.testing.assert_array_equal(sol['V'], original_v)
    assert sol['links'] == original_links


@pytest.mark.parametrize('kind', ['mixed', 'barrel_only', 'empty', 'zero_current'])
def test_allocate_exactly_one_array_per_new_layer(kind):
    grid, sol, widths, oz = graph_fixture(13, repeats=100)
    if kind == 'barrel_only':
        sol['links'] = [v for v in sol['links'] if v[3] is None]
    elif kind == 'empty':
        sol['links'] = []
    elif kind == 'zero_current':
        sol['V'].fill(0.)
    endpoint_layers = {sol['nodes'][node][0] for a, b, _, _ in sol['links'] for node in (a, b)}
    sheet_layers = {th.STD_CU_LAYERS.get(layer, str(layer))
                    for _, _, _, layer in sol['links'] if layer is not None}
    zeros = np.zeros
    with mock.patch.object(th.np, 'zeros', wraps=zeros) as allocate:
        q = th._joule_from_solution(sol, grid, widths, oz)
        assert allocate.call_count == len(endpoint_layers)
        assert all(c.args == ((grid.ny, grid.nx),) and not c.kwargs for c in allocate.call_args_list)
    with mock.patch.object(th.np, 'zeros', wraps=zeros) as allocate:
        eager_joule(sol, grid, widths, oz)
        assert allocate.call_count == 2*len(sol['links'])
    with mock.patch.object(th.np, 'zeros', wraps=zeros) as allocate:
        maps, _ = th._current_field_from_solution(sol, grid, widths, oz)
        assert allocate.call_count == len(sheet_layers)
    assert set(q[0]) == endpoint_layers
    assert set(maps) == sheet_layers


@pytest.mark.parametrize('quarter_turn', range(4))
@pytest.mark.parametrize('phase', [(0., 0.), (.0625, .0625)])
def test_native_contact_graph_fields_and_energy_remain_exact(quarter_turn, phase):
    from test_thermal_raster_topology import _board
    import cec_thermal_raster_topology as topology
    board, _, _ = _board(quarter_turn, phase)
    before = topology._native_epoch(board)
    grid = th.Grid(*th._board_geometry(board), .125)
    name = 'RENAMED_NATIVE_RAIL'
    with mock.patch.object(th, '_SOLVE_DEADLINE', None):
        raster = th._stream_copper_rasters(board, grid, dict(th.STD_CU_LAYERS),
            {'F.Cu': 1., 'B.Cu': 1.}, {name})
        src = th._terminal_cells_for_refs(raster['pad_map'], name, ['SOURCE_X'])
        sink = th._terminal_cells_for_refs(raster['pad_map'], name, ['LOAD_Y'])
        lid = {v: k for k, v in th.STD_CU_LAYERS.items()}
        masks = {lid[s]: m for s, m in raster['net_layer_mask'][name].items()}
        widths = {lid[s]: m for s, m in raster['net_width_frac'][name].items()}
        oz = {phys: 1. for phys in masks}
        sol = th._solve_net_electrical(masks, {}, [(lid[s], c) for s, c in src],
            [(lid[s], c) for s, c in sink], 1.1, grid, oz, {'F.Cu': 0.}, 25e-6,
            width_frac=widths, backend='cpu')
    assert sol is not None
    old = eager_joule(sol, grid, widths, oz)
    new = th._joule_from_solution(sol, grid, widths, oz)
    same_maps(old[0], new[0])
    assert old[1:] == new[1:]
    assert new[3] == pytest.approx(sol['accounting']['terminal_work_W'], rel=1e-8)
    assert sum(v.sum()*grid.cell_area_m2 for v in new[0].values()) == pytest.approx(new[3])
    old_map = eager_current(sol, grid, widths, oz, 1.1, name)
    new_map = th._current_field_from_solution(sol, grid, widths, oz, 1.1, name)
    same_maps(old_map[0], new_map[0])
    assert old_map[1] == new_map[1]
    assert topology._native_epoch(board) == before
