"""A fixed Source land absorbs only already-owned contacts in actual metal."""
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_leaf as leaf
from cec_native_items import discard_items
from test_measurement_leaf import fixture


def boundary_fixture(quarter=0, *, zone=True, outside=False):
    board, root, land, tracks, xy = fixture('/unrelated_alias', quarter)
    land.SetSize(pcbnew.VECTOR2I_MM(2, 2))
    retained = pcbnew.PCB_TRACK(board)
    retained.SetStart(xy((20, 10))); retained.SetEnd(xy((20.5, 9.5)))
    retained.SetWidth(200000); retained.SetLayer(0); retained.SetNetCode(root.GetNetCode())
    board.Add(retained)
    if zone:
        z = pcbnew.ZONE(board); z.SetLayer(0); z.SetNetCode(root.GetNetCode()); board.Add(z)
        poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
        for point in ((19.5, 5), (21, 5), (21, 14 if outside else 11),
                      (19.5, 14 if outside else 11)):
            p = xy(point); poly.Append(p.x, p.y)
        z.Outline().Append(poly); z.SetFilledPolysList(0, poly)
        z.SetIsFilled(True); z.CacheTriangulation(0)
    proposal = leaf.plan(board, force._uid(root))
    discard_items(board, tracks)
    path = [list(xy(p)) for p in ((10, 10), (12, 12), (20, 12), (20, 10))]
    return board, root, land, retained, proposal, path, xy


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('zone', [False, True])
@pytest.mark.parametrize('compiled', [False, True])
def test_fixed_native_land_absorbs_retained_boundary_contact_only(quarter, zone, compiled):
    board, root, land, retained, proposal, path, _ = boundary_fixture(quarter, zone=zone)
    before = leaf._binding(board)
    options = {'_compiled_guard': leaf.compile_path_guard(board, proposal)} if compiled else {}
    diagnostic = {}
    assert leaf.path_clear(board, proposal, path, diagnostics=diagnostic, **options), diagnostic
    assert leaf._binding(board) == before
    leaf.add_path(board, proposal, path)
    fresh = leaf.plan(board, force._uid(root))
    assert fresh['boundary_uuids'] == proposal['boundary_uuids']
    assert fresh['points_nm'][-1] == proposal['points_nm'][-1]
    assert force._uid(land) in fresh['boundary_uuids']
    assert force._uid(retained) in fresh['boundary_uuids']
    assert not fresh['current_authority'] and not fresh['kelvin_qualified']


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('compiled', [False, True])
@pytest.mark.parametrize('fault', ['outside_land_zone', 'unlisted_contact', 'missing_boundary_land'])
def test_native_land_is_not_whole_net_or_whole_zone_contact_authority(quarter, compiled, fault):
    board, root, land, retained, proposal, path, xy = boundary_fixture(
        quarter, outside=fault == 'outside_land_zone')
    if fault == 'unlisted_contact':
        item = retained.Duplicate(); item.m_Uuid.Clone(pcbnew.KIID())
        item.SetStart(xy((20, 10.4))); item.SetEnd(xy((20.1, 10.5))); board.Add(item)
    elif fault == 'missing_boundary_land':
        proposal = dict(proposal, boundary_uuids=[u for u in proposal['boundary_uuids']
            if u != force._uid(land)])
    before = leaf._binding(board)
    options = {'_compiled_guard': leaf.compile_path_guard(board, proposal)} if compiled else {}
    diagnostic = {}
    assert not leaf.path_clear(board, proposal, path, diagnostics=diagnostic, **options)
    assert diagnostic['reason'] == 'unowned_same_net_contact'
    assert leaf._binding(board) == before


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('compiled', [False, True])
def test_circular_land_does_not_authorize_empty_bounding_box_corners(quarter, compiled):
    board, root, land, retained, proposal, _, xy = boundary_fixture(quarter, zone=False)
    land.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    z = pcbnew.ZONE(board); z.SetLayer(0); z.SetNetCode(root.GetNetCode()); board.Add(z)
    poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
    for p in ((20, 10), (21, 10), (21, 11), (20, 11)):
        at = xy(p); poly.Append(at.x, at.y)
    z.Outline().Append(poly); z.SetFilledPolysList(0, poly)
    z.SetIsFilled(True); z.CacheTriangulation(0)
    # Native Source boundary membership must be rederived, not caller added.
    leaf.add_path(board, proposal, proposal['points_nm'])
    proposal = leaf.plan(board, force._uid(root))
    discard_items(board, [t for t in board.GetTracks()
        if force._uid(t) in proposal['track_uuids']])
    assert force._uid(z) in proposal['boundary_uuids']
    path = [list(xy(p)) for p in ((10, 10), (12, 12), (20.75, 12), (20.75, 10.75), (20, 10))]
    options = {'_compiled_guard': leaf.compile_path_guard(board, proposal)} if compiled else {}
    diagnostic = {}
    assert not leaf.path_clear(board, proposal, path, diagnostics=diagnostic, **options)
    assert diagnostic['reason'] == 'unowned_same_net_contact'
    assert diagnostic['uuid'] == force._uid(z)
