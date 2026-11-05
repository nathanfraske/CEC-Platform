"""Closed native pad boundaries stay fixed; empty box corners are not metal."""
from types import SimpleNamespace
import pcbnew
import pytest
import cec_native_scalar_corner_scope as scope
import cec_route_corner_contacts as contacts
import cec_fr as routing
from cec_local_copper_cell import copper_inventory
from test_route_corner_contacts import fixture


def land(board,net,at,layer,offset,shape):
    fp=pcbnew.FOOTPRINT(board);board.Add(fp);fp.SetReference('RENAMED_ROUND_LAND')
    p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(shape);p.SetSize(pcbnew.VECTOR2I(700000,700000));p.SetPosition(at(10+offset[0],10+offset[1]))
    if shape==pcbnew.PAD_SHAPE_ROUNDRECT:p.SetRoundRectRadiusRatio(.5)
    layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers)
    return p


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_ROUNDRECT])
def test_empty_native_pad_corner_does_not_hide_a_contact_preserving_45_chamfer(angle,mirror,layer,shape):
    b,net,tracks,at=fixture(angle,mirror,layer);p=land(b,net,at,layer,(-.3,.3),shape);point=at(10,10)
    assert p.GetBoundingBox().Contains(point) and not p.HitTest(point)
    assert not p.GetEffectiveShape(layer).Collide(point,0)
    assert not contacts.native_pad_anchor(p,point,layer_id=layer)
    selected=scope.select(b,{net.GetNetname()},maximum_chamfer_nm=600000)
    assert len(selected['selected'])==1 and selected['inventory_complete']
    before=(p.GetNetname(),tuple(p.GetPosition()),p.GetShape())
    result=routing.chamfer_unlocked_right_angles(b,max_chamfer_mm=.6,min_chamfer_mm=.02)
    assert result['chamfered']==1 and not result['native_contact_refusals'],result
    assert before==(p.GetNetname(),tuple(p.GetPosition()),p.GetShape())
    assert any(t.GetEffectiveShape(layer).Collide(p.GetEffectiveShape(layer),0) for t in b.GetTracks())


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_false_hitbox_launch_never_waives_an_actual_whole_leg_contact(angle,mirror,layer):
    b,net,tracks,at=fixture(angle,mirror,layer);p=land(b,net,at,layer,(.3,-.3),pcbnew.PAD_SHAPE_CIRCLE)
    assert p.GetBoundingBox().Contains(at(10,10)) and not p.HitTest(at(10,10))
    assert not contacts.native_pad_anchor(p,at(10,10),layer_id=layer)
    before=copper_inventory(b)
    result=routing.chamfer_unlocked_right_angles(b,max_chamfer_mm=.6,min_chamfer_mm=.02)
    assert result['chamfered']==0 and result['skipped']['native_contact']==1,result
    assert copper_inventory(b)==before
    assert p.m_Uuid.AsString() in result['native_contact_refusals'][0]['lost_contacts']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_copper_launch_stays_immutable(layer):
    b,net,tracks,at=fixture(layer=layer);p=land(b,net,at,layer,(.1,.1),pcbnew.PAD_SHAPE_CIRCLE)
    assert contacts.native_pad_anchor(p,at(10,10),layer_id=layer)
    before=copper_inventory(b);q=routing.chamfer_unlocked_right_angles(b)
    assert q['chamfered']==0 and q['skipped']['launch']==1 and copper_inventory(b)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_literal_rounded_pad_boundary_is_not_a_false_removable_corner(angle,mirror,layer):
    b,net,tracks,at=fixture(angle,mirror,layer)
    p=land(b,net,at,layer,(-.6625,0),pcbnew.PAD_SHAPE_ROUNDRECT)
    p.SetSize(pcbnew.VECTOR2I(1325000,600000));p.SetRoundRectRadiusRatio(.25)
    p.SetOrientationDegrees(angle)
    point=at(10,10)
    delta=point-p.GetPosition()
    assert delta.x*delta.x+delta.y*delta.y==662500**2
    assert not p.GetEffectiveShape(layer).Collide(point,0)
    assert contacts.native_pad_anchor(p,point,layer_id=layer)
    before=copper_inventory(b)
    q=scope.select(b,{net.GetNetname()},minimum_chamfer_nm=20000)
    assert not q['selected'] and q['skipped']['immutable_launch']==1
    result=routing.chamfer_unlocked_right_angles(b,min_chamfer_mm=.02)
    assert result['chamfered']==0 and result['skipped']['launch']==1 and copper_inventory(b)==before


@pytest.mark.parametrize('fault',['missing_shape','native_error','empty_shape'])
def test_unknown_native_pad_material_remains_a_protected_launch(fault):
    if fault=='missing_shape':pad=SimpleNamespace(IsOnLayer=lambda layer:True)
    elif fault=='native_error':
        def unknown(layer):raise RuntimeError('native shape unavailable')
        pad=SimpleNamespace(IsOnLayer=lambda layer:True,GetEffectiveShape=unknown)
    else:
        pad=SimpleNamespace(IsOnLayer=lambda layer:True,GetEffectiveShape=lambda layer:pcbnew.SHAPE_POLY_SET())
    assert contacts.native_pad_anchor(pad,pcbnew.VECTOR2I(0,0),layer_id=pcbnew.F_Cu)


def test_other_face_hitbox_is_not_copper_on_the_routing_face():
    pad=SimpleNamespace(IsOnLayer=lambda layer:False)
    assert not contacts.native_pad_anchor(pad,pcbnew.VECTOR2I(0,0),layer_id=pcbnew.F_Cu)
