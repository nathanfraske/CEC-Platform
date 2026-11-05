"""Native geometry regressions for transaction-owned junction finishing."""
import pcbnew
import pytest
import cec_terminal_overhang as repair


def board():
    result=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(result,'arbitrary-signal');result.Add(net)
    for a,b in [((0,0),(10,0)),((10,0),(10,10)),((10,10),(0,10)),((0,10),(0,0))]:
        edge=pcbnew.PCB_SHAPE(result);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05));result.Add(edge)
    return result,net


def track(b,n,a,z,layer=pcbnew.F_Cu):
    item=pcbnew.PCB_TRACK(b);item.SetNet(n);item.SetLayer(layer)
    item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*z))
    item.SetWidth(pcbnew.FromMM(.2));item.SetLocked(True);b.Add(item)
    return item


def uid(t):return t.m_Uuid.AsString()
def endpoints(t):return repair._point(t.GetStart()),repair._point(t.GetEnd())


def fixture():
    b,n=board()
    middle=track(b,n,(5,2),(5,8))
    branches=[track(b,n,(2,5),(5,5)),track(b,n,(5,8),(8,8))]
    return b,n,middle,branches


def test_trim_to_real_branch_junction_without_deleting_either_edge():
    b,n,middle,branches=fixture();old=[endpoints(t) for t in branches]
    r=repair.trim_generated_overhangs(b,{uid(middle)},nets=[n.GetNetname()])
    assert r['changed_count']==1
    assert endpoints(middle)==((5000000,5000000),(5000000,8000000))
    assert [endpoints(t) for t in branches]==old
    assert len(list(b.GetTracks()))==3 and middle.IsLocked()
    assert not repair.trim_generated_overhangs(b,{uid(middle)},nets=[n.GetNetname()])['changed_count']


def test_never_trim_unowned_or_other_net_copper():
    for scope,nets in [(set(),['arbitrary-signal']), (None,['another-net'])]:
        b,n,middle,_=fixture();old=endpoints(middle)
        r=repair.trim_generated_overhangs(b,{uid(middle)} if scope is None else scope,nets=nets)
        assert not r['changed_count'] and endpoints(middle)==old


def test_off_center_physical_contact_on_tail_is_not_disconnected():
    b,n,middle,_=fixture();old=endpoints(middle)
    track(b,n,(4,3),(4.85,3))
    r=repair.trim_generated_overhangs(b,{uid(middle)},nets=[n.GetNetname()])
    assert not r['changed_count'] and endpoints(middle)==old
    assert r['vetoes'][0]['reason']=='would_lose_physical_contact'


def test_other_layer_crossing_is_not_a_fake_junction():
    b,n=board();middle=track(b,n,(5,2),(5,8))
    track(b,n,(2,5),(5,5),pcbnew.B_Cu);track(b,n,(5,8),(8,8))
    old=endpoints(middle)
    assert not repair.trim_generated_overhangs(b,{uid(middle)},nets=[n.GetNetname()])['changed_count']
    assert endpoints(middle)==old


def test_same_net_plated_pad_contact_vetoes_trim():
    b,n,middle,_=fixture();old=endpoints(middle)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ANY1');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(pcbnew.VECTOR2I_MM(5,3));pad.SetNet(n);fp.Add(pad)
    assert not repair.trim_generated_overhangs(b,{uid(middle)},nets=[n.GetNetname()])['changed_count']
    assert endpoints(middle)==old


def test_owned_acute_corner_keeps_outer_endpoints_width_and_uuid():
    b,n=board();a=track(b,n,(5,6),(5,4));z=track(b,n,(5,4),(4,5.2))
    ids={uid(a),uid(z)}
    r=repair.repair_generated_acute_corners(b,ids,nets=[n.GetNetname()],clearance_mm=.2)
    assert r['changed_count']==1
    assert endpoints(a)[0]==(5000000,6000000) and endpoints(z)[1]==(4000000,5200000)
    assert endpoints(a)[1]==endpoints(z)[0]
    assert {uid(a),uid(z)}==ids and a.IsLocked() and z.IsLocked()
    assert a.GetWidth()==z.GetWidth()==pcbnew.FromMM(.2)


