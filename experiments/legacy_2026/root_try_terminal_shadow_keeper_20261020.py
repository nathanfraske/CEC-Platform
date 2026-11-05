"""Single explicit source-current terminal-shadow proposal; no blind waves."""
import argparse
import json
from pathlib import Path
import cec_swig_guard; cec_swig_guard.pin()
import wx; quiet = wx.LogNull()
import cec_dense_reference_mapping as intake
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_stage_admission as admission
import cec_terminal_shadow_keeper_finish as owner

p = argparse.ArgumentParser()
for key in ('source', 'grade', 'out', 'reporting-build'):
    p.add_argument('--'+key, type=Path, required=True)
p.add_argument('--hint', required=True); p.add_argument('--zone-uuid', required=True)
p.add_argument('--track-uuid', action='append', required=True)
p.add_argument('--allow-locked-source', action='store_true')
a = p.parse_args(); assert not a.out.exists(); a.out.mkdir(parents=True)
epoch = force._code_identity(); source_family = force._family(a.source, a.hint)
result = dict(ok=False, complete=False, changed=False, errors=[], records=[],
    source=str(a.source.resolve()), source_sha256=force._hash(a.source), code_identity=epoch,
    source_selected=False, routing_admitted=False, fab_ready=False, release_authority=False)
try:
    board, floors, before, binding = intake.source_context(a.source, a.grade, a.hint)
    assert not before['unconnected_items']
    q = owner.plan(a.source, board_hint=a.hint, zone_uuid=a.zone_uuid,
        track_uuids=a.track_uuid, allow_locked_source=a.allow_locked_source)
    candidate = owner.construct(a.source, q)
    child = force._copy_family(a.source, a.out/'UNADMITTED-terminal-shadow')
    field._save_field_snapshot(candidate, child)
    received = owner.receive_literal(a.source, child, q)
    result['independent_saved_receiving'] = received
    assert received['ok'] and received['complete'], received['errors']
    report = a.out/'native.json'; shadow = force._copy_family(child, a.out/'native-input')
    produced = native.run(shadow, report, reporting_build=a.reporting_build, timeout_s=10.)
    result['native_producer'] = produced
    assert produced['ok'] and produced['complete'] and not produced['native_inventory']['potentially_truncated']
    after = json.loads(report.read_text())
    known = {admission._canonical_identity(v) for v in before['violations']}
    fresh = [v for v in after['violations'] if admission._canonical_identity(v) not in known]
    result.update(candidate=str(child), candidate_sha256=force._hash(child), new_native_faults=fresh,
        opens=len(after['unconnected_items']), source_raw_native_count=len(before['violations']),
        candidate_raw_native_count=len(after['violations']), proposal=q,
        records=[dict(plan=dict(proposal=q), materialized=dict(retired_track_uuids=q['track_uuids'],
            modified_zone_uuids=[q['zone_uuid']]))])
    assert not fresh and not after['unconnected_items'], 'new_terminal_shadow_native_fault_or_open'
    result.update(ok=True, complete=True, changed=True)
except (ValueError, RuntimeError, KeyError, TypeError, OSError, AssertionError, owner.native.Refused) as exc:
    result['errors'].append(type(exc).__name__+':'+str(exc))
assert epoch == force._code_identity() and source_family == force._family(a.source, a.hint)
result['source_family_and_code_unchanged'] = True
result['input_sha256'] = {str(q.resolve()):force._hash(q) for q in
    (Path(__file__), Path(owner.__file__), a.grade)}
force._write(a.out/'stage.json', result)
print(json.dumps(dict(stage=str(a.out/'stage.json'), ok=result['ok'], changed=result['changed'],
    errors=result['errors'], progress=result.get('independent_saved_receiving',{}).get('actual_saved_progress'))), flush=True)
if not result['ok']: raise SystemExit(1)
