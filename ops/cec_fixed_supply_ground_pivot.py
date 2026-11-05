"""Fixed-supply capacitor pivots with freshly proved shorter Ground returns.

This source-owned constructor never cuts a track, bus, barrel or pour and
never changes a part, load, factory rule or current rating. Existing saved
local POFV rules supply dimensions, not a profile-name-only permission. Full
current/fields/Kelvin/native-DRC/assembly receiving remains mandatory.
"""
import argparse,json,math,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_capacitor_return_repack as capacitors
import cec_decoupler_cell as cells
import cec_existing_local_pofv_pad_rule as saved_rule
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as references
import cec_pi_cleanup as placement
import cec_pose_additive_reconstruction as poses
import cec_search_budget as budget
import cec_consumer_corner_miter as contacts
import cec_native_ground_span_reflow as ground_chain
import cec_sensitive_scalar_path_reflow as path_geometry


def require(condition,message):
    if not condition:raise ValueError(message)


def plan(board,source,*,board_hint,pad_uuid,turn_degrees):
    require(type(board_hint) is str and bool(board_hint) and type(pad_uuid) is str
        and type(turn_degrees) is int and turn_degrees in (90,180,270),
        'literal_fixed_supply_ground_pivot_scope_required')
    fp,ground,supply,face=capacitors.context(board,pad_uuid)
    before=cells._existing_return(board,ground,16.,allow_native_track_body=True)
    require(before is not None and before[0]>.1,'known_source_ground_return_required')
    context=saved_rule.resolve(board,ground)
    require(context is not None,'exact_existing_source_local_factory_rule_required')
    groups=[g for g in board.Groups() if g.GetName()==saved_rule.GROUP]
    require(len(groups)==1 and not groups[0].IsLocked(),'unlocked_exact_source_local_factory_group_required')
    limits=context['minimum_nm'];geometry=saved_rule.geometry(context,
        (limits['via_diameter']/1e6,limits['hole_size']/1e6))
    # Work on an isolated native copy: discovery itself changes no source
    # item or caller-owned connectivity epoch.
    trial=pcbnew.FOOTPRINT(fp);anchor=supply.GetPosition()
    trial.SetOrientationDegrees(fp.GetOrientationDegrees()+turn_degrees)
    moved=trial.FindPadByNumber(supply.GetNumber());at=fp.GetPosition()+anchor-moved.GetPosition()
    require(math.dist(tuple(at),tuple(fp.GetPosition()))<=2000000,'bounded_fixed_supply_capacitor_pivot_required')
    return dict(schema=1,source_sha256=force._hash(source),authority_sha256=force._hash(Path(__file__)),
        footprint_uuid=force._uid(fp),ground_pad_uuid=pad_uuid,supply_pad_uuid=force._uid(supply),
        source_supply_nm=list(anchor),source_supply_net=supply.GetNetname(),surface_id=face,
        turn_degrees=turn_degrees,target_pose=[at.x/1e6,at.y/1e6,trial.GetOrientationDegrees()],
        source_return_mm=before[0],source_factory_context=context,geometry_mm=list(geometry),
        source_bypass_assignments=capacitors._assignments(board,board_hint),
        source_copper_retirement_authorized=False,current_or_release_qualified=False)


def construct(board,source,scope,*,board_hint):
    fresh=plan(board,source,board_hint=board_hint,pad_uuid=scope['ground_pad_uuid'],turn_degrees=scope['turn_degrees'])
    require(fresh==scope,'fixed_supply_ground_pivot_stale_or_forged_plan')
    fp,ground,supply,_=capacitors.context(board,scope['ground_pad_uuid'])
    fp.SetPosition(pcbnew.VECTOR2I(round(scope['target_pose'][0]*1e6),round(scope['target_pose'][1]*1e6)))
    fp.SetOrientationDegrees(scope['target_pose'][2])
    require(list(supply.GetPosition())==scope['source_supply_nm'],'fixed_supply_anchor_moved')
    saved_rule.bind_projected_source_poses(board,{fp.GetReference():scope['target_pose']})
    placement._pose_preflight(board,fp)
    require(scope['source_bypass_assignments']==capacitors._assignments(board,board_hint),'fixed_supply_pivot_assignment_changed')
    diagnostics={}
    with force._thermal_hint(board_hint),budget.scoped(30000) as work:
        made,error=cells._add_ground_return(board,ground,board_path=str(source),reach_mm=.75,
            lock=True,diagnostics=diagnostics,pofv_geometry=tuple(scope['geometry_mm']))
        search=work.report()
    require(made is not None,'bounded_fixed_supply_pivot_ground_entry_refused:'+str(error))
    items=made.pop('items',[])
    require(len(items)<=5,'bounded_local_ground_pivot_additions_required')
    group=fr.group_local_pofv_signal_vias(board,items) if items else None
    additive._ground_refill(board)
    return dict(scope=scope,added_native_uuids=sorted(force._uid(t) for t in items),
        actual_ground_entry=made,local_group_extension=group,search=search,
        independent_saved_and_original_parent_receiving_still_required=True)


