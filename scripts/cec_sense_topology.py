"""Bounded sense-input lineage through typed series resistors.

This is electrical identity evidence, not copper connectivity or an electrical
rating. Capacitors, connectors and untyped two-terminal parts are not edges.
Ambiguous, incomplete and work-limited searches never choose a nearest shunt.
"""
from collections import defaultdict
import math
import re


def trace_inputs(pad_nets, inputs, *, resistor_refs, anchors,
                 max_hops=4, max_expansions=256):
    """Resolve each declared input pair to one anchor and two disjoint paths.

    ``anchors`` maps authoritative reference -> {pad: net}; it is supplied by
    the caller, not inferred from component names, resistance or proximity.
    Paths run from the input toward the anchor and retain both resistor pads.
    """
    if type(max_hops) is not int or not 0 <= max_hops <= 8:
        raise ValueError('sense topology max_hops must be an integer in 0..8')
    if type(max_expansions) is not int or not 1 <= max_expansions <= 100000:
        raise ValueError('sense topology max_expansions must be in 1..100000')
    terminals = defaultdict(list)
    for ref, pads in sorted(anchors.items()):
        if len(pads) != 2 or len(set(pads.values())) != 2 or not all(pads.values()):
            raise ValueError('sense anchor requires two distinct assigned terminals')
        if dict(pad_nets.get(ref, {})) != dict(pads):
            raise ValueError('sense anchor disagrees with live pad nets')
        for pad, net in sorted(pads.items()):terminals[net].append((ref,pad))
    edges = defaultdict(list)
    for ref in sorted(set(resistor_refs)-set(anchors)):
        pads = pad_nets.get(ref, {})
        if len(pads) != 2 or len(set(pads.values())) != 2 or not all(pads.values()):continue
        (a,na),(b,nb) = sorted(pads.items())
        edges[na].append((ref,a,b,nb))
        edges[nb].append((ref,b,a,na))
    results=[]
    for item in sorted(inputs,key=lambda row:(row['ref'],tuple(row['pins']))):
        used=0
        truncated=False
        def walk(start):
            nonlocal used,truncated
            found=[]
            pending=[(start,(),frozenset((start,)))]
            while pending:
                if used>=max_expansions:
                    truncated=True;break
                net,path,visited=pending.pop(0);used+=1
                if net in terminals:
                    found.extend(dict(anchor_ref=ref,anchor_pad=pin,anchor_net=net,
                                      series=list(path)) for ref,pin in terminals[net])
                    continue
                successors=[edge for edge in edges.get(net,()) if edge[3] not in visited]
                if len(path)>=max_hops:
                    truncated |= bool(successors)
                    continue
                for ref,near,far,other in successors:
                    step=dict(ref=ref,input_pad=near,anchor_pad=far,
                              input_net=net,anchor_net=other)
                    pending.append((other,path+(step,),visited|{other}))
            return found
        ref=item['ref'];pins=tuple(item['pins'])
        nets=(item['p'],item['n'])
        row=dict(ref=ref,device=item.get('device'),pins=list(pins),input_nets=list(nets))
        if (len(pins)!=2 or len(set(nets))!=2 or not all(nets)
                or any(pad_nets.get(ref,{}).get(pin)!=net for pin,net in zip(pins,nets))):
            row.update(ok=False,reason='input_contract_mismatch',candidates=[])
            results.append(row);continue
        positive,negative=(walk(net) for net in nets)
        candidates=[]
        for p in positive:
            for n in negative:
                if used>=max_expansions:
                    truncated=True;break
                used+=1
                if p['anchor_ref']!=n['anchor_ref'] or p['anchor_pad']==n['anchor_pad']:continue
                p_refs={s['ref'] for s in p['series']};n_refs={s['ref'] for s in n['series']}
                if p_refs & n_refs:continue
                p_nets={nets[0]}|{s['anchor_net'] for s in p['series']}
                n_nets={nets[1]}|{s['anchor_net'] for s in n['series']}
                if p_nets & n_nets:continue
                candidates.append(dict(anchor_ref=p['anchor_ref'],p=p,n=n,
                    kind='filtered' if p['series'] or n['series'] else 'direct'))
                if len(candidates)>=2:break
            if truncated or len(candidates)>=2:break
        row.update(ok=not truncated and len(candidates)==1,
            reason=('search_budget_exhausted' if truncated else
                    'unresolved' if not candidates else 'ambiguous' if len(candidates)>1 else 'resolved'),
            candidates=candidates,work_used=used,work_limit=max_expansions,
            max_hops=max_hops,exhaustion_is_no_path_proof=False)
        if row['ok']:row['selected']=candidates[0]
        results.append(row)
    return dict(schema=1,ok=all(row['ok'] for row in results),inputs=len(results),
                resolved=sum(row['ok'] for row in results),details=results)


