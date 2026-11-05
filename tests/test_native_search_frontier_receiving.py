"""Actual per-layer copper/clearance attribution stays read-only and bounded."""
import pcbnew
import pytest
from root_native_search_frontier_receiving_20261012 import explain
from test_rectilinear_copper import fixture
from cec_local_copper_cell import copper_inventory


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_actual_foreign_copper_uuid_is_attributed_only_on_its_native_face(layer,angle):
    b,ts=fixture(layer=layer,angle=angle)
    foreign=pcbnew.NETINFO_ITEM(b,'INDEPENDENT_NET');b.Add(foreign)
    t=ts[0].Duplicate();t.SetNet(foreign);b.Add(t)
    before=copper_inventory(b)
    hop=dict(start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),width_nm=t.GetWidth(),
             refusal_stage='native_foreign_shape_guard')
    r=explain(b,ts[0].GetNetname(),int(layer),[hop],clearance_nm=200000)
    hits=r['rows'][0]['actual_native_blockers']
    assert any(h.get('uuid')==t.m_Uuid.AsString() for h in hits)
    assert not r['physical_no_path_proof'] and not r['automatic_ripup_authorized']
    opposite=pcbnew.B_Cu if layer==pcbnew.F_Cu else pcbnew.F_Cu
    other=explain(b,ts[0].GetNetname(),int(opposite),[hop],clearance_nm=200000)
    assert not other['rows'][0]['actual_native_blockers']
    assert before==copper_inventory(b)


@pytest.mark.parametrize('fault',['empty','oversized','bool_width','missing_net'])
def test_unbounded_or_ambiguous_telemetry_is_not_native_evidence(fault):
    b,ts=fixture();hops=[dict(start_nm=[30000000,30000000],end_nm=[31000000,30000000],width_nm=200000)]
    net=ts[0].GetNetname()
    if fault=='empty':hops=[]
    elif fault=='oversized':hops*=129
    elif fault=='bool_width':hops[0]['width_nm']=True
    else:net='not-an-actual-net'
    with pytest.raises(ValueError):explain(b,net,int(pcbnew.F_Cu),hops,clearance_nm=200000)
