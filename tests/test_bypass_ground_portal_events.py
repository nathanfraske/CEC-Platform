"""Retained Ground-root seats are proposals, never hole/process waivers."""
import math
import time

import pcbnew
import pytest

import cec_bypass_ground_portal_events as op
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_escape_pose_frontier as frontier
import cec_force_current as force
from test_cell_retained_ground_barrel import fixture
from test_escape_pose_frontier import two_follower_fixture
from test_field_proposals import track


def menu(b, source, pad, **options):
    cap = pad.GetParentFootprint()
    # Keep the native owner alive while its borrowed footprint is inspected.
    parent = pcbnew.LoadBoard(str(source))
    prior = parent.FindFootprintByReference(cap.GetReference())
    owner = b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR')
    return op.events(b, cap, owner.FindPadByNumber('6'), prior,
        max_shift_mm=options.pop('max_shift_mm', 6.),
        deadline=options.pop('deadline', time.monotonic()+10.), **options)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_literal_barrel_roots_propose_native_transformed_land_seats_without_mutation(
        tmp_path, quarter, mirror, layer):
    b, source, pad, via, _ = fixture(tmp_path, quarter, mirror, layer)
    before = row._source_binding(b)
    digest = force._hash(source)
    proof = menu(b, source, pad)
    assert proof['complete'] and proof['sites']
    assert proof['source_reference_portals'] == 1
    assert len(proof['sites']) <= 16
    cap = pad.GetParentFootprint()
    old = tuple(cap.GetPosition())
    offset = tuple(pad.GetPosition()[i]-old[i] for i in (0, 1))
    rail = cap.FindPadByNumber('1')
    rail_delta = tuple(rail.GetPosition()[i]-pad.GetPosition()[i] for i in (0, 1))
    owner = b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR')
    supply = tuple(owner.FindPadByNumber('6').GetPosition())
    for site in proof['sites']:
        assert site['target_via_uuid'] == force._uid(via)
        assert site['target_via_nm'] == list(via.GetPosition())
        assert len(site['actual_saved_reference_contacts']) == 2
        assert site['ground_nm'] == [site['position_nm'][i]+offset[i] for i in (0, 1)]
        assert math.dist(site['position_nm'], old) <= 6000000
        assert math.dist([site['ground_nm'][i]+rail_delta[i] for i in (0, 1)], supply) <= 3500000
        assert site['octilinear_return_upper_bound_mm'] <= .8+1e-9
    assert row._source_binding(b) == before and force._hash(source) == digest
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert not proof['no_path_proof']


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_real_retained_portal_choice_passes_existing_live_return_guard_without_another_hole(tmp_path, layer):
    b, source, pad, via, _ = fixture(tmp_path, layer=layer)
    cap = pad.GetParentFootprint()
    before = row._source_binding(b)
    old = cap.GetPosition()
    proof = menu(b, source, pad, max_sites=64)
    found = []
    try:
        for site in proof['sites']:
            cap.SetPosition(pcbnew.VECTOR2I(*site['position_nm']))
            choices = escape.retained_ground_barrel_ops(b, pad, deadline=time.monotonic()+10.)
            if choices:
                found.append(site)
        assert found
        assert len([t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']) == 2
        assert via.GetWidth(layer) == 600000 and via.GetDrillValue() == 300000
    finally:
        cap.SetPosition(old)
    assert row._source_binding(b) == before


@pytest.mark.parametrize('fault', ['unfilled', 'missing_plane', 'no_profile', 'blind', 'foreign'])
def test_no_fictitious_plane_barrel_or_filename_permission(tmp_path, fault):
    b, source, pad, via, _ = fixture(tmp_path)
    if fault == 'unfilled':
        next(iter(b.Zones())).UnFill()
    elif fault == 'missing_plane':
        b.Remove(next(iter(b.Zones())))
    elif fault == 'no_profile':
        props = b.GetProperties(); props['CEC_FAB_PROFILE'] = ''; b.SetProperties(props)
    elif fault == 'blind':
        via.SetViaType(pcbnew.VIATYPE_BLIND); via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu)
    else:
        via.SetNet(b.FindNet('+3V3'))
    before = row._source_binding(b)
    proof = menu(b, source, pad)
    assert not proof['sites'] and not proof['source_reference_portals']
    assert row._source_binding(b) == before and not proof['no_path_proof']


@pytest.mark.parametrize('foreign_face', [pcbnew.In2_Cu, pcbnew.B_Cu])
def test_existing_root_does_not_waive_foreign_copper_or_fabrication(tmp_path, foreign_face):
    b, source, pad, via, _ = fixture(tmp_path)
    track(b, '+3V3', (8.5, 8.4), (11.5, 8.4), width=1.5, layer=foreign_face)
    cap = pad.GetParentFootprint(); old = cap.GetPosition()
    before = row._source_binding(b)
    proof = menu(b, source, pad)
    assert proof['sites']  # The read-only proposal is not clearance authority.
    try:
        for site in proof['sites']:
            cap.SetPosition(pcbnew.VECTOR2I(*site['position_nm']))
            assert not escape.retained_ground_barrel_ops(b, pad, deadline=time.monotonic()+10.)
    finally:
        cap.SetPosition(old)
    assert row._source_binding(b) == before


def test_bounded_menu_shares_slots_between_actual_reference_roots(tmp_path):
    b, source, pad, via, _ = fixture(tmp_path)
    second = pcbnew.PCB_VIA(b); second.SetNet(b.FindNet('GND'))
    second.SetPosition(pcbnew.VECTOR2I_MM(11.2, 8.4))
    second.SetWidth(600000); second.SetDrill(300000)
    second.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(second)
    before = row._source_binding(b)
    proof = menu(b, source, pad, max_sites=2)
    assert len(proof['sites']) == 2 and proof['source_reference_portals'] == 2
    assert {r['target_via_uuid'] for r in proof['sites']} == {force._uid(via), force._uid(second)}
    assert row._source_binding(b) == before


@pytest.mark.parametrize('field,value', [
    ('reach_mm', .800001), ('reach_mm', True), ('reach_mm', 0),
    ('max_shift_mm', 0), ('max_shift_mm', 32.01), ('max_shift_mm', float('nan')),
    ('max_sites', True), ('max_sites', 0), ('max_sites', 65), ('deadline', float('inf'))])
def test_search_budgets_are_explicit_finite_and_never_extended(tmp_path, field, value):
    b, source, pad, *_ = fixture(tmp_path)
    before = row._source_binding(b)
    with pytest.raises(ValueError):
        menu(b, source, pad, **{field:value})
    assert row._source_binding(b) == before


def test_expired_observation_is_not_a_no_path_proof(tmp_path):
    b, source, pad, *_ = fixture(tmp_path)
    before = row._source_binding(b)
    proof = menu(b, source, pad, deadline=time.monotonic()-1.)
    assert not proof['complete'] and proof['deadline_exhausted'] and not proof['sites']
    assert not proof['no_path_proof'] and row._source_binding(b) == before


@pytest.mark.parametrize('accepted', [True, False])
def test_follower_really_tries_root_event_but_still_requires_live_return_receiving(
        tmp_path, monkeypatch, accepted):
    b, source, selected, caps, path = two_follower_fixture(tmp_path)
    chosen = caps[0]; selected = {chosen.GetReference():selected[chosen.GetReference()]}
    before = row._source_binding(b); digest = force._hash(path)
    target = (17173000, 16261000); calls = []
    monkeypatch.setattr(frontier, '_surface_obstacles', lambda *a, **kw:([], [], lambda *a:0))
    monkeypatch.setattr(frontier, '_surface_hits', lambda *a, **kw:[])
    monkeypatch.setattr(frontier, 'courtyard_screen', lambda *a, **kw:dict(ok=True))
    monkeypatch.setattr(frontier, '_bypass_courtyard_events', lambda *a, **kw:[])
    def event(board, cap, *a, **kw):
        calls.append(cap.GetOrientationDegrees())
        return dict(sites=[dict(supply_distance_mm=1.2, position_nm=list(target),
            orientation_deg=0)] if cap.GetOrientationDegrees() == 0 else [])
    monkeypatch.setattr(op, 'events', event)
    monkeypatch.setattr(frontier, 'ground_screen', lambda *a, **kw:dict(
        ok=accepted and tuple(chosen.GetPosition()) == target and chosen.GetOrientationDegrees() == 0))
    proof = frontier.follower_frontier(b, source, selected, board_path='opaque',
        max_shift_mm=8., deadline=time.monotonic()+10.)
    assert calls == [0, 90, 180, -90]
    assert proof['retained_ground_portal_event_count'] == 1
    assert proof['ok'] == accepted
    if accepted:
        assert tuple(chosen.GetPosition()) == target
    else:
        assert row._source_binding(b) == before
    assert force._hash(path) == digest
