"""Real native local antipads, not a permission to consume protected pours."""
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
import cec_ground_via_clearance_window as operation
import cec_zone_fill as fill
from test_existing_local_pofv_pad_rule import case
from test_field_proposals import track


def fixture(tmp_path, *, quarter=0, face=pcbnew.F_Cu):
    board, source, pad = case(tmp_path, quarter*90, face)
    for layer in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetNet(board.FindNet('GND'))
        zone.SetLayer(layer)
        zone.SetLocalClearance(200000)
        zone.SetMinThickness(100000)
        zone.Outline().NewOutline()
        for x, y in ((1, 1), (39, 1), (39, 39), (1, 39)):
            zone.Outline().Append(x*1000000, y*1000000)
        board.Add(zone)
    foreign = pcbnew.ZONE(board)
    foreign.SetNet(board.FindNet('obstruction'))
    foreign.SetLayer(pcbnew.B_Cu if face == pcbnew.F_Cu else pcbnew.F_Cu)
    foreign.SetZoneName('ARBITRARY_RETAINED_POWER')
    foreign.SetLocalClearance(200000)
    foreign.SetMinThickness(100000)
    foreign.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    foreign.Outline().NewOutline()
    at = pad.GetPosition()
    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        foreign.Outline().Append(at.x+x*1000000, at.y+y*1000000)
    board.Add(foreign)
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        selected.append(zone)
    fill.compile_selected(board, selected, initialize_selected=True)
    field._save_field_snapshot(board, source)
    board = pcbnew.LoadBoard(str(source))
    return board, source, force._uid(pad), force._uid(foreign)


def saved(tmp_path, **options):
    board, source, uid, foreign = fixture(tmp_path, **options)
    args = dict(board_hint='synthetic', pad_uuid=uid)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'candidate')
    return source, Path(result['candidate']), args, proposal, foreign


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_source_contained_ground_entry_is_replayed_in_cardinal_frames(tmp_path, quarter, face):
    source, child, args, proposal, foreign = saved(tmp_path, quarter=quarter, face=face)
    raw = source.read_bytes()
    result = operation.receive(source, child, **args)
    assert result['ok'] and result['complete'], result
    assert result['original_native_partitions']['joined_Source_ground_partitions'] == 1
    assert result['construction']['Ground_return_mm'] == 0.
    assert result['construction']['all_face_native_via_geometry_received']
    assert result['construction']['local_foreign_subtractions'][0]['zero_loss_outside_Source_envelope']
    assert result['exact_native_Source_reconstruction_received']
    assert not result['current_capacity_qualified'] and not result['release_authority']
    assert source.read_bytes() == raw
    assert proposal['foreign_zones'][0]['uuid'] == foreign


@pytest.mark.parametrize('fault', ['width', 'drill', 'axis', 'unlocked', 'part',
    'extra_track', 'Source_track', 'zone_outline', 'zone_clearance', 'sidecar', 'group'])
def test_no_unowned_saved_delta_can_enter_through_the_antipad_exception(tmp_path, fault):
    source, child, args, proposal, foreign = saved(tmp_path)
    board = pcbnew.LoadBoard(str(child))
    old = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via = next(t for t in board.GetTracks() if force._uid(t) not in old)
    if fault == 'width': via.SetWidth(via.GetWidth()+1)
    elif fault == 'drill': via.SetDrill(via.GetDrillValue()+1)
    elif fault == 'axis': via.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'unlocked': via.SetLocked(False)
    elif fault == 'part': next(iter(board.GetFootprints())).SetValue('NOT_THE_SOURCE_PART')
    elif fault == 'extra_track': track(board, 'GND', (30, 30), (31, 30), width=.2)
    elif fault == 'Source_track':
        next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(200001)
    elif fault == 'zone_outline':
        zone = next(z for z in board.Zones() if force._uid(z)==foreign)
        zone.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'zone_clearance':
        next(z for z in board.Zones() if force._uid(z)==foreign).SetLocalClearance(200001)
    elif fault == 'sidecar':
        data = json.loads(child.with_suffix('.kicad_pro').read_text())
        data['foreign_mutation'] = True
        child.with_suffix('.kicad_pro').write_text(json.dumps(data))
    else:
        next(g for g in board.Groups() if g.ContainsItem(via)).RemoveItem(via)
    if fault != 'sidecar': field._save_field_snapshot(board, child)
    result = operation.receive(source, child, **args)
    assert not result['ok'] and not result['complete'] and result['errors'], result


def rectangle(x0, y0, x1, y1):
    result = pcbnew.SHAPE_POLY_SET()
    idx = result.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        result.Append(x, y, idx)
    return result


