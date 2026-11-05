"""Source-typed whole jogs, not ordinary overrides or corner-scope inflation."""
import copy
import json
import os
import time
from pathlib import Path
import pcbnew
import pytest
import cec_sensitive_scalar_path_reflow as op
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_sensitive_scalar_corner_stage import fixture as source_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,old,owner,net=source_fixture(tmp_path,angle=angle,mirror=mirror,layer=layer)
    def at(x,y):
        x,y=round((x-20)*1e6),round((y-20)*1e6)
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return ((20000000+x)/1e6,(20000000+y)/1e6)
    discard_items(b,old)
    b.FindFootprintByReference('X2').SetPosition(pcbnew.VECTOR2I_MM(*at(20,20)))
    points=[at(*p) for p in ((15,15),(16,15),(16.5,15.5),(17.5,15.5),(18,16),(18,18),(20,20))]
    cut=[track(b,net,a,z,layer=layer,width=.2) for a,z in zip(points,points[1:])]
    for t in cut:t.SetLocked(True)
    field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    ids=sorted(force._uid(t) for t in cut)
    ends=sorted([list(pcbnew.VECTOR2I_MM(*points[i])) for i in (0,-1)])
    return b,source,cut,ids,ends,net,at


def saved(tmp_path,**kwargs):
    b,source,cut,ids,points,net,at=fixture(tmp_path,**kwargs)
    proposal=op.plan(source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    board=op.construct(proposal);op.additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
    return source,child,ids,points,proposal


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_multi_bend_source_path_reflows_in_all_rigid_frames_and_faces(tmp_path,angle,mirror,layer):
    source,child,ids,points,proposal=saved(tmp_path,angle=angle,mirror=mirror,layer=layer)
    raw=(source.read_bytes(),child.read_bytes())
    r=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    assert r['ok'] and r['complete'],r
    assert r['native_strokes_before_after']==[6,1] and r['shortened_centerline_mm']>1.
    assert r['every_source_native_contact_and_component_preserved'] and r['every_source_pad_pair_path_proved_nonworse']
    assert r['native_ground_material_preservation']['every_preexisting_ground_return_path_material_preserved']
    assert not r['ordinary_reclassification'] and not r['GPIO_mode_or_load_assumed']
    assert r['full_current_fields_absolute_cuts_uncapped_native_DRC_and_release_still_required']
    assert not r['current_qualified'] and not r['fab_ready'] and not r['release_authority']
    assert raw==(source.read_bytes(),child.read_bytes())
    actual=pcbnew.LoadBoard(str(child));t=next(t for t in actual.GetTracks() if force._uid(t) in r['added_native_uuids'])
    assert t.GetLayer()==layer and t.GetWidth()==200000 and t.IsLocked()


@pytest.mark.parametrize('fault',['unknown_package','USB_pin','power_type','not_sensitive','current_budget',
    'pair','analogue_pair','group','mask','locked','mixed_lock','mixed_face','mixed_width',
    'foreign_copper','outside_edge','side_contact'])
def test_literal_source_ownership_process_contacts_and_clearance_are_not_optional(tmp_path,monkeypatch,fault):
    b,source,cut,ids,points,net,at=fixture(tmp_path);unlock=True
    owner=b.FindFootprintByReference('X1')
    if fault=='unknown_package':owner.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8'))
    elif fault=='USB_pin':next(iter(owner.Pads())).SetNumber('18')
    elif fault=='power_type':next(iter(owner.Pads())).SetPinType('power_in')
    elif fault=='not_sensitive':monkeypatch.setattr(op.sensitive,'eligible_nets',lambda *a,**k:{})
    elif fault=='current_budget':monkeypatch.setattr(op.sensitive.synth,'spec_net_current_contract',lambda *a,**k:dict(amps=.001))
    elif fault=='pair':monkeypatch.setattr(op.sensitive.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/mate')])
    elif fault=='analogue_pair':monkeypatch.setattr(op.sensitive.semantics,'analog_input_pairs',lambda *a,**k:[dict(p=net,n='/mate')])
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(cut[0])
    elif fault=='mask':cut[0].SetHasSolderMask(True)
    elif fault=='locked':unlock=False
    elif fault=='mixed_lock':cut[0].SetLocked(False)
    elif fault=='mixed_face':cut[0].SetLayer(pcbnew.B_Cu)
    elif fault=='mixed_width':cut[0].SetWidth(210000)
    elif fault=='foreign_copper':
        b.Add(pcbnew.NETINFO_ITEM(b,'FOREIGN'));track(b,'FOREIGN',at(17,16.5),at(17,17.5),width=.2)
    elif fault=='outside_edge':points=[[-1000000,-1000000],points[-1]]
    else:track(b,net,at(18,16),at(18.5,16),width=.2)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',retired_track_uuids=ids,
        points_nm=points,allow_locked_source=unlock)


@pytest.mark.parametrize('fault',['changed_port','raw_diagonal','hard90','repeated','same_path','extra_points','float','bool','nonfinite','self_intersection'])
def test_new_path_is_a_bounded_simple_strictly_shorter_0_45_port_preserving_path(tmp_path,fault):
    b,source,cut,ids,points,net,at=fixture(tmp_path)
    if fault=='changed_port':points[0][0]+=1
    elif fault=='raw_diagonal':points=[[15000000,15000000],[17000001,17000000],[20000000,20000000]]
    elif fault=='hard90':points=[[15000000,15000000],[15000000,20000000],[20000000,20000000]]
    elif fault=='repeated':points=[points[0],points[0],points[-1]]
    elif fault=='same_path':points=[list(t.GetStart()) for t in cut]+[list(cut[-1].GetEnd())]
    elif fault=='extra_points':points=[[i,i] for i in range(17)]
    elif fault=='float':points[0][0]=15000000.
    elif fault=='bool':points[0][0]=True
    elif fault=='nonfinite':points[0][0]=float('nan')
    else:
        points=[[0,0],[1000000,0],[2000000,1000000],[2000000,2000000],[1000000,3000000],
            [0,3000000],[-1000000,2000000],[-1000000,1000000],[1000000,-1000000]]
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',retired_track_uuids=ids,
        points_nm=points,allow_locked_source=True)