def board_evidence(board, *, anchor_pairs=None, anchor_refs=(),
                   max_hops=4, max_expansions=256):
    """Native adapter using typed resistor footprints and existing pair identity.

    Library category is an explicit type witness; a refdes beginning with R,
    or a numeric value alone, cannot make a capacitor/connector a series edge.
    Callers may supply arbitrary declared anchor net pairs. The default keeps
    the pipeline's existing HI/LO family convention, without joining sheets.
    ``anchor_refs`` may additionally name components from complete current-flow
    authority. This supports renamed force nets without guessing from values.
    """
    import cec_pair_semantics
    footprints={fp.GetReference():fp for fp in board.GetFootprints()}
    pad_nets={ref:{pad.GetNumber():pad.GetNetname() for pad in fp.Pads()}
              for ref,fp in footprints.items()}
    # Repeated pad numbers are legal, but conflicting assignments are not.
    for ref,fp in footprints.items():
        seen=defaultdict(set)
        for pad in fp.Pads():seen[pad.GetNumber()].add(pad.GetNetname())
        if any(len(nets)>1 for nets in seen.values()):
            raise ValueError('conflicting native pad identity for '+ref)
    resistors={ref for ref,fp in footprints.items()
        if re.search(r'(?:^|[-_])Resistor_(?:SMD|THT)$',fp.GetFPIDAsString().partition(':')[0])}
    if anchor_pairs is None:
        names={net for pads in pad_nets.values() for net in pads.values() if net}
        anchor_pairs=[(net,net[:-3]+'_LO') for net in sorted(names)
                      if net.endswith('_HI') and net[:-3]+'_LO' in names]
    pairs={frozenset(pair) for pair in anchor_pairs}
    if any(len(pair)!=2 or not all(pair) for pair in pairs):
        raise ValueError('invalid declared sense anchor pair')
    declared=set(anchor_refs)
    anchors={ref:pads for ref,pads in pad_nets.items()
             if ref in resistors and len(pads)==2 and len(set(pads.values()))==2
             and (frozenset(pads.values()) in pairs or ref in declared)}
    inputs=[]
    for ref,fp in footprints.items():
        contract=cec_pair_semantics.footprint_input_contract(fp)
        if contract is None:
            if re.match(r'^INA(?:181|240)', fp.GetValue(), re.I):
                raise ValueError('selected_measurement_package_required_for_input_contract')
            continue
        device,pins=contract
        inputs.append(dict(ref=ref,device=device,pins=list(pins),
            p=pad_nets[ref].get(pins[0],''),n=pad_nets[ref].get(pins[1],'')))
    result=trace_inputs(pad_nets,inputs,
        resistor_refs=resistors,anchors=anchors,max_hops=max_hops,max_expansions=max_expansions)
    result.update(anchor_refs=sorted(anchors),typed_resistor_refs=sorted(resistors),
                  authority='declared_input_pins_and_typed_series_resistors',
                  copper_connectivity_proved=False)
    return result


def placement_segments(row):
    """Export only real same-net copper demands, never a resistor bypass.

    The topology row is an identity witness, not a route. Each series device
    splits a leg into separate copper segments; its internal electrical path
    must never be represented as same-net PCB copper. Geometry consumers must
    recheck both endpoint identities against their current pad data.
    """
    if not row.get('ok') or not row.get('selected'):
        raise ValueError('unqualified sense topology cannot create placement demands')
    selected = row['selected']
    segments = []
    for index, leg in enumerate(('p', 'n')):
        ref, pad, net = row['ref'], row['pins'][index], row['input_nets'][index]
        path = selected[leg]
        for step in path['series']:
            if step['input_net'] != net or step['anchor_net'] == net:
                raise ValueError('discontinuous sense series path')
            segments.append(dict(leg=leg, net=net,
                start=dict(ref=ref, pad=pad),
                end=dict(ref=step['ref'], pad=step['input_pad'])))
            ref, pad, net = step['ref'], step['anchor_pad'], step['anchor_net']
        if net != path['anchor_net'] or path['anchor_ref'] != selected['anchor_ref']:
            raise ValueError('discontinuous sense anchor path')
        segments.append(dict(leg=leg, net=net,
            start=dict(ref=ref, pad=pad),
            end=dict(ref=path['anchor_ref'], pad=path['anchor_pad'])))
    return segments


