"""Native, board-independent frozen-copper and residual-polish regressions."""
import json
from unittest import mock

import pcbnew
import pytest

import cec_certificate_repair as certificate
import cec_fab_repair as repair
import cec_fr
from cec_local_copper_cell import copper_inventory


def fixture(layer, rotated):
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, '/renamed-net')
    board.Add(net)

    def track(length, locked):
        item = pcbnew.PCB_TRACK(board)
        a, b = ((21, 31), (21, 31 + length)) if rotated else ((3, 4), (3 + length, 4))
        item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*b))
        item.SetWidth(pcbnew.FromMM(.2))
        item.SetLayer(board.GetLayerID(layer))
        item.SetNet(net)
        item.SetLocked(locked)
        board.Add(item)
        return item

    return board, track


@pytest.mark.parametrize('layer,rotated', [('F.Cu', False), ('B.Cu', True)])
def test_locked_long_overlap_is_immutable_but_owned_track_can_be_trimmed(layer, rotated):
    board, track = fixture(layer, rotated)
    short, long = track(2, False), track(4, True)
    baseline = copper_inventory(board)
    assert repair.repair_backtracks(board) == 0
    assert copper_inventory(board) == baseline
    assert repair.repair_backtracks(board, allow_locked_track_uuids=[long.m_Uuid.AsString()]) == 1
    assert long.GetStart() == short.GetEnd()


@pytest.mark.parametrize('allow_victim', [False, True])
def test_two_locked_duplicates_require_explicit_victim_authority(allow_victim):
    board, track = fixture('F.Cu', False)
    first, second = track(2, True), track(2, True)
    baseline = copper_inventory(board)
    uid = second.m_Uuid.AsString()
    assert repair.repair_backtracks(board, allow_locked_track_uuids=[uid] if allow_victim else []) == int(allow_victim)
    after = copper_inventory(board)
    assert after[first.m_Uuid.AsString()] == baseline[first.m_Uuid.AsString()]
    assert (uid not in after) == allow_victim


def test_unlocked_duplicate_can_be_deleted_without_touching_locked_survivor():
    board, track = fixture('B.Cu', True)
    locked, unlocked = track(2, True), track(2, False)
    baseline = copper_inventory(board)
    uid = unlocked.m_Uuid.AsString()
    assert repair.repair_backtracks(board) == 1
    assert copper_inventory(board) == {key: row for key, row in baseline.items() if key != uid}


def test_width_normalization_honors_exact_locked_authority():
    board, track = fixture('F.Cu', False)
    locked, unlocked = track(2, True), track(4, False)
    for item in (locked, unlocked):
        item.SetWidth(199800)
    board.GetDesignSettings().m_TrackMinWidth = 200000
    assert cec_fr.normalize_track_width(board, preserve_locked=True) == 1
    assert locked.GetWidth() == 199800
    assert unlocked.GetWidth() == 200000
    assert cec_fr.normalize_track_width(board, preserve_locked=True,
        allow_locked_track_uuids=[locked.m_Uuid.AsString()]) == 1


@pytest.mark.parametrize('mutation', ['delete', 'move', 'unlock', 'width', 'net'])
def test_native_transaction_rejects_unauthorized_copper_mutations(tmp_path, mutation):
    board, track = fixture('B.Cu', True)
    locked = track(4, True)
    source = tmp_path / 'board.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    baseline_bytes = source.read_bytes()
    expected = repair._copper_inventory_isolated(source)
    uid = locked.m_Uuid.AsString()
    candidate = json.loads(json.dumps(expected))
    if mutation == 'delete':
        del candidate[uid]
    else:
        index, value = {'move': (3, 99000000), 'unlock': (2, False),
                        'width': (8, 300000), 'net': (1, '/different-net')}[mutation]
        candidate[uid][index] = value
    assert not repair._protected_copper_check(expected, candidate)['ok']
    metrics = dict(drc=0, unconnected=0, kelvin_ok=True, diffpair_ok=True,
                   route_blocking=0, route_advisory=0, objective=0)
    with mock.patch.object(repair, '_copper_inventory_isolated',
                           side_effect=[expected] + [candidate]*5), \
         mock.patch.object(repair, '_score_isolated', side_effect=[dict(metrics, objective=100)] + [metrics]*5), \
         mock.patch.object(repair, '_fab_isolated', return_value=dict(fab_blocking=0, fab_drc=0, fab_unconnected=0)), \
         mock.patch.object(repair, '_foreign_isolated', return_value=dict(foreign_status='ok', foreign_blocking=0)), \
         mock.patch.object(repair, '_repair_isolated', return_value={}), \
         mock.patch.object(repair, '_sliver_repair_isolated', return_value={}):
        result = repair.repair_admitted(str(source))
    assert not result['adopted']
    assert all(not row['safe'] and row['protected_copper']['changed_uuids'] == [uid]
               for row in result['variants'])
    assert source.read_bytes() == baseline_bytes


@pytest.mark.parametrize('opens,accepted,expected', [
    (2, [], False), (0, [], True), (2, [{'accepted': True}], True),
    (None, [], False)])
def test_cosmetic_polish_does_not_advance_a_stalled_open_board(opens, accepted, expected):
    assert certificate._residual_polish_ready({'unconnected': opens}, accepted) == expected


@pytest.mark.parametrize('opens', [0, 1, 2])
def test_even_closed_local_placement_must_be_admitted_before_global_polish(opens):
    assert not certificate._residual_polish_ready({'unconnected': opens},
        [{'accepted': True}], placement_changed=True)


@pytest.mark.parametrize('kind', ['none', 'translate', 'rotate', 'flip'])
def test_native_pose_boundary_not_refdes_or_worker_claim(tmp_path, kind):
    board, _ = fixture('F.Cu', False)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('RENAMED_SUPPORT')
    fp.SetPosition(pcbnew.VECTOR2I_MM(10, 20))
    board.Add(fp)
    source, target = tmp_path/'before.kicad_pcb', tmp_path/'after.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    if kind == 'translate':
        fp.SetPosition(pcbnew.VECTOR2I_MM(10.25, 20.25))
    elif kind == 'rotate':
        fp.SetOrientationDegrees(90)
    elif kind == 'flip':
        fp.Flip(fp.GetPosition(), False)
    pcbnew.SaveBoard(str(target), board)
    proof = certificate._route_polish_boundary_worker(str(source), str(target))
    assert proof['ok'] and proof['placement_changed'] == (kind != 'none')
    assert proof['release_authority'] is False
