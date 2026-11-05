"""Actual native fixed-port detours; synthetic catalogs never rate real boards."""
from pathlib import Path
import os
from unittest.mock import patch
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_path_finish as owner
from test_full_current_terminal_trim import authority
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,width=.2):
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (20+x,20+y)
    net='/different/FULL_LOAD'
    b=_board([(*pose(p),net) for p in [(14,20),(24,26)]],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for f in b.GetFootprints():
        for p in f.Pads():ls=pcbnew.LSET();ls.AddLayer(face);p.SetLayerSet(ls)
    old=[pose(p) for p in [(16,20),(18,20),(20,18),(22,18),(24,20),(24,24)]];ids=[]
    for a,z in zip(old,old[1:]):
        t=track(b,net,a,z,layer=face,width=width);t.SetLocked(True);ids.append(force._uid(t))
    for a,z in [((14,20),(16,20)),((24,24),(24,26))]:
        track(b,net,pose(a),pose(z),layer=face,width=width).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    # The source chain is independently ordered lexically by its endpoints.
    b=pcbnew.LoadBoard(str(source));cut=[t for t in b.GetTracks() if force._uid(t) in ids]
    ordered=[list(p) for p in owner.chain._chain(cut)]
    points=[[round(x*1e6),round(y*1e6)] for x,y in [pose(p) for p in [(16,20),(20,20),(24,24)]]]
    if points[0]!=ordered[0]:points.reverse()
    return source,net,ids,points


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('width',[.2,1.])
def test_fixed_port_native_current_reflow_removes_the_whole_detour(tmp_path,quarter,mirror,face,width):
    source,net,ids,points=fixture(tmp_path,quarter,mirror,face,width);initial=source.read_bytes()
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source));p=owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
        assert p['shape']['actual_visible_native_material_removed']['ok']
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['saved_trace_length_mm']==pytest.approx(4.) and r['native_strokes_before_after']==[5,2]
    assert r['source_width_face_current_ports_and_native_contacts_preserved'] and source.read_bytes()==initial
    assert r['new_holes']==r['new_vias']==r['pads_moved']==0 and not r['power_pours_changed'] and not r['release_authority']


@pytest.mark.parametrize('fault',['missing','incomplete','floor','locked','mask','group','pad','via','side_tap','pair','wrong_ports','non45','hard90','not_shorter'])
def test_no_geometry_hint_can_reclassify_a_role_or_lose_owned_contacts(tmp_path,fault):
    source,net,ids,points=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));cut=[t for t in b.GetTracks() if force._uid(t) in ids]
    if fault=='mask':cut[0].SetHasSolderMask(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(cut[0])
    elif fault in ('pad','via'):
        if fault=='pad':
            f=pcbnew.FOOTPRINT(b);f.SetReference('SIDE');p=pcbnew.PAD(f);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(pcbnew.VECTOR2I_MM(20,18));ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);p.SetNet(b.FindNet(net));f.Add(p);b.Add(f)
        else:
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(20,18));v.SetWidth(600000);v.SetDrill(300000)
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='side_tap':track(b,net,(20,18),(20,16))
    elif fault=='wrong_ports':points[0][0]+=100000
    elif fault=='non45':points[1][1]+=1
    elif fault=='hard90':points=[[16000000,20000000],[24000000,20000000],[24000000,24000000]]
    elif fault=='not_shorter':points=[list(p) for p in owner.chain._chain(cut)]
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with authority(net,incomplete=fault=='incomplete',missing=fault=='missing',floor=.3 if fault=='floor' else .1), \
         patch.object(owner.precision,'derive_coupled_pairs',return_value=[dict(p=net,n='/N')] if fault=='pair' else []):
        with pytest.raises(ValueError):owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=fault!='locked')


