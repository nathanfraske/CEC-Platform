"""Fresh native DRC on the unchanged accepted prefix; not a repack receipt."""
import json
import argparse
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_native_drc_runner as drc


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-name',default='incumbent')
    name=parser.parse_args().run_name
    assert name and len(name)<=64 and all(c.isalnum()or c in '-_'for c in name)
    start=time.monotonic();_native();work=Path(__file__).resolve().parent
    study=json.loads((work/'geometry-fixed-ground-pivot.json').read_text())
    source=Path(study['source']);assert force._hash(source)==study['source_sha256']
    before=force._family(source,'atx-24pin-rev3');epoch=force._code_identity()
    output=work/(name+'-native-drc.json')
    result=drc.run(source,output,reporting_build=Path('/home/codex/.cache/cec/native-drc-10.0.5'),
        timeout_s=8.5,footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
    assert result.get('ok')and result.get('complete'),result
    data=json.loads(output.read_text())
    counts=dict(errors=sum(r.get('severity')=='error'for r in data['violations']),
        warnings=sum(r.get('severity')=='warning'for r in data['violations']),opens=len(data['unconnected_items']))
    assert before==force._family(source,'atx-24pin-rev3')and epoch==force._code_identity()
    report=dict(source=str(source),source_sha256=study['source_sha256'],source_family=before,
        code_identity=epoch,native_DRC=counts,producer=result,source_unchanged=True,
        elapsed_s=time.monotonic()-start,repack_received=False,release_authority=False)
    (work/(name+'-check.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(counts=counts,elapsed_s=report['elapsed_s'],repack_received=False)))
    assert counts['errors']==counts['opens']==0


if __name__=='__main__':main()
