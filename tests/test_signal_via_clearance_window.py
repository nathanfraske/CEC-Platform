"""Checked signal windows do not authorize power cuts or ordinary trace cuts."""
import copy
import inspect
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_signal_via_clearance_window as operation
import cec_zone_fill as fill
from test_field_proposals import track
from test_ground_via_clearance_window import rectangle
from test_ordinary_native_portals import fixture as ordinary_fixture


def fixture(tmp_path, *, quarter=0, back=False, net='/renamed/CONTROL'):
    source, board, _ = ordinary_fixture(tmp_path, net=net, quarter=quarter, back=back)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    pad = next(iter(next(iter(board.GetFootprints())).Pads()))
    dx, dy = ((0, 1200000), (1200000, 0), (0, -1200000), (-1200000, 0))[quarter]
    at = pad.GetPosition()+pcbnew.VECTOR2I(dx, dy)
    for name in ('GND', 'UNRELATED_POWER'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for layer in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(board); zone.SetNet(board.FindNet('GND')); zone.SetLayer(layer)
        zone.SetLocalClearance(200000); zone.SetMinThickness(100000)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        zone.Outline().NewOutline()
        for x, y in ((1, 1), (29, 1), (29, 29), (1, 29)):
            zone.Outline().Append(x*1000000, y*1000000)
        board.Add(zone)
    foreign = pcbnew.ZONE(board); foreign.SetNet(board.FindNet('UNRELATED_POWER'))
    foreign.SetLayer(pcbnew.F_Cu if back else pcbnew.B_Cu)
    foreign.SetZoneName('arbitrary retained foreign metal')
    foreign.SetLocalClearance(200000); foreign.SetMinThickness(100000)
    foreign.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    foreign.Outline().NewOutline()
    for x, y in ((-900000, -900000), (900000, -900000),
                 (900000, 900000), (-900000, 900000)):
        foreign.Outline().Append(at.x+x, at.y+y)
    board.Add(foreign)
    selected = pcbnew.ZONES()
    for zone in board.Zones(): selected.append(zone)
    fill.compile_selected(board, selected, initialize_selected=True)
    field._save_field_snapshot(board, source)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), position_nm=list(at))
    return pcbnew.LoadBoard(str(source)), source, args, force._uid(foreign)


def saved(tmp_path, **options):
    board, source, args, foreign = fixture(tmp_path, **options)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'candidate')
    return source, Path(result['candidate']), args, proposal, foreign


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_real_native_signal_window_replayed_in_cardinal_frames(tmp_path, quarter, back):
    source, child, args, proposal, foreign = saved(tmp_path, quarter=quarter, back=back)
    raw = source.read_bytes()
    result = operation.receive(source, child, **args)
    assert result['ok'] and result['complete'], result
    assert result['construction']['full_Source_ordinary_class_dimensions']
    assert result['construction']['surface_leg_does_not_cross_Source_foreign_copper']
    assert result['construction']['surface_clearance_changes_confined_to_via_window']
    assert result['construction']['all_face_native_new_hole_geometry_received']
    assert result['construction']['local_foreign_subtractions'][0]['zero_loss_outside_Source_envelope']
    assert result['original_native_partitions_preserved']
    assert result['window_is_not_itself_an_open_count_progress_claim']
    assert not result['release_authority'] and not result['current_capacity_qualified']
    assert (proposal['width_nm'], proposal['diameter_nm'], proposal['drill_nm']) == (220000, 600000, 300000)
    assert proposal['foreign_zones'][0]['uuid'] == foreign and source.read_bytes() == raw


@pytest.mark.parametrize('net', ['+3V3', 'GND_RETURN', '/VCC_RAW', '/USB_D_P',
    '/USB_D_N', '/SENSEC1_HI', '/SENSEC1_LO', '/CLOCK', '/SB_SENSE0'])
def test_power_pair_Kelvin_and_unresolved_sensitive_roles_cannot_borrow_signal_authority(tmp_path, net):
    board, source, args, _ = fixture(tmp_path, net=net)
    with pytest.raises(ValueError, match='not_positively_ordinary'):
        operation.plan(source, **args)


@pytest.mark.parametrize('pin', ['power_in', 'power_out'])
def test_neutral_spelling_does_not_hide_a_saved_supply_pin(tmp_path, pin):
    board, source, args, _ = fixture(tmp_path)
    pad, _ = operation._pad(board, args['pad_uuid']); pad.SetPinType(pin)
    field._save_field_snapshot(board, source)
    with pytest.raises(ValueError, match='not_positively_ordinary'):
        operation.plan(source, **args)