def test_native_local_window_is_not_a_general_foreign_refill_permission():
    before = rectangle(0, 0, 10000000, 10000000)
    region = rectangle(4000000, 4000000, 6000000, 6000000)
    after = before.CloneDropTriangulation()
    after.BooleanSubtract(rectangle(4500000, 4500000, 5500000, 5500000))
    proof = operation._local_subtraction(before, after, region, time.monotonic()+10.)
    assert proof['zero_foreign_spill'] and proof['zero_loss_outside_Source_envelope']
    bad = after.CloneDropTriangulation()
    bad.BooleanSubtract(rectangle(0, 0, 100000, 100000))
    with pytest.raises(ValueError, match='outside_Source_envelope'):
        operation._local_subtraction(before, bad, region, time.monotonic()+10.)
    bad = after.CloneDropTriangulation()
    bad.BooleanAdd(rectangle(11000000, 11000000, 12000000, 12000000))
    with pytest.raises(ValueError, match='added_foreign_power'):
        operation._local_subtraction(before, bad, region, time.monotonic()+10.)
    with pytest.raises(ValueError, match='actual_native_clearance'):
        operation._local_subtraction(before, before, region, time.monotonic()+10.)


@pytest.mark.parametrize('key, value', [('diameter_nm', 100000), ('pad_uuid', 'unknown'),
    ('at_nm', [0, 0]), ('existing_group_uuid', 'unknown')])
def test_untrusted_proposal_does_not_supply_geometry_or_scope(tmp_path, key, value):
    board, source, uid, _ = fixture(tmp_path)
    proposal = operation.plan(source, board_hint='synthetic', pad_uuid=uid)
    forged = copy.deepcopy(proposal)
    forged[key] = value
    with pytest.raises(ValueError):
        operation.write_private(forged, tmp_path/'forged')


@pytest.mark.parametrize('value', [0, 11, True, float('nan')])
def test_ten_second_constituent_limit_is_not_optional(tmp_path, value):
    with pytest.raises(ValueError):
        operation.plan(tmp_path/'missing', board_hint='synthetic', pad_uuid='x', timeout_s=value)


def test_transaction_window_phase_accepts_only_an_actual_land_identity():
    import root_receive_local_transaction_20261022 as receiving
    row = dict(kind='source_contained_ground_window', pad_uuid='not-a-board-or-refdes',
        candidate='/untrusted/request/board.kicad_pcb', candidate_sha256='0'*64)
    assert receiving.validate_phases([row]) == ['source_contained_ground_window']
    for key, value in (('width_nm', 1), ('allow_power_cut', True),
                       ('current_a', .01), ('zone_uuids', ['caller-allowed'])):
        with pytest.raises(ValueError, match='exact_typed_local_phase_schema'):
            receiving.validate_phases([dict(row, **{key: value})])
    for value in (None, '', True, ['unknown']):
        with pytest.raises(ValueError):
            receiving.validate_phases([dict(row, pad_uuid=value)])


def test_even_a_fill_only_forgery_inside_the_local_envelope_needs_exact_native_replay(tmp_path):
    source, child, args, proposal, foreign = saved(tmp_path)
    board = pcbnew.LoadBoard(str(child))
    zone = next(z for z in board.Zones() if force._uid(z)==foreign)
    face = zone.GetLayer()
    at = proposal['at_nm']
    actual = zone.GetFilledPolysList(face).CloneDropTriangulation()
    actual.BooleanSubtract(rectangle(at[0]+410000, at[1]-10000, at[0]+430000, at[1]+10000))
    zone.SetFilledPolysList(face, actual)
    # Deliberately forge a saved file, bypassing our writer's independent
    # hole-bridge representation guard; the receiver must still reject it.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child), board)
    result = operation.receive(source, child, **args)
    assert not result['ok'] and not result['complete']
    assert any('complete_independent_Source_replay' in error for error in result['errors'])


@pytest.mark.parametrize('fault', ['no_rule', 'locked_group', 'unknown_profile', 'DNP',
    'wrong_net', 'small_land', 'foreign_track', 'foreign_pad', 'duplicate_hole'])
