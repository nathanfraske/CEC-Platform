"""Complete native-join guards must participate in bounded path search.

Workers below only order proposals. Real native retained-track tangents and
the owning menu still decide which complete proposal can be emitted.
"""
import copy
import time

import pcbnew
import pytest

import cec_cell_escape_replan as cell
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_component_ports as ports
import cec_native_via_frontier as frontier


def fixture(monkeypatch, *, back=False, quarter=0, kind='source_boundary'):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, '/arbitrary/retained_join'); board.Add(net)
    face = int(pcbnew.B_Cu if back else pcbnew.F_Cu)
    other = int(pcbnew.F_Cu if back else pcbnew.B_Cu)
    def point(x, y):
        x -= 20; y -= 20
        if kind=='local_supply':x *= .15; y *= .15
        for _ in range(quarter):x, y = -y, x
        return (round((30+x)*1e6), round((30+y)*1e6))
    def track(a, b):
        item = pcbnew.PCB_TRACK(board); item.SetNet(net); item.SetLayer(face)
        item.SetWidth(200000); item.SetStart(pcbnew.VECTOR2I(*a))
        item.SetEnd(pcbnew.VECTOR2I(*b)); board.Add(item); return item
    a, b = point(10,10), point(25,10)
    first, last = track(a,point(7,10)), track(b,point(28,10))
    request = dict(kind=kind, net=str(net.GetNetname()), width_nm=200000,
        a=dict(at_nm=list(a),layers=[face],native_uuids=[force._uid(first)]),
        b=dict(at_nm=list(b),layers=[face],native_uuids=[force._uid(last)]))
    if kind=='local_supply':request.update(
        source_required_surface_layer=face,source_maximum_same_surface_path_mm=3.5)
    if kind == 'source_typed_incoming_quiet_output':
        import cec_macro_quiet_output as quiet
        policy = dict(allowed_layers=[face])
        request.update(source_policy=copy.deepcopy(policy),allowed_layers=[face])
        monkeypatch.setattr(quiet,'_policy',lambda *_a:copy.deepcopy(policy))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_a:None)
    monkeypatch.setattr(cells,'_netclass',lambda *_a:dict(width=200000,clearance=200000))
    for name in ('retained_ground_reference_connection','retained_local_supply_connection',
                 'retained_native_boundary_connection'):
        monkeypatch.setattr(cell,name,lambda *_a,**_k:None)
    import cec_retained_ground_component as ground
    monkeypatch.setattr(ground,'observe',lambda *_a,**_k:None)
    monkeypatch.setattr(ports,'endpoints',lambda _b,_n,end,**_k:[copy.deepcopy(end)])
    monkeypatch.setattr(ports,'surface_maze_pairs',lambda *_a,**_k:[])
    monkeypatch.setattr(fr,'_tap_foreign_clear',lambda *_a,**_k:False)
    monkeypatch.setattr(frontier,'sites',lambda *_a,**_k:dict(
        sites_nm=[],drill_mm=.3,diameter_mm=.6))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *_a,**_k:None)
    def ops(points, layer=face, width=200000):
        return [('trk',s,t,width,layer) for s,t in zip(points,points[1:])]
    good = ops([a,point(12,8),point(23,8),b])
    # Stay inside the surface length budget: test the native JOIN guard,
    # rather than accidentally stopping at the independent length check.
    bad = ops([a,point(8,8),point(23,8),b])
    real_guard = ports.plain_endpoint_turn_guard(board,str(net.GetNetname()))
    assert real_guard(good) is True and real_guard(bad) is False
    return board,request,face,other,point,ops,good,bad


