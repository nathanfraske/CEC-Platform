"""A new producer result must not bypass a requested, exact Source fallback.

The off-centre offers below are deliberately not consumer permissions. Only
the real Source-track planner, ordinary Source dimensions and saved receiver
can admit their replacement. No protector/refdes/coordinate rule is used.
"""
import json
import time

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as op
from test_ground_access_completion import fixture as old_fixture


def fixture(tmp_path, **frames):
    b, source, pad, point = old_fixture(tmp_path, mode='dogbone', observed=True, **frames)
    for t in b.GetTracks():
        if t.GetNetname() != 'GND':
            continue
        if t.GetClass() == 'PCB_TRACK':
            t.SetWidth(500000)
        else:
            t.SetWidth(900000)
            t.SetDrill(500000)
    additive._ground_refill(b)
    pcbnew.SaveBoard(str(source), b)
    project = source.with_suffix('.kicad_pro')
    payload = json.loads(project.read_text())
    default = next(c for c in payload['net_settings']['classes'] if c['name'] == 'Default')
    default.update(track_width=.5, clearance=.2, via_diameter=.9, via_drill=.5)
    payload['net_settings']['netclass_assignments'] = {}
    payload['net_settings']['netclass_patterns'] = []
    project.write_text(json.dumps(payload))
    uid = force._uid(pad)
    b = pcbnew.LoadBoard(str(source))
    pad = next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p) == uid)
    return b, source, pad


def off_centre_offer(board, pad, **kwargs):
    # This probe is never saved/admitted. In particular its flag is not
    # proof of containment, class compliance or a Ground return.
    via = pcbnew.PCB_VIA(board)
    at = pad.GetPosition()
    via.SetPosition(pcbnew.VECTOR2I(at.x + 25000, at.y))
    via.SetWidth(500000)
    via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNetCode(pad.GetNetCode())
    board.Add(via)
    return dict(status='via-in-pad', items=[via], via_uuid=force._uid(via),
                contained_off_center=True), None


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_actual_saved_full_class_carrier_gets_exact_ordinary_source_barrel(tmp_path, quarter, mirror, layer):
    b, source, pad = fixture(tmp_path, quarter=quarter, mirror=mirror, layer=layer)
    before = source.read_bytes()
    old = {force._uid(t) for t in b.GetTracks()}
    q = op._source_track_root(b, pad, (.9, .5), 1.5, time.monotonic() + 10.)
    assert q and q['status'] == 'source-track-entry'
    proof = q['source_track_root']
    assert proof['carrier_width_nm'] == proof['saved_ground_class_width_nm'] == 500000
    assert proof['requested_via_geometry_nm'] == [900000, 500000]
    assert not proof['new_capacity_credited']
    assert len({force._uid(t) for t in b.GetTracks()} - old) == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_off_centre_offer_does_not_skip_real_requested_source_fallback(tmp_path, monkeypatch, quarter, layer):
    _, source, pad = fixture(tmp_path, quarter=quarter, layer=layer)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    before = source.read_bytes()
    q = op.plan(source, **args)
    assert q['source_track_root'] and len(q['ops']) == 1
    assert q['ops'][0][2:] == [500000, 900000]
    child = op.write_private(q, tmp_path / 'saved-fallback')['candidate']
    result = op.receive(source, child, **args)
    assert result['ok'] and result['complete'], result
    assert result['new_holes'] == 1 and result['every_source_native_partition_identical']
    assert result['saved_return_witness_mm'] <= 1.5
    assert result['all_source_known_returns']['ok']
    assert not result['current_qualified'] and not result['release_authority']
    assert source.read_bytes() == before


def test_source_track_preference_skips_unusable_off_centre_tier_and_preserves_requested_class(tmp_path, monkeypatch):
    _, source, pad = fixture(tmp_path)
    monkeypatch.setattr(op.cells, '_add_ground_return', lambda *a, **k: pytest.fail('unneeded off-centre search'))
    q = op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    assert q['source_track_root'] and q['ops'][0][2:] == [500000, 900000]


def test_source_first_probe_reuses_only_the_unmodified_invocation_local_board(tmp_path, monkeypatch):
    _, source, pad = fixture(tmp_path)
    original = pcbnew.LoadBoard
    loads = []
    def load(path):
        loads.append(str(path))
        return original(path)
    monkeypatch.setattr(op.pcbnew, 'LoadBoard', load)
    q = op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    assert q['source_track_root']
    # One fresh Source working board plus the separate final port-context
    # observation; no duplicate just to try its untouched Source carrier.
    assert loads == [str(source), str(source)]


