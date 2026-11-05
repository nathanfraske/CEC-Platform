"""Old endpoint aliases merge only through actual retained native copper."""
import math,time
import pcbnew
import pytest
import cec_native_component_ports as ports
import cec_measurement_leaf as leaf
from test_field_proposals import track
from test_lastmile import _board


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_distinct_source_endpoints_on_one_barrel_are_one_search_terminal(rotation,mirror,face):
    net='/renamed/%s_%s/SUPPLY'%(rotation,mirror)
    def xy(p):
        x,y=p[0]-10,p[1]-10
        if mirror:x=-x
        a=math.radians(rotation)
        return round(10+x*math.cos(a)-y*math.sin(a),6),round(10+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*xy(p),net) for p in ((5,10),(15,10))]);b.SetCopperLayerCount(6)
    for point in ((5,10),(15,10)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)))
        v.SetWidth(1000000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname(net));b.Add(v)
    # Same-net opposite-face copper at another location does not merge islands.
    track(b,net,xy((8,10)),xy((12,10)),layer=pcbnew.In2_Cu)
    anchors=[list(pcbnew.VECTOR2I_MM(*xy(p))) for p in ((5,10),(5.2,10),(15,10))]
    before=leaf._binding(b)
    rows=ports.boundary_components(b,net,face,anchors,deadline=time.monotonic()+3.)
    assert len(rows)==2 and rows[0]['source_anchors_nm']==anchors[:2]
    assert rows[1]['source_anchors_nm']==anchors[2:]
    assert not set(rows[0]['retained_component_native_uuids'])&set(rows[1]['retained_component_native_uuids'])
    assert before==leaf._binding(b)
    import cec_rated_supply_detour as detour
    group=dict(net=net,layer=b.GetLayerName(face),anchors_nm=anchors,width_nm=200000)
    pairs=detour._planar_cut_ports(b,group,deadline=time.monotonic()+3.)
    assert pairs and pairs[0][0]['at_nm']==anchors[0] and pairs[0][1]['at_nm']==anchors[2]
    assert group['anchors_nm']==anchors and before==leaf._binding(b)


@pytest.mark.parametrize('fault',['off_contact','unknown_net','expired','duplicate','float','boolean','unbounded'])
def test_no_coordinate_alias_or_same_net_name_can_create_a_retained_component(fault):
    b=_board([(5,10,'actual'),(15,10,'actual')]);anchors=[[5000000,10000000],[15000000,10000000]]
    net='actual';deadline=time.monotonic()+3.
    if fault=='off_contact':anchors[0]=[9000000,9000000]
    elif fault=='unknown_net':net='other'
    elif fault=='expired':deadline=time.monotonic()-1.
    elif fault=='duplicate':anchors[1]=anchors[0]
    elif fault=='float':anchors[0][0]=5000000.
    elif fault=='boolean':anchors[0][0]=True
    else:deadline=time.monotonic()+11.
    before=leaf._binding(b)
    with pytest.raises(ValueError):ports.boundary_components(b,net,pcbnew.F_Cu,anchors,deadline=deadline)
    assert before==leaf._binding(b)


def test_a_genuine_three_island_supply_needs_a_tree_not_a_two_terminal_waiver():
    b=_board([(5,10,'actual'),(15,10,'actual'),(10,20,'actual')])
    anchors=[[5000000,10000000],[15000000,10000000],[10000000,20000000]]
    import cec_rated_supply_detour as detour
    group=dict(net='actual',layer='F.Cu',anchors_nm=anchors,width_nm=200000)
    before=leaf._binding(b)
    with pytest.raises(ValueError,match='two_distinct'):
        detour._planar_cut_ports(b,group,deadline=time.monotonic()+3.)
    assert group['anchors_nm']==anchors and before==leaf._binding(b)


@pytest.mark.parametrize('fault',['two_islands','two_faces','unfilled','single_face_control'])
def test_zone_owner_is_not_a_physical_island_or_cross_layer_union(fault):
    b=_board([(5,10,'actual'),(15,10,'actual')]);b.SetCopperLayerCount(6)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu)
    z.SetNetCode(b.GetNetcodeFromNetname('actual'))
    z.SetLocalClearance(200000);z.SetMinThickness(100000)
    boxes=[(3,8,17,12)] if fault!='two_islands' else [(3,8,7,12),(13,8,17,12)]
    for x0,y0,x1,y1 in boxes:
        z.Outline().NewOutline()
        for at in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
            z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
    if fault=='two_faces':
        faces=pcbnew.LSET();faces.AddLayer(pcbnew.F_Cu);faces.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(faces)
    b.Add(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    if fault=='two_islands':assert z.GetFilledPolysList(pcbnew.F_Cu).OutlineCount()==2
    if fault=='unfilled':z.UnFill()
    before=leaf._binding(b);anchors=[[5000000,10000000],[15000000,10000000]]
    if fault=='single_face_control':
        rows=ports.boundary_components(b,'actual',pcbnew.F_Cu,anchors,deadline=time.monotonic()+3.)
        assert len(rows)==1 and rows[0]['source_anchors_nm']==anchors
    else:
        with pytest.raises(ValueError,match='native_cut_boundary_(zone_island|fill)'):
            ports.boundary_components(b,'actual',pcbnew.F_Cu,anchors,deadline=time.monotonic()+3.)
    assert before==leaf._binding(b)
