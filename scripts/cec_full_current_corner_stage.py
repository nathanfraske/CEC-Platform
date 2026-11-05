"""Finite zero-open trials of independently owned full-current native miters."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_full_current_corner_finish as owner
import cec_field_coupling as field
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_stage_admission as admission


def menus(board, requests):
    live = {force._uid(t):t for t in board.GetTracks()}; groups = defaultdict(list)
    for row in requests: groups[row['net'], row['layer'], row['width_nm']].append(row)
    result = []
    for rows in groups.values():
        batch = []; ids = set()
        for row in rows:
            prospective = ids | set(row['source_track_uuids'])
            if len(batch) < 4 and len(prospective) <= 8 and sum(live[u].GetLength() for u in prospective) <= 48000000:
                batch.append(row); ids = prospective
        if len(batch) > 1: result.append(batch)
        result.extend([row] for row in rows)
    return result


def run(source, outdir, *, board_hint, expected_source_sha256, reporting_build,
        allow_locked_source=False, max_trials=8, maximum_nm=2000000, minimum_nm=50000):
    owner._settings(allow_locked_source, maximum_nm, minimum_nm)
    if (type(board_hint) is not str or not board_hint or type(max_trials) is not int or not 1 <= max_trials <= 16
            or type(expected_source_sha256) is not str or len(expected_source_sha256) != 64
            or any(c not in '0123456789abcdef' for c in expected_source_sha256) or reporting_build is None):
        raise ValueError('bounded_explicit_saved_full_current_corner_context_required')
    source, outdir = map(lambda p:Path(p).resolve(), (source,outdir))
    if not source.is_file() or force._hash(source) != expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_full_current_corner_output_required')
    outdir.mkdir(parents=True); epoch = force._code_identity(); family = force._family(source, board_hint)
    result = dict(ok=False, complete=False, changed=False, errors=[], source=str(source),
        source_sha256=expected_source_sha256, candidate=str(source), candidate_sha256=expected_source_sha256,
        code_identity=epoch, attempts=[], records=[], source_selected=False, routing_admitted=False,
        fab_ready=False, release_authority=False)
    def observe(path,label):
        shadow = force._copy_family(path,outdir/(label+'-native-input')); report = outdir/(label+'.drc.json')
        proof = native.run(shadow, report, reporting_build=reporting_build, timeout_s=10.)
        result.setdefault('native_producers', {})[label] = proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_full_current_corner_native_inventory_required')
        return json.loads(report.read_text())
    try:
        parent = pcbnew.LoadBoard(str(source)); before = quality.analyze_board(parent)
        settings = dict(allow_locked_source=allow_locked_source, maximum_nm=maximum_nm, minimum_nm=minimum_nm)
        inventory = owner.discover(parent, source, board_hint=board_hint, **settings)
        result['before'] = inventory
        baseline = observe(source,'source')
        if baseline['unconnected_items']: raise ValueError('zero_opens_precede_full_current_corner_refinement')
        faults = {admission._canonical_identity(v) for v in baseline['violations']}
        for index, requests in enumerate(menus(parent, inventory['requests'])[:max_trials]):
            row = dict(requests=requests, accepted=False); result['attempts'].append(row)
            try:
                board = pcbnew.LoadBoard(str(source))
                proposal = owner.plan(board,source,requests,board_hint=board_hint,**settings)
                made = owner.materialize(board,source,proposal,board_hint=board_hint)
                child = force._copy_family(source, outdir/('UNADMITTED-full-current-corners-'+str(index)))
                field._save_field_snapshot(board,child)
                proof = owner.receive(source,child,proposal,board_hint=board_hint); row['independent_saved_receiving'] = proof
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('independent_full_current_corner_refused:'+str(proof['errors']))
                after = quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if (after['issue_count'] > before['issue_count'] or after['non_octilinear_count'] > before['non_octilinear_count']
                        or not after['power_contours']['complete'] or not before['power_contours']['complete']
                        or after['power_contours']['finding_count'] > before['power_contours']['finding_count']):
                    raise ValueError('whole_board_full_current_corner_craft_or_contour_regression')
                report = observe(child,'candidate-'+str(index))
                row['new_native_fault_ids'] = sorted({admission._canonical_identity(v) for v in report['violations']}-faults)
                if report['unconnected_items'] or row['new_native_fault_ids']:
                    raise ValueError('full_current_corner_new_native_fault_or_open')
                result.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    records=[dict(plan=proposal,materialized=made)],independent_saved_receiving=proof,
                    saved_trace_length_mm=proof['saved_trace_length_mm'],chamfered=made['chamfered'])
                row.update(accepted=True,candidate=str(child),candidate_sha256=result['candidate_sha256'])
                break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
                row['refusal'] = type(exc).__name__+':'+str(exc)
        result.update(ok=True,complete=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    stable = epoch == force._code_identity() and family == force._family(source,board_hint)
    result['source_family_and_code_unchanged'] = stable
    if not stable: result.update(ok=False,complete=False); result['errors'].append('full_current_corner_source_or_code_changed')
    force._write(outdir/'stage.json',result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'): p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--expected-source-sha256',required=True); p.add_argument('--board-hint',required=True)
    p.add_argument('--allow-locked-source',action='store_true'); p.add_argument('--max-trials',type=int,default=8)
    a = p.parse_args()
    import cec_swig_guard; cec_swig_guard.pin()
    import wx; quiet = wx.LogNull()
    r = run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,max_trials=a.max_trials)
    print(json.dumps(dict(report=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        chamfered=r.get('chamfered'),saved_trace_length_mm=r.get('saved_trace_length_mm'),
        candidate=r['candidate'],candidate_sha256=r['candidate_sha256'],errors=r['errors'])),flush=True)


if __name__ == '__main__': main()
