import time
import pcbnew
import pytest
import cec_measurement_leaf as leaf
import cec_native_via_frontier as frontier
from test_measurement_leaf import fixture


@pytest.mark.parametrize('quarter',range(4))
def test_projected_barrel_frontier_sees_real_inner_layer_copper(quarter):
    board,pad,anchor,tracks,xy=fixture('arbitrary_portal_net',quarter)
    foreign=pcbnew.NETINFO_ITEM(board,'unrelated_inner_bus');board.Add(foreign)
    bus=pcbnew.PCB_TRACK(board);bus.SetLayer(pcbnew.In2_Cu)
    bus.SetStart(xy((12,7)));bus.SetEnd(xy((12,15)));bus.SetWidth(3000000)
    bus.SetNet(foreign);board.Add(bus)
    before=leaf._binding(board)
    result=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        radius_mm=8,max_sites=8,deadline=time.monotonic()+2)
    assert result['sites_nm'] and len(result['sites_nm'])<=8
    assert all(not bus.GetEffectiveShape(pcbnew.In2_Cu).Collide(
        pcbnew.VECTOR2I(*p),500000) for p in result['sites_nm'])
    assert not result['routing_admitted'] and not result['no_path_proof']
    assert leaf._binding(board)==before


def test_caller_contact_guard_cannot_be_skipped_or_widened():
    board,pad,anchor,tracks,xy=fixture('caller_contact')
    before=leaf._binding(board);calls=[]
    def refuse(at,dia):calls.append((at,dia));return False
    result=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        max_sites=4,deadline=time.monotonic()+2,barrel_guard=refuse)
    assert not result['sites_nm'] and calls and all(dia>=600000 for _,dia in calls)
    assert leaf._binding(board)==before


@pytest.mark.parametrize('kwargs',[dict(radius_mm=25),dict(max_sites=0),dict(clearance_nm=-1),
    dict(deadline=0)])
def test_frontier_has_finite_explicit_search_domain(kwargs):
    board,pad,anchor,tracks,xy=fixture()
    args=dict(clearance_nm=200000,deadline=time.monotonic()+2);args.update(kwargs)
    with pytest.raises(ValueError):frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),**args)


@pytest.mark.parametrize('quarter',range(4))
def test_diverse_ranking_funds_directions_before_nearby_corner_aliases(quarter):
    def rotate(point):
        x,y=point
        for _ in range(quarter):x,y=-y,x
        return x,y
    # The nearest three coordinates all probe the same obstructed corridor.
    points={rotate(p) for p in [(1,0),(1.1,.01),(1.2,.02),(-2,0),(0,3),(0,-4)]}
    old=frontier._rank_points(points,(0,0),diverse=False)
    new=frontier._rank_points(points,(0,0),diverse=True)
    assert old[0]==new[0]==rotate((1,0))
    assert set(new[:4])=={rotate(p) for p in [(1,0),(-2,0),(0,3),(0,-4)]}
    assert len(new)==len(set(new))==len(points) and set(new)==points


@pytest.mark.parametrize('quarter',range(4))
def test_diverse_native_proposals_keep_exact_barrel_and_contact_guards(quarter):
    board,pad,anchor,tracks,xy=fixture('renamed_diverse',quarter)
    foreign=pcbnew.NETINFO_ITEM(board,'independent_barrier');board.Add(foreign)
    bus=pcbnew.PCB_TRACK(board);bus.SetLayer(pcbnew.In2_Cu);bus.SetNet(foreign)
    bus.SetStart(xy((12,7)));bus.SetEnd(xy((12,15)));bus.SetWidth(3000000);board.Add(bus)
    before=leaf._binding(board);queried=[]
    def allow(at,dia):queried.append(tuple(at));return True
    proof=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        max_sites=8,radius_mm=8,deadline=time.monotonic()+2,barrel_guard=allow,diverse=True)
    assert proof['spatially_diverse_proposals'] and proof['sites_nm']
    assert {tuple(p) for p in proof['sites_nm']}<=set(queried)
    assert all(not bus.GetEffectiveShape(pcbnew.In2_Cu).Collide(pcbnew.VECTOR2I(*p),500000)
        for p in proof['sites_nm'])
    assert leaf._binding(board)==before and not proof['routing_admitted']


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_diverse_proposal_mode_is_explicit_boolean(flag):
    board,pad,anchor,tracks,xy=fixture()
    with pytest.raises(ValueError,match='bounded_native_barrel_frontier_required'):
        frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
            deadline=time.monotonic()+2,diverse=flag)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('geometry',[(.671227,.3),(1.,.4),(3.531,.3),(6.836,.3)])
