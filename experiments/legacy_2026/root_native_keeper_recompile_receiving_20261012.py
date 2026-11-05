"""Independently replay typed keeper replacement, not arbitrary zone pruning.

All original strokes, pads, vias, process settings and native partitions stay
intact. Every incumbent keeper port must still touch its received replacement.
Unknown Kelvin nets are frozen; changed positive nets require two absolute
native cuts. No branch current, thermal, barrel or release credit is granted.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as owner
from root_native_kelvin_contour_scope_20261012 import positive_contour_scope


def receive(source, candidate, contours, *, board_hint, sense_timeout_s=10.):
    result = dict(schema=1, scope='fresh_native_owned_keeper_recompile_receiving',
        ok=False, complete=False, errors=[], new_capacity_credited=False,
        coupled_thermal_qualified=False, unknown_evidence_qualified=False, release_authority=False)
    try:
        if (type(contours) is not list or not 1 <= len(contours) <= 8
                or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_exact_keeper_recompile_inventory_required')
        if (type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
                or not 0<sense_timeout_s<=60.):
            raise ValueError('bounded_explicit_absolute_keeper_sense_work_lease_required')
        paths = [Path(source).resolve(), Path(candidate).resolve()]
        epoch = force._code_identity()
        families = [force._family(path, board_hint) for path in paths]
        before, child = [pcbnew.LoadBoard(str(path)) for path in paths]
        _, old = additive._nodes(paths[0]); _, new = additive._nodes(paths[1])
        uids = [r['materialized']['zone_uuid'] for r in contours]
        if (any(type(u) is not str or not u for u in uids)
                or len(uids) != len(set(uids)) or old.keys() != new.keys()
                or any(old[u][0] != 'zone' or new[u][0] != 'zone' for u in uids)):
            raise ValueError('exact_retained_native_owner_inventory_required')
        if (force._preservation_snapshot(paths[0])[1] != force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0]) != force._sidecars(paths[1])):
            raise ValueError('keeper_source_metadata_or_sidecars_changed')
        source_zones = {force._uid(z): z for z in before.Zones()}
        zones = {force._uid(z): z for z in child.Zones()}
        nets = sorted({str(zones[u].GetNetname()) for u in uids})
        proofs, ports = [], []
        from cec_rounded_landing import _native_source
        for row, uid in zip(contours, uids):
            plan = row['plan']; replacement = plan.get('replacement_source_zone') or {}
            if (plan.get('retire_source_tracks') is not False
                    or plan.get('rebuild_keeper_from_tracks') is not True
                    or plan.get('fill_policy') != 'conductor_preserving_regions'
                    or replacement.get('configuration', {}).get('uuid') != uid
                    or replacement != _native_source(source_zones[uid], allow_complex_fill=True)):
                raise ValueError('exact_source_retaining_typed_keeper_plan_required')
            proof = owner.receive(child, plan, uid, regional_source=before, timeout_s=10.)
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('saved_typed_keeper_enclosure_not_received:' + str(proof.get('reason')))
            proofs.append(proof)
            # Keep every actual old pad/barrel port, not just the declared
            # centerline endpoints or a net-level open counter. Whole-board
            # partitions separately prove their retained mutual reachability.
            layer = plan['layer_id']; old_fill = source_zones[uid].GetFilledPolysList(layer)
            new_fill = zones[uid].GetFilledPolysList(layer)
            items = [*(p for fp in before.GetFootprints() for p in fp.Pads()),
                     *(t for t in before.GetTracks() if t.GetClass() == 'PCB_VIA')]
            if len(items) > 16384: raise ValueError('keeper_native_port_inventory_bound')
            old_ports = []
            deadline = time.monotonic() + 10.
            for item in items:
                if time.monotonic() >= deadline: raise ValueError('keeper_native_port_deadline')
                if not item.IsOnLayer(layer) or item.GetNetname() != plan['net']: continue
                shape = item.GetEffectiveShape(layer)
                if not old_fill.Collide(shape, 0): continue
                if not new_fill.Collide(shape, 0):
                    raise ValueError('incumbent_keeper_native_port_lost:' + force._uid(item))
                old_ports.append(force._uid(item))
            ports.append(dict(zone_uuid=uid, native_port_uuids=sorted(old_ports)))
        # Reconstruct the phase independently from immutable original copper.
        # A saved child or worker JSON is not the expected-transaction oracle.
        with tempfile.TemporaryDirectory(prefix='cec-keeper-recompile-receiving-') as tmp:
            expected = force._copy_family(paths[0], Path(tmp) / 'family')
            rebuilt = pcbnew.LoadBoard(str(expected)); rebuilt.SetFileName(str(expected))
            for row in contours:
                plan = row['plan']; uid = row['materialized']['zone_uuid']
                tracks = [v['uuid'] for v in plan['source_tracks']]
                emitted = owner.materialize(rebuilt, plan,
                    allow_locked_track_uuids=tracks, allow_grouped_track_uuids=tracks,
                    allow_locked_zone_uuids=[uid], allow_grouped_zone_uuids=[uid])
                if emitted['zone_uuid'] != uid: raise ValueError('keeper_native_owner_identity_changed')
                owner.fill(rebuilt, plan, uid, regional_source=before, timeout_s=10.)
                additive._ground_refill(rebuilt)
            field._save_field_snapshot(rebuilt, expected)
            _, actual = additive._nodes(expected)
            if (actual.keys() != new.keys() or any(syntax._freeze(actual[u]) != syntax._freeze(new[u])
                                                  for u in new)):
                raise ValueError('exact_typed_keeper_and_ground_refill_replay_differs')
        first = sense.replay(paths[0], board_hint=board_hint, timeout_s=sense_timeout_s)
        last = sense.replay(paths[1], board_hint=board_hint, timeout_s=sense_timeout_s)
        scope = positive_contour_scope(first)
        if set(nets) & set(scope['frozen_nets']):
            raise ValueError('changed_unknown_or_failing_kelvin_keeper_refused')
        kelvin = sense.compare_contour_preservation(first, last, modified_nets=nets)
        if kelvin.get('comparison_complete') is not True or kelvin.get('same_evidence') is not True:
            raise ValueError('absolute_keeper_cuts_and_strict_unaffected_evidence_required')
        parts = ordinary._partition(before, time.monotonic() + 10.)
        updated = ordinary._partition(child, time.monotonic() + 10., retained_keys=set().union(*parts))
        if not all(any(part <= other for other in updated) for part in parts):
            raise ValueError('incumbent_native_keeper_partition_lost')
        debt = current.receive(*paths, board_hint=board_hint)
        if debt.get('ok') is not True or debt.get('complete') is not True:
            raise ValueError('unchanged_keeper_full_current_debt_not_received')
        with force._thermal_hint(board_hint):
            delta = sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                           - field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if delta: raise ValueError('new_native_keeper_field_blocker')
        stable = epoch == force._code_identity() and families == [
            force._family(path, board_hint) for path in paths]
        if not stable: raise ValueError('keeper_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source=str(paths[0]), candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]), candidate_sha256=force._hash(paths[1]),
            code_identity=epoch, source_candidate_and_code_unchanged=True,
            actual_modified_zone_uuids=sorted(uids), actual_modified_nets=nets,
            saved_native_keeper_receiving=proofs, retained_native_keeper_ports=ports,
            exact_native_owner_recompile_and_ground_refill_received=True,
            all_source_native_conductor_partitions_preserved=True,
            physical_kelvin_preservation=kelvin, positive_source_scope=scope,
            current_debt_receiving=debt, new_field_blockers=[])
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, owner.Refused) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
