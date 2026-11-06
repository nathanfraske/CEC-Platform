"""Independent saved-board checks, one externally bounded worker per stage."""
import json
from pathlib import Path
import sys
import time
from repair_port import ROOT,WORK,SOURCE,SOURCE_SHA,VIA,HINT,barrel,force,_native
import cec_field_coupling as field
import cec_fr as fr

OUT=WORK/'port-repaired-v1'
TABLE=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table'
BUILD=Path('/home/codex/.cache/cec/native-drc-10.0.5')


def main():
    name=sys.argv[1];started=time.monotonic();p,_=_native()
    record=json.loads((OUT/'construction.json').read_text())
    candidate=Path(record['candidate'])
    def identity():
        return dict(source=force._hash(SOURCE),candidate=force._hash(candidate),
            source_sidecars=force._sidecars(SOURCE),candidate_sidecars=force._sidecars(candidate),
            code_identity=force._code_identity())
    epoch=identity()
    assert epoch['source']==SOURCE_SHA and epoch['candidate']==record['candidate_sha256']
    if name=='barrel':
        result=barrel.receive(SOURCE,candidate,via_uuid=VIA,board_hint=HINT,
            allow_owned_locked=True,repair_source_pad_overlap=True,timeout_s=9.)
    elif name=='ground':
        import cec_ground_return_preservation as returns
        result=returns.receive(p.LoadBoard(str(SOURCE)),p.LoadBoard(str(candidate)),timeout_s=8.5)
    elif name=='current':
        import cec_current_debt as current
        result=current.receive(SOURCE,candidate,board_hint=HINT)
    elif name=='craft':
        import cec_route_quality as craft
        a,b=[craft.analyze_board(p.LoadBoard(str(path)))for path in(SOURCE,candidate)]
        result=dict(ok=b['issue_count']<=a['issue_count']and b['non_octilinear_count']<=a['non_octilinear_count'],
            before_after=[a['issue_count'],b['issue_count']],
            non_octilinear_before_after=[a['non_octilinear_count'],b['non_octilinear_count']])
    elif name=='pairs':
        from cec_pipeline import pairs
        result=pairs.receive(SOURCE,candidate,timeout_s=8.)
    elif name.startswith('drc-'):
        import cec_native_drc_runner as drc
        path=SOURCE if name=='drc-source'else candidate
        target=OUT/(name+'-native.json')
        result=drc.run(path,target,reporting_build=BUILD,timeout_s=8.5,footprint_table=TABLE)
        if result.get('ok')and result.get('complete'):
            data=json.loads(target.read_text())
            counts=dict(errors=sum(v.get('severity')=='error'for v in data['violations']),
                warnings=sum(v.get('severity')=='warning'for v in data['violations']),opens=len(data['unconnected_items']))
            result=dict(ok=counts['errors']==0 and counts['opens']==0,counts=counts,producer=result)
    elif name.startswith('field-'):
        import cec_additive_route_receiving as additive
        path=SOURCE if name=='field-source'else candidate
        b=p.LoadBoard(str(path));before=field._field_snapshot_inventory(b)
        if path==candidate:
            additive._ground_refill(b)
            assert field._field_snapshot_inventory(b)==before,'saved_fill_not_exact'
        report=field.field_coupling_summary(str(path),board=b,board_hint=HINT,
            _work=field._ProposalWork(started+9.,16384,1000000,1000000,16384))
        result=dict(ok=True,report=report)
    elif name.startswith('sense-'):
        import cec_force_sense_evidence as sense
        path=SOURCE if name=='sense-source'else candidate
        report=sense.replay(path,board_hint=HINT,timeout_s=8.8)
        result=dict(ok=report.get('complete')is True,report=report)
    else:raise ValueError('unknown independent stage')
    assert identity()==epoch,'source_or_code_epoch_changed'
    report=dict(stage=name,identity=epoch,result=result,ok=result.get('ok')is True,
        elapsed_s=time.monotonic()-started,release_authority=False)
    (OUT/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(stage=name,ok=report['ok'],elapsed_s=report['elapsed_s'],
        counts=result.get('counts'),errors=result.get('errors'),before_after=result.get('before_after'))))


if __name__=='__main__':main()
