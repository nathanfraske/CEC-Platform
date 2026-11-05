"""A 90-degree diagonal V is a right angle, not a free-angle exception."""
import math
import pytest
import pcbnew
import cec_octilinear_corner as corners
import cec_native_scalar_corner_scope as scope
import cec_fr as routing
import cec_route_quality as quality
from cec_local_copper_cell import copper_inventory


@pytest.mark.parametrize('first,second,expected', [
    ((10,0),(0,10),'cardinal'), ((-10,0),(0,-8),'cardinal'),
    ((10,10),(-8,8),'diagonal'), ((-10,-10),(8,-8),'diagonal'),
    ((10,-10),(-8,-8),'diagonal'), ((-10,10),(8,8),'diagonal'),
    ((3,4),(-4,3),None), ((0,0),(0,10),None),
    ((10,0),(-10,0),None), ((10,10),(20,20),None),
    ((10,10),(10,0),None), ((10,0),(10,10),None)])
def test_only_exact_canonical_perpendicular_vectors_are_right_angles(first,second,expected):
    assert corners.kind(first,second)==expected


@pytest.mark.parametrize('extent,maximum,minimum,expected', [
    (1000,200,50,141), (1000,100,100,None), (1000,100,99,None),
    (1000,100,98,70), (80000,200000,50000,None), (90000,200000,50000,36000)])
def test_diagonal_retreat_limits_are_actual_lengths_and_exact_integer_rounding(extent,maximum,minimum,expected):
    result=corners.coordinate_inset((extent,extent),(-extent,extent),maximum_nm=maximum,minimum_nm=minimum)
    assert result==expected
    if result is not None:
        assert minimum*minimum <= 2*result*result <= maximum*maximum
        assert 5*result <= 2*extent


def fixture(angle=0,mirrored=False,layer=pcbnew.F_Cu):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'unrelated_native_control');b.Add(net)
    def at(x,y):
        if mirrored:x=-x
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I_MM(20+x,20+y)
    tracks=[]
    for a,z in (((-4,-4),(0,0)),((0,0),(-4,4))):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(layer);t.SetWidth(200000)
        t.SetStart(at(*a));t.SetEnd(at(*z));b.Add(t);tracks.append(t)
    return b,net,tracks,at


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_diagonal_corner_is_scheduled_and_replaced_by_two_45_degree_bends(angle,mirrored,layer):
    b,net,tracks,at=fixture(angle,mirrored,layer)
    selected=scope.select(b,{net.GetNetname()})
    assert set(selected['scope'])=={t.m_Uuid.AsString() for t in tracks}
    old_ids={t.m_Uuid.AsString() for t in tracks}
    result=routing.chamfer_unlocked_right_angles(b,max_chamfer_mm=.2,min_chamfer_mm=.05)
    assert result['right_angles']==result['chamfered']==1,result
    assert result['detail'][0]['corner_kind']=='diagonal'
    live=list(b.GetTracks());new=[t for t in live if t.m_Uuid.AsString() not in old_ids]
    assert len(live)==3 and len(new)==1
    dx,dy=new[0].GetEnd()-new[0].GetStart()
    assert (dx==0)!=(dy==0)
    assert all(t.GetNetCode()==net.GetNetCode() and t.GetLayer()==layer and t.GetWidth()==200000 for t in live)
    assert all(quality.canonical_heading(t.GetStart(),t.GetEnd(),tolerance_nm=0)['ok'] for t in live)
    # Every remaining local joint opens by 135 degrees, not a new hard V.
    endpoints={}
    for t in live:
        for p in (t.GetStart(),t.GetEnd()):endpoints.setdefault(tuple(p),[]).append(t)
    for point,incident in endpoints.items():
        if len(incident)!=2:continue
        vectors=[]
        for t in incident:
            other=t.GetEnd() if tuple(t.GetStart())==point else t.GetStart()
            vectors.append((other.x-point[0],other.y-point[1]))
        assert sum(a*z for a,z in zip(*vectors))<0


@pytest.mark.parametrize('fault',['locked','sensitive','grouped','side_contact','nearby_zone','free_angle'])
def test_diagonal_extension_retains_existing_ownership_and_contact_refusals(fault):
    b,net,tracks,at=fixture()
    if fault=='locked':tracks[0].SetLocked(True)
    elif fault=='grouped':
        g=pcbnew.PCB_GROUP(b);b.Add(g)
        for t in tracks:g.AddItem(t)
    elif fault=='side_contact':
        f=pcbnew.FOOTPRINT(b);b.Add(f);p=pcbnew.PAD(f);f.Add(p);p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I(20000,20000));p.SetPosition(at(.09,0))
    elif fault=='nearby_zone':
        z=pcbnew.ZONE(b);z.SetNet(net);z.SetLayer(pcbnew.F_Cu)
        z.Outline().NewOutline()
        for x,y in ((-.1,-.1),(.1,-.1),(.1,.1),(-.1,.1)):
            p=at(x,y);z.Outline().Append(p.x,p.y)
        b.Add(z)
    elif fault=='free_angle':tracks[1].SetEnd(at(-4,3))
    before=copper_inventory(b)
    result=routing.chamfer_unlocked_right_angles(b,exclude_nets={net.GetNetname()} if fault=='sensitive' else ())
    assert result['chamfered']==0,result
    assert copper_inventory(b)==before
    if fault in ('side_contact','nearby_zone'):assert result['skipped']['native_contact']==1


@pytest.mark.parametrize('value',[0,-1,True,float('nan')])
def test_invalid_inset_bounds_refuse(value):
    with pytest.raises(ValueError):corners.coordinate_inset((1,1),(-1,1),maximum_nm=value,minimum_nm=1)
