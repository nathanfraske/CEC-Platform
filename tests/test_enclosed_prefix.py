"""Near-collinear surgery must expand copper with proof, not round equality."""
import pcbnew
import pytest
import cec_fab_repair as repair
from test_junction_polish import board_net,track


@pytest.mark.parametrize('delta',[1,49,999])
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_guarded_reconstruction_retains_old_tube_width_and_canonicalizes(delta,rotation):
    b,n=board_net()
    def p(x,y):
        for _ in range(rotation//90):x,y=-y,x
        return (x+30000000,y+30000000)
    wide=track(b,n,p(0,0),p(1000000,0),400000)
    t=track(b,n,p(0,0),p(1300000,delta),200000)
    oldwide=(wide.GetStart(),wide.GetEnd(),wide.GetWidth())
    result=repair.repair_enclosed_prefixes(b)
    assert result['reconstructed']==1,result
    assert t.GetWidth()==200000+2*(delta+10)
    assert list(t.GetStart())==list(p(1000000,0))
    assert list(t.GetEnd())==list(p(1300000,0))
    assert result['detail'][0]['old_union_contained']
    assert not result['detail'][0]['exact_union_equivalence_claimed']
    assert oldwide==(wide.GetStart(),wide.GetEnd(),wide.GetWidth())
    assert repair.repair_enclosed_prefixes(b)['reconstructed']==0


@pytest.mark.parametrize('case',['same_width','too_far','other_net','other_layer','locked','grouped','deadline'])
def test_missing_coverage_or_authority_does_not_mutate(case):
    b,n=board_net();w=track(b,n,(10000000,10000000),(11000000,10000000),400000)
    t=track(b,n,(10000000,10000000),(11300000,10000001),200000)
    if case=='same_width':w.SetWidth(200000)
    if case=='too_far':t.SetEnd(pcbnew.VECTOR2I(11300000,10001001))
    if case=='other_net':z=pcbnew.NETINFO_ITEM(b,'other');b.Add(z);t.SetNet(z)
    if case=='other_layer':t.SetLayer(pcbnew.B_Cu)
    if case=='locked':t.SetLocked(True)
    if case=='grouped':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    before=(t.GetStart(),t.GetEnd(),t.GetWidth())
    result=repair.repair_enclosed_prefixes(b,timeout_s=0 if case=='deadline' else 2)
    assert result['reconstructed']==0
    assert before==(t.GetStart(),t.GetEnd(),t.GetWidth())
