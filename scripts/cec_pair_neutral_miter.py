"""Source-derived length-neutral 90-to-two-45 pair splices.

Translate ONE diagonal without changing its vector. Borrow exactly the new
cardinal flat's length from an adjoining same-direction cardinal source leg.
Both fixed ports, both diagonal vectors and total cardinal length stay exact.
This geometry certificate grants no clearance, coupling, reference or release
authority; the complete saved pair receiver still owns those decisions.
"""
import argparse,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_fr as fr
import cec_paired_route_reconstruction as whole_pair
from cec_native_items import discard_items


def frames(points):
    if (type(points) not in (list,tuple) or len(points)!=4 or any(type(p) not in (list,tuple)
            or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)):
        raise ValueError('four_actual_integer_source_miter_stations_required')
    p=[list(q) for q in points];edges=[[b[i]-a[i] for i in (0,1)] for a,b in zip(p,p[1:])]
    result=[]
    for apex in (1,2):
        u,v=edges[apex-1:apex+1]
        if (not u[0] or abs(u[0])!=abs(u[1]) or not v[0] or abs(v[0])!=abs(v[1])
                or sum(a*b for a,b in zip(u,v))):continue
        common=[i for i in (0,1) if u[i]*v[i]>0]
        if len(common)!=1:continue
        axis=common[0];sign=1 if u[axis]>0 else -1;flank=edges[0] if apex==2 else edges[2]
        if flank[1-axis] or sign*flank[axis]<=60000:continue
        result.append(dict(source_points_nm=p,apex_index=apex,axis=axis,sign=sign,
            available_shift_nm=sign*flank[axis]-20000))
    return result


def shifted_points(frame,delta_nm):
    if (type(frame) is not dict or frame not in frames(frame.get('source_points_nm'))
            or type(delta_nm) is not int or not 20000<=delta_nm<=200000
            or 2*delta_nm>frame['available_shift_nm']):
        raise ValueError('bounded_actual_source_neutral_miter_frame_required')
    p=[q[:] for q in frame['source_points_nm']];axis=frame['axis'];shift=2*delta_nm*frame['sign']
    if frame['apex_index']==2:
        first=p[1][:];flat=p[2][:];first[axis]-=shift;flat[axis]-=shift
        return [p[0],first,flat,p[2],p[3]]
    flat=p[1][:];last=p[2][:];flat[axis]+=shift;last[axis]+=shift
    return [p[0],p[1],flat,last,p[3]]


def exact_scope(board,pair,cut,fresh):
    """Rederive the integer translation identity; no length tolerance waiver."""
    import cec_pair_local_reference_refinement as owner
    if (len(cut)!=3 or len(fresh)!=4 or len({(t.GetNetname(),int(t.GetLayer())) for t in cut+fresh})!=1):
        raise ValueError('one_native_three_to_four_neutral_pair_splice_required')
    old=owner._chain(cut);new=owner._chain(fresh)
    actual=owner.bend_inventory(board,pair)['selected'];ids={force._uid(t) for t in cut}
    if not any(set(q['source_track_uuids'])<=ids for q in actual):
        raise ValueError('neutral_splice_requires_an_actual_source_hard90')
    for frame in frames(old):
        index=frame['apex_index']
        flat=(new[index+1][frame['axis']]-new[index][frame['axis']])*frame['sign']
        if flat<=0 or flat%2:continue
        delta=flat//2
        try:expected=shifted_points(frame,delta)
        except ValueError:continue
        if expected==[list(q) for q in new]:
            return dict(ok=True,complete=True,frame=frame,delta_nm=delta,
                fixed_ports_exact=True,diagonal_vectors_translated_not_resized=True,
                cardinal_length_borrowed_equals_added_flat=True,exact_centerline_length_unchanged=True,
                source_hard90_rederived=True,pair_qualified=False,release_authority=False)
    raise ValueError('saved_miter_is_not_the_exact_source_length_neutral_splice')


