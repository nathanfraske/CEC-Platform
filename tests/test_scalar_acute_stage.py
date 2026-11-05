"""Bounded saved-source acute finishing, with real native geometry guards."""
import os
from pathlib import Path

import pcbnew
import pytest

import cec_scalar_corner_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
from test_lastmile import _board
from test_field_proposals import track


POLICY = 'acute_shortcut'


def fixture(angle=0, mirror=False, layer=pcbnew.F_Cu, net='/renamed/CONTROL'):
    def at(x, y):
        x, y = round((x-20)*1e6), round((y-20)*1e6)
        if mirror:
            x = -x
        for _ in range(angle//90):
            x, y = -y, x
        return ((20000000+x)/1e6, (20000000+y)/1e6)
    ends = [at(15,15), at(20,19.5)]
    b = _board([(*p, net) for p in ends], edge=(0,0,40,40))
    b.SetCopperLayerCount(6)
    layers = pcbnew.LSET(); layers.AddLayer(layer)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            p.SetLayerSet(layers); p.SetPadName('1')
            p.SetSize(pcbnew.VECTOR2I(100000,100000))
    tracks = [track(b,net,at(*a),at(*z),layer=layer,width=.2)
              for a,z in (((15,15),(20,20)),((20,20),(20,19.5)))]
    return b,net,tracks,at


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('locked',[False,True])
def test_native_acute_rotation_mirror_layer_and_explicit_locks(angle,mirror,layer,locked):
    b,net,tracks,at=fixture(angle,mirror,layer)
    for t in tracks:t.SetLocked(locked)
    ids={force._uid(t) for t in tracks};ends={at(15,15),at(20,19.5)}
    before=sum(t.GetLength() for t in tracks)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    assert len(requests)==1 and not stage.inventory(b,{net})['selected']
    result=stage.construct(b,requests,{net},geometry_policy=POLICY,allow_locked_source=locked)
    assert result['chamfered']==1 and set(result['retired_track_uuids'])==ids
    assert not result['mutation_or_release_admission']
    assert not stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    current=list(b.GetTracks());assert len(current)==2
    assert sum(t.GetLength() for t in current)<before
    assert all(t.GetWidth()==200000 and t.GetLayer()==layer and t.IsLocked()==locked for t in current)
    assert not ids & {force._uid(t) for t in current}
    assert ends <= {tuple(v/1e6 for v in p) for t in current for p in (t.GetStart(),t.GetEnd())}
    assert quality.analyze_board(b)['issue_count']==0
    assert all(quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0) for t in current)
    assert result['details'][0]['native_contact_preservation']['ok']


@pytest.mark.parametrize('kind',['pad','via','track','zone','unknown_zone'])
def test_same_net_old_side_contacts_are_not_cut_by_shortening(kind):
    b,net,tracks,at=fixture()
    point=pcbnew.VECTOR2I_MM(*at(20,20))
    if kind=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference('SIDE')
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(tracks[0].GetNet())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        # Touch the old rounded tip without covering its exact vertex. An
        # actual in-pad vertex is intentionally not cosmetic inventory.
        p.SetPosition(pcbnew.VECTOR2I_MM(*at(20.06,20.06)))
        p.SetSize(pcbnew.VECTOR2I(20000,20000))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls)
    elif kind=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(tracks[0].GetNet());v.SetPosition(point)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(100000);v.SetDrill(50000);b.Add(v)
    elif kind=='track':
        track(b,net,at(20,20),at(20.1,20.1),width=.02)
    else:
        z=pcbnew.ZONE(b);z.SetNet(tracks[0].GetNet());z.SetLayer(pcbnew.F_Cu)
        shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline()
        for x,y in ((19.98,19.98),(20.02,19.98),(20.02,20.02),(19.98,20.02)):
            p=pcbnew.VECTOR2I_MM(*at(x,y));shape.Append(p.x,p.y)
        z.Outline().Append(shape);b.Add(z)
        if kind=='zone':z.SetFilledPolysList(pcbnew.F_Cu,shape);z.SetIsFilled(True)
    before=field._field_snapshot_inventory(b)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    if not requests:
        # A true third endpoint is not a two-edge cosmetic request at all.
        assert kind=='track'
        return
    result=stage.construct(b,requests,{net},geometry_policy=POLICY)
    assert result['chamfered']==0 and not result['retired_track_uuids']
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('kind',['foreign_copper','foreign_rule_area','edge'])
def test_actual_full_width_foreign_and_edge_guards_block_replacement(kind):
    b,net,tracks,at=fixture()
    if kind=='edge':
        # Both alternate proposals approach this actual internal aperture.
        for a,z in (((19.2,19.2),(19.8,19.2)),((19.8,19.2),(19.8,19.8)),
                    ((19.8,19.8),(19.2,19.8)),((19.2,19.8),(19.2,19.2))):
            s=pcbnew.PCB_SHAPE(b);s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(pcbnew.VECTOR2I_MM(*a));s.SetEnd(pcbnew.VECTOR2I_MM(*z))
            s.SetLayer(pcbnew.Edge_Cuts);b.Add(s)
    elif kind=='foreign_copper':
        track(b,'/OTHER',(19,19.5),(21,19.5),width=.2)
    else:
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True);shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline()
        for x,y in ((19,19),(21,19),(21,21),(19,21)):shape.Append(round(x*1e6),round(y*1e6))
        z.Outline().Append(shape);b.Add(z)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    before=field._field_snapshot_inventory(b)
    result=stage.construct(b,requests,{net},geometry_policy=POLICY)
    assert result['chamfered']==0 and before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['locked','group','width','non45','aliased','ineligible','stale','duplicate','policy'])