@pytest.mark.parametrize('fault', ['width', 'drill', 'axis', 'unlock', 'part', 'extra_track',
    'Source_pad', 'zone_outline', 'zone_clearance', 'sidecar', 'foreign_saved_net'])
def test_exact_saved_reconstruction_rejects_every_unowned_delta(tmp_path, fault):
    source, child, args, proposal, foreign = saved(tmp_path)
    board = pcbnew.LoadBoard(str(child)); old = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via = next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t) not in old)
    if fault == 'width': via.SetWidth(via.GetWidth()+1)
    elif fault == 'drill': via.SetDrill(via.GetDrillValue()+1)
    elif fault == 'axis': via.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'unlock': via.SetLocked(False)
    elif fault == 'part': next(iter(board.GetFootprints())).SetValue('not Source')
    elif fault == 'extra_track': track(board, proposal['net'], (25, 25), (26, 25), width=.22)
    elif fault == 'Source_pad': operation._pad(board, args['pad_uuid'])[0].Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'zone_outline': next(z for z in board.Zones() if force._uid(z)==foreign).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'zone_clearance': next(z for z in board.Zones() if force._uid(z)==foreign).SetLocalClearance(200001)
    elif fault == 'sidecar': child.with_suffix('.kicad_pro').write_text('{}')
    else: via.SetNet(board.FindNet('UNRELATED_POWER'))
    if fault != 'sidecar':
        # Deliberately malformed evidence bypasses the normal snapshot writer.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), board)
    result = operation.receive(source, child, **args)
    assert not result['ok'] and not result['complete'] and result['errors']


@pytest.mark.parametrize('fault', ['foreign_track', 'surface_pour', 'DNP', 'hole', 'noncanonical', 'remote'])
def test_Source_obstacles_and_exact_launch_are_not_window_permission(tmp_path, fault):
    board, source, args, foreign = fixture(tmp_path)
    pad, face = operation._pad(board, args['pad_uuid']); at = args['position_nm']
    if fault == 'foreign_track': track(board, 'UNRELATED_POWER',
        ((at[0]-1000000)/1e6, at[1]/1e6), ((at[0]+1000000)/1e6, at[1]/1e6), layer=pcbnew.In2_Cu)
    elif fault == 'surface_pour':
        zone = next(z for z in board.Zones() if force._uid(z)==foreign); zone.SetLayer(face)
        selected = pcbnew.ZONES(); selected.append(zone); fill.compile_selected(board, selected, initialize_selected=True)
    elif fault == 'DNP': pad.GetParentFootprint().SetDNP(True)
    elif fault == 'hole':
        via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet()); via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetWidth(600000); via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    elif fault == 'noncanonical': args['position_nm'][0] += 1
    else: args['position_nm'][1] += 3000000
    if fault in ('foreign_track', 'surface_pour', 'DNP', 'hole'):
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source), board)
    with pytest.raises(ValueError):
        proposal = operation.plan(source, **args)
        operation.write_private(proposal, tmp_path/'bad')


@pytest.mark.parametrize('key, value', [('width_nm', 1), ('diameter_nm', 100000),
    ('drill_nm', 100000), ('net', '+3V3'), ('foreign_zones', []), ('clearance_nm', 1)])
def test_caller_does_not_supply_dimensions_electrical_role_or_allowed_cut(tmp_path, key, value):
    board, source, args, _ = fixture(tmp_path)
    proposal = operation.plan(source, **args); forged = copy.deepcopy(proposal); forged[key] = value
    with pytest.raises(ValueError, match='fresh_exact'):
        operation.write_private(forged, tmp_path/'forged')


@pytest.mark.parametrize('value', [0, 11, True, float('nan')])
def test_each_native_constituent_has_a_ten_second_limit(tmp_path, value):
    with pytest.raises(ValueError):
        operation.plan(tmp_path/'missing', board_hint='synthetic', pad_uuid='x', position_nm=[0, 0], timeout_s=value)


def test_late_identity_hash_cannot_outlive_receiving_deadline(tmp_path, monkeypatch):
    source, child, args, _, _ = saved(tmp_path)
    offset = [0.]; real_now, real_hash = time.monotonic, force._hash
    monkeypatch.setattr(operation, 'time', SimpleNamespace(monotonic=lambda: real_now()+offset[0]))
    def slow_tail(path, *a, **kw):
        result = real_hash(path, *a, **kw)
        if not offset[0] and Path(path)==source:
            for frame in inspect.stack():
                if frame.filename==operation.__file__ and frame.function=='receive' and 'paired' in frame.frame.f_locals:
                    offset[0] = 11.; break
        return result
    monkeypatch.setattr(force, '_hash', slow_tail)
    result = operation.receive(source, child, **args)
    assert offset[0] == 11. and not result['ok'] and not result['complete']
    assert any('Source_signal_window_deadline' in error for error in result['errors'])


