"""Read-only layer reach through an unchanged source barrel in an SMD land.

This recognizes existing physical contact, not permission to drill, resize or
qualify a via. All returned barrels must belong to the caller's pre-mutation
source inventory, have simple unmodified through geometry, and be positively
contained by the actual same-net pad under its declared filled/capped process.
Inherited manufacturing debt remains unqualified. Destination routing-layer,
clearance, reference, field and saved-board checks remain separate.
"""
import pcbnew
import cec_fab_profile as fab
import cec_kelvin_copper_cut as native


def inspect(board,pad,retained_via_uuids):
    allowed=set(retained_via_uuids)
    if (len(allowed)>16384 or any(type(u) is not str or not u for u in allowed)):
        raise ValueError('bounded_explicit_retained_barrel_inventory_required')
    surface=set(pad.GetLayerSet().CuStack())
    enabled=tuple(board.GetEnabledLayers().CuStack())
    result=dict(layers=sorted(surface & set(enabled)),retained_via_uuids=[],
        new_hole_or_via_geometry_authorized=False,inherited_debt_qualified=False,
        release_authority=False)
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole() or pad.GetNetCode()<=0
            or len(surface)!=1 or not surface<={pcbnew.F_Cu,pcbnew.B_Cu}
            or len(enabled)<2 or {enabled[0],enabled[-1]}!={pcbnew.F_Cu,pcbnew.B_Cu}):
        return result
    for via in board.GetTracks():
        if (via.GetClass()!='PCB_VIA' or via.m_Uuid.AsString() not in allowed
                or via.GetNetCode()!=pad.GetNetCode() or via.GetPosition()!=pad.GetPosition()
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
            continue
        try:
            if not native._simple_drill(via,enabled):continue
            if not fab.via_pad_decision(board,pad,via.GetPosition(),
                    max(via.GetWidth(layer) for layer in enabled),via.GetDrillValue(),via.GetNetCode())[0]:
                continue
        except native.Unknown:
            continue
        result['retained_via_uuids'].append(via.m_Uuid.AsString())
    if result['retained_via_uuids']:
        result['layers']=sorted(enabled)
        result['retained_via_uuids'].sort()
    return result
