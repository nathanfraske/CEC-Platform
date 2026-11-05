"""Saved signed copper regions preserve real windows, strokes and authority."""
import pcbnew
import pytest

import cec_native_contour_regions as regions
import cec_power_contours as contours
import cec_rectilinear_copper as owner
from test_rectilinear_copper import fixture


def board(*, separate=False, angle=0, mirror=False, layer=pcbnew.F_Cu,
          locked=False, grouped=False):
    b, tracks = fixture(angle=angle, mirror=mirror, layer=layer,
                        locked=locked, grouped=grouped)
    if separate:
        start = tracks[0].GetStart()
        end = tracks[1].GetEnd()
        delta = tracks[0].GetEnd() - start
        tracks[1].SetStart(end-delta)
    else:
        a, corner, end = tracks[0].GetStart(), tracks[0].GetEnd(), tracks[1].GetEnd()
        fourth = end - (corner-a)
        for p, q in [(end, fourth), (fourth, a)]:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(p); t.SetEnd(q); t.SetNet(tracks[0].GetNet())
            t.SetLayer(layer); t.SetWidth(2_000_000); t.SetLocked(locked)
            b.Add(t); tracks.append(t)
            if grouped:
                list(b.Groups())[0].AddItem(t)
    return b, tracks


def proposal(b, tracks, **kwargs):
    return regions.plan(b, [t.m_Uuid.AsString() for t in tracks],
        required_width_nm=1_500_000, clearance_nm=200_000,
        min_thickness_nm=100_000, **kwargs)


def rehash(plan):
    plan.pop("plan_sha256")
    plan["plan_sha256"] = owner._digest(plan)


def filled(b, plan, emitted):
    zone = next(z for z in b.Zones() if z.m_Uuid.AsString() == emitted['zone_uuids'][0])
    zone.SetFilledPolysList(plan['layer_id'], regions.native_poly(plan['regions_nm']))
    zone.SetIsFilled(True)
    return zone


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu])
def test_saved_native_hole_survives_reload_and_real_refill(tmp_path, angle, mirror, layer):
    b, tracks = board(angle=angle, mirror=mirror, layer=layer)
    before = [owner._track_row(t) for t in tracks]
    plan = proposal(b, tracks)
    assert len(plan['regions_nm']) == 1
    assert len(plan['regions_nm'][0]['holes_nm']) == 1
    assert [owner._track_row(t) for t in tracks] == before
    emitted = regions.materialize(b, plan)
    assert not emitted['retired_track_uuids']
    regions.fill(b, plan, emitted['zone_uuids'])
    path = tmp_path/'signed-regions.kicad_pcb'
    pcbnew.SaveBoard(str(path), b)
    child = pcbnew.LoadBoard(str(path))
    result = regions.receive(child, plan, emitted['zone_uuids'])
    assert result['ok'] and result['complete'], result
    assert result['authored_hole_count'] == 1
    assert result['verified_track_count'] == 4
    assert not result['new_capacity_credited'] and not result['release_authority']
    assert not result['separate_regions_electrically_connected_inferred']
    original = {r['uuid']: r for r in before}
    assert {t.m_Uuid.AsString(): owner._track_row(t) for t in child.GetTracks()} == original
    z = next(iter(child.Zones()))
    assert z.Outline().HoleCount(0) == 1
    center = pcbnew.VECTOR2I(sum(r['start_nm'][0] for r in before)//4,
                            sum(r['start_nm'][1] for r in before)//4)
    assert not z.GetFilledPolysList(layer).Contains(center)
    z.UnFill()
    regions.fill(child, plan, emitted['zone_uuids'])
    assert regions.receive(child, plan, emitted['zone_uuids'])['ok']


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu])
def test_disconnected_native_regions_never_claim_a_new_connection(tmp_path, layer):
    b, tracks = board(separate=True, layer=layer)
    plan = proposal(b, tracks)
    assert len(plan['regions_nm']) == 2
    assert not plan['separate_regions_electrically_connected_inferred']
    emitted = regions.materialize(b, plan)
    assert len(emitted['zone_uuids']) == 2 and len(list(b.Zones())) == 2
    regions.fill(b, plan, emitted['zone_uuids'])
    path = tmp_path/'two-actual-regions.kicad_pcb'
    pcbnew.SaveBoard(str(path), b)
    result = regions.receive(pcbnew.LoadBoard(str(path)), plan, emitted['zone_uuids'])
    assert result['ok'] and result['region_count'] == 2, result


