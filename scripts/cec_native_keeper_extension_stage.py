"""Bounded automatic existing-keeper contour refinement on a saved source.

Only source-retaining extensions are considered. No source copper, component,
layer, rule, current allocation or keeper process can be ripped up. Every
accepted prefix is independently replayed from the SAME initial source with
native DRC, full current, fields and absolute cuts. The stage has no production
selector, GUI, wafer/fab release or authority to guess a board's identity.
"""
import argparse
import json
import math
import time
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_native_keeper_extension_receiving as owner
import cec_rectilinear_copper as contour
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_power_contours as audit
import cec_native_drc_runner as native
import cec_stage_admission as admission


def screen_requests(board,requests,*,max_requests=8,max_screen_requests=128,
                    allow_signed_native_keeper=False,timeout_s=10.):
    """Spend construction leases on native-contact eligible requests, not a prefix.

    Screening has its own finite inventory and time limits. Skipped/ambiguous
    scopes are explicitly recorded and never reported as repaired or no-path.
    """
    if (type(requests) is not list or type(max_requests) is not int or not 1<=max_requests<=16
            or type(max_screen_requests) is not int or not 1<=max_screen_requests<=256
            or type(allow_signed_native_keeper) is not bool
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_actual_keeper_scheduler_context_required')
    deadline=time.monotonic()+timeout_s
    result=dict(source_request_count=len(requests),max_screen_requests=max_screen_requests,
        selected=[],screened=[],complete=False,construction_authority=False)
    for index,request in enumerate(requests[:max_screen_requests]):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('native_keeper_request_screen_deadline')
        row=dict(source_request_index=index,eligible=False)
        result['screened'].append(row)
        try:
            contacts=owner.contacting_keeper_uuids(board,[q['uuid'] for q in request['source_tracks']],
                allow_signed_native_keeper=allow_signed_native_keeper,timeout_s=remaining)
            row['contacting_keeper_uuids']=contacts
            if len(contacts)!=1:raise ValueError('one_actual_contacting_native_keeper_required:'+str(len(contacts)))
            row['eligible']=True
            result['selected'].append(dict(source_request_index=index,request=request))
        except (ValueError,KeyError,TypeError,RuntimeError) as exc:
            if time.monotonic()>=deadline:raise ValueError('native_keeper_request_screen_deadline') from exc
            row['refusal']=type(exc).__name__+':'+str(exc)
        if len(result['selected'])>=max_requests:break
    if time.monotonic()>=deadline:raise ValueError('native_keeper_request_screen_deadline')
    unexamined=len(requests)-len(result['screened'])
    result.update(complete=True,unexamined_source_requests=unexamined,
        all_source_requests_examined=unexamined==0,
        stop_reason=('source_inventory_exhausted' if not unexamined else
            'construction_request_budget' if len(result['selected'])==max_requests else 'screen_inventory_budget'))
    return result


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        max_requests=8,max_accepted=2,sense_timeout_s=10.,retain_existing_keeper_group=False,
        retained_native_track_material=False,allow_signed_native_keeper=False,request_scope='components',
        source_diagonal_quantum_nm=0,envelope_margin_nm=1000,min_width_mm=1.0,max_screen_requests=128):
    """Run a finite portfolio; unfinished findings are never called clean."""
    if (type(board_hint) is not str or not board_hint
            or type(expected_source_sha256) is not str or len(expected_source_sha256)!=64
            or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(max_requests) is not int or not 1<=max_requests<=16
            or type(max_screen_requests) is not int or not 1<=max_screen_requests<=256
            or type(max_accepted) is not int or not 1<=max_accepted<=4
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0<sense_timeout_s<=60. or reporting_build is None
            or type(retain_existing_keeper_group) is not bool or type(retained_native_track_material) is not bool
            or type(allow_signed_native_keeper) is not bool or type(request_scope) is not str
            or request_scope not in ('components','local_findings','terminal_caps')
            or type(source_diagonal_quantum_nm) is not int or source_diagonal_quantum_nm not in (0,1)
            or type(envelope_margin_nm) is not int or not 1<=envelope_margin_nm<=100000):
        raise ValueError('explicit_bounded_source_hash_native_keeper_stage_context_required')
    if type(min_width_mm) not in (int,float) or not math.isfinite(min_width_mm) or not 0<min_width_mm<=100.:
        raise ValueError('literal_positive_finite_contour_inventory_width_required')
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_saved_source_and_fresh_private_keeper_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    include_terminal_caps=request_scope=='terminal_caps'
    def inspect(board):return audit.audit_board(board,timeout_s=10.,include_terminal_caps=include_terminal_caps,
        min_width_mm=min_width_mm)
    outdir.mkdir(parents=True)
    r=dict(schema=1,scope='bounded_automatic_source_retained_keeper_extension',source=str(source),
        source_sha256=expected_source_sha256,code_identity=epoch,errors=[],attempts=[],contours=[],
        candidate=str(source),candidate_sha256=expected_source_sha256,changed=False,
        complete=False,ok=False,all_power_contours_clean=False,source_selected=False,
        routing_admitted=False,fab_ready=False,release_authority=False,new_capacity_credited=False,
        current_authority_changed=False,max_requests=max_requests,max_accepted=max_accepted,
        retain_existing_keeper_group=retain_existing_keeper_group,retained_native_track_material=retained_native_track_material,
        allow_signed_native_keeper=allow_signed_native_keeper,request_scope=request_scope,
        source_diagonal_quantum_nm=source_diagonal_quantum_nm,terminal_caps_included=include_terminal_caps,
        envelope_margin_nm=envelope_margin_nm,max_screen_requests=max_screen_requests)
    if min_width_mm!=1.:r['contour_inventory_min_width_mm']=min_width_mm
    def grade(path,label):
        output=outdir/(label+'.drc.json')
        proof=native.run(path,output,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_native_keeper_stage_inventory_required')
        return json.loads(output.read_text())
    try:
        source_board=pcbnew.LoadBoard(str(source));before=grade(source,'source')
        if before['unconnected_items']:raise ValueError('native_open_closure_precedes_optional_contour_stage')
        faults={admission._canonical_identity(v) for v in before['violations']}
        portfolio=(audit.component_requests(source_board,timeout_s=10.,max_component_tracks=64,min_width_mm=min_width_mm)
            if request_scope=='components' else audit.finding_requests(source_board,timeout_s=10.,
                include_terminal_caps=include_terminal_caps,min_width_mm=min_width_mm))
        if not portfolio['complete']:raise ValueError('complete_actual_source_contour_portfolio_required')
        if include_terminal_caps:
            portfolio['requests']=[q for q in portfolio['requests'] if 'wide_exposed_terminal_cap' in q.get('finding_types',[])]
        r['source_request_count']=len(portfolio['requests'])
        r['before']=inspect(source_board)
        if not r['before']['complete']:raise ValueError('complete_source_power_contour_audit_required')
        r['request_screening']=screen_requests(source_board,portfolio['requests'],max_requests=max_requests,
            max_screen_requests=max_screen_requests,allow_signed_native_keeper=allow_signed_native_keeper)
        current=source
        for selected in r['request_screening']['selected']:
            if len(r['contours'])>=max_accepted:break
            index=selected['source_request_index'];request=selected['request']
            row=dict(net=request['net'],layer_id=request['layer_id'],source_request_index=index,accepted=False)
            r['attempts'].append(row)
            try:
                board=pcbnew.LoadBoard(str(current));regional_source=pcbnew.LoadBoard(str(current))
                ids=[q['uuid'] for q in request['source_tracks']]
                live={force._uid(t):t for t in board.GetTracks()}
                if not ids or not set(ids)<=live.keys():raise ValueError('current_native_contour_request_missing')
                import cec_native_contour_regions as signed
                names=(contour.ZONE_NAME,signed.ZONE_NAME) if allow_signed_native_keeper else (contour.ZONE_NAME,)
                zones=[force._uid(z) for z in board.Zones() if z.GetZoneName() in names]
                plan=owner.plan(board,ids,required_width_nm=min(live[u].GetWidth() for u in ids),
                    allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()],
                    allow_grouped_track_uuids=[u for u in ids if live[u].GetParentGroup() is not None],
                    allow_locked_zone_uuids=zones,allow_grouped_zone_uuids=zones,timeout_s=10.,
                    retain_existing_keeper_lock=True,retain_existing_keeper_group=retain_existing_keeper_group,
                    retained_native_track_material=retained_native_track_material,
                    allow_signed_native_keeper=allow_signed_native_keeper,
                    source_diagonal_quantum_nm=source_diagonal_quantum_nm,envelope_margin_nm=envelope_margin_nm)
                uid=plan['replacement_source_zone']['configuration']['uuid']
                if uid in {q['materialized']['zone_uuid'] for q in r['contours']}:
                    raise ValueError('one_original_keeper_may_be_extended_only_once_per_transaction')
                emitted=contour.materialize(board,plan,allow_locked_track_uuids=ids,
                    allow_grouped_track_uuids=ids,allow_locked_zone_uuids=[uid],allow_grouped_zone_uuids=[uid])
                contour.fill(board,plan,uid,regional_source=regional_source,timeout_s=10.)
                additive._ground_refill(board)
                candidate=force._copy_family(current,outdir/('UNADMITTED-keeper-extension-'+str(index)))
                field._save_field_snapshot(board,candidate);saved=pcbnew.LoadBoard(str(candidate))
                after=inspect(saved)
                prior=inspect(regional_source)
                if not after['complete'] or not prior['complete'] or after['finding_count']>=prior['finding_count']:
                    raise ValueError('no_strict_actual_native_contour_improvement')
                result=grade(candidate,'candidate-'+str(index))
                delta={admission._canonical_identity(v) for v in result['violations']}-faults
                row['new_native_fault_ids']=sorted(delta)
                if result['unconnected_items'] or delta:raise ValueError('new_native_keeper_extension_DRC_or_open')
                record=dict(plan=plan,materialized=emitted)
                proof=owner.receive(source,candidate,r['contours']+[record],board_hint=board_hint,
                    sense_timeout_s=sense_timeout_s)
                row['independent_whole_original_source_receiving']=proof
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('original_source_keeper_extension_not_received:'+str(proof['errors']))
                r['contours'].append(record);current=candidate
                row.update(accepted=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),
                    findings_before=prior['finding_count'],findings_after=after['finding_count'])
                r['independent_final_original_source_receiving']=proof
            except (ValueError,KeyError,TypeError,OSError,RuntimeError,contour.Refused) as exc:
                row['refusal']=type(exc).__name__+':'+str(exc)
            print(json.dumps({k:row.get(k) for k in ('net','layer_id','accepted','refusal','findings_after')}),flush=True)
        r.update(candidate=str(current),candidate_sha256=force._hash(current),changed=bool(r['contours']),
            after=inspect(pcbnew.LoadBoard(str(current))))
        if not r['after']['complete']:raise ValueError('complete_final_native_contour_inventory_required')
        r.update(ok=True,complete=True,all_power_contours_clean=r['after']['finding_count']==0,
            unattempted_source_requests=max(0,r['source_request_count']-len(r['attempts'])))
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,contour.Refused) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    r['source_family_and_code_unchanged']=stable
    if not stable:r.update(ok=False,complete=False);r['errors'].append('keeper_stage_source_or_code_changed')
    force._write(outdir/'stage.json',r)
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--max-requests',type=int,default=8);p.add_argument('--max-accepted',type=int,default=2)
    p.add_argument('--max-screen-requests',type=int,default=128,
        help='Native-contact prescreen bound (1..256); ineligible requests do not spend construction leases')
    p.add_argument('--sense-timeout-s',type=float,default=10.)
    p.add_argument('--retain-existing-keeper-group',action='store_true')
    p.add_argument('--retained-native-track-material',action='store_true')
    p.add_argument('--allow-signed-native-keeper',action='store_true')
    p.add_argument('--request-scope',choices=('components','local_findings','terminal_caps'),default='components')
    p.add_argument('--source-diagonal-quantum-nm',type=int,choices=(0,1),default=0)
    p.add_argument('--envelope-margin-nm',type=int,default=1000,
        help='Actual added construction copper, never a receiving or clearance tolerance (1..100000 nm)')
    p.add_argument('--min-width-mm',type=float,default=1.,help='Contour inventory work floor only; no current-width or fabrication rule change')
    a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,max_requests=a.max_requests,max_accepted=a.max_accepted,
        sense_timeout_s=a.sense_timeout_s,retain_existing_keeper_group=a.retain_existing_keeper_group,
        retained_native_track_material=a.retained_native_track_material,
        allow_signed_native_keeper=a.allow_signed_native_keeper,request_scope=a.request_scope,
        source_diagonal_quantum_nm=a.source_diagonal_quantum_nm,envelope_margin_nm=a.envelope_margin_nm,
        min_width_mm=a.min_width_mm,max_screen_requests=a.max_screen_requests)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        accepted=len(r['contours']),before=r.get('before',{}).get('finding_count'),
        after=r.get('after',{}).get('finding_count'),errors=r['errors'])),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
