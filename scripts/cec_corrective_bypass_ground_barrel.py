"""Exclusive corrective capacitor-to-plane Ground barrel replacement only.

Not a general via mover, copper window, current qualification or admission.
The fresh missing-bypass transition and independent saved leaf own their own
roles. Every other return, native DRC and physical/current gate remains due.
"""
import copy
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as syntax
import cec_fab_profile as fab
import cec_force_current as force
import cec_missing_bypass_repair as repair
import cec_native_partition_pair as partitions

SCOPE='exclusive_corrective_missing_bypass_Ground_barrel-v1'


def _need(ok,reason):
    if not ok:raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10,
        'bounded_corrective_barrel_lease_required')
    return time.monotonic()+seconds


def _left(deadline):
    left=deadline-time.monotonic()
    _need(left>0,'corrective_barrel_deadline')
    return min(10.,left)


def _wire(value):
    def encode(value):
        if isinstance(value,(set,frozenset)):return sorted(value,key=repr)
        raise TypeError('unsupported_corrective_barrel_record')
    return json.loads(json.dumps(value,sort_keys=True,allow_nan=False,default=encode))


def _objects(board,pad_uuid,via_uuid):
    pads=[p for fp in board.GetFootprints()for p in fp.Pads()]
    tracks=list(board.GetTracks())
    _need(len(pads)+len(tracks)<=16384,'corrective_barrel_native_inventory_bound')
    found=[p for p in pads if force._uid(p)==pad_uuid]
    vias=[v for v in tracks if force._uid(v)==via_uuid]
    _need(len(found)==len(vias)==1 and vias[0].GetClass()=='PCB_VIA',
        'unique_corrective_Ground_pad_and_barrel_required')
    return found[0],vias[0],pads+tracks


def _geometry(board,via):
    faces=tuple(board.GetEnabledLayers().CuStack())
    _need(via.GetViaType()==pcbnew.VIATYPE_THROUGH
        and via.TopLayer()==pcbnew.F_Cu and via.BottomLayer()==pcbnew.B_Cu
        and via.Padstack().Mode()==pcbnew.PADSTACK.MODE_NORMAL
        and all(via.IsOnLayer(f)for f in faces)
        and not any(via.IsBackdrilledOrPostMachined(f)for f in faces),
        'ordinary_uniform_full_through_corrective_barrel_required')
    widths={int(via.GetWidth(f))for f in faces};drill=int(via.GetDrillValue())
    _need(len(widths)==1 and 0<drill<min(widths),'positive_uniform_corrective_barrel_required')
    width=next(iter(widths))
    dia,hole,_=fab.board_legal_through_via_geometry(board,width/1e6,drill/1e6)
    _need(width>=round(dia*1e6)and drill>=round(hole*1e6),
        'source_corrective_barrel_process_dimensions_unknown')
    return faces,width,drill


def _contacts(board,pad,via,deadline):
    faces,width,drill=_geometry(board,via)
    pad_uid=force._uid(pad);via_uid=force._uid(via)
    _need(pad.GetNetname()==via.GetNetname()=='GND'and pad.GetNetCode()>0
        and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not pad.HasHole(),
        'actual_corrective_capacitor_Ground_net_required')
    _,_,objects=_objects(board,pad_uid,via_uid);touched=False
    for item in objects:
        _left(deadline)
        if force._uid(item)==via_uid:continue
        hit=any(item.IsOnLayer(f)and item.GetEffectiveShape(f).Collide(via.GetEffectiveShape(f),0)
            for f in faces)
        if not hit:continue
        _need(item==pad,'corrective_barrel_has_other_pad_track_or_barrel_contact:'+force._uid(item))
        touched=True
    _need(touched,'corrective_barrel_must_touch_its_actual_Ground_pad')
    plane=[]
    for zone in board.Zones():
        if zone.GetIsRuleArea():continue
        _left(deadline)
        for face in faces:
            if not zone.IsOnLayer(face):continue
            fill=zone.GetFilledPolysList(face)
            if not fill.OutlineCount():continue
            copper=pcbnew.SHAPE_POLY_SET()
            via.TransformShapeToPolygon(copper,face,0,1,pcbnew.ERROR_INSIDE,False)
            hole=pcbnew.SHAPE_POLY_SET()
            via.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
            copper.BooleanSubtract(hole)
            if not partitions._positive_overlap(copper,fill,deadline):continue
            _need(zone.GetNetname()=='GND','corrective_barrel_touches_foreign_saved_fill')
            plane.append(dict(zone_uuid=force._uid(zone),layer_id=int(face)))
    _need(any(r['layer_id']not in(pcbnew.F_Cu,pcbnew.B_Cu)for r in plane),
        'positive_saved_internal_Ground_reference_contact_required')
    return sorted(plane,key=lambda r:(r['layer_id'],r['zone_uuid']))


