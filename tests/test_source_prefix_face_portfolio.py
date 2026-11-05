"""Scheduling mocks are NOT admission; native endpoint material is always real."""
import time
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_native_portal_geometry as geometry
import cec_source_rule_signal_launches as local
import cec_certificate_repair as repair
from cec_native_route_portal import endpoint_layers
from test_existing_local_pofv_pad_rule import case

LAYERS=[int(pcbnew.F_Cu),int(pcbnew.In2_Cu),int(pcbnew.B_Cu)]

def scheduling_fixture(tmp_path,monkeypatch,*,count=1):
    board,source,pad=case(tmp_path)
    other=next(p for f in board.GetFootprints()for p in f.Pads()if p.GetNumber()=='2')
    a,b=list(pad.GetPosition()),list(other.GetPosition())
    # Scheduling-only injection: no electrical/process authority follows.
    # Every listed via is materialized as real copper before endpoint checks.
    choices=[dict(at_nm=[a[0],a[1]-i*750000],layers=LAYERS,
        operations=([('trk',*a,a[0],a[1]-i*750000,200000,pcbnew.F_Cu)]if i else[])
            +[('via',a[0],a[1]-i*750000,200000,300000)],
        proposed_not_retained_native_contact=True)for i in range(count)]
    def propose(board,p,**kwargs):
        return dict(choices=choices if force._uid(p)==force._uid(pad)else[])
    monkeypatch.setattr(local,'propose',propose)
    menus=[[dict(at_nm=a,layers=[int(pcbnew.F_Cu)])],
           [dict(at_nm=b,layers=LAYERS)]]
    return board,source,pad,other,menus

def run(board,pad,other,menus,guard,*,seconds=1.,turn_guard=None):
    deadline=time.monotonic()+seconds
    result,report=geometry._source_local_operations(board,[pad,other],menus,
        net=pad.GetNetname(),width=200000,clearance=200000,layers=LAYERS,bridges=LAYERS[1:],
        deadline=deadline,guard=guard,planar=None,turn_guard=turn_guard)
    return result,report,deadline

@pytest.mark.parametrize('face',[int(pcbnew.B_Cu),int(pcbnew.In2_Cu)])
@pytest.mark.parametrize('reverse',[False,True])
def test_scheduling_f_bias_cannot_starve_real_prefix_face_or_reverse(tmp_path,monkeypatch,face,reverse):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch)
    original=field._field_snapshot_inventory(board);calls=[]
    source_at=tuple(pad.GetPosition())
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        assert code==scratch.GetNetcodeFromNetname(pad.GetNetname())
        assert endpoint_layers(scratch,a,code)&set(al)
        assert endpoint_layers(scratch,b,code)&set(bl)
        calls.append((a,set(al),b,set(bl),kwargs['deadline_monotonic'],id(scratch)))
        if al!={face}or bl!={face}or (a!=source_at)!=reverse:return None
        ops=[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,face)]
        return ops if kwargs['ops_ok'](ops)else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result,report,deadline=run(board,pad,other,menus,lambda ops:True)
    assert result and report['face_strata_share_original_local_lease']
    assert report['both_launch_directions']and report['original_combined_portfolio_preserved']
    assert all(c[4]<=deadline for c in calls)
    assert len({c[5]for c in calls})==1  # exact prefix materialized once
    assert all(row['face_stratified']for row in report['attempts'])
    assert original==field._field_snapshot_inventory(board)

def test_combined_forward_fallback_remains_and_reuses_exact_prefix_scratch(tmp_path,monkeypatch):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch);calls=[]
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        calls.append((al,bl,id(scratch),id(kwargs['foreign_cache']),id(kwargs['planar_guard'])))
        if len(al)==1 and len(bl)==1:return None
        ops=[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,int(pcbnew.F_Cu))]
        return ops if kwargs['ops_ok'](ops)else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result,r,deadline=run(board,pad,other,menus,lambda ops:True)
    assert result and r['attempts'][-1]['face_stratified']is False
    assert r['attempts'][-1]['launch_order']==[0,1]
    assert len({c[2:]for c in calls})==1
    assert all(row['local_original_deadline_monotonic']==deadline and row['deadline_monotonic']<=deadline
        for row in r['attempts'])

@pytest.mark.parametrize('refusal',['full_guard','turn_guard'])
def test_full_prefix_middle_guard_refusal_never_returns_success(tmp_path,monkeypatch,refusal):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch);seen=[]
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        ops=[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,next(iter(al)))]
        assert not kwargs['ops_ok'](ops)
        return ops  # Adversarial worker ignores its callback; caller rechecks.
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    def guard(ops):seen.append(ops);return refusal!='full_guard'
    def turn(ops):seen.append(ops);return False
    result,r,_=run(board,pad,other,menus,guard,
        turn_guard=turn if refusal=='turn_guard'else None)
    assert result is None and seen
    assert all(any(op[0]=='via'for op in ops)and any(op[0]=='trk'for op in ops)for ops in seen)