def test_local_window_must_not_split_a_foreign_terminal_partition(tmp_path):
    board, source, args, foreign = fixture(tmp_path); x, y = args['position_nm']
    zone = next(z for z in board.Zones() if force._uid(z)==foreign)
    zone.Outline().RemoveAllContours(); zone.Outline().NewOutline()
    for dx, dy in ((-150000, -2000000), (150000, -2000000), (150000, 2000000), (-150000, 2000000)):
        zone.Outline().Append(x+dx, y+dy)
    for index, delta in enumerate((-1500000, 1500000)):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('UNRELATED_END_'+str(index)); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(zone.GetNet())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I(300000, 300000))
        pad.SetPosition(pcbnew.VECTOR2I(x, y+delta)); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers = pcbnew.LSET(); layers.AddLayer(zone.GetLayer()); pad.SetLayerSet(layers); fp.Add(pad)
    selected = pcbnew.ZONES(); selected.append(zone); fill.compile_selected(board, selected, initialize_selected=True)
    field._save_field_snapshot(board, source)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'split')
    received = operation.receive(source, Path(result['candidate']), **args)
    assert not received['ok'] and any('demoted_a_retained_native_partition' in e for e in received['errors'])


def test_typed_transaction_has_no_dimension_or_electrical_scope_override():
    import root_receive_local_transaction_20261022 as receiving
    row = dict(kind='source_ordinary_signal_window', pad_uuid='actual-source-land', position_nm=[123, 456],
        candidate='/untrusted/proposal/board.kicad_pcb', candidate_sha256='0'*64)
    assert receiving.validate_phases([row]) == ['source_ordinary_signal_window']
    assert receiving.validate_phases([row, dict(row, pad_uuid='second-Source-land')]) == [row['kind']]*2
    with pytest.raises(ValueError): receiving.validate_phases([row, row])
    for key, value in (('width_nm', 1), ('allow_power_cut', True), ('current_a', .01), ('zone_uuids', ['caller'])):
        with pytest.raises(ValueError, match='exact_typed_local_phase_schema'):
            receiving.validate_phases([dict(row, **{key: value})])
    for value in (None, [], [True, 1], [1., 2], [1, 2, 3]):
        with pytest.raises(ValueError): receiving.validate_phases([dict(row, position_nm=value)])


def surface_fixture(tmp_path, *, long=False, crosses=False):
    board, source, args, uid = fixture(tmp_path)
    pad, face = operation._pad(board, args['pad_uuid'])
    x, y = pad.GetPosition(); args['position_nm'] = [x, y+(1500000 if long else 1200000)]
    zone = next(z for z in board.Zones() if force._uid(z)==uid)
    zone.SetLayer(face); zone.SetLocalClearance(200000 if long else 500000)
    zone.Outline().RemoveAllContours(); zone.Outline().NewOutline()
    near_x = x-200000 if crosses else x+(200000 if long else 400000)
    near_y = y+(650000 if long else 1000000)
    for a, b in ((near_x, near_y), (x+1800000, near_y),
                 (x+1800000, y+2400000), (near_x, y+2400000)):
        zone.Outline().Append(a, b)
    selected = pcbnew.ZONES(); selected.append(zone)
    fill.compile_selected(board, selected, initialize_selected=True)
    field._save_field_snapshot(board, source)
    return source, args


def test_surface_clearance_may_approach_the_same_checked_via_window_but_not_cross_copper(tmp_path):
    source, args = surface_fixture(tmp_path)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'local-clearance')
    received = operation.receive(source, Path(result['candidate']), **args)
    assert received['ok'] and received['construction']['surface_clearance_changes_confined_to_via_window'], received


def test_a_signal_window_is_never_a_surface_route_across_Source_copper(tmp_path):
    source, args = surface_fixture(tmp_path, crosses=True)
    with pytest.raises(ValueError, match='surface_leg_crosses_retained_foreign_copper'):
        operation.plan(source, **args)


