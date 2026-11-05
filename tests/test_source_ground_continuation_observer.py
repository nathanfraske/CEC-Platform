"""Mixed Source Ground continuation never substitutes for live local returns.

The Source role/assignment seed is the existing test-only continuation fixture.
The complete compiler, native connectivity/fills and return observer are real;
no successful graph, compiler packet or receiving verdict is supplied by a mock.
"""
import copy
import time

import pcbnew
import pytest

import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_shortcut as reference
import cec_source_ground_boundary_connection as observer
import cec_source_ground_continuation as continuation
from cec_native_items import discard_items
from test_source_ground_continuation import fixture as continuation_source
from test_source_ground_boundary_connection import fixture as incident_source


def _via(board, at):
    via = pcbnew.PCB_VIA(board)
    via.SetNet(board.FindNet('GND'))
    via.SetPosition(pcbnew.VECTOR2I(*at))
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)
    return via


def _filled_plane(board, face):
    zone = pcbnew.ZONE(board); zone.SetNet(board.FindNet('GND')); zone.SetLayer(face)
    polygon = pcbnew.SHAPE_POLY_SET(); polygon.NewOutline()
    for x, y in ((0, 0), (30, 0), (30, 30), (0, 30)):
        polygon.Outline(0).Append(x*1000000, y*1000000)
    zone.Outline().Append(polygon)
    zone.SetFilledPolysList(face, polygon); zone.SetIsFilled(True); board.Add(zone)


def _fixture(tmp_path, monkeypatch, *, quarter=0, back=False, prefix='observer_cell'):
    parts = continuation_source(tmp_path, monkeypatch, quarter=quarter, back=back, prefix=prefix)
    source, parent, unused, base_proposal, ids, roots, tail_uid = parts
    augmented = pcbnew.LoadBoard(str(source))
    props = augmented.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    augmented.SetProperties(props)
    for face in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        _filled_plane(augmented, face)
    tail = next(t for t in augmented.GetTracks() if force._uid(t) == tail_uid)
    # The retained fixed tail really reaches a filled reference plane. It is
    # not joined to the moving land by a Source net label or a zone UUID.
    retained_via = _via(augmented, tuple(tail.GetEnd()))
    retained_via_uuid = force._uid(retained_via)
    field._save_field_snapshot(augmented, source)
    parent = pcbnew.LoadBoard(str(source))
    started = time.monotonic()
    board, packet = compiler.compile(source, base_proposal['poses'], board_hint='opaque',
        additional_obstacle_track_uuids=ids, timeout_s=10.)
    assert time.monotonic()-started <= 10.
    assert packet['source_family_and_code_unchanged']
    boundaries = {k:r for k,r in packet['requests'].items()
        if r['kind'] == 'source_boundary' and r['net'] == 'GND'
        and any(a.get('kind') == continuation.KIND for a in
            r.get('exact_additional_macro_component_source_ownership', []))}
    assert len(boundaries) == 1
    key, request = next(iter(boundaries.items()))
    assert {a['kind'] for a in request['exact_additional_macro_component_source_ownership']} == {
        'positive_existing_low_power_ground_boundary', continuation.KIND}
    assert set(ids) <= set(packet['retired_track_uuids'])
    assert all('source_owned_barrel_roots' not in a for a in
        request['exact_additional_macro_component_source_ownership'] if a['kind'] == continuation.KIND)
    local_vias = {}
    for ground_key, ground in packet['requests'].items():
        if ground['kind'] == 'ground':
            via = _via(board, tuple(ground['a']['at_nm']))
            local_vias[ground['a']['pad_uuid']] = force._uid(via)
    assert local_vias
    return dict(source=source, parent=parent, board=board, packet=packet, key=key,
        request=request, requests=packet['requests'], local_vias=local_vias,
        retained_via_uuid=retained_via_uuid, ids=ids)


def _prepare(case, *, requests=None, packet=None):
    actual_packet = case['packet'] if packet is None else packet
    return observer._prepare_observer(case['parent'], case['requests'] if requests is None else requests,
        board_hint='opaque', source_proposal=actual_packet['source_plan'],
        source_macro_packet=actual_packet, timeout_s=10.)


