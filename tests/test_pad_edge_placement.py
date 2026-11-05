"""Board/cutout clearance is part of placement, not a late route surprise."""
import copy

import pytest
import cec_placement_geometry as geo


def native_fault(pad='p1', edge='e1', position=(20, 0)):
    return dict(type='copper_edge_clearance', severity='error', items=[
        dict(uuid=edge, pos=dict(x=position[0], y=position[1]), description='localized boundary'),
        dict(uuid=pad, description='localized pad')])


def evidence(ref='arbitrary'):
    result = geo.classify_drc({'violations':[native_fault()]},
                             {'p1':dict(ref=ref, pad='X', net='signal')})
    return dict(result, source_unchanged=True, sha256='source')


def test_native_pad_edge_is_kept_but_track_edge_is_not_placement():
    rows = [native_fault(), native_fault(pad='track')]
    result = geo.classify_drc({'violations':rows}, {'p1':dict(ref='any', pad='X', net='N')})
    assert not result['ok'] and result['pad_edge_count'] == 1
    assert result['pad_copper_count'] == 0
    assert result['findings'][0]['domain'] == 'pad_edge'
    assert len(geo.craft_projection(dict(result, source_unchanged=True))['violations']) == 1


def test_edge_conflict_identity_survives_uuid_changes_but_distinguishes_edges():
    one = geo.craft_projection(evidence())
    same = copy.deepcopy(one)
    for item in same['violations'][0]['members']:
        item['uuid'] = 'normalized'
        item['description'] = 'different language'
    assert geo.craft_conflict_keys(one) == geo.craft_conflict_keys(same)
    same['violations'][0]['members'][0]['pos'] = dict(x=0, y=15)
    assert geo.craft_conflict_keys(one) != geo.craft_conflict_keys(same)


def test_one_movable_edge_footprint_is_not_an_immutable_self_short():
    assert geo.fixed_pad_conflicts(evidence(), [])['ok']
    assert not geo.fixed_pad_conflicts(evidence(), ['arbitrary'])['ok']
    with pytest.raises(ValueError, match='ownership'):
        geo.fixed_pad_conflicts({'findings':[dict(domain='pad_edge', items=[])]}, [])


def test_edge_proposals_preserve_complete_cells_and_fixed_anchors():
    poses = {'owner':(15,4,90), 'arbitrary':(19,4,180)}
    projected = geo.craft_projection(evidence())
    proposals = geo.clearance_move_specs(projected, poses, owner_by_cap={'arbitrary':'owner'}, max_specs=8)
    assert len(proposals) == 8
    for proposal in proposals:
        assert proposal['kind'] == 'native_pad_edge_reseat'
        assert proposal['proposal_only'] and set(proposal['placements']) == set(poses)
        a, b = proposal['placements']['owner'], proposal['placements']['arbitrary']
        assert (b[0]-a[0], b[1]-a[1], a[2], b[2]) == pytest.approx((4,0,90,180))
    assert not geo.clearance_move_specs(projected, poses, owner_by_cap={'arbitrary':'owner'}, fixed=['owner'])


def test_edge_budget_covers_cardinal_escape_before_subclearance_steps():
    proposals=geo.clearance_move_specs(geo.craft_projection(evidence()),
        {'arbitrary':(4,4,0)},steps_mm=(.05,.1,.2,.4),max_specs=4)
    assert {p['distance_mm'] for p in proposals}=={.4}
    assert {p['position'][:2] for p in proposals}=={(3.6,4),(4,3.6),(4,4.4),(4.4,4)}


def test_native_progress_screen_cannot_admit_unchanged_missing_or_new_faults():
    before=geo.craft_projection(evidence())
    assert not geo.required_progress(before,before,domain='pad_edge')['ok']
    assert not geo.required_progress(None,before,domain='pad_edge')['ok']
    after=dict(before,violations=[])
    result=geo.required_progress(before,after,domain='pad_edge')
    assert result['ok'] and result['removed_faults']==1 and not result['admission_authority']
    after['violations']=[dict(domain='pad_copper',type='clearance',members=[{'ref':'foreign'}])]
    assert not geo.required_progress(before,after,domain='pad_edge')['ok']


