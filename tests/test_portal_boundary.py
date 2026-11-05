import copy,math
import pytest
import cec_portal_boundary as boundary


def test_overlaps_reversed_bounds_and_tangencies_are_not_open_windows():
    assert boundary.free_intervals((0,0),(1,0),[(3,1,2,-1),(2.5,-1,4,1)],
        inflation=.25,lower=1,upper=6)==[(1,1.75),(4.25,6)]
    assert boundary.free_intervals((0,0),(1,0),[(0,0,6,1)],
        inflation=0,lower=1,upper=6)==[]


@pytest.mark.parametrize('quarter',range(4))
def test_narrow_unsampled_windows_preserve_polarity_pose_and_original_budget(quarter):
    def point(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return (31+x,22+y)
    def vector(p):
        x,y=point(p);return (x-31,y-22)
    rows=[]
    for lead in (1.3,2.,3.,4.,5.,6.):
        rows.append(dict(side='start',sign=1,route_heading=vector((1,0)),
            lateral_mm=0.,lead_mm=lead,center=point((lead,0)),
            p=point((lead,.4)),n=point((lead,-.4)),
            actual_p=point((0,.4)),actual_n=point((0,-.4))))
    reservations=[]
    # With 0.5 diameter / 0.2 clearance, the clear window is (2.55,2.85).
    for x0,x1 in ((-1,2.1),(3.3,8)):
        points=[point((x,y)) for x in (x0,x1) for y in (-2,2)]
        reservations.append(dict(net='POWER',layer='B.Cu',
            x0=min(x for x,y in points),x1=max(x for x,y in points),
            y0=min(y for x,y in points),y1=max(y for x,y in points)))
    originals=copy.deepcopy((rows,reservations))
    added=boundary.boundary_rows(rows,reservations,p_net='PAIR_A',n_net='PAIR_B',
        diameter_mm=.5,clearance_mm=.2)
    assert len(added)==3 and (rows,reservations)==originals
    assert all(2.55<row['lead_mm']<2.85 for row in added)
    for row in added:
        assert math.dist(row['p'],row['n'])==pytest.approx(.8)
        assert row['actual_p']==rows[0]['actual_p']
        assert row['actual_n']==rows[0]['actual_n']
        assert row['sign']==1 and row['route_heading']==rows[0]['route_heading']


def test_no_obstacles_no_new_domain_and_exact_member_net_exemption():
    rows=[dict(side='end',sign=-1,route_heading=(1,0),lateral_mm=0,
        lead_mm=lead,center=(lead,0),p=(lead,.5),n=(lead,-.5)) for lead in (1.3,2,3)]
    assert boundary.boundary_rows(rows,[],p_net='A',n_net='B',diameter_mm=.5,clearance_mm=.2)==[]
    # Own net A remains foreign to B; exempting the entire pair would be wrong.
    reservations=[dict(net='A',x0=0,y0=-1,x1=5,y1=1)]
    assert boundary.boundary_rows(rows,reservations,p_net='A',n_net='B',diameter_mm=.5,clearance_mm=.2)==[]


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,0])
def test_invalid_geometry_is_not_a_search_waiver(bad):
    with pytest.raises(ValueError):
        boundary.boundary_rows([],[],p_net='A',n_net='B',diameter_mm=bad,clearance_mm=.2)


@pytest.mark.parametrize('quarter',[0,1])
def test_loaded_native_reservation_guard_confirms_unsampled_window(tmp_path,quarter):
    import pcbnew
    import cec_fr
    from unittest.mock import patch
    from test_endpoint_pofv_domain import fixture
    from cec_local_copper_cell import copper_inventory
    source,_ends,pair=fixture(tmp_path,quarter=quarter,narrow=.8)
    board=pcbnew.LoadBoard(str(source));before=copper_inventory(board)
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return (30+x,30+y)
    a,b=point(0,0),point(1,0);heading=(b[0]-a[0],b[1]-a[1])
    rows=[dict(side='start',sign=1,route_heading=heading,lateral_mm=0,
        lead_mm=lead,center=point(lead,0),p=point(lead,.4),n=point(lead,-.4))
        for lead in (1.3,2,3,4,5,6)]
    reservations=[]
    for x0,x1 in ((-1,2.1),(3.3,8)):
        corners=[point(x,y) for x in (x0,x1) for y in (-2,2)]
        reservations.append(dict(net='FOREIGN_POWER',layer='B.Cu',
            x0=min(x for x,y in corners),x1=max(x for x,y in corners),
            y0=min(y for x,y in corners),y1=max(y for x,y in corners)))
    added=boundary.boundary_rows(rows,reservations,p_net=pair['p'],n_net=pair['n'],
        diameter_mm=.5,clearance_mm=.2)
    def clear(row):
        return all(cec_fr._via_spot_clear(board,pcbnew.VECTOR2I_MM(*row[member]),
            pcbnew.FromMM(.5),pcbnew.FromMM(.2),{board.GetNetcodeFromNetname(net)},
            drill_nm=pcbnew.FromMM(.25),net_code=board.GetNetcodeFromNetname(net))
            for member,net in (('p',pair['p']),('n',pair['n'])))
    with patch.object(cec_fr,'_guarded_power_reservations',return_value=reservations):
        assert not any(clear(row) for row in rows)
        assert len(added)==3 and all(clear(row) for row in added)
    assert copper_inventory(board)==before