def test_source_sized_barrel_uses_actual_extent_on_every_layer(quarter,geometry):
    import cec_fr as fr
    board,pad,anchor,tracks,xy=fixture('arbitrary_larger_web',quarter)
    foreign=pcbnew.NETINFO_ITEM(board,'independent_inner_copper');board.Add(foreign)
    bus=pcbnew.PCB_TRACK(board);bus.SetLayer(pcbnew.In2_Cu);bus.SetNet(foreign)
    bus.SetStart(xy((12,7)));bus.SetEnd(xy((12,15)));bus.SetWidth(3000000);board.Add(bus)
    before=leaf._binding(board);queries=[]
    dia,drill=geometry
    def source_guard(at,width):queries.append((tuple(at),width));return True
    proof=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        radius_mm=8,max_sites=8,deadline=time.monotonic()+2,diverse=True,
        diameter_mm=dia,drill_mm=drill,barrel_guard=source_guard)
    assert proof['sites_nm'] and proof['diameter_mm']==dia and proof['drill_mm']==drill
    width=round(dia*1e6)
    assert all(queried_width==width for _,queried_width in queries)
    assert {tuple(q) for q in proof['sites_nm']}<={q for q,_ in queries}
    for at in proof['sites_nm']:
        point=pcbnew.VECTOR2I(*at)
        assert not bus.GetEffectiveShape(pcbnew.In2_Cu).Collide(point,width//2+200000)
        assert fr._via_spot_clear(board,point,width,200000,{pad.GetNetCode()},
            drill_nm=round(drill*1e6),net_code=pad.GetNetCode())
    assert leaf._binding(board)==before and not proof['routing_admitted']
    assert not proof['release_authority'] and not proof['no_path_proof']


def test_explicit_default_geometry_has_unchanged_legacy_proposals():
    board,pad,_,_,xy=fixture('default_parity')
    args=dict(clearance_nm=200000,radius_mm=4,max_sites=8,diverse=True)
    implicit=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),
        deadline=time.monotonic()+2,**args)
    explicit=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),
        deadline=time.monotonic()+2,diameter_mm=.6,drill_mm=.3,**args)
    assert implicit==explicit


@pytest.mark.parametrize('kwargs',[dict(diameter_mm=True),dict(diameter_mm=float('nan')),
    dict(diameter_mm=8.000001),dict(diameter_mm=0),dict(drill_mm=float('inf')),
    dict(drill_mm=-.1),dict(drill_mm=.6),dict(drill_mm=True),dict(barrel_guard={})])
def test_explicit_barrel_geometry_and_guard_are_bounded_and_typed(kwargs):
    board,pad,_,_,xy=fixture()
    with pytest.raises(ValueError,match='bounded_native_barrel_frontier_required'):
        frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
            deadline=time.monotonic()+2,**kwargs)


@pytest.mark.parametrize('quarter',range(4))
def test_axis_proposals_prefer_a_straight_entry_without_changing_native_guards(quarter):
    board,pad,_,_,xy=fixture('axis_aligned_source',quarter);before=leaf._binding(board);queries=[]
    def guard(at,width):queries.append(tuple(at));return True
    origin=list(xy((12,10)))
    proof=frontier.sites(board,pad.GetNetCode(),origin,clearance_nm=200000,radius_mm=8,max_sites=8,
        deadline=time.monotonic()+2,diverse=True,prefer_axis_aligned=True,barrel_guard=guard)
    assert proof['source_axis_alignment_preferred'] and proof['sites_nm']
    assert any(p[0]==origin[0] or p[1]==origin[1] for p in proof['sites_nm'])
    assert {tuple(p) for p in proof['sites_nm']}<=set(queries)
    assert leaf._binding(board)==before and not proof['routing_admitted']


