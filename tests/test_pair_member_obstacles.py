"""Native pair-member ownership is not a foreign-envelope exemption."""
import math
import time

import pcbnew as pcb
import pytest

import cec_field_coupling as field
import cec_precision_route as route
from cec_pair_member_obstacles import MemberObstacles


def fixture(turn=0):
    b = pcb.CreateEmptyBoard()
    b.SetCopperLayerCount(6)
    nets = []
    for name in ('arbitrary_positive', 'arbitrary_negative'):
        n = pcb.NETINFO_ITEM(b, name); b.Add(n); nets.append(n)
    for a, z in (((0,0),(40,0)),((40,0),(40,40)),
                 ((40,40),(0,40)),((0,40),(0,0))):
        e = pcb.PCB_SHAPE(b); e.SetShape(pcb.SHAPE_T_SEGMENT)
        e.SetStart(pcb.VECTOR2I_MM(*a)); e.SetEnd(pcb.VECTOR2I_MM(*z))
        e.SetLayer(pcb.Edge_Cuts); b.Add(e)
    def xy(p):
        x, y = p
        for _ in range(turn): x, y = -y, x
        return x+20, y+20
    return b, nets, xy


def obstacle(b, net, xy, kind, layer):
    if kind in ('smd', 'pth'):
        fp = pcb.FOOTPRINT(b); fp.SetReference('UNSPECIFIED'); b.Add(fp)
        pad = pcb.PAD(fp); fp.Add(pad); pad.SetNumber('1'); pad.SetNet(net)
        pad.SetPosition(pcb.VECTOR2I_MM(*xy((0, 0))))
        pad.SetShape(pcb.PAD_SHAPE_CIRCLE); pad.SetSize(pcb.VECTOR2I_MM(1,1))
        layers = pcb.LSET()
        if kind == 'pth':
            pad.SetAttribute(pcb.PAD_ATTRIB_PTH); pad.SetDrillSize(pcb.VECTOR2I_MM(.5,.5))
            for face in b.GetEnabledLayers().CuStack(): layers.AddLayer(face)
        else:
            pad.SetAttribute(pcb.PAD_ATTRIB_SMD); layers.AddLayer(layer)
        pad.SetLayerSet(layers); return pad
    if kind == 'via':
        t = pcb.PCB_VIA(b); t.SetViaType(pcb.VIATYPE_THROUGH)
        t.SetLayerPair(pcb.F_Cu, pcb.B_Cu); t.SetPosition(pcb.VECTOR2I_MM(*xy((0,0))))
        t.SetWidth(pcb.FromMM(1)); t.SetDrill(pcb.FromMM(.5))
    elif kind == 'track':
        t = pcb.PCB_TRACK(b); t.SetLayer(layer)
        t.SetStart(pcb.VECTOR2I_MM(*xy((0,-1)))); t.SetEnd(pcb.VECTOR2I_MM(*xy((0,1))))
        t.SetWidth(pcb.FromMM(.3))
    else: raise AssertionError(kind)
    t.SetNet(net); b.Add(t); return t


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('kind',('smd','pth','via','track'))
@pytest.mark.parametrize('layer',(pcb.F_Cu,pcb.In2_Cu))
def test_native_partner_collision_but_same_member_reuse(turn,kind,layer):
    b, nets, xy = fixture(turn)
    item = obstacle(b,nets[1],xy,kind,layer)
    before = field._field_snapshot_inventory(b)
    guard = MemberObstacles(b,layer,tuple(int(n.GetNetCode()) for n in nets))
    a, z = xy((-2,0)), xy((2,0))
    assert not guard.clear('p',a,z,.2,.2)
    assert guard.clear('n',a,z,.2,.2)
    detail = guard.paths([a,z],[xy((-2,3)),xy((2,3))],.2,.2)
    assert detail['ok'] is False
    assert detail['issues'][0]['blockers'][0]['uuid'] == item.m_Uuid.AsString()
    assert field._field_snapshot_inventory(b) == before


@pytest.mark.parametrize('turn',range(4))
def test_native_clearance_rejects_near_miss_and_accepts_real_margin(turn):
    b, nets, xy = fixture(turn)
    obstacle(b,nets[1],xy,'via',pcb.F_Cu)
    guard = MemberObstacles(b,pcb.F_Cu,tuple(int(n.GetNetCode()) for n in nets))
    assert not guard.clear('p',xy((-2,.79999)),xy((2,.79999)),.2,.2)
    assert guard.clear('p',xy((-2,.80001)),xy((2,.80001)),.2,.2)


@pytest.mark.parametrize('turn',range(4))
def test_existing_smd_copper_not_invented_on_other_layer(turn):
    b, nets, xy = fixture(turn)
    obstacle(b,nets[1],xy,'smd',pcb.F_Cu)
    guard = MemberObstacles(b,pcb.In2_Cu,tuple(int(n.GetNetCode()) for n in nets))
    assert guard.clear('p',xy((-2,0)),xy((2,0)),.2,.2)


def test_identity_is_explicit_and_native_geometry_errors_fail_closed():
    b,nets,xy = fixture()
    codes = tuple(int(n.GetNetCode()) for n in nets)
    for invalid in ((codes[0],codes[0]),(0,codes[1]),(9999,codes[1]),(True,codes[1])):
        with pytest.raises(ValueError): MemberObstacles(b,pcb.F_Cu,invalid)
    guard = MemberObstacles(b,pcb.F_Cu,codes)
    class Unknown:
        def Collide(self,*args): raise ValueError('unavailable native shape')
    guard.index[codes[1]] = [(Unknown(),None,{},0)]
    assert not guard.clear('p',xy((-1,0)),xy((1,0)),.2,.2)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('layer',(pcb.F_Cu,pcb.In2_Cu,pcb.B_Cu))
