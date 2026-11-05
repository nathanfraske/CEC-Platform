"""Recompile an existing solid pad-bank owner after external native motion.

All source pads/tracks fully enclosed by the old owner must participate. The
new chamfered envelope comes only from their actual retained native copper.
An old cover's apparently excess area may provide essential current width.
Retaining its leads does NOT establish preservation of that capacity. The
independent saved current-debt gate must receive any area retirement before
selection. This does not authorize motion, reduce a width/current, change
clearance/solid settings, or grant release.
Whole-board source-partition, current, Kelvin and assembly receiving remain
separate mandatory obligations.
"""
from __future__ import annotations
import time
import math
import cec_pad_bank_collector as bank
import cec_rectilinear_copper as owner
import cec_owned_contour_refresh as contour

SCOPE='source_complete_solid_pad_bank_refresh_not_motion_or_current_authority'
KEYS={'schema','scope','zone_uuid','source_configuration','source_pad_rows','source_track_rows',
    'candidate_pad_rows','candidate_track_rows','source_outline_sha256','policy','cover_extent','polygon_nm',
    'fill_envelope_nm','actual_chamfer_nm','source_conductors_retained','external_motion_receiving_required',
    'new_capacity_credited','release_authority','plan_sha256'}


def _uid(item):return item.m_Uuid.AsString()


def _zone(board,uid):
    matches=[z for z in board.Zones() if _uid(z)==uid]
    if len(matches)!=1:raise owner.Refused('one_literal_native_bank_owner_required')
    return matches[0]


def _settings(z):
    import pcbnew
    s=contour._configuration(z)
    if (s['name']!=bank.ZONE_NAME or s['rule_area'] or s['group_uuid'] or s['priority']!=0
            or not s['locked'] or s['layers']!=[s['layer_id']]
            or s['pad_connection']!=int(pcbnew.ZONE_CONNECTION_FULL) or s['smoothing']!=0):
        raise owner.Refused('exact_existing_solid_bank_owner_settings_required')
    return s


def _enclosed(board,z,deadline):
    pads=[]
    for f in board.GetFootprints():
        for p in f.Pads():
            owner._check_deadline(deadline)
            if p.GetNetname()!=z.GetNetname() or not p.IsOnLayer(z.GetLayer()):continue
            shape=bank._pad_shape(p,z.GetLayer());shape.BooleanSubtract(z.Outline())
            if not shape.OutlineCount():pads.append(_uid(p))
    tracks=owner._enclosed_native_track_ids(board,z.Outline(),z.GetNetname(),z.GetLayer(),deadline)
    return sorted(pads),sorted(tracks)


def _native_rows(board,pads,tracks,lid,policy,deadline):
    return bank._geometry(board,pads,tracks,lid,policy,deadline)


def _cover(board,pads,tracks,lid,policy,deadline,extent):
    # Retained lead bodies are independently bound, but need not enlarge the
    # pad landing. Their original native widths remain actual current paths.
    # This never grants permission to delete those leads or credit the cover.
    if extent not in ('pad_row','pad_row_and_retained_leads'):
        raise owner.Refused('literal_supported_bank_cover_extent_required')
    selected=tracks if extent=='pad_row_and_retained_leads' else []
    _,_,_,_,outline,cut=_native_rows(board,pads,selected,lid,policy,deadline)
    return outline,cut


def _dims(rows,excluded):return [{k:v for k,v in r.items() if k not in excluded} for r in rows]


def _source_fill(board,zone,pads,tracks,lid,policy,deadline):
    if not zone.IsFilled() or not zone.HasFilledPolysForLayer(lid):
        raise owner.Refused('actual_filled_source_bank_required')
    filled=zone.GetFilledPolysList(lid)
    owner._shape_identity(filled,deadline)
    for shape in _native_rows(board,pads,tracks,lid,policy,deadline)[3]:
        missing=shape.CloneDropTriangulation();missing.BooleanSubtract(filled)
        if missing.OutlineCount():raise owner.Refused('source_bank_fill_loses_enclosed_native_copper')


