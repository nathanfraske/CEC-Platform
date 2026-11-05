"""Finite source-derived ordinary-chain construction scope.

Locks protect copper by default. An explicit exact UUID scope may repack a
previously locked *ordinary* chain, but cannot turn a power/pair/ground net,
group, branch or missing source object into ordinary permission. This is a
construction proposal; the independent saved native delta/partition receiver
must verify the same locked scope against the unchanged source.
"""
from collections import Counter, defaultdict


def migration_endpoint_faces(body_layers,endpoint_layers,*,source_layer):
    """Separate source-typed landing faces from the permitted route body.

    The source face may be used between the two existing plated endpoints
    without being selected as an endpoint's migrated landing face. This
    helper supplies no new layer permission: the caller must first derive
    permitted body faces from the actual ordinary net/project policy.
    """
    def valid(values):
        return (type(values) in (list,tuple) and 1<=len(values)<=4
            and len(set(values))==len(values)
            and all(type(n) is int and 0<=n<64 for n in values))
    if not valid(body_layers) or type(source_layer) is not int or not 0<=source_layer<64:
        raise ValueError('bounded_permitted_ordinary_body_faces_required')
    requested=body_layers if endpoint_layers is None else endpoint_layers
    if not valid(requested) or not set(requested)<=set(body_layers) or source_layer in requested:
        raise ValueError('distinct_existing_barrel_landing_faces_must_be_in_body_scope')
    return sorted(requested)


def _ids(values, label):
    if (not isinstance(values, (list, tuple, set, frozenset)) or len(values)>32
            or any(type(uid) is not str or not uid for uid in values)
            or len(values)!=len(set(values))):
        raise ValueError('finite_unique_'+label+'_required')
    return set(values)


def chain(rows, requested, eligible_nets, *, allow_locked_track_uuids=()):
    requested_ids=_ids(requested,'ordinary_chain')
    allowed=_ids(allow_locked_track_uuids,'ordinary_locked_scope')
    if not requested_ids or not allowed<=requested_ids:
        raise ValueError('exact_nonempty_ordinary_chain_and_locked_subset_required')
    if (not isinstance(rows,(list,tuple)) or not 1<=len(rows)<=16384
            or any(type(row) is not dict or type(row.get('uuid')) is not str
                or not row['uuid'] for row in rows)):
        raise ValueError('bounded_actual_ordinary_chain_inventory_required')
    lookup={row['uuid']:row for row in rows}
    if len(lookup)!=len(rows) or not requested_ids<=lookup.keys():
        raise ValueError('ambiguous_or_stale_native_ordinary_chain_inventory')
    selected=[lookup[uid] for uid in sorted(requested_ids)]
    if any(lookup[uid].get('locked') is not True for uid in allowed):
        raise ValueError('ordinary_locked_scope_must_name_actual_locked_source_tracks')
    nets={row.get('net') for row in selected}
    layers={row.get('layer') for row in selected}
    widths={row.get('width_nm') for row in selected}
    if (len(nets)!=1 or any(type(net) is not str or not net for net in nets)
            or not nets<=set(eligible_nets) or len(layers)!=1 or len(widths)!=1
            or any(type(layer) is not int for layer in layers)
            or any(type(width) is not int or not 0<width<=350000 for width in widths)
            or any(row.get('kind')!='PCB_TRACK' or row.get('grouped') is not False
                or type(row.get('locked')) is not bool
                or row['locked'] and row['uuid'] not in allowed for row in selected)):
        raise ValueError('source_typed_ungrouped_uniform_ordinary_chain_required')
    degree,adjacency=Counter(),defaultdict(set)
    for row in selected:
        points=[]
        for name in ('start_nm','end_nm'):
            value=row.get(name)
            if (not isinstance(value,(list,tuple)) or len(value)!=2
                    or any(type(v) is not int or abs(v)>2000000000 for v in value)):
                raise ValueError('actual_native_integer_ordinary_chain_endpoints_required')
            points.append(tuple(value))
        left,right=points
        if left==right:raise ValueError('nonzero_native_ordinary_chain_required')
        degree[left]+=1;degree[right]+=1
        adjacency[left].add(right);adjacency[right].add(left)
    ends=sorted(point for point,value in degree.items() if value==1)
    if len(ends)!=2 or any(value not in (1,2) for value in degree.values()):
        raise ValueError('one_linear_ordinary_chain_required')
    seen,pending=set(),[ends[0]]
    while pending:
        point=pending.pop()
        if point not in seen:seen.add(point);pending.extend(adjacency[point]-seen)
    if len(seen)!=len(degree):raise ValueError('disconnected_native_ordinary_chain_refused')
    return dict(schema=1,retired_track_uuids=sorted(requested_ids),net=next(iter(nets)),
        source_layer=next(iter(layers)),source_width_nm=next(iter(widths)),
        endpoints_nm=[list(point) for point in ends],locked_scope_used=sorted(allowed),
        native_saved_boundary_and_partition_receiving_required=True,
        current_or_pair_or_ground_authority=False,release_authority=False)


