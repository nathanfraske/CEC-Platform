"""Extend a declared repeated-cell row without copying electrical definitions.

Cells declare role-to-reference maps; supply followers declare their owners.
The row's actual pitch, orientation and internal geometry determine the new
seat. This is a placement proposal, never permission to move retained copper,
reuse stale frozen-power receipts, or claim routing/release admission.
"""
import math


def extend_row(placements, *, cells, moving_cell, row_cells, anchor_role,
               follower_owners=None, immutable_refs=(), side='before',
               tolerance_mm=.01):
    """Propose one whole-cell translation beside an existing uniform row.

    Already aligned cells and all unrelated poses remain untouched. Refuse
    ambiguous ownership, mismatched cell geometry and irregular rows instead
    of guessing a footprint/net map or silently normalizing other channels.
    """
    if (side not in ('before', 'after') or not 0 < tolerance_mm <= .1
            or not math.isfinite(tolerance_mm) or not 2 <= len(row_cells) <= 16
            or moving_cell in row_cells or len(set(row_cells)) != len(row_cells)):
        raise ValueError('bounded distinct repeated-cell row required')
    selected = [moving_cell, *row_cells]
    if any(name not in cells for name in selected):
        raise ValueError('declared cell missing')
    role_set = set(cells[moving_cell])
    if (not 2 <= len(role_set) <= 32 or anchor_role not in role_set
            or any(set(cells[name]) != role_set for name in selected)):
        raise ValueError('matching complete cell roles required')
    refs = [ref for name in selected for ref in cells[name].values()]
    if len(set(refs)) != len(refs) or any(ref not in placements for ref in refs):
        raise ValueError('unique live cell membership required')
    core_members = set(cells[moving_cell].values())
    members = set(core_members)
    followers = dict(follower_owners or {})
    for follower, owner in followers.items():
        if follower in refs or follower not in placements:
            raise ValueError('ambiguous or missing supply follower')
        if owner in core_members:
            members.add(follower)
    if len(members) > 64:
        raise ValueError('whole-cell member budget exceeded')
    for ref in set(refs) | members:
        pose = placements[ref]
        if len(pose) != 3 or not all(math.isfinite(float(v)) for v in pose):
            raise ValueError('finite XY/orientation poses required')
    reference = cells[row_cells[0]]
    reference_anchor = placements[reference[anchor_role]]
    for name in selected:
        cell = cells[name]
        anchor = placements[cell[anchor_role]]
        for role in role_set:
            a, b = placements[reference[role]], placements[cell[role]]
            if (math.dist((a[0]-reference_anchor[0], a[1]-reference_anchor[1]),
                          (b[0]-anchor[0], b[1]-anchor[1])) > tolerance_mm
                    or abs((float(a[2])-float(b[2])+180) % 360-180) > 1e-5):
                raise ValueError('cell geometry/orientation differs from row')
    anchors = [placements[cells[name][anchor_role]] for name in row_cells]
    pitch = tuple(anchors[1][axis]-anchors[0][axis] for axis in (0, 1))
    if math.hypot(*pitch) <= tolerance_mm:
        raise ValueError('nonzero repeated-cell pitch required')
    for a, b in zip(anchors, anchors[1:]):
        if math.dist(pitch, (b[0]-a[0], b[1]-a[1])) > tolerance_mm:
            raise ValueError('row is not uniformly spaced and collinear')
    end, sign = (anchors[0], -1) if side == 'before' else (anchors[-1], 1)
    target = tuple(end[axis]+sign*pitch[axis] for axis in (0, 1))
    origin = placements[cells[moving_cell][anchor_role]]
    delta = tuple(target[axis]-origin[axis] for axis in (0, 1))
    moved = math.hypot(*delta) > 1e-6
    if moved and members & set(immutable_refs):
        raise ValueError('whole cell intersects an immutable pose contract')
    poses = {ref: (placements[ref][0]+delta[0], placements[ref][1]+delta[1],
                   placements[ref][2]) for ref in sorted(members)}
    return dict(schema=1, kind='repeated-cell-row-extension', changed=moved,
        moving_cell=moving_cell, row_cells=list(row_cells), anchor_role=anchor_role,
        side=side, pitch_mm=list(pitch), delta_mm=list(delta), poses=poses,
        source_poses={ref: list(placements[ref]) for ref in sorted(members)},
        supply_followers=[dict(ref=ref, owner=followers[ref])
                          for ref in sorted(members & followers.keys())],
        routing_admitted=False, release_authority=False,
        requires_native_placement_and_incident_copper_revalidation=True)


