"""Exact via-repair target scope survives planning, execution and admission."""
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import patch

import pcbnew
import pytest
import cec_certificate_repair as repair
from cec_native_items import discard_items


def native_fixture(tmp_path, offset=0, names=('A17', 'B92')):
    from test_local_copper_cell import native_cell
    board, fps, internal, external, _, _ = native_cell(offset=offset, names=names)
    discard_items(board, internal)
    for a, b in (((0, 0), (30, 0)), ((30, 0), (30, 30)),
                 ((30, 30), (0, 30)), ((0, 30), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(a[0]+offset, a[1]+offset))
        edge.SetEnd(pcbnew.VECTOR2I_MM(b[0]+offset, b[1]+offset))
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(pcbnew.FromMM(.05))
        board.Add(edge)
    net = pcbnew.NETINFO_ITEM(board, '/OTHER_BRANCH')
    board.Add(net)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(6+offset, 8+offset))
    via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    path = str(tmp_path/'native.kicad_pcb')
    pcbnew.SaveBoard(path, board)
    endpoints = [dict(kind='pad', ref=fp.GetReference(), pad='1',
        uuid=next(iter(fp.Pads())).m_Uuid.AsString(),
        x_mm=fp.GetPosition().x/1e6, y_mm=fp.GetPosition().y/1e6) for fp in fps]
    cert = dict(net='/LOCAL', endpoints=endpoints, width_mm=.25, clearance_mm=.2,
        dominant_blockers=[dict(kind='via', uuid=via.m_Uuid.AsString(), hit_count=3)])
    payload = dict(unconn_nets=['/LOCAL'], final_completion=dict(refused_details=[
        dict(net='/LOCAL', distance_mm=3.162278, certificate=cert)]))
    row = repair.plan_congestion_via_repairs(path, payload)['targets'][0]
    return path, row, cert, external.m_Uuid.AsString()


@pytest.mark.parametrize('offset,names', [(0, ('A17', 'B92')), (37, ('X9', 'Z81'))])
def test_native_plan_to_exact_close_leaves_other_island_alone(tmp_path, offset, names):
    import cec_local_copper_cell as cell
    path, row, cert, external = native_fixture(tmp_path, offset, names)
    assert row['route_endpoints'] == cert['endpoints']
    assert row['width_mm'] == .25 and row['clearance_mm'] == .2
    cert['endpoints'][0]['ref'] = 'mutated-caller-data'
    assert row['route_endpoints'][0]['ref'] == names[0]
    before = cell.copper_inventory(pcbnew.LoadBoard(path))
    with patch.object(repair, '_lastmile_worker', side_effect=AssertionError('scope widened')):
        report = repair._certified_via_target_worker(path, row, 10.)
    assert report['closed'] == 1, report
    assert report['search_scope'] == 'certificate_exact_pair'
    assert report['components_before'] == 3 and report['components_after'] == 2
    after = cell.copper_inventory(pcbnew.LoadBoard(path))
    assert after[external] == before[external]
    assert all(after[uid] == geom for uid, geom in before.items())


@pytest.mark.parametrize('endpoints', [None, [], [{}], [{}, {}],
    [dict(x_mm=float('nan'), y_mm=1), dict(x_mm=2, y_mm=3)]])
def test_invalid_present_pair_never_widens_search(endpoints):
    with patch.object(repair, '_lastmile_worker') as legacy, \
            patch.object(repair.pcbnew, 'LoadBoard') as load:
        report = repair._certified_via_target_worker('unused',
            dict(target_net='/ANON', route_endpoints=endpoints), 2.)
    assert report['refusal'] == 'certificate_pair_invalid'
    legacy.assert_not_called()
    load.assert_not_called()


def test_stale_pair_and_timeout_save_nothing(tmp_path):
    path, row, _, _ = native_fixture(tmp_path)
    original = open(path, 'rb').read()
    row['route_endpoints'][0]['ref'] = 'NOT_LIVE'
    with patch.object(repair, '_lastmile_worker') as legacy:
        report = repair._certified_via_target_worker(path, row, 2.)
    assert report['refusal'] == 'certificate_endpoint_not_live'
    assert open(path, 'rb').read() == original
    legacy.assert_not_called()
    with patch.object(repair, '_close_certificate_pair', return_value=(False,
            dict(refusal='certificate_pair_search_timeout'))), \
            patch.object(repair, '_lastmile_worker') as legacy:
        report = repair._certified_via_target_worker(path, row, 2.)
    assert report['timed_out'] and report['closed'] == 0
    assert open(path, 'rb').read() == original
    legacy.assert_not_called()


