"""Small endpoint owners use explicit scope and independently prove benefit."""
import json
from types import SimpleNamespace

import pcbnew
import pytest
import cec_certificate_repair as repair
import cec_support_motion as motion
import cec_route_placement_admission as admission
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
import cec_route_checkpoint as checkpoint
from test_route_placement_admission import placement_proof


def fixture(*, offset=(0, 0), back=False, owner_pads=3):
    board = pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    nets = []
    for name in ('/SIGNAL_RENAMED', '/RETURN_RENAMED', '/OTHER_RENAMED'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets.append(net)
    def fp(ref, x, count):
        part = pcbnew.FOOTPRINT(board); part.SetReference(ref)
        part.SetPosition(pcbnew.VECTOR2I_MM(x + offset[0], 20 + offset[1]))
        for i in range(count):
            pad = pcbnew.PAD(part); pad.SetNumber(str(i + 1)); pad.SetNet(nets[min(i, 2)])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(part.GetPosition() + pcbnew.VECTOR2I_MM(0, i * 2)); part.Add(pad)
        board.Add(part)
        if back:
            part.Flip(part.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            part.Rotate(pcbnew.VECTOR2I_MM(*offset), pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
        return part
    fp('OWNER_RENAMED', 20, owner_pads)
    fp('ANCHOR_RENAMED', 16, 2)
    fp('PEER_RENAMED', 28, 2)
    return board


def pad(board, ref, number):
    return next(p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == str(number))


def track(board, root, end):
    item = pcbnew.PCB_TRACK(board); item.SetNet(root.GetNet()); item.SetLayer(root.GetParentFootprint().GetLayer())
    item.SetStart(root.GetPosition()); item.SetEnd(end); item.SetWidth(200000); board.Add(item)


def target():
    return repair.asdict(repair.FootprintRepairTarget(ref='OWNER_RENAMED',
        target_net='/SIGNAL_RENAMED', endpoint_ref='PEER_RENAMED', endpoint_pad='1',
        endpoint_x_mm=28, endpoint_y_mm=20, hit_count=1, distance_mm=8,
        priority=(0,), motion='toward_endpoint'))


@pytest.mark.parametrize('count', [2, 3, 8, 16, 17])
@pytest.mark.parametrize('back', [False, True])
def test_only_explicit_owner_scope_allows_small_smd_ic(count, back):
    board = fixture(offset=(42, -13), back=back, owner_pads=count)
    row = target(); row['companion_refs'] = ['ANCHOR_RENAMED']
    assert motion.capture(board, row, motion.limits())['ok'] is (count == 2)
    assert motion.capture(board, row, motion.limits(max_owner_copper_pads=16))['ok'] is (count <= 16)
    # The exact same IC may NOT be smuggled into another owner's companion list.
    row = dict(ref='ANCHOR_RENAMED', companion_refs=['OWNER_RENAMED'])
    assert motion.capture(board, row, motion.limits(max_owner_copper_pads=16))['ok'] is (count == 2)


@pytest.mark.parametrize('limit', [1, 17, True, 3.5, float('nan')])
def test_owner_scope_is_bounded(limit):
    with pytest.raises(ValueError): motion.limits(max_owner_copper_pads=limit)


@pytest.mark.parametrize('fault', ['locked', 'grouped', 'fixed', 'tht', 'drilled'])
def test_owner_scope_does_not_relax_other_guards(fault):
    board = fixture(); owner = board.FindFootprintByReference('OWNER_RENAMED')
    policy = motion.limits(max_owner_copper_pads=16)
    if fault == 'locked': owner.SetLocked(True)
    if fault == 'fixed': policy['immutable_refs'] = ['OWNER_RENAMED']
    if fault == 'tht': pad(board, 'OWNER_RENAMED', 1).SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    if fault == 'drilled': pad(board, 'OWNER_RENAMED', 1).SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    if fault == 'grouped':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(owner)
    assert not motion.capture(board, target(), policy)['ok']


@pytest.mark.parametrize('stage', ['endpoint_owner_relocation', 'footprint_relocation'])
def test_stage_scope_reaches_generation_and_final_filter(tmp_path, monkeypatch, stage):
    source = tmp_path/'source.kicad_pcb'; board = fixture(); pcbnew.SaveBoard(str(source), board)
    seen = []
    def proposals(path, row, **kwargs):
        seen.append(kwargs['support_limits'])
        domain = motion.capture(board, row, kwargs['support_limits'])
        # Simulate the early occupancy check which previously killed ALL owner poses.
        return [dict(dx_mm=.05, dy_mm=0, rotation_delta_deg=0)] if domain['ok'] else []
    monkeypatch.setattr(repair, '_combined_footprint_relocation_candidates', proposals)
    monkeypatch.setattr(repair, '_spawn_apply', lambda worker, args, **kw: worker(*args))
    before = source.read_bytes()
    result = repair._attempt_footprint_relocation(str(source), {}, target(),
        work_dir=str(tmp_path), token='native-scope', stage_name=stage, max_copper_pads=16,
        max_candidates=0, support_limits=motion.limits())
    assert seen[0]['max_owner_copper_pads'] == (16 if stage == 'endpoint_owner_relocation' else 2)
    frontier = result['candidate_frontier']
    assert frontier['generated'] == frontier['unvisited'] == (1 if stage == 'endpoint_owner_relocation' else 0)
    assert source.read_bytes() == before and not result['adopted']


def test_measured_craft_geometry_is_skipped_before_native_transaction(tmp_path, monkeypatch):
    import cec_route_pose_history as poses
    source = tmp_path/'source.kicad_pcb'
    board = fixture(); pcbnew.SaveBoard(str(source), board)
    row = target()
    row.setdefault('route_endpoints', [])
    candidate = dict(dx_mm=.05, dy_mm=0, rotation_delta_deg=0)
    context = dict(stage='endpoint_owner_relocation', max_copper_pads=16, max_branch_tracks=8)
    key = poses.craft_geometry_key(row, candidate, context)
    assert key is not None
    # The later planning witness may point at a track instead of the old pad.
    row.update(endpoint_ref='', endpoint_pad='', endpoint_x_mm=39., endpoint_y_mm=27.)
    monkeypatch.setattr(repair, '_spawn_apply', lambda worker, args, **kw: worker(*args))
    result = repair._attempt_footprint_relocation(str(source), {}, row,
        work_dir=str(tmp_path), token='native-cache', stage_name='endpoint_owner_relocation',
        max_copper_pads=16, max_branch_tracks=8, max_candidates=1,
        candidate_override=[candidate], support_limits=motion.limits(), skip_candidate_keys=[key])
    assert result['candidate_frontier']['craft_geometry_prior_skipped'] == 1
    assert result['candidate_frontier']['scheduled'] == 0
    assert result['attempts'] == [] and not result['adopted']


@pytest.mark.parametrize('max_refs', [1, 2, 3, 4])
def test_planner_counts_owner_in_total_ref_bound(tmp_path, monkeypatch, max_refs):
    board = fixture()
    for index in range(5):
        part = pcbnew.FOOTPRINT(board); part.SetReference('SUPPORT_%s' % index)
        part.SetPosition(pcbnew.VECTOR2I_MM(20.5 + index*.3, 20.5))
        for number in ('1', '2'):
            item = pcbnew.PAD(part); item.SetNumber(number); item.SetNet(pad(board, 'OWNER_RENAMED', 1).GetNet())
            item.SetAttribute(pcbnew.PAD_ATTRIB_SMD); item.SetLayerSet(pcbnew.PAD.SMDMask())
            item.SetPosition(part.GetPosition()); item.SetSize(pcbnew.VECTOR2I_MM(.2, .2)); part.Add(item)
        board.Add(part)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    cert = dict(net='/SIGNAL_RENAMED', endpoints=[
        dict(endpoint='owner', kind='pad', ref='OWNER_RENAMED', pad='1', x_mm=20, y_mm=20),
        dict(endpoint='peer', kind='pad', ref='PEER_RENAMED', pad='1', x_mm=28, y_mm=20)])
    monkeypatch.setattr(repair, 'refusal_certificates', lambda _: [dict(certificate=cert, detail={})])
    monkeypatch.setattr(repair, '_surface_trapped_endpoint_labels', lambda *_: {'owner'})
    plan = repair.plan_endpoint_owner_repairs(str(source), {}, max_refs=max_refs)
    assert len(plan['targets']) == 1
    row = plan['targets'][0]
    assert len(row['companion_refs']) == max_refs - 1
    assert motion.capture(board, row, motion.limits(max_refs=max_refs, max_owner_copper_pads=16))['ok']


@pytest.mark.parametrize('ground_name', ['GND', '/renamed/AGND', '/elsewhere/PGND',
    'GNDA', 'GNDD', '/renamed/DGND'])
@pytest.mark.parametrize('back', [False, True])
def test_owner_affinity_does_not_collect_neighbours_by_ground_only(tmp_path, monkeypatch, ground_name, back):
    board = fixture(back=back)
    owner = board.FindFootprintByReference('OWNER_RENAMED')
    ground = pcbnew.NETINFO_ITEM(board, ground_name); board.Add(ground)
    other = pcbnew.NETINFO_ITEM(board, '/UNRELATED_TIMING_NET'); board.Add(other)
    pad(board, 'OWNER_RENAMED', 2).SetNet(ground)
    for ref, delta, connected in [('RETURN_ONLY_NEIGHBOUR', .8, False),
                                   ('ACTUAL_SUPPLY_SUPPORT', 2., True)]:
        part = pcbnew.FOOTPRINT(board); part.SetReference(ref)
        part.SetPosition(owner.GetPosition() + pcbnew.VECTOR2I_MM(delta, 0))
        for number, net in [('1', pad(board, 'OWNER_RENAMED', 1).GetNet() if connected else other),
                            ('2', ground)]:
            land = pcbnew.PAD(part); land.SetNumber(number); land.SetNet(net)
            land.SetAttribute(pcbnew.PAD_ATTRIB_SMD); land.SetLayerSet(pcbnew.PAD.SMDMask())
            land.SetSize(pcbnew.VECTOR2I_MM(.3,.3)); land.SetPosition(part.GetPosition()); part.Add(land)
        board.Add(part)
        if back: part.Flip(part.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    at = pad(board, 'OWNER_RENAMED', 1).GetPosition()
    peer = pad(board, 'PEER_RENAMED', 1).GetPosition()
    cert = dict(net='/SIGNAL_RENAMED', endpoints=[
        dict(endpoint='owner', kind='pad', ref='OWNER_RENAMED', pad='1', x_mm=at.x/1e6, y_mm=at.y/1e6),
        dict(endpoint='peer', kind='pad', ref='PEER_RENAMED', pad='1', x_mm=peer.x/1e6, y_mm=peer.y/1e6)])
    monkeypatch.setattr(repair, 'refusal_certificates', lambda _: [dict(certificate=cert, detail={})])
    monkeypatch.setattr(repair, '_surface_trapped_endpoint_labels', lambda *_: {'owner'})
    plan = repair.plan_endpoint_owner_repairs(str(source), {}, max_refs=2)
    assert len(plan['targets']) == 1
    assert plan['targets'][0]['companion_refs'] == ('ACTUAL_SUPPLY_SUPPORT',)


def routed_move(tmp_path, fault, *, back=False, owner_pads=3):
    board = fixture(offset=(42, -13) if back else (0, 0), back=back, owner_pads=owner_pads)
    for i in (1, 2):
        track(board, pad(board, 'OWNER_RENAMED', i), pad(board, 'ANCHOR_RENAMED', i).GetPosition())
    if fault == 'grouped':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(board.FindFootprintByReference('OWNER_RENAMED'))
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    candidate = tmp_path/'candidate.kicad_pcb'; repair._copy_board_family(str(source), str(candidate))
    moved = pcbnew.LoadBoard(str(candidate))
    original = {i: pad(moved, 'OWNER_RENAMED', i).GetPosition() for i in (1, 2)}
    owner = moved.FindFootprintByReference('OWNER_RENAMED')
    owner.SetPosition(owner.GetPosition() + pcbnew.VECTOR2I_MM(.6, 0))
    for i in (1, 2):
        if fault == 'lost_return' and i == 2: continue
        track(moved, pad(moved, 'OWNER_RENAMED', i), original[i])
    if fault != 'no_gain':
        item = pad(moved, 'OWNER_RENAMED', 1)
        end = pad(moved, 'PEER_RENAMED', 1).GetPosition()
        if fault == 'new_stub_only': end = item.GetPosition() + pcbnew.VECTOR2I_MM(2, 0)
        track(moved, item, end)
    if fault == 'missing_pad': owner.Remove(pad(moved, 'OWNER_RENAMED', 3))
    pcbnew.SaveBoard(str(candidate), moved)
    return source, candidate


@pytest.mark.parametrize('fault', ['none', 'no_gain', 'lost_return', 'new_stub_only', 'missing_pad'])
@pytest.mark.parametrize('back', [False, True])
def test_connectivity_benefit_uses_native_graph_not_claimed_airwires(tmp_path, fault, back):
    source, candidate = routed_move(tmp_path, fault, back=back)
    first, last = pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(candidate))
    proof = admission.endpoint_owner_connectivity(first, last, 'OWNER_RENAMED')
    assert proof['ok'] is (fault == 'none'), proof
    assert not proof['release_authority']
    if fault == 'lost_return': assert proof['reason'] == 'owner_original_component_not_restored'
    if fault in ('no_gain', 'new_stub_only'): assert proof['reason'] == 'owner_has_no_native_connectivity_gain'


@pytest.mark.parametrize('fault,reason', [
    ('none', 'support_placement_revalidated'),
    ('no_gain', 'owner_has_no_native_connectivity_gain'),
    ('lost_return', 'owner_original_component_not_restored'),
    ('grouped', 'immutable_or_out_of_scope_component'),
    ('fixed', 'immutable_or_out_of_scope_component'),
    ('large', 'immutable_or_out_of_scope_component'),
])
def test_independent_native_admission_integrates_owner_gate(tmp_path, monkeypatch, fault, reason):
    source, candidate = routed_move(tmp_path, fault, owner_pads=17 if fault == 'large' else 3)
    skeleton = tmp_path/'stock.kicad_pcb'; skeleton.write_bytes(source.read_bytes())
    state = dict(placement_scope='complete', placements=pipeline._placement_board_snapshot(source)['placements'],
        frozen_nets=[], skeleton=str(skeleton), unchanged_plan={'amps': 1})
    for path in (source, candidate):
        path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
        path.with_suffix('.kicad_dru').write_text('(version 1)\n')
    candidate.with_suffix('.kicad_pro').write_bytes(source.with_suffix('.kicad_pro').read_bytes())
    cfg = SimpleNamespace(params={}, pins={'OWNER_RENAMED': [20,20,0]} if fault == 'fixed' else {})
    monkeypatch.setattr(checkpoint, 'preservation', lambda *_: placement_proof())
    monkeypatch.setattr(synth, 'config_with_board_route_authority', lambda c,p: (c, dict(ok=True,bound=True)))
    monkeypatch.setattr(pipeline, '_measure_placement_physical_in_process', lambda *_: dict(ok=True))
    before = source.read_bytes(), candidate.read_bytes()
    proof = admission._native_prepare(source, candidate, tmp_path/'admission', cfg)
    assert proof['ok'] is (fault == 'none'), proof
    assert proof['reason'] == reason, proof
    assert (source.read_bytes(), candidate.read_bytes()) == before
