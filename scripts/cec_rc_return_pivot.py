"""Finite source-derived RC-support return pivots with independent receiving."""
from pathlib import Path
import argparse
import json
import math

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_decoupler_cell as cell
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_pi_cleanup as cleanup
import cec_power_connectivity as power
import cec_rc_return_pivot_receiving as receiving


def source_menu(board, source, board_hint, *, max_trials=12):
    if type(max_trials) is not int or not 1 <= max_trials <= 12:
        raise ValueError('bounded_rc_return_menu_required')
    native = power.inventory(board)
    isolated = {p['uuid'] for n in native['nets'] if n['net'] == 'GND'
        for c in n['components'] if c['no_other_native_contacts'] for p in c['terminals']}
    eligible = ordinary.eligible_nets(board, source, board_hint)
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    selected = {r['cap_ref'] for r in assigned['assigned'].values()}
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    rows = []
    for fp in sorted(board.GetFootprints(), key=force._uid):
        pads = list(fp.Pads())
        if (fp.IsLocked() or force._uid(fp) in grouped or fp.GetReference() in selected
                or not constraints._capacitance_f_board(fp.GetValue()) or len(pads) != 2
                or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in pads)):
            continue
        ground = [p for p in pads if p.GetNetname() == 'GND' and force._uid(p) in isolated]
        anchor = [p for p in pads if str(p.GetNetname()) in eligible]
        if len(ground) != 1 or len(anchor) != 1:
            continue
        for delta in (180., 90., 270.):
            rows.append(dict(footprint_uuid=force._uid(fp), ref=fp.GetReference(),
                anchor_pin=str(anchor[0].GetNumber()), ground_pin=str(ground[0].GetNumber()),
                rotation_delta_deg=delta))
    # Interleave distinct components before exhausting all angles of one.
    components = sorted({r['footprint_uuid'] for r in rows})
    return sorted(rows, key=lambda r: ((180., 90., 270.).index(r['rotation_delta_deg']),
        components.index(r['footprint_uuid'])))[:max_trials]


def run(source, directory, *, source_sha256, board_hint, max_trials=12,
        return_reach_mm=1.5, timeout_s=10.):
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if (type(return_reach_mm) not in (int, float) or not math.isfinite(return_reach_mm)
            or not 0 < return_reach_mm <= 1.5
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(board_hint) is not str or not board_hint):
        raise ValueError('invalid_rc_return_run_bounds')
    force._check_proposal_directory(directory, force._protected_paths(source, board_hint))
    if force._hash(source) != source_sha256:
        raise ValueError('rc_return_source_hash_mismatch')
    family = force._family(source, board_hint)
    epoch = force._code_identity()
    parent = pcbnew.LoadBoard(str(source))
    menu = source_menu(parent, source, board_hint, max_trials=max_trials)
    directory.mkdir(parents=True)
    report = dict(schema=1, ok=False, scope='bounded_source_rc_return_pivots',
        source=str(source), source_sha256=source_sha256, menu=menu, trials=[],
        board=None, release_authority=False, power_authority=False, routing_admitted=False)
    for index, choice in enumerate(menu):
        board = pcbnew.LoadBoard(str(source))
        fp = next(fp for fp in board.GetFootprints() if force._uid(fp) == choice['footprint_uuid'])
        fp.Rotate(fp.FindPadByNumber(choice['anchor_pin']).GetPosition(),
            pcbnew.EDA_ANGLE(choice['rotation_delta_deg'], pcbnew.DEGREES_T))
        row = dict(choice, ok=False)
        report['trials'].append(row)
        try:
            cleanup._pose_preflight(board, fp)
            old = {force._uid(t) for t in board.GetTracks()}
            with force._thermal_hint(board_hint):
                evidence, error = cell._add_ground_return(board,
                    fp.FindPadByNumber(choice['ground_pin']), board_path=str(source),
                    reach_mm=return_reach_mm, lock=True)
            if error or not evidence:
                raise ValueError(error or 'rc_return_no_constructed_entry')
            added = [t for t in board.GetTracks() if force._uid(t) not in old]
            row['process_ownership'] = fr.group_local_pofv_signal_vias(board, added)
            target = force._copy_family(source, directory/('trial-'+str(index)))
            board.SetFileName(str(target))
            additive._ground_refill(board)
            field._save_field_snapshot(board, target)
            additive.bind_local_via_rule(board, target)
            receipt = receiving.receive(source, target, board_hint=board_hint,
                timeout_s=timeout_s, return_reach_mm=return_reach_mm)
            row.update(board=str(target), receiving=receipt, ok=receipt['ok'])
            if receipt['ok'] is True:
                report.update(ok=True, board=str(target), board_sha256=force._hash(target),
                    source_opens=receipt['source_opens'], opens=receipt['opens'])
                break
        except Exception as exc:
            row['error'] = type(exc).__name__+':'+str(exc)
    report['source_family_and_code_unchanged'] = family == force._family(source, board_hint) and epoch == force._code_identity()
    if report['source_family_and_code_unchanged'] is not True:
        report['ok'] = False
        report['error'] = 'rc_return_source_or_code_epoch_changed'
    force._write(directory/'receiving.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--hint', required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--max-trials', type=int, default=12)
    a = p.parse_args()
    result = run(a.source, a.directory, source_sha256=a.sha256,
        board_hint=a.hint, max_trials=a.max_trials)
    print(json.dumps({k: result.get(k) for k in ('ok', 'source_opens', 'opens', 'board', 'error')}), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