def _assert_live_returns(case):
    pads = {force._uid(p):p for f in case['board'].GetFootprints() for p in f.Pads()}
    for ground in case['requests'].values():
        if ground['kind'] != 'ground':
            continue
        value = cells._existing_return(case['board'], pads[ground['a']['pad_uuid']],
            ground['reach_mm'], allow_native_track_body=True)
        assert value is not None and value[0] == 0
        assert reference._reference_contacts(case['board'], value[1])


@pytest.mark.parametrize('quarter,back', [(0,False), (1,False), (2,True), (3,True)])
def test_fixture_really_compiles_mixed_request_and_joins_native_filled_components(
        tmp_path, monkeypatch, quarter, back):
    case = _fixture(tmp_path, monkeypatch, quarter=quarter, back=back)
    _assert_live_returns(case)
    pads = {force._uid(p):p for f in case['board'].GetFootprints() for p in f.Pads()}
    tracks = {force._uid(t):t for t in case['board'].GetTracks()}
    keys = []
    for end in ('a', 'b'):
        port = case['request'][end]
        if port.get('pad_uuid'):
            keys.append(force._item_key(pads[port['pad_uuid']]))
        else:
            keys.extend(force._item_key(tracks[uid]) for uid in port['native_uuids'])
    native = observer.partitions._inventory(case['board'], time.monotonic()+10.,
        dict(items=16384, polygons=4096, vertices=200000))
    assert keys and all(k in native['component_of'] for k in keys)
    assert len({native['component_of'][k] for k in keys}) == 1


@pytest.mark.parametrize('quarter,back', [(0,False), (1,False), (2,True), (3,True)])
def test_fresh_complete_compiler_mixed_component_with_real_fill_and_local_returns(
        tmp_path, monkeypatch, quarter, back):
    case = _fixture(tmp_path, monkeypatch, quarter=quarter, back=back,
        prefix='different_identity' if quarter else 'observer_cell')
    before = [row._source_binding(case[name]) for name in ('parent', 'board')]
    source_bytes = case['source'].read_bytes()
    _assert_live_returns(case)
    live = _prepare(case)
    proof = live(case['board'], timeout_s=10.)[case['key']]
    assert proof and proof['all_named_contacts_connected']
    assert proof['actual_native_filled_island_connectivity_proved']
    assert proof['independently_received_local_ground_returns']
    assert not proof['whole_zone_uuid_connectivity_credit']
    assert proof['remote_smd_return_not_inferred'] is True
    assert proof['new_copper'] == proof['new_holes'] == 0
    assert not proof['current_qualified'] and not proof['routing_admitted'] and not proof['release_authority']
    assert before == [row._source_binding(case[name]) for name in ('parent', 'board')]
    assert source_bytes == case['source'].read_bytes()


def test_legacy_direct_pad_incident_authority_still_passes(tmp_path, monkeypatch):
    parent, board, request, requests, proposal = incident_source(tmp_path, monkeypatch)
    proof = observer.observe(parent, board, request, requests, board_hint='opaque',
        source_proposal=proposal, timeout_s=10.)
    assert proof and proof['all_named_contacts_connected']


def _positive(case):
    live = _prepare(case)
    assert live(case['board'], timeout_s=10.)[case['key']] is not None
    return live


@pytest.mark.parametrize('fault', ['missing_macro', 'missing_explicit_cut', 'missing_fresh_authority',
    'changed_root', 'direct_root_alias', 'serialized_request_only'])
