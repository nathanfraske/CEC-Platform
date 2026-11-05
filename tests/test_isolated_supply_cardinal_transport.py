"""Whole isolated supply cohorts rotate; separately posed lands cannot.

Every positive uses real KiCad footprints, copper, groups and connectivity.
No synthetic success receipt or mocked native ownership is involved.
"""
import copy
import math

import pcbnew
import pytest

import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_force_current as force
import cec_smd_macro_transport as macro
import cec_source_supply_endpoint_cut as supply
from test_isolated_selected_bypass_supply_transport_20261026 import fixture, options, HINT
from test_isolated_supply_port_projection_20261026 import fixture as port_fixture
from test_field_proposals import track


def rotate_owners(board, turn, *, pivot=(15, 15), shift=(1.2, .8)):
    for fp in board.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I_MM(*pivot), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
        fp.Move(pcbnew.VECTOR2I_MM(*shift))


def apply(source, child, path, **kw):
    return macro.apply(source, child, source_path=path, board_hint=HINT,
        maximum_shift_mm=32., allow_cardinal_rotations=True,
        rebuild_source_ground_endpoints=True, rebuild_source_supply_endpoints=True,
        allow_owned_locked_ground_endpoints=True, **kw)


@pytest.mark.parametrize('turn', [90, 180, 270])
@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('back', [False, True])
def test_complete_native_cardinal_cohort_and_saved_reconstruction(tmp_path, turn, quarter, mirror, back):
    parent, _, path, ids, remote, group = fixture(tmp_path, quarter, mirror, back)
    child = pcbnew.LoadBoard(str(path))
    rotate_owners(child, turn)
    old_bytes = path.read_bytes()
    old = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd()), t.GetLength())
           for t in parent.GetTracks()}
    packet = apply(parent, child, path)
    proof, = packet['rigid_isolated_selected_bypass_supply_components']
    assert proof['cardinal_transform']['turn_deg'] == turn
    assert set(proof['track_uuids']) == set(ids)
    for t in child.GetTracks():
        uid = force._uid(t)
        if uid in ids:
            assert tuple(t.GetStart()) == supply.component_point(proof, old[uid][0])
            assert tuple(t.GetEnd()) == supply.component_point(proof, old[uid][1])
            assert math.isclose(t.GetLength(), old[uid][2], abs_tol=1e-6)
            assert t.IsLocked()
        else:
            assert uid == remote and (tuple(t.GetStart()), tuple(t.GetEnd())) == old[uid][:2]
    assert proof['partial_source_groups'][0]['stationary_members'] == [remote]
    assert not proof['inherited_neckdown_debt_qualified']
    assert not proof['new_thin_allowance'] and not packet['saved_candidate_authorized']
    saved = force._copy_family(path, tmp_path / 'saved')
    field._save_field_snapshot(child, saved)
    assert supply.verify_isolated_components(parent, pcbnew.LoadBoard(str(saved)), [proof],
        **options(), allow_cardinal_rotations=True)
    assert path.read_bytes() == old_bytes


@pytest.mark.parametrize('fault', ['cap_shift', 'cap_turn', 'owner_noncardinal', 'pad_shift',
    'pad_orientation', 'pad_net', 'pad_size', 'pad_layer', 'no_permission', 'float_permission'])
def test_not_one_common_native_transform_is_rejected_before_copper_write(tmp_path, fault):
    parent, _, path, ids, remote, group = fixture(tmp_path)
    child = pcbnew.LoadBoard(str(path)); rotate_owners(child, 180)
    cap = child.FindFootprintByReference('C_RENAMED')
    owner = child.FindFootprintByReference('RENAMED_MONITOR')
    pad = owner.FindPadByNumber('6')
    kw = dict(options(), allow_cardinal_rotations=True)
    if fault == 'cap_shift': cap.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'cap_turn': cap.SetOrientationDegrees(90)
    elif fault == 'owner_noncardinal': owner.SetOrientationDegrees(179.99)
    elif fault == 'pad_shift': pad.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_orientation': pad.SetOrientationDegrees(179.99)
    elif fault == 'pad_net': pad.SetNet(child.FindNet('OTHER'))
    elif fault == 'pad_size': pad.SetSize(pad.GetSize() + pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_layer':
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
    elif fault == 'no_permission': kw['allow_cardinal_rotations'] = False
    else: kw['allow_cardinal_rotations'] = 1.
    before = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}
    with pytest.raises(ValueError): supply.isolated_components(parent, child, **kw)
    assert before == {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}


