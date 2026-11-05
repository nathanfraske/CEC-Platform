"""Native synthetic local-splice regressions, never hardware current ratings."""
import copy,json
import pcbnew,pytest
import cec_local_keeper_miter as op
import cec_native_contour_regions as regions
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_corner_finish as discovery
from test_full_current_corner_finish import fixture as current_fixture
from test_field_proposals import track

def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu,remote_hole=False):
    source,net,domains,contract=current_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,width=.6)
    b=pcbnew.LoadBoard(str(source));ids=sorted(force._uid(t) for t in b.GetTracks())
    q=regions.plan(b,ids,required_width_nm=200000,clearance_nm=200000,min_thickness_nm=100000,
        contour_style='chamfer45',contour_grid_nm=1000,envelope_margin_nm=1000,fill_envelope_margin_nm=4,
        allow_locked_track_uuids=ids)
    made=regions.materialize(b,q,allow_locked_track_uuids=ids);regions.fill(b,q,made['zone_uuids'])
    z=next(iter(b.Zones()));z.SetLocked(True)
    if remote_hole:
        assert quarter==0 and not mirror
        h=z.Outline().NewHole(0)
        for x,y in ((12000000,14900000),(13000000,14900000),(13000000,15100000),(12000000,15100000)):
            z.Outline().Append(x,y,0,h)
        from cec_zone_fill import compile_selected
        zones=pcbnew.ZONES();zones.append(z);compile_selected(b,zones,initialize_selected=True)
    field._save_field_snapshot(b,source)
    assert not discovery.discover(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',allow_locked_source=True)['requests']
    return source,ids,net,domains,contract

def saved(tmp_path,monkeypatch,**kwargs):
    source,ids,net,domains,contract=fixture(tmp_path,monkeypatch,**kwargs)
    q=op.plan(source,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=True)
    q=json.loads(json.dumps(q));b,made=op.construct(q)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    return source,child,q,made

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_fully_hidden_current_corner_is_received_with_its_local_keeper_not_skipped(tmp_path,monkeypatch,quarter,mirror,face):
    source,child,q,made=saved(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face)
    before=source.read_bytes();r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['removed_bend_flags']==1 and r['actual_trace_length_removed_mm']>0
    assert r['remote_keeper_material_exact'] and r['actual_visible_native_material_removed']['ok']
    assert r['no_new_barrels'] and not r['current_qualified'] and not r['release_authority']
    assert source.read_bytes()==before

def test_remote_literal_window_is_preserved_not_regenerated_from_track_history(tmp_path,monkeypatch):
    source,child,q,made=saved(tmp_path,monkeypatch,remote_hole=True)
    assert q['source_zone_regions_nm'][0]['holes_nm']==q['desired_zone_regions_nm'][0]['holes_nm']
    assert op.receive(source,child,q,board_hint='synthetic')['ok']

@pytest.mark.parametrize('fault',['source_width','budget','point','zone','bounds','retreat','other_rules'])
def test_saved_proposal_cannot_invent_a_source_or_relax_current_or_work_bounds(tmp_path,monkeypatch,fault):
    source,child,q,made=saved(tmp_path,monkeypatch);bad=copy.deepcopy(q)
    if fault=='source_width':bad['full_current_plan']['width_nm']-=1
    elif fault=='budget':bad['full_current_plan']['contract']['current_authority']['amps']/=2
    elif fault=='point':bad['points_nm'][1][0]+=1
    elif fault=='zone':bad['desired_zone_regions_nm'][0]['outer_nm'][0][0]+=1
    elif fault=='bounds':bad['patch_bounds_nm'][0]-=1000
    elif fault=='retreat':bad['retreat_nm']=2000001
    else:bad['source_zone_configuration']['clearance_nm']-=1
    with pytest.raises(ValueError):op.construct(bad)

@pytest.mark.parametrize('fault',['width','track','pad','via','extra','zone_priority','zone_name','remote_window','sidecar'])
def test_complete_saved_receiver_rejects_untouched_object_and_remote_contour_changes(tmp_path,monkeypatch,fault):
    source,child,q,made=saved(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(child))
    t=next(iter(b.GetTracks()));z=next(iter(b.Zones()))
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='track':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(pcbnew.VECTOR2I_MM(40,40))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='extra':track(b,t.GetNetname(),(35,35),(40,35),width=.6)
    elif fault=='zone_priority':z.SetAssignedPriority(1)
    elif fault=='zone_name':z.SetZoneName('unknown')
    elif fault=='remote_window':z.Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,child)
    if fault=='sidecar':force._write(child.with_suffix('.kicad_pro'),{})
    r=op.receive(source,child,q,board_hint='synthetic');assert not r['ok'] and r['errors']

