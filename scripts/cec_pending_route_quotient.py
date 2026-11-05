"""Contract source copper-only degree-two waypoints in a pending repair graph.

The real retained graph is built WITHOUT the explicitly pending cut. A pure
ordinary track island with two pending incidences is old route ink, not an
electrical terminal. Coalesce those two requests, inventory the exact source
ink for retirement, and route between the outer retained boundaries instead.
Pads, barrels, fills, groups, source width and full receiving remain hard.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary


def plan(parent,board,rows,*,source_path,board_hint,already_retired_track_uuids=(),
         timeout_s=3.,maximum_members=32,maximum_islands=32,maximum_cut_nm=96000000):
    if (type(rows) not in (list,tuple) or not 1<=len(rows)<=128 or any(type(r) is not dict for r in rows)
            or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(maximum_members) is not int or not 2<=maximum_members<=64
            or type(maximum_islands) is not int or not 1<=maximum_islands<=32
            or type(maximum_cut_nm) is not int or not 0<maximum_cut_nm<=96000000
            or Path(parent.GetFileName()).resolve()!=Path(source_path).resolve()
            or Path(board.GetFileName()).resolve()!=Path(source_path).resolve()):
        raise ValueError('bounded_original_source_pending_quotient_context_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_pending_quotient_deadline')
    original={force._uid(t):t for t in parent.GetTracks()}
    live={force._uid(i):i for i in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]}
    if len(live)>16384 or len({r.get('uid') for r in rows})!=len(rows):
        raise ValueError('bounded_unique_native_pending_quotient_inventory_required')
    if (type(already_retired_track_uuids) not in (list,tuple,set,frozenset)
            or len(already_retired_track_uuids)>768
            or any(type(u) is not str or u not in live or live[u].GetClass()!='PCB_TRACK'
                for u in already_retired_track_uuids)):
        raise ValueError('literal_actual_native_pending_cut_required')
    cut=set(already_retired_track_uuids)
    for r in rows:
        t=live.get(r['uid'])
        if (t is None or t.GetClass()!='PCB_TRACK' or r['item']!=t
                or r['net']!=str(t.GetNetname()) or r['code']!=t.GetNetCode()
                or r['layer']!=t.GetLayer() or r['width']!=t.GetWidth()
                or type(r['typed_anchor_retained']) is not bool):
            raise ValueError('actual_native_pending_quotient_row_required')
        if not r['typed_anchor_retained']:
            cut.update(r.get('pending_member_uuids',[r['uid']]))
            cut.update(r.get('envelope_extension_uuids',[]))
            cut.add(r['uid'])
    if not cut<=live.keys() or any(live[u].GetClass()!='PCB_TRACK' for u in cut) or len(cut)>768:
        raise ValueError('actual_complete_native_pending_track_cut_required')
    eligible=set(ordinary.eligible_nets(parent,Path(source_path),board_hint))
    nets={r['net'] for r in rows if r['net'] in eligible and not r['typed_anchor_retained']}
    before=field._field_snapshot_inventory(board)
    material={u:i for u,i in live.items() if u not in cut and str(i.GetNetname()) in nets}
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in material.values():
        tick()
        if not graph.Add(item):raise ValueError('native_pending_quotient_graph_unknown')
    components={};point_cache={}
    def component_at(r,key):
        point=tuple(r[key]);cache_key=(r['net'],r['layer'],point)
        if cache_key in point_cache:return point_cache[cache_key]
        at=pcbnew.VECTOR2I(*point);cap=pcbnew.SHAPE_SEGMENT(at,at,1)
        seeds=[]
        for u,item in material.items():
            tick()
            if str(item.GetNetname())!=r['net'] or not item.IsOnLayer(r['layer']):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled():raise ValueError('pending_native_quotient_fill_unknown')
                if not item.HasFilledPolysForLayer(r['layer']):continue
                shape=item.GetFilledPolysList(r['layer'])
            else:shape=item.GetEffectiveShape(r['layer'])
            if shape.Collide(cap,0):seeds.append(item)
        result=None
        if 1<=len(seeds)<=16:
            ids={force._uid(seeds[0])}|{force._uid(i) for i in graph.GetConnectedItems(seeds[0])
                if str(i.GetNetname())==r['net']}
            if ids<=material.keys() and {force._uid(i) for i in seeds}<=ids:
                result=tuple(sorted(ids));components[result]=ids
        point_cache[cache_key]=result
        return result
    work=[dict(r) for r in rows];joins=[];refusals=[];used=set();retired=set()
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    source_grouped={force._uid(i) for g in parent.Groups() for i in g.GetItems()}
    while len(joins)<maximum_islands:
        incidences={}
        for r in work:
            if r['net'] not in nets or r['typed_anchor_retained'] or r['groups']:continue
            for key in ('start','end'):
                comp=component_at(r,key)
                if comp is not None and comp not in used:incidences.setdefault(comp,[]).append((r,key))
        changed=False
        for comp,links in sorted(incidences.items()):
            tick()
            if len(links)!=2 or links[0][0]['uid']==links[1][0]['uid']:continue
            members=set(comp);left,ka=links[0];right,kb=links[1]
            if (left['net'],left['layer'],left['width'])!=(right['net'],right['layer'],right['width']):continue
            if any(material[u].GetClass()!='PCB_TRACK' for u in members):continue
            reason=None
            for u in members:
                t=material[u];old=original.get(u)
                if (old is None or u in grouped|source_grouped or t.GetParentGroup() is not None
                        or old.GetClass()!='PCB_TRACK' or (str(t.GetNetname()),int(t.GetLayer()),t.GetWidth())!=
                            (left['net'],left['layer'],left['width'])
                        or (str(old.GetNetname()),int(old.GetLayer()),old.GetWidth(),bool(old.IsLocked()),
                            tuple(old.GetStart()),tuple(old.GetEnd()))!=
                           (str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()),
                            tuple(t.GetStart()),tuple(t.GetEnd()))):
                    reason='not_exact_unchanged_ungrouped_source_ordinary_ink';break
            all_members=set(members)
            for r in (left,right):
                all_members.update(r.get('pending_member_uuids',[r['uid']]))
                all_members.update(r.get('envelope_extension_uuids',[]));all_members.add(r['uid'])
            if reason is None and (len(all_members)>maximum_members
                    or sum(live[u].GetLength() for u in all_members)>maximum_cut_nm
                    or any(live[u].GetLength()>32000000 for u in all_members)):
                reason='bounded_native_quotient_union_or_length_scope'
            a=tuple(left['end' if ka=='start' else 'start']);b=tuple(right['end' if kb=='start' else 'start'])
            if a==b:reason='quotient_would_create_cycle_not_two_external_ports'
            if reason:
                refusals.append(dict(source_component_uuids=list(comp),reason=reason));used.add(comp);continue
            primary=min((left,right),key=lambda r:r['uid'])
            merged=dict(primary,start=a,end=b,pending_member_uuids=sorted(all_members),
                pending_cohort_retired_uuids=sorted(all_members-{primary['uid']}),
                envelope_extension_uuids=sorted(all_members-{primary['uid']}),
                locked=any(live[u].IsLocked() for u in all_members),groups=[],typed_anchor_retained=False)
            work=[r for r in work if r['uid'] not in (left['uid'],right['uid'])]+[merged]
            retired.update(all_members-{primary['uid']});used.add(comp)
            joins.append(dict(net=left['net'],layer=left['layer'],source_width_nm=left['width'],
                exact_source_copper_only_component_uuids=list(comp),electrical_terminals_removed=0,
                original_pending_row_uuids=[left['uid'],right['uid']],external_ports_nm=[list(a),list(b)],
                complete_pending_member_uuids=sorted(all_members)))
            changed=True;break
        if not changed:break
    if field._field_snapshot_inventory(board)!=before:
        raise ValueError('read_only_pending_native_quotient_changed_geometry')
    return work,sorted(retired),dict(schema=1,joins=joins,refusals=refusals,
        actual_native_graph_excludes_declared_pending_cut=True,board_mutated=False,
        pads_barrels_fills_and_groups_removed=False,automatic_retirement_authorized=False,
        original_source_partitions_and_full_native_receiving_still_required=True,
        source_current_reduced=False,release_authority=False)
