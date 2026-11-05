"""Ordinary barrel construction cannot waive native source/endpoint rules."""
import math
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_barrel_reseat as reseat
import cec_source_cut_chain as chain
import cec_fr as fr
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,rotation=0,rename='A'):
    b=_board([],edge=(0,0,25,25));n=pcbnew.NETINFO_ITEM(b,'/ordinary_'+rename);b.Add(n)
    track(b,n.GetNetname(),(6,8),(10,8));track(b,n.GetNetname(),(10,8),(14,8),layer=pcbnew.B_Cu)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(10,8));v.SetWidth(600000);v.SetDrill(300000)
    v.SetNet(n);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);b.Add(v)
    # Original neighbouring copper is the real external restoration boundary.
    track(b,n.GetNetname(),(6,8),(5,8));track(b,n.GetNetname(),(14,8),(15,8),layer=pcbnew.B_Cu)
    if rotation:
        for i in b.GetTracks():i.Rotate(pcbnew.VECTOR2I_MM(12,12),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);uid=force._uid(v)
    q=reseat.plan(pcbnew.LoadBoard(str(source)),source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    target=force._copy_family(source,tmp_path/'trial');child=pcbnew.LoadBoard(str(source));reseat.subtract(child,source,q)
    def rotate(xy):
        a=math.radians(-rotation);x,y=xy[0]-12,xy[1]-12
        return round(12+x*math.cos(a)-y*math.sin(a),6),round(12+x*math.sin(a)+y*math.cos(a),6)
    for layer,points in ((pcbnew.F_Cu,[(6,8),(9.5,8),(10,8.5)]),
            (pcbnew.B_Cu,[(14,8),(10.5,8),(10,8.5)])):
        for a,z in zip(points,points[1:]):track(child,n.GetNetname(),rotate(a),rotate(z),layer=layer)
    v=pcbnew.PCB_VIA(child);v.SetPosition(pcbnew.VECTOR2I_MM(*rotate((10,8.5))))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(child.GetNetcodeFromNetname(n.GetNetname()))
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);child.Add(v)
    field._save_field_snapshot(child,target)
    return source,target,uid


@pytest.mark.parametrize('rotation,name',[(0,'A'),(90,'Renamed'),(180,'Other'),(270,'Different')])
def test_rotated_source_barrel_restores_both_real_boundaries(tmp_path,rotation,name):
    source,target,uid=fixture(tmp_path,rotation,name);before=source.read_bytes()
    assert not reseat.receive(source,target,via_uuid=uid,board_hint='synthetic')['ok']
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['barrel_geometry_exact'] and proof['all_surviving_partitions_preserved']
    assert not proof['release_authority'] and not proof['current_authority'] and source.read_bytes()==before
    assert not additive.receive(source,target)['ok']
    receipt=chain.receive(source,target,board_hint='synthetic',phases=[
        dict(kind='ordinary_barrel_reseat',candidate=str(target),via_uuid=uid,allow_owned_locked=True)])
    assert receipt['ok'] and receipt['complete'],receipt


@pytest.mark.parametrize('fault',['width','drill','diameter','open','extra','pose','ordinary_flag'])
def test_incoming_copper_cannot_weaken_scope(tmp_path,fault):
    source,target,uid=fixture(tmp_path);child=pcbnew.LoadBoard(str(target))
    incoming={force._uid(i) for i in child.GetTracks()}-{force._uid(i) for i in pcbnew.LoadBoard(str(source)).GetTracks()}
    tracks=[i for i in child.GetTracks() if force._uid(i) in incoming and i.GetClass()=='PCB_TRACK']
    v=next(i for i in child.GetTracks() if i.GetClass()=='PCB_VIA')
    if fault=='width':tracks[0].SetWidth(150000)
    elif fault=='drill':v.SetDrill(250000)
    elif fault=='diameter':v.SetWidth(700000)
    elif fault=='open':tracks[0].Move(pcbnew.VECTOR2I_MM(0,.3))
    elif fault=='extra':track(child,'/ordinary_A',(20,20),(21,20))
    elif fault=='pose':
        fp=pcbnew.FOOTPRINT(child);fp.SetReference('UNRELATED');child.Add(fp)
    field._save_field_snapshot(child,target)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=1 if fault=='ordinary_flag' else True)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['group','tee','small','specialized','pad'])
def test_source_cannot_claim_protected_or_unowned_departures(tmp_path,fault):
    source,target,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    via=next(i for i in b.GetTracks() if i.GetClass()=='PCB_VIA')
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');g.AddItem(via);b.Add(g)
    elif fault=='tee':track(b,'/ordinary_A',(9,7),(9,9))
    elif fault=='small':via.SetWidth(350000);via.SetDrill(250000)
    elif fault=='specialized':
        net=pcbnew.NETINFO_ITEM(b,'/SENSE_HI');b.Add(net)
        for i in b.GetTracks():i.SetNet(net)
    else:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('FIXED');p=pcbnew.PAD(fp)
        p.SetNet(b.FindNet('/ordinary_A'));p.SetPosition(via.GetPosition());p.SetSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);fp.Add(p);b.Add(fp)
    with pytest.raises(ValueError):
        reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)