@pytest.mark.parametrize('fault',['lock','group','mask','unknown_zone','unfilled_zone','underwidth','extra_branch','slab',
    'unknown_budget','coupled_pair','second_keeper','local_window'])
def test_source_permission_or_local_ownership_failure_is_not_a_pour_cleanup_waiver(tmp_path,monkeypatch,fault):
    source,ids,net,domains,contract=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    t=next(iter(b.GetTracks()));z=next(iter(b.Zones()))
    if fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    elif fault=='mask':t.SetHasSolderMask(True)
    elif fault=='unknown_zone':z.SetZoneName('not-owned')
    elif fault=='unfilled_zone':z.SetIsFilled(False)
    elif fault=='underwidth':contract['required_by_layer_mm']['F.Cu']=.600001
    elif fault=='unknown_budget':contract['current_authority']['source']='guess'
    elif fault=='coupled_pair':monkeypatch.setattr(discovery.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/OTHER')])
    elif fault=='second_keeper':
        duplicate=z.Duplicate(False);duplicate.m_Uuid.Clone(pcbnew.KIID());b.Add(duplicate)
    elif fault=='local_window':
        h=z.Outline().NewHole(0)
        for x,y in ((24900000,14900000),(25000000,14900000),(25000000,15000000),(24900000,15000000)):
            z.Outline().Append(x,y,0,h)
    elif fault=='extra_branch':track(b,net,(24,15),(24,14),width=.6)
    elif fault=='slab':
        z.Outline().RemoveAllContours();z.Outline().BooleanAdd(op.box_poly([5000000,5000000,40000000,40000000]))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=fault!='lock')

@pytest.mark.parametrize('retreat',[True,0,49999,2000001])
def test_explicit_work_bounds_are_not_truthy_geometry_permissions(tmp_path,monkeypatch,retreat):
    source,ids,_,_,_=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_explicit'):
        op.plan(source,board_hint='synthetic',retired_track_uuids=ids,retreat_nm=retreat,allow_locked_source=True)

def test_exhausted_source_worker_writes_an_explicit_no_change_receipt(tmp_path,monkeypatch):
    import runpy,sys
    from pathlib import Path
    from cec_native_items import discard_items
    source,ids,_,_,_=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    discard_items(b,list(b.GetTracks()));field._save_field_snapshot(b,source)
    report=tmp_path/'synthetic-discovery-only-native.json'
    force._write(report,dict(violations=[],unconnected_items=[]))
    grade=tmp_path/'synthetic-discovery-only-grade.json'
    force._write(grade,dict(code_identity=force._code_identity(),boards=dict(candidate=dict(
        sha256=force._hash(source),native_producer=dict(ok=True,complete=True,
        native_inventory=dict(potentially_truncated=False),report=str(report),report_sha256=force._hash(report),
        source_files={str(source):force._hash(source)})))))
    worker=Path(__file__).resolve().parents[1]/'build/root_run_local_keeper_miter_20261019.py'
    out=tmp_path/'bounded-stop'
    monkeypatch.setattr(sys,'argv',[str(worker),'--source',str(source),'--grade',str(grade),
        '--out',str(out),'--hint','synthetic','--reporting-build',str(tmp_path/'not-called-native')])
    before=source.read_bytes();runpy.run_path(str(worker),run_name='__main__')
    receipt=json.loads((out/'stage.json').read_text())
    assert receipt['ok'] and receipt['complete'] and not receipt['changed']
    assert not receipt['attempts'] and not receipt['errors'] and source.read_bytes()==before

def test_raw_polygon_gain_cannot_replace_actual_drilled_substrate_material_evidence(tmp_path,monkeypatch):
    source,child,q,_=saved(tmp_path,monkeypatch)
    monkeypatch.setattr(op.actual_material,'removed_material',lambda *a,**k:dict(
        positive_material_removed=False,actual_substrate_intersection_and_global_bores_subtracted=True))
    r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and any('positive_drilled_substrate' in e for e in r['errors'])
