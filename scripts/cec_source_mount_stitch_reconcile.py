"""Exact existing-library mechanical stitch positions, never a new library.

Only the eight satellite-pad local centers are acquired. Actual drill voids
move: this is NOT identical copper material or factory/current qualification.
The literal receiver permits only independently replayed existing GND fills
in addition. A separately bounded full private receiving stage is mandatory.
"""
import copy
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_library_context as libraries
import cec_source_retaining_ses_import as raw


def _require(value, reason):
    if not value: raise ValueError(reason)


def _budget(value):
    _require(type(value) in (int,float) and math.isfinite(value) and 0<value<=10.,
             'bounded_mount_reconciliation_lease_required')
    return time.monotonic()+value


def _table(source,hint):
    local=source.parent/'fp-lib-table'
    if local.is_file(): return local.resolve()
    import cec_synth_pipeline as synth
    return (Path(synth.Config.load(hint).dir)/'fp-lib-table').resolve(strict=True)


def _uuid(node):
    values=[c[1].strip('"') for c in node[1:] if isinstance(c,list) and c and c[0]=='uuid']
    _require(len(values)==1,'unique_literal_pad_uuid_required')
    return values[0]


def _signature(p):
    return (p.GetNumber(),int(p.GetAttribute()),int(p.GetShape()),tuple(p.GetSize()),
            tuple(p.GetDrillSize()),int(p.GetDrillShape()),tuple(map(int,p.GetLayerSet().Seq())),
            bool(p.HasHole()),any(p.IsBackdrilledOrPostMachined(l)for l in p.GetLayerSet().CuStack()),
            p.GetLocalClearance(),p.GetLocalSolderMaskMargin(),p.GetLocalSolderPasteMargin(),
            p.GetLocalSolderPasteMarginRatio(),int(p.GetZoneConnectionOverrides(None)))


def _inventory(fp):
    pads=list(fp.Pads())
    _require(len(pads)==9 and len({force._uid(p) for p in pads})==9,
             'exact_nine_unique_mount_pads_required')
    for p in pads:
        _require(p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and p.GetShape()==pcbnew.PAD_SHAPE_CIRCLE
                 and p.GetDrillShape()==pcbnew.PAD_DRILL_SHAPE_CIRCLE
                 and p.GetSize().x==p.GetSize().y and p.GetDrillSize().x==p.GetDrillSize().y
                 and 0<p.GetDrillSize().x<p.GetSize().x
                 and not any(p.IsBackdrilledOrPostMachined(l)for l in p.GetLayerSet().CuStack()),
                 'only_positive_circular_full_pth_mount_pads_required')
    ordered=sorted(pads,key=lambda p:p.GetDrillSize().x,reverse=True)
    main,sat=ordered[0],ordered[1:]
    _require(main.GetDrillSize().x>sat[0].GetDrillSize().x
             and tuple(main.GetFPRelativePosition())==(0,0), 'unique_centered_main_mount_bore_required')
    result={}
    for p in sat:
        x,y=map(int,p.GetFPRelativePosition())
        _require((x or y) and (not x or not y or abs(x)==abs(y)),
                 'exact_canonical_eight_radial_directions_required')
        ray=((x>0)-(x<0),(y>0)-(y<0))
        _require(ray not in result,'duplicate_mount_satellite_ray')
        result[ray]=p
    _require(set(result)=={(x,y)for x in(-1,0,1)for y in(-1,0,1)if x or y},
             'all_eight_distinct_mount_rays_required')
    _require(len({_signature(p) for p in sat})==1,'uniform_source_satellite_geometry_required')
    return main,result


def _court(fp):
    # Local authored courtyard graphics, not a world-coordinate AABB.
    return sorted((int(i.GetLayer()),int(i.GetShape()),tuple(i.GetStart()-fp.GetPosition()),
                   tuple(i.GetEnd()-fp.GetPosition()),i.GetWidth())
                  for i in fp.GraphicalItems() if i.GetClass()=='PCB_SHAPE'
                  and i.GetLayer() in (pcbnew.F_CrtYd,pcbnew.B_CrtYd))


