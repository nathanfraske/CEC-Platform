"""Recognize complete bounded pending chains despite overlapping end caps.

Finite copper remains authoritative. Endpoint topology merely discovers an
entire transaction; every external body/pad/barrel contact must still be at
its two retained ports. No source cut, current or release authority follows.
"""
import math
import time
import pcbnew
import cec_force_current as force


def plan(board, rows, *, timeout_s=3., maximum_members=16, maximum_cut_nm=48000000,
         maximum_input_edges=64):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or
            not 0 < timeout_s <= 10 or type(maximum_members) is not int or
            not 2 <= maximum_members <= 16 or type(maximum_cut_nm) is not int or
            not 0 < maximum_cut_nm <= 48000000 or type(maximum_input_edges) is not int
            or not 1<=maximum_input_edges<=128):
        raise ValueError('bounded_whole_pending_linear_cohort_required')
    if type(rows) not in (list,tuple) or not 1 <= len(rows) <= maximum_input_edges or len({r['uid'] for r in rows}) != len(rows):
        raise ValueError('unique_literal_pending_linear_edges_required')
    deadline=time.monotonic()+timeout_s
    items={force._uid(t):t for t in board.GetTracks()};pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(items)>8192 or len(pads)>4096:raise ValueError('bounded_native_linear_inventory_required')
    def signature(r):
        return (r['code'],r['layer'],r['width'],r['locked'],tuple(sorted(force._uid(g) for g in r['groups'])))
    partitions={};retired=set();merged=[];joins=[];refusals=[]
    for r in rows:
        t=items.get(r['uid'])
        actual_groups=tuple(sorted(force._uid(g) for g in board.Groups() if t is not None and g.ContainsItem(t)))
        if (t is None or t.GetClass()!='PCB_TRACK' or t!=r['item'] or r['net']!=str(t.GetNetname()) or
                (t.GetNetCode(),t.GetLayer(),t.GetWidth(),t.IsLocked())!=signature(r)[:4] or
                actual_groups!=signature(r)[4] or t.GetLength()<=0 or
                {tuple(t.GetStart()),tuple(t.GetEnd())}!={tuple(r['start']),tuple(r['end'])}):
            raise ValueError('literal_native_pending_linear_edge_required')
        if r['typed_anchor_retained'] or any(g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|') for g in r['groups']):
            merged.append(dict(r));continue
        partitions.setdefault(signature(r),[]).append(r)
    for cohort in partitions.values():
        byid={r['uid']:r for r in cohort};at={}
        for r in cohort:
            for p in (tuple(r['start']),tuple(r['end'])):at.setdefault(p,set()).add(r['uid'])
        remaining=set(byid)
        while remaining:
            if time.monotonic()>=deadline:raise ValueError('native_whole_linear_cohort_deadline')
            members={min(remaining)};queue=list(members)
            while queue:
                r=byid[queue.pop()]
                for p in (tuple(r['start']),tuple(r['end'])):
                    peers=at[p]-members;members.update(peers);queue.extend(peers)
            remaining-=members;selected=[byid[u] for u in sorted(members)]
            incidence={p:us & members for p,us in at.items() if us & members}
            ports=sorted(p for p,us in incidence.items() if len(us)==1)
            if (len(members)<2 or len(members)>maximum_members or len(ports)!=2 or
                    any(len(us)>2 for us in incidence.values()) or
                    sum(items[u].GetLength() for u in members)>maximum_cut_nm or
                    any(items[u].GetLength()>32000000 for u in members)):
                merged.extend(dict(r) for r in selected);continue
            root=selected[0];layer=root['layer'];code=root['code'];width=root['width']
            caps=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width) for p in ports]
            externals=[p for p in pads if p.GetNetCode()==code and p.IsOnLayer(layer)]
            externals += [t for u,t in items.items() if u not in members and t.GetNetCode()==code and t.IsOnLayer(layer)]
            bad=[]
            for peer in externals:
                if time.monotonic()>=deadline:raise ValueError('native_whole_linear_cohort_deadline')
                shape=peer.GetEffectiveShape(layer)
                if not any(shape.Collide(items[u].GetEffectiveShape(layer),0) for u in members):continue
                if not any(shape.Collide(cap,0) for cap in caps):bad.append(force._uid(peer))
            if bad:
                refusals.append(dict(members=sorted(members),unrepresented_native_contact_uuids=bad))
                merged.extend(dict(r) for r in selected);continue
            primary=dict(root,start=ports[0],end=ports[1],pending_member_uuids=sorted(members),
                pending_cohort_retired_uuids=sorted(members-{root['uid']}))
            merged.append(primary);retired.update(members-{root['uid']})
            joins.append(dict(member_uuids=sorted(members),external_ports_nm=[list(p) for p in ports],
                source_width_nm=width,actual_native_external_contacts_checked=True))
    return merged,sorted(retired),dict(joins=joins,refusals=refusals,native_geometry_mutated=False,
        source_partition_and_current_receiving_required=True,automatic_retirement_authorized=False,
        current_qualified=False,release_authority=False)
