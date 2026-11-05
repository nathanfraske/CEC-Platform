"""Native-obstruction proposals never become copper or power authority."""
import copy
import math
from types import SimpleNamespace

import pcbnew
import pytest

import cec_local_return_feedback as feedback
import cec_placement_evidence_identity as identity
import cec_placement_search_domain as domain
import cec_synth_pipeline as synth


def fixture(tmp_path, *, diagonal=False, via=False, flipped=False):
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, '/RENAMED_POWER'); board.Add(net)
    for ref, x in (('DEVICE', 10.), ('BYPASS', 11.)):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, 10.)); board.Add(fp)
        if flipped:
            fp.Flip(fp.GetPosition(), False)
    if via:
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(pcbnew.VECTOR2I_MM(10., 10.))
        item.SetWidth(pcbnew.FromMM(2.)); item.SetDrill(pcbnew.FromMM(.3))
        item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    else:
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(8., 8. if diagonal else 10.))
        item.SetEnd(pcbnew.VECTOR2I_MM(12., 12. if diagonal else 10.))
        item.SetWidth(pcbnew.FromMM(2.)); item.SetLayer(pcbnew.B_Cu)
    item.SetNetCode(net.GetNetCode()); item.SetLocked(True); board.Add(item)
    path = tmp_path/'source.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), board)
    poses = {fp.GetReference(): (fp.GetPosition().x/1e6, fp.GetPosition().y/1e6,
                                fp.GetOrientationDegrees()) for fp in board.GetFootprints()}
    blocker = dict(kind='via' if via else 'track', uuid=item.m_Uuid.AsString(),
        net='/RENAMED_POWER', layer='B.Cu', locked=True)
    if via:
        blocker.update(at_mm=[10.,10.],diameter_mm=2.)
    else:
        blocker.update(from_mm=[8.,8. if diagonal else 10.],
                       to_mm=[12.,12. if diagonal else 10.],width_mm=2.)
    proof = dict(search_exhausted=True, conclusion='no_legal_immediate_ground_return',
        terminal=dict(ref='DEVICE', pad='G'), pad_center=dict(copper_admission=dict(
            ok=False, at_mm=[10.,10.], diameter_mm=.35, clearance_mm=.2, blockers=[blocker])))
    row = dict(owner_ref='DEVICE',cap_ref='BYPASS',status='assigned',
        owner_position_mm=[10.,10.],cap_position_mm=[11.,10.],supply_access_ok=False,
        supply_access_certificate=dict(ground_return=dict(attempts=[dict(error='refused',evidence=proof)])))
    evidence = dict(decoupler=dict(details=[row]),input_identity=identity.capture(path))
    return path, poses, evidence, row, proof, blocker


@pytest.mark.parametrize('capsule,point,expected', [
    (((0,0),(10,0),1), (5,0), [(-6,0),(6,0),(0,-1),(0,1)]),
    (((0,0),(0,10),1), (0,5), [(-1,0),(1,0),(0,-6),(0,6)]),
    (((0,0),(0,0),1), (0,0), [(-1,0),(1,0),(0,-1),(0,1)]),
    (((0,0),(10,10),1), (5,5), [(-math.sqrt(2),0),(math.sqrt(2),0),
                                    (0,-math.sqrt(2)),(0,math.sqrt(2))]),
])
def test_exact_capsule_axis_intersections(capsule,point,expected):
    result = domain.axis_exits_from_copper_union(point,capsules=[capsule])
    for actual, target in zip(result,expected):
        assert actual == pytest.approx(target)


def test_round_end_and_diagonal_corner_are_not_bbox_obstructions():
    assert domain.axis_exits_from_copper_union((.1,9.9),capsules=[((0,0),(10,10),1)]) == [(0.,0.)]
    rows = domain.axis_exits_from_copper_union((-0.6,0.8),capsules=[((0,0),(10,0),1.1)])
    assert rows[0][0] == pytest.approx(-math.sqrt(1.1**2-.8**2)+.6)


def test_capsules_and_rectangles_merge_without_tessellation_seam_exit():
    rows = domain.axis_exits_from_copper_union((1,0),capsules=[((0,0),(2,0),1),((3,0),(5,0),1)],
                                              rectangles=[(5.5,-1,8,1)],envelope=.1)
    assert rows[:2] == pytest.approx([(-2.1,0),(7.1,0)])
    assert rows[2:] == pytest.approx([(0,-1.1),(0,1.1)])


@pytest.mark.parametrize('shape', [((0,0),(1,1),0),((0,0),(1,1),-1),
    ((0,float('nan')),(1,1),1),((0,0),(1,float('inf')),1)])
def test_invalid_capsules_are_not_guessed(shape):
    with pytest.raises(ValueError):
        domain.axis_exits_from_copper_union((0,0),capsules=[shape])


@pytest.mark.parametrize('diagonal,via,flipped',[(False,False,False),(True,False,False),
                                               (False,True,False),(True,False,True)])