def apply_draft(board, proposal):
    """Apply exact native poses to a caller-owned private board, not copper.

    Retained routes deliberately stay unchanged. A routed source therefore
    produces a draft needing reconstruction, NOT an additive checkpoint.
    Source-pose mismatch, locks and footprint groups fail before any mutation.
    """
    import pcbnew
    import cec_local_copper_cell as copper
    import cec_route_placement_admission as admission
    if (proposal.get('kind') != 'repeated-cell-row-extension'
            or proposal.get('routing_admitted') is not False
            or proposal.get('release_authority') is not False):
        raise ValueError('unadmitted complete-cell proposal required')
    before = admission._population(board)
    original_copper = copper.copper_inventory(board)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if len(footprints) != len(before):
        raise ValueError('ambiguous native component identity')
    grouped = {item.m_Uuid.AsString() for group in board.Groups()
               for item in group.GetItems()}
    old = {}
    if set(proposal['poses']) != set(proposal['source_poses']):
        raise ValueError('source and proposed membership mismatch')
    for ref, source in proposal['source_poses'].items():
        fp = footprints.get(ref)
        if fp is None or fp.IsLocked() or fp.m_Uuid.AsString() in grouped:
            raise ValueError('native cell member missing, locked or grouped')
        at = fp.GetPosition()
        angle = fp.GetOrientationDegrees()
        if ((at.x, at.y) != tuple(round(float(v)*1e6) for v in source[:2])
                or abs((angle-float(source[2])+180) % 360-180) > 1e-5):
            raise ValueError('native source pose differs from proposal')
        pose = proposal['poses'][ref]
        if (len(pose) != 3 or not all(math.isfinite(float(v)) for v in pose)
                or abs((float(pose[2])-angle+180) % 360-180) > 1e-5):
            raise ValueError('row draft requires finite translation-only poses')
        delta = [(float(pose[i])-float(source[i])) for i in (0, 1)]
        if math.dist(delta, proposal['delta_mm']) > 1e-6:
            raise ValueError('incomplete rigid cell transform')
        old[ref] = (pcbnew.VECTOR2I(at.x, at.y), angle)
    if not old or len(old) > 64:
        raise ValueError('bounded nonempty native cell required')
    try:
        for ref, pose in proposal['poses'].items():
            footprints[ref].SetPosition(pcbnew.VECTOR2I(
                round(float(pose[0])*1e6), round(float(pose[1])*1e6)))
            footprints[ref].SetOrientationDegrees(float(pose[2]))
        if (before != admission._population(board)
                or original_copper != copper.copper_inventory(board)):
            raise ValueError('row draft changed electrical definitions or copper')
    except Exception:
        for ref, (at, angle) in old.items():
            footprints[ref].SetPosition(at)
            footprints[ref].SetOrientationDegrees(angle)
        raise
    return dict(schema=1, moved_refs=sorted(old), all_original_copper_exact=True,
        component_values_nets_pads_and_faces_exact=True, routing_admitted=False,
        release_authority=False, requires_incident_copper_reconstruction=True)


