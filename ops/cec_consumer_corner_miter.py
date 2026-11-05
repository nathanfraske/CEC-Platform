"""Agent construction for already proved source-consumer group elbows.

Geometry is not electrical authority. The existing consumer group receiver
must rederive the exact root, tap, budget, native partitions and saved delta.
No allocation, load, pad, via, rule, group identity or release change is made.
"""
import argparse,json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cec_swig_guard;cec_swig_guard.pin()
import wx;quiet=wx.LogNull()
import pcbnew
import cec_additive_route_receiving as additive
import cec_consumer_group_reconstruction as owner
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_native_fill_geometry as fills
import cec_octilinear_corner as octilinear
import cec_ordinary_pad_corner as geometry
import cec_route_corner_contacts as contacts
import cec_route_quality as quality
import cec_stage_admission as admission


def require(condition,message):
    if not condition:raise ValueError(message)


def owner_for(source_ownership):
    require(type(source_ownership) is str and source_ownership in ('strict_outer','planar_nonplane','retained_planar_island'),
        'explicit_known_source_consumer_ownership_required')
    if source_ownership=='strict_outer':return owner
    if source_ownership=='retained_planar_island':
        import cec_retained_consumer_planar_reflow
        return cec_retained_consumer_planar_reflow
    import cec_planar_consumer_reconstruction
    return cec_planar_consumer_reconstruction


