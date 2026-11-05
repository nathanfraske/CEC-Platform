"""Actual filled-reference boundaries must generate new via-axis events.

Proposal clipping never substitutes for exact annular/native receiving.
"""
import time
import pcbnew
import pytest
import cec_native_via_frontier as frontier
import cec_field_coupling as field
import cec_fr as fr
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as native_fixture


def fixture(tmp_path, *, quarter=0, layer=pcbnew.F_Cu, second_edge=10.):
    board, source, _, _, owner, cap, root = native_fixture(tmp_path, quarter=quarter, layer=layer)
    def xy(x, y):
        for _ in range(quarter):
            x, y = 20-y, x
        return pcbnew.VECTOR2I(round(x*1e6), round(y*1e6))
    def unrotate(point):
        x, y = (v/1e6 for v in point)
        for _ in range(quarter):
            x, y = y, 20-x
        return x, y
    discard_items(board, list(board.Zones()))
    for face, edge in ((pcbnew.In1_Cu, 10.), (pcbnew.In4_Cu, second_edge)):
        zone=pcbnew.ZONE(board);zone.SetLayer(face);zone.SetNet(board.FindNet('GND'))
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in ((edge,2),(28,2),(28,28),(edge,28)):
            p=xy(x,y);poly.Append(p.x,p.y)
        zone.Outline().Append(poly);zone.SetFilledPolysList(face,poly);zone.SetIsFilled(True);board.Add(zone)
    # Real foreign surface land: every through-axis still owes all-layer
    # native foreign-copper guards, even though reference clipping succeeds.
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED_RENAMED_OBSTACLE');fp.SetLayer(layer);board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('other');pad.SetNet(board.FindNet('+3V3'))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetPosition(xy(12,15))
    mask=pcbnew.LSET();mask.AddLayer(layer);pad.SetLayerSet(mask);fp.Add(pad)
    return board, list(xy(10.1,15)), unrotate


def sites(board, origin, **options):
    return frontier.sites(board,board.GetNetcodeFromNetname('GND'),origin,
        clearance_nm=200000,radius_mm=4.,max_sites=8,diameter_mm=.9,drill_mm=.5,
        deadline=time.monotonic()+3.,**options)


def assert_actual_annuli(board, positions):
    for at in positions:
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetWidth(900000);via.SetDrill(500000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
            annulus=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(annulus,face,0,1,pcbnew.ERROR_OUTSIDE)
            bore=pcbnew.SHAPE_POLY_SET();pcbnew.SHAPE_CIRCLE(via.GetPosition(),250000).TransformToPolygon(bore,1,pcbnew.ERROR_INSIDE)
            annulus.BooleanSubtract(bore)
            metal=pcbnew.SHAPE_POLY_SET()
            for zone in board.Zones():
                if zone.GetNetname()=='GND' and zone.IsOnLayer(face):metal.BooleanAdd(zone.GetFilledPolysList(face))
            annulus.BooleanSubtract(metal)
            assert annulus.OutlineCount()==0, (at,board.GetLayerName(face),annulus.Area())
        assert fr._via_spot_clear(board,via.GetPosition(),900000,200000,
            {via.GetNetCode()},drill_nm=500000,net_code=via.GetNetCode())


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_true_mode_generates_shifted_plane_edge_events_before_ranking(tmp_path,quarter,layer):
    b,origin,unrotate=fixture(tmp_path,quarter=quarter,layer=layer)
    before=field._field_snapshot_inventory(b)
    result=sites(b,origin,require_full_ground_reference=True)
    assert result['sites_nm']
    assert all(unrotate(p)[0]>=10.45 for p in result['sites_nm'])
    assert any(10.45<=unrotate(p)[0]<10.6 for p in result['sites_nm'])
    assert_actual_annuli(b,result['sites_nm'])
    assert field._field_snapshot_inventory(b)==before
    assert not result['routing_admitted'] and not result['release_authority']


def test_both_ground_faces_intersect_before_candidate_generation(tmp_path):
    b,origin,unrotate=fixture(tmp_path,second_edge=10.6)
    result=sites(b,origin,require_full_ground_reference=True)
    assert result['sites_nm'] and all(unrotate(p)[0]>=11.05 for p in result['sites_nm'])
    assert_actual_annuli(b,result['sites_nm'])


def test_flag_false_exact_legacy_parity_and_new_events_not_postfiltered_old_list(tmp_path):
    b,origin,unrotate=fixture(tmp_path)
    legacy=sites(b,origin)
    explicit=sites(b,origin,require_full_ground_reference=False)
    assert legacy==explicit
    assert any(unrotate(p)[0]<10.45 for p in legacy['sites_nm'])
    clipped=sites(b,origin,require_full_ground_reference=True)
    assert clipped['sites_nm'] and set(map(tuple,clipped['sites_nm']))-set(map(tuple,legacy['sites_nm']))


@pytest.mark.parametrize('fault',['non_ground','unknown_profile','missing_face','unfilled_face'])
def test_true_mode_needs_ground_factory_and_every_actual_filled_face(tmp_path,fault):
    b,origin,_=fixture(tmp_path);code=b.GetNetcodeFromNetname('GND')
    if fault=='non_ground':code=b.GetNetcodeFromNetname('+3V3')
    elif fault=='unknown_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='UNKNOWN_PROFILE';b.SetProperties(props)
    elif fault=='missing_face':discard_items(b,[next(z for z in b.Zones() if z.IsOnLayer(pcbnew.In4_Cu))])
    else:next(z for z in b.Zones() if z.IsOnLayer(pcbnew.In4_Cu)).UnFill()
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        frontier.sites(b,code,origin,clearance_nm=200000,radius_mm=4.,max_sites=8,
            diameter_mm=.9,drill_mm=.5,deadline=time.monotonic()+3.,require_full_ground_reference=True)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('flag',[None,1,'true'])
def test_reference_scope_flag_is_strict_boolean(tmp_path,flag):
    b,origin,_=fixture(tmp_path)
    with pytest.raises(ValueError):sites(b,origin,require_full_ground_reference=flag)
