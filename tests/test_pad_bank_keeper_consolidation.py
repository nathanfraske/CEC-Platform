"""Solid generated banks can join keepers without changing their old copper."""
import time

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_multi_keeper_contour as owner
import cec_native_fill_geometry as geometry
import cec_pad_bank_collector as bank
import cec_regional_fill as regional
from test_pad_bank_collector import fixture


def case(tmp_path, angle=0, mirror=False, face=pcbnew.F_Cu, bank_first=False):
    b, pads, tracks = fixture(angle, mirror, face)
    proposal = bank.plan(b, [force._uid(p) for p in pads], layer_id=face,
        clearance_nm=200000, min_thickness_nm=200000)
    made = bank.materialize(b, proposal)
    z = next(q for q in b.Zones() if force._uid(q) == made['zone_uuid'])
    z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-00000000000'+str(1 if bank_first else 2)))
    # A distinct registered solid contour at the far end of a retained lead.
    # The real bank above is generated from the actual pad row, not renamed
    # test geometry. All transforms exercise the exact same runtime policy.
    keeper = pcbnew.ZONE(z); keeper.m_Uuid.Clone(pcbnew.KIID(
        '00000000-0000-4000-8000-00000000000'+str(2 if bank_first else 1)))
    keeper.SetZoneName(owner.signed.ZONE_NAME); keeper.SetLocked(False)
    keeper.SetMinThickness(100000); keeper.Outline().RemoveAllContours()
    x, y = tracks[0].GetEnd(); r = 1800000
    keeper.Outline().NewOutline()
    for px, py in ((x-r,y-r),(x+r,y-r),(x+r,y+r),(x-r,y+r)):
        keeper.Outline().Append(px, py)
    b.Add(keeper); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(b, source)
    return b, source, pads, tracks, z, keeper


def plan(source, tracks, **options):
    kwargs = dict(allow_locked_source=True, fill_policy='source_preserving_regions',
        allow_compatible_keeper_classes=True, allow_conservative_keeper_contract=True,
        clip_native_additions=True, native_addition_inset_nm=4)
    kwargs.update(options)
    return owner.plan(source, [force._uid(tracks[0])], **kwargs)


