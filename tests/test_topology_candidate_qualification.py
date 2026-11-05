"""Bounded topology selection must include qualification and atomic rollback."""
import time
import pcbnew
import pytest
import cec_precision_route as route
from cec_native_copper_snapshot import CopperSnapshot


PAIR=dict(name='synthetic',p='P',n='N',kind='can',width=.25,gap=.2)
PLAN={'edges':[{'a':0,'b':1}]}


def board_fixture():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('P','N','GND','retained'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    return board


def track(board,net='P',y=5):
    item=pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I_MM(3,y))
    item.SetEnd(pcbnew.VECTOR2I_MM(23,y))
    item.SetLayer(pcbnew.F_Cu);item.SetWidth(pcbnew.FromMM(.25))
    item.SetNet(board.FindNet(net));item.SetLocked(True);board.Add(item)
    return item


def via(board,net='GND'):
    item=pcbnew.PCB_VIA(board)
    item.SetPosition(pcbnew.VECTOR2I_MM(2,2))
    item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    item.SetViaType(pcbnew.VIATYPE_THROUGH)
    item.SetWidth(pcbnew.FromMM(.45));item.SetDrill(pcbnew.FromMM(.25))
    item.SetNet(board.FindNet(net));item.SetLocked(True);board.Add(item)
    return item


def signature(board):
    return {item.m_Uuid.AsString(): (
        item.GetClass(),item.GetNetname(),item.GetStart().x,item.GetStart().y,
        item.GetEnd().x,item.GetEnd().y,item.GetWidth(),int(item.GetLayer()),
        item.IsLocked(),
        (item.GetDrillValue(),int(item.GetViaType()),item.TopLayer(),item.BottomLayer())
        if item.GetClass()=='PCB_VIA' else None)
        for item in board.GetTracks()}


def test_scoped_snapshot_restores_exact_native_track_and_via_repeatedly():
    board=board_fixture()
    retained=track(board,'retained',15);retained_via=via(board,'retained')
    parent=[track(board),via(board)]
    expected=signature(board)
    snapshot=CopperSnapshot(board,{item.m_Uuid.AsString() for item in parent})
    for repeat in range(3):
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() in snapshot.uuids:
                item.SetLocked(False);item.SetWidth(pcbnew.FromMM(.8))
                item.SetNet(board.FindNet('N'));board.Remove(item)
        snapshot.restore()
        assert signature(board)==expected
        assert retained.m_Uuid.AsString() in signature(board)
        assert retained_via.m_Uuid.AsString() in signature(board)


def test_snapshot_missing_scope_fails_without_mutating_board():
    board=board_fixture();track(board);before=signature(board)
    with pytest.raises(ValueError,match='complete temporary copper scope'):
        CopperSnapshot(board,{'not-present'})
    assert signature(board)==before


def domains(monkeypatch,direct,layered=None):
    monkeypatch.setattr(route,'_multidrop_tree_alternatives',
        lambda plan,max_trees: [PLAN]*max_trees)
    monkeypatch.setattr(route,'_native_pair_edge_orders',
        lambda plan,max_orders: [(str(i),PLAN['edges']) for i in range(max_orders)])
    monkeypatch.setattr(route,'_route_direct_pair_tree',direct)
    monkeypatch.setattr(route,'_route_layered_multidrop_pair_tree',layered or
        (lambda *a,**kw: {'refused':'synthetic layered failure','remaining_edge_count':1}))


