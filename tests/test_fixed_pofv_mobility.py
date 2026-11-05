"""Locked local vias constrain their movable owner's pose, not board names."""
import hashlib
import math
import copy
import inspect

import pytest

pcbnew = pytest.importorskip('pcbnew')
import cec_certificate_repair as repair
import cec_fab_profile as fab
import cec_fixed_pofv_mobility as mobility


def fixture(*, ref='SUPPORT', offset=(0, 0), back=False,
            size=(0.6, 0.4), diameter=0.35, drill=0.25):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    settings = board.GetDesignSettings()
    settings.m_ViasMinSize = pcbnew.FromMM(0.5)
    settings.m_MinViaAnnularWidth = pcbnew.FromMM(0.1)
    net = pcbnew.NETINFO_ITEM(board, '/ANY_RETURN')
    board.Add(net)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20 + offset[0], 30 + offset[1]))
    pad = pcbnew.PAD(fp)
    pad.SetPadName('arbitrary')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(*size))
    pad.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(0.775, 0))
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetNet(net)
    fp.Add(pad)
    board.Add(fp)
    if back:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pad.GetPosition())
    via.SetWidth(pcbnew.FromMM(diameter))
    via.SetDrill(pcbnew.FromMM(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    via.SetLocked(True)
    board.Add(via)
    assert fab.local_pofv_via_decision(board, via)[0]
    return board, fp, pad, via


def pose(dx=0, dy=0, angle=0):
    return dict(dx_mm=dx, dy_mm=dy, rotation_delta_deg=angle)


@pytest.mark.parametrize('ref,offset,back', [
    ('SUPPORT', (0, 0), False), ('RENAMED', (71, -13), True)])
@pytest.mark.parametrize('candidate,ok', [
    (pose(1), True), (pose(3), False), (pose(-2, 2, 90), False)])
def test_actual_native_lands_bound_moves(ref, offset, back, candidate, ok):
    board, fp, pad, via = fixture(ref=ref, offset=offset, back=back)
    before = (tuple(pad.GetPosition()), tuple(via.GetPosition()), fp.GetOrientationDegrees())
    result = mobility.evaluate(board, dict(ref=ref), candidate)
    assert result['checked'] == 1 and result['ok'] is ok
    assert result['qualification_authority'] is False
    assert result['requires_live_reconnection_proof'] is True
    assert before == (tuple(pad.GetPosition()), tuple(via.GetPosition()), fp.GetOrientationDegrees())


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('angle', [-90, 45, 90, 180])
def test_rotation_about_immutable_barrel_keeps_native_containment(back, angle):
    board, fp, pad, via = fixture(back=back)
    x = (pad.GetPosition().x - fp.GetPosition().x) / 1e6
    y = (pad.GetPosition().y - fp.GetPosition().y) / 1e6
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    candidate = pose(x - (c*x+s*y), y - (-s*x+c*y), angle)
    result = mobility.evaluate(board, dict(ref=fp.GetReference()), candidate)
    assert result['checked'] == 1 and result['ok']
    # Compare the predicted transform against KiCad's actual pad transform.
    fp.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(candidate['dx_mm'], candidate['dy_mm']))
    fp.SetOrientationDegrees(fp.GetOrientationDegrees() + angle)
    assert math.hypot(pad.GetPosition().x-via.GetPosition().x,
                      pad.GetPosition().y-via.GetPosition().y) <= 2
    assert fab.local_pofv_via_decision(board, via)[0]


def test_large_land_containment_can_exceed_dogbone_centre_limit():
    board, fp, pad, via = fixture(size=(6, 1))
    result = mobility.evaluate(board, dict(ref=fp.GetReference()), pose(2))
    assert result['checked'] == 1 and result['ok']
    fp.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(2, 0))
    assert fab.local_pofv_via_decision(board, via)[0]


@pytest.mark.parametrize('back,offset', [(False, (0, 0)), (True, (71, -13))])
@pytest.mark.parametrize('angle', [0, 90, 180, -90])
@pytest.mark.parametrize('shift,expected', [(.05, True), (.3, False), (.5, True)])
def test_partial_overlap_rejected_before_routing_with_native_transform(back, offset, angle, shift, expected):
    board, fp, pad, via = fixture(ref='UNRELATED', back=back, offset=offset, size=(.6, .6))
    old_origin = fp.GetPosition()
    old_pad = pad.GetPosition()
    old_via = tuple(via.GetPosition())
    x, y = (old_pad.x-old_origin.x)/1e6, (old_pad.y-old_origin.y)/1e6
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    candidate = pose(x-(c*x+s*y)+shift, y-(-s*x+c*y), angle)
    result = mobility.evaluate(board, dict(ref=fp.GetReference()), candidate)
    assert result['checked'] == 1 and result['ok'] is expected
    assert tuple(pad.GetPosition()) == tuple(old_pad) and tuple(via.GetPosition()) == old_via
    if not expected:
        assert result['violations'][0]['reason'] == 'immutable_local_via_partial_pad_overlap'
    fp.SetPosition(old_origin + pcbnew.VECTOR2I_MM(candidate['dx_mm'], candidate['dy_mm']))
    fp.SetOrientationDegrees(fp.GetOrientationDegrees() + angle)
    # Compare the cheap inverse-coordinate predicate to the unchanged full
    # native via-pad authority. A disjoint result still needs a real dogbone.
    blocked, _ = fab.via_at_pad_conflicts(board, via.GetPosition(),
        via.GetWidth(), via.GetDrillValue(), via.GetNetCode())
    assert (blocked is None) is expected