@pytest.mark.parametrize('angle', [0,90,180,270])
@pytest.mark.parametrize('mirror', [False,True])
@pytest.mark.parametrize('face', [pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('bank_first', [False,True])
def test_native_generated_bank_and_keeper_join_keeps_pads_drills_tracks_and_every_old_fill(
        tmp_path, angle, mirror, face, bank_first):
    b, source, pads, tracks, z, keeper = case(tmp_path, angle, mirror, face, bank_first)
    original = source.read_bytes(); p = plan(source, tracks)
    assert len(p['source_zones']) == 2 and p['retained_keeper_locked']
    assert p['retained_keeper_min_thickness_nm'] == 200000
    assert {q['configuration']['name'] for q in p['source_zones']} == {bank.ZONE_NAME,owner.signed.ZONE_NAME}
    child = force._copy_family(source, tmp_path/'child'); made = owner.construct(b, p)
    field._save_field_snapshot(b, child); saved = pcbnew.LoadBoard(str(child))
    assert len(list(saved.Zones())) == 1
    kept = next(iter(saved.Zones())); assert kept.IsLocked() and kept.GetMinThickness() == 200000
    for row in p['source_zones']:
        assert regional.exact_source_contour_present(kept.GetFilledPolysList(face),
            geometry.reconstruct(row['fill'],time.monotonic()+10.),time.monotonic()+10.)
    _, old = additive._nodes(source); _, new = additive._nodes(child)
    for item in [*saved.GetFootprints(),*tracks]:
        assert syntax._freeze(old[force._uid(item)]) == syntax._freeze(new[force._uid(item)])
    received = owner.receive(source, child, [dict(plan=p,materialized=made)],board_hint='synthetic')
    assert received['ok'] and received['complete'], received['errors']
    assert received['every_source_track_and_old_fill_retained']
    assert not received['new_capacity_credited'] and not received['release_authority']
    assert source.read_bytes() == original


@pytest.mark.parametrize('options', [dict(allow_compatible_keeper_classes=False),
    dict(allow_conservative_keeper_contract=False), dict(allow_locked_source=False),
    dict(fill_policy='native'), dict(allow_compatible_keeper_classes=1)])
def test_explicit_source_preserving_class_and_conservative_process_policy_required(tmp_path,options):
    b, source, pads, tracks, z, keeper = case(tmp_path)
    original = source.read_bytes()
    with pytest.raises(owner.Refused): plan(source,tracks,**options)
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['clearance','thermal_gap','thermal_spoke','connection','priority',
    'unknown_name','group','unfilled','smoothing','wrong_net','wrong_face'])
def test_bank_name_does_not_grant_process_or_ownership_normalization(tmp_path,fault):
    b, source, pads, tracks, z, keeper = case(tmp_path)
    if fault == 'clearance': z.SetLocalClearance(250000)
    elif fault == 'thermal_gap': z.SetThermalReliefGap(333333)
    elif fault == 'thermal_spoke': z.SetThermalReliefSpokeWidth(333333)
    elif fault == 'connection': z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault == 'priority': z.SetAssignedPriority(2)
    elif fault == 'unknown_name': z.SetZoneName('unregistered-solid-region')
    elif fault == 'group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(z)
    elif fault == 'unfilled': z.UnFill()
    elif fault == 'smoothing': z.SetCornerSmoothingType(1)
    elif fault == 'wrong_net': z.SetNetCode(0)
    else: z.SetLayer(pcbnew.B_Cu)
    field._save_field_snapshot(b, source); original = source.read_bytes()
    with pytest.raises(owner.Refused): plan(source,tracks)
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['name','min_floor','lock','old_fill','profile','retired_bank'])
def test_rehashed_worker_cannot_choose_bank_process_ownership_or_new_geometry(tmp_path,fault):
    b, source, pads, tracks, z, keeper = case(tmp_path); p=plan(source,tracks)
    if fault == 'name': p['source_zones'][1]['configuration']['name']='unregistered'
    elif fault == 'min_floor': p['retained_keeper_min_thickness_nm']=100000
    elif fault == 'lock': p['retained_keeper_locked']=False
    elif fault == 'old_fill': p['source_zones'][1]['fill'][0][0][0][0]+=1
    elif fault == 'profile': p['profile'][0][0][0][0]+=1
    else: p['retired_zone_uuids']=[]
    p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
    original=field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused): owner.construct(b,p)
    assert field._field_snapshot_inventory(b)==original


@pytest.mark.parametrize('fault', ['pad_drill','pad_pose','track_width','thermal','lost_fill','extra_copper'])
def test_saved_phase_replay_rejects_source_or_candidate_drift(tmp_path,fault):
    b, source, pads, tracks, z, keeper = case(tmp_path); p=plan(source,tracks)
    made=owner.construct(b,p)
    if fault == 'pad_drill': pads[0].SetDrillSize(pcbnew.VECTOR2I(1000000,1000000))
    elif fault == 'pad_pose': pads[0].Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'track_width': tracks[0].SetWidth(tracks[0].GetWidth()-1)
    elif fault == 'thermal': next(iter(b.Zones())).SetThermalReliefGap(333333)
    elif fault == 'lost_fill':
        kept=next(iter(b.Zones()));fill=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        fill.RemoveOutline(fill.OutlineCount()-1);kept.SetFilledPolysList(pcbnew.F_Cu,fill)
    else:
        item=tracks[0].Duplicate();item.m_Uuid.Clone(pcbnew.KIID())
        item.Move(pcbnew.VECTOR2I(20000000,0));b.Add(item)
    child=force._copy_family(source,tmp_path/'bad');field._save_field_snapshot(b,child)
    original=[p.read_bytes() for p in (source,child)]
    result=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert not result['ok'] and not result['complete'] and result['errors']
    assert original==[p.read_bytes() for p in (source,child)]
