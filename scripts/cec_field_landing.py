"""Actual-barrel-centered owned landing frames, not ampacity or release proof.

Explicitly reauthors one native solid landing from its complete symmetric
resident barrel inventory. No barrel, pad, track, group or process setting is
changed. Old excess zone pixels are deliberately not preserved; every prior
electrical/current/field/Kelvin connection needs independent board receiving.
"""
import time
import cec_rectilinear_copper as native

SCOPE='owned_native_barrel_landing_frame_not_current_or_release'


def _geometry(rows,required_width_nm,edge_margin_nm,style):
    from cec_via_field_layout import shape_evidence
    if (type(required_width_nm) is not int or not 1<=required_width_nm<=100_000_000
            or type(edge_margin_nm) is not int or not 1<=edge_margin_nm<=1_000_000
            or style not in ('square','chamfer45')):
        raise native.Refused('invalid_native_field_frame_bounds')
    sites=[r['position_nm'] for r in rows]
    center=[(min(p[i] for p in sites)+max(p[i] for p in sites))//2 for i in range(2)]
    evidence=shape_evidence(sites,center)
    if not evidence['centered'] or not evidence['rotationally_symmetric']:
        raise native.Refused('complete_symmetric_actual_barrel_field_required')
    radius=(rows[0]['diameter_nm']+1)//2+1
    half=[max(max(abs(p[i]-center[i]) for p in sites)+radius+edge_margin_nm,
        (required_width_nm+1)//2) for i in range(2)]
    x0,y0=center[0]-half[0],center[1]-half[1]
    x1,y1=center[0]+half[0],center[1]+half[1]
    if style=='square':points=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
    else:
        corner=min(radius//2,half[0]//2,half[1]//2)
        points=[[x0+corner,y0],[x1-corner,y0],[x1,y0+corner],[x1,y1-corner],
            [x1-corner,y1],[x0+corner,y1],[x0,y1-corner],[x0,y0+corner]]
    if any(abs(v)>2_000_000_000 for p in points for v in p):
        raise native.Refused('native_coordinate_bound')
    return points,evidence


def plan(board,zone_uuid,via_uuids,*,required_width_nm,edge_margin_nm=100_000,
        style='chamfer45',allow_locked_zone_uuids=(),allow_grouped_zone_uuids=()):
    import pcbnew
    from cec_rounded_landing import _native_source
    from cec_via_field_layout import _via_row,_disk
    deadline=time.monotonic()+2
    by_id={z.m_Uuid.AsString():z for z in board.Zones()}
    if len(by_id)>8192 or zone_uuid not in by_id:raise native.Refused('native_field_landing_missing')
    zone=by_id[zone_uuid];source=_native_source(zone,allow_complex_fill=True)
    c=source['configuration'];wanted=list(via_uuids)
    if (not c['net'] or c['rule_area'] or c['smoothing']
            or c['connection']!=int(pcbnew.ZONE_CONNECTION_FULL)
            or not 1<=len(wanted)<=25 or len(set(wanted))!=len(wanted)):
        raise native.Refused('explicit_owned_solid_barrel_landing_required')
    if (c['locked'] and zone_uuid not in set(allow_locked_zone_uuids)
            or c['group_uuid'] and zone_uuid not in set(allow_grouped_zone_uuids)):
        raise native.Refused('explicit_field_landing_owner_required')
    tracks=list(board.GetTracks())
    if len(tracks)>8192:raise native.Refused('native_field_track_inventory_bound')
    vias={v.m_Uuid.AsString():v for v in tracks if v.GetClass()=='PCB_VIA'}
    if not set(wanted)<=vias.keys():raise native.Refused('native_field_barrel_missing')
    rows=[_via_row(vias[uid]) for uid in sorted(wanted)];layer=c['layers'][0]
    keys={(r['net'],r['diameter_nm'],r['drill_nm'],r['via_type'],tuple(r['layers'])) for r in rows}
    if (len(keys)!=1 or rows[0]['net']!=c['net']
            or rows[0]['via_type']!=int(pcbnew.VIATYPE_THROUGH)
            or not 0<rows[0]['drill_nm']<rows[0]['diameter_nm']<=10_000_000):
        raise native.Refused('one_actual_through_barrel_inventory_required')
    contained=set()
    for uid,via in vias.items():
        native._check_deadline(deadline)
        if via.GetNetname()!=c['net'] or not via.IsOnLayer(layer):continue
        r=_via_row(via);missing=_disk(board,c['net'],layer,r['position_nm'],r['diameter_nm'])
        missing.BooleanSubtract(zone.Outline())
        if not missing.OutlineCount():contained.add(uid)
    if contained!=set(wanted):raise native.Refused('complete_resident_barrel_inventory_required')
    points,evidence=_geometry(rows,required_width_nm,edge_margin_nm,style)
    profile=native._poly(points)
    native._require_unoccupied_outline(board,profile,c['net'],layer,deadline,
        clearance_nm=c['clearance_nm'])
    for row in rows:
        missing=_disk(board,c['net'],layer,row['position_nm'],row['diameter_nm'])
        missing.BooleanSubtract(profile)
        if missing.OutlineCount():raise native.Refused('field_frame_does_not_cover_full_barrel')
    result=dict(schema=1,scope=SCOPE,source_zone=source,source_vias=rows,
        polygon_nm=points,field_shape=evidence,net=c['net'],layer_id=layer,
        required_width_nm=required_width_nm,edge_margin_nm=edge_margin_nm,style=style,
        new_capacity_credited=False,release_authority=False,requires_independent_receiving=True)
    result['plan_sha256']=native._digest(result)
    return result


def _validate(proposal):
    if type(proposal) is not dict:raise native.Refused('native_field_frame_identity_changed')
    p=dict(proposal);digest=p.pop('plan_sha256',None)
    if (digest!=native._digest(p) or p.get('scope')!=SCOPE or type(p.get('schema')) is not int or p['schema']!=1
            or p.get('new_capacity_credited') is not False or p.get('release_authority') is not False
            or p.get('requires_independent_receiving') is not True):
        raise native.Refused('native_field_frame_identity_changed')
    rows=p.get('source_vias');config=(p.get('source_zone') or {}).get('configuration',{})
    if (type(rows) is not list or not 1<=len(rows)<=25 or len({r.get('uuid') for r in rows if type(r) is dict})!=len(rows)
            or any(type(r) is not dict or type(r.get('position_nm')) is not list or len(r['position_nm'])!=2
                or any(type(v) is not int or abs(v)>2_000_000_000 for v in r['position_nm'])
                or type(r.get('diameter_nm')) is not int or not 1<=r['diameter_nm']<=10_000_000
                or type(r.get('drill_nm')) is not int or not 0<r['drill_nm']<r['diameter_nm']
                or r.get('net')!=p.get('net') for r in rows)
            or config.get('net')!=p.get('net') or config.get('layers')!=[p.get('layer_id')]):
        raise native.Refused('invalid_native_field_frame_inventory')
    points,evidence=_geometry(p['source_vias'],p['required_width_nm'],p['edge_margin_nm'],p['style'])
    if points!=p['polygon_nm'] or evidence!=p['field_shape']:
        raise native.Refused('native_field_frame_not_derived_from_actual_barrels')


def materialize(board,proposal,*,allow_locked_zone_uuids=(),allow_grouped_zone_uuids=()):
    _validate(proposal)
    uid=proposal['source_zone']['configuration']['uuid']
    expected=plan(board,uid,[r['uuid'] for r in proposal['source_vias']],
        required_width_nm=proposal['required_width_nm'],edge_margin_nm=proposal['edge_margin_nm'],
        style=proposal['style'],allow_locked_zone_uuids=allow_locked_zone_uuids,
        allow_grouped_zone_uuids=allow_grouped_zone_uuids)
    if expected!=proposal:raise native.Refused('native_field_frame_source_changed')
    z=next(z for z in board.Zones() if z.m_Uuid.AsString()==uid)
    z.UnFill();z.Outline().RemoveAllContours();z.Outline().NewOutline()
    for at in proposal['polygon_nm']:z.Outline().Append(*at)
    return dict(zone_uuid=uid,modified_zone_uuids=[uid],new_capacity_credited=False,
        native_fill_received=False,release_authority=False)


def receive(board,proposal,*,timeout_s=2):
    from cec_rounded_landing import _configuration
    from cec_via_field_layout import _via_row,_disk
    result=dict(ok=False,complete=False,release_authority=False,new_capacity_credited=False,
        original_source_fill_preserved=False,full_board_receiving_required=True)
    try:
        import math
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<=timeout_s<=10:
            raise native.Refused('invalid_native_field_frame_deadline')
        _validate(proposal);deadline=time.monotonic()+timeout_s
        native._check_deadline(deadline);c=proposal['source_zone']['configuration']
        z=next((z for z in board.Zones() if z.m_Uuid.AsString()==c['uuid']),None)
        if z is None or _configuration(z)!=c:raise native.Refused('native_field_frame_process_changed')
        expected=native._poly(proposal['polygon_nm'])
        native._require_unoccupied_outline(board,expected,c['net'],c['layers'][0],deadline,
            clearance_nm=c['clearance_nm'])
        a=z.Outline().CloneDropTriangulation();a.BooleanSubtract(expected)
        b=expected.CloneDropTriangulation();b.BooleanSubtract(z.Outline())
        if a.OutlineCount() or b.OutlineCount():raise native.Refused('saved_field_frame_outline_changed')
        if not z.IsFilled() or not z.HasFilledPolysForLayer(c['layers'][0]):
            raise native.Refused('saved_field_frame_fill_unknown')
        actual=z.GetFilledPolysList(c['layers'][0]);native._shape_identity(actual,deadline)
        # Full barrel-disk support must be supplied by THIS actual landing.
        # An unrelated same-net plane/track cannot disguise a truncated frame.
        vias={v.m_Uuid.AsString():v for v in board.GetTracks() if v.GetClass()=='PCB_VIA'}
        for row in proposal['source_vias']:
            native._check_deadline(deadline)
            if row['uuid'] not in vias or _via_row(vias[row['uuid']])!=row:
                raise native.Refused('saved_field_frame_barrel_changed')
            missing=_disk(board,c['net'],c['layers'][0],row['position_nm'],row['diameter_nm'])
            missing.BooleanSubtract(actual)
            if missing.OutlineCount():raise native.Refused('saved_field_frame_full_barrel_support_missing')
        spill=actual.CloneDropTriangulation();spill.BooleanSubtract(expected)
        if spill.OutlineCount():raise native.Refused('saved_field_frame_spill')
        result.update(ok=True,complete=True,field_shape=proposal['field_shape'],
            actual_barrels_unchanged=True)
    except (native.Refused,ValueError,RuntimeError) as exc:result['reason']=str(exc)
    return result