def save_placement_draft(board, path):
    """Serialize authored identities without hiding obsolete incident copper.

    Unlike a routing checkpoint, a placement draft deliberately leaves old
    incident copper in place for reconstruction. Native LoadBoard can relabel
    a shorted retained track component after a footprint move. Keep the raw
    authored file exact, report EVERY load-only delta, and never admit this as
    routed. The strict routing snapshot writer is not changed or bypassed by
    any routing receiver; its refusal remains required at that boundary.
    """
    import pcbnew
    import cec_field_coupling as field
    from pathlib import Path
    before=field._field_snapshot_inventory(board)
    name=board.GetFileName() or ''
    try:pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    finally:board.SetFileName(name)
    if not Path(path).is_file() or field._field_snapshot_inventory(board)!=before:
        raise ValueError('placement serialization changed authored native material')
    loaded=pcbnew.LoadBoard(str(path));after=field._field_snapshot_inventory(loaded)
    changes=[dict(key=list(k),before=before.get(k),after=after.get(k))
        for k in sorted(before.keys()|after.keys()) if before.get(k)!=after.get(k)]
    if (before.keys()!=after.keys() or any(r['key'][0]!='track'
            or r['before'][0]!=r['after'][0] or r['before'][2:]!=r['after'][2:]
            for r in changes)):
        raise ValueError('placement reload changed geometry, terminal or zone identity')
    return dict(authored_caller_material_exact=True,reloaded_copper_identity_exact=not changes,
        load_only_copper_deltas=changes,requires_incident_copper_reconstruction=True,
        routing_admitted=False,release_authority=False)


