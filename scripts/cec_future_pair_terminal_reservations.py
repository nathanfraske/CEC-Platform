"""Source-bound paired-terminal escapes as temporary planning obstacles.

The original live pair, two real lands on one unchanged component, legal
signal/reference layer and original widths own the reservation. Explicit
coordinates propose a finite escape, never copper, retirement permission,
coupling/reference qualification or a routed pair. Mandatory removal before
fill/save/receiving is shared with whole-current future reservations.
"""
import math,time
from pathlib import Path


def construct(board,source,requests,*,source_sha256,blocked_net,board_hint,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_precision_route as precision
    import cec_route_quality as quality
    import cec_fab_profile as fab
    import cec_current_topology as topology
    import cec_fr as fr
    from cec_native_items import discard_items
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(requests) is not list or not 1<=len(requests)<=4
            or type(blocked_net) is not str or not blocked_net):
        raise ValueError('bounded_explicit_pair_terminal_reservations_required')
    deadline=time.monotonic()+timeout_s;source=Path(source).resolve()
    if force._hash(source)!=source_sha256:raise ValueError('exact_pair_terminal_source_identity_required')
    parent=pcbnew.LoadBoard(str(source));pairs=precision.derive_coupled_pairs(str(source),board=parent)
    old={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    live={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    permitted=set(fab.referenced_signal_layers(parent,hint=str(source)))
    with force._thermal_hint(board_hint):protected=set(topology.board_current_domains(parent,board_hint))
    protected|={z.GetNetname() for z in parent.Zones() if not z.GetIsRuleArea()}
    plans=[];seen=set();receipts=[]
    for q in requests:
        if time.monotonic()>=deadline:raise ValueError('pair_terminal_reservation_deadline')
        if type(q) is not dict or set(q)!={'source_sha256','pair','layer','p_pad_uuid','n_pad_uuid','p_points_nm','n_points_nm'}:
            raise ValueError('exact_pair_terminal_reservation_fields_required')
        pair_rows=[p for p in pairs if p['name']==q['pair']]
        if q['source_sha256']!=source_sha256 or len(pair_rows)!=1 or q['layer'] not in permitted:
            raise ValueError('positive_source_pair_and_reference_signal_layer_required')
        pair=pair_rows[0];nets={pair['p'],pair['n']}
        if any(type(pair.get(k)) not in (int,float) or not math.isfinite(pair[k]) or pair[k]<=0
                for k in ('width','gap','clearance')):
            raise ValueError('complete_positive_source_pair_dimensions_required')
        if blocked_net in nets or nets&protected:raise ValueError('foreign_nonpower_coupled_pair_required')
        pads=[old.get(q[side+'_pad_uuid']) for side in ('p','n')]
        if any(p is None for p in pads) or force._uid(pads[0])==force._uid(pads[1]):
            raise ValueError('two_actual_distinct_source_pair_lands_required')
        if (force._uid(pads[0].GetParentFootprint())!=force._uid(pads[1].GetParentFootprint())
                or pads[0].GetParentFootprint().IsDNP()):
            raise ValueError('one_populated_source_component_pair_terminal_required')
        lid=parent.GetLayerID(q['layer']);width=round(pair['width']*1e6)
        gap=max(parent.GetDesignSettings().m_MinClearance,round(pair['clearance']*1e6))
        if lid not in board.GetEnabledLayers().CuStack() or not 0<width<=1000000:
            raise ValueError('enabled_source_pair_layer_and_width_required')
        for side,pad in zip(('p','n'),pads):
            uid=force._uid(pad);actual=live.get(uid);points=q[side+'_points_nm']
            def signature(item):
                owner=item.GetParentFootprint()
                return (force._uid(owner),tuple(owner.GetPosition()),owner.GetOrientationDegrees(),
                    owner.IsFlipped(),owner.IsDNP(),owner.GetFPIDAsString(),owner.GetValue(),
                    tuple(item.GetPosition()),tuple(item.GetSize()),item.GetOrientationDegrees(),
                    int(item.GetAttribute()),int(item.GetShape()),tuple(item.GetOffset()),
                    tuple(item.GetDrillSize()),tuple(map(int,item.GetLayerSet().CuStack())))
            if (actual is None or actual.GetNetname()!=pair[side] or pad.GetNetname()!=pair[side]
                    or signature(pad)!=signature(actual)
                    or not pad.IsOnLayer(lid) or not actual.IsOnLayer(lid)
                    or type(points) is not list or not 2<=len(points)<=8
                    or any(type(p) is not list or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)
                    or points[0]!=list(pad.GetPosition()) or (uid,lid) in seen):
                raise ValueError('unchanged_actual_source_pair_land_and_finite_escape_required')
            length=0;seen.add((uid,lid))
            for start,end in zip(points,points[1:]):
                if start==end or not quality.is_canonical_stroke(tuple(start),tuple(end)):
                    raise ValueError('canonical_nonempty_pair_terminal_escape_required')
                length+=math.dist(start,end)
                if length>10000000:raise ValueError('pair_terminal_escape_length_bound')
                a,b=pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end)
                if not fr._edge_leg_clear(board,a,b,math.ceil(width/2+gap)):
                    raise ValueError('pair_terminal_escape_outside_native_material')
                plans.append((a,b,width,lid,pair[side]))
            receipts.append(dict(pair=pair['name'],member=side,source_pad_uuid=uid,net=pair[side],
                layer=q['layer'],points_nm=points,width_nm=width,clearance_nm=gap))
        paths=[[tuple(v/1e6 for v in p) for p in q[side+'_points_nm']] for side in ('p','n')]
        if (not precision._polys_no_cross(*paths) or not precision._pair_min_clear(*paths,-1,-1,
                pair['width'],pair['gap'],strict_pair_gap=True)):
            raise ValueError('pair_terminal_reservation_members_cross_or_violate_source_gap')
    if time.monotonic()>=deadline or force._hash(source)!=source_sha256:
        raise ValueError('pair_terminal_reservation_source_or_deadline_changed')
    ghosts=[];rows=[]
    try:
        for start,end,width,layer,net in plans:
            track=pcbnew.PCB_TRACK(board);track.SetStart(start);track.SetEnd(end);track.SetWidth(width)
            track.SetLayer(layer);track.SetNetCode(board.GetNetcodeFromNetname(net));track.SetLocked(True)
            board.Add(track);ghosts.append(track)
            rows.append(dict(temporary_uuid=force._uid(track),net=net,layer=board.GetLayerName(layer),
                start_nm=list(start),end_nm=list(end),width_nm=width))
    except Exception:
        discard_items(board,ghosts);raise
    return ghosts,dict(schema=1,scope='source_owned_ephemeral_paired_terminal_escapes',source_sha256=source_sha256,
        rows=rows,source_terminal_contracts=receipts,actual_component_poses_changed=False,
        saved_copper_authority=False,retirement_authority=False,coupling_or_reference_qualified=False,
        current_capacity_credited=False,mandatory_removal_before_fill_save_or_receiving=True,release_authority=False)
