import pytest
import pcbnew
import cec_fr as fr
import cec_measurement_leaf as leaf
import cec_native_terminal_reservation as future


def fixture(quarter=0, name='/renamed/bus_member'):
    b=pcbnew.BOARD(); b.SetCopperLayerCount(6)
    props=b.GetProperties(); props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'; b.SetProperties(props)
    n=pcbnew.NETINFO_ITEM(b,name); b.Add(n)
    f=pcbnew.FOOTPRINT(b); f.SetReference('arbitrary_owner'); b.Add(f)
    p=pcbnew.PAD(f); p.SetNumber('arbitrary_pin'); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I(800000,400000)); p.SetNet(n); f.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(20000000,20000000)); p.SetOrientationDegrees(quarter*90)
    return b,p


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['/renamed/USB_D_P','neutral_net_alias'])
def test_actual_terminal_excludes_future_barrel_space_on_every_layer(quarter,name):
    b,p=fixture(quarter,name); before=leaf._binding(b)
    g=future.Guard(b,[p.m_Uuid.AsString()])
    for layer in b.GetEnabledLayers().CuStack():
        assert not g((19000000,20000000),(21000000,20000000),200000,int(layer))
        assert g((19000000,21000000),(21000000,21000000),200000,int(layer))
    assert before==leaf._binding(b)
    assert not g.report()['connectivity_credited'] and not g.report()['release_authority']


@pytest.mark.parametrize('fault',['duplicate','missing','unconnected','small_land','no_profile','bad_process','foreign_copper'])
def test_no_unproved_future_seat_reservation(fault):
    b,p=fixture(); ids=[p.m_Uuid.AsString()]; kwargs={}
    if fault=='duplicate':ids*=2
    elif fault=='missing':ids=['not-a-native-pad']
    elif fault=='unconnected':p.SetNetCode(0)
    elif fault=='small_land':p.SetSize(pcbnew.VECTOR2I(200000,200000))
    elif fault=='no_profile':
        props=b.GetProperties(); props['CEC_FAB_PROFILE']=''; b.SetProperties(props)
    elif fault=='bad_process':kwargs={'diameter_mm':.25,'drill_mm':.25}
    elif fault=='foreign_copper':
        n=pcbnew.NETINFO_ITEM(b,'other'); b.Add(n)
        t=pcbnew.PCB_TRACK(b); t.SetNet(n); t.SetLayer(pcbnew.In2_Cu); t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I(19000000,20000000));t.SetEnd(pcbnew.VECTOR2I(21000000,20000000));b.Add(t)
    with pytest.raises(ValueError):future.Guard(b,ids,**kwargs)
