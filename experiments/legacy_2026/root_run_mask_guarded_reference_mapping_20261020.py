"""Construct one bounded original-owner mapping after native-mask preflight."""
import argparse
import json
from pathlib import Path
import cec_swig_guard; cec_swig_guard.pin()
import wx; quiet = wx.LogNull()
import cec_dense_reference_mapping as mapping
import cec_reference_mask_obstacles as masks
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_stage_admission as admission

p = argparse.ArgumentParser(description=__doc__)
for key in ('source', 'grade', 'out', 'reporting-build'):
    p.add_argument('--' + key, type=Path, required=True)
p.add_argument('--hint', required=True)
p.add_argument('--maximum-components', type=int, default=6)
p.add_argument('--max-seeds', type=int, default=16)
a = p.parse_args()
mapping.require(not a.out.exists() and 1 <= a.max_seeds <= 32,
    'fresh_finite_mask_guarded_mapping_work_required')
failed, proposal, guarded = [], None, None
for index in range(a.max_seeds):
    try:
        trial = mapping.plan(a.source, grade=a.grade, board_hint=a.hint,
            maximum_components=a.maximum_components, seed_index=index)
        proof = masks.observe(a.source, trial)
        mapping.require(proof['ok'] and proof['complete'], str(proof['errors']))
        proposal, guarded = trial, proof
        break
    except ValueError as exc:
        failed.append(dict(seed_index=index, reason=str(exc)))
mapping.require(proposal is not None, 'finite_mask_guarded_mapping_search_exhausted:' + str(failed))
board, manifest = mapping.construct(a.source, proposal)
child = force._copy_family(a.source, a.out/'UNADMITTED-reference-map')
field._save_field_snapshot(board, child)
proof = mapping.receive(a.source, child, proposal)
mapping.require(proof['ok'] and proof['complete'], str(proof['errors']))
# The original receiver reconstructs every child exactly; the mask guard is
# separately rebound rather than treating a successful plan as saved evidence.
saved_guard = masks.observe(a.source, proposal)
mapping.require(saved_guard == guarded, 'mask_preflight_changed_during_native_construction')
report = a.out/'native.json'
shadow = force._copy_family(child, a.out/'native-input')
produced = native.run(shadow, report, reporting_build=a.reporting_build, timeout_s=10.)
mapping.require(produced['ok'] and produced['complete']
    and not produced['native_inventory']['potentially_truncated'],
    'complete_mask_guarded_mapping_native_drc_required')
after = json.loads(report.read_text())
before = json.loads(Path(proposal['binding']['native_report']).read_text())
known = {admission._canonical_identity(v) for v in before['violations']}
fresh = [v for v in after['violations'] if admission._canonical_identity(v) not in known]
ok = not fresh and not after['unconnected_items']
result = dict(ok=ok, complete=True, changed=True, source=str(a.source.resolve()),
    source_sha256=force._hash(a.source), candidate=str(child), candidate_sha256=force._hash(child),
    code_identity=force._code_identity(), proposal=proposal, manifest=manifest,
    independent_annotation_receiving=proof, actual_native_mask_obstacle_preflight=saved_guard,
    native_producer=produced, new_native_faults=fresh, opens=len(after['unconnected_items']),
    source_raw_native_count=len(before['violations']), candidate_raw_native_count=len(after['violations']),
    prior_seed_refusals=failed, source_seed_domain_exhaustive=False,
    errors=[] if ok else ['native_reference_mapping_refused'],
    records=[dict(plan=dict(proposal=proposal), materialized=manifest)],
    source_family_and_code_unchanged=proof['source_candidate_families_and_code_unchanged'],
    input_sha256={str(q.resolve()): force._hash(q) for q in
        [Path(__file__), Path(mapping.__file__), Path(masks.__file__), a.grade,
         Path(proposal['binding']['native_report'])]},
    routing_admitted=False, fab_ready=False, release_authority=False)
force._write(a.out/'stage.json', result)
print(json.dumps(dict(stage=str(a.out/'stage.json'), ok=ok, mode=proposal['mode'],
    references=[r['reference'] for r in proposal['records']],
    raw_native=[result['source_raw_native_count'], result['candidate_raw_native_count']],
    native_mask_artwork_count=len(saved_guard['native_mask_artwork']), new_native=fresh)), flush=True)