def plan(source,candidate,*,zone_uuid,pad_uuids,support_track_uuids,allow_locked_zone=False,
         allow_locked_track_uuids=(),chamfer_nm=600000,margin_nm=1000,grid_nm=1000,
         cover_extent='pad_row_and_retained_leads',timeout_s=10.):
    import pcbnew
    if (type(zone_uuid) is not str or type(allow_locked_zone) is not bool
            or type(pad_uuids) not in (list,tuple) or not 2<=len(pad_uuids)<=32
            or len(set(pad_uuids))!=len(pad_uuids)
            or type(support_track_uuids) not in (list,tuple) or len(support_track_uuids)>64
            or len(set(support_track_uuids))!=len(support_track_uuids)
            or any(type(u) is not str for u in (*pad_uuids,*support_track_uuids))
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(cover_extent) is not str or cover_extent not in ('pad_row','pad_row_and_retained_leads')
            or type(allow_locked_track_uuids) not in (list,tuple)
            or any(type(u) is not str for u in allow_locked_track_uuids)
            or len(set(allow_locked_track_uuids))!=len(allow_locked_track_uuids)
            or type(chamfer_nm) is not int or not 1<=chamfer_nm<=1000000
            or type(margin_nm) is not int or not 1<=margin_nm<=100000
            or type(grid_nm) is not int or not 1<=grid_nm<=100000):
        raise owner.Refused('bounded_literal_source_bank_refresh_required')
    deadline=time.monotonic()+timeout_s;old,new=_zone(source,zone_uuid),_zone(candidate,zone_uuid)
    cfg=_settings(old)
    if _settings(new)!=cfg or not allow_locked_zone:raise owner.Refused('bank_owner_settings_or_permission_changed')
    if not old.IsFilled() or not old.HasFilledPolysForLayer(cfg['layer_id']):
        raise owner.Refused('actual_filled_source_bank_required')
    pads,tracks=_enclosed(source,old,deadline)
    if pads!=sorted(pad_uuids) or tracks!=sorted(support_track_uuids):
        raise owner.Refused('every_enclosed_native_bank_pad_and_track_required')
    policy=dict(chamfer_nm=chamfer_nm,margin_nm=margin_nm,grid_nm=grid_nm)
    _source_fill(source,old,pads,tracks,cfg['layer_id'],policy,deadline)
    before=_native_rows(source,pads,tracks,cfg['layer_id'],policy,deadline)
    after=_native_rows(candidate,pads,tracks,cfg['layer_id'],policy,deadline)
    if (_dims(before[1],{'position_nm','orientation_deg','geometry_sha256'})!=_dims(after[1],{'position_nm','orientation_deg','geometry_sha256'})
            or _dims(before[2],{'start_nm','end_nm'})!=_dims(after[2],{'start_nm','end_nm'})):
        raise owner.Refused('retained_bank_native_dimensions_or_identity_changed')
    permissions=set(allow_locked_track_uuids)
    if permissions-set(tracks):raise owner.Refused('bank_track_permission_outside_complete_source_inventory')
    if any(r['locked'] and r['uuid'] not in permissions or r['group_uuid'] for r in before[2]):
        raise owner.Refused('exact_unowned_bank_track_motion_permissions_required')
    net,new_pads,new_tracks,_,_,_=after
    outline,cut=_cover(candidate,pads,tracks,cfg['layer_id'],policy,deadline,cover_extent)
    domain=owner._fill_envelope(outline,style='chamfer45',margin_nm=4)
    bank._clear(candidate,domain,net,cfg['layer_id'],cfg['clearance_nm'],deadline,own_zone_uuid=zone_uuid)
    if cfg['min_thickness_nm']>=min(max(p['size_nm']) for p in new_pads):
        raise owner.Refused('bank_floor_not_below_source_lands')
    result=dict(schema=1,scope=SCOPE,zone_uuid=zone_uuid,source_configuration=cfg,
        source_pad_rows=before[1],source_track_rows=before[2],candidate_pad_rows=new_pads,
        candidate_track_rows=new_tracks,source_outline_sha256=owner._shape_identity(old.Outline(),deadline)[0],
        policy=policy,cover_extent=cover_extent,polygon_nm=outline,fill_envelope_nm=domain,actual_chamfer_nm=cut,
        source_conductors_retained=True,external_motion_receiving_required=True,
        new_capacity_credited=False,release_authority=False)
    result['plan_sha256']=owner._digest(result);return result


