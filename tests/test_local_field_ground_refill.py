"""Local field owners cannot normalize unrelated ground copper or invent fill."""
import copy,time
import pcbnew
import pytest
import cec_rectilinear_copper as native
import cec_via_field_layout as fields
from test_owned_via_field import field_fixture,plan


def ground_field_fixture(tmp_path):
    b,vs,zs,at=field_fixture();gnd=pcbnew.NETINFO_ITEM(b,'GND');b.Add(gnd)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ARBITRARY_PLANE_ANCHOR');b.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNet(gnd);pad.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I_MM(2,2));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetLayerSet(pcbnew.PAD.PTHMask())
    z=pcbnew.ZONE(b);z.SetNet(gnd);z.SetLayer(pcbnew.In1_Cu)
    z.SetLocalClearance(300000);z.SetMinThickness(250000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.Outline().NewOutline()
    for x,y in [(2,2),(58,2),(58,58),(2,58)]:z.Outline().Append(x*1000000,y*1000000)
    b.Add(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'immutable-source.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    source=pcbnew.LoadBoard(str(path));compiled=pcbnew.LoadBoard(str(path))
    cv=[v for v in compiled.GetTracks() if v.GetClass()=='PCB_VIA']
    cz=[next(v for v in compiled.Zones() if v.m_Uuid.AsString()==old.m_Uuid.AsString()) for old in zs]
    proposal=plan(compiled,cv,cz);fields.materialize_owned_field(compiled,proposal)
    compiled.BuildConnectivity();assert pcbnew.ZONE_FILLER(compiled).Fill(compiled.Zones())
    return source,compiled,proposal,z.m_Uuid.AsString(),path


def test_local_native_refill_preserves_every_unowned_point_and_only_uses_compiled_inside(tmp_path):
    source,compiled,fp,uid,path=ground_field_fixture(tmp_path);encoded=path.read_bytes()
    zone=next(z for z in compiled.Zones() if z.m_Uuid.AsString()==uid)
    # Emulate the globally refilled cache changing an unrelated far feature.
    altered=zone.GetFilledPolysList(pcbnew.In1_Cu).CloneDropTriangulation()
    far=native._poly([(14000000,14000000),(15000000,14000000),(15000000,15000000),(14000000,15000000)])
    altered.BooleanSubtract(far);zone.SetFilledPolysList(pcbnew.In1_Cu,altered)
    proposal=fields.plan_local_ground_refill(source,compiled,[fp],[uid])
    original=next(z for z in source.Zones() if z.m_Uuid.AsString()==uid).GetFilledPolysList(pcbnew.In1_Cu)
    fields.materialize_local_ground_refill(source,compiled,proposal,[fp])
    actual=zone.GetFilledPolysList(pcbnew.In1_Cu);allowed=pcbnew.SHAPE_POLY_SET()
    for window in proposal['ground_rows'][0]['windows_nm']:allowed.BooleanAdd(native._poly(window))
    outa=actual.CloneDropTriangulation();outa.BooleanSubtract(allowed)
    outb=original.CloneDropTriangulation();outb.BooleanSubtract(allowed)
    da=outa.CloneDropTriangulation();da.BooleanSubtract(outb)
    db=outb.CloneDropTriangulation();db.BooleanSubtract(outa)
    assert not da.OutlineCount() and not db.OutlineCount()
    ina=actual.CloneDropTriangulation();ina.BooleanIntersection(allowed)
    inb=altered.CloneDropTriangulation();inb.BooleanIntersection(allowed)
    da=ina.CloneDropTriangulation();da.BooleanSubtract(inb)
    db=inb.CloneDropTriangulation();db.BooleanSubtract(ina)
    assert not da.OutlineCount() and not db.OutlineCount()
    savedpath=tmp_path/'received-local.kicad_pcb';pcbnew.SaveBoard(str(savedpath),compiled)
    received=fields.receive_local_ground_refill(source,pcbnew.LoadBoard(str(savedpath)),proposal)
    assert received['ok'] and not received['invented_copper'] and not received['release_authority']
    assert path.read_bytes()==encoded


@pytest.mark.parametrize('fault',['source_fill','compiled_fill','outline','unfilled','rehash_window'])
def test_local_refill_refuses_stale_sources_and_unowned_window_edits(tmp_path,fault):
    source,compiled,fp,uid,path=ground_field_fixture(tmp_path)
    proposal=fields.plan_local_ground_refill(source,compiled,[fp],[uid])
    sz=next(z for z in source.Zones() if z.m_Uuid.AsString()==uid)
    cz=next(z for z in compiled.Zones() if z.m_Uuid.AsString()==uid)
    if fault=='outline':cz.Outline().Append(30000000,30000000)
    elif fault=='unfilled':cz.UnFill()
    elif fault=='rehash_window':
        proposal['ground_rows'][0]['windows_nm'][0][0][0]-=1
        proposal.pop('plan_sha256');proposal['plan_sha256']=native._digest(proposal)
    else:
        z=sz if fault=='source_fill' else cz
        f=z.GetFilledPolysList(pcbnew.In1_Cu).CloneDropTriangulation()
        f.BooleanSubtract(native._poly([(14000000,14000000),(15000000,14000000),(15000000,15000000),(14000000,15000000)]))
        z.SetFilledPolysList(pcbnew.In1_Cu,f)
    with pytest.raises(native.Refused):fields.materialize_local_ground_refill(source,compiled,proposal,[fp])


def test_saved_local_refill_cannot_hide_even_one_nanometre_copper_loss(tmp_path):
    source,compiled,fp,uid,path=ground_field_fixture(tmp_path)
    proposal=fields.plan_local_ground_refill(source,compiled,[fp],[uid])
    fields.materialize_local_ground_refill(source,compiled,proposal,[fp])
    z=next(z for z in compiled.Zones() if z.m_Uuid.AsString()==uid)
    f=z.GetFilledPolysList(pcbnew.In1_Cu).CloneDropTriangulation()
    f.BooleanSubtract(native._poly([(14000000,14000000),(14000001,14000000),(14000001,14000001),(14000000,14000001)]))
    z.SetFilledPolysList(pcbnew.In1_Cu,f)
    with pytest.raises(native.Refused):fields.receive_local_ground_refill(source,compiled,proposal)