def test_distinct_pairs_share_a_via_without_being_deduplicated(tmp_path):
    path, row, cert, _ = native_fixture(tmp_path)
    different = deepcopy(cert)
    different['endpoints'][0] = dict(kind='node', x_mm=20., y_mm=20.)
    reverse = deepcopy(cert)
    reverse['endpoints'].reverse()
    payload = dict(unconn_nets=['/LOCAL'], final_completion=dict(refused_details=[
        dict(net='/LOCAL', distance_mm=4., certificate=item)
        for item in (cert, different, reverse)]))
    targets = repair.plan_congestion_via_repairs(path, payload)['targets']
    assert len(targets) == 2
    assert targets[0]['via']['uuid'] == targets[1]['via']['uuid']
    assert targets[0]['route_endpoints'] != targets[1]['route_endpoints']
    assert len(repair.plan_congestion_via_repairs(path, payload, limit=1)['targets']) == 1


def test_legacy_plan_receives_explicit_internal_budget():
    with patch.object(repair, '_lastmile_worker', return_value={'closed': 0}) as worker:
        report = repair._certified_via_target_worker('legacy', {'target_net': '/N'}, 17.)
    assert worker.call_args.args == ('legacy', ('/N',), 24, 8.0, True, 17.)
    assert report['search_scope'] == 'legacy_net_without_endpoint_evidence'


def test_final_bridge_expands_domain_instead_of_repeating_fast_seats(tmp_path):
    path, row, _, _ = native_fixture(tmp_path)
    calls = []
    def bridge(*args, **kwargs):
        calls.append(kwargs)
        return None
    with patch.object(repair.cec_fr, '_lastmile_bridge', side_effect=bridge), \
            patch.object(repair.cec_fr, '_guarded_profiled_lastmile_legs', return_value=None), \
            patch.object(repair.cec_fr, '_lastmile_refusal_certificate', return_value={}):
        report = repair._certified_via_target_worker(path, row, 10.)
    assert len(calls) == 2
    fast, broad = calls
    assert fast['seat_angles_deg'] == (0, 90, 180, 270)
    assert max(fast['seat_offsets_mm']) == 2 and not fast['allow_lattice']
    assert broad['seat_angles_deg'] is None and broad['seat_offsets_mm'] is None
    assert broad['allow_lattice']
    assert fast['deadline_monotonic'] < broad['deadline_monotonic']
    assert [phase['phase'] for phase in report['bridge_phases']] == [
        'cardinal_fast_seats', 'expanded_local_seats']
    assert report['closed'] == 0


def test_exact_success_still_requires_whole_board_admission():
    target = repair.ViaRepairTarget('random', '/OWNER', 0, 0, 600000, 300000,
        (), (), 1, 0, ())
    row = dict(via=asdict(target), target_net='/TARGET', route_endpoints=[])
    calls = []
    def worker(function, args, **kwargs):
        calls.append(function.__name__)
        if function is repair._relocate_via_worker:
            return True, {'changed': True}
        if function is repair._certified_via_target_worker:
            assert args[1] == row and args[2] < kwargs['timeout_s']
            return {'closed': 1}
        if function is repair._refill_worker:
            return True
        if function is repair._score_worker:
            return {'drc': 1, 'unconnected': 2}
        raise AssertionError(function)
    with patch.object(repair, '_copy_board_family') as copy, \
            patch.object(repair, '_spawn_apply', side_effect=worker), \
            patch.object(repair, '_run_drc'), \
            patch.object(repair, '_accepts', return_value=(False, 'regression')) as gate:
        result = repair._attempt_congestion_via_relocation('canonical',
            {'drc': 0, 'unconnected': 2}, row, work_dir='scratch', token='test', max_candidates=1)
    assert not result['adopted']
    assert result['attempts'][0]['decision'] == 'regression'
    gate.assert_called_once()
    assert copy.call_count == 1  # initial private copy only, never promotion
    assert calls[-1] == '_score_worker'
