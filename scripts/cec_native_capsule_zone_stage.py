"""Bounded real-track to native-zone finishing with whole-source receiving.

No board names, references, coordinates, new current budgets or current
division select a repair. The existing complete source domain and per-face
width contract own each cut. Every old track capsule must remain inside real
saved native fill. A separate replay rebuilds the entire transaction from the
immutable parent; renderer masks and a worker's success flags grant nothing.
Existing split/cross-layer buses, barrels, poses and board dimensions stay put.
An explicit source-retaining mode adds only a verified outer contour. It does
not replace rated tracks, claim duplicate current capacity or relax cut proof.
"""
from collections import defaultdict
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
import cec_field_coupling as field
import cec_force_crossface_receiving as force_receiver
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_native_drc_runner as native
import cec_ordinary_route_receiving as ordinary
import cec_power_contours as contours
import cec_rectilinear_copper as owner
import cec_route_quality as quality
import cec_stage_admission as admission


def plan(board, source, ids, *, board_hint, style='chamfer45', allow_locked_source=False,
         retain_source_tracks=False):
    """Read-only plan from actual source strokes and unchanged design authority."""
    if (type(board_hint) is not str or not board_hint or type(ids) is not list
            or not 1 <= len(ids) <= 2 or len(set(ids)) != len(ids)
            or any(type(u) is not str or not u for u in ids)
            or type(allow_locked_source) is not bool or type(retain_source_tracks) is not bool
            or style not in ('square','chamfer45')):
        raise ValueError('bounded_explicit_source_capsule_zone_context_required')
    live={force._uid(t):t for t in board.GetTracks()}
    if len(live)>16384 or not set(ids)<=live.keys():
        raise ValueError('bounded_actual_capsule_source_inventory_required')
    selected=[live[u] for u in ids]
    if (any(t.GetClass()!='PCB_TRACK' or t.HasSolderMask() or t.GetParentGroup()
            or t.IsLocked() and not allow_locked_source or not 0<t.GetLength()<=128000000
            for t in selected)
            or len({(t.GetNetname(),int(t.GetLayer())) for t in selected})!=1):
        raise ValueError('plain_same_face_owned_native_capsules_required')
    net=str(selected[0].GetNetname())
    if not net or net.rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND'):
        raise ValueError('ground_is_not_an_owned_supply_capsule')
    with force._thermal_hint(board_hint):
        domain=topology.board_current_domains(board,board_hint).get(net)
        contract=topology.route_width_contracts(board,board_hint=board_hint).get(net)
    if (type(domain) is not dict or domain.get('complete') is not True or domain.get('missing_refs')
            or domain.get('net')!=net or not domain.get('source_refs') or not domain.get('sink_refs')
            or type(contract) is not dict):
        raise ValueError('positive_existing_complete_source_domain_required')
    for row in (domain,contract):
        amps=row.get('amps')
        if type(amps) not in (int,float) or not math.isfinite(amps) or amps<=0:
            raise ValueError('unchanged_positive_source_current_authority_required')
    if domain['amps']!=contract['amps']:
        raise ValueError('source_domain_and_face_contract_disagree')
    for item in selected:
        force_receiver.require_track_floor(board,item,contract,item.GetWidth())
    spec=fr._project_netclass_resolver(str(source))(net) or {}
    clearance=spec.get('clearance',.2)
    if type(clearance) not in (int,float) or not math.isfinite(clearance) or clearance<0:
        raise ValueError('valid_unchanged_source_clearance_required')
    proposal=owner.plan(board,ids,clearance_nm=max(int(board.GetDesignSettings().m_MinClearance),
        math.ceil(clearance*1e6)),min_thickness_nm=100000,
        required_width_nm=min(t.GetWidth() for t in selected),
        allow_locked_track_uuids=ids if allow_locked_source else (),
        retire_source_tracks=not retain_source_tracks,contour_style=style,contour_grid_nm=1000,
        fill_envelope_margin_nm=4,timeout_s=10.)
    return proposal


