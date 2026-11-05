"""Retire a dominated local Ground dogbone, not a functional plane stitch.

Only one exact, generated small through barrel and its single capacitor
departure can be removed. A shorter existing, same-land, source-qualified
dogbone and every actual reference-plane contact must remain. No new copper,
pose, process exception, inferred current rating or release authority.
"""
from pathlib import Path
import hashlib
import tempfile
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_device_bypass as caps
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_dead_end_tail as tails
import cec_ground_return_preservation as returns
import cec_redundant_local_ground_return as kernel
import cec_route_quality as quality
import cec_stale_local_ground_via as stale
from cec_native_items import discard_items


def _groups(board,retired=()):
    retired=set(retired)
    return sorted((force._uid(g),g.GetName(),bool(g.IsLocked()),
        tuple(sorted(force._uid(i) for i in g.GetItems() if force._uid(i) not in retired)))
        for g in board.Groups())


def _binding(board):
    return hashlib.sha256(repr((kernel._binding(board),_groups(board))).encode()).hexdigest()


def _qualified_root(board,via):
    # Ordinary diameter/drill compliance never permits a partial SMD overlap.
    return stale._qualified_bridge(board,via) and fab.via_at_pad_conflicts(board,
        via.GetPosition(),via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())[0] is None


def _direct(board, via):
    tracks=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
        and t.GetNetCode()==via.GetNetCode()
        and tuple(via.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd()))
        and int(t.GetLayer()) in (pcbnew.F_Cu,pcbnew.B_Cu)]
    choices=[]
    for track in tracks:
        ends=[tuple(track.GetStart()),tuple(track.GetEnd())]
        other=ends[1] if ends[0]==tuple(via.GetPosition()) else ends[0]
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if (pad.GetNetCode()==via.GetNetCode()
                        and tuple(pad.GetPosition())==other
                        and cells.cec_return_escape.smd_surface_layer(pad)==track.GetLayer()):
                    choices.append((pad,track))
    if len(choices)!=1:
        raise ValueError('one_literal_direct_surface_ground_land_departure_required')
    return choices[0]


