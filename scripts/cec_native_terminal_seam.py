"""Reinforce nominally touching duplicate terminals, never extend their copper.

Two same-footprint RECT SMD pads can touch exactly at an edge. KiCad then
counts them as connected, but independently guarded physical pad envelopes
need not share definite material. An explicit, factory-minimum short track
across that seam makes the intended connection unambiguous. This compiler
only proposes copper contained in the original two-pad envelope. Current,
pair, exact saved delta and full native receiving remain separate obligations.
"""
import math,time
import pcbnew
from shapely.geometry import box,LineString
from shapely.ops import unary_union
import cec_force_current as force
import cec_fr as fr
import cec_precision_route as precision
import cec_route_dimensions as dimensions
from cec_cell_row_rebuild import _source_binding


def _rectangle(pad,layer):
    angle=pad.GetOrientationDegrees()
    size=pad.GetSize(layer);offset=pad.GetOffset(layer);delta=pad.GetDelta(layer)
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or pad.GetShape(layer)!=pcbnew.PAD_SHAPE_RECT
            or not pad.IsOnLayer(layer) or not pad.FlashLayer(layer)
            or not math.isfinite(angle) or angle%90
            or offset.x or offset.y or delta.x or delta.y
            or pad.ShapePos(layer)!=pad.GetPosition()
            or min(size.x,size.y)<=0):
        raise ValueError('exact_cardinal_unmodified_rectangular_SMD_terminal_required')
    sx,sy=int(size.x),int(size.y)
    if angle%180:sx,sy=sy,sx
    x,y=map(int,pad.GetPosition());hx,hy=sx//2,sy//2
    return box(x-hx,y-hy,x+hx,y+hy)


def plan(board,source,*,board_hint,pad_pairs,timeout_s=2.,max_span_nm=500000):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_span_nm) is not int
            or not 1<=max_span_nm<=500000 or type(pad_pairs) not in (list,tuple)
            or not 1<=len(pad_pairs)<=16
            or any(type(row) not in (list,tuple) or len(row)!=2
                or any(type(u) is not str or not u for u in row) or row[0]==row[1]
                for row in pad_pairs)
            or len({tuple(sorted(row)) for row in pad_pairs})!=len(pad_pairs)
            or type(board_hint) is not str or not board_hint):
        raise ValueError('bounded_explicit_native_terminal_seam_scope_required')
    deadline=time.monotonic()+timeout_s
    pairs=precision.derive_coupled_pairs(str(source),board=board)
    excluded={q[k] for q in pairs for k in ('p','n')}
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    if len(pads)>16384:raise ValueError('native_terminal_seam_inventory_bound')
    resolver=dimensions.project_resolver(source,board=board)
    width=math.ceil(dimensions.board_limits(board)['track_width']*1e6)
    if width<=0:raise ValueError('positive_unchanged_factory_track_floor_required')
    rows=[]
    for supplied in pad_pairs:
        if time.monotonic()>=deadline:raise ValueError('native_terminal_seam_deadline')
        if any(u not in pads for u in supplied):raise ValueError('source_terminal_identity_missing')
        left,right=[pads[u] for u in supplied];owner=left.GetParentFootprint()
        net=str(left.GetNetname())
        if (force._uid(owner)!=force._uid(right.GetParentFootprint())
                or left.GetNetCode()<=0 or left.GetNetCode()!=right.GetNetCode()
                or net in excluded or owner.IsDNP()
                or str(left.GetNumber())==str(right.GetNumber())):
            raise ValueError('two_distinct_populated_same_owner_nonpaired_terminals_required')
        layers=set(map(int,left.GetLayerSet().CuStack()))&set(map(int,right.GetLayerSet().CuStack()))
        if len(layers)!=1 or next(iter(layers)) not in (pcbnew.F_Cu,pcbnew.B_Cu):
            raise ValueError('one_actual_outer_terminal_face_required')
        layer=next(iter(layers));first,last=map(tuple,(left.GetPosition(),right.GetPosition()))
        dx,dy=last[0]-first[0],last[1]-first[1]
        if (not (bool(dx)^bool(dy)) or math.dist(first,last)>max_span_nm):
            raise ValueError('bounded_cardinal_adjacent_terminal_seam_required')
        a,b=_rectangle(left,layer),_rectangle(right,layer)
        # No space filling or shorting of remote same-net islands: literal
        # native copper must already touch, and the exact rectangular cores
        # must meet at one edge with positive overlap in the other direction.
        contact=a.intersection(b)
        if (contact.is_empty or contact.area!=0 or contact.length<=0
                or not left.GetEffectiveShape(layer).Collide(right.GetEffectiveShape(layer),0)):
            raise ValueError('actual_nominal_edge_only_terminal_contact_required')
        envelope=unary_union([a,b])
        capsule=LineString([first,last]).buffer(width/2+2.,resolution=64)
        if not envelope.covers(capsule):
            raise ValueError('factory_minimum_seam_copper_outside_original_pad_envelope')
        spec=resolver(net) or {};clearance=max(
            int(board.GetDesignSettings().m_MinClearance),math.ceil(float(spec.get('clearance') or 0)*1e6))
        if (not fr._edge_leg_clear(board,left.GetPosition(),right.GetPosition(),width//2+clearance)
                or not fr._tap_foreign_clear(board,left.GetPosition(),right.GetPosition(),width,
                    layer,clearance,{left.GetNetCode()},foreign_cache={})):
            raise ValueError('native_terminal_seam_foreign_copper_hole_or_edge_blocked')
        rows.append(dict(pad_uuids=list(supplied),owner_uuid=force._uid(owner),net=net,
            source_pad_lock_states=[bool(p.IsLocked()) for p in (left,right)],
            source_owner_locked=bool(owner.IsLocked()),
            layer=int(layer),start_nm=list(first),end_nm=list(last),width_nm=width,
            clearance_nm=clearance,full_class_width_nm=math.ceil(max(
                dimensions.board_limits(board)['track_width'],float(spec.get('track_width') or 0),
                float((spec.get('track_width_by_layer_mm') or {}).get(board.GetLayerName(layer)) or 0))*1e6),
            nominal_source_pad_envelope_contains_new_copper=True,
            bridge_length_mm=math.dist(first,last)/1e6))
    if time.monotonic()>=deadline:raise ValueError('native_terminal_seam_deadline')
    return dict(schema=1,source_binding=_source_binding(board),board_hint=board_hint,
        pad_pairs=[list(q) for q in pad_pairs],max_span_nm=max_span_nm,rows=rows,
        source_geometry_extended=False,source_current_or_pair_contract_changed=False,
        release_authority=False,current_qualified=False,independent_saved_receiving_required=True)


def construct(board,source,proposal):
    fresh=plan(board,source,board_hint=proposal['board_hint'],pad_pairs=proposal['pad_pairs'],
        max_span_nm=proposal['max_span_nm'])
    if fresh!=proposal:raise ValueError('stale_native_terminal_seam_proposal')
    made=[]
    try:
        for row in fresh['rows']:
            track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
            track.SetEnd(pcbnew.VECTOR2I(*row['end_nm']));track.SetWidth(row['width_nm'])
            track.SetLayer(row['layer']);track.SetNetCode(board.GetNetcodeFromNetname(row['net']))
            track.SetLocked(True);board.Add(track);made.append(track)
        # Qualify the entire batch before adding ANY ownership memberships.
        # A refused incoming component must not leave a changed old group.
        for row,track in zip(fresh['rows'],made):
            if row['width_nm']>=row['full_class_width_nm']:continue
            qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,[track],
                row['full_class_width_nm'],required_clearance=row['clearance_nm'])
            if rejected or {force._uid(t) for t in qualified}!={force._uid(track)}:
                raise ValueError('native_terminal_seam_not_independently_pad_local')
    except Exception:
        from cec_native_items import discard_items
        discard_items(board,made)
        raise
    for row,track in zip(fresh['rows'],made):
        fr.group_endpoint_neckdowns(board,[track],row['full_class_width_nm'],
            required_clearance=row['clearance_nm'])
    return [force._uid(t) for t in made]