def test_actual_off_centre_status_uses_fallback_even_when_centre_size_was_possible(tmp_path, monkeypatch):
    _, source, pad, _ = old_fixture(tmp_path, mode='vip', observed=True)
    offers = []
    def offer(*a, **k):
        offers.append(1)
        return off_centre_offer(*a, **k)
    monkeypatch.setattr(op.cells, '_add_ground_return', offer)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    q = op.plan(source, **args)
    assert offers == [1] and q['source_track_root']
    assert q['ops'][0][2:] == [300000, 600000]
    child = op.write_private(q, tmp_path / 'actual-status-fallback')['candidate']
    received = op.receive(source, child, **args)
    assert received['ok'] and received['complete'], received


def test_failed_source_track_search_is_not_repeated_in_the_same_unchanged_epoch(tmp_path, monkeypatch):
    _, source, pad = fixture(tmp_path)
    calls = []
    def unavailable(*a, **k):
        calls.append(1)
        return None
    monkeypatch.setattr(op, '_source_track_root', unavailable)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    with pytest.raises(ValueError, match='new_in_pad_ground_hole_must_be_exact_source_land_entry'):
        op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    assert calls == [1]


@pytest.mark.parametrize('fault', ['missing_project', 'nonclass_width', 'over_bound',
                                  'smaller_request', 'grouped', 'mask', 'foreign'])
def test_wider_carrier_needs_positive_saved_class_and_exact_requested_geometry(tmp_path, fault):
    b, source, pad = fixture(tmp_path)
    requested = (.9, .5)
    if fault == 'missing_project':
        source.with_suffix('.kicad_pro').unlink()
    elif fault == 'smaller_request':
        requested = (.6, .3)
    elif fault == 'over_bound':
        payload = json.loads(source.with_suffix('.kicad_pro').read_text())
        payload['net_settings']['classes'][0]['track_width'] = 1.1
        source.with_suffix('.kicad_pro').write_text(json.dumps(payload))
    group = None
    if fault == 'grouped':
        group = pcbnew.PCB_GROUP(b)
        b.Add(group)
    for t in b.GetTracks():
        if t.GetClass() != 'PCB_TRACK' or t.GetNetname() != 'GND':
            continue
        if fault == 'nonclass_width': t.SetWidth(400000)
        elif fault == 'over_bound': t.SetWidth(1100000)
        elif fault == 'grouped': group.AddItem(t)
        elif fault == 'mask': t.SetHasSolderMask(True)
        elif fault == 'foreign': t.SetNetCode(b.GetNetcodeFromNetname('+3V3'))
    old = {force._uid(t) for t in b.GetTracks()}
    assert op._source_track_root(b, pad, requested, 1.5, time.monotonic() + 10.) is None
    assert {force._uid(t) for t in b.GetTracks()} == old


@pytest.mark.parametrize('preference', [False, True])
def test_unreplaced_off_centre_offer_remains_strictly_refused(tmp_path, monkeypatch, preference):
    _, source, pad = fixture(tmp_path)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    monkeypatch.setattr(op, '_source_track_root', lambda *a, **k: None)
    with pytest.raises(ValueError, match='new_in_pad_ground_hole_must_be_exact_source_land_entry'):
        op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad),
                prefer_source_track_root=preference)


def test_a_real_exact_centre_entry_still_wins_without_optional_fallback(tmp_path, monkeypatch):
    b, source, pad = old_fixture(tmp_path, mode='vip')[:3]
    monkeypatch.setattr(op, '_source_track_root', lambda *a, **k: pytest.fail('unneeded fallback'))
    q = op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    assert q['source_track_root'] is None and len(q['ops']) == 1
    assert q['ops'][0][0] == 'via' and q['ops'][0][1] == list(pad.GetPosition())


@pytest.mark.parametrize('fault', ['hole', 'diameter', 'position', 'class'])
def test_saved_fallback_cannot_admit_forged_geometry_or_changed_source_class(tmp_path, monkeypatch, fault):
    _, source, pad = fixture(tmp_path)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    q = op.plan(source, **args)
    child = op.write_private(q, tmp_path / 'tampered')['candidate']
    if fault == 'class':
        payload = json.loads(source.with_suffix('.kicad_pro').read_text())
        payload['net_settings']['classes'][0]['track_width'] = .6
        source.with_suffix('.kicad_pro').write_text(json.dumps(payload))
    else:
        b = pcbnew.LoadBoard(child)
        parent = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
        v = next(t for t in b.GetTracks() if force._uid(t) not in parent)
        if fault == 'hole': v.SetDrill(300000)
        elif fault == 'diameter': v.SetWidth(600000)
        else: v.Move(pcbnew.VECTOR2I(1, 0))
        field._save_field_snapshot(b, child)
    result = op.receive(source, child, **args)
    assert not result['ok'] and not result['complete'] and result['errors']


def test_public_construction_still_rederives_and_receiver_spends_lease_on_physical_checks(tmp_path, monkeypatch):
    _, source, pad = fixture(tmp_path)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    q = op.plan(source, **args)
    original = op.plan
    calls = []
    def counted(*a, **k):
        calls.append(str(a[0]))
        return original(*a, **k)
    monkeypatch.setattr(op, 'plan', counted)
    op.construct(q)
    assert calls == [str(source)]
    child = op.write_private(q, tmp_path / 'single-independent-replay')['candidate']
    calls.clear()
    result = op.receive(source, child, **args)
    assert result['ok'] and result['complete'], result
    assert calls == [str(source)]
    assert result['all_source_known_returns']['ok']
    assert result['every_source_native_partition_identical']


