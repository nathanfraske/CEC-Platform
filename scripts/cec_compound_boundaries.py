"""Original-parent proof for a fully removed inter-cell passive branch.

Never reconnect to a vanished staging coordinate. Only an isolated removed
copper component with exactly two moved SMD terminals may become a live
pad-to-pad obligation. Junctions and external contacts refuse, not disappear.
"""
import copy
import pcbnew


def rebind_internal_branches(original, staged, anchors, removed, moved_refs):
    def fail(reason):
        return dict(ok=False,reason=reason,release_authority=False)
    if len(removed)>8 or len(moved_refs)>4:
        return fail('compound_boundary_scope_exceeded')
    tracks={t.m_Uuid.AsString():t for t in original.GetTracks()
            if t.GetClass()=='PCB_TRACK' and t.m_Uuid.AsString() in removed}
    if set(tracks)!=set(removed):
        return fail('removed_copper_not_on_original_parent')
    pending=set(tracks); groups=[]
    def touch(a,b):
        return (a.GetNetCode()==b.GetNetCode() and a.GetLayer()==b.GetLayer()
                and a.GetEffectiveShape().Collide(b.GetEffectiveShape(),0))
    while pending:
        group={min(pending)};pending-=group
        while True:
            more={uid for uid in pending if any(touch(tracks[uid],tracks[old]) for old in group)}
            if not more:break
            group|=more;pending-=more
        groups.append(group)
    result=copy.deepcopy(anchors); proofs=[]
    for group in groups:
        rows=[a for a in result if a.get('track_uuid') in group]
        refs={a.get('ref') for a in rows}
        if len(refs)<2:continue
        branch=[tracks[uid] for uid in sorted(group)]
        code=branch[0].GetNetCode(); net=branch[0].GetNetname()
        if code<=0:return fail('unassigned_intercell_branch')
        contacts=[]
        for fp in original.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode()!=code:continue
                if any(pad.IsOnLayer(t.GetLayer()) and
                       pad.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0) for t in branch):
                    contacts.append((fp.GetReference(),str(pad.GetNumber()),pad))
        if (len(contacts)!=2 or len({r for r,_n,_p in contacts})!=2
                or {r for r,_n,_p in contacts}!=refs or not refs<=set(moved_refs)
                or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for _r,_n,p in contacts)):
            return fail('intercell_branch_has_unaccounted_terminal')
        # A plane is also an external electrical boundary. Conservatively
        # refuse outline contact even if the current fill is unavailable;
        # this helper has no authority to discard a plane pickup.
        for zone in original.Zones():
            if zone.GetIsRuleArea() or zone.GetNetCode()!=code:continue
            if any(zone.IsOnLayer(t.GetLayer()) and
                   zone.Outline().Collide(t.GetEffectiveShape(),0) for t in branch):
                return fail('intercell_branch_has_zone_contact')
        for other in original.GetTracks():
            if other.m_Uuid.AsString() in group or other.GetNetCode()!=code:continue
            if any(other.IsOnLayer(t.GetLayer()) and
                   other.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0) for t in branch):
                return fail('intercell_branch_has_external_copper_contact')
        endpoints=[]
        for ref,number,_pad in sorted(contacts,key=lambda c:c[:2]):
            fp=staged.FindFootprintByReference(ref)
            pads=[p for p in fp.Pads() if str(p.GetNumber())==number and p.GetNetname()==net] if fp else []
            if len(pads)!=1:return fail('intercell_terminal_not_live')
            pad=pads[0];pos=pad.GetPosition()
            endpoints.append(dict(kind='pad',ref=ref,pad=number,uuid=pad.m_Uuid.AsString(),
                                  x_mm=pos.x/1e6,y_mm=pos.y/1e6))
        first,last=endpoints
        result=[a for a in result if a.get('track_uuid') not in group]
        result.append(dict(net=net,ref=last['ref'],pad=last['pad'],
            x_mm=first['x_mm'],y_mm=first['y_mm'],track_uuid='',
            route_endpoints=endpoints,original_removed_track_uuids=sorted(group)))
        proofs.append(dict(net=net,terminals=[[p['ref'],p['pad']] for p in endpoints],
            removed_track_uuids=sorted(group),old_obligations=len(rows),
            live_pad_pair_obligations=1,release_authority=False))
    return dict(ok=True,anchors=result,proofs=proofs,release_authority=False)