def repack_row_draft(board, intent, *, max_row_shift_mm=3., max_support_shift_mm=3.,
                     max_support_refs=2, max_nodes=2048):
    """Fit the whole aligned row around native keepouts and small supports.

    The row can slide only along its own measured axis, without changing
    pitch or expanding the outline. A bounded, native-conflict-derived set of
    unlocked small SMD supports can translate cooperatively. No power/pair
    receipt is rebound; all incident routing must subsequently be rebuilt.
    """
    import pcbnew
    from shapely import affinity
    from shapely.geometry import box
    import cec_assembly_envelope as assembly
    import cec_cell_packing as packing
    import cec_constraints as constraints
    import cec_local_copper_cell as copper
    import cec_route_placement_admission as admission
    import cec_synth_pipeline as synth
    if (not 0 < max_row_shift_mm <= 6 or not 0 < max_support_shift_mm <= 6
            or type(max_support_refs) is not int or not 0 <= max_support_refs <= 4
            or type(max_nodes) is not int or not 1 <= max_nodes <= 4096):
        raise ValueError('bounded cooperative row fitting required')
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    core = {ref for name in [intent['moving_cell'], *intent['row_cells']]
            for ref in intent['cells'][name].values()}
    assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    if any(req['ref'] in core for req in assignment['missing']):
        raise ValueError('whole-row supply ownership incomplete')
    row_refs = core | {row['cap_ref'] for row in assignment['assigned'].values()
                      if row['requirement']['ref'] in core}
    if not 1 <= len(row_refs) <= 64 or not row_refs <= fps.keys():
        raise ValueError('bounded live native row required')
    grouped = {item.m_Uuid.AsString() for group in board.Groups() for item in group.GetItems()}
    if any(fps[r].IsLocked() or fps[r].m_Uuid.AsString() in grouped for r in row_refs):
        raise ValueError('protected row member')
    faces = {fps[r].IsFlipped() for r in row_refs}
    if len(faces) != 1:
        raise ValueError('cooperative row fitting requires one face')
    back = next(iter(faces));layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    a, b = [fps[intent['cells'][name][intent['anchor_role']]].GetPosition()
            for name in intent['row_cells'][:2]]
    angle = math.degrees(math.atan2(b.y-a.y,b.x-a.x))
    def frame(shape):return affinity.rotate(shape,-angle,origin=(0,0))
    def shape_of(fp):
        native = fp.GetCourtyard(fp.GetLayer())
        if native.OutlineCount():return frame(assembly.polygon_from_native(native))
        x0,x1,y0,y1 = synth._footprint_courtyard_box(fp)
        return frame(box(x0,y0,x1,y1))
    bodies = {r:shape_of(fp) for r,fp in fps.items()
              if fp.IsFlipped()==back or any(p.HasHole() for p in fp.Pads())}
    reservations = [frame(assembly.polygon_from_native(z.Outline())) for z in board.Zones()
        if z.GetIsRuleArea() and z.GetDoNotAllowFootprints() and z.IsOnLayer(layer)]
    members = [bodies[r] for r in sorted(row_refs)]
    sites = packing.contact_translation_sites([g.bounds for g in members],
        bounds=(0.,0.,max_row_shift_mm,0.),obstacles=[g.bounds for g in reservations],
        clearance=.1,max_sites=8,preferred_origin=(0.,0.))
    candidates = [(0.,0.), *sites]
    before_population = admission._population(board)
    before_copper = copper.copper_inventory(board)
    trials = []
    for preferred in dict.fromkeys(candidates):
        trial = dict(preferred_mm=list(preferred));trials.append(trial)
        posed = [affinity.translate(g,*preferred) for g in members]
        if any(g.intersects(k) or g.distance(k)<.1-1e-7 for g in posed for k in reservations):
            trial['reason']='native_footprint_reservation';continue
        supports = {ref for ref,g in bodies.items() if ref not in row_refs
                    and any(g.intersects(p) or g.distance(p)<.1-1e-7 for p in posed)}
        trial['conflicting_supports']=sorted(supports)
        if len(supports)>max_support_refs:
            trial['reason']='support_count_budget';continue
        if any(fps[r].IsLocked() or fps[r].m_Uuid.AsString() in grouped
                or not 2 <= len(list(fps[r].Pads())) <= 6
                or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in fps[r].Pads())
                for r in supports):
            trial['reason']='locked_grouped_or_nonsupport_obstacle';continue
        # Independent small-support translations must not split an owned
        # bypass cell. Such supports need an explicit whole-cell transaction,
        # not merely adding their followers as independently packed objects.
        owned_supports={r['cap_ref'] for r in assignment['assigned'].values()}
        owned_supports|={r['requirement']['ref'] for r in assignment['assigned'].values()}
        if supports&owned_supports:
            trial['reason']='owned_local_support_cell_requires_rigid_scope';continue
        groups = {'row':dict(members=members,bounds=(0.,0.,max_row_shift_mm,0.),preferred=preferred)}
        for ref in sorted(supports):
            groups[ref]=dict(members=[bodies[ref]],
                bounds=(-max_support_shift_mm,-max_support_shift_mm,
                         max_support_shift_mm,max_support_shift_mm),preferred=(0.,0.))
        fixed = [g for ref,g in bodies.items() if ref not in row_refs|supports]+reservations
        result = packing.pack_translations(groups,fixed,clearance=.1,
            max_nodes=max_nodes,sites_per_group=24)
        if not result['ok']:
            trial.update(reason='native_courtyard_cooperative_fit_refused',nodes=result['nodes']);continue
        old = {ref:tuple(fps[ref].GetPosition()) for ref in row_refs|supports}
        transforms = {}
        try:
            for group,(dx,dy) in result['translations'].items():
                theta=math.radians(angle)
                world=(dx*math.cos(theta)-dy*math.sin(theta),dx*math.sin(theta)+dy*math.cos(theta))
                refs = row_refs if group=='row' else {group}
                transforms[group]=dict(refs=sorted(refs),delta_mm=list(world))
                for ref in refs:fps[ref].Move(pcbnew.VECTOR2I(round(world[0]*1e6),round(world[1]*1e6)))
            if admission._population(board)!=before_population or copper.copper_inventory(board)!=before_copper:
                raise ValueError('cooperative fitting changed electrical definitions or copper')
        except Exception:
            for ref,at in old.items():fps[ref].SetPosition(pcbnew.VECTOR2I(*at))
            raise
        return dict(ok=True,transforms=transforms,nodes=result['nodes'],
            native_keepout_count=len(reservations),support_refs=sorted(supports),
            trials=trials,all_original_copper_exact=True,routing_admitted=False,release_authority=False)
    return dict(ok=False,reason='bounded_cooperative_row_fit_refused',
                trials=trials,native_keepout_count=len(reservations),
                routing_admitted=False,release_authority=False)