def supply_contacts(parent,child,old,new,face):
    peers=[*parent.GetTracks(),*(p for fp in parent.GetFootprints() for p in fp.Pads()),*parent.Zones()]
    require(len(peers)<=16384,'fixed_supply_pivot_contact_inventory_bound')
    result=[];width=min(old.GetSize());live={force._uid(p):p for p in child.GetTracks()}
    live.update({force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads()})
    live.update({force._uid(z):z for z in child.Zones()})
    for item in peers:
        if force._uid(item)==force._uid(old) or item.GetNetCode()!=old.GetNetCode() or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            require(item.IsFilled() and item.HasFilledPolysForLayer(face),'source_supply_contact_fill_unknown')
            shape=item.GetFilledPolysList(face)
        else:shape=item.GetEffectiveShape(face)
        if not shape.Collide(old.GetEffectiveShape(face),0):continue
        require(force._uid(item) in live,'source_supply_peer_missing')
        result.append(contacts.retained_contact_proof(item,[old],[new],face,width,time.monotonic()+10.))
    require(bool(result),'actual_positive_source_supply_contact_required')
    return result


def receive(source,candidate,*,board_hint,pad_uuid,turn_degrees):
    r=dict(ok=False,complete=False,errors=[],current_or_barrel_capacity_qualified=False,
        routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(source!=candidate,'distinct_source_and_saved_fixed_supply_pivot_required')
        epoch=force._code_identity();digest=force._hash(Path(__file__));families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=plan(parent,source,board_hint=board_hint,pad_uuid=pad_uuid,turn_degrees=turn_degrees)
        fp,ground,supply,face=capacitors.context(child,pad_uuid)
        require(force._uid(fp)==scope['footprint_uuid'] and force._uid(supply)==scope['supply_pad_uuid']
            and list(supply.GetPosition())==scope['source_supply_nm'] and supply.GetNetname()==scope['source_supply_net']
            and [fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]==scope['target_pose'],
            'actual_saved_fixed_supply_pivot_differs_from_source')
        placement._pose_preflight(child,fp)
        owned=poses.receive(source,candidate,selected_footprint_uuids=[scope['footprint_uuid']],board_hint=board_hint,
            timeout_s=10.,max_shift_mm=2.,allow_field_reflow=True)
        r['independent_saved_native_pose']=owned
        require(owned['ok'] and owned['complete'],'independent_fixed_supply_pose_refused:'+str(owned['errors']))
        require(force._sidecars(source)==force._sidecars(candidate),'fixed_supply_pivot_native_rules_or_sidecars_changed')
        require(scope['source_bypass_assignments']==capacitors._assignments(child,board_hint),'fixed_supply_pivot_bypass_assignments_changed')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        live={force._uid(t):t for t in child.GetTracks()}
        require(not set(old)-set(new) and incoming<=live.keys() and len(incoming)<=5,'ground_pivot_cannot_cut_or_add_untyped_material')
        vias=[live[u] for u in incoming if live[u].GetClass()=='PCB_VIA']
        require(len(vias)<=1 and all(t.GetNetname()=='GND' and t.GetClass() in ('PCB_VIA','PCB_TRACK') for t in [live[u] for u in incoming]),
            'fixed_supply_pivot_only_one_new_local_ground_barrel')
        require(all(live[u].IsLocked() for u in incoming),'new_fixed_supply_ground_entry_must_remain_locked')
        plane=[]
        for via in vias:
            geometry=(via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6)
            require(saved_rule.geometry(scope['source_factory_context'],geometry)==geometry
                and fab.local_pofv_via_decision(child,via)[0],'saved_ground_barrel_has_no_exact_source_process_authority')
            settings=parent.GetDesignSettings();diameter=via.GetWidth(via.TopLayer());drill=via.GetDrillValue()
            if diameter<settings.m_ViasMinSize or drill<settings.m_MinThroughDrill or diameter-drill<2*settings.m_ViasMinAnnularWidth:
                old_groups=[g for g in parent.Groups() if g.GetName()==saved_rule.GROUP]
                new_groups=[g for g in child.Groups() if g.GetName()==saved_rule.GROUP]
                require(len(old_groups)==len(new_groups)==1 and force._uid(old_groups[0])==force._uid(new_groups[0])
                    and new_groups[0].ContainsItem(via),'actual_existing_native_group_required_for_local_barrel_floor')
            plane=references._reference_contacts(child,via)
        new_return=cells._existing_return(child,ground,16.,allow_native_track_body=True)
        require(new_return is not None and new_return[0]<=.75 and new_return[0]<scope['source_return_mm']-.1,
            'strict_saved_immediate_ground_return_gain_required')
        tracks=[live[u] for u in incoming if live[u].GetClass()=='PCB_TRACK']
        if tracks:
            width=max(child.GetDesignSettings().m_TrackMinWidth,int(cells._netclass(child,'GND')['width']))
            require(all(int(t.GetLayer())==face and t.GetWidth()==width and not t.HasSolderMask()
                and not t.GetParentGroup() for t in tracks),'exact_full_class_local_ground_connector_required')
            points=ground_chain._chain(tracks);path_geometry._points([list(p) for p in points])
            require({points[0],points[-1]}=={tuple(ground.GetPosition()),tuple(new_return[1].GetPosition())}
                and sum(t.GetLength() for t in tracks)<=750000,'every_new_ground_track_must_belong_to_the_actual_immediate_return')
        preservation=returns.receive(parent,child)
        require(preservation['ok'] and preservation['complete'],'fixed_supply_pivot_regressed_another_ground_terminal')
        old_pad=next(p for fp in parent.GetFootprints() for p in fp.Pads() if force._uid(p)==scope['supply_pad_uuid'])
        contact_proof=supply_contacts(parent,child,old_pad,supply,face)
        require(epoch==force._code_identity() and digest==force._hash(Path(__file__))
            and families==[force._family(p,board_hint) for p in (source,candidate)],'fixed_supply_pivot_sources_or_authority_changed')
        r.update(ok=True,complete=True,source_scope=scope,source_candidate_and_code_unchanged=True,
            modified_footprint_uuids=[scope['footprint_uuid']],retired_native_uuids=[],added_native_uuids=sorted(incoming),
            source_supply_pad_centre_and_all_source_tracks_preserved=True,source_bypass_assignments_preserved=True,
            source_rules_and_dimensions_preserved=True,actual_supply_contact_webs=contact_proof,
            all_original_ground_returns=preservation,source_return_mm=scope['source_return_mm'],saved_return_mm=new_return[0],
            return_gain_mm=scope['source_return_mm']-new_return[0],actual_ground_reference_contacts=plane,
            exact_source_process_geometry_rederived=True,full_original_parent_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover(board,source,*,board_hint,max_capacitors=8):
    require(type(max_capacitors) is int and 1<=max_capacitors<=32,'bounded_fixed_supply_pivot_catalog_required')
    observed=returns._observe(board,16.,time.monotonic()+10.)
    ordered=sorted((q for q in observed.values() if q['return_mm'] is not None and q['return_mm']>.1),
        key=lambda q:(-q['return_mm'],tuple(q['at_nm']),q['pad_uuid']))
    offers=[];refusals=[];seen=0
    for row in ordered:
        try:
            capacitors.context(board,row['pad_uuid'])
            saved=saved_rule.resolve(board,next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==row['pad_uuid']))
            require(saved is not None,'exact_existing_source_local_factory_rule_required')
        except (ValueError,RuntimeError,KeyError) as exc:
            refusals.append(dict(pad_uuid=row['pad_uuid'],reason=str(exc)));continue
        if seen==max_capacitors:break
        seen+=1
        for turn in (90,180,270):
            try:offers.append(plan(board,source,board_hint=board_hint,pad_uuid=row['pad_uuid'],turn_degrees=turn))
            except (ValueError,RuntimeError,KeyError) as exc:refusals.append(dict(pad_uuid=row['pad_uuid'],turn_degrees=turn,reason=str(exc)))
    return dict(offers=offers,refusals=refusals,complete=True,max_capacitors=max_capacitors,
        eligible_capacitors_considered=seen,catalog_is_bounded_not_global_impossibility=True,
        board_mutated=False,electrical_or_release_authority=False)


def run(source,out,*,board_hint,expected_source_sha256,grade,reporting_build,max_capacitors=8,max_trials=24):
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    import cec_field_coupling as field
    source,out,grade=[Path(p).resolve() for p in (source,out,grade)]
    require(type(max_trials) is int and 1<=max_trials<=24 and not out.exists()
        and force._hash(source)==expected_source_sha256,'fresh_bounded_hash_exact_ground_pivot_run_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    inputs={str(p):force._hash(p) for p in (Path(__file__).resolve(),Path(contacts.__file__).resolve(),grade)}
    prior,producer=contacts.baseline(json.loads(grade.read_text()),source,epoch)
    inputs[producer['report']]=producer['report_sha256'];keys={admission._canonical_identity(q) for q in prior['violations']}
    menu=discover(pcbnew.LoadBoard(str(source)),source,board_hint=board_hint,max_capacitors=max_capacitors)
    out.mkdir(parents=True);r=dict(ok=True,complete=True,changed=False,errors=[],tool_kind='fixed_supply_ground_pivot',
        source=str(source),source_sha256=force._hash(source),code_identity=epoch,input_sha256=inputs,
        inventory=menu,attempts=[],records=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    for i,scope in enumerate(menu['offers'][:max_trials]):
        args=dict(pad_uuid=scope['ground_pad_uuid'],turn_degrees=scope['turn_degrees'])
        trial=dict(plan=args,accepted=False);r['attempts'].append(trial)
        try:
            b=pcbnew.LoadBoard(str(source));made=construct(b,source,scope,board_hint=board_hint)
            target=force._copy_family(source,out/('UNADMITTED-fixed-supply-pivot-'+str(i)));field._save_field_snapshot(b,target)
            proof=receive(source,target,board_hint=board_hint,**args);trial['independent_saved_receiving']=proof
            require(proof['ok'] and proof['complete'],'saved_fixed_supply_ground_pivot_refused:'+str(proof['errors']))
            shadow=force._copy_family(target,out/('native-input-'+str(i)));report=out/('native-'+str(i)+'.json')
            actual=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
            require(actual['ok'] and actual['complete'] and not actual['native_inventory']['potentially_truncated'],
                'complete_uncapped_fixed_supply_pivot_native_receiving_required')
            after=json.loads(report.read_text());faults=[q for q in after['violations'] if admission._canonical_identity(q) not in keys]
            trial.update(new_native_faults=faults,opens=len(after['unconnected_items']))
            require(not faults and not trial['opens'],'fixed_supply_ground_pivot_new_native_fault_or_open')
            trial['accepted']=True
            r.update(changed=True,candidate=str(target),candidate_sha256=force._hash(target),
                records=[dict(plan=args,materialized=dict(modified_footprint_uuids=proof['modified_footprint_uuids'],
                    retired_native_uuids=[],added_native_uuids=proof['added_native_uuids']))],
                independent_source_receiving=proof,native_candidate_producer=actual,
                source_return_mm=proof['source_return_mm'],saved_return_mm=proof['saved_return_mm'],return_gain_mm=proof['return_gain_mm'])
            break
        except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:trial['refusal']=str(exc)
    r['source_family_and_code_unchanged']=(epoch==force._code_identity() and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in inputs.items()))
    require(r['source_family_and_code_unchanged'],'fixed_supply_ground_pivot_input_epoch_changed')
    r['bounded_attempt_limit_reached']=len(r['attempts'])==max_trials and not r['changed'] and len(menu['offers'])>max_trials
    force._write(out/'stage.json',r);return r


def main():
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','grade','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-capacitors',type=int,default=8);p.add_argument('--max-trials',type=int,default=24)
    a=p.parse_args();r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        grade=a.grade,reporting_build=a.reporting_build,max_capacitors=a.max_capacitors,max_trials=a.max_trials)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','return_gain_mm','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
