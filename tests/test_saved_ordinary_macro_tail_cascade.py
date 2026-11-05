"""Real saved ordinary cascades retain one immutable aggregate boundary."""
import copy
import json
import math
from pathlib import Path

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_native_macro_tail_cleanup as cleanup
import cec_saved_macro_tail_cleanup as saved
from test_field_proposals import track
from test_lastmile import _board
from test_native_macro_tail_cleanup import report, warning


def boundary(path):
    return dict(path=str(path), sha256=force._hash(path))


def cascade(tmp_path, *, rotation=0, mirror=False, back=False):
    """Native trunk -> two through ports -> opposite-face bridge -> tail."""
    def xy(point):
        x, y = point[0] - 15, point[1] - 15
        if mirror:
            x = -x
        angle = math.radians(rotation)
        return (round(15 + x * math.cos(angle) - y * math.sin(angle), 6),
                round(15 + x * math.sin(angle) + y * math.cos(angle), 6))

    net = '/unrelated/RENAMED_CONTROL_71'
    board = _board([(*xy((5, 10)), net), (*xy((25, 10)), net)], edge=(0, 0, 30, 30))
    front, other = ((pcbnew.B_Cu, pcbnew.F_Cu) if back else (pcbnew.F_Cu, pcbnew.B_Cu))
    if back:
        for fp in board.GetFootprints():
            fp.Flip(fp.GetPosition(), False)
    trunk = track(board, net, xy((5, 10)), xy((25, 10)), width=.2, layer=front)
    bridge = track(board, net, xy((12, 13)), xy((15, 10)), width=.2, layer=other)
    tail = track(board, net, xy((12, 13)), xy((12, 16)), width=.2, layer=front)
    ports = []
    for point in ((12, 13), (15, 10)):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)))
        via.SetNet(trunk.GetNet())
        via.SetWidth(600000)
        via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLocked(True)
        board.Add(via)
        ports.append(force._uid(via))
    prefix = tmp_path / 'prefix.kicad_pcb'
    field._save_field_snapshot(board, prefix)
    original = force._copy_family(prefix, tmp_path / 'separate-original-macro')
    bridge_uid, tail_uid, trunk_uid = map(force._uid, (bridge, tail, trunk))
    grade_calls = []

    def native_grade(path, index):
        grade_calls.append(index)
        live = {force._uid(t) for t in pcbnew.LoadBoard(str(path)).GetTracks()}
        return report(warning(bridge_uid)) if bridge_uid in live else report()

    made = cleanup.construct(prefix, tmp_path / 'constructed', board_hint='synthetic',
        original_native=report(), proposed_native=report(warning(tail_uid)),
        allow_locked_obsolete_port_vias=True, native_grade=native_grade, timeout_s=10.)
    assert made['ok'] and made['complete'], made
    assert grade_calls == [0, 1] and len(made['passes']) == 2
    assert made['final_exclusive_barrel_uuids'] == [ports[0]]
    assert made['final_single_face_barrel_uuids'] == [ports[1]]
    steps = [dict(kind='ordinary', source=boundary(Path(row['source'])),
        candidate=boundary(Path(row['candidate'])), retired_track_uuids=row['retired_track_uuids'],
        retired_via_uuids=row['retired_via_uuids'],
        allow_locked_ordinary_via_uuids=row['locked_via_scope_used']) for row in made['passes']]
    proposal = json.loads(json.dumps(dict(schema=1, kind='typed_saved_macro_tail_cleanup',
        original=boundary(original), prefix=boundary(prefix), steps=steps)))
    return dict(original=original, prefix=prefix, final=Path(made['candidate']), proposal=proposal,
        ports=ports, bridge=bridge_uid, tail=tail_uid, trunk=trunk_uid, net=net, front=front,
        made=made, xy=xy)


def receive(case, proposal=None, *, final=None):
    return saved.receive(case['original'], case['prefix'], final or case['final'],
        case['proposal'] if proposal is None else proposal, board_hint='synthetic', timeout_s=10.)


def immutable_files(case):
    paths = {case['original'], case['prefix'], case['final']}
    paths.update(Path(row[key]['path']) for row in case['proposal']['steps'] for key in ('source', 'candidate'))
    return {path: path.read_bytes() for path in paths}