def test_source_leg_clearance_cannot_extend_the_via_window_into_a_routing_corridor(tmp_path):
    source, args = surface_fixture(tmp_path, long=True)
    proposal = operation.plan(source, **args)
    with pytest.raises(ValueError, match='outside_Source_envelope'):
        operation.write_private(proposal, tmp_path/'not-a-track-window')


@pytest.mark.parametrize('foreign_fill', [False, True])
def test_even_fill_only_forgery_inside_the_local_envelope_needs_exact_native_replay(tmp_path, foreign_fill):
    source, child, args, proposal, foreign = saved(tmp_path)
    board = pcbnew.LoadBoard(str(child))
    zone = next(z for z in board.Zones() if force._uid(z)==foreign) if foreign_fill else next(z for z in board.Zones() if z.GetNetname()=='GND')
    layer = zone.GetLayer(); at = args['position_nm']
    actual = zone.GetFilledPolysList(layer).CloneDropTriangulation()
    actual.BooleanSubtract(rectangle(at[0]+410000, at[1]-10000, at[0]+430000, at[1]+10000))
    zone.SetFilledPolysList(layer, actual)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), board)
    result = operation.receive(source, child, **args)
    assert not result['ok'] and any('complete_independent_Source_replay' in e for e in result['errors']), result


def test_late_writer_identity_tail_is_included_in_its_ten_second_lease(tmp_path, monkeypatch):
    board, source, args, _ = fixture(tmp_path); proposal = operation.plan(source, **args)
    offset = [0.]; real_now, real_hash = time.monotonic, force._hash
    monkeypatch.setattr(operation, 'time', SimpleNamespace(monotonic=lambda: real_now()+offset[0]))
    def slow_tail(path, *a, **kw):
        result = real_hash(path, *a, **kw)
        if not offset[0]:
            for frame in inspect.stack():
                if frame.filename==operation.__file__ and frame.function=='write_private' and 'target' in frame.frame.f_locals:
                    offset[0] = 11.; break
        return result
    monkeypatch.setattr(force, '_hash', slow_tail)
    with pytest.raises(ValueError, match='Source_signal_window_deadline'):
        operation.write_private(proposal, tmp_path/'late-writer')
    assert offset[0] == 11.


def test_saved_new_hole_rule_area_is_not_an_antipad_permission(tmp_path):
    board, source, args, _ = fixture(tmp_path); x, y = args['position_nm']
    area = pcbnew.ZONE(board); area.SetIsRuleArea(True); area.SetDoNotAllowVias(True)
    area.SetLayer(pcbnew.In2_Cu); area.Outline().NewOutline()
    for dx, dy in ((-500000, -500000), (500000, -500000), (500000, 500000), (-500000, 500000)):
        area.Outline().Append(x+dx, y+dy)
    board.Add(area); field._save_field_snapshot(board, source)
    proposal = operation.plan(source, **args)
    with pytest.raises(ValueError, match='native rule area excludes via land'):
        operation.write_private(proposal, tmp_path/'forbidden-hole')


def test_larger_saved_board_minimum_wins_over_class_via_preference(tmp_path):
    board, source, args, _ = fixture(tmp_path)
    data = json.loads(source.with_suffix('.kicad_pro').read_text())
    data['board'] = dict(design_settings=dict(rules=dict(min_via_diameter=.8)))
    source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    proposal = operation.plan(source, **args)
    assert proposal['diameter_nm'] == 800000 and proposal['drill_nm'] == 300000
    result = operation.write_private(proposal, tmp_path/'full-board-floor')
    assert operation.receive(source, Path(result['candidate']), **args)['ok']


def test_edge_clearance_is_not_a_via_window_permission(tmp_path):
    board, source, args, _ = fixture(tmp_path)
    pad, _ = operation._pad(board, args['pad_uuid'])
    pad.GetParentFootprint().Move(pcbnew.VECTOR2I(900000-pad.GetPosition().x, 0))
    args['position_nm'] = [100000, pad.GetPosition().y]
    field._save_field_snapshot(board, source)
    with pytest.raises(ValueError, match='hole_or_edge'):
        operation.plan(source, **args)


def test_actual_phase_dispatch_replays_saved_signal_window_and_rejects_injection(tmp_path):
    import root_receive_local_transaction_20261022 as receiving
    source, child, args, _, _ = saved(tmp_path)
    row = dict(kind='source_ordinary_signal_window', pad_uuid=args['pad_uuid'], position_nm=args['position_nm'],
        candidate=str(child), candidate_sha256=force._hash(child))
    actual, result = receiving.receive_phase(source, source, row, 'synthetic')
    assert actual == child and result['ok'] and result['complete']
    with pytest.raises(ValueError, match='exact_typed_local_phase_schema'):
        receiving.receive_phase(source, source, dict(row, current_a=.01), 'synthetic')


