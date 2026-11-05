"""Existing native local links are observations, not redundant new routes."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
from test_cell_escape_replan import fixture


def native(monkeypatch,quarter=0,back=False):
    b,poses,owner,cap=fixture(monkeypatch,prefix='opaque_'+str(quarter))
    a,z=owner.FindPadByNumber('5'),cap.FindPadByNumber('1')
    t=pcbnew.PCB_TRACK(b);t.SetStart(a.GetPosition());t.SetEnd(z.GetPosition())
    t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(a.GetNet());b.Add(t)
    for fp in b.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:
            fp.SetLayer(pcbnew.B_Cu);layers=pcbnew.LSET()
            for lid in (pcbnew.B_Cu,pcbnew.B_Mask,pcbnew.B_Paste):layers.AddLayer(lid)
            for pad in fp.Pads():pad.SetLayerSet(layers)
    t.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    if back:t.SetLayer(pcbnew.B_Cu)
    def end(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))
    request=dict(kind='local_supply',net='RAIL',a=end(a),b=end(z),width_nm=200000)
    return b,request,t


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_retains_the_actual_short_visible_link_without_adding_material(monkeypatch,quarter,back):
    b,request,t=native(monkeypatch,quarter,back);before=escape.row._source_binding(b)
    proof=escape.retained_local_supply_connection(b,request)
    assert proof and proof['explicit_native_path_mm']==.5 and proof['new_copper']==0
    assert proof['zone_edges_excluded'] and not proof['current_qualified']
    assert escape.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['gap','wrong_pad','wrong_net','wrong_position','wrong_layer','output_role'])
def test_net_labels_or_approximate_ports_never_replace_a_real_bypass_link(monkeypatch,fault):
    b,request,t=native(monkeypatch)
    if fault=='gap':t.SetEnd(t.GetStart()+pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='wrong_pad':request['b']['pad_uuid']='not_source'
    elif fault=='wrong_net':request['net']='OUT'
    elif fault=='wrong_position':request['b']['at_nm'][0]+=1
    elif fault=='wrong_layer':request['a']['layers']=[int(pcbnew.B_Cu)]
    else:b.FindFootprintByReference('opaque_0_owner').FindPadByNumber('5').SetNumber('1')
    assert escape.retained_local_supply_connection(b,request) is None
