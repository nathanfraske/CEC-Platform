"""Finite generic trials of source-owned joint track/keeper finishing."""
import argparse,json,time
from pathlib import Path
import pcbnew
import cec_current_keeper_corner as owner
import cec_full_current_corner_finish as corners
import cec_force_current as force
import cec_field_coupling as field
import cec_force_sense_evidence as sense
import cec_native_drc_runner as native
import cec_stage_admission as admission


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=4):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(max_trials) is not int or not 1<=max_trials<=8 or type(allow_locked_source) is not bool
            or reporting_build is None):raise ValueError('bounded_source_current_keeper_stage_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_current_keeper_stage_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,records=[],attempts=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        report=outdir/(label+'.drc.json');made=native.run(path,report,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=made
        if not made['ok'] or not made['complete'] or made['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_current_keeper_native_inventory_required')
        return json.loads(report.read_text())
    try:
        parent=pcbnew.LoadBoard(str(source))
        found=corners.discover(parent,source,board_hint=board_hint,allow_locked_source=allow_locked_source)
        r['discovery']=found;baseline=None;deadline=time.monotonic()+180.
        for index,entry in enumerate(found['composed_power_contour_frontier'][:max_trials]):
            if time.monotonic()>=deadline:raise ValueError('bounded_current_keeper_stage_deadline')
            row=dict(request=entry['request'],accepted=False);r['attempts'].append(row)
            try:
                q=owner.plan(source,board_hint=board_hint,request=entry['request'],allow_locked_source=allow_locked_source)
                b,made=owner.construct(q);child=force._copy_family(source,outdir/('UNADMITTED-current-keeper-'+str(index)))
                field._save_field_snapshot(b,child);row.update(candidate=str(child),candidate_sha256=force._hash(child))
                proof=owner.receive(source,child,q,board_hint=board_hint);row['independent_saved_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('original_source_keeper_receiving_refused:'+str(proof['errors']))
                if baseline is None:
                    baseline=observe(source,'source')
                    if baseline['unconnected_items']:raise ValueError('zero_opens_precede_current_keeper_finishing')
                after=observe(child,'candidate-'+str(index))
                added=sorted({admission._canonical_identity(v) for v in after['violations']}-
                    {admission._canonical_identity(v) for v in baseline['violations']})
                row['new_native_fault_ids']=added;row['opens']=len(after['unconnected_items'])
                if added or row['opens']:raise ValueError('current_keeper_new_native_fault_or_open')
                first,last=[sense.replay(path,board_hint=board_hint,timeout_s=40.) for path in (source,child)]
                nets=[q['request']['net'],'GND']
                cuts=sense.compare_contour_preservation(first,last,modified_nets=nets,
                    native_copper_transforms=sense.native_copper_transform_inventory(parent,b,modified_nets=nets))
                row['whole_original_clipped_preservation']=cuts
                if not cuts['same_evidence'] or not cuts['comparison_complete']:
                    raise ValueError('whole_original_current_keeper_clipped_evidence_regressed')
                row['accepted']=True
                r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    records=[dict(plan=q,materialized=made)],independent_saved_receiving=proof,
                    saved_trace_length_mm=proof['saved_trace_length_mm'],chamfered=proof['chamfered'])
                break
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
            print(json.dumps(dict(attempt=index,accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
        r.update(ok=True,complete=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('current_keeper_source_family_or_code_changed')
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    r['finite_portfolio_not_an_impossibility_proof']=True;force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=4)
    a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','chamfered','saved_trace_length_mm','candidate','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
