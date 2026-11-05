"""Contact-preserving same-face finishing of source-sensitive scalar GPIO nets.

Positive package/pin evidence selects a scalar, not its firmware mode. No GPIO
high-Z/current/ADC configuration is inferred. Sensitive field roles remain
unchanged. Current domains, ground, zones, coupled/analog input pairs, clocks
and unresolved current-monitor packages remain outside this owner. The whole
source is independently reconstructed and received; no ordinary-net override,
new barrel, component motion, budget change or release authority is granted.
"""
import argparse
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_crossface_receiving as force_receiver
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_native_drc_runner as native
import cec_ordinary_route_receiving as ordinary
import cec_pair_semantics as semantics
import cec_precision_route as precision
import cec_route_quality as quality
import cec_scalar_corner_stage as geometry
import cec_stage_admission as admission
import cec_synth_pipeline as synth
from cec_octilinear_corner import kind as corner_kind,coordinate_inset


def _visible_miter_flat(width_nm,retreat_squared_nm2):
    # Conservative exact integer lower bound for a real >=20um inner flat,
    # including diagonal source legs. Never make a centreline-only cosmetic
    # change whose full-width copper still visibly forms the old hard elbow.
    twice_required=width_nm+math.isqrt(2*20000**2)+1
    return 4*retreat_squared_nm2>=twice_required**2


def _right_angle_contacts(parent,source_tracks,fresh,matches):
    """Re-derive each literal two-to-three miter before its old contact guard.

    Batching does not enlarge the two-edge adjacency guard. Every new edge
    belongs to exactly one disjoint original corner; a multi-corner worker
    cannot use an unrelated short wire to make a total-length metric pass.
    """
    live={force._uid(t):t for t in source_tracks};used=set();rows=[]
    for request in matches:
        cut=[live[u] for u in request['source_track_uuids']]
        ends=[{tuple(t.GetStart()),tuple(t.GetEnd())} for t in cut]
        shared=ends[0]&ends[1]
        if len(shared)!=1:raise ValueError('literal_sensitive_right_angle_vertex_required')
        corner=next(iter(shared));ports=[next(iter(e-shared)) for e in ends]
        vectors=[tuple(p[i]-corner[i] for i in (0,1)) for p in ports]
        if corner_kind(*vectors) is None:raise ValueError('literal_sensitive_octilinear_right_angle_required')
        legs=[];inner=[];retreats=[]
        for port,vector in zip(ports,vectors):
            options=[]
            for uid,t in fresh.items():
                points={tuple(t.GetStart()),tuple(t.GetEnd())}
                if port not in points or len(points)!=2:continue
                at=next(iter(points-{port}));delta=tuple(at[i]-corner[i] for i in (0,1))
                cross=delta[0]*vector[1]-delta[1]*vector[0]
                projection=sum(x*y for x,y in zip(delta,vector));length2=sum(x*x for x in vector)
                retreat2=sum(x*x for x in delta)
                if not cross and 0<projection<length2 and 50000**2<=retreat2<=200000**2:
                    options.append((uid,t,at,retreat2))
            if len(options)!=1:raise ValueError('unique_literal_sensitive_retained_miter_leg_required')
            uid,t,at,retreat2=options[0];legs.append((uid,t));inner.append(at);retreats.append(retreat2)
        bridges=[(uid,t) for uid,t in fresh.items()
            if {tuple(t.GetStart()),tuple(t.GetEnd())}==set(inner)]
        if (retreats[0]!=retreats[1] or len(bridges)!=1
                or not _visible_miter_flat(cut[0].GetWidth(),retreats[0])):
            raise ValueError('exact_equal_retreat_sensitive_miter_bridge_required')
        replacement=legs+bridges;ids={u for u,t in replacement}
        if len(ids)!=3 or ids&used:raise ValueError('disjoint_source_sensitive_miter_material_required')
        used.update(ids)
        proof=geometry.contacts.preserve_contacts(parent,cut,
            tuple(t.GetEffectiveShape(request['layer']) for uid,t in replacement),
            layer_id=request['layer'],net_code=cut[0].GetNetCode(),
            deadline_monotonic=time.monotonic()+10.,max_items=16384)
        if not proof['ok']:raise ValueError('old_sensitive_scalar_contact_lost_or_unknown')
        rows.append(dict(source_track_uuids=request['source_track_uuids'],added_track_uuids=sorted(ids),
            retreat_squared_nm2=retreats[0],real_inner_copper_flat_at_least_nm=20000,
            native_source_contact_preservation=proof))
    if used!=set(fresh):raise ValueError('only_exact_source_sensitive_miter_material_may_be_added')
    return dict(ok=True,complete=True,scope='individually_retyped_disjoint_two_edge_sensitive_corners',
        corners=rows,all_fresh_native_material_independently_accounted=True)


