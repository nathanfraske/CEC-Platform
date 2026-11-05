"""Independent saved native RC-elbow scope; never whole routing qualification."""
import copy
import os

import pcbnew
import pytest

import cec_source_rc_elbow_reflow as op
import cec_force_current as force
from test_measurement_filter_elbow import elbow, save, add_track
from test_measurement_filter_span import fixed_annotation


def path(f, offsets=None):
    left = tuple(f['cuts'][0].GetStart())
    x = tuple((f['cuts'][0].GetEnd()[k]-left[k])//400000 for k in (0, 1))
    y = tuple((f['cuts'][1].GetEnd()[k]-f['cuts'][1].GetStart()[k])//200000 for k in (0, 1))
    offsets = offsets or [(0, 0), (345000, 0), (1145000, 800000),
        (2800000, 800000), (3400000, 200000), (3700000, 200000)]
    points = [[left[k]+x[k]*a+y[k]*b for k in (0, 1)] for a, b in offsets]
    if points[0] > points[-1]:
        points.reverse()
    return points


def plan(f, points=None):
    return op.plan(f['board'], f['source'], board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        span_uuids=[force._uid(t) for t in f['cuts']], points_nm=path(f) if points is None else points)


def construct(f, tmp_path, q=None):
    candidate = force._copy_family(f['source'], tmp_path/'private')
    proof = op.construct_private(f['source'], candidate, q or plan(f))
    assert proof['complete'] and not proof['routing_admitted'] and not proof['release_authority']
    return candidate


def receive(f, candidate, **kwargs):
    args = dict(board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        span_uuids=[force._uid(t) for t in f['cuts']])
    args.update(kwargs)
    return op.receive(f['source'], candidate, **args)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_independent_saved_three_edge_reconstruction(tmp_path, monkeypatch, quarter, mirror):
    f = elbow(tmp_path, monkeypatch, quarter=quarter, mirror=mirror,
        translate=(2345678, -1234567), renamed=True)
    original = f['source'].read_bytes(); q = plan(f); candidate = construct(f, tmp_path, q)
    result = receive(f, candidate)
    assert result['ok'] and result['complete'], result['errors']
    assert len(result['retired_track_uuids']) == 3 and len(result['incoming_track_uuids']) == 5
    assert result['independent_exact_additions_and_native_Ground_refill']['ok']
    assert result['bounded_composition'] == dict(stage_order=['fresh_canonical_saved_path',
        'exact_additive_Ground', 'partitions_restoration_final_identity'], constituent_count=3,
        constituent_timeout_s=10., aggregate_timeout_s=30., individual_leases_extended=False,
        cached_verdicts_used=False)
    assert [stage['name'] for stage in result['stages']] == result['bounded_composition']['stage_order']
    assert all(stage['complete'] and stage['elapsed_s'] <= 10 for stage in result['stages'])
    assert result['elapsed_s'] <= 30
    contacts = result['Source_plan']['native_path_guard']['retained_contacts']
    assert len(contacts) == 3 and all(r['both_direction_subtractions_empty'] for r in contacts)
    assert not any(result[k] for k in ('routing_admitted', 'current_qualified', 'kelvin_qualified', 'release_authority'))
    assert result['whole_parent_native_current_field_return_and_absolute_measurement_receiving_required']
    assert f['source'].read_bytes() == original
    old, _, _, _ = op.literal._inventory(original.decode())
    new, _, _, _ = op.literal._inventory(candidate.read_text())
    retired = set(result['retired_track_uuids'])
    assert all(new[uid][2] == record[2] for uid, record in old.items() if uid not in retired)
    board = pcbnew.LoadBoard(str(candidate))
    assert all(t.GetWidth() == 250000 and t.GetLayer() == pcbnew.F_Cu and t.IsLocked()
        for t in board.GetTracks() if force._uid(t) in result['incoming_track_uuids'])


def test_closed_source_annotation_group_and_all_members_remain_literal(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); group = fixed_annotation(f)
    original = f['source'].read_bytes(); candidate = construct(f, tmp_path)
    result = receive(f, candidate)
    assert result['ok'], result['errors']
    old, _, _, _ = op.literal._inventory(original.decode())
    new, _, _, _ = op.literal._inventory(candidate.read_text())
    for uid in [force._uid(group), *(force._uid(item) for item in group.GetItems())]:
        assert old[uid][2] == new[uid][2]


@pytest.mark.parametrize('fault', ['bool', 'non45', 'hard90', 'different_port', 'different_tangent',
    'too_long', 'loop', 'tiny'])
def test_route_packet_cannot_relax_source_geometry(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); points = path(f)
    if fault == 'bool': points[1][0] = True
    elif fault == 'non45': points[2][0] += 1
    elif fault == 'hard90': points = [points[0], points[1],
        [points[1][0], points[1][1]+500000], [points[-2][0], points[1][1]+500000], points[-2], points[-1]]
    elif fault == 'different_port': points[-1][0] += 1
    elif fault == 'different_tangent': points[1][1] += 345000
    elif fault == 'too_long':
        points = path(f, [(0, 0), (100000, 0), (3100000, 3000000),
            (6300000, 3000000), (3500000, 200000), (3700000, 200000)])
    elif fault == 'loop': points[3] = points[1]
    elif fault == 'tiny': points[1][0] = points[0][0]+1
    with pytest.raises(ValueError): plan(f, points)


def test_port_contacts_must_preserve_full_native_apertures_not_only_ids(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    points = path(f, [(0, 0), (20000, 0), (820000, -800000),
        (2475000, -800000), (3475000, 200000), (3700000, 200000)])
    with pytest.raises(ValueError, match='contact_aperture_changed'): plan(f, points)


def test_short_arrival_extra_native_cap_fragments_are_not_area_waived(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    points = path(f, [(0, 0), (345000, 0), (1145000, 800000),
        (2875000, 800000), (3475000, 200000), (3700000, 200000)])
    with pytest.raises(ValueError, match='contact_aperture_changed'): plan(f, points)


def test_body_pickup_elsewhere_in_same_node_is_not_allowed(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    add_track(f, (12, 18), (12, 11.9044)); save(f)
    with pytest.raises(ValueError, match='acquired_same_net_contact'): plan(f)


@pytest.mark.parametrize('fault', ['width', 'net', 'lock', 'face', 'extra_track', 'extra_via', 'retained',
    'root', 'pose', 'sidecar', 'stale', 'partial_cut', 'extra_cut', 'group', 'unknown_metadata'])
def test_exact_saved_delta_process_source_and_companions_required(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    board = pcbnew.LoadBoard(str(candidate)); original_ids = {force._uid(t) for t in f['board'].GetTracks()}
    new = next(t for t in board.GetTracks() if force._uid(t) not in original_ids)
    if fault == 'width': new.SetWidth(260000)
    elif fault == 'net': new.SetNet(board.FindNet(f['owner'].FindPadByNumber('6').GetNetname()))
    elif fault == 'lock': new.SetLocked(False)
    elif fault == 'face': new.SetLayer(pcbnew.B_Cu)
    elif fault == 'extra_track':
        t = new.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I_MM(50, 50)); t.SetEnd(pcbnew.VECTOR2I_MM(51, 50)); board.Add(t)
    elif fault == 'extra_via':
        v = pcbnew.PCB_VIA(board); v.SetNet(new.GetNet()); v.SetPosition(new.GetStart())
        v.SetWidth(600000); v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(v)
    elif fault == 'retained': next(t for t in board.GetTracks() if force._uid(t) in original_ids).SetWidth(260000)
    elif fault == 'root': candidate.write_text(candidate.read_text().replace('(general', '(unknown_root yes) (general', 1))
    elif fault == 'pose': board.FindFootprintByReference(f['cap'].GetReference()).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'sidecar': candidate.with_suffix('.kicad_pro').write_text('{}')
    elif fault == 'stale': f['source'].write_text(f['source'].read_text().replace('10Ω', '100Ω'))
    elif fault == 'partial_cut': board.Add(f['span'].Duplicate())
    elif fault == 'extra_cut': board.Remove(next(t for t in board.GetTracks() if force._uid(t) == force._uid(f['tracks'][0])))
    elif fault == 'group':
        g = pcbnew.PCB_GROUP(board); board.Add(g); g.AddItem(new)
    elif fault == 'unknown_metadata':
        candidate.write_text(candidate.read_text().replace('(uuid "'+force._uid(new)+'")',
            '(uuid "'+force._uid(new)+'") (unknown_process yes)', 1))
    if fault not in ('root', 'sidecar', 'stale', 'unknown_metadata'):
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate), board)
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete'] and result['errors']
    assert not result['routing_admitted'] and not result['release_authority']


@pytest.mark.parametrize('fault', ['authority', 'points', 'source', 'producer', 'extra'])
def test_constructor_does_not_trust_proposal_receipts(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); q = plan(f)
    if fault == 'authority': q['Source_observation']['retirement_authority'] = True
    elif fault == 'points': q['Source_observation']['source_points_nm'][0][0] += 1
    elif fault == 'source': q['source'] = '/not/the/Source.kicad_pcb'
    elif fault == 'producer': q['producer_sha256'] = '0'*64
    elif fault == 'extra': q['current_override'] = 1.
    candidate = force._copy_family(f['source'], tmp_path/'private')
    with pytest.raises(ValueError, match='fresh_exact_Source_RC_elbow_recipe_required'):
        op.construct_private(f['source'], candidate, q)
    assert candidate.read_bytes() == f['source'].read_bytes()


def test_samefile_and_hardlink_never_mutate_source(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); q = plan(f); raw = f['source'].read_bytes()
    candidate = tmp_path/'alias.kicad_pcb'; os.link(f['source'], candidate)
    for target in (f['source'], candidate):
        with pytest.raises(ValueError, match='exact_private_RC_elbow_Source_copy_required'):
            op.construct_private(f['source'], target, q)
        assert not receive(f, target)['ok']
    assert f['source'].read_bytes() == raw


@pytest.mark.parametrize('seconds', [True, 0, 10.01, float('nan')])
def test_independent_receiver_has_no_timeout_override(tmp_path, monkeypatch, seconds):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    result = receive(f, candidate, timeout_s=seconds)
    assert not result['ok'] and 'bounded_Source_RC_elbow_lease_required' in result['errors'][0]


def test_receiver_freshly_rechecks_canonical_source(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    f['schematic'].write_text(f['schematic'].read_text().replace('(pin input ', '(pin output '))
    result = receive(f, candidate)
    assert not result['ok'] and result['errors']


def test_unknown_independent_additive_result_cannot_be_promoted(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    monkeypatch.setattr(op.additive, 'receive', lambda *a, **kw:
        dict(ok=False, complete=False, errors=['fixture unknown actual refill']))
    result = receive(f, candidate)
    assert not result['ok'] and result['independent_exact_additions_and_native_Ground_refill']['complete'] is False


def test_late_independent_additive_result_is_refused(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path); actual = op.additive.receive
    def late(*args, **kwargs):
        result = actual(*args, **kwargs)
        now = op.time.monotonic(); monkeypatch.setattr(op.time, 'monotonic', lambda: now+100.)
        return result
    monkeypatch.setattr(op.additive, 'receive', late)
    result = receive(f, candidate)
    assert not result['ok'] and any('deadline' in reason for reason in result['errors'])
    assert len(result['stages']) == 2 and result['stages'][0]['complete']
    assert not result['stages'][1]['complete'] and 'error' in result['stages'][1]


@pytest.mark.parametrize('fault', ['source', 'candidate', 'schematic', 'code'])
def test_stage_boundaries_recheck_family_and_canonical_epoch(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path); actual = op.additive.receive
    def changed(*args, **kwargs):
        result = actual(*args, **kwargs)
        if fault == 'source': f['source'].write_text(f['source'].read_text()+'\n')
        elif fault == 'candidate': candidate.write_text(candidate.read_text()+'\n')
        elif fault == 'schematic': f['schematic'].write_text(f['schematic'].read_text()+'\n')
        elif fault == 'code':
            code = copy.deepcopy(force._code_identity()); code['not_the_code'] = True
            monkeypatch.setattr(force, '_code_identity', lambda: code)
        return result
    monkeypatch.setattr(op.additive, 'receive', changed)
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete']
    assert result['stages'][0]['complete'] and not result['stages'][1]['complete']
    assert len(result['stages']) == 2 and result['stages'][1]['error']


def test_final_partition_constituent_cannot_reuse_remaining_additive_time(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path); actual = op.partitions._partition
    deadlines = []
    def late(board, deadline, **kwargs):
        deadlines.append(deadline)
        result = actual(board, deadline, **kwargs)
        if len(deadlines) == 2:
            monkeypatch.setattr(op.time, 'monotonic', lambda: deadline+0.001)
        return result
    monkeypatch.setattr(op.partitions, '_partition', late)
    result = receive(f, candidate)
    assert not result['ok'] and len(result['stages']) == 3
    assert all(stage['complete'] for stage in result['stages'][:2])
    assert not result['stages'][2]['complete'] and 'deadline' in result['stages'][2]['error']
    assert len(deadlines) == 2 and deadlines[0] == deadlines[1]


def test_final_source_epoch_change_after_partition_is_not_promoted(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path); actual = op.partitions._partition
    calls = []
    def changed(*args, **kwargs):
        result = actual(*args, **kwargs); calls.append(1)
        if len(calls) == 2:
            f['source'].write_text(f['source'].read_text()+'\n')
        return result
    monkeypatch.setattr(op.partitions, '_partition', changed)
    result = receive(f, candidate)
    assert not result['ok'] and len(result['stages']) == 3
    assert not result['stages'][2]['complete'] and result['stages'][2]['error']