@pytest.mark.parametrize('position,allowed', [((34,34), True), ((34,30), False)])
def test_real_foreign_pad_can_occupy_window_but_not_the_conductor(position, allowed):
    b, tracks = board()
    n = pcbnew.NETINFO_ITEM(b, '/UNRELATED'); b.Add(n)
    fp = pcbnew.FOOTPRINT(b); b.Add(fp); p = pcbnew.PAD(fp); fp.Add(p)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetPosition(pcbnew.VECTOR2I_MM(*position)); p.SetSize(pcbnew.VECTOR2I_MM(1,1)); p.SetNet(n)
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); p.SetLayerSet(layers)
    if allowed:
        plan = proposal(b, tracks); emitted = regions.materialize(b, plan)
        regions.fill(b, plan, emitted['zone_uuids'])
        assert regions.receive(b, plan, emitted['zone_uuids'])['ok']
    else:
        with pytest.raises(owner.Refused, match='foreign_native_copper'):
            proposal(b, tracks)
        assert not list(b.Zones())


@pytest.mark.parametrize('locked,grouped', [(True,False),(False,True),(True,True)])
def test_exact_source_ownership_permission_and_retention(locked, grouped):
    b, tracks = board(locked=locked, grouped=grouped)
    ids = [t.m_Uuid.AsString() for t in tracks]
    with pytest.raises(owner.Refused): proposal(b, tracks)
    plan = proposal(b, tracks, allow_locked_track_uuids=ids, allow_grouped_track_uuids=ids)
    with pytest.raises(owner.Refused): regions.materialize(b, plan)
    assert not list(b.Zones()) and len(list(b.GetTracks())) == 4
    emitted = regions.materialize(b, plan, allow_locked_track_uuids=ids, allow_grouped_track_uuids=ids)
    if grouped:
        assert {t.m_Uuid.AsString() for t in list(b.Groups())[0].GetItems()} == set(ids+emitted['zone_uuids'])


@pytest.mark.parametrize('fault', ['hole_removed','filler_slab','domain_grown','fake_capacity',
    'priority','bad_width','bool_gap','bad_grid','bad_margin','mixed_owner','extra_flag'])
def test_rehashed_worker_plan_cannot_expand_region_or_weaken_authority(fault):
    b, tracks = board(); plan = proposal(b, tracks)
    if fault == 'hole_removed': plan['regions_nm'][0]['holes_nm'] = []
    elif fault == 'filler_slab': plan['regions_nm'][0]['outer_nm'] = [[20_000_000,20_000_000],[45_000_000,20_000_000],[45_000_000,45_000_000],[20_000_000,45_000_000]]
    elif fault == 'domain_grown': plan['actual_fill_regions_nm'][0]['holes_nm'] = []
    elif fault == 'fake_capacity': plan['new_capacity_credited'] = True
    elif fault == 'priority': plan['priority'] = 1
    elif fault == 'bad_width': plan['required_width_nm'] = 2_000_001
    elif fault == 'bool_gap': plan['clearance_nm'] = False
    elif fault == 'bad_grid': plan['contour_grid_nm'] = 0
    elif fault == 'bad_margin': plan['fill_envelope_margin_nm'] = 11
    elif fault == 'mixed_owner': plan['source_tracks'][1]['net'] = '/OTHER'
    elif fault == 'extra_flag': plan['waive_native_loss'] = True
    rehash(plan)
    with pytest.raises(owner.Refused): regions.materialize(b, plan)
    assert not list(b.Zones()) and len(list(b.GetTracks())) == 4


