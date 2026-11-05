"""Remove only new straight copper wholly covered by one unchanged SMD land.

Uses a conservative native inside polygon and the full actual-width capsule,
not centre points, a pad bbox, same pad number or a global net-name heuristic.
Caller owns saved-board receiving. Existing copper and vias are never pruned.
"""
import math
import pcbnew
import cec_board_geometry as geometry


def prune_in_land(board, added_track_uuids, *, max_items=512):
    if (type(max_items) is not int or not 1<=max_items<=512
            or not isinstance(added_track_uuids,(list,tuple,set))
            or len(added_track_uuids)>max_items):
        raise ValueError('bounded_received_track_inventory_required')
    ids=set(added_track_uuids)
    if len(ids)!=len(added_track_uuids) or any(type(u) is not str or not u for u in ids):
        raise ValueError('ambiguous_received_track_identity')
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    if not ids<=tracks.keys():raise ValueError('received_track_missing')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()
          if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()]
    if len(pads)>4096:raise ValueError('native_pad_inventory_bound')
    removed=[];owners=[];cache={}
    for uid in sorted(ids):
        t=tracks[uid]
        if t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None:continue
        radius=math.ceil(t.GetWidth()/2)+1001;layer=int(t.GetLayer())
        for pad in pads:
            if pad.GetNetCode()!=t.GetNetCode() or not pad.IsOnLayer(layer) or not pad.FlashLayer(layer):continue
            key=(pad.m_Uuid.AsString(),layer)
            if key not in cache:
                native=pad.GetEffectivePolygon(layer,pcbnew.ERROR_INSIDE)
                cache[key]=(native,geometry.material_boundaries(native))
            native,bounds=cache[key]
            if bounds and geometry.material_leg_clear(native,bounds,t.GetStart(),t.GetEnd(),radius):
                board.Remove(t);removed.append(t)  # Retain the SWIG owner until function return.
                owners.append(dict(uuid=uid,pad_uuid=key[0],layer_id=layer,
                    basis='full_width_capsule_inside_native_SMD_land',guard_nm=1001))
                break
    return dict(removed=[row['uuid'] for row in owners],proofs=owners,
                release_authority=False,requires_saved_board_receiving=True)