@pytest.mark.parametrize('fault',['width','lock','face','pose','extra_track','extra_via','source_track','sidecar','wrong_cut','unknown_path'])
def test_saved_child_is_reconstructed_from_source_not_imported_as_an_overlay(tmp_path,monkeypatch,fault):
    source,child,ids,points,proposal=saved(tmp_path)
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='wrong_cut':ids=ids[:-1]
    elif fault=='unknown_path':monkeypatch.setattr(op.sensitive_path.cells,'_shortest_track_path_mm',lambda *a,**k:None)
    else:
        b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()))
        if fault=='width':t.SetWidth(199999)
        elif fault=='lock':t.SetLocked(False)
        elif fault=='face':t.SetLayer(pcbnew.B_Cu)
        elif fault=='pose':b.FindFootprintByReference('X1').Move(pcbnew.VECTOR2I(1,0))
        elif fault=='extra_track':track(b,t.GetNetname(),(5,5),(6,5),width=.2)
        elif fault=='extra_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(t.GetStart());v.SetWidth(600000);v.SetDrill(300000)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        else:t.Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(b,child)
    q=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    assert not q['ok'] and not q['complete'] and q['errors'],q


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(allow_locked_source=1),dict(timeout_s=0),
    dict(timeout_s=True),dict(timeout_s=11),dict(retired_track_uuids=[]),dict(retired_track_uuids=['a']*17)])
def test_empty_or_unbounded_context_is_not_authority(tmp_path,options):
    params=dict(board_hint='synthetic',retired_track_uuids=['x','y'],points_nm=[[0,0],[1000000,1000000]])
    params.update(options)
    with pytest.raises((ValueError,OSError)):op.plan(tmp_path/'missing.kicad_pcb',**params)


def test_discovery_is_read_only_and_proposes_the_entire_jog(tmp_path):
    b,source,cut,ids,points,net,at=fixture(tmp_path);raw=source.read_bytes()
    q=op.discover(source,board_hint='synthetic',allow_locked_source=True,stop_after_first=True)
    assert q['plans'] and q['bounded_portfolio_complete'],q
    assert set(q['plans'][0]['retired_track_uuids'])==set(ids)
    assert q['plans'][0]['replacement_points_nm']==points
    assert source.read_bytes()==raw and not q['source_geometry_mutated']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_discovery_collision_prefilter_uses_actual_native_foreign_geometry(tmp_path,layer):
    b,source,cut,ids,points,net,at=fixture(tmp_path,layer=layer)
    b.Add(pcbnew.NETINFO_ITEM(b,'FOREIGN'))
    track(b,'FOREIGN',at(16,17),at(18,17),layer=layer,width=.2)
    with pytest.raises(ValueError,match='foreign_copper'):
        op._clear_path(b,cut,points,time.monotonic()+10.,{})


