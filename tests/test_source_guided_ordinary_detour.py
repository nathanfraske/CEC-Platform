"""Exact guide geometry, native obstacles, typed ownership and saved replay."""
import copy,math,time
from pathlib import Path
from unittest import mock
import pcbnew
import pytest
import cec_source_guided_ordinary_detour as guided
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as owner
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def transform(angle,mirror):
    def point(p):
        x,y=p
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return [int(x+16000000),int(y+16000000)]
    return point


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('diagonal',[False,True])
@pytest.mark.parametrize('side',[0,1])
def test_integer_bypass_is_fixed_port_monotone_and_has_only_45deg_turns(angle,mirror,diagonal,side):
    point=transform(angle,mirror);hint=[point((-4000000,0)),point((4000000,8000000 if diagonal else 0))]
    path=guided.guide_bypass(hint,2000000,6000000,500000,side)
    assert path[0]==hint[0] and path[-1]==hint[-1]
    edges=[[b[i]-a[i] for i in (0,1)] for a,b in zip(path,path[1:])]
    assert all(not(x and y) or abs(x)==abs(y) for x,y in edges)
    assert all(sum(a*b for a,b in zip(u,v))>0 for u,v in zip(edges,edges[1:]))
    assert len(set(map(tuple,path)))==len(path)
    assert not guided.strictly_shorter(path,hint)


@pytest.mark.parametrize('a,b',[(2,1),(3,2),(7,5),(17,12),(99,70),(577,408),(3363,2378),(19601,13860),(114243,80782)])
def test_radical_comparison_has_no_float_or_equal_length_waiver(a,b):
    cardinal=[[0,0],[a,0]];diagonal=[[0,0],[b,b]]
    assert guided.strictly_shorter(cardinal,diagonal)==(a*a<2*b*b)
    assert guided.strictly_shorter(diagonal,cardinal)==(2*b*b<a*a)
    assert not guided.strictly_shorter(cardinal,cardinal)


@pytest.mark.parametrize('fault',['bool','non45','zero','lo','hi','height','side','middle'])
def test_unsupported_hint_or_ambiguous_integer_bypass_refuses(fault):
    points=[[0,0],[8000000,0]];args=[2000000,6000000,500000,0]
    if fault=='bool':points[0][0]=False
    elif fault=='non45':points[-1][1]=3000000
    elif fault=='zero':points[-1]=points[0][:]
    elif fault=='lo':args[0]=0
    elif fault=='hi':args[1]=8000000
    elif fault=='height':args[2]=-1
    elif fault=='side':args[3]=2
    else:args[2]=2000000
    with pytest.raises(ValueError):guided.guide_bypass(points,*args)


def fixture(tmp_path,*,angle=0,mirror=False,face=pcbnew.F_Cu,net='/unrelated/CONTROL',locked=True):
    point=transform(angle,mirror)
    mm=lambda p:tuple(v/1e6 for v in point(p))
    a,z=(-7000000,0),(7000000,0)
    b=_board([(*mm(a),net),(*mm(z),net),(*mm((0,0)),'GND')],edge=(0,0,34,34))
    b.SetCopperLayerCount(6);props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for fp in b.GetFootprints():
        for p in fp.Pads():p.SetNumber('1')
    # Canonical45 rising/falling flanks, enough room for actual foreign pad.
    path=[a,(-5000000,0),(-2000000,3000000),(2000000,3000000),(5000000,0),z]
    ids=[]
    for x,y in zip(path,path[1:]):
        t=track(b,net,mm(x),mm(y),width=.2);t.SetLayer(face);t.SetLocked(locked);ids.append(force._uid(t))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    guide_source=force._copy_family(source,tmp_path/'guide');h=pcbnew.LoadBoard(str(guide_source))
    discard_items(h,list(h.GetTracks()));g=track(h,net,mm(a),mm(z),width=.2);g.SetLayer(face);g.SetLocked(locked)
    gid=force._uid(g);field._save_field_snapshot(h,guide_source)
    return source,guide_source,gid,ids,net


