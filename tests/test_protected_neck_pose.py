"""A moved pad cannot abandon the native owner of a protected narrow escape."""
import pcbnew
import pytest

import cec_fr as fr
import cec_protected_neck_pose as neck
from test_support_motion import fixture


def native_case(back=False, angle=0, offset=(0, 0), grouped=True):
    board = fixture(back=back, offset=offset)
    fp = board.FindFootprintByReference('SUPPORT'); fp.SetReference('ARBITRARY_OWNER')
    fp.SetOrientationDegrees(angle)
    pad = next(p for p in fp.Pads() if p.GetNumber() == '1')
    track = pcbnew.PCB_TRACK(board); track.SetNet(pad.GetNet()); track.SetLayer(fp.GetLayer())
    track.SetWidth(200000); track.SetStart(pad.GetPosition())
    track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I_MM(-2, -2)); board.Add(track)
    if grouped:
        group = pcbnew.PCB_GROUP(board); group.SetName(fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(group); group.AddItem(track)
    return board, fp, pad, track, dict(ref=fp.GetReference(), companion_refs=[])


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_native_contact_domain_and_half_turn_do_not_change_source(back, angle):
    board, fp, pad, track, target = native_case(back, angle, (11, -7))
    before = (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(pad.GetPosition()))
    rows = neck.capture(board, target, lambda _net: dict(track_width=.5))
    assert len(rows) == 1
    assert neck.preserves(rows, dict(dx_mm=0, dy_mm=0))
    assert not neck.preserves(rows, dict(dx_mm=0, dy_mm=2))
    pivots = neck.pivots(rows)
    assert len(pivots) == 1 and neck.preserves(rows, pivots[0])
    assert before == (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(pad.GetPosition()))
    original_pad_position = tuple(pad.GetPosition())
    fp.SetOrientationDegrees(fp.GetOrientationDegrees()+180)
    fp.Move(pcbnew.VECTOR2I_MM(pivots[0]['dx_mm'], pivots[0]['dy_mm']))
    assert tuple(pad.GetPosition()) == original_pad_position


@pytest.mark.parametrize('kind', ['ungrouped', 'full_width', 'unowned', 'other_net'])
def test_unrelated_copper_does_not_invent_a_pad_constraint(kind):
    board, fp, pad, track, target = native_case(grouped=kind != 'ungrouped')
    if kind == 'full_width': track.SetWidth(500000)
    if kind == 'unowned': track.Move(pcbnew.VECTOR2I_MM(3, 3))
    if kind == 'other_net':
        other = pcbnew.NETINFO_ITEM(board, '/FOREIGN'); board.Add(other); track.SetNet(other)
    assert neck.capture(board, target, lambda _net: dict(track_width=.5)) == []


def test_native_circular_pad_does_not_use_bounding_box_contact():
    board, fp, pad, track, target = native_case()
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE); pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
    rows = neck.capture(board, target, lambda _net: dict(track_width=.5))
    assert not neck.preserves(rows, dict(dx_mm=.35, dy_mm=.35))
    assert neck.preserves(rows, dict(dx_mm=.2, dy_mm=.2))