def discover(board,source,*,board_hint,timeout_s=10.):
    """Read-only automatic seam inventory; no source-specific identifiers.

    Existing definite connections are not repaired. Only the specific lower
    material-disconnection result permits a nominal seam proposal; an unknown
    drill/fill/graphic or an exhausted inventory never becomes permission.
    """
    from itertools import combinations
    import cec_generated_pickup_retirement as physical
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):raise ValueError('bounded_native_seam_discovery_required')
    deadline=time.monotonic()+timeout_s;before=_source_binding(board)
    proposed=[];refused=[];checked=0;graph_status={};complete=True
    for owner in sorted(board.GetFootprints(),key=force._uid):
        if owner.IsDNP():continue
        pads=sorted(owner.Pads(),key=force._uid)
        if len(pads)>1024:raise ValueError('native_seam_owner_inventory_bound')
        for left,right in combinations(pads,2):
            checked+=1
            if checked>65536 or time.monotonic()>=deadline:
                complete=False;break
            if (left.GetNetCode()<=0 or left.GetNetCode()!=right.GetNetCode()
                    or left.GetNumber()==right.GetNumber()
                    or math.dist(tuple(left.GetPosition()),tuple(right.GetPosition()))>500000):continue
            ids=[force._uid(left),force._uid(right)]
            try:
                proposal=plan(board,source,board_hint=board_hint,pad_pairs=[ids],
                    timeout_s=min(2.,max(.001,deadline-time.monotonic())))
            except ValueError:continue
            net=str(left.GetNetname())
            if net not in graph_status:
                try:
                    physical._scoped_terminal_graph(board,net,
                        timeout_s=min(2.,max(.001,deadline-time.monotonic())))
                    graph_status[net]='already_definitely_connected'
                except Exception as exc:
                    graph_status[net]=str(exc)
            if graph_status[net]=='source_pickup_actual_drilled_terminal_material_disconnected':
                proposed.append(ids)
                if len(proposed)>16:complete=False;break
            elif graph_status[net]!='already_definitely_connected':
                refused.append(dict(pad_uuids=ids,reason=graph_status[net]))
        if not complete:break
    if before!=_source_binding(board):raise ValueError('native_seam_discovery_source_changed')
    return dict(schema=1,complete=complete,checked_owner_pad_pairs=checked,
        pad_pairs=proposed,refusals=refused,physical_net_status=graph_status,
        source_binding=before,source_mutated=False,construction_authorized=False,
        release_authority=False)