def plan(source,*,board_hint,mount_uuids,timeout_s=10.,terminal_mode='existing_ground'):
    _require(terminal_mode in('existing_ground','source_unassigned_mechanical')
        and type(terminal_mode)is str,'explicit_supported_mount_terminal_mode_required')
    deadline=_budget(timeout_s);source=Path(source).resolve(strict=True)
    _require(type(board_hint)is str and bool(board_hint)
             and type(mount_uuids)in(list,tuple) and 1<=len(mount_uuids)<=16
             and all(type(u)is str and u for u in mount_uuids) and len(set(mount_uuids))==len(mount_uuids),
             'explicit_unique_source_mount_uuid_scope_required')
    sha=force._hash(source);table=_table(source,board_hint)
    mode_epoch=(force._family(source,board_hint),force._code_identity())\
        if terminal_mode=='source_unassigned_mechanical'else None
    authority=libraries.authority(source,table)
    board=pcbnew.LoadBoard(str(source));_require(board is not None,'actual_native_source_board_required')
    fps={force._uid(fp):fp for fp in board.GetFootprints()};_,nodes=additive._nodes(source);rows=[];terminals=[]
    for uid in mount_uuids:
        _require(time.monotonic()<deadline,'mount_plan_deadline')
        fp=fps.get(uid);_require(fp is not None,'actual_source_mount_uuid_required')
        nickname,item=str(fp.GetFPIDAsString()).split(':',1)
        attrs=pcbnew.FP_EXCLUDE_FROM_BOM|pcbnew.FP_EXCLUDE_FROM_POS_FILES
        _require(item.startswith('MountingHole_') and fp.GetAttributes()&attrs==attrs,
                 'positive_source_library_mechanical_mount_role_required')
        row=authority['rows'].get(nickname)
        _require(row is not None and row['enabled'],'enabled_existing_source_library_required')
        vendor=(Path(row['path'])/(item+'.kicad_mod')).resolve(strict=True)
        vendor_sha=force._hash(vendor);canonical=pcbnew.FootprintLoad(str(vendor.parent),item)
        _require(canonical is not None,'actual_canonical_mount_item_required')
        canonical.SetParent(board)
        authored_layers={force._uid(p):pcbnew.LSET(p.GetLayerSet())for p in canonical.Pads()}
        # Match canonical in the exact source pose/face. Source metadata,
        # references, visibility, UUIDs and locks are never copied from it.
        canonical.SetPosition(fp.GetPosition())
        if fp.IsFlipped():
            # These full-through mechanical pads have symmetric *.Cu and
            # *.Mask authority. Native Flip truncates unused inner-layer
            # bits to the current stack; retain the authored library mask.
            _require(all(p.IsOnLayer(pcbnew.F_Cu)and p.IsOnLayer(pcbnew.B_Cu)
                         and p.IsOnLayer(pcbnew.F_Mask)and p.IsOnLayer(pcbnew.B_Mask)
                         for p in canonical.Pads()),'symmetric_full_through_library_mount_required')
            canonical.Flip(canonical.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            for pad in canonical.Pads():pad.SetLayerSet(authored_layers[force._uid(pad)])
        canonical.SetOrientationDegrees(fp.GetOrientationDegrees())
        main,sat=_inventory(fp);expected_main,expected_sat=_inventory(canonical)
        _require(_signature(main)==_signature(expected_main) and _court(fp)==_court(canonical),
                 'canonical_main_bore_land_and_hardware_courts_must_already_match')
        _require(all(p.GetNetCode()==main.GetNetCode() and p.GetNumber()==main.GetNumber()
                         and tuple(p.GetLayerSet().Seq())==tuple(main.GetLayerSet().Seq())for p in sat.values()),
                 'one_uniform_existing_mount_terminal_required')
        isolation=None
        if terminal_mode=='existing_ground':
            _require(main.GetNetname()=='GND' and main.GetNetCode()>0,
                'one_explicit_existing_ground_mount_terminal_required')
        else:
            import cec_unassigned_mount_isolation as unassigned
            _require(all(p.GetNetCode()==0 and not p.GetNetname()for p in fp.Pads()),
                'literal_unassigned_mechanical_mount_required')
            isolation=unassigned.isolated(board,fp,main,list(sat.values()),deadline=deadline)
            terminals.append(fp.GetReference()+'.'+main.GetNumber())
        changes=[]
        for ray,pad in sorted(sat.items()):
            target=expected_sat[ray]
            _require(_signature(pad)==_signature(target),'canonical_satellite_drill_land_layer_annulus_required')
            at=list(map(int,pad.GetFPRelativePosition()));to=list(map(int,target.GetFPRelativePosition()))
            if at!=to:changes.append(dict(pad_uuid=force._uid(pad),before_nm=at,after_nm=to))
        literal_pads={_uuid(c)for c in nodes[uid][1:]if isinstance(c,list)and c and c[0]=='pad'}
        _require(literal_pads=={force._uid(p)for p in fp.Pads()},'exact_literal_native_pad_identity_required')
        if terminal_mode=='source_unassigned_mechanical':
            changed_ids={c['pad_uuid']for c in changes}
            for node in nodes[uid][1:]:
                if not isinstance(node,list)or not node or node[0]!='pad'or _uuid(node)not in changed_ids:continue
                locks=[c for c in node[1:]if c=='locked'or isinstance(c,list)and c and c[0]=='locked']
                _require(not locks or locks==[['locked','no']],
                    'directly_locked_mount_satellite_refused')
        record=dict(footprint_uuid=uid,reference=fp.GetReference(),fpid=str(fp.GetFPIDAsString()),
            vendor=str(vendor),vendor_sha256=vendor_sha,main_pad_uuid=force._uid(main),changes=changes)
        if isolation is not None:record['unassigned_isolation']=isolation
        rows.append(record)
    mode_binding={}
    if terminal_mode=='source_unassigned_mechanical':
        mode_binding=dict(terminal_mode=terminal_mode,
            unassigned_policy_binding=unassigned.policy_binding(board_hint,terminals),
            source_family=mode_epoch[0],code_identity=mode_epoch[1])
        _require(mode_epoch==(force._family(source,board_hint),force._code_identity()),
            'unassigned_mount_source_or_code_epoch_changed')
    _require(force._hash(source)==sha and libraries.authority(source,table)==authority,
             'source_or_vendor_epoch_changed_during_mount_plan')
    result=dict(schema=1,scope='exact_existing_library_mount_satellite_centers',source=str(source),
        source_sha256=sha,board_hint=board_hint,mount_uuids=list(mount_uuids),library_authority=authority,
        rows=rows,complete=True,changed_pad_count=sum(len(q['changes'])for q in rows),
        current_qualified=False,factory_qualified=False,release_authority=False,routing_admitted=False,
        **mode_binding)
    # Library manifests contain internal tuples; new typed family bindings
    # may do so too. A public saved plan must have the SAME representation
    # before and after JSON, without dropping or weakening any identity. The
    # fresh planner is canonicalized in exactly this way on every replay.
    return json.loads(json.dumps(result,sort_keys=True,allow_nan=False))


def _fresh(proposal):
    _require(plan(proposal['source'],board_hint=proposal['board_hint'],mount_uuids=proposal['mount_uuids'],
        terminal_mode=proposal.get('terminal_mode','existing_ground'))==proposal,
             'stale_or_forged_source_library_mount_plan')


def apply(board,proposal):
    _fresh(proposal)
    original=pcbnew.LoadBoard(proposal['source'])
    _require(field._field_snapshot_inventory(original)==field._field_snapshot_inventory(board),
             'exact_native_source_mount_board_required')
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    for row in proposal['rows']:
        for change in row['changes']:pads[change['pad_uuid']].SetFPRelativePosition(pcbnew.VECTOR2I(*change['after_nm']))
    return dict(changed_pad_count=proposal['changed_pad_count'],release_authority=False)


def expected_nodes(proposal,*,refill_ground=True):
    _fresh(proposal);_,nodes=additive._nodes(proposal['source']);expected=copy.deepcopy(nodes)
    for row in proposal['rows']:
        changes={c['pad_uuid']:c['after_nm']for c in row['changes']}
        for child in expected[row['footprint_uuid']][1:]:
            if not isinstance(child,list)or not child or child[0]!='pad':continue
            uid=_uuid(child)
            if uid not in changes:continue
            ats=[c for c in child[1:]if isinstance(c,list)and c and c[0]=='at']
            _require(len(ats)==1 and len(ats[0])in(3,4),'one_literal_satellite_local_position_required')
            for k,v in enumerate(changes[uid],1):ats[0][k]=str(Decimal(v)/Decimal(1000000))
    if refill_ground:
        board=pcbnew.LoadBoard(proposal['source']);apply(board,proposal);additive._ground_refill(board)
        with tempfile.TemporaryDirectory(prefix='cec-mount-ground-replay-')as directory:
            path=Path(directory)/'expected.kicad_pcb';field._save_field_snapshot(board,path);_,filled=additive._nodes(path)
        for uid,node in nodes.items():
            if node[0]!='zone':continue
            net=[c for c in node if isinstance(c,list)and c and c[0]=='net_name']
            # Native ZONE electrical identity, never caller annotation.
            zone=next(z for z in board.Zones()if force._uid(z)==uid)
            if zone.GetIsRuleArea()or zone.GetNetname()!='GND':continue
            _require(additive._without(node,'filled_polygon')==additive._without(filled[uid],'filled_polygon'),
                     'ground_refill_changed_source_zone_declaration')
            expected[uid]=[c for c in expected[uid]if not(isinstance(c,list)and c and c[0]=='filled_polygon')]
            expected[uid].extend(c for c in filled[uid]if isinstance(c,list)and c and c[0]=='filled_polygon')
    return expected


def construct_private(source,candidate,proposal):
    _require(Path(source).resolve()==Path(proposal['source'])and Path(source).resolve()!=Path(candidate).resolve()
             and force._hash(Path(candidate))==proposal['source_sha256'],'exact_private_mount_source_copy_required')
    nodes=expected_nodes(proposal);text=raw.raw_text(source);spans=raw.inventory(text);_,old=additive._nodes(source)
    changed={u for u in old if syntax._freeze(old[u])!=syntax._freeze(nodes[u])}
    for uid in sorted(changed,key=lambda u:spans[u][0],reverse=True):
        a,z=spans[uid];text=text[:a]+additive._render(nodes[uid])+text[z:]
    raw.write_raw(candidate,text)
    return dict(candidate=str(candidate),candidate_sha256=force._hash(Path(candidate)),
                changed_root_uuids=sorted(changed),routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,mount_uuids,timeout_s=10.,terminal_mode='existing_ground'):
    deadline=_budget(timeout_s);report=dict(ok=False,complete=False,errors=[],routing_admitted=False,
        current_qualified=False,factory_qualified=False,release_authority=False,
        mandatory_full_receivers=['factory_bore_annular_hole_edge','native_ground_preservation',
            'original_parent_current_protected_pair','source_candidate_intake','parity','native_all_findings','craft','live_epoch'])
    try:
        proposal=plan(source,board_hint=board_hint,mount_uuids=mount_uuids,timeout_s=max(.001,deadline-time.monotonic()),
            terminal_mode=terminal_mode)
        expected=expected_nodes(proposal);actual_root,actual=additive._nodes(candidate)
        _require(actual.keys()==expected.keys()and all(syntax._freeze(actual[u])==syntax._freeze(n)
            for u,n in expected.items()),'exact_source_satellite_and_selected_ground_replay_differs')
        # UUID maps omit setup/layers/general and other opaque board roots.
        # Preserve the complete Source tree, substituting only the separately
        # reconstructed UUID-bearing objects. A matching item map cannot
        # grant permission to lower a saved board floor or alter its stack.
        source_root,source_nodes=additive._nodes(source)
        expected_root=copy.deepcopy(source_root)
        for index,node in enumerate(source_root):
            if not isinstance(node,list):continue
            ids=[c[1].strip('"')for c in node[1:]if isinstance(c,list)and len(c)==2 and c[0]=='uuid']
            _require(len(ids)<=1,'unique_literal_root_uuid_required')
            if ids:
                _require(ids[0]in source_nodes and ids[0]in expected,'known_literal_mount_root_required')
                expected_root[index]=expected[ids[0]]
        _require(syntax._freeze(expected_root)==syntax._freeze(actual_root),
            'complete_source_root_outside_mount_delta_changed')
        _fresh(proposal);_require(time.monotonic()<deadline,'mount_literal_receiving_deadline')
        report.update(ok=True,complete=True,changed_pad_count=proposal['changed_pad_count'],
                      source_library_authority=proposal['library_authority'],scope_only_never_admission=True)
    except (ValueError,RuntimeError,OSError,KeyError,TypeError)as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report


def receive_physical(source,candidate,proposal,*,timeout_s=10.):
    """Independent changed-mount factory geometry and all-source partition gate.

    This does not run DRC, current, local-return, intake, parity or manufacture
    qualification. A caller must require those independently, not consume this
    Boolean as a full receiving certificate.
    """
    import cec_fab_check as factory
    import cec_fab_native_geometry as holes
    import cec_fab_profile as profile
    import cec_board_geometry as geometry
    import cec_ordinary_route_receiving as ordinary
    deadline=_budget(timeout_s);_fresh(proposal)
    literal=receive(source,candidate,board_hint=proposal['board_hint'],mount_uuids=proposal['mount_uuids'],
                    timeout_s=max(.001,deadline-time.monotonic()),
                    terminal_mode=proposal.get('terminal_mode','existing_ground'))
    _require(literal['ok']and literal['complete'],'literal_mount_receiving_required_before_physics')
    boards=[pcbnew.LoadBoard(str(p))for p in(source,candidate)];parent,child=boards
    declared=profile.board_profile_name(parent)
    _require(declared is not None and declared==profile.board_profile_name(child),
             'unchanged_declared_mount_factory_profile_required')
    rules=factory.profile_rules(factory.PROFILES['jlcpcb'],factory.board_outer_copper_oz(source),declared)
    changed={q['pad_uuid']for row in proposal['rows']for q in row['changes']}
    audits=[]
    for path,b in zip((source,candidate),boards):
        remaining=deadline-time.monotonic();_require(remaining>0,'mount_physical_receiving_deadline')
        audit=holes.audit_holes(b,rules,board_path=path,timeout_s=min(10.,remaining))
        _require(audit['complete'],'complete_factory_mount_drill_audit_required');audits.append(audit)
    def identity(row):return tuple(sorted((row['left']['uuid'],row['right']['uuid'])))
    old={identity(row):row for row in audits[0]['findings']}
    for row in audits[1]['findings']:
        pair=identity(row)
        _require(not changed.intersection(pair),'changed_mount_hole_has_factory_spacing_fault')
        _require(pair in old and row['floor_mm']==old[pair]['floor_mm']
                 and row['signed_gap_mm']>=old[pair]['signed_gap_mm'],
                 'new_or_worsened_factory_hole_fault')
    outline=geometry.outline_material(child);boundaries=geometry.material_boundaries(outline)
    selected=set(proposal['mount_uuids']);rebindings={}
    original={force._uid(p):p for fp in parent.GetFootprints()for p in fp.Pads()}
    for fp in child.GetFootprints():
        if force._uid(fp)not in selected:continue
        for pad in fp.Pads():
            _require((pad.GetSize().x-pad.GetDrillSize().x)/2>=max(
                factory.PROFILES['jlcpcb']['min_annular']*1e6,child.GetDesignSettings().m_ViasMinAnnularWidth),
                'ordinary_mount_annular_floor_required')
            _require(pad.GetDrillSize().x>=max(factory.PROFILES['jlcpcb']['min_drill']*1e6,
                child.GetDesignSettings().m_MinThroughDrill),'ordinary_mount_drill_floor_required')
            margin=math.ceil(pad.GetSize().x/2+max(rules['edge']*1e6,
                child.GetDesignSettings().m_CopperEdgeClearance))
            _require(geometry.material_leg_clear(outline,boundaries,pad.GetPosition(),pad.GetPosition(),margin),
                     'mount_contact_land_or_bore_outside_factory_edge')
            uid=force._uid(pad)
            if uid in changed:rebindings[force._item_key(pad)]=force._item_key(original[uid])
    isolated_reports=[]
    if proposal.get('terminal_mode')=='source_unassigned_mechanical':
        import cec_unassigned_mount_isolation as unassigned
        import cec_native_partition_pair as partitions
        for b in boards:
            for fp in b.GetFootprints():
                if force._uid(fp)not in selected:continue
                main,sat=_inventory(fp)
                isolated_reports.append(unassigned.isolated(b,fp,main,list(sat.values()),deadline=deadline))
        remaining=deadline-time.monotonic();_require(remaining>0,'mount_physical_receiving_deadline')
        partition=partitions.compare(parent,child,timeout_s=min(10.,remaining))
        _require(partition['available']and partition['preserved'],
            'source_native_ground_or_conductor_partition_lost')
    else:
        before=ordinary._partition(parent,deadline)
        after=ordinary._partition(child,deadline,_identity_rebindings=rebindings)
        _require(set().union(*before)==set().union(*after)
                 and all(any(a<=z for z in after)for a in before),
                 'source_native_ground_or_conductor_partition_lost')
    _fresh(proposal);_require(time.monotonic()<deadline,'mount_physical_receiving_deadline')
    return dict(ok=True,complete=True,factory_hole_reports=audits,
        literal_receiving=literal,
        main_bores_annuli_mount_centers_and_hardware_source_exact=True,
        all_source_native_partitions_preserved=True,changed_mechanical_pad_identity_rebindings=[
            dict(candidate=k,source=v)for k,v in rebindings.items()],
        unassigned_isolation_reports=isolated_reports,
        current_qualified=False,factory_qualified=False,release_authority=False,
        mandatory_native_current_local_return_intake_parity_craft_live_receiving_still_required=True)


def native_nonregression(before,after):
    """Exact findings, not a required decrease in an unrelated warning count.

    Source-library coordinate replay proves normalization. Native DRC may
    already consider a small drift within its comparison tolerance; requiring
    it to remove a nonexistent warning rejects a real source correction.
    No new finding, inherited error, exclusion or increased opens is waived.
    """
    import cec_received_private_stage as stage
    delta=stage.native_findings_delta(before,after)
    passed=(delta['ok'] is True
        and not any(v.get('severity')=='error' for v in after['violations'])
        and not before.get('excluded_violations') and not after.get('excluded_violations')
        and len(after['unconnected_items'])<=len(before['unconnected_items']))
    return dict(ok=bool(passed),findings_delta=delta,inherited_findings_qualified=False)


def receive_full(source,candidate,out,*,board_hint,mount_uuids,assembly_instance=None,terminal_mode='existing_ground'):
    """Saved mechanical proof plus unchanged shared gates; outer caller <=120s.

    No publication. Every geometric/native lease is <=10s. Literal replay
    preserves all protected copper/pair/group nodes, not an additive waiver.
    """
    import json
    import traceback
    import cec_received_private_stage as stage
    import cec_current_debt as current
    import cec_ground_return_preservation as returns
    import cec_native_drc_runner as native
    import cec_synth_pipeline as synth
    import cec_constraints as constraints
    import cec_route_quality as quality
    source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    result=dict(ok=False,complete=False,admitted=False,current_qualified=False,
        factory_qualified=False,thermal_qualified=False,release_authority=False,
        candidate=str(candidate),candidate_sha256=force._hash(candidate),gates={},reports={})
    gates=result['gates'];reports=result['reports'];started=time.monotonic()
    paths=[source,candidate]
    try:
        identities=[stage.identity(p,board_hint,assembly_instance if p==source else
            stage.matched_instance(assembly_instance,candidate))for p in paths]
        proposal=plan(source,board_hint=board_hint,mount_uuids=mount_uuids,terminal_mode=terminal_mode)
        reports['literal']=receive(source,candidate,board_hint=board_hint,mount_uuids=mount_uuids,terminal_mode=terminal_mode)
        reports['physical']=receive_physical(source,candidate,proposal)
        gates['operator']=all(reports[k].get('ok')is True and reports[k].get('complete')is True
                              for k in ('literal','physical'))
        if not gates['operator']:raise ValueError('mechanical_scope_refused')
        # Project companions/rules may not change. PCB delta was received above.
        a,b=[force._companion_inventory(p)[0]for p in paths]
        gates['project_rules']=set(a)==set(b)and all(force._hash(a[k])==force._hash(b[k])for k in a)
        reports['current']=current.receive(source,candidate,board_hint=board_hint)
        gates['current']=reports['current'].get('ok')is True and reports['current'].get('complete')is True
        reports['field']=field.assess_native_mechanical_mount(source,candidate,board_hint=board_hint,
            mount_uuids=mount_uuids,timeout_s=10.,terminal_mode=terminal_mode)
        gates['field']=reports['field'].get('ok')is True and reports['field'].get('complete')is True
        parent,child=[pcbnew.LoadBoard(str(p))for p in paths]
        reports['ground_returns']=returns.receive(parent,child,timeout_s=10.)
        gates['ground_returns']=reports['ground_returns'].get('ok')is True and reports['ground_returns'].get('complete')is True
        cfg=synth.Config.load(board_hint)
        intakes,session=stage.receive_intakes(cfg,source,candidate,out,assembly_instance=assembly_instance)
        reports.update(intakes)
        for name in ('source','candidate'):
            gates[name+'_intake']=reports[name+'_intake'].get('ok')is True and reports[name+'_intake'].get('intake',{}).get('ok')is True
        build=Path('/home/codex/.cache/cec/native-drc-10.0.5')
        expected=native._describe_build(build)
        native_reports=[]
        for name,path,identity in zip(('source','candidate'),paths,identities):
            report=out/(name+'-native.json')
            proof=native.run(path,report,reporting_build=build,timeout_s=10.,board_hint=board_hint)
            stage.require_native_tool(proof,expected)
            context=proof.get('native_library_context',{})
            if not(context.get('bound')is True and context.get('source_and_context_unchanged')is True
                   and stage.stable(context.get('authority'))==identity['native_library_authority']):
                raise ValueError('native_library_epoch_mismatch')
            reports[name+'_native_producer']=proof;native_reports.append(json.loads(report.read_text()))
        before,after=native_reports
        reports['native_nonregression']=native_nonregression(before,after)
        reports['native_delta']=reports['native_nonregression']['findings_delta']
        warnings=lambda r:sum(v.get('severity')=='warning'for v in r['violations'])
        gates['native']=reports['native_nonregression']['ok']
        reports['native_counts']=[dict(opens=len(r['unconnected_items']),warnings=warnings(r))for r in native_reports]
        reports['parity']=constraints._chk_sch_pcb_sync(child,str(candidate),{'sch':str(cfg.sch)})
        gates['parity']=reports['parity'][0]is True
        reports['craft']=[quality.analyze_board(x)for x in (parent,child)]
        gates['craft']=all(reports['craft'][1][k]<=reports['craft'][0][k]for k in ('issue_count','non_octilinear_count'))
        gates['source_live']=identities==[stage.identity(p,board_hint,assembly_instance if p==source else
            stage.matched_instance(assembly_instance,candidate))for p in paths]
        if terminal_mode=='source_unassigned_mechanical':
            _fresh(proposal)
            gates['unassigned_policy_and_source_live']=True
        result['complete']=True
        result['ok']=all(value is True for value in gates.values())
    except Exception as exc:
        result['error']=str(exc);result['traceback']=traceback.format_exc()
    finally:
        result['elapsed_s']=time.monotonic()-started
        force._write(out/'receiving.json',result)
    return result
