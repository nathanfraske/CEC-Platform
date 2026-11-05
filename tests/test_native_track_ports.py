import pcbnew
import pytest

import cec_native_track_ports as ports
import cec_certificate_repair as repair
import cec_cell_row_rebuild as row


@pytest.mark.parametrize('end',[(20000000,10000000),(10000000,20000000),(20000000,20000000),(0,20000000)])
def test_exact_interior_ports_preserve_native_line_and_source(end):
    b=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(b,'/renamed');b.Add(net)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(10000000,10000000))
    t.SetEnd(pcbnew.VECTOR2I(*end));t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetNet(net);b.Add(t)
    before=row._source_binding(b)
    values=ports.sites(t,toward_nm=(15000000,13567891),max_sites=8)
    assert 0<len(values)<=8 and len(set(values))==len(values)
    for p in values:
        assert ports.on_centerline(t,p)
        anchor=repair._certificate_endpoint_anchor(b,dict(kind='track_contact',
            uuid=t.m_Uuid.AsString(),x_mm=p[0]/1e6,y_mm=p[1]/1e6),net.GetNetCode(),200000,200000,200000)
        assert tuple(anchor[0])==p and anchor[3].m_Uuid.AsString()==t.m_Uuid.AsString()
    assert row._source_binding(b)==before


def test_unowned_near_track_point_is_not_snapped_to_an_endpoint():
    b=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(b,'unrelated');b.Add(net)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(10,1))
    t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetNet(net);b.Add(t)
    endpoint=dict(kind='track_contact',uuid=t.m_Uuid.AsString(),x_mm=5,y_mm=1.000001)
    assert repair._certificate_endpoint_anchor(b,endpoint,net.GetNetCode(),200000,200000,200000) is None
    assert not ports.on_centerline(t,(11000000,1000000))
    assert not ports.on_centerline(t,(1000000,1000001))


def test_nonoctilinear_zero_length_and_invalid_contact_domains_decline():
    b=pcbnew.BOARD();t=pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(4,2))
    assert ports.sites(t)==[]
    t.SetEnd(t.GetStart());assert ports.sites(t)==[]
    with pytest.raises(ValueError):ports.sites(t,max_sites=17)
    with pytest.raises(ValueError):ports.sites(t,toward_nm=(1.,2))