def native_radius_positive_at(poly,radius,deadline):
    require(time.monotonic()<deadline,'native_contact_cap_witness_deadline')
    eroded=poly.CloneDropTriangulation()
    eroded.Inflate(-radius,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
    require(time.monotonic()<deadline,'native_contact_cap_witness_deadline')
    return bool(eroded.OutlineCount())


def retained_contact_proof(item,old,new,face,width,deadline):
    """Containment is stronger than comparing maximum inscribed radii.

    Retain the old slow radius guard as fallback, without an epsilon/area
    waiver. Positive one-nanometre erosion plus exact old-contact subset of
    new contact implies every old inscribed disk still exists, not only one
    sampled radius. Native polygons use the SAME 1-nm inside geometry as
    the existing guard. This proves contact geometry, never current capacity.
    """
    body=contacts.native_contact_polygon(item,face,deadline)
    def material(items):
        poly=pcbnew.SHAPE_POLY_SET()
        for t in items:poly.BooleanAdd(contacts.native_contact_polygon(t,face,deadline))
        poly.BooleanIntersection(body);return poly
    before,after=material(old),material(new)
    positive=before.CloneDropTriangulation()
    positive.Inflate(-1,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
    missing=before.CloneDropTriangulation();missing.BooleanSubtract(after)
    if positive.OutlineCount() and not missing.OutlineCount():
        a,av=fills.identity(before,deadline);z,zv=fills.identity(after,deadline)
        return dict(uuid=force._uid(item),method='exact_full_native_contact_containment',
            source_contact_sha256=a,source_vertices=av,candidate_contact_sha256=z,candidate_vertices=zv,
            positive_native_contact_radius_lower_bound_nm=1,
            every_old_native_contact_point_retained=True,maximum_inscribed_radius_cannot_decrease=True,
            polygon_error_nm=1,current_or_barrel_capacity_qualified=False)
    # The legacy search caps BOTH radii at width//2. A positive erosion at
    # that cap proves the candidate reaches the largest possible legacy
    # answer, without repeatedly eroding a complex old contact polygon.
    # For even-width native rectangles the cap can be empty. If the old cap
    # is also empty, its exact integer upper bound is cap-1; test that ONE
    # candidate erosion. Any inconclusive result keeps the original guard.
    cap=width//2
    if positive.OutlineCount() and cap>1:
        try:
            reached_cap=native_radius_positive_at(after,cap,deadline);old_cap=None;upper=cap
            if not reached_cap:
                old_cap=native_radius_positive_at(before,cap,deadline)
                require(not old_cap,'retained_consumer_contact_web_would_shrink')
                upper=cap-1
            proved=reached_cap or native_radius_positive_at(after,upper,deadline)
            if proved:
                return dict(uuid=force._uid(item),method='exact_native_radius_search_cap_witness',
                    legacy_search_cap_nm=cap,source_contact_positive=True,source_radius_upper_bound_nm=upper,
                    candidate_radius_lower_bound_nm=upper,source_cap_erosion_positive=old_cap,
                    candidate_at_cap_erosion_positive=reached_cap,maximum_inscribed_radius_cannot_decrease=True,
                    same_native_erosion_and_integer_radius_domain=True,current_or_barrel_capacity_qualified=False)
        except ValueError as exc:
            # An optional fast witness expiring must not consume/tighten the
            # original independent fallback leases or discard a valid offer.
            if str(exc)!='native_contact_cap_witness_deadline':raise
    # Keep the original independent ten-second radius leases. Sharing one
    # lease across old+new would silently tighten the old fallback and lose
    # a valid offer merely because both native calculations take time.
    first=contacts.native_contact_radius(item,old,face,width,time.monotonic()+10.)
    last=contacts.native_contact_radius(item,new,face,width,time.monotonic()+10.)
    require(first>0 and last>=first,'retained_consumer_contact_web_would_shrink')
    return dict(uuid=force._uid(item),method='existing_native_inscribed_radius_fallback',before_nm=first,after_nm=last)


def inventory(board,source,*,board_hint,allow_locked_source=False,max_corners=8,minimum_flat_nm=20000,
        source_ownership='strict_outer'):
    authority=owner_for(source_ownership)
    require(type(allow_locked_source) is bool and type(max_corners) is int and 1<=max_corners<=8
        and type(minimum_flat_nm) is int and 20000<=minimum_flat_nm<=200000,'bounded_consumer_miter_work_required')
    live={force._uid(t):t for t in board.GetTracks()};groups=list(board.Groups())
    require(len(live)<=16384,'consumer_miter_native_inventory_bound')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()];offers=[];refused=[]
    issues=quality.analyze_board(board,min_open_angle_deg=134.999)['issues']
    for row in issues:
        if abs(row['opening_angle_deg']-90.)>.01:continue
        ids=row['track_uuids'];old=[live[u] for u in ids]
        owners=[g for g in groups if any(g.ContainsItem(t) for t in old)]
        if not owners and source_ownership!='retained_planar_island':continue
        request=dict(source_track_uuids=ids,net=row['net'],layer=int(old[0].GetLayer()))
        try:
            require(len(old)==2 and len({(t.GetWidth(),int(t.GetLayer()),bool(t.IsLocked())) for t in old})==1
                and all(not t.HasSolderMask() and (not t.IsLocked() or allow_locked_source) for t in old),
                'exact_uniform_process_and_explicit_locks_required')
            scope=authority.plan(board,source,board_hint=board_hint,retired_track_uuids=ids)
            common={tuple(old[0].GetStart()),tuple(old[0].GetEnd())}&{tuple(old[1].GetStart()),tuple(old[1].GetEnd())}
            require(len(common)==1,'literal_shared_consumer_corner_required')
            at=next(iter(common));face=int(old[0].GetLayer());width=old[0].GetWidth()
            request.update(at_nm=list(at),anchor_pad_uuids=[force._uid(p) for p in pads
                if p.GetNetCode()==old[0].GetNetCode() and p.IsOnLayer(face)
                and any(t.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0) for t in old)])
            shape=geometry._proposal(board,request,time.monotonic()+10.)
            far=[tuple(t.GetEnd()) if tuple(t.GetStart())==at else tuple(t.GetStart()) for t in old]
            vectors=[tuple(p[i]-at[i] for i in (0,1)) for p in far]
            scale=2 if octilinear.kind(*vectors)=='diagonal' else 1
            needed=width+math.isqrt(2*minimum_flat_nm**2)+1
            require(4*shape['inset_nm']**2*scale>=needed**2,'visible_full_width_inner_flat_required')
            new=[]
            for leg in shape['legs_nm']:
                t=old[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*leg['start_nm']));t.SetEnd(pcbnew.VECTOR2I(*leg['end_nm']));new.append(t)
            body=[t for t in board.GetTracks() if force._uid(t) not in ids and t.GetNetCode()==old[0].GetNetCode()
                and t.IsOnLayer(face) and any(s.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face),0) for s in old)]
            webs=[]
            for item in body:
                webs.append(retained_contact_proof(item,old,new,face,width,time.monotonic()+10.))
            gain=sum(t.GetLength() for t in old)-sum(t.GetLength() for t in new)
            require(gain>0,'consumer_miter_must_shorten_actual_strokes')
            offers.append(dict(request=request,shape=shape,group_uuid=scope['group_uuid'],
                predicted_length_removed_mm=gain/1e6,retained_native_contact_webs=webs))
        except (ValueError,RuntimeError,KeyError) as exc:refused.append(dict(request=request,reason=str(exc)))
    offers.sort(key=lambda q:(-q['predicted_length_removed_mm'],q['request']['source_track_uuids']))
    by_group={}
    for offer in offers:
        batch=by_group.setdefault(offer['group_uuid'],[])
        used={u for q in batch for u in q['request']['source_track_uuids']}
        if not used&set(offer['request']['source_track_uuids']) and len(batch)<max_corners:batch.append(offer)
    batches=sorted(by_group.values(),key=lambda qs:(-len(qs),-sum(q['predicted_length_removed_mm'] for q in qs)))
    return dict(batches=batches,refusals=refused,positive_corner_offers=len(offers),source_ownership=source_ownership,
        complete=True,source_mutated=False,electrical_or_release_authority=False)