def discover(board,source,pair,*,allow_locked_source=False):
    import cec_pair_local_reference_refinement as owner
    _,nodes=additive._nodes(source);tracks={force._uid(t):t for t in board.GetTracks()}
    if len(tracks)>16384:raise ValueError('bounded_neutral_pair_source_inventory_required')
    result=[];seen=set()
    for corner in owner.bend_inventory(board,pair)['selected']:
        base=[tracks[u] for u in corner['source_track_uuids']];ids={force._uid(t) for t in base}
        ports=owner._chain(base)
        for t in tracks.values():
            if (t.GetClass()!='PCB_TRACK' or force._uid(t) in ids or t.GetParentGroup()
                    or t.GetNetname()!=corner['net'] or int(t.GetLayer())!=corner['layer']
                    or not allow_locked_source and t.IsLocked()
                    or not {tuple(t.GetStart()),tuple(t.GetEnd())}&{tuple(ports[0]),tuple(ports[-1])}):continue
            selected=base+[t];key=tuple(sorted(force._uid(q) for q in selected))
            if key in seen:continue
            if (any(q.GetParentGroup() or q.HasSolderMask() or q.GetWidth()!=round(pair['width']*1e6)
                    or q.IsLocked() and not allow_locked_source for q in selected)
                    or len({repr(owner._process(nodes[force._uid(q)])) for q in selected})!=1):continue
            try:options=frames(owner._chain(selected))
            except ValueError:continue
            for frame in options:
                seen.add(key);result.append(dict(source_track_uuids=list(key),frame=frame,
                    source_corner=corner,pair_name=pair['name']))
    return result


def construct(board,source,pair,request,delta_nm,*,allow_locked_source=False):
    import cec_pair_local_reference_refinement as owner
    if request not in discover(board,source,pair,allow_locked_source=allow_locked_source):
        raise ValueError('neutral_pair_request_not_rederived_from_actual_source')
    points=shifted_points(request['frame'],delta_nm);live={force._uid(t):t for t in board.GetTracks()}
    old=[live[u] for u in request['source_track_uuids']];exemplar=old[0]
    width=exemplar.GetWidth();face=int(exemplar.GetLayer());code=exemplar.GetNetCode()
    zones,copper=fr._foreign_shape_indexes(board,face,{code})
    clearance=max(int(board.GetDesignSettings().m_MinClearance),math.ceil(pair['clearance']*1e6))
    for a,b in zip(points,points[1:]):
        if (not fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),(width+1)//2)
                or not fr._snapshot_foreign_clear(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,clearance,zones,copper)):
            raise ValueError('neutral_pair_new_shape_fails_unchanged_native_clearance')
    made=[]
    for a,b in zip(points,points[1:]):
        item=exemplar.Duplicate();item.m_Uuid.Clone(pcbnew.KIID())
        item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b));made.append(item)
    proof=exact_scope(board,pair,old,made)
    for item in made:board.Add(item)
    discard_items(board,old)
    return dict(retired_track_uuids=request['source_track_uuids'],exact_neutral_geometry=proof,
        added_track_uuids=[force._uid(t) for t in made])


def construct_whole_pair(board,source,pair,request,delta_nm,*,board_hint,allow_locked_source=False):
    """Use the existing full-bus owner, never relax inherited local deficit gates."""
    scope=whole_pair.plan(board,source,board_hint=board_hint,pair_name=pair['name'])
    before={force._uid(t):t for t in board.GetTracks()}
    local=construct(board,source,pair,request,delta_nm,allow_locked_source=allow_locked_source)
    copies={};unmodified=[]
    for uid in scope['retired_track_uuids']:
        if uid in local['retired_track_uuids']:continue
        old=before[uid];item=old.Duplicate();item.m_Uuid.Clone(pcbnew.KIID());board.Add(item)
        copies[uid]=force._uid(item);unmodified.append(old)
    discard_items(board,unmodified)
    return dict(source_whole_pair_scope=json.loads(json.dumps(scope,allow_nan=False)),
        local_source_track_uuids=local['retired_track_uuids'],local_new_track_uuids=local['added_track_uuids'],
        unchanged_pair_native_copies=copies,exact_neutral_geometry=local['exact_neutral_geometry'],
        all_barrels_pads_and_nonpair_conductors_retained=True)