def test_complete_serialized_continuation_cannot_supply_fresh_compiler_authority(
        tmp_path, monkeypatch, fault):
    case = _fixture(tmp_path, monkeypatch)
    _positive(case)
    packet = copy.deepcopy(case['packet'])
    requests = copy.deepcopy(case['requests'])
    if fault == 'missing_macro':
        live = observer._prepare_observer(case['parent'], requests, board_hint='opaque',
            source_proposal=packet['source_plan'], timeout_s=10.)
    else:
        if fault == 'missing_explicit_cut':
            packet['explicit_additional_obstacle_track_uuids'] = []
        elif fault == 'missing_fresh_authority':
            packet['additional_source_boundary_ownership'] = [r for r in
                packet['additional_source_boundary_ownership'] if r['authority']['kind'] != continuation.KIND]
        elif fault == 'changed_root':
            authority = next(a for a in requests[case['key']]['exact_additional_macro_component_source_ownership']
                if a['kind'] == continuation.KIND)
            authority['root_authorities'][0]['source_pad_roots'][0]['pad_uuid'] = 'not-a-source-land'
            authority['source_ground_continuation']['existing_root_authorities'] = copy.deepcopy(
                authority['root_authorities'])
        elif fault == 'direct_root_alias':
            authority = next(a for a in requests[case['key']]['exact_additional_macro_component_source_ownership']
                if a['kind'] == continuation.KIND)
            authority['kind'] = 'positive_existing_low_power_ground_boundary'
            authority['source_owned_barrel_roots'] = []
            authority['source_pad_roots'] = copy.deepcopy(authority['root_authorities'][0]['source_pad_roots'])
        else:
            # A caller-authored packet whose serialized request list mirrors
            # the forgery is still not a fresh full Source compilation.
            requests[case['key']]['width_nm'] += 1
            packet['requests'] = copy.deepcopy(requests)
        live = _prepare(case, requests=requests, packet=packet)
    assert live(case['board'], timeout_s=10.)[case['key']] is None


@pytest.mark.parametrize('fault', ['drop_continuations', 'extra_field', 'changed_point',
    'new_native_contact', 'changed_return_role'])
def test_original_mixed_source_request_must_match_even_if_marker_is_removed(
        tmp_path, monkeypatch, fault):
    case = _fixture(tmp_path, monkeypatch)
    _positive(case)
    requests = copy.deepcopy(case['requests']); request = requests[case['key']]
    if fault == 'drop_continuations':
        request['exact_additional_macro_component_source_ownership'] = [a for a in
            request['exact_additional_macro_component_source_ownership'] if a['kind'] != continuation.KIND]
    elif fault == 'extra_field':
        request['caller_connection_promise'] = True
    elif fault == 'changed_point':
        request['a']['at_nm'][0] += 1
    elif fault == 'new_native_contact':
        end = next(e for e in ('a', 'b') if request[e].get('native_uuids'))
        request[end]['native_uuids'] = [next(iter(case['local_vias'].values()))]
    else:
        authority = next(a for a in request['exact_additional_macro_component_source_ownership']
            if a['kind'] == continuation.KIND)
        authority['root_authorities'][0]['source_pad_roots'][0]['role'] = 'power_input'
        authority['source_ground_continuation']['existing_root_authorities'] = copy.deepcopy(
            authority['root_authorities'])
    assert _prepare(case, requests=requests)(case['board'], timeout_s=10.)[case['key']] is None


def _boundary_pad(case):
    return next(case['request'][end]['pad_uuid'] for end in ('a', 'b')
        if case['request'][end].get('pad_uuid'))


@pytest.mark.parametrize('fault', ['missing_local_barrel', 'unfilled_reference', 'missing_reference',
    'missing_ground_request', 'changed_reach', 'changed_barrel_process'])
