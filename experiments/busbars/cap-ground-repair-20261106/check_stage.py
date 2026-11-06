"""Independent saved checks; each process is externally bounded to 10s."""
import json
import argparse
from pathlib import Path
import sys
import time
from construct import ROOT,WORK,SOURCE,SHA,VIA,PAD,HINT,force,_native
import cec_field_coupling as field

TABLE=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table'
BUILD=Path('/home/codex/.cache/cec/native-drc-10.0.5')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage');parser.add_argument('--revision',default='')
    args=parser.parse_args();name=args.stage
    assert len(args.revision)<=48 and all(c.isalnum()or c in '-_'for c in args.revision)
    out=WORK/('checks-'+args.revision)if args.revision else WORK
    out.mkdir(exist_ok=True)
    start=time.monotonic();p,_=_native()
    record=json.loads((WORK/'construction.json').read_text());candidate=Path(record['candidate'])
    assert not (out/(name+'.json')).exists(),'fresh_stage_output_required'
    def identity():
        return dict(source=force._hash(SOURCE),candidate=force._hash(candidate),
            source_sidecars=force._sidecars(SOURCE),candidate_sidecars=force._sidecars(candidate),
            code_identity=force._code_identity())
    epoch=identity()
    assert epoch['source']==SHA and epoch['candidate']==record['candidate_sha256']
    if name=='source-plan':
        import cec_source_cap_ground_via_repair as repair
        proof=repair.plan(SOURCE,PAD,VIA,record['target_at_nm'],board_hint=HINT,
            allow_locked_via_uuid=VIA,timeout_s=9.)
        result=dict(ok=True,proof=proof)
    elif name=='barrel':
        import cec_source_cap_ground_via_repair as repair
        planned=json.loads((out/'source-plan.json').read_text())
        assert planned['identity']==epoch and planned['ok']
        # Re-derive the Source in this receiver; no caller proof skips checks.
        result=repair.receive(SOURCE,candidate,planned['result']['proof'],board_hint=HINT,timeout_s=9.)
    elif name=='ground':
        import cec_ground_return_preservation as returns
        result=returns.receive(p.LoadBoard(str(SOURCE)),p.LoadBoard(str(candidate)),timeout_s=8.5)
    elif name=='current':
        import cec_current_debt as current
        result=current.receive(SOURCE,candidate,board_hint=HINT)
    elif name=='craft':
        import cec_route_quality as craft
        a,z=[craft.analyze_board(p.LoadBoard(str(path)))for path in(SOURCE,candidate)]
        result=dict(ok=z['issue_count']<=a['issue_count']and z['non_octilinear_count']<=a['non_octilinear_count'],
            before_after=[a['issue_count'],z['issue_count']],
            non_octilinear_before_after=[a['non_octilinear_count'],z['non_octilinear_count']])
    elif name=='pairs':
        from cec_pipeline import pairs
        result=pairs.receive(SOURCE,candidate,timeout_s=8.)
    elif name.startswith('drc-'):
        import cec_native_drc_runner as drc
        path=SOURCE if name=='drc-source'else candidate;target=out/(name+'-native.json')
        result=drc.run(path,target,reporting_build=BUILD,timeout_s=8.5,footprint_table=TABLE)
        if result.get('ok')and result.get('complete'):
            data=json.loads(target.read_text())
            counts=dict(errors=sum(v.get('severity')=='error'for v in data['violations']),
                warnings=sum(v.get('severity')=='warning'for v in data['violations']),opens=len(data['unconnected_items']))
            result=dict(ok=counts['errors']==counts['opens']==0,counts=counts,producer=result)
    elif name.startswith('field-'):
        import cec_additive_route_receiving as additive
        path=SOURCE if name=='field-source'else candidate;b=p.LoadBoard(str(path))
        before=field._field_snapshot_inventory(b)
        if path==candidate:
            additive._ground_refill(b)
            assert field._field_snapshot_inventory(b)==before,'saved_fill_not_exact'
        report=field.field_coupling_summary(str(path),board=b,board_hint=HINT,
            _work=field._ProposalWork(start+9.,16384,1000000,1000000,16384))
        result=dict(ok=True,report=report)
    else:raise ValueError('unknown_independent_stage')
    assert identity()==epoch,'source_or_code_epoch_changed'
    report=dict(stage=name,identity=epoch,result=result,ok=result.get('ok')is True,
        elapsed_s=time.monotonic()-start,release_authority=False)
    (out/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(stage=name,ok=report['ok'],elapsed_s=report['elapsed_s'],
        counts=result.get('counts'),errors=result.get('errors'),before_after=result.get('before_after'))))


if __name__=='__main__':main()
