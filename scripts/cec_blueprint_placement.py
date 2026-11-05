"""Restore declared rigid-cell geometry as a proposal, never as admission.

Replacement placement may encounter a source whose followers have drifted
away from an intact anchor. Freezing that malformed cell forever cannot repair
it. Restore its declared transform atomically, retain explicit mechanical
constraints, and require the normal native/assembly/electrical adjudication.
"""
import copy


def restore_candidate(cfg, candidate):
    import cec_cell_extract
    import cec_synth_pipeline as synth

    report = dict(schema=1, applicable=False, changed=False, admitted=False,
                  changed_refs=[], refusals=[])
    proposed = {}
    back = set(candidate.back_refs or ())
    for stamp in synth._declared_blueprint_stamps(cfg, candidate.P):
        expected, _ = cec_cell_extract.stamp(
            stamp['template'], at_mm=tuple(stamp['at_mm']), rot=stamp['rot'],
            ref_map=stamp.get('ref_map') or {}, net_map=stamp.get('net_map'))
        report['applicable'] = True
        for ref, (x, y, angle, flipped) in expected.items():
            pose = (float(x), float(y), float(angle))
            if ref not in candidate.P:
                report['refusals'].append(dict(ref=ref, reason='missing_native_member'))
            if ref in proposed and synth._placement_changed_refs({ref:pose}, proposed):
                report['refusals'].append(dict(ref=ref, reason='conflicting_cell_contracts'))
            # Face changes require a separate native/copper ownership operation.
            # This proposal intentionally only restores same-face poses.
            if bool(flipped) != (ref in back):
                report['refusals'].append(dict(ref=ref, reason='cell_face_mismatch'))
            proposed[ref] = pose
    changed = synth._placement_changed_refs(proposed, candidate.P)
    # Supply components delegated out of the precision template still belong
    # to their electrical owner. Move them with that owner's full rigid
    # transform, including rotation, rather than orphaning a passing bypass.
    report['supply_followers'] = []
    if changed and getattr(cfg, 'sch', None):
        from cec_placement_search_domain import rigid_cell_transform
        nl = synth.View(cfg).nl
        requirements = synth._device_bypass_specs(nl, list(nl.comps), list(nl.comps))
        for cap, requirement in sorted(requirements.items()):
            owner = requirement.get('owner')
            if owner not in changed or owner not in candidate.P or cap in proposed:
                continue
            if cap not in candidate.P:
                report['refusals'].append(dict(ref=cap, reason='missing_supply_follower'))
                continue
            old, new = candidate.P[owner], proposed[owner]
            poses = rigid_cell_transform({owner:old, cap:candidate.P[cap]}, owner,
                new[2]-old[2], (new[0]-old[0], new[1]-old[1]))
            proposed[cap] = poses[cap]
            report['supply_followers'].append(dict(ref=cap, owner=owner))
        changed = synth._placement_changed_refs(proposed, candidate.P)
    params = getattr(cfg, 'params', {}) or {}
    fixed = set(getattr(cfg, 'pins', {}) or ())
    fixed.update((params.get('anchor_pins') or {}).keys())
    fixed.update((params.get('anchor_local_placements') or {}).keys())
    for group in params.get('rigid_groups') or ():
        fixed.update((group.get('offsets') or {}).keys())
    fixed.update((getattr(candidate, 'noncontact_placement_contract', {}) or {}).get('immutable_refs', ()))
    if getattr(candidate, 'frozen_placement_contract', None):
        report['refusals'].append(dict(reason='frozen_copper_requires_separate_transaction'))
    for ref in sorted(changed & fixed):
        report['refusals'].append(dict(ref=ref, reason='explicit_pose_constraint'))
    report['changed_refs'] = sorted(changed)
    if not changed or report['refusals']:
        return None, report
    restored = copy.copy(candidate)
    restored.P = dict(candidate.P, **proposed)
    restored.strat = str(candidate.strat) + '-rigid-cell-restore'
    restored.blueprint_restore = dict(report, changed=True)
    report['changed'] = True
    return restored, report


