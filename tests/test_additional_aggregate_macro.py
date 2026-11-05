"""Real canonical/native capacitor geometry; only aggregate current is synthetic.

These tests grant no new load allocation, barrel rating or complete macro grade.
"""
import copy
from pathlib import Path

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_additional_aggregate_macro as op
import cec_source_aggregate_capacitor_cell as cap
from test_source_aggregate_capacitor_cell import fixture as base_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, routed=False):
    source, root, _ = base_fixture(tmp_path, monkeypatch)
    original = pcbnew.LoadBoard(str(source))
    # Ordinary geometry separated from the future Ground land, not the old
    # aggregate fixture's partial-overlap Source via (which remains fab debt).
    for via in original.GetTracks():
        if via.GetClass() == 'PCB_VIA' and via.GetNetname() == 'GND':
            via.SetPosition(pcbnew.VECTOR2I_MM(15.2, 14)); via.SetWidth(600000); via.SetDrill(300000)
    cap.additive._ground_refill(original); cap.field._save_field_snapshot(original, source)
    parent = pcbnew.LoadBoard(str(source)); board = pcbnew.LoadBoard(str(source))
    fp = parent.FindFootprintByReference('RENAMED_C'); owner = parent.FindFootprintByReference('AMP73')
    poses = {fp.GetReference(): [14, 14, fp.GetOrientationDegrees()],
        owner.GetReference(): [owner.GetPosition().x / 1e6, owner.GetPosition().y / 1e6, owner.GetOrientationDegrees()]}
    roles = op.collect(parent, poses, board_hint=str(root))
    proposal = dict(poses=poses, board_hint=str(root), additional_aggregate_capacitors=roles,
        reference_group_uuids=[], retired_track_uuids=[], row_plan={})
    moved = board.FindFootprintByReference(fp.GetReference())
    moved.SetPosition(pcbnew.VECTOR2I_MM(14, 14)); moved.SetOrientationDegrees(fp.GetOrientationDegrees())
    if routed:
        # Leave the adjacent Ground land with real class clearance while
        # keeping the complete same-face path below the Source 3.5 mm bound.
        for a, b in [((13.5, 14), (13.5, 13.75)),
                     ((13.5, 13.75), (15.25, 12)), ((15.25, 12), (16, 12))]:
            track(board, '/ALPHA', a, b, width=.5)
        track(board, 'GND', (14.5, 14), (15.2, 14), width=.2)
        child = cap.force._copy_family(source, tmp_path / 'child')
        cap.additive._ground_refill(board); cap.field._save_field_snapshot(board, child)
        board = pcbnew.LoadBoard(str(child))
    return source, root, parent, board, proposal


def test_positive_role_requests_do_not_shadow_selected_bypass_owner_key(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    original = source.read_bytes(); roles = proposal['additional_aggregate_capacitors']
    assert set(roles) == {'RENAMED_C'}
    proof = roles['RENAMED_C']; assert proof['no_Source_copper_retirement']
    assert proof['unchanged_selected_bypass_assignments']['AMP73:6:100n'] == 'EXISTING_FEED'
    requests = op.requests(parent, child, proposal)
    assert set(requests) == {'aggregate_cap_feed:' + proof['footprint_uuid'],
        'aggregate_cap_local:' + proof['footprint_uuid'], 'ground:' + proof['ground_pad_uuid']}
    assert 'local_supply:' + proof['source_locality_owner']['pad_uuid'] not in requests
    assert requests['ground:' + proof['ground_pad_uuid']]['reach_mm'] == .8
    local = requests['aggregate_cap_local:' + proof['footprint_uuid']]
    assert local['a']['pad_uuid'] == proof['source_locality_owner']['pad_uuid']
    assert local['b']['pad_uuid'] == proof['supply_pad_uuid']
    assert local['source_maximum_same_surface_path_mm'] == 3.5
    assert local['source_required_surface_layer'] == proof['source_locality_owner']['face']
    assert source.read_bytes() == original


def test_saved_full_width_owner_feed_and_immediate_actual_reference_return(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch, routed=True)
    raw = source.read_bytes(); candidate = Path(child.GetFileName()).read_bytes()
    proof = op.observe(parent, child, proposal)
    assert proof['ok'] and proof['complete']
    row = proof['capacitors']['RENAMED_C']
    assert row['actual_local_path_mm'] <= 3.5 and row['actual_Ground_return_mm'] <= .8
    assert row['full_current_Source_root_connections']
    assert source.read_bytes() == raw
    assert Path(child.GetFileName()).read_bytes() == candidate


@pytest.mark.parametrize('fault', ['owner_absent', 'owner_moves', 'unknown_source', 'noncardinal'])
def test_unproved_Source_or_locality_never_creates_a_macro_role(tmp_path, monkeypatch, fault):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    poses = copy.deepcopy(proposal['poses'])
    if fault == 'owner_absent': poses.pop('AMP73')
    elif fault == 'owner_moves': poses['AMP73'][0] += .1
    elif fault == 'noncardinal': poses['RENAMED_C'][2] += 1
    elif fault == 'unknown_source':
        root.write_text(root.read_text().replace('FIXTURE_VENDOR', 'UNKNOWN'))
    with pytest.raises(ValueError): op.collect(parent, poses, board_hint=str(root))


@pytest.mark.parametrize('fault', ['wrong_rail', 'minimum_reassigned', 'duplicate_identity', 'owner_changed',
    'changed_land', 'changed_package'])
def test_saved_child_cannot_borrow_another_role_or_replace_the_minimum(tmp_path, monkeypatch, fault):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    fp = child.FindFootprintByReference('RENAMED_C')
    if fault == 'wrong_rail': fp.FindPadByNumber('1').SetNet(child.FindNet('GND'))
    elif fault == 'minimum_reassigned': child.FindFootprintByReference('EXISTING_FEED').Move(pcbnew.VECTOR2I_MM(10, 0))
    elif fault == 'duplicate_identity':
        proposal['additional_aggregate_capacitors']['fake'] = copy.deepcopy(proposal['additional_aggregate_capacitors']['RENAMED_C'])
    elif fault == 'owner_changed': child.FindFootprintByReference('AMP73').SetValue('UNKNOWN')
    elif fault == 'changed_land': fp.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(2, 2))
    else: fp.SetFPID(pcbnew.LIB_ID('fixture', 'C_0805_2012Metric'))
    with pytest.raises(ValueError): op.requests(parent, child, proposal)


