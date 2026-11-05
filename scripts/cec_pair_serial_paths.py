"""Exact native copper-contact trees for series pair-transition accounting.

A branched bus can contain many parallel terminal taps without putting every
barrel in series on a signal path. This audit never changes the transition
limit, whole-net skew convention, copper, reference, clearance or fab gates.
Unknown primitive types, incomplete inventories and cycles furnish no authority.
"""
import itertools
import math
import time

def tree_paths(graph, terminals, route_via_ids, *, deadline=None):
    """Report every unique terminal path, not an optimistic path in a loop."""
    if (not 3 <= len(terminals) <= 16 or len(set(terminals.values())) != len(terminals)
            or any(node not in graph for node in terminals.values())
            or sum(len(adjacent) for adjacent in graph.values()) != 2*(len(graph)-1)):
        raise ValueError('complete_unique_native_terminal_tree_required')
    rows = []
    traversals = {}
    for left, right in itertools.combinations(sorted(terminals), 2):
        if deadline is not None and time.monotonic() >= deadline:
            raise ValueError('native_serial_path_deadline')
        if left not in traversals:
            source = terminals[left];parents = {source:None};pending = [source]
            while pending:
                current = pending.pop()
                for other in graph[current]:
                    if other not in parents:
                        parents[other] = current;pending.append(other)
            if len(parents) != len(graph):
                raise ValueError('complete_unique_native_terminal_tree_required')
            traversals[left] = parents
        parents = traversals[left];path = [];cursor = terminals[right]
        while cursor is not None:
            path.append(cursor);cursor = parents[cursor]
        path.reverse()
        vias = [node[1] for node in path if node[0] == 'via'
                and node[1] in route_via_ids]
        rows.append(dict(terminals=[left,right], route_via_uuids=vias,
            route_transition_vias=len(vias)))
    return rows


def graph_evidence(board,graph):
    """Bounded native witnesses for redundant plated-pad transition loops."""
    import pcbnew
    items = {item.m_Uuid.AsString():item for item in board.GetTracks()}
    pads = {pad.m_Uuid.AsString():pad for fp in board.GetFootprints() for pad in fp.Pads()}
    evidence = dict(nodes=len(graph),edges=sum(map(len,graph.values()))//2,
                    redundant_plated_tap_witnesses=[])
    for pad_id,pad in sorted(pads.items()):
        root = ('pad',pad_id)
        if root not in graph or pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not pad.HasHole():
            continue
        for via_id,via in sorted(items.items()):
            barrel = ('via',via_id)
            if barrel not in graph or via.GetClass() != 'PCB_VIA':
                continue
            shared = sorted(set(graph[root]) & set(graph[barrel]))
            if len(shared) >= 2 and len(evidence['redundant_plated_tap_witnesses']) < 16:
                evidence['redundant_plated_tap_witnesses'].append(dict(
                    pad_uuid=pad_id,via_uuid=via_id,net=pad.GetNetname(),
                    pad_at_mm=[v/1e6 for v in pad.GetPosition()],
                    via_at_mm=[v/1e6 for v in via.GetPosition()],
                    actual_contact_layers=[board.GetLayerName(node[1]) for node in shared],
                    scope='parallel_native_contact_loop_not_ripup_permission'))
    return evidence


