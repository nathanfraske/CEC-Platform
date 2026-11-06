"""Bounded explicit source-pad-bank construction plus independent checks."""
from pathlib import Path
import argparse
import json
from cec_pipeline.native import _native
from cec_pipeline import construction,power
import cec_force_current as force
import cec_suite_inspection as inspect
import cec_native_drc_runner as native
import cec_current_debt as current


def main(args):
    assert force._hash(args.source) == args.sha256 and not args.output.exists()
    pcb,quiet = _native(); board = pcb.LoadBoard(str(args.source))
    matches = [f for f in board.GetFootprints() if f.GetReference() == args.reference]
    assert len(matches) == 1
    op = dict(kind='bank_collector',pad_uuids=[force._uid(p) for p in matches[0].Pads()],
              support_track_uuids=args.support_uuid,layer=args.layer,chamfer_nm=250000)
    request = dict(operations=[op])
    target = force._copy_family(args.source,args.output/'carrier')
    inspect.write_json(args.output/'request.json',dict(source=str(args.source),
                       source_sha256=args.sha256,board_hint=args.board_hint,request=request))
    result = construction._construct(args.source,target,request,args.board_hint)
    inspect.write_json(args.output/'construction.json',result)
    received = power.receive(args.source,target,op,result['changes'][0],board_hint=args.board_hint)
    inspect.write_json(args.output/'received.json',received)
    print('geometry',received['ok'],received['complete'],received.get('errors'),flush=True)
    assert received['ok'] and received['complete']
    table = 'checkpoints/review-20261105-outline-compaction/boards/'+args.board_hint+'/library/fp-lib-table'
    r = native.run(target,args.output/'native-drc.json',timeout_s=10.,
                   reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',footprint_table=table)
    inspect.write_json(args.output/'native-drc.runner.json',r)
    assert r['ok'] and r['complete']
    raw = json.loads((args.output/'native-drc.json').read_text())
    print('native',dict(errors=sum(v['severity']=='error' for v in raw['violations']),
          opens=len(raw['unconnected_items'])),flush=True)
    r = current.receive(args.source,target,board_hint=args.board_hint)
    inspect.write_json(args.output/'current.json',r)
    print('current',{k:v for k,v in r.items() if k not in ('before_result','after_result')},flush=True)
    print('candidate',str(target),force._hash(target))
    assert force._hash(args.source) == args.sha256


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--reference',required=True)
    parser.add_argument('--layer',required=True)
    parser.add_argument('--board-hint',required=True)
    parser.add_argument('--support-uuid',action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
