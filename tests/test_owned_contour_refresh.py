"""Source-derived contours follow retained motion without bounding-box fill."""
import copy

import pcbnew
import pytest

import cec_owned_contour_refresh as refresh
import cec_native_contour_regions as regions
import cec_rectilinear_copper as owner
from test_native_contour_regions import board, proposal


def fixture(tmp_path, *, angle=0, mirror=False, layer=pcbnew.F_Cu, locked=False):
    source, tracks = board(angle=angle, mirror=mirror, layer=layer, locked=locked)
    ids = [t.m_Uuid.AsString() for t in tracks]
    old = proposal(source, tracks, allow_locked_track_uuids=ids)
    emitted = regions.materialize(source, old, allow_locked_track_uuids=ids)
    regions.fill(source, old, emitted['zone_uuids'])
    path = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(path), source)
    source, child = [pcbnew.LoadBoard(str(path)) for _ in range(2)]
    for t in child.GetTracks(): t.Move(pcbnew.VECTOR2I(0, -500_000))
    parameters = {k: old[k] for k in regions.PARAMETERS}
    return source, child, dict(zone_uuid=emitted['zone_uuids'][0], track_uuids=ids,
        parameters=parameters, allow_locked_zone=locked, allow_locked_track_uuids=ids)


def filled(board, result):
    import cec_zone_fill
    zone = next(z for z in board.Zones() if z.m_Uuid.AsString() == result['zone_uuid'])
    cec_zone_fill.compile_selected(board, [zone], initialize_selected=True)


def rehash(result):
    result.pop('plan_sha256'); result['plan_sha256'] = owner._digest(result)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu])
def test_refresh_rebuilds_actual_saved_windows_without_touching_tracks(tmp_path, angle, mirror, layer):
    source, child, args = fixture(tmp_path, angle=angle, mirror=mirror, layer=layer)
    tracks = [owner._track_row(t) for t in child.GetTracks()]
    result = refresh.plan(source, child, **args)
    assert len(result['candidate_regions_nm'][0]['holes_nm']) == 1
    emitted = refresh.materialize(child, result,source=source)
    assert not emitted['tracks_added_or_retired']
    filled(child, result)
    path = tmp_path/'child.kicad_pcb'; pcbnew.SaveBoard(str(path), child)
    saved = pcbnew.LoadBoard(str(path))
    received = refresh.receive(saved, result,source=source)
    assert received['ok'] and received['complete'], received
    assert received['source_track_count'] == 4
    assert received['external_motion_receiving_required']
    assert not received['current_qualified'] and not received['new_capacity_credited']
    assert not received['release_authority']
    assert [owner._track_row(t) for t in saved.GetTracks()] == tracks
    assert next(iter(saved.Zones())).m_Uuid.AsString() == args['zone_uuid']


@pytest.mark.parametrize('fault', ['width', 'net', 'face', 'group', 'lock', 'missing_track',
    'wrong_source_outline', 'source_filler', 'stale_candidate_outline', 'source_priority',
    'source_clearance', 'thermal', 'non45', 'no_motion', 'duplicate', 'extra_parameter',
    'bad_gap', 'foreign_pad', 'zero_deadline'])
def test_stale_incomplete_or_unrelated_owned_geometry_is_refused(tmp_path, fault):
    source, child, args = fixture(tmp_path)
    t = next(iter(child.GetTracks())); z = next(iter(source.Zones()))
    if fault == 'width': t.SetWidth(t.GetWidth()-1)
    elif fault == 'net': t.SetNetCode(0)
    elif fault == 'face': t.SetLayer(pcbnew.B_Cu)
    elif fault == 'group':
        g = pcbnew.PCB_GROUP(child); child.Add(g); g.AddItem(t)
    elif fault == 'lock': t.SetLocked(True)
    elif fault == 'missing_track': child.Remove(t)
    elif fault == 'wrong_source_outline': z.Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'source_filler':
        r = copy.deepcopy(args['parameters'])
        poly = regions.native_poly([dict(outer_nm=[[20_000_000,20_000_000],[45_000_000,20_000_000],
            [45_000_000,45_000_000],[20_000_000,45_000_000]], holes_nm=[])])
        z.Outline().RemoveAllContours(); z.Outline().Append(poly)
    elif fault == 'stale_candidate_outline': next(iter(child.Zones())).Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'source_priority': z.SetAssignedPriority(2)
    elif fault == 'source_clearance': z.SetLocalClearance(199_999)
    elif fault == 'thermal': z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault == 'non45': t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,1))
    elif fault == 'no_motion':
        for item in child.GetTracks(): item.Move(pcbnew.VECTOR2I(0,500_000))
    elif fault == 'duplicate': args['track_uuids'].append(args['track_uuids'][0])
    elif fault == 'extra_parameter': args['parameters']['waive'] = True
    elif fault == 'bad_gap': args['parameters']['clearance_nm'] = False
    elif fault == 'foreign_pad':
        n = pcbnew.NETINFO_ITEM(child, '/FOREIGN'); child.Add(n)
        fp = pcbnew.FOOTPRINT(child); child.Add(fp); pad = pcbnew.PAD(fp); fp.Add(pad)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetNet(n); pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        pad.SetPosition(pcbnew.VECTOR2I_MM(34,29.5)); layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
    elif fault == 'zero_deadline': args['timeout_s'] = 0
    before = regions._binding(child)
    with pytest.raises(owner.Refused): refresh.plan(source, child, **args)
    assert regions._binding(child) == before