def _check(candidate,proposal):
    if type(proposal) is not dict or set(proposal)!=KEYS:raise owner.Refused('exact_bank_refresh_plan_fields_required')
    p=dict(proposal);digest=p.pop('plan_sha256',None)
    if (digest!=owner._digest(p) or p.get('schema')!=1 or p.get('scope')!=SCOPE
            or p.get('source_conductors_retained') is not True or p.get('external_motion_receiving_required') is not True
            or p.get('new_capacity_credited') is not False or p.get('release_authority') is not False):
        raise owner.Refused('literal_bank_refresh_identity_or_authority_changed')
    z=_zone(candidate,p['zone_uuid']);cfg=_settings(z)
    if cfg!=p['source_configuration']:raise owner.Refused('bank_refresh_settings_changed')
    deadline=time.monotonic()+10.
    _,pads,tracks,_,_,_=_native_rows(candidate,[r['uuid'] for r in p['candidate_pad_rows']],
        [r['uuid'] for r in p['candidate_track_rows']],cfg['layer_id'],p['policy'],deadline)
    outline,cut=_cover(candidate,[r['uuid'] for r in pads],[r['uuid'] for r in tracks],
        cfg['layer_id'],p['policy'],deadline,p['cover_extent'])
    if pads!=p['candidate_pad_rows'] or tracks!=p['candidate_track_rows'] or outline!=p['polygon_nm'] or cut!=p['actual_chamfer_nm']:
        raise owner.Refused('actual_bank_motion_or_derived_geometry_changed')
    if owner._fill_envelope(outline,style='chamfer45',margin_nm=4)!=p['fill_envelope_nm']:
        raise owner.Refused('bank_refresh_derived_fill_envelope_changed')
    if (_dims(p['source_pad_rows'],{'position_nm','orientation_deg','geometry_sha256'})!=_dims(pads,{'position_nm','orientation_deg','geometry_sha256'})
            or _dims(p['source_track_rows'],{'start_nm','end_nm'})!=_dims(tracks,{'start_nm','end_nm'})):
        raise owner.Refused('bank_refresh_native_source_dimensions_changed')
    bank._clear(candidate,p['fill_envelope_nm'],cfg['net'],cfg['layer_id'],cfg['clearance_nm'],deadline,own_zone_uuid=p['zone_uuid'])
    return z


def materialize(candidate,proposal):
    z=_check(candidate,proposal);z.UnFill();z.Outline().RemoveAllContours();z.Outline().NewOutline()
    for x,y in proposal['polygon_nm']:z.Outline().Append(x,y)
    return dict(zone_uuid=_uid(z),same_native_owner_retained=True,independent_filled_receiving_required=True,release_authority=False)


def receive(source,candidate,proposal):
    result=dict(ok=False,complete=False,new_capacity_credited=False,release_authority=False)
    try:
        z=_check(candidate,proposal);cfg=proposal['source_configuration'];old=_zone(source,proposal['zone_uuid'])
        if _settings(old)!=cfg or owner._shape_identity(old.Outline(),time.monotonic()+10.)[0]!=proposal['source_outline_sha256']:
            raise owner.Refused('actual_source_bank_owner_changed')
        pads,tracks=_enclosed(source,old,time.monotonic()+10.)
        if pads!=[r['uuid'] for r in proposal['source_pad_rows']] or tracks!=[r['uuid'] for r in proposal['source_track_rows']]:
            raise owner.Refused('source_bank_enclosed_inventory_changed')
        _,old_pads,old_tracks,_,_,_=_native_rows(source,pads,tracks,cfg['layer_id'],proposal['policy'],time.monotonic()+10.)
        _source_fill(source,old,pads,tracks,cfg['layer_id'],proposal['policy'],time.monotonic()+10.)
        if old_pads!=proposal['source_pad_rows'] or old_tracks!=proposal['source_track_rows']:
            raise owner.Refused('source_bank_native_rows_changed')
        if (_dims(old_pads,{'position_nm','orientation_deg','geometry_sha256'})!=_dims(proposal['candidate_pad_rows'],{'position_nm','orientation_deg','geometry_sha256'})
                or _dims(old_tracks,{'start_nm','end_nm'})!=_dims(proposal['candidate_track_rows'],{'start_nm','end_nm'})):
            raise owner.Refused('saved_bank_source_dimensions_changed')
        declared=dict(schema=1,scope='native_solid_pad_bank_not_current_or_release_qualification',
            source_pads=proposal['candidate_pad_rows'],retained_source_tracks=(
                proposal['candidate_track_rows'] if proposal['cover_extent']=='pad_row_and_retained_leads' else []),
            layer_id=cfg['layer_id'],net=cfg['net'],polygon_nm=proposal['polygon_nm'],
            actual_fill_envelope_nm=proposal['fill_envelope_nm'],clearance_nm=cfg['clearance_nm'],
            min_thickness_nm=cfg['min_thickness_nm'],envelope_policy=proposal['policy'],actual_chamfer_nm=proposal['actual_chamfer_nm'],
            source_conductors_retained=True,new_capacity_credited=False,release_authority=False)
        declared['plan_sha256']=owner._digest(declared)
        proof=bank.receive(candidate,declared,_uid(z));result['native_filled_bank_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise owner.Refused(str(proof))
        result.update(ok=True,complete=True,source_complete_bank_received=True)
    except Exception as exc:result['errors']=[type(exc).__name__+':'+str(exc)]
    return result
