"""Source-owned local copper reconstruction after a repeated-cell row move.

This is a bounded pre-routing transaction, not additive routing admission.
Every surviving unrelated object and every power trunk/barrel stays exact.
Moved power terminals explicitly invalidate the old power/placement receipts.
Local reconstruction must not disguise a power-port move as ordinary routing.
"""
import json
import hashlib
import math
from pathlib import Path
import shutil

import pcbnew
import cec_cell_copper_preflight as preflight
import cec_local_copper_cell as local
import cec_pad_incident_tracks as incident
import cec_force_current as force
import cec_route_placement_admission as placement
from cec_native_items import discard_items


def _source_binding(board):
    import cec_field_coupling as field
    payload=(sorted(field._field_snapshot_inventory(board).items()),
        sorted(placement._population(board).items()),
        sorted((force._uid(g),g.GetName(),sorted(force._uid(i) for i in g.GetItems()))
               for g in board.Groups()),
        sorted((fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees(),fp.IsLocked())
               for fp in board.GetFootprints()))
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def _target_chain_conflicts(board,poses,cells,retired,*,max_checks=2_000_000):
    """A source-owned rigid route is not automatically legal at its new seat."""
    import cec_decoupler_cell as cell
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    clones={}
    for spec in cells.values():
        for uid in spec['uuids']:
            # PCB_TRACK(source_track) selects the parent-taking overload in
            # KiCad 10 SWIG, NOT a geometric copy: it produces a zero-length
            # unnetted track at the origin. Construct this diagnostic native
            # shape explicitly and bind the original physical/net identity.
            source=tracks[uid];dx,dy=spec['delta_nm']
            obj=pcbnew.PCB_TRACK(board);obj.SetLayer(source.GetLayer())
            obj.SetStart(pcbnew.VECTOR2I(source.GetStart().x+dx,source.GetStart().y+dy))
            obj.SetEnd(pcbnew.VECTOR2I(source.GetEnd().x+dx,source.GetEnd().y+dy))
            obj.SetWidth(source.GetWidth());obj.SetNetCode(source.GetNetCode())
            clones[uid]=obj
    if type(max_checks) is not int or not 1<=max_checks<=4_000_000:
        raise ValueError('bounded_destination_copper_checks_required')
    blockers={};minimum=int(board.GetDesignSettings().m_MinClearance);checked=0
    classes={}
    def gap(net):
        if net not in classes:classes[net]=max(minimum,int(cell._netclass(board,net)['clearance']))
        return classes[net]
    # Rotate diagnostic copies, never the SOURCE owner. Native integer pad
    # coordinates need not survive a non-cardinal rotate-and-restore round
    # trip exactly; planning must not change even one nanometre of source.
    future_owners=[];pads=[]
    for ref,fp in fps.items():
        if ref in poses:
            fp=pcbnew.FOOTPRINT(fp);future_owners.append(fp)
            target=poses[ref]
            fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
            fp.SetOrientationDegrees(target[2])
        pads.extend(fp.Pads())
    for uid,track in clones.items():
        layer=track.GetLayer();shape=track.GetEffectiveShape(layer);own=str(track.GetNetname())
        for other_uid,other in [*[(force._uid(p),p) for p in pads],
                *[(u,clones.get(u,t)) for u,t in tracks.items() if u not in retired and u!=uid]]:
            checked+=1
            if checked>max_checks:raise ValueError('native_destination_copper_budget_exhausted')
            if ((track.GetNetCode()>0 and other.GetNetCode()==track.GetNetCode())
                    or not other.IsOnLayer(layer)):continue
            if shape.Collide(other.GetEffectiveShape(layer),max(gap(own),gap(other.GetNetname()))):
                blockers.setdefault(uid,[]).append(dict(uuid=other_uid,
                    kind=other.GetClass(),net=other.GetNetname(),layer=board.GetLayerName(layer)))
        for zone in board.Zones():
            checked+=1
            if checked>max_checks:raise ValueError('native_destination_copper_budget_exhausted')
            if not zone.IsOnLayer(layer):continue
            if zone.GetIsRuleArea():
                if zone.GetDoNotAllowTracks() and shape.Collide(zone.Outline(),0):
                    blockers.setdefault(uid,[]).append(dict(uuid=force._uid(zone),kind='native_track_keepout'))
            elif zone.GetNetCode()!=track.GetNetCode():
                if not zone.IsFilled():
                    blockers.setdefault(uid,[]).append(dict(uuid=force._uid(zone),kind='foreign_zone_fill_unknown'))
                elif shape.Collide(zone.GetFilledPolysList(layer),max(gap(own),zone.GetLocalClearance())):
                    blockers.setdefault(uid,[]).append(dict(uuid=force._uid(zone),kind='foreign_filled_zone',
                        net=zone.GetNetname(),layer=board.GetLayerName(layer)))
    return blockers


