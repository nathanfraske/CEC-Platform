"""Closed reference maps must not hide two distinct measurement obligations.

Native Source maps, literal straps, fixed contacts and priority replay run
through their real implementations. No board/refdes/coordinate exception.
"""
import copy
import time

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_priority_preflight as priority
import cec_measurement_leaf as leaf
import cec_source_reference_group_transport as maps
from test_measurement_auxiliary_cut import fixture as native_case
from test_source_measurement_auxiliary_join import annotation


def case(tmp_path, quarter=0, back=False, fault=None):
    board, source, owner, strap, departure = native_case(tmp_path)
    owner.SetReference('Q24')
    group = annotation(board, owner, fault)
    if quarter:
        angle = pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(20,20), angle)
        for item in board.GetDrawings():
            if item.GetClass() == 'PCB_TEXT': item.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    if back:
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Flip(pcbnew.VECTOR2I_MM(20,20), False)
    field._save_field_snapshot(board, source)
    parent = pcbnew.LoadBoard(str(source))
    uid = force._uid(owner.FindPadByNumber('9'))
    return parent, source, uid, force._uid(group), force._uid(strap), force._uid(departure)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_optin_rederives_real_saved_map_and_keeps_both_native_cuts(tmp_path, quarter, back):
    board, source, uid, group, strap, departure = case(tmp_path, quarter, back)
    before = source.read_bytes(), row._source_binding(board)
    with pytest.raises(ValueError): leaf.plan_with_auxiliary_strap(board, uid)
    outer, inner = leaf.plan_with_auxiliary_strap(board, uid, allow_source_reference_maps=True)
    assert outer['track_uuids'] == [departure]
    assert inner['track_uuids'] == [strap]
    assert inner['source_reference_map']['group_uuid'] == group
    assert outer['separately_owned_source_auxiliary_strap'] == inner
    assert (source.read_bytes(), row._source_binding(board)) == before
    assert not inner['current_authority'] and not inner['release_authority']


@pytest.mark.parametrize('fault', ['arbitrary', 'copper', 'pad', 'nested'])
def test_optin_cannot_turn_a_group_name_into_copper_authority(tmp_path, fault):
    board, source, uid, *_ = case(tmp_path, fault=fault)
    before = source.read_bytes(), row._source_binding(board)
    with pytest.raises(ValueError):
        leaf.plan_with_auxiliary_strap(board, uid, allow_source_reference_maps=True)
    assert (source.read_bytes(), row._source_binding(board)) == before


@pytest.mark.parametrize('fault', ['members', 'source', 'group', 'width', 'missing_map'])
def test_mapped_strap_context_is_independently_rederived(tmp_path, fault):
    board, source, uid, *_ = case(tmp_path)
    outer, proof = leaf.plan_with_auxiliary_strap(board, uid, allow_source_reference_maps=True)
    proof = copy.deepcopy(proof)
    if fault == 'members': proof['source_reference_map']['member_uuids'].append('invented')
    elif fault == 'source': proof['source_reference_map']['source_sha256'] = 'not-source'
    elif fault == 'group': proof['source_reference_map']['group_uuid'] = 'not-group'
    elif fault == 'width': proof['width_nm'] += 1
    else: del proof['source_reference_map']
    before = source.read_bytes(), row._source_binding(board)
    with pytest.raises(ValueError):
        leaf._plan(board, uid, role='measurement', timeout_s=10., max_tracks=16,
            max_length_mm=24., source_auxiliary_strap=proof)
    assert (source.read_bytes(), row._source_binding(board)) == before


@pytest.mark.parametrize('flag', [None, 0, 1, 'yes', {}, []])
def test_map_optin_is_a_boolean_before_native_access(flag):
    with pytest.raises(ValueError):
        leaf.plan_with_auxiliary_strap(None, 'unknown', allow_source_reference_maps=flag)


def test_priority_replay_rederives_the_map_as_well_as_both_copper_scopes(tmp_path, monkeypatch):
    board, source, uid, group, *_ = case(tmp_path)
    outer, inner = leaf.plan_with_auxiliary_strap(board, uid, allow_source_reference_maps=True)
    child = pcbnew.LoadBoard(str(source))
    owner = child.FindFootprintByReference(outer['owner'])
    owner.Move(pcbnew.VECTOR2I_MM(.5,.5))
    # Priority tests only the real original conductors and selected moved
    # owner. Actual map transport belongs to the separate saved macro gate.
    moved = dict(scope='provisional_source_owned_smd_cohort_endpoint_transport', changes=[],
        moved_owner_footprint_uuids=[force._uid(owner)])
    monkeypatch.setattr(priority.topology, 'route_width_contracts', lambda *a, **k: {
        outer['net']: dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(priority.fr, 'locked_pour_authority_nets_board', lambda *a, **k: {outer['net']})
    retired = outer['track_uuids'] + inner['track_uuids']
    result = priority.inspect(board, child, moved, board_hint='opaque',
        source_measurement_leaves=[outer, inner], retired_source_track_uuids=retired)
    assert result['ok'], result
    assert result['independently_typed_source_measurement_reconstruction'] == [outer, inner]
    assert not result['release_authority']


def test_complete_prepare_requires_the_exact_declared_map_group(tmp_path, monkeypatch):
    board, source, uid, group, *_ = case(tmp_path)
    fp = next(f for f in board.GetFootprints() if f.GetReference() == 'Q24')
    cap = pcbnew.FOOTPRINT(board); cap.SetReference('renamed_cap'); cap.SetValue('100nF')
    cap.SetPosition(pcbnew.VECTOR2I_MM(26,6)); board.Add(cap)
    for pin, net, x in [('1','RAIL',26), ('2','GND',27)]:
        p = pcbnew.PAD(cap); p.SetNumber(pin); p.SetNet(board.FindNet(net))
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        cap.Add(p); p.SetPosition(pcbnew.VECTOR2I_MM(x,6))
    field._save_field_snapshot(board, source)
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **k: dict(
        assigned={'source': dict(cap_ref=cap.GetReference(), requirement=dict(
            ref=fp.GetReference(), pin='6', rail='RAIL', return_rail='GND'))}))
    monkeypatch.setattr(escape.topology, 'board_current_domains', lambda *a, **k: {})
    monkeypatch.setattr(escape.fr, 'coupled_pair_nets', lambda *a, **k: set())
    poses = {f.GetReference(): [f.GetPosition().x/1e6, f.GetPosition().y/1e6+.2,
        f.GetOrientationDegrees()] for f in (fp, cap)}
    before = source.read_bytes(), row._source_binding(board)
    with pytest.raises(ValueError): escape.prepare(board, poses, board_hint='opaque')
    proposal = escape.prepare(board, poses, board_hint='opaque', reference_group_uuids=[group])
    kinds = {q['scope'] for q in proposal['measurement_leaves']}
    assert {'source_typed_thin_measurement_leaf',
        'source_typed_same_net_auxiliary_measurement_strap'} <= kinds
    assert proposal['reference_group_uuids'] == [group]
    assert (source.read_bytes(), row._source_binding(board)) == before