def test_missing_or_unknown_actual_return_never_uses_continuation_as_return_credit(
        tmp_path, monkeypatch, fault):
    case = _fixture(tmp_path, monkeypatch)
    live = _positive(case)
    pad_uid = _boundary_pad(case)
    if fault == 'missing_local_barrel':
        discard_items(case['board'], [t for t in case['board'].GetTracks()
            if force._uid(t) == case['local_vias'][pad_uid]])
        pad = next(p for f in case['board'].GetFootprints() for p in f.Pads() if force._uid(p) == pad_uid)
        assert cells._existing_return(case['board'], pad,
            case['requests']['ground:'+pad_uid]['reach_mm'], allow_native_track_body=True) is None
    elif fault == 'unfilled_reference':
        for zone in case['board'].Zones():
            zone.UnFill()
    elif fault == 'missing_reference':
        discard_items(case['board'], [next(iter(case['board'].Zones()))])
    elif fault in ('missing_ground_request', 'changed_reach'):
        requests = copy.deepcopy(case['requests'])
        if fault == 'missing_ground_request':
            del requests['ground:'+pad_uid]
        else:
            requests['ground:'+pad_uid]['reach_mm'] += .1
        live = _prepare(case, requests=requests)
    else:
        via = next(t for t in case['board'].GetTracks() if force._uid(t) == case['local_vias'][pad_uid])
        via.SetDrill(via.GetWidth())
    assert live(case['board'], timeout_s=10.)[case['key']] is None


def test_same_zone_uuid_with_disconnected_actual_fill_refuses_despite_local_returns(
        tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)
    live = _positive(case)
    before = sorted(force._uid(z) for z in case['board'].Zones())
    vias = [t for t in case['board'].GetTracks() if t.GetClass() == 'PCB_VIA']
    islands = pcbnew.SHAPE_POLY_SET()
    for via in vias:
        at = via.GetPosition(); index = islands.NewOutline()
        for dx, dy in ((-400000,-400000), (400000,-400000), (400000,400000), (-400000,400000)):
            islands.Outline(index).Append(at.x+dx, at.y+dy)
    for zone in case['board'].Zones():
        zone.SetFilledPolysList(zone.GetLayer(), islands); zone.SetIsFilled(True)
    _assert_live_returns(case)
    assert before == sorted(force._uid(z) for z in case['board'].Zones())
    assert live(case['board'], timeout_s=10.)[case['key']] is None


@pytest.mark.parametrize('fault', ['parent_native', 'source_bytes', 'source_sidecar'])
def test_prepared_continuation_observer_rechecks_live_source_identity(tmp_path, monkeypatch, fault):
    case = _fixture(tmp_path, monkeypatch)
    live = _positive(case)
    if fault == 'parent_native':
        edge = next(t for t in case['parent'].GetTracks() if force._uid(t) in case['ids'])
        edge.SetWidth(edge.GetWidth()+1)
    elif fault == 'source_bytes':
        case['source'].write_bytes(case['source'].read_bytes()+b'\n')
    else:
        project = case['source'].with_suffix('.kicad_pro')
        project.write_bytes(project.read_bytes()+b'\n')
    with pytest.raises(ValueError, match='epoch_or_geometry_changed'):
        live(case['board'], timeout_s=10.)


def test_independent_compilation_is_fresh_but_live_graph_and_return_are_not_cached(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)
    original = compiler.compile; calls = []
    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        return result
    monkeypatch.setattr(compiler, 'compile', counted)
    live = _prepare(case)
    assert calls == [True]
    assert live(case['board'], timeout_s=10.)[case['key']] is not None
    assert live(case['board'], timeout_s=10.)[case['key']] is not None
    assert calls == [True]
    pad_uid = _boundary_pad(case)
    discard_items(case['board'], [t for t in case['board'].GetTracks()
        if force._uid(t) == case['local_vias'][pad_uid]])
    assert live(case['board'], timeout_s=10.)[case['key']] is None
    assert calls == [True]


@pytest.mark.parametrize('timeout', [True, 0., -1., 10.000001, float('nan'), float('inf')])
def test_observer_constituents_cannot_be_unbounded(timeout):
    with pytest.raises(ValueError, match='bounded_source_ground_boundary_observer_context_required'):
        observer._prepare_observer(None, {}, board_hint='opaque', source_proposal={}, timeout_s=timeout)


def test_expired_actual_preparation_lease_is_not_renewed(tmp_path, monkeypatch):
    case = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='deadline'):
        observer._prepare_observer(case['parent'], case['requests'], board_hint='opaque',
            source_proposal=case['packet']['source_plan'], source_macro_packet=case['packet'],
            timeout_s=.000001)