def main(argv=None):
    """Agent/pipeline entry point: save a private, explicitly unadmitted draft.

    Copy only project/rule companions. Frozen placement/power/pair receipts
    from the routed parent are deliberately NOT transferred to the new poses.
    Native assembly/pad geometry is measured separately from old routing debt.
    """
    import argparse
    import json
    from pathlib import Path
    import shutil
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    import cec_constraints as constraints
    import cec_force_current as force
    import cec_placement_geometry as geometry
    import cec_assembly_envelope as assembly
    import cec_additive_route_receiving as additive
    import cec_copper_echo as sexpr
    import cec_cell_row_rebuild as rebuild
    import cec_cell_copper_preflight as copper_preflight
    import cec_current_topology as topology

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--intent', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--hint', required=True)
    parser.add_argument('--repack-declared-row', action='store_true',
        help='Permit bounded common row sliding and conflict-derived small-support draft moves')
    parser.add_argument('--reconstruct-local-copper',action='store_true',
        help='After independent placement receiving, construct a separate unadmitted local-copper child')
    parser.add_argument('--allow-owned-locked-local-recompile',action='store_true',
        help='Explicit source-owned small-edge permission; requires --reconstruct-local-copper')
    args = parser.parse_args(argv)
    if args.allow_owned_locked_local_recompile and not args.reconstruct_local_copper:
        parser.error('--allow-owned-locked-local-recompile requires --reconstruct-local-copper')
    source, target = args.source.resolve(), args.out.resolve()
    if (not source.is_file() or force._hash(source) != args.source_sha256
            or target.exists() or source.parent == target):
        raise ValueError('immutable hashed source and new private output required')
    intent = json.loads(args.intent.read_text())
    family, code = force._family(source, args.hint), force._code_identity()
    intent_hash = force._hash(args.intent)
    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise ValueError('native source board missing')
    poses = {fp.GetReference(): (fp.GetPosition().x/1e6, fp.GetPosition().y/1e6,
                                 fp.GetOrientationDegrees()) for fp in board.GetFootprints()}
    assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    moving_owners = set(intent['cells'][intent['moving_cell']].values())
    if any(requirement['ref'] in moving_owners for requirement in assignment['missing']):
        raise ValueError('whole-cell supply ownership is incomplete')
    followers = {}
    for row in assignment['assigned'].values():
        cap, owner = row['cap_ref'], row['requirement']['ref']
        if owner not in moving_owners:
            continue
        if cap in followers and followers[cap] != owner:
            raise ValueError('supply follower has multiple native owners')
        followers[cap] = owner
    proposal = extend_row(poses, cells=intent['cells'], moving_cell=intent['moving_cell'],
        row_cells=intent['row_cells'], anchor_role=intent['anchor_role'],
        side=intent.get('side', 'before'), follower_owners=followers)
    if not proposal['changed']:
        raise ValueError('already aligned; no replacement artifact needed')
    target.mkdir(parents=True)
    output = target/'board.kicad_pcb'
    for suffix in ('.kicad_pro', '.kicad_dru'):
        companion = source.with_suffix(suffix)
        if companion.is_file():
            shutil.copy2(companion, output.with_suffix(suffix))
    report = dict(schema=1, status='placement-draft-requires-incident-copper-reconstruction',
        source=str(source), source_sha256=args.source_sha256, board=str(output),
        source_saved_family=family,implementation_files_sha256=code,
        intent=str(args.intent.resolve()), intent_sha256=intent_hash, proposal=proposal,
        invalidated_parent_authority_companions=[str(path) for path in source.parent.glob(
            source.stem+'.*') if path.suffix not in ('.kicad_pcb', '.kicad_pro', '.kicad_dru')],
        routing_admitted=False, release_authority=False)
    report['native_transform'] = apply_draft(board, proposal)
    report['serialization']=save_placement_draft(board,output)
    report['board_sha256'] = force._hash(output)
    before = geometry.evaluate(source, timeout_s=10)
    after = geometry.evaluate(output, timeout_s=10)
    report['paired_assembly_before'] = assembly.candidate_check(source)
    report['paired_assembly_after'] = assembly.candidate_check(output)
    if args.repack_declared_row and (not after['ok'] or not report['paired_assembly_after']['ok']):
        report['unrepacked_native_placement'] = after
        report['unrepacked_paired_assembly'] = report['paired_assembly_after']
        if intent.get('superseded_placement_reservations'):
            report['assembly_reservation_transition']=assembly.reconcile_placement_reservations(
                board,source_path=source,updates=intent['superseded_placement_reservations'],
                root=Path(__file__).resolve().parents[1])
        report['row_repacking'] = repack_row_draft(board,intent)
        if report['row_repacking']['ok']:
            report['serialization']=save_placement_draft(board,output)
            report['board_sha256'] = force._hash(output)
            after = geometry.evaluate(output,timeout_s=10)
            report['paired_assembly_after'] = assembly.candidate_check(output)
    report['native_placement_before'] = before
    report['native_placement_after'] = after
    old_keys = geometry.craft_conflict_keys(geometry.craft_projection(before))
    new_keys = geometry.craft_conflict_keys(geometry.craft_projection(after))
    report['new_native_placement_conflicts'] = sorted(new_keys-old_keys)
    report['native_placement_nonregression'] = not report['new_native_placement_conflicts']
    saved=pcbnew.LoadBoard(str(output))
    report['native_footprint_reservations']=assembly.footprint_reservation_check(saved)
    final_poses={fp.GetReference():(fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()) for fp in saved.GetFootprints()}
    report['final_moved_poses']={ref:dict(before=list(poses[ref]),after=list(pose))
        for ref,pose in final_poses.items() if pose!=poses[ref]}
    _,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(output)
    moved_ids={fp.m_Uuid.AsString() for fp in saved.GetFootprints()
               if fp.GetReference() in report['final_moved_poses']}
    allowed=moved_ids|{r['reservation_uuid'] for r in report.get(
        'assembly_reservation_transition',{}).get('updates',[])}
    report['unrelated_native_nodes_exact']=(old_nodes.keys()==new_nodes.keys() and all(
        sexpr._freeze(old_nodes[k])==sexpr._freeze(new_nodes[k]) for k in old_nodes if k not in allowed))
    import cec_route_placement_admission as admission
    report['saved_component_definitions_exact']=(admission._population(saved)==
        admission._population(pcbnew.LoadBoard(str(source))))
    report['placement_and_paired_stack_pass'] = bool(after['ok']
        and report['paired_assembly_after']['ok'] and report['native_footprint_reservations']['ok']
        and report['unrelated_native_nodes_exact'] and report['saved_component_definitions_exact'])
    # Mechanical fit and retained-copper fit are independent. Measure the
    # authored source board at its proposed poses, not the draft LoadBoard's
    # potentially propagated net labels. This never qualifies a power field.
    with force._thermal_hint(args.hint):
        domains=topology.board_current_domains(board,args.hint)
    report['retained_power_preflight']=copper_preflight.check(board,
        sorted(report['final_moved_poses']),retained_uuids=rebuild.retained_power_items(board,domains))
    report['blocked_stage']=('power_terminal_and_landing_recompile'
        if not report['retained_power_preflight']['ok'] else 'incident_copper_reconstruction')
    report['source_family_unchanged'] = family == force._family(source, args.hint)
    report['code_epoch_unchanged'] = code == force._code_identity()
    report['intent_unchanged'] = intent_hash == force._hash(args.intent)
    force._write(target/'placement-draft.json', report)
    if not all(report[key] for key in ('source_family_unchanged', 'code_epoch_unchanged', 'intent_unchanged')):
        raise ValueError('source, intent or implementation changed during construction')
    if args.reconstruct_local_copper:
        if not report['placement_and_paired_stack_pass']:
            raise ValueError('local reconstruction requires independently passing placement and assembly')
        child=rebuild.prepare(source,output,target/'local-recompile',board_hint=args.hint,
            allow_owned_locked=args.allow_owned_locked_local_recompile)
        report['local_recompile_child']={key:child[key] for key in ('status','board','board_sha256',
            'local_recompile','strict_saved_copper_identity_exact','routing_admitted','release_authority')}
        force._write(target/'placement-draft.json',report)
    print(json.dumps({key: report[key] for key in ('status', 'board', 'board_sha256',
        'proposal', 'native_transform', 'native_placement_nonregression',
        'placement_and_paired_stack_pass', 'new_native_placement_conflicts',
        'source_family_unchanged', 'blocked_stage', 'release_authority')}, indent=2))


if __name__ == '__main__':
    main()
