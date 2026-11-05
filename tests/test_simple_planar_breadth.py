"""Simple native joins get finite breadth before a fenced anchor's deep maze.

No board name, refdes policy or selected production coordinate is involved.
The full class width, source copper and all receiving gates remain authoritative.
"""
import time
from unittest import mock

import pcbnew
import pytest
import cec_fr as fr
from test_lastmile import _board


def _portfolio_row(rank, distance, common, label):
    return (rank, distance, 0, 1, (0, 0), (1, 1), common,
            frozenset((0,)), frozenset((0,)), None, None,
            {'kind': 'pad', 'tag': label}, {'kind': 'pad'})


def test_planar_schedule_is_finite_nearest_and_preserves_deep_reserved_order():
    via = _portfolio_row(0, 3., frozenset((0,)), 'reserved-via')
    pad = _portfolio_row(1, 2., frozenset((0,)), 'surface-pad')
    remote = _portfolio_row(0, 1., frozenset(), 'no-common-layer')
    source = [via, remote, pad]
    assert fr._simple_planar_pair_schedule(source, 1) == [
        (True, pad), (False, via), (False, remote), (False, pad)]
    assert source == [via, remote, pad]
    assert fr._simple_planar_pair_schedule(source, 0) == [
        (False, row) for row in source]


@pytest.mark.parametrize('common, permitted, expected', [
    ({0, 2, 4, 6, 8, 10}, [6, 2, 0], [6, 2, 0]),
    ({0, 2, 4, 6, 8, 10}, [6, 2, 0, 8], [6, 2, 0, 8]),
    ({0}, [6, 2, 0, 8], [0]),
    ({8}, [6, 2, 0], []),
    ({6, 2}, [6, 6, 2, 0], [6, 2]),
    (set(), [6, 2, 0], []),
])
def test_common_layers_share_bridge_permissions_and_profile_order(common, permitted, expected):
    assert fr._same_layer_route_portfolio(common, permitted, profile_first=True) == expected
    assert fr._same_layer_route_portfolio(common, permitted, profile_first=False) == sorted(common, reverse=True)


@pytest.mark.parametrize('value', [None, 1, 'yes', []])
def test_layer_policy_is_explicit_not_truthy(value):
    with pytest.raises(ValueError, match='native_layer_portfolio_policy'):
        fr._same_layer_route_portfolio({0}, [0], profile_first=value)


@pytest.mark.parametrize('bounded', [False, True])
def test_declared_profile_prefers_real_signal_layer_even_without_new_breadth(bounded):
    board = _board([], edge=(0, 0, 20, 20)); board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, '/SCALAR'); board.Add(net)
    for x in (10, 12):
        via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(x, 10))
        via.SetWidth(600000); via.SetDrill(300000); via.SetNet(net)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    original = fr._guarded_profiled_lastmile_legs
    layers = []
    def checked(*args, **kwargs):
        layers.append(args[4])
        return original(*args, **kwargs)
    with mock.patch.object(fr._fab, 'board_profile_name', return_value='jlcpcb_6l_pofv_signal'), \
            mock.patch.object(fr, '_lastmile_route_layers',
                return_value=[pcbnew.In2_Cu, pcbnew.B_Cu, pcbnew.F_Cu]), \
            mock.patch.object(fr, '_guarded_profiled_lastmile_legs', side_effect=checked):
        result = fr.synthesize_lastmile(board, include_nets={'/SCALAR'},
            max_mm=5., min_w=.2, clearance=.2,
            simple_planar_pairs=4 if bounded else 0, wall_timeout_s=2.)
    assert result['closed'] == 1 and layers == [pcbnew.In2_Cu]
    assert all(t.GetLayer() == pcbnew.In2_Cu for t in board.GetTracks()
               if t.GetClass() == 'PCB_TRACK')


@pytest.mark.parametrize('value', [None, True, -1, 65, 2., '2'])
def test_simple_breadth_limit_is_exact_not_truthy(value):
    board = _board([(10, 10, '/SCALAR')])
    with pytest.raises(ValueError, match='simple_planar_pair_limit'):
        fr.synthesize_lastmile(board, simple_planar_pairs=value)


@pytest.mark.parametrize('value', [None, True, 0, float('inf'), float('nan'), 601])
def test_simple_breadth_requires_finite_shared_work_lease(value):
    board = _board([(10, 10, '/SCALAR')])
    with pytest.raises(ValueError, match='simple_planar_work_lease'):
        fr.synthesize_lastmile(board, simple_planar_pairs=4,
                               wall_timeout_s=value)