def plan(board,source,via_uuid,retained_via_uuid,*,allow_source_locked=False,timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if (any(type(u) is not str or not u for u in (via_uuid,retained_via_uuid))
            or via_uuid==retained_via_uuid or type(allow_source_locked) is not bool):
        raise ValueError('explicit_distinct_source_ground_dogbones_required')
    source=Path(source).resolve();binding=_binding(board)
    private=pcbnew.LoadBoard(str(source))
    if binding!=_binding(private):
        raise ValueError('ground_dogbone_requires_exact_saved_native_source')
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(tracks)+len(pads)+len(list(board.Zones()))>16384:
        raise ValueError('ground_dogbone_native_inventory_bound')
    live={force._uid(t):t for t in tracks}
    via,retained=live.get(via_uuid),live.get(retained_via_uuid)
    for item in (via,retained):
        if (item is None or item.GetClass()!='PCB_VIA' or item.GetNetname()!='GND'
                or item.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or item.TopLayer()!=pcbnew.F_Cu or item.BottomLayer()!=pcbnew.B_Cu):
            raise ValueError('literal_source_ground_through_barrels_required')
    groups=[g for g in board.Groups() if g.ContainsItem(via)]
    ordinary=fab.board_legal_through_via_geometry(board,
        via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6)
    if (len(groups)!=1 or groups[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
            or groups[0].IsLocked() or via.IsLocked() and not allow_source_locked
            or via.GetWidth(via.TopLayer())>=round(ordinary[0]*1e6)
               and via.GetDrillValue()>=round(ordinary[1]*1e6)
            or not fab.local_pofv_via_decision(board,via)[0]
            or not _qualified_root(board,retained)):
        raise ValueError('generated_local_barrel_and_unchanged_qualified_retained_root_required')
    pad,lead=_direct(board,via);other_pad,keep=_direct(board,retained)
    if force._uid(pad)!=force._uid(other_pad) or force._uid(lead)==force._uid(keep):
        raise ValueError('two_distinct_dogbones_owned_by_the_same_actual_land_required')
    fp=pad.GetParentFootprint();members=list(fp.Pads());farads=caps.capacitance_f(fp.GetValue())
    if (fp.IsDNP() or len(members)!=2 or not caps.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
            or farads is None or not 0<farads<=1e-3
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in members)
            or len([p for p in members if p.GetNetname()=='GND'])!=1):
        raise ValueError('populated_two_land_local_capacitor_ground_owner_required')
    face=int(lead.GetLayer());floor=max(200000,board.GetDesignSettings().m_TrackMinWidth,
        int(cells._netclass(board,'GND')['width']))
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    for track,barrel in ((lead,via),(keep,retained)):
        if (track.GetLayer()!=face or force._uid(track) in grouped or track.HasSolderMask()
                or track.IsLocked() and not allow_source_locked
                or not floor<=track.GetWidth()<=350000 or not 0<track.GetLength()<=1500000
                or not quality.is_canonical_stroke(tuple(track.GetStart()),tuple(track.GetEnd()),tolerance_nm=0)
                or not fab.local_pofv_dogbone_matches(pad,pad.GetPosition(),barrel.GetPosition(),face,pad.GetNetCode())):
            raise ValueError('bounded_full_class_source_dogbones_with_explicit_lock_authority_required')
    if keep.GetLength()>=lead.GetLength()-10000:
        raise ValueError('strictly_shorter_retained_ground_dogbone_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('ground_dogbone_native_deadline')
    # No retained terminal, inner departure or structural stitch is silently
    # retired. The old barrel can touch exactly its one outer departure.
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    for item in [*pads,*tracks]:
        tick();uid=force._uid(item)
        if uid==via_uuid:continue
        touches=[l for l in layers if item.IsOnLayer(l)
            and item.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0)]
        if touches and (uid!=force._uid(lead) or touches!=[face]):
            raise ValueError('retired_ground_barrel_has_another_native_contact')
        if uid in {force._uid(lead),force._uid(pad),via_uuid}:continue
        if item.IsOnLayer(face) and item.GetEffectiveShape(face).Collide(lead.GetEffectiveShape(face),0):
            if uid!=force._uid(keep):
                raise ValueError('retired_ground_departure_has_another_native_contact')
            # The two departures may join only inside their actual common
            # land, never at an unowned external route/body junction.
            a=pcbnew.SHAPE_POLY_SET();b=pcbnew.SHAPE_POLY_SET()
            lead.TransformShapeToPolygon(a,face,0,1,pcbnew.ERROR_OUTSIDE)
            keep.TransformShapeToPolygon(b,face,0,1,pcbnew.ERROR_OUTSIDE)
            a.BooleanIntersection(b);a.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
            if a.OutlineCount():raise ValueError('dogbone_join_outside_actual_owner_land')
    for zone in board.Zones():
        tick()
        if zone.GetIsRuleArea() or not zone.IsOnLayer(face):continue
        if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
            if zone.Outline().Collide(lead.GetEffectiveShape(face),0):
                raise ValueError('retired_dogbone_surface_fill_unknown')
        elif zone.GetFilledPolysList(face).Collide(lead.GetEffectiveShape(face),0):
            raise ValueError('retired_dogbone_has_surface_zone_contact')
    discard_items(private,[t for t in private.GetTracks() if force._uid(t)==force._uid(lead)])
    isolated=stale.plan(private,via_uuid,allow_source_locked=allow_source_locked,
        max_bridge_mm=3.,timeout_s=max(.001,deadline-time.monotonic()))
    if isolated['retained_root_via_uuid']!=retained_via_uuid:
        raise ValueError('requested_retained_dogbone_must_own_actual_all_plane_bridge')
    tick()
    return dict(schema=1,kind='dominated_generated_local_ground_dogbone',source_binding=binding,
        source_sha256=force._hash(source),via_uuid=via_uuid,retained_via_uuid=retained_via_uuid,
        retained_root_via_uuid=retained_via_uuid,allow_source_locked=allow_source_locked,ground_net='GND',
        retired_track_uuids=sorted([force._uid(lead),via_uuid]),retired_via_uuids=[via_uuid],
        obsolete_surface_track_uuids=[force._uid(lead)],source_kernel_length_mm=lead.GetLength()/1e6,
        retained_departure_uuid=force._uid(keep),retained_departure_length_mm=keep.GetLength()/1e6,
        owner_pad_uuid=force._uid(pad),source_minus_departure_stale_barrel_proof=isolated,
        actual_contact_plane_ids=isolated['actual_contact_plane_ids'],source_diameter_nm=via.GetWidth(via.TopLayer()),
        no_new_copper_holes_or_poses=True,ordinary_ground_stitch_retirement_authorized=False,
        current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,board.GetFileName(),proposal['via_uuid'],proposal['retained_via_uuid'],
        allow_source_locked=proposal['allow_source_locked'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('stale_or_forged_dominated_ground_dogbone_plan')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in fresh['retired_track_uuids']])


def discover(board,source,*,allow_source_locked=False,maximum_candidates=4,timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if (type(allow_source_locked) is not bool or type(maximum_candidates) is not int
            or not 1<=maximum_candidates<=8):
        raise ValueError('bounded_source_ground_dogbone_discovery_required')
    if (len(list(board.GetTracks()))+sum(f.GetPadCount() for f in board.GetFootprints())
            +len(list(board.Zones()))>16384):
        raise ValueError('ground_dogbone_native_inventory_bound')
    grouped={force._uid(i) for g in board.Groups()
        if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP and not g.IsLocked() for i in g.GetItems()}
    vias=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND']
    if len(vias)>1024:raise ValueError('ground_dogbone_discovery_inventory_bound')
    by_pad={};refused=[];plans=[];pairs=[]
    for via in vias:
        if time.monotonic()>=deadline:break
        try:pad,track=_direct(board,via)
        except ValueError:continue
        by_pad.setdefault(force._uid(pad),[]).append((via,track))
    for rows in by_pad.values():
        for via,lead in rows:
            if force._uid(via) not in grouped:continue
            for root,keep in rows:
                gain=lead.GetLength()-keep.GetLength()
                if force._uid(via)!=force._uid(root) and gain>10000:
                    pairs.append((-gain,force._uid(via),force._uid(root)))
    if len(pairs)>128:raise ValueError('ground_dogbone_discovery_pair_bound')
    examined=0
    for _,old,root in sorted(pairs):
        if time.monotonic()>=deadline or len(plans)>=maximum_candidates:break
        examined+=1
        try:
            plans.append(plan(board,source,old,root,allow_source_locked=allow_source_locked,
                timeout_s=max(.001,deadline-time.monotonic())))
        except ValueError as exc:refused.append(dict(via_uuid=old,retained_via_uuid=root,reason=str(exc)))
    return dict(plans=plans,refused=refused,pairs_examined=examined,
        complete=time.monotonic()<deadline and examined==len(pairs),source_mutated=False,
        candidate_inventory_complete=time.monotonic()<deadline and examined==len(pairs),
        no_path_or_full_board_finishing_certificate=False,release_authority=False)


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    r=tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
    if r['ok'] and r['complete']:
        try:
            before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
            # KiCad omits empty groups when saving. Compare an independently
            # serialized exact subtraction, not a guessed membership waiver.
            with tempfile.TemporaryDirectory(prefix='cec-dominated-ground-groups-') as work:
                expected=pcbnew.LoadBoard(str(source))
                discard_items(expected,[t for t in expected.GetTracks()
                    if force._uid(t) in proposal['retired_track_uuids']])
                path=force._copy_family(Path(source),Path(work)/'expected')
                field._save_field_snapshot(expected,path)
                if _groups(pcbnew.LoadBoard(str(path)))!=_groups(after):
                    raise ValueError('ground_dogbone_unowned_group_or_factory_context_change')
            root=next(v for v in after.GetTracks() if force._uid(v)==proposal['retained_via_uuid'])
            old=next(v for v in before.GetTracks() if force._uid(v)==proposal['via_uuid'])
            if not _qualified_root(after,root):raise ValueError('retained_dogbone_factory_context_lost')
            proof=stale._witnesses(after,old,root,set(proposal['actual_contact_plane_ids']),
                proposal['source_diameter_nm'],deadline)
            if {p['layer'] for p in proof}!=set(proposal['actual_contact_plane_ids']):
                raise ValueError('retained_dogbone_actual_plane_bridge_lost_after_refill')
            ground=returns.receive(before,after,timeout_s=max(.001,deadline-time.monotonic()))
            if not ground['ok'] or not ground['complete']:
                raise ValueError('dominated_dogbone_cut_worsened_a_known_ground_return')
            r.update(actual_saved_reference_plane_bridges=proof,all_known_ground_returns=ground,
                no_new_copper_holes_or_poses=True,retired_via_uuids=proposal['retired_via_uuids'],
                removed_surface_copper_mm=proposal['source_kernel_length_mm'])
        except (ValueError,RuntimeError,StopIteration) as exc:
            r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