def test_all_blocked_templates_are_rejected_before_funding_source_replays(tmp_path,monkeypatch):
    b,source,*_=fixture(tmp_path);raw=source.read_bytes();caches=[];boards=[]
    def blocked(board,cut,points,deadline,cache):
        caches.append(id(cache));boards.append(id(board))
        raise ValueError('synthetic_native_collision')
    monkeypatch.setattr(op,'_clear_path',blocked)
    monkeypatch.setattr(op,'plan',lambda *a,**k:pytest.fail('blocked template spent a source replay'))
    q=op.discover(source,board_hint='synthetic',allow_locked_source=True,maximum_candidates=1)
    assert not q['plans'] and not q['trials'] and q['cheap_geometry_refusals']['synthetic_native_collision']>1
    assert len(set(caches))==len(set(boards))==1 and source.read_bytes()==raw


def test_discovery_and_independent_plan_never_share_native_obstacle_snapshots(tmp_path,monkeypatch):
    b,source,*_=fixture(tmp_path);actual=op._clear_path;calls=[]
    def observed(board,cut,points,deadline,cache):
        calls.append((board,cache))
        return actual(board,cut,points,deadline,cache)
    monkeypatch.setattr(op,'_clear_path',observed)
    q=op.discover(source,board_hint='synthetic',allow_locked_source=True,maximum_candidates=1)
    assert len(q['plans'])==1 and len(calls)>=2
    assert calls[0][0] is not calls[-1][0] and calls[0][1] is not calls[-1][1]
    proof=q['plans'][0]
    op.plan(source,board_hint='synthetic',retired_track_uuids=proof['retired_track_uuids'],
        points_nm=proof['replacement_points_nm'],allow_locked_source=True)
    assert calls[-2][0] is not calls[-1][0] and calls[-2][1] is not calls[-1][1]


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_real_native_reports_keep_zero_opens_and_gain_no_faults(tmp_path,layer):
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native DRC build not configured')
    source,child,ids,points,proposal=saved(tmp_path,layer=layer);reports=[]
    for label,path in (('before',source),('after',child)):
        output=tmp_path/'reports'/(label+'.json');q=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert q['ok'] and q['complete'] and not q['native_inventory']['potentially_truncated'],q
        reports.append(json.loads(output.read_text()))
    assert not reports[-1]['unconnected_items']
    before={admission._canonical_identity(v) for v in reports[0]['violations']}
    assert not {admission._canonical_identity(v) for v in reports[1]['violations']}-before


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(expected_source_sha256='bad'),
    dict(reporting_build=None),dict(allow_locked_source=1),dict(maximum_candidates=True),
    dict(maximum_candidates=0),dict(maximum_candidates=9)])
def test_stage_rejects_invalid_policy_before_creating_a_family(tmp_path,options):
    b,source,*_=fixture(tmp_path)
    params=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=tmp_path/'unused',allow_locked_source=True,maximum_candidates=1)
    params.update(options)
    with pytest.raises(ValueError):op.run(source,tmp_path/'out',**params)
    assert not (tmp_path/'out').exists()


def test_complete_generic_stage_uses_native_current_field_and_absolute_cut_receiving(tmp_path):
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native DRC build not configured')
    b,source,*_=fixture(tmp_path);raw=source.read_bytes()
    q=op.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(build),allow_locked_source=True,maximum_candidates=1)
    assert q['ok'] and q['complete'] and q['changed'],q
    row=q['attempts'][-1]
    assert row['accepted'] and not row['errors'] and not row['new_native_fault_ids'] and row['opens']==0
    assert row['whole_parent_current']['ok'] and row['whole_parent_current']['complete']
    assert not row['new_field_blockers'] and row['whole_parent_clipped_preservation']['same_evidence']
    assert source.read_bytes()==raw and q['source_family_and_code_unchanged']
    assert not q['fab_ready'] and not q['release_authority']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('change',['same','grow','one_nm_loss','unknown','hole','same_hole'])