@pytest.mark.parametrize('rotation,mirror,back', [
    (0, False, False), (0, False, True), (90, True, False), (90, True, True),
    (180, False, False), (180, False, True), (270, True, False), (270, True, True)])
def test_real_two_pass_saved_chain_and_original_union_are_both_received(tmp_path, monkeypatch, rotation, mirror, back):
    case = cascade(tmp_path, rotation=rotation, mirror=mirror, back=back)
    before = immutable_files(case)
    actual = saved.ordinary.receive
    calls = []

    def observed(source, candidate, **kwargs):
        proof = actual(source, candidate, **kwargs)
        calls.append((Path(source), Path(candidate), kwargs, proof))
        return proof

    monkeypatch.setattr(saved.ordinary, 'receive', observed)
    result = receive(case)
    assert result['ok'] and result['complete'], result
    assert len(result['steps']) == 2 and len(calls) == 3
    assert all(proof['ok'] and proof['complete'] for *_, proof in calls)
    assert calls[-1][:2] == (case['prefix'], case['final'])
    assert calls[-1][0] != case['original']
    kwargs = calls[-1][2]
    assert set(kwargs['retired_track_uuids']) == {case['tail'], case['bridge']}
    assert kwargs['retired_via_uuids'] == [case['ports'][0]]
    assert kwargs['redundant_single_face_via_uuids'] == [case['ports'][1]]
    assert set(kwargs['allow_locked_via_uuids']) == set(case['ports'])
    assert kwargs['allow_redundant_cut_only'] is True
    assert all(len(step['receiving']['independently_rederived_obsolete_port_vias'][0]
        ['source_actual_contact_faces']) == 2 for step in result['steps'])
    assert result['whole_original_ordinary_cascade_receiving']['all_prior_native_terminal_partitions_preserved']
    assert not result['current_qualified'] and not result['release_authority']
    assert result['original_macro_source_receiving_still_required']
    child = pcbnew.LoadBoard(str(case['final']))
    assert {force._uid(t) for t in child.GetTracks()} == {case['trunk']}
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize('failure', ['false', 'incomplete', 'exception'])
def test_local_success_cannot_replace_mandatory_aggregate_receiver(tmp_path, monkeypatch, failure):
    case = cascade(tmp_path)
    before = immutable_files(case)
    actual = saved.ordinary.receive
    local = []

    def reject_aggregate(source, candidate, **kwargs):
        if Path(source) == case['prefix'] and Path(candidate) == case['final']:
            if failure == 'exception':
                raise ValueError('synthetic_aggregate_boundary_refusal')
            return dict(ok=failure != 'false', complete=failure != 'incomplete', errors=['aggregate refused'])
        proof = actual(source, candidate, **kwargs)
        local.append(proof)
        return proof

    monkeypatch.setattr(saved.ordinary, 'receive', reject_aggregate)
    result = receive(case)
    assert len(local) == 2 and all(p['ok'] and p['complete'] for p in local)
    assert not result['ok'] and not result['complete'] and result['errors'], result
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize('fault', ['schema_boolean', 'unknown_kind', 'mixed_repeated', 'five_steps',
    'hash', 'source_chain', 'repeat_cut', 'extra_claim', 'unknown_track', 'locked_via_scope'])
