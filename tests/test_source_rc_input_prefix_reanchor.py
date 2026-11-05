"""Real native prefix ownership; only canonical exporter/current fixtures stubbed."""
import copy
import hashlib
import os

import pcbnew
import pytest

import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_source_rc_input_prefix_reanchor as op
from test_measurement_filter_elbow import elbow, save, add_track
from test_measurement_filter_span import fixed_annotation


def points(f, offsets=None):
    start = tuple(f['tracks'][0].GetStart())
    x = tuple((f['cuts'][0].GetEnd()[k]-f['cuts'][0].GetStart()[k])//400000 for k in (0, 1))
    y = tuple((f['tracks'][0].GetEnd()[k]-start[k])//1100000 for k in (0, 1))
    offsets = offsets or [(0, 0), (0, 350000), (954400, 1304400), (3780000, 1304400)]
    return [[start[k]+x[k]*a+y[k]*b for k in (0, 1)] for a, b in offsets]


def plan(f, path=None, **kwargs):
    args = dict(board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        span_uuids=[force._uid(t) for t in f['cuts']], points_nm=points(f) if path is None else path)
    args.update(kwargs)
    return op.plan(f['board'], f['source'], **args)


def construct(f, tmp_path, proposal=None):
    candidate = force._copy_family(f['source'], tmp_path/'private')
    proof = op.construct_private(f['source'], candidate, proposal or plan(f))
    assert proof['complete'] and not proof['routing_admitted'] and not proof['release_authority']
    return candidate


def receive(f, candidate, **kwargs):
    args = dict(board_hint=f['hint'], pad_uuid=force._uid(f['root']),
        span_uuids=[force._uid(t) for t in f['cuts']])
    args.update(kwargs)
    return op.receive(f['source'], candidate, **args)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_native_renamed_translated_prefix_is_independently_received(tmp_path, monkeypatch, quarter, mirror):
    f = elbow(tmp_path, monkeypatch, quarter=quarter, mirror=mirror,
        translate=(2345678, -1234567), renamed=True)
    raw = f['source'].read_bytes(); q = plan(f)
    obs = q['Source_observation']
    assert set(obs['retired_track_uuids']) == {force._uid(t) for t in f['tracks'][:5]}
    assert set(obs['derived_root_prefix_uuids']) == {force._uid(t) for t in f['tracks'][:2]}
    assert {r['native_uuid'] for r in obs['retained_contacts']} == {
        force._uid(f['root']), force._uid(f['tracks'][5])}
    assert obs['anchor_elbow']['complete'] and len(obs['Source_node_observation']['node_pad_uuids']) == 3
    candidate = construct(f, tmp_path, q); result = receive(f, candidate)
    assert result['ok'] and result['complete'], result['errors']
    assert len(result['retired_track_uuids']) == 5 and len(result['incoming_track_uuids']) == 3
    assert result['independent_exact_additions_and_native_Ground_refill']['ok']
    assert result['bounded_composition'] == dict(stage_order=['fresh_canonical_saved_path',
        'exact_additive_Ground', 'partitions_restoration_final_identity'], constituent_count=3,
        constituent_timeout_s=10., aggregate_timeout_s=30., individual_leases_extended=False,
        cached_verdicts_used=False)
    assert all(s['complete'] and s['elapsed_s'] <= 10 for s in result['stages'])
    assert result['elapsed_s'] <= 30
    assert not any(result[k] for k in ('routing_admitted', 'pose_authority', 'current_qualified',
        'kelvin_qualified', 'release_authority'))
    assert f['source'].read_bytes() == raw
    old, _, _, _ = op.literal._inventory(raw.decode()); new, _, _, _ = op.literal._inventory(candidate.read_text())
    assert all(new[u][2] == entry[2] for u, entry in old.items() if u not in result['retired_track_uuids'])
    child = pcbnew.LoadBoard(str(candidate))
    actual = leaf.plan(child, force._uid(f['root']))
    assert set(result['incoming_track_uuids']) <= set(actual['track_uuids'])


def test_original_elbow_and_leaf_ownership_are_not_expanded(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch)
    old_leaf = leaf.plan(f['board'], force._uid(f['root']))
    assert old_leaf['track_uuids'] == [force._uid(f['tracks'][0])]
    with pytest.raises(ValueError, match='bounded_named_measurement_filter_elbow_source_required'):
        op.observer.plan_elbow(f['board'], f['source'], board_hint=f['hint'], pad_uuid=force._uid(f['root']),
            span_uuids=[force._uid(t) for t in f['tracks'][:5]], expected_source_sha256=force._hash(f['source']))
    assert len(plan(f)['Source_observation']['retired_track_uuids']) == 5


def test_closed_Source_reference_group_and_every_member_stay_literal(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); group = fixed_annotation(f)
    raw = f['source'].read_bytes(); candidate = construct(f, tmp_path)
    result = receive(f, candidate)
    assert result['ok'], result['errors']
    old, _, _, _ = op.literal._inventory(raw.decode()); new, _, _, _ = op.literal._inventory(candidate.read_text())
    for uid in [force._uid(group), *(force._uid(i) for i in group.GetItems())]:
        assert old[uid][2] == new[uid][2]


@pytest.mark.parametrize('fault', ['duplicate_anchor', 'partial_anchor', 'extra_anchor', 'missing_anchor',
    'branch', 'other_terminal', 'barrel', 'fill', 'prefix_width', 'prefix_lock', 'prefix_face',
    'prefix_group', 'unknown_metadata', 'missing_manufacturer', 'canonical_net', 'incomplete_current'])
def test_caller_cannot_extend_or_forge_root_exclusive_Source_ownership(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); args = {}
    ids = [force._uid(t) for t in f['cuts']]
    if fault == 'duplicate_anchor': ids[0] = ids[1]
    elif fault == 'partial_anchor': ids.pop()
    elif fault == 'extra_anchor': ids.append(force._uid(f['tracks'][1]))
    elif fault == 'missing_anchor': ids[0] = '00000000-0000-0000-0000-000000000000'
    elif fault == 'branch': add_track(f, (10, 10.5), (9, 10.5))
    elif fault == 'other_terminal':
        f['cap'].FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(10, 10.5))
    elif fault == 'barrel':
        v = pcbnew.PCB_VIA(f['board']); v.SetNet(f['root'].GetNet()); v.SetPosition(pcbnew.VECTOR2I_MM(10, 10.5))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetWidth(600000); v.SetDrill(300000); f['board'].Add(v)
    elif fault == 'fill':
        z = pcbnew.ZONE(f['board']); z.SetNet(f['root'].GetNet()); z.SetLayer(pcbnew.F_Cu); f['board'].Add(z)
    elif fault == 'prefix_width': f['tracks'][0].SetWidth(260000)
    elif fault == 'prefix_lock': f['tracks'][0].SetLocked(False)
    elif fault == 'prefix_face': f['tracks'][0].SetLayer(pcbnew.B_Cu)
    elif fault == 'prefix_group':
        g = pcbnew.PCB_GROUP(f['board']); f['board'].Add(g); g.AddItem(f['tracks'][0])
    elif fault == 'unknown_metadata':
        text = f['source'].read_text().replace('(uuid "'+force._uid(f['tracks'][0])+'")',
            '(uuid "'+force._uid(f['tracks'][0])+'") (new_ownership yes)', 1)
        f['source'].write_text(text)
    elif fault == 'missing_manufacturer': f['owner'].SetField('MPN', 'unknown')
    elif fault == 'canonical_net': f['rh'].FindPadByNumber('1').SetNet(f['rl'].FindPadByNumber('1').GetNet())
    elif fault == 'incomplete_current': f['domains']['force_a']['complete'] = False
    if fault != 'unknown_metadata': save(f)
    with pytest.raises(ValueError): plan(f, span_uuids=ids, **args)


@pytest.mark.parametrize('fault', ['bool', 'non45', 'hard90', 'port', 'tangent', 'long', 'tiny', 'loop',
    'root_aperture', 'foreign', 'other_node_contact'])
def test_replacement_has_no_geometry_contact_or_width_waiver(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); path = points(f)
    if fault == 'bool': path[1][0] = True
    elif fault == 'non45': path[2][0] += 1
    elif fault == 'hard90': path = points(f, [(0, 0), (0, 1304400), (3780000, 1304400)])
    elif fault == 'port': path[-1][0] += 1
    elif fault == 'tangent': path = points(f, [(0, 0), (350000, 0), (1654400, 1304400), (3780000, 1304400)])
    elif fault == 'long': path = points(f, [(0, 0), (0, 9000000), (7695600, 1304400), (3780000, 1304400)])
    elif fault == 'tiny': path[1][1] = path[0][1]+1
    elif fault == 'loop': path.insert(2, path[0])
    elif fault == 'root_aperture': path = points(f, [(0, 0), (0, 20000), (1284400, 1304400), (3780000, 1304400)])
    elif fault == 'foreign':
        add_track(f, (11, 10), (11, 12), net=f['owner'].FindPadByNumber('6').GetNet()); save(f)
    elif fault == 'other_node_contact':
        add_track(f, (12, 18), (12, 11.5)); save(f)
    with pytest.raises(ValueError): plan(f, path)


@pytest.mark.parametrize('fault', ['cuts', 'source', 'producer', 'scope', 'extra'])
def test_constructor_rederives_every_proposal_field(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); q = plan(f)
    if fault == 'cuts': q['Source_observation']['retired_track_uuids'].pop()
    elif fault == 'source': q['source'] = '/wrong/Source.kicad_pcb'
    elif fault == 'producer': q['producer_sha256'] = '0'*64
    elif fault == 'scope': q['Source_observation']['pose_authority'] = True
    elif fault == 'extra': q['current_override'] = .1
    candidate = force._copy_family(f['source'], tmp_path/'private')
    with pytest.raises(ValueError, match='fresh_exact_Source_RC_prefix_recipe_required'):
        op.construct_private(f['source'], candidate, q)
    assert candidate.read_bytes() == f['source'].read_bytes()


@pytest.mark.parametrize('fault', ['width', 'net', 'lock', 'face', 'extra_via', 'extra_track', 'retained',
    'root', 'pose', 'sidecar', 'partial_cut', 'extra_cut', 'group', 'unknown_metadata'])
def test_saved_receiver_rejects_unowned_or_partial_material(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    board = pcbnew.LoadBoard(str(candidate)); original = {force._uid(t) for t in f['board'].GetTracks()}
    new = next(t for t in board.GetTracks() if force._uid(t) not in original)
    if fault == 'width': new.SetWidth(260000)
    elif fault == 'net': new.SetNet(f['owner'].FindPadByNumber('6').GetNet())
    elif fault == 'lock': new.SetLocked(False)
    elif fault == 'face': new.SetLayer(pcbnew.B_Cu)
    elif fault == 'extra_via':
        v = pcbnew.PCB_VIA(board); v.SetNet(new.GetNet()); v.SetPosition(new.GetStart())
        v.SetWidth(600000); v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(v)
    elif fault == 'extra_track':
        t = new.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID()); t.SetStart(pcbnew.VECTOR2I_MM(50, 50))
        t.SetEnd(pcbnew.VECTOR2I_MM(51, 50)); board.Add(t)
    elif fault == 'retained': next(t for t in board.GetTracks() if force._uid(t) in original).SetWidth(260000)
    elif fault == 'root': candidate.write_text(candidate.read_text().replace('(general', '(unknown_root yes) (general', 1))
    elif fault == 'pose': board.FindFootprintByReference(f['cap'].GetReference()).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'sidecar': candidate.with_suffix('.kicad_pro').write_text('{}')
    elif fault == 'partial_cut': board.Add(f['tracks'][1].Duplicate())
    elif fault == 'extra_cut': board.Remove(next(t for t in board.GetTracks() if force._uid(t) == force._uid(f['tracks'][5])))
    elif fault == 'group':
        g = pcbnew.PCB_GROUP(board); board.Add(g); g.AddItem(new)
    elif fault == 'unknown_metadata': candidate.write_text(candidate.read_text().replace('(uuid "'+force._uid(new)+'")',
        '(uuid "'+force._uid(new)+'") (unknown_process yes)', 1))
    if fault not in ('root', 'sidecar', 'unknown_metadata'):
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate), board)
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete'] and result['errors']