@pytest.mark.parametrize('flag',[1,None,'true'])
def test_axis_preference_is_explicit_and_not_a_boolean_coercion(flag):
    board,pad,_,_,xy=fixture()
    with pytest.raises(ValueError,match='bounded_native_barrel_frontier_required'):
        frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
            deadline=time.monotonic()+2,prefer_axis_aligned=flag)


def test_axis_cost_does_not_pay_for_a_large_detour_to_save_a_tiny_bend():
    near=(.01,2.);straight=(0.,2.05);far=(0.,3.)
    assert frontier._rank_points([near,straight,far],(0.,0.),diverse=False,axis_bend_penalty_mm=.3)==[straight,near,far]


def own_land_fixture(quarter=0,back=False,shape=pcbnew.PAD_SHAPE_RECT):
    from test_lastmile import _board
    board=_board([],edge=(0,0,20,20));board.SetCopperLayerCount(6)
    for name in ('arbitrary_local_return','foreign_land'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('not_a_named_board_rule');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet('arbitrary_local_return'))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(shape);pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,10));pad.SetOrientationDegrees(quarter*90)
    if shape==pcbnew.PAD_SHAPE_ROUNDRECT:pad.SetRoundRectRadiusRatio(.2)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    pad.SetLayerSet(layers);fp.Add(pad)
    def point(x,y):
        for _ in range(quarter):x,y=20-y,x
        return [round(x*1e6),round(y*1e6)]
    return board,pad,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_OVAL])
def test_close_own_smd_seat_is_proposed_only_after_exact_native_and_contact_guards(quarter,back,shape):
    import cec_fr as fr
    board,pad,point=own_land_fixture(quarter,back,shape);before=leaf._binding(board);calls=[]
    def guard(at,dia):calls.append(tuple(at));return True
    # 50 um of physical separation from the pad's bounding envelope. The
    # old extra 200-um foreign-net moat erased this entire 30-um search cell.
    proof=frontier.sites(board,pad.GetNetCode(),point(10.65,10),clearance_nm=200000,
        radius_mm=.03,max_sites=4,deadline=time.monotonic()+2,barrel_guard=guard)
    assert proof['sites_nm'],proof
    assert {tuple(q)for q in proof['sites_nm']}<=set(calls)
    for at in proof['sites_nm']:
        position=pcbnew.VECTOR2I(*at)
        assert fr._via_pad_excluded(board,position,600000,300000,pad.GetNetCode()) is None
        assert fr._via_spot_clear(board,position,600000,200000,{pad.GetNetCode()},
            drill_nm=300000,net_code=pad.GetNetCode())
    assert leaf._binding(board)==before and not proof['routing_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('back',[False,True])
def test_foreign_smd_moat_and_same_net_partial_land_exclusion_remain_exact(back):
    import cec_fr as fr
    board,pad,point=own_land_fixture(back=back);code=pad.GetNetCode()
    pad.SetNet(board.FindNet('foreign_land'))
    proof=frontier.sites(board,code,point(10.65,10),clearance_nm=200000,
        radius_mm=.03,max_sites=4,deadline=time.monotonic()+2)
    assert proof['sites_nm']==[]
    pad.SetNet(board.FindNet('arbitrary_local_return'))
    # A one-nanometre pad overlap still needs actual process authority; this
    # ordinary remote-barrel frontier supplies none. Full containment isn't
    # inferred from sharing the net either.
    for at in (point(10.599999,10),point(10,10)):
        assert not fr._via_spot_clear(board,pcbnew.VECTOR2I(*at),600000,200000,{code},
            drill_nm=300000,net_code=code)


def test_new_own_smd_proposals_do_not_bypass_a_refusing_barrel_guard():
    board,pad,point=own_land_fixture();calls=[]
    def refuse(at,dia):calls.append(tuple(at));return False
    result=frontier.sites(board,pad.GetNetCode(),point(10.65,10),clearance_nm=200000,
        radius_mm=.03,max_sites=4,deadline=time.monotonic()+2,barrel_guard=refuse)
    assert calls and result['sites_nm']==[]
