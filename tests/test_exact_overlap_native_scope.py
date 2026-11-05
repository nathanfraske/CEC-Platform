"""Scoped normalization cannot mutate an unrelated native track."""
import pytest
import pcbnew

import cec_fab_repair as repair
import cec_field_coupling as field
import cec_exact_overlap_receiving as overlap


def fixture(layer=pcbnew.F_Cu):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, '/arbitrary/new-net'); board.Add(net)
    tracks = []
    for a, b in [((1, 1), (1, 6)), ((1, 1), (1, 3)),
                 ((8, 1), (8, 6)), ((8, 1), (8, 3))]:
        track = pcbnew.PCB_TRACK(board); track.SetNet(net); track.SetLayer(layer)
        track.SetWidth(200000); track.SetStart(pcbnew.VECTOR2I_MM(*a))
        track.SetEnd(pcbnew.VECTOR2I_MM(*b)); board.Add(track); tracks.append(track)
    return board, tracks


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_native_scoped_repair_preserves_other_unlocked_overlap_and_receives(tmp_path, layer):
    board, tracks = fixture(layer)
    source, candidate = [tmp_path / (name + '.kicad_pcb') for name in ('source', 'candidate')]
    field._save_field_snapshot(board, source)
    old = field._field_snapshot_inventory(board)
    scope = [t.m_Uuid.AsString() for t in tracks[:2]]
    assert repair.repair_backtracks(board, track_uuid_scope=scope) == 1
    after = field._field_snapshot_inventory(board)
    assert all(after[k] == v for k, v in old.items() if k[0] != 'track' or k[1] not in scope)
    field._save_field_snapshot(board, candidate)
    assert overlap.receive(source, candidate, source_track_uuids=scope)['ok']


def test_scope_is_not_lock_authority():
    board, tracks = fixture()
    for t in tracks[:2]: t.SetLocked(True)
    scope = [t.m_Uuid.AsString() for t in tracks[:2]]
    assert repair.repair_backtracks(board, track_uuid_scope=scope) == 0
    assert repair.repair_backtracks(board, track_uuid_scope=scope,
                                    allow_locked_track_uuids=scope) == 1


def test_alternative_can_retire_a_fully_covered_prefix_and_receive(tmp_path):
    board, tracks = fixture()
    source, candidate = [tmp_path / (name + '.kicad_pcb') for name in ('source', 'candidate')]
    field._save_field_snapshot(board, source)
    scope = [t.m_Uuid.AsString() for t in tracks[:2]]
    assert repair.repair_backtracks(board, track_uuid_scope=scope,
                                    overlap_policy='retire_covered') == 1
    assert len(list(board.GetTracks())) == 3
    field._save_field_snapshot(board, candidate)
    assert overlap.receive(source, candidate, source_track_uuids=scope)['ok']


def test_retirement_policy_cannot_delete_a_wider_short_prefix():
    board, tracks = fixture(); tracks[1].SetWidth(300000)
    scope = [t.m_Uuid.AsString() for t in tracks[:2]]
    old = field._field_snapshot_inventory(board)
    assert repair.repair_backtracks(board, track_uuid_scope=scope,
                                    overlap_policy='retire_covered') == 0
    assert field._field_snapshot_inventory(board) == old


def test_unknown_overlap_policy_refuses_before_mutation():
    board, _tracks = fixture(); old = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        repair.repair_backtracks(board, overlap_policy='guess')
    assert field._field_snapshot_inventory(board) == old


@pytest.mark.parametrize('scope', [[], ['missing'], 'not-a-sequence', ['same', 'same']])
def test_invalid_native_scope_refuses_without_mutation(scope):
    board, _tracks = fixture(); before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        repair.repair_backtracks(board, track_uuid_scope=scope)
    assert field._field_snapshot_inventory(board) == before
