"""Finite native zero-open trials of typed source-current dead-end trimming."""
import argparse,json
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_full_current_terminal_trim as owner
import cec_field_coupling as field
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_stage_admission as admission


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=8):
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool or
            type(max_trials) is not int or not 1<=max_trials<=16 or type(expected_source_sha256) is not str or
            len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256) or reporting_build is None):
        raise ValueError('bounded_explicit_full_current_terminal_trim_stage_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_terminal_trim_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    result=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,attempts=[],records=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));report=outdir/(label+'.drc.json')
        proof=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
        result.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_terminal_trim_native_inventory_required')
        return json.loads(report.read_text())
    try:
        b=pcbnew.LoadBoard(str(source));before=quality.analyze_board(b)
        result['before']=owner.discover(b,source,board_hint=board_hint,allow_locked_source=allow_locked_source)
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_optional_terminal_trim')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        for index,request in enumerate(result['before']['requests'][:max_trials]):
            record=dict(request=request,accepted=False);result['attempts'].append(record)
            try:
                b=pcbnew.LoadBoard(str(source));proposal=owner.plan(b,source,request,board_hint=board_hint,allow_locked_source=allow_locked_source)
                made=owner.materialize(b,source,proposal,board_hint=board_hint)
                child=force._copy_family(source,outdir/('UNADMITTED-current-terminal-trim-'+str(index)));field._save_field_snapshot(b,child)
                proof=owner.receive(source,child,proposal,board_hint=board_hint);record['independent_saved_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('saved_terminal_trim_receiving_refused:'+str(proof['errors']))
                after=quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if (after['issue_count']>before['issue_count'] or after['non_octilinear_count']>before['non_octilinear_count'] or
                        not after['power_contours']['complete'] or not before['power_contours']['complete'] or
                        after['power_contours']['finding_count']>before['power_contours']['finding_count']):
                    raise ValueError('terminal_trim_whole_native_craft_or_contour_regression')
                report=observe(child,'candidate-'+str(index))
                record['new_native_fault_ids']=sorted({admission._canonical_identity(v) for v in report['violations']}-faults)
                if report['unconnected_items'] or record['new_native_fault_ids']:raise ValueError('terminal_trim_new_native_fault_or_open')
                record.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                result.update(changed=True,candidate=str(child),candidate_sha256=record['candidate_sha256'],
                    records=[dict(plan=proposal,materialized=made)],independent_saved_receiving=proof,
                    trimmed=1,saved_trace_length_mm=proof['saved_trace_length_mm'])
                break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:record['refusal']=type(exc).__name__+':'+str(exc)
        result.update(ok=True,complete=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    result['source_family_and_code_unchanged']=stable
    if not stable:result.update(ok=False,complete=False);result['errors'].append('terminal_trim_source_family_or_code_changed')
    force._write(outdir/'stage.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=8);a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        trimmed=r.get('trimmed'),saved_trace_length_mm=r.get('saved_trace_length_mm'),candidate=r['candidate'],
        candidate_sha256=r['candidate_sha256'],errors=r['errors'])),flush=True)


if __name__=='__main__':main()
