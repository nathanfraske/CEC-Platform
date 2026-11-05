"""Compatible owners may be consolidated; process/physical evidence may not."""
import copy
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_multi_keeper_contour as owner
import cec_native_contour_regions as signed
import cec_native_fill_geometry as geometry
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path, face=pcbnew.F_Cu, rotate=False):
    xy = lambda p: (p[1],p[0]) if rotate else p
    net = '/TEST/RENAMED-SUPPLY'
    b = _board([(*xy(p),net) for p in ((3,6),(11,6))],edge=(0,0,16,16))
    b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if face not in (pcbnew.F_Cu,pcbnew.B_Cu):
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
                pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                if face == pcbnew.B_Cu:fp.SetLayer(face)
                mask=pcbnew.LSET();mask.AddLayer(face);pad.SetLayerSet(mask)
    t = track(b,net,xy((3,6)),xy((11,6)),layer=face);t.SetWidth(1000000)
    keepers = []
    for x0,x1 in ((2.5,4.5),(9.5,11.5)):
        z=pcbnew.ZONE(b);z.SetNet(t.GetNet());z.SetLayer(face);z.SetZoneName(signed.ZONE_NAME)
        z.SetLocalClearance(200000);z.SetMinThickness(100000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocked(True);z.Outline().NewOutline()
        for p in ((x0,5.5),(x1,5.5),(x1,6.5),(x0,6.5)):
            v=pcbnew.VECTOR2I_MM(*xy(p));z.Outline().Append(v.x,v.y)
        b.Add(z);keepers.append(z)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return b,source,t,keepers


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_literal_saved_owner_union_preserves_tracks_process_and_actual_old_fill(tmp_path,face,rotate):
    b,source,t,zones=fixture(tmp_path,face,rotate);original=source.read_bytes()
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True)
    child=force._copy_family(source,tmp_path/'child');c=pcbnew.LoadBoard(str(child))
    made=owner.construct(c,p);field._save_field_snapshot(c,child);saved=pcbnew.LoadBoard(str(child))
    assert len(list(saved.Zones()))==1 and len(list(saved.GetTracks()))==1
    kept=next(iter(saved.Zones()));assert kept.IsLocked() and kept.GetLocalClearance()==200000
    assert kept.Outline().OutlineCount()==1
    for old in p['source_zones']:
        missing=geometry.reconstruct(old['fill'],time.monotonic()+10)
        missing.BooleanSubtract(kept.GetFilledPolysList(face));assert not missing.OutlineCount()
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert not proof['release_authority'] and not proof['new_capacity_credited']
    assert source.read_bytes()==original


@pytest.mark.parametrize('mode',['clearance','thermal_gap','lock','group','name','priority','unfilled','no_lock','reference_net'])
def test_no_process_ownership_or_ground_waiver(tmp_path,mode):
    b,source,t,zones=fixture(tmp_path)
    if mode=='clearance':zones[1].SetLocalClearance(250000)
    elif mode=='thermal_gap':zones[1].SetThermalReliefGap(333333)
    elif mode=='lock':zones[1].SetLocked(False)
    elif mode=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(zones[1])
    elif mode=='name':zones[1].SetZoneName('unregistered-owner')
    elif mode=='priority':zones[1].SetAssignedPriority(1)
    elif mode=='unfilled':zones[1].UnFill()
    elif mode=='reference_net':
        n=b.FindNet('GND')
        if n is None:n=pcbnew.NETINFO_ITEM(b,'GND');b.Add(n)
        t.SetNet(n)
        for z in zones:z.SetNet(n)
        for fp in b.GetFootprints():
            for pad in fp.Pads():pad.SetNet(n)
        b.BuildConnectivity()
    field._save_field_snapshot(b,source);original=source.read_bytes()
    with pytest.raises(owner.Refused):
        owner.plan(source,[force._uid(t)],allow_locked_source=mode!='no_lock')
    assert source.read_bytes()==original


@pytest.mark.parametrize('mode',['profile','source_fill','retired_id','process_digest'])
def test_rehashed_worker_plan_cannot_mutate_actual_board(tmp_path,mode):
    b,source,t,zones=fixture(tmp_path);p=owner.plan(source,[force._uid(t)],allow_locked_source=True)
    if mode=='profile':p['profile'][0][0][0][0]+=1000
    elif mode=='source_fill':p['source_zones'][0]['fill'][0][0][0][0]+=1000
    elif mode=='retired_id':p['retired_zone_uuids']=[]
    else:p['source_process_sha256']='0'*64
    p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused):owner.construct(b,p)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('mode',['source_track','candidate_extra','candidate_process'])