def retained_power_items(board, domains, *, minimum_trunk_width_mm=.75):
    """Planning-only exact native power trunks and their attached barrels.

    A power-net name alone does not make every low-current consumer's via a
    force-current field. Those other objects still require owned restoration;
    absence here never authorizes deleting them or certifies their load.
    """
    if not math.isfinite(minimum_trunk_width_mm) or not .5<=minimum_trunk_width_mm<=2:
        raise ValueError('bounded_power_trunk_screen_width_required')
    nets=set(domains)
    wide=[t for t in board.GetTracks() if t.GetClass() in ('PCB_TRACK','PCB_ARC') and t.IsLocked()
          and t.GetNetname() in nets and t.GetWidth()>=round(minimum_trunk_width_mm*1e6)]
    ids={force._uid(t) for t in wide}
    for via in board.GetTracks():
        if via.GetClass()!='PCB_VIA' or via.GetNetname() not in nets:continue
        if any(via.GetNetCode()==t.GetNetCode() and via.IsOnLayer(t.GetLayer())
               and via.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(t.GetLayer()),0)
               for t in wide):ids.add(force._uid(via))
    return sorted(ids)


def plan(board, poses, cells, *, protected_nets=(), allow_owned_locked=False,
         max_tracks=256, maximum_local_length_mm=8.,maximum_pad_leg_length_mm=None,
         allow_cardinal_rotations=False,allow_octilinear_rotations=False,reference_group_uuids=(),
         maximum_reference_translation_mm=10.,maximum_translation_mm=64.):
    """Derive local edge ownership from immutable native source pad contacts.

    Locked local branches can be recompiled only when explicitly requested.
    That permission is object-scoped: no grouped edge, current/pair net, wide
    trunk, interior tap or shared surviving pad contact becomes removable.
    External cut boundaries remain restoration obligations. Original terminal
    partitions, rated power and native DRC still decide final admission.
    """
    if (not poses or len(poses)>64 or type(allow_owned_locked) is not bool
            or type(allow_cardinal_rotations) is not bool or type(allow_octilinear_rotations) is not bool
            or type(max_tracks) is not int or not 1<=max_tracks<=256
            or not math.isfinite(maximum_local_length_mm) or not 0<maximum_local_length_mm<=8):
        raise ValueError('bounded_explicit_cell_recompile_policy_required')
    # Finite native work reach only. Higher-level Source compilers still
    # independently enforce the bound of EACH positive part role. The old
    # 64-mm default is unchanged; a distant, already typed additional cap
    # must explicitly carry its larger construction reach through this layer.
    if (type(maximum_translation_mm) not in (int,float) or not math.isfinite(maximum_translation_mm)
            or not 0<maximum_translation_mm<=128.):
        raise ValueError('bounded_explicit_native_cell_translation_required')
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    if len(fps)!=len(list(board.GetFootprints())) or not set(poses)<=fps.keys():
        raise ValueError('source_cell_identity_missing_or_ambiguous')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (type(reference_group_uuids) not in (list,tuple) or len(reference_group_uuids)>8
            or len(set(reference_group_uuids))!=len(reference_group_uuids)
            or any(type(u)is not str or not u for u in reference_group_uuids)):
        raise ValueError('explicit_source_reference_group_uuid_scope_required')
    reference_transports={}
    if reference_group_uuids:
        import cec_source_reference_group_transport as reference_transport
        for uid in reference_group_uuids:
            g=next((g for g in board.Groups() if force._uid(g)==uid),None)
            members=[] if g is None else [i for i in g.GetItems() if i.GetClass()=='FOOTPRINT']
            if len(members)!=1 or members[0].GetReference() not in poses:
                raise ValueError('requested_reference_group_must_own_selected_cell')
            fp=members[0]
            proof=reference_transport.inspect(board.GetFileName(),owner_uuid=force._uid(fp),group_uuid=uid)
            turn=(poses[fp.GetReference()][2]-fp.GetOrientationDegrees())%360
            if turn%90 or turn and not allow_cardinal_rotations:
                raise ValueError('source_reference_group_explicit_cardinal_rotation_required')
            reference_transports[fp.GetReference()]=proof
    binding=_source_binding(board)
    if maximum_pad_leg_length_mm is None:
        bounds=board.GetBoardEdgesBoundingBox()
        maximum_pad_leg_length_mm=max(maximum_local_length_mm,
            math.hypot(bounds.GetWidth(),bounds.GetHeight())/1e6)
    if (type(maximum_pad_leg_length_mm) not in (float,int)
            or not math.isfinite(maximum_pad_leg_length_mm)
            or not 0<maximum_pad_leg_length_mm<=512):
        raise ValueError('bounded_native_pad_leg_span_required')
    oldposes={};deltas={};rotations={}
    for ref,target in poses.items():
        fp=fps[ref];at=fp.GetPosition();angle=fp.GetOrientationDegrees()
        if (fp.IsLocked() or force._uid(fp) in grouped and ref not in reference_transports or len(target)!=3
                or not all(math.isfinite(v) for v in target)):
            raise ValueError('unlocked_translation_only_cell_poses_required')
        turn=(target[2]-angle)%360
        if not any(abs(turn-v)<1e-5 for v in (0.,360.)):
            permitted=(allow_cardinal_rotations and any(abs(turn-v)<1e-5 for v in (90.,180.,270.)))
            permitted|=allow_octilinear_rotations and any(abs(turn-v)<1e-5 for v in range(45,360,45))
            if (not permitted
                    or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())):
                raise ValueError('explicit_surface_cardinal_rotation_required')
        rotations[ref]=turn if turn<359.99999 else 0.
        oldposes[ref]=[at.x/1e6,at.y/1e6,angle]
        delta=[round(target[i]*1e6)-int((at.x,at.y)[i]) for i in (0,1)]
        if math.hypot(*delta)>maximum_translation_mm*1e6:raise ValueError('cell_translation_budget')
        deltas[ref]=delta
    membership={};cell_deltas={}
    for name,refs in cells.items():
        if not refs or len(refs)>32 or len(set(refs))!=len(refs) or not set(refs)<=poses.keys():
            raise ValueError('complete_unique_moving_cell_membership_required')
        # This opt-in tier recompiles external pad legs, not an assumed
        # rotation of internal copper between multiple footprint owners.
        # A later joint rigid-cell implementation needs its own source proof.
        if any(rotations[r] for r in refs) and len(refs)!=1:
            raise ValueError('rotated_cell_requires_single_native_owner')
        transforms={tuple(deltas[r]) for r in refs}
        if len(transforms)!=1:raise ValueError('declared_cell_not_rigid')
        for ref in refs:
            if ref in membership:raise ValueError('overlapping_declared_cells')
            membership[ref]=name
        cell_deltas[name]=list(next(iter(transforms)))
    pads=[p for ref in poses for p in fps[ref].Pads()]
    source=incident.inspect(board,pads)
    if not source['ok']:raise ValueError('native_source_pad_incidence_unknown')
    targetpads={}
    for ref,target in poses.items():
        detached=pcbnew.FOOTPRINT(fps[ref])
        detached.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        detached.SetOrientationDegrees(target[2])
        for pad in detached.Pads():
            targetpads[force._uid(pad)]=(detached,pad)
    items={force._uid(t):t for t in board.GetTracks()}
    protected=set(protected_nets)
    small={uid for uid,t in items.items() if t.GetClass()=='PCB_TRACK'
        and uid not in grouped and str(t.GetNetname()) not in protected
        and 0<t.GetWidth()<500000 and t.GetLength()/1e6<=maximum_pad_leg_length_mm
        and (not t.IsLocked() or allow_owned_locked)}
    allpads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.IsOnCopperLayer()]
    def cut_is_endpoint_owned(row):
        edge=items[row['track_uuid']];layer=edge.GetLayer();shape=edge.GetEffectiveShape(layer)
        contact=tuple(row['contact_nm']);far=tuple(row['far_nm'])
        for pad in allpads:
            if (pad.GetParentFootprint().GetReference() in poses or not pad.IsOnLayer(layer)
                    or not shape.Collide(pad.GetEffectiveShape(layer),0)):continue
            # A real fixed pad at the surviving far endpoint is an explicit
            # restoration boundary. An unowned interior tap is not removable.
            if not pad.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*far),0):return False
        for other in items.values():
            if (force._uid(other)==row['track_uuid'] or other.GetNetCode()!=edge.GetNetCode()
                    or not other.IsOnLayer(layer) or not shape.Collide(other.GetEffectiveShape(layer),0)):continue
            if other.GetClass()=='PCB_VIA':
                if not any(other.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*p),0)
                           for p in (contact,far)):return False
                continue
            if other.GetClass()!='PCB_TRACK':return False
            endpoints={tuple(other.GetStart()),tuple(other.GetEnd())}
            common=endpoints&{contact,far}
            if len(common)!=1:return False
            at=next(iter(common));left=far if at==contact else contact
            right=next(iter(endpoints-{at}))
            a=(left[0]-at[0],left[1]-at[1]);b=(right[0]-at[0],right[1]-at[1])
            if a[0]*b[1]==a[1]*b[0] and a[0]*b[0]+a[1]*b[1]>0:return False
        return True
    owned=set();internal={};refusals=[]
    for name,refs in cells.items():
        if cell_deltas[name]==[0,0] and not any(rotations[r] for r in refs):
            internal[name]=dict(refs=sorted(refs),uuids=[],chains=[],delta_nm=[0,0],refused_chains=[])
            continue
        proposal=local.plan(board,[fps[r] for r in refs],generated_locked_uuids=small,
            protected_nets=protected,max_items=12,max_length_mm=maximum_local_length_mm)
        selected=set(proposal['internal_track_uuids'])&small
        if selected and any(rotations[r] for r in refs):
            raise ValueError('rotated_internal_copper_reconstruction_not_supported')
        if selected&owned:raise ValueError('ambiguous_cell_internal_copper')
        owned|=selected
        internal[name]=dict(refs=sorted(refs),uuids=sorted(selected),delta_nm=cell_deltas[name],
            chains=[q['uuids'] for q in proposal['accepted']],
            refused_chains=proposal.get('rejected',[]))
    removable=set()
    rows=[]
    for row in source['contacts']:
        uid=row['track_uuid'];item=items[uid]
        entry=dict(row,locked=bool(item.IsLocked()),width_nm=int(item.GetWidth()))
        target=targetpads.get(row['pad_uuid'])
        if target is None:raise ValueError('target_terminal_copy_identity_refused')
        if deltas[row['ref']]==[0,0] and not rotations[row['ref']]:
            entry['disposition']='unchanged_source_pad_contact_retained'
        elif uid in owned:entry['disposition']='rigid_internal_recompile'
        elif target[1].GetEffectiveShape(row['layer']).Collide(item.GetEffectiveShape(row['layer']),0):
            entry['disposition']='live_native_pad_contact_retained_at_target'
        elif (uid in small and row.get('contact_kind')=='native_contained_trace_boundary'
              and {force._uid(p) for p in allpads if p.IsOnLayer(item.GetLayer())
                   and p.GetEffectiveShape(item.GetLayer()).Collide(item.GetEffectiveShape(item.GetLayer()),0)}
                  =={row['pad_uuid']}
              and cut_is_endpoint_owned(dict(row,contact_nm=list(item.GetStart()),far_nm=list(item.GetEnd())))):
            # A sole selected source SMD land owns both native endpoint
            # contacts. Recompile its complete small ungrouped kernel, not
            # an entire net. Every old surviving conductor junction remains
            # an explicit final restoration requirement, including contacts
            # that were joined through the former pad's copper area.
            removable.add(uid);entry['disposition']='owned_single_pad_kernel_requires_reconstruction'
        elif row.get('fixed_boundary'):
            entry['disposition']='retained_native_boundary_requires_reconnection'
        elif uid in small and cut_is_endpoint_owned(row):
            removable.add(uid);entry['disposition']='owned_pad_leg_requires_reconnection'
        else:
            entry['disposition']='retained_protected_boundary_requires_specialized_reconnection'
        rows.append(entry)
    if len(owned|removable)>max_tracks:raise ValueError('source_owned_local_track_budget')
    collisions=_target_chain_conflicts(board,poses,internal,removable-owned)
    blocked=set()
    for spec in internal.values():
        for chain in spec['chains']:
            if set(chain)&collisions.keys():blocked.update(chain)
        spec['uuids']=sorted(set(spec['uuids'])-blocked)
    # Recompile the complete source-owned chain instead of carrying half of
    # it across a retained trace, barrel, pad or power fill. The source graph
    # remains a restoration obligation; no score benefit is claimed for cuts.
    owned-=blocked;removable|=blocked
    for r in rows:
        if r['track_uuid'] in blocked:r['disposition']='owned_internal_chain_requires_reconstruction'
    if _source_binding(board)!=binding:raise ValueError('native_source_identity_changed_during_contact_inventory')
    result=dict(schema=1,kind='source-owned-cell-row-local-recompile',source_native_sha256=binding,source_poses=oldposes,
        target_poses={r:list(p) for r,p in poses.items()},cells=internal,
        target_internal_chain_blockers=collisions,
        source_incident_boundaries=rows,retired_track_uuids=sorted(removable-owned),
        source_native_barrel_boundaries=source['native_barrel_contacts'],
        transformed_track_uuids=sorted(owned),allow_owned_locked=allow_owned_locked,
        allow_cardinal_rotations=allow_cardinal_rotations,
        max_tracks=max_tracks,maximum_local_length_mm=maximum_local_length_mm,
        maximum_pad_leg_length_mm=maximum_pad_leg_length_mm,
        protected_nets=sorted(protected),routing_admitted=False,release_authority=False,
        all_source_terminal_and_surviving_junction_partitions_require_restoration=True,
        requires_new_power_prefix_and_rated_current_receiving=any(d!=[0,0] for d in deltas.values())
            or any(rotations.values()))
    if allow_octilinear_rotations:result['allow_octilinear_rotations']=True
    if maximum_translation_mm!=64.:result['maximum_translation_mm']=maximum_translation_mm
    if reference_group_uuids:
        result['reference_group_uuids']=list(reference_group_uuids)
        result['source_reference_group_transports']=reference_transports
        import cec_source_reference_group_transport as reference_transport
        reference_transport._translation_bound(maximum_reference_translation_mm)
        for ref in reference_transports:
            reference_transport._delta(tuple(round((poses[ref][k]-oldposes[ref][k])*1e6)
                for k in (0,1)),maximum_reference_translation_mm)
        if maximum_reference_translation_mm != 10.:
            result['maximum_reference_translation_mm']=maximum_reference_translation_mm
    return result