def _native_tree(board, net, pad_ids, *, deadline):
    """Collapse exact same-face native copper, then join actual plated spans.

    Series accounting needs copper islands, not an approximate centreline
    intersection graph: a real tee can contact the side of a wide track.
    Native effective-shape contact grants only electrical layer-path evidence,
    never hole-aperture/current, clearance, width or fabrication qualification.
    """
    import pcbnew

    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('native_serial_contact_deadline')

    uid = lambda item:item.m_Uuid.AsString()
    tracks = [t for t in board.GetTracks() if t.GetNetname() == net]
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.IsOnCopperLayer() and p.GetNetname() == net]
    if (not 1 <= len(tracks) <= 512 or set(pad_ids) != {uid(p) for p in pads}
            or any(t.GetClass() not in ('PCB_TRACK','PCB_VIA') for t in tracks)
            or any(z.GetNetname() == net and not z.GetIsRuleArea() for z in board.Zones())):
        raise ValueError('bounded_trace_only_complete_terminal_inventory_required')
    enabled = set(map(int,board.GetEnabledLayers().CuStack()))
    junctions = {}
    graph = {}
    def add_edge(left,right,*,length_mm):
        graph.setdefault(left,{})[right] = length_mm
        graph.setdefault(right,{})[left] = length_mm
    for item in tracks:
        tick()
        if item.GetClass() == 'PCB_TRACK':
            a,z = tuple(item.GetStart()),tuple(item.GetEnd())
            if a == z or item.GetWidth() <= 0 or int(item.GetLayer()) not in enabled:
                raise ValueError('positive_enabled_native_track_required')
        else:
            if (item.GetViaType() != pcbnew.VIATYPE_THROUGH or item.GetDrillValue() <= 0
                    or item.GetWidth(item.TopLayer()) <= item.GetDrillValue()
                    or int(item.TopLayer()) != int(pcbnew.F_Cu)
                    or int(item.BottomLayer()) != int(pcbnew.B_Cu)):
                raise ValueError('actual_positive_through_barrel_required')
            junctions[('via',uid(item))] = item
    for pad in pads:
        if (pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH,pcbnew.PAD_ATTRIB_SMD)
                or pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and not pad.HasHole()):
            raise ValueError('actual_copper_terminal_required')
        junctions[('pad',uid(pad))] = pad
    by_uid = {uid(item):item for item in [*tracks,*pads]}
    if len(by_uid) != len(tracks)+len(pads):
        raise ValueError('unique_native_copper_primitive_ids_required')
    root_nodes = {uid(item):node for node,item in junctions.items()}
    for face in sorted(enabled):
        rows = [(key,item.GetEffectiveShape(face)) for key,item in by_uid.items()
                if item.IsOnLayer(face)]
        parents = {key:key for key,_shape in rows}
        def find(key):
            while parents[key] != key:
                parents[key] = parents[parents[key]];key = parents[key]
            return key
        for (left,a),(right,z) in itertools.combinations(rows,2):
            tick()
            if a.Collide(z,0):
                left,right = find(left),find(right)
                parents[max(left,right)] = min(left,right)
        islands = {}
        for key,_shape in rows:
            islands.setdefault(find(key),[]).append(key)
        for key,members in islands.items():
            island = ('island',face,key);graph.setdefault(island,{})
            for member in members:
                if member in root_nodes:
                    add_edge(root_nodes[member],island,length_mm=0.)
    return graph


def analyze(board, pair, *, p_route_vias, n_route_vias, timeout_s=10.):
    """Return counting authority only for a complete exact multi-terminal tree."""
    result = dict(schema=1, applicable=False, complete=False,
        exact_native_contact_tree=False, paths=[], errors=[],
        native_contact_graphs=[],
        limit_changed=False, whole_net_skew_convention_changed=False,
        current_or_fabrication_qualification=False, release_authority=False)
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10):
            raise ValueError('bounded_native_serial_path_budget_required')
        import cec_precision_route as precision
        plan = precision._multidrop_pair_plan(board,pair)
        if plan is None:
            result.update(complete=True,reason='not_a_native_multiterminal_pair')
            return result
        result['applicable'] = True
        if not 3 <= len(plan['ports']) <= 16:
            raise ValueError('bounded_native_multiterminal_inventory_required')
        deadline = time.monotonic()+float(timeout_s)
        results = []
        for member,route_vias in (('p',p_route_vias),('n',n_route_vias)):
            pads = {}
            for name,row in plan['ports'].items():
                choices = [pad for fp in board.GetFootprints()
                    if fp.GetReference() in row['physical_refs']
                    for pad in fp.Pads() if pad.GetNetname() == pair[member]
                    and pad.GetNumber() == row[member+'_pad']
                    and tuple(pad.GetPosition()) == tuple(round(v*1e6) for v in row[member])]
                if len(choices) != 1:
                    raise ValueError('unique_actual_native_terminal_pad_required')
                pads[name] = choices[0].m_Uuid.AsString()
            graph = _native_tree(board,pair[member],set(pads.values()),deadline=deadline)
            result['native_contact_graphs'].append(dict(member=member,**graph_evidence(board,graph)))
            paths = tree_paths(graph,{name:('pad',key) for name,key in pads.items()},
                {via.m_Uuid.AsString() for via in route_vias},deadline=deadline)
            results.append(paths)
        if [r['terminals'] for r in results[0]] != [r['terminals'] for r in results[1]]:
            raise ValueError('native_member_terminal_paths_disagree')
        result['paths'] = [dict(terminals=p['terminals'],p=p,n=n)
                           for p,n in zip(*results)]
        result.update(complete=True,exact_native_contact_tree=True,
            terminal_count=len(plan['ports']),
            max_route_transition_vias_p=max(r['route_transition_vias'] for r in results[0]),
            max_route_transition_vias_n=max(r['route_transition_vias'] for r in results[1]),
            reason='every_unique_native_terminal_path_received')
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