def test_Source_clipping_removes_native_extra_copper_without_waiving_any_spill_or_nonlocal_loss():
    before = rectangle(0, 0, 10000000, 10000000)
    region = rectangle(4000000, 4000000, 6000000, 6000000)
    native = before.CloneDropTriangulation()
    native.BooleanSubtract(rectangle(4500000, 4500000, 5500000, 5500000))
    native.BooleanAdd(rectangle(11000000, 11000000, 12000000, 12000000))
    constrained, proof = operation._source_clipped_native_fill(before, native, region, time.monotonic()+10.)
    spill = constrained.CloneDropTriangulation(); spill.BooleanSubtract(before)
    assert not spill.OutlineCount() and proof['zero_foreign_spill']
    assert proof['literal_integer_loss_vertices_inside_via_window']
    assert proof['Source_intersection_is_construction_not_a_spill_tolerance']
    bad = native.CloneDropTriangulation(); bad.BooleanSubtract(rectangle(0, 0, 100000, 100000))
    with pytest.raises(ValueError, match='outside_Source_envelope'):
        operation._source_clipped_native_fill(before, bad, region, time.monotonic()+10.)


def test_native_component_marker_rebuild_does_not_alias_disconnected_polygons():
    board = pcbnew.CreateEmptyBoard(); zone = pcbnew.ZONE(board); zone.SetLayer(pcbnew.B_Cu)
    net = pcbnew.NETINFO_ITEM(board, 'arbitrary real net'); board.Add(net); zone.SetNet(net)
    board.Add(zone); original = rectangle(0, 0, 1000000, 1000000)
    original.Append(rectangle(2000000, 0, 3000000, 1000000))
    zone.SetFilledPolysList(pcbnew.B_Cu, original); zone.SetIsFilled(True)
    zone.SetIsIsland(pcbnew.B_Cu, 1)
    # Reordered native positive records must carry their actual old marker,
    # not the previous array index.
    replacement = rectangle(2000000, 0, 3000000, 1000000)
    replacement.Append(rectangle(0, 0, 1000000, 1000000))
    operation._reinstall_native_faces(zone, {int(pcbnew.B_Cu): replacement}, time.monotonic()+10., source_zone=zone)
    # The owner restores compiled record order as well as actual markers,
    # without depending on clearing an old cache index.
    assert not zone.IsIsland(pcbnew.B_Cu, 0) and zone.IsIsland(pcbnew.B_Cu, 1)
    assert zone.GetFilledPolysList(pcbnew.B_Cu).Outline(0).BBox().GetX() == 0


def test_clipping_must_not_copy_one_native_nonisland_marker_to_split_fragments():
    board = pcbnew.CreateEmptyBoard(); zone = pcbnew.ZONE(board); zone.SetLayer(pcbnew.B_Cu); board.Add(zone)
    net = pcbnew.NETINFO_ITEM(board, 'arbitrary real net'); board.Add(net); zone.SetNet(net)
    original = rectangle(0, 0, 3000000, 1000000)
    zone.SetFilledPolysList(pcbnew.B_Cu, original); zone.SetIsFilled(True)
    split = rectangle(0, 0, 1000000, 1000000); split.Append(rectangle(2000000, 0, 3000000, 1000000))
    with pytest.raises(ValueError, match='component_split_requires_independent_native_anchor_owner'):
        operation._reinstall_native_faces(zone, {int(pcbnew.B_Cu): split}, time.monotonic()+10., source_zone=zone)


def test_stricter_saved_hole_spacing_is_installed_before_the_new_hole_probe(tmp_path):
    board, source, args, _ = fixture(tmp_path); x, y = args['position_nm']
    via = pcbnew.PCB_VIA(board); via.SetNet(board.FindNet('GND'))
    via.SetPosition(pcbnew.VECTOR2I(x+900000, y)); via.SetWidth(600000); via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    selected = pcbnew.ZONES()
    for zone in board.Zones(): selected.append(zone)
    fill.compile_selected(board, selected, initialize_selected=True); field._save_field_snapshot(board, source)
    data = json.loads(source.with_suffix('.kicad_pro').read_text())
    data['board'] = dict(design_settings=dict(rules=dict(min_hole_to_hole=.8)))
    source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='hole_or_edge'):
        operation.plan(source, **args)
