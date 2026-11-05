"""Generic exact-copper cleanup and full-width overshoot regressions."""
import math
import os
import sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','scripts'))
import pcbnew
import pytest
import cec_fab_repair as repair

def track(board,net,a,b,width,locked=False):
    t=pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
    t.SetWidth(width);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetLocked(locked)
    board.Add(t);return t

def board_net():
    b=pcbnew.CreateEmptyBoard();n=pcbnew.NETINFO_ITEM(b,'arbitrary_domain')
    b.Add(n);return b,n

@pytest.mark.parametrize('delta',[1,49,999])
def test_near_duplicate_is_not_exact_copper(delta):
    b,n=board_net()
    a=track(b,n,(8000000,10000000),(8000000,15000000),200000)
    z=track(b,n,(8000000+delta,10000000),(8000000+delta,15000000),200000)
    before=[(t.m_Uuid.AsString(),t.GetStart(),t.GetEnd()) for t in (a,z)]
    assert repair.repair_backtracks(b)==0
    assert before==[(t.m_Uuid.AsString(),t.GetStart(),t.GetEnd()) for t in (a,z)]

@pytest.mark.parametrize('delta',[1,49,999])
def test_near_collinear_fork_is_not_union_equivalence(delta):
    b,n=board_net()
    a=track(b,n,(1000000,1000000),(3000000,1000000),200000)
    z=track(b,n,(1000000,1000000),(5000000,1000000+delta),200000)
    end=z.GetStart()
    assert repair.repair_backtracks(b)==0
    assert z.GetStart()==end

def test_exact_different_width_duplicate_keeps_wider_native_copper():
    b,n=board_net()
    small=track(b,n,(8000000,10000000),(8000000,15000000),200000)
    wide=track(b,n,(8000000,10000000),(8000000,15000000),500000)
    uid=wide.m_Uuid.AsString()
    assert repair.repair_backtracks(b)==1
    assert [(t.m_Uuid.AsString(),t.GetWidth()) for t in b.GetTracks()]==[(uid,500000)]

def test_grouped_duplicate_requires_explicit_group_member_authority():
    b,n=board_net()
    a=track(b,n,(8000000,10000000),(8000000,15000000),200000,locked=True)
    z=track(b,n,(8000000,10000000),(8000000,15000000),200000)
    g=pcbnew.PCB_GROUP(b);g.SetName('generic-owned-prefix');b.Add(g);g.AddItem(z)
    assert repair.repair_backtracks(b)==0
    assert repair.repair_backtracks(b,allow_grouped_track_uuids=[z.m_Uuid.AsString()])==1
    assert list(g.GetItems())==[]

@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_rotated_full_width_unanchored_overrun_is_buried_in_trunk(angle,mirror):
    b,n=board_net()
    def pos(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return (int((x+30)*1e6),int((y+30)*1e6))
    branch=track(b,n,pos(5,10),pos(12,10),1200000)
    trunk=track(b,n,pos(10,5),pos(10,15),2000000,locked=True)
    old_trunk=(trunk.GetStart(),trunk.GetEnd(),trunk.GetWidth(),trunk.IsLocked())
    result=repair.repair_junction_overruns(b)
    assert result['trimmed']==1,result
    assert (branch.GetEnd().x,branch.GetEnd().y)==pos(10,10)
    assert branch.GetWidth()==1200000
    assert (trunk.GetStart(),trunk.GetEnd(),trunk.GetWidth(),trunk.IsLocked())==old_trunk
    # Native physical connectivity agrees; no BuildConnectivity/net propagation.
    c=pcbnew.CONNECTIVITY_DATA();c.Add(branch);c.Add(trunk)
    assert trunk.m_Uuid.AsString() in {t.m_Uuid.AsString() for t in c.GetConnectedItems(branch)}
    assert repair.repair_junction_overruns(b)['trimmed']==0

def test_real_pad_at_tail_forbids_retirement():
    b,n=board_net()
    branch=track(b,n,(5000000,10000000),(12000000,10000000),1200000)
    track(b,n,(10000000,5000000),(10000000,15000000),2000000)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('arbitrary_part');b.Add(fp)
    p=pcbnew.PAD(fp);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I(500000,500000))
    p.SetPosition(pcbnew.VECTOR2I(12000000,10000000))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
    p.SetNet(n);fp.Add(p)
    end=branch.GetEnd()
    assert repair.repair_junction_overruns(b)['trimmed']==0
    assert branch.GetEnd()==end

def test_contacting_branch_cannot_be_deleted_as_overshoot():
    b,n=board_net()
    t=track(b,n,(5000000,10000000),(12000000,10000000),1200000)
    track(b,n,(10000000,5000000),(10000000,15000000),2000000)
    track(b,n,(12000000,10000000),(14000000,12000000),250000)
    result=repair.repair_junction_overruns(b)
    assert result['trimmed']==0,result

def test_narrower_receiver_cannot_hide_full_width_end_cap():
    b,n=board_net()
    track(b,n,(5000000,10000000),(12000000,10000000),2000000)
    track(b,n,(10000000,5000000),(10000000,15000000),1200000)
    assert repair.repair_junction_overruns(b)['trimmed']==0

def test_locked_branch_needs_explicit_uuid_authority():
    b,n=board_net()
    t=track(b,n,(5000000,10000000),(12000000,10000000),1200000,locked=True)
    track(b,n,(10000000,5000000),(10000000,15000000),2000000)
    assert repair.repair_junction_overruns(b)['trimmed']==0
    assert repair.repair_junction_overruns(b,allow_locked_track_uuids=[t.m_Uuid.AsString()])['trimmed']==1

@pytest.mark.parametrize('fn',[repair.repair_backtracks,repair.repair_junction_overruns])
def test_expired_deadline_never_mutates(fn):
    b,n=board_net()
    a=track(b,n,(1000000,1000000),(3000000,1000000),500000)
    z=track(b,n,(1000000,1000000),(5000000,1000000),250000)
    before=[(t.m_Uuid.AsString(),t.GetStart(),t.GetEnd()) for t in b.GetTracks()]
    fn(b,timeout_s=0)
    assert before==[(t.m_Uuid.AsString(),t.GetStart(),t.GetEnd()) for t in b.GetTracks()]
