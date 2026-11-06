"""Collect independently saved receipts, bound to exact private bytes."""
import json,sys
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts')]
import cec_force_current as force
WORK=Path(__file__).parent
result=json.loads((WORK/'correction.json').read_text())
for key in('geometry','partition','drc','current'):
 p=WORK/(key+'-receipt.json');result[key]=dict(path=str(p),sha256=force._hash(p),result=json.loads(p.read_text()))
assert result['geometry']['result']['exact_saved_polygons_disjoint']
assert result['geometry']['result']['independent_source_gain_empty']
assert result['partition']['result']['preserved']
assert result['drc']['result']['candidate_errors']==result['drc']['result']['candidate_opens']==0
assert result['current']['result']['ok']and result['current']['result']['complete']
assert all(force._hash(Path(v['path']))==v['sha256']for v in result['authority'])
assert force._hash(Path(result['candidate']['path']))==result['candidate']['sha256']
result.update(status='PRIVATE_GUARD_FILL_CORRECTION_SCREENED_NOT_PRODUCTION_ADMITTED',native_refill_alone_sufficient=False,selected_refill_probe=dict(path=str(WORK/'probe.json'),sha256=force._hash(WORK/'probe.json')),source_outlines_current_tracks_typed_groups_rules_and_other_fill_AST_exact=True,merge_scope_only_guard_polygon_and_selected_zone_saved_fill=True,routing_admitted=False,current_qualified=False,thermal_qualified=False,release_authority=False,refill_warning='A raw native refill recreates integer-boundary penetration. Reconstruct this exact bound correction after any refill and rerun source/current/native/paired receiving; no refill exemption or threshold waiver.')
result['tools']=[dict(path=str(WORK/p),sha256=force._hash(WORK/p))for p in('probe.py','receive.py','finalize.py')]
out=ROOT/'docs/evidence/20261105-bar-land/c37-guard-fill-correction.json'
out.write_text(json.dumps(result,indent=2)+'\n')
(WORK/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(receipt=str(out),receipt_sha256=force._hash(out),candidate=result['candidate'])))
