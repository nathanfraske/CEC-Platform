"""Finite connected ordinary Source-chain replacement, not wider cut authority.

This distinct planar track-only tier owns at most sixteen serial Source
strokes. It cannot retire barrels, groups, power/pair/measurement copper or
move parts. The unchanged public ordinary receiver independently restores
every original boundary and native partition; whole-parent gates still apply.
"""
from pathlib import Path
import math,time
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_cell_row_rebuild as binding
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as craft

MAX_SOURCE_TRACKS=16
MAX_INCOMING_TRACKS=64

def _need(ok,reason):
    if not ok:raise ValueError(reason)

def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10,
        'bounded_connected_ordinary_lease_required')
    return time.monotonic()+seconds

def _left(deadline):
    remaining=deadline-time.monotonic()
    _need(remaining>0,'connected_ordinary_deadline')
    return min(10.,remaining)

def _net(net):
    _need(type(net)is str and 0<len(net)<=256 and not any(ord(c)<32 for c in net),
        'literal_connected_ordinary_net_required')

def _intersects(a,b,c,d):
    def cross(p,q,r):return(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):return cross(p,q,r)==0 and all(min(p[i],q[i])<=r[i]<=max(p[i],q[i])for i in(0,1))
    x,y,z,w=cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    return(x*y<0 and z*w<0)or on(a,b,c)or on(a,b,d)or on(c,d,a)or on(c,d,b)

def _chain(rows,deadline):
    adj={};edges={}
    for t in rows:
        _left(deadline);a,b=tuple(t.GetStart()),tuple(t.GetEnd());uid=force._uid(t)
        _need(a!=b and craft.is_canonical_stroke(a,b,tolerance_nm=0),
            'canonical_nonzero_connected_Source_strokes_required')
        edges[uid]=(a,b)
        for p in(a,b):adj.setdefault(p,[]).append(uid)
    ends=sorted(p for p,ids in adj.items()if len(ids)==1)
    _need(len(ends)==2 and len(adj)==len(rows)+1 and all(len(ids)<=2 for ids in adj.values()),
        'one_noncyclic_nonbranching_Source_chain_required')
    at=ends[0];used=set();ordered=[]
    while len(used)<len(rows):
        _left(deadline);nexts=[u for u in adj[at]if u not in used]
        _need(len(nexts)==1,'one_connected_Source_chain_required')
        uid=nexts[0];used.add(uid);a,b=edges[uid];ordered.append((uid,at,b if at==a else a));at=ordered[-1][2]
    _need(at==ends[1],'complete_connected_Source_chain_required')
    for i,(_,a,b)in enumerate(ordered):
        for _,c,d in ordered[i+2:]:
            _left(deadline)
            _need(not _intersects(a,b,c,d),'Source_chain_has_unrepresented_crossing_or_contact')
    return ordered,ends

