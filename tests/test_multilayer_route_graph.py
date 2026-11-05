"""The via-enabled fallback shares canonical geometry and power guards."""
import math
import time

import pcbnew
import pytest

import cec_fr as fr


def board_net():
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, '/renamed-control')
    board.Add(net)
    board.GetDesignSettings().m_MinClearance = 200000
    return board, net


@pytest.mark.parametrize('sx,sy', [(1,1),(-1,1),(1,-1),(-1,-1)])
@pytest.mark.parametrize('reverse_layers', [False,True])
@pytest.mark.parametrize('weight',[1.0,2.5])
@pytest.mark.parametrize('dominance',[False,True])
def test_off_grid_diagonal_then_layer_transition(sx,sy,reverse_layers,weight,dominance,monkeypatch):
    board, net = board_net()
    start = pcbnew.VECTOR2I_MM(11.13,-4.37)
    end = start+pcbnew.VECTOR2I(sx*1000000,sy*1000000)
    first,last = (pcbnew.B_Cu,pcbnew.F_Cu) if reverse_layers else (pcbnew.F_Cu,pcbnew.B_Cu)
    split = 500000
    def local(point):
        return sx*(point.x-start.x),sy*(point.y-start.y)
    def corridor(a,b,_width,_gap,layer,_copper):
        ax,ay=local(a);bx,by=local(b)
        if ax!=ay or bx!=by:return False
        return max(ax,bx)<=split if layer==first else min(ax,bx)>=split
    monkeypatch.setattr(fr,'_foreign_shape_indexes',lambda _b,layer,*a,**k:(layer,[]))
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',corridor)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda _b,p,*a,**k:local(p)==(split,split))
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    diagnostic={}
    ops=fr._multilayer_maze_lastmile_ops(board,start,end,net.GetNetCode(),(first,last),
        200000,lambda *a:True,width_for_layer=lambda _l:200000,
        start_layers=(first,),end_layers=(last,),grid_mm=.5,margin_mm=.5,
        max_vias=1,max_length_nm=1500000,diagnostics=diagnostic,
        heuristic_weight=weight,deadline_monotonic=time.monotonic()+2.,neutral_state_dominance=dominance)
    assert ops is not None
    assert sum(op[0]=='via' for op in ops)==1
    assert {op[4] for op in ops if op[0]=='trk'}=={first,last}
    length=0
    for op in ops:
        if op[0]!='trk':continue
        _,a,b,width,layer=op
        assert abs(a.x-b.x)==abs(a.y-b.y)>0
        assert corridor(a,b,width,200000,layer,[])
        length+=math.hypot(a.x-b.x,a.y-b.y)
    assert length<=1500000
    assert diagnostic['stop']=='found'
    assert not diagnostic['no_path_proof'] and not diagnostic['release_authority']
    assert diagnostic['heuristic_weight']==weight
    assert not diagnostic['shortest_path_qualified']
    assert diagnostic['neutral_state_dominance_active']==dominance


@pytest.mark.parametrize('reserved', [False,True])
def test_future_pour_is_guarded_even_before_native_copper_exists(monkeypatch,reserved):
    board, net=board_net()
    rows=[dict(net='/future-power',layer=layer,x0=.8,y0=-1,x1=1.2,y1=1)
          for layer in ('F.Cu','B.Cu')]
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:rows if reserved else [])
    start,end=pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,0)
    # Actual reservation collision implementation, not a stubbed verdict.
    def edge(a,b,_half):
        return all(0<=p.x<=2000000 and abs(p.y)<=100000 for p in (a,b))
    diagnostic={}
    ops=fr._multilayer_maze_lastmile_ops(board,start,end,net.GetNetCode(),
        (pcbnew.F_Cu,pcbnew.B_Cu),200000,edge,
        width_for_layer=lambda _l:200000,grid_mm=.5,margin_mm=.5,diagnostics=diagnostic)
    assert (ops is None)==reserved
    if reserved:
        assert diagnostic['stop']=='bounded_graph_exhausted'
        assert diagnostic['hop_refusals']['future_power_reservation']>0
        assert len(diagnostic['blocked_hop_samples'])<=8
    else:
        assert diagnostic['stop']=='found'
    assert not diagnostic['no_path_proof']