def test_samefile_hardlink_and_source_proposal_drift_cannot_mutate_Source(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); q = plan(f); raw = f['source'].read_bytes()
    alias = tmp_path/'alias.kicad_pcb'; os.link(f['source'], alias)
    for candidate in (f['source'], alias):
        with pytest.raises(ValueError, match='exact_private_Source_RC_prefix_copy_required'):
            op.construct_private(f['source'], candidate, q)
        assert not receive(f, candidate)['ok']
    assert f['source'].read_bytes() == raw


@pytest.mark.parametrize('seconds', [True, 0, 10.01, float('nan')])
def test_finite_constituent_bounds_cannot_be_overridden(tmp_path, monkeypatch, seconds):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    result = receive(f, candidate, timeout_s=seconds)
    assert not result['ok'] and 'bounded_Source_RC_prefix_lease_required' in result['errors'][0]


def test_unknown_additive_result_remains_unknown(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    monkeypatch.setattr(op.additive, 'receive', lambda *a, **kw:
        dict(ok=False, complete=False, errors=['unknown actual native refill']))
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete']
    assert result['independent_exact_additions_and_native_Ground_refill']['complete'] is False


@pytest.mark.parametrize('fault', ['source', 'candidate', 'schematic', 'code', 'deadline'])
def test_stage_boundaries_recheck_live_identity_and_deadline(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path); original = op.additive.receive
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if fault == 'source': f['source'].write_text(f['source'].read_text()+'\n')
        elif fault == 'candidate': candidate.write_text(candidate.read_text()+'\n')
        elif fault == 'schematic': f['schematic'].write_text(f['schematic'].read_text()+'\n')
        elif fault == 'code':
            old = force._code_identity(); monkeypatch.setattr(force, '_code_identity', lambda: dict(old, changed='fixture'))
        elif fault == 'deadline':
            later = op.time.monotonic()+100.; monkeypatch.setattr(op.time, 'monotonic', lambda: later)
        return result
    monkeypatch.setattr(op.additive, 'receive', changed)
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete'] and result['errors']
    assert result['stages'][0]['complete'] and not result['stages'][1]['complete']


def test_fresh_canonical_source_and_all_external_terminal_assignments_are_required(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); candidate = construct(f, tmp_path)
    f['schematic'].write_text(f['schematic'].read_text().replace('(pin input ', '(pin output '))
    result = receive(f, candidate)
    assert not result['ok'] and not result['complete']


def test_only_fresh_semantic_export_identity_handles_generated_clock_changes(tmp_path, monkeypatch):
    f = elbow(tmp_path, monkeypatch); original = op.observer.source_roles._export; calls = []
    def volatile(*args, **kwargs):
        tree, proof = original(*args, **kwargs); calls.append(1)
        proof['netlist_sha256'] = hashlib.sha256(str(len(calls)).encode()).hexdigest()
        return tree, proof
    monkeypatch.setattr(op.observer.source_roles, '_export', volatile)
    q = plan(f); candidate = construct(f, tmp_path, q); result = receive(f, candidate)
    assert len(calls) >= 3 and result['ok'], result['errors']


@pytest.mark.parametrize('fault', ['semantic', 'exporter'])
def test_changed_semantic_or_exporter_identity_is_not_clock_noise(tmp_path, monkeypatch, fault):
    f = elbow(tmp_path, monkeypatch); q = plan(f); original = op.observer.source_roles._export
    def changed(*args, **kwargs):
        tree, proof = original(*args, **kwargs)
        if fault == 'semantic': proof['netlist_semantic_sha256'] = '0'*64
        else:
            from pathlib import Path
            Path(proof['exporter']).write_bytes(b'changed exporter tool')
            proof['exporter_sha256'] = force._hash(Path(proof['exporter']))
        return tree, proof
    monkeypatch.setattr(op.observer.source_roles, '_export', changed)
    candidate = force._copy_family(f['source'], tmp_path/'private')
    with pytest.raises(ValueError, match='fresh_exact_Source_RC_prefix_recipe_required'):
        op.construct_private(f['source'], candidate, q)
    assert candidate.read_bytes() == f['source'].read_bytes()
