"""Private source-bound small-cell construction; no release/admission authority."""
import json,sys,uuid
from pathlib import Path
from cec_pipeline import drafts,repack,geometry
from cec_pipeline.native import _native

ROOT=Path('/home/codex/src/CEC-Platform');WORK=ROOT/'experiments/repack/atx-small-cell-20261105'
overlay=json.loads((ROOT/('docs/evidence/20261105-bottom-compaction/5v-small-cell-'+sys.argv[1].split('-')[-1]+'-overlay.json')).read_text())
label=sys.argv[1];folder=WORK/label
if not folder.exists():
 p=json.loads((ROOT/'docs/evidence/20261105-bottom-compaction/inward-v7-placement.json').read_text())
 p['carrier']=overlay['carrier'];p['cover']=overlay['cover']
 plan=WORK/(label+'-placement.json');repack.inspection.write_json(plan,p)
 request=dict(schema=5,placement=dict(path=str(plan),sha256=repack.inspection.sha(plan)),board_hints=dict(carrier='atx-24pin-rev3',cover='hub-standard-rev2'),redraws=overlay['redraws'],retired_tracks=overlay['retired_tracks'],via_moves=overlay['via_moves'],via_copies=overlay['via_copies'],zone_redraws=dict(carrier=[],cover=[]),flatbars=dict(carrier=[],cover=[]))
 for e in request['redraws']['carrier']:geometry.path(e['points_nm'],minimum_phase_nm=20000)
 repack.inspection.write_json(WORK/(label+'-request.json'),request)
 print(json.dumps(drafts.stage(request,folder,refill=True)))
else:print('existing private stage: '+str(folder))