def run(board,request,other,*,source=None):
    before = field._field_snapshot_inventory(board)
    detail = {}; emitted = []; deadline = time.monotonic()+2.
    cell._connection_menu(board,request,board_hint='synthetic',deadline=deadline,
        layers=[other],append=emitted.append,detail=detail,source_board=source)
    assert field._field_snapshot_inventory(board) == before
    return emitted,detail,deadline


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_direct_search_continues_after_native_join_refusal(monkeypatch,back,quarter):
    board,request,face,other,point,ops,good,bad = fixture(monkeypatch,back=back,quarter=quarter)
    calls = []
    def bridge(*args,**kwargs):
        accept = kwargs.get('ops_ok'); assert callable(accept)
        # Search callbacks must not emit or mutate the owner's counters.
        assert accept(bad) is False and accept(good) is True
        calls.append(kwargs); return good
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline = run(board,request,other)
    assert emitted == [good] and calls
    assert detail['native_plain_endpoint_turn_refusals'] == 0
    assert all(c['deadline_monotonic'] <= deadline for c in calls)
    assert detail['unchanged_current_contract'] is None


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_direct_worker_cannot_bypass_final_recheck(monkeypatch,back,quarter):
    board,request,face,other,point,ops,good,bad = fixture(monkeypatch,back=back,quarter=quarter)
    def bridge(*args,**kwargs):
        accept = kwargs.get('ops_ok'); assert callable(accept)
        assert accept(bad) is False
        return bad  # Deliberately adversarial worker.
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline = run(board,request,other)
    assert emitted == [] and detail['native_plain_endpoint_turn_refusals'] > 0


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('bad_target',[False,True])
@pytest.mark.parametrize('bad_source',[False,True])
@pytest.mark.parametrize('ignores_guard',[False,True])
def test_frontier_middle_checks_both_outward_prefixes(monkeypatch,back,quarter,bad_target,bad_source,ignores_guard):
    board,request,face,other,point,ops,good,bad = fixture(monkeypatch,back=back,quarter=quarter)
    a,b = tuple(request['a']['at_nm']),tuple(request['b']['at_nm'])
    p,q = point(8 if bad_source else 12,8),point(27 if bad_target else 23,8)
    refused=bad_source or bad_target
    monkeypatch.setattr(frontier,'sites',lambda _b,_n,at,**_k:dict(
        sites_nm=[p if tuple(at)==a else q],drill_mm=.3,diameter_mm=.6))
    def stub(_b,start,end,width,layer,*args,**kwargs):
        return [(tuple(start),tuple(end),width)]
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',stub)
    middle = ops([p,q],layer=other); middle_calls=[]
    def bridge(_b,start,start_faces,end,end_faces,*args,**kwargs):
        if tuple(start)==a:return None  # The later direct portfolio is separate.
        assert tuple(start)==p and tuple(end)==q
        accept=kwargs.get('ops_ok'); assert callable(accept)
        # Bare middle has no retained endpoint join. Only full composition
        # can reject the backward target departure.
        assert ports.plain_endpoint_turn_guard(board,request['net'])(middle) is True
        assert accept(middle) is (not refused)
        middle_calls.append(kwargs)
        return middle if ignores_guard or not refused else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline=run(board,request,other)
    expected=[*ops([a,p]),('via',p,.3,.6),*middle,*ops([b,q]),('via',q,.3,.6)]
    assert emitted == ([] if refused else [expected]) and middle_calls
    assert all(c['deadline_monotonic']<=deadline for c in middle_calls)
    assert detail['native_plain_endpoint_turn_refusals']==int(refused and ignores_guard)


@pytest.mark.parametrize('kind',['local_supply','source_boundary'])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('ignores_guard',[False,True])
def test_surface_search_validates_complete_legs_before_selecting(monkeypatch,kind,back,quarter,ignores_guard):
    board,request,face,other,point,ops,good,bad=fixture(
        monkeypatch,back=back,quarter=quarter,kind=kind)
    # A local supply's finite length guard is retained; use compact tracks.
    if kind!='local_supply':monkeypatch.setattr(ports,'surface_maze_pairs',lambda _b,pairs,**_k:pairs[:1])
    calls=[]
    def legs(*args,**kwargs):
        if len(args)>2 and tuple(args[2]) not in (tuple(request['b']['at_nm']),):return None
        accept=kwargs.get('path_validator'); assert callable(accept)
        bad_legs=[(s,t,w)for _,s,t,w,_ in bad]
        good_legs=[(s,t,w)for _,s,t,w,_ in good]
        assert accept(bad_legs) is False and accept(good_legs) is True
        if kind=='local_supply':
            long_legs=[(s,t,w)for _,s,t,w,_ in ops(
                [point(10,10),point(60,10),point(60,20),point(25,20),point(25,10)])]
            assert accept(long_legs) is False
        calls.append(kwargs); return bad_legs if ignores_guard else good_legs
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',legs)
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *_a,**_k:None)
    emitted,detail,deadline=run(board,request,other)
    assert emitted==([] if ignores_guard else [good]) and calls
    assert detail['native_plain_endpoint_turn_refusals']==int(ignores_guard)
    assert all(c['deadline_monotonic']<=deadline for c in calls)