@pytest.mark.parametrize('fault', ['unfilled','missing_zone','source_width','source_pose',
    'hole_removed','actual_hole_filled','one_nm_loss','one_nm_spill','priority','pad_connection','layer'])
def test_actual_saved_geometry_loss_or_spill_is_not_waived(fault):
    b, tracks = board(); plan = proposal(b, tracks); emitted = regions.materialize(b, plan)
    zone = next(iter(b.Zones()))
    if fault != 'unfilled': zone = filled(b, plan, emitted)
    if fault == 'source_width': tracks[0].SetWidth(1_999_999)
    elif fault == 'source_pose': tracks[0].SetEnd(tracks[0].GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault == 'hole_removed': zone.Outline().RemoveAllContours(); zone.Outline().Append(regions.native_poly([{**plan['regions_nm'][0], 'holes_nm': []}]))
    elif fault == 'actual_hole_filled': zone.SetFilledPolysList(plan['layer_id'], regions.native_poly([{**plan['regions_nm'][0], 'holes_nm': []}]))
    elif fault == 'one_nm_loss':
        shape = zone.GetFilledPolysList(plan['layer_id']).CloneDropTriangulation()
        shape.BooleanSubtract(owner._poly([[30_000_000,30_000_000],[30_000_001,30_000_000],[30_000_001,30_000_001],[30_000_000,30_000_001]]))
        zone.SetFilledPolysList(plan['layer_id'], shape)
    elif fault == 'one_nm_spill':
        shape = zone.GetFilledPolysList(plan['layer_id']).CloneDropTriangulation()
        shape.BooleanAdd(owner._poly([[34_000_000,34_000_000],[34_000_001,34_000_000],[34_000_001,34_000_001],[34_000_000,34_000_001]]))
        zone.SetFilledPolysList(plan['layer_id'], shape)
    elif fault == 'priority': zone.SetAssignedPriority(3)
    elif fault == 'pad_connection': zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault == 'layer': zone.SetLayer(pcbnew.B_Cu)
    result = regions.receive(b, plan, ['missing'] if fault == 'missing_zone' else emitted['zone_uuids'])
    assert not result['ok'] and not result['complete'], result
    assert not result['new_capacity_credited'] and not result['release_authority']


def test_stale_source_binding_does_not_modify_the_board():
    b, tracks = board(); plan = proposal(b, tracks)
    list(b.GetFootprints())[0].SetPosition(pcbnew.VECTOR2I_MM(20,20))
    with pytest.raises(owner.Refused, match='source_geometry_binding'):
        regions.materialize(b, plan)
    assert not list(b.Zones())


@pytest.mark.parametrize('fault', ['duplicate','hidden_layer','non45','deadline'])
def test_unsupported_strokes_or_deadline_are_refused(fault):
    b, tracks = board()
    if fault == 'hidden_layer': tracks[0].SetLayer(pcbnew.In1_Cu)
    elif fault == 'non45': tracks[0].SetEnd(pcbnew.VECTOR2I_MM(37,31))
    with pytest.raises(owner.Refused):
        if fault == 'duplicate': proposal(b, tracks+tracks[:1])
        elif fault == 'deadline': proposal(b, tracks, timeout_s=0)
        else: proposal(b, tracks)
    assert not list(b.Zones())


def test_original_single_outline_owner_keeps_its_conservative_default():
    b, tracks = board()
    with pytest.raises(owner.Refused, match='separate_owner'):
        owner.plan(b, [t.m_Uuid.AsString() for t in tracks], required_width_nm=1_500_000,
                   clearance_nm=200_000, min_thickness_nm=100_000, contour_style='chamfer45')


def test_style_audit_receives_actual_holes_without_ignoring_exposed_caps():
    b, tracks = board()
    before = contours.audit_board(b)
    assert before['complete'] and before['finding_count'] > 0
    plan = proposal(b, tracks); emitted = regions.materialize(b, plan)
    regions.fill(b, plan, emitted['zone_uuids'])
    after = contours.audit_board(b)
    assert after['complete'] and after['finding_count'] == 0
    assert after['purposeful_native_cover_count'] == 4
    assert not after['replacement_authorized']
    # A renderer name or authored outline cannot replace missing actual copper.
    zone = next(iter(b.Zones())); zone.SetIsFilled(False)
    unsafe = contours.audit_board(b)
    assert unsafe['complete'] and unsafe['finding_count'] == before['finding_count']


@pytest.mark.parametrize('fault', ['missing_region','duplicate','reversed','new_rule','zero_gap'])
def test_region_identity_or_configuration_cannot_be_omitted_or_reassigned(fault):
    b, tracks = board(separate=True); plan = proposal(b, tracks)
    emitted = regions.materialize(b, plan); ids = emitted['zone_uuids']
    regions.fill(b, plan, ids)
    assert regions.receive(b, plan, ids)['ok']
    if fault == 'missing_region': ids = ids[:1]
    elif fault == 'duplicate': ids = [ids[0], ids[0]]
    elif fault == 'reversed': ids = list(reversed(ids))
    elif fault == 'new_rule': next(iter(b.Zones())).SetIsRuleArea(True)
    elif fault == 'zero_gap': next(iter(b.Zones())).SetLocalClearance(0)
    assert not regions.receive(b, plan, ids)['ok']


def test_declared_fresh_zone_identities_replay_exact_saved_native_regions(tmp_path):
    import uuid
    b, tracks = board(separate=True); plan = proposal(b, tracks)
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    emitted = regions.materialize(b, plan, zone_uuids=ids)
    assert emitted['zone_uuids'] == ids
    regions.fill(b, plan, ids)
    path = tmp_path/'exact-zone-identities.kicad_pcb'; pcbnew.SaveBoard(str(path), b)
    assert regions.receive(pcbnew.LoadBoard(str(path)), plan, ids)['ok']


@pytest.mark.parametrize('fault', ['invalid','too_few','duplicate','incumbent_identity'])
def test_invalid_new_zone_identities_are_refused_before_any_mutation(fault):
    import uuid
    b, tracks = board(separate=True); plan = proposal(b, tracks)
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    if fault == 'invalid': ids[0] = 'not-a-uuid'
    elif fault == 'too_few': ids = ids[:1]
    elif fault == 'duplicate': ids[1] = ids[0]
    elif fault == 'incumbent_identity': ids[0] = tracks[0].m_Uuid.AsString()
    with pytest.raises(owner.Refused): regions.materialize(b, plan, zone_uuids=ids)
    assert not list(b.Zones())


@pytest.mark.parametrize('fault', ['changed_fill','missing','priority','unfilled'])
def test_real_higher_priority_support_is_bound_by_saved_native_hole_bridges(fault):
    import time
    b, tracks = board()
    support = pcbnew.ZONE(b); support.SetNet(tracks[0].GetNet()); support.SetLayer(pcbnew.F_Cu)
    support.SetAssignedPriority(4); support.SetLocalClearance(200_000)
    support.SetMinThickness(100_000); support.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    support.Outline().Append(owner._poly([[28_000_000,28_000_000],[35_000_000,28_000_000],
        [35_000_000,32_000_000],[28_000_000,32_000_000]]))
    b.Add(support); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    plan = proposal(b, tracks)
    assert len(plan['supporting_zones']) == 1
    emitted = regions.materialize(b, plan); regions.fill(b, plan, emitted['zone_uuids'])
    assert regions.receive(b, plan, emitted['zone_uuids'])['ok']
    if fault == 'changed_fill':
        support.SetFilledPolysList(pcbnew.F_Cu, owner._poly([[0,0],[1,0],[1,1],[0,1]]))
    elif fault == 'missing': b.Remove(support)
    elif fault == 'priority': support.SetAssignedPriority(5)
    elif fault == 'unfilled': support.SetIsFilled(False)
    assert not regions.receive(b, plan, emitted['zone_uuids'])['ok']
