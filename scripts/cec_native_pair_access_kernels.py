"""Expose scarce pair access before rebuilding ordinary pending route tails.

A pending ordinary lead can leave most of its old two-terminal corridor in
place. That retained tail is an obstacle even when its own reroute is ordered
after a constrained pair. This bounded, read-only planner may collect that
whole *same-face* ordinary kernel. It keeps the two real plated terminals,
source width, all barrel identities and all unrelated layers/nets intact.
It supplies construction scope, NOT retirement or saved-board admission.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_pair_semantics as semantics


def plan(parent,board,rows,*,source_path,board_hint,timeout_s=3.,maximum_members=32,
         maximum_kernels=4,maximum_total_members=64,maximum_cut_nm=96000000,
         clearance_for,declared_source_motion_uuids=()):
    if (type(rows) not in (list,tuple) or not 1<=len(rows)<=128
            or type(board_hint) is not str or not board_hint or not callable(clearance_for)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(maximum_members) is not int or not 2<=maximum_members<=32
            or type(maximum_kernels) is not int or not 1<=maximum_kernels<=4
            or type(maximum_total_members) is not int or not maximum_members<=maximum_total_members<=128
            or type(maximum_cut_nm) is not int or not 0<maximum_cut_nm<=96000000
            or Path(parent.GetFileName()).resolve()!=Path(source_path).resolve()
            or Path(board.GetFileName()).resolve()!=Path(source_path).resolve()):
        raise ValueError('bounded_original_source_pair_access_kernel_context_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_pair_access_kernel_deadline')
    original={force._uid(t):t for t in parent.GetTracks()}
    items={force._uid(t):t for t in board.GetTracks()}
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(items)>8192 or len(original)>8192 or len(pads)>4096 or len({r['uid'] for r in rows})!=len(rows):
        raise ValueError('bounded_unique_pair_access_native_inventory_required')
    pending_ids={r['uid'] for r in rows}
    if (type(declared_source_motion_uuids) not in (list,tuple,set,frozenset)
            or len(declared_source_motion_uuids)>512
            or any(type(u) is not str for u in declared_source_motion_uuids)):
        raise ValueError('literal_original_source_pair_kernel_motion_scope_required')
    declared=set(declared_source_motion_uuids)
    if len(declared)!=len(declared_source_motion_uuids) or not declared<=original.keys():
        raise ValueError('literal_original_source_pair_kernel_motion_scope_required')
    for r in rows:
        declared.update(r.get('pending_member_uuids',[r['uid']]))
        declared.update(r.get('envelope_extension_uuids',[]))
    for r in rows:
        t=items.get(r['uid'])
        if (t is None or t.GetClass()!='PCB_TRACK' or t!=r['item']
                or r['net']!=str(t.GetNetname()) or r['code']!=t.GetNetCode()
                or r['layer']!=t.GetLayer() or r['width']!=t.GetWidth()
                or type(r['typed_anchor_retained']) is not bool):
            raise ValueError('actual_native_pair_access_pending_row_required')
    eligible=set(ordinary.eligible_nets(parent,Path(source_path),board_hint))
    pair_nets={n for _,p,n0 in semantics.coupled_pair_names(parent) for n in (p,n0)}
    constrained=[r for r in rows if r['net'] in pair_nets]
    # Only original ordinary copper that ALREADY belongs to a pending net
    # can enter the candidate set. The straight capsule is an obstruction
    # witness/proposal domain, never a claimed legal diagonal pair route.
    pending_domains={(r['net'],r['layer']) for r in rows if r['net'] in eligible and not r['typed_anchor_retained']}
    witnesses={}
    for q in constrained:
        tick();gap=clearance_for(q['net'])
        if type(gap) is not int or not 0<=gap<=2000000:raise ValueError('literal_pair_access_clearance_required')
        cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*q['start']),pcbnew.VECTOR2I(*q['end']),q['width'])
        for uid,t in items.items():
            tick()
            if (uid in pending_ids or uid not in original or t.GetClass()!='PCB_TRACK'
                    or (str(t.GetNetname()),int(t.GetLayer())) not in pending_domains
                    or not t.IsOnLayer(q['layer'])):continue
            if t.GetEffectiveShape(q['layer']).Collide(cap,gap):
                witnesses.setdefault((str(t.GetNetname()),int(t.GetLayer())),[]).append(
                    dict(retained_source_track_uuid=uid,pending_pair_track_uuid=q['uid'],
                        pair_net=q['net'],clearance_nm=gap))
    consumed=set();replacement=[];kernels=[];refusals=[]
    def grouped(t):return any(g.ContainsItem(t) for g in board.Groups())
    def ends(t):return (tuple(t.GetStart()),tuple(t.GetEnd()))
    for (net,layer),why in sorted(witnesses.items(),key=lambda q:(-len(q[1]),q[0])):
        tick()
        if len(kernels)>=maximum_kernels:break
        seed_rows=[r for r in rows if r['net']==net and r['layer']==layer and r['uid'] not in consumed]
        if not seed_rows:continue
        root=min(seed_rows,key=lambda r:r['uid']);members={root['uid']};queue=list(members)
        possible={u:t for u,t in items.items() if t.GetClass()=='PCB_TRACK'
            and str(t.GetNetname())==net and t.GetLayer()==layer}
        # Exact endpoint graph only. Native body/width/group contacts are
        # independently checked below; they cannot silently become lost tees.
        at={}
        for uid,t in possible.items():
            for point in ends(t):at.setdefault(point,set()).add(uid)
        reason=None
        while queue:
            tick();uid=queue.pop();t=possible[uid];before=original.get(uid)
            if (before is None or before.GetClass()!='PCB_TRACK' or grouped(t)
                    or any(g.ContainsItem(before) for g in parent.Groups()) or t.GetWidth()!=root['width']
                    or (str(before.GetNetname()),int(before.GetLayer()),before.GetWidth(),bool(before.IsLocked()))!=
                       (net,layer,t.GetWidth(),bool(t.IsLocked()))
                    or t.GetLength()<=0 or t.GetLength()>32000000):
                reason='source_width_lock_group_or_native_identity_boundary';break
            if uid not in declared and (ends(t)!=ends(before)):
                reason='undeclared_original_source_kernel_geometry_changed';break
            for point in ends(t):
                for other in at[point]-members:
                    members.add(other);queue.append(other)
            if len(members)>maximum_members:
                reason='explicit_native_kernel_member_work_bound';break
        incidence={p:us&members for p,us in at.items() if us&members}
        ports=sorted(p for p,us in incidence.items() if len(us)==1)
        relevant=[r for r in seed_rows if r['uid'] in members]
        obligations=set()
        for r in relevant:
            obligations.update(r.get('pending_member_uuids',[r['uid']]))
            obligations.update(r.get('envelope_extension_uuids',[]))
        if reason is None and (len(members)<2 or len(ports)!=2 or any(len(us)>2 for us in incidence.values())
                or not obligations<=members or not any(q['retained_source_track_uuid'] in members for q in why)):
            reason='not_one_complete_two_terminal_pending_ordinary_kernel'
        if reason is None and (sum(items[u].GetLength() for u in members)>maximum_cut_nm
                or sum(len(k['member_uuids']) for k in kernels)+len(members)>maximum_total_members):
            reason='explicit_native_kernel_union_or_length_work_bound'
        terminal_ids={};bad=[]
        if reason is None:
            retained=[*pads,*[t for u,t in items.items() if u not in members],
                *[z for z in board.Zones() if not z.GetIsRuleArea()]]
            for peer in retained:
                tick()
                if str(peer.GetNetname())!=net or not peer.IsOnLayer(layer):continue
                if peer.GetClass()=='ZONE':
                    bad.append(force._uid(peer));continue
                shape=peer.GetEffectiveShape(layer)
                if not any(shape.Collide(items[u].GetEffectiveShape(layer),0) for u in members):continue
                plated=peer.GetClass()=='PCB_VIA' and peer.GetViaType()==pcbnew.VIATYPE_THROUGH
                plated|=peer.GetClass()=='PAD' and peer.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and peer.HasHole()
                point=tuple(peer.GetPosition())
                if not plated or point not in ports:bad.append(force._uid(peer));continue
                terminal_ids.setdefault(point,[]).append(force._uid(peer))
            if bad or any(len(terminal_ids.get(p,[]))!=1 for p in ports):
                reason='native_body_branch_or_nonunique_nonplated_terminal_boundary'
        if reason is not None:
            refusals.append(dict(net=net,layer=layer,reason=reason,member_uuids=sorted(members),
                unrepresented_native_contacts=bad));continue
        consumed.update(r['uid'] for r in relevant)
        chosen=min(relevant,key=lambda r:r['uid'])
        replacement.append(dict(chosen,start=ports[0],end=ports[1],locked=any(items[u].IsLocked() for u in members),
            pending_member_uuids=sorted(members),pending_cohort_retired_uuids=sorted(members-{chosen['uid']}),
            envelope_extension_uuids=sorted(members-{chosen['uid']}),groups=[],typed_anchor_retained=False))
        kernels.append(dict(net=net,layer=layer,member_uuids=sorted(members),source_width_nm=root['width'],
            original_pending_row_uuids=sorted(r['uid'] for r in relevant),external_ports_nm=[list(p) for p in ports],
            retained_plated_terminal_uuids=[terminal_ids[p][0] for p in ports],native_obstruction_witnesses=why,
            positive_source_ordinary_classification=True,barrels_removed_or_created=False))
    result=[r for r in rows if r['uid'] not in consumed]+replacement
    retired=sorted({u for r in replacement for u in r['pending_cohort_retired_uuids']})
    return result,retired,dict(schema=1,kernels=kernels,refusals=refusals,constrained_pair_nets=sorted(pair_nets),
        exact_source_only=True,native_geometry_mutated=False,unrelated_copper_or_layers_changed=False,
        width_reduced=False,current_sharing_assumed=False,automatic_retirement_authorized=False,
        saved_whole_source_partitions_and_native_receiving_required=True,release_authority=False)