@pytest.mark.parametrize('fault',['width','face','pad','sidecar','extra','via','forged_geometry','forged_contact'])
def test_independent_saved_receiver_refuses_forged_or_unowned_delta(tmp_path,fault):
    source,net,ids,points=fixture(tmp_path)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));p=owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child')
        t=next(t for t in b.GetTracks() if force._uid(t) in made['added_native_uuids'])
        if fault=='width':t.SetWidth(199999)
        elif fault=='face':t.SetLayer(pcbnew.B_Cu)
        elif fault=='pad':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
        elif fault=='extra':track(b,net,(30,30),(31,30))
        elif fault=='via':
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(20,20));v.SetWidth(600000);v.SetDrill(300000)
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='forged_geometry':p['shape']['points_nm'][1][0]+=1
        else:p['shape']['native_port_contacts']=[]
        field._save_field_snapshot(b,child);r=owner.receive(source,child,p,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('quarter',[0,2])
def test_source_discovery_and_uncapped_stage_find_and_receive_a_whole_path(tmp_path,face,quarter):
    import cec_full_current_path_stage as stage
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,net,ids,points=fixture(tmp_path,quarter=quarter,face=face);old=source.read_bytes()
    with authority(net,face):
        r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=Path(native),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['saved_trace_length_mm']>0 and r['native_strokes_before_after'][1]<r['native_strokes_before_after'][0]
    assert r['source_family_and_code_unchanged'] and not r['attempts'][0]['new_native_fault_ids']
    assert all(p['ok'] and p['complete'] and not p['native_inventory']['potentially_truncated'] for p in r['native_producers'].values())
    assert source.read_bytes()==old


def test_bounded_portfolio_does_not_starve_other_nets_faces_or_series_paths():
    menu=[]
    for i in range(100):menu.append((1000-i,('busy-'+str(i),),[],('/BUS',0,200000,('long-series',))))
    for net,face,family in [('/OTHER',0,'separate'),('/BUS',2,'back'),('/BUS',0,'short-series')]:
        menu.append((1.,(net+family,),[],(net,face,200000,(family,))))
    ordered=owner._fair_menu(menu)
    assert len(ordered)==103 and len({q[1] for q in ordered})==103
    assert {q[3] for q in ordered[:4]}=={q[3] for q in menu}
    assert ordered==owner._fair_menu(list(reversed(menu)))


@pytest.mark.parametrize('value',[True,0,5,float('nan'),'4'])
def test_campaign_bounds_cannot_create_unbounded_or_untyped_work(tmp_path,value):
    import cec_full_current_path_stage as stage
    with pytest.raises(ValueError):stage.run_campaign(tmp_path/'missing',tmp_path/'never',board_hint='synthetic',
        expected_source_sha256='0'*64,reporting_build=tmp_path/'native',max_passes=value)
    assert not (tmp_path/'never').exists()


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_campaign_improves_then_stops_without_repeating_the_same_source(tmp_path,face,monkeypatch,capsys):
    import cec_full_current_path_stage as stage
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,net,ids,points=fixture(tmp_path,face=face)
    with authority(net,face):
        r=stage.run_campaign(source,tmp_path/'campaign',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=Path(native),allow_locked_source=True,max_passes=4)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['stop_reason']=='no_accepted_finite_portfolio_offer' and len(r['phase_receipts'])==1 and len(r['passes'])==2
    assert r['original_parent_receiving_still_required'] and not r['whole_board_cleanliness_or_no_path_proof']
    assert not r['source_selected'] and not r['routing_admitted'] and not r['fab_ready']
    # Check CLI representation of this REAL completed native campaign,
    # without dispatching or mutating the same output directory twice.
    import sys,json
    monkeypatch.setattr(stage,'run_campaign',lambda *a,**k:r)
    monkeypatch.setattr(sys,'argv',['path-stage','--source',str(source),'--out',str(tmp_path/'campaign'),
        '--board-hint','synthetic','--expected-source-sha256',force._hash(source),'--reporting-build',native,'--max-passes','4'])
    capsys.readouterr();assert stage.main()==0
    shown=json.loads(capsys.readouterr().out);assert not shown['errors'] and shown['saved_trace_length_mm']>0
    assert Path(shown['receipt'])==tmp_path/'campaign/campaign.json' and Path(shown['receipt']).is_file()


@pytest.mark.parametrize('kwargs',[dict(allow_locked_source=1),dict(max_trials=True),dict(max_trials=0),
    dict(expected_source_sha256='bad'),dict(board_hint=''),dict(reporting_build=None)])
def test_campaign_context_is_validated_before_any_directory_is_created(tmp_path,kwargs):
    import cec_full_current_path_stage as stage
    args=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native');args.update(kwargs)
    with pytest.raises(ValueError):stage.run_campaign(tmp_path/'missing',tmp_path/'never',**args)
    assert not (tmp_path/'never').exists()