def _fenced_access_board(quarter, back):
    # The scalar's remote island has a surface pad at (12,10) and a spanning
    # via at (7,10), connected by retained copper around the north. The new
    # source pad at (10,10) can reach the surface pad directly; the via is
    # fenced by independent copper at x=8.5. Mirror and rotate the entire
    # geometry to ensure this is not one directional placement workaround.
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    def xy(x, y):
        for _ in range(quarter):
            x, y = 20-y, x
        return pcbnew.VECTOR2I(round(x*1e6), round(y*1e6))
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')],
                   edge=(0, 0, 20, 20))
    for fp in board.GetFootprints():
        point = tuple(fp.GetPosition())
        fp.SetPosition(xy(*(v/1e6 for v in point)))
        for pad in fp.Pads():
            layers = pcbnew.LSET(); layers.AddLayer(face)
            pad.SetLayerSet(layers)
    scalar = board.GetNetcodeFromNetname('/SCALAR')
    for start, end in [((12, 10), (14, 10)), ((14, 10), (14, 6)),
                       ((14, 6), (7, 6)), ((7, 6), (7, 10))]:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(xy(*start)); track.SetEnd(xy(*end))
        track.SetLayer(face); track.SetWidth(200000); track.SetNetCode(scalar)
        track.SetLocked(True); board.Add(track)
    via = pcbnew.PCB_VIA(board); via.SetPosition(xy(7, 10))
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNetCode(scalar)
    via.SetLocked(True); board.Add(via)
    foreign = pcbnew.NETINFO_ITEM(board, '/FOREIGN'); board.Add(foreign)
    wall = pcbnew.PCB_TRACK(board); wall.SetStart(xy(8.5, 8.5))
    wall.SetEnd(xy(8.5, 11.5)); wall.SetLayer(face); wall.SetWidth(200000)
    wall.SetNet(foreign); wall.SetLocked(True); board.Add(wall)
    return board


def _snapshot(board):
    return {item.m_Uuid.AsString():
            (item.GetNetname(), item.GetLayer(), item.IsLocked(),
             tuple(item.GetPosition()) if item.GetClass() == 'PCB_VIA'
             else (tuple(item.GetStart()), tuple(item.GetEnd()), item.GetWidth()))
            for item in board.GetTracks()}


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_easy_surface_join_precedes_deep_search_and_preserves_retained_copper(quarter, back):
    board = _fenced_access_board(quarter, back)
    before = _snapshot(board)
    original = fr._guarded_profiled_lastmile_legs
    calls = []
    def checked(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs['canonical_only'] is True
        assert kwargs['allow_maze'] is False
        assert kwargs['start_escape'] is None and kwargs['end_escape'] is None
        return original(*args, **kwargs)
    with mock.patch.object(fr, '_guarded_profiled_lastmile_legs', side_effect=checked):
        result = fr.synthesize_lastmile(board, include_nets={'/SCALAR'},
            min_w=.2, clearance=.2, max_mm=5., simple_planar_pairs=4,
            wall_timeout_s=2., per_net_timeout_s=1.)
    assert result['closed'] == 1 and result['legs'] == 1
    assert result['simple_planar_breadth']['committed'] == 1
    assert result['closed_details'][0]['simple_planar_breadth'] is True
    assert calls
    after = _snapshot(board)
    assert all(after[uid] == row for uid, row in before.items())
    additions = [item for item in board.GetTracks()
                 if item.m_Uuid.AsString() not in before]
    assert len(additions) == 1 and additions[0].GetWidth() == 200000
    assert additions[0].GetClass() == 'PCB_TRACK'
    assert fr.net_connectivity_component_count(
        board, board.GetNetcodeFromNetname('/SCALAR')) == 1


@pytest.mark.parametrize('verdict', [False, None])
def test_simple_proposal_cannot_bypass_field_refusal_or_unknown(verdict):
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')],
                   edge=(0, 0, 20, 20))
    before = _snapshot(board)
    with mock.patch('cec_field_coupling.assess_proposed_route',
            return_value=dict(ok=verdict, complete=verdict is False,
                              reason='synthetic_field_refusal')) as gate:
        result = fr.synthesize_lastmile(board, include_nets={'/SCALAR'},
            min_w=.2, clearance=.2, max_mm=5., maze_max_mm=0.,
            simple_planar_pairs=4, wall_timeout_s=1.,
            per_net_timeout_s=.5, field_guard=True)
    assert gate.called and result['closed'] == 0
    assert result['simple_planar_breadth']['committed'] == 0
    assert _snapshot(board) == before