@pytest.mark.parametrize('rotation,name',[(0,'Portal'),(90,'Moved'),(180,'Another'),(270,'Unrelated')])
def test_replacement_portals_do_not_collide_with_the_retired_source_hole(tmp_path,rotation,name):
    source,target,uid=fixture(tmp_path,rotation,name);before=source.read_bytes()
    native=pcbnew.LoadBoard(str(source));old=next(t for t in native.GetTracks() if force._uid(t)==uid)
    near=pcbnew.VECTOR2I(old.GetPosition().x+200000,old.GetPosition().y)
    assert not fr._via_spot_clear(native,near,600000,200000,{old.GetNetCode()},
        drill_nm=300000,net_code=old.GetNetCode(),foreign_cache={})
    proof=reseat.portal_candidates(source,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=True,radius_mm=.5,grid_mm=.1)
    assert proof['ok'] and proof['complete'],proof
    assert list(near) in proof['portals_nm'] and before==source.read_bytes()
    assert not proof['routing_admitted'] and not proof['no_path_proof'] and not proof['release_authority']


@pytest.mark.parametrize('radius,grid',[(True,.1),(float('nan'),.1),(0,.1),(2.1,.1),(.5,True),
    (.5,float('inf')),(.5,.04),(.5,1),(2.,.05)])
def test_portal_menu_requires_finite_literal_bounded_work(tmp_path,radius,grid):
    source,target,uid=fixture(tmp_path)
    proof=reseat.portal_candidates(source,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=True,radius_mm=radius,grid_mm=grid)
    assert not proof['ok'] and proof['errors'] and not proof['routing_admitted']


@pytest.mark.parametrize('value',[True,-1,16.1,float('inf'),float('nan'),'4'])
def test_additional_path_is_a_literal_bounded_work_policy(tmp_path,value):
    source,target,uid=fixture(tmp_path)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=True,max_additional_path_mm=value)
    assert not proof['ok'] and proof['errors'],proof
    with pytest.raises(ValueError):
        chain._phases([dict(kind='ordinary_barrel_reseat',candidate=str(target),via_uuid=uid,
            allow_owned_locked=True,max_additional_path_mm=value)],target)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('name',['renamed_long_signal','another_independent_net'])
def test_explicit_long_source_endpoint_leg_keeps_native_scope_and_default(tmp_path,rotation,name):
    b=_board([],edge=(0,0,35,35));n=pcbnew.NETINFO_ITEM(b,'/'+name);b.Add(n)
    for layer,a,z in [(pcbnew.F_Cu,(7,8),(20,8)),(pcbnew.F_Cu,(6,8),(7,8)),
            (pcbnew.B_Cu,(20,8),(24,8)),(pcbnew.B_Cu,(24,8),(25,8))]:
        track(b,n.GetNetname(),a,z,layer=layer)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(20,8));v.SetWidth(600000)
    v.SetDrill(300000);v.SetNet(n);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);b.Add(v)
    if rotation:
        for i in b.GetTracks():i.Rotate(pcbnew.VECTOR2I_MM(17,17),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    source=tmp_path/'long-source.kicad_pcb';field._save_field_snapshot(b,source);uid=force._uid(v)
    before=source.read_bytes()
    with pytest.raises(ValueError):
        reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    q=reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,max_source_leg_mm=14.)
    child=pcbnew.LoadBoard(str(source));reseat.subtract(child,source,q)
    def rotate(xy):
        angle=math.radians(-rotation);x,y=xy[0]-17,xy[1]-17
        return round(17+x*math.cos(angle)-y*math.sin(angle),6),round(17+x*math.sin(angle)+y*math.cos(angle),6)
    for layer,points in [(pcbnew.F_Cu,[(7,8),(19.5,8),(20,8.5)]),
            (pcbnew.B_Cu,[(24,8),(20.5,8),(20,8.5)])]:
        for a,z in zip(points,points[1:]):track(child,n.GetNetname(),rotate(a),rotate(z),layer=layer)
    via=pcbnew.PCB_VIA(child);via.SetPosition(pcbnew.VECTOR2I_MM(*rotate((20,8.5))))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNetCode(child.GetNetcodeFromNetname(n.GetNetname()));child.Add(via)
    target=force._copy_family(source,tmp_path/'long-target');field._save_field_snapshot(child,target)
    assert not reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)['ok']
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=True,max_source_leg_mm=14.)
    assert proof['ok'] and proof['complete'],proof
    received=chain.receive(source,target,board_hint='synthetic',phases=[dict(
        kind='ordinary_barrel_reseat',candidate=str(target),via_uuid=uid,allow_owned_locked=True,
        max_source_leg_mm=14.)])
    assert received['ok'] and received['complete'],received
    assert source.read_bytes()==before and not proof['release_authority'] and not proof['current_authority']


