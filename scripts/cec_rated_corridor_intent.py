"""Source-bound full-load future-path obstacles; not copper or capacity credit.

The caller supplies spatial intent only. Width comes from the exact source
current contract. This does not authorize moving an existing item, accepting
the proposed power path, sharing current, or changing a fabrication rule.
"""
import math


def segments(request, *, source_sha256, blocked_net, contract, domain):
    if (type(request) is not dict
            or set(request) != {'schema', 'source_sha256', 'net', 'layer', 'paths_nm'}
            or request['schema'] != 1 or type(request['schema']) is not int
            or type(source_sha256) is not str or len(source_sha256) != 64
            or any(c not in '0123456789abcdef' for c in source_sha256)
            or request['source_sha256'] != source_sha256):
        raise ValueError('exact_source_bound_future_current_path_required')
    net, layer = request['net'], request['layer']
    if (type(net) is not str or not net or net == blocked_net
            or type(layer) is not str or not layer
            or type(domain) is not dict or domain.get('net') != net
            or domain.get('complete') is not True
            or type(domain.get('amps')) not in (int, float)
            or not math.isfinite(domain['amps']) or domain['amps'] <= 0
            or not domain.get('source_refs') or not domain.get('sink_refs')
            or type(contract) is not dict or layer not in contract.get('routing_layers', ())):
        raise ValueError('unchanged_complete_foreign_current_domain_required')
    floor = contract.get('required_by_layer_mm', {}).get(layer)
    if (type(floor) not in (int, float) or not math.isfinite(floor)
            or not 0 < floor <= 20):
        raise ValueError('whole_actual_layer_current_width_required')
    width = math.ceil(floor * 1e6)
    paths = request['paths_nm']
    if (type(paths) is not list or not 1 <= len(paths) <= 8
            or any(type(path) is not list or not 2 <= len(path) <= 65 for path in paths)
            or sum(len(path) - 1 for path in paths) > 64):
        raise ValueError('bounded_explicit_future_current_paths_required')
    result = []
    for path in paths:
        if any(type(point) is not list or len(point) != 2
               or any(type(v) is not int or abs(v) > 2_000_000_000 for v in point)
               for point in path):
            raise ValueError('finite_actual_integer_future_current_path_required')
        for left, right in zip(path, path[1:]):
            dx, dy = right[0]-left[0], right[1]-left[1]
            if (not (dx or dy) or not (dx == 0 or dy == 0 or abs(dx) == abs(dy))
                    or math.hypot(dx, dy) > 100_000_000):
                raise ValueError('bounded_nonzero_octilinear_current_intent_required')
            result.append((tuple(left), tuple(right), width, layer))
    return result


def install(board, source, requests, *, board_hint, blocked_net):
    """Temporary foreign tracks for a bounded current-aware search only.

    Rederive the domains/contracts from the immutable saved source. The
    construction caller owns removal in a finally block before any save;
    this supplies no current, contact, sharing, thermal or route authority.
    Partial validation failure rolls back every temporary item atomically.
    """
    import pcbnew
    import cec_force_current as force
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_fr as fr
    from cec_native_items import discard_items
    if (type(requests) not in (list, tuple) or not 1<=len(requests)<=4
            or type(board_hint) is not str or not board_hint
            or type(blocked_net) is not str or not blocked_net):
        raise ValueError('bounded_source_current_intent_installation_required')
    sha=force._hash(source);parent=pcbnew.LoadBoard(str(source))
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(parent,board_hint)
        contracts=topology.route_width_contracts(parent,board_hint=board_hint)
    items=[];proofs=[]
    try:
        for request in requests:
            if type(request) is not dict:raise ValueError('exact_source_current_request_required')
            reserved=segments(request,source_sha256=sha,blocked_net=blocked_net,
                domain=domains.get(request.get('net')),contract=contracts.get(request.get('net')))
            layer=int(board.GetLayerID(request['layer']));net=board.FindNet(request['net'])
            if (layer not in board.GetEnabledLayers().CuStack()
                    or layer in {board.GetLayerID(n) for n in fr.plane_layers(board)}
                    or fab.COPPER_LAYER_IDS.get(layer)!=request['layer']
                    or net is None or net.GetNetCode()<=0):
                raise ValueError('actual_enabled_nonplane_foreign_current_layer_required')
            for left,right,width,_ in reserved:
                t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*left))
                t.SetEnd(pcbnew.VECTOR2I(*right));t.SetWidth(width);t.SetLayer(layer)
                t.SetNet(net);board.Add(t);items.append(t)
            proofs.append(dict(source_sha256=sha,net=request['net'],actual_layer=request['layer'],
                full_source_width_nm=reserved[0][2],segments=len(reserved),
                current_or_sharing_qualified=False,release_authority=False))
        if sha!=force._hash(source):raise ValueError('saved_current_intent_source_changed')
    except Exception:
        discard_items(board,items)
        raise
    return items,proofs
