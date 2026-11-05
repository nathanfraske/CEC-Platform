"""Receive additive source-retained contours with two absolute native cuts.

No JSON 'passed' flag, unchanged coverage counter, or declared net allowlist
can requalify changed evidence. Actual saved native zone UUIDs define scope;
the exact source-plus-zone transaction and native ground refill are rebuilt.
Every other native node and sidecar remains unchanged. Unknown legs stay
strict under the existing physical comparator. No new current credit.
"""
from pathlib import Path
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
    result = dict(schema=1, scope='fresh_positive_source_retained_contour_requalification',
                  ok=False, complete=False, errors=[], new_capacity_credited=False,
                  unknown_evidence_qualified=False, release_authority=False)
    try:
        if (type(contours) is not list or not 1 <= len(contours) <= 8
                or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_exact_native_contour_inventory_required')
        import math
        if (type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
                or not 0<sense_timeout_s<=60.):
            raise ValueError('bounded_explicit_absolute_contour_sense_work_lease_required')
        paths = [Path(source).resolve(), Path(candidate).resolve()]
        epoch = force._code_identity()
        families = [force._family(path, board_hint) for path in paths]
        old_board, child = [pcbnew.LoadBoard(str(path)) for path in paths]
        root, old = additive._nodes(paths[0]); _, new = additive._nodes(paths[1])
        zone_ids = [row['materialized']['zone_uuid'] for row in contours]
        if (any(type(uid) is not str or not uid for uid in zone_ids)
                or len(set(zone_ids)) != len(zone_ids)
                or old.keys() - new.keys() or new.keys() - old.keys() != set(zone_ids)
                or any(new[uid][0] != 'zone' for uid in zone_ids)):
            raise ValueError('exact_source_plus_received_contour_zones_required')
        old_fixed = force._preservation_snapshot(paths[0])[1]
        new_fixed = force._preservation_snapshot(paths[1])[1]
        if old_fixed != new_fixed or force._sidecars(paths[0]) != force._sidecars(paths[1]):
            raise ValueError('source_metadata_or_sidecars_changed')
        zones = {force._uid(z): z for z in child.Zones()}
        nets = sorted({str(zones[uid].GetNetname()) for uid in zone_ids})
        proofs = []
        for row in contours:
            plan = row['plan']; uid = row['materialized']['zone_uuid']
            if (plan.get('retire_source_tracks') is not False
                    or plan.get('net') != zones[uid].GetNetname()):
                raise ValueError('positive_source_retaining_contour_plan_required')
            proof = owner.receive(child, plan, uid, timeout_s=10.)
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('saved_native_contour_enclosure_not_received')
            proofs.append(proof)
        # Replay only the actual independently received zones and GND fills.
        # Unrelated pose/property/net/rule/copper edits are not a contour phase.
        with tempfile.TemporaryDirectory(prefix='cec-positive-contour-receiving-') as tmp:
            expected = force._copy_family(paths[0], Path(tmp) / 'family')
            rebuilt_root = [root[0], *root[1:], *[new[uid] for uid in sorted(zone_ids)]]
            expected.write_text(additive._render(rebuilt_root) + '\n')
            rebuilt = pcbnew.LoadBoard(str(expected)); rebuilt.SetFileName(str(expected))
            additive._ground_refill(rebuilt); field._save_field_snapshot(rebuilt, expected)
            _, actual = additive._nodes(expected)
            if (actual.keys() != new.keys() or any(
                    syntax._freeze(actual[uid]) != syntax._freeze(new[uid]) for uid in new)):
                raise ValueError('exact_native_contour_and_ground_refill_replay_differs')
        before = sense.replay(paths[0], board_hint=board_hint, timeout_s=sense_timeout_s)
        after = sense.replay(paths[1], board_hint=board_hint, timeout_s=sense_timeout_s)
        scope = positive_contour_scope(before)
        if set(nets) & set(scope['frozen_nets']):
            raise ValueError('changed_unknown_or_failing_kelvin_net_refused')
        transforms = [dict(net=net, retired_track_uuids=[], added_track_uuids=[],
            retired_via_uuids=[], added_via_uuids=[],
            added_zone_uuids=sorted(uid for uid in zone_ids if zones[uid].GetNetname() == net))
            for net in nets]
        kelvin = sense.compare_contour_preservation(before, after,
            modified_nets=nets, native_copper_transforms=transforms)
        if kelvin.get('comparison_complete') is not True or kelvin.get('same_evidence') is not True:
            raise ValueError('two_absolute_cuts_and_strict_unaffected_evidence_required')
        parts = ordinary._partition(old_board, time.monotonic() + 10.)
        retained = set().union(*parts)
        updated = ordinary._partition(child, time.monotonic() + 10., retained_keys=retained)
        if not all(any(part <= new_part for new_part in updated) for part in parts):
            raise ValueError('original_native_conductor_partition_lost')
        debt = current.receive(*paths, board_hint=board_hint)
        if debt.get('ok') is not True or debt.get('complete') is not True:
            raise ValueError('unchanged_full_current_debt_not_received')
        with force._thermal_hint(board_hint):
            field_delta = sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                                 - field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if field_delta:
            raise ValueError('new_native_field_blocker')
        stable = epoch == force._code_identity() and families == [
            force._family(path, board_hint) for path in paths]
        if not stable:
            raise ValueError('native_source_candidate_or_code_changed_during_receiving')
        result.update(ok=True, complete=True, source=str(paths[0]), candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]), candidate_sha256=force._hash(paths[1]),
            code_identity=epoch, source_candidate_and_code_unchanged=stable,
            saved_native_contour_receiving=proofs,
            exact_source_plus_contours_and_ground_refill_received=True,
            actual_modified_nets=nets, native_item_transforms=transforms,
            positive_source_scope=scope, physical_kelvin_preservation=kelvin,
            current_debt_receiving=debt, new_field_blockers=[],
            all_source_native_partitions_preserved=True)
    except (KeyError, TypeError, ValueError, OSError, owner.Refused) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
