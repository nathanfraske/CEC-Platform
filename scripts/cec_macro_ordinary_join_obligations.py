"""Source-owned ordinary opens participate in the SAME macro joint solve.

An obstacle repair must not consume a stationary owner's only signal escape.
Explicit bounded net requests derive their exact old disconnected lands,
class dimensions and ordinary eligibility afresh. At least one selected land
must be a manufacturer-typed signal/control pin in the actual macro cohort. This is
not power, pair, sense, no-connect, current or placement authority.
"""
import math
import copy
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
import cec_ordinary_signal_completion as ordinary


def boundary_scope(board, source, request, *, board_hint, timeout_s=10.):
    """Bind search policy for an already-owned ordinary cut component.

    This is not a retirement or endpoint-projection authority. The compiler
    independently owns those operations and every surviving contact. Here
    actual saved Source edges, positive ordinary eligibility and full class
    dimensions only permit the SAME native search used by an ordinary open.
    """
    import cec_ordinary_route_receiving as eligible
    import cec_route_dimensions as dimensions
    import cec_fr as fr
    started=time.monotonic()
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or request.get('kind')!='source_boundary'
            or request.get('every_surviving_source_component_port_mandatory') is not True
            or type(request.get('width_nm')) is not int or not 0<request['width_nm']<=350000):
        raise ValueError('bounded_positive_ordinary_cut_boundary_required')
    source=Path(source).resolve(strict=True);binding=row._source_binding(board)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_ordinary_cut_source_required')
    if request.get('net') not in eligible.eligible_nets(board,source,board_hint):
        raise ValueError('positive_ordinary_cut_source_net_required')
    authorities=request.get('exact_additional_macro_component_source_ownership')
    if (type(authorities) is not list or not 1<=len(authorities)<=64
            or any(type(q) is not dict or set(q)!={'kind','native_source_uuid'}
                or q.get('kind')!='positive_source_ordinary' for q in authorities)):
        raise ValueError('only_positive_original_ordinary_cut_edges_required')
    ids=[q['native_source_uuid'] for q in authorities]
    live={force._uid(t):t for t in board.GetTracks()}
    if len(set(ids))!=len(ids) or not set(ids)<=live.keys():
        raise ValueError('unique_actual_ordinary_source_cut_edges_required')
    for uid in ids:
        edge=live[uid]
        if (edge.GetClass()!='PCB_TRACK' or edge.GetNetname()!=request['net'] or edge.HasSolderMask()
                or edge.GetParentGroup() is not None or not 0<edge.GetWidth()<=request['width_nm']
                or not 0<edge.GetLength()<=32000000):
            raise ValueError('literal_bounded_ordinary_cut_source_geometry_required')
    all_live={**live,**{force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}}
    for name in ('a','b'):
        endpoint=request.get(name,{})
        named=([endpoint['pad_uuid']] if endpoint.get('pad_uuid') else endpoint.get('native_uuids'))
        if (type(named) is not list or not 1<=len(named)<=16 or len(set(named))!=len(named)
                or not set(named)<=all_live.keys() or set(named)&set(ids)
                or any(all_live[u].GetNetname()!=request['net'] for u in named)):
            raise ValueError('actual_surviving_ordinary_cut_contacts_required')
    spec=fr._project_netclass_resolver(str(source))(request['net']) or {}
    compiled=dimensions.compile_spec(spec,limits=dimensions.board_limits(board),role='branch')
    minimum_width=max(request['width_nm'],round(compiled['track_width']*1e6))
    clearance=max(int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance') or 0)*1e6))
    if not 0<minimum_width<500000 or clearance<=0:
        raise ValueError('bounded_authored_ordinary_cut_search_dimensions_required')
    if time.monotonic()-started>=timeout_s or row._source_binding(board)!=binding:
        raise ValueError('ordinary_cut_search_scope_expired_or_source_changed')
    return dict(scope='source_typed_stationary_ordinary_cut_search',source=str(source),
        source_sha256=force._hash(source),source_native_binding=binding,board_hint=board_hint,
        request={k:copy.deepcopy(v) for k,v in request.items() if k!='source_ordinary_boundary_scope'},
        minimum_width_nm=minimum_width,clearance_nm=clearance,
        no_cut_endpoint_projection_or_current_authority=True,routing_admitted=False,release_authority=False)


def plan(board, source, proposal, nets, *, timeout_s=10.):
    if (type(nets) not in (list, tuple) or not 1 <= len(nets) <= 4
            or any(type(n) is not str or not n or len(n) > 256
                   or any(ord(c) < 32 for c in n) for n in nets)
            or len(set(nets)) != len(nets)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_explicit_source_ordinary_macro_joins_required')
    deadline = time.monotonic() + timeout_s
    source = Path(source).resolve(strict=True)
    binding = row._source_binding(board)
    if (proposal.get('scope') != 'source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding') != binding
            or row._source_binding(pcbnew.LoadBoard(str(source))) != binding):
        raise ValueError('literal_complete_macro_source_required_for_ordinary_joins')
    requests = {}
    for net in nets:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('source_ordinary_macro_join_inventory_deadline')
        scoped = ordinary.plan(board, source, board_hint=proposal['board_hint'], net=net,
                               timeout_s=min(10., remaining))
        if scoped.get('complete') is not True:
            raise ValueError('positive_disconnected_ordinary_macro_source_required:'+net)
        demand = scoped['request']
        pads = ordinary._pads(board, demand)
        witnesses = []
        for pad in pads:
            fp = pad.GetParentFootprint()
            ref = fp.GetReference()
            if ref not in proposal['poses']:
                continue
            model = roles.footprint_contract(fp)
            if (model is None or model != proposal['device_contracts'].get(ref)
                    or set(model['pins']) != {p.GetNumber() for p in fp.Pads()}
                    or model['pins'].get(pad.GetNumber()) not in ('signal_input', 'signal_output', 'control')):
                continue
            witnesses.append(dict(pad_uuid=force._uid(pad), owner=ref, pin=pad.GetNumber(),
                role=model['pins'][pad.GetNumber()], manufacturer_source=model['source']))
        if not witnesses:
            raise ValueError('actual_macro_manufacturer_signal_pin_required:'+net)
        def endpoint(pad):
            return dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()),
                        layers=sorted(map(int, pad.GetLayerSet().CuStack())))
        requests['ordinary_join:'+net] = dict(kind='source_boundary', net=net,
            a=endpoint(pads[0]), b=endpoint(pads[1]), width_nm=demand['width_nm'],
            clearance_nm=demand['clearance_nm'], source_ordinary_join_scope=scoped,
            source_ordinary_native_binding=binding,
            source_macro_signal_pin_witnesses=witnesses,
            simultaneous_obstacle_and_original_open_connectivity_required=True,
            no_power_pair_measurement_or_current_authority=True)
    if row._source_binding(board) != binding or time.monotonic() >= deadline:
        raise ValueError('source_ordinary_macro_join_inventory_changed_or_expired')
    return requests