def plan(board,source,*,board_hint,net,retired_track_uuids,allow_locked_track_uuids,timeout_s=10.):
    deadline=_deadline(timeout_s);_net(net)
    _need(type(board_hint)is str and bool(board_hint),'explicit_connected_ordinary_board_identity_required')
    source=Path(source).resolve(strict=True)
    _need(Path(board.GetFileName()).resolve()==source,'exact_saved_connected_ordinary_Source_required')
    epoch=force._code_identity();family=force._family(source,board_hint);native=binding._source_binding(board)
    digest=force._hash(source)
    cuts=ordinary._ids(retired_track_uuids,'connected_ordinary_Source_tracks',MAX_SOURCE_TRACKS)
    locks=ordinary._ids(allow_locked_track_uuids,'connected_ordinary_Source_locks',MAX_SOURCE_TRACKS)
    _need(cuts and locks<=cuts,'nonempty_connected_Source_cut_and_exact_locks_required')
    _need(net in ordinary.eligible_nets(board,source,board_hint),'Source_net_not_ordinary_connected_scope')
    all_tracks=list(board.GetTracks());tracks={force._uid(t):t for t in all_tracks}
    _need(len(tracks)==len(all_tracks)and cuts<=tracks.keys(),'unique_actual_connected_Source_track_inventory_required')
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    rows=[tracks[u]for u in sorted(cuts)]
    _need(all(t.GetClass()=='PCB_TRACK'and str(t.GetNetname())==net
        and force._uid(t)not in grouped and t.GetParentGroup()is None and not t.HasSolderMask()
        and 0<t.GetWidth()<500000 for t in rows),'only_ungrouped_unmasked_actual_ordinary_Source_tracks')
    _need(locks=={force._uid(t)for t in rows if t.IsLocked()},'exact_actual_connected_Source_lock_inventory_required')
    widths={t.GetWidth()for t in rows};faces={int(t.GetLayer())for t in rows}
    _need(len(widths)==len(faces)==1,'one_literal_Source_width_and_surface_chain_required')
    width=next(iter(widths));face=next(iter(faces))
    spec=fr._project_netclass_resolver(str(source),board=board)(net)
    value=(spec or {}).get('track_width')
    _need(type(value)in(int,float)and math.isfinite(value)and value>0
        and width>=max(int(board.GetDesignSettings().m_TrackMinWidth),math.ceil(value*1e6)),
        'unchanged_complete_Source_ordinary_width_required')
    ordered,ends=_chain(rows,deadline)
    _need(epoch==force._code_identity()and family==force._family(source,board_hint)
        and native==binding._source_binding(board),'connected_ordinary_Source_or_code_changed')
    _left(deadline)
    return dict(schema=1,scope='finite_connected_planar_ordinary_Source_chain',complete=True,
        source=str(source),source_sha256=digest,board_hint=board_hint,net=net,
        retired_track_uuids=sorted(cuts),allow_locked_track_uuids=sorted(locks),
        ordered_source_track_uuids=[u for u,_,_ in ordered],source_endpoint_nm=[list(p)for p in ends],
        width_nm=width,layer_id=face,maximum_source_tracks=MAX_SOURCE_TRACKS,
        maximum_incoming_tracks=MAX_INCOMING_TRACKS,source_native_binding=native,
        power_authority=False,placement_authority=False,barrel_authority=False,release_authority=False)

def receive(source,candidate,*,board_hint,net,retired_track_uuids,allow_locked_track_uuids,timeout_s=10.):
    deadline=_deadline(timeout_s)
    r=dict(ok=False,complete=False,errors=[],scope='saved_connected_ordinary_Source_reflow',
        whole_original_parent_gates_required=True,power_authority=False,placement_authority=False,
        barrel_authority=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        _need(source!=candidate,'distinct_connected_ordinary_saved_boards_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(candidate))
        q=plan(parent,source,board_hint=board_hint,net=net,retired_track_uuids=retired_track_uuids,
            allow_locked_track_uuids=allow_locked_track_uuids,timeout_s=_left(deadline))
        old=additive._nodes(source)[1];new=additive._nodes(candidate)[1]
        _need(old.keys()-new.keys()==set(q['retired_track_uuids']),'exact_connected_Source_retirement_required')
        incoming=new.keys()-old.keys()
        rows=[t for t in child.GetTracks()if force._uid(t)in incoming]
        _need(1<=len(rows)<=MAX_INCOMING_TRACKS and {force._uid(t)for t in rows}==incoming,
            'bounded_track_only_connected_ordinary_additions_required')
        _need(all(t.GetClass()=='PCB_TRACK'and str(t.GetNetname())==net
            and t.GetWidth()==q['width_nm']and int(t.GetLayer())==q['layer_id']
            and not t.HasSolderMask()and craft.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)
            for t in rows),'literal_same_Source_net_width_face_track_replacement_required')
        # No new groups or modified membership; route-lock ownership never
        # confers annotation/factory-group transport permission.
        for uid,node in old.items():
            if node[0]=='group':
                _need(uid in new and ordinary.sexpr._freeze(node)==ordinary.sexpr._freeze(new[uid]),
                    'connected_ordinary_Source_group_changed')
        proof=ordinary.receive(source,candidate,board_hint=board_hint,
            retired_track_uuids=q['retired_track_uuids'],allow_locked_track_uuids=q['allow_locked_track_uuids'],
            max_retired_tracks=MAX_SOURCE_TRACKS,timeout_s=_left(deadline))
        r['independent_ordinary_receiving']=proof
        _need(proof.get('ok')is True and proof.get('complete')is True,'connected_ordinary_independent_saved_replay_refused')
        _need(epoch==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)],
            'connected_ordinary_Source_candidate_or_code_changed')
        _left(deadline)
        r.update(ok=True,complete=True,source_plan=q,new_track_uuids=sorted(incoming),
            all_original_native_boundaries_and_partitions_received=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