def restoration_candidates(cfg, candidate, *, max_candidates=4):
    """Bounded complete-cell reseating around native bodies and keepouts.

    A new assembly exclusion can conflict with a previously authored cell.
    Re-seat the complete cell and its supply followers, never just the member
    that happens to collide. Preserve anchors explicitly owned by another
    contract. These are shortlisted proposals for the canonical exact gates.
    """
    import math
    import pcbnew
    import cec_pcb
    import cec_synth_pipeline as synth
    from cec_cell_packing import contact_translation_sites

    if type(max_candidates) is not int or not 1 <= max_candidates <= 8:
        raise ValueError('rigid-cell shortlist budget must be an integer from 1 to 8')
    restored, report = restore_candidate(cfg, candidate)
    if restored is None:
        return [], report
    candidates = [restored]
    report['reseating'] = []
    if max_candidates == 1 or not getattr(candidate, 'source_board', None):
        return candidates, report
    board = pcbnew.LoadBoard(str(candidate.source_board))
    if board is None:
        raise ValueError('native source required for rigid-cell reseating')
    comps = synth._extend_footprint_map_from_board(
        synth._fp_of(synth.View(cfg).nl), candidate.source_board, refs=restored.P)
    params = getattr(cfg, 'params', {}) or {}
    fixed = set(getattr(cfg, 'pins', {}) or ())
    fixed.update((params.get('anchor_pins') or {}).keys())
    fixed.update((params.get('anchor_local_placements') or {}).keys())
    for group in params.get('rigid_groups') or ():
        fixed.update((group.get('offsets') or {}).keys())
    fixed.update((getattr(candidate, 'noncontact_placement_contract', {}) or {}).get('immutable_refs', ()))
    nl=synth.View(cfg).nl
    requirements=synth._device_bypass_specs(nl,list(nl.comps),list(nl.comps))
    back=set(restored.back_refs or ())
    boxes={ref:cec_pcb.courtyard_bbox(comps[ref],*pose)
           for ref,pose in restored.P.items() if ref in comps}
    ranked=[]
    for index,stamp in enumerate(synth._declared_blueprint_stamps(cfg,restored.P)):
        members={str((stamp.get('ref_map') or {}).get(r,r))
                 for r in stamp['template'].get('parts',{})}
        if not members.intersection(report['changed_refs']):
            continue
        anchor_declaration=stamp['template'].get('anchor')
        anchor_ref=(anchor_declaration.get('ref') if isinstance(anchor_declaration,dict)
                    else anchor_declaration)
        anchor=str((stamp.get('ref_map') or {}).get(anchor_ref,anchor_ref))
        # Only live-anchor stamps are movable. An explicit absolute stamp
        # position must not be silently turned into a free translation.
        declarations=params.get('blueprint_cells') or ()
        if not any(str(c.get('anchor_ref') or '')==anchor and c.get('anchor_at') is None
                   for c in declarations):
            continue
        owners=set(members)
        members.update(cap for cap,spec in requirements.items() if spec.get('owner') in owners)
        if members & fixed or not members <= boxes.keys():
            continue
        faces={ref in back for ref in members}
        if len(faces)!=1:
            continue
        backside=next(iter(faces))
        moving=[(boxes[r][0],boxes[r][2],boxes[r][1],boxes[r][3]) for r in sorted(members)]
        obstacles=[(b[0],b[2],b[1],b[3]) for r,b in boxes.items()
                   if r not in members and (r in back)==backside]
        layer=pcbnew.B_Cu if backside else pcbnew.F_Cu
        for zone in board.Zones():
            if (zone.GetIsRuleArea() and zone.GetDoNotAllowFootprints()
                    and zone.GetLayerSet().Contains(layer)):
                bb=zone.GetBoundingBox()
                obstacles.append((bb.GetLeft()/1e6,bb.GetTop()/1e6,
                                  bb.GetRight()/1e6,bb.GetBottom()/1e6))
        bounds=(.1-min(b[0] for b in moving), .1-min(b[1] for b in moving),
                float(candidate.W)-.1-max(b[2] for b in moving),
                float(candidate.H)-.1-max(b[3] for b in moving))
        if bounds[0]>bounds[2] or bounds[1]>bounds[3]:
            continue
        sites=contact_translation_sites(moving,bounds=bounds,obstacles=obstacles,
            clearance=.1,preferred_origin=(0.,0.),max_sites=16)
        for dx,dy in sites:
            if math.hypot(dx,dy)<1e-7:
                continue
            trial=copy.copy(restored);trial.P=dict(restored.P)
            trial.P.update({r:(restored.P[r][0]+dx,restored.P[r][1]+dy,restored.P[r][2])
                            for r in members})
            receipt=dict(cell_index=index,anchor=anchor,members=sorted(members),delta_mm=[dx,dy])
            trial.strat=restored.strat+'-contact-reseat'
            trial.blueprint_restore=dict(report,reseating=[receipt])
            ranked.append(((round(math.hypot(dx,dy),6),index,dx,dy),trial,receipt))
    for _rank,trial,receipt in sorted(ranked,key=lambda row:row[0])[:max_candidates-1]:
        candidates.append(trial);report['reseating'].append(receipt)
    report['candidate_count']=len(candidates)
    return candidates,report