def make_plan(source,hint,gid,ids,**kw):
    return guided.plan(source,hint,gid,ids,board_hint='synthetic',allow_locked_track_uuids=ids,**kw)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_guide_shortens_arbitrary_owned_chain_and_receives_saved_phase(tmp_path,angle,mirror,face):
    source,hint,gid,ids,net=fixture(tmp_path,angle=angle,mirror=mirror,face=face)
    before=[p.read_bytes() for p in (source,hint)];p=make_plan(source,hint,gid,ids)
    assert p['exact_radical_strict_shortening'] and p['net']==net
    b=pcbnew.LoadBoard(str(source));made=guided.construct(b,p)
    child=force._copy_family(source,tmp_path/'candidate');additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=guided.receive(source,child,p,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert not proof['release_authority'] and proof['full_native_current_field_cut_receiving_required']
    assert made['private_unadmitted'] and len(made['incoming_track_uuids'])<=5
    assert [p.read_bytes() for p in (source,hint)]==before


@pytest.mark.parametrize('net',['+5V','GND','/USB_D_P','/CAN_H','/SENSE_HI','/CLOCK'])
def test_old_guide_cannot_grant_power_ground_pair_sense_or_clock_ownership(tmp_path,net):
    source,hint,gid,ids,_=fixture(tmp_path,net=net)
    with pytest.raises(ValueError,match='ordinary_signal_role'):make_plan(source,hint,gid,ids)


@pytest.mark.parametrize('fault',['lock','extra_lock','group','width','guide_width','guide_face','port','branch','process','deadline'])
def test_source_or_guide_scope_cannot_be_manufactured(tmp_path,fault):
    source,hint,gid,ids,_=fixture(tmp_path)
    if fault in ('lock','extra_lock','deadline'):
        with pytest.raises(ValueError):guided.plan(source,hint,gid,ids,board_hint='synthetic',
            allow_locked_track_uuids=[] if fault=='lock' else ids+(['missing'] if fault=='extra_lock' else []),
            timeout_s=0 if fault=='deadline' else 10.)
        return
    path=hint if fault.startswith('guide_') else source;b=pcbnew.LoadBoard(str(path));t=next(iter(b.GetTracks()))
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    elif fault in ('width','guide_width'):t.SetWidth(250000)
    elif fault=='guide_face':t.SetLayer(pcbnew.In3_Cu)
    elif fault=='port':t.SetStart(t.GetStart()+pcbnew.VECTOR2I(0,100000))
    elif fault=='branch':
        extra=t.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(100000,100000));b.Add(extra);ids.append(force._uid(extra))
    else:t.SetLocked(False)
    field._save_field_snapshot(b,path)
    with pytest.raises(ValueError):make_plan(source,hint,gid,ids)


def test_same_net_real_midbody_tap_cannot_be_dropped_for_a_shorter_guide(tmp_path):
    source,hint,gid,ids,net=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    tap=track(b,net,(16,19),(16,21),width=.2);tap.SetLocked(True);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='no_received_shortening'):make_plan(source,hint,gid,ids)


def test_rehashed_worker_polygon_and_changed_native_board_are_not_authority(tmp_path):
    source,hint,gid,ids,_=fixture(tmp_path);p=make_plan(source,hint,gid,ids);b=pcbnew.LoadBoard(str(source))
    forged=copy.deepcopy(p);forged['candidate_points_nm'][1][0]+=100000
    forged.pop('plan_sha256');forged['plan_sha256']=owner._digest(forged)
    with pytest.raises(ValueError,match='source_derived'):guided.construct(b,forged)
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(100000,0))
    with pytest.raises(ValueError,match='native_board_changed'):guided.construct(b,p)


@pytest.mark.parametrize('fault',['width','net','pad','barrel','partial','lock'])
def test_saved_child_requires_exact_native_geometry_process_and_full_replay(tmp_path,fault):
    source,hint,gid,ids,_=fixture(tmp_path);p=make_plan(source,hint,gid,ids);b=pcbnew.LoadBoard(str(source));made=guided.construct(b,p)
    t=next(t for t in b.GetTracks() if force._uid(t)==made['incoming_track_uuids'][0])
    if fault=='width':t.SetWidth(100000)
    elif fault=='net':pass  # Exercise the saved receiver below, not SaveBoard's net normalization.
    elif fault=='pad':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(100000,0))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetNetCode(t.GetNetCode());v.SetPosition(t.GetStart());v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='partial':discard_items(b,[t])
    else:t.SetLocked(False)
    child=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,child)
    if fault=='net':
        root,nodes=additive._nodes(child);node=nodes[force._uid(t)]
        row=next(q for q in node if isinstance(q,list) and q and q[0]=='net')
        row[1]=str(b.GetNetcodeFromNetname('GND'))
        child.write_text(additive._render(root)+'\n')
    proof=guided.receive(source,child,p,board_hint='synthetic');assert not proof['ok'] and proof['errors']


