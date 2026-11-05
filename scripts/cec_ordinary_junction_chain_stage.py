"""Finite source-owned ordinary-junction cleanup; no release admission."""
import argparse,json,time
from pathlib import Path
import pcbnew
import cec_ordinary_junction_chain_finish as owner
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_stage_admission as admission


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,max_trials=16):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(allow_locked_source) is not bool or type(max_trials) is not int or not 1<=max_trials<=16
            or reporting_build is None):raise ValueError('bounded_source_junction_stage_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_junction_source_and_fresh_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(ok=False,complete=False,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,records=[],attempts=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));report=outdir/(label+'.drc.json')
        proof=native.run(shadow,report,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_junction_native_inventory_required')
        return json.loads(report.read_text())
    try:
        found=owner.discover(pcbnew.LoadBoard(str(source)),source,board_hint=board_hint,allow_locked_source=allow_locked_source)
        r['discovery']=found;baseline=None;deadline=time.monotonic()+180.
        for index,request in enumerate(found['requests'][:max_trials]):
            if time.monotonic()>=deadline:raise ValueError('bounded_source_junction_stage_deadline')
            row=dict(request=request,accepted=False);r['attempts'].append(row)
            try:
                q=owner.plan(source,board_hint=board_hint,request=request,allow_locked_source=allow_locked_source)
                b,made=owner.construct(q);child=force._copy_family(source,outdir/('UNADMITTED-junction-'+str(index)))
                field._save_field_snapshot(b,child);proof=owner.receive(source,child,q,board_hint=board_hint)
                row.update(candidate=str(child),candidate_sha256=force._hash(child),independent_saved_receiving=proof)
                if not proof['ok'] or not proof['complete']:raise ValueError('saved_junction_receiving_refused:'+str(proof['errors']))
                if baseline is None:
                    baseline=observe(source,'source')
                    if baseline['unconnected_items']:raise ValueError('zero_opens_precede_junction_finishing')
                after=observe(child,'candidate-'+str(index))
                row['new_native_fault_ids']=sorted({admission._canonical_identity(v) for v in after['violations']}-
                    {admission._canonical_identity(v) for v in baseline['violations']})
                row['opens']=len(after['unconnected_items'])
                if row['opens'] or row['new_native_fault_ids']:raise ValueError('new_source_junction_native_fault_or_open')
                row['accepted']=True
                r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    records=[dict(plan=q,materialized=made)],independent_saved_receiving=proof,
                    saved_trace_length_mm=proof['saved_trace_length_mm'],mode=proof['mode'])
                break
            except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
            print(json.dumps(dict(attempt=index,accepted=row['accepted'],refusal=row.get('refusal'))),flush=True)
        r.update(ok=True,complete=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not stable:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        r['errors'].append('junction_stage_source_family_or_code_changed')
    r['source_family_and_code_unchanged']=stable;r['finite_portfolio_not_an_impossibility_proof']=True
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-trials',type=int,default=16);a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','mode','saved_trace_length_mm','candidate','candidate_sha256','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