def test_timeout_is_not_reported_as_a_geometric_failure(monkeypatch):
    board,net=board_net()
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    diagnostic={}
    assert fr._multilayer_maze_lastmile_ops(board,pcbnew.VECTOR2I_MM(0,0),
        pcbnew.VECTOR2I_MM(2,2),net.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,
        lambda *a:True,width_for_layer=lambda _l:200000,
        deadline_monotonic=time.monotonic()-1,diagnostics=diagnostic) is None
    assert diagnostic['stop']=='deadline_exhausted'
    assert diagnostic['expanded_states']==0
    assert not diagnostic['no_path_proof']


def test_exact_guard_can_still_refuse_diagonal_shortcut(monkeypatch):
    board,net=board_net()
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',lambda *a:False)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    diagnostic={}
    assert fr._multilayer_maze_lastmile_ops(board,pcbnew.VECTOR2I_MM(0,0),
        pcbnew.VECTOR2I_MM(1,1),net.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,
        lambda *a:True,width_for_layer=lambda _l:200000,diagnostics=diagnostic) is None
    assert diagnostic['hop_refusals']['foreign_copper_or_hole']>0
    assert diagnostic['stop']=='bounded_graph_exhausted'


@pytest.mark.parametrize('weight',[0.,.9,3.01,True,float('nan'),float('inf')])
def test_unbounded_or_invalid_search_priority_is_rejected(weight):
    b,n=board_net()
    with pytest.raises(ValueError,match='bounded_multilayer_heuristic_weight'):
        fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,2),
            n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda _l:200000,heuristic_weight=weight)


@pytest.mark.parametrize('deadline',[None,float('nan'),float('inf'),True])
def test_weighted_search_requires_an_explicit_bounded_lease(deadline):
    b,n=board_net()
    with pytest.raises(ValueError,match='explicit_short_lease'):
        fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,2),
            n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda _l:200000,heuristic_weight=2.,deadline_monotonic=deadline)


@pytest.mark.parametrize('weight',[1.,2.5])
def test_search_priority_never_waives_native_hop_barrel_or_field_receiving(monkeypatch,weight):
    b,n=board_net()
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',lambda *a:False)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    d={}
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,2),
        n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
        width_for_layer=lambda _l:200000,heuristic_weight=weight,
        deadline_monotonic=time.monotonic()+2.,diagnostics=d,planar_guard=lambda *a:True)
    assert ops is None and d['hop_refusals']['foreign_copper_or_hole']>0
    assert not list(b.GetTracks())


@pytest.mark.parametrize('sx,sy',[(1,1),(-1,1),(1,-1),(-1,-1)])
@pytest.mark.parametrize('capture',[0.,1.])
def test_exact_terminal_capture_connects_off_grid_corner_with_all_native_guards(monkeypatch,sx,sy,capture):
    b,n=board_net();start=pcbnew.VECTOR2I_MM(11.13,-4.37)
    end=start+pcbnew.VECTOR2I(sx*1130000,sy*370000)
    def xy(p):return sx*(p.x-start.x),sy*(p.y-start.y)
    def corridor(a,z,_width,_gap,layer,_copper):
        if layer!=pcbnew.F_Cu:return False
        ax,ay=xy(a);zx,zy=xy(z)
        flat=ay==zy==0 and 0<=min(ax,zx)<=max(ax,zx)<=760000
        diag=ax-ay==zx-zy==760000 and 0<=min(ay,zy)<=max(ay,zy)<=370000
        return flat or diag
    monkeypatch.setattr(fr,'_foreign_shape_indexes',lambda _b,layer,*a,**k:(layer,[]))
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',corridor)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    d={};ops=fr._multilayer_maze_lastmile_ops(b,start,end,n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),
        200000,lambda *a:True,width_for_layer=lambda l:200000,start_layers=(pcbnew.F_Cu,),
        end_layers=(pcbnew.F_Cu,),grid_mm=.5,margin_mm=.5,max_length_nm=1300000,
        terminal_capture_mm=capture,deadline_monotonic=time.monotonic()+2.,diagnostics=d)
    assert bool(ops)==bool(capture)
    if capture:
        assert ops[0][1]==start and ops[-1][2]==end
        assert all(o[0]=='trk' and corridor(o[1],o[2],o[3],200000,o[4],[]) for o in ops)
        assert sum(math.hypot(o[2].x-o[1].x,o[2].y-o[1].y) for o in ops)<=1300000
        assert d['terminal_capture_found'] and d['terminal_capture_trials']>0
    assert not d['no_path_proof'] and not d['release_authority']
    assert not list(b.GetTracks())


