"""Native-bound electrical locality restrictions for geometric proposal search.

This is a non-regression search domain, not a new electrical release rule.
Existing violations are retained as explicit debt, never silently qualified.
"""
import inspect
import math


def build(board, craft):
    import cec_fr
    import cec_synth_pipeline as synth
    positions = {str(fp.GetReference()): (fp.GetPosition().x/1e6,
        fp.GetPosition().y/1e6, float(fp.GetOrientationDegrees()))
        for fp in board.GetFootprints()}
    templates = synth._parallel_pour_pad_templates(board)
    specs = synth._parallel_pour_critical_terminal_specs(craft)
    baseline = synth._parallel_pour_critical_terminal_geometry(positions, templates, specs)
    if baseline['qualified_relations'] != len(specs):
        raise ValueError('incomplete native critical-terminal binding')
    # Same default actually used by precision.compile's Kelvin constructor;
    # do not introduce an unrelated placer distance or a new load assumption.
    limit = float(inspect.signature(cec_fr.synthesize_kelvin_taps).parameters['max_ic_mm'].default)
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError('Kelvin constructor range unavailable')
    detection = []
    for row in (craft.get('detection_cell') or {}).get('details', ()):
        pairs = row.get('terminal_pairs')
        if not pairs:
            raise ValueError('detector terminal binding unavailable')
        for pair in pairs:
            for endpoint in pair:
                _point(positions, templates, endpoint)
        distance = _distance(positions, templates, pairs)
        stated = float(row['distance_mm'])
        maximum = float(row['limit_mm'])
        if (not all(math.isfinite(v) for v in (stated, maximum)) or maximum <= 0
                or abs(stated-distance) > 3e-6):
            raise ValueError('detector evidence does not match native geometry')
        detection.append(dict(net=row['net'], pairs=pairs, baseline_mm=distance,
                              limit_mm=maximum, ceiling_mm=max(maximum,distance)))
    return dict(positions=positions, templates=templates, specs=specs,
                terminal_baseline=baseline, kelvin_limit_mm=limit, detection=detection,
                scope='non-regressing native locality domain; no release authority')


def _point(positions, templates, endpoint):
    import cec_pcb
    ref, pin, net = (str(endpoint[k]) for k in ('ref','pad','net'))
    pads = [p for p in templates.get(ref, ()) if str(p.get('pad'))==pin]
    if len(pads)!=1 or pads[0].get('net')!=net or ref not in positions:
        raise ValueError('ambiguous or missing bound electrical terminal')
    x,y,angle = map(float,positions[ref])
    if not all(math.isfinite(v) for v in (x,y,angle)):
        raise ValueError('nonfinite electrical terminal pose')
    dx,dy = cec_pcb._rot(*pads[0]['local'],angle)
    return x+dx,y+dy


def _distance(positions, templates, pairs):
    return min(math.dist(_point(positions,templates,a),_point(positions,templates,b))
               for a,b in pairs)


def check(contract, positions, *, tolerance_mm=3e-6):
    """Reject new crossing/range/locality debt per relation, not a total score.

    One shortened input cannot compensate for another input becoming longer
    than its own bound. Already-out-of-range inputs may improve or stay equal,
    but passing inputs retain the constructor's normal range, not zero slack.
    """
    import cec_synth_pipeline as synth
    errors=[]
    try:
        for ref,pose in positions.items():
            if len(pose)!=3 or not all(math.isfinite(float(v)) for v in pose):
                raise ValueError('invalid electrical search pose')
        baseline=contract['terminal_baseline']
        after=synth._parallel_pour_critical_terminal_geometry(
            positions,contract['templates'],contract['specs'])
        old={(r['anchor_ref'],r['ref']):r for r in baseline['details']}
        new={(r['anchor_ref'],r['ref']):r for r in after['details']}
        declared={(r['anchor_ref'],r['ref']) for r in contract['specs']
                  if r.get('follower_pad_contract')}
        if set(old)!=set(new):
            raise ValueError('electrical relationship disappeared')
        for key,row in new.items():
            prior=old[key]
            if row['crossings']>prior['crossings']:
                errors.append(dict(kind='terminal_crossing',refs=list(key),
                                   before=prior['crossings'],after=row['crossings']))
            # Filtered topologies already have their own path/demand contract.
            # Do not substitute the direct constructor's radius for that path.
            if row.get('relation_kind')=='filtered':
                if row['direct_length_mm']>prior['direct_length_mm']+tolerance_mm:
                    errors.append(dict(kind='filtered_terminal_length',refs=list(key)))
                continue
            distances=row.get('terminal_distances_mm') or {}
            old_distances=prior.get('terminal_distances_mm') or {}
            if set(distances)!=set(old_distances) or not distances:
                raise ValueError('per-terminal native range unavailable')
            for net,distance in distances.items():
                ceiling=max(float(contract['kelvin_limit_mm']) if key in declared else 0.,
                            float(old_distances[net]))
                if distance>ceiling+tolerance_mm:
                    errors.append(dict(kind='terminal_range',refs=list(key),net=net,
                        distance_mm=distance,ceiling_mm=ceiling,baseline_mm=old_distances[net]))
        for relation in contract['detection']:
            distance=_distance(positions,contract['templates'],relation['pairs'])
            if distance>relation['ceiling_mm']+tolerance_mm:
                errors.append(dict(kind='detector_locality',net=relation['net'],
                    distance_mm=distance,ceiling_mm=relation['ceiling_mm']))
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        return dict(ok=False,errors=[dict(kind='electrical_binding_error',error=str(exc))])
    return dict(ok=not errors,errors=errors)


def binding_matches(contract, positions, *, tolerance_mm=3e-6):
    """Never apply an old native-point contract to a moved incumbent."""
    expected=contract['positions']
    if set(expected)!=set(positions):return False
    for ref,old in expected.items():
        pose=positions[ref]
        if (len(pose)!=3 or not all(math.isfinite(float(v)) for v in pose)
                or math.dist(old[:2],pose[:2])>tolerance_mm
                or abs((float(pose[2])-old[2]+180)%360-180)>1e-6):
            return False
    return True
