"""Negotiated, source-owned ordinary detours for a real ground ingress.

One obstructing ordinary stroke and at most one actual dependent neighbour
may take bounded 0/45 detours. No power, pair, analog, clock, pad, barrel or
pour moves. Geometry hints never grant ownership. The saved signal repair
and the subsequent source-rule in-pad ground entry are independently replayed
against their ORIGINAL parents, then received as a complete two-phase chain.
No intermediate signal-only repair is an admitted result of this operator.
"""
import math
import tempfile
import time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_access_completion as ground
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as shortcut
import cec_native_ground_span_reflow as lease
import cec_native_via_obstruction_stack as stack
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
import cec_source_guided_ordinary_detour as guide
from cec_native_items import discard_items

SCOPE='source_owned_negotiated_ordinary_ground_ingress'


def _length(points):
    q=guide.length_terms(points)
    return q['cardinal_nm']+math.sqrt(2)*q['diagonal_component_nm']


def _context(source,board_hint,pad_uuid,deadline):
    board=pcbnew.LoadBoard(str(source));pad,face=ground._pad(board,pad_uuid)
    before=cells._existing_return(board,pad,16.,allow_native_track_body=True)
    if before is None or before[0]<=1.5:
        raise ValueError('positive_known_nonlocal_source_ground_return_required')
    context,group,geometry=ground._existing_pad_rule(board,pad)
    diameter,drill=[round(v*1e6) for v in geometry]
    # The larger of actual project/netclass and native limits; never a
    # smaller clearance inferred from the new via diameter.
    spec=cells._netclass(board,'GND')
    clearance=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
    proof=stack.inspect(board,pad.GetPosition(),diameter,clearance,pad.GetNetCode(),
        timeout_s=min(5.,max(.001,deadline-time.monotonic())))
    if (not proof['complete'] or len(proof.get('distinct_copper_blocker_uuids',[]))!=1):
        raise ValueError('complete_single_ordinary_source_ingress_blocker_required')
    return board,pad,face,before[0],context,group,geometry,clearance,proof


def _selected(board,source,board_hint,ids,allow_locked_source):
    live={force._uid(t):t for t in board.GetTracks()}
    if len(live)>16384 or not set(ids)<=live.keys():raise ValueError('bounded_actual_ingress_source_tracks_required')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    eligible=ordinary.eligible_nets(board,source,board_hint)
    faces={board.GetLayerID(n) for n in fab.routing_layers(board,include_power=False)}
    selected=[live[u] for u in ids]
    for t in selected:
        if (t.GetClass()!='PCB_TRACK' or force._uid(t) in grouped or t.GetParentGroup()
                or t.HasSolderMask() or t.GetNetname() not in eligible or int(t.GetLayer()) not in faces
                or not board.GetDesignSettings().m_TrackMinWidth<=t.GetWidth()<500000
                or t.IsLocked() and not allow_locked_source):
            raise ValueError('positive_ungrouped_source_ordinary_stroke_and_explicit_lock_scope_required')
        points=[list(t.GetStart()),list(t.GetEnd())];guide.length_terms(points)
        extent=max(abs(points[1][i]-points[0][i]) for i in (0,1))
        if not 200000<=extent<=64000000:raise ValueError('bounded_straight_source_ingress_stroke_required')
    if len(selected)==2 and (selected[0].GetNetCode()==selected[1].GetNetCode()
            or selected[0].GetLayer()!=selected[1].GetLayer()):
        raise ValueError('dependent_peer_must_be_distinct_ordinary_net_on_same_face')
    return selected