@pytest.mark.parametrize('fault', ['thin_local', 'missing_local', 'wrong_face_local', 'missing_ground', 'thin_ground'])
def test_broken_saved_paths_never_observe_positive(tmp_path, monkeypatch, fault):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch, routed=True)
    if fault.endswith('_local'):
        # Fault the actual bridge, not the short departure covered by the
        # capacitor's own land and the adjacent full-width track body. That
        # redundant departure can change without breaking the real path.
        originals = {cap.force._uid(t) for t in parent.GetTracks()}
        additions = [t for t in child.GetTracks() if t.GetClass() == 'PCB_TRACK'
                     and t.GetNetname() == '/ALPHA' and cap.force._uid(t) not in originals]
        assert len(additions) == 3
        bridge = max(additions, key=lambda t: t.GetLength())
        assert bridge.GetLength() > 2e6
        original = (bridge.GetWidth(), bridge.GetLayer(), tuple(bridge.GetStart()), tuple(bridge.GetEnd()))
        if fault == 'thin_local': bridge.SetWidth(199999)
        elif fault == 'missing_local': bridge.Move(pcbnew.VECTOR2I_MM(10, 0))
        else: bridge.SetLayer(pcbnew.B_Cu)
        assert original != (bridge.GetWidth(), bridge.GetLayer(), tuple(bridge.GetStart()), tuple(bridge.GetEnd()))
    for t in child.GetTracks():
        if t.GetClass() != 'PCB_TRACK': continue
        if fault == 'missing_ground' and t.GetNetname() == 'GND': t.Move(pcbnew.VECTOR2I_MM(10, 0))
        if fault == 'thin_ground' and t.GetNetname() == 'GND': t.SetWidth(100000)
    with pytest.raises(ValueError): op.observe(parent, child, proposal)


@pytest.mark.parametrize('fault', ['thin_covered_departure', 'missing_covered_departure', 'wrong_face_covered_departure'])
def test_redundant_covered_departure_is_not_mistaken_for_a_broken_actual_path(tmp_path, monkeypatch, fault):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch, routed=True)
    originals = {cap.force._uid(t) for t in parent.GetTracks()}
    additions = [t for t in child.GetTracks() if t.GetClass() == 'PCB_TRACK'
                 and t.GetNetname() == '/ALPHA' and cap.force._uid(t) not in originals]
    assert len(additions) == 3
    covered = min(additions, key=lambda t: t.GetLength())
    assert covered.GetLength() == 250000
    if fault == 'thin_covered_departure': covered.SetWidth(199999)
    elif fault == 'missing_covered_departure': covered.Move(pcbnew.VECTOR2I_MM(10, 0))
    else: covered.SetLayer(pcbnew.B_Cu)
    proof = op.observe(parent, child, proposal)
    assert proof['ok'] and proof['complete']
    assert proof['capacitors']['RENAMED_C']['actual_local_path_mm'] <= 3.5


