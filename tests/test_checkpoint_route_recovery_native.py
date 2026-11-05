"""Native proposal cleanup preserves all retained copper and actual barrels."""
import pcbnew
import pytest
import cec_checkpoint_route_recovery as recovery
import cec_force_current as force
from test_additive_route_receiving import terminal, barrel
from test_field_proposals import track
from test_lastmile import _board
from test_field_refill_proposals import ground_fixture
import cec_field_coupling as field
from pathlib import Path


def ids(board):
    return {force._uid(t) for t in board.GetTracks()}


def test_new_dangling_chain_is_peeled_without_touching_source():
    board = _board([], edge=(0,0,30,30))
    source = track(board, '/CONTROL', (4,14), (6,14))
    old = ids(board)
    first = track(board, '/CONTROL', (6,14), (8,14))
    second = track(board, '/CONTROL', (8,14), (10,14))
    report = recovery.prune_incoming_dead_ends(board,
        [force._uid(first), force._uid(second)], source_uuids=old)
    assert report['complete'] and report['passes'] >= 2
    assert ids(board) == {force._uid(source)}
    assert not report['source_material_removed']


def test_complete_live_pad_bridge_is_not_pruned():
    board = _board([], edge=(0,0,30,30))
    track(board, '/CONTROL', (2,2), (3,2))
    terminal(board, 'X1', (4,14)); terminal(board, 'X2', (12,14))
    old = ids(board)
    first = track(board, '/CONTROL', (4,14), (8,14))
    second = track(board, '/CONTROL', (8,14), (12,14))
    report = recovery.prune_incoming_dead_ends(board,
        [force._uid(first), force._uid(second)], source_uuids=old)
    assert report['complete'] and report['removed_uuids'] == []


def test_source_barrel_is_never_deletable_and_new_isolated_via_is():
    board = _board([], edge=(0,0,30,30))
    track(board, '/CONTROL', (2,2), (3,2))
    source = barrel(board, (6,14)); old = ids(board)
    incoming = barrel(board, (20,14))
    with pytest.raises(ValueError, match='source_material'):
        recovery.prune_incoming_dead_ends(board, [force._uid(source)], source_uuids=old)
    result = recovery.prune_incoming_dead_ends(board, [force._uid(incoming)], source_uuids=old)
    assert result['complete'] and ids(board) == old


def test_actual_through_hole_reaches_both_layers_without_extra_via():
    board = _board([], edge=(0,0,30,30))
    track(board, '/CONTROL', (2,2), (3,2))
    terminal(board, 'X1', (4,14)); terminal(board, 'X2', (12,14))
    for fp in board.GetFootprints():
        pad = next(iter(fp.Pads()))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    old = ids(board)
    incoming = track(board, '/CONTROL', (4,14), (12,14), layer=pcbnew.B_Cu)
    result = recovery.prune_incoming_dead_ends(board, [force._uid(incoming)], source_uuids=old)
    assert result['complete'] and not result['removed_uuids']


def test_group_owned_proposal_requires_its_owner_packet():
    board = _board([], edge=(0,0,30,30))
    incoming = track(board, '/CONTROL', (4,14), (8,14))
    group = pcbnew.PCB_GROUP(board); group.SetName('owned'); board.Add(group)
    group.AddItem(incoming)
    with pytest.raises(ValueError, match='ungrouped'):
        recovery.prune_incoming_dead_ends(board, [force._uid(incoming)], source_uuids=[])


def reconstruction_fixture(tmp_path):
    source, board = ground_fixture(tmp_path)
    terminal(board,'X1',(6,14)); terminal(board,'X2',(12,14))
    field._save_field_snapshot(board,source)
    donor_path=force._copy_family(source,tmp_path/'donor')
    donor=pcbnew.LoadBoard(str(donor_path))
    track(donor,'/CONTROL',(6,14),(12,14))
    current=pcbnew.LoadBoard(str(source))
    current.FindFootprintByReference('X2').SetPosition(pcbnew.VECTOR2I_MM(16,14))
    return source, current, donor


def test_native_template_uses_current_terminal_positions_not_old_pose(tmp_path):
    source, board, donor = reconstruction_fixture(tmp_path)
    before=ids(board)
    result=recovery.construct(board,donor,source_path=source,board_hint='unclassified-test')
    assert result['joins']==1 and len(result['created_uuids'])==1, result
    added=next(t for t in board.GetTracks() if force._uid(t) not in before)
    assert set((tuple(added.GetStart()),tuple(added.GetEnd())))=={(6000000,14000000),(16000000,14000000)}
    assert not result['source_poses_imported'] and not result['routing_admitted']


def test_partition_timeout_does_not_mislabel_infeasibility_or_erase_prefix(tmp_path,monkeypatch):
    source, board, donor = reconstruction_fixture(tmp_path)
    import cec_ordinary_route_receiving as native
    def expire(*args,**kwargs):
        raise ValueError('ordinary_receiving_deadline')
    monkeypatch.setattr(native,'_partition',expire)
    before=ids(board)
    result=recovery.construct(board,donor,source_path=source,board_hint='unclassified-test')
    assert result['stop']=='bounded_native_partition_lease' and not result['no_path_proof']
    assert ids(board)==before and not result['routing_admitted']