def eligible_nets(board,source,board_hint):
    """Read-only native package witness; never infer a nonload power budget."""
    if type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_sensitive_scalar_design_identity_required')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode()>0]
    if len(pads)>16384:raise ValueError('sensitive_scalar_terminal_inventory_bound')
    resolver=fr._project_netclass_resolver(str(source));witnesses={}
    with force._thermal_hint(board_hint):
        excluded=set(topology.board_current_domains(board,board_hint))
        excluded|={str(p.GetNetname()) for p in pads
            if synth.spec_net_current_contract(board_hint,str(p.GetNetname())) is not None}
    excluded|={str(z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    power_nets=set(excluded)
    excluded|={n for pair in precision.derive_coupled_pairs(str(source),board=board)
        for n in (pair['p'],pair['n'])}
    excluded|={n for pair in semantics.analog_input_pairs(board) for n in (pair['p'],pair['n'])}
    excluded|=semantics.unresolved_current_monitor_nets(board)
    for pad in pads:
        net=str(pad.GetNetname());fp=pad.GetParentFootprint()
        try:model=roles.footprint_contract(fp)
        except ValueError:
            # Contradictory selected package metadata cannot qualify this
            # net as a scalar signal; retain a fail-closed negative scope.
            excluded.add(net)
            continue
        if (str(pad.GetPinType()) in ('power_in','power_out') or model and model['pins'].get(
                str(pad.GetNumber())) in ('power_input','power_output','power_return','ground','switch')):
            excluded.add(net);power_nets.add(net)
        if fp.IsDNP() or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:continue
        witness=roles.scalar_gpio_pin(fp,str(pad.GetNumber()))
        if witness is None:continue
        # This is a pin-role witness, not footprint/manufacturing validation.
        # Duplicate numeric GPIO lands or a contradictory displayed family
        # cannot silently choose which terminal owns this source scope.
        if len([p for p in fp.Pads() if p.GetNumber()==pad.GetNumber()])!=1:
            continue
        role=field.classify_net(net,netclass=resolver(net))
        if not role['victim'] or role['aggressor']:continue
        witnesses.setdefault(net,[]).append(dict(pad_uuid=force._uid(pad),
            owner_uuid=force._uid(fp),manufacturer_pin=witness,
            GPIO_application_mode_current_or_high_impedance_assumed=False))
    result={}
    for net,rows in witnesses.items():
        if net in excluded:continue
        role=field.classify_net(net,netclass=resolver(net))
        if role['power']:
            import cec_sensitive_divider_role as divider
            topology_witness=divider.witness(board,net,power_nets=power_nets)
            if topology_witness is None:continue
            rows=[dict(row,source_closed_passive_divider=topology_witness,
                original_field_classification_retained=role) for row in rows]
        result[net]=sorted(rows,key=lambda row:row['pad_uuid'])
    return result


def inventory(board,source,board_hint,*,geometry_policy='acute_shortcut'):
    witness=eligible_nets(board,source,board_hint)
    result=geometry.inventory(board,set(witness),geometry_policy=geometry_policy)
    if geometry_policy=='right_angle_chamfer':
        live={force._uid(t):t for t in board.GetTracks()};visible=[]
        for request in result['selected']:
            corner=request['at_nm'];edges=[live[u] for u in request['source_track_uuids']]
            far=[t.GetEnd() if tuple(t.GetStart())==tuple(corner) else t.GetStart() for t in edges]
            vectors=[(p.x-corner[0],p.y-corner[1]) for p in far]
            step=coordinate_inset(*vectors,maximum_nm=200000,minimum_nm=50000)
            squared=(2 if corner_kind(*vectors)=='diagonal' else 1)*(step or 0)**2
            if _visible_miter_flat(edges[0].GetWidth(),squared):visible.append(request)
            else:result['skipped']['no_visible_full_width_miter_flat']=result['skipped'].get('no_visible_full_width_miter_flat',0)+1
        result['selected']=visible
        result['scope']=sorted({u for r in visible for u in r['source_track_uuids']})
    result['source_sensitive_scalar_witnesses']=witness
    result['ordinary_reclassification_or_current_authority']=False
    result['geometry_policy']=geometry_policy
    return result


def receive(source,candidate,retired,*,board_hint,allow_locked_source=False,sense_timeout_s=40.,
            geometry_policy='acute_shortcut',max_batch_corners=1,source_corner_scopes=None):
    result=dict(ok=False,complete=False,errors=[],ordinary_reclassification=False,
        GPIO_application_mode_or_current_authority_assumed=False,new_capacity_credited=False,
        current_qualified=False,unknown_evidence_qualified=False,fab_ready=False,release_authority=False)
    try:
        sense_timeout_s=force_receiver.evidence_replay_budget(sense_timeout_s)
        if (geometry_policy not in geometry.GEOMETRY_POLICIES or type(allow_locked_source) is not bool
                or type(max_batch_corners) is not int or not 1<=max_batch_corners<=8
                or geometry_policy=='acute_shortcut' and max_batch_corners!=1
                or type(retired) is not list or not 2<=len(retired)<=2*max_batch_corners
                or len(retired)%2 or len(set(retired))!=len(retired)):
            raise ValueError('bounded_explicit_native_sensitive_corner_scope_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        inv=inventory(parent,paths[0],board_hint,geometry_policy=geometry_policy)
        if source_corner_scopes is None:
            if max_batch_corners!=1:raise ValueError('explicit_disjoint_sensitive_corner_scopes_required')
            matches=[r for r in inv['selected'] if r['source_track_uuids']==sorted(retired)]
        else:
            if (type(source_corner_scopes) is not list or not 1<=len(source_corner_scopes)<=max_batch_corners
                    or any(type(s) is not list or len(s)!=2 or any(type(u) is not str or not u for u in s)
                        for s in source_corner_scopes)
                    or len({u for s in source_corner_scopes for u in s})!=2*len(source_corner_scopes)):
                raise ValueError('explicit_disjoint_sensitive_corner_scopes_required')
            by_scope={tuple(r['source_track_uuids']):r for r in inv['selected']}
            matches=[by_scope.get(tuple(sorted(s))) for s in source_corner_scopes]
            if any(r is None for r in matches):raise ValueError('actual_source_sensitive_corner_scopes_required')
        if (not 1<=len(matches)<=max_batch_corners or 2*len(matches)!=len(retired)
                or set().union(*(set(r['source_track_uuids']) for r in matches))!=set(retired)
                or len({(r['net'],r['layer']) for r in matches})!=1):
            raise ValueError('actual_disjoint_source_sensitive_scalar_corners_required')
        request=matches[0];net=request['net'];layer=request['layer']
        live={force._uid(t):t for t in parent.GetTracks()};cut=[live[u] for u in retired]
        if (any(t.IsLocked() for t in cut) and not allow_locked_source
                or len({(t.GetWidth(),bool(t.IsLocked())) for t in cut})!=1):
            raise ValueError('explicit_consistent_sensitive_scalar_source_locks_required')
        root,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        incoming=sorted(new.keys()-old.keys())
        if old.keys()-new.keys()!=set(retired) or not 1<=len(incoming)<=3*len(matches):
            raise ValueError('exact_source_corner_tracks_and_bounded_new_sensitive_strokes_required')
        fresh={force._uid(t):t for t in child.GetTracks() if force._uid(t) in incoming}
        width=cut[0].GetWidth();locked=bool(cut[0].IsLocked())
        if fresh.keys()!=set(incoming) or any(t.GetClass()!='PCB_TRACK' or str(t.GetNetname())!=net
                or t.GetLayer()!=layer or t.GetWidth()!=width or t.HasSolderMask() or t.GetParentGroup()
                or bool(t.IsLocked())!=locked or t.GetLength()>32000000
                or not quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0) for t in fresh.values()):
            raise ValueError('unchanged_same_face_width_locks_and_plain_sensitive_strokes_required')
        if (sum(t.GetLength() for t in fresh.values())>=sum(t.GetLength() for t in cut)
                or force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('strict_shortening_and_unchanged_sensitive_source_metadata_required')
        contacts=(_right_angle_contacts(parent,cut,fresh,matches) if geometry_policy=='right_angle_chamfer'
            else geometry.contacts.preserve_contacts(parent,cut,
                tuple(t.GetEffectiveShape(layer) for t in fresh.values()),layer_id=layer,
                net_code=cut[0].GetNetCode(),deadline_monotonic=time.monotonic()+10.,max_items=16384))
        result['native_source_contact_preservation']=contacts
        if not contacts['ok']:raise ValueError('old_sensitive_scalar_contact_lost_or_unknown')
        with tempfile.TemporaryDirectory(prefix='cec-sensitive-scalar-receiving-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            rebuilt_root=[root[0],*[node for node in root[1:] if not (isinstance(node,list)
                and next((str(x[1]).strip('"') for x in node if isinstance(x,list)
                    and len(x)>1 and x[0]=='uuid'),None) in retired)],*[new[u] for u in incoming]]
            expected.write_text(additive._render(rebuilt_root)+'\n')
            rebuilt=pcbnew.LoadBoard(str(expected));additive._ground_refill(rebuilt)
            field._save_field_snapshot(rebuilt,expected);_,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('exact_sensitive_scalar_and_native_ground_refill_replay_differs')
        parts=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=retired)
        updated=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*parts))
        if not all(any(part<=q for q in updated) for part in parts):
            raise ValueError('retained_native_sensitive_scalar_partition_lost')
        first,last=[quality.analyze_board(b) for b in (parent,child)]
        corners_after=inventory(child,paths[1],board_hint,geometry_policy=geometry_policy)
        strict_gain=(last['issue_count']<first['issue_count'] if geometry_policy=='acute_shortcut'
            else len(corners_after['selected'])<len(inv['selected']))
        if (not strict_gain or last['issue_count']>first['issue_count'] or last['non_octilinear_count']>first['non_octilinear_count']
                or last['power_contours']['finding_count']>first['power_contours']['finding_count']):
            raise ValueError('strict_whole_board_sensitive_craft_gain_required')
        debt=current.receive(*paths,board_hint=board_hint);result['whole_source_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('unchanged_sensitive_current_debt_required')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        result['new_field_blockers']=delta
        if delta:raise ValueError('new_sensitive_scalar_field_blocker')
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in paths]
        transforms=force_receiver.count_manifest(net,retired,list(fresh.values()))
        preservation=sense.compare_contour_preservation(before,after,modified_nets=[net],native_copper_transforms=transforms)
        result['physical_kelvin_preservation']=preservation
        if not preservation['comparison_complete'] or not preservation['same_evidence']:
            raise ValueError('absolute_sensitive_scalar_cuts_and_unaffected_evidence_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('sensitive_scalar_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_family_and_code_unchanged=True,net=net,source_width_nm=width,
            geometry_policy=geometry_policy,retired_track_uuids=sorted(retired),added_native_uuids=sorted(fresh),
            received_source_corner_count=len(matches),max_batch_corners=max_batch_corners,
            source_corner_scopes=[r['source_track_uuids'] for r in matches],
            selected_geometry_findings_before_after=[len(inv['selected']),len(corners_after['selected'])],
            source_pin_witnesses=inv['source_sensitive_scalar_witnesses'][net],
            original_retained_native_partitions_preserved=True,exact_native_ground_refill_received=True,
            shortened_centerline_mm=(sum(t.GetLength() for t in cut)-sum(t.GetLength() for t in fresh.values()))/1e6,
            complete_uncapped_native_DRC_and_full_release_checks_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_requests=4,sense_timeout_s=40.,geometry_policy='acute_shortcut',max_batch_corners=1):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(allow_locked_source) is not bool or type(max_requests) is not int or not 1<=max_requests<=8
            or reporting_build is None or geometry_policy not in geometry.GEOMETRY_POLICIES
            or type(max_batch_corners) is not int or not 1<=max_batch_corners<=8
            or geometry_policy=='acute_shortcut' and max_batch_corners!=1):
        raise ValueError('bounded_explicit_sensitive_scalar_stage_context_required')
    sense_timeout_s=force_receiver.evidence_replay_budget(sense_timeout_s)
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('exact_sensitive_source_and_fresh_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    result=dict(ok=False,complete=False,changed=False,source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],errors=[],
        ordinary_reclassification=False,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        proof=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        result.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_sensitive_scalar_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        result.update(geometry_policy=geometry_policy,max_batch_corners=max_batch_corners)
        initial=inventory(pcbnew.LoadBoard(str(source)),source,board_hint,geometry_policy=geometry_policy);result['before']=initial
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_optional_sensitive_scalar_finishing')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        for index,request in enumerate(initial['selected'][:max_requests]):
            row=dict(request=request,accepted=False);result['attempts'].append(row)
            try:
                b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
                requests=[request];owned=set(request['source_track_uuids'])
                for other in initial['selected'][index+1:]:
                    if len(requests)>=max_batch_corners:break
                    if ((other['net'],other['layer'])!=(request['net'],request['layer'])
                            or owned&set(other['source_track_uuids'])):continue
                    proposed=owned|set(other['source_track_uuids'])
                    if len({(live[u].GetWidth(),bool(live[u].IsLocked())) for u in proposed})!=1:continue
                    requests.append(other);owned=proposed
                row['source_requests']=requests
                if any(live[u].IsLocked() for u in owned) and not allow_locked_source:
                    raise ValueError('explicit_sensitive_scalar_source_lock_permission_required')
                proposal=geometry.construct(b,requests,set(initial['source_sensitive_scalar_witnesses']),
                    allow_locked_source=allow_locked_source,geometry_policy=geometry_policy)
                row['untrusted_geometry']=proposal
                if not proposal['chamfered']:raise ValueError('no_contact_preserving_sensitive_shortcut')
                child=force._copy_family(source,outdir/('UNADMITTED-sensitive-scalar-'+str(index)))
                additive._ground_refill(b);field._save_field_snapshot(b,child)
                observed=observe(child,'candidate-'+str(index))
                added=sorted({admission._canonical_identity(v) for v in observed['violations']}-faults)
                row['new_native_fault_ids']=added
                if observed['unconnected_items'] or added:raise ValueError('sensitive_native_opens_or_new_warning')
                proof=receive(source,child,proposal['retired_track_uuids'],board_hint=board_hint,
                    allow_locked_source=allow_locked_source,sense_timeout_s=sense_timeout_s,
                    geometry_policy=geometry_policy,max_batch_corners=max_batch_corners,
                    source_corner_scopes=([r['request']['source_track_uuids'] for r in proposal['details'] if r['changed']]
                        if max_batch_corners!=1 else None))
                row['independent_sensitive_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('saved_sensitive_receiving_refused:'+str(proof['errors']))
                row.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                result.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    independent_sensitive_receiving=proof,retired_track_uuids=proposal['retired_track_uuids'])
                break
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
        result.update(ok=True,complete=True,after=inventory(pcbnew.LoadBoard(result['candidate']),result['candidate'],board_hint,
            geometry_policy=geometry_policy))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    result['source_family_and_code_unchanged']=stable
    if not stable:
        result.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        result['errors'].append('sensitive_scalar_source_or_code_changed')
    force._write(outdir/'stage.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-requests',type=int,default=4)
    p.add_argument('--geometry-policy',choices=geometry.GEOMETRY_POLICIES,default='acute_shortcut')
    p.add_argument('--max-batch-corners',type=int,default=1)
    p.add_argument('--sense-timeout-s',type=float,default=40.);a=p.parse_args()
    import wx
    quiet=wx.LogNull()
    result=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        max_requests=a.max_requests,sense_timeout_s=a.sense_timeout_s,geometry_policy=a.geometry_policy,
        max_batch_corners=a.max_batch_corners)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=result['ok'],complete=result['complete'],
        changed=result['changed'],candidate_sha256=result['candidate_sha256'],errors=result['errors'])),flush=True)
    return 0 if result['ok'] and result['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