def test_carrier_menu_excludes_all_retired_strokes_and_moving_source_roots(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    proof = proposal['additional_aggregate_capacitors']['RENAMED_C']
    inventory = proof['source_supply_inventory']
    proposal['retired_track_uuids'] = [s['native_uuid'] for s in inventory['retained_full_width_strokes']]
    requests = op.requests(parent, child, proposal)
    feed = requests['aggregate_cap_feed:' + proof['footprint_uuid']]
    assert 'pad_uuid' in feed['b'] and feed['b']['pad_uuid'] in inventory['root_pad_uuids']


def test_actual_missing_carrier_is_not_selected_when_retirement_list_omits_it(tmp_path, monkeypatch):
    from cec_native_items import discard_items
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    proof = proposal['additional_aggregate_capacitors']['RENAMED_C']
    carriers = {s['native_uuid'] for s in proof['source_supply_inventory']['retained_full_width_strokes']}
    assert carriers and not proposal['retired_track_uuids']
    discard_items(child, [t for t in child.GetTracks() if cap.force._uid(t) in carriers])
    requests = op.requests(parent, child, proposal)
    feed = requests['aggregate_cap_feed:' + proof['footprint_uuid']]
    assert not set(feed['b'].get('native_uuids', ())) & carriers
    assert feed['b']['pad_uuid'] in proof['source_supply_inventory']['root_pad_uuids']


def test_moving_Source_pad_and_absent_strokes_cannot_leave_a_fictional_carrier(tmp_path, monkeypatch):
    from cec_native_items import discard_items
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    source_fp = child.FindFootprintByReference('EXISTING_FEED')
    source_fp.Move(pcbnew.VECTOR2I_MM(.1, 0))
    proposal['poses']['EXISTING_FEED'] = [source_fp.GetPosition().x / 1e6,
        source_fp.GetPosition().y / 1e6, source_fp.GetOrientationDegrees()]
    inventory = proposal['additional_aggregate_capacitors']['RENAMED_C']['source_supply_inventory']
    ids = {s['native_uuid'] for s in inventory['retained_full_width_strokes']}
    discard_items(child, [t for t in child.GetTracks() if cap.force._uid(t) in ids])
    with pytest.raises(ValueError, match='no_surviving_full_current_Source_carrier'):
        op.requests(parent, child, proposal)


def test_selected_caps_are_not_reclassified_and_no_additional_role_is_a_noop(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    owner = parent.FindFootprintByReference('AMP73'); selected = parent.FindFootprintByReference('EXISTING_FEED')
    poses = {'AMP73': [owner.GetPosition().x / 1e6, owner.GetPosition().y / 1e6, owner.GetOrientationDegrees()],
        'EXISTING_FEED': [selected.GetPosition().x / 1e6 + .1, selected.GetPosition().y / 1e6, selected.GetOrientationDegrees()]}
    assert op.collect(parent, poses, board_hint=str(root)) == {}
    parent.SetFileName('')
    assert op.collect(parent, poses, board_hint=str(root)) == {}
    assert op.requests(parent, child, dict(additional_aggregate_capacitors={})) == {}


def test_recovery_may_derive_unique_owner_but_default_requires_explicit_stationary_witness(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    poses = {'RENAMED_C': proposal['poses']['RENAMED_C']}
    with pytest.raises(ValueError): op.collect(parent, poses, board_hint=str(root))
    assert op.collect(parent, poses, board_hint=str(root), require_explicit_owner=False) == proposal['additional_aggregate_capacitors']


def test_actual_center_distance_is_not_replaced_by_a_short_pad_edge_path(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    proposal['poses']['RENAMED_C'] = [12, 14, 0]
    proposal['additional_aggregate_capacitors'] = op.collect(parent, proposal['poses'], board_hint=str(root))
    child.FindFootprintByReference('RENAMED_C').SetPosition(pcbnew.VECTOR2I_MM(12, 14))
    with pytest.raises(ValueError, match='actual_owner_locality'): op.requests(parent, child, proposal)


def test_original_incident_Ground_metal_cannot_be_retired_by_this_role(tmp_path, monkeypatch):
    source, root, parent, child, proposal = fixture(tmp_path, monkeypatch)
    old_ground = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('2')
    at = [v / 1e6 for v in old_ground.GetPosition()]
    track(parent, 'GND', at, [at[0], at[1] + .5], width=.2)
    cap.field._save_field_snapshot(parent, source)
    with pytest.raises(ValueError, match='old_Ground_copper'): op.collect(parent, proposal['poses'], board_hint=str(root))
