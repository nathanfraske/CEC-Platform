import copy
import time
import pcbnew
import pytest
import cec_source_ground_boundary_connection as op
import cec_field_coupling as field
from cec_native_items import discard_items
from test_complete_cell_connections import native_source


def fixture(tmp_path,monkeypatch,quarter=0,back=False,cap_port=False):
    source,parent,unused,proposal=native_source(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source))
    plane=pcbnew.ZONE(b);plane.SetNet(b.FindNet('GND'));plane.SetLayer(pcbnew.In4_Cu)
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in((0,0),(30,0),(30,30),(0,30)):poly.Outline(0).Append(x*1000000,y*1000000)
    plane.Outline().Append(poly);plane.SetFilledPolysList(pcbnew.In4_Cu,poly);plane.SetIsFilled(True);b.Add(plane)
    if back:
        for f in b.GetFootprints():
            f.SetLayer(pcbnew.B_Cu)
            for p in f.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.B_Cu)
    if quarter:
        for item in[*b.GetFootprints(),*b.GetTracks(),*b.Zones()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source);parent=pcbnew.LoadBoard(str(source))
    poses={ref:[parent.FindFootprintByReference(ref).GetPosition().x/1e6+.5,
        parent.FindFootprintByReference(ref).GetPosition().y/1e6+.5,
        parent.FindFootprintByReference(ref).GetOrientationDegrees()]for ref in proposal['poses']}
    proposal=op.escape.prepare(parent,poses,board_hint='opaque')
    owner=next(ref for ref in poses if ref.endswith('_cap'if cap_port else '_owner'))
    pad=parent.FindFootprintByReference(owner).FindPadByNumber('2');face=next(iter(pad.GetLayerSet().CuStack()))
    edge=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND'
        and pad.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face),0))
    authority=op.compiler._ground_boundary_authority(parent,edge,dict(source_process_barrel_motion=[]),
        proposal,time.monotonic()+10)
    root=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_VIA')
    remote=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND'
        and op.force._uid(t)!=op.force._uid(edge))
    board=pcbnew.LoadBoard(str(source));op.escape.apply_private(board,proposal)
    projected=next(p for f in board.GetFootprints()for p in f.Pads()if op.force._uid(p)==op.force._uid(pad))
    # Other staged mandatory Ground obligations supply their own actual local
    # return. The boundary observer neither creates nor admits these barrels.
    grounds=op.escape.obligations(parent,board,proposal)
    for request in grounds.values():
        if request['kind']!='ground':continue
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pcbnew.VECTOR2I(*request['a']['at_nm']));board.Add(via)
    request=dict(kind='source_boundary',net='GND',
        a=dict(native_uuids=[op.force._uid(root)],at_nm=list(root.GetPosition()),layers=[int(face)]),
        b=dict(pad_uuid=op.force._uid(pad),at_nm=list(projected.GetPosition()),layers=[int(face)]),
        width_nm=max(authority['source_width_nm'],authority['source_full_class_width_nm']),
        exact_additional_macro_component_source_ownership=[authority],every_surviving_source_component_port_mandatory=True)
    requests=grounds;requests['test_source_boundary']=request
    return parent,board,request,requests,proposal


def observe(parent,board,request,requests,proposal):
    return op.observe(parent,board,request,requests,source_proposal=proposal,board_hint='opaque')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_source_role_mandatory_local_return_and_filled_island_all_required(tmp_path,monkeypatch,quarter,back):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch,quarter,back)
    before=[op.row._source_binding(b)for b in(parent,board)]
    proof=observe(parent,board,request,requests,proposal)
    assert proof and proof['all_named_contacts_connected']and not proof['whole_zone_uuid_connectivity_credit']
    assert proof['independently_received_local_ground_returns'][0]['return_mm']==0
    assert proof['new_copper']==proof['new_holes']==0 and not proof['new_hole_admission_authority']
    assert not proof['current_qualified']and not proof['routing_admitted']and not proof['release_authority']
    assert before==[op.row._source_binding(b)for b in(parent,board)]


@pytest.mark.parametrize('fault',['no_ground','reach','role','authority','source_width','current',
    'fake_plan','source_part','child_part','padsize','rule','profile','point','new_atom','zone_uuid','missing_plane','unfilled','no_local'])
