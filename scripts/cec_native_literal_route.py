"""Validate an agent-selected native planar path without changing authority.

The enclosing constructor supplies the actual source-owned branch row and
native clearance callback. An explicit path cannot move its ports, change its
net, layer or width, add a barrel, or skip independent whole-source receiving.
No board, reference or coordinate exception is encoded here.
"""
import math
import cec_route_quality as quality


def plan(source_row,request,*,native_clear):
    keys={'uid','net','layer','width_nm','points_nm'}
    if (type(request) is not dict or set(request)!=keys or not callable(native_clear)
            or any(request[k]!=source_row[k] for k in ('uid','net','layer'))
            or type(request['uid']) is not str or not request['uid']
            or type(request['net']) is not str or not request['net']
            or type(request['layer']) is not int or type(request['width_nm']) is not int
            or not 0<request['width_nm']==source_row['width']<=10000000):
        raise ValueError('literal_native_route_must_bind_actual_source_identity_net_layer_width')
    points=request['points_nm']
    if (type(points) is not list or not 2<=len(points)<=33
            or any(type(p) is not list or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)
            or len(set(map(tuple,points)))!=len(points)
            or points[0]!=list(source_row['start']) or points[-1]!=list(source_row['end'])):
        raise ValueError('bounded_literal_native_route_must_keep_both_actual_ports')
    legs=list(zip(points,points[1:]))
    if (any(not quality.is_canonical_stroke(tuple(s),tuple(t),tolerance_nm=0) for s,t in legs)
            or sum(math.dist(s,t) for s,t in legs)>150000000):
        raise ValueError('bounded_nonempty_canonical_native_route_required')
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        if any(max(a[k],b[k])<min(c[k],d[k]) or max(c[k],d[k])<min(a[k],b[k]) for k in (0,1)):return False
        return orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0
    for i,(s,t) in enumerate(legs):
        if i and orient(points[i-1],s,t)==0 and sum((s[k]-points[i-1][k])*(t[k]-s[k]) for k in (0,1))<0:
            raise ValueError('literal_native_route_backtracking_refused')
        if any(intersects(s,t,u,v) for u,v in legs[:max(0,i-1)]):
            raise ValueError('literal_native_route_self_intersection_refused')
        if native_clear(tuple(s),tuple(t),request['width_nm'],request['layer']) is not True:
            raise ValueError('literal_native_route_native_clearance_refused:'+str(dict(leg=i,start_nm=s,end_nm=t)))
    return dict(schema=1,source_track_uuid=request['uid'],net=request['net'],layer=request['layer'],
        width_nm=request['width_nm'],points_nm=points,leg_count=len(legs),
        actual_source_ports_width_and_layer_preserved=True,native_clearance_callback_passed=True,
        new_barrels=0,whole_source_current_field_drc_and_connectivity_receiving_required=True,
        routing_admitted=False,current_qualified=False,release_authority=False)