def test_whole_saved_replay_detects_out_of_transaction_edit(tmp_path,mode):
    b,source,t,zones=fixture(tmp_path);p=owner.plan(source,[force._uid(t)],allow_locked_source=True)
    child=force._copy_family(source,tmp_path/'child');made=owner.construct(b,p)
    if mode=='candidate_extra':track(b,t.GetNetname(),(3,10),(4,10))
    elif mode=='candidate_process':next(iter(b.Zones())).SetThermalReliefGap(444444)
    field._save_field_snapshot(b,child)
    if mode=='source_track':
        original=pcbnew.LoadBoard(str(source));next(iter(original.GetTracks())).SetWidth(1100000)
        field._save_field_snapshot(original,source)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def test_disconnected_authoring_is_refused_instead_of_losing_an_outer_contour_on_save(tmp_path):
    b,source,t,zones=fixture(tmp_path);t.SetEnd(pcbnew.VECTOR2I_MM(4,6))
    other=track(b,t.GetNetname(),(10,6),(11,6));other.SetWidth(1000000)
    field._save_field_snapshot(b,source);original=source.read_bytes()
    with pytest.raises(owner.Refused,match='one_connected_literal_saved_keeper_outline_required'):
        owner.plan(source,[force._uid(t),force._uid(other)],allow_locked_source=True)
    assert source.read_bytes()==original


def test_partial_native_report_never_dispatches_an_owner_edit(tmp_path,monkeypatch):
    import cec_multi_keeper_contour_stage as stage
    b,source,t,zones=fixture(tmp_path);original=source.read_bytes()
    monkeypatch.setattr(stage.native,'run',lambda *a,**k:dict(ok=True,complete=False,
        native_inventory=dict(potentially_truncated=True)))
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build='not-used',allow_locked_source=True)
    assert not r['ok'] and not r['complete'] and not r['changed'] and not r['attempts']
    assert source.read_bytes()==original


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_explicit_preserving_mode_roundtrips_every_literal_incumbent_record(tmp_path,face,rotate):
    import cec_regional_fill as regional
    b,source,t,zones=fixture(tmp_path,face,rotate)
    # Two overlapping positive records encode an existing source-preserving
    # owner. A native union/refill is not allowed to erase that provenance.
    old=zones[0].GetFilledPolysList(face).CloneDropTriangulation()
    old.Append(zones[0].GetFilledPolysList(face));zones[0].SetFilledPolysList(face,old)
    zones[0].SetIsFilled(True);field._save_field_snapshot(b,source);original=source.read_bytes()
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions')
    c=pcbnew.LoadBoard(str(source));made=owner.construct(c,p)
    child=force._copy_family(source,tmp_path/'preserving');field._save_field_snapshot(c,child)
    saved=pcbnew.LoadBoard(str(child));kept=next(iter(saved.Zones()))
    for row in p['source_zones']:
        assert regional.exact_source_contour_present(kept.GetFilledPolysList(face),
            geometry.reconstruct(row['fill'],time.monotonic()+10),time.monotonic()+10)
    assert made['source_preserving_native_fill']['all_additions_from_anchored_native_fill']
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert not made['new_capacity_credited'] and not made['release_authority'] and source.read_bytes()==original


def test_old_native_boundary_is_not_rounded_away_by_fresh_compilation(tmp_path):
    import cec_regional_fill as regional
    b,source,t,zones=fixture(tmp_path)
    fill=zones[0].GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    # An explicit frozen source-boundary witness, not a geometry tolerance.
    # The new source-preserving producer must carry it verbatim or refuse.
    q=fill.Outline(0).CPoint(0);fill.Outline(0).SetPoint(0,pcbnew.VECTOR2I(q.x,q.y-1))
    zones[0].SetFilledPolysList(pcbnew.F_Cu,fill);zones[0].SetIsFilled(True)
    field._save_field_snapshot(b,source)
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions')
    made=owner.construct(b,p);kept=next(iter(b.Zones()))
    assert regional.exact_source_contour_present(kept.GetFilledPolysList(pcbnew.F_Cu),fill,time.monotonic()+10)
    assert made['every_source_track_and_old_fill_retained']


@pytest.mark.parametrize('fault',['missing_old_record','added_fill','forged_policy','changed_protected_fill'])
def test_saved_preserving_mode_rejects_fabricated_source_or_output(tmp_path,fault):
    b,source,t,zones=fixture(tmp_path)
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions')
    made=owner.construct(b,p);kept=next(iter(b.Zones()))
    if fault=='missing_old_record':
        filled=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        filled.RemoveOutline(filled.OutlineCount()-1);kept.SetFilledPolysList(pcbnew.F_Cu,filled)
    elif fault=='added_fill':
        filled=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        filled.Append(owner.owner._poly([(12000000,12000000),(12500000,12000000),
            (12500000,12500000),(12000000,12500000)]));kept.SetFilledPolysList(pcbnew.F_Cu,filled)
    elif fault=='forged_policy':
        p['fill_policy']='native';p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
    else:
        p['protected_source_regions']=[copy.deepcopy(p['source_zones'][0])]
        p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
    child=force._copy_family(source,tmp_path/'altered');field._save_field_snapshot(b,child)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def test_preserving_mode_clips_stronger_regional_void_and_retains_the_real_track(tmp_path):
    b,source,t,zones=fixture(tmp_path);z=pcbnew.ZONE(b);z.SetNet(t.GetNet());z.SetLayer(pcbnew.F_Cu)
    z.SetAssignedPriority(2);z.SetLocalClearance(200000);z.SetMinThickness(100000)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.SetZoneName('separate-source-region')
    shape=owner.owner._poly([(5000000,5400000),(9000000,5400000),(9000000,6600000),(5000000,6600000)])
    z.Outline().Append(shape);b.Add(z)
    physical=owner.owner._poly([(5000000,5400000),(5200000,5400000),(5200000,6600000),(5000000,6600000)])
    z.SetFilledPolysList(pcbnew.F_Cu,physical);z.SetIsFilled(True)
    field._save_field_snapshot(b,source)
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions')
    assert len(p['protected_source_regions'])==1
    before=owner._snapshot(z,time.monotonic()+10);tid=force._uid(t)
    owner.construct(b,p);assert owner._snapshot(z,time.monotonic()+10)==before
    assert any(force._uid(q)==tid for q in b.GetTracks())
    void=shape.CloneDropTriangulation();void.BooleanSubtract(physical)
    kept=next(q for q in b.Zones() if force._uid(q)==p['keeper_uuid'])
    intrusion=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();intrusion.BooleanIntersection(void)
    assert not intrusion.OutlineCount()


