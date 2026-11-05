"""Explicit synthetic budgets exercise native geometry, not hardware ratings."""
import copy
import time
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_corner_finish as owner
import cec_full_current_corner_stage as stage
import cec_native_scalar_corner_scope as scope
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu,width=1.):
    net = '/renamed/POWER_BUS'
    def pose(p):
        x,y = p[0]-25,p[1]-25
        if mirror: x=-x
        for _ in range(quarter): x,y=-y,x
        return 25+x,25+y
    points = [pose(p) for p in ((10,15),(25,15),(25,30))]
    board = _board([(*points[0],net),(*points[-1],net)],edge=(0,0,50,50));board.SetCopperLayerCount(6)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    for a,b in zip(points,points[1:]):
        t=track(board,net,a,b,layer=face,width=width);t.SetLocked(True)
    domains={net:dict(net=net,complete=True,source_refs=['X1'],sink_refs=['X2'])}
    contract=dict(net=net,routing_layers=['F.Cu','B.Cu','In2.Cu'],
        required_by_layer_mm={n:.2 for n in ('F.Cu','B.Cu','In2.Cu')},
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    monkeypatch.setattr(owner.topology,'board_current_domains',lambda *a,**k:copy.deepcopy(domains))
    monkeypatch.setattr(owner.topology,'route_width_contracts',lambda *a,**k:{net:copy.deepcopy(contract)})
    monkeypatch.setattr(owner.topology,'distributed_supply_contracts',lambda *a,**k:dict(contracts={}))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(board,source)
    return source,net,domains,contract


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('width',[.2,.6,1.,5.])
def test_saved_full_width_miters_are_native_renamed_rotated_and_mirrored(tmp_path,monkeypatch,quarter,mirror,face,width):
    source,net,domains,contract=fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,width=width)
    before=source.read_bytes();model=copy.deepcopy((domains,contract));b=pcbnew.LoadBoard(str(source))
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    assert len(rows)==1
    proposal=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    made=owner.materialize(b,source,proposal,board_hint='synthetic')
    candidate=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,candidate)
    result=owner.receive(source,candidate,proposal,board_hint='synthetic')
    assert result['ok'] and result['complete'],result
    assert result['saved_trace_length_mm']>0 and result['actual_visible_native_material_removed']['ok']
    assert result['chamfered']==1 and result['source_width_face_and_current_exact']
    assert result['new_holes']==result['new_vias']==0 and not result['ordinary_reclassification']
    assert not result['release_authority'] and (domains,contract)==model and source.read_bytes()==before
    saved=pcbnew.LoadBoard(str(candidate))
    assert len(list(saved.GetTracks()))==3
    assert all(t.GetWidth()==round(width*1e6) and t.GetLayer()==face and t.IsLocked() for t in saved.GetTracks())
    assert not scope.select(saved,{net},maximum_width_nm=10000000)['selected']


@pytest.mark.parametrize('fault',['incomplete','unknown_authority','underwidth','missing_source','missing_sink',
    'bad_margin','missing_face','ground','locked','mask','group','pair','stale_path'])
