import pytest
from cec_maze_channels import gap_axes, octilinear_neighbors


def test_mixed_contact_margins_keep_real_foreign_to_own_net_channel():
    from cec_maze_channels import mixed_centerline_boxes
    # Foreign copper needs radius + electrical clearance. The own-net force
    # contact exclusion already includes its radius, not foreign clearance.
    native=[(0,0,10,5)];own=[(0,5.75,10,8)]
    assert not gap_axes([*native,*own],(-10,-10,20,20),
        inflation=.4,target=(5,5.575))[1]
    mixed=mixed_centerline_boxes(native,own,inflation=.4,target=(5,5.575))
    assert 6 in gap_axes(mixed,(-10,-10,20,20),inflation=0,target=(5,5.575))[1]


def test_mixed_contact_hints_remain_bounded_with_dense_native_pin_field():
    from cec_maze_channels import mixed_centerline_boxes
    native=[(i,0,i+.1,1) for i in range(256)]
    extra=[(-i-1,2,-i-.5,3) for i in range(64)]
    boxes=mixed_centerline_boxes(native,extra,inflation=.2,target=(0,0))
    assert len(boxes)==256 and set(extra)<=set(boxes)


@pytest.mark.parametrize('bad',[None,True,[(0,0,0,1)],[(0,0,1,float('nan'))],
    [(0,0,1,1)]*65,[(False,0,1,1)]])
def test_invalid_centerline_hints_cannot_expand_work_or_weaken_guards(bad):
    from cec_maze_channels import checked_centerline_boxes
    with pytest.raises(ValueError):checked_centerline_boxes(bad)


def test_extra_axes_do_not_delete_exact_diagonal_neighbours():
    xs, ys = [-10, -3, 0, 2, 10], [-10, -4, 0, 3, 10]
    neighbours = dict((direction, (xs[x], ys[y]))
                      for direction, x, y in octilinear_neighbors(xs, ys, 2, 2))
    assert neighbours == {0: (2, 0), 1: (-3, 0), 2: (0, 3), 3: (0, -4),
                          4: (10, 10), 5: (10, -10), 6: (-3, 3), 7: (-10, -10)}


@pytest.mark.parametrize("xs,ys", [([0,1,2],[0,1,2]), ([0,1,3,5],[0,2,3,7])])
def test_every_proposed_hop_is_canonical_and_nearest(xs, ys):
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            for _direction, nx, ny in octilinear_neighbors(xs, ys, ix, iy):
                dx, dy = xs[nx]-x, ys[ny]-y
                assert (dx or dy) and (not dx or not dy or abs(dx) == abs(dy))
                if dx and dy:
                    assert not any(0 < abs(xx-x) < abs(dx) and (xx-x)*dx > 0
                        and yy in ys for xx in xs
                        for yy in [y + (1 if dy > 0 else -1)*abs(xx-x)])


@pytest.mark.parametrize("blocked", [False, True])
def test_real_maze_preserves_diagonal_channel_with_off_grid_axis(monkeypatch, blocked):
    import pcbnew
    import cec_fr
    import cec_maze_channels
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, "synthetic-diagonal")
    board.Add(net)
    start, end = pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(1, 1)
    monkeypatch.setattr(cec_maze_channels, "gap_axes", lambda *a, **k: ([250000], []))
    monkeypatch.setattr(cec_fr, "_foreign_shape_indexes", lambda *a, **k: ([], []))
    monkeypatch.setattr(cec_fr, "_guarded_power_reservations", lambda: [])
    checked = []
    def guard(a, b, *_args):
        checked.append(((a.x, a.y), (b.x, b.y)))
        return not blocked and a.x == a.y and b.x == b.y
    monkeypatch.setattr(cec_fr, "_snapshot_foreign_clear", guard)
    result = cec_fr._maze_lastmile_legs(
        board, start, end, 200000, pcbnew.F_Cu, 200000, net.GetNetCode(),
        lambda *a: True, grid_mm=.5, margin_mm=1)
    assert checked
    if blocked:
        assert result is None
    else:
        assert result and result[0][0] == start and result[-1][1] == end
        assert all(abs(b.x-a.x) == abs(b.y-a.y) for a, b, _w in result)