def demand_geometry(segments, pad_lookup):
    """Shared full/cheap placement metric with exact endpoint/net identity.

    ``pad_lookup(ref, pad, net)`` must return one current physical pad centre
    or raise for missing/ambiguous/mismatched data. Distinct electrical nets
    may not silently share a made-up chord through a series component. This
    is a demand metric, not a proof of routed copper or physical infeasibility.
    """
    rays = []
    for segment in segments:
        ends = [tuple(map(float, pad_lookup(end['ref'], end['pad'], segment['net'])))
                for end in (segment['start'], segment['end'])]
        if any(len(p) != 2 or not all(map(math.isfinite, p)) for p in ends):
            raise ValueError('invalid sense demand geometry')
        rays.append(dict(segment, start_mm=ends[0], end_mm=ends[1]))

    def crosses(a, b, c, d):
        def orient(p, q, r):
            return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
        o1, o2, o3, o4 = orient(a,b,c), orient(a,b,d), orient(c,d,a), orient(c,d,b)
        return (((o1 < -1e-9 and o2 > 1e-9) or (o2 < -1e-9 and o1 > 1e-9))
                and ((o3 < -1e-9 and o4 > 1e-9) or (o4 < -1e-9 and o3 > 1e-9)))

    crossings = []
    for i, first in enumerate(rays):
        for j, second in enumerate(rays[i+1:], i+1):
            if first['net'] != second['net'] and crosses(
                    first['start_mm'], first['end_mm'], second['start_mm'], second['end_mm']):
                crossings.append([i,j])
    return dict(crossings=len(crossings), crossing_segments=crossings,
                direct_length_mm=round(sum(math.dist(r['start_mm'], r['end_mm']) for r in rays),6),
                segment_count=len(rays), segments=rays, copper_connectivity_proved=False)


def filtered_alignment(board, evidence, *, tolerance_mm):
    """Measure the existing lateral-alignment rule in the actual shunt frame.

    No nearest-component choice and no fixed board-X axis. This is a placement
    measurement only; it cannot prove the trace reaches the selected terminals.
    """
    if not math.isfinite(tolerance_mm) or tolerance_mm<=0:
        raise ValueError('alignment tolerance must be finite and positive')
    footprints={fp.GetReference():fp for fp in board.GetFootprints()}
    details=[]
    for row in evidence['details']:
        if not row['ok']:
            details.append(dict(ref=row['ref'],ok=False,reason=row['reason']))
            continue
        selected=row['selected']
        if selected['kind']!='filtered':continue
        anchor=footprints.get(selected['anchor_ref']);owner=footprints.get(row['ref'])
        if anchor is None or owner is None:
            raise ValueError('resolved sense footprint missing from native board')
        def require_net(fp,number,net):
            matching=[p for p in fp.Pads() if p.GetNumber()==number]
            if not matching or any(p.GetNetname()!=net for p in matching):
                raise ValueError('resolved sense terminal net changed')
        for pin,net in zip(row['pins'],row['input_nets']):require_net(owner,pin,net)
        for leg in ('p','n'):
            for step in selected[leg]['series']:
                fp=footprints.get(step['ref'])
                if fp is None:raise ValueError('resolved series component missing')
                require_net(fp,step['input_pad'],step['input_net'])
                require_net(fp,step['anchor_pad'],step['anchor_net'])
        points=[]
        for leg in ('p','n'):
            number=selected[leg]['anchor_pad']
            pads=[p for p in anchor.Pads() if p.GetNumber()==number]
            if any(p.GetNetname()!=selected[leg]['anchor_net'] for p in pads):
                raise ValueError('resolved sense anchor net changed')
            coordinates={(p.GetPosition().x,p.GetPosition().y) for p in pads}
            if len(coordinates)!=1:
                raise ValueError('resolved sense anchor geometry is ambiguous')
            points.append(next(iter(coordinates)))
        position=owner.GetPosition();a,b=points
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<=0:raise ValueError('sense anchor axis is degenerate')
        cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2
        offset=abs(dx*(position.y-cy)-dy*(position.x-cx))/length/1e6
        details.append(dict(ref=row['ref'],anchor_ref=selected['anchor_ref'],
            ok=offset<=tolerance_mm+1e-9,lateral_offset_mm=round(offset,6),
            tolerance_mm=tolerance_mm,axis=[dx/length,dy/length],
            series_refs=sorted({s['ref'] for leg in ('p','n') for s in selected[leg]['series']})))
    return dict(ok=all(row['ok'] for row in details),details=details,
                checked=sum('lateral_offset_mm' in row for row in details))
