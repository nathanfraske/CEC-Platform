"""Off-grid gap axes are finite proposals, not copper/clearance exceptions."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_lastmile import _board


def fixture(angle):
    b=_board([],edge=(0,0,30,30))
    for name in ('/renamed/control','/unrelated/obstacle'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('OTHER_WALL_'+str(angle))
    for number,x,w in (('1',5.765,11.53),('2',21.1,17.8)):
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(w,2));p.SetPosition(pcbnew.VECTOR2I_MM(x,13))
        p.SetNet(b.FindNet('/unrelated/obstacle'));fp.Add(p)
    b.Add(fp)
    if angle:fp.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    def rotated(x,y):
        dx,dy=fr._nm(x-15),fr._nm(y-15)
        for _ in range(angle//90):dx,dy=dy,-dx
        return pcbnew.VECTOR2I(15000000+dx,15000000+dy)
    s,t=rotated(10,10),rotated(14,16)
    corners=[rotated(x,y) for x,y in ((9,9),(15,17))]
    bounds=(min(p.x for p in corners),min(p.y for p in corners),
        max(p.x for p in corners),max(p.y for p in corners))
    return b,s,t,bounds


def route(b,s,t,bounds,*,channels,width=200000):
    d={}
    def edge(a,c,half):
        return all(bounds[0]<=p.x<=bounds[2] and bounds[1]<=p.y<=bounds[3] for p in (a,c))
    ops=fr._multilayer_maze_lastmile_ops(b,s,t,b.GetNetcodeFromNetname('/renamed/control'),
        (pcbnew.F_Cu,pcbnew.B_Cu),200000,edge,width_for_layer=lambda _:width,
        start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),max_vias=0,
        grid_mm=.5,margin_mm=1,deadline_monotonic=time.monotonic()+2,
        obstacle_channel_axes=channels,diagnostics=d)
    return ops,d


@pytest.mark.parametrize('angle',range(0,360,90))
def test_real_native_gap_missed_by_grid_is_found_without_narrowing_route(angle):
    b,s,t,bounds=fixture(angle);before=field._field_snapshot_inventory(b)
    legacy,old=route(b,s,t,bounds,channels=False)
    ops,d=route(b,s,t,bounds,channels=True)
    assert legacy is None and old['stop']=='bounded_graph_exhausted'
    assert ops and d['stop']=='found' and len(d['native_channel_axes'])==2
    assert all(o[0]=='trk' and o[3]==200000 and o[4]==pcbnew.F_Cu for o in ops)
    assert tuple(ops[0][1])==tuple(s) and tuple(ops[-1][2])==tuple(t)
    for _,a,c,w,lay in ops:
        dx,dy=abs(a.x-c.x),abs(a.y-c.y)
        assert not dx or not dy or dx==dy
        assert fr._tap_foreign_clear(b,a,c,w,lay,200000,
            {b.GetNetcodeFromNetname('/renamed/control')})
    assert before==field._field_snapshot_inventory(b)
    assert not d['release_authority'] and not d['no_path_proof']


def test_axis_hint_does_not_grant_a_wider_route_clearance_or_new_barrel():
    b,s,t,bounds=fixture(0)
    ops,d=route(b,s,t,bounds,channels=True,width=300000)
    assert ops is None and not list(b.GetTracks())
    assert d['stop']=='bounded_graph_exhausted'


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_channel_mode_requires_literal_boolean(bad):
    b,s,t,bounds=fixture(0)
    with pytest.raises(ValueError,match='explicit_multilayer_channel_axes_required'):
        route(b,s,t,bounds,channels=bad)


def test_axes_require_short_explicit_lease():
    b,s,t,_=fixture(0)
    with pytest.raises(ValueError,match='explicit_short_lease'):
        fr._multilayer_maze_lastmile_ops(b,s,t,b.GetNetcodeFromNetname('/renamed/control'),
            (pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda _:200000,obstacle_channel_axes=True)
