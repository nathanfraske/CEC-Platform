"""The search cannot propose moves its downstream support gate disallows."""
import copy
import math
import pytest
import pcbnew
import cec_support_motion as motion
import cec_certificate_repair as repair
import cec_route_placement_admission as admission


def fixture(*, offset=(0, 0), back=False):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, '/RENAMED'); board.Add(net)
    for index, ref in enumerate(('SUPPORT', 'PEER')):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(20 + index*4 + offset[0], 20 + offset[1]))
        for number, delta in (('1', -.5), ('2', .5)):
            pad = pcbnew.PAD(fp); pad.SetNumber(number); pad.SetNet(net)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.4)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(delta, 0)); fp.Add(pad)
        board.Add(fp)
        if back: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for a,b in (((0,0),(60,0)),((60,0),(60,60)),((60,60),(0,60)),((0,60),(0,0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000); board.Add(edge)
    return board


@pytest.mark.parametrize('policy', [dict(max_refs=0), dict(max_refs=True),
    dict(max_refs=5), dict(max_shift_mm=6.001), dict(max_shift_mm=float('nan')),
    dict(max_shift_mm=-1), dict(max_shift_mm=True), dict(immutable_refs='ABC')])
def test_bad_limits_fail_closed(policy):
    with pytest.raises(ValueError): motion.limits(**policy)


@pytest.mark.parametrize('offset,back', [((0,0),False),((17,-8),True)])
def test_rotation_checks_every_member_not_just_owner(offset, back):
    board=fixture(offset=offset,back=back)
    domain=motion.capture(board,dict(ref='SUPPORT',companion_refs=['PEER']),motion.limits())
    assert domain['ok']
    assert motion.evaluate(domain,dict(dx_mm=6))['ok']
    assert not motion.evaluate(domain,dict(dx_mm=6.000001))['ok']
    result=motion.evaluate(domain,dict(rotation_delta_deg=180))
    assert not result['ok'] and result['movement_mm']['PEER']==8
    assert motion.evaluate(domain,dict(dx_mm=4,rotation_delta_deg=180))['ok']
    assert admission._native_prepare.__defaults__[-2:] == (motion.MAX_REFS,motion.MAX_SHIFT_MM)


@pytest.mark.parametrize('kind', ['locked','fixed','grouped','tht','multilead','missing','duplicate'])
def test_scope_filter_matches_native_revalidation(kind):
    board=fixture();fp=board.FindFootprintByReference('SUPPORT')
    target=dict(ref='SUPPORT'); policy=motion.limits()
    if kind=='locked':fp.SetLocked(True)
    if kind=='fixed':policy=motion.limits(immutable_refs=['SUPPORT'])
    if kind=='grouped':
        group=pcbnew.PCB_GROUP(board);group.SetName('protected');board.Add(group);group.AddItem(fp)
    if kind=='tht':list(fp.Pads())[0].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    if kind=='multilead':
        pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    if kind=='missing':target['ref']='ABSENT'
    if kind=='duplicate':target['companion_refs']=['SUPPORT']
    assert not motion.capture(board,target,policy)['ok']


@pytest.mark.parametrize('pose', [dict(dx_mm=float('inf')),dict(dy_mm=None),
                                 dict(rotation_delta_deg='invalid')])
def test_bad_pose_fails_closed(pose):
    assert not motion.evaluate(motion.capture(fixture(),dict(ref='SUPPORT'),motion.limits()),pose)['ok']


def test_bound_is_applied_before_occupancy_top_k(tmp_path):
    board=fixture();source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    original=source.read_bytes()
    target=repair.asdict(repair.FootprintRepairTarget(ref='SUPPORT',target_net='/RENAMED',
        endpoint_ref='PEER',endpoint_pad='1',endpoint_x_mm=28.5,endpoint_y_mm=20,
        hit_count=1,distance_mm=9,priority=(0,),motion='toward_endpoint'))
    unconstrained=repair._occupancy_relocation_candidates(str(source),target,limit=1)
    assert math.hypot(unconstrained[0]['dx_mm'],unconstrained[0]['dy_mm'])>6
    constrained=repair._occupancy_relocation_candidates(str(source),target,limit=1,
                                                       support_limits=motion.limits())
    assert len(constrained)==1
    assert math.hypot(constrained[0]['dx_mm'],constrained[0]['dy_mm'])<=6
    assert source.read_bytes()==original


def test_expanded_and_legacy_poses_get_final_filter(tmp_path,monkeypatch):
    board=fixture();source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    target=repair.asdict(repair.FootprintRepairTarget(ref='SUPPORT',target_net='/RENAMED',
        endpoint_ref='PEER',endpoint_pad='1',endpoint_x_mm=28.5,endpoint_y_mm=20,
        hit_count=1,distance_mm=9,priority=(0,),motion='toward_endpoint'))
    poses=[dict(dx_mm=9.9,dy_mm=0,rotation_delta_deg=0),
           dict(dx_mm=0,dy_mm=0,rotation_delta_deg=180,mobility_companion_refs=['PEER']),
           dict(dx_mm=1,dy_mm=0,rotation_delta_deg=90)]
    before=copy.deepcopy(poses)
    monkeypatch.setattr(repair,'_spawn_apply',lambda worker,args,**kw:worker(*args))
    result=repair._attempt_footprint_relocation(str(source),{},target,work_dir=str(tmp_path),
        token='bounded',candidate_override=poses,max_candidates=0,support_limits=motion.limits())
    frontier=result['candidate_frontier']; domain=frontier['support_motion_domain']
    assert frontier['scheduled']==0 and frontier['unvisited']==1
    assert len(domain['rejected'])==2 and not domain['release_authority']
    assert poses==before and not result['adopted']
