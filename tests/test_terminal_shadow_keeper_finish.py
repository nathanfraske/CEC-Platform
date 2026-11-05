"""Synthetic geometry/current-contract fixtures, never a hardware rating."""
import copy
from pathlib import Path
import pcbnew
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_terminal_shadow_keeper_finish as owner
from test_lastmile import _board


def fixture(tmp_path, monkeypatch, *, quarter=0, mirror=False, face=pcbnew.F_Cu, load=False):
    b = _board([], edge=(0, 0, 60, 60)); b.SetCopperLayerCount(6)
    props = b.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'; b.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(b, '/SYNTHETIC_TERMINAL_GEOMETRY_NOT_A_CURRENT_RATING'); b.Add(net)
    def at(x, y):
        if mirror: x = -x
        for _ in range(quarter): x, y = -y, x
        return pcbnew.VECTOR2I(round((30+x)*1e6), round((30+y)*1e6))
    vias = []
    for x in (-3, 0):
        v = pcbnew.PCB_VIA(b); v.SetNet(net); v.SetPosition(at(x, 0)); v.SetWidth(900000)
        v.SetDrill(300000); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetLocked(True); b.Add(v); vias.append(v)
    def track(a, z):
        t = pcbnew.PCB_TRACK(b); t.SetNet(net); t.SetLayer(face); t.SetWidth(600000)
        t.SetStart(at(*a)); t.SetEnd(at(*z)); t.SetLocked(True); b.Add(t); return t
    body = track((-3, 0), (0, 0)); tail = track((0, 0), (.2, 0))
    if load:
        fp = pcbnew.FOOTPRINT(b); b.Add(fp); fp.SetReference('PHYSICAL_LOAD_NOT_DISCARDABLE')
        pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('1'); pad.SetNet(net)
        pad.SetPosition(at(.49, 0)); pad.SetSize(pcbnew.VECTOR2I_MM(.03, .05))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers = pcbnew.LSET(); layers.AddLayer(face); pad.SetLayerSet(layers)
    pieces = [Polygon(owner.native.purposeful_envelope(owner.native._native_capsule(t),
        style='chamfer45', margin_nm=1000, grid_nm=1000)) for t in (body, tail)]
    pieces += [Polygon(owner.centered.centered_cover(b, v, face, 900000)) for v in vias]
    poly = unary_union(pieces)
    zone = pcbnew.ZONE(b); zone.SetNet(net); zone.SetLayer(face); zone.SetZoneName(owner.native.ZONE_NAME)
    zone.SetAssignedPriority(0); zone.SetLocalClearance(200000); zone.SetMinThickness(100000)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); zone.SetCornerSmoothingType(0); zone.SetLocked(True)
    zone.Outline().Append(owner.native._poly([[int(x), int(y)] for x, y in list(poly.exterior.coords)[:-1]])); b.Add(zone)
    # An unrelated reference sheet is literal Source evidence, not permission
    # to refill it during a terminal-contour transaction.
    gnd = pcbnew.NETINFO_ITEM(b, 'GND'); b.Add(gnd)
    ground = pcbnew.ZONE(b); ground.SetNet(gnd); ground.SetLayer(pcbnew.In1_Cu)
    ground.SetMinThickness(100000); ground.SetLocalClearance(200000); ground.Outline().NewOutline()
    for point in [(1000000, 1000000), (59000000, 1000000), (59000000, 59000000), (1000000, 59000000)]:
        ground.Outline().Append(*point)
    b.Add(ground); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir(); owner.field._save_field_snapshot(b, source)
    monkeypatch.setattr(owner.current, '_model', lambda *a: ('synthetic_geometry_not_hardware', {},
        dict(explicit_synthetic_not_a_hardware_budget=True)))
    monkeypatch.setattr(owner.current, '_source_width_floor', lambda *a: 400000)
    return source, dict(board_hint='renamed_synthetic_terminal_geometry', zone_uuid=owner.force._uid(zone),
        track_uuids=[owner.force._uid(tail)], allow_locked_source=True), owner.force._uid(body)


def saved(tmp_path, monkeypatch, **kwargs):
    source, request, body = fixture(tmp_path, monkeypatch, **kwargs)
    proposal = owner.plan(source, **request); board = owner.construct(source, proposal)
    child = owner.force._copy_family(source, tmp_path/'candidate'); owner.field._save_field_snapshot(board, child)
    return source, child, proposal, body


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_native_terminal_shadow_rebuild_has_actual_visible_progress_and_retains_contacts(tmp_path, monkeypatch, quarter, mirror, face):
    source, child, proposal, body = saved(tmp_path, monkeypatch, quarter=quarter, mirror=mirror, face=face)
    raw = source.read_bytes(); proof = owner.receive_literal(source, child, proposal)
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_other_native_items_and_ground_sheets_literal']
    assert proof['every_surviving_native_partition_preserved']
    assert proof['actual_saved_progress']['removed_native_area_mm2'] >= .0025
    assert proof['actual_saved_progress']['saved_trace_length_mm'] == pytest.approx(.2)
    assert proof['actual_saved_progress']['every_original_surviving_keeper_contact_material_preserved']
    assert source.read_bytes() == raw and not proof['current_or_barrel_qualified'] and not proof['release_authority']
    assert body in proposal['retained_track_uuids'] and len(proposal['retained_centered_frames']) == 2


