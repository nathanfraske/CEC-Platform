"""Explicit off-board conductor networks, separate from native PCB copper.

This is a bounded DC/electrothermal diagnostic, not an admission receiver.
The caller supplies real bar, joint and PCB branches and thermal boundaries;
no default solder resistance, convection, equal sharing or extra PCB metal is
invented. Distributed contacts are represented by multiple joint branches.
Native connectivity, Kelvin isolation and physical qualification stay separate.
"""
from __future__ import annotations

import math

from .identity import digest, require


def _number(value, name, low, high):
    require(type(value) in (int, float) and math.isfinite(value)
            and low <= value <= high, name)
    return float(value)


def _names(values, name):
    require(type(values) is list and 1 <= len(values) <= 128
            and all(type(v) is str and 0 < len(v) <= 100 for v in values)
            and len(set(values)) == len(values), name)
    return values


def _pairs(rows, nodes, fields, label):
    require(type(rows) is list and 1 <= len(rows) <= 512, 'bounded_' + label)
    seen = set()
    for row in rows:
        require(type(row) is dict and set(row) == fields, 'exact_' + label)
        require(type(row['id']) is str and 0 < len(row['id']) <= 100
                and row['id'] not in seen, 'unique_' + label)
        seen.add(row['id'])
        require(row['a'] in nodes and row['b'] in nodes and row['a'] != row['b'],
                'existing_distinct_' + label + '_endpoints')


def _solve(nodes, links, fixed, injections):
    """Positive-resistance network with explicit fixed boundary nodes."""
    import numpy as np

    connected = set(fixed)
    while True:
        before = len(connected)
        for a, b, _ in links:
            if a in connected or b in connected:
                connected.update((a, b))
        if len(connected) == before:
            break
    require(connected == set(nodes), 'network_has_floating_or_uncooled_nodes')
    unknown = [n for n in nodes if n not in fixed]
    index = {n: i for i, n in enumerate(unknown)}
    matrix = np.zeros((len(unknown), len(unknown)))
    rhs = np.array([injections.get(n, 0.) for n in unknown], dtype=float)
    for a, b, resistance in links:
        conductance = 1. / resistance
        for left, right in ((a, b), (b, a)):
            if left in fixed:
                continue
            i = index[left]
            matrix[i, i] += conductance
            if right in fixed:
                rhs[i] += conductance * fixed[right]
            else:
                matrix[i, index[right]] -= conductance
    try:
        answer = np.linalg.solve(matrix, rhs) if unknown else []
    except np.linalg.LinAlgError as exc:
        raise ValueError('singular_conductor_network') from exc
    require(all(math.isfinite(float(v)) for v in answer), 'nonfinite_network_result')
    result = dict(fixed)
    result.update(zip(unknown, (float(v) for v in answer)))
    balance = {n: -injections.get(n, 0.) for n in nodes}
    for a, b, resistance in links:
        flow = (result[a] - result[b]) / resistance
        balance[a] += flow
        balance[b] -= flow
    scale = max(1., sum(abs(v) for v in injections.values()),
                sum(abs((result[a]-result[b])/r) for a, b, r in links))
    require(max((abs(balance[n]) for n in unknown), default=0.) <= scale * 1e-9,
            'network_conservation_residual')
    return result, balance


