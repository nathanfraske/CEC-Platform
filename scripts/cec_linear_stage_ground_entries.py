"""Independent Ground demands for a freshly Source-proved linear power stage.

This is NOT a relaxed low-power capacitor portal. Every original selected
minimum keeps its own immediate return, and each manufacturer Ground root
keeps a separate immediate-return demand. No owner-through-cap/package link,
cut, barrel, current, thermal, placement, routing or release right is created.
The enclosing compiler/receiver still owns every original Source obligation.
"""
import json
import math
import time

import pcbnew
import cec_constraints as constraints
import cec_cell_row_rebuild as row
import cec_control_gate_bias_placement as identity
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_source_linear_power_stage as stage

SCOPE = 'Source_linear_stage_independent_ground_demands-v1'


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _wire(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _unique(board, ref):
    matches = [fp for fp in board.GetFootprints() if fp.GetReference() == ref]
    _need(len(matches) == 1, 'linear_stage_ground_unique_native_package_required:' + ref)
    return matches[0]


def _selected(inventory, owners):
    """Keep the complete original requirement identities, not nearest-cap hints."""
    requirements = {r['id'] for r in inventory['requirements'] if r['ref'] in owners}
    _need(requirements, 'linear_stage_ground_original_selected_minima_required')
    rows = {}
    for key, selected in inventory['assigned'].items():
        req = selected['requirement']
        if req['ref'] not in owners:
            continue
        _need(key in requirements and req.get('return_rail', 'GND') == 'GND',
              'linear_stage_ground_grounded_selected_minima_required')
        rows[key] = dict(cap_ref=selected['cap_ref'], owner=req['ref'], pin=str(req['pin']),
            rail=req['rail'], return_rail='GND', kind=req['kind'], max_mm=req['max_mm'])
    _need(set(rows) == requirements
          and len({r['cap_ref'] for r in rows.values()}) == len(rows),
          'linear_stage_ground_complete_unique_selected_minima_required')
    return rows


def entries(parent, posed, proposal, *, board_hint, timeout_s=10.):
    """Recompile Source, compare actual poses/minima, return a narrow composition.

    ``selected_bypasses`` is the ONLY exclusion set for the legacy low-power
    ``assigned_ground_entries`` call. Merge ``independent_ground_requests``
    AFTER the ordinary Ground loop, replacing—not inheriting—any shortcut
    keys on those exact roots. Ground-strapped control pads and all other
    original requests remain the enclosing compiler's independent duties.
    Request metadata is not authority: saved receiving must call this again.
    """
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s)
          and 0 < timeout_s <= 10. and type(proposal) is dict,
          'bounded_linear_stage_ground_constituent_required')
    deadline = time.monotonic() + timeout_s

    def tick():
        _need(time.monotonic() < deadline, 'linear_stage_ground_constituent_deadline')

    enabled = proposal.get('allow_linear_power_stage_reconstruction', False)
    _need(type(enabled) is bool, 'linear_stage_ground_explicit_boolean_scope_required')
    if not enabled:
        _need(not proposal.get('source_linear_power_stages'),
              'linear_stage_ground_role_requires_explicit_Source_scope')
        return {}
    _need(type(board_hint) is str and bool(board_hint), 'linear_stage_ground_Source_hint_required')
    poses = proposal.get('poses')
    before = row._source_binding(parent), row._source_binding(posed)
    fresh = stage.collect(parent, poses, board_hint=board_hint,
        reference_group_uuids=proposal.get('reference_group_uuids', ()),
        enabled=True, timeout_s=max(.001, deadline-time.monotonic()))
    _need(_wire(fresh) == _wire(proposal.get('source_linear_power_stages', {})),
          'linear_stage_ground_stale_or_forged_Source_identity')
    tick()
    if not fresh:
        _need(before == (row._source_binding(parent), row._source_binding(posed)),
              'linear_stage_ground_empty_scope_changed_native_frame')
        return {}
    owners = set(fresh)
    with force._thermal_hint(board_hint):
        original = _selected(constraints._device_bypass_assignment(parent, project_max_mm=3.5), owners)
        projected = _selected(constraints._device_bypass_assignment(posed, project_max_mm=3.5), owners)
    _need(original == projected, 'linear_stage_ground_original_selected_minima_changed')
    selected = {r['cap_ref']: dict(owner=r['owner'], pin=r['pin'], rail=r['rail'])
                for r in original.values()}
    proposed = proposal.get('selected_bypasses')
    _need(type(proposed) is dict and {k: v for k, v in proposed.items()
        if k in selected or type(v) is dict and v.get('owner') in owners} == selected,
        'linear_stage_ground_proposal_selected_minima_changed')
    demand_pads = {}; roots = {}
    for ref in sorted(owners | set(selected)):
        tick(); source = _unique(parent, ref); actual = _unique(posed, ref)
        _need(ref in poses, 'linear_stage_ground_complete_selected_follower_poses_required')
        target = poses[ref]
        _need(type(target) in (list, tuple) and len(target) == 3
              and all(type(v) in (int, float) and math.isfinite(v) for v in target),
              'linear_stage_ground_finite_target_pose_required')
        expected = pcbnew.FOOTPRINT(source)
        expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        expected.SetOrientationDegrees(target[2])
        _need(identity._footprint(posed, actual) == identity._footprint(posed, expected),
              'linear_stage_ground_exact_rigid_Source_package_required:' + ref)
        _need(not actual.IsDNP() and not actual.IsLocked(),
              'linear_stage_ground_populated_unlocked_Source_package_required')
        if ref in owners:
            model = fresh[ref]['manufacturer']
            _need(model['device_package'] == 'TPS2121 RUX'
                  and not set(model['pins'].values()) & {'switch', 'feedback'},
                  'linear_stage_ground_positive_complete_linear_manufacturer_required')
            ground = [p for p in actual.Pads() if model['pins'].get(p.GetNumber())
                in ('ground', 'reference', 'power_return') and p.GetNetname() == 'GND']
            _need(ground and all(p.GetNetname() == 'GND' for p in actual.Pads()
                if model['pins'].get(p.GetNumber()) in ('ground', 'power_return')),
                'linear_stage_ground_all_manufacturer_roots_required')
            roots[ref] = sorted(force._uid(p) for p in ground)
        else:
            choice = selected[ref]; owner = _unique(posed, choice['owner'])
            pads = list(actual.Pads())
            _need(len(pads) == 2 and actual.IsFlipped() == owner.IsFlipped()
                  and {p.GetNetname() for p in pads} == {'GND', choice['rail']},
                  'linear_stage_ground_exact_selected_surface_capacitor_required')
            positive = next(p for p in pads if p.GetNetname() == choice['rail'])
            supply = owner.FindPadByNumber(choice['pin'])
            _need(supply is not None and supply.GetNetname() == choice['rail']
                  and fresh[choice['owner']]['manufacturer']['pins'].get(choice['pin'])
                      in ('power_input', 'power_output')
                  and math.dist(tuple(supply.GetPosition()), tuple(positive.GetPosition())) <= 3500000,
                  'linear_stage_ground_selected_supply_locality_required')
            ground = [p for p in pads if p.GetNetname() == 'GND']
        for pad in ground:
            layers = list(map(int, pad.GetLayerSet().CuStack()))
            _need(pad.GetNetCode() > 0 and not pad.HasHole() and not pad.IsLocked()
                  and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and len(layers) == 1
                  and layers[0] in (pcbnew.F_Cu, pcbnew.B_Cu) and posed.IsLayerEnabled(layers[0]),
                  'linear_stage_ground_independent_surface_land_required')
            uid = force._uid(pad)
            _need(uid not in demand_pads, 'linear_stage_ground_duplicate_root_identity')
            demand_pads[uid] = pad
    tick()
    width = max(200000, int(posed.GetDesignSettings().m_TrackMinWidth),
                int(cells._netclass(posed, 'GND')['width']))
    demands = {'ground:'+uid: dict(kind='ground', net='GND',
        a=dict(pad_uuid=uid, at_nm=list(pad.GetPosition()),
               layers=list(map(int, pad.GetLayerSet().CuStack()))),
        reach_mm=.8, width_nm=width, same_package_ground_link_proposal_allowed=False,
        independent_linear_stage_ground_demand=True, current_authority=False,
        source_trace_retirement_authority=False, new_barrel_authority=False, release_authority=False)
        for uid, pad in sorted(demand_pads.items())}
    _need(before == (row._source_binding(parent), row._source_binding(posed)),
          'linear_stage_ground_native_frame_changed')
    tick()
    return _wire(dict(scope=SCOPE, selected_bypasses=selected,
        independent_ground_requests=demands, manufacturer_ground_roots=roots,
        source_linear_power_stages=fresh, current_authority=False,
        source_trace_retirement_authority=False, new_barrel_authority=False,
        routing_admitted=False, release_authority=False))


def requests(parent, posed, proposal, *, board_hint, timeout_s=10.):
    """Convenience demand map; ``entries`` also provides the narrow exclusion set."""
    return entries(parent, posed, proposal, board_hint=board_hint,
                   timeout_s=timeout_s).get('independent_ground_requests', {})