def _via_clear(board,pad,geometry,clearance):
    diameter,drill=[round(v*1e6) for v in geometry];at=pad.GetPosition()
    face=cells.cec_return_escape.smd_surface_layer(pad)
    return (fr._edge_leg_clear(board,at,at,diameter//2)
        and cells._hole_to_hole_clear(board,at,geometry[1])[0]
        and fr._via_spot_clear(board,at,diameter,clearance,{pad.GetNetCode()},
            drill_nm=drill,net_code=pad.GetNetCode(),contained_layers={face},local_pofv_pad=pad))


def _ghost_via(board,pad,geometry):
    v=pcbnew.PCB_VIA(board);v.SetPosition(pad.GetPosition());v.SetNet(pad.GetNet())
    v.SetWidth(round(geometry[0]*1e6));v.SetDrill(round(geometry[1]*1e6))
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.m_Uuid.Clone(pcbnew.KIID());board.Add(v);return v


def plan(source,*,board_hint,pad_uuid,peer_track_uuid=None,allow_locked_source=False,
         max_extra_mm=1.,max_offset_mm=1.,timeout_s=10.):
    deadline=lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(pad_uuid) is not str or not pad_uuid
            or peer_track_uuid is not None and (type(peer_track_uuid) is not str or not peer_track_uuid)
            or type(allow_locked_source) is not bool
            or any(type(v) not in (int,float) or not math.isfinite(v) or not .1<=v<=2.
                for v in (max_extra_mm,max_offset_mm))):
        raise ValueError('bounded_typed_source_ground_ingress_contract_required')
    source=Path(source).resolve();family=force._family(source,board_hint)
    parent,pad,face,before,context,group,geometry,clearance,proof=_context(source,board_hint,pad_uuid,deadline)
    primary=proof['distinct_copper_blocker_uuids'][0]
    if primary==peer_track_uuid:raise ValueError('ingress_peer_must_not_duplicate_primary')
    ids=[primary]+([peer_track_uuid] if peer_track_uuid else [])
    selected=_selected(parent,source,board_hint,ids,allow_locked_source)
    if len(selected)==2 and not selected[1].GetEffectiveShape(face if selected[1].IsOnLayer(face)
            else selected[1].GetLayer()).Collide(pad.GetPosition(),round(max_offset_mm*1e6)+clearance):
        raise ValueError('dependent_ordinary_peer_must_be_in_source_ingress_corridor')
    work=pcbnew.LoadBoard(str(source));work_pad,_=ground._pad(work,pad_uuid)
    discard_items(work,[t for t in work.GetTracks() if force._uid(t) in ids])
    if not _via_clear(work,work_pad,geometry,clearance):
        raise ValueError('ingress_has_another_native_process_drill_edge_or_copper_blocker')
    ghost=_ghost_via(work,work_pad,geometry);shortcut._reference_contacts(work,ghost)
    resolver=fr._project_netclass_resolver(str(source));choices=[]
    def options(t,dependency=None):
        gap=max(200000,int(parent.GetDesignSettings().m_MinClearance),
            fr._nm(float((resolver(t.GetNetname()) or {}).get('clearance') or 0)))
        old=[list(t.GetStart()),list(t.GetEnd())]
        def validate(points):
            if _length(points)-_length(old)>max_extra_mm*1e6:return False
            if points==old or not guide._source_contacts(parent,[t],points,deadline):return False
            if dependency is not None:
                shape=dependency.GetEffectiveShape(t.GetLayer())
                if not any(shape.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),
                        pcbnew.VECTOR2I(*b),t.GetWidth()),gap) for a,b in zip(points,points[1:])):return False
            return True
        return guide.propose(work,old,net_code=t.GetNetCode(),layer=int(t.GetLayer()),width_nm=t.GetWidth(),
            clearance_nm=gap,deadline=deadline,samples=128,max_checked=512,max_returned=3,
            max_offset_nm=round(max_offset_mm*1e6),max_padding_nm=2000000,validate=validate)
    initial=options(selected[0],selected[1] if len(selected)==2 else None)
    for option in initial['options']:
        points=option['points_nm'];ghost_tracks=[]
        for a,b in zip(points,points[1:]):
            t=selected[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));work.Add(t);ghost_tracks.append(t)
        try:
            if len(selected)==1:choices=[points];break
            second=options(selected[1])
            if second['options']:choices=[points,second['options'][0]['points_nm']];break
        finally:discard_items(work,ghost_tracks)
    if not choices:raise ValueError('bounded_negotiated_ordinary_ingress_has_no_native_clear_option')
    paths=[]
    for t,points in zip(selected,choices):
        old=[list(t.GetStart()),list(t.GetEnd())]
        paths.append(dict(source_track_uuid=force._uid(t),net=t.GetNetname(),layer=int(t.GetLayer()),
            width_nm=t.GetWidth(),locked=bool(t.IsLocked()),source_points_nm=old,candidate_points_nm=points,
            source_length=guide.length_terms(old),candidate_length=guide.length_terms(points)))
    if time.monotonic()>=deadline or family!=force._family(source,board_hint):
        raise ValueError('ground_ingress_source_family_or_plan_lease_changed')
    return dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),
        source_native_binding=row._source_binding(parent),board_hint=board_hint,pad_uuid=pad_uuid,
        peer_track_uuid=peer_track_uuid,allow_locked_source=allow_locked_source,
        max_extra_mm=max_extra_mm,max_offset_mm=max_offset_mm,paths=paths,
        retired_track_uuids=sorted(ids),allow_locked_track_uuids=sorted(force._uid(t) for t in selected if t.IsLocked()),
        source_return_witness_mm=before,source_local_rule=context,source_local_rule_group_uuid=group,
        source_via_geometry_mm=list(geometry),native_obstruction_stack=proof,
        peer_is_actual_native_blocker_of_primary_detour=bool(peer_track_uuid),
        all_source_ports_tangents_widths_process_and_side_contacts_preserved=True,
        intermediate_is_not_an_admitted_result=True,whole_native_fields_current_and_fab_receiving_required=True,
        current_qualified=False,fab_ready=False,release_authority=False)


