"""Power style is actual geometry, not a rendering or current-width waiver."""
import math
import pcbnew
import pytest
from shapely.geometry import Polygon
import cec_power_contours as contours


def board():
    b=pcbnew.CreateEmptyBoard(); n=pcbnew.NETINFO_ITEM(b,'arbitrary/rail')
    b.Add(n); return b,n


def track(b,n,a,z,w):
    t=pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*z))
    t.SetNet(n);t.SetWidth(w);t.SetLayer(pcbnew.F_Cu);b.Add(t);return t


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_short_wide_native_tracks_report_all_orientations(angle,mirror):
    b,n=board()
    def point(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return (int((x+20)*1e6),int((y+20)*1e6))
    t=track(b,n,point(0,0),point(.05,0),6500000)
    before=(t.GetStart(),t.GetEnd(),t.GetWidth())
    result=contours.audit_board(b)
    assert result['complete'] and result['finding_count']==1
    assert result['findings'][0]['type']=='short_wide_capsule'
    assert result['findings'][0]['cap_extension_mm']==3.25
    assert not result['replacement_authorized']
    assert before==(t.GetStart(),t.GetEnd(),t.GetWidth())


def test_unequal_elbow_and_protected_width_are_logged():
    b,n=board();a=track(b,n,(10000000,10000000),(10000000,20000000),1000000)
    z=track(b,n,(10000000,10000000),(20000000,10000000),4000000);z.SetLocked(True)
    issues=contours.audit_board(b)['findings']
    assert [r['type'] for r in issues]==['unequal_width_round_join']
    assert issues[0]['locked'] and not issues[0]['ordinary_neckdown_allowed']
    assert issues[0]['track_uuids']==sorted([a.m_Uuid.AsString(),z.m_Uuid.AsString()])


def test_native_large_convex_smd_pad_hides_cap_but_footprint_box_does_not():
    b,n=board();track(b,n,(10000000,10000000),(10050000,10000000),2000000)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
    p.SetNet(n);p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(pcbnew.VECTOR2I(4000000,4000000));p.SetPosition(pcbnew.VECTOR2I(10000000,10000000))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
    assert contours.audit_board(b)['finding_count']==0
    p.SetSize(pcbnew.VECTOR2I(100000,100000))
    assert contours.audit_board(b)['finding_count']==1


def test_scoped_audit_keeps_retained_neighbor_for_junction_topology():
    b,n=board();a=track(b,n,(10000000,10000000),(10000000,20000000),1000000)
    track(b,n,(10000000,10000000),(20000000,10000000),4000000)
    assert contours.audit_board(b,track_uuid_scope=[a.m_Uuid.AsString()])['finding_count']==1
    assert contours.audit_board(b,track_uuid_scope=[])['finding_count']==0


def test_deadline_is_unknown_not_a_clean_board():
    b,n=board();track(b,n,(10000000,10000000),(10050000,10000000),2000000)
    result=contours.audit_board(b,timeout_s=0)
    assert not result['complete'] and not result['replacement_authorized']


@pytest.mark.parametrize('flush_start,flush_end',[(False,False),(True,False),(False,True),(True,True)])
def test_analytic_elbow_has_clean_constant_width_and_explicit_caps(flush_start,flush_end):
    result=contours.rectilinear_profile([(5,10),(10,10),(10,15)],2,
        flush_start=flush_start,flush_end=flush_end)
    p=Polygon(result['polygon']); coords=result['polygon']
    assert p.is_valid and not p.interiors
    assert all(a[0]==z[0] or a[1]==z[1] for a,z in zip(coords,coords[1:]+coords[:1]))
    assert p.bounds==(5 if flush_start else 4,9,11,15 if flush_end else 16)
    assert p.covers(Polygon([(5,9),(10,9),(10,11),(5,11)]))
    assert p.covers(Polygon([(9,10),(11,10),(11,15),(9,15)]))
    assert not result['replacement_authorized'] and not result['post_fill_width_qualified']


@pytest.mark.parametrize('points',[[(0,0),(1,1)],[(0,0),(0,0)],[(0,0),(1,0),(0,0)]])
def test_planner_refuses_diagonal_zero_length_and_backtrack(points):
    with pytest.raises(ValueError):contours.rectilinear_profile(points,2)


@pytest.mark.parametrize('width',[0,-1,math.nan,math.inf,True])
def test_invalid_width_cannot_become_copper(width):
    with pytest.raises(ValueError):contours.rectilinear_profile([(0,0),(10,0)],width)


def native_join_with_remote_zone_deficit(*,angle=0,mirror=False,gap_nm=500,hole_at_join=False):
    """Real tracks remain copper where native fill has an unrelated strip."""
    import cec_rectilinear_copper as owner
    b,n=board()
    def point(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return x+20000000,y+20000000
    a=track(b,n,point(0,0),point(0,8000000),1000000)
    z=track(b,n,point(0,0),point(8000000,0),1000000)
    zone=pcbnew.ZONE(b);zone.SetNet(n);zone.SetLayer(pcbnew.F_Cu);zone.SetZoneName(owner.ZONE_NAME)
    outline=[(-600000,-600000),(8600000,-600000),(8600000,600000),
             (600000,600000),(600000,8600000),(-600000,8600000)]
    native=pcbnew.SHAPE_POLY_SET();native.NewOutline()
    for q in outline:native.Append(*point(*q))
    zone.Outline().Append(native)
    y0=0 if hole_at_join else 3000000;y1=200000 if hole_at_join else 3400000
    hole=[(500000-gap_nm,y0),(500000,y0),(500000,y1),(500000-gap_nm,y1)]
    native.NewHole(0)
    for q in hole:native.Append(*point(*q),0,0)
    zone.SetFilledPolysList(pcbnew.F_Cu,native);zone.SetIsFilled(True);b.Add(zone)
    return b,a,z,zone


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('gap_nm',[1,500,50000])
def test_local_join_proof_keeps_exact_remote_body_deficit_visible(angle,mirror,gap_nm):
    b,a,z,zone=native_join_with_remote_zone_deficit(angle=angle,mirror=mirror,gap_nm=gap_nm)
    before=[(str(t.m_Uuid.AsString()),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in (a,z)]
    r=contours.audit_board(b,include_terminal_caps=True)
    assert r['complete'] and not r['findings']
    assert r['locally_hidden_join_nonlocal_body_deficit_count']==1
    witness=r['locally_hidden_join_nonlocal_body_deficits'][0]
    assert witness['track_uuid']==a.m_Uuid.AsString()
    assert witness['entire_join_disk_covered_by_saved_purposeful_fill']
    assert not witness['entire_track_capsule_covered_by_saved_zone_fill']
    assert witness['retained_native_track_copper_still_present']
    assert witness['missing_from_zone_fill_area_mm2']>0
    assert not witness['area_or_distance_waiver_used'] and not witness['current_or_release_qualified']
    assert before==[(str(t.m_Uuid.AsString()),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in (a,z)]
    assert not r['replacement_authorized'] and not r['nonlocal_body_deficits_waived_or_current_qualified']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('gap_nm',[1,500,50000])
def test_even_one_nm_missing_from_actual_join_is_not_suppressed(angle,mirror,gap_nm):
    b,*_=native_join_with_remote_zone_deficit(angle=angle,mirror=mirror,gap_nm=gap_nm,hole_at_join=True)
    r=contours.audit_board(b,include_terminal_caps=True)
    assert r['complete']
    assert any(q['type']=='wide_round_elbow' for q in r['findings'])


@pytest.mark.parametrize('invalid',['unfilled','foreign_net','wrong_face','noncanonical_owner','one_join_cap_absent'])
def test_local_join_still_requires_actual_same_face_same_net_canonical_fill(invalid):
    b,a,z,zone=native_join_with_remote_zone_deficit()
    if invalid=='unfilled':zone.SetIsFilled(False)
    elif invalid=='foreign_net':
        other=pcbnew.NETINFO_ITEM(b,'different/rail');b.Add(other);zone.SetNet(other)
    elif invalid=='wrong_face':zone.SetLayer(pcbnew.B_Cu)
    elif invalid=='noncanonical_owner':
        # A label is not a geometry contract. Break an actual native edge,
        # retaining the old saved fill, so this remains a real negative case.
        ring=zone.Outline().Outline(0);p=ring.CPoint(0)
        ring.SetPoint(0,pcbnew.VECTOR2I(p.x+1,p.y))
    else:
        fill=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        cut=pcbnew.SHAPE_POLY_SET();cut.NewOutline()
        for p in [(19400000,19400000),(20600000,19400000),(20600000,20000000),(19400000,20000000)]:cut.Append(*p)
        fill.BooleanSubtract(cut);zone.SetFilledPolysList(pcbnew.F_Cu,fill)
    r=contours.audit_board(b)
    assert r['complete'] and any(q['type']=='wide_round_elbow' for q in r['findings'])