def test_native_matched_via_holes_do_not_block_legal_member_continuation(turn,layer):
    b,nets,xy=fixture(turn)
    b.GetDesignSettings().m_HoleClearance=250000
    for net,y in zip(nets,(-.375,.375)):
        v=obstacle(b,net,xy,'via',layer)
        v.SetPosition(pcb.VECTOR2I_MM(*xy((0,y))))
        v.SetWidth(pcb.FromMM(.5));v.SetDrill(pcb.FromMM(.25))
    guard=MemberObstacles(b,layer,tuple(int(n.GetNetCode()) for n in nets))
    assert guard.paths([xy((0,-.225002)),xy((2,-.225002))],
        [xy((0,.225002)),xy((2,.225002))],.25,.2)['ok']


def test_own_net_exclusions_without_member_identity_refuse():
    b,nets,xy = fixture()
    detail = {}
    result = route._grid_coupled_path(b,start_center=xy((-8,0)),end_center=xy((8,0)),
        p_start=xy((-8,-.2)),n_start=xy((-8,.2)),
        p_end=xy((8,-.2)),n_end=xy((8,.2)),layer_id=pcb.F_Cu,
        width=.2,gap=.2,clearance=.2,own={n.GetNetCode() for n in nets},
        diagnostics=detail)
    assert result is None and detail['status']=='member_guard_snapshot_refused'
    assert detail['visited']==0 and 'explicit_native' in detail['error']


def test_extra_excluded_net_and_unfilled_pair_zone_cannot_grant_authority():
    b,nets,xy=fixture();codes=tuple(int(n.GetNetCode()) for n in nets)
    detail={}
    result=route._grid_coupled_path(b,start_center=xy((-8,0)),end_center=xy((8,0)),
        p_start=xy((-8,-.2)),n_start=xy((-8,.2)),p_end=xy((8,-.2)),n_end=xy((8,.2)),
        layer_id=pcb.F_Cu,width=.2,gap=.2,clearance=.2,own=set(codes)|{9999},
        pair_net_codes=codes,diagnostics=detail)
    assert result is None and detail['status']=='member_guard_snapshot_refused'
    z=pcb.ZONE(b);z.SetNet(nets[1]);z.SetLayer(pcb.F_Cu);b.Add(z)
    with pytest.raises(ValueError,match='independent_fill_authority'):
        MemberObstacles(b,pcb.F_Cu,codes)


@pytest.mark.parametrize('turn',range(4))
def test_grid_constructs_detour_instead_of_crossing_existing_partner_via(turn):
    b,nets,xy = fixture(turn)
    obstacle(b,nets[1],xy,'via',pcb.F_Cu)
    codes = tuple(int(n.GetNetCode()) for n in nets)
    start,end = xy((-8,0)),xy((8,0))
    heading = tuple((end[i]-start[i])/16 for i in (0,1))
    detail = {}; before = field._field_snapshot_inventory(b)
    result = route._grid_coupled_path(b,start_center=start,end_center=end,
        p_start=xy((-8,-.2)),n_start=xy((-8,.2)),
        p_end=xy((8,-.2)),n_end=xy((8,.2)),layer_id=pcb.F_Cu,
        width=.2,gap=.2,clearance=.2,own=set(codes),pair_net_codes=codes,
        portal_mode=True,portal_start_heading=heading,portal_end_heading=heading,
        initial_turn_steps=1,terminal_turn_steps=1,
        deadline=time.monotonic()+10,diagnostics=detail)
    assert result is not None,detail
    guard = MemberObstacles(b,pcb.F_Cu,codes)
    assert guard.paths(*result[:2],.2,.2)['ok']
    assert any(abs(math.dist(start,p)+math.dist(p,end)-16)>.1 for p in result[0][1:-1])
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('turn',range(4))
def test_direction_reversal_cannot_borrow_opposite_lane_verdict(turn):
    b,nets,xy=fixture(turn)
    # An N object on the plus edge blocks only P-on-plus; reversing travel
    # changes the physical plus side and therefore reverses the mask.
    via=obstacle(b,nets[1],xy,'via',pcb.F_Cu)
    via.SetPosition(pcb.VECTOR2I_MM(*xy((0,.375))));via.SetWidth(pcb.FromMM(.5))
    guard=MemberObstacles(b,pcb.F_Cu,tuple(int(n.GetNetCode()) for n in nets))
    a,z=xy((-1,0)),xy((1,0))
    assert guard.corridor_mask(a,z,.2,.55,.2)==2
    assert guard.corridor_mask(z,a,.2,.55,.2)==1


def test_taper_passes_exact_member_guard_to_joint_escape():
    calls=[]
    def clear(a,z): calls.append((a,z));return True
    result=route._portal_pair_taper_escape((0,.375),(0,-.375),
        [(0,.2),(1,.2),(4,.2)],[(0,-.2),(1,-.2),(4,-.2)],
        width=.2,gap=.2,segment_clear=lambda a,z:True,
        p_segment_clear=clear,n_segment_clear=lambda a,z:False)
    assert result is None and calls
