"""Bounded sizing screen for explicit two-node parallel copper bundles.

No equal layer/pin sharing, barrel ampacity, or native-node equivalence is
inferred. This is a resistance-interval planning tool, NOT permission to
replace full-current copper. Native contacts, transitions, clipped Kelvin,
coupled thermal and saved-board receiving must independently accept a change.
All required inputs are explicit; there are no board, refdes or net policies.
"""
from __future__ import annotations

import math

MAX_BRANCHES = 8
MAX_SEGMENTS = 256
RHO_20_OHM_MM = 1.72e-5
ALPHA_CU = .00393


def _number(value, label, *, minimum=0., maximum=2000.):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('parallel_current_invalid_' + label)
    return float(value)


def _interval(value, label, *, positive=True, maximum=2000.):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('parallel_current_explicit_interval_required_' + label)
    lo, hi = (_number(v, label, maximum=maximum) for v in value)
    if hi < lo or positive and lo <= 0:
        raise ValueError('parallel_current_invalid_interval_' + label)
    return lo, hi


def _rho(temperature_c):
    return RHO_20_OHM_MM * (1 + ALPHA_CU * (temperature_c - 20))


def plated_barrel_resistance_ohm(*, length_mm, drill_mm, plating_mm, temperature_c):
    """Thin-wall lower-area resistance bound, not a barrel current rating.

    Actual plating bounds must be supplied, never a default IPC/class label.
    A via field's aggregate resistance requires an actual connected network,
    not a count divided into this value. Solder/pin fill is not credited.
    """
    length = _number(length_mm, 'barrel_length', minimum=1e-9)
    drill = _number(drill_mm, 'barrel_drill', minimum=1e-9)
    plating = _number(plating_mm, 'barrel_plating', minimum=1e-9, maximum=1.)
    temperature = _number(temperature_c, 'barrel_temperature', minimum=-100., maximum=300.)
    return _rho(temperature) * length / (math.pi * drill * plating)


def short_neck_temperature_rise_bound_c(*, amps, length_mm, width_mm, copper_mm,
                                      endpoint_temperature_c, conductivity_w_mk):
    """1-D steady uniform heating with BOTH endpoints held at a known bound.

    Side cooling is ignored. The endpoint temperature and minimum copper
    conductivity are conditions to verify in a coupled native-board solve,
    not inferred sinks. This does NOT accept an IPC-width failure or prove
    contact spreading, current crowding, transients, barrels or board cooling.
    rho is conservatively evaluated at 300 C, the declared model ceiling.
    """
    current = _number(amps, 'neck_current')
    length = _number(length_mm, 'neck_length', minimum=1e-9)
    width = _number(width_mm, 'neck_width', minimum=1e-9)
    thickness = _number(copper_mm, 'neck_copper', minimum=1e-9, maximum=1.)
    end = _number(endpoint_temperature_c, 'endpoint_temperature', minimum=-100., maximum=300.)
    k = _number(conductivity_w_mk, 'copper_conductivity', minimum=1e-9, maximum=1000.)
    # rho[ohm mm] / k[W/(m K)] requires a 1000 conversion to mm.
    rise = current**2 * _rho(300.) * 1000 * length**2 / (8 * k * (width * thickness)**2)
    if end + rise > 300:
        raise ValueError('parallel_current_neck_model_temperature_ceiling_exceeded')
    return dict(rise_bound_c=rise, peak_bound_c=end+rise,
        both_endpoint_temperature_bound_c=end, conductivity_min_w_mk=k,
        boundary_receiving_required=True, current_crowding_qualified=False,
        coupled_thermal_qualified=False, routing_admitted=False, release_authority=False)


