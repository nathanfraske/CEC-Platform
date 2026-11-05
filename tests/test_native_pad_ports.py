import time
import pcbnew
import pytest
from shapely.geometry import Point, Polygon
import cec_native_pad_ports as ports
import cec_native_fill_geometry as native
import cec_native_component_ports as components
import cec_force_current as force
import cec_fr as fr
from test_lastmile import _board


def fixture(quarter=0, shape=pcbnew.PAD_SHAPE_ROUNDRECT):
    b=_board([(10,10,'random_net')],edge=(0,0,30,30))
    p=next(p for fp in b.GetFootprints() for p in fp.Pads())
    p.SetSize(pcbnew.VECTOR2I_MM(1.325,.6));p.SetShape(shape)
    p.SetOrientationDegrees(quarter*90)
    return b,p


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                                  pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL])
def test_points_retain_full_width_contact_in_actual_rotated_native_land(quarter,shape):
    b,p=fixture(quarter,shape)
    if shape==pcbnew.PAD_SHAPE_CIRCLE:p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    rows=ports.sites(p,width_nm=200000,toward_nm=(20000000,15000000))
    assert rows and len(rows)<=8 and tuple(p.GetPosition()) not in rows
    poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,1,pcbnew.ERROR_OUTSIDE,False)
    rings=native.snapshot(poly,time.monotonic()+1,max_vertices=4096,max_polygons=1)[0]
    inset=Polygon(rings[0],rings[1:]).buffer(-102000,quad_segs=64)
    assert all(inset.covers(Point(xy)) for xy in rows)
    assert all(p.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*xy),0) for xy in rows)


def test_component_edges_are_opt_in_exact_native_identity_and_face():
    b,p=fixture();uid=force._uid(p)
    boundary=dict(at_nm=list(p.GetPosition()),layers=[0],native_uuids=[uid])
    kwargs=dict(toward_nm=(20000000,15000000),deadline=time.monotonic()+2)
    assert components.endpoints(b,'random_net',boundary,**kwargs)==[boundary]
    rows=components.endpoints(b,'random_net',boundary,pad_attachment_width_nm=200000,**kwargs)
    assert rows[0]==boundary and len(rows)>1
    assert all(row['native_uuids']==[uid] and row['layers']==[0] for row in rows)


@pytest.mark.parametrize('fault',['hole','tht','offset','custom','wide','expired','empty'])
def test_unowned_or_impossible_access_does_not_produce_attachment(fault):
    b,p=fixture();args=dict(width_nm=200000)
    if fault=='hole':p.SetDrillSize(pcbnew.VECTOR2I_MM(.25,.25))
    elif fault=='tht':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='offset':p.SetOffset(pcbnew.VECTOR2I(10000,0))
    elif fault=='custom':p.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='wide':args['width_nm']=800000
    elif fault=='expired':args['deadline']=time.monotonic()-1
    else:args['max_sites']=0
    assert ports.sites(p,**args)==[]


@pytest.mark.parametrize('value',[None,True,0,.2,-1,20000001])
def test_width_is_exact_finite_authority(value):
    _,p=fixture()
    with pytest.raises(ValueError):ports.sites(p,width_nm=value)


@pytest.mark.parametrize('value',[None,1,'yes',[],{}])
def test_pipeline_policy_is_explicit_not_truthy(value):
    b,_=fixture()
    with pytest.raises(ValueError):fr.synthesize_lastmile(b,native_pad_edge_ports=value)