def test_real_bound_native_objects_produce_rigid_cell_exits(tmp_path,diagonal,via,flipped):
    path,p,e,row,proof,blocker = fixture(tmp_path,diagonal=diagonal,via=via,flipped=flipped)
    before = path.read_bytes(); original = copy.deepcopy((p,e))
    context = feedback.bound_native_obstacles(e)
    assert context['ok'] and not context['complete_clearance_authority']
    moves = feedback.move_specs(p,[row],native_context=context)
    assert len(moves) == 4
    for move in moves:
        assert move['native_board_sha256'] == identity.digest(path)
        assert move['native_blocker_uuid'] == blocker['uuid']
        assert move['exit_basis'] == 'bound_native_capsule_union'
        assert set(move['placements']) == set(p)
        assert move['requires_native_requalification']
        assert math.dist(move['placements']['DEVICE'][:2],move['placements']['BYPASS'][:2]) == 1
    assert path.read_bytes() == before and (p,e) == original


@pytest.mark.parametrize('mutation',['uuid','net','width','position','layer','lock','tentative'])
def test_blocker_cannot_claim_different_native_geometry(tmp_path,mutation):
    _,p,e,row,_,blocker = fixture(tmp_path)
    context = feedback.bound_native_obstacles(e)
    if mutation=='uuid': blocker['uuid']='invented'
    if mutation=='net': blocker['net']='renamed-again'
    if mutation=='width': blocker['width_mm']+=.01
    if mutation=='position': blocker['from_mm'][0]+=.01
    if mutation=='layer': blocker['layer']='F.Cu'
    if mutation=='lock': blocker['locked']=False
    if mutation=='tentative': blocker['ownership_origin']='tentative_cell_copper'
    assert not feedback.move_specs(p,[row],native_context=context)


def test_missing_stale_or_mid_evaluation_board_never_binds_geometry(tmp_path):
    path,p,e,row,_,_ = fixture(tmp_path)
    assert not feedback.move_specs(p,[row])
    e['input_identity_after'] = copy.deepcopy(e['input_identity'])
    assert not feedback.bound_native_obstacles(e)['ok']
    e.pop('input_identity_after');path.write_bytes(path.read_bytes()+b'\n')
    assert not feedback.bound_native_obstacles(e)['ok']


def test_different_native_pose_and_fixed_follower_are_not_partial_moves(tmp_path):
    _,p,e,row,_,_=fixture(tmp_path);context=feedback.bound_native_obstacles(e)
    assert not feedback.move_specs(p,[row],native_context=context,immovable=['BYPASS'])
    p['BYPASS']=(11.01,10.,0.)
    diagnostic={}
    assert not feedback.move_specs(p,[row],native_context=context,diagnostics=diagnostic)
    assert diagnostic['rejection_counts']['stale_native_cell_pose']


def test_union_includes_unsampled_other_layer_track_and_budget_is_explicit(tmp_path):
    path,p,e,row,_,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path));item=pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I_MM(8.,11.5));item.SetEnd(pcbnew.VECTOR2I_MM(12.,11.5))
    item.SetWidth(pcbnew.FromMM(2.));item.SetLayer(pcbnew.In2_Cu);board.Add(item)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    e['input_identity']=identity.capture(path);context=feedback.bound_native_obstacles(e)
    moves=feedback.move_specs(p,[row],native_context=context)
    assert any(m['dy_mm']==pytest.approx(2.925) for m in moves)
    diagnostic={}
    assert not feedback.move_specs(p,[row],native_context=context,max_native_intersections=0,
                                   diagnostics=diagnostic)
    assert diagnostic['rejection_counts']['native_exit_budget_exhausted']
    assert not diagnostic['geometric_infeasibility_proven']


def test_failed_stub_native_evidence_can_generate_whole_cell_reseat(tmp_path):
    _,p,e,row,proof,blocker=fixture(tmp_path)
    proof['pad_center']['copper_admission']['blockers']=[dict(kind='pad',ref='DEVICE')]
    proof['blocking_native_objects']=[dict(blocker=blocker,observed_in=[dict(origin='dogbone')])]
    context=feedback.bound_native_obstacles(e)
    assert feedback.move_specs(p,[row],native_context=context)


def test_normal_placement_generator_consumes_bound_native_geometry(tmp_path):
    path,p,e,_,_,_=fixture(tmp_path)
    original=path.read_bytes();diagnostic={}
    moves=synth._placement_craft_move_specs(SimpleNamespace(P=p),e,
        required_stages=['return_path_placement'],proposal_diagnostics=diagnostic)
    native=[m for m in moves if m.get('native_blocker_uuid')]
    assert native and diagnostic['local_ground_return']['native_geometry_binding']['ok']
    assert all(m['requires_native_requalification'] for m in native)
    assert path.read_bytes()==original