def test_exact_locked_permissions_required(tmp_path):
    source, child, args = fixture(tmp_path, locked=True)
    args['allow_locked_zone'] = False
    with pytest.raises(owner.Refused): refresh.plan(source, child, **args)
    args['allow_locked_zone'] = True; args['allow_locked_track_uuids'] = []
    with pytest.raises(owner.Refused): refresh.plan(source, child, **args)
    args['allow_locked_track_uuids'] = [t.m_Uuid.AsString() for t in source.GetTracks()]
    assert refresh.plan(source, child, **args)


@pytest.mark.parametrize('fault', ['worker_capacity', 'worker_waiver', 'filler', 'source_hole',
    'source_row', 'fill_spill', 'source_width', 'added_flag'])
def test_rehashed_worker_refresh_cannot_forge_source_or_fill(tmp_path, fault):
    source, child, args = fixture(tmp_path)
    result = refresh.plan(source, child, **args)
    if fault == 'worker_capacity': result['new_capacity_credited'] = True
    elif fault == 'worker_waiver': result['external_motion_receiving_required'] = False
    elif fault == 'filler': result['candidate_regions_nm'][0]['holes_nm'] = []
    elif fault == 'source_hole': result['source_regions_nm'][0]['holes_nm'] = []
    elif fault == 'source_row': result['source_tracks'][0]['start_nm'][0] += 1
    elif fault == 'fill_spill': result['actual_fill_regions_nm'][0]['holes_nm'] = []
    elif fault == 'source_width': result['source_tracks'][0]['width_nm'] -= 1
    elif fault == 'added_flag': result['old_source_was_good'] = True
    rehash(result); before = regions._binding(child)
    with pytest.raises(owner.Refused): refresh.materialize(child, result,source=source)
    assert regions._binding(child) == before


@pytest.mark.parametrize('fault', ['stale', 'unfilled', 'missing', 'hole_filled', 'track', 'priority'])
def test_saved_refresh_loss_is_not_hidden(tmp_path, fault):
    source, child, args = fixture(tmp_path); result = refresh.plan(source, child, **args)
    if fault != 'stale': refresh.materialize(child, result,source=source)
    if fault not in ('stale','unfilled'): filled(child, result)
    z = next(iter(child.Zones()))
    if fault == 'missing': child.Remove(z)
    elif fault == 'hole_filled':
        z.SetFilledPolysList(z.GetLayer(), regions.native_poly([
            {**result['candidate_regions_nm'][0], 'holes_nm': []}]))
    elif fault == 'track': next(iter(child.GetTracks())).Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'priority': z.SetAssignedPriority(3)
    assert not refresh.receive(child, result,source=source)['ok']


@pytest.mark.parametrize('fault',['source_shift','source_binding','missing_source'])
def test_exact_source_must_be_replayed_not_reconstructed_from_quantized_outline(tmp_path,fault):
    source,child,args=fixture(tmp_path);result=refresh.plan(source,child,**args)
    actual=source
    if fault=='source_shift':next(iter(source.GetTracks())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_binding':result['source_geometry_binding']='0'*64;rehash(result)
    else:actual=None
    before=regions._binding(child)
    with pytest.raises(owner.Refused):refresh.materialize(child,result,source=actual)
    assert regions._binding(child)==before
    assert not refresh.receive(child,result,source=actual)['ok']
