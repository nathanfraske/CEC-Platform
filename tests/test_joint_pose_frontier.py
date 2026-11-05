"""Joint candidates derive separation from native geometry, not board names."""
import copy

import pcbnew
import pytest

import cec_joint_pose_frontier as joint
import cec_support_motion as motion
from test_compound_support_candidate import cells
from test_support_motion import fixture


def native_case(back=False, offset=(0, 0)):
    board = fixture(back=back, offset=offset)
    for fp in board.GetFootprints():
        shape = pcbnew.PCB_SHAPE(fp); shape.SetShape(pcbnew.SHAPE_T_RECT)
        shape.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd); shape.SetWidth(50000)
        shape.SetStart(fp.GetPosition()+pcbnew.VECTOR2I_MM(-1, -.6))
        shape.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(1, .6)); fp.Add(shape)
    rows = cells()
    rows[0]['candidate'].update(dx_mm=1.1, dy_mm=.05)
    rows[1]['candidate'].update(dx_mm=-1.1, dy_mm=-.05)
    for row in rows:
        row['candidate']['endpoint_via_aperture'] = dict(via_mm=[999, 999])
    return board, rows


@pytest.mark.parametrize('back,offset', [(False, (0, 0)), (True, (13, -7))])
def test_native_joint_pose_separates_courtyards_and_keeps_source_unchanged(tmp_path, back, offset):
    board, rows = native_case(back, offset)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    original = source.read_bytes(); inputs = copy.deepcopy(rows)
    found = joint.refine(board, [rows], motion.limits(), max_expansions=32)
    assert found['measured'] > 1 and found['proposals'][0]['advisory_conflicts'] == 0
    assert found['proposals'][0]['depth'] > 0
    assert found['input_board_unchanged'] and not found['release_authority']
    assert found['native_placement_and_route_admission_required']
    for row in found['proposals'][0]['cells']:
        candidate = row['candidate']
        if 'joint_pose_refinement' in candidate:
            assert 'endpoint_via_aperture' not in candidate
            assert not candidate['joint_pose_refinement']['release_authority']
    assert rows == inputs and source.read_bytes() == original
    assert joint.refine(board, [rows], motion.limits(), max_expansions=32) == found


def test_foreign_pads_separate_even_when_the_courtyard_is_missing():
    board = fixture(); board.GetDesignSettings().m_MinClearance = 200000
    other = pcbnew.NETINFO_ITEM(board, '/OTHER'); board.Add(other)
    for pad in board.FindFootprintByReference('PEER').Pads(): pad.SetNet(other)
    rows = cells()
    rows[0]['candidate'].update(dx_mm=1.15, dy_mm=0)
    rows[1]['candidate'].update(dx_mm=-1.15, dy_mm=0)
    found = joint.refine(board, [rows], motion.limits(), max_expansions=32)
    assert found['proposals'][0]['advisory_conflicts'] == 0
    assert found['proposals'][0]['depth'] > 0


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('kind', ['track', 'via'])
def test_saved_copper_is_considered_without_permission_to_remove_it(back, kind):
    board = fixture(back=back); board.GetDesignSettings().m_MinClearance = 200000
    net = pcbnew.NETINFO_ITEM(board, '/FIXED_COPPER'); board.Add(net)
    fp = board.FindFootprintByReference('SUPPORT')
    point = next(iter(fp.Pads())).GetPosition()+pcbnew.VECTOR2I_MM(0, .9)
    if kind == 'track':
        item = pcbnew.PCB_TRACK(board); item.SetLayer(fp.GetLayer()); item.SetWidth(200000)
        item.SetStart(point+pcbnew.VECTOR2I_MM(-.2, 0)); item.SetEnd(point+pcbnew.VECTOR2I_MM(.2, 0))
    else:
        item = pcbnew.PCB_VIA(board); item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetPosition(point); item.SetWidth(600000); item.SetDrill(300000)
    item.SetNet(net); item.SetLocked(True); board.Add(item)
    rows = cells()
    rows[0]['candidate'].update(dx_mm=0, dy_mm=.9)
    rows[1]['candidate'].update(dx_mm=0, dy_mm=.2)
    found = joint.refine(board, [rows], motion.limits(), max_expansions=32)
    assert found['proposals'][0]['advisory_conflicts'] == 0
    assert found['proposals'][0]['depth'] > 0
    assert any(c['candidate'].get('joint_pose_refinement', {}).get('kind') == 'saved_copper_envelope'
               for c in found['proposals'][0]['cells'])
    assert any(str(t.m_Uuid.AsString()) == str(item.m_Uuid.AsString()) for t in board.GetTracks())
    assert item.IsLocked() and item.GetNetname() == '/FIXED_COPPER'


@pytest.mark.parametrize('fault', ['locked', 'immutable', 'shift', 'companion'])
def test_joint_search_does_not_expand_original_motion_authority(fault):
    board, rows = native_case(); policy = motion.limits()
    if fault == 'locked': board.FindFootprintByReference('PEER').SetLocked(True)
    if fault == 'immutable': policy = motion.limits(immutable_refs=['PEER'])
    if fault == 'shift': rows[0]['candidate']['dx_mm'] = 6.01
    if fault == 'companion': rows[0]['candidate']['mobility_companion_refs'] = ['PEER']
    found = joint.refine(board, [rows], policy)
    assert not found['proposals'] and found['refused_seeds']


def test_cumulative_adjustment_and_original_motion_bounds():
    board, rows = native_case()
    found = joint.refine(board, [rows], motion.limits(max_shift_mm=1.2),
                         max_adjust_mm=.15, max_depth=3, max_expansions=12)
    assert found['measured'] <= 13
    for proposal in found['proposals']:
        for seed, row in zip(rows, proposal['cells']):
            a, b = seed['candidate'], row['candidate']
            assert joint.math.hypot(a['dx_mm']-b['dx_mm'], a['dy_mm']-b['dy_mm']) <= .15
            assert joint.math.hypot(b['dx_mm'], b['dy_mm']) <= 1.2


def test_opposite_side_bodies_are_not_same_side_obstacles():
    board, rows = native_case()
    peer = board.FindFootprintByReference('PEER')
    peer.Flip(peer.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    found = joint.refine(board, [rows], motion.limits())
    assert found['measured'] == 1 and found['proposals'][0]['advisory_conflicts'] == 0


def test_joint_native_exception_restores_poses(monkeypatch):
    board, rows = native_case()
    before = [(fp.GetReference(), tuple(fp.GetPosition()), fp.GetOrientationDegrees())
              for fp in board.GetFootprints()]
    def fail(_fp): raise RuntimeError('injected native geometry failure')
    monkeypatch.setattr(joint, '_body', fail)
    with pytest.raises(RuntimeError): joint.refine(board, [rows], motion.limits())
    assert before == [(fp.GetReference(), tuple(fp.GetPosition()), fp.GetOrientationDegrees())
                      for fp in board.GetFootprints()]


@pytest.mark.parametrize('kwargs', [dict(limit=True), dict(max_expansions=513),
    dict(max_depth=4), dict(max_adjust_mm=1.01), dict(margin_mm=float('nan'))])
def test_unbounded_search_is_refused(kwargs):
    board, rows = native_case()
    with pytest.raises(ValueError): joint.refine(board, [rows], motion.limits(), **kwargs)
