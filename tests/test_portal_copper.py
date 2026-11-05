"""Future return access must not narrow, disconnect or edit unrelated copper."""
import math

import pytest
import cec_portal_copper as engine

pcbnew = pytest.importorskip("pcbnew")


@pytest.mark.parametrize("swap,reverse,offset", [
    (False,False,0), (True,False,0), (False,True,0), (True,True,7.123)])
def test_orthogonal_detours_transform_without_dimension_loss(swap,reverse,offset):
    def transform(p):
        x,y = (p[1],p[0]) if swap else p
        return (x+offset,y+offset)
    start,end = transform((10,2)),transform((10,18))
    if reverse:
        start,end=end,start
    center=transform((10,10))
    paths=engine.detours(start,end,width=2,circles=[(*center,.25)],clearance=.3)
    assert 0<len(paths)<=12
    for path in paths:
        assert path[0]==start and path[-1]==end
        assert len(path)==6  # one envelope; no per-circle staircase
        for a,b in zip(path,path[1:]):
            assert a[0]==b[0] or a[1]==b[1]
            assert engine.point_segment_distance(center,a,b)>=1.55


@pytest.mark.parametrize("kwargs", [
    {"width":0}, {"width":float("nan")}, {"clearance":-1},
    {"max_trials":0}, {"max_trials":1.5}, {"circles":[(2,2,-1)]},
    {"circles":[(2,2)]}])
def test_invalid_geometry_fails_closed(kwargs):
    args=dict(width=1,circles=[(10,10,.2)],clearance=.2)
    args.update(kwargs)
    with pytest.raises(ValueError):
        engine.detours((10,2),(10,18),**args)


def test_detour_budget_and_endpoint_refusal():
    args=dict(width=1,circles=[(10,10,.2)],clearance=.2)
    assert len(engine.detours((10,2),(10,18),max_trials=1,**args))==1
    assert engine.detours((10,10),(10,18),**args)==[]
    assert engine.detours((2,2),(18,18),**args)==[]
    assert engine.detours((2,2),(2,18),**args)==[[(2,2),(2,18)]]