@pytest.mark.parametrize('value',[True,0,-1,16.0001,float('inf'),float('nan'),'12'])
def test_source_leg_budget_never_broadens_implicitly_or_accepts_nonliteral_scope(tmp_path,value):
    source,target,uid=fixture(tmp_path)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',
        allow_owned_locked=True,max_source_leg_mm=value)
    assert not proof['ok'] and proof['errors'],proof
    with pytest.raises(ValueError):
        chain._phases([dict(kind='ordinary_barrel_reseat',candidate=str(target),via_uuid=uid,
            allow_owned_locked=True,max_source_leg_mm=value)],target)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_tiny_contiguous_same_width_barrel_kernel_is_source_typed(tmp_path,rotation):
    source,target,uid=fixture(tmp_path,rotation);b=pcbnew.LoadBoard(str(source))
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    endpoint=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu
        and tuple(via.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd())))
    far=pcbnew.VECTOR2I(*(endpoint.GetEnd() if tuple(endpoint.GetStart())==tuple(via.GetPosition()) else endpoint.GetStart()))
    root=pcbnew.VECTOR2I(*via.GetPosition());length=math.dist(tuple(root),tuple(far))
    bend=pcbnew.VECTOR2I(*(round(root[i]+.15*(far[i]-root[i])/length*1e6) for i in (0,1)))
    # The following edge physically overlaps the circular land but does not
    # terminate at its centre. It must share an exact endpoint and width with
    # the actual centre-ending stub, never a coincident interior tee.
    endpoint.SetStart(root);endpoint.SetEnd(bend)
    following=pcbnew.PCB_TRACK(b);following.SetStart(bend);following.SetEnd(far)
    following.SetWidth(endpoint.GetWidth());following.SetLayer(endpoint.GetLayer());following.SetNet(endpoint.GetNet())
    b.Add(following);field._save_field_snapshot(b,source)
    q=reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert force._uid(following) in q['retired_track_uuids'] and len(q['retired_track_uuids'])==3


@pytest.mark.parametrize('fault',[None,'width','extra'])
def test_explicit_larger_reseat_is_work_extent_not_a_geometry_or_ownership_waiver(tmp_path,fault):
    source,target,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(target))
    via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA');via.SetPosition(pcbnew.VECTOR2I_MM(10,10.5))
    old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    for layer,points in ((pcbnew.F_Cu,[(6,8),(7.5,8),(10,10.5)]),
            (pcbnew.B_Cu,[(14,8),(12.5,8),(10,10.5)])):
        legs=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==layer and force._uid(t) not in old]
        legs.sort(key=lambda t:math.dist(tuple(t.GetStart()),tuple(pcbnew.VECTOR2I_MM(*points[0]))))
        for leg,a,z in zip(legs,points,points[1:]):leg.SetStart(pcbnew.VECTOR2I_MM(*a));leg.SetEnd(pcbnew.VECTOR2I_MM(*z))
    if fault=='width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t) not in old).SetWidth(150000)
    elif fault=='extra':track(b,'/ordinary_A',(20,20),(21,20))
    field._save_field_snapshot(b,target)
    assert not reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)['ok']
    result=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,
        max_reseat_mm=3.,max_additional_path_mm=8.)
    assert result['ok']==(fault is None),result
    if fault is None:assert result['complete'] and not result['release_authority'] and not result['current_authority']


@pytest.mark.parametrize('value',[True,0,-1,16.1,float('inf'),float('nan'),'8'])
def test_unknown_or_unbounded_barrel_reseat_distance_refuses(tmp_path,value):
    source,target,uid=fixture(tmp_path)
    result=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,max_reseat_mm=value)
    assert not result['ok'] and result['errors'],result


def test_endpoint_refusal_reports_the_actual_blocking_copper(tmp_path):
    source,target,uid=fixture(tmp_path);parent=pcbnew.LoadBoard(str(source))
    other=pcbnew.NETINFO_ITEM(parent,'/foreign');parent.Add(other)
    track(parent,'/foreign',(8,9.85),(8,10.85));field._save_field_snapshot(parent,source)
    # Recompile a continuous F.Cu detour through this real foreign object;
    # the barrel and both original external boundaries remain unchanged.
    child=pcbnew.LoadBoard(str(source));foreign_parent=next(t for t in parent.GetTracks() if t.GetNetname()=='/foreign')
    q=reseat.plan(child,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    reseat.subtract(child,source,q)
    track(child,'/ordinary_A',(14,8),(10.5,8),layer=pcbnew.B_Cu)
    track(child,'/ordinary_A',(10.5,8),(10,8.5),layer=pcbnew.B_Cu)
    via=pcbnew.PCB_VIA(child);via.SetPosition(pcbnew.VECTOR2I_MM(10,8.5));via.SetWidth(600000)
    via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetNetCode(child.GetNetcodeFromNetname('/ordinary_A'));child.Add(via)
    for a,z in zip([(6,8),(6,9.5),(9,9.5),(10,8.5)],[(6,9.5),(9,9.5),(10,8.5)]):
        track(child,'/ordinary_A',a,z)
    field._save_field_snapshot(child,target)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert not proof['ok'] and proof['endpoint_leg_guard_failures'],proof
    assert any(force._uid(foreign_parent)==hit['uuid'] for row in proof['endpoint_leg_guard_failures']
        for hit in row['blockers']),proof