def test_off_grid_narrow_channel_is_sampled_without_global_refinement():
    # 1.7 mm pads on an off-grid 2.54 pitch; 0.25 track + 0.25 clearance.
    xs, ys = gap_axes([(49220,16550,50920,18250),(51760,16550,53460,18250)],
                      (40000,10000,54000,21000), inflation=375,
                      target=(52610,19940))
    assert xs == [51340]
    assert ys == []


def test_closed_channel_is_not_made_routable_by_sampling():
    assert gap_axes([(0,0,10,10),(11,0,21,10)], (-20,-20,40,40),
                    inflation=1, target=(25,5)) == [[], []]


def test_native_rounding_aliases_do_not_exhaust_diverse_gap_menu():
    # Several almost-identical source boxes yield nanometre slivers and gap
    # midpoints in one cluster. A physically separate useful throat must
    # still enter the bounded proposal list.
    boxes=[(0,0,100,100),(103,0,200,100),(104,0,201,100),
           (300,0,400,100),(403,0,500,100),(600,0,700,100),(720,0,820,100)]
    old=gap_axes(boxes,(-100,-100,1000,200),inflation=0,target=(100,50),max_axes=2)
    new=gap_axes(boxes,(-100,-100,1000,200),inflation=0,target=(100,50),max_axes=2,
        minimum_span=5,minimum_axis_separation=10)
    assert 710 not in old[0] and 710 in new[0]
    assert len(new[0])<=2


def test_axis_count_is_bounded_and_disjoint_projections_are_ignored():
    boxes = [(i*10,0,i*10+2,2) for i in range(20)]
    assert len(gap_axes(boxes, (-1,-1,201,3), inflation=1,
                        target=(5,1), max_axes=3)[0]) == 3
    assert gap_axes([(0,0,2,2),(10,10,12,12)], (-1,-1,20,20),
                    inflation=1,target=(15,15)) == [[],[]]
    with pytest.raises(ValueError):
        gap_axes(boxes*20,(-1,-1,201,3),inflation=1,target=(5,1))
def test_off_grid_pad_to_edge_channel_is_sampled():
    from cec_maze_channels import gap_axes
    xs, ys = gap_axes([(100, 100, 200, 200)], (0, 0, 400, 400),
                      inflation=50, target=(190, 220), center_bounds=(70,70,350,260))
    assert 255 in ys


def test_staggered_obstacles_use_clearance_inflated_projection_overlap():
    xs, ys = gap_axes([(0, 7, 2, 9), (10, 2, 12, 4)],
                      (-10, -10, 20, 20), inflation=2,
                      target=(15, 15))
    assert xs == [6]
    assert ys == []