@pytest.mark.parametrize('refusal',['edge','copper','field','reservation','length'])
def test_terminal_capture_never_waives_whole_tail_obligations(monkeypatch,refusal):
    b,n=board_net();start=pcbnew.VECTOR2I_MM(0,0);end=pcbnew.VECTOR2I_MM(1.13,.37)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    def corridor(a,z,_width,_gap,layer,_copper):
        if layer!=pcbnew.F_Cu:return False
        flat=a.y==z.y==0 and 0<=min(a.x,z.x)<=max(a.x,z.x)<=760000
        diag=a.x-a.y==z.x-z.y==760000 and 0<=min(a.y,z.y)<=max(a.y,z.y)<=370000
        return (flat or diag) and not (refusal=='copper' and max(a.x,z.x)>700000)
    monkeypatch.setattr(fr,'_foreign_shape_indexes',lambda _b,layer,*a,**k:(layer,[]))
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',corridor)
    rows=[dict(net='/reserved-power',layer='F.Cu',x0=.69,y0=-.1,x1=.73,y1=.1)] if refusal=='reservation' else []
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:rows)
    guard=(lambda a,z,w,l:math.hypot(z.x-a.x,z.y-a.y)<=600000) if refusal=='field' else None
    ops=fr._multilayer_maze_lastmile_ops(b,start,end,n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),
        200000,lambda a,z,h:not(refusal=='edge' and max(a.x,z.x)>700000),
        width_for_layer=lambda l:200000,start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),
        grid_mm=.5,margin_mm=.5,max_length_nm=1250000 if refusal=='length' else 1300000,
        terminal_capture_mm=1.,deadline_monotonic=time.monotonic()+2.,planar_guard=guard)
    assert ops is None and not list(b.GetTracks())


@pytest.mark.parametrize('radius',[-1.,2.01,True,float('nan'),float('inf')])
def test_terminal_capture_is_a_bounded_explicit_option(radius):
    b,n=board_net()
    with pytest.raises(ValueError,match='bounded_multilayer_terminal_capture'):
        fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(1,1),
            n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda l:200000,terminal_capture_mm=radius)


@pytest.mark.parametrize('sx,sy',[(1,1),(-1,1),(1,-1),(-1,-1)])
@pytest.mark.parametrize('vias',[0,2])
def test_dominance_preserves_native_multilayer_reachability_and_distance_labels(monkeypatch,sx,sy,vias):
    b,n=board_net();other=pcbnew.NETINFO_ITEM(b,'opaque-obstacle');b.Add(other)
    origin=pcbnew.VECTOR2I_MM(17.13,-8.37)
    def point(x,y):return origin+pcbnew.VECTOR2I(round(sx*x*1e6),round(sy*y*1e6))
    t=pcbnew.PCB_TRACK(b);t.SetStart(point(1.5,0));t.SetEnd(point(1.5,1.25))
    t.SetWidth(400000);t.SetLayer(pcbnew.F_Cu);t.SetNet(other);b.Add(t)
    def edge(a,z,h):
        return all(0<=sx*(p.x-origin.x)<=3000000 and 0<=sy*(p.y-origin.y)<=2000000 for p in (a,z))
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    answers=[];details=[]
    for enabled in (False,True):
        d={};ops=fr._multilayer_maze_lastmile_ops(b,point(0,0),point(3,0),n.GetNetCode(),
            (pcbnew.F_Cu,pcbnew.B_Cu),200000,edge,width_for_layer=lambda l:200000,
            start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),grid_mm=.5,margin_mm=.5,
            max_vias=vias,max_length_nm=3500000,deadline_monotonic=time.monotonic()+2.,
            neutral_state_dominance=enabled,diagnostics=d)
        answers.append(bool(ops));details.append(d)
        if ops:
            assert sum(o[0]=='via' for o in ops)<=vias
            assert sum(math.dist(tuple(o[1]),tuple(o[2])) for o in ops if o[0]=='trk')<=3500000
            for o in ops:
                if o[0]=='trk':assert fr._tap_foreign_clear(b,o[1],o[2],o[3],o[4],200000,{n.GetNetCode()})
        assert d['stop'] in ('found','bounded_graph_exhausted')
    assert answers==[bool(vias),bool(vias)]
    assert details[1]['dominated_states']>0
    assert len(list(b.GetTracks()))==1