def solve(model):
    """Solve the supplied coupled network, never silently accept a plateau.

    All resistances are in ohms / K per watt. Positive injections enter nodes.
    Each electrical branch heats one declared thermal node. A bar divided into
    sections plus explicit solder branches can represent distributed transfer.
    Temperature-independent branches must explicitly set alpha_per_K to zero.
    """
    require(type(model) is dict and set(model) == {
        'schema', 'electrical_nodes', 'thermal_nodes', 'reference', 'injections_a',
        'electrical', 'thermal', 'bath_C', 'evidence'}, 'exact_conductor_model_required')
    require(type(model['schema']) is int and model['schema'] == 1,
            'conductor_schema_required')
    nodes = _names(model['electrical_nodes'], 'explicit_electrical_nodes_required')
    thermal = _names(model['thermal_nodes'], 'explicit_thermal_nodes_required')
    require(model['reference'] in nodes, 'existing_electrical_reference_required')
    evidence = model['evidence']
    require(type(evidence) is dict and set(evidence) == {'basis', 'limitations'}
            and all(type(v) is str and v.strip() for v in evidence.values()),
            'explicit_parameter_basis_and_limitations_required')
    injections = model['injections_a']
    require(type(injections) is dict and set(injections) <= set(nodes),
            'explicit_existing_current_injections_required')
    for v in injections.values():
        _number(v, 'finite_bounded_current_required', -10000, 10000)
    require(abs(sum(injections.values())) <= 1e-10
            and any(abs(v) > 0 for v in injections.values()),
            'balanced_nonzero_current_injections_required')
    baths = model['bath_C']
    require(type(baths) is dict and baths and set(baths) <= set(thermal),
            'explicit_existing_thermal_boundaries_required')
    for v in baths.values():
        _number(v, 'physical_bath_temperature_required', -273.14, 1000)
    branches, paths = model['electrical'], model['thermal']
    _pairs(branches, nodes, {'id','a','b','r_ref_ohm','ref_C','alpha_per_K',
                            'valid_C','thermal_node','kind'}, 'electrical_branches')
    _pairs(paths, thermal, {'id','a','b','K_per_W'}, 'thermal_branches')
    for branch in branches:
        _number(branch['r_ref_ohm'], 'positive_bounded_electrical_resistance', 1e-9, 1e6)
        _number(branch['ref_C'], 'physical_reference_temperature', -273.14, 1000)
        _number(branch['alpha_per_K'], 'explicit_bounded_temperature_coefficient', 0, .02)
        valid = branch['valid_C']
        require(type(valid) is list and len(valid) == 2, 'explicit_resistance_temperature_range')
        for value in valid:
            _number(value, 'physical_resistance_temperature_range', -273.14, 1000)
        require(valid[0] <= branch['ref_C'] <= valid[1] and valid[0] < valid[1],
                'valid_resistance_reference_range')
        require(branch['thermal_node'] in thermal
                and branch['kind'] in ('bar','joint','pcb','component'),
                'explicit_branch_heat_node_and_kind')
    for path in paths:
        _number(path['K_per_W'], 'positive_bounded_thermal_resistance', 1e-9, 1e9)
    heat_links = [(p['a'], p['b'], p['K_per_W']) for p in paths]
    temperatures, _ = _solve(thermal, heat_links, baths, {})
    result = None
    for iteration in range(1, 201):
        links = []
        for branch in branches:
            temp = temperatures[branch['thermal_node']]
            require(branch['valid_C'][0] <= temp <= branch['valid_C'][1],
                    'resistance_temperature_model_extrapolation')
            r = branch['r_ref_ohm'] * (1 + branch['alpha_per_K'] * (temp-branch['ref_C']))
            require(math.isfinite(r) and r > 0, 'nonpositive_hot_resistance')
            links.append((branch['a'], branch['b'], r))
        volts, balances = _solve(nodes, links, {model['reference']: 0.}, injections)
        heat = dict.fromkeys(thermal, 0.)
        rows = []
        for branch, (a, b, resistance) in zip(branches, links):
            current = (volts[a]-volts[b])/resistance
            watts = current*current*resistance
            heat[branch['thermal_node']] += watts
            rows.append(dict(id=branch['id'], kind=branch['kind'], current_a=current,
                             resistance_ohm=resistance, joule_W=watts,
                             temperature_C=temperatures[branch['thermal_node']]))
        new_temps, heat_balance = _solve(thermal, heat_links, baths, heat)
        error = max(abs(new_temps[n]-temperatures[n]) for n in thermal)
        if error < 1e-7:
            total = sum(heat.values())
            supplied = sum(volts[n]*v for n, v in injections.items())
            rejected = -sum(heat_balance[n] for n in baths)
            require(abs(total-supplied) <= max(1e-10, total*1e-8)
                    and abs(total-rejected) <= max(1e-10, total*1e-8)
                    and max(abs(v) for v in balances.values()) <= 1e-7,
                    'electrothermal_energy_or_current_balance_failed')
            result = dict(model_sha256=digest(model), iterations=iteration,
                          voltage_V=volts, temperature_C=temperatures, branches=rows,
                          total_joule_W=total, supplied_W=supplied, rejected_W=rejected,
                          converged=True, scope='supplied lumped DC/steady thermal network only',
                          native_copper_changed=False, native_connectivity_inferred=False,
                          current_sharing_assumed=False, parameter_qualification=False,
                          assembled_Kelvin_checked=False, release_authority=False)
            break
        temperatures = {n: (temperatures[n]+new_temps[n])*.5 for n in thermal}
    require(result is not None, 'electrothermal_iteration_limit_not_qualification')
    return result


def bulk_resistance_bounds(dimensions_mm, resistivity_ohm_m):
    """Geometric ohmic bounds only; caller supplies material/temperature bounds."""
    require(type(dimensions_mm) is dict and set(dimensions_mm) == {'length','width','height'},
            'exact_bar_dimension_intervals_required')
    for interval in [*dimensions_mm.values(), resistivity_ohm_m]:
        require(type(interval) is list and len(interval) == 2, 'two_element_bound_required')
        for value in interval:
            _number(value, 'positive_finite_dimension_or_resistivity', 1e-12, 1000)
        require(interval[0] <= interval[1], 'ordered_material_bounds_required')
    length, width, height = (dimensions_mm[k] for k in ('length','width','height'))
    return [resistivity_ohm_m[0]*length[0]*1000/(width[1]*height[1]),
            resistivity_ohm_m[1]*length[1]*1000/(width[0]*height[0])]
