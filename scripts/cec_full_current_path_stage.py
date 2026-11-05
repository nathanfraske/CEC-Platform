"""Finite zero-open saved-source trials of full-current fixed-port reflow."""
import argparse,json
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_full_current_path_finish as owner
import cec_field_coupling as field
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_stage_admission as admission


def _context(board_hint,expected_source_sha256,reporting_build,allow_locked_source,max_trials):
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool or
            type(max_trials) is not int or not 1<=max_trials<=8 or type(expected_source_sha256) is not str or
            len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256) or reporting_build is None):
        raise ValueError('bounded_explicit_full_current_path_stage_required')


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=4,port_policy='tracks_only'):
    if type(port_policy) is not str or port_policy not in ('tracks_only','source_circular_barrels'):raise ValueError('explicit_full_current_path_port_policy_required')
    _context(board_hint,expected_source_sha256,reporting_build,allow_locked_source,max_trials)
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_full_current_path_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    result=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));report=outdir/(label+'.drc.json')
        proof=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
        result.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_full_current_path_native_inventory_required')
        return json.loads(report.read_text())
    try:
        b=pcbnew.LoadBoard(str(source));before=quality.analyze_board(b)
        result['before']=owner.discover(b,source,board_hint=board_hint,allow_locked_source=allow_locked_source,maximum_candidates=max_trials,port_policy=port_policy)
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_optional_full_current_path_refinement')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        for index,request in enumerate(result['before']['requests']):
            record=dict(request=request,accepted=False);result['attempts'].append(record)
            try:
                b=pcbnew.LoadBoard(str(source));proposal=owner.plan(b,source,board_hint=board_hint,
                    retired_track_uuids=request['retired_track_uuids'],points_nm=request['points_nm'],allow_locked_source=allow_locked_source,port_policy=port_policy)
                made=owner.materialize(b,source,proposal,board_hint=board_hint)
                child=force._copy_family(source,outdir/('UNADMITTED-current-path-'+str(index)));field._save_field_snapshot(b,child)
                proof=owner.receive(source,child,proposal,board_hint=board_hint);record['independent_saved_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('saved_full_current_path_receiving_refused:'+str(proof['errors']))
                after=quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if (after['issue_count']>before['issue_count'] or after['non_octilinear_count']>before['non_octilinear_count'] or
                        not after['power_contours']['complete'] or not before['power_contours']['complete'] or
                        after['power_contours']['finding_count']>before['power_contours']['finding_count']):
                    raise ValueError('full_current_path_whole_native_craft_or_contour_regression')
                report=observe(child,'candidate-'+str(index))
                record['new_native_fault_ids']=sorted({admission._canonical_identity(v) for v in report['violations']}-faults)
                if report['unconnected_items'] or record['new_native_fault_ids']:raise ValueError('full_current_path_new_native_fault_or_open')
                record.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                result.update(changed=True,candidate=str(child),candidate_sha256=record['candidate_sha256'],
                    records=[dict(plan=proposal,materialized=made)],independent_saved_receiving=proof,
                    saved_trace_length_mm=proof['saved_trace_length_mm'],native_strokes_before_after=proof['native_strokes_before_after'])
                break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:record['refusal']=type(exc).__name__+':'+str(exc)
        result.update(ok=True,complete=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    result['source_family_and_code_unchanged']=stable
    if not stable:result.update(ok=False,complete=False);result['errors'].append('full_current_path_source_family_or_code_changed')
    force._write(outdir/'stage.json',result);return result


def run_campaign(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=4,max_passes=4,port_policy='tracks_only'):
    """Finite native improvement loop, never a global-cleanliness certificate.

    Every pass rebuilds its own source state. A repeated hash, zero change or
    failure stops the loop; failure cannot be relabelled as acceptance.
    Downstream receiving still independently replays each phase and the
    ORIGINAL parent. No typed/current deadline or source rule is widened.
    """
    if type(max_passes) is not int or not 1<=max_passes<=4:raise ValueError('one_to_four_native_current_path_passes_required')
    if type(port_policy) is not str or port_policy not in ('tracks_only','source_circular_barrels'):raise ValueError('explicit_full_current_path_port_policy_required')
    _context(board_hint,expected_source_sha256,reporting_build,allow_locked_source,max_trials)
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('literal_source_and_fresh_current_path_campaign_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    cursor=source;digest=expected_source_sha256;seen={digest};phases=[];passes=[];reason='pass_limit';gains=[]
    for index in range(max_passes):
        dest=outdir/('pass-'+str(index))
        stage=run(cursor,dest,board_hint=board_hint,expected_source_sha256=digest,reporting_build=reporting_build,
            allow_locked_source=allow_locked_source,max_trials=max_trials,port_policy=port_policy)
        path=dest/'stage.json';passes.append(dict(path=str(path),sha256=force._hash(path),ok=stage['ok'],complete=stage['complete'],changed=stage['changed']))
        if not stage['ok'] or not stage['complete']:reason='stage_failure';break
        if not stage['changed']:reason='no_accepted_finite_portfolio_offer';break
        if stage['candidate_sha256'] in seen:reason='repeated_source_hash_refused';break
        seen.add(stage['candidate_sha256']);phases.append(dict(kind='full_current_path',path=str(path),sha256=force._hash(path)))
        gains.append(stage['saved_trace_length_mm'])
        cursor=Path(stage['candidate']);digest=stage['candidate_sha256']
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    success=stable and reason not in ('stage_failure','repeated_source_hash_refused')
    r=dict(ok=success,complete=success,errors=[] if success else [reason if stable else 'source_family_or_code_changed'],source=str(source),
        source_sha256=expected_source_sha256,candidate=str(cursor),candidate_sha256=digest,changed=bool(phases),code_identity=epoch,
        source_family_and_code_unchanged=stable,phase_receipts=phases,passes=passes,stop_reason=reason,
        saved_trace_length_mm=sum(gains),
        original_parent_receiving_still_required=True,whole_board_cleanliness_or_no_path_proof=False,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    force._write(outdir/'campaign.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=4)
    p.add_argument('--max-passes',type=int,help='Finite improvement campaign; one to four independently typed passes')
    p.add_argument('--port-policy',choices=['tracks_only','source_circular_barrels'],default='tracks_only');a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    operation=run if a.max_passes is None else run_campaign
    options={} if a.max_passes is None else dict(max_passes=a.max_passes)
    r=operation(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials,port_policy=a.port_policy,**options)
    print(json.dumps(dict(receipt=str(a.out/('stage.json' if a.max_passes is None else 'campaign.json')),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        saved_trace_length_mm=r.get('saved_trace_length_mm'),native_strokes_before_after=r.get('native_strokes_before_after'),
        candidate=r['candidate'],candidate_sha256=r['candidate_sha256'],errors=r['errors'])),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
