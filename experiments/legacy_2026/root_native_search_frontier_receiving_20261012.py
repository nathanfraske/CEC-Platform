"""Attribute failed maze hops through the EXISTING native collision kernel.

No obstacle is inferred from a rendered pixel, ref prefix or bounding box.
This read-only receipt is not a min-cut, placement permission or no-path proof.
"""
import time
import pcbnew
import cec_fr as fr


def explain(board, net, layer, hops, *, clearance_nm, timeout_s=10.):
    if (type(net) is not str or not net or type(layer) is not int
            or layer not in board.GetEnabledLayers().CuStack()
            or type(clearance_nm) is not int or not 0<=clearance_nm<=10_000_000
            or type(hops) is not list or not 1<=len(hops)<=128
            or type(timeout_s) not in (int,float) or not 0<timeout_s<=10.):
        raise ValueError('bounded_native_search_frontier_required')
    nc=board.FindNet(net)
    if nc is None or nc.GetNetCode()<=0:raise ValueError('exact_native_search_net_required')
    deadline=time.monotonic()+timeout_s
    zones,copper=fr._layer_foreign_shapes(board,layer,{nc.GetNetCode()},identified=True)
    zones,copper=fr._bucket_foreign_shapes(zones),fr._bucket_foreign_shapes(copper)
    rows=[]
    for hop in hops:
        if time.monotonic()>=deadline:raise ValueError('native_search_frontier_deadline')
        width=hop.get('width_nm');points=[hop.get('start_nm'),hop.get('end_nm')]
        if (type(width) is not int or not 0<width<=100_000_000
                or any(type(p) is not list or len(p)!=2 or any(type(v) is not int
                    or abs(v)>2_000_000_000 for v in p) for p in points)):
            raise ValueError('exact_native_failed_hop_dimensions_required')
        hits=fr._snapshot_foreign_blockers(pcbnew.VECTOR2I(*points[0]),pcbnew.VECTOR2I(*points[1]),
            width,clearance_nm,zones,copper,limit=16)
        rows.append(dict(start_nm=points[0],end_nm=points[1],width_nm=width,
            recorded_refusal_stage=hop.get('refusal_stage'),actual_native_blockers=hits,
            collision_evidence_available=bool(hits) and all(h.get('contact')!='geometry_unknown' for h in hits)))
    return dict(schema=1,scope='exact_native_collision_attribution_for_sampled_failed_hops',
        net=net,layer=board.GetLayerName(layer),checked_hops=len(rows),rows=rows,
        physical_no_path_proof=False,automatic_ripup_authorized=False,release_authority=False)
