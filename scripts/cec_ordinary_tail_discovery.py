"""Native leaf-chain proposals for the existing exact ordinary-cut receiver.

Warnings alone grant no removal authority. The positive source classifier
excludes power, ground, pairs and Kelvin domains. Native finite-body contacts
include pads, plated barrels, interior tees and protected grouped copper.
Discover a whole terminal-free tail, not one segment that merely moves the
warning. Every proposed cut still requires independent saved receiving.
"""
import argparse,json,time,math
from pathlib import Path
import cec_swig_guard;cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary


def discover(board,source,board_hint,warning_uuids,*,timeout_s=10.,allow_connected_seed_cohorts=False):
    return _discover_native_leaf_chains(board,warning_uuids,
        positive_nets=ordinary.eligible_nets(board,source,board_hint),maximum_width_nm=499999,timeout_s=timeout_s,
        allow_connected_seed_cohorts=allow_connected_seed_cohorts)


def _discover_native_leaf_chains(board,warning_uuids,*,positive_nets,maximum_width_nm,timeout_s=10.,
                                 allow_connected_seed_cohorts=False):
    """Read-only geometric hints only; typed callers retain separate receiving.

    No net classification or cut permission is supplied by this shared walk.
    Ordinary and full-current supply callers each supply their own positive
    types and independently receive saved cuts. Width, finite native body,
    actual land/barrel/tee and group guards remain shared.
    """
    if (type(positive_nets) not in (set,frozenset) or any(type(n) is not str or not n for n in positive_nets)
            or type(maximum_width_nm) is not int or not 0<maximum_width_nm<=1000000
            or type(allow_connected_seed_cohorts)is not bool):
        raise ValueError('bounded_positive_native_leaf_hint_context_required')
    if not isinstance(warning_uuids,(list,tuple)) or len(warning_uuids)>32 or len(set(warning_uuids))!=len(warning_uuids):
        raise ValueError('bounded_unique_native_tail_warning_scope_required')
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_native_tail_discovery_deadline_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_tail_discovery_deadline')
    positive=positive_nets
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(tracks)>4096 or len(pads)>2048:raise ValueError('bounded_native_tail_board_inventory_required')
    lookup={force._uid(t):t for t in tracks};selected=set();rows=[]
    if not set(warning_uuids)<=lookup.keys():raise ValueError('native_tail_warning_source_item_missing')
    for uid in warning_uuids:
        tick();seed=lookup[uid];row=dict(warning_uuid=uid,net=seed.GetNetname(),proposed_track_uuids=[])
        rows.append(row)
        if (seed.GetClass()!='PCB_TRACK' or seed.GetNetname() not in positive
                or seed.GetParentGroup() is not None or not 0<seed.GetWidth()<=maximum_width_nm):
            row['refusal']='not_positive_source_ordinary_free_track';continue
        net=seed.GetNetname();face=seed.GetLayer();width=seed.GetWidth()
        if any(not z.GetIsRuleArea() and z.GetNetname()==net and z.IsOnLayer(face) for z in board.Zones()):
            row['refusal']='same_net_filled_or_owned_zone_requires_separate_receiver';continue
        physical=[t for t in tracks if t.GetNetname()==net and t.IsOnLayer(face)]
        lands=[p for p in pads if p.GetNetname()==net and p.IsOnLayer(face)]
        if len(physical)>128 or len(lands)>128:
            row['refusal']='native_tail_component_inventory_bound';continue
        physical+=lands
        shapes={force._uid(t):t.GetEffectiveShape(face) for t in physical}
        peers={u:set() for u in shapes}
        items={force._uid(t):t for t in physical}
        if len(items)!=len(physical):raise ValueError('native_tail_item_identity_duplicated')
        keys=sorted(shapes)
        for i,u in enumerate(keys):
            tick()
            for v in keys[i+1:]:
                if shapes[u].Collide(shapes[v],0):peers[u].add(v);peers[v].add(u)
        eligible={force._uid(t) for t in physical if t.GetClass()=='PCB_TRACK'
            and t.GetParentGroup() is None and t.GetWidth()==width}
        def one_retained_native_contact_cluster(live):
            if not live:return False
            seen={next(iter(live))};pending=list(seen)
            while pending:
                u=pending.pop();more=(peers[u]&live)-seen
                seen.update(more);pending.extend(more)
            return seen==live
        def positive_collinear_overlap(current,live):
            # A reconstructed branch can double back along an existing lead
            # and leave a short overhanging end. It is not an endpoint leaf:
            # its peers contact its INTERIOR. Only recognize actual straight,
            # equal-width, same-face overlap, never a nearby or crossing line.
            a=tuple(current.GetStart());b=tuple(current.GetEnd())
            dx,dy=b[0]-a[0],b[1]-a[1];length2=dx*dx+dy*dy
            if not length2:return False
            for uid in live:
                item=items[uid]
                if item.GetClass()!='PCB_TRACK' or item.GetWidth()!=current.GetWidth():continue
                c=tuple(item.GetStart());d=tuple(item.GetEnd())
                if any(dx*(p[1]-a[1])-dy*(p[0]-a[0]) for p in (c,d)):continue
                lo,hi=sorted((dx*(p[0]-a[0])+dy*(p[1]-a[1]) for p in (c,d)))
                if min(length2,hi)-max(0,lo)>0:return True
            return False
        def one_retained_native_endpoint_cluster(current,live):
            ends=[pcbnew.SHAPE_CIRCLE(current.GetStart(),0),pcbnew.SHAPE_CIRCLE(current.GetEnd(),0)]
            seats=[{i for i,e in enumerate(ends) if shapes[u].Collide(e,0)} for u in live]
            if not seats or not set.intersection(*seats):return False
            # A pad/barrel plus a retained lead can touch the same tail end.
            # They must ALREADY contact without the removed tail, otherwise
            # it is a real bridge rather than a dead end.
            return one_retained_native_contact_cluster(live)
        def connected_hint_cohort(current):
            # Two tiny dangling Source capsules can both touch the same
            # retained lead as well as each other. Neither is an individual
            # leaf, but their exact hinted connected cohort can have ONE
            # retained contact cluster. This is discovery only: callers must
            # independently receive the entire saved cut and current model.
            # Never absorb an unhinted track, land, barrel, zone or another
            # net/width/face. Legacy ordinary discovery keeps this disabled.
            if not allow_connected_seed_cohorts:return set()
            hinted=set(warning_uuids)&eligible
            cohort={current};pending=[current]
            while pending:
                tick();u=pending.pop();more=(peers[u]&hinted)-cohort
                cohort.update(more);pending.extend(more)
                if len(cohort)>4:return set()
            if len(cohort)<2:return set()
            boundary=set().union(*(peers[u]for u in cohort))-cohort
            return cohort if one_retained_native_contact_cluster(boundary)else set()
        visited=set();next_uid=uid
        while next_uid in eligible:
            tick()
            live=peers[next_uid]-visited
            if len(live)>1:
                if (one_retained_native_endpoint_cluster(items[next_uid],live)
                        or positive_collinear_overlap(items[next_uid],live)
                        and one_retained_native_contact_cluster(live)):
                    visited.add(next_uid)
                elif (allow_connected_seed_cohorts and row.get('connected_hinted_seed_cohort')
                        and visited and one_retained_native_contact_cluster(live)):
                    # A contracted source lobe can leave its old finite
                    # capsule overlapping several NEW leads near their
                    # junction, without any centreline endpoint landing on
                    # them. They must already form ONE retained native body
                    # cluster. Only whole-load supply callers enable cohort
                    # discovery, and independently prove all full-width joins
                    # and physical/current nonregression of the complete cut.
                    visited.add(next_uid)
                elif not visited:
                    cohort=connected_hint_cohort(next_uid)
                    if cohort:
                        visited.update(cohort)
                        row['connected_hinted_seed_cohort']=sorted(cohort)
                        row['one_retained_native_contact_cluster']=True
                        # Contract the proved hinted lobe, then continue
                        # the same bounded leaf walk through a sole ordinary
                        # stem. Otherwise removing the lobe would just expose
                        # that OLD stem as the next dangling warning.
                        boundary=set().union(*(peers[u]for u in cohort))-visited
                        if len(boundary)==1 and next(iter(boundary))in eligible:
                            next_uid=next(iter(boundary));continue
                break
            visited.add(next_uid)
            if len(selected|visited)>32:raise ValueError('native_tail_exact_cut_scope_bound')
            if not live:break
            next_uid=next(iter(live))
        row['proposed_track_uuids']=sorted(visited);selected.update(visited)
        if len(selected)>32:raise ValueError('native_tail_exact_cut_scope_bound')
        if not visited:row['refusal']='native_body_junction_or_multiple_protected_contacts'
    return dict(schema=1,scope='positive_source_native_leaf_chain_hints_not_retirement_authority',
        proposed_exact_track_uuids=sorted(selected),attempts=rows,complete=True,
        finite_native_body_contacts_used=True,protected_native_items_never_proposed_for_cut=True,
        independent_exact_saved_ordinary_receiving_required=True,
        routing_admitted=False,current_qualified=False,release_authority=False)


def main():
    p=argparse.ArgumentParser()
    for k in ('source','native-drc','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--hint',required=True);a=p.parse_args();assert not a.out.exists()
    sha=force._hash(a.source);r=json.loads(a.native_drc.read_text())
    ids=[v['items'][0]['uuid'] for v in r['violations'] if v['type']=='track_dangling' and len(v['items'])==1]
    result=discover(pcbnew.LoadBoard(str(a.source)),a.source,a.hint,ids)
    assert sha==force._hash(a.source)
    result.update(source=str(a.source),source_sha256=sha,native_report_sha256=force._hash(a.native_drc),
        proposer_sha256=force._hash(Path(__file__)))
    force._write(a.out,result)
    print(json.dumps(dict(receipt=str(a.out),proposed=len(result['proposed_exact_track_uuids']),
        rejected_seeds=[r['warning_uuid'] for r in result['attempts'] if r.get('refusal')],
        complete=result['complete'],release_authority=False)),flush=True)


if __name__=='__main__':main()