def test_simple_proposal_cannot_bypass_route_quality_refusal():
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')],
                   edge=(0, 0, 20, 20))
    with mock.patch('cec_route_quality.assess_proposed_route',
            return_value=dict(ok=False, complete=True, issues=['synthetic_bad_craft'])) as gate:
        result = fr.synthesize_lastmile(board, include_nets={'/SCALAR'},
            min_w=.2, clearance=.2, max_mm=5., maze_max_mm=0.,
            simple_planar_pairs=4, wall_timeout_s=1., per_net_timeout_s=.5)
    assert gate.called and result['closed'] == 0 and not list(board.GetTracks())


def test_simple_probes_share_expiry_and_do_not_emit_partial_copper():
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')])
    def expires(*args, **kwargs):
        assert kwargs['canonical_only'] is True
        time.sleep(.012)
        return None
    with mock.patch.object(fr, '_guarded_profiled_lastmile_legs', side_effect=expires):
        result = fr.synthesize_lastmile(board, include_nets={'/SCALAR'},
            simple_planar_pairs=1, wall_timeout_s=.01, per_net_timeout_s=.01)
    assert result['closed'] == 0 and result['timed_out'] is True
    assert not list(board.GetTracks())
    assert result['simple_planar_breadth']['no_path_proof'] is False


@pytest.mark.parametrize('fault', [None, 1, 'yes', True])
def test_canonical_only_policy_is_explicit_and_cannot_request_maze(fault):
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')])
    with pytest.raises(ValueError, match='canonical_only_without_maze'):
        fr._guarded_profiled_lastmile_legs(board, pcbnew.VECTOR2I_MM(10, 10),
            pcbnew.VECTOR2I_MM(12, 10), 200000, pcbnew.F_Cu, 200000,
            board.GetNetcodeFromNetname('/SCALAR'), lambda *_: True,
            canonical_only=fault, allow_maze=True)


def test_canonical_only_refusal_does_not_enumerate_channels_or_maze():
    board = _board([(10, 10, '/SCALAR'), (7, 10, '/SCALAR')],
                   edge=(0, 0, 20, 20))
    foreign = pcbnew.NETINFO_ITEM(board, '/FOREIGN'); board.Add(foreign)
    wall = pcbnew.PCB_TRACK(board); wall.SetNet(foreign); wall.SetWidth(200000)
    wall.SetLayer(pcbnew.F_Cu); wall.SetStart(pcbnew.VECTOR2I_MM(8.5, 0))
    wall.SetEnd(pcbnew.VECTOR2I_MM(8.5, 20)); board.Add(wall)
    with mock.patch('cec_maze_channels.native_obstacle_boxes',
            side_effect=AssertionError('no channel enumeration in cheap tier')):
        result = fr._guarded_profiled_lastmile_legs(board, pcbnew.VECTOR2I_MM(10, 10),
            pcbnew.VECTOR2I_MM(7, 10), 200000, pcbnew.F_Cu, 200000,
            board.GetNetcodeFromNetname('/SCALAR'), lambda *_: True,
            canonical_only=True, allow_maze=False,
            deadline_monotonic=time.monotonic()+1.)
    assert result is None


def test_excluded_net_and_disabled_receipt_remain_unchanged():
    board = _board([(10, 10, '/SCALAR'), (12, 10, '/SCALAR')])
    result = fr.synthesize_lastmile(board, exclude_nets={'/SCALAR'},
        simple_planar_pairs=4, wall_timeout_s=1.)
    assert result['simple_planar_breadth']['attempted'] == 0
    assert result['closed'] == 0 and not list(board.GetTracks())
    disabled = fr.synthesize_lastmile(board, exclude_nets={'/SCALAR'})
    assert 'simple_planar_breadth' not in disabled


@pytest.mark.parametrize('budget, expected', [(None, 0), (20., 16), (90., 16), (601., 0)])
def test_normal_residual_worker_enables_breadth_only_with_supported_work_lease(budget, expected):
    import cec_certificate_repair as repair
    board = mock.Mock()
    with mock.patch.object(repair.pcbnew, 'LoadBoard', return_value=board), \
            mock.patch.object(fr, '_project_netclass_resolver', return_value=None), \
            mock.patch.object(fr, 'synthesize_lastmile', return_value={'closed': 0}) as worker:
        repair._lastmile_worker('synthetic', ('/SCALAR',), 8, 4,
                                 wall_timeout_s=budget)
    assert worker.call_args.kwargs['simple_planar_pairs'] == expected
    assert worker.call_args.kwargs['wall_timeout_s'] == budget
    assert worker.call_args.kwargs['include_nets'] == {'/SCALAR'}


