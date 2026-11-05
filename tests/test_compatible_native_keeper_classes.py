"""Registered outline generators are not different fabrication processes."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_multi_keeper_contour as owner
import cec_multi_keeper_contour_stage as stage
from test_multi_keeper_contour import fixture


def keeper_case(tmp_path, face=pcbnew.F_Cu, rotate=False, reverse=False):
    b, source, track, zones = fixture(tmp_path, face, rotate)
    zones[int(reverse)].SetZoneName(owner.owner.ZONE_NAME)
    field._save_field_snapshot(b, source)
    kwargs = dict(allow_locked_source=True, fill_policy='source_preserving_regions',
        clip_native_additions=True, native_addition_inset_nm=1)
    return b, source, track, zones, kwargs


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu, 6])
@pytest.mark.parametrize('rotate', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
def test_different_registered_classes_keep_all_physical_settings_and_replay(tmp_path, face, rotate, reverse):
    b, source, track, zones, kwargs = keeper_case(tmp_path, face, rotate, reverse)
    original = source.read_bytes()
    with pytest.raises(owner.Refused, match='exact_compatible_ungrouped'):
        owner.plan(source, [force._uid(track)], **kwargs)
    p = owner.plan(source, [force._uid(track)], **kwargs, allow_compatible_keeper_classes=True)
    assert len({z['configuration']['name'] for z in p['source_zones']}) == 2
    child = force._copy_family(source, tmp_path/'child')
    c = pcbnew.LoadBoard(str(child)); made = owner.construct(c, p)
    field._save_field_snapshot(c, child)
    proof = owner.receive(source, child, [dict(plan=p, materialized=made)], board_hint='synthetic')
    assert proof['ok'] and proof['complete'], proof['errors']
    _, before = additive._nodes(source); _, after = additive._nodes(child)
    kept = p['keeper_uuid']
    assert owner._process(before[kept]) == owner._process(after[kept])
    assert syntax._freeze(before[force._uid(track)]) == syntax._freeze(after[force._uid(track)])
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['unknown_name', 'clearance', 'min_thickness', 'thermal_gap',
    'thermal_bridge', 'islands', 'lock', 'group', 'priority', 'connection'])
def test_class_compatibility_never_waives_an_actual_process_or_owner_difference(tmp_path, fault):
    b, source, track, zones, kwargs = keeper_case(tmp_path)
    z = zones[1]
    if fault == 'unknown_name': z.SetZoneName('UNREGISTERED_PROCESS')
    elif fault == 'clearance': z.SetLocalClearance(250000)
    elif fault == 'min_thickness': z.SetMinThickness(110000)
    elif fault == 'thermal_gap': z.SetThermalReliefGap(333333)
    elif fault == 'thermal_bridge': z.SetThermalReliefSpokeWidth(333333)
    elif fault == 'islands': z.SetIslandRemovalMode(2)
    elif fault == 'lock': z.SetLocked(False)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(b); b.Add(group); group.AddItem(z)
    elif fault == 'priority': z.SetAssignedPriority(1)
    elif fault == 'connection': z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    field._save_field_snapshot(b, source); original = source.read_bytes()
    with pytest.raises(owner.Refused):
        owner.plan(source, [force._uid(track)], **kwargs, allow_compatible_keeper_classes=True)
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['drop_policy', 'bad_policy', 'change_name', 'change_fill', 'forge_process'])
def test_rehashed_plan_is_not_a_process_name_or_geometry_oracle(tmp_path, fault):
    b, source, track, zones, kwargs = keeper_case(tmp_path)
    p = owner.plan(source, [force._uid(track)], **kwargs, allow_compatible_keeper_classes=True)
    if fault == 'drop_policy': p.pop('allow_compatible_keeper_classes')
    elif fault == 'bad_policy': p['allow_compatible_keeper_classes'] = 1
    elif fault == 'change_name': p['source_zones'][0]['configuration']['name'] = 'UNREGISTERED'
    elif fault == 'change_fill': p['source_zones'][0]['fill'][0][0][0][0] += 1000
    elif fault == 'forge_process': p['source_process_sha256'] = '0'*64
    p.pop('plan_sha256'); p['plan_sha256'] = owner.owner._digest(p)
    original = field._field_snapshot_inventory(b)
    with pytest.raises(owner.Refused): owner.construct(b, p)
    assert field._field_snapshot_inventory(b) == original


@pytest.mark.parametrize('fault', ['source_name', 'candidate_name', 'candidate_unknown_setting'])
def test_saved_phase_binds_actual_names_and_even_inactive_process_settings(tmp_path, fault):
    b, source, track, zones, kwargs = keeper_case(tmp_path)
    p = owner.plan(source, [force._uid(track)], **kwargs, allow_compatible_keeper_classes=True)
    child = force._copy_family(source, tmp_path/'child'); c = pcbnew.LoadBoard(str(child))
    made = owner.construct(c, p); field._save_field_snapshot(c, child)
    target = source if fault == 'source_name' else child
    changed = pcbnew.LoadBoard(str(target)); z = next(iter(changed.Zones()))
    if fault == 'candidate_unknown_setting': z.SetThermalReliefGap(333333)
    else: z.SetZoneName('UNREGISTERED')
    field._save_field_snapshot(changed, target)
    original = [path.read_bytes() for path in (source, child)]
    proof = owner.receive(source, child, [dict(plan=p, materialized=made)], board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']
    assert original == [path.read_bytes() for path in (source, child)]


@pytest.mark.parametrize('value,fill_policy', [(1, 'source_preserving_regions'),
    (True, 'native'), ('yes', 'source_preserving_regions')])
def test_explicit_source_preserving_policy_is_required_before_output(tmp_path, value, fill_policy):
    b, source, track, zones, kwargs = keeper_case(tmp_path)
    kwargs['fill_policy'] = fill_policy
    with pytest.raises(owner.Refused, match='compatible_keeper_class_policy'):
        owner.plan(source, [force._uid(track)], **kwargs, allow_compatible_keeper_classes=value)
    out = tmp_path/'stage'
    with pytest.raises(ValueError):
        stage.run(source, out, board_hint='synthetic', expected_source_sha256=force._hash(source),
            reporting_build=tmp_path/'native', allow_compatible_keeper_classes=value, fill_policy=fill_policy)
    assert not out.exists()