@pytest.mark.parametrize('physical_regression', [False, True])
def test_unknown_return_observation_is_not_misreported_as_measured_regression(tmp_path, monkeypatch, physical_regression):
    _, source, pad = fixture(tmp_path)
    monkeypatch.setattr(op.cells, '_add_ground_return', off_centre_offer)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    q = op.plan(source, **args)
    child = op.write_private(q, tmp_path / 'refused-return-proof')['candidate']
    monkeypatch.setattr(op.returns, 'receive', lambda *a, **k: dict(ok=False, complete=False,
        regressed_terminals=['actual_terminal'] if physical_regression else [],
        errors=[] if physical_regression else ['ground_return_preservation_deadline']))
    result = op.receive(source, child, **args)
    assert not result['ok'] and not result['complete']
    reason = 'worsened_source_known_returns' if physical_regression else 'source_known_returns_inconclusive'
    assert any(reason in error for error in result['errors'])


def test_final_family_validation_cannot_outlive_the_same_receiving_lease(tmp_path, monkeypatch):
    import inspect
    _, source, pad = fixture(tmp_path)
    args = dict(board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    q = op.plan(source, **args)
    child = op.write_private(q, tmp_path / 'validation-time-bound')['candidate']
    clock = [time.monotonic()]
    original = op.force._family
    calls = []
    def family(*a, **k):
        parent = inspect.currentframe().f_back
        if parent.f_code.co_name == 'receive' and parent.f_code.co_filename == op.__file__:
            calls.append(str(a[0]))
            if len(calls) == 3: clock[0] += 11.
        return original(*a, **k)
    monkeypatch.setattr(op.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(op.force, '_family', family)
    result = op.receive(source, child, **args)
    assert len(calls) == 4, result
    assert not result['ok'] and not result['complete']
    assert any('source_code_or_lease_changed' in error for error in result['errors'])


@pytest.mark.parametrize('fault', ['missing_return', 'reference_refusal', 'native_exception'])
def test_post_add_probe_refusal_or_exception_restores_the_whole_native_board(tmp_path, monkeypatch, fault):
    b, source, pad = fixture(tmp_path)
    before = op.row._source_binding(b)
    if fault == 'missing_return':
        monkeypatch.setattr(op.cells, '_existing_return', lambda *a, **k: None)
    else:
        def refuse(*a, **k):
            raise (RuntimeError('unexpected-native-error') if fault == 'native_exception'
                else ValueError('reference-contact-refused'))
        monkeypatch.setattr(op.shortcut, '_reference_contacts', refuse)
    if fault == 'native_exception':
        with pytest.raises(RuntimeError, match='unexpected-native-error'):
            op._source_track_root(b, pad, (.9, .5), 1.5, time.monotonic()+10.)
    else:
        assert op._source_track_root(b, pad, (.9, .5), 1.5, time.monotonic()+10.) is None
    assert op.row._source_binding(b) == before


def test_final_plan_family_and_hash_observations_cannot_outlive_its_lease(tmp_path, monkeypatch):
    import inspect
    _, source, pad = fixture(tmp_path)
    clock = [10.]
    original = op.force._family
    calls = []
    def family(*a, **k):
        parent = inspect.currentframe().f_back
        if parent.f_code.co_name == 'plan' and parent.f_code.co_filename == op.__file__:
            calls.append(1)
            if len(calls) == 2: clock[0] = 21.
        return original(*a, **k)
    monkeypatch.setattr(op.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(op.force, '_family', family)
    with pytest.raises(ValueError, match='ground_completion_plan_deadline'):
        op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    assert calls == [1, 1]


def test_final_private_writer_identity_and_candidate_hash_are_in_same_lease(tmp_path, monkeypatch):
    import inspect
    _, source, pad = fixture(tmp_path)
    q = op.plan(source, board_hint='synthetic', pad_uuid=force._uid(pad), prefer_source_track_root=True)
    before = source.read_bytes()
    clock = [10.]
    original = op.force._code_identity
    calls = []
    def identity():
        parent = inspect.currentframe().f_back
        if parent.f_code.co_name == 'write_private' and parent.f_code.co_filename == op.__file__:
            calls.append(1)
            if len(calls) == 2: clock[0] = 21.
        return original()
    monkeypatch.setattr(op.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(op.force, '_code_identity', identity)
    with pytest.raises(ValueError, match='ground_completion_saved_source_code_or_lease_changed'):
        op.write_private(q, tmp_path / 'UNADMITTED-expired-writer')
    assert calls == [1, 1] and source.read_bytes() == before
