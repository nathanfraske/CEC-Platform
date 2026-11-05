"""Receive additive routing with explicit GND refill and local via ownership.

Ground antipads necessarily change when a routed child gains a barrel. They
are not permission to change protected power copper or to accept stale fills.
Reconstruct the exact additive transaction from source primitives, replay
ONLY existing GND fills and existing exact-object POFV rules independently,
and compare the saved child with that expected result. No release authority.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_copper_echo as sexpr
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_fab_profile as fab


def _nodes(path):
    root=sexpr._parse(sexpr._TOKEN.findall(Path(path).read_text()))
    by_id={}
    for node in root[1:]:
        if not isinstance(node,list):continue
        uid=next((row[1].strip('"') for row in node[1:]
            if isinstance(row,list) and row and row[0]=='uuid' and len(row)==2),None)
        if uid:
            if uid in by_id:raise ValueError('ambiguous_native_uuid')
            by_id[uid]=node
    return root,by_id


def _without(node,field_name):
    return sexpr._freeze([row for row in node if not
        (isinstance(row,list) and row and row[0]==field_name)])


def _members(node):
    row=next((row for row in node if isinstance(row,list) and row and row[0]=='members'),[])
    values=[value.strip('"') for value in row[1:]]
    if len(set(values))!=len(values):raise ValueError('ambiguous_group_members')
    return set(values)


def _render(node):
    return '('+' '.join(_render(value) if isinstance(value,list) else value for value in node)+')'


def _ground_refill(board):
    before=field._field_snapshot_inventory(board)
    ground=pcbnew.ZONES()
    selected=set()
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and zone.GetNetname()=='GND':
            selected.add(str(zone.m_Uuid.AsString()));zone.UnFill();ground.append(zone)
    if ground.size():
        import cec_zone_fill
        try:
            cec_zone_fill.compile_selected(board,ground,initialize_selected=True)
        except cec_zone_fill.NativeFillFailed as exc:
            raise ValueError('native_ground_refill_refused') from exc
    after=field._field_snapshot_inventory(board)
    allowed={('zone',uid) for uid in selected}
    if before.keys()!=after.keys() or any(before[key]!=after[key]
            for key in before if key not in allowed):
        raise ValueError('ground_refill_changed_non_ground_evidence')
    return sorted(selected)


def bind_local_via_rule(board,path):
    groups=[g for g in board.Groups() if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP]
    if len(groups)>1:raise ValueError('ambiguous_local_via_ownership')
    if not groups:return dict(applicable=False,written=False)
    profile_name=fab.board_profile_name(board)
    profile=fab.get_profile(profile_name) if profile_name else None
    if not profile or profile.get('pofv') is not True:
        raise ValueError('no_declared_local_via_process')
    vias=list(groups[0].GetItems())
    if not vias or any(v.GetClass()!='PCB_VIA' for v in vias):
        raise ValueError('invalid_local_via_group')
    # Inherited members retain their existing debt; incoming members must be
    # independently qualified by the receiving function below. This mirrors
    # the actual emitter's rule for the unchanged exact-object group only.
    diameters=[v.GetWidth(v.TopLayer())/1e6 for v in vias]
    drills=[v.GetDrillValue()/1e6 for v in vias]
    evidence=dict(group=fr.LOCAL_POFV_SIGNAL_VIA_GROUP,profile=profile_name,
        min_diameter_mm=min(diameters),min_drill_mm=min(drills),
        min_annular_mm=min((d-h)/2 for d,h in zip(diameters,drills)))
    return fr.ensure_local_pofv_signal_via_rule(str(path),
        dict(local_pofv_signal_vias=evidence))


def bind_local_endpoint_rule(board,path):
    """Derive the exact-group floor from all actual native members.

    A new wider launch must not raise the rule above older narrow members.
    This emits geometry, not permission: incoming members still require
    independent bounded endpoint and whole-current receiving.
    """
    groups=[g for g in board.Groups() if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP]
    if len(groups)>1:raise ValueError('ambiguous_native_endpoint_group')
    if not groups:return dict(applicable=False,written=False)
    all_members=list(groups[0].GetItems())
    members=[i for i in all_members if i.GetClass() in ('PCB_TRACK','PCB_ARC')]
    # Frozen purposeful covers can belong to this group too. The emitted
    # condition is Track-only: a cover supplies no width or current waiver.
    # Independent delta receiving still prohibits new/changed power zones.
    if (not members or len(all_members)>4096 or any(i.GetWidth()<=0 for i in members)):
        raise ValueError('bounded_native_endpoint_track_group_required')
    minimum=min(i.GetWidth() for i in members)
    return fr.ensure_endpoint_neckdown_rule(str(path),dict(group=fr.ENDPOINT_NECKDOWN_GROUP,
        tracks=len(members),min_width_mm=minimum/1e6))


def finalize_private(source,candidate,directory):
    """Finalize a separate proposal; never modify either incoming family."""
    source,candidate,directory=map(lambda p:Path(p).resolve(),(source,candidate,directory))
    if directory.exists():raise ValueError('private_output_already_exists')
    target=directory/source.name
    force._copy_family(source,directory)
    board=pcbnew.LoadBoard(str(candidate))
    board.SetFileName(str(target))
    ground=_ground_refill(board)
    field._save_field_snapshot(board,target)
    rule=bind_local_via_rule(board,target)
    return dict(board=str(target),sha256=force._hash(target),ground_refilled=ground,
        local_via_rule=rule,release_authority=False,requires_independent_receiving=True)


def _fixed_supply_rotations(source, candidate, changed, old, new, work):
    """Reconstruct eligible bypass rotations from the immutable native parent.

    No arbitrary pose allowlist: infer selected bypass ownership, keep its
    real supply land centre fixed, prohibit flipping/other edits, and replay
    the full native footprint transform independently. A moved return must
    own a qualified immediate ground path in the saved received child. This
    does not substitute for full DRC/craft/current/assembly receiving.
    """
    import math
    import cec_constraints as constraints
    import cec_decoupler_cell as cell
    before=pcbnew.LoadBoard(str(source));after=pcbnew.LoadBoard(str(candidate))
    first={force._uid(fp):fp for fp in before.GetFootprints()}
    last={force._uid(fp):fp for fp in after.GetFootprints()}
    if first.keys()!=last.keys():raise ValueError('rotation_footprint_population_changed')
    assignment=constraints._device_bypass_assignment(before,project_max_mm=3.5)
    owners={}
    for row in assignment['assigned'].values():
        owners.setdefault(row['cap_ref'],[]).append(row['requirement'])
    selected={};proofs=[];rotations={}
    for uid in sorted(changed):
        if old[uid][0]!='footprint':continue
        fp,target=first[uid],last[uid]
        requirements=owners.get(fp.GetReference(),[])
        if len(requirements)!=1:raise ValueError('rotation_not_uniquely_selected_bypass')
        req=requirements[0];return_rail=req.get('return_rail') or 'GND'
        pads=list(fp.Pads());target_pads=list(target.Pads())
        if (return_rail!='GND' or len(pads)!=2 or len(target_pads)!=2
                or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)
                or fp.IsFlipped()!=target.IsFlipped()):
            raise ValueError('rotation_not_two_land_ground_bypass')
        supplies=[p for p in pads if p.GetNetname()==req['rail']]
        returns=[p for p in pads if p.GetNetname()==return_rail]
        if len(supplies)!=1 or len(returns)!=1:raise ValueError('rotation_pad_roles_ambiguous')
        anchor=supplies[0];landing=target.FindPadByNumber(str(anchor.GetNumber()))
        ground=target.FindPadByNumber(str(returns[0].GetNumber()))
        if (landing is None or ground is None or landing.GetNetname()!=req['rail']
                or ground.GetNetname()!=return_rail or tuple(anchor.GetPosition())!=tuple(landing.GetPosition())):
            raise ValueError('rotation_supply_anchor_changed')
        delta=(target.GetOrientationDegrees()-fp.GetOrientationDegrees())%360
        if not any(abs(delta-angle)<1e-5 for angle in (90.,180.,270.)):
            raise ValueError('rotation_not_declared_quarter_turn')
        pose=(target.GetPosition().x,target.GetPosition().y,target.GetOrientationDegrees())
        if not all(math.isfinite(float(value)) for value in pose):raise ValueError('nonfinite_rotation_pose')
        # Same source footprint, not a candidate clone or guessed pad model.
        fp.SetPosition(target.GetPosition());fp.SetOrientationDegrees(pose[2])
        if tuple(anchor.GetPosition())!=tuple(landing.GetPosition()):
            raise ValueError('rotation_does_not_preserve_native_supply_anchor')
        covered=cell._existing_return(after,ground,1.5,allow_native_track_body=True)
        shared=None
        if covered is None:
            owner=after.FindFootprintByReference(req['ref'])
            if owner is not None:
                for peer in cell._owner_ground_pads(owner):
                    shared=cell._shared_ground_return(after,ground,peer,1.5)
                    if shared is not None:break
            if shared is None:raise ValueError('rotation_has_no_immediate_ground_return')
            via=next((v for v in after.GetTracks() if v.GetClass()=='PCB_VIA'
                      and force._uid(v)==shared['via_uuid']),None)
            if via is None:raise ValueError('rotation_shared_barrel_identity_missing')
        else:
            via=covered[1]
        qualified,reason=fab.local_pofv_via_decision(after,via,allow_source_track_body=True)
        if qualified is not True:raise ValueError('rotation_ground_barrel_unqualified:'+str(reason))
        selected[uid]=fp
        rotations[uid]=(str(anchor.GetNumber()),delta)
        proofs.append(dict(uuid=uid,ref=target.GetReference(),owner_ref=req['ref'],rail=req['rail'],
            supply_pad_uuid=force._uid(anchor),supply_position_nm=force._point(anchor),
            return_pad_uuid=force._uid(ground),rotation_delta_deg=delta,
            ground_via_uuid=force._uid(via),
            ground_topology='selected_owner_shared_entry' if shared else 'immediate_entry',
            ground_path_mm=shared['path_mm'] if shared else covered[0],
            **(dict(shared_ground_evidence=shared) if shared else {}),
            native_copper_mutation_authorized=False))
    if not selected:raise ValueError('no_eligible_fixed_supply_rotation')
    prototype=Path(work)/'pose-reconstruction.kicad_pcb'
    field._save_field_snapshot(before,prototype)
    _,replayed=_nodes(prototype)
    # KiCad Rotate and SetOrientation serialize some equivalent text/land
    # angle representatives differently at half/three-quarter turns. Accept
    # only an exact second native replay, never normalize arbitrary fields or
    # copy the received footprint wholesale.
    mismatches=[uid for uid in selected if sexpr._freeze(replayed[uid])!=sexpr._freeze(new[uid])]
    if mismatches:
        rotated=pcbnew.LoadBoard(str(source))
        by_uid={force._uid(fp):fp for fp in rotated.GetFootprints()}
        for uid,(pin,delta) in rotations.items():
            fp=by_uid[uid];fp.Rotate(fp.FindPadByNumber(pin).GetPosition(),
                                    pcbnew.EDA_ANGLE(delta,pcbnew.DEGREES_T))
        alternate=Path(work)/'native-pivot-reconstruction.kicad_pcb'
        field._save_field_snapshot(rotated,alternate)
        _,alternate_nodes=_nodes(alternate)
        for uid in mismatches:
            replayed[uid]=alternate_nodes[uid]
    for uid in selected:
        if sexpr._freeze(replayed[uid])!=sexpr._freeze(new[uid]):
            raise ValueError('received_footprint_differs_from_native_anchor_rotation')
    return {uid:replayed[uid] for uid in selected},proofs


def _qualified_endpoint_additions(board,path,uuids,native_tracks,*,board_hint=None):
    """Independently classify only incoming, complete pad-local neckdowns.

    Existing ownership is immutable debt, not proof for a new track. The
    project/board full-width contract and native pad/throat geometry must
    qualify every incoming member, without changing those requirements.
    """
    import math
    import cec_route_dimensions as dimensions
    resolver=dimensions.project_resolver(path,board=board)
    cohorts={}
    current_only=set()
    current_domains=None
    current_profile=None
    current_contract=None
    for uid in uuids:
        item=native_tracks.get(uid)
        if item is None or item.GetClass()!='PCB_TRACK' or item.GetNetCode()<=0:
            raise ValueError('incoming_endpoint_not_native_net_track')
        spec=resolver(item.GetNetname()) or {}
        width=max(float(spec.get('track_width') or 0),
            float((spec.get('track_width_by_layer_mm') or {}).get(board.GetLayerName(item.GetLayer())) or 0),
            dimensions.board_limits(board)['track_width'])
        width_nm=math.ceil(width*1e6)
        if width_nm<=0 or item.GetWidth()>=width_nm:
            # The constructor also widens a small class to an executable
            # sustained-current floor. A bounded prefix can then equal the
            # class yet be narrower than that real floor. Do not reject this
            # merely by class equality, and do not infer current authority
            # from the new group's label or an anonymous worker filename.
            # Reuse the same manufacturer-positive, nonaggregate supply-pin
            # classifier as final current checking below.
            if type(board_hint) is not str or not board_hint:
                raise ValueError('incoming_endpoint_not_subclass_escape')
            if current_domains is None:
                import cec_current_topology as topology
                current_domains=topology.board_current_domains(board,board_hint=board_hint)
                current_profile=fab.active_profile_name(board,hint=board_hint)
                current_contract=lambda net:topology.current_contract_for_net(
                    net,board_hint,current_domains)
            net=str(item.GetNetname())
            authority=current_contract(net)
            if net in current_domains or not authority or not current_profile:
                raise ValueError('incoming_current_endpoint_authority_unqualified')
            layer=board.GetLayerName(item.GetLayer())
            required=math.ceil(dimensions.current_trace_widths(
                authority,(layer,),current_profile,rise_c=30.)[layer]*1e6)
            width_nm=max(width_nm,required)
            if item.GetWidth()>=width_nm:
                raise ValueError('incoming_endpoint_not_subclass_escape')
            current_only.add(uid)
        cohorts.setdefault((item.GetNetCode(),item.GetLayer(),width_nm,
            math.ceil(float(spec.get('clearance') or 0)*1e6)),[]).append(item)
    for (_net,_layer,width,clearance),items in cohorts.items():
        qualified,rejected=fr._qualified_endpoint_neckdown_tracks(
            board,items,width,required_clearance=clearance)
        if rejected or {force._uid(t) for t in qualified}!={force._uid(t) for t in items}:
            raise ValueError('incoming_endpoint_geometry_unqualified:'+str(rejected))
    if current_only:
        import cec_constraints as constraints
        legal=constraints._validated_current_supply_escape_uuids(
            board,current_contract,current_profile,current_domains)
        if not current_only<=legal:
            raise ValueError('incoming_current_endpoint_supply_role_unqualified')


def _qualified_pair_return_additions(board, incoming, native_tracks):
    """An ownership extension is only new ordinary native GND barrels.

    This supplies no plane/contact/current waiver. Whole-pair reference and
    field receiving plus native DRC remain independent requirements.
    """
    if not incoming or len(incoming)>128:
        raise ValueError('bounded_exact_pair_return_additions_required')
    proofs=[]
    for uid in sorted(incoming):
        item=native_tracks.get(uid)
        if (item is None or item.GetClass()!='PCB_VIA'
                or item.GetNetname()!='GND' or item.GetNetCode()<=0
                or item.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or item.TopLayer()!=pcbnew.F_Cu or item.BottomLayer()!=pcbnew.B_Cu):
            raise ValueError('pair_return_extension_not_new_native_ground_through_via')
        diameter=item.GetWidth(item.TopLayer());drill=item.GetDrillValue()
        required_diameter,required_drill,limits=fab.board_legal_through_via_geometry(
            board,diameter/1e6,drill/1e6)
        if (diameter<=drill or drill<=0 or diameter<math.ceil(required_diameter*1e6)
                or drill<math.ceil(required_drill*1e6)):
            raise ValueError('pair_return_extension_below_unchanged_board_geometry')
        proofs.append(dict(uuid=uid,diameter_nm=diameter,drill_nm=drill,
                           unchanged_board_limits=limits,plane_and_field_receiving_required=True))
    return proofs


def receive(source,candidate,*,timeout_s=10.0,allow_fixed_supply_rotations=False,
            allow_endpoint_neckdown_additions=False,retired_stale_consumer_group_uuids=(),
            allow_pair_return_via_additions=False,board_hint=None):
    """Strict source-plus-delta replay; uncertainty refuses the saved child."""
    started=time.monotonic()
    report=dict(schema=1,scope='source_plus_additions_ground_refill_receiving',
        ok=False,complete=False,release_authority=False,
        inherited_debt_qualified=False,errors=[],allowed_original_changes=[])
    try:
        if type(timeout_s) not in (int,float) or not 0<timeout_s<=30:
            raise ValueError('invalid_receiving_budget')
        if type(allow_endpoint_neckdown_additions) is not bool:
            raise ValueError('explicit_endpoint_addition_mode_required')
        if type(allow_pair_return_via_additions) is not bool:
            raise ValueError('explicit_pair_return_addition_mode_required')
        if (not isinstance(retired_stale_consumer_group_uuids,(list,tuple))
                or len(retired_stale_consumer_group_uuids)>4
                or len(set(retired_stale_consumer_group_uuids))!=len(retired_stale_consumer_group_uuids)
                or retired_stale_consumer_group_uuids and (type(board_hint) is not str or not board_hint)):
            raise ValueError('bounded_explicit_stale_annotation_scope_and_design_identity_required')
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        old_root,old=_nodes(source);_root,new=_nodes(candidate)
        retired_annotations=set(retired_stale_consumer_group_uuids)
        if old.keys()-new.keys()!=retired_annotations:raise ValueError('original_native_item_removed')
        added=new.keys()-old.keys()
        old_board=pcbnew.LoadBoard(str(source));new_board=pcbnew.LoadBoard(str(candidate))
        if retired_annotations:
            import cec_supply_consumer_branch as consumer
            report['retired_invalid_annotation_receiving']=[consumer.stale_anchor_annotation_plan(
                old_board,u,board_hint=board_hint,timeout_s=min(10.,timeout_s)) for u in sorted(retired_annotations)]
        native_tracks={str(item.m_Uuid.AsString()):item for item in new_board.GetTracks()}
        ground={str(z.m_Uuid.AsString()) for z in old_board.Zones()
            if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
        changed={uid for uid in old.keys()-retired_annotations if sexpr._freeze(old[uid])!=sexpr._freeze(new[uid])}
        endpoint_additions=set()
        pose_nodes={}
        if allow_fixed_supply_rotations and any(old[uid][0]=='footprint' for uid in changed):
            with tempfile.TemporaryDirectory(prefix='cec-anchor-rotation-replay-') as work:
                pose_nodes,report['fixed_supply_rotations']=_fixed_supply_rotations(
                    source,candidate,changed,old,new,work)
        for uid in sorted(changed):
            before,after=old[uid],new[uid]
            if uid in pose_nodes:
                report['allowed_original_changes'].append(dict(uuid=uid,kind='native_fixed_supply_bypass_rotation'))
            elif uid in ground and _without(before,'filled_polygon')==_without(after,'filled_polygon'):
                report['allowed_original_changes'].append(dict(uuid=uid,kind='existing_ground_fill'))
            elif (before[0]=='group' and len(before)>1
                    and before[1]=='"'+fr.LOCAL_POFV_SIGNAL_VIA_GROUP+'"'
                    and _without(before,'members')==_without(after,'members')
                    and _members(before)<=_members(after)):
                incoming=_members(after)-_members(before)
                if not incoming or not incoming<=added:
                    raise ValueError('ownership_extension_not_exact_additions')
                for member in incoming:
                    item=native_tracks.get(member)
                    if item is None or item.GetClass()!='PCB_VIA':
                        raise ValueError('ownership_extension_not_native_via')
                    valid,reason=fab.local_pofv_via_decision(new_board,item,allow_source_track_body=True)
                    if valid is not True:raise ValueError('incoming_local_via_unqualified:'+str(reason))
                report['allowed_original_changes'].append(dict(uuid=uid,
                    kind='exact_local_via_group_extension',added_members=sorted(incoming)))
            elif (allow_pair_return_via_additions and before[0]=='group'
                    and len(before)>1 and before[1]=='"'+fr.LOCAL_PAIR_RETURN_VIA_GROUP+'"'
                    and _without(before,'members')==_without(after,'members')
                    and _members(before)<=_members(after)):
                incoming=_members(after)-_members(before)
                if not incoming or not incoming<=added:
                    raise ValueError('pair_return_extension_not_exact_new_additions')
                proofs=_qualified_pair_return_additions(new_board,incoming,native_tracks)
                report['allowed_original_changes'].append(dict(uuid=uid,
                    kind='exact_new_ground_return_group_extension',added_members=sorted(incoming),
                    geometry_proofs=proofs))
            elif (allow_endpoint_neckdown_additions and before[0]=='group'
                    and len(before)>1 and before[1]=='"'+fr.ENDPOINT_NECKDOWN_GROUP+'"'
                    and _without(before,'members')==_without(after,'members')
                    and _members(before)<=_members(after)):
                incoming=_members(after)-_members(before)
                if not incoming or not incoming<=added:
                    raise ValueError('endpoint_extension_not_exact_additions')
                _qualified_endpoint_additions(new_board,candidate,incoming,native_tracks,
                    board_hint=board_hint)
                endpoint_additions.update(incoming)
                report['allowed_original_changes'].append(dict(uuid=uid,
                    kind='exact_qualified_endpoint_group_extension',added_members=sorted(incoming)))
            else:raise ValueError('original_native_item_changed:'+uid)
        for uid in added:
            node=new[uid]
            if node[0] not in ('segment','via','group'):
                raise ValueError('unsupported_additive_native_item')
            if node[0]=='group':
                if not _members(node)<=added:raise ValueError('new_group_claims_original_material')
                if node[1]=='"'+fr.ENDPOINT_NECKDOWN_GROUP+'"':
                    if not allow_endpoint_neckdown_additions:
                        raise ValueError('explicit_endpoint_addition_mode_required')
                    _qualified_endpoint_additions(new_board,candidate,_members(node),native_tracks,
                        board_hint=board_hint)
                    endpoint_additions.update(_members(node))
                if node[1]=='"'+fr.LOCAL_POFV_SIGNAL_VIA_GROUP+'"':
                    for member in _members(node):
                        item=native_tracks.get(member)
                        if item is None or item.GetClass()!='PCB_VIA':
                            raise ValueError('local_via_group_has_non_via')
                        valid,reason=fab.local_pofv_via_decision(new_board,item,allow_source_track_body=True)
                        if valid is not True:raise ValueError('incoming_local_via_unqualified:'+str(reason))
        def root_metadata(root):
            return sexpr._freeze([root[0],*[node for node in root[1:]
                if not isinstance(node,list) or not any(isinstance(row,list)
                    and row and row[0]=='uuid' for row in node[1:])]])
        if root_metadata(old_root)!=root_metadata(_root):
            raise ValueError('literal_source_root_changed')
        _,old_fixed=force._preservation_snapshot(source)
        _,new_fixed=force._preservation_snapshot(candidate)
        if old_fixed!=new_fixed:raise ValueError('board_settings_changed')
        old_sidecars,new_sidecars=force._sidecars(source),force._sidecars(candidate)
        if any(old_sidecars.get(key)!=new_sidecars.get(key)
                for key in old_sidecars.keys()|new_sidecars.keys() if key!='.kicad_dru'):
            raise ValueError('non_rule_sidecar_changed')
        with tempfile.TemporaryDirectory(prefix='cec-additive-receiving-') as work:
            expected=force._copy_family(source,Path(work)/'family')
            # Build from the original nodes, not the candidate's zone fills.
            # Append exactly the received new copper/groups and monotonically
            # extended group, while retaining every source outline/property.
            base=[]
            for node in old_root[1:]:
                uid=next((row[1].strip('"') for row in node if isinstance(row,list)
                    and row and row[0]=='uuid' and len(row)==2),None) if isinstance(node,list) else None
                if uid in retired_annotations:continue
                base.append(pose_nodes[uid] if uid in pose_nodes else
                    new[uid] if uid in changed and old[uid][0]=='group' else node)
            root=[old_root[0],*base,*[new[uid] for uid in sorted(added)]]
            expected.write_text(_render(root)+'\n')
            replay_stencil=expected.read_bytes().decode('utf-8')
            board=pcbnew.LoadBoard(str(expected));board.SetFileName(str(expected))
            report['replayed_ground_uuids']=_ground_refill(board)
            field._save_field_snapshot(board,expected)
            # Source fields are authority, not serializer-normalization output.
            # Independently refilled GND caches and all NEW native nodes still
            # come from this replay; this is not an original-field waiver.
            from cec_source_retaining_ses_import import retain_replay_source_nodes
            expected.write_bytes(retain_replay_source_nodes(replay_stencil,
                expected.read_bytes().decode('utf-8'),set(old)-retired_annotations,
                set(report['replayed_ground_uuids'])).encode('utf-8'))
            report['expected_exact_local_rule']=bind_local_via_rule(board,expected)
            if endpoint_additions:
                report['expected_exact_endpoint_rule']=bind_local_endpoint_rule(board,expected)
            _,expected_nodes=_nodes(expected)
            differences=expected_nodes.keys()^new.keys()
            differences|={uid for uid in expected_nodes.keys()&new.keys()
                if sexpr._freeze(expected_nodes[uid])!=sexpr._freeze(new[uid])}
            if differences:
                report['native_replay_mismatch_uuids']=sorted(differences)[:16]
                raise ValueError('saved_candidate_differs_from_native_source_delta_refill')
            rule=expected.with_suffix('.kicad_dru');received=candidate.with_suffix('.kicad_dru')
            if rule.exists()!=received.exists() or (rule.exists() and rule.read_bytes()!=received.read_bytes()):
                raise ValueError('candidate_rule_differs_from_exact_native_replay')
        if time.monotonic()-started>=timeout_s:raise ValueError('additive_receiving_deadline')
        report.update(ok=True,complete=True,added_native_uuids=sorted(added),
            original_power_and_terminal_geometry_exact=not bool(pose_nodes),
            original_power_copper_and_supply_anchors_exact=True,
            existing_ground_fill_matches_independent_native_replay=True,
            exact_object_rule_matches_independent_native_replay=True)
    except Exception as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    report['elapsed_s']=round(time.monotonic()-started,6)
    return report
