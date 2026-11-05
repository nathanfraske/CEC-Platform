"""Source-exact additive keeper pockets, including frozen legacy regional debt.

Every incumbent filled record, conductor, pad, barrel and process field stays
literal. Fresh native additions are clipped to every stronger same-net void
and filtered by the same source feature/anchor policy. Existing intrusion is
not qualified or extended: it remains literal source debt. This independent
changed-copper operation does not loosen the older absolute-region operation.
"""
import json
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_fill_geometry as fills
import cec_ordinary_route_receiving as ordinary
import cec_regional_fill as regional
import cec_rectilinear_copper as native
import cec_rounded_landing as landing
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_ground_return_preservation as ground
import cec_shallow_copper_pocket_cover as pockets

POLICY = 'literal-source-fill-retaining-additive-shallow-keeper-pocket-v1'
def require(value, message):
    if not value: raise ValueError(message)
def plain(value): return json.loads(json.dumps(value, allow_nan=False))


def plan(source, *, board_hint, zone_uuid, candidate_index=0, maximum_depth_nm=500000, maximum_span_nm=4000000):
    source = Path(source).resolve(); b = pcbnew.LoadBoard(str(source)); epoch = force._code_identity()
    require(type(board_hint) is str and board_hint and type(candidate_index) is int and 0 <= candidate_index < 64,
        'bounded_source_keeper_pocket_context_required')
    zones = {force._uid(z): z for z in b.Zones()}
    require(zone_uuid in zones and len(zones) <= 8192, 'actual_unique_source_keeper_required')
    z = zones[zone_uuid]; face = int(z.GetFirstLayer()); config = landing._configuration(z)
    from cec_native_contour_regions import ZONE_NAME as signed_name
    require(config['name'] in (native.ZONE_NAME, signed_name) and config['layers'] == [face]
        and not z.GetIsRuleArea() and config['net'] and config['net'].rsplit('/', 1)[-1] != 'GND'
        and config['connection'] == int(pcbnew.ZONE_CONNECTION_FULL) and config['smoothing'] == 0
        and z.IsFilled() and z.HasFilledPolysForLayer(face), 'registered_solid_single_face_actual_keeper_required')
    require(z.Outline().OutlineCount() == 1 and not z.Outline().HoleCount(0), 'simple_authored_keeper_pocket_required')
    ring = z.Outline().Outline(0)
    points = [[ring.CPoint(i).x, ring.CPoint(i).y] for i in range(ring.PointCount())]
    offers = pockets.candidates(points, maximum_depth_nm=maximum_depth_nm, maximum_span_nm=maximum_span_nm)
    require(candidate_index < len(offers), 'no_source_shallow_pocket_in_finite_portfolio')
    offer = offers[candidate_index]
    addition = native._poly(offer['points_nm']); addition.BooleanSubtract(z.Outline())
    native._require_unoccupied_outline(b, addition, config['net'], face, time.monotonic()+10.,
        clearance_nm=config['clearance_nm'], allow_native_hole_bridges=True)
    protected = []
    for other in zones.values():
        if (other is z or other.GetIsRuleArea() or not other.IsOnLayer(face) or other.GetNetname() != config['net']
                or other.GetAssignedPriority() <= config['priority']): continue
        overlap = other.Outline().CloneDropTriangulation(); overlap.BooleanIntersection(native._poly(offer['points_nm']))
        if not overlap.OutlineCount(): continue
        protected.append(dict(native=native._support_row(other, face, time.monotonic()+10., allow_native_hole_bridges=True),
            configuration=landing._configuration(other)))
    require(len(protected) <= 64, 'finite_source_regional_pocket_inventory_required')
    source_snapshot = landing._native_source(z, allow_complex_fill=True)
    helper = dict(fill_policy='source_preserving_regions', net=config['net'], layer_id=face,
        min_thickness_nm=config['min_thickness_nm'], supporting_zones=[],
        regional_fill_binding=dict(source_zone_uuid=zone_uuid, protected_regions=protected,
            source_island=bool(z.IsIsland(face, 0)),
            source_islands=[bool(z.IsIsland(face, i)) for i in range(z.GetFilledPolysList(face).OutlineCount())]))
    require(epoch == force._code_identity(), 'source_keeper_pocket_runtime_changed')
    return plain(dict(policy=POLICY, source_sha256=force._hash(source), code_identity=epoch,
        authority_sha256=force._hash(Path(__file__)), geometry_authority_sha256=force._hash(Path(pockets.__file__)),
        board_hint=board_hint, zone_uuid=zone_uuid, candidate_index=candidate_index,
        maximum_depth_nm=maximum_depth_nm, maximum_span_nm=maximum_span_nm,
        source_keeper=source_snapshot, source_configuration=config, selected_pocket=offer,
        regional_combination_contract=helper, original_fill_records_must_stay_literal=True,
        current_or_barrel_qualified=False, inherited_regional_intrusion_qualified=False, release_authority=False))


def args(proposal):
    return {key: proposal[key] for key in ('board_hint', 'zone_uuid', 'candidate_index', 'maximum_depth_nm', 'maximum_span_nm')}


