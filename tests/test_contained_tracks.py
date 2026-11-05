"""Exact thick-stroke containment includes nearly collinear thin branches."""
import pcbnew
import pytest
import cec_fab_repair as repair
from test_junction_polish import board_net,track


@pytest.mark.parametrize('delta',[1,49,999])
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_whole_narrow_capsule_is_native_contained_without_shrinking_wide(delta,rotation):
    b,n=board_net()
    def p(x,y):
        for _ in range(rotation//90):x,y=-y,x
        return (x+30000000,y+30000000)
    wide=track(b,n,p(0,0),p(1300000,delta),400000)
    narrow=track(b,n,p(0,0),p(1000000,0),200000)
    signature=(wide.m_Uuid.AsString(),wide.GetStart(),wide.GetEnd(),wide.GetWidth())
    result=repair.repair_contained_tracks(b)
    assert result['retired']==1,result
    assert result['detail'][0]['native_outward_minus_inward_empty']
    assert not result['detail'][0]['wider_conductor_modified']
    assert list(b.GetTracks())==[wide]
    assert signature==(wide.m_Uuid.AsString(),wide.GetStart(),wide.GetEnd(),wide.GetWidth())
    assert repair.repair_contained_tracks(b)['retired']==0


@pytest.mark.parametrize('case',['equal_width','uncovered_far_end','other_net','other_layer','locked','grouped','deadline'])
def test_missing_coverage_or_authority_preserves_both_capsules(case):
    b,n=board_net();wide=track(b,n,(10000000,10000000),(11300000,10000001),400000)
    t=track(b,n,(10000000,10000000),(11000000,10000000),200000)
    if case=='equal_width':wide.SetWidth(200000)
    if case=='uncovered_far_end':t.SetEnd(pcbnew.VECTOR2I(12000000,10000000))
    if case=='other_net':z=pcbnew.NETINFO_ITEM(b,'other');b.Add(z);t.SetNet(z)
    if case=='other_layer':t.SetLayer(pcbnew.B_Cu)
    if case=='locked':t.SetLocked(True)
    if case=='grouped':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    result=repair.repair_contained_tracks(b,timeout_s=0 if case=='deadline' else 2)
    assert result['retired']==0 and len(list(b.GetTracks()))==2


def test_net_layer_index_and_explicit_scope_bound_unrelated_inventory():
    b,n=board_net();wide=track(b,n,(10000000,10000000),(11300000,10000001),400000)
    t=track(b,n,(10000000,10000000),(11000000,10000000),200000)
    for index in range(300):
        net=pcbnew.NETINFO_ITEM(b,'arbitrary-'+str(index));b.Add(net)
        track(b,net,(20000000,10000000),(21000000,10000000),200000)
    uid=t.m_Uuid.AsString()
    result=repair.repair_contained_tracks(b,track_uuid_scope=[uid])
    assert result['retired']==1 and result['complete']
    assert result['pair_checks']<=2
    assert len(list(b.GetTracks()))==301
