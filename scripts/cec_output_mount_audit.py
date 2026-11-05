#!/usr/bin/env python3
"""Audit CURRENT XFCN daughterboard holes, port pinouts and missing key evidence.

This is a screening gate, not a substitute for a measured 3D mated assembly.
The main-side screw-axis Z/datum is not dimensioned completely in the source
drawings. No footprint origin is silently treated as a measured screw axis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cec_mount_patterns as patterns


def inspect_board(path, refs, *, daughterboard=False, row_frames=()):
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    path = Path(path)
    board = pcbnew.LoadBoard(str(path))
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    contacts = {}
    import cec_placement_geometry
    for ref in refs:
        if ref not in footprints:
            raise ValueError(f'{path}: missing interface reference {ref}')
        fp = footprints[ref]
        pads = list(fp.Pads())
        nets = sorted({pad.GetNetname() for pad in pads})
        if len(nets) != 1 or not nets[0]:
            raise ValueError(f'{path}: {ref} is not a single electrical node')
        row = {'ref': ref, 'net': nets[0],
               'footprint': str(fp.GetFPID().GetLibItemName()),
               'origin_mm': [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6],
               'rotation_deg': fp.GetOrientationDegrees()}
        if daughterboard:
            if len(pads) != 1 or pads[0].GetDrillSize().x <= 0:
                raise ValueError(f'{path}: {ref} lacks one physical bolt hole')
            pad = pads[0]
            row.update(hole_mm=[pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6],
                       hole_diameter_mm=pad.GetDrillSize().x / 1e6)
        contacts[ref] = row
    # The declaration supplies row frames; no reference-name or board lookup
    # is used to infer a footprint's installed lateral axis.
    for row_refs, seed_angle in row_frames:
        axis = contacts[row_refs[0]]['rotation_deg'] - seed_angle
        for ref in row_refs:
            contacts[ref]['copper_interval_mm'] = cec_placement_geometry.footprint_copper_interval(
                footprints[ref], axis_angle_deg=axis)
    return {'path': str(path.resolve()),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'contacts': contacts}


def audit(*, overrides=None, joint_error_mm=0.6):
    import cec_xfcn_contract as contract
    overrides = overrides or {}
    if set(overrides) - set(contract.PROJECTS):
        raise ValueError('unknown project override')
    boards, findings, ports, comparisons = {}, [], [], []
    for name, spec in contract.PROJECTS.items():
        boards[name] = inspect_board(
            overrides.get(name, contract.project_path(name, 'pcb')),
            spec['refs'], daughterboard=spec['kind'] == 'daughterboard',
            row_frames=[(refs, spec['interface_frame_seed_mm'][refs[0]][2])
                        for _mate, refs, _db_refs in contract.OUTPUT_MOUNT_PORTS.get(name, ())])
        for ref, expectation in spec['refs'].items():
            actual = boards[name]['contacts'][ref]['net']
            expected = expectation['net']
            if actual != expected and not (expected.startswith('/') and actual.endswith(expected)):
                findings.append({'code': 'interface_net_drift', 'project': name,
                                 'ref': ref, 'actual': actual, 'expected': expected})
        if spec['kind'] == 'main':
            import cec_placement_geometry
            geometry = cec_placement_geometry.evaluate(boards[name]['path'])
            interface_findings = [row for row in geometry['findings']
                if row['domain'] == 'pad_copper' and any(
                    item.get('ref') in spec['refs'] for item in row.get('items', []))]
            boards[name]['pad_copper_screen'] = {'ok': not interface_findings,
                'findings': interface_findings, 'source_sha256': geometry['sha256']}
            if interface_findings:
                findings.append({'code': 'interface_pad_copper_violation', 'project': name,
                                 'native_report_rows': len(interface_findings)})
    declared_mains = {n for n, spec in contract.PROJECTS.items() if spec['kind'] == 'main'}
    if declared_mains != set(contract.OUTPUT_MOUNT_PORTS):
        raise ValueError('output mating map does not cover every declared main board')
    for name, declarations in contract.OUTPUT_MOUNT_PORTS.items():
        declared_refs = [r for _, refs, _ in declarations for r in refs]
        if len(set(declared_refs)) != len(declared_refs) or set(declared_refs) != set(contract.PROJECTS[name]['refs']):
            raise ValueError('output mating map has missing or duplicate contacts')
        for index, (mate, main_refs, db_refs) in enumerate(declarations, 1):
            rows = boards[name]['contacts']
            db = boards[mate]['contacts']
            seed = contract.PROJECTS[name]['interface_frame_seed_mm']
            angle = rows[main_refs[0]]['rotation_deg'] - seed[main_refs[0]][2]
            a = math.radians(angle)
            axis = (math.cos(a), -math.sin(a))
            projected = {r: sum(v*d for v, d in zip(rows[r]['origin_mm'], axis)) for r in main_refs}
            ordered = sorted(main_refs, key=projected.get)
            port = {'project': name, 'port': index, 'mate': mate,
                    'specified_order': list(main_refs), 'actual_order': ordered,
                    'pinout': [{'position': n, 'main_ref': a, 'main_net': rows[a]['net'],
                                'db_ref': b, 'db_net': db[b]['net']}
                               for n, (a, b) in enumerate(zip(main_refs, db_refs), 1)]}
            if ordered != list(main_refs):
                findings.append({'code': 'port_order_disagrees_with_common_pinout',
                                 'project': name, 'port': index})
            # A common part at a common rotation has a common screw-axis
            # offset. It cancels in pair spacings even though absolute Z is
            # unqualified. Mixed parts/rotations cannot use that inference.
            common_parts = {}
            db_map = dict(zip(main_refs, db_refs))
            for ref in ordered:
                common_parts.setdefault((rows[ref]['footprint'], rows[ref]['rotation_deg']), []).append(ref)
            port['uniform_part_pitch_checks'] = []
            for group in common_parts.values():
                if len(group) < 2:
                    continue
                x_main = [projected[r] for r in group]
                x_db = sorted(db[db_map[r]]['hole_mm'][0] for r in group)
                error = round(patterns.pitch_residual(x_main, x_db), 6)
                port['uniform_part_pitch_checks'].append({'main_refs': group,
                    'db_refs': [db_map[r] for r in group], 'error_mm': error})
                if error > 1e-4:
                    findings.append({'code': 'nominal_mating_pitch_mismatch',
                                     'project': name, 'port': index,
                                     'main_refs': group, 'error_mm': error})
            if len(common_parts) > 1:
                port['pitch_status'] = 'unknown_mixed_part_screw_axis_datums'
            port['body_gap_screen'] = []
            policy = contract.OUTPUT_MOUNT_GAP_POLICY
            for left, right in zip(ordered, ordered[1:]):
                bodies = [contract.OUTPUT_MOUNT_BODY_SCREEN[
                    contract.PROJECTS[name]['refs'][r]['part']] for r in (left, right)]
                size = sum(b['width_mm'] for b in bodies) / 2
                nominal_gap = projected[right] - projected[left] - size
                worst_gap = nominal_gap - sum(b['width_tolerance_mm'] for b in bodies)/2 - 2*policy['position_error_mm']
                passed = worst_gap >= policy['minimum_gap_mm'] - 1e-6
                gap = {'refs': [left, right], 'nominal_gap_mm': round(nominal_gap, 6),
                       'screened_worst_gap_mm': round(worst_gap, 6),
                       'minimum_gap_mm': policy['minimum_gap_mm'],
                       'position_allowance_qualified': False, 'ok': passed}
                port['body_gap_screen'].append(gap)
                if not passed:
                    findings.append({'code': 'mating_body_gap_below_screen_margin',
                                     'project': name, 'port': index, **gap})
            ports.append(port)
            import cec_mating_rows
            # Zero-clearance projection screen does not invent a process
            # allowance. It is conservative, not proof of physical fit or
            # infeasibility for staggered pads/mixed-part screw-axis offsets.
            port['copper_envelope_screen'] = cec_mating_rows.envelope_row_screen(
                [contract.PROJECTS[mate]['placements_mm'][r][0] for r in db_refs],
                [rows[r]['copper_interval_mm'] for r in main_refs],
                maximum_last_mm=contract.OUTPUT_MOUNT_LAST_DATUM_LIMIT_MM[mate])
            if not port['copper_envelope_screen']['fits_fixed_envelope']:
                findings.append({'code': 'interface_copper_envelope_fit_unproven',
                    'project': name, 'port': index,
                    'excess_mm': port['copper_envelope_screen']['excess_mm'],
                    'note': 'conservative projection screen; native pad DRC is authoritative'})

    daughters = [name for name, spec in contract.PROJECTS.items()
                 if spec['kind'] == 'daughterboard']
    for receiver in daughters:
        receiving = list(boards[receiver]['contacts'].values())
        for insert in daughters:
            if insert == receiver:
                continue
            inserting = list(boards[insert]['contacts'].values())
            result = patterns.possible_fit(
                [r['hole_mm'] for r in receiving], [r['hole_mm'] for r in inserting],
                joint_error_mm=joint_error_mm)
            comparisons.append({'receiver_pattern': receiver, 'insert': insert, **result,
                'mapped_refs': ([] if result['mapping'] is None else
                    [[inserting[i]['ref'], receiving[j]['ref']]
                     for i, j in enumerate(result['mapping'])])})
            if result['status'] != 'excluded':
                findings.append({'code': 'cross_family_fit_not_excluded',
                                 'receiver_pattern': receiver, 'insert': insert})
    findings.extend([
        {'code': 'measured_main_screw_axis_and_tolerance_stack_missing'},
        {'code': 'positive_anti_mismatch_key_not_implemented',
         'note': 'Identical M3 screws do not prevent wrong-family single-bolt attachment.'},
    ])
    nominal_codes = {'nominal_mating_pitch_mismatch', 'interface_net_drift',
                     'port_order_disagrees_with_common_pinout', 'mating_body_gap_below_screen_margin'}
    return {'schema': 2, 'ok': True, 'admission_gate': False,
            'actual_interface_pad_copper_ok': not any(
                row['code'] == 'interface_pad_copper_violation' for row in findings),
            'nominal_spacing_and_body_screen_ok': not any(f['code'] in nominal_codes for f in findings),
            'purpose': 'mechanical_interface_screen_not_fit_qualification',
            'screening_joint_error_mm': joint_error_mm,
            'tolerances_qualified': False, 'boards': boards,
            'ports': ports, 'cross_family_screen': comparisons,
            'findings': findings,
            'dimensions_changed': False, 'physical_key_complete': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--input', action='append', default=[], metavar='PROJECT=PCB')
    args = parser.parse_args(argv)
    overrides = dict(item.split('=', 1) for item in args.input)
    result = audit(overrides=overrides)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'out': str(path), 'admission_gate': result['admission_gate'],
                      'findings': result['findings']}, indent=2))
    return 2 if not result['admission_gate'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