@pytest.mark.parametrize('exception', ['generated', 'unlocked', 'ordinary', 'unqualified'])
def test_only_existing_qualified_immutable_small_vias_constrain(exception):
    board, fp, pad, via = fixture()
    generated = ()
    if exception == 'generated':
        generated = (via.m_Uuid.AsString(),)
    elif exception == 'unlocked':
        via.SetLocked(False)
    elif exception == 'ordinary':
        via.SetWidth(pcbnew.FromMM(0.5))
    else:
        props = board.GetProperties()
        props.clear()
        board.SetProperties(props)
    result = mobility.evaluate(board, dict(ref=fp.GetReference()), pose(3),
                               generated_locked_uuids=generated)
    assert result['ok'] and result['checked'] == 0
    assert result['qualification_authority'] is False


def test_companion_owner_is_checked_even_when_target_has_no_small_via():
    board, fp, pad, via = fixture(ref='DEPENDENT')
    primary = pcbnew.FOOTPRINT(board)
    primary.SetReference('OWNER')
    primary.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(5, 0))
    board.Add(primary)
    candidate = {**pose(3), 'mobility_companion_refs': ['DEPENDENT']}
    result = mobility.evaluate(board, dict(ref='OWNER'), candidate)
    assert not result['ok'] and result['checked'] == 1
    assert result['violations'][0]['ref'] == 'DEPENDENT'


def test_filter_is_stable_and_worker_refuses_without_mutation(tmp_path):
    board, fp, pad, via = fixture()
    source = tmp_path / 'input.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    target = repair.asdict(repair.FootprintRepairTarget(
        ref=fp.GetReference(), target_net='/SIGNAL', endpoint_ref='OWNER',
        endpoint_pad='7', endpoint_x_mm=2, endpoint_y_mm=3, hit_count=1,
        distance_mm=1, priority=(0,)))
    candidates = [pose(3), pose(1), pose(-1), pose(0, 3)]
    result = mobility.filter_candidates(str(source), target, candidates)
    assert result['eligible'] == candidates[1:3]
    assert [row['candidate'] for row in result['rejected']] == [candidates[0], candidates[3]]
    changed, evidence = repair._relocate_footprint_worker(str(source), target, pose(3))
    assert not changed
    assert evidence['refusal'] == 'immutable_local_via_owner_out_of_reach'
    assert evidence['fixed_via_domain']['checked'] == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    # Native LoadBoard may materialize a missing .pro/.prl for this synthetic
    # file. The move must not save copper or write a compensating DRC rule.
    assert not source.with_suffix('.kicad_dru').exists()


def test_invalid_poses_do_not_consume_the_trial_cap(tmp_path, monkeypatch):
    board, fp, pad, via = fixture()
    source = tmp_path / 'input.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    target = repair.asdict(repair.FootprintRepairTarget(
        ref=fp.GetReference(), target_net='/SIGNAL', endpoint_ref='OWNER',
        endpoint_pad='7', endpoint_x_mm=2, endpoint_y_mm=3, hit_count=1,
        distance_mm=1, priority=(0,)))
    attempted = []
    def spawn(worker, args, **kwargs):
        if worker is mobility.filter_candidates:
            return worker(*args)
        assert worker is repair._relocate_footprint_worker
        attempted.append(args[2])
        return False, dict(refusal='synthetic_downstream_refusal')
    monkeypatch.setattr(repair, '_spawn_apply', spawn)
    monkeypatch.setattr(repair, '_copy_board_family', lambda *args: None)
    result = repair._attempt_footprint_relocation(str(source), {}, target,
        work_dir=str(tmp_path), token='bounded', max_candidates=1,
        candidate_override=[pose(3), pose(1), pose(-1)])
    assert attempted == [pose(1)]
    frontier = result['candidate_frontier']
    assert frontier['generated'] == 3 and frontier['scheduled'] == 1
    assert frontier['unvisited'] == 1
    assert len(frontier['fixed_via_domain']['rejected']) == 1


def test_parent_report_preserves_untried_pose_refusals_without_maps():
    result = dict(attempts=[], stop='candidate_exhausted',
        candidate_frontier=dict(generated=1, scheduled=0, unvisited=0,
            exhaustion_is_no_path_proof=False, fixed_via_domain=dict(
                eligible=[], rejected=[dict(candidate={**pose(3),
                    'occupancy_score': {'large_map': [1, 2, 3]}},
                    proof={'reason': 'immutable_owner'})])))
    original = copy.deepcopy(result)
    sweep = dict(attempts=[])
    repair._record_placement_sweep_result(sweep, dict(ref='ANY', target_net='/ANY'), result)
    assert result == original
    frontier = sweep['candidate_frontiers'][0]['frontier']
    domain = frontier['fixed_via_domain']
    assert domain['eligible_count'] == 0 and 'eligible' not in domain
    assert domain['rejected'] == [dict(candidate=pose(3), proof={'reason': 'immutable_owner'})]
    assert not frontier['exhaustion_is_no_path_proof']
    # All three production support/early-owner/late-owner call sites retain it.
    assert inspect.getsource(repair.repair_board).count('_record_placement_sweep_result(') == 3
