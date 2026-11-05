"""Native proposal ordering is layer/net/shape aware, never an admission gate."""
import json
import pytest
import pcbnew

import cec_pose_copper_score as scoring
from test_fixed_pofv_mobility import pose


def fixture(*, back=False, offset=(0, 0), ref='RENAMED_CELL'):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_MinClearance = 200000
    nets = []
    for name in ('/SIGNAL_A', '/SIGNAL_B', '/FOREIGN'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets.append(net)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20+offset[0], 20+offset[1])); board.Add(fp)
    pads = []
    for index, x in enumerate((-1, 1)):
        pad = pcbnew.PAD(fp); pad.SetNumber(str(index+1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(x, 0)); pad.SetNet(nets[index])
        fp.Add(pad); pads.append(pad)
    if back: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    return board, fp, pads, nets


def track(board, fp, net, dx, dy, *, layer=None, locked=True):
    item = pcbnew.PCB_TRACK(board)
    item.SetStart(fp.GetPosition()+pcbnew.VECTOR2I_MM(dx-.1, dy))
    item.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(dx+.1, dy)); item.SetWidth(100000)
    item.SetNet(net); item.SetLayer(fp.GetLayer() if layer is None else layer)
    item.SetLocked(locked); board.Add(item); return item


def state(fp, board):
    return (tuple(fp.GetPosition()), fp.GetOrientationDegrees(),
            tuple(tuple(p.GetPosition()) for p in fp.Pads()),
            tuple((i.m_Uuid.AsString(), tuple(i.GetStart()), tuple(i.GetEnd()), i.IsLocked())
                  for i in board.GetTracks()))


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('offset', [(0, 0), (17, -11)])
def test_package_empty_space_is_not_a_native_land_contact(back, offset):
    board, fp, pads, nets = fixture(back=back, offset=offset)
    track(board, fp, nets[2], 0, 2)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    before = state(fp, board)
    result = scorer.score(pose(0, 2))
    assert result['new_copper_pairs'] == 0
    assert not result['qualification_authority']
    assert result['custom_rule_and_refill_proof_required']
    assert state(fp, board) == before


@pytest.mark.parametrize('angle', [-90, 90, 180])
@pytest.mark.parametrize('back', [False, True])
def test_native_rotated_lands_hit_and_restore_exactly(angle, back):
    board, fp, pads, nets = fixture(back=back)
    # Place an obstacle at one actual future land, not a hand-derived box.
    position, orientation = fp.GetPosition(), fp.GetOrientationDegrees()
    fp.SetPosition(position+pcbnew.VECTOR2I_MM(0, 2))
    fp.SetOrientationDegrees(orientation+angle)
    at = pcbnew.VECTOR2I(pads[0].GetPosition())
    fp.SetPosition(position); fp.SetOrientationDegrees(orientation)
    item = track(board, fp, nets[2], (at.x-position.x)/1e6, (at.y-position.y)/1e6)
    before = state(fp, board)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    assert scorer.score(pose(0, 2, angle))['new_fixed_copper_pairs'] == 1
    assert scorer.score(pose(0, 2, angle))['conflicting_copper_uuids'] == [item.m_Uuid.AsString()]
    assert state(fp, board) == before


@pytest.mark.parametrize('same_net,inner,locked,generated,expected,fixed', [
    (False, False, True, False, 1, 1), (True, False, True, False, 0, 0),
    (False, True, True, False, 0, 0), (False, False, False, False, 1, 0),
    (False, False, True, True, 1, 0)])
def test_net_layer_and_receipts_change_cost_not_edit_authority(
        same_net, inner, locked, generated, expected, fixed):
    board, fp, pads, nets = fixture()
    item = track(board, fp, nets[0] if same_net else nets[2], -1, 2,
                 layer=pcbnew.In1_Cu if inner else pcbnew.F_Cu, locked=locked)
    before = state(fp, board)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference(),
        generated_locked_uuids=[item.m_Uuid.AsString()] if generated else ())
    result = scorer.score(pose(0, 2))
    assert (result['new_copper_pairs'], result['new_fixed_copper_pairs']) == (expected, fixed)
    assert state(fp, board) == before


def test_net_zero_does_not_make_two_unconnected_items_the_same_net():
    board, fp, pads, nets = fixture()
    pads[0].SetNetCode(0)
    item = track(board, fp, nets[2], -1, 2); item.SetNetCode(0)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    assert scorer.score(pose(0, 2))['new_copper_pairs'] == 1


def test_through_via_includes_back_surface_and_baseline_is_not_new():
    board, fp, pads, nets = fixture(back=True)
    via = pcbnew.PCB_VIA(board); via.SetPosition(pads[0].GetPosition())
    via.SetWidth(350000); via.SetDrill(250000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(nets[2]); via.SetLocked(True); board.Add(via)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    result = scorer.score(pose())
    assert result['copper_pairs'] == 1 and result['new_copper_pairs'] == 0
    assert scorer.score(pose(0, 2))['copper_pairs'] == 0


def test_pad_local_clearance_is_respected_without_a_physical_overlap():
    board, fp, pads, nets = fixture()
    pads[0].SetLocalClearance(500000)
    track(board, fp, nets[2], -1, 2.7)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    assert scorer.score(pose(0, 2))['new_fixed_copper_pairs'] == 1


def test_incident_copper_is_not_implicitly_removed_for_other_pads():
    board, fp, pads, nets = fixture()
    item = track(board, fp, nets[0], -1, 0)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    assert scorer.score(pose(-2))['new_fixed_copper_pairs'] == 1
    assert item in list(board.GetTracks())


def test_cell_companions_follow_native_rigid_transform_and_restore():
    board, fp, pads, nets = fixture()
    other = pcbnew.FOOTPRINT(board); other.SetReference('OTHER_SUPPORT')
    other.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(2, 3)); board.Add(other)
    pad = pcbnew.PAD(other); pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4))
    pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetPosition(other.GetPosition()); pad.SetNet(nets[0])
    other.Add(pad)
    track(board, fp, nets[2], 4, -2)
    before = (state(fp, board), state(other, board))
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference(), (other.GetReference(),))
    assert scorer.score(pose(1, 0, 90))['new_copper_pairs'] == 1
    assert (state(fp, board), state(other, board)) == before


