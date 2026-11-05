"""A source heading is qualified only if native copper reaches its input."""
import pcbnew
import pytest
from cec_kelvin_departure import audit_pad_departures
from cec_local_copper_cell import copper_inventory
from test_kelvin_departure import native,with_input


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('fault',[None,'missing','wrong_net','near_miss','source_overlap'])
def test_exact_native_through_barrels_bridge_layers_without_inventing_contacts(tmp_path,quarter,fault):
    board,pads=native(tmp_path,0,False,[((10.88,10),(12,10))])
    board.SetCopperLayerCount(6);net=board.FindNet('ARBITRARY')
    for layer,a,z in [(pcbnew.In2_Cu,(12,10),(14,10)),(pcbnew.F_Cu,(14,10),(14,13))]:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(250000);t.SetLayer(layer);t.SetNet(net);board.Add(t)
    target=with_input(board,14,13);vias=[]
    positions=[(12,10),(14,10)]+([(10.9,10)] if fault=='source_overlap' else [])
    for i,at in enumerate(positions):
        if fault=='missing' and i==0:continue
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(*( (12.5,10) if fault=='near_miss' and i==0 else at)))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net);board.Add(v);vias.append(v)
        if fault=='wrong_net' and i==0:v.SetNetCode(0)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    original=copper_inventory(board)
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),
        [t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'],target_pads=[target],connectivity_vias=vias)
    assert result['ok']==(fault is None),result
    if fault is None:
        assert result['departures'][0]['reachable_input_pad_uuids']==[target.m_Uuid.AsString()]
        assert set(v.m_Uuid.AsString() for v in vias)<=set(result['departures'][0]['input_contact_paths'][target.m_Uuid.AsString()])
    assert copper_inventory(board)==original