def test_neutral_dominance_is_not_used_for_accumulated_field_run_states(monkeypatch):
    b,n=board_net();d={}
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    ops=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,0),
        n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
        width_for_layer=lambda l:200000,planar_guard=lambda *a:True,
        neutral_state_dominance=True,diagnostics=d,deadline_monotonic=time.monotonic()+2.)
    assert ops and not d['neutral_state_dominance_active'] and d['dominated_states']==0


def test_field_dominance_key_preserves_all_continuation_memory():
    base=(4,5,pcbnew.F_Cu,0,1,2,5,200000)
    key=fr._multilayer_dominance_key(base,field_memory=True)
    more_vias=(*base[:4],3,*base[5:])
    assert key==fr._multilayer_dominance_key(more_vias,field_memory=True)
    # A different heading, run origin or width can change the next accumulated
    # parallel-run decision even though the current XY/layer is identical.
    for index in (0,1,2,3,5,6,7):
        changed=list(base);changed[index]+=1
        assert key!=fr._multilayer_dominance_key(tuple(changed),field_memory=True)


@pytest.mark.parametrize('sx,sy',[(1,1),(-1,1),(1,-1),(-1,-1)])
@pytest.mark.parametrize('vias',[0,2,4])
def test_field_memory_dominance_preserves_bounded_native_and_long_run_refusals(monkeypatch,sx,sy,vias):
    b,n=board_net();other=pcbnew.NETINFO_ITEM(b,'independent-field-obstacle');b.Add(other)
    origin=pcbnew.VECTOR2I_MM(17.13,-8.37)
    def point(x,y):return origin+pcbnew.VECTOR2I(round(sx*x*1e6),round(sy*y*1e6))
    t=pcbnew.PCB_TRACK(b);t.SetStart(point(1.5,0));t.SetEnd(point(1.5,1.25))
    t.SetWidth(400000);t.SetLayer(pcbnew.F_Cu);t.SetNet(other);b.Add(t)
    def edge(a,z,h):
        return all(0<=sx*(p.x-origin.x)<=3000000 and 0<=sy*(p.y-origin.y)<=2000000 for p in (a,z))
    def field_guard(a,z,width,layer):
        # Tiny individual hops pass, but a prolonged straight run on F.Cu
        # does not. The state frontier must retain this future obligation.
        return layer!=pcbnew.F_Cu or math.dist(tuple(a),tuple(z))<=1000000
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    answers=[]
    for enabled in (False,True):
        d={};ops=fr._multilayer_maze_lastmile_ops(b,point(0,0),point(3,0),n.GetNetCode(),
            (pcbnew.F_Cu,pcbnew.B_Cu),200000,edge,width_for_layer=lambda l:200000,
            start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),grid_mm=.5,margin_mm=.5,
            max_vias=vias,max_length_nm=3500000,deadline_monotonic=time.monotonic()+2.,
            planar_guard=field_guard,field_state_dominance=enabled,diagnostics=d)
        answers.append(bool(ops))
        assert d['field_state_dominance_active']==enabled
        assert d['field_state_memory_preserved']==enabled
        assert not d['neutral_state_dominance_active']
        if ops:
            assert sum(o[0]=='via' for o in ops)<=vias
            assert sum(math.dist(tuple(o[1]),tuple(o[2])) for o in ops if o[0]=='trk')<=3500000
            for o in ops:
                if o[0]=='trk':
                    assert field_guard(o[1],o[2],o[3],o[4])
                    assert fr._tap_foreign_clear(b,o[1],o[2],o[3],o[4],200000,{n.GetNetCode()})
        assert d['stop'] in ('found','bounded_graph_exhausted')
    assert answers==[bool(vias),bool(vias)]
    assert len(list(b.GetTracks()))==1


@pytest.mark.parametrize('value',[1,None,'yes'])
def test_field_dominance_requires_explicit_boolean(value):
    b,n=board_net()
    with pytest.raises(ValueError,match='explicit_field_multilayer_dominance'):
        fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,0),
            n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda l:200000,field_state_dominance=value)


def test_field_dominance_requires_bounded_short_lease():
    b,n=board_net()
    for deadline in (None,time.monotonic()+30.):
        with pytest.raises(ValueError,match='field_dominance_requires_explicit_short_lease'):
            fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(2,0),
                n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
                width_for_layer=lambda l:200000,field_state_dominance=True,deadline_monotonic=deadline)
