"""Direct return locality needs literal copper, not an endpoint graph alias."""
import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_field_coupling as field
from test_local_pofv_body_contact import body_fixture


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_source_track_body_proves_short_return_without_adding_a_duplicate_trace(angle,mirror,layer):
    b,v,t,p=body_fixture(angle,mirror,layer);ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    for item in (v,t,p):item.SetNet(ground)
    original=field._field_snapshot_inventory(b)
    assert cells._existing_return(b,p,1.5) is None
    result=cells._straight_filled_return_mm(b,p,v,include_native_tracks=True)
    assert result==pytest.approx(.625,abs=1e-9)
    result=cells._existing_return(b,p,1.5,allow_native_track_body=True)
    assert result is not None and result[0]==pytest.approx(.625,abs=1e-9)
    assert field._field_snapshot_inventory(b)==original


@pytest.mark.parametrize('fault',['wrong_face','foreign_net','real_gap','missing_track','remote_via'])
def test_proximity_and_a_single_global_net_do_not_bridge_missing_copper(fault):
    b,v,t,p=body_fixture();ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    for item in (v,t,p):item.SetNet(ground)
    if fault=='wrong_face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='foreign_net':
        other=pcbnew.NETINFO_ITEM(b,'/FOREIGN');b.Add(other);t.SetNet(other)
    elif fault=='real_gap':t.SetStart(p.GetPosition()+pcbnew.VECTOR2I_MM(.6,0))
    elif fault=='missing_track':
        from cec_native_items import discard_items
        discard_items(b,[t])
    else:v.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    original=field._field_snapshot_inventory(b)
    assert cells._existing_return(b,p,1.5,allow_native_track_body=True) is None
    assert field._field_snapshot_inventory(b)==original