def test_source_or_process_contradictions_never_gain_full_current_corner_authority(tmp_path,monkeypatch,fault):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));tracks=list(b.GetTracks())
    if fault=='incomplete':domains[net]['complete']=False
    elif fault=='unknown_authority':contract['current_authority']['source']='guess'
    elif fault=='underwidth':contract['required_by_layer_mm']['F.Cu']=1.000001
    elif fault=='missing_source':domains[net]['source_refs']=[]
    elif fault=='missing_sink':domains[net]['sink_refs']=[]
    elif fault=='bad_margin':contract['current_authority']['geometry_margin']=.9
    elif fault=='missing_face':contract['routing_layers']=[]
    elif fault=='ground':
        domains['GND']=domains.pop(net);contract['net']='GND'
        b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
        for t in tracks:t.SetNet(b.FindNet('GND'))
        for fp in b.GetFootprints():
            for pad in fp.Pads():pad.SetNet(b.FindNet('GND'))
    elif fault=='mask':tracks[0].SetHasSolderMask(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='pair':monkeypatch.setattr(owner.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/OTHER')])
    elif fault=='stale_path':b.SetFileName(str(tmp_path/'different.kicad_pcb'))
    old=field._field_snapshot_inventory(b)
    if fault=='stale_path':
        with pytest.raises(ValueError):owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
    else:
        r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=fault!='locked')
        assert not r['requests']
    assert old==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('tamper',['narrow','pose','extra_net','via','stale_plan'])
def test_independent_saved_receiver_refuses_foreign_changes(tmp_path,monkeypatch,tamper):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    p=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    owner.materialize(b,source,p,board_hint='synthetic')
    if tamper=='narrow':next(iter(b.GetTracks())).SetWidth(999999)
    elif tamper=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,1))
    elif tamper=='extra_net':track(b,'/OTHER',(35,35),(40,35))
    elif tamper=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(20,20));
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    else:p['maximum_nm']=1000000
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=owner.receive(source,child,p,board_hint='synthetic')
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('kwargs',[dict(max_trials=0),dict(max_trials=17),dict(max_trials=True),dict(allow_locked_source=1),
    dict(maximum_nm=2000001),dict(minimum_nm=0),dict(expected_source_sha256='guess')])
def test_invalid_trial_context_cannot_create_an_output_family(tmp_path,kwargs):
    settings=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    settings.update(kwargs);out=tmp_path/'not-created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',out,**settings)
    assert not out.exists()


def test_narrow_default_geometry_scope_does_not_silently_expand(tmp_path,monkeypatch):
    source,net,domains,contract=fixture(tmp_path,monkeypatch,width=1.)
    b=pcbnew.LoadBoard(str(source));assert not scope.select(b,{net})['selected']
    assert len(scope.select(b,{net},maximum_width_nm=10000000)['selected'])==1


@pytest.mark.parametrize('mode',['full_cover','unknown_fill','different_net','different_face'])
def test_visible_progress_uses_real_same_net_same_face_fills_not_only_track_lengths(tmp_path,monkeypatch,mode):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(source))
    rows=owner.discover(child,source,board_hint='synthetic',allow_locked_source=True)['requests']
    p=owner.plan(child,source,rows,board_hint='synthetic',allow_locked_source=True)
    made=owner.materialize(child,source,p,board_hint='synthetic')
    zone=pcbnew.ZONE(parent);zone.SetLayer(pcbnew.B_Cu if mode=='different_face' else pcbnew.F_Cu)
    if mode=='different_net':
        parent.Add(pcbnew.NETINFO_ITEM(parent,'/OTHER'));zone.SetNet(parent.FindNet('/OTHER'))
    else:zone.SetNet(parent.FindNet(net))
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((5,5),(40,5),(40,40),(5,40)):poly.Append(x*1000000,y*1000000)
    zone.Outline().NewOutline()
    for x,y in ((5,5),(40,5),(40,40),(5,40)):zone.Outline().Append(x*1000000,y*1000000)
    face=zone.GetLayer();zone.SetFilledPolysList(face,poly);zone.SetIsFilled(mode!='unknown_fill');parent.Add(zone)
    old=list(parent.GetTracks());new=list(child.GetTracks());retired=set(made['retired_track_uuids'])
    if mode in ('full_cover','unknown_fill'):
        with pytest.raises(ValueError,match='hidden_by_retained_native_copper|unknown_same_net_fill'):
            owner._visible_removed(parent,old,new,retired,deadline=time.monotonic()+10.)
    else:assert owner._visible_removed(parent,old,new,retired,deadline=time.monotonic()+10.)['ok']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_adjacent_shared_edge_corners_are_one_exact_saved_full_current_cut(tmp_path,monkeypatch,face):
    source,net,domains,contract=fixture(tmp_path,monkeypatch,face=face)
    b=pcbnew.LoadBoard(str(source));items=list(b.GetTracks())
    last=next(t for t in items if t.GetStart().x==t.GetEnd().x)
    last.SetEnd(pcbnew.VECTOR2I_MM(25,25))
    t=track(b,net,(25,25),(35,25),layer=face,width=1.);t.SetLocked(True)
    for fp in b.GetFootprints():
        if fp.GetReference()=='X2':
            fp.Move(pcbnew.VECTOR2I_MM(10,-5))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    assert len(rows)==2
    proposal=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    assert len(proposal['full_current_proposal']['retired_track_uuids'])==3
    owner.materialize(b,source,proposal,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'two-corners');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,proposal,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['chamfered']==2 and r['actual_visible_native_material_removed']['ok'],r


