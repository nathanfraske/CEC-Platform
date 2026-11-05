"""Rank a bounded pair-layer portfolio by actual native endpoint access.

Ranking is not route or current authority. Only profile-referenced signal
layers are offered. Existing native incident tracks are preferred, followed by
actual pad/barrel access; no guessed via, nearest-object snap, source mutation
or claim of field/reference qualification is made.
"""
import math
import pcbnew
import cec_fab_profile as fab


def rank(board,pair,endpoints):
    if (len(endpoints)!=4 or pair.get('p')==pair.get('n')
            or any(not isinstance(p,(tuple,list)) or len(p)!=2 or
                any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10000 for v in p)
                for p in endpoints)):
        raise ValueError('four_bounded_actual_pair_ports_required')
    import cec_fr as fr
    names=list(dict.fromkeys(fab.referenced_signal_layers(board)))
    layers=[(name,board.GetLayerID(name)) for name in names if board.GetLayerID(name)>=0]
    items=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(items)>16384 or len(pads)>16384:raise ValueError('bounded_native_pair_layer_inventory_required')
    result=[]
    for order,(name,layer) in enumerate(layers):
        ports=[]
        for net,point in zip((pair['p'],pair['p'],pair['n'],pair['n']),endpoints):
            xy=tuple(round(v*1e6) for v in point);incidents=[];access=[]
            for t in items:
                if t.GetNetname()!=net:continue
                if t.GetClass()=='PCB_TRACK' and t.GetLayer()==layer and xy in (tuple(t.GetStart()),tuple(t.GetEnd())):
                    incidents.append(t.m_Uuid.AsString());access.append(t.m_Uuid.AsString())
                elif t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==xy and layer in fr._through_barrel_layers(board,t):
                    access.append(t.m_Uuid.AsString())
            for pad in pads:
                if pad.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH and pad.GetNetname()==net and tuple(pad.GetPosition())==xy and (
                        layer in pad.GetLayerSet().CuStack() or layer in fr._pth_barrel_layers(board,pad)):
                    access.append(pad.m_Uuid.AsString())
            ports.append(dict(net=net,at_nm=list(xy),actual_incident_track_uuids=sorted(incidents),
                actual_native_access_uuids=sorted(set(access))))
        result.append(dict(layer=name,ports=ports,
            ports_with_incident_tracks=sum(bool(p['actual_incident_track_uuids']) for p in ports),
            ports_with_existing_access=sum(bool(p['actual_native_access_uuids']) for p in ports),
            stable_profile_order=order,rank_is_not_route_or_manufacturing_authority=True))
    ranked=sorted(result,key=lambda r:(-r['ports_with_existing_access'],-r['ports_with_incident_tracks'],
        r['stable_profile_order']))
    complete=[r for r in ranked if r['ports_with_existing_access']==4]
    # Only existing common access earns additional primary-layer trials. A
    # layer requiring new transitions remains the established coupled
    # constructor's guarded fallback, not a guessed "free" source layer.
    return complete[:3] if complete else ranked[:1]
