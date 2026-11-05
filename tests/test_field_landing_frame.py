import copy
import pcbnew
import pytest
import cec_field_landing as frame
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


def make_frame_board(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,old=fixture()
    for t in old:b.Remove(t)
    for fp in list(b.GetFootprints()):b.Remove(fp)
    net=old[0].GetNet()
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I_MM(30+x,30+y)
    vs=[]
    for x in (-1.3,0,1.3):
        for y in (-1.3,0,1.3):
            v=pcbnew.PCB_VIA(b);v.SetNet(net);v.SetPosition(at(x,y))
            v.SetWidth(600_000);v.SetDrill(300_000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True);b.Add(v);vs.append(v)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
    p.SetNet(net);p.SetPosition(at(0,0));p.SetSize(pcbnew.VECTOR2I_MM(1,1))
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls)
    z=pcbnew.ZONE(b);z.SetNet(net);z.SetLayer(layer);z.SetZoneName('OWNED_FIELD')
    z.SetAssignedPriority(3);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetMinThickness(100_000);z.SetLocalClearance(200_000);z.Outline().NewOutline()
    for x,y in [(-2,-2.5),(4,-2.5),(4,2.5),(-2,2.5)]:
        v=at(x,y);z.Outline().Append(v.x,v.y)
    b.Add(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,z,vs


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In3_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('style',['square','chamfer45'])
def test_saved_complete_native_barrel_centered_frame(tmp_path,angle,mirror,layer,style):
    b,z,vs=make_frame_board(angle,mirror,layer);before=copper_inventory(b)
    ids=[v.m_Uuid.AsString() for v in vs]
    p=frame.plan(b,z.m_Uuid.AsString(),ids,required_width_nm=3_200_000,style=style)
    assert copper_inventory(b)==before
    e=frame.materialize(b,p);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'saved.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    r=frame.receive(pcbnew.LoadBoard(str(path)),p)
    assert r['ok'] and r['complete'] and r['actual_barrels_unchanged'],r
    assert r['field_shape']['centered'] and r['field_shape']['rotationally_symmetric']
    assert not r['release_authority'] and not r['new_capacity_credited']
    assert not r['original_source_fill_preserved']


@pytest.mark.parametrize('fault',['omit','asymmetric','rehashed_slab','barrel_changed','foreign_corner','unfilled'])
def test_frame_refuses_incomplete_unproved_or_obstructed_inventory(fault):
    b,z,vs=make_frame_board();ids=[v.m_Uuid.AsString() for v in vs]
    if fault=='omit':ids=ids[:-1]
    if fault=='asymmetric':vs[0].SetPosition(vs[0].GetPosition()+pcbnew.VECTOR2I(1,0))
    if fault=='foreign_corner':
        n=pcbnew.NETINFO_ITEM(b,'UNRELATED');b.Add(n)
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
        pad.SetNet(n);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetPosition(pcbnew.VECTOR2I_MM(28.6,28.6))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(ls)
    before=copper_inventory(b)
    if fault in ('omit','asymmetric','foreign_corner'):
        with pytest.raises(owner.Refused):frame.plan(b,z.m_Uuid.AsString(),ids,required_width_nm=3_200_000)
        assert copper_inventory(b)==before;return
    p=frame.plan(b,z.m_Uuid.AsString(),ids,required_width_nm=3_200_000)
    if fault=='rehashed_slab':
        p['polygon_nm'][0][0]-=1_000_000;p.pop('plan_sha256');p['plan_sha256']=owner._digest(p)
        with pytest.raises(owner.Refused):frame.materialize(b,p)
        assert copper_inventory(b)==before;return
    frame.materialize(b,p)
    if fault!='unfilled':b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    if fault=='barrel_changed':vs[0].SetDrill(400_000)
    r=frame.receive(b,p);assert not r['ok'] and not r['release_authority'],r