def test_nonimproving_edge_trial_skips_expensive_craft(monkeypatch):
    import cec_synth_pipeline as synth
    measured=evidence()
    monkeypatch.setattr(synth,'materialize',lambda *a:None)
    monkeypatch.setattr(geo,'evaluate',lambda *a:measured)
    def forbidden(*args,**kwargs):raise AssertionError('unchanged native fault must not spend full craft budget')
    monkeypatch.setattr(synth,'placement_craft_evidence',forbidden)
    from types import SimpleNamespace
    result=synth._placement_craft_trial_worker(dict(candidate=SimpleNamespace(),cfg=None,path='unused',
        required_native_progress='pad_edge',baseline_geometry=geo.craft_projection(measured)))
    assert not result['ok'] and result['error_kind']=='native_clearance_progress'


def test_owned_cutout_does_not_receive_futile_rigid_translation():
    result = geo.classify_drc({'violations':[native_fault()]},
        {'p1':dict(ref='arbitrary', pad='X', net='N')}, {'e1':'arbitrary'})
    assert not geo.fixed_pad_conflicts(result, [])['ok']
    assert result['findings'][0]['items'][0]['edge_owner_ref'] == 'arbitrary'
    assert 'ref' not in result['findings'][0]['items'][0]
    projected = geo.craft_projection(dict(result, source_unchanged=True))
    assert not geo.clearance_move_specs(projected, {'arbitrary':(5,5,0)})
    # An aperture on a different, independently seated footprint may be
    # avoided, but never by translating the whole coupled cell together.
    result['findings'][0]['items'][0]['edge_owner_ref'] = 'owner'
    projected = geo.craft_projection(dict(result, source_unchanged=True))
    poses = {'arbitrary':(5,5,0), 'owner':(7,5,0)}
    assert geo.fixed_pad_conflicts(result, [])['ok']
    assert geo.clearance_move_specs(projected, poses)
    assert not geo.clearance_move_specs(projected, poses, owner_by_cap={'arbitrary':'owner'})


@pytest.mark.parametrize('back,cutout,owned', [
    (False,False,False), (True,False,False), (False,True,False),
    (True,True,False), (False,True,True), (True,True,True)])
def test_native_edge_rule_detects_and_bounded_move_repairs(tmp_path, back, cutout, owned):
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    board = pcbnew.BOARD()
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('edge-device')
    loops = [[(0,0),(20,0),(20,15),(0,15),(0,0)]]
    if cutout:
        loops.append([(9,4),(11,4),(11,6),(9,6),(9,4)])
    owned_edges = []
    for loop_idx, corners in enumerate(loops):
        for a,b in zip(corners,corners[1:]):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            board.Add(edge)
            if owned and loop_idx:
                owned_edges.append(edge)
    pad = pcbnew.PAD(fp)
    pad.SetNumber('1')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    fp.Add(pad)
    board.Add(fp)
    x = 8.3 if cutout else 19.3
    fp.SetPosition(pcbnew.VECTOR2I_MM(x,5))
    if back:
        fp.Flip(fp.GetPosition(),False)
    # Transfer unchanged world-space cutout geometry into the footprint,
    # so the native saved-board identity supplies ownership evidence.
    for edge in owned_edges:
        board.Remove(edge)
        fp.Add(edge)
    path = tmp_path/'board.kicad_pcb'
    pcbnew.SaveBoard(str(path),board)
    path.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "edge-limit" (constraint edge_clearance (min 0.5mm)))\n')
    before = path.read_bytes()
    result = geo.evaluate(path)
    assert not result['ok'] and result['pad_edge_count'] == 1, result
    assert result['source_unchanged'] and path.read_bytes() == before
    if owned:
        assert not geo.fixed_pad_conflicts(result, [])['ok']
        assert not geo.clearance_move_specs(geo.craft_projection(result),
                                           {'edge-device':(x,5,0)})
        fp.SetPosition(pcbnew.VECTOR2I_MM(x-.4,5))
        pcbnew.SaveBoard(str(path),board)
        assert geo.evaluate(path)['pad_edge_count'] == 1
        return
    proposal = next(p for p in geo.clearance_move_specs(geo.craft_projection(result),
        {'edge-device':(x,5,fp.GetOrientationDegrees())}, steps_mm=(.4,))
        if p['position'][0] < x and p['position'][1] == 5)
    fp.SetPosition(pcbnew.VECTOR2I_MM(*proposal['position'][:2]))
    pcbnew.SaveBoard(str(path),board)
    after = geo.evaluate(path)
    assert after['ok'] and after['pad_edge_count'] == 0, after