def boundary_attachment_pairs(scope, terminal_migration=None):
    """Copy the exact typed source boundaries after temporary planning work.

    Reservation loops and spatial proposals are not source endpoints. Never
    accept their local variables as attachment authority. Existing plated
    migration may change eligible faces, but must name these same axes in the
    same order. This grants no new connectivity, current, or cut authority.
    """
    if (type(scope) is not dict or scope.get('schema') != 1
            or type(scope.get('source_layer')) is not int
            or not 0 <= scope['source_layer'] < 64
            or type(scope.get('endpoints_nm')) is not list
            or len(scope['endpoints_nm']) != 2
            or any(type(point) is not list or len(point) != 2
                or any(type(v) is not int or abs(v) > 2_000_000_000 for v in point)
                for point in scope['endpoints_nm'])
            or scope['endpoints_nm'][0] == scope['endpoints_nm'][1]
            or scope.get('native_saved_boundary_and_partition_receiving_required') is not True
            or scope.get('current_or_pair_or_ground_authority') is not False
            or scope.get('release_authority') is not False):
        raise ValueError('exact_typed_ordinary_source_boundary_required')
    points = scope['endpoints_nm']
    faces = [[scope['source_layer']], [scope['source_layer']]]
    if terminal_migration is not None:
        rows = terminal_migration.get('endpoints') if type(terminal_migration) is dict else None
        if (type(rows) is not list or len(rows) != 2
                or any(type(row) is not dict or row.get('at_nm') != point
                    or type(row.get('target_layers')) is not list
                    or not 1 <= len(row['target_layers']) <= 4
                    or len(row['target_layers']) != len(set(row['target_layers']))
                    or any(type(face) is not int or not 0 <= face < 64
                        for face in row['target_layers'])
                    for row, point in zip(rows, points))):
            raise ValueError('migration_must_preserve_exact_source_boundary_axes')
        faces = [row['target_layers'] for row in rows]
    return [(dict(at_nm=list(points[0]), layers=list(faces[0])),
             dict(at_nm=list(points[1]), layers=list(faces[1])))]


