"""Zero-emission cell motion still owes real retained paths and partitions."""
import pcbnew
import pytest

import test_complete_cell_connections as fixtures
import test_complete_cell_receiving as restoration_fixtures
import cec_complete_cell_receiving as receiver
import cec_cell_escape_replan as escape
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
from cec_native_items import discard_items


def saved_pair(tmp_path, monkeypatch, quarter=0, back=False):
    source, board, _, initial = fixtures.native_source(tmp_path, monkeypatch, turn=quarter)
    cap_ref = next(iter(initial['selected_bypasses']))
    owner_ref = initial['selected_bypasses'][cap_ref]['owner']
    cap = board.FindFootprintByReference(cap_ref)
    for pad in cap.Pads():
        pad.SetSize(pcbnew.VECTOR2I(500000,1000000))
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu)
                pad.SetLayerSet(layers)
        for track in board.GetTracks():
            if track.GetClass() == 'PCB_TRACK': track.SetLayer(pcbnew.B_Cu)
    # Rename the positively assigned parts; update the fixture's Source
    # assignment provider, not any receiver-authored ownership request.
    owner = board.FindFootprintByReference(owner_ref)
    owner.SetReference('opaque_stationary_device')
    cap.SetReference('opaque_sliding_bypass')
    req = dict(ref=owner.GetReference(), pin='5', rail='RAIL', return_rail='GND')
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment',
        lambda *a, **kw:dict(assigned={'selected':dict(cap_ref=cap.GetReference(),requirement=req)}))
    field._save_field_snapshot(board, source)
    parent = pcbnew.LoadBoard(str(source))
    cap = parent.FindFootprintByReference(cap.GetReference())
    owner = parent.FindFootprintByReference(owner.GetReference())
    ground = cap.FindPadByNumber('2')
    via = next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA')
    delta = [(via.GetPosition()[i]-ground.GetPosition()[i])*.3 for i in (0,1)]
    poses = {owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()],
        cap.GetReference():[(cap.GetPosition()[i]+delta[i])/1e6 for i in (0,1)]+[cap.GetOrientationDegrees()]}
    plan = escape.prepare(parent, poses, board_hint='opaque')
    assert plan['retired_track_uuids'] == []
    child = force._copy_family(source, tmp_path/'child')
    projected = pcbnew.LoadBoard(str(source)); escape.apply_private(projected, plan)
    additive._ground_refill(projected)
    receiver._save_literal_projection(source, child, projected, plan, {cap.GetReference()})
    monkeypatch.setattr(receiver.force, '_family', lambda p,h:force._hash(p))
    return source, child, plan


@pytest.mark.parametrize('quarter,back', [(0,False),(1,False),(2,True),(3,True)])
def test_full_receive_accepts_actual_zero_cut_retained_slide(tmp_path,monkeypatch,quarter,back):
    source, child, plan = saved_pair(tmp_path,monkeypatch,quarter,back)
    original = [p.read_bytes() for p in (source,child)]
    result = receiver.receive(source,child,board_hint='opaque')
    assert result['ok'] and result['complete'], result
    assert result['added_native_uuids'] == result['retired_track_uuids'] == []
    assert result['actual_native_terminal_paths'] and result['all_source_ground_returns']['ok']
    assert result['all_original_surviving_native_partitions_preserved']
    assert [p.read_bytes() for p in (source,child)] == original


@pytest.mark.parametrize('damage', ['supply','ground','partition','out_of_pad','extra_conductor','missing_retained_track'])
def test_zero_cut_motion_never_waives_native_connectivity_or_copper_delta(tmp_path,monkeypatch,damage):
    source, child, plan = saved_pair(tmp_path,monkeypatch)
    board = pcbnew.LoadBoard(str(child))
    cap = board.FindFootprintByReference(next(iter(plan['selected_bypasses'])))
    if damage in ('supply','ground','missing_retained_track'):
        net = 'RAIL' if damage != 'ground' else 'GND'
        track = next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net)
        discard_items(board,[track])
    elif damage == 'partition':
        board.FindFootprintByReference('external_OUT').FindPadByNumber('1').SetNet(board.FindNet('RAIL'))
    elif damage == 'out_of_pad':
        cap.Move(pcbnew.VECTOR2I(0,1500000))
    else:
        track = pcbnew.PCB_TRACK(board); track.SetNet(board.FindNet('OUT')); track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(22,22));track.SetEnd(pcbnew.VECTOR2I_MM(23,22));track.SetWidth(200000);board.Add(track)
    field._save_field_snapshot(board,child)
    result = receiver.receive(source,child,board_hint='opaque')
    assert not result['ok'],result


def test_source_retirement_without_any_restoration_gets_no_zero_cut_permission(tmp_path,monkeypatch):
    source, child, plan = restoration_fixtures.saved_pair(tmp_path,monkeypatch)
    assert plan['retired_track_uuids']
    original_ids = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    native = pcbnew.LoadBoard(str(child))
    incoming = [t for t in native.GetTracks() if force._uid(t) not in original_ids]
    assert incoming
    discard_items(native,incoming)
    field._save_field_snapshot(native,child)
    result = receiver.receive(source,child,board_hint='opaque')
    assert not result['ok'],result