def apply(board, proposal):
    """Apply only the independently source-typed local delta, privately.

    This intentionally produces an unfinished construction snapshot. Wide
    power copper/vias are NOT translated or deleted. Do not serialize this
    with a routed-board writer until the power and external connections are
    restored. The caller must retain it as unadmitted if preflight fails.
    """
    if proposal.get('kind')!='source-owned-cell-row-local-recompile' or proposal.get('routing_admitted') is not False:
        raise ValueError('unadmitted_source_cell_recompile_required')
    current=plan(board,proposal['target_poses'],
        {name:cell['refs'] for name,cell in proposal['cells'].items()},
        protected_nets=proposal['protected_nets'],allow_owned_locked=proposal['allow_owned_locked'],
        max_tracks=proposal['max_tracks'],maximum_local_length_mm=proposal['maximum_local_length_mm'],
        maximum_pad_leg_length_mm=proposal['maximum_pad_leg_length_mm'],
        allow_cardinal_rotations=proposal.get('allow_cardinal_rotations',False),
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False),
        reference_group_uuids=proposal.get('reference_group_uuids',()),
        maximum_reference_translation_mm=proposal.get('maximum_reference_translation_mm',10.),
        maximum_translation_mm=proposal.get('maximum_translation_mm',64.))
    if current!=proposal:raise ValueError('stale_or_forged_source_cell_recompile')
    before=local.copper_inventory(board);population=placement._population(board)
    tracks={force._uid(t):t for t in board.GetTracks()}
    references=proposal.get('source_reference_group_transports',{})
    if references:
        import cec_source_reference_group_transport as reference_transport
        requests=[(proof,int((proposal['target_poses'][ref][2]-proposal['source_poses'][ref][2])%360)//90,
            tuple(round((proposal['target_poses'][ref][k]-proposal['source_poses'][ref][k])*1e6) for k in (0,1)))
            for ref,proof in references.items()]
        if any(turn for proof,turn,delta in requests):
            import cec_source_reference_group_cardinal_batch as cardinal
            cardinal.transform_many(board,requests,maximum_translation_mm=proposal.get('maximum_reference_translation_mm',10.))
        else:reference_transport.transform_many(board,[(proof,delta)for proof,turn,delta in requests],
            maximum_translation_mm=proposal.get('maximum_reference_translation_mm',10.))
    for uid in proposal['retired_track_uuids']:
        if uid not in tracks:raise ValueError('source_owned_edge_missing')
    for cell in proposal['cells'].values():
        delta=pcbnew.VECTOR2I(*cell['delta_nm'])
        for uid in cell['uuids']:tracks[uid].Move(delta)
    discard_items(board,[tracks[u] for u in proposal['retired_track_uuids']])
    for ref,target in proposal['target_poses'].items():
        if ref in references:continue
        fp=board.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        fp.SetOrientationDegrees(target[2])
    after=local.copper_inventory(board)
    changed=set(proposal['retired_track_uuids'])|set(proposal['transformed_track_uuids'])
    if (population!=placement._population(board) or before.keys()-after.keys()!=set(proposal['retired_track_uuids'])
            or after.keys()-before.keys() or any(before[u]!=after[u] for u in before.keys()-changed)):
        raise ValueError('cell_recompile_changed_unowned_material')
    return dict(transformed_tracks=len(proposal['transformed_track_uuids']),
        retired_owned_pad_legs=len(proposal['retired_track_uuids']),
        all_surviving_unrelated_copper_exact=True,all_vias_and_force_current_copper_exact=True,
        electrical_component_definitions_exact=True,routing_admitted=False,release_authority=False)