@pytest.mark.parametrize('fault', ['points', 'current', 'source', 'tracks', 'profile', 'authority'])
def test_stale_or_rehashed_native_plan_cannot_change_the_cut_or_current_contract(tmp_path, monkeypatch, fault):
    source, child, proposal, _ = saved(tmp_path, monkeypatch); bad = copy.deepcopy(proposal)
    if fault == 'points': bad['points_nm'][0][0] += 1
    elif fault == 'current': bad['full_source_current_width_floor_nm'] = 1
    elif fault == 'source': bad['source_sha256'] = '0'*64
    elif fault == 'tracks': bad['track_uuids'] = bad['retained_track_uuids']
    elif fault == 'profile': bad['source_current_contract'] = dict(invented_rating=True)
    else: bad['authority_sha256'] = '0'*64
    proof = owner.receive_literal(source, child, bad)
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']


@pytest.mark.parametrize('fault', ['width', 'drill', 'ground', 'text', 'owner', 'new_track'])
def test_saved_mutants_cannot_hide_unowned_changes_behind_a_success_flag(tmp_path, monkeypatch, fault):
    source, child, proposal, body = saved(tmp_path, monkeypatch)
    b = pcbnew.LoadBoard(str(child))
    if fault == 'width': next(t for t in b.GetTracks() if owner.force._uid(t) == body).SetWidth(599999)
    elif fault == 'drill': next(t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA').SetDrill(310000)
    elif fault == 'ground': next(z for z in b.Zones() if z.GetNetname() == 'GND').UnFill()
    elif fault == 'text':
        text = pcbnew.PCB_TEXT(b); text.SetText('UNOWNED'); text.SetLayer(pcbnew.B_SilkS); b.Add(text)
    elif fault == 'owner': next(z for z in b.Zones() if owner.force._uid(z) == proposal['zone_uuid']).SetMinThickness(99999)
    else:
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(10, 10)); t.SetEnd(pcbnew.VECTOR2I_MM(11, 10)); t.SetWidth(200000); b.Add(t)
    owner.field._save_field_snapshot(b, child)
    proof = owner.receive_literal(source, child, proposal)
    assert not proof['ok'] and proof['errors']


def test_actual_load_contact_inside_old_excess_prevents_its_retirement(tmp_path, monkeypatch):
    source, request, _ = fixture(tmp_path, monkeypatch, load=True); proposal = owner.plan(source, **request)
    with pytest.raises(ValueError, match='original_terminal_contact_outside_derived_profile'):
        owner.construct(source, proposal)


@pytest.mark.parametrize('fault', ['lock', 'missing', 'body', 'empty', 'truthy', 'floor'])
def test_unknown_ownership_or_source_width_never_becomes_cut_authority(tmp_path, monkeypatch, fault):
    source, request, body = fixture(tmp_path, monkeypatch)
    if fault == 'lock': request['allow_locked_source'] = False
    elif fault == 'missing': request['zone_uuid'] = 'MISSING'
    elif fault == 'body': request['track_uuids'] = [body]
    elif fault == 'empty': request['track_uuids'] = []
    elif fault == 'truthy': request['allow_locked_source'] = 1
    else: monkeypatch.setattr(owner.current, '_source_width_floor', lambda *a: 600001)
    raw = source.read_bytes()
    with pytest.raises(ValueError): owner.plan(source, **request)
    assert source.read_bytes() == raw


def test_readonly_discovery_rederives_actual_native_geometry_without_board_specifics(tmp_path, monkeypatch):
    source, request, _ = fixture(tmp_path, monkeypatch); raw = source.read_bytes()
    found = owner.discover(source, board_hint=request['board_hint'], allow_locked_source=True)
    assert found['ok'] and found['complete'] and len(found['proposals']) == 1
    assert found['proposals'][0]['target']['track_uuids'] == request['track_uuids']
    assert not found['actual_geometry_constructed'] and not found['release_authority'] and source.read_bytes() == raw


@pytest.mark.parametrize('value', [True, 0, 33])
def test_discovery_budget_is_typed_and_finite(tmp_path, monkeypatch, value):
    source, request, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError): owner.discover(source, board_hint=request['board_hint'], maximum_trials=value)