def native_choices(board, request, pairs, *, route_layers, width_for_layer,
                   clearance_nm, foreign_cache, deadline, accept):
    """Bounded saved-outline search for compiler-owned ordinary join menus.

    A local endpoint halo can exclude the only side of a retained bus that
    is traversable. Reuse the exact native endpoint graph used by ordinary
    completion, not preselected radial vias. Original component aliases,
    exact width/clearance, native guards, productive walks and final whole
    selection receiving remain mandatory. This routine emits nothing.
    """
    import cec_fr as fr
    join=request.get('source_ordinary_join_scope')
    boundary=request.get('source_ordinary_boundary_scope')
    if (request.get('kind') != 'source_boundary' or (join is None)==(boundary is None)
            or type(pairs) not in (list, tuple) or not 1 <= len(pairs) <= 32
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not time.monotonic() < deadline <= time.monotonic()+10.
            or not callable(width_for_layer) or not callable(accept)):
        raise ValueError('bounded_source_ordinary_joint_native_search_required')
    scoped=join if join is not None else boundary
    source = Path(scoped['source']).resolve(strict=True)
    before = pcbnew.LoadBoard(str(source))
    if join is not None:
        original=scoped.get('request',{})
        fresh=ordinary.plan(before,source,board_hint=scoped['board_hint'],net=request['net'],
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if (fresh!=scoped or fresh.get('complete') is not True
                or original.get('net')!=request.get('net')
                or original.get('width_nm')!=request.get('width_nm')
                or row._source_binding(before)!=request.get('source_ordinary_native_binding')):
            raise ValueError('fresh_saved_ordinary_scope_required_for_joint_native_search')
    else:
        fresh=boundary_scope(before,source,request,board_hint=scoped['board_hint'],
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if fresh!=scoped:
            raise ValueError('fresh_saved_ordinary_cut_scope_required_for_joint_native_search')
        original=dict(width_nm=fresh['minimum_width_nm'],clearance_nm=fresh['clearance_nm'])
    if (type(clearance_nm) is not int
            or clearance_nm < max(original['clearance_nm'],int(board.GetDesignSettings().m_MinClearance))):
        raise ValueError('ordinary_joint_native_clearance_cannot_relax_source')
    resolver = fr._project_netclass_resolver(str(source))
    spec = resolver(request['net']) or {}
    permitted = set(fr._lastmile_route_layers(board, net_name=request['net'],
        spec=spec, exclude_front=False))
    original_faces = set(request['a']['layers']) & set(request['b']['layers'])
    layers = sorted(permitted & (set(route_layers) | original_faces))
    bridges = [l for l in layers if l != pcbnew.F_Cu]
    result = dict(choices=[], trials=[], original_deadline=deadline,
        exact_native_guards_and_saved_outline_envelope=True,
        exact_native_access_refusals=[],
        no_path_proof=False, routing_admitted=False, release_authority=False)
    if len(layers) < 2 or not bridges:
        return result
    binding = row._source_binding(board)
    code = board.GetNetcodeFromNetname(request['net'])
    width = max(request['width_nm'],original['width_nm'],int(board.GetDesignSettings().m_TrackMinWidth))
    widths={face:width_for_layer(face) for face in layers}
    if any(type(w)is not int or w<width for w in widths.values()):
        raise ValueError('ordinary_joint_native_width_cannot_relax_source')
    # General component menus can contain legitimate pad-edge/body contact
    # sites. The stricter native-endpoint graph accepts ONLY literal centres,
    # track ends and barrel axes. One unsupported alias cannot abort the
    # original valid pair and all other aliases. Filter, never invent access.
    from cec_native_route_portal import endpoint_layers
    valid=[]
    for pair in pairs:
        first,last=pair
        aa=endpoint_layers(board,tuple(first['at_nm']),code)&set(first['layers'])&set(layers)
        bb=endpoint_layers(board,tuple(last['at_nm']),code)&set(last['layers'])&set(layers)
        if not aa or not bb:
            result['exact_native_access_refusals'].append(dict(a_nm=first['at_nm'],b_nm=last['at_nm']))
            continue
        valid.append((dict(first,layers=sorted(aa)),dict(last,layers=sorted(bb))))
        if len(valid)>=8:break
    # Finite actual aliases, original named pair first. Retain a finer pass
    # within the SAME lease even when the coarse graph refuses or times out.
    work = [(pair, reverse) for pair in valid for reverse in (False, True)]
    seen = set()
    for resolution, grid in enumerate((.5, .25)):
        now = time.monotonic()
        if now >= deadline:
            break
        resolution_deadline = now+(deadline-now)/(2-resolution)
        for index, (pair, reverse) in enumerate(work):
            now = time.monotonic()
            if now >= resolution_deadline:
                break
            first, last = pair[::-1] if reverse else pair
            lease = min(resolution_deadline, now+max(.03,
                (resolution_deadline-now)/min(4, len(work)-index)))
            diagnostic = {}
            direct = math.dist(first['at_nm'], last['at_nm'])/1e6
            ops = fr._lastmile_bridge(board, tuple(first['at_nm']), set(first['layers']),
                tuple(last['at_nm']), set(last['layers']), width, code, bridges, clearance_nm,
                drill=float(spec.get('via_drill') or .3), dia=float(spec.get('via_diameter') or .6),
                leg_ok=lambda a,b,h: fr._edge_leg_clear(board,a,b,h), allow_maze=True,
                foreign_cache=foreign_cache, width_for_layer=lambda face:widths[face],
                deadline_monotonic=lease, diagnostics=diagnostic, ops_ok=accept,
                max_length_nm=min(32., direct+8.)*1e6, multilayer_lays=layers,
                _multilayer_only=True, _multilayer_pair_limit=1, native_endpoint_seeds=True,
                middle_native_board_envelope=True, middle_grid_mm=grid,
                obstacle_channel_axes=True, canonical_turns_only=True,
                middle_max_vias=2, max_expanded_states=50000, search_wall_cap_s=10.)
            result['trials'].append(dict(grid_mm=grid, reverse=reverse,
                a_nm=first['at_nm'], b_nm=last['at_nm'], found=ops is not None,
                deadline_monotonic=lease, diagnostics=diagnostic))
            if ops is not None and accept(ops):
                signature=repr([(op[0], tuple(op[1]), tuple(op[2]) if op[0]=='trk' else op[2],
                                 *op[3:]) for op in ops])
                if signature not in seen:
                    seen.add(signature)
                    result['choices'].append(ops)
            if len(result['choices']) >= 4:
                break
        if len(result['choices']) >= 4:
            break
    if row._source_binding(board) != binding:
        raise ValueError('ordinary_joint_native_search_changed_private_frame')
    return result