def test_forged_scope_and_real_missing_returns_refuse(tmp_path,monkeypatch,fault):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    uid=request['b']['pad_uuid'];ground='ground:'+uid
    if fault=='no_ground':del requests[ground]
    elif fault=='reach':requests[ground]['reach_mm']=8.
    elif fault=='role':request['exact_additional_macro_component_source_ownership'][0]['source_pad_roots'][0]['role']='ground_current_source'
    elif fault=='authority':request['exact_additional_macro_component_source_ownership'][0]['source_pad_roots'][0]['manufacturer_source']='caller'
    elif fault=='source_width':request['width_nm']-=1
    elif fault=='current':request['exact_additional_macro_component_source_ownership'][0]['current_authority']=True
    elif fault=='fake_plan':proposal=copy.deepcopy(proposal);proposal['device_contracts']={}
    elif fault=='source_part':next(f for f in parent.GetFootprints()if f.GetReference().endswith('_owner')).SetValue('unknown')
    elif fault=='child_part':next(f for f in board.GetFootprints()if f.GetReference().endswith('_owner')).SetValue('unknown')
    elif fault=='padsize':next(p for f in board.GetFootprints()for p in f.Pads()if op.force._uid(p)==uid).SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='rule':board.GetDesignSettings().m_TrackMinWidth+=1
    elif fault=='profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_4l';board.SetProperties(props)
    elif fault=='point':request['b']['at_nm'][0]+=1
    elif fault=='new_atom':
        via=next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA')
        request['a']['native_uuids']=[op.force._uid(via)];request['a']['at_nm']=list(via.GetPosition())
        if op.force._uid(via)in{op.force._uid(t)for t in parent.GetTracks()}:request['a']['native_uuids']=['not_source']
    elif fault=='zone_uuid':request['a']['native_uuids']=[op.force._uid(next(iter(board.Zones())))]
    elif fault=='missing_plane':board.Remove(next(iter(board.Zones())))
    elif fault=='unfilled':
        for z in board.Zones():z.UnFill()
    else:
        at=pcbnew.VECTOR2I(*request['b']['at_nm'])
        discard_items(board,[t for t in board.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetPosition()==at])
    assert observe(parent,board,request,requests,proposal)is None


def test_same_zone_identifiers_do_not_join_separate_native_filled_islands(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    assert observe(parent,board,request,requests,proposal)
    root=request['b']['at_nm'];other=request['a']['at_nm']
    poly=pcbnew.SHAPE_POLY_SET()
    for x,y in(root,other):
        poly.NewOutline()
        for dx,dy in((-750000,-1250000),(750000,-1250000),(750000,1250000),(-750000,1250000)):
            poly.Outline(poly.OutlineCount()-1).Append(x+dx,y+dy)
    for z in board.Zones():z.SetFilledPolysList(z.GetLayer(),poly);z.SetIsFilled(True)
    assert observe(parent,board,request,requests,proposal)is None


@pytest.mark.parametrize('back',[False,True])
def test_exact_source_selected_bypass_ground_also_owes_own_immediate_return(tmp_path,monkeypatch,back):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch,back=back,cap_port=True)
    proof=observe(parent,board,request,requests,proposal)
    assert proof and proof['independently_received_local_ground_returns'][0]['max_return_mm']==.8
    del requests['ground:'+request['b']['pad_uuid']]
    assert observe(parent,board,request,requests,proposal)is None


def test_batch_derives_source_cut_ground_set_and_filled_graph_once(tmp_path,monkeypatch):
    parent,board,request,requests,proposal=fixture(tmp_path,monkeypatch)
    for index in range(12):requests['boundary_copy:'+str(index)]=copy.deepcopy(request)
    bad=copy.deepcopy(request);bad['b']['at_nm'][0]+=1;requests['forged_port']=bad
    counts=dict(source=0,ground=0,graph=0)
    for name,module,attribute in(('source',op.escape,'recompile_source_proposal'),
            ('ground',op.escape,'obligations'),('graph',op.partitions,'_inventory')):
        original=getattr(module,attribute)
        def counted(*args,_name=name,_original=original,**kwargs):
            counts[_name]+=1;return _original(*args,**kwargs)
        monkeypatch.setattr(module,attribute,counted)
    result=op.observe_many(parent,board,requests,board_hint='opaque',source_proposal=proposal)
    assert counts==dict(source=1,ground=1,graph=1)
    assert result['test_source_boundary']and all(result['boundary_copy:'+str(i)]for i in range(12))
    assert result['forged_port']is None
    assert all(result[k]is None for k,r in requests.items()if r['kind']=='ground')


@pytest.mark.parametrize('timeout',[True,0,-1,10.1,float('nan')])
def test_bounded_context_refuses(timeout):
    with pytest.raises(ValueError):op.observe(None,None,{}, {},board_hint='opaque',source_proposal={},timeout_s=timeout)