def multiface_chain(rows, via_rows, requested, requested_vias, eligible_nets, *,
                    allow_locked_track_uuids=(), allow_locked_via_uuids=()):
    """Exact linear ordinary chain through exclusively owned layer jumps.

    Layer coordinates are separate vertices until a positively selected
    through-barrel joins them. Mere XY coincidence never supplies continuity.
    Native all-contact barrel ownership, boundary restoration and saved delta
    receiving are mandatory independently; this pure topology grants no cut.
    """
    ids = _ids(requested, 'multiface_tracks')
    vias = _ids(requested_vias, 'multiface_barrels')
    locks = _ids(allow_locked_track_uuids, 'multiface_track_locks')
    via_locks = _ids(allow_locked_via_uuids, 'multiface_barrel_locks')
    if not ids or not 1 <= len(vias) <= 4 or not locks <= ids or not via_locks <= vias:
        raise ValueError('bounded_exact_multiface_track_and_barrel_scope_required')
    if (not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 16384
            or not isinstance(via_rows, (list, tuple)) or not 1 <= len(via_rows) <= 16384):
        raise ValueError('bounded_actual_multiface_native_inventory_required')
    for inventory in (rows, via_rows):
        if (any(type(r) is not dict or type(r.get('uuid')) is not str
                or not r['uuid'] for r in inventory)
                or len({r['uuid'] for r in inventory}) != len(inventory)):
            raise ValueError('unique_actual_multiface_native_inventory_required')
    tracks = {r['uuid']:r for r in rows}; barrels = {r['uuid']:r for r in via_rows}
    if not ids <= tracks.keys() or not vias <= barrels.keys() or tracks.keys() & barrels.keys():
        raise ValueError('stale_or_ambiguous_multiface_source_scope')
    selected = [tracks[u] for u in sorted(ids)]
    nets = {r.get('net') for r in selected}; widths = {r.get('width_nm') for r in selected}
    if (len(nets) != 1 or not nets <= set(eligible_nets) or len(widths) != 1
            or any(type(n) is not str or not n for n in nets)
            or any(type(w) is not int or not 0 < w <= 350000 for w in widths)):
        raise ValueError('uniform_positive_ordinary_multiface_source_required')
    def point(v):
        if (type(v) not in (list, tuple) or len(v) != 2
                or any(type(x) is not int or abs(x) > 2000000000 for x in v)):
            raise ValueError('literal_integer_multiface_source_point_required')
        return tuple(v)
    for r in selected:
        if (r.get('kind') != 'PCB_TRACK' or r.get('grouped') is not False
                or type(r.get('locked')) is not bool
                or type(r.get('layer')) is not int or not 0 <= r['layer'] < 64
                or r['locked'] and r['uuid'] not in locks
                or r['uuid'] in locks and not r['locked']):
            raise ValueError('explicit_ungrouped_multiface_track_scope_required')
        if point(r['start_nm']) == point(r['end_nm']):
            raise ValueError('nonzero_multiface_source_track_required')
    axes = {}; contacts = defaultdict(list)
    for uid in sorted(vias):
        r = barrels[uid]; at = point(r.get('at_nm'))
        if (r.get('kind') != 'PCB_VIA' or r.get('net') not in nets
                or r.get('through') is not True or r.get('grouped') is not False
                or type(r.get('locked')) is not bool
                or r['locked'] and uid not in via_locks
                or uid in via_locks and not r['locked']
                or at in axes):
            raise ValueError('unique_explicit_ordinary_multiface_barrel_axis_required')
        axes[at] = uid
    degree = Counter(); adjacency = defaultdict(set); source_nodes = {}
    for r in selected:
        ends = []
        for key in ('start_nm', 'end_nm'):
            at = point(r[key]); uid = axes.get(at)
            node = ('via', uid) if uid else ('face', r['layer'], *at)
            if uid: contacts[uid].append((r['uuid'], r['layer']))
            ends.append(node); source_nodes[node] = dict(at_nm=list(at), layers=[r['layer']])
        left, right = ends
        degree[left] += 1; degree[right] += 1
        adjacency[left].add(right); adjacency[right].add(left)
    if any(len(contacts[u]) != 2 or len({face for _,face in contacts[u]}) != 2 for u in vias):
        raise ValueError('each_selected_barrel_requires_exact_two_distinct_face_departures')
    terminals = sorted(n for n,d in degree.items() if d == 1)
    if (len(terminals) != 2 or any(n[0] != 'face' for n in terminals)
            or any(d not in (1,2) for d in degree.values())
            or len(selected) != len(degree)-1):
        raise ValueError('one_branch_free_acyclic_multiface_chain_required')
    seen = set(); pending = [terminals[0]]
    while pending:
        n = pending.pop()
        if n not in seen: seen.add(n); pending.extend(adjacency[n]-seen)
    if seen != set(degree): raise ValueError('disconnected_multiface_source_chain')
    return dict(schema=1, net=next(iter(nets)), source_width_nm=next(iter(widths)),
        retired_track_uuids=sorted(ids), retired_via_uuids=sorted(vias),
        locked_scope_used=sorted(locks), locked_via_scope_used=sorted(via_locks),
        endpoints=[source_nodes[n] for n in terminals],
        source_layer_ids=sorted({r['layer'] for r in selected}),
        native_exclusive_barrel_and_saved_boundary_receiving_required=True,
        current_or_pair_or_ground_authority=False, release_authority=False)