def test_source_guide_exception_still_cleans_up_temporary_reservations(tmp_path):
    import cec_future_pose_clearance as future
    from test_native_portal_preclear import fixture as portal_fixture,plan as portal_plan
    b,source,pad,blocked=portal_fixture(tmp_path,locked=True);p=portal_plan(b,source,pad,allow_locked_track_uuids=[blocked])
    with mock.patch.object(guided,'propose',side_effect=RuntimeError('independent source-guide abort')):
        with pytest.raises(RuntimeError,match='source-guide abort'):future.construct(b,p,source=source)
    assert not any(z.GetIsRuleArea() for z in b.Zones())


def test_actual_future_portal_pipeline_uses_native_source_guide_before_maze(tmp_path):
    import cec_future_pose_clearance as future
    from test_native_portal_preclear import fixture as portal_fixture,plan as portal_plan
    b,source,pad,blocked=portal_fixture(tmp_path,locked=True);p=portal_plan(b,source,pad,allow_locked_track_uuids=[blocked])
    result=future.construct(b,p,source=source,refine_maze=True,source_guided_detours=True)
    assert result['closed']==1 and result['source_guided_detours']
    assert result['nets'][0]['construction']['source_guide_trials'][0]['selected']
    assert all(not z.GetIsRuleArea() for z in b.Zones())
    child=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,child)
    q=ordinary.receive(source,child,retired_track_uuids=[blocked],allow_locked_track_uuids=[blocked],board_hint='synthetic')
    assert q['ok'] and q['complete'],q


def test_rejected_guide_does_not_disable_the_existing_native_maze_fallback(tmp_path):
    import cec_future_pose_clearance as future
    from test_native_portal_preclear import fixture as portal_fixture,plan as portal_plan
    b,source,pad,blocked=portal_fixture(tmp_path,locked=True);p=portal_plan(b,source,pad,allow_locked_track_uuids=[blocked])
    with mock.patch.object(guided,'propose',return_value=dict(options=[],checked_candidates=1,all_returned_paths_fully_native_guarded=True,complete=True)):
        result=future.construct(b,p,source=source,refine_maze=True)
    assert result['closed']==1 and not result['nets'][0]['construction']['source_guide_trials'][0]['selected']


@pytest.mark.parametrize('value',[1,'yes',None])
def test_source_guide_pipeline_mode_requires_an_explicit_boolean(tmp_path,value):
    import cec_future_pose_clearance as future
    from test_native_portal_preclear import fixture as portal_fixture,plan as portal_plan
    b,source,pad,blocked=portal_fixture(tmp_path,locked=True);p=portal_plan(b,source,pad,allow_locked_track_uuids=[blocked])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='explicit_future_pose_maze_refinement'):
        future.construct(b,p,source=source,source_guided_detours=value)
    assert before==field._field_snapshot_inventory(b)


def test_native_track_permission_area_cannot_be_bypassed_by_a_clear_hint(tmp_path):
    source,hint,gid,ids,net=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    z=pcbnew.ZONE(b);z.SetIsRuleArea(True);z.SetLayer(pcbnew.F_Cu);z.SetDoNotAllowTracks(True)
    z.Outline().NewOutline()
    for p in [(0,0),(34000000,0),(34000000,34000000),(0,34000000)]:z.Outline().Append(*p)
    b.Add(z);before=field._field_snapshot_inventory(b)
    r=guided.propose(b,[[9000000,16000000],[23000000,16000000]],
        net_code=b.GetNetcodeFromNetname(net),layer=pcbnew.F_Cu,width_nm=200000,clearance_nm=200000)
    assert not r['ok'] and not r['options'] and not r['no_path_proof']
    assert before==field._field_snapshot_inventory(b)