def test_shared_native_anchor_filter_never_adopts_a_free_floating_island(tmp_path):
    import cec_regional_fill as regional
    b,source,t,zones=fixture(tmp_path)
    proposals=owner.owner._poly([(3000000,5800000),(4000000,5800000),(4000000,6200000),(3000000,6200000)])
    proposals.Append(owner.owner._poly([(12000000,12000000),(13000000,12000000),
        (13000000,13000000),(12000000,13000000)]))
    kept=regional.anchored_native_additions(b,proposals,net=t.GetNetname(),layer=pcbnew.F_Cu,
        source_zone_uuids=[force._uid(z) for z in zones],deadline=time.monotonic()+10)
    assert kept.OutlineCount()==1


@pytest.mark.parametrize('policy',[True,None,'preserve-everything'])
def test_fill_policy_is_explicit_and_not_a_truthy_waiver(tmp_path,policy):
    b,source,t,zones=fixture(tmp_path);original=source.read_bytes()
    with pytest.raises(owner.Refused):owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy=policy)
    assert source.read_bytes()==original


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('inset',[0,4])
def test_clipped_native_additions_roundtrip_without_relaxing_the_source_boundary(tmp_path,face,rotate,inset):
    b,source,t,zones=fixture(tmp_path,face,rotate);original=source.read_bytes()
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions',
        clip_native_additions=True,native_addition_inset_nm=inset)
    made=owner.construct(b,p);child=force._copy_family(source,tmp_path/'clipped')
    field._save_field_snapshot(b,child)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert source.read_bytes()==original and not proof['release_authority']


@pytest.mark.parametrize('policy,flag',[('native',True),('source_preserving_regions',1),
    ('source_preserving_regions',None),('source_preserving_regions','yes')])
def test_native_addition_clip_cannot_be_a_truthy_or_unowned_permission(tmp_path,policy,flag):
    b,source,t,zones=fixture(tmp_path);original=source.read_bytes()
    with pytest.raises(owner.Refused):
        owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy=policy,clip_native_additions=flag)
    assert source.read_bytes()==original


def test_addition_clipping_discards_an_outside_producer_piece_not_incumbent_copper(tmp_path):
    import cec_regional_fill as regional
    b,source,t,zones=fixture(tmp_path)
    p=owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions',
        clip_native_additions=True)
    native_source=pcbnew.LoadBoard(str(source));made=owner.construct(b,p);kept=next(iter(b.Zones()))
    # Untrusted producer test double. Independent whole-board replay remains
    # required; this unit test grants no admission to the fabricated piece.
    outside=owner.owner._poly([(14000000,14000000),(14500000,14000000),
        (14500000,14500000),(14000000,14500000)])
    compiled=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();compiled.Append(outside)
    kept.SetFilledPolysList(pcbnew.F_Cu,compiled)
    owner._preserve_source_regions(native_source,kept,p,time.monotonic()+10)
    actual=kept.GetFilledPolysList(pcbnew.F_Cu)
    intersection=actual.CloneDropTriangulation();intersection.BooleanIntersection(outside)
    assert not intersection.OutlineCount()
    for old in p['source_zones']:
        assert regional.exact_source_contour_present(actual,
            geometry.reconstruct(old['fill'],time.monotonic()+10),time.monotonic()+10)


@pytest.mark.parametrize('inset',[-1,True,None,11])
def test_new_material_inset_is_bounded_and_not_a_truthy_source_copper_waiver(tmp_path,inset):
    b,source,t,zones=fixture(tmp_path)
    with pytest.raises(owner.Refused):
        owner.plan(source,[force._uid(t)],allow_locked_source=True,fill_policy='source_preserving_regions',
            clip_native_additions=True,native_addition_inset_nm=inset)


def test_new_material_inset_without_owned_clip_policy_is_refused(tmp_path):
    b,source,t,zones=fixture(tmp_path)
    with pytest.raises(owner.Refused):owner.plan(source,[force._uid(t)],allow_locked_source=True,native_addition_inset_nm=4)