@pytest.mark.parametrize('turn,blocked', [(0,False),(1,False),(2,False),(3,False),(0,True)])
def test_native_via_throat_closes_with_small_work_without_moving_copper(turn, blocked):
    import math
    import pcbnew
    import cec_fr
    import cec_search_budget
    from cec_maze_channels import native_obstacle_boxes

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    wanted = pcbnew.NETINFO_ITEM(board, 'fixture-supply')
    foreign = pcbnew.NETINFO_ITEM(board, 'fixture-return')
    board.Add(wanted)
    board.Add(foreign)
    def point(x, y):
        for _ in range(turn):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(20+x, 20+y)
    start, end = point(0., 0.), point(2., 1.15)
    for x, y in ((0., .85), (1.475, -.04)):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point(x,y))
        via.SetWidth(pcbnew.FromMM(.35))
        via.SetDrill(pcbnew.FromMM(.2))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(foreign.GetNetCode())
        via.SetLocked(True)
        board.Add(via)
    original = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with cec_search_budget.scoped(512) as budget:
        result = cec_fr._guarded_profiled_lastmile_legs(
            board, start, end, pcbnew.FromMM(.5), pcbnew.In2_Cu,
            pcbnew.FromMM(.2), wanted.GetNetCode(), lambda *_a: not blocked,
            allow_maze=False, max_length_nm=pcbnew.FromMM(3.28))
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == original
    assert budget.used < 512
    if blocked:
        assert result is None
    else:
        assert result and result[0][0] == start and result[-1][1] == end
        assert sum(math.hypot(b.x-a.x,b.y-a.y) for a,b,_w in result) <= 3.28e6
        assert all(not (b.x-a.x) or not (b.y-a.y) or abs(b.x-a.x)==abs(b.y-a.y)
                   for a,b,_w in result)
        assert len(native_obstacle_boxes(board, pcbnew.In2_Cu, {wanted.GetNetCode()},
                                        (0,0,40e6,40e6),(end.x,end.y))) == 2


def test_native_obstacles_ignore_same_net_and_surface_tracks_on_other_layer():
    import pcbnew
    from cec_maze_channels import native_obstacle_boxes
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, 'same-net')
    board.Add(net)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(1,1))
    track.SetEnd(pcbnew.VECTOR2I_MM(2,1))
    track.SetWidth(pcbnew.FromMM(.2))
    track.SetLayer(pcbnew.F_Cu)
    track.SetNetCode(net.GetNetCode())
    board.Add(track)
    assert native_obstacle_boxes(board, pcbnew.F_Cu, {net.GetNetCode()},
                                 (0,0,3e6,3e6),(2e6,1e6)) == []
    assert native_obstacle_boxes(board, pcbnew.B_Cu, set(),
                                 (0,0,3e6,3e6),(2e6,1e6)) == []
    assert len(native_obstacle_boxes(board, pcbnew.F_Cu, set(),
                                    (0,0,3e6,3e6),(2e6,1e6))) == 1


@pytest.mark.parametrize('turn',range(4))
def test_compound_channels_preserve_old_prefix_and_bound_canonical_proposals(turn):
    from cec_maze_channels import orthogonal_channel_paths
    def xy(x,y):
        for _ in range(turn):x,y=-y,x
        return x,y
    def bbox(row):
        pts=[xy(x,y) for x in (row[0],row[2]) for y in (row[1],row[3])]
        return min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts)
    start,end=xy(0,0),xy(5000000,1000000)
    boxes=[bbox((1000000,-500000,1800000,1000000)),
           bbox((2500000,1500000,3200000,2500000))]
    bounds=bbox((-3000000,-3000000,8000000,5000000))
    old=orthogonal_channel_paths(start,end,boxes,bounds,inflation=325000)
    new=orthogonal_channel_paths(start,end,boxes,bounds,inflation=325000,compound=True)
    assert new[:len(old)]==old and len(new)>len(old)
    assert len(new)<=len(old)+128 and any(len(path)==5 for path in new)
    assert all(path[0]==start and path[-1]==end and len(path)<=5 for path in new)
    assert all(a!=b and (a[0]==b[0] or a[1]==b[1])
        for path in new for a,b in zip(path,path[1:]))


def test_compound_channel_cannot_bypass_complete_native_path_guard(monkeypatch):
    import pcbnew
    import cec_fr as fr
    import cec_maze_channels as channels
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'arbitrary_compound');board.Add(net)
    monkeypatch.setattr(fr,'_canonical_45_xy_paths',lambda *_:[])
    monkeypatch.setattr(fr,'_offset_manhattan_xy_paths',lambda *_:[])
    monkeypatch.setattr(channels,'native_obstacle_boxes',lambda *a,**kw:
        [(1000000,-500000,1800000,1000000),(2500000,1500000,3200000,2500000)])
    before=list(board.GetTracks());checked=[]
    result=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(0,0),
        pcbnew.VECTOR2I(5000000,1000000),250000,pcbnew.F_Cu,200000,
        net.GetNetCode(),lambda *a:checked.append(a) or True,
        allow_maze=False,path_validator=lambda *_:False)
    assert checked and result is None and list(board.GetTracks())==before