def _args(q):
    return {k:q[k] for k in ('board_hint','pad_uuid','peer_track_uuid','allow_locked_source',
        'max_extra_mm','max_offset_mm')}


def construct(proposal,*,incoming_uuids=None):
    if plan(proposal['source'],**_args(proposal))!=proposal:raise ValueError('stale_or_forged_ground_ingress_plan')
    count=sum(len(p['candidate_points_nm'])-1 for p in proposal['paths'])
    if incoming_uuids is not None and (type(incoming_uuids) is not list or len(incoming_uuids)!=count
            or len(set(incoming_uuids))!=count or any(type(u) is not str or not u for u in incoming_uuids)):
        raise ValueError('exact_ground_ingress_replacement_identities_required')
    board=pcbnew.LoadBoard(proposal['source']);live={force._uid(t):t for t in board.GetTracks()}
    prototypes=[live[p['source_track_uuid']].Duplicate() for p in proposal['paths']]
    discard_items(board,[live[u] for u in proposal['retired_track_uuids']]);index=0
    for prototype,path in zip(prototypes,proposal['paths']):
        for a,b in zip(path['candidate_points_nm'],path['candidate_points_nm'][1:]):
            t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[index]) if incoming_uuids else pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t);index+=1
    return board


def receive(source,intermediate,proposal,*,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],scope=SCOPE,current_qualified=False,fab_ready=False,release_authority=False)
    try:
        deadline=lease._deadline(timeout_s);source,intermediate=[Path(p).resolve() for p in (source,intermediate)]
        if source==intermediate or str(source)!=proposal['source']:
            raise ValueError('exact_distinct_source_ground_ingress_chain_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint']) for p in (source,intermediate)]
        q=plan(source,**_args(proposal),timeout_s=max(.001,deadline-time.monotonic()))
        if q!=proposal:raise ValueError('independent_ground_ingress_plan_differs')
        _,old=additive._nodes(source);_,new=additive._nodes(intermediate)
        incoming=set(new)-set(old)
        if set(old)-set(new)!=set(q['retired_track_uuids']):raise ValueError('exact_ground_ingress_retirement_required')
        child=pcbnew.LoadBoard(str(intermediate));live={force._uid(t):t for t in child.GetTracks()};ordered=[]
        for p in q['paths']:
            for a,b in zip(p['candidate_points_nm'],p['candidate_points_nm'][1:]):
                hits=[u for u in incoming-set(ordered) if u in live and live[u].GetClass()=='PCB_TRACK'
                    and list(live[u].GetStart())==a and list(live[u].GetEnd())==b]
                if len(hits)!=1:raise ValueError('exact_ground_ingress_native_operation_identity_required')
                ordered.append(hits[0])
        if set(ordered)!=incoming:raise ValueError('ground_ingress_cannot_add_unowned_material')
        with tempfile.TemporaryDirectory(prefix='cec-ground-ingress-replay-') as work:
            expected=construct(q,incoming_uuids=ordered);additive._ground_refill(expected)
            path=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(expected,path)
            _,nodes=additive._nodes(path)
            if ({u:syntax._freeze(v) for u,v in nodes.items()}!={u:syntax._freeze(v) for u,v in new.items()}
                    or force._sidecars(source)!=force._sidecars(intermediate)):
                raise ValueError('saved_ground_ingress_differs_from_exact_source_replay')
        remaining=lambda:min(10.,max(.001,deadline-time.monotonic()))
        delta=ordinary.receive(source,intermediate,retired_track_uuids=q['retired_track_uuids'],
            allow_locked_track_uuids=q['allow_locked_track_uuids'],board_hint=q['board_hint'],timeout_s=remaining())
        r['ordinary_receiving']=delta
        if not delta['ok'] or not delta['complete']:raise ValueError('independent_ordinary_ingress_receiving_refused')
        pad,_=ground._pad(child,q['pad_uuid'])
        clearance=max(200000,int(child.GetDesignSettings().m_MinClearance),int(cells._netclass(child,'GND')['clearance']))
        if not _via_clear(child,pad,q['source_via_geometry_mm'],clearance):
            raise ValueError('saved_ordinary_detours_do_not_free_the_source_ground_ingress')
        parent=pcbnew.LoadBoard(str(source));preserved=returns.receive(parent,child,timeout_s=remaining())
        r['all_source_known_returns']=preserved
        if not preserved['ok'] or not preserved['complete']:raise ValueError('ingress_lost_source_ground_returns')
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('ingress_worsened_whole_native_route_craft')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,q['board_hint']) for p in (source,intermediate)]):
            raise ValueError('ground_ingress_source_code_or_lease_changed')
        r.update(ok=True,complete=True,proposal=q,code_identity=epoch,added_native_uuids=ordered,
            retired_track_uuids=q['retired_track_uuids'],modified_nets=sorted(p['net'] for p in q['paths']),
            intermediate_is_not_an_admitted_result=True,source_ground_ingress_actually_clear=True,
            original_parts_barrels_power_and_rules_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,TimeoutError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def receive_full(source,intermediate,candidate,proposal,*,timeout_s=10.):
    """Two explicit <=10s leases, not an intermediate adopted as a baseline."""
    lease._deadline(timeout_s)
    r=dict(ok=False,complete=False,errors=[],scope=SCOPE,current_qualified=False,fab_ready=False,release_authority=False)
    paths=[Path(p).resolve() for p in (source,intermediate,candidate)]
    try:
        if len(set(paths))!=3:raise ValueError('three_distinct_saved_ingress_chain_members_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint']) for p in paths]
        first=receive(paths[0],paths[1],proposal,timeout_s=timeout_s);r['ordinary_phase']=first
        if not first['ok'] or not first['complete']:raise ValueError('source_owned_ordinary_ingress_phase_refused')
        second=ground.receive(paths[1],paths[2],board_hint=proposal['board_hint'],pad_uuid=proposal['pad_uuid'],
            use_existing_local_pad_rule=True,timeout_s=timeout_s);r['ground_phase']=second
        if not second['ok'] or not second['complete']:raise ValueError('mandatory_source_rule_ground_entry_phase_refused')
        if second['new_holes']!=1 or second['saved_return_witness_mm']!=0:
            raise ValueError('ground_ingress_must_finish_with_a_real_direct_in_pad_entry')
        if epoch!=force._code_identity() or families!=[force._family(p,proposal['board_hint']) for p in paths]:
            raise ValueError('ground_ingress_complete_chain_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[2]),proposal=proposal,
            retired_track_uuids=first['retired_track_uuids'],
            added_native_uuids=first['added_native_uuids']+second['added_native_uuids'],
            modified_nets=sorted(set(first['modified_nets'])|{'GND'}),
            source_return_witness_mm=proposal['source_return_witness_mm'],saved_return_witness_mm=0,
            signal_only_intermediate_not_adopted_as_baseline=True,
            whole_native_fields_current_clipped_and_fabrication_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover(source,*,board_hint,pad_uuid,allow_locked_source=False,max_extra_mm=1.,max_offset_mm=1.,timeout_s=10.):
    """At most four nearby positive ordinary peers, dependency proved by plan.

    A refusal is finite search exhaustion, not proof that no route exists.
    No inferred net role or source coordinate/refdes table is used.
    """
    deadline=lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(pad_uuid) is not str or not pad_uuid
            or type(allow_locked_source) is not bool
            or any(type(v) not in (int,float) or not math.isfinite(v) or not .1<=v<=2.
                for v in (max_extra_mm,max_offset_mm))):
        raise ValueError('bounded_typed_source_ground_ingress_contract_required')
    board,pad,face,before,context,group,geometry,clearance,proof=_context(Path(source),board_hint,pad_uuid,deadline)
    primary=proof['distinct_copper_blocker_uuids'][0]
    first=_selected(board,source,board_hint,[primary],allow_locked_source)[0]
    peers=[];eligible=ordinary.eligible_nets(board,source,board_hint)
    for t in board.GetTracks():
        if (t.GetClass()!='PCB_TRACK' or force._uid(t)==primary or t.GetNetCode()==first.GetNetCode()
                or t.GetLayer()!=first.GetLayer() or t.GetNetname() not in eligible
                or t.GetParentGroup() or t.HasSolderMask() or not 0<t.GetWidth()<500000
                or t.IsLocked() and not allow_locked_source):continue
        if t.GetEffectiveShape(t.GetLayer()).Collide(pad.GetPosition(),round(max_offset_mm*1e6)+clearance):
            a,b=[list(t.GetStart()),list(t.GetEnd())]
            peers.append((min(math.dist(pad.GetPosition(),p) for p in (a,b)),force._uid(t)))
    trials=[]
    for peer in [None,*[u for distance,u in sorted(peers)[:4]]]:
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        try:
            q=plan(source,board_hint=board_hint,pad_uuid=pad_uuid,peer_track_uuid=peer,
                allow_locked_source=allow_locked_source,max_extra_mm=max_extra_mm,max_offset_mm=max_offset_mm,
                timeout_s=min(10.,remaining))
            return dict(ok=True,complete=True,proposal=q,trials=trials,maximum_peer_trials=5,
                native_board_mutated=False,release_authority=False)
        except (ValueError,TimeoutError) as exc:trials.append(dict(peer_track_uuid=peer,error=str(exc)))
    return dict(ok=False,complete=time.monotonic()<deadline,proposal=None,trials=trials,maximum_peer_trials=5,
        native_board_mutated=False,no_path_proof=False,release_authority=False)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,pad_uuid,
        allow_locked_source=False,max_extra_mm=1.,max_offset_mm=1.):
    """A real pipeline stage, including independent whole-board hard gates.

    The caller selects a literal target identity, never geometry or net
    ownership. Discovery derives its obstructing owners. Every phase gets its
    own bounded lease; a rejected draft remains explicitly UNADMITTED. Neither
    zero opens nor this local proof is a production/fabrication qualification.
    """
    import json
    import cec_current_debt as current
    import cec_force_sense_evidence as sense
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    source,outdir,reporting_build=[Path(p).resolve() for p in (source,outdir,reporting_build)]
    if (outdir.exists() or source==outdir or not source.is_file() or not reporting_build.is_dir()
            or type(expected_source_sha256) is not str or force._hash(source)!=expected_source_sha256):
        raise ValueError('distinct_new_ingress_output_and_exact_source_digest_required')
    # Validate untrusted flags and limits before creating outputs.
    lease._deadline(10.)
    if (type(allow_locked_source) is not bool or type(board_hint) is not str or not board_hint
            or type(pad_uuid) is not str or not pad_uuid
            or any(type(v) not in (int,float) or not math.isfinite(v) or not .1<=v<=2.
                for v in (max_extra_mm,max_offset_mm))):
        raise ValueError('bounded_typed_source_ground_ingress_contract_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,records=[],
        current_qualified=False,fab_ready=False,source_selected=False,routing_admitted=False,release_authority=False)
    def progress(label):
        force._write(outdir/'progress.json',r)
        print(json.dumps(dict(phase=label,changed=r['changed'],errors=r['errors'])),flush=True)
    try:
        found=discover(source,board_hint=board_hint,pad_uuid=pad_uuid,allow_locked_source=allow_locked_source,
            max_extra_mm=max_extra_mm,max_offset_mm=max_offset_mm);r['discovery']=found
        if not found['ok'] or not found['complete']:raise ValueError('bounded_source_ingress_discovery_refused')
        q=found['proposal'];b=construct(q);additive._ground_refill(b)
        middle=force._copy_family(source,outdir/'UNADMITTED-signal-detours');field._save_field_snapshot(b,middle)
        r['intermediate']=str(middle);progress('saved_unadmitted_signal_detours')
        entry=ground.plan(middle,board_hint=board_hint,pad_uuid=pad_uuid,use_existing_local_pad_rule=True)
        written=ground.write_private(entry,outdir/'UNADMITTED-complete-ground-ingress')
        child=Path(written['candidate'])
        r['unadmitted_candidate']=str(child)
        received=receive_full(source,middle,child,q);r['independent_saved_phase']=received
        if not received['ok'] or not received['complete']:raise ValueError('independent_saved_ingress_chain_refused')
        progress('independent_complete_chain_received')
        debt=current.receive(source,child,board_hint=board_hint);r['whole_parent_current']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('whole_parent_current_refused')
        with force._thermal_hint(board_hint):
            fields=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-
                field.blocker_keys(field.field_coupling_summary(str(source))))
        r['new_field_blockers']=fields
        if fields:raise ValueError('whole_parent_field_regression')
        native_reports=[]
        for path,label in ((source,'source'),(child,'candidate')):
            target=outdir/(label+'.native.json');proof=native.run(path,target,reporting_build=reporting_build,timeout_s=10.)
            r[label+'_native_producer']=proof
            if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
                raise ValueError('complete_uncapped_native_ingress_inventory_required')
            native_reports.append(json.loads(target.read_text()))
            progress(label+'_uncapped_native_complete')
        old,new=native_reports
        new_faults=sorted({admission._canonical_identity(v) for v in new['violations']}-
            {admission._canonical_identity(v) for v in old['violations']})
        r.update(new_native_fault_ids=new_faults,opens=len(new['unconnected_items']))
        if new_faults or r['opens']:raise ValueError('whole_parent_new_native_fault_or_open')
        cut0,cut1=[sense.replay(path,board_hint=board_hint,timeout_s=40.) for path in (source,child)]
        source_board=pcbnew.LoadBoard(str(source));child_board=pcbnew.LoadBoard(str(child))
        cuts=sense.compare_contour_preservation(cut0,cut1,modified_nets=received['modified_nets'],
            native_copper_transforms=sense.native_copper_transform_inventory(source_board,child_board,
                modified_nets=received['modified_nets']))
        r['whole_parent_clipped_preservation']=cuts
        if not cuts['same_evidence'] or not cuts['comparison_complete']:
            raise ValueError('whole_parent_clipped_copper_evidence_changed')
        r.update(ok=True,complete=True,changed=True,candidate=str(child),candidate_sha256=force._hash(child),
            records=[dict(plan=q,intermediate=str(middle),intermediate_sha256=force._hash(middle),
                materialized={k:received[k] for k in ('added_native_uuids','retired_track_uuids')})])
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,TimeoutError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('ingress_source_family_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('board-hint','expected-source-sha256','pad-uuid'):p.add_argument('--'+key,required=True)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--max-extra-mm',type=float,default=1.)
    p.add_argument('--max-offset-mm',type=float,default=1.)
    a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,pad_uuid=a.pad_uuid,allow_locked_source=a.allow_locked_source,
        max_extra_mm=a.max_extra_mm,max_offset_mm=a.max_offset_mm)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] and r['changed'] else 1


if __name__=='__main__':raise SystemExit(main())