def test_native_ground_containment_has_no_tiny_area_or_unknown_fill_waiver(tmp_path,face,change):
    from test_lastmile import _board
    first=_board([],edge=(0,0,20,20));first.SetCopperLayerCount(6)
    last=_board([],edge=(0,0,20,20));last.SetCopperLayerCount(6)
    for board in (first,last):board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    uid=pcbnew.KIID()
    def zone(board,edge,hole=False):
        z=pcbnew.ZONE(board);z.m_Uuid.Clone(uid);z.SetNet(board.FindNet('GND'));z.SetLayer(face)
        z.Outline().NewOutline()
        for x,y in ((1000000,1000000),(9000000,1000000),(9000000,9000000),(1000000,9000000)):z.Outline().Append(x,y)
        fill=pcbnew.SHAPE_POLY_SET();fill.NewOutline()
        for x,y in ((1000000,1000000),(edge,1000000),(edge,9000000),(1000000,9000000)):fill.Append(x,y)
        if hole:
            aperture=pcbnew.SHAPE_POLY_SET();aperture.NewOutline()
            for x,y in ((4000000,4000000),(4100000,4000000),(4100000,4100000),(4000000,4100000)):aperture.Append(x,y)
            fill.BooleanSubtract(aperture)
        z.SetFilledPolysList(face,fill);z.SetIsFilled(True);board.Add(z);return z
    zone(first,9000000,hole=change=='same_hole')
    changed=zone(last,9000001 if change=='grow' else 8999999 if change=='one_nm_loss' else 9000000,
        hole=change in ('hole','same_hole'))
    if change=='unknown':changed.SetIsFilled(False)
    raw=[field._field_snapshot_inventory(b) for b in (first,last)]
    if change in ('same','grow','same_hole'):
        q=op._preserved_ground_material(first,last,time.monotonic()+10.)
        assert q['ok'] and q['complete'] and not q['area_or_distance_waiver_used']
        assert q['layers']==[dict(zone_uuid=uid.AsString(),layer_id=face,native_source_minus_candidate_empty=True)]
    else:
        with pytest.raises(ValueError):op._preserved_ground_material(first,last,time.monotonic()+10.)
    assert raw==[field._field_snapshot_inventory(b) for b in (first,last)]


def boundary_fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,old,ids,points,net,at=fixture(tmp_path,angle,mirror,layer)
    discard_items(b,old)
    b.FindFootprintByReference('X2').SetPosition(pcbnew.VECTOR2I_MM(*at(20,10)))
    line=[at(*p) for p in ((15,15),(16,16),(17,16),(17.5,15.5),(18,15.5),(18.5,15),(18.5,12),(20,10.5),(20,10))]
    cut=[track(b,net,a,z,layer=layer,width=.2) for a,z in zip(line,line[1:])]
    retained=track(b,net,at(14,14),at(15,15),layer=layer,width=.2)
    for t in cut:t.SetLocked(True)
    field._save_field_snapshot(b,source);field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    direct=sorted([list(pcbnew.VECTOR2I_MM(*line[i])) for i in (0,-1)])
    return b,source,sorted(force._uid(t) for t in cut),direct,force._uid(retained)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_fixed_port_reflow_must_keep_retained_boundary_turns_at_most_45(tmp_path,angle,mirror,layer):
    b,source,ids,direct,retained=boundary_fixture(tmp_path,angle,mirror,layer)
    with pytest.raises(ValueError,match='new_boundary_hard_turn'):
        op.plan(source,board_hint='synthetic',retired_track_uuids=ids,points_nm=direct,allow_locked_source=True)
    q=op.discover(source,board_hint='synthetic',allow_locked_source=True,stop_after_first=True)
    assert q['plans'],q
    proposal=q['plans'][0];assert set(proposal['retired_track_uuids'])==set(ids)
    assert proposal['replacement_points_nm']!=direct
    assert any(retained in r['retained_endpoint_peers'] and r['two_edge_boundary_tangent_required']
        for r in proposal['native_boundary_tangents'])
    board=op.construct(proposal);op.additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
    r=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,
        points_nm=proposal['replacement_points_nm'],allow_locked_source=True)
    assert r['ok'] and r['complete'],r
    assert r['selected_net_right_angle_findings_before_after'][1]<=r['selected_net_right_angle_findings_before_after'][0]
    assert r['shortened_centerline_mm']>.01 and r['native_strokes_before_after'][1]<len(ids)


def test_a_saved_electrically_connected_shortcut_cannot_smuggle_a_new_boundary_90(tmp_path):
    b,source,ids,points,retained=boundary_fixture(tmp_path)
    original=[t for t in b.GetTracks() if force._uid(t) in ids];example=original[0].Duplicate()
    discard_items(b,original);example.m_Uuid.Clone(pcbnew.KIID())
    example.SetStart(pcbnew.VECTOR2I(*points[0]));example.SetEnd(pcbnew.VECTOR2I(*points[-1]));b.Add(example)
    child=force._copy_family(source,tmp_path/'unsafe');op.additive._ground_refill(b);field._save_field_snapshot(b,child)
    q=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
    assert not q['ok'] and any('new_boundary_hard_turn' in e for e in q['errors'])
