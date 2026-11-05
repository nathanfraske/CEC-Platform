"""Exact isolated-pose replay, with no footprint or fabrication loopholes."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_isolated_pose_receiving as isolated
from test_additive_route_receiving import terminal
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path, *, connected=False, mutation=None, reflow=False):
    source, board = ground_fixture(tmp_path)
    terminal(board, 'X1', (10,14))
    fp = board.FindFootprintByReference('X1')
    fp.Reference().SetLayer(pcbnew.F_SilkS); fp.Value().SetLayer(pcbnew.F_SilkS)
    fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(10,15))
    fp.Value().SetPosition(pcbnew.VECTOR2I_MM(10,16))
    if connected:
        track(board, '/CONTROL', (10,14), (11,14))
    field._save_field_snapshot(board, source)
    uid = force._uid(fp)
    candidate = force._copy_family(source, tmp_path/'trial')
    board = pcbnew.LoadBoard(str(candidate)); fp = board.FindFootprintByReference('X1')
    fp.SetPosition(pcbnew.VECTOR2I_MM(13,14)); fp.SetOrientationDegrees(90)
    if reflow:
        fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(13,16))
        fp.Reference().SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
        fp.Value().SetPosition(pcbnew.VECTOR2I_MM(13,17))
        fp.Value().SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    if mutation == 'pad':
        next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif mutation == 'hidden':
        fp.Reference().SetVisible(False)
    elif mutation == 'track':
        track(board, '/CONTROL', (13,14), (14,14))
    elif mutation == 'outline':
        next(iter(board.GetDrawings())).Move(pcbnew.VECTOR2I_MM(1,0))
    additive._ground_refill(board); field._save_field_snapshot(board, candidate)
    return source, candidate, uid


def test_exact_isolated_cardinal_pose_is_received(tmp_path):
    source, candidate, uid = fixture(tmp_path)
    before = source.read_bytes()
    result = isolated.receive(source,candidate,selected_footprint_uuids=[uid])
    assert result['ok'] and result['complete'], result
    assert source.read_bytes() == before and not result['release_authority']


@pytest.mark.parametrize('mutation', ['pad','hidden','track','outline'])
def test_pose_scope_cannot_smuggle_other_edits(tmp_path, mutation):
    source, candidate, uid = fixture(tmp_path,mutation=mutation,reflow=True)
    result = isolated.receive(source,candidate,selected_footprint_uuids=[uid],allow_field_reflow=True)
    assert not result['ok'] and result['errors'], result


def test_connected_terminal_is_not_isolated(tmp_path):
    source, candidate, uid = fixture(tmp_path,connected=True)
    result = isolated.receive(source,candidate,selected_footprint_uuids=[uid])
    assert not result['ok'] and 'retained_same_net_contacts' in result['errors'][0], result


def test_explicit_text_pose_scope_preserves_font_visibility_and_identity(tmp_path):
    source, candidate, uid = fixture(tmp_path,reflow=True)
    assert not isolated.receive(source,candidate,selected_footprint_uuids=[uid])['ok']
    result = isolated.receive(source,candidate,selected_footprint_uuids=[uid],allow_field_reflow=True)
    assert result['ok'] and result['bounded_source_authored_field_poses_replayed'], result
