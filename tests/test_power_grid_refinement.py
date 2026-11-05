"""Bounded per-net precision must retain awarded copper and physical rules."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

import cec_slab_pour as slab


@pytest.mark.parametrize('cell,distance,cells', [(.8, None, 4), (.4, 3.2, 8),
                                               (.2, 3.2, 16), (.2, 2., 10)])
def test_escape_distance_does_not_shrink_with_resolution(cell, distance, cells):
    assert slab._terminal_escape_cells(cell, distance) == cells


def test_refinement_budget_is_checked_before_allocating_fine_masks():
    grid = SimpleNamespace(nx=100, ny=100, cell=.8)
    assert slab._power_refinement_schedule(grid, 2, 50000) == [
        dict(cell_mm=.4, cells_upper_bound=40804, admitted=True),
        dict(cell_mm=.2, cells_upper_bound=163216, admitted=False)]
    assert slab._power_refinement_schedule(grid, 0, 50000) == []
    for levels, budget in [(-1, 3), (5, 3), (1.5, 3), (True, 3), (2, 0)]:
        with pytest.raises(ValueError):
            slab._power_refinement_schedule(grid, levels, budget)


def scene(monkeypatch, names, offset=0):
    class Net:
        def __init__(self, name): self.name = name
        def GetNetname(self): return self.name

    class Board:
        def GetNetInfo(self):
            return SimpleNamespace(NetsByNetcode=lambda: {
                i + 1: Net(name) for i, name in enumerate(names)})
        def GetTracks(self): return []

    class Grid:
        def __init__(self, board, cell):
            self.cell = cell
            self.x0 = self.y0 = offset
            self.nx, self.ny = 18, 8

    calls = []

    def prep(board, net, nc, layers, grid, **kw):
        calls.append((net, grid.cell, kw))
        shape = (grid.ny, grid.nx)
        free = np.ones(shape, bool)
        # First allocation fits at coarse precision; second requires a finer
        # mask. The next net must see that fine allocation in its ledger too.
        if net == names[1] and grid.cell > .4:
            free[:, 8] = False
        anchors = np.zeros(shape, bool)
        labels = np.zeros(shape, int)
        anchors[4, 2] = anchors[4, 15] = True
        labels[4, 2], labels[4, 15] = 1, 2
        return dict(layers=['F.Cu'], passable={'F.Cu': free},
                    anchors={'F.Cu': anchors}, clab=labels, nclusters=2,
                    rcells={'F.Cu': 1}, reqw={'F.Cu': .6},
                    foreign={'F.Cu': ~free}, bias_fn=lambda *_: 1.,
                    bridge_forbidden=np.zeros(shape, bool)), None

    monkeypatch.setattr(slab, 'Grid', Grid)
    monkeypatch.setattr(slab, 'shunt_neighborhoods', lambda *_: [])
    monkeypatch.setattr(slab, '_board_thermal_config', lambda *_: None)
    monkeypatch.setattr(slab, '_prep_overunder_net', prep)
    monkeypatch.setattr(slab, '_overunder_bridge_geometry', lambda *_: {})
    monkeypatch.setattr(slab, 'terminal_cluster_members', lambda *a, **kw: [])
    monkeypatch.setattr(slab, '_clip_pours_around_generated_vias',
                        lambda rows, *a, **kw: (rows, 0))
    monkeypatch.setattr(slab, '_clip_pours_around_foreign_copper',
                        lambda board, rows, **kw: (rows, 0))
    monkeypatch.setattr(slab, 'prune_unseeded_pour_components',
                        lambda board, rows, vias: (rows, {}))
    return Board(), calls


@pytest.mark.parametrize('names,offset', [(['first', 'second', 'third'], 0),
                                        (['x', 'y', 'z'], 37)])
def test_only_failed_net_refines_and_each_reservation_keeps_its_grid(monkeypatch, names, offset):
    board, calls = scene(monkeypatch, names, offset)
    collect = {}
    prior = [dict(net='external', layer='B.Cu', polygon=[(0,0),(1,0),(1,1),(0,1)])]
    prior_vias = [dict(net='external', x_mm=100., y_mm=100., radius_mm=.3)]
    pours, vias, report = slab.synthesize_overunder_pours(
        board, [dict(net=n, layer='F.Cu') for n in names], collect=collect,
        reserved_pours=prior, reserved_vias=prior_vias, grid_refinement_levels=2)
    assert not vias and all(report[n]['path_found'] for n in names)
    assert [(net, cell) for net, cell, _ in calls] == [
        (names[0], .8), (names[1], .8), (names[1], .4), (names[2], .8)]
    # The recursive solve receives the complete awarded geometry and original
    # current/clearance contract. No coarse winner is replaced to help a loser.
    awarded = [row for row in pours if row['net'] == names[0]]
    assert awarded
    assert all(row in calls[2][2]['generated_pours'] for row in awarded)
    assert prior[0] in calls[2][2]['generated_pours']
    assert prior_vias[0] in calls[2][2]['generated_vias']
    assert calls[2][2]['terminal_escape_mm'] == 3.2
    assert calls[2][2]['clearance_mm'] == .3
    assert collect[names[0]]['grid'].cell == .8
    assert collect[names[1]]['grid'].cell == .4
    assert collect[names[2]]['grid'].cell == .8
    assert report[names[1]]['selected_cell_mm'] == .4
    json.dumps(report)
    for net in names:
        route = collect[net]
        polygons, ok = slab.reservation_from_search(
            net, route['ok'], route['path_cells'], route['bridges'],
            route['rcells'], route['foreign'], route['grid'],
            terminal_anchors=route['anchors'])
        assert ok and polygons


def test_exhausted_refinement_stays_unrouted_without_touching_previous_winner(monkeypatch):
    names = ['ok', 'blocked', 'next']
    board, calls = scene(monkeypatch, names)
    pours, _, report = slab.synthesize_overunder_pours(
        board, [dict(net=n) for n in names], grid_refinement_levels=2,
        max_refinement_cells=1)
    assert report['ok']['path_found'] and report['next']['path_found']
    assert not report['blocked']['path_found']
    assert not any(row['net'] == 'blocked' for row in pours)
    assert len(calls) == 3
    assert report['blocked']['grid_refinement'][0]['stop_reason'] == 'grid_cell_budget_exhausted'


def test_bridge_refinement_exhaustion_remains_fatal_and_serializable(monkeypatch):
    names = ['ok', 'blocked']
    board, _ = scene(monkeypatch, names)
    original = slab.synthesize_overunder_pours

    def refuse(*args, **kwargs):
        raise slab.BridgeSearchRefused('blocked', {'refusals': ['native_field_refused']}, {})

    monkeypatch.setattr(slab, 'synthesize_overunder_pours', refuse)
    with pytest.raises(slab.BridgeSearchRefused) as error:
        original(board, [dict(net=n) for n in names], grid_refinement_levels=2)
    assert len(error.value.evidence['grid_refinement']) == 2
    json.dumps(error.value.evidence)
    assert 'grid_refinement' in str(error.value)


def test_unexpected_errors_cannot_be_relabelled_as_no_path(monkeypatch):
    board, _ = scene(monkeypatch, ['ok', 'blocked'])
    original = slab.synthesize_overunder_pours

    def fail(*args, **kwargs):
        raise RuntimeError('invalid exact copper')

    monkeypatch.setattr(slab, 'synthesize_overunder_pours', fail)
    with pytest.raises(RuntimeError, match='invalid exact copper'):
        original(board, [dict(net='blocked')], grid_refinement_levels=2)