@pytest.mark.parametrize('fault', ['turn', 'source_origin', 'candidate_origin', 'delta', 'extra', 'bool'])
def test_forged_transform_never_survives_saved_whole_component_rederivation(tmp_path, fault):
    parent, _, path, ids, remote, group = fixture(tmp_path)
    child = pcbnew.LoadBoard(str(path)); rotate_owners(child, 180)
    proof = copy.deepcopy(apply(parent, child, path)['rigid_isolated_selected_bypass_supply_components'])
    transform = proof[0]['cardinal_transform']
    if fault == 'turn': transform['turn_deg'] = 90
    elif fault == 'source_origin': transform['source_origin_nm'][0] += 1
    elif fault == 'candidate_origin': transform['candidate_origin_nm'][0] += 1
    elif fault == 'delta': proof[0]['delta_nm'][0] += 1
    elif fault == 'extra': transform['unknown'] = 1
    else: transform['turn_deg'] = True
    with pytest.raises(ValueError):
        supply.verify_isolated_components(parent, child, proof, **options(), allow_cardinal_rotations=True)


@pytest.mark.parametrize('same_net', [False, True])
def test_real_new_destination_contact_rejects_and_restores_rotated_tracks(tmp_path, same_net):
    parent, _, path, ids, remote, group = fixture(tmp_path)
    # The new 180-degree transformed branch crosses x20..21.2/y20.8.
    track(parent, '+3V3' if same_net else 'OTHER', (21., 20.75), (21., 20.85), width=.2)
    field._save_field_snapshot(parent, path)
    child = pcbnew.LoadBoard(str(path)); rotate_owners(child, 180)
    before = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}
    with pytest.raises(ValueError, match='transported_isolated_supply'):
        apply(parent, child, path)
    assert before == {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}


@pytest.mark.parametrize('turn', [90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_complete_compiler_projects_every_rotated_isolated_port(tmp_path, turn, back):
    path, group, main = port_fixture(tmp_path, back)
    native = pcbnew.LoadBoard(str(path))
    rotate_owners(native, turn, shift=(4., 0.))
    poses = {f.GetReference(): [v / 1e6 for v in f.GetPosition()] + [f.GetOrientationDegrees()]
             for f in native.GetFootprints()}
    kwargs = dict(board_hint=HINT, max_shift_mm=32., allow_owned_locked_escapes=True,
        rebuild_projected_ground=True, reference_group_uuids=[group],
        compilation_phase_timeouts_s=[10., 10., 10.])
    posed, packet = compiler.compile(path, poses, **kwargs)
    proof, = packet['transport']['rigid_isolated_selected_bypass_supply_components']
    assert proof['cardinal_transform']['turn_deg'] == turn
    retained = {k: r for k, r in packet['requests'].items() if k.startswith('retained:')}
    assert len(retained) == 3 and main not in packet['retired_track_uuids']
    for request in retained.values():
        at = pcbnew.VECTOR2I(*request['b']['at_nm'])
        assert all(next(t for t in posed.GetTracks() if force._uid(t) == u).GetEffectiveShape(
            proof['layer_id']).Collide(at, 0) for u in request['b']['native_uuids'])
    _, again = compiler.compile(path, packet['source_plan']['poses'], **kwargs)
    assert again['requests'] == packet['requests']
    assert again['transport']['rigid_isolated_selected_bypass_supply_components'] == [proof]
    assert not packet['routing_admitted'] and not packet['saved_candidate_authorized']


@pytest.mark.parametrize('turn', [90, 180, 270])
@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_fixed_supply_land_pivot_cannot_acquire_or_needlessly_move_fixed_branch(tmp_path, turn, quarter, back):
    parent, _, path, ids, remote, group = fixture(tmp_path, quarter, back=back)
    child = pcbnew.LoadBoard(str(path)); cap = child.FindFootprintByReference('C_RENAMED')
    cap.Rotate(cap.FindPadByNumber('1').GetPosition(), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
    before = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth(), t.IsLocked())
              for t in child.GetTracks()}
    # The supply endpoint is stationary even though this capacitor pivots.
    # There is deliberately no Ground conductor in this fixture: the full
    # macro correctly requires an actual conductor change and is therefore
    # not the owner of this isolated-supply observation.
    components = supply.isolated_components(parent, child, **options(),
        allow_cardinal_rotations=True)
    assert components == []
    assert before == {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth(), t.IsLocked())
                      for t in child.GetTracks()}


@pytest.mark.parametrize('fault', ['shape', 'supply_track'])
def test_fixed_center_alone_does_not_prove_unchanged_supply_metal(tmp_path, fault):
    parent, _, path, ids, remote, group = fixture(tmp_path)
    child = pcbnew.LoadBoard(str(path)); cap = child.FindFootprintByReference('C_RENAMED')
    cap.Rotate(cap.FindPadByNumber('1').GetPosition(), pcbnew.EDA_ANGLE(180, pcbnew.DEGREES_T))
    if fault == 'shape':cap.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.7, .6))
    else:next(t for t in child.GetTracks() if force._uid(t) == ids[-1]).SetWidth(500001)
    with pytest.raises(ValueError):
        supply.isolated_components(parent, child, **options(), allow_cardinal_rotations=True)