def test_forged_or_nonfinite_cascade_request_cannot_admit(tmp_path, fault):
    case = cascade(tmp_path)
    p = copy.deepcopy(case['proposal'])
    final = case['final']
    if fault == 'schema_boolean':
        p['schema'] = True
    elif fault == 'unknown_kind':
        p['steps'][1]['kind'] = 'unchecked'
    elif fault == 'mixed_repeated':
        final = force._copy_family(case['final'], tmp_path / 'mixed-final')
        p['steps'].append(dict(kind='ground', source=boundary(case['final']), candidate=boundary(final),
            retired_track_uuids=[case['tail']]))
    elif fault == 'five_steps':
        p['steps'] *= 3
    elif fault == 'hash':
        p['steps'][1]['candidate']['sha256'] = '0' * 64
    elif fault == 'source_chain':
        p['steps'][1]['source'] = boundary(case['prefix'])
    elif fault == 'repeat_cut':
        p['steps'][1]['retired_track_uuids'].append(case['tail'])
    elif fault == 'extra_claim':
        p['steps'][1]['receiver_ok'] = True
    elif fault == 'unknown_track':
        p['steps'][1]['retired_track_uuids'] = ['not-an-actual-source-track']
    else:
        p['steps'][0]['allow_locked_ordinary_via_uuids'] = []
    before = immutable_files(case)
    result = receive(case, p, final=final)
    assert not result['ok'] and result['errors'], result
    if fault == 'mixed_repeated':
        assert 'repeated_ordinary_cascade_must_be_a_pure_exact_chain' in str(result['errors'])
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_added_final_copper_is_not_hidden_by_valid_earlier_pass(tmp_path):
    case = cascade(tmp_path)
    board = pcbnew.LoadBoard(str(case['final']))
    track(board, case['net'], (7, 18), (9, 18), width=.2)
    field._save_field_snapshot(board, case['final'])
    case['proposal']['steps'][-1]['candidate'] = boundary(case['final'])
    before = immutable_files(case)
    result = receive(case)
    assert not result['ok'] and 'exact_monotonic_track_only_saved_cut_required' in str(result['errors']), result
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_preexisting_single_face_barrel_cannot_borrow_cascade_port_authority(tmp_path):
    case = cascade(tmp_path)
    board = pcbnew.LoadBoard(str(case['prefix']))
    trunk = next(t for t in board.GetTracks() if force._uid(t) == case['trunk'])
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(*case['xy']((20, 10))))
    via.SetNet(trunk.GetNet()); via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(via)
    field._save_field_snapshot(board, case['prefix'])
    case['proposal']['prefix'] = boundary(case['prefix'])
    case['proposal']['steps'][0]['source'] = boundary(case['prefix'])
    case['proposal']['steps'][0]['retired_via_uuids'].append(force._uid(via))
    before = immutable_files(case)
    result = receive(case)
    assert not result['ok'], result
    assert 'original_multiface_to_one_enabled_face_routing_port_required' in str(result['errors']), result
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize('net', ['+5V', 'GND', '/USB_D_P'])
def test_power_ground_and_pair_cannot_be_relabelled_as_ordinary_cascade(tmp_path, net):
    case = cascade(tmp_path)
    paths = immutable_files(case)
    for path in paths:
        board = pcbnew.LoadBoard(str(path))
        board.Add(pcbnew.NETINFO_ITEM(board, net))
        code = board.GetNetcodeFromNetname(net)
        for item in [*board.GetTracks(), *(p for f in board.GetFootprints() for p in f.Pads())]:
            item.SetNetCode(code)
        field._save_field_snapshot(board, path)
    p = case['proposal']
    p['original'], p['prefix'] = boundary(case['original']), boundary(case['prefix'])
    for row in p['steps']:
        row['source'], row['candidate'] = boundary(Path(row['source']['path'])), boundary(Path(row['candidate']['path']))
    before = immutable_files(case)
    result = receive(case)
    assert not result['ok'] and result['errors'], result
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_source_byte_change_between_real_local_steps_is_detected(tmp_path, monkeypatch):
    case = cascade(tmp_path)
    actual = saved._step
    calls = []

    def change_source_after_receiving(left, right, row, hint, deadline):
        proof = actual(left, right, row, hint, deadline)
        calls.append(proof)
        if len(calls) == 1:
            case['prefix'].write_bytes(case['prefix'].read_bytes() + b'\n')
        return proof

    monkeypatch.setattr(saved, '_step', change_source_after_receiving)
    result = receive(case)
    assert len(calls) == 2 and all(p['ok'] and p['complete'] for p in calls)
    assert not result['ok'] and 'typed_tail_source_family_or_code_changed' in str(result['errors']), result


@pytest.mark.parametrize('bound', ['tracks', 'vias'])
def test_aggregate_union_work_limit_remains_fail_closed_even_after_local_trues(tmp_path, monkeypatch, bound):
    case = cascade(tmp_path)
    p = copy.deepcopy(case['proposal'])
    if bound == 'tracks':
        p['steps'][1]['retired_track_uuids'] += ['extra-track-%02d' % i for i in range(31)]
    else:
        p['steps'][1]['retired_via_uuids'] += ['extra-via-%02d' % i for i in range(3)]
    calls = []
    monkeypatch.setattr(saved, '_step', lambda *args: calls.append(args) or dict(ok=True, complete=True))
    result = receive(case, p)
    assert len(calls) == 2
    assert not result['ok'] and 'whole_original_ordinary_cascade_work_bound' in str(result['errors']), result
