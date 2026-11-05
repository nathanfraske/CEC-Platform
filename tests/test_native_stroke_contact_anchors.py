"""Real native body contacts must not disappear in endpoint-only motion."""
import pcbnew
import pytest
import cec_force_current as force
from root_native_stroke_contact_anchors_20261013 import plan
from test_lastmile import _board
from test_field_proposals import track


def nodes(board):
    result={}
    for item in board.GetTracks():
        faces=([item.GetLayer()] if item.GetClass()=='PCB_TRACK' else
            [l for l in board.GetEnabledLayers().CuStack() if item.IsOnLayer(l)])
        pts=([tuple(item.GetStart()),tuple(item.GetEnd())] if item.GetClass()=='PCB_TRACK'
            else [tuple(item.GetPosition())])
        for layer in faces:
            for p in pts:
                key=(int(item.GetNetCode()),int(layer),p)
                if key not in result:result[key]=len(result)
    return result


@pytest.mark.parametrize('quarter',range(4))
def test_native_interior_pad_and_barrel_contacts_anchor_the_whole_source_body(quarter):
    b=_board([(20,20,'RENAMED_RAIL')],edge=(0,0,40,40))
    t=track(b,'RENAMED_RAIL',(10,20),(30,20));t.SetWidth(1000000)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(20.25,20))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('RENAMED_RAIL'));b.Add(v)
    pivot=pcbnew.VECTOR2I_MM(20,20);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(pivot,angle)
    pad=next(p for f in b.GetFootprints() for p in f.Pads());n=nodes(b)
    assert not pad.HitTest(t.GetStart()) and not pad.HitTest(t.GetEnd())
    proof=plan(b,n,[force._uid(pad)],[])
    endpoints=[n[(t.GetNetCode(),int(t.GetLayer()),tuple(p))] for p in (t.GetStart(),t.GetEnd())]
    assert set(endpoints)<=set(proof['fixed_nodes'])
    assert any(r['kind']=='conservative_native_interior_body_rigid_link' for r in proof['witnesses'])
    assert proof['construction_exclusions_only'] and not proof['contacts_preserved']
    assert not proof['current_qualified'] and not proof['routing_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['different_net','different_layer','bounding_box_only'])
def test_wrong_net_layer_or_uncontacted_native_body_cannot_create_an_anchor(fault):
    b=_board([(15,19 if fault=='bounding_box_only' else 15,'A'),(35,35,'OTHER')],edge=(0,0,40,40))
    t=track(b,'OTHER' if fault=='different_net' else 'A',(10,10),(20,20));t.SetWidth(200000)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()=='A')
    if fault=='different_layer':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(ls)
    proof=plan(b,nodes(b),[force._uid(pad)],[])
    assert not proof['fixed_nodes'] and not proof['required_nodes'] and not proof['rigid_links']


@pytest.mark.parametrize('timeout',[True,0,-1,float('nan'),float('inf'),10.1])
def test_native_contact_inventory_requires_an_explicit_finite_work_bound(timeout):
    b=_board([(20,20,'A')]);track(b,'A',(10,20),(30,20))
    with pytest.raises(ValueError):plan(b,nodes(b),[],[],timeout_s=timeout)