def test_no_authority_from_stale_or_unsupported_acute_pair(fault):
    b,net,tracks,at=fixture();nets={net}
    requests=stage.inventory(b,nets,geometry_policy=POLICY)['selected']
    kwargs=dict(geometry_policy=POLICY)
    if fault=='locked':tracks[0].SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='width':tracks[0].SetWidth(300000)
    elif fault=='non45':tracks[0].SetStart(pcbnew.VECTOR2I_MM(15,15.01))
    elif fault=='aliased':tracks[0].SetEnd(pcbnew.VECTOR2I_MM(20,20.000001))
    elif fault=='ineligible':nets=set()
    elif fault=='stale':requests[0]['at_nm'][0]+=1
    elif fault=='duplicate':requests=requests*2
    else:kwargs['geometry_policy']='not-a-policy'
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):stage.construct(b,requests,nets,**kwargs)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('angle',[0,90])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_native_stage_with_ordinary_current_field_and_absolute_cut_receivers(tmp_path,angle,layer):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    b,net,tracks,at=fixture(angle,False,layer)
    for t in tracks:t.SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source);old=source.read_bytes()
    result=stage.run(source,tmp_path/'stage',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=Path(native),
        allow_locked_source=True,geometry_policy=POLICY)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['craft_before']['issue_count']==1 and result['craft_after']['issue_count']==0
    assert result['independent_receiving']['ok'] and result['source_family_and_code_unchanged']
    assert not result['fab_ready'] and not result['routing_admitted'] and not result['release_authority']
    assert old==source.read_bytes()
    assert not source.with_suffix('.kicad_pro').exists()


@pytest.mark.parametrize('net',['+5V','GND','/USB_D_P','/SENSEC1_HI','/CLOCK'])
def test_actual_specialized_net_classification_never_inherits_ordinary_authority(tmp_path,net):
    b,net,tracks,at=fixture(net=net)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    actual=ordinary.eligible_nets(b,source,'synthetic')
    assert net not in actual
    assert not stage.inventory(b,actual,geometry_policy=POLICY)['selected']


def test_reference_plane_and_overlong_source_are_not_finishing_scopes():
    b,net,tracks,at=fixture(layer=pcbnew.In1_Cu)
    assert not stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    b,net,tracks,at=fixture()
    tracks[0].SetStart(pcbnew.VECTOR2I_MM(-20,-20))
    assert not stage.inventory(b,{net},geometry_policy=POLICY)['selected']