def receive_phase(source,candidate,materialized,*,board_hint,pair_name):
    import cec_pair_local_reference_refinement as owner
    r=dict(ok=False,complete=False,errors=[],pair_qualified=False,release_authority=False)
    try:
        base_keys={'source_whole_pair_scope',
                'local_source_track_uuids','local_new_track_uuids','unchanged_pair_native_copies',
                'exact_neutral_geometry','all_barrels_pads_and_nonpair_conductors_retained'}
        craft_operation=isinstance(materialized,dict) and 'geometry_operation' in materialized
        if type(materialized) is not dict or set(materialized)!=(base_keys|(
                {'geometry_operation','operation_parameters'} if craft_operation else set())):
            raise ValueError('exact_source_whole_pair_neutral_receipt_required')
        if materialized['all_barrels_pads_and_nonpair_conductors_retained'] is not True:
            raise ValueError('literal_neutral_pair_preservation_declaration_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=whole_pair.plan(parent,source,board_hint=board_hint,pair_name=pair_name)
        if json.loads(json.dumps(scope,allow_nan=False))!=materialized['source_whole_pair_scope']:
            raise ValueError('whole_pair_neutral_source_scope_changed')
        old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in child.GetTracks()}
        cut=materialized['local_source_track_uuids'];added=materialized['local_new_track_uuids']
        copies=materialized['unchanged_pair_native_copies']
        if (type(cut) is not list or type(added) is not list or type(copies) is not dict
                or len(set(cut))!=len(cut) or len(set(added))!=len(added)
                or (not (1<=len(cut)<=16 and 1<=len(added)<=16) if craft_operation else (len(cut)!=3 or len(added)!=4))
                or not set(cut)<=set(scope['retired_track_uuids'])
                or set(copies)!=set(scope['retired_track_uuids'])-set(cut)
                or len(set(copies.values()))!=len(copies) or set(copies.values())&set(added)
                or set(new)-set(old)!=set(copies.values())|set(added)):
            raise ValueError('exact_complete_pair_copy_and_local_miter_inventory_required')
        _,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(candidate)
        for uid,target in copies.items():
            if additive._without(old_nodes[uid],'uuid')!=additive._without(new_nodes[target],'uuid'):
                raise ValueError('nonlocal_source_pair_copper_or_process_changed')
        if craft_operation:
            import cec_pair_craft_reflow as physical_craft
            local=physical_craft.certificate(parent,scope['pair'],[old[u] for u in cut],[new[u] for u in added],
                materialized['geometry_operation'],materialized['operation_parameters'])
        else:local=exact_scope(parent,scope['pair'],[old[u] for u in cut],[new[u] for u in added])
        if local!=materialized['exact_neutral_geometry']:
            raise ValueError('neutral_miter_integer_geometry_certificate_changed')
        # Preserve process fields of the changed native legs as well.
        if materialized.get('geometry_operation')=='balanced_fixed_miters':
            signatures={}
            for uid in cut:
                net=old[uid].GetNetname();signature=owner._process(old_nodes[uid])
                if net in signatures and signatures[net]!=signature:
                    raise ValueError('matched_pair_source_member_process_not_uniform')
                signatures[net]=signature
            if (set(signatures)!={scope['pair']['p'],scope['pair']['n']}
                    or any(new[uid].GetNetname() not in signatures or owner._process(new_nodes[uid])!=signatures[new[uid].GetNetname()] for uid in added)):
                raise ValueError('matched_pair_member_source_layer_width_lock_or_net_process_changed')
        else:
            signature=owner._process(old_nodes[cut[0]])
            if any(owner._process(nodes[uid])!=signature for nodes,ids in ((old_nodes,cut),(new_nodes,added)) for uid in ids):
                raise ValueError('neutral_miter_source_layer_width_lock_or_process_changed')
        continuous=owner.compare_continuous(owner.continuous_from_board(parent,scope['pair']),
            owner.continuous_from_board(child,scope['pair']))
        r['continuous_coupling']=continuous
        if not continuous['ok']:raise ValueError('neutral_pair_continuous_member_deficit_regressed')
        physical=[]
        for sample in (.5,.25,.1):
            with force._thermal_hint(board_hint):
                packets=[owner.constraints.high_speed_pair_summary(str(path),board=b,sample_mm=sample)
                    for path,b in ((source,parent),(candidate,child))]
            metrics=[next(q for q in packet['pairs'] if (q['p'],q['n'])==(scope['pair']['p'],scope['pair']['n'])) for packet in packets]
            if any(q['violations'] for q in metrics):
                r['rejected_full_pair_physical_sample']=dict(sample_mm=sample,before=metrics[0],after=metrics[1])
                raise ValueError('whole_pair_miter_requires_positive_full_source_and_candidate_contracts:'+str([q['violations'] for q in metrics]))
            comparison=owner.metric_progress(*metrics,coupling=continuous)
            if not comparison['ok']:raise ValueError('whole_pair_neutral_nonreference_metric_regressed:'+str(comparison['errors']))
            physical.append(dict(sample_mm=sample,before=metrics[0],after=metrics[1],comparison=comparison))
        native=whole_pair.receive(source,candidate,board_hint=board_hint,pair_name=pair_name,
            retired_track_uuids=scope['retired_track_uuids'],timeout_s=10.)
        r['existing_full_bus_receiver']=native
        if not native['ok'] or not native['complete']:raise ValueError('existing_full_pair_receiver_refused:'+str(native['errors']))
        before,after=[len(owner.bend_inventory(b,scope['pair'])['selected']) for b in (parent,child)]
        if after>before or not craft_operation and after==before:
            raise ValueError('actual_source_pair_hard90_count_must_decrease_or_typed_physical_craft_must_improve')
        craft=[owner.quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('neutral_pair_whole_board_route_craft_regressed')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('neutral_pair_phase_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,pair=scope['pair'],exact_neutral_geometry=local,
            full_pair_physical_samples=physical,hard90_before_after=[before,after],
            shortened_centerline_mm=0.,all_unchanged_native_pair_copies_replayed=True,
            physical_craft_operation=materialized.get('geometry_operation'),
            craft_before_after=[q['issue_count'] for q in craft],source_candidate_families_and_code_unchanged=True,
            local_inherited_deficit_receiver_not_relaxed_or_invoked=True)
        if materialized.get('geometry_operation')=='fixed_port_miter':
            r['shortened_centerline_mm']=local['length']['flat_growth_nm']*(math.sqrt(2)-1)/1e6
        elif materialized.get('geometry_operation')=='balanced_fixed_miters':
            one=local['length']['flat_growth_nm_each']*(math.sqrt(2)-1)/1e6
            r['shortened_centerline_mm_each']=one;r['shortened_centerline_mm']=2*one
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def receive_chain(source,candidate,records,*,board_hint,reporting_build):
    import cec_pair_local_reference_refinement as owner
    r=dict(ok=False,complete=False,errors=[],pair_qualified=False,full_pair_gate_unchanged=True,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,goal_complete=False)
    try:
        if type(records) is not list or not 1<=len(records)<=4 or reporting_build is None:
            raise ValueError('bounded_whole_pair_neutral_chain_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();cursor=source;families=[(source,force._family(source,board_hint))];nets=set();proofs=[]
        for row in records:
            if set(row)!={'source','source_sha256','candidate','candidate_sha256','pair_name','materialized'}:
                raise ValueError('exact_whole_pair_neutral_chain_record_required')
            old,new=[Path(row[k]).resolve() for k in ('source','candidate')]
            if old!=cursor or force._hash(old)!=row['source_sha256'] or force._hash(new)!=row['candidate_sha256']:
                raise ValueError('unchanged_contiguous_neutral_pair_chain_required')
            proof=receive_phase(old,new,row['materialized'],board_hint=board_hint,pair_name=row['pair_name']);proofs.append(proof)
            if not proof['ok'] or not proof['complete']:raise ValueError('whole_pair_neutral_phase_refused:'+str(proof['errors']))
            nets.update(proof['pair'][k] for k in ('p','n'));families.append((new,force._family(new,board_hint)));cursor=new
        if cursor!=candidate:raise ValueError('neutral_pair_chain_end_differs')
        debt=owner.current.receive(source,candidate,board_hint=board_hint);r['whole_parent_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('neutral_pair_whole_parent_current_refused')
        with force._thermal_hint(board_hint):
            fields=sorted(owner.field.blocker_keys(owner.field.field_coupling_summary(str(candidate)))-
                owner.field.blocker_keys(owner.field.field_coupling_summary(str(source))))
        r['new_field_blockers']=fields
        if fields:raise ValueError('neutral_pair_whole_parent_field_regressed')
        first,last=[owner.sense.replay(p,board_hint=board_hint,timeout_s=40.) for p in (source,candidate)]
        nets.add('GND');before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        cuts=owner.sense.compare_contour_preservation(first,last,modified_nets=sorted(nets),
            native_copper_transforms=owner.sense.native_copper_transform_inventory(before,after,modified_nets=sorted(nets)))
        r['whole_parent_clipped_preservation']=cuts
        if not cuts['same_evidence'] or not cuts['comparison_complete']:raise ValueError('neutral_pair_absolute_cuts_and_unaffected_evidence_refused')
        import tempfile
        reports=[];producers={}
        with tempfile.TemporaryDirectory(prefix='cec-neutral-pair-native-') as tmp:
            for label,path in (('source',source),('candidate',candidate)):
                shadow=force._copy_family(path,Path(tmp)/label);dest=Path(tmp)/(label+'.json')
                producer=owner.native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
                if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
                    raise ValueError('complete_uncapped_neutral_pair_native_inventory_required')
                reports.append(json.loads(dest.read_text()));producers[label]=dict(report_sha256=force._hash(dest),complete=True,
                    raw_count=len(reports[-1]['violations']),opens=len(reports[-1]['unconnected_items']))
        faults=sorted({owner.admission._canonical_identity(v) for v in reports[1]['violations']}-
            {owner.admission._canonical_identity(v) for v in reports[0]['violations']})
        r.update(native_producers=producers,native_report_inventories=dict(zip(('source','candidate'),reports)),
            new_native_fault_ids=faults,opens=len(reports[1]['unconnected_items']))
        if faults or r['opens']:raise ValueError('neutral_pair_new_native_fault_or_open')
        if epoch!=force._code_identity() or any(q!=force._family(p,board_hint) for p,q in families):
            raise ValueError('neutral_pair_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,source=str(source),source_sha256=force._hash(source),candidate=str(candidate),candidate_sha256=force._hash(candidate),
            code_identity=epoch,source_candidate_families_and_code_unchanged=True,independently_received_phases=proofs,records=records,
            shortened_centerline_mm=0.,hard90_vertices_removed=sum(q['hard90_before_after'][0]-q['hard90_before_after'][1] for q in proofs),
            all_original_power_copper_barrels_pads_poses_rules_and_interfaces_retained=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=24):
    import cec_pair_local_reference_refinement as owner
    import cec_precision_route as precision
    if type(max_trials) is not int or not 1<=max_trials<=32 or type(allow_locked_source) is not bool:
        raise ValueError('finite_explicit_neutral_miter_stage_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or force._hash(source)!=expected_source_sha256:raise ValueError('exact_source_and_fresh_neutral_miter_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,pair_qualified=False,fab_ready=False,release_authority=False)
    active=source;tried=set()
    try:
        while len(r['attempts'])<max_trials and len(r['records'])<4:
            b=pcbnew.LoadBoard(str(active));tasks=[]
            for pair in precision.derive_coupled_pairs(str(active),board=b):
                for request in discover(b,active,pair,allow_locked_source=allow_locked_source):
                    for delta in (20000,40000,80000,160000,200000):
                        key=(tuple(request['source_track_uuids']),delta)
                        if key not in tried and 2*delta<=request['frame']['available_shift_nm']:tasks.append((key,pair,request,delta))
            if not tasks:break
            progressed=False
            for key,pair,request,delta in tasks:
                if len(r['attempts'])>=max_trials:break
                tried.add(key);row=dict(request=request,delta_nm=delta,accepted=False);r['attempts'].append(row)
                try:
                    b=pcbnew.LoadBoard(str(active));made=construct_whole_pair(b,active,pair,request,delta,
                        board_hint=board_hint,allow_locked_source=allow_locked_source)
                    additive._ground_refill(b);child=force._copy_family(active,outdir/('UNADMITTED-neutral-miter-'+str(len(r['attempts'])-1)))
                    field._save_field_snapshot(b,child)
                    record=dict(source=str(active),source_sha256=force._hash(active),candidate=str(child),candidate_sha256=force._hash(child),
                        pair_name=pair['name'],materialized=made)
                    whole=receive_chain(source,child,r['records']+[record],board_hint=board_hint,reporting_build=reporting_build)
                    row['whole_source_receiving']=whole
                    if not whole['ok'] or not whole['complete']:raise ValueError('neutral_miter_whole_source_refused:'+str(whole['errors']))
                    r['records'].append(record);active=child;row['accepted']=True;progressed=True
                    r['independent_whole_parent_receiving']=whole;break
                except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.geometry.Refused) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
                finally:print(json.dumps(dict(pair=pair['name'],delta_nm=delta,accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
            if not progressed:break
        r.update(ok=True,complete=True,changed=bool(r['records']),candidate=str(active),candidate_sha256=force._hash(active))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:r.update(ok=False,complete=False,changed=False);r['errors'].append('neutral_pair_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=24)
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,reporting_build=a.reporting_build,
        allow_locked_source=a.allow_locked_source,max_trials=a.max_trials)
    print(json.dumps({k:r[k] for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