def board_fixture(names=("POWER_ALPHA","RETURN_BETA","OBSTACLE")):
    board=pcbnew.BOARD(); board.SetCopperLayerCount(6)
    for a,b in (((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    nets=[]
    for name in names:
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets.append(net)
    return board,nets


def track(board,net,a,b,width=1,layer=pcbnew.B_Cu):
    item=pcbnew.PCB_TRACK(board);item.SetNet(net)
    item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b))
    item.SetWidth(pcbnew.FromMM(width));item.SetLayer(layer);item.SetLocked(True)
    board.Add(item)
    return item


def portal(net,at=(10,10),layers=None):
    return dict(ref="RENAMED_COMPONENT",pad="changed-pin",net_code=net.GetNetCode(),
                at_mm=at,diameter_mm=.35,layer_ids=layers or [pcbnew.B_Cu])


def snapshot(board):
    return sorted((t.m_Uuid.AsString(),t.GetWidth(),t.GetLayer(),
        t.GetNetCode(),t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.IsLocked())
        for t in board.GetTracks())


@pytest.mark.parametrize("names", [("FEED","RETURN","OTHER"),("XYZ","ABC","DEF")])
def test_native_replacement_keeps_width_lock_layer_contacts_and_unrelated_items(names):
    board,nets=board_fixture(names)
    old=track(board,nets[0],(10,2),(10,18),2)
    before_uid=old.m_Uuid.AsString()
    peers=[track(board,nets[0],(10,2),(13,2)),track(board,nets[0],(10,18),(13,18))]
    peer_ids={t.m_Uuid.AsString() for t in peers}
    obstacle=track(board,nets[2],(3,1),(3,25),1)
    obstacle_before=snapshot(board)
    result=engine.replan_owned_tracks(board,[old],[portal(nets[1])])
    assert result["changed"]==1 and not result["remaining_blocked_portals"]
    assert result["accepted"][0]["retained_contacts"]==2
    after={t.m_Uuid.AsString():t for t in board.GetTracks()}
    assert before_uid not in after
    retained=peer_ids|{obstacle.m_Uuid.AsString()}
    assert [r for r in snapshot(board) if r[0] in retained]==[
        r for r in obstacle_before if r[0] in retained]
    assert all(t.GetWidth()==pcbnew.FromMM(2) and t.IsLocked()
        and t.GetLayer()==pcbnew.B_Cu and t.GetNetCode()==nets[0].GetNetCode()
        for uid,t in after.items() if uid not in retained)


@pytest.mark.parametrize("mode", ["group","mid-contact","blocked","endpoint","diagonal","not-owned"])
def test_refusal_preserves_every_original_native_item(mode):
    board,nets=board_fixture()
    old=track(board,nets[0],(10,2) if mode!="endpoint" else (10,10),
              (10,18) if mode!="diagonal" else (18,18),2)
    if mode=="diagonal":
        at=(14,10)
    else:
        at=(10,10)
    if mode=="group":
        group=pcbnew.PCB_GROUP(board);group.SetName("protected topology")
        board.Add(group);group.AddItem(old)
    if mode=="mid-contact":
        track(board,nets[0],(10,10),(10.1,10),.2)
    if mode=="blocked":
        for x in (8,12):
            track(board,nets[2],(x,1),(x,25),1)
    before=snapshot(board)
    result=engine.replan_owned_tracks(board,[] if mode=="not-owned" else [old],
                                       [portal(nets[1],at)])
    assert result["changed"]==0
    assert snapshot(board)==before
    assert result["remaining_blocked_portals"]


@pytest.mark.parametrize("mode", ["same-net","other-layer"])
def test_nonconflicting_portals_do_not_rewrite_copper(mode):
    board,nets=board_fixture()
    old=track(board,nets[0],(10,2),(10,18),2)
    p=portal(nets[0] if mode=="same-net" else nets[1],
             layers=[pcbnew.F_Cu] if mode=="other-layer" else None)
    before=snapshot(board)
    assert engine.replan_owned_tracks(board,[old],[p])["changed"]==0
    assert before==snapshot(board)


def test_board_netclass_clearance_is_not_lowered_by_default():
    board,nets=board_fixture()
    nc=pcbnew.NETCLASS("large clearance");nc.SetClearance(pcbnew.FromMM(.7))
    nets[0].SetNetClass(nc)
    old=track(board,nets[0],(10,2),(10,18),2)
    result=engine.replan_owned_tracks(board,[old],[portal(nets[1])])
    assert result["clearance_mm"]==.7 and result["changed"]==1
    path=result["accepted"][0]["path_mm"]
    assert all(engine.point_segment_distance((10,10),a,b)>=1+.175+.7
               for a,b in zip(path,path[1:]))


@pytest.mark.parametrize('swap,reverse,offset',[(False,False,0),(True,True,17.3)])
def test_portal_plan_guard_uses_actual_layer_and_foreign_net(swap,reverse,offset):
    def p(x,y): return (y+offset,x+offset) if swap else (x+offset,y+offset)
    a,b=p(2,10),p(18,10)
    if reverse: a,b=b,a
    portal=dict(net='REFERENCE',layer_ids=[6],at_mm=p(10,10),diameter_mm=.35)
    assert engine.segment_portal_conflict(a,b,2.,net='SUPPLY',layer_id=6,
        portals=[portal],clearance_mm=.25) is portal
    assert engine.segment_portal_conflict(a,b,2.,net='SUPPLY',layer_id=8,
        portals=[portal],clearance_mm=.25) is None
    assert engine.segment_portal_conflict(a,b,2.,net='REFERENCE',layer_id=6,
        portals=[portal],clearance_mm=.25) is None


def test_portal_reservations_require_explicit_process_qualification():
    board,_=board_fixture()
    result=engine.required_ground_portals(board)
    assert result["portals"]==[] and result["reason"]=="no_declared_pofv_geometry"


@pytest.mark.parametrize("return_rail", ["GND","SUPPLY"])
def test_source_assigned_portals_preserve_duplicate_pad_instances_and_return_topology(monkeypatch,return_rail):
    import cec_constraints
    board,nets=board_fixture(("SUPPLY","GND","OTHER"))
    props=board.GetProperties();props["CEC_FAB_PROFILE"]="jlcpcb_6l_pofv_signal"
    board.SetProperties(props)
    def fp(ref):
        f=pcbnew.FOOTPRINT(board);f.SetReference(ref);board.Add(f);return f
    def pad(f,pin,net,at):
        p=pcbnew.PAD(f);p.SetNumber(pin);p.SetNet(net)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetPosition(pcbnew.VECTOR2I_MM(*at));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);f.Add(p);return p
    owner=fp("OWNER_RENAMED");assigned={}
    for index,y in enumerate((10,20)):
        supply=pad(owner,str(index+2),nets[0],(10,y))
        pad(owner,"1",nets[1],(10,y+1))  # distinct physical pads, identical number
        cap=fp("BYPASS_"+str(index))
        pad(cap,"1",nets[0],(11.2,y));pad(cap,"2",nets[1],(11.2,y+1))
        req=dict(ref=owner.GetReference(),pin=str(index+2),pad=supply,
                 rail="SUPPLY",return_rail=return_rail)
        assigned[str(index)]={"requirement":req,"cap_ref":cap.GetReference(),"distance_mm":1.2}
    monkeypatch.setattr(cec_constraints,"_device_bypass_assignment",
                        lambda *a,**kw:{"assigned":assigned})
    before=snapshot(board)
    result=engine.required_ground_portals(board)
    assert snapshot(board)==before  # reserves, never silently installs copper
    if return_rail=="GND":
        assert len(result["portals"])==4 and not result["refused"]
        assert len({p["uuid"] for p in result["portals"]})==4
        owner_sites=[p["at_mm"] for p in result["portals"] if p["ref"]=="OWNER_RENAMED"]
        assert sorted(owner_sites)==[[10.,11.],[10.,21.]]
    else:
        assert not result["portals"]  # never rewrite rail-to-rail EMC into GND


