"""A layer failure is not authority to starve the other native layers."""
import time

import pcbnew
import pytest

import cec_field_coupling as field
import cec_field_search as search
import cec_fr as fr
from test_lastmile import _board


@pytest.mark.parametrize('quarter', [0, 1, 2, 3])
def test_short_hops_cannot_hide_a_long_parallel_run(quarter):
    board = _board([(10, 10, '/PWM'), (14, 10, '/PWM')], edge=(4, 4, 20, 20))
    net = pcbnew.NETINFO_ITEM(board, '/SENSE'); board.Add(net)
    victim = pcbnew.PCB_TRACK(board); victim.SetNet(net)
    victim.SetStart(pcbnew.VECTOR2I_MM(10, 10.8)); victim.SetEnd(pcbnew.VECTOR2I_MM(14, 10.8))
    victim.SetWidth(200000); victim.SetLayer(pcbnew.F_Cu); board.Add(victim)
    center = pcbnew.VECTOR2I_MM(12, 12)
    for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
        item.Rotate(center, pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
    first, last = [fp.GetPosition() for fp in sorted(board.GetFootprints(), key=lambda f:f.GetReference())]
    guard = search.PlanarSearchGuard(board, '/PWM')
    assert not guard(first, last, 200000, pcbnew.F_Cu)
    saved = (tuple(victim.GetStart()), tuple(victim.GetEnd()), victim.GetNetCode())
    legs = fr._maze_lastmile_legs(board, first, last, 200000, pcbnew.F_Cu,
        200000, board.GetNetcodeFromNetname('/PWM'),
        lambda a,b,half: guard(a,b,2*int(half)+1,pcbnew.F_Cu),
        grid_mm=.25, margin_mm=1.5, deadline_monotonic=time.monotonic()+2.)
    # The old maze returned the long forbidden straight run after its short
    # hops all passed. A bounded alternate result is allowed only if every
    # actual manufactured run satisfies the same predicate.
    assert legs is None or all(guard(a,b,w,pcbnew.F_Cu) for a,b,w in legs)
    assert saved == (tuple(victim.GetStart()), tuple(victim.GetEnd()), victim.GetNetCode())


@pytest.mark.parametrize('back,quarter', [(False,0), (False,1), (True,2), (True,3)])
def test_run_aware_maze_finds_a_real_detour_instead_of_only_vetoing_output(back, quarter):
    board = _board([(10,10,'/PWM'), (14,10,'/PWM')], edge=(4,4,20,20))
    net = pcbnew.NETINFO_ITEM(board, '/SENSE'); board.Add(net)
    victim = pcbnew.PCB_TRACK(board); victim.SetNet(net)
    victim.SetStart(pcbnew.VECTOR2I_MM(10,10.8)); victim.SetEnd(pcbnew.VECTOR2I_MM(14,10.8))
    victim.SetWidth(200000); victim.SetLayer(pcbnew.F_Cu); board.Add(victim)
    origin = pcbnew.VECTOR2I_MM(12,12)
    for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
        if back: item.Flip(origin, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        item.Rotate(origin, pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
    start, end = [fp.GetPosition() for fp in sorted(board.GetFootprints(), key=lambda f:f.GetReference())]
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    guard = search.PlanarSearchGuard(board, '/PWM')
    legs = fr._maze_lastmile_legs(board, start, end, 200000, layer, 200000,
        board.GetNetcodeFromNetname('/PWM'), lambda a,b,half: fr._edge_leg_clear(board,a,b,half),
        run_guard=lambda a,b,width: guard(a,b,width,layer),
        grid_mm=.25, margin_mm=1.5, deadline_monotonic=time.monotonic()+2.)
    assert legs and len(legs) > 1
    assert all(guard(a,b,w,layer) for a,b,w in legs)
    for a,b,width in legs:
        item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet('/PWM'))
        item.SetStart(a);item.SetEnd(b);item.SetWidth(width);item.SetLayer(layer);board.Add(item)
    assert field.field_coupling_summary('', board=board)['ok']


def test_multilayer_maze_keeps_parallel_run_context_and_native_endpoint_layers():
    board = _board([(10,10,'/PWM'), (14,10,'/PWM')], edge=(4,4,20,20))
    net = pcbnew.NETINFO_ITEM(board, '/SENSE'); board.Add(net)
    victim = pcbnew.PCB_TRACK(board); victim.SetNet(net)
    victim.SetStart(pcbnew.VECTOR2I_MM(10,10.8)); victim.SetEnd(pcbnew.VECTOR2I_MM(14,10.8))
    victim.SetWidth(200000); victim.SetLayer(pcbnew.F_Cu); board.Add(victim)
    guard = search.PlanarSearchGuard(board, '/PWM')
    operations = fr._multilayer_maze_lastmile_ops(board,
        pcbnew.VECTOR2I_MM(10,10), pcbnew.VECTOR2I_MM(14,10),
        board.GetNetcodeFromNetname('/PWM'), [pcbnew.F_Cu, pcbnew.B_Cu], 200000,
        lambda a,b,half: fr._edge_leg_clear(board,a,b,half),
        width_for_layer=lambda _layer: 200000,
        start_layers=[pcbnew.F_Cu], end_layers=[pcbnew.F_Cu],
        grid_mm=.25, margin_mm=1.5, max_vias=0, planar_guard=guard,
        deadline_monotonic=time.monotonic()+2.)
    assert operations and len(operations) > 1
    assert all(op[0]=='trk' and op[4]==pcbnew.F_Cu
        and guard(op[1],op[2],op[3],op[4]) for op in operations)


@pytest.mark.parametrize('reverse', [False, True])
def test_second_layer_receives_a_canonical_trial_before_first_layer_maze(monkeypatch, reverse):
    board = _board([(8, 8, '/OPAQUE'), (12, 8, '/OPAQUE')], edge=(3, 3, 18, 18))
    board.SetCopperLayerCount(6)
    layers = [pcbnew.In2_Cu, pcbnew.B_Cu]
    if reverse: layers.reverse()
    start, end = (8000000, 8000000), (12000000, 8000000)
    attempted = []
    native = fr._guarded_lastmile_legs
    def route(*args, **kwargs):
        layer = args[4]; attempted.append((layer, kwargs['allow_maze']))
        if layer == layers[0]:
            assert not kwargs['allow_maze'], 'first layer consumed depth before other layer breadth'
            return None
        return native(*args, **kwargs)
    monkeypatch.setattr(fr, '_guarded_lastmile_legs', route)
    # These endpoints already own both layers; neither a mocked legal barrel
    # nor a relaxed via dimension is needed to test the scheduling contract.
    accepted = []
    def receiver(ops):
        accepted.append(ops)
        return True
    result = fr._lastmile_bridge(board, start, set(layers), end, set(layers),
        200000, board.GetNetcodeFromNetname('/OPAQUE'), layers, 200000,
        allow_maze=True, seat_limit=4, ops_ok=receiver,
        deadline_monotonic=time.monotonic()+2.)
    assert result and attempted == [(layers[0], False), (layers[1], False)]
    assert accepted and all(op[4] == layers[1] for op in result)


def test_first_working_canonical_route_keeps_its_native_geometry():
    board = _board([(8, 8, '/OPAQUE'), (12, 8, '/OPAQUE')], edge=(3, 3, 18, 18))
    layers = [pcbnew.In2_Cu, pcbnew.B_Cu]
    result = fr._lastmile_bridge(board, (8000000,8000000), set(layers),
        (12000000,8000000), set(layers), 200000,
        board.GetNetcodeFromNetname('/OPAQUE'), layers, 200000,
        allow_maze=True, deadline_monotonic=time.monotonic()+2.)
    assert len(result) == 1 and result[0][4] == layers[0]
    assert tuple(result[0][1]) == (8000000,8000000)
    assert tuple(result[0][2]) == (12000000,8000000)


def test_deep_seat_rank_is_interleaved_across_actual_layers(monkeypatch):
    board = _board([(8,8,'/OPAQUE'), (12,8,'/OPAQUE')], edge=(3,3,18,18))
    board.SetCopperLayerCount(6)
    layers = [pcbnew.In2_Cu, pcbnew.B_Cu]
    seen = []
    native = fr._guarded_lastmile_legs
    def route(*args, **kwargs):
        layer = args[4]; deep = kwargs['allow_maze']; seen.append((layer, deep))
        if not deep or layer == layers[0]: return None
        return native(*args, **kwargs)
    monkeypatch.setattr(fr, '_guarded_lastmile_legs', route)
    diagnostics = {}
    result = fr._lastmile_bridge(board, (8000000,8000000), set(layers),
        (12000000,8000000), set(layers), 200000,
        board.GetNetcodeFromNetname('/OPAQUE'), layers, 200000,
        allow_maze=True, deadline_monotonic=time.monotonic()+2., diagnostics=diagnostics)
    assert result and seen == [(layers[0],False), (layers[1],False),
                               (layers[0],True), (layers[1],True)]
    assert diagnostics['counters']['single_layer_pair_trials'] == 4
    assert all(row['pair_trials'] == 1 for row in diagnostics['layers'])


@pytest.mark.parametrize('breadth', [0, True, 17, float('nan')])
def test_layer_portfolio_remains_explicitly_bounded(breadth):
    board = _board([(8,8,'/OPAQUE'), (12,8,'/OPAQUE')])
    with pytest.raises(ValueError, match='finite bridge layer breadth'):
        fr._lastmile_bridge(board, (8000000,8000000), {pcbnew.F_Cu},
            (12000000,8000000), {pcbnew.F_Cu}, 200000,
            board.GetNetcodeFromNetname('/OPAQUE'), [pcbnew.B_Cu], 200000,
            layer_breadth_pairs=breadth)
