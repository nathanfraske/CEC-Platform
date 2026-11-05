"""Independent saved-family replay for source-retaining signed contour phases.

Worker plans, a net-level counter and a named native zone are not authority.
Reconstruct only the declared phase from the immutable parent, compare the
whole saved native transaction, then require strict Kelvin/current/field
preservation. Full uncapped DRC and release qualification remain external.
"""
from pathlib import Path
import math
import tempfile
import time


def receive_literal_phase(source, candidate, records, *, board_hint=None):
    """Exact native replay only, deliberately NOT electrical qualification."""
    import pcbnew
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax
    import cec_field_coupling as field
    import cec_force_current as force
    import cec_native_contour_regions as regions
    result = dict(schema=1, scope='source_retained_signed_native_contour_phase_replay',
        ok=False, complete=False, errors=[], new_capacity_credited=False, release_authority=False,
        full_board_receiving_required=True)
    try:
        if (type(records) is not list or not 1 <= len(records) <= 8
                or any(type(r) is not dict or set(r) != {'plan','materialized'} for r in records)):
            raise ValueError('bounded_exact_signed_contour_records_required')
        paths = [Path(source).resolve(), Path(candidate).resolve()]
        epoch = force._code_identity()
        families = [force._family(path, board_hint) for path in paths]
        before, child = [pcbnew.LoadBoard(str(path)) for path in paths]
        _, old = additive._nodes(paths[0]); _, new = additive._nodes(paths[1])
        ids = [u for row in records for u in row['materialized']['zone_uuids']]
        if (not 1 <= len(ids) <= 64 or any(type(u) is not str or not u for u in ids)
                or len(set(ids)) != len(ids) or set(ids) & old.keys()
                or new.keys() != old.keys() | set(ids)
                or any(new[u][0] != 'zone' for u in ids)):
            raise ValueError('exact_added_native_region_zone_inventory_required')
        if (force._preservation_snapshot(paths[0])[1] != force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0]) != force._sidecars(paths[1])):
            raise ValueError('signed_contour_source_metadata_or_sidecars_changed')
        proofs = []
        for row in records:
            proof = regions.receive(child, row['plan'], row['materialized']['zone_uuids'])
            if not proof['ok'] or not proof['complete']:
                raise ValueError('saved_signed_native_regions_not_received:'+str(proof['reason']))
            proofs.append(proof)
        # The immutable SOURCE is the expected-transaction oracle. Never
        # regenerate expectations from arbitrary changed polygons in the child.
        with tempfile.TemporaryDirectory(prefix='cec-signed-contour-replay-') as tmp:
            expected = force._copy_family(paths[0], Path(tmp)/'family')
            rebuilt = pcbnew.LoadBoard(str(expected)); rebuilt.SetFileName(str(expected))
            for row in records:
                plan = row['plan']; track_ids = [r['uuid'] for r in plan['source_tracks']]
                emitted = regions.materialize(rebuilt, plan, allow_locked_track_uuids=track_ids,
                    allow_grouped_track_uuids=track_ids, zone_uuids=row['materialized']['zone_uuids'])
                if emitted != row['materialized']:
                    raise ValueError('signed_native_materialized_record_changed')
                regions.fill(rebuilt, plan, emitted['zone_uuids'])
                additive._ground_refill(rebuilt)
                field._save_field_snapshot(rebuilt, expected)
                rebuilt = pcbnew.LoadBoard(str(expected))
            _, actual = additive._nodes(expected)
            # Only the declared zones, recompiled Ground fills and their
            # explicit existing group may come from native reconstruction.
            # KiCad may reorder an unrelated property's hide/effects fields
            # when saving. The constructor correctly retains that original
            # literal node; do not demand unrelated serializer churn instead.
            owned = set(ids) | {force._uid(z) for z in before.Zones()
                if not z.GetIsRuleArea() and z.GetNetname() == 'GND'}
            owned.update(row['plan']['group_uuid'] for row in records
                if row['plan'].get('group_uuid'))
            if (actual.keys() != new.keys() or any(
                    syntax._freeze(actual[u] if u in owned else old[u]) != syntax._freeze(new[u])
                    for u in new)):
                raise ValueError('exact_signed_regions_and_ground_refill_replay_differs')
        stable = epoch == force._code_identity() and families == [
            force._family(path, board_hint) for path in paths]
        if not stable: raise ValueError('signed_contour_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source=str(paths[0]), candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]), candidate_sha256=force._hash(paths[1]),
            code_identity=epoch, source_candidate_and_code_unchanged=True,
            declared_added_zone_uuids=ids, actual_modified_nets=sorted({r['plan']['net'] for r in records}),
            saved_signed_region_receiving=proofs, exact_source_phase_and_ground_refill_received=True)
    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source, candidate, records, *, board_hint, sense_timeout_s=10.):
    """Source-typed geometry, graph and evidence preservation; no waivers."""
    import pcbnew
    import cec_current_debt as current
    import cec_field_coupling as field
    import cec_force_current as force
    import cec_force_sense_evidence as sense
    import cec_ordinary_route_receiving as ordinary
    result = dict(schema=1, scope='source_retained_signed_native_contour_preservation',
        ok=False, complete=False, errors=[], new_capacity_credited=False,
        current_qualified=False, coupled_thermal_qualified=False, release_authority=False,
        full_uncapped_DRC_and_release_receiving_required=True)
    try:
        if type(board_hint) is not str or not board_hint:
            raise ValueError('explicit_source_board_design_basis_required')
        if (type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
                or not 0<sense_timeout_s<=60.):
            raise ValueError('explicit_bounded_native_contour_sense_lease_required')
        result['sense_timeout_s']=float(sense_timeout_s)
        paths = [Path(source).resolve(), Path(candidate).resolve()]
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in paths]
        literal = receive_literal_phase(*paths, records, board_hint=board_hint)
        result['independent_saved_phase'] = literal
        if not literal['ok'] or not literal['complete']:
            raise ValueError('signed_native_literal_phase_refused:'+str(literal['errors']))
        before, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        parts = ordinary._partition(before, time.monotonic()+10.)
        updated = ordinary._partition(child, time.monotonic()+10., retained_keys=set().union(*parts))
        if not all(any(part <= other for other in updated) for part in parts):
            raise ValueError('signed_contour_source_native_partition_lost')
        first = sense.replay(paths[0], board_hint=board_hint, timeout_s=sense_timeout_s)
        last = sense.replay(paths[1], board_hint=board_hint, timeout_s=sense_timeout_s)
        transforms = [dict(net=net, retired_track_uuids=[], added_zone_uuids=[
            u for row in records if row['plan']['net'] == net for u in row['materialized']['zone_uuids']])
            for net in literal['actual_modified_nets']]
        kelvin = sense.compare_contour_preservation(first, last, modified_nets=literal['actual_modified_nets'],
            native_copper_transforms=transforms)
        result['physical_kelvin_preservation'] = kelvin
        if not kelvin.get('comparison_complete') or not kelvin.get('same_evidence'):
            raise ValueError('absolute_signed_contour_cuts_and_unaffected_evidence_required')
        debt = current.receive(*paths, board_hint=board_hint)
        result['current_debt_receiving'] = debt
        if not debt.get('ok') or not debt.get('complete'):
            raise ValueError('full_saved_signed_contour_current_debt_not_received')
        with force._thermal_hint(board_hint):
            delta = sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                           - field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        result['new_field_blockers'] = delta
        if delta: raise ValueError('new_signed_contour_field_blocker')
        if epoch != force._code_identity() or families != [force._family(p, board_hint) for p in paths]:
            raise ValueError('signed_contour_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]), code_identity=epoch,
            source_candidate_and_code_unchanged=True, all_source_native_conductor_partitions_preserved=True,
            physical_kelvin_preservation=kelvin, current_debt_receiving=debt, new_field_blockers=[])
    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