def test_native_error_restores_members_and_propagates(monkeypatch):
    board, fp, pads, nets = fixture()
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    before = state(fp, board)
    def fail(): raise RuntimeError('native geometry failed')
    monkeypatch.setattr(scorer, '_contacts', fail)
    with pytest.raises(RuntimeError): scorer.score(pose(1, 2, 90))
    assert state(fp, board) == before


@pytest.mark.parametrize('candidate', [pose(float('nan')), pose(0, float('inf')), pose(0, 0, float('nan'))])
def test_nonfinite_pose_fails_without_mutation(candidate):
    board, fp, pads, nets = fixture()
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    before = state(fp, board)
    with pytest.raises(ValueError): scorer.score(candidate)
    assert state(fp, board) == before


@pytest.mark.parametrize('assigned', ['/SIGNAL_A', '/FOREIGN'])
def test_saved_project_clearance_on_either_side_is_a_floor(tmp_path, assigned):
    board, fp, pads, nets = fixture()
    track(board, fp, nets[2], -1, 2.7)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes': [{'name': 'Default', 'clearance': .2},
                    {'name': 'WIDE', 'clearance': .5}],
        'netclass_assignments': {assigned: ['WIDE']}}}))
    saved = source.read_bytes()
    loaded = pcbnew.LoadBoard(str(source))
    scorer = scoring.NativePoseCopperScore(loaded, fp.GetReference())
    assert scorer.score(pose(0, 2))['new_copper_pairs'] == 1
    assert source.read_bytes() == saved


def test_stationary_pad_is_retained_but_companion_pad_is_not_an_obstacle():
    board, fp, pads, nets = fixture()
    other = pcbnew.FOOTPRINT(board); other.SetReference('STATIONARY'); board.Add(other)
    other.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(-1, 2))
    pad = pcbnew.PAD(other); pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4))
    pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetPosition(other.GetPosition()); pad.SetNet(nets[2])
    other.Add(pad)
    scorer = scoring.NativePoseCopperScore(board, fp.GetReference())
    assert scorer.score(pose(0, 2))['new_fixed_copper_pairs'] == 1
    moving = scoring.NativePoseCopperScore(board, fp.GetReference(), (other.GetReference(),))
    assert moving.score(pose(0, 2))['new_copper_pairs'] == 0


def test_occupancy_top_k_prefers_native_clearance_to_package_box_hits(tmp_path, monkeypatch):
    import cec_certificate_repair as repair
    import cec_fixed_pofv_mobility as mobility
    board, fp, pads, nets = fixture()
    for y in (1.85, 1.95, 2.05, 2.15): track(board, fp, nets[2], 0, y)
    track(board, fp, nets[2], 3, 2)
    for a, b in (((0, 0), (50, 0)), ((50, 0), (50, 50)),
                 ((50, 50), (0, 50)), ((0, 50), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000); board.Add(edge)
    source = tmp_path/'rank.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    target = repair.asdict(repair.FootprintRepairTarget(ref=fp.GetReference(),
        target_net='/SIGNAL_A', endpoint_ref='PEER', endpoint_pad='1',
        endpoint_x_mm=23, endpoint_y_mm=22, hit_count=1, distance_mm=3,
        priority=(0,), motion='toward_endpoint'))
    candidates = [dict(**pose(0, 2), synthetic=True), dict(**pose(4, 2), synthetic=True)]
    monkeypatch.setattr(mobility, 'proposals', lambda *a, **kw: candidates)
    monkeypatch.setattr(mobility, 'contained_land_proposals', lambda *a, **kw: [])
    monkeypatch.setattr(mobility, 'evaluate', lambda board, target, candidate, **kw:
                        {'ok': candidate.get('synthetic', False)})
    saved = source.read_bytes()
    rows = repair._occupancy_relocation_candidates(str(source), target, limit=2)
    assert [row['dx_mm'] for row in rows] == [0, 4]
    assert rows[0]['occupancy_score']['copper_hits'] > rows[1]['occupancy_score']['copper_hits']
    assert rows[0]['occupancy_score']['native_copper']['new_copper_pairs'] == 0
    assert rows[1]['occupancy_score']['native_copper']['new_fixed_copper_pairs'] == 1
    assert source.read_bytes() == saved


@pytest.mark.parametrize('companions', [('RENAMED_CELL',), ('MISSING',), ('A','B','C','D')])
def test_invalid_cell_does_not_start_native_mutation(companions):
    board, fp, pads, nets = fixture()
    before = state(fp, board)
    with pytest.raises(ValueError):
        scoring.NativePoseCopperScore(board, fp.GetReference(), companions)
    assert state(fp, board) == before