def test_expired_native_inventory_cannot_report_complete_even_without_requests(monkeypatch):
    b,net,tracks,at=fixture();clock=[0.]
    def slow_inventory(board):
        clock[0]=11.
        return dict(issues=[])
    monkeypatch.setattr(stage.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(stage.quality,'analyze_board',slow_inventory)
    with pytest.raises(ValueError,match='complete_native_ordinary_corner_inventory_required'):
        stage.inventory(b,{net},geometry_policy=POLICY)


@pytest.mark.parametrize('count',[0,4])
def test_contact_guard_rejects_unbounded_or_empty_new_shapes(count):
    b,net,tracks,at=fixture()
    shape=tracks[0].GetEffectiveShape(pcbnew.F_Cu)
    with pytest.raises(ValueError,match='bounded_native_corner_contact_scope_required'):
        stage.contacts.preserve_contacts(b,tracks,[shape]*count,layer_id=pcbnew.F_Cu,
            net_code=tracks[0].GetNetCode(),deadline_monotonic=stage.time.monotonic()+1.)


@pytest.mark.parametrize('kind',['retained_tail','retained_prefix'])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_shortcut_reuses_retained_full_width_collinear_neighbor_without_new_backtrack(kind,angle,layer):
    b,net,tracks,at=fixture(angle,False,layer)
    ends=((20,19.5),(18,19.5)) if kind=='retained_tail' else ((15,15),(19.5,19.5))
    neighbor=track(b,net,at(*ends[0]),at(*ends[1]),layer=layer,width=.2)
    uid=force._uid(neighbor);before=field._field_snapshot_inventory(b)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    assert len(requests)==1
    result=stage.construct(b,requests,{net},geometry_policy=POLICY)
    assert result['chamfered']==1
    proof=result['details'][0]['retained_native_copper_reuse']
    assert proof['complete'] and proof['reused_native_uuids']==[uid]
    assert proof['emitted_segments']==1
    assert len(list(b.GetTracks()))==2 and quality.analyze_board(b)['issue_count']==0
    assert field._field_snapshot_inventory(b)['track',uid]==before['track',uid]


@pytest.mark.parametrize('kind',['narrow','offset'])
def test_retained_neighbor_does_not_get_reuse_credit_from_proximity_or_skinny_copper(kind):
    b,net,tracks,at=fixture()
    y=19.500001 if kind=='offset' else 19.5
    track(b,net,(20,y),(18,y),width=.1 if kind=='narrow' else .2)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    result=stage.construct(b,requests,{net},geometry_policy=POLICY)
    assert result['chamfered']==1
    proof=result['details'][0]['retained_native_copper_reuse']
    assert proof['changed_segments']==0 and not proof['reused_native_uuids']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_fully_retained_shortcut_is_exact_cut_only_not_new_redundant_tracks(angle,layer):
    b,net,tracks,at=fixture(angle,False,layer)
    ids={force._uid(t) for t in tracks};retained=[]
    for a,z in (((15,15),(19.5,19.5)),((19.5,19.5),(20,19.5))):
        retained.append(track(b,net,at(*a),at(*z),layer=layer,width=.2))
    before=field._field_snapshot_inventory(b)
    requests=stage.inventory(b,{net},geometry_policy=POLICY)['selected']
    assert len(requests)==1
    result=stage.construct(b,requests,{net},geometry_policy=POLICY)
    assert result['chamfered']==1 and set(result['retired_track_uuids'])==ids
    assert not result['incoming_source_owners']
    assert result['details'][0]['retained_native_copper_reuse']['emitted_segments']==0
    after=field._field_snapshot_inventory(b)
    assert before.keys()-after.keys()=={('track',u) for u in ids}
    assert all(before[k]==v for k,v in after.items())
    assert quality.analyze_board(b)['issue_count']==0


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_cut_only_stage_still_proves_native_partitions_boundaries_and_current(tmp_path,layer):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    b,net,tracks,at=fixture(layer=layer)
    for t in tracks:t.SetLocked(True)
    for a,z in (((15,15),(19.5,19.5)),((19.5,19.5),(20,19.5))):
        track(b,net,at(*a),at(*z),layer=layer,width=.2)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source);old=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',reporting_build=Path(native),
        expected_source_sha256=force._hash(source),geometry_policy=POLICY,allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    proof=r['independent_receiving']
    assert proof['ok'] and proof['actual_saved_redundant_cut_only']
    assert proof['whole_original_ordinary_delta']['all_prior_surviving_copper_junctions_preserved']
    assert r['craft_after']['issue_count']==0 and source.read_bytes()==old