def construct(source, proposal):
    require(plan(source, **args(proposal)) == proposal, 'stale_or_forged_source_keeper_pocket_plan')
    original, child = [pcbnew.LoadBoard(str(source)) for _ in range(2)]
    zone = next(z for z in child.Zones() if force._uid(z) == proposal['zone_uuid'])
    face = proposal['source_configuration']['layers'][0]
    zone.UnFill(); zone.Outline().RemoveAllContours(); zone.Outline().Append(native._poly(proposal['selected_pocket']['points_nm']))
    batch = pcbnew.ZONES(); batch.append(zone)
    import cec_zone_fill
    cec_zone_fill.compile_selected(child, batch, timeout_s=10.)
    result = regional._combine(original, zone.GetFilledPolysList(face), proposal['regional_combination_contract'], time.monotonic()+10.)
    zone.UnFill(); zone.SetFilledPolysList(face, result); zone.SetIsFilled(True)
    flags = proposal['regional_combination_contract']['regional_fill_binding']['source_islands']
    for i, flag in enumerate(flags):
        if flag: zone.SetIsIsland(face, result.OutlineCount()-len(flags)+i)
    # Only Ground on the actually modified face may need new antipads. Leave
    # untouched dedicated reference faces literal instead of globally refilling.
    ground_zones = pcbnew.ZONES()
    for other in child.Zones():
        if not other.GetIsRuleArea() and other.GetNetname() == 'GND' and other.IsOnLayer(face): ground_zones.append(other)
    if ground_zones.size(): cec_zone_fill.compile_selected(child, ground_zones, timeout_s=10.)
    return child


def receive(source, candidate, proposal, *, board_hint):
    result = dict(ok=False, complete=False, errors=[], current_or_barrel_qualified=False,
        inherited_regional_intrusion_qualified=False, release_authority=False)
    try:
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        require(source != candidate and board_hint == proposal['board_hint'], 'actual_source_pocket_child_required')
        epoch = force._code_identity(); families = [force._family(q, board_hint) for q in (source, candidate)]
        replay = construct(source, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-source-pocket-') as work:
            expected = force._copy_family(source, Path(work)/'expected'); field._save_field_snapshot(replay, expected)
            require(syntax._freeze(additive._nodes(expected)[0]) == syntax._freeze(additive._nodes(candidate)[0]),
                'source_pocket_changed_unowned_saved_native_evidence')
        require(force._sidecars(source) == force._sidecars(candidate)
            and force._preservation_snapshot(source)[1] == force._preservation_snapshot(candidate)[1],
            'source_pocket_fields_parts_rules_or_stack_changed')
        before, after = [pcbnew.LoadBoard(str(q)) for q in (source, candidate)]
        zone0, zone1 = [next(z for z in b.Zones() if force._uid(z) == proposal['zone_uuid']) for b in (before, after)]
        require(landing._configuration(zone0) == landing._configuration(zone1), 'source_keeper_process_or_owner_changed')
        face = proposal['source_configuration']['layers'][0]
        require(regional.exact_source_contour_present(zone1.GetFilledPolysList(face), zone0.GetFilledPolysList(face), time.monotonic()+10.),
            'every_original_keeper_filled_record_must_be_literal')
        old = zone0.GetFilledPolysList(face); new = zone1.GetFilledPolysList(face)
        fresh = new.CloneDropTriangulation(); fresh.BooleanSubtract(old)
        for region in proposal['regional_combination_contract']['regional_fill_binding']['protected_regions']:
            item = next(z for z in before.Zones() if force._uid(z) == region['native']['uuid'])
            void = item.Outline().CloneDropTriangulation(); void.BooleanSubtract(item.GetFilledPolysList(face))
            intrusion = fresh.CloneDropTriangulation(); intrusion.BooleanIntersection(void)
            require(not intrusion.OutlineCount(), 'new_copper_intruded_into_an_unchanged_stronger_void')
        parts = ordinary._partition(before, time.monotonic()+10.)
        actual = ordinary._partition(after, time.monotonic()+10., retained_keys=set().union(*parts))
        require(all(any(part <= row for row in actual) for part in parts), 'source_pocket_lost_native_partition')
        debt = current.receive(source, candidate, board_hint=board_hint)
        require(debt['ok'] and debt['complete'], 'source_pocket_current_debt_regressed_or_unknown')
        returns = ground.receive(before, after, timeout_s=10.)
        require(returns['ok'] and returns['complete'], 'source_pocket_ground_return_regressed')
        with force._thermal_hint(board_hint):
            blockers = sorted(field.blocker_keys(field.field_coupling_summary(str(candidate))) - field.blocker_keys(field.field_coupling_summary(str(source))))
        require(not blockers, 'source_pocket_new_field_blocker')
        first, last = [sense.replay(q, board_hint=board_hint, timeout_s=40.) for q in (source, candidate)]
        net = proposal['source_configuration']['net']
        for evidence in (first, last):
            require(all(row.get('ok') is True for row in evidence['clipped_isolation']['details'] if row['net'] == net),
                'changed_keeper_requires_positive_absolute_source_and_candidate_cuts')
        cuts = sense.compare_contour_preservation(first, last, modified_nets=[net])
        require(cuts['same_evidence'] and cuts['comparison_complete'], 'source_pocket_clipped_kelvin_or_unaffected_evidence_changed')
        require(epoch == force._code_identity() and families == [force._family(q, board_hint) for q in (source, candidate)], 'source_pocket_family_or_runtime_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            code_identity=epoch, exact_saved_native_source_reconstruction=True,
            every_source_filled_record_and_all_conductors_literal=True, no_new_stronger_regional_intrusion=True,
            source_current_receiving=debt, all_native_partitions_preserved=True, source_ground_return_receiving=returns,
            physical_kelvin_preservation=cuts, new_field_blockers=blockers,
            uncapped_native_pair_stack_and_visual_receiving_still_required=True)
    except (ValueError, RuntimeError, AssertionError, KeyError, TypeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
