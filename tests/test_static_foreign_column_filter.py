"""Only actual fixed foreign copper can reject a projected column early."""
import pcbnew
import pytest
import cec_force_current as force
import cec_fr as fr
import cec_static_foreign_column_filter as filter
from test_lastmile import _board
from test_field_proposals import track


def board_case(quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for name in ('GND','FOREIGN'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    def point(x,y):
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    moving=pcbnew.FOOTPRINT(b);moving.SetReference('arbitrary_moving_package');b.Add(moving)
    pad=pcbnew.PAD(moving);pad.SetNumber('unknown');pad.SetNet(b.FindNet('FOREIGN'))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.,1.));pad.SetPosition(point(8,8))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers);moving.Add(pad)
    aa,zz=point(11,10),point(15,10)
    edge=track(b,'FOREIGN',[v/1e6 for v in aa],[v/1e6 for v in zz],width=.5,layer=layer)
    return b,moving,pad,edge,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_stationary_native_foreign_track_collisions_are_guard_parity_in_every_frame(quarter,mirror,layer):
    b,moving,pad,edge,point=board_case(quarter,mirror,layer)
    indices=filter.snapshot(b,force._uid(moving),b.GetNetcodeFromNetname('GND'))
    at=point(13,10);r=filter.collision(indices,tuple(at),600000,200000)
    assert r and r['positive_literal_stationary_native_collision'] and r['face']==int(layer)
    assert r['blocker']['uuid']==force._uid(edge) and r['negative_search_filter_only']
    assert not r['construct_or_saved_admission_authority']
    assert not fr._via_spot_clear(b,at,600000,200000,{b.GetNetcodeFromNetname('GND')},
        drill_nm=300000,net_code=b.GetNetcodeFromNetname('GND'))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_omitting_the_moving_package_is_not_a_positive_via_or_own_land_waiver(quarter,mirror):
    b,moving,pad,edge,point=board_case(quarter,mirror)
    indices=filter.snapshot(b,force._uid(moving),b.GetNetcodeFromNetname('GND'))
    assert filter.collision(indices,tuple(pad.GetPosition()),600000,200000) is None
    assert not fr._via_spot_clear(b,pad.GetPosition(),600000,200000,{b.GetNetcodeFromNetname('GND')},
        drill_nm=300000,net_code=b.GetNetcodeFromNetname('GND'))


def test_explicit_multiple_moving_packages_have_no_reference_name_policy():
    b,moving,pad,edge,point=board_case();other=pcbnew.FOOTPRINT(b);other.SetReference('another');b.Add(other)
    r=filter.snapshot(b,[force._uid(moving),force._uid(other)],b.GetNetcodeFromNetname('GND'))
    assert filter.collision(r,tuple(point(13,10)),600000,200000)


@pytest.mark.parametrize('fault',['missing','duplicate','empty','bool_net'])
def test_unbound_source_package_or_untyped_net_cannot_be_a_filter_context(fault):
    b,moving,pad,edge,point=board_case();ids=force._uid(moving);net=b.GetNetcodeFromNetname('GND')
    if fault=='missing':ids='missing'
    elif fault=='duplicate':ids=[ids,ids]
    elif fault=='empty':ids=[]
    else:net=True
    with pytest.raises(ValueError):filter.snapshot(b,ids,net)


@pytest.mark.parametrize('options',[dict(at_nm=(0.,1)),dict(diameter_nm=True),dict(diameter_nm=0),
    dict(clearance_nm=-1),dict(clearance_nm=True)])
def test_untyped_column_geometry_grants_no_admission(options):
    args=dict(indices={},at_nm=(0,1),diameter_nm=300000,clearance_nm=200000);args.update(options)
    with pytest.raises(ValueError):filter.collision(**args)