@pytest.mark.parametrize('reason',['duplicate','wrong_quiet_width','wrong_quiet_face'])
def test_search_guard_keeps_other_complete_proposal_restrictions(monkeypatch,reason):
    quiet=reason.startswith('wrong_quiet')
    board,request,face,other,point,ops,good,bad=fixture(monkeypatch,
        kind='source_typed_incoming_quiet_output' if quiet else 'source_boundary')
    if reason=='duplicate':invalid=[*good,good[-1]]
    elif reason=='wrong_quiet_width':invalid=ops([point(10,10),point(25,10)],width=300000)
    elif reason=='wrong_quiet_face':invalid=ops([point(10,10),point(25,10)],layer=other)
    def bridge(*args,**kwargs):
        accept=kwargs.get('ops_ok'); assert callable(accept)
        assert accept(invalid) is False and accept(good) is True
        return good
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline=run(board,request,other,source=board if quiet else None)
    assert emitted==[good]
    assert detail['nonproductive_connection_walk_refusals']==0
    assert detail['native_plain_endpoint_turn_refusals']==0


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_frontier_rejected_pair_does_not_hide_next_pair_in_same_menu(monkeypatch,back,quarter):
    board,request,face,other,point,ops,good,bad=fixture(monkeypatch,back=back,quarter=quarter)
    a,b=tuple(request['a']['at_nm']),tuple(request['b']['at_nm'])
    p,qbad,qgood=point(12,8),point(26,9),point(25,0)
    monkeypatch.setattr(frontier,'sites',lambda _b,_n,at,**_k:dict(
        sites_nm=[p]if tuple(at)==a else[qbad,qgood],drill_mm=.3,diameter_mm=.6))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda _b,s,t,w,*_a,**_k:[(tuple(s),tuple(t),w)])
    seen=[]
    def bridge(_b,start,_sf,end,_ef,*args,**kwargs):
        if tuple(start)==a:return None
        middle=ops([tuple(start),tuple(end)],layer=other)
        accepted=kwargs['ops_ok'](middle);seen.append((tuple(end),accepted))
        return middle if accepted else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline=run(board,request,other)
    assert seen==[(qbad,False),(qgood,True)]
    assert len(emitted)==1 and emitted[0][-1]==('via',qgood,.3,.6)
    assert detail['native_plain_endpoint_turn_refusals']==0


def test_ordinary_native_search_uses_the_same_pure_complete_guard(monkeypatch):
    board,request,face,other,point,ops,good,bad=fixture(monkeypatch)
    request['source_ordinary_boundary_scope']={'dispatch_fixture_only':True}
    import cec_macro_ordinary_join_obligations as ordinary
    def native_choices(*args,**kwargs):
        assert kwargs['accept'](bad)is False and kwargs['accept'](good)is True
        return dict(choices=[good],dispatch_fixture_only=True)
    monkeypatch.setattr(ordinary,'native_choices',native_choices)
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *_a,**_k:None)
    emitted,detail,deadline=run(board,request,other)
    assert emitted==[good] and detail['native_plain_endpoint_turn_refusals']==0


def test_real_bridge_continues_after_first_complete_candidate_refusal(tmp_path):
    from test_bridge_new_hole_pair import fixture as native_fixture
    from test_bridge_seat_pair_first import solve
    data=native_fixture(tmp_path);before=data[0].read_bytes();seen=[];diagnostics={}
    def normalized(operations):
        return [('trk',tuple(op[1]),tuple(op[2]),op[3],op[4])if op[0]=='trk'
            else('via',tuple(op[1]),op[2],op[3])for op in operations]
    def accept(ops):
        seen.append(normalized(ops))
        return len(seen)>1
    board,proposal=solve(data,policy=True,diagnostics=diagnostics,ops_ok=accept)
    assert proposal and len(seen)>1 and normalized(proposal)==seen[-1]
    assert data[0].read_bytes()==before
    assert not diagnostics['no_path_proof']and not diagnostics['release_authority']
