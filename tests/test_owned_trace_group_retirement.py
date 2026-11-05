"""Whole explicit ownership is required; names and partial groups grant nothing."""
import pytest
import cec_swig_guard;cec_swig_guard.pin()
import pcbnew
import cec_collector_reconstruction as collector
from cec_native_items import discard_items

def fixture():
    b=pcbnew.CreateEmptyBoard();n=pcbnew.NETINFO_ITEM(b,'renamed-arbitrary-net');b.Add(n)
    other=pcbnew.NETINFO_ITEM(b,'foreign');b.Add(other)
    g=pcbnew.PCB_GROUP(b);g.SetName('arbitrary-renamed-ownership');b.Add(g)
    tracks=[]
    for i in range(3):
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(n.GetNetCode());t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(200000);t.SetStart(pcbnew.VECTOR2I_MM(i,2));t.SetEnd(pcbnew.VECTOR2I_MM(i+1,2))
        t.SetLocked(True);b.Add(t);g.AddItem(t);tracks.append(t)
    return b,n,other,g,tracks

def request(b,n,g,tracks,**kwargs):
    return collector.owned_trace_group_retirement(b,n.GetNetname(),group_uuid=collector._uid(g),
        track_uuids=[collector._uid(t) for t in tracks],**kwargs)

def test_exact_whole_group_is_resolved_without_mutation_or_qualification():
    b,n,other,g,tracks=fixture();before={collector._uid(t) for t in b.GetTracks()}
    group,items,r=request(b,n,g,tracks)
    assert group.GetName()=='arbitrary-renamed-ownership'
    assert {collector._uid(t) for t in items}==before
    assert before=={collector._uid(t) for t in b.GetTracks()}
    assert r['complete_native_membership_verified'] and r['restoration_required']
    assert all(r[key] is False for key in ('automatic_ripup_authorized','current_qualified','routing_admitted','release_authority'))
    discard_items(b,[*items,group])
    assert not list(b.GetTracks()) and not list(b.Groups())

@pytest.mark.parametrize('case',['partial','duplicate','wrong_net','missing_group','extra_member','nested','barrel'])
def test_incomplete_or_wrong_native_scope_is_refused(case):
    b,n,other,g,tracks=fixture()
    if case=='partial':tracks=tracks[:-1]
    elif case=='duplicate':tracks=[*tracks,tracks[0]]
    elif case=='wrong_net':tracks[0].SetNetCode(other.GetNetCode())
    elif case=='missing_group':
        fake=pcbnew.PCB_GROUP(b);fake.SetName(g.GetName());g=fake
    elif case=='extra_member':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('ANY_OWNER');b.Add(fp);g.AddItem(fp)
    elif case=='nested':
        parent=pcbnew.PCB_GROUP(b);parent.SetName('parent');b.Add(parent);parent.AddItem(g)
    else:
        v=pcbnew.PCB_VIA(b);v.SetNetCode(n.GetNetCode());v.SetPosition(pcbnew.VECTOR2I_MM(2,2))
        v.SetWidth(600000);v.SetDrill(300000);b.Add(v);g.AddItem(v);tracks.append(v)
    before=len(list(b.GetTracks())),len(list(b.Groups()))
    with pytest.raises(ValueError):request(b,n,g,tracks)
    assert before==(len(list(b.GetTracks())),len(list(b.Groups())))

@pytest.mark.parametrize('budget',[0,-1,11,float('nan'),True])
def test_unbounded_or_invalid_budget_is_refused(budget):
    b,n,other,g,tracks=fixture()
    with pytest.raises(ValueError):request(b,n,g,tracks,timeout_s=budget)