def receive_literal_phase(source,candidate,records,*,board_hint,allow_locked_source=False,
                          retain_source_tracks=False):
    """Rebuild every primitive and native fill from the immutable source."""
    result=dict(ok=False,complete=False,errors=[],new_capacity_credited=False,
        current_qualified=False,release_authority=False)
    try:
        if (type(retain_source_tracks) is not bool
                or type(records) is not list or not 1<=len(records)<=8
                or any(type(r) is not dict or set(r)!={'plan','materialized'} for r in records)):
            raise ValueError('bounded_exact_capsule_zone_records_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        selected=[r['uuid'] for record in records for r in record['plan']['source_tracks']]
        cut=[] if retain_source_tracks else selected
        added=[r['materialized']['zone_uuid'] for r in records]
        if (len(set(selected))!=len(selected) or len(set(added))!=len(added) or set(added)&old.keys()
                or old.keys()-new.keys()!=set(cut) or new.keys()-old.keys()!=set(added)
                or any(new[u][0]!='zone' for u in added)):
            raise ValueError('exact_original_capsules_to_fresh_native_zones_required')
        if (force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('capsule_zone_source_metadata_or_sidecars_changed')
        child=pcbnew.LoadBoard(str(paths[1]));proofs=[]
        with tempfile.TemporaryDirectory(prefix='cec-capsule-zone-receiving-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            rebuilt=pcbnew.LoadBoard(str(expected))
            for record in records:
                declared=record['plan'];ids=[r['uuid'] for r in declared['source_tracks']]
                derived=plan(rebuilt,paths[0],ids,board_hint=board_hint,
                    style=declared['contour_style'],allow_locked_source=allow_locked_source,
                    retain_source_tracks=retain_source_tracks)
                if derived!=declared:
                    raise ValueError('capsule_zone_plan_not_rederived_from_actual_source')
                made=owner.materialize(rebuilt,derived,
                    allow_locked_track_uuids=ids if allow_locked_source else ())
                fresh=next(z for z in rebuilt.Zones() if force._uid(z)==made['zone_uuid'])
                uid=record['materialized']['zone_uuid'];fresh.m_Uuid.Clone(pcbnew.KIID(uid))
                made['zone_uuid']=uid
                if made!=record['materialized']:
                    raise ValueError('capsule_zone_materialized_record_changed')
                owner.fill(rebuilt,derived,uid,timeout_s=10.)
                additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,expected)
                rebuilt=pcbnew.LoadBoard(str(expected))
                proof=owner.receive(child,derived,uid,timeout_s=10.)
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('actual_saved_full_original_capsule_not_enclosed:'+str(proof['reason']))
                proofs.append(proof)
            _,actual=additive._nodes(expected)
            if (actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new)):
                raise ValueError('whole_native_capsule_zone_and_ground_refill_replay_differs')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('capsule_zone_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),code_identity=epoch,
            source_candidate_and_code_unchanged=True,retired_track_uuids=cut,added_zone_uuids=added,
            retained_track_uuids=selected if retain_source_tracks else [],
            modified_nets=sorted({r['plan']['net'] for r in records}),
            exact_source_phase_and_native_ground_refill_received=True,
            saved_full_original_capsule_receiving=proofs)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source,candidate,records,*,board_hint,allow_locked_source=False,sense_timeout_s=40.,
            retain_source_tracks=False):
    """Strict whole-source current, retained connectivity, field and absolute cuts."""
    result=dict(ok=False,complete=False,errors=[],new_capacity_credited=False,
        current_qualified=False,coupled_thermal_qualified=False,unknown_evidence_qualified=False,
        branch_sharing_assumed=False,fab_ready=False,release_authority=False)
    try:
        sense_timeout_s=force_receiver.evidence_replay_budget(sense_timeout_s)
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        literal=receive_literal_phase(*paths,records,board_hint=board_hint,allow_locked_source=allow_locked_source,
            retain_source_tracks=retain_source_tracks)
        result['independent_saved_phase']=literal
        if not literal['ok'] or not literal['complete']:
            raise ValueError('native_capsule_zone_literal_phase_refused:'+str(literal['errors']))
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        parts=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=literal['retired_track_uuids'])
        updated=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*parts))
        if not all(any(part<=other for other in updated) for part in parts):
            raise ValueError('original_retained_native_capsule_partition_lost')
        debt=current.receive(*paths,board_hint=board_hint);result['whole_source_current_receiving']=debt
        if not debt['ok'] or not debt['complete']:
            raise ValueError('unchanged_whole_source_current_debt_required')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        result['new_field_blockers']=delta
        if delta:raise ValueError('new_native_capsule_zone_field_blocker')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in paths]
        by_net=defaultdict(lambda:dict(retired_track_uuids=[],added_zone_uuids=[]))
        for record in records:
            row=by_net[record['plan']['net']]
            if not retain_source_tracks:
                row['retired_track_uuids'] += [r['uuid'] for r in record['plan']['source_tracks']]
            row['added_zone_uuids'].append(record['materialized']['zone_uuid'])
        transforms=[dict(net=n,**{k:sorted(v) for k,v in row.items()}) for n,row in sorted(by_net.items())]
        proof=sense.compare_contour_preservation(first,last,modified_nets=literal['modified_nets'],
            native_copper_transforms=transforms)
        result['physical_kelvin_preservation']=proof
        if not proof['comparison_complete'] or not proof['same_evidence']:
            raise ValueError('two_absolute_changed_cuts_and_strict_unaffected_evidence_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('capsule_zone_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),code_identity=epoch,
            source_candidate_and_code_unchanged=True,all_retained_native_partitions_preserved=True,
            full_original_current_copper_preserved=True,native_item_transforms=transforms,
            fresh_uncapped_DRC_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_changes=4,max_fills=8,sense_timeout_s=40.,retain_source_tracks=False,
        min_width_mm=1.0):
    """Finite sequential proposals, one whole-original-source receiving boundary."""
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(allow_locked_source) is not bool or type(retain_source_tracks) is not bool
            or type(min_width_mm) not in (int,float) or not math.isfinite(min_width_mm)
            or not 0<min_width_mm<=100.
            or reporting_build is None
            or type(max_changes) is not int or not 1<=max_changes<=8
            or type(max_fills) is not int or not max_changes<=max_fills<=16):
        raise ValueError('bounded_explicit_capsule_zone_stage_context_required')
    sense_timeout_s=force_receiver.evidence_replay_budget(sense_timeout_s)
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('exact_source_and_fresh_capsule_zone_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    started=time.monotonic();deadline=started+300.
    result=dict(ok=False,complete=False,changed=False,source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        errors=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,
        branch_sharing_assumed=False,new_capacity_credited=False,retain_source_tracks=retain_source_tracks,
        contour_inventory_min_width_mm=min_width_mm)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        proof=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        result.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_capsule_zone_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_optional_capsule_zone_finishing')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        active=source;fills=0;tried=set();initial=contours.audit_board(pcbnew.LoadBoard(str(source)),
            timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
        result['before_contours']=initial
        if not initial['complete']:raise ValueError('complete_original_power_contour_inventory_required')
        for _ in range(max_changes):
            parent=pcbnew.LoadBoard(str(active));before=quality.analyze_board(parent)
            with force._thermal_hint(board_hint):
                before_field=field.blocker_keys(field.field_coupling_summary(str(active)))
            inventory=contours.finding_requests(parent,timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
            if not inventory['complete']:raise ValueError('complete_local_capsule_inventory_required')
            progress=False
            for request in inventory['requests'][:64]:
                ids=[r['uuid'] for r in request['source_tracks']]
                for style in ('chamfer45','square'):
                    key=(tuple(sorted(ids)),style)
                    if key in tried:continue
                    if fills>=max_fills or time.monotonic()>=deadline:break
                    tried.add(key);row=dict(source=str(active),request=request,style=style,
                        geometry_screened=False,accepted=False);result['attempts'].append(row)
                    try:
                        b=pcbnew.LoadBoard(str(active))
                        proposal=plan(b,active,ids,board_hint=board_hint,style=style,
                            allow_locked_source=allow_locked_source,retain_source_tracks=retain_source_tracks)
                        fills+=1;made=owner.materialize(b,proposal,
                            allow_locked_track_uuids=ids if allow_locked_source else ())
                        owner.fill(b,proposal,made['zone_uuid'],timeout_s=10.);additive._ground_refill(b)
                        child=force._copy_family(active,outdir/('UNADMITTED-capsule-zone-'+str(len(result['attempts'])-1)))
                        field._save_field_snapshot(b,child);saved=pcbnew.LoadBoard(str(child))
                        proof=owner.receive(saved,proposal,made['zone_uuid'],timeout_s=10.)
                        row['saved_full_original_capsule_receiving']=proof
                        if not proof['ok'] or not proof['complete']:raise ValueError('saved_original_capsule_loss:'+str(proof['reason']))
                        after=quality.analyze_board(saved)
                        old=contours.audit_board(parent,timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
                        new=contours.audit_board(saved,timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
                        row['after_contours']=new
                        if (not old['complete'] or not new['complete'] or new['finding_count']>=old['finding_count']
                                or after['issue_count']>before['issue_count']
                                or after['non_octilinear_count']>before['non_octilinear_count']):
                            raise ValueError('strict_native_power_contour_gain_without_route_regression_required')
                        debt=current.receive(active,child,board_hint=board_hint);row['current_screen']=debt
                        if not debt['ok'] or not debt['complete']:raise ValueError('native_capsule_zone_current_screen_refused')
                        with force._thermal_hint(board_hint):
                            field_delta=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-before_field)
                        row['new_field_blockers']=field_delta
                        if field_delta:raise ValueError('native_capsule_zone_field_screen_refused')
                        observed=observe(child,'candidate-'+str(len(result['attempts'])-1))
                        new_faults=sorted({admission._canonical_identity(v) for v in observed['violations']}-faults)
                        row['new_native_fault_ids']=new_faults;row['native_opens']=len(observed['unconnected_items'])
                        if observed['unconnected_items'] or new_faults:raise ValueError('capsule_zone_native_opens_or_new_warning')
                        result['records'].append(dict(plan=proposal,materialized=made))
                        row.update(geometry_screened=True,candidate=str(child),candidate_sha256=force._hash(child))
                        active=child;progress=True;break
                    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
                        row['refusal']=type(exc).__name__+':'+str(exc)
                if progress or fills>=max_fills or time.monotonic()>=deadline:break
            if not progress:break
        result['fill_trials']=fills
        if result['records']:
            proof=receive(source,active,result['records'],board_hint=board_hint,
                allow_locked_source=allow_locked_source,sense_timeout_s=sense_timeout_s,
                retain_source_tracks=retain_source_tracks)
            result['independent_whole_source_receiving']=proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('whole_original_capsule_zone_phase_refused:'+str(proof['errors']))
            result.update(changed=True,candidate=str(active),candidate_sha256=force._hash(active))
            for row in result['attempts']:
                row['accepted']=row['geometry_screened']
        result['after_contours']=contours.audit_board(pcbnew.LoadBoard(result['candidate']),
            timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
        result.update(ok=True,complete=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    result['source_family_and_code_unchanged']=stable
    if not stable:
        result.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        result['errors'].append('capsule_zone_source_or_code_changed')
    result['wall_elapsed_s']=time.monotonic()-started;force._write(outdir/'stage.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--board-hint',required=True);parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--allow-locked-source',action='store_true')
    parser.add_argument('--retain-source-tracks',action='store_true',
        help='Add a native outer contour but retain all source rated tracks and strict electrical receiving')
    parser.add_argument('--max-changes',type=int,default=4);parser.add_argument('--max-fills',type=int,default=8)
    parser.add_argument('--min-width-mm',type=float,default=1.,
        help='Explicit contour inventory floor only; current-width and fabrication rules remain unchanged')
    parser.add_argument('--sense-timeout-s',type=float,default=40.);args=parser.parse_args()
    import wx
    quiet=wx.LogNull()
    result=run(args.source,args.out,board_hint=args.board_hint,expected_source_sha256=args.expected_source_sha256,
        reporting_build=args.reporting_build,allow_locked_source=args.allow_locked_source,
        max_changes=args.max_changes,max_fills=args.max_fills,sense_timeout_s=args.sense_timeout_s,
        retain_source_tracks=args.retain_source_tracks,min_width_mm=args.min_width_mm)
    print(json.dumps(dict(receipt=str(args.out/'stage.json'),ok=result['ok'],complete=result['complete'],
        changed=result['changed'],before=result.get('before_contours',{}).get('finding_count'),
        after=result.get('after_contours',{}).get('finding_count'),candidate_sha256=result['candidate_sha256'],
        errors=result['errors'])),flush=True)
    return 0 if result['ok'] and result['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