def screen_bundle(current, branches, *, terminals, permitted_layers, rise_c=30.):
    """Screen a complete caller-declared parallel bundle between TWO nodes.

    Every branch carries the same supplied terminal identities; intermediate
    cross-links/loads are outside this topology and need a network solve.
    Worst branch share uses its R_min against all other R_max, NOT I/N.
    Segment utilization retains the correlation between copper area, path
    resistance and current: thinner copper cannot simultaneously attract the
    current of the thickest version of that same path. The exact one-variable
    extremum is checked, including an interior critical area. Series resistance
    intervals include transitions/contact paths;
    supplying them does not itself qualify their thermal/current capability.
    Margin is applied once to each resulting branch current, never to current
    sharing. A passing IPC screen still provides no routing/release admission.
    """
    import cec_fab_profile as fab
    if not isinstance(current, dict) or not {'amps','geometry_margin','margin_included'} <= current.keys():
        raise ValueError('parallel_current_existing_authority_required')
    amps = _number(current['amps'], 'aggregate_current', minimum=1e-9)
    margin = _number(current['geometry_margin'], 'geometry_margin', minimum=1.)
    if type(current['margin_included']) is not bool or current['margin_included'] and margin != 1.:
        raise ValueError('parallel_current_margin_must_apply_once')
    rise = _number(rise_c, 'rise', minimum=1e-9, maximum=300.)
    if (not isinstance(terminals, (list,tuple)) or len(terminals)!=2
            or any(type(t) is not str or not t for t in terminals) or terminals[0]==terminals[1]):
        raise ValueError('parallel_current_two_distinct_terminals_required')
    if (not isinstance(permitted_layers, (list,tuple,set,frozenset)) or not permitted_layers
            or any(l not in fab.COPPER_LAYERS for l in permitted_layers)
            or len(set(permitted_layers)) != len(permitted_layers)):
        raise ValueError('parallel_current_explicit_permitted_layers_required')
    if (not isinstance(branches, (list,tuple)) or not 2<=len(branches)<=MAX_BRANCHES):
        raise ValueError('parallel_current_branch_bound')
    rows = []; ids = set(); count = 0
    for branch in branches:
        if not isinstance(branch, dict) or set(branch) != {'id','terminals','segments','series_ohm','temperature_c'}:
            raise ValueError('parallel_current_explicit_complete_branch_required')
        uid = branch['id']
        if type(uid) is not str or not uid or uid in ids:
            raise ValueError('parallel_current_unique_branch_required')
        ids.add(uid)
        ends = branch['terminals']
        if not isinstance(ends, (list,tuple)) or tuple(ends) not in (tuple(terminals),tuple(reversed(terminals))):
            raise ValueError('parallel_current_not_same_two_terminal_bundle')
        temps = branch['temperature_c']
        if not isinstance(temps,(list,tuple)) or len(temps)!=2:
            raise ValueError('parallel_current_temperature_interval_required')
        tlo,thi = (_number(t,'temperature',minimum=-100.,maximum=300.) for t in temps)
        if thi<tlo:raise ValueError('parallel_current_temperature_interval_order')
        rlo,rhi = _interval(branch['series_ohm'], 'series_resistance', positive=False, maximum=1000.)
        rmid = (rlo+rhi)/2
        segments = branch['segments']
        if not isinstance(segments,(list,tuple)) or not segments:
            raise ValueError('parallel_current_nonempty_segments_required')
        details = []
        for segment in segments:
            count += 1
            if count>MAX_SEGMENTS:raise ValueError('parallel_current_segment_bound')
            if not isinstance(segment,dict) or set(segment)!={'layer','length_mm','width_mm','copper_mm'}:
                raise ValueError('parallel_current_explicit_complete_segment_required')
            layer = segment['layer']
            if type(layer) is not str or layer not in permitted_layers:
                raise ValueError('parallel_current_unpermitted_layer')
            length = _interval(segment['length_mm'],'length')
            width = _interval(segment['width_mm'],'width')
            copper = _interval(segment['copper_mm'],'copper',maximum=1.)
            low = _rho(tlo)*length[0]/(width[1]*copper[1])
            high = _rho(thi)*length[1]/(width[0]*copper[0])
            middle = _rho((tlo+thi)/2)*sum(length)/2/(sum(width)/2*(sum(copper)/2))
            rlo += low; rhi += high; rmid += middle
            details.append(dict(layer=layer,length_mm=length,width_mm=width,copper_mm=copper,
                                resistance_ohm=(low,high),rho_length_min_ohm_mm2=_rho(tlo)*length[0]))
        if not all(math.isfinite(r) and r>0 for r in (rlo,rhi,rmid)):
            raise ValueError('parallel_current_positive_finite_resistance_required')
        rows.append(dict(id=uid,resistance_ohm=(rlo,rhi),nominal_resistance_ohm=rmid,segments=details))
    total_g = sum(1/r['nominal_resistance_ohm'] for r in rows)
    for row in rows:
        own_lo, own_hi = row['resistance_ohm']
        others = [r for r in rows if r['id'] != row['id']]
        maximum = amps * (1/own_lo) / (1/own_lo + sum(1/r['resistance_ohm'][1] for r in others))
        minimum = amps * (1/own_hi) / (1/own_hi + sum(1/r['resistance_ohm'][0] for r in others))
        nominal = amps/(row['nominal_resistance_ohm']*total_g)
        for segment in row['segments']:
            # All OTHER own-branch resistances are minimized and all other
            # branches maximized. For this segment retain R=C/A exactly.
            # I(A)/A^b = I_total*A^(1-b)/(D*A+E), b=.725;
            # its sole interior maximum is A=(1-b)*E/(b*D).
            conductance = sum(1/r['resistance_ohm'][1] for r in others)
            c = segment['rho_length_min_ohm_mm2']
            rest = max(0.,own_lo-segment['resistance_ohm'][0])
            d,e = 1+rest*conductance,c*conductance
            area_lo = segment['width_mm'][0]*segment['copper_mm'][0]
            area_hi = segment['width_mm'][1]*segment['copper_mm'][1]
            critical = (1-.725)*e/(.725*d)
            candidates = {area_lo,area_hi,min(area_hi,max(area_lo,critical))}
            coefficient = fab.ipc2221_required_width_mm(1.,segment['layer'],
                copper_mm=1.,rise_c=rise,margin=margin)
            evaluations = [(coefficient*(amps*a/(d*a+e))**(1/.725)/a,a,
                            amps*a/(d*a+e)) for a in candidates]
            ratio,area,at_current = max(evaluations)
            segment.update(ipc_worst_capacity_ratio=ratio,critical_area_mm2=area,
                critical_current_a=at_current,ipc_width_screen_ok=ratio <= 1.)
        row.update(nominal_current_a=nominal, current_interval_a=(minimum,maximum),
                   ipc_width_screen_ok=all(s['ipc_width_screen_ok'] for s in row['segments']))
    return dict(schema=1,scope='bounded_two_node_resistance_and_ipc_width_screen',
        aggregate_current_authority=dict(current),terminals=list(terminals),rise_c=rise,branches=rows,
        nominal_equivalent_resistance_ohm=1/total_g,
        worst_network_loss_w=amps**2/sum(1/r['resistance_ohm'][1] for r in rows),
        ipc_width_screen_ok=all(r['ipc_width_screen_ok'] for r in rows),
        unequal_sharing_screened=True, per_connector_pin_current_division=False,
        native_common_nodes_verified=False, transitions_current_qualified=False,
        coupled_thermal_qualified=False, routing_admitted=False, release_authority=False)