def test_real_coupling_rejection_continues_to_next_native_topology(monkeypatch):
    board=board_fixture();source=track(board,'retained',15)
    parent=via(board);original=signature(board)
    snapshot=CopperSnapshot(board,{parent.m_Uuid.AsString()})
    calls=[];metrics=[]
    def direct(*args,**kwargs):
        assert signature(board)==original
        calls.append(kwargs['deadline'])
        track(board,'P',5);track(board,'N',8 if len(calls)==1 else 5.45)
        return dict(remaining_edge_count=0,refused=None)
    def qualify(rep):
        measured=route._pair_coupling_summary(board,PAIR)
        admission=route._pair_coupling_contract(PAIR,measured,{'P':20.,'N':20.})
        metrics.append(admission['ok'])
        rep['physical_coupling_admission']=admission
        if not admission['ok']:
            # A final gate may normalize/remove parent package copper and
            # emit supporting returns before it discovers a refusal.
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() in snapshot.uuids:board.Remove(item)
            via(board)
            rep['refused']='native measured coupling failed'
        return rep
    domains(monkeypatch,direct)
    deadline=time.monotonic()+30
    result=route._route_multidrop_topologies(board,PAIR,PLAN,deadline=deadline,
        candidate_qualifier=qualify,restore_parent=snapshot.restore)
    assert not result.get('refused')
    assert metrics==[False,True]
    assert len(result['topology_attempts'])==2
    assert all(value<=deadline for value in calls)
    assert signature(board)[source.m_Uuid.AsString()]==original[source.m_Uuid.AsString()]
    assert len(list(board.GetTracks()))==4  # retained + parent + accepted P/N


@pytest.mark.parametrize('failure',['refused','exception','invalid-report'])
def test_rejected_candidates_leave_only_exact_parent_and_source(monkeypatch,failure):
    board=board_fixture();track(board,'retained');parent=via(board)
    original=signature(board);snapshot=CopperSnapshot(board,{parent.m_Uuid.AsString()})
    calls=[]
    def emit(*args,**kwargs):
        assert signature(board)==original
        calls.append(1);track(board);via(board)
        return {'remaining_edge_count':0}
    def qualify(rep):
        for item in list(board.GetTracks()):
            if item.m_Uuid.AsString() in snapshot.uuids:board.Remove(item)
        if failure=='exception':raise RuntimeError('qualification unavailable')
        if failure=='invalid-report':return None
        return dict(rep,refused='final quality refused')
    domains(monkeypatch,emit,emit)
    monkeypatch.setattr(route,'_pair_transaction_detour',lambda *a,**k:{'ok':True})
    monkeypatch.setattr(route.cec_pair_skew,'from_board',lambda *a,**k:{'ok':True})
    kwargs=dict(candidate_qualifier=qualify,restore_parent=snapshot.restore,
                max_native_orders=2,max_trees=3)
    if failure=='refused':
        result=route._route_multidrop_topologies(board,PAIR,PLAN,**kwargs)
        assert result['refused']=='final quality refused'
        assert len(result['topology_attempts'])==5
        assert len(calls)==5
    else:
        with pytest.raises((RuntimeError,TypeError)):
            route._route_multidrop_topologies(board,PAIR,PLAN,**kwargs)
        assert len(calls)==1
    assert signature(board)==original


def test_expired_deadline_does_not_start_a_candidate(monkeypatch):
    board=board_fixture();track(board);before=signature(board)
    def unexpected(*a,**kw):raise AssertionError('budget already exhausted')
    domains(monkeypatch,unexpected,unexpected)
    result=route._route_multidrop_topologies(board,PAIR,PLAN,
        deadline=time.monotonic()-1,candidate_qualifier=unexpected)
    assert result['refused']=='topology search deadline exhausted'
    assert result['topology_attempts']==[]
    assert signature(board)==before


def test_layered_candidate_must_pass_same_qualifier(monkeypatch):
    board=board_fixture();attempts=[]
    def layered(*a,**kw):
        assert not list(board.GetTracks());track(board)
        return {'remaining_edge_count':0}
    def qualify(result):
        attempts.append(1)
        return dict(result,refused='coupling' if len(attempts)==1 else None)
    domains(monkeypatch,lambda *a,**kw:{'refused':'native unavailable'},layered)
    monkeypatch.setattr(route,'_pair_transaction_detour',lambda *a,**k:{'ok':True})
    monkeypatch.setattr(route.cec_pair_skew,'from_board',lambda *a,**k:{'ok':True})
    result=route._route_multidrop_topologies(board,PAIR,PLAN,candidate_qualifier=qualify)
    assert not result.get('refused')
    assert len(attempts)==2
    assert len(list(board.GetTracks()))==1