def _via_process(path,uid):
    _,nodes=syntax._nodes(path)
    _need(uid in nodes and nodes[uid][0]=='via','literal_corrective_via_required')
    return [n for n in nodes[uid]if not(isinstance(n,list)and n and n[0]in('uuid','at'))]


def _context(source,intent,ground_pad_uuid,via_uuid,hint,consent,deadline):
    source=Path(source).resolve(strict=True);digest=force._hash(source)
    role=repair.plan(source,intent,board_hint=hint,timeout_s=_left(deadline))
    board=pcbnew.LoadBoard(str(source));pad,via,_=_objects(board,ground_pad_uuid,via_uuid)
    records=[p for p in role['source_capacitor_ports']if p['uuid']==ground_pad_uuid and p['net']=='GND']
    _need(len(records)==1 and force._uid(pad.GetParentFootprint())==intent['capacitor_uuid']
        and records[0]['at_nm']==list(pad.GetPosition()),'exact_fresh_corrective_Ground_port_required')
    _need(consent is None or consent==via_uuid,'only_exact_locked_corrective_via_consent_required')
    _need(not via.IsLocked()or consent==via_uuid,'explicit_locked_corrective_via_consent_required')
    _need(not any(g.ContainsItem(via)for g in board.Groups()),'grouped_corrective_barrel_refused')
    _need(math.dist(tuple(pad.GetPosition()),tuple(via.GetPosition()))<=2000000,
        'bounded_source_corrective_pad_barrel_relation_required')
    contacts=_contacts(board,pad,via,deadline)
    proof=dict(scope=SCOPE,source=str(source),source_sha256=digest,board_hint=hint,
        missing_bypass_intent=copy.deepcopy(intent),corrective_role=repair._replay_identity(role),
        ground_pad_uuid=ground_pad_uuid,via_uuid=via_uuid,allow_locked_via_uuid=consent,
        source_via_at_nm=list(via.GetPosition()),source_reference_contacts=contacts,
        via_process=_via_process(source,via_uuid),source_family=force._family(source,hint),
        code_identity=force._code_identity(),complete=True,barrel_only=True,
        other_material_cut_authority=False,current_qualified=False,admitted=False)
    _need(force._hash(source)==digest and force._code_identity()==role['code_identity']
        and force._family(source,hint)==role['source_family'],
        'corrective_barrel_source_changed')
    return _wire(proof),board,role


def plan(source,missing_bypass_intent,ground_pad_uuid,via_uuid,*,board_hint,
         allow_locked_via_uuid=None,timeout_s=10.):
    deadline=_deadline(timeout_s)
    proof,_,_=_context(source,missing_bypass_intent,ground_pad_uuid,via_uuid,board_hint,
        allow_locked_via_uuid,deadline)
    _left(deadline)
    return proof


