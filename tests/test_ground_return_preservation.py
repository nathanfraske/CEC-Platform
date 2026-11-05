"""A shorter bypass must not purchase a worse device/reference return."""
import pcbnew
import pytest

import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_ground_return_preservation as guard
from cec_native_items import discard_items
from test_local_pofv_body_contact import body_fixture


def native_pair(tmp_path, *, angle=0, back=False):
    b, via, track, pad = body_fixture(angle=angle,
        layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    ground = pcbnew.NETINFO_ITEM(b, 'GND'); b.Add(ground)
    for item in (via, track, pad):
        item.SetNet(ground)
    pad.GetParentFootprint().SetReference('arbitrary_terminal')
    path = tmp_path / 'source.kicad_pcb'; pcbnew.SaveBoard(str(path), b)
    parent = pcbnew.LoadBoard(str(path)); child = pcbnew.LoadBoard(str(path))
    return parent, child, force._uid(via), force._uid(track), force._uid(pad)


def item(board, uid):
    return next(i for i in [*board.GetTracks(),
        *(p for fp in board.GetFootprints() for p in fp.Pads())] if force._uid(i) == uid)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_native_rotation_and_surface_replay_is_read_only(tmp_path, angle, back):
    parent, child, via, track, pad = native_pair(tmp_path, angle=angle, back=back)
    bindings = [row._source_binding(b) for b in (parent, child)]
    proof = guard.receive(parent, child)
    assert proof['ok'] and proof['complete'] and proof['source_known_terminals'] == 1
    assert not proof['regressed_terminals'] and not proof['source_unknown_terminals']
    assert proof['native_boards_unchanged'] and not proof['routing_admitted']
    assert not proof['reference_planes_qualified'] and not proof['release_authority']
    assert [row._source_binding(b) for b in (parent, child)] == bindings


@pytest.mark.parametrize('fault', ['longer', 'missing_track', 'gap', 'wrong_face'])
def test_connected_or_nearby_copper_does_not_hide_worse_or_lost_return(tmp_path, fault):
    parent, child, via, track, pad = native_pair(tmp_path)
    if fault == 'longer':
        item(child, via).Move(pcbnew.VECTOR2I_MM(.25, 0))
    elif fault == 'missing_track':
        discard_items(child, [item(child, track)])
    elif fault == 'gap':
        item(child, track).SetStart(item(child, pad).GetPosition() + pcbnew.VECTOR2I_MM(.6, 0))
    else:
        item(child, track).SetLayer(pcbnew.B_Cu)
    proof = guard.receive(parent, child)
    assert not proof['ok'] and proof['complete'] and len(proof['regressed_terminals']) == 1
    assert proof['errors'] == ['source_known_ground_return_worsened_or_lost']


def test_actual_shorter_return_can_follow_source_owned_pad_motion(tmp_path):
    parent, child, via, track, pad = native_pair(tmp_path)
    p = item(child, pad); p.SetPosition(p.GetPosition() + pcbnew.VECTOR2I_MM(.1, 0))
    proof = guard.receive(parent, child)
    assert proof['ok'] and proof['complete'] and len(proof['improved_terminals']) == 1
    assert proof['source_pose_changes_not_authorized']


@pytest.mark.parametrize('fault', ['new_identity', 'net', 'pin', 'parent', 'surface', 'dnp'])
def test_missing_or_relabelled_native_terminal_cannot_escape_inventory(tmp_path, fault):
    parent, child, via, track, uid = native_pair(tmp_path); pad = item(child, uid)
    if fault == 'new_identity':
        pad.m_Uuid.Clone(pcbnew.KIID())
    elif fault == 'net':
        other = pcbnew.NETINFO_ITEM(child, 'other'); child.Add(other); pad.SetNet(other)
    elif fault == 'pin':
        pad.SetNumber('not_the_source_pin')
    elif fault == 'parent':
        pad.GetParentFootprint().m_Uuid.Clone(pcbnew.KIID())
    elif fault == 'surface':
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
    else:
        pad.GetParentFootprint().SetDNP(True)
    proof = guard.receive(parent, child)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def test_source_unknown_remains_declared_not_a_fabrication_certificate(tmp_path):
    parent, child, via, track, pad = native_pair(tmp_path)
    discard_items(parent, [item(parent, track)]); discard_items(child, [item(child, track)])
    proof = guard.receive(parent, child)
    assert proof['ok'] and proof['complete'] and proof['source_known_terminals'] == 0
    assert len(proof['source_unknown_terminals']) == 1 and not proof['current_qualified']


def test_terminal_improvement_cannot_offset_another_terminal_regression(tmp_path):
    parent, child, via, track, uid = native_pair(tmp_path)
    for board in (parent, child):
        original = item(board, uid); fp = original.GetParentFootprint()
        peer = original.Duplicate(); peer.m_Uuid.Clone(pcbnew.KIID())
        # Bind the same second physical identity into the two saved candidates.
        if board is parent:
            peer_uid = force._uid(peer)
        else:
            peer.m_Uuid.Clone(pcbnew.KIID(peer_uid))
        peer.SetNumber('2'); peer.SetPosition(original.GetPosition()+pcbnew.VECTOR2I_MM(2, 0)); fp.Add(peer)
    item(child, via).Move(pcbnew.VECTOR2I_MM(.25, 0))
    proof = guard.receive(parent, child)
    assert not proof['ok'] and proof['complete']
    assert len(proof['improved_terminals']) == len(proof['regressed_terminals']) == 1


@pytest.mark.parametrize('options', [{'timeout_s': 0}, {'timeout_s': 11}, {'timeout_s': True},
    {'reach_mm': float('nan')}, {'reach_mm': 33}, {'reach_mm': True}])
def test_unbounded_or_untyped_work_cannot_become_a_receipt(tmp_path, options):
    parent, child, *_ = native_pair(tmp_path)
    with pytest.raises(ValueError, match='bounded_ground_return_preservation_required'):
        guard.receive(parent, child, **options)


def test_expired_native_observation_is_unknown_not_success(tmp_path, monkeypatch):
    parent, child, *_ = native_pair(tmp_path)
    clock = iter([0., 100., 100., 100.])
    monkeypatch.setattr(guard.time, 'monotonic', lambda: next(clock))
    proof = guard.receive(parent, child)
    assert not proof['ok'] and not proof['complete'] and proof['lease_exhausted']
    assert proof['errors'] == ['ground_return_preservation_deadline']


@pytest.mark.parametrize('measured_regression', [False, True])
def test_final_native_identity_observation_is_in_the_same_lease(tmp_path, monkeypatch, measured_regression):
    parent, child, via, *_ = native_pair(tmp_path)
    if measured_regression:
        item(child, via).Move(pcbnew.VECTOR2I_MM(.25, 0))
    clock = [10.]
    bindings = []
    original = guard.row._source_binding
    def bind(board):
        value = original(board)
        bindings.append(value)
        if len(bindings) == 3: clock[0] = 21.
        return value
    monkeypatch.setattr(guard.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(guard.row, '_source_binding', bind)
    proof = guard.receive(parent, child, timeout_s=10.)
    assert len(bindings) == 4
    assert not proof['ok'] and not proof['complete'] and proof['lease_exhausted']
    assert proof['native_boards_unchanged']
    assert 'ground_return_preservation_deadline' in proof['errors']
    assert bool(proof['regressed_terminals']) == measured_regression