def test_acute_corner_refuses_a_partly_owned_junction():
    b,n=board();a=track(b,n,(5,6),(5,4));z=track(b,n,(5,4),(4,5.2))
    old=[endpoints(a),endpoints(z)]
    assert not repair.repair_generated_acute_corners(b,{uid(a)},nets=[n.GetNetname()],clearance_mm=.2)['changed_count']
    assert [endpoints(a),endpoints(z)]==old


def test_acute_corner_respects_reservations():
    b,n=board();a=track(b,n,(5,6),(5,4));z=track(b,n,(5,4),(4,5.2))
    old=[endpoints(a),endpoints(z)]
    r=repair.repair_generated_acute_corners(b,{uid(a),uid(z)},nets=[n.GetNetname()],clearance_mm=.2,
        avoid=[(3.5,4.5,5.5,6.5,'immutable-lane','F.Cu')])
    assert not r['changed_count'] and [endpoints(a),endpoints(z)]==old


def test_rational_junctions_are_not_rounded_into_gaps():
    assert repair._segment_contacts((0,0),(3,0),(1,-1),(2,2))==[repair.Fraction(4,9)]


@pytest.mark.parametrize('matrix',[(1,0,0,1),(0,-1,1,0),(-1,0,0,-1),(0,1,-1,0),(-1,0,0,1)])
def test_normalization_is_not_tied_to_orientation_or_board_coordinates(matrix):
    a,b,c,d=matrix
    def transform(point):
        x,y=point[0]-5,point[1]-5
        return (5+a*x+b*y,5+c*x+d*y)
    board_,net=board()
    middle=track(board_,net,transform((5,2)),transform((5,8)))
    track(board_,net,transform((2,5)),transform((5,5)))
    track(board_,net,transform((5,8)),transform((8,8)))
    result=repair.trim_generated_overhangs(board_,{uid(middle)},nets=[net.GetNetname()])
    assert result['changed_count']==1
    assert set(endpoints(middle))=={tuple(int(round(v*1e6)) for v in transform(point)) for point in ((5,5),(5,8))}


def test_acute_repair_checks_foreign_copper_not_only_centreline_geometry():
    b,n=board();a=track(b,n,(5,6),(5,4));z=track(b,n,(5,4),(4,5.2))
    foreign=pcbnew.NETINFO_ITEM(b,'different-net');b.Add(foreign)
    # Both shortest candidate paths cross this horizontal obstruction.
    track(b,foreign,(3.5,5.6),(5.5,5.6))
    old=[endpoints(a),endpoints(z)]
    assert not repair.repair_generated_acute_corners(b,{uid(a),uid(z)},nets=[n.GetNetname()],clearance_mm=.2)['changed_count']
    assert [endpoints(a),endpoints(z)]==old


@pytest.mark.parametrize('clearance',[-.1,float('nan'),float('inf')])
def test_invalid_clearance_is_a_policy_error(clearance):
    b,n=board()
    with pytest.raises(ValueError):
        repair.repair_generated_acute_corners(b,set(),nets=[n.GetNetname()],clearance_mm=clearance)


def test_removing_one_corner_cannot_worsen_a_retained_corner():
    def fault(at, angle):
        return dict(type='covered_backtrack', net='synthetic', layer='F.Cu',
                    at_mm=at, track_uuids=['arbitrary-a', 'arbitrary-b'],
                    opening_angle_deg=angle)
    retained = fault([1., 1.], 70.)
    removed = fault([2., 2.], 30.)
    before = dict(issues=[retained, removed])
    assert not repair._craft_improvement(before,
        dict(issues=[fault([1., 1.], 60.)]))
    assert repair._craft_improvement(before, dict(issues=[retained]))
    assert repair._craft_improvement(before,
        dict(issues=[fault([1., 1.], 80.)]))
    assert not repair._craft_improvement(before, before)


def test_non_finite_craft_angle_is_not_an_improvement():
    row = dict(type='acute_backtrack', opening_angle_deg=float('nan'))
    with pytest.raises(ValueError, match='non_finite_craft_angle'):
        repair._craft_improvement(dict(issues=[row]), dict(issues=[]))