def test_complete_native_qualification_is_idempotent(tmp_path):
    board=board_fixture()
    for net,y in [('P',5),('N',5.45)]:
        for index,x in enumerate((3,23)):
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(net+str(index));board.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x,y));pad.SetNet(board.FindNet(net));fp.Add(pad)
        track(board,net,y)
    path=tmp_path/'qualified.kicad_pcb'
    pcbnew.SaveBoard(str(path),board,True)
    before=signature(board)
    kwargs=dict(pair_pre_ids=set(),board_path=str(path),pair_avoid=(),endpoint_stations=[])
    first=route._qualify_pair_candidate(board,PAIR,{},**kwargs)
    assert not first.get('refused'),first
    after=signature(board)
    second=route._qualify_pair_candidate(board,PAIR,dict(first),**kwargs)
    assert not second.get('refused'),second
    assert signature(board)==after==before
    for key in ('post_closure_geometry','physical_skew_admission','physical_coupling_admission'):
        assert second[key]==first[key]


def test_loaded_grouped_copper_roundtrip_keeps_native_registry_alive(tmp_path):
    """Born-owned toy proxies alone miss the loaded/borrowed finalization bug."""
    import subprocess
    import sys
    from pathlib import Path
    script=r'''
import gc,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import pcbnew
import cec_precision_route
from cec_native_copper_snapshot import CopperSnapshot
from cec_native_items import discard_items
path=Path(sys.argv[2])/'borrowed.kicad_pcb'
board=pcbnew.CreateEmptyBoard()
group=pcbnew.PCB_GROUP(board);group.SetName('temporary-prefix');board.Add(group)
for i in range(16):
    item=pcbnew.PCB_VIA(board) if i%2 else pcbnew.PCB_TRACK(board)
    if i%2:
        item.SetPosition(pcbnew.VECTOR2I_MM(i,2))
        item.SetDrill(pcbnew.FromMM(.25));item.SetWidth(pcbnew.FromMM(.45))
        item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    else:
        item.SetStart(pcbnew.VECTOR2I_MM(i,2));item.SetEnd(pcbnew.VECTOR2I_MM(i,3))
        item.SetWidth(pcbnew.FromMM(.25))
    board.Add(item);group.AddItem(item)
pcbnew.SaveBoard(str(path),board,True)
capsule=sys.modules['swig_runtime_data4'].type_pointer_capsule
def roundtrip():
    loaded=pcbnew.LoadBoard(str(path))
    ids={t.m_Uuid.AsString() for t in loaded.GetTracks()}
    snap=CopperSnapshot(loaded,ids)
    for _ in range(3):
        snap.restore()
        assert {t.m_Uuid.AsString() for t in loaded.GetTracks()}==ids
        assert {t.m_Uuid.AsString() for g in loaded.Groups() for t in g.GetItems()}==ids
    # The native transaction's ordinary rollback must be just as safe as its
    # snapshot restore when a saved checkpoint supplied the parent copper.
    assert len(cec_precision_route._rollback_created_tracks(loaded,set()))==16
    assert not list(loaded.GetTracks())
    snap.restore()
    assert {t.m_Uuid.AsString() for t in loaded.GetTracks()}==ids
roundtrip();gc.collect()
for _ in range(8):
    before=sys.getrefcount(capsule)
    roundtrip();gc.collect()
    assert sys.getrefcount(capsule)==before,'unbalanced native registry reference'
assert isinstance(pcbnew.LoadBoard(str(path)),pcbnew.BOARD)
'''
    result=subprocess.run([sys.executable,'-c',script,
        str(Path(__file__).resolve().parents[1]/'scripts'),str(tmp_path)],
        text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr[-4000:]