def baseline(data,source,epoch,source_ownership='strict_outer'):
    require(data['code_identity']==epoch,'consumer_miter_baseline_code_mismatch')
    if data.get('tool_kind')=='source_consumer_corner_miter':
        require(data.get('source_ownership','strict_outer')==source_ownership,'consumer_miter_baseline_owner_changed')
        require(data['ok'] and data['complete'] and data['changed'] and data['candidate_sha256']==force._hash(source),
            'exact_previous_consumer_miter_candidate_required')
        require(data['input_sha256'][str(Path(__file__).resolve())]==force._hash(Path(__file__)),
            'consumer_miter_baseline_tool_changed')
        authority_path=Path(owner_for(source_ownership).__file__).resolve()
        require(data['input_sha256'].get(str(authority_path))==force._hash(authority_path),
            'consumer_miter_baseline_authority_changed')
        producer=data['native_candidate_producer']
    else:
        sides=[v for v in data['boards'].values() if v['sha256']==force._hash(source)]
        require(bool(sides),'literal_consumer_miter_baseline_source_required');producer=sides[0]['native_producer']
    require(producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated'],
        'complete_uncapped_consumer_miter_native_baseline_required')
    path=Path(producer['report']);require(force._hash(path)==producer['report_sha256'],'baseline_native_report_changed')
    report=json.loads(path.read_text());require(not report['unconnected_items'],'source_must_have_zero_opens')
    return report,producer