def test_normal_canonical_worker_enables_simple_breadth_without_extra_budget():
    import cec_certificate_repair as repair
    board = mock.Mock()
    with mock.patch.object(repair.pcbnew, 'LoadBoard', return_value=board), \
            mock.patch.object(fr, '_project_netclass_resolver', return_value=None), \
            mock.patch.object(fr, 'synthesize_lastmile', return_value={'closed': 0}) as worker, \
            mock.patch.dict('os.environ', {'CEC_CERTIFICATE_CANONICAL_NET_TIMEOUT_S': '8'}):
        repair._broad_canonical_worker('synthetic', ('/SCALAR',))
    policy = worker.call_args.kwargs
    assert policy['simple_planar_pairs'] == 16
    assert policy['wall_timeout_s'] == policy['per_net_timeout_s'] == 6.
    assert policy['bridge_fast'] is True and policy['maze_max_mm'] == 0.


def test_normal_staged_worker_enables_breadth_inside_both_original_leases():
    import cec_certificate_repair as repair
    board = mock.Mock(); board.GetNetcodeFromNetname.return_value = 1
    with mock.patch.object(repair.pcbnew, 'LoadBoard', return_value=board), \
            mock.patch.object(fr, '_project_netclass_resolver', return_value=None), \
            mock.patch.object(fr, 'net_connectivity_component_count', return_value=2), \
            mock.patch.object(fr, 'synthesize_lastmile', return_value={'closed': 0}) as worker:
        repair._lastmile_worker('synthetic', ('/SCALAR',), 8, 4,
                                 wall_timeout_s=20., prefer_bridge=True)
    assert len(worker.call_args_list) == 2
    assert all(call.kwargs['simple_planar_pairs'] == 16 for call in worker.call_args_list)
    assert all(0 < call.kwargs['wall_timeout_s'] <= 20 for call in worker.call_args_list)


@pytest.mark.parametrize('configured', [0, 3, 16, 64])
def test_critical_control_stage_exposes_parameter_not_board_specific_policy(configured):
    from types import SimpleNamespace
    import cec_synth_pipeline as pipeline
    board = mock.Mock()
    bounds = mock.Mock(); bounds.GetWidth.return_value = 30000000
    bounds.GetHeight.return_value = 40000000
    board.GetBoardEdgesBoundingBox.return_value = bounds
    board.GetFootprints.return_value = []
    board.GetNetcodeFromNetname.return_value = 1
    cfg = SimpleNamespace(params={'critical_control_simple_planar_pairs': configured})
    with mock.patch.object(pcbnew, 'LoadBoard', return_value=board), \
            mock.patch.object(pcbnew, 'SaveBoard'), \
            mock.patch('cec_zone_fill.fill', return_value=True), \
            mock.patch.object(fr, '_project_netclass_resolver', return_value=None), \
            mock.patch.object(fr, 'net_connectivity_component_count', return_value=1), \
            mock.patch.object(fr, 'synthesize_lastmile', return_value={'closed': 0}) as worker:
        pipeline._repair_declared_control_lastmile('synthetic', ['/SCALAR'],
                                                   cfg=cfg, wall_timeout_s=10.)
    assert worker.call_args.kwargs['simple_planar_pairs'] == configured
    assert worker.call_args.kwargs['wall_timeout_s'] == 10.


@pytest.mark.parametrize('configured', [True, None, -1, 65, '16'])
def test_critical_stage_refuses_invalid_policy_before_route_mutation(configured):
    from types import SimpleNamespace
    import cec_synth_pipeline as pipeline
    board = mock.Mock()
    bounds = mock.Mock(); bounds.GetWidth.return_value = 30000000
    bounds.GetHeight.return_value = 40000000
    board.GetBoardEdgesBoundingBox.return_value = bounds
    board.GetFootprints.return_value = []
    cfg = SimpleNamespace(params={'critical_control_simple_planar_pairs': configured})
    with mock.patch.object(pcbnew, 'LoadBoard', return_value=board), \
            mock.patch.object(fr, 'synthesize_lastmile') as worker:
        with pytest.raises(ValueError, match='simple_planar_pair_limit'):
            pipeline._repair_declared_control_lastmile('synthetic', ['/SCALAR'],
                                                       cfg=cfg, wall_timeout_s=10.)
    worker.assert_not_called()
