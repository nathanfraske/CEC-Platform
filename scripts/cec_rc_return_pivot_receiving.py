"""Receive an isolated RC-support ground pivot, not bypass/power relocation.

Infer the capacitor and ordinary anchor from the unchanged source. Its signal
land stays physically exact, its previously isolated GND land gains a short
factory-qualified return, and every old conductor component survives. This
separate contract cannot widen ordinary routing or selected-device bypass
motion into power, differential or Kelvin construction.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cell
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_placement_geometry as geometry
import cec_route_placement_admission as placement
import cec_stage_admission as stage
import cec_support_pivot_receiving as support


def receive(source, candidate, *, board_hint, timeout_s=10., return_reach_mm=1.5):
    started = time.monotonic()
    report = dict(schema=1, scope='isolated_rc_ground_pivot_receiving',
        ok=False, complete=False, errors=[], release_authority=False,
        power_authority=False, routing_admitted=False,
        placement_authority_transferred=False)
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10
                or type(return_reach_mm) not in (int, float)
                or not math.isfinite(return_reach_mm) or not 0 < return_reach_mm <= 1.5):
            raise ValueError('invalid_rc_return_pivot_bounds')
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        if placement._population(parent) != placement._population(child):
            raise ValueError('rc_return_pivot_component_definition_changed')
        _, old = additive._nodes(source)
        _, new = additive._nodes(candidate)
        if not old.keys() <= new.keys():
            raise ValueError('rc_return_pivot_cannot_retire_source_material')
        fps = {force._uid(fp): fp for fp in parent.GetFootprints()}
        targets = {force._uid(fp): fp for fp in child.GetFootprints()}
        changed = [uid for uid in fps if sexpr._freeze(old[uid]) != sexpr._freeze(new[uid])]
        if not 1 <= len(changed) <= 4:
            raise ValueError('bounded_nonempty_rc_return_pivots_required')
        eligible = ordinary.eligible_nets(parent, source, board_hint)
        with force._thermal_hint(board_hint):
            assignment = constraints._device_bypass_assignment(parent, project_max_mm=3.5)
        selected = {r['cap_ref'] for r in assignment['assigned'].values()}
        grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        old_parts = ordinary._partition(parent, time.monotonic()+timeout_s)
        retained = set().union(*old_parts)
        keys = {force._uid(p): force._item_key(p) for fp in parent.GetFootprints() for p in fp.Pads()}
        conn = pcbnew.CONNECTIVITY_DATA()
        for item in [*(p for fp in parent.GetFootprints() for p in fp.Pads()),
                     *parent.GetTracks(), *[z for z in parent.Zones() if not z.GetIsRuleArea()]]:
            if not conn.Add(item):
                raise ValueError('rc_return_source_contact_unknown')
        proofs = []
        for uid in changed:
            fp, target = fps[uid], targets[uid]
            pads = list(fp.Pads())
            if (fp.IsLocked() or uid in grouped or fp.GetReference() in selected
                    or not constraints._capacitance_f_board(fp.GetValue())
                    or len(pads) != 2 or fp.IsFlipped() != target.IsFlipped()
                    or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)
                    or len({str(p.GetNumber()) for p in pads}) != 2):
                raise ValueError('not_an_unlocked_nonbypass_two_land_capacitor')
            ground = [p for p in pads if p.GetNetname() == 'GND']
            anchor = [p for p in pads if str(p.GetNetname()) in eligible]
            if len(ground) != 1 or len(anchor) != 1:
                raise ValueError('rc_return_ordinary_anchor_and_ground_roles_required')
            ground, anchor = ground[0], anchor[0]
            final_ground = target.FindPadByNumber(str(ground.GetNumber()))
            fixed = support._fixed_land(anchor)
            if fixed is None or fixed != support._fixed_land(target.FindPadByNumber(str(anchor.GetNumber()))):
                raise ValueError('rc_return_signal_land_not_physically_exact')
            if any(force._uid(i) != force._uid(ground) for i in conn.GetConnectedItems(ground)):
                raise ValueError('rc_return_moving_ground_is_not_source_isolated')
            delta = (target.GetOrientationDegrees()-fp.GetOrientationDegrees()) % 360
            if (not any(abs(delta-v) < 1e-6 for v in (90, 180, 270))
                    or math.dist(list(fp.GetPosition()), list(target.GetPosition())) > 6e6):
                raise ValueError('rc_return_outside_quarter_turn_motion_bound')
            with force._thermal_hint(board_hint):
                entry = cell._existing_return(child, final_ground, return_reach_mm)
                if entry is None:
                    raise ValueError('rc_return_has_no_immediate_saved_ground_entry')
                qualified, reason = fab.local_pofv_via_decision(child, entry[1])
                if qualified is not True:
                    raise ValueError('rc_return_barrel_not_process_qualified:'+str(reason))
            proofs.append(dict(uuid=uid, ref=fp.GetReference(), anchor_pin=str(anchor.GetNumber()),
                ground_pin=str(ground.GetNumber()), rotation_delta_deg=delta,
                ground_path_mm=entry[0], ground_via_uuid=force._uid(entry[1])))
        incoming = new.keys()-old.keys()
        if not 1 <= len(incoming) <= 64:
            raise ValueError('bounded_rc_ground_additions_required')
        ground_positions = [targets[p['uuid']].FindPadByNumber(p['ground_pin']).GetPosition() for p in proofs]
        for item in child.GetTracks():
            if force._uid(item) not in incoming:
                continue
            points = ([item.GetPosition()] if item.GetClass() == 'PCB_VIA'
                else [item.GetStart(), item.GetEnd()])
            if (item.GetNetname() != 'GND' or item.GetClass() not in ('PCB_VIA', 'PCB_TRACK')
                    or not any(all(math.dist(list(p), list(g)) <= return_reach_mm*1e6+1
                        for p in points) for g in ground_positions)):
                raise ValueError('rc_return_incoming_copper_is_not_bounded_local_ground')
        rebind = {force._item_key(p): keys[force._uid(p)] for uid in changed for p in targets[uid].Pads()}
        new_parts = ordinary._partition(child, time.monotonic()+timeout_s,
            retained_keys=retained, _identity_rebindings=rebind)
        if any(not any(p <= q for q in new_parts) for p in old_parts):
            raise ValueError('rc_return_lost_original_native_component')
        with tempfile.TemporaryDirectory(prefix='cec-rc-return-pivot-') as work:
            work = Path(work)
            projected = force._copy_family(source, work/'projected')
            base = pcbnew.LoadBoard(str(projected))
            by_uid = {force._uid(fp): fp for fp in base.GetFootprints()}
            for p in proofs:
                fp = by_uid[p['uuid']]
                fp.Rotate(fp.FindPadByNumber(p['anchor_pin']).GetPosition(),
                    pcbnew.EDA_ANGLE(p['rotation_delta_deg'], pcbnew.DEGREES_T))
            field._save_field_snapshot(base, projected)
            _, replayed = additive._nodes(projected)
            if any(sexpr._freeze(replayed[u]) != sexpr._freeze(new[u]) for u in changed):
                raise ValueError('rc_return_is_not_exact_source_native_transform')
            receipt = additive.receive(projected, candidate, timeout_s=timeout_s)
            report['independent_pose_and_additive_replay'] = receipt
            if receipt.get('ok') is not True or receipt.get('complete') is not True:
                raise ValueError('rc_return_exact_additive_replay_refused')
            def grade(path, name):
                isolated = force._copy_family(path, work/name)
                out = work/(name+'.json')
                result = subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json',
                    '--severity-all', '--output', str(out), str(isolated)],
                    capture_output=True, text=True, timeout=timeout_s)
                if result.returncode:
                    raise ValueError('rc_return_native_drc_failed')
                return json.loads(out.read_text())
            before, after = grade(source, 'before'), grade(candidate, 'after')
        known = {stage._canonical_identity(v) for v in before['violations']}
        unseen = [v for v in after['violations'] if stage._canonical_identity(v) not in known]
        inherited = []
        actual = []
        for v in unseen:
            proof = support._inherited_silk_overlap(parent, child, v, old, new)
            (inherited if proof else actual).append(proof or v)
        report.update(pivots=proofs, source_opens=len(before['unconnected_items']),
            opens=len(after['unconnected_items']), all_raw_drc=len(after['violations']),
            new_native_faults=actual, positively_proved_inherited_silk_collisions=inherited,
            original_native_conductor_and_terminal_partitions_preserved=True)
        if actual or report['opens'] >= report['source_opens']:
            raise ValueError('rc_return_has_no_nonregressing_native_closure')
        report['physical_placement'] = geometry.evaluate(candidate, timeout_s=timeout_s)
        if report['physical_placement'].get('ok') is not True:
            raise ValueError('rc_return_physical_placement_refused')
        with force._thermal_hint(board_hint):
            first = field.field_coupling_summary(str(source), board=parent)
            last = field.field_coupling_summary(str(candidate), board=child)
        report['new_native_field_blockers'] = sorted(field.blocker_keys(last)-field.blocker_keys(first))
        if report['new_native_field_blockers']:
            raise ValueError('rc_return_introduces_field_coupling_blocker')
        stable = families == [force._family(p, board_hint) for p in (source, candidate)] and epoch == force._code_identity()
        report['source_candidate_and_code_unchanged'] = stable
        if not stable:
            raise ValueError('rc_return_source_candidate_or_epoch_changed')
        report.update(ok=True, complete=True, reason='received_isolated_rc_return_pivot',
            board=str(candidate), board_sha256=force._hash(candidate), source_sha256=force._hash(source))
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    report['elapsed_s'] = round(time.monotonic()-started, 6)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--hint', required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    force._check_output(a.report, force._protected_paths(a.source, a.hint)
        | force._protected_paths(a.candidate, a.hint))
    result = receive(a.source, a.candidate, board_hint=a.hint)
    force._write(a.report, result)
    print(json.dumps({k: result.get(k) for k in ('ok', 'source_opens', 'opens', 'errors')}), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