@pytest.mark.parametrize('turn',range(4))
def test_independent_terminal_approaches_close_native_five_leg_channel(turn):
    import time
    import pcbnew
    import cec_fr as fr
    import cec_maze_channels as channels
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'renamed_measurement_channel');board.Add(net)
    foreign=pcbnew.NETINFO_ITEM(board,'unrelated_guard_material');board.Add(foreign)
    def xy(x,y):
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I_MM(20+x,20+y)
    boxes=[(-.4,-.5,.4,-.3),(-.4,.3,.4,.5),
           (5.6,-.5,6.4,-.3),(5.6,.3,6.4,.5),(1.5,-3,4.5,3)]
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('unrelated_obstacle_owner');board.Add(fp)
    for i,(a,b,c,d) in enumerate(boxes):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(i));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPosition(xy((a+c)/2,(b+d)/2));pad.SetSize(pcbnew.VECTOR2I_MM(c-a,d-b))
        pad.SetOrientationDegrees(90*turn);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNet(foreign);fp.Add(pad)
    start,end=xy(0,0),xy(6,0);margin=4000000
    bounds=(min(start.x,end.x)-margin,min(start.y,end.y)-margin,
            max(start.x,end.x)+margin,max(start.y,end.y)+margin)
    native=channels.native_obstacle_boxes(board,pcbnew.F_Cu,{net.GetNetCode()},
        bounds,tuple(end))
    old=channels.orthogonal_channel_paths(tuple(start),tuple(end),native,bounds,
        inflation=300000,compound=True)
    new=channels.orthogonal_channel_paths(tuple(start),tuple(end),native,bounds,
        inflation=300000,compound=True,independent_approaches=True)
    assert new[:len(old)]==old and len(new)<=len(old)+1024
    before=list(board.GetTracks())
    assert fr._guarded_profiled_lastmile_legs(board,start,end,200000,pcbnew.F_Cu,
        200000,net.GetNetCode(),lambda *_:True,allow_maze=False,maze_margin_mm=4.) is None
    result=fr._guarded_profiled_lastmile_legs(board,start,end,200000,pcbnew.F_Cu,
        200000,net.GetNetCode(),lambda *_:True,allow_maze=False,maze_margin_mm=4.,
        refine_maze=True,deadline_monotonic=time.monotonic()+3.)
    assert result and len(result)==5 and list(board.GetTracks())==before
    assert result[0][0]==start and result[-1][1]==end
    assert all(a.x==b.x or a.y==b.y for a,b,_ in result)
    segment=pcbnew.SHAPE_SEGMENT
    assert all(not p.GetEffectiveShape(pcbnew.F_Cu).Collide(segment(a,b,w),200000)
        for p in fp.Pads() for a,b,w in result)
    rejected=fr._guarded_profiled_lastmile_legs(board,start,end,200000,pcbnew.F_Cu,
        200000,net.GetNetCode(),lambda *_:True,allow_maze=False,maze_margin_mm=4.,
        refine_maze=True,deadline_monotonic=time.monotonic()+3.,path_validator=lambda *_:False)
    assert rejected is None and list(board.GetTracks())==before


@pytest.mark.parametrize('options',[
    {'independent_approaches':1},
    {'independent_approaches':True},
    {'independent_approaches':True,'compound':True,'max_axes':9},
])
def test_independent_approach_mode_requires_explicit_bounded_scope(options):
    from cec_maze_channels import orthogonal_channel_paths
    with pytest.raises(ValueError):
        orthogonal_channel_paths((0,0),(10,10),[],(-10,-10,20,20),inflation=1,**options)