def test_readonly_inventory_and_plan_reuse_the_actual_native_source_for_dimensions(tmp_path,monkeypatch):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));calls=[];original=owner.fr._project_netclass_resolver
    def resolver(path,*,board=None):
        calls.append(board)
        assert board is not None and board.GetFileName()==str(source)
        return original(path,board=board)
    monkeypatch.setattr(owner.fr,'_project_netclass_resolver',resolver)
    rows=owner.discover(board,source,board_hint='synthetic',allow_locked_source=True)['requests']
    proposal=owner.plan(board,source,rows,board_hint='synthetic',allow_locked_source=True)
    assert proposal['full_current_proposal']['contract']==contract and calls
    assert all(q is board for q in calls)


def test_readonly_repeated_net_models_are_local_not_a_saved_receiving_authority(tmp_path,monkeypatch):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));original=owner.full._model;calls=[]
    def model(*args,**kwargs):calls.append(args[2]);return original(*args,**kwargs)
    monkeypatch.setattr(owner.full,'_model',model)
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    assert rows and calls==[net]
    contract['current_authority']['amps']=0
    assert not owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    assert calls==[net,net]


@pytest.mark.parametrize('mode',['actual','outline_only','different_net','different_face'])
def test_hidden_preflight_requires_literal_saved_fill_coverage(tmp_path,monkeypatch,mode):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));items=list(b.GetTracks())
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.B_Cu if mode=='different_face' else pcbnew.F_Cu)
    if mode=='different_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'/OTHER'));z.SetNet(b.FindNet('/OTHER'))
    else:z.SetNet(b.FindNet(net))
    z.Outline().NewOutline()
    for x,y in ((5,5),(40,5),(40,40),(5,40)):z.Outline().Append(x*1000000,y*1000000)
    z.SetFilledPolysList(z.GetLayer(),z.Outline());z.SetIsFilled(mode!='outline_only');b.Add(z)
    old=field._field_snapshot_inventory(b)
    assert owner._fully_hidden_source(b,items,{},time.monotonic()+10.)==(mode=='actual')
    assert old==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('mode',['partial_keeper','outline_only','different_net','different_face'])
def test_trace_only_chamfer_cannot_leave_a_retained_power_keeper_spur(tmp_path,monkeypatch,mode):
    source,net,domains,contract=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));z=pcbnew.ZONE(b)
    z.SetLayer(pcbnew.B_Cu if mode=='different_face' else pcbnew.F_Cu)
    if mode=='different_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'/OTHER'));z.SetNet(b.FindNet('/OTHER'))
    else:z.SetNet(b.FindNet(net))
    z.SetZoneName('arbitrary_actual_source_owner')
    z.Outline().NewOutline()
    for x,y in ((24,14),(26,14),(26,16),(24,16)):z.Outline().Append(x*1000000,y*1000000)
    z.SetFilledPolysList(z.GetLayer(),z.Outline());z.SetIsFilled(mode!='outline_only');b.Add(z)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source));before=source.read_bytes()
    r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
    if mode in ('partial_keeper','outline_only'):
        assert not r['requests'] and len(r['composed_power_contour_frontier'])==1
        assert r['refusals']['source_corner_requires_owner_synchronized_power_contour_refresh']==1
        q=r['composed_power_contour_frontier'][0]['retained_native_corner_owners'][0]
        assert q['actual_native_fill']==(mode=='partial_keeper') and q['requires_composed_contour_owner']
    else:assert len(r['requests'])==1 and not r['composed_power_contour_frontier']
    assert source.read_bytes()==before
