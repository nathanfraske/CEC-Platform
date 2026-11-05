"""Native pin escape proposals have no routing or fabrication authority."""
import math
import pcbnew
import pytest
import cec_escape_frontier as frontier
import cec_fr as fr
from test_escape_frontier import native_fixture,run_native


def sites(board,pad,nc,layer,**kwargs):
    opts=dict(radius_nm=8000000,diameter_nm=600000,clearance_nm=200000,
              stub_layer=int(layer),stub_width_nm=200000)
    opts.update(kwargs)
    return frontier.native_escape_sites(board,tuple(pad.GetPosition()),int(nc),**opts)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_wide_inner_shadow_has_guarded_off_grid_sites_without_copper_changes(quarter,back):
    b,p,nc,lay,v=native_fixture(quarter=quarter,back=back)
    original=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
              for t in b.GetTracks()]
    points=sites(b,p,nc,lay)
    assert points==sites(b,p,nc,lay) and 0<len(points)<=64
    assert all(0<math.dist(q,tuple(p.GetPosition()))<=8000000 for q in points)
    assert any(fr._via_spot_clear(b,pcbnew.VECTOR2I(*q),600000,200000,{nc},
        drill_nm=300000,net_code=nc) for q in points)
    ops,d=run_native(b,p,nc,lay,v,obstacle_channel_axes=True)
    assert ops and any(e['counters'].get('native_obstacle_seat_proposals')
                      for e in d['endpoints'])
    assert [(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
            for t in b.GetTracks()]==original
    for o in ops:
        if o[0]=='trk':assert fr._tap_foreign_clear(b,o[1],o[2],o[3],o[4],200000,{nc})
        else:assert o[2]>=.3 and o[3]>=.6
    assert not d['release_authority'] and not d['no_path_proof']


@pytest.mark.parametrize('opts',[dict(radius_nm=8000001),dict(max_axes=9),
    dict(diameter_nm=0),dict(clearance_nm=-1),dict(stub_layer=999),
    dict(stub_width_nm=True),dict(radius_nm=float('inf'))])
def test_invalid_or_unbounded_menus_refused(opts):
    b,p,nc,lay,v=native_fixture()
    with pytest.raises(ValueError):sites(b,p,nc,lay,**opts)


def test_future_power_guard_still_refuses_native_escape_menu(monkeypatch):
    b,p,nc,lay,v=native_fixture()
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[dict(
        net='/OTHER',layer='In3.Cu',x0=21,y0=31,x1=39,y1=49)])
    ops,d=run_native(b,p,nc,lay,v,obstacle_channel_axes=True)
    assert ops is None and len(list(b.GetTracks()))==2
    assert d['endpoints'][0]['counters']['native_obstacle_seat_proposals']<=64


def test_dense_surface_aliases_cannot_evict_wide_inner_shadow_boundaries():
    b,p,nc,lay,v=native_fixture()
    for x in (29.5,29.6,29.7,30.3,30.4,30.5):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('renamed_obstacle_'+str(x));b.Add(fp)
        q=pcbnew.PAD(fp);q.SetNumber('any');q.SetNet(b.FindNet('/OTHER'))
        q.SetAttribute(pcbnew.PAD_ATTRIB_SMD);q.SetShape(pcbnew.PAD_SHAPE_RECT)
        q.SetLayerSet(pcbnew.PAD.SMDMask());q.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
        q.SetPosition(pcbnew.VECTOR2I_MM(x,40.1));fp.Add(q)
    points=sites(b,p,nc,lay)
    assert any(abs(y-40000000)>4500000 for _,y in points)


@pytest.mark.parametrize('flag',[None,1,'yes'])
def test_mode_requires_literal_boolean(flag):
    b,p,nc,lay,v=native_fixture()
    with pytest.raises(ValueError,match='bridge_obstacle_axes'):
        run_native(b,p,nc,lay,v,obstacle_channel_axes=flag)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_inner_current_width_does_not_abort_bounded_native_menu(quarter,back):
    b,p,nc,lay,v=native_fixture(quarter=quarter,back=back)
    original=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
              for t in b.GetTracks()]
    points=sites(b,p,nc,lay,stub_width_nm=5719035)
    assert points==sites(b,p,nc,lay,stub_width_nm=5719035) and len(points)<=64
    assert all(0<math.dist(q,tuple(p.GetPosition()))<=8000000 for q in points)
    assert [(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
            for t in b.GetTracks()]==original


@pytest.mark.parametrize('width',[2000001,78297620,1000000000,2147483647])
def test_trace_width_never_expands_escape_search_or_creates_copper(width):
    b,p,nc,lay,v=native_fixture()
    old_count=len(list(b.GetTracks()))
    points=sites(b,p,nc,lay,stub_width_nm=width)
    assert len(points)<=64 and all(all(type(c) is int for c in q) for q in points)
    assert all(0<math.dist(q,tuple(p.GetPosition()))<=8000000 for q in points)
    assert len(list(b.GetTracks()))==old_count


def test_wide_stub_inflates_its_own_face_at_the_actual_contract(monkeypatch):
    import cec_maze_channels as channels
    b,p,nc,lay,v=native_fixture()
    x,y=tuple(p.GetPosition())
    monkeypatch.setattr(channels,'native_obstacle_boxes',lambda board,layer,*args:
        [(x-100000,y-100000,x+100000,y+100000)] if layer==lay else [])
    small=sites(b,p,nc,lay,stub_width_nm=200000)
    wide=sites(b,p,nc,lay,stub_width_nm=5719035)
    assert small and wide and set(small)!=set(wide)
    assert max(max(abs(q[0]-x),abs(q[1]-y)) for q in small)<=601000
    assert any(max(abs(q[0]-x),abs(q[1]-y))>3000000 for q in wide)


@pytest.mark.parametrize('width',[0,-1,2147483648,True,2.1e6,float('nan'),float('inf')])
def test_invalid_native_width_cannot_borrow_wide_bus_proposals(width):
    b,p,nc,lay,v=native_fixture()
    with pytest.raises(ValueError,match='bounded_native_escape_geometry'):
        sites(b,p,nc,lay,stub_width_nm=width)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_whole_current_landing_menu_preserves_bounds_without_barrel_authority(quarter,back):
    b,p,nc,lay,v=native_fixture(quarter=quarter,back=back)
    old_count=len(list(b.GetTracks()))
    points=sites(b,p,nc,lay,diameter_nm=6019035,stub_width_nm=5719035)
    assert points==sites(b,p,nc,lay,diameter_nm=6019035,stub_width_nm=5719035)
    assert len(points)<=64 and all(0<math.dist(q,tuple(p.GetPosition()))<=8000000 for q in points)
    assert len(list(b.GetTracks()))==old_count


@pytest.mark.parametrize('diameter',[2000001,78297620,1000000000,2147483647])
def test_large_land_cannot_expand_finite_native_search_or_create_a_via(diameter):
    b,p,nc,lay,v=native_fixture()
    old_count=len(list(b.GetTracks()))
    points=sites(b,p,nc,lay,diameter_nm=diameter)
    assert len(points)<=64 and all(0<math.dist(q,tuple(p.GetPosition()))<=8000000 for q in points)
    assert len(list(b.GetTracks()))==old_count


@pytest.mark.parametrize('diameter',[0,-1,2147483648,True,2.1e6,float('nan'),float('inf')])
def test_invalid_native_diameter_is_still_rejected(diameter):
    b,p,nc,lay,v=native_fixture()
    with pytest.raises(ValueError,match='bounded_native_escape_geometry'):
        sites(b,p,nc,lay,diameter_nm=diameter)