def receive(source,candidate,proposal,new_via_uuid,*,board_hint,
            retired_supply_track_uuids=(),timeout_s=10.):
    deadline=_deadline(timeout_s)
    fresh,parent,role=_context(source,proposal['missing_bypass_intent'],proposal['ground_pad_uuid'],
        proposal['via_uuid'],board_hint,proposal['allow_locked_via_uuid'],deadline)
    _need(fresh==proposal,'corrective_barrel_requires_exact_fresh_source_replay')
    candidate=Path(candidate).resolve(strict=True);digest=force._hash(candidate)
    child=pcbnew.LoadBoard(str(candidate));old_id=proposal['via_uuid']
    _need(type(new_via_uuid)is str and new_via_uuid and new_via_uuid!=old_id
        and not any(force._uid(t)==old_id for t in child.GetTracks())
        and not any(force._uid(t)==new_via_uuid for t in parent.GetTracks()),
        'exact_old_barrel_retirement_and_new_identity_required')
    pad,via,_=_objects(child,proposal['ground_pad_uuid'],new_via_uuid)
    _need(not any(g.ContainsItem(via)for g in child.Groups()),'grouped_new_corrective_barrel_refused')
    _need(_via_process(candidate,new_via_uuid)==proposal['via_process'],
        'corrective_barrel_all_native_process_and_geometry_must_match')
    _need(math.dist(tuple(via.GetPosition()),tuple(proposal['source_via_at_nm']))<=1000000,
        'corrective_barrel_replacement_displacement_exceeded')
    ok,reason=fab.via_pad_decision(child,pad,via.GetPosition(),via.GetWidth(pad.GetLayer()),
        via.GetDrillValue(),via.GetNetCode())
    _need(ok,'corrective_new_barrel_full_pad_containment_and_process_required:'+reason)
    contacts=_contacts(child,pad,via,deadline)
    _need({r['layer_id']for r in contacts}>={r['layer_id']for r in proposal['source_reference_contacts']},
        'corrective_barrel_lost_source_Ground_reference_face')
    _need(type(retired_supply_track_uuids)in(list,tuple,set)and
        len(retired_supply_track_uuids)==len(set(retired_supply_track_uuids)),
        'exact_corrective_supply_retirement_inventory_required')
    retired=set(retired_supply_track_uuids)
    if retired:
        import cec_measurement_leaf as leaf
        old_cap=parent.FindFootprintByReference(role['capacitor_ref'])
        supply=next(p for p in old_cap.Pads()if p.GetNetname()==role['requirement']['rail'])
        owned=leaf.plan_missing_bypass_supply(parent,force._uid(supply),board_hint=board_hint,
            missing_bypass_intent=proposal['missing_bypass_intent'],timeout_s=_left(deadline))
        _need(retired==set(owned['track_uuids']),'only_independently_owned_corrective_supply_leaf_may_be_retired')
    role_receiving=repair.receive(source,candidate,role,board_hint=board_hint,timeout_s=_left(deadline))
    old_cap=parent.FindFootprintByReference(role['capacitor_ref'])
    new_cap=child.FindFootprintByReference(role['capacitor_ref'])
    rebindings={force._item_key(new_cap.FindPadByNumber(p.GetNumber())):force._item_key(p)
        for p in old_cap.Pads()}
    physical=partitions.compare(parent,child,timeout_s=_left(deadline),
        retired_uuids=retired|{old_id},identity_rebindings=rebindings)
    _need(physical['available']is True and physical['preserved']is True,
        'corrective_barrel_retained_native_terminal_and_copper_partitions_changed')
    _need(digest==force._hash(candidate)and force._hash(source)==proposal['source_sha256']
        and force._family(source,board_hint)==proposal['source_family']
        and force._code_identity()==proposal['code_identity'],'corrective_barrel_receiving_epoch_changed')
    _left(deadline)
    return _wire(dict(scope=SCOPE,ok=True,complete=True,barrel_only=True,source_sha256=proposal['source_sha256'],
        candidate_sha256=digest,new_via_uuid=new_via_uuid,source_reference_contacts=proposal['source_reference_contacts'],
        candidate_reference_contacts=contacts,corrective_role_receiving=role_receiving,
        retained_native_partitions=physical,all_other_returns_require_independent_receiving=True,
        other_material_cut_authority=False,current_qualified=False,admitted=False))