@pytest.mark.parametrize("persist", [True,False])
def test_long_narrow_link_is_rejected_and_removed_even_without_grouping(persist):
    import cec_decoupler_cell as cells
    board,nets=board_fixture()
    fp=pcbnew.FOOTPRINT(board);fp.SetReference("SUPPLY_DEVICE");board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber("27");pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(ls);pad.SetNet(nets[0]);fp.Add(pad)
    body=track(board,nets[0],(12.3,10),(15,10),.5,pcbnew.F_Cu)
    bad=track(board,nets[0],(10,10),(12.3,10),.2,pcbnew.F_Cu)
    ok,evidence=cells._admit_link_neckdowns(board,[bad],pcbnew.FromMM(.5),persist_group=persist)
    assert not ok and evidence["rejected"][0]["reason"]=="escape_budget_exceeded"
    assert snapshot(board)[0][0]==body.m_Uuid.AsString() and len(snapshot(board))==1
    assert not list(board.Groups())


@pytest.mark.parametrize("persist", [True,False])
def test_short_narrow_launch_with_full_width_throat_is_qualified(persist):
    import cec_decoupler_cell as cells
    board,nets=board_fixture()
    fp=pcbnew.FOOTPRINT(board);fp.SetReference("OTHER_DEVICE");board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber("99");pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(ls);pad.SetNet(nets[0]);fp.Add(pad)
    body=track(board,nets[0],(10.5,10),(15,10),.5,pcbnew.F_Cu)
    short=track(board,nets[0],(10,10),(10.5,10),.2,pcbnew.F_Cu)
    ok,evidence=cells._admit_link_neckdowns(board,[short,body],pcbnew.FromMM(.5),persist_group=persist)
    assert ok and evidence["qualified"] and not evidence["rejected"]
    assert len(snapshot(board))==2
    assert bool(list(board.Groups())) is persist
