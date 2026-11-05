"""Independent lanes only select subsets of fresh native topology menus.

Scheduling mocks below are explicitly non-admission. Separate tests exercise
real native search and independent saved Source receiving.
"""
import copy
import time
from types import SimpleNamespace
import pcbnew
import pytest
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
import cec_native_portal_geometry as geometry
import cec_ordinary_signal_completion as ordinary
from cec_native_route_portal import endpoint_layers
from test_native_portal_face_portfolio import plated_fixture
from test_ordinary_native_portals import fixture,target
from test_native_portal_resolution_portfolio import stubs
from test_existing_local_pofv_pad_rule import case

def lane(kind='retained_face',first=int(pcbnew.B_Cu),last=int(pcbnew.B_Cu),reverse=False,index=0):
    return dict(kind=kind,pair_index=index,from_layer=first,to_layer=last,reverse=reverse)

@pytest.mark.parametrize('fault',[
    False,True,{},[],{'kind':'unknown','pair_index':0,'from_layer':0,'to_layer':0,'reverse':False},
    {'kind':'retained_face','pair_index':True,'from_layer':0,'to_layer':0,'reverse':False},
    {'kind':'retained_face','pair_index':32,'from_layer':0,'to_layer':0,'reverse':False},
    {'kind':'source_local_face','pair_index':16,'from_layer':0,'to_layer':0,'reverse':False},
    {'kind':'source_local_face','pair_index':-1,'from_layer':0,'to_layer':0,'reverse':False},
    {'kind':'retained_face','pair_index':0,'from_layer':True,'to_layer':0,'reverse':False},
    {'kind':'retained_face','pair_index':0,'from_layer':0.,'to_layer':0,'reverse':False},
    {'kind':'retained_face','pair_index':0,'from_layer':0,'to_layer':0,'reverse':1},
    {'kind':'retained_face','pair_index':0,'from_layer':0,'to_layer':0,'reverse':False,'receiver_ok':True},
])
def test_malformed_lane_schema_refuses_without_native_admission(fault):
    with pytest.raises(ValueError):geometry._lane_request(fault)

@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('face',[int(pcbnew.B_Cu),int(pcbnew.In2_Cu)])
def test_retained_lane_gets_single_topology_direction_and_original_lease(tmp_path,monkeypatch,face,reverse):
    source,board,net,request=plated_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');before=child.read_bytes()
    # Scheduling is mocked, but native topology discovery still enforces a
    # real <=10s lease. Share its clock epoch rather than relying on uptime.
    origin=time.monotonic();clock=[origin];calls=[]
    monkeypatch.setattr(geometry,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    def bridge(b,a,al,z,zl,width,code,*args,**kwargs):
        assert al==zl=={face}
        assert endpoint_layers(b,a,code)&al and endpoint_layers(b,z,code)&zl
        assert kwargs['deadline_monotonic']==origin+5.
        calls.append((a,z,kwargs))
        return None
    stubs(monkeypatch,bridge)
    result=geometry.apply_native_portals(child,request,5.,lane=lane(first=face,last=face,reverse=reverse))
    assert result['closed']==0 and len(calls)==1
    a=tuple(request['route_endpoints'][1 if reverse else 0][k]*1e6 for k in('x_mm','y_mm'))
    assert calls[0][0]==a
    assert child.read_bytes()==before

@pytest.mark.parametrize('fault',['unproved_face','disabled_face','absent_pair'])
def test_retained_lane_never_promotes_unproved_access_or_alias_index(tmp_path,monkeypatch,fault):
    source,board,net=fixture(tmp_path)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);request['retained_same_face_track_ends']=True
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    selected=lane(first=int(pcbnew.B_Cu),last=int(pcbnew.B_Cu))
    if fault=='disabled_face':selected['from_layer']=int(pcbnew.In6_Cu)
    elif fault=='absent_pair':selected=lane(first=0,last=0,index=31)
    stubs(monkeypatch,lambda *a,**kw:pytest.fail('unproved lane reached search'))
    with pytest.raises(ValueError):geometry.apply_native_portals(child,request,5.,lane=selected)
    assert child.read_bytes()==raw

@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('face',[int(pcbnew.B_Cu),int(pcbnew.In2_Cu)])
def test_actual_retained_lane_native_search_and_saved_receiving(tmp_path,face,reverse):
    source,board,net,request=plated_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');raw=source.read_bytes()
    result=geometry.apply_native_portals(child,request,10.,lane=lane(first=face,last=face,reverse=reverse))
    assert result['closed']==1,result
    proof=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete'],proof
    assert proof['whole_shared_stage_still_required']and source.read_bytes()==raw

