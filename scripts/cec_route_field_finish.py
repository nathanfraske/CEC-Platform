"""Bounded field-coupling finishing; coordinator regrading owns admission.

Only structurally closed routes are eligible. Work occurs in a private board
family and an owned, deadline-limited process group. No missing report, timeout,
or partial worker output can replace the selected route.
"""
import json
import math
import sys
from pathlib import Path


def eligible(result):
    result=result or {}
    field=result.get('field_coupling') or {}
    count=field.get('blocking_count')
    return (result.get('drc')==0 and result.get('unconnected')==0
            and field.get('ok') is False and type(count) is int and count>0)


def apply(result, directory, *, timeout_s=90., max_rounds=1):
    import cec_certificate_repair as repair
    import cec_full_pipeline as pipeline
    import cec_operation_budget as budget
    if not eligible(result):
        return dict(changed=False,skipped='no_closed_route_field_defects',release_authority=False)
    if not math.isfinite(timeout_s) or not 1 <= timeout_s <= 120:
        raise ValueError('field finishing timeout must be between 1 and 120 seconds')
    if type(max_rounds) is not int or not 1 <= max_rounds <= 2:
        raise ValueError('field finishing allows one or two rounds')
    source=Path(result['routed']).resolve()
    work=Path(directory).resolve()
    work.mkdir(parents=True,exist_ok=False)
    original=pipeline.sha256_file(source)
    staged,output,report=work/'source.kicad_pcb',work/'candidate.kicad_pcb',work/'repair.json'
    repair._copy_board_family(str(source),str(staged))
    operation=budget.run([sys.executable,str(Path(__file__).with_name('cec_field_coupling_repair.py')),
        str(staged),str(output),'--max-rounds',str(max_rounds),'--json',str(report)],
        work/'operation',operation='route_field_finish',timeout=timeout_s)
    if pipeline.sha256_file(source)!=original:
        raise RuntimeError('field finisher input changed during isolated work')
    payload=json.loads(report.read_text())
    before=result['field_coupling']['blocking_count']
    field=payload.get('final_field') or {}
    after=field.get('blocking_count')
    score=payload.get('final_score') or {}
    changed=(type(after) is int and 0 <= after < before
             and score.get('drc')==0 and score.get('unconnected')==0
             and output.is_file())
    if changed:
        repair._copy_board_family(str(output),str(source))
    return dict(changed=changed,before=before,after=after,operation=operation,
        report=str(report),source_sha256=original,output_sha256=pipeline.sha256_file(source),
        release_authority=False,requires_independent_admission=True)
