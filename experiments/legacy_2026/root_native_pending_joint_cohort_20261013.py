"""Coalesce exact pending free joints before PRIVATE transactional rerouting.

A maze cannot start inside a newly obstructed joint. Two already-requested
equal-width edges can be reconstructed together only where no native pad,
barrel, third conductor, width or group boundary owns their shared joint.
This is a bounded construction scope, never retirement/current permission.
"""
import math
import time
import pcbnew
import cec_force_current as force


def coalesce(board, rows, *, timeout_s=3., maximum_members=8, maximum_cut_nm=48000000,
             maximum_input_edges=64):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(maximum_members) is not int or not 1<=maximum_members<=8
            or type(maximum_cut_nm) is not int or not 0<maximum_cut_nm<=48000000
            or type(maximum_input_edges) is not int or not 1<=maximum_input_edges<=128
            or type(rows) not in (list,tuple) or not 1<=len(rows)<=maximum_input_edges):
        raise ValueError('bounded_explicit_pending_joint_cohort_required')
    deadline=time.monotonic()+timeout_s
    items={force._uid(t):t for t in board.GetTracks()}
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(items)>8192 or len(pads)>4096 or len({r['uid'] for r in rows})!=len(rows):
        raise ValueError('bounded_unique_native_pending_joint_inventory_required')
    work=[]
    for row in rows:
        uid=row['uid'];t=items.get(uid)
        if (t is None or t.GetClass()!='PCB_TRACK' or row['item']!=t
                or row['net']!=str(t.GetNetname()) or row['code']!=int(t.GetNetCode())
                or row['layer']!=int(t.GetLayer()) or row['width']!=t.GetWidth()
                or row['locked']!=t.IsLocked()
                or {tuple(row['start']),tuple(row['end'])}!={tuple(t.GetStart()),tuple(t.GetEnd())}):
            raise ValueError('pending_joint_row_must_name_the_literal_actual_native_edge')
        work.append(dict(row,pending_member_uuids=[uid]))
    joins=[];refusals=[]
    def signature(row):
        return (row['net'],row['code'],row['layer'],row['width'],row['locked'],
                tuple(sorted(force._uid(g) for g in row['groups'])))
    def anchored(row):
        return row['typed_anchor_retained'] or any(g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|')
            for g in row['groups'])
    while True:
        joined=False
        for i,left in enumerate(work):
            for j in range(i+1,len(work)):
                if time.monotonic()>=deadline:raise ValueError('pending_joint_cohort_deadline')
                right=work[j];common={tuple(left[k]) for k in ('start','end')}&{tuple(right[k]) for k in ('start','end')}
                if len(common)!=1 or signature(left)!=signature(right) or anchored(left) or anchored(right):continue
                at=next(iter(common));members=set(left['pending_member_uuids'])|set(right['pending_member_uuids'])
                if (len(members)>maximum_members or sum(items[u].GetLength() for u in members)>maximum_cut_nm
                        or any(items[u].GetLength()>32000000 for u in members)):
                    continue
                cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),left['width'])
                def touched(item):
                    return (item.GetNetCode()==left['code'] and item.IsOnLayer(left['layer'])
                        and item.GetEffectiveShape(left['layer']).Collide(cap,0))
                terminals=[force._uid(p) for p in pads if touched(p)]
                barrels=[u for u,t in items.items() if t.GetClass()=='PCB_VIA' and touched(t)]
                outsiders=[u for u,t in items.items() if u not in members and t.GetClass()=='PCB_TRACK' and touched(t)]
                if terminals or barrels or outsiders:
                    refusals.append(dict(at_nm=list(at),members=sorted(members),
                        native_pad_uuids=terminals,native_barrel_uuids=barrels,other_native_conductor_uuids=outsiders))
                    continue
                ports=sorted(({tuple(left[k]) for k in ('start','end')}|
                    {tuple(right[k]) for k in ('start','end')})-{at})
                if len(ports)!=2:continue
                primary=min((left,right),key=lambda r:r['uid']);merged=dict(primary,
                    start=ports[0],end=ports[1],pending_member_uuids=sorted(members),
                    pending_cohort_retired_uuids=sorted(members-{primary['uid']}))
                joins.append(dict(at_nm=list(at),member_uuids=sorted(members),
                    external_ports_nm=[list(p) for p in ports],width_nm=left['width'],
                    net=left['net'],layer=int(left['layer']),actual_free_degree_two_joint=True))
                work=[r for k,r in enumerate(work) if k not in (i,j)]+[merged]
                joined=True;break
            if joined:break
        if not joined:break
    if time.monotonic()>=deadline:raise ValueError('pending_joint_cohort_deadline')
    retired=sorted(u for row in work for u in row.get('pending_cohort_retired_uuids',[]))
    return work,retired,dict(schema=1,joins=joins,anchored_joints_not_consumed=refusals,
        native_geometry_mutated=False,exact_requested_members_only=True,
        native_zone_contacts_and_saved_partitions_still_require_receiving=True,
        automatic_retirement_authorized=False,current_qualified=False,release_authority=False)