def source_prefix_fixture(tmp_path):
    board,source,pad=case(tmp_path)
    other=next(p for f in board.GetFootprints()for p in f.Pads()if p.GetNumber()=='2')
    request=dict(target_net=pad.GetNetname(),width_mm=.2,clearance_mm=.2,
        retained_same_face_track_ends=True,retained_barrel_face_access=True,
        source_local_pad_rule_launches=True,route_endpoints=[
            dict(uuid=force._uid(p),kind='pad',x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6)
            for p in (pad,other)])
    return source,board,pad,other,request

@pytest.mark.parametrize('reverse',[False,True])
def test_actual_source_rule_lane_materializes_prefix_and_receives_saved_native(tmp_path,reverse):
    import cec_additive_route_receiving as receiving
    source,board,pad,other,request=source_prefix_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');raw=source.read_bytes()
    result=geometry.apply_native_portals(child,request,10.,
        lane=lane('source_local_face',first=int(pcbnew.B_Cu),last=int(pcbnew.B_Cu),reverse=reverse))
    assert result['closed']==1,result
    proof=receiving.receive(source,child,timeout_s=10.)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==raw

def test_source_prefix_lane_complete_guard_refuses_whole_packet(tmp_path,monkeypatch):
    import cec_route_proposal_guard as guards
    unpack=guards.RouteProposalGuard._unpack
    source,board,pad,other,request=source_prefix_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes();seen=[]
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        assert code==scratch.GetNetcodeFromNetname(pad.GetNetname())
        assert endpoint_layers(scratch,a,code)&al and endpoint_layers(scratch,b,code)&bl
        ops=[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,next(iter(al)))]
        seen.append(ops)
        assert not kwargs['ops_ok'](ops)
        return ops  # Malicious scheduling worker cannot override final guard.
    checks=stubs(monkeypatch,bridge,accept=False)
    monkeypatch.setattr(guards.RouteProposalGuard,'_unpack',staticmethod(unpack),raising=False)
    result=geometry.apply_native_portals(child,request,5.,
        lane=lane('source_local_face',first=int(pcbnew.B_Cu),last=int(pcbnew.B_Cu)))
    assert result['closed']==0 and seen and child.read_bytes()==raw
    assert any(k=='complete_guard'and any(op[0]=='via'for op in ops)for k,ops in checks)

def test_explicit_none_preserves_real_default_behavior(tmp_path):
    source,board,net,request=plated_fixture(tmp_path)
    a=force._copy_family(source,tmp_path/'default')
    b=force._copy_family(source,tmp_path/'none')
    first=geometry.apply_native_portals(a,request,10.)
    second=geometry.apply_native_portals(b,request,10.,lane=None)
    assert first['closed']==second['closed']==1
    assert ordinary.receive(source,a,board_hint='synthetic',net=net)['ok']
    assert ordinary.receive(source,b,board_hint='synthetic',net=net)['ok']

@pytest.mark.parametrize('fault',['unproved_face','missing_source_permission'])
def test_source_local_lane_cannot_invent_a_plane_or_missing_local_rule(tmp_path,monkeypatch,fault):
    source,board,pad,other,request=source_prefix_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    selected=lane('source_local_face',first=int(pcbnew.In1_Cu),last=int(pcbnew.In1_Cu))
    if fault=='missing_source_permission':
        child.with_suffix('.kicad_dru').unlink()
        selected=lane('source_local_face')
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *a,**kw:pytest.fail('unproved topology searched'))
    with pytest.raises(ValueError):geometry.apply_native_portals(child,request,5.,lane=selected)
    assert child.read_bytes()==raw

def test_lane_pair_index_and_faces_are_literal_subsets_not_strata_ordinals():
    a=dict(at_nm=[1,2],layers=[0,6],native_uuids=['A'],unchanged='root')
    b=dict(at_nm=[3,4],layers=[2,6],native_uuids=['B'],unchanged='peer')
    pairs=[(a,b),(dict(a,at_nm=[5,6]),b)];old=copy.deepcopy(pairs)
    selected=lane(first=6,last=2,index=1,reverse=True)
    result=geometry._lane_pair(pairs,selected)
    assert result[0]['at_nm']==[5,6]and result[0]['layers']==[6]
    assert result[1]['at_nm']==[3,4]and result[1]['layers']==[2]
    assert pairs==old  # reverse changes traversal, NOT from/to authority.
    for wrong in [lane(first=2,last=2),lane(index=31)]:
        with pytest.raises(ValueError):geometry._lane_pair(pairs,wrong)

