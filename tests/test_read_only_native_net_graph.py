"""Unrefilled trial vias never inherit a foreign filled plane's identity."""
import pytest
import pcbnew
import cec_fr as fr
import cec_field_coupling as field


def fixture(name,quarter,kind):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,name);g=pcbnew.NETINFO_ITEM(b,'GND');b.Add(n);b.Add(g)
    def xy(x,y):
        for _ in range(quarter):x,y=50-y,x
        return pcbnew.VECTOR2I(round(x*1e6),round(y*1e6))
    pads=[]
    for x in (20,35):
        f=pcbnew.FOOTPRINT(b);f.SetReference('arbitrary_'+str(x));b.Add(f)
        p=pcbnew.PAD(f);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I(800000,800000));p.SetNet(n)
        f.Add(p);p.SetPosition(xy(x,20));pads.append(p)
    for a,z in ((20,25),(35,30)):
        t=pcbnew.PCB_TRACK(b);t.SetStart(xy(a,20));t.SetEnd(xy(z,20));t.SetWidth(200000)
        t.SetLayer(pcbnew.F_Cu);t.SetNet(n);b.Add(t)
    for x in (25,30):
        v=pcbnew.PCB_VIA(b);v.SetPosition(xy(x,20));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(n);b.Add(v)
    if kind=='foreign_track':
        t=pcbnew.PCB_TRACK(b);t.SetStart(xy(24,20));t.SetEnd(xy(31,20));t.SetWidth(1000000)
        t.SetLayer(pcbnew.B_Cu);t.SetNet(g);b.Add(t)
    else:
        z=pcbnew.ZONE(b);z.SetNet(n if kind=='same_net_plane' else g);z.SetLayer(pcbnew.B_Cu)
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in ((15,15),(40,15),(40,25),(15,25)):poly.Append(xy(x,y).x,xy(x,y).y)
        z.Outline().Append(poly);z.SetFilledPolysList(pcbnew.B_Cu,poly);z.SetIsFilled(True);b.Add(z)
    return b,n,pads


@pytest.mark.parametrize('name',['/renamed/pair_member','arbitrary_load'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('kind',['foreign_track','foreign_plane','same_net_plane'])
def test_native_queries_preserve_authored_nets_and_do_not_borrow_foreign_copper(name,quarter,kind):
    b,n,pads=fixture(name,quarter,kind);before=field._field_snapshot_inventory(b)
    graph=fr._read_only_route_connectivity(b)
    reached={i.m_Uuid.AsString() for i in graph.GetConnectedItems(pads[0])}
    assert (pads[1].m_Uuid.AsString() in reached)==(kind=='same_net_plane')
    assert before==field._field_snapshot_inventory(b)
    assert fr.net_connectivity_component_count(b,n.GetNetCode())==(1 if kind=='same_net_plane' else 2)
    assert before==field._field_snapshot_inventory(b)
    restricted=fr._read_only_route_connectivity(b,{n.GetNetCode()})
    assert reached=={i.m_Uuid.AsString() for i in restricted.GetConnectedItems(pads[0])}


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('foreign',['GND','arbitrary_other_power'])
def test_unattached_trial_barrel_is_not_relabelled_by_stale_foreign_fill(quarter,foreign):
    b,n,pads=fixture('/unrelated/protected_member',quarter,'foreign_plane')
    zone=list(b.Zones())[0]
    if foreign!='GND':
        other=pcbnew.NETINFO_ITEM(b,foreign);b.Add(other);zone.SetNet(other)
    x,y=27,22
    for _ in range(quarter):x,y=50-y,x
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I(x*1000000,y*1000000))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNet(n)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    before=field._field_snapshot_inventory(b)
    graph=fr._read_only_route_connectivity(b)
    assert {i.m_Uuid.AsString() for i in graph.GetConnectedItems(via)}=={via.m_Uuid.AsString()}
    graph.GetConnectedItems(pads[0])
    assert via.GetNetCode()==n.GetNetCode()
    assert before==field._field_snapshot_inventory(b)
