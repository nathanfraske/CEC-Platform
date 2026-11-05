"""A real source-track subinterval is not a proximity or fabrication waiver."""
import math
import pcbnew
import pytest
import cec_fab_profile as fab
import cec_field_coupling as field
from test_local_pofv_ownership import fixture


def body_fixture(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,v=fixture();t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    p=next(p for f in b.GetFootprints() for p in f.Pads());p.SetOrientationDegrees(angle)
    layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers);t.SetLayer(layer)
    center=p.GetPosition();c,s=round(math.cos(math.radians(angle))),round(math.sin(math.radians(angle)))
    direction=-1 if mirror else 1
    def at(x,y=0):
        x*=direction
        return pcbnew.VECTOR2I(center.x+c*x-s*y,center.y+s*x+c*y)
    t.SetStart(at(0));t.SetEnd(at(5000000));v.SetPosition(at(625000,1))
    return b,v,t,p


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_native_subinterval_retains_existing_reach_and_needs_no_duplicate_stub(angle,mirror,layer):
    b,v,t,p=body_fixture(angle,mirror,layer);original=field._field_snapshot_inventory(b)
    assert fab.local_pofv_body_contact_matches(p,t,v)
    assert fab.local_pofv_via_decision(b,v)[0] is False
    result=fab.local_pofv_via_decision(b,v,allow_source_track_body=True)
    assert result==(True,'bounded same-layer SMD source-track body contact'),result
    assert field._field_snapshot_inventory(b)==original


@pytest.mark.parametrize('fault',['gap','wrong_layer','wrong_net','no_smd','no_owned_source_endpoint',
    'too_far','partial_pad_overlap','profile_missing','undersized_drill','outside_interval',
    'noncanonical','fractional_projection'])
def test_nearby_pad_or_source_body_never_substitutes_for_required_native_contact_or_process(fault):
    b,v,t,p=body_fixture()
    if fault=='gap':v.Move(pcbnew.VECTOR2I_MM(0,.4))
    elif fault=='wrong_layer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='wrong_net':
        other=pcbnew.NETINFO_ITEM(b,'/OTHER');b.Add(other);t.SetNet(other)
    elif fault=='no_smd':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='no_owned_source_endpoint':t.SetStart(p.GetPosition()+pcbnew.VECTOR2I_MM(-2,0))
    elif fault=='too_far':v.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    elif fault=='partial_pad_overlap':v.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(.4,0))
    elif fault=='profile_missing':
        properties=b.GetProperties();properties['CEC_FAB_PROFILE']='';b.SetProperties(properties)
    elif fault=='undersized_drill':v.SetDrill(1000)
    elif fault=='outside_interval':v.SetPosition(t.GetStart()-pcbnew.VECTOR2I_MM(.625,0))
    elif fault=='noncanonical':t.SetEnd(t.GetStart()+pcbnew.VECTOR2I_MM(5,1))
    else:
        # The projected diagonal point is a half-nanometre, not a rounded
        # construction endpoint. No positional tolerance creates ownership.
        t.SetEnd(t.GetStart()+pcbnew.VECTOR2I(5000000,5000000))
        v.SetPosition(t.GetStart()+pcbnew.VECTOR2I(625000,625001))
    original=field._field_snapshot_inventory(b)
    assert not fab.local_pofv_via_decision(b,v,allow_source_track_body=True)[0]
    assert field._field_snapshot_inventory(b)==original
