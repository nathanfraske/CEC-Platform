"""Shared electrical craft gates inside a route-time component transaction.

Use the final pipeline's native authorities and unchanged policy. Geometry
preflight ignores deliberately disconnected copper; final evaluation does not.
This is a rejection gate, never release authority or a dimensional waiver.
"""
import json
import math
from collections import Counter
from types import SimpleNamespace


def _key(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _decoupler_cell_faults(rows):
    """Keep each measured physical cause, not a concatenated display string.

    Every original gate and new/worsened cause remains rejecting. Legacy
    rows retain their exact old identity; malformed partial atomic evidence
    is an error, never permission to discard an unrepresented failure.
    """
    codes={'local_supply_missing','local_supply_length_excess',
        'capacitor_ground_return_missing','owner_ground_return_missing',
        'owner_cap_ground_gap_excess','local_return_missing','local_return_length_excess'}
    result={}
    for row in rows:
        identity=[row.get(key)for key in ('owner','pin','cap','rail')]
        details=row.get('reason_details')
        if details is None:
            result[_key([*identity,row.get('reason')])]=1
            continue
        if (type(details)is not list or not 1<=len(details)<=len(codes)
                or any(type(d)is not dict or set(d)!={'code','message','severity'}
                    or type(d['code'])is not str or d['code']not in codes
                    or type(d['message'])is not str or not d['message']
                    or type(d['severity'])not in(int,float)
                    or not math.isfinite(d['severity'])or d['severity']<=0 for d in details)
                or len({d['code']for d in details})!=len(details)
                or '; '.join(d['message']for d in details)!=row.get('reason')):
            raise ValueError('complete_unique_measured_decoupler_fault_details_required')
        for detail in details:
            key=_key([*identity,detail['code']])
            result[key]=max(result.get(key,0),detail['severity'])
    return result


def geometry_faults(details):
    """Conservative early return-distance filter; routed gates remain final.

    The native authority publishes rounded diagnostics, so a sub-report-unit
    excess might survive this inexpensive filter, never the final oracle.
    Do not use supply-copper availability while incident branches are removed.
    """
    return {_key([row.get('cap_ref'), row.get('owner_ref'), row.get('owner_pin'),
                  row.get('rail'), 'absolute_return_distance']):
            float(row['ground_distance_mm'])
            for row in details
            if row.get('return_gate_mode') == 'absolute_ground_distance'
            and isinstance(row.get('ground_distance_mm'), (float, int))
            and isinstance(row.get('return_limit_mm'), (float, int))
            and row['ground_distance_mm'] > row['return_limit_mm']}


def proximity_geometry_faults(details, *, loop_excess_max_mm=0.25):
    """Necessary proximity bound, allowing the best future return topology.

    A disconnected staging board can temporarily lose its via-in-pad return
    classification. Do not hard-reject its isolated-supply failure alone:
    restoring/adding a qualified dual VIP return may make the complete-loop
    mode valid. Reject only when BOTH existing proximity modes necessarily
    fail at these native pad positions. Shared-pin competition, rail-to-rail
    cells and unavailable reference geometry remain for the full oracle.
    """
    if (type(loop_excess_max_mm) not in (int,float)
            or not math.isfinite(loop_excess_max_mm) or loop_excess_max_mm<0):
        raise ValueError('loop proximity limit must be finite and nonnegative')
    import cec_synth_pipeline as synth
    identities=[(row.get('owner_ref'),str(row.get('owner_pin')),row.get('rail'))
                for row in details]
    counts=Counter(identities)
    faults={}
    def number(value):
        return type(value) in (int,float) and math.isfinite(value) and value>=0
    def point(value):
        return (isinstance(value,(list,tuple)) and len(value)==2
                and all(type(v) in (int,float) and math.isfinite(v) for v in value))
    for row,identity in zip(details,identities):
        if (row.get('status')!='assigned' or counts[identity]!=1
                or row.get('return_gate_mode')!='absolute_ground_distance'
                or row.get('shared_pin_reference') or not row.get('cap_ref')
                or not row.get('owner_ref') or row.get('owner_pin') is None):
            continue
        tangent=row.get('tangent_target') or {}
        ideal_supply=synth._decoupler_ideal_supply_mm(tangent)
        ideal_loop=(tangent.get('best_loop') or {}).get('loop_proxy_mm')
        supply_limit=row.get('supply_excess_limit_mm')
        coordinates=[row.get(key) for key in ('owner_supply_position_mm',
            'cap_supply_position_mm','owner_ground_position_mm','cap_ground_position_mm')]
        if (not all(number(v) for v in (ideal_supply,ideal_loop,supply_limit))
                or not all(point(v) for v in coordinates)):
            continue
        # Positions are native integer-nanometre coordinates emitted as mm;
        # use them and the raw tangent reference, not rounded display distances.
        supply=math.dist(coordinates[0],coordinates[1])
        ground=math.dist(coordinates[2],coordinates[3])
        supply_violation=supply-float(ideal_supply)-float(supply_limit)
        loop_violation=supply+ground-float(ideal_loop)-float(loop_excess_max_mm)
        if supply_violation>1e-9 and loop_violation>1e-9:
            faults[_key([row['cap_ref'],row['owner_ref'],row['owner_pin'],
                         row.get('rail'),'both_supply_and_vip_loop_proximity'])] = \
                min(supply_violation,loop_violation)
    return faults


def measure(board_path, policy=None, phase='routed'):
    import pcbnew
    import cec_decoupler_cell
    import cec_synth_pipeline as synth
    if phase not in ('geometry', 'routed'):
        raise ValueError('unknown support craft phase')
    params = dict((policy or {}).get('params') or {})
    cfg = SimpleNamespace(params=params)
    adjacency = synth._oracle_decoupler_adjacency(str(board_path), cfg,
        phase='routed' if phase == 'routed' else 'placement')
    if 'error' in adjacency or 'details' not in adjacency:
        return dict(ok=False, error='decoupler_geometry_unavailable', release_authority=False)
    faults = {'return_geometry': geometry_faults(adjacency['details']),
        'proximity_geometry': proximity_geometry_faults(adjacency['details'],
            loop_excess_max_mm=float(params.get('decoupler_loop_excess_max_mm',0.25)))}
    gates = {}
    if phase == 'routed':
        board = pcbnew.LoadBoard(str(board_path))
        cells = cec_decoupler_cell.audit_board(board, board_path=str(board_path),
            ground_reach_mm=float(params.get('decoupler_ground_reach_mm', 1.5)),
            ground_pin_max_mm=float(params.get('decoupler_ground_pin_max_mm', 2.5)))
        dimensions = synth._oracle_netclass_geometry(str(board_path))
        if 'error' in dimensions or 'error' in cells:
            return dict(ok=False, error='routed_craft_measurement_unavailable', release_authority=False)
        gates = dict(decouple_ok=adjacency['ok'], decoupler_cell_ok=cells['ok'],
                     netclass_geometry_ok=dimensions['ok'])
        faults['decouple_ok'] = {_key(row[:2]): float(row[2]) for row in
            adjacency.get('all_violations', adjacency.get('violations', []))}
        faults['decoupler_cell_ok'] = _decoupler_cell_faults(cells.get('refused', []))
        faults['netclass_geometry_ok'] = {_key([row.get('net'), row.get('kind'), uid]): 1
            for row in dimensions.get('violations', []) for uid in row.get('uuids', [])}
    elif phase != 'geometry':
        raise ValueError('unknown support craft phase')
    return dict(ok=True, phase=phase, gates=gates, faults=faults, release_authority=False)


def compare(before, after):
    """Reject new/worsened identities as well as any passing gate regression."""
    if before.get('ok') is not True or after.get('ok') is not True:
        return dict(accepted=False, decision='support_craft_worker_error',
                    reason='measurement_unavailable',
                    release_authority=False)
    losses = sorted(key for key, passed in before.get('gates', {}).items()
                    if passed is True and after.get('gates', {}).get(key) is not True)
    new = {}
    for kind, rows in after.get('faults', {}).items():
        previous = before.get('faults', {}).get(kind, {})
        added = sorted(key for key, severity in rows.items()
                       if key not in previous or severity > previous[key])
        if added:
            new[kind] = added
    accepted = not losses and not new
    return dict(accepted=accepted, decision='support_craft_nonregression' if accepted
                else 'support_craft_regressed', gate_regressions=losses,
                new_or_worsened_faults=new, release_authority=False)
