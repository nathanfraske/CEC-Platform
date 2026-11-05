"""Bounded agent waypoints for the existing exact native multilayer search.

Guides select effort, not permission. Every complete leg uses the same native
guards and actual layer widths. No partial route is returned and nothing is
added to the board. Saved whole-source receiving remains the caller's duty.
"""
import math
import time
import pcbnew
import cec_fr as fr


def plan(board,start,end,net_code,layers,clearance_nm,edge_guard,*,width_for_layer,
         start_layers,end_layers,waypoints,drill,dia,planar_guard=None,
         max_vias=2,max_length_nm=100000000,max_expanded_states=400000,
         grid_mm=.2,diagnostics=None):
    if (type(waypoints) is not list or not 1<=len(waypoints)<=8
            or type(max_vias) is not int or not 0<=max_vias<=4
            or type(max_length_nm) is not int or not 0<max_length_nm<=160000000
            or not callable(width_for_layer) or not callable(edge_guard)):
        raise ValueError('bounded_explicit_native_route_guides_required')
    points=[]
    for row in waypoints:
        if (type(row) is not dict or set(row)!={'at_nm','layer'}
                or type(row['at_nm']) is not list or len(row['at_nm'])!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in row['at_nm'])
                or type(row['layer']) is not int or row['layer'] not in layers):
            raise ValueError('exact_permitted_native_waypoint_required')
        points.append((pcbnew.VECTOR2I(*row['at_nm']),[row['layer']]))
    targets=[*points,(end,list(end_layers))]
    origin=start;faces=list(start_layers);ops=[];used_vias=0;length=0
    details=diagnostics if diagnostics is not None else {}
    details.update(scope='bounded_native_agent_guided_complete_route',legs=[],
        complete_route=False,partial_geometry_returned=False,routing_admitted=False,release_authority=False)
    for target,target_faces in targets:
        if tuple(origin)==tuple(target) and set(faces)&set(target_faces):
            raise ValueError('nonempty_native_guided_leg_required')
        leg={}
        single=len(layers)==1
        found=fr._multilayer_maze_lastmile_ops(board,origin,target,net_code,layers,clearance_nm,
            edge_guard,width_for_layer=width_for_layer,start_layers=faces,end_layers=target_faces,
            drill=drill,dia=dia,max_vias=0 if single else max_vias-used_vias,
            grid_mm=grid_mm,foreign_cache={},deadline_monotonic=time.monotonic()+9.5,
            max_length_nm=max_length_nm-length,diagnostics=leg,heuristic_weight=3.,
            canonical_turns_only=True,obstacle_channel_axes=True,native_board_envelope=True,
            max_expanded_states=max_expanded_states,allow_single_layer=single,
            planar_guard=planar_guard,neutral_state_dominance=True,field_state_dominance=True)
        details['legs'].append(dict(start_nm=list(origin),end_nm=list(target),
            start_layers=faces,end_layers=target_faces,found=bool(found),search=leg))
        if not found:
            details.update(stop='bounded_guided_leg_refused',completed_legs=len(details['legs'])-1)
            return None
        used_vias+=sum(op[0]=='via' for op in found)
        length+=sum(math.dist(tuple(op[1]),tuple(op[2])) for op in found if op[0]=='trk')
        if used_vias>max_vias or length>max_length_nm:
            raise ValueError('complete_guided_route_exceeded_whole_budget')
        ops.extend(found);origin=target;faces=target_faces
    details.update(complete_route=True,stop='found',new_vias=used_vias,length_nm=length)
    return ops