def run(source,out,*,board_hint,expected_source_sha256,grade,reporting_build,allow_locked_source=False,max_corners=8,
        source_ownership='strict_outer'):
    authority=owner_for(source_ownership)
    source,out,grade=map(lambda p:Path(p).resolve(),(source,out,grade))
    require(type(expected_source_sha256) is str and len(expected_source_sha256)==64
        and force._hash(source)==expected_source_sha256,'literal_consumer_miter_source_hash_required')
    require(not out.exists(),'fresh_consumer_miter_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    inputs={str(p):force._hash(p) for p in (Path(__file__).resolve(),Path(authority.__file__).resolve(),grade)}
    prior,producer=baseline(json.loads(grade.read_text()),source,epoch,source_ownership)
    inputs[producer['report']]=producer['report_sha256'];keys={admission._canonical_identity(v) for v in prior['violations']}
    board=pcbnew.LoadBoard(str(source));menu=inventory(board,source,board_hint=board_hint,
        allow_locked_source=allow_locked_source,max_corners=max_corners,source_ownership=source_ownership)
    out.mkdir(parents=True,exist_ok=False)
    result=dict(ok=True,complete=True,changed=False,errors=[],tool_kind='source_consumer_corner_miter',
        source=str(source),source_sha256=force._hash(source),code_identity=epoch,input_sha256=inputs,
        inventory=menu,attempts=[],records=[],source_ownership=source_ownership,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    for index,batch in enumerate(menu['batches'][:8]):
        board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
        cut=sorted({u for q in batch for u in q['request']['source_track_uuids']});trial=dict(accepted=False,corners=len(batch))
        result['attempts'].append(trial)
        try:
            scope=authority.plan(board,source,board_hint=board_hint,retired_track_uuids=cut);new=[]
            for offer in batch:
                exemplar=live[offer['request']['source_track_uuids'][0]]
                for leg in offer['shape']['legs_nm']:
                    t=exemplar.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*leg['start_nm']))
                    t.SetEnd(pcbnew.VECTOR2I(*leg['end_nm']));new.append(t)
            authority.subtract(board,scope)
            for t in new:board.Add(t)
            added=[force._uid(t) for t in new];authority.assign(board,scope,added,[]);additive._ground_refill(board)
            child=force._copy_family(source,out/('UNADMITTED-group-miter-'+str(index)));field._save_field_snapshot(board,child)
            proof=authority.receive(source,child,board_hint=board_hint,retired_track_uuids=cut)
            trial.update(candidate=str(child),candidate_sha256=force._hash(child),receiving=proof)
            require(proof['ok'] and proof['complete'] and not proof['errors'],'independent_consumer_group_receiving_refused')
            shadow=force._copy_family(child,out/('native-input-'+str(index)));report=out/('native-'+str(index)+'.json')
            actual=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
            require(actual['ok'] and actual['complete'] and not actual['native_inventory']['potentially_truncated'],
                'complete_consumer_miter_native_receiving_required')
            measured=json.loads(report.read_text());faults=[v for v in measured['violations'] if admission._canonical_identity(v) not in keys]
            trial.update(new_native_faults=faults,opens=len(measured['unconnected_items']))
            require(not faults and not trial['opens'],'consumer_miter_new_native_fault_or_open')
            before=quality.analyze_board(pcbnew.LoadBoard(str(source)));after=quality.analyze_board(board)
            require(after['issue_count']<=before['issue_count'] and after['non_octilinear_count']<=before['non_octilinear_count'],
                'consumer_miter_route_craft_regressed')
            trial['accepted']=True
            result.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                records=[dict(plan=dict(retired_track_uuids=cut),materialized=dict(retired_track_uuids=cut,added_native_uuids=added))],
                corners=len(batch),actual_length_removed_mm=sum(q['predicted_length_removed_mm'] for q in batch),
                source_group_scope=scope,shapes=batch,independent_source_consumer_receiving=proof,native_candidate_producer=actual)
            break
        except (ValueError,RuntimeError,KeyError) as exc:trial['refusal']=str(exc)
    result['source_family_and_code_unchanged']=(epoch==force._code_identity() and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in inputs.items()))
    require(result['source_family_and_code_unchanged'],'consumer_miter_input_epoch_changed')
    force._write(out/'stage.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','grade','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('board-hint','expected-source-sha256'):p.add_argument('--'+key,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-corners',type=int,default=8)
    p.add_argument('--source-ownership',choices=('strict_outer','planar_nonplane','retained_planar_island'),default='strict_outer')
    a=p.parse_args();r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        grade=a.grade,reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_corners=a.max_corners,
        source_ownership=a.source_ownership)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','corners','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