def test_actual_source_geometry_and_process_are_not_caller_assertions(tmp_path, fault):
    board, source, uid, _ = fixture(tmp_path)
    pad, _ = operation.access._pad(board, uid)
    if fault == 'no_rule': source.with_suffix('.kicad_dru').unlink()
    elif fault == 'locked_group': next(iter(board.Groups())).SetLocked(True)
    elif fault == 'unknown_profile':
        props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'unknown'; board.SetProperties(props)
    elif fault == 'DNP': pad.GetParentFootprint().SetDNP(True)
    elif fault == 'wrong_net': pad.SetNet(board.FindNet('obstruction'))
    elif fault == 'small_land': pad.SetSize(pcbnew.VECTOR2I(100000, 100000))
    elif fault == 'foreign_track':
        at = pad.GetPosition()
        track(board, 'obstruction', (at.x/1e6-1, at.y/1e6),
            (at.x/1e6+1, at.y/1e6), layer=pcbnew.In2_Cu, width=.2)
    elif fault == 'foreign_pad':
        other = pad.GetParentFootprint().FindPadByNumber('3')
        other.SetPosition(pad.GetPosition())
    else:
        # Select an actual VIA, never silently reinterpret the fixture track.
        via = next(v for v in board.GetTracks() if v.GetClass()=='PCB_VIA').Duplicate()
        via.m_Uuid.Clone(pcbnew.KIID()); via.SetPosition(pad.GetPosition()); board.Add(via)
    if fault != 'no_rule': field._save_field_snapshot(board, source)
    with pytest.raises(ValueError):
        operation.plan(source, board_hint='synthetic', pad_uuid=uid)


def test_a_window_cannot_split_an_existing_foreign_conductor_component(tmp_path):
    board, source, uid, foreign = fixture(tmp_path)
    pad, _ = operation.access._pad(board, uid)
    at = pad.GetPosition()
    zone = next(z for z in board.Zones() if force._uid(z)==foreign)
    zone.Outline().RemoveAllContours(); zone.Outline().NewOutline()
    for x, y in ((-150000, -2000000), (150000, -2000000),
                 (150000, 2000000), (-150000, 2000000)):
        zone.Outline().Append(at.x+x, at.y+y)
    for index, delta in enumerate((-1500000, 1500000)):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('ARBITRARY_FORCE_END_'+str(index)); board.Add(fp)
        end = pcbnew.PAD(fp); end.SetNumber('1'); end.SetNet(zone.GetNet())
        end.SetShape(pcbnew.PAD_SHAPE_RECT); end.SetSize(pcbnew.VECTOR2I(300000, 300000))
        end.SetPosition(pcbnew.VECTOR2I(at.x, at.y+delta)); end.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers = pcbnew.LSET(); layers.AddLayer(zone.GetLayer()); end.SetLayerSet(layers); fp.Add(end)
    selected = pcbnew.ZONES(); selected.append(zone)
    fill.compile_selected(board, selected, initialize_selected=True)
    field._save_field_snapshot(board, source)
    args = dict(board_hint='synthetic', pad_uuid=uid)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'split')
    received = operation.receive(source, Path(result['candidate']), **args)
    assert not received['ok'] and not received['complete']
    assert any('demoted_a_retained_native_partition' in error for error in received['errors'])


def test_already_connected_nonlocal_ground_is_not_false_open_progress(tmp_path):
    board, source, uid, _ = fixture(tmp_path)
    pad, face = operation.access._pad(board, uid)
    seed = pad.GetParentFootprint().FindPadByNumber('2')
    track(board, 'GND', [v/1e6 for v in pad.GetPosition()],
        [v/1e6 for v in seed.GetPosition()], layer=face, width=.2)
    field._save_field_snapshot(board, source)
    args = dict(board_hint='synthetic', pad_uuid=uid)
    proposal = operation.plan(source, **args)
    result = operation.write_private(proposal, tmp_path/'not-an-open')
    received = operation.receive(source, Path(result['candidate']), **args)
    assert not received['ok'] and not received['complete']
    assert any('close_a_real_native_Ground_island' in error for error in received['errors'])


def test_receiving_deadline_includes_the_final_live_identity_tail(tmp_path, monkeypatch):
    source, child, args, _, _ = saved(tmp_path)
    offset = [0.]
    real_now, real_hash = time.monotonic, force._hash
    monkeypatch.setattr(operation, 'time', SimpleNamespace(monotonic=lambda: real_now()+offset[0]))
    def slow_final_hash(path, *a, **kw):
        answer = real_hash(path, *a, **kw)
        if not offset[0] and Path(path)==source:
            for frame in inspect.stack():
                if frame.filename==operation.__file__ and frame.function=='receive' and 'joins' in frame.frame.f_locals:
                    offset[0] = 11.
                    break
        return answer
    monkeypatch.setattr(force, '_hash', slow_final_hash)
    result = operation.receive(source, child, **args)
    assert offset[0] == 11.
    assert not result['ok'] and not result['complete']
    assert any('Source_ground_window_deadline' in error for error in result['errors']), result['errors']
