"""Native current-owned junction prototype; no board/refdes coordinate policy.

Discover the scalar engine's protected real track-body tees. A native pad-corner
geometry proposal grants no net authority: full.plan/receive must independently
prove the original complete current contract and exact subtract/add transaction.
This is a private feasibility probe, never production selection or a release.
"""
import argparse
import json
import time
import re
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_full_current_corner_finish as corners
import cec_full_current_planar_reflow as full
import cec_ordinary_pad_corner as geometry
import cec_route_corner_contacts as contacts
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_native_drc_runner as native
import cec_stage_admission as admission
from cec_native_items import discard_items


def require(condition, message='current_body_tee_evidence_required'):
    if not condition:
        raise ValueError(message)

p = argparse.ArgumentParser(description=__doc__)
for k in ('source', 'grade', 'out', 'reporting-build'):
    p.add_argument('--'+k, type=Path, required=True)
p.add_argument('--hint', required=True)
p.add_argument('--expected-source-sha256', required=True)
p.add_argument('--allow-locked-source', action='store_true')
p.add_argument('--max-trials', type=int, default=8)
a = p.parse_args()
require(not a.out.exists() and 1 <= a.max_trials <= 16, 'fresh_bounded_current_body_tee_work_required')
require(re.fullmatch('[0-9a-f]{64}', a.expected_source_sha256) is not None, 'explicit_source_hash_required')
require(force._hash(a.source) == a.expected_source_sha256, 'current_body_tee_source_hash_mismatch')
source = a.source.resolve(); epoch = force._code_identity(); family = force._family(source, a.hint)
inputs = {str(Path(__file__).resolve()): force._hash(Path(__file__)), str(a.grade): force._hash(a.grade)}
grade = json.loads(a.grade.read_text()); require(grade['code_identity'] == epoch)
side = next(k for k in ('candidate', 'source') if grade['boards'][k]['sha256'] == force._hash(source))
producer = grade['boards'][side]['native_producer']; require(producer['ok'] and producer['complete'])
require(not producer['native_inventory']['potentially_truncated'])
baseline_path = Path(producer['report']); require(force._hash(baseline_path) == producer['report_sha256'])
inputs[str(baseline_path)] = producer['report_sha256']
before = json.loads(baseline_path.read_text()); prior = {admission._canonical_identity(v) for v in before['violations']}
board = pcbnew.LoadBoard(str(source))
inventory = corners.discover(board, source, board_hint=a.hint,
    allow_locked_source=a.allow_locked_source, minimum_nm=20000)
requests = inventory['native_inventory']['immutable_body_tees']
a.out.mkdir()
r = dict(ok=False, complete=False, changed=False, errors=[], source=str(source),
    source_sha256=force._hash(source), code_identity=epoch, input_sha256=inputs, attempts=[],
    existing_default_cosmetic_body_tee_guard_unchanged=True,
    source_selected=False, routing_admitted=False, fab_ready=False, release_authority=False)
for i, tee in enumerate(requests[:a.max_trials]):
    board = pcbnew.LoadBoard(str(source)); live = {force._uid(t): t for t in board.GetTracks()}
    old = [live[u] for u in tee['source_track_uuids']]; face = tee['layer']; width = old[0].GetWidth()
    row = dict(request=tee, accepted=False); r['attempts'].append(row)
    try:
        require(len({(t.GetWidth(), bool(t.IsLocked())) for t in old}) == 1)
        require(all(not t.GetParentGroup() and not t.HasSolderMask() and
            (not t.IsLocked() or a.allow_locked_source) for t in old))
        current = full.plan(board, source, board_hint=a.hint, retired_track_uuids=tee['source_track_uuids'])
        require(not corners._retained_corner_keepers(board, tee, old[0], time.monotonic()+10.),
            'retained_power_contour_has_separate_ownership')
        body = [live[u] for u in tee['actual_native_body_track_uuids']]
        require(all(t.GetWidth() >= width and not t.GetParentGroup() and not t.HasSolderMask() for t in body))
        request = dict(net=tee['net'], layer=face, at_nm=tee['at_nm'],
            source_track_uuids=tee['source_track_uuids'], anchor_pad_uuids=[])
        shape = geometry._proposal(board, request, time.monotonic()+10.)
        new = []
        for j, leg in enumerate(shape['legs_nm']):
            t = old[0 if j < 2 else 1].Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*leg['start_nm'])); t.SetEnd(pcbnew.VECTOR2I(*leg['end_nm'])); new.append(t)
        webs = []
        for t in body:
            first = contacts.native_contact_radius(t, old, face, width, time.monotonic()+10.)
            last = contacts.native_contact_radius(t, new, face, width, time.monotonic()+10.)
            require(first > 0 and last >= first, 'retained_body_native_contact_web_would_shrink')
            webs.append(dict(uuid=force._uid(t), before_nm=first, after_nm=last))
        for t in new: board.Add(t)
        discard_items(board, old); additive._ground_refill(board)
        child = force._copy_family(source, a.out/('UNADMITTED-current-body-tee-'+str(i)))
        field._save_field_snapshot(board, child)
        proof = full.receive(source, child, board_hint=a.hint, retired_track_uuids=tee['source_track_uuids'])
        row.update(candidate=str(child), candidate_sha256=force._hash(child), current=proof,
            old_source_current_proposal=current, retained_body_contact_webs=webs, geometry=shape)
        require(proof['ok'] and proof['complete'] and not proof['errors'], str(proof))
        shadow = force._copy_family(child, a.out/('native-input-'+str(i)))
        report = a.out/('native-'+str(i)+'.json')
        actual = native.run(shadow, report, reporting_build=a.reporting_build, timeout_s=10.)
        require(actual['ok'] and actual['complete'] and not actual['native_inventory']['potentially_truncated'])
        after = json.loads(report.read_text()); fresh = [v for v in after['violations']
            if admission._canonical_identity(v) not in prior]
        row.update(new_native_faults=fresh, opens=len(after['unconnected_items']), native_producer=actual)
        require(not fresh and not row['opens'], str((fresh, row['opens'])))
        row['accepted'] = True
        r.update(ok=True, complete=True, changed=True, candidate=str(child), candidate_sha256=force._hash(child),
            records=[dict(plan=dict(retired_track_uuids=tee['source_track_uuids']),
                materialized=dict(retired_track_uuids=tee['source_track_uuids'],
                    added_native_uuids=proof['added_native_uuids']))],
            source_family_and_code_unchanged=True, prototype_only=True,
            independent_full_current_source_receiving=proof, retained_body_contact_webs=webs)
        break
    except (ValueError, RuntimeError) as exc:
        row['refusal'] = str(exc)
    print(json.dumps(dict(attempt=i, net=tee['net'], accepted=row['accepted'], refusal=row.get('refusal'))), flush=True)
require(epoch == force._code_identity() and family == force._family(source, a.hint))
require(all(force._hash(Path(p)) == h for p, h in inputs.items()), 'current_body_tee_input_or_tool_changed')
r.update(complete=True, source_family_and_code_unchanged=True)
if not r['ok']:r['errors'] = ['finite_current_body_tee_prototype_domain_exhausted']
force._write(a.out/'stage.json', r)
print(json.dumps(dict(report=str(a.out/'stage.json'), ok=r['ok'], changed=r['changed'], attempts=len(r['attempts']))), flush=True)
