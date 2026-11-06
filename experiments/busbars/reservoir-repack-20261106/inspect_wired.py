"""Fresh source role replay for the explicit native placement study only."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_wired_aggregate_capacitor as wired


def main():
    start=time.monotonic();p,_=_native();work=Path(__file__).resolve().parent
    study=json.loads((work/'geometry-fixed-ground-pivot.json').read_text())
    source=Path(study['source']);assert wired.cap.force._hash(source)==study['source_sha256']
    board=p.LoadBoard(str(source))
    poses={ref:[values[0]/1e6,values[1]/1e6,values[2]]for ref,values in study['proposed_poses'].items()}
    proof=wired.inspect(board,board.FindFootprintByReference('C55'),poses,'atx-24pin-rev3',
        allow_linear_power_stage_reconstruction=True,timeout_s=9.)
    result=dict(complete=True,elapsed_s=time.monotonic()-start,identity=proof,
        final_routing_or_physical_acceptance=False,board_saved=False)
    (work/'wired-source-identity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(complete=True,elapsed_s=result['elapsed_s'],local_owner=proof['source_locality_owner'],
        source_contact_counts={k:len(v)for k,v in proof['actual_source_contacts'].items()},
        routing_admitted=proof['routing_admitted'])))


if __name__=='__main__':main()