def _draft_pose_targets(board,child,receipt):
    """Require the saved draft, not a claimed receipt, to own every new pose."""
    if placement._population(board)!=placement._population(child):
        raise ValueError('draft_changed_component_values_pad_definitions_faces_or_nets')
    source_fps={fp.GetReference():fp for fp in board.GetFootprints()}
    draft_fps={fp.GetReference():fp for fp in child.GetFootprints()}
    if (len(source_fps)!=len(list(board.GetFootprints()))
            or len(draft_fps)!=len(list(child.GetFootprints())) or source_fps.keys()!=draft_fps.keys()):
        raise ValueError('ambiguous_or_changed_draft_component_identity')
    def pose(fp):
        return [fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    actual={ref:dict(before=pose(fp),after=pose(draft_fps[ref]))
            for ref,fp in source_fps.items() if pose(fp)!=pose(draft_fps[ref])}
    if not actual or actual!=receipt.get('final_moved_poses'):
        raise ValueError('saved_draft_pose_scope_differs_from_receipt')
    return {ref:list(row['after']) for ref,row in actual.items()}


def prepare(source,draft,out,*,board_hint,allow_owned_locked=False):
    """Consume a hash-bound approved row draft into an isolated local rebuild.

    Only project/rule files travel forward. Frozen receipts and skeletons are
    invalidated, not copied/rebound to the moved force terminals. An unfinished
    artifact must never be submitted as a routed/fabrication candidate.
    """
    import cec_assembly_envelope as assembly
    import cec_constraints as constraints
    import cec_current_topology as topology
    import cec_field_coupling as field
    import cec_cell_row as row
    import cec_additive_route_receiving as additive
    import cec_copper_echo as sexpr
    import cec_placement_geometry as geometry
    source,draft,out=[Path(p).resolve() for p in (source,draft,out)]
    receipt=json.loads((draft.parent/'placement-draft.json').read_text())
    if (force._hash(source)!=receipt['source_sha256'] or force._hash(draft)!=receipt['board_sha256']
            or not receipt.get('placement_and_paired_stack_pass') or out.exists()):
        raise ValueError('exact_qualified_placement_draft_and_new_private_output_required')
    intent_path=Path(receipt['intent'])
    if force._hash(intent_path)!=receipt['intent_sha256']:raise ValueError('source_row_intent_changed')
    intent=json.loads(intent_path.read_text())
    family=force._family(source,board_hint);draft_family=force._family(draft,board_hint)
    code=force._code_identity()
    root=Path(__file__).resolve().parents[1]
    source_policy=assembly.declared_policy(source)
    assembly_dependencies=assembly.dependencies(source_policy,root) if source_policy else []
    assembly_family=force._family_file_hashes(assembly_dependencies)
    def assembly_check(path):
        return (assembly.candidate_check(path,params={'assembly_envelope':source_policy})
            if source_policy else dict(ok=True,applicable=False,violations=[]))
    board=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(draft))
    # Draft LoadBoard can renet obsolete copper. Import only its exact poses,
    # NEVER its native copper/net labels. The original source is authoritative.
    poses=_draft_pose_targets(board,child,receipt)
    # A producer's PASS bit is not permission to skip receiving. Re-run the
    # saved placement, native reservations and declared paired assembly under
    # the current policy before constructing or writing any private child.
    fresh_checks=dict(native_placement=geometry.evaluate(draft,timeout_s=10),
        native_reservations=assembly.footprint_reservation_check(child),
        paired_stack=assembly_check(draft))
    if not all(q['ok'] for q in fresh_checks.values()):
        raise ValueError('saved_draft_current_placement_or_stack_receiving_refused')
    assignments=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    cells={name:set(roles.values()) for name,roles in intent['cells'].items()}
    for name,refs in cells.items():
        refs.update(q['cap_ref'] for q in assignments['assigned'].values()
                    if q['requirement']['ref'] in set(intent['cells'][name].values()))
        if not refs<=poses.keys():raise ValueError('complete_moved_cell_and_supply_followers_required')
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
    import cec_fr as fr
    protected=(set(domains)-{'GND'})|set(fr.coupled_pair_nets(board))
    protected_ids=retained_power_items(board,domains)
    proposal=plan(board,poses,{n:sorted(r) for n,r in cells.items()},
        protected_nets=protected,allow_owned_locked=allow_owned_locked)
    output=out/'board.kicad_pcb';out.mkdir(parents=True)
    for suffix in ('.kicad_pro','.kicad_dru'):
        if source.with_suffix(suffix).is_file():shutil.copy2(source.with_suffix(suffix),output.with_suffix(suffix))
    report=dict(schema=1,status='local-cell-reconstruction-unadmitted',source=str(source),
        source_sha256=force._hash(source),draft=str(draft),draft_sha256=force._hash(draft),
        source_saved_family=family,draft_saved_family=draft_family,
        implementation_files_sha256=code,
        board=str(output),proposal=proposal,release_authority=False,routing_admitted=False,
        old_frozen_power_receipts_not_transferred=True,power_qualified=False,
        draft_fresh_placement_receiving=fresh_checks,source_assembly_dependencies=assembly_family)
    report['assembly_reservation_transition']=assembly.reconcile_placement_reservations(board,
        source_path=source,updates=intent.get('superseded_placement_reservations',[]),
        root=root) if intent.get('superseded_placement_reservations') else None
    # Reservation edits are declared, separate mechanical authorization. They
    # change the source binding but must not silently alter the derived copper
    # scope. Re-derive with the same original pads before the first copper edit.
    mechanical_proposal=plan(board,poses,{n:sorted(r) for n,r in cells.items()},
        protected_nets=protected,allow_owned_locked=allow_owned_locked)
    if any(mechanical_proposal[k]!=proposal[k] for k in proposal if k!='source_native_sha256'):
        raise ValueError('assembly_reservation_changed_source_copper_ownership')
    report['proposal']=mechanical_proposal
    report['local_recompile']=apply(board,mechanical_proposal)
    report['retained_power_preflight']=preflight.check(board,list(poses),retained_uuids=protected_ids)
    try:
        field._save_field_snapshot(board,output)
        report['strict_saved_copper_identity_exact']=True
    except ValueError as exc:
        # Keep diagnostic raw-authored material separate from routing authority.
        # No net relabel is used to silence the physical short. Its complete
        # reload deltas remain visible, and NO ordinary routing wave is started.
        report['strict_saved_copper_identity_exact']=False
        report['strict_save_refusal']=str(exc)
        report['unadmitted_raw_serialization']=row.save_placement_draft(board,output)
    report['board_sha256']=force._hash(output)
    _,oldnodes=additive._nodes(source);_,newnodes=additive._nodes(output)
    fp_ids={force._uid(fp) for fp in board.GetFootprints() if fp.GetReference() in poses}
    zone_ids={q['reservation_uuid'] for q in (report['assembly_reservation_transition'] or {}).get('updates',[])}
    retired=set(mechanical_proposal['retired_track_uuids'])
    allowed=fp_ids|zone_ids|set(mechanical_proposal['transformed_track_uuids'])
    report['all_unrelated_authored_nodes_exact']=(oldnodes.keys()-newnodes.keys()==retired
        and not newnodes.keys()-oldnodes.keys() and all(sexpr._freeze(oldnodes[k])==sexpr._freeze(newnodes[k])
            for k in oldnodes.keys()-retired-allowed))
    if not report['all_unrelated_authored_nodes_exact']:
        raise ValueError('saved_local_recompile_changed_unrelated_authored_material')
    # Only original source footprint material is imported. Validate that
    # resulting saved geometry again; a draft cannot spoof receiving by
    # editing its courtyard, dropping a stack declaration or changing fields.
    report['construction_fresh_placement_receiving']=dict(
        native_placement=geometry.evaluate(output,timeout_s=10),
        native_reservations=assembly.footprint_reservation_check(pcbnew.LoadBoard(str(output))),
        paired_stack=assembly_check(output))
    if not all(q['ok'] for q in report['construction_fresh_placement_receiving'].values()):
        report['status']='local-recompile-construction-placement-receiving-refused'
        report['blocked_stage']='placement_and_paired_stack_revalidation'
    if not report['retained_power_preflight']['ok'] and not report.get('blocked_stage'):
        report['status']='local-recompile-started-power-port-reconstruction-required'
        report['blocked_stage']='power_terminal_and_landing_recompile'
    report['remaining_source_boundary_obligations']=sum(q['disposition']!='rigid_internal_recompile'
        and q['disposition'] not in ('unchanged_source_pad_contact_retained','live_native_pad_contact_retained_at_target')
        for q in mechanical_proposal['source_incident_boundaries'])
    report['source_draft_and_code_unchanged']=(family==force._family(source,board_hint)
        and draft_family==force._family(draft,board_hint) and code==force._code_identity()
        and assembly_family==force._family_file_hashes(assembly_dependencies))
    if not report['source_draft_and_code_unchanged']:raise ValueError('source_draft_or_code_changed')
    force._write(out/'cell-row-rebuild.json',report)
    return report


def main(argv=None):
    """Bounded pipeline entry point; never publish or start ordinary routing."""
    import argparse
    import cec_swig_guard
    cec_swig_guard.pin()
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','draft','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--hint',required=True)
    parser.add_argument('--allow-owned-locked',action='store_true',
        help='Explicitly recompile source-owned small local edges; never unlock power trunks or groups')
    args=parser.parse_args(argv)
    report=prepare(args.source,args.draft,args.out,board_hint=args.hint,
        allow_owned_locked=args.allow_owned_locked)
    print(json.dumps({key:report[key] for key in ('status','board','board_sha256',
        'local_recompile','strict_saved_copper_identity_exact','source_draft_and_code_unchanged',
        'routing_admitted','release_authority')},indent=2))


if __name__=='__main__':main()