def test_scratch_netcode_is_independently_resolved(tmp_path,monkeypatch):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch)
    actual=pad.GetNetCode()
    monkeypatch.setattr(board,'GetNetcodeFromNetname',lambda net:actual+1000)
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        assert code==actual==scratch.GetNetcodeFromNetname(pad.GetNetname())
        return None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result,_,_=run(board,pad,other,menus,lambda ops:True)
    assert result is None

def test_mutated_scratch_never_acquires_native_source_authority(tmp_path,monkeypatch):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch)
    loader=pcbnew.LoadBoard
    def changed(path):
        scratch=loader(path);next(iter(scratch.GetTracks())).Move(pcbnew.VECTOR2I(1,0))
        return scratch
    monkeypatch.setattr(pcbnew,'LoadBoard',changed)
    with pytest.raises(ValueError,match='exact_saved_source'):
        run(board,pad,other,menus,lambda ops:True)

def test_expired_original_deadline_cannot_be_reset_for_warm_pass(tmp_path,monkeypatch):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *a,**kw:pytest.fail('expired search invoked'))
    result,r,deadline=run(board,pad,other,menus,lambda ops:True,seconds=-1.)
    assert result is None and not r['attempts']

def test_finite_scheduling_keeps_at_most_sixteen_original_pairs(tmp_path,monkeypatch):
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch,count=20)
    calls=[]
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        calls.append((a,b,al,bl,id(scratch)));return None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result,r,deadline=run(board,pad,other,menus,lambda ops:True,seconds=3.)
    assert result is None
    fallback=[a for a in r['attempts']if not a['face_stratified']]
    warm=[a for a in r['attempts']if a['face_stratified']]
    assert 1<=len(fallback)<=16 and len(warm)<=24
    assert all(a['launch_order']==[0,1]for a in fallback)
    assert all(a['deadline_monotonic']<=deadline for a in r['attempts'])

def test_real_source_rule_prefix_search_and_saved_native_geometry(tmp_path):
    """No scheduling, rule inspector, physical guard or route search mocks."""
    from cec_route_proposal_guard import RouteProposalGuard
    import cec_additive_pair_repair as additive
    import cec_additive_route_receiving as receiving
    board,source,pad=case(tmp_path)
    other=next(p for f in board.GetFootprints()for p in f.Pads()if p.GetNumber()=='2')
    deadline=time.monotonic()+10.
    guard=RouteProposalGuard(board,pad.GetNetname(),board_path=source,
        netclass_resolver=fr._project_netclass_resolver(str(source)),deadline=deadline)
    menus=[[dict(at_nm=list(pad.GetPosition()),layers=[int(pcbnew.F_Cu)])],
        [dict(at_nm=list(other.GetPosition()),layers=LAYERS)]]
    result,report=geometry._source_local_operations(board,[pad,other],menus,
        net=pad.GetNetname(),width=200000,clearance=200000,layers=LAYERS,bridges=LAYERS[1:],
        deadline=deadline,guard=guard,planar=None,turn_guard=None)
    assert result,dict(report=report,guards=guard.details)
    old={force._uid(t)for t in board.GetTracks()}
    repair._lay_ops(board,result,pad.GetNetCode(),lock=False)
    child=force._copy_family(source,tmp_path/'real-prefix-child')
    additive.save_native_additions(child,board,{},old)
    proof=receiving.receive(source,child,timeout_s=10.)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()!=child.read_bytes()

def test_immutable_prefix_setup_is_charged_before_topology_search_slice(tmp_path,monkeypatch):
    """Deterministic scheduling counterexample, not a physical admission mock."""
    from types import SimpleNamespace
    import cec_field_search as field_search
    board,source,pad,other,menus=scheduling_fixture(tmp_path,monkeypatch)
    clock=[100.]
    monkeypatch.setattr(geometry,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    original=field_search.PlanarSearchGuard
    setup=[]
    def expensive(*args,**kwargs):
        value=original(*args,**kwargs)
        clock[0]+=.9;setup.append(.9)
        return value
    monkeypatch.setattr(field_search,'PlanarSearchGuard',expensive)
    searches=[]
    def bridge(scratch,a,al,b,bl,width,code,*args,**kwargs):
        remaining=kwargs['deadline_monotonic']-clock[0]
        searches.append(remaining)
        assert remaining>0,'immutable prefix setup consumed the allocated topology search slice'
        # Spend only a small fraction, never manufacture new lease authority.
        clock[0]+=min(.01,remaining/2)
        return None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    deadline=110.
    result,r=geometry._source_local_operations(board,[pad,other],menus,
        net=pad.GetNetname(),width=200000,clearance=200000,layers=LAYERS,bridges=LAYERS[1:],
        deadline=deadline,guard=lambda ops:False,planar=None,turn_guard=None)
    assert result is None and searches and setup==[.9]
    assert clock[0]>=100.9 and clock[0]<deadline
    assert all(a['local_original_deadline_monotonic']==deadline
        and a['deadline_monotonic']<=deadline for a in r['attempts'])