def test_source_prefix_lane_uses_independent_scratch_netcode_not_original_adapter(tmp_path,monkeypatch):
    source,board,pad,other,request=source_prefix_fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    actual=pad.GetNetCode();seen=[]
    monkeypatch.setattr(board,'GetNetcodeFromNetname',lambda net:actual+1000)
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        seen.append(code)
        assert code==actual==scratch.GetNetcodeFromNetname(pad.GetNetname())
        assert endpoint_layers(scratch,a,code)&al and endpoint_layers(scratch,b,code)&bl
        return None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    menus=[[dict(at_nm=list(pad.GetPosition()),layers=[0])],
        [dict(at_nm=list(other.GetPosition()),layers=[0,6,2])]]
    operations,r=geometry._source_local_operations(board,[pad,other],menus,net=pad.GetNetname(),
        width=200000,clearance=200000,layers=[0,6,2],bridges=[6,2],
        deadline=time.monotonic()+5.,guard=lambda ops:False,planar=None,turn_guard=None,
        lane=lane('source_local_face'))
    assert operations is None and seen==[actual]and child.read_bytes()==raw


def contained_control_fixture(tmp_path,face=pcbnew.F_Cu):
    import json
    import cec_existing_local_pofv_pad_rule as saved_rule
    from test_source_rule_signal_launches import narrow_interval_case
    board,source,pad=narrow_interval_case(tmp_path,face=face);net=pad.GetNetname()
    for wall in list(board.GetTracks()):
        if wall.GetClass()=='PCB_TRACK'and wall.GetWidth()in(1000000,1600000):board.Remove(wall)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()in('GND',net):p.SetNet(pad.GetNet());p.SetPinType('input')
    group=next(g for g in board.Groups()if g.GetName()==saved_rule.GROUP)
    for item in list(board.GetTracks()):
        if item.GetNetname()=='GND':
            group.RemoveItem(item);board.Remove(item)
    # A real plated target supplies both route faces, not an annulus-width
    # waiver on the old .3/.2 seed barrel. Retain the actual existing small
    # group rule using a separate fully contained GND seed, far from this net.
    other=next(p for f in board.GetFootprints()for p in f.Pads()if p.GetNumber()=='2')
    other.SetAttribute(pcbnew.PAD_ATTRIB_PTH);other.SetLayerSet(pcbnew.PAD.PTHMask())
    other.SetSize(pcbnew.VECTOR2I(800000,800000));other.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
    seed_fp=pcbnew.FOOTPRINT(board);seed_fp.SetReference('SEPARATE_GROUP_SEED');board.Add(seed_fp)
    seed=pcbnew.PAD(seed_fp);seed.SetNumber('1');seed.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    seed.SetShape(pcbnew.PAD_SHAPE_RECT);seed.SetLayerSet(pcbnew.PAD.SMDMask())
    seed.SetSize(pcbnew.VECTOR2I(600000,600000));seed.SetPosition(pcbnew.VECTOR2I_MM(25,25))
    seed.SetNet(board.FindNet('GND'));seed_fp.Add(seed)
    via=pcbnew.PCB_VIA(board);via.SetPosition(seed.GetPosition());via.SetNet(seed.GetNet())
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(300000);via.SetDrill(200000);board.Add(via);group.AddItem(via)
    field._save_field_snapshot(board,source)
    pro=source.with_suffix('.kicad_pro');project=json.loads(pro.read_text())
    project['net_settings']={'classes':[dict(name='Default',track_width=.2,
        clearance=.2,via_diameter=.5,via_drill=.3)]};pro.write_text(json.dumps(project))
    board=pcbnew.LoadBoard(str(source));q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    assert q['complete'],q
    request=target(board,q);request.update(retained_same_face_track_ends=True,
        retained_barrel_face_access=True,source_local_pad_rule_launches=True,
        source_local_contained_intervals_only=True)
    return source,board,net,request


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('reverse',[False,True])
def test_independent_contained_lane_rederives_prefix_and_receives_real_saved_join(tmp_path,face,reverse):
    import cec_additive_route_receiving as additive
    source,board,net,request=contained_control_fixture(tmp_path,face)
    route_face=int(pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu)
    child=force._copy_family(source,tmp_path/'contained-child');raw=source.read_bytes()
    r=geometry.apply_native_portals(child,request,10.,
        lane=lane('source_local_face',first=route_face,last=route_face,reverse=reverse))
    assert r['closed']==1,r
    found=r['source_local_pad_rule_launches']['launch_menus']
    assert any(x.get('contained_intervals_only')and any(
        v['kind']=='contained_source_pad_interval'for v in x['choices'])for x in found)
    for module in(ordinary,additive):
        opts=dict(net=net)if module is ordinary else{}
        proof=module.receive(source,child,board_hint='synthetic',timeout_s=10.,**opts)
        assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==raw and not r['release_authority']


@pytest.mark.parametrize('value',[0,1,None,'yes'])
def test_new_contained_lane_flag_cannot_invent_context(tmp_path,value):
    source,board,net,request=contained_control_fixture(tmp_path)
    request['source_local_contained_intervals_only']=value
    child=force._copy_family(source,tmp_path/'bad-policy');raw=child.read_bytes()
    with pytest.raises(ValueError,match='explicit_source_local_contained_interval_policy'):
        geometry.apply_native_portals(child,request,10.)
    assert child.read_bytes()==raw
