"""Complete circular lands must not inherit mitered polygon-offset artifacts."""
import pytest
from shapely.geometry import Point,Polygon

import cec_slab_pour as slab


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('shift',[(0.,0.),(123.45,-61.2)])
def test_valid_disk_near_small_reentrant_notch_is_not_rejected_by_miter_erosion(turn,shift):
    def point(x,y):
        for _ in range(turn):x,y=-y,x
        return x+shift[0],y+shift[1]
    ring=[point(x,y) for x,y in [(0,0),(3,0),(3,3),(2.9,3),
                               (2.9,2.9),(2.8,2.9),(2.8,3),(0,3)]]
    site=point(2.45,2.45)
    copper=Polygon(ring)
    radius=.9/2+.045
    assert copper.covers(Point(*site)) and copper.boundary.distance(Point(*site))>radius
    assert not copper.buffer(-radius,join_style=2).buffer(1e-9).covers(Point(*site))
    pours=[dict(layer=layer,polygon=ring) for layer in ('FACE','INNER')]
    vias=[dict(field_index=0,x_mm=site[0],y_mm=site[1])]
    slab.require_bridge_landings(pours,vias,[(0,0,'FACE','INNER',1.,0.)])


@pytest.mark.parametrize('defect',['edge','hole','outside','missing_layer','missing_barrel'])
def test_real_landing_losses_still_refuse_at_unchanged_radius_and_margin(defect):
    ring=[(0.,0.),(3.,0.),(3.,3.),(0.,3.)]
    site=(2.45,1.5)
    holes=[]
    if defect=='edge':site=(2.55,1.5)  # Centre/free barrel is not .495 mm of land.
    elif defect=='hole':holes=[[(2.8,1.4),(2.9,1.4),(2.9,1.6),(2.8,1.6)]]
    elif defect=='outside':site=(3.2,1.5)
    pours=[dict(layer=layer,polygon=ring,holes=holes) for layer in ('FACE','INNER')]
    if defect=='missing_layer':pours.pop()
    vias=[] if defect=='missing_barrel' else [dict(field_index=0,x_mm=site[0],y_mm=site[1])]
    with pytest.raises(slab.BridgeFieldRefused):
        slab.require_bridge_landings(pours,vias,[(0,0,'FACE','INNER',1.,0.)])


@pytest.mark.parametrize('diameter,margin',[(0.,.045),(.9,-.01),(float('nan'),.045),(.9,float('inf'))])
def test_invalid_landing_requirements_never_become_permission(diameter,margin):
    with pytest.raises(ValueError):
        slab.require_bridge_landings([],[],[],diameter_mm=diameter,landing_margin_mm=margin)
