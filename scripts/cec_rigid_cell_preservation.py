"""Independent original-parent proof for rigid internal support-cell copper.

Do not trust the mover's UUID allowlist. Re-infer bounded internal paths on
the source board, forbid locks/groups/power/foreign contacts, and require an
exact common native transform with unchanged conductor properties. Full
terminal/component restoration is checked by the enclosing branch proof.
"""
import math

import pcbnew
import cec_local_copper_cell as copper


def prove(source, candidate, moved_refs, rewritten, *, max_items=8):
    import cec_fr
    report=dict(ok=False, proved=[], release_authority=False)
    first={fp.GetReference():fp for fp in source.GetFootprints()}
    last={fp.GetReference():fp for fp in candidate.GetFootprints()}
    refs=set(moved_refs)
    if not refs <= first.keys() or not refs <= last.keys():
        return dict(report,reason='rigid_cell_component_missing')
    plan=copper.plan(source,[first[ref] for ref in sorted(refs)],
        protected_nets=cec_fr.locked_pour_authority_nets_board(source,include_complete_nets=False),
        max_items=max_items)
    permitted=set(plan['internal_track_uuids'])
    if not set(rewritten) <= permitted:
        return dict(report,reason='not_owned_rigid_cell_motion',refused=sorted(set(rewritten)-permitted))
    old_items={item.m_Uuid.AsString():item for item in source.GetTracks()}
    new_items={item.m_Uuid.AsString():item for item in candidate.GetTracks()}
    old_inventory,new_inventory=copper.copper_inventory(source),copper.copper_inventory(candidate)
    pads=[pad for ref in refs for pad in first[ref].Pads() if pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD]
    for chain in plan['accepted']:
        members=set(chain['uuids'])
        if not members.intersection(rewritten):continue
        owners=[]
        for net,layer,x,y in chain['terminals']:
            matching=[pad for pad in pads if pad.GetNetCode()==net and pad.IsOnLayer(layer)
                      and pad.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(x,y),0)]
            if len(matching)!=1:
                return dict(report,reason='rigid_terminal_not_unique')
            owners.append(matching[0])
        origin=owners[0].GetParentFootprint();destination=last[origin.GetReference()]
        delta=destination.GetOrientationDegrees()-origin.GetOrientationDegrees()
        cosine,sine=math.cos(math.radians(delta)),math.sin(math.radians(delta))
        old_at,new_at=origin.GetPosition(),destination.GetPosition()
        def transform(point):
            x,y=point.x-old_at.x,point.y-old_at.y
            return (round(new_at.x+cosine*x+sine*y),round(new_at.y-sine*x+cosine*y))
        for pad in owners:
            before=pad.GetParentFootprint();after=last[before.GetReference()]
            if (transform(before.GetPosition())!=tuple(after.GetPosition())
                    or round((after.GetOrientationDegrees()-before.GetOrientationDegrees()-delta)%360,6) not in (0.,360.)
                    or before.IsFlipped()!=after.IsFlipped()):
                return dict(report,reason='internal_cell_has_no_common_rigid_transform')
        for uid in sorted(members):
            if uid not in new_items:
                return dict(report,reason='rigid_internal_member_missing',refused=[uid])
            old,new=old_items[uid],new_items[uid]
            a,b=old_inventory[uid],new_inventory[uid]
            if (a[0]!='PCB_TRACK' or a[:3]!=b[:3] or a[7:]!=b[7:]
                    or transform(old.GetStart())!=tuple(new.GetStart())
                    or transform(old.GetEnd())!=tuple(new.GetEnd())):
                return dict(report,reason='internal_copper_not_exact_rigid_transform',refused=[uid])
        report['proved'].append(dict(uuids=sorted(members),
            pad_uuids=[pad.m_Uuid.AsString() for pad in owners],
            refs=sorted({pad.GetParentFootprint().GetReference() for pad in owners}),
            rotation_delta_deg=delta, coordinate_tolerance_nm=0))
    return dict(report,ok=True,reason='exact_owned_internal_rigid_motion')
