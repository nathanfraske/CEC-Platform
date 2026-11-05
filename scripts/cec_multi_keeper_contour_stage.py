"""Bounded source-retained multi-owner contour consolidation and reception."""
import argparse
import json
import math
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_power_contours as audit
import cec_multi_keeper_contour as owner
import cec_native_drc_runner as native
import cec_route_quality as quality
import cec_stage_admission as admission


def run(source, outdir, *, board_hint, expected_source_sha256, reporting_build,
        max_requests=16, max_accepted=2, allow_locked_source=False,fill_policy='native',
        clip_native_additions=False,native_addition_inset_nm=0,allow_compatible_keeper_classes=False,
        allow_conservative_keeper_contract=False,min_width_mm=1.0,allow_single_keeper_extension=False,
        retain_source_track_groups=False):
    if (type(board_hint) is not str or not board_hint or reporting_build is None
            or type(max_requests) is not int or not 1 <= max_requests <= 32
            or type(max_accepted) is not int or not 1 <= max_accepted <= 4
            or type(allow_locked_source) is not bool or type(fill_policy) is not str
            or fill_policy not in ('native','source_preserving_regions') or type(clip_native_additions) is not bool
            or clip_native_additions and fill_policy!='source_preserving_regions'
            or type(native_addition_inset_nm) is not int or not 0<=native_addition_inset_nm<=10
            or native_addition_inset_nm and not clip_native_additions
            or type(allow_compatible_keeper_classes) is not bool
            or allow_compatible_keeper_classes and fill_policy!='source_preserving_regions'
            or type(allow_conservative_keeper_contract) is not bool
            or allow_conservative_keeper_contract and (not allow_locked_source or fill_policy!='source_preserving_regions')
            or type(allow_single_keeper_extension) is not bool or type(retain_source_track_groups) is not bool
            or (allow_single_keeper_extension or retain_source_track_groups) and fill_policy!='source_preserving_regions'
            or type(min_width_mm) not in (int,float) or not math.isfinite(min_width_mm)
            or not 0<min_width_mm<=100.):
        raise ValueError('bounded_explicit_multi_keeper_stage_context_required')
    source, outdir = [Path(p).resolve() for p in (source,outdir)]
    if not source.is_file() or force._hash(source) != expected_source_sha256 or outdir.exists():
        raise ValueError('unchanged_saved_source_and_fresh_multi_keeper_output_required')
    epoch = force._code_identity(); family = force._family(source, board_hint); outdir.mkdir(parents=True)
    r = dict(source=str(source), source_sha256=expected_source_sha256, candidate=str(source),
        candidate_sha256=expected_source_sha256, code_identity=epoch, ok=False, complete=False,
        changed=False, errors=[], attempts=[], records=[], source_selected=False, routing_admitted=False,
        fab_ready=False, release_authority=False, new_capacity_credited=False)
    if min_width_mm!=1.:r['contour_inventory_min_width_mm']=min_width_mm
    def observe(path, label):
        shadow = force._copy_family(path, outdir/(label+'-native-input'))
        dest = outdir/(label+'.drc.json')
        proof = native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label] = proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_multi_keeper_native_inventory_required')
        return json.loads(dest.read_text())
    def inspect(path):
        return audit.audit_board(pcbnew.LoadBoard(str(path)),timeout_s=10.,include_terminal_caps=True,min_width_mm=min_width_mm)
    try:
        first = observe(source, 'source')
        if first['unconnected_items']: raise ValueError('zero_open_source_precedes_optional_multi_keeper_contour_cleanup')
        faults = {admission._canonical_identity(v) for v in first['violations']}
        initial_quality = quality.analyze_board(pcbnew.LoadBoard(str(source)))
        r['before'] = inspect(source)
        requests = audit.finding_requests(pcbnew.LoadBoard(str(source)), timeout_s=10.,include_terminal_caps=True,
            min_width_mm=min_width_mm)
        if not requests['complete'] or not r['before']['complete']:
            raise ValueError('complete_actual_multi_keeper_request_inventory_required')
        r['source_request_count'] = len(requests['requests']); selected = source; attempted = set()
        for index, request in enumerate(requests['requests'][:max_requests]):
            if len(r['records']) >= max_accepted: break
            row = dict(net=request['net'], layer_id=request['layer_id'], accepted=False)
            r['attempts'].append(row)
            try:
                proposal = owner.plan(selected, [t['uuid'] for t in request['source_tracks']],
                    allow_locked_source=allow_locked_source,fill_policy=fill_policy,
                    clip_native_additions=clip_native_additions,native_addition_inset_nm=native_addition_inset_nm,
                    allow_compatible_keeper_classes=allow_compatible_keeper_classes,
                    allow_conservative_keeper_contract=allow_conservative_keeper_contract,
                    allow_single_keeper_extension=allow_single_keeper_extension,
                    retain_source_track_groups=retain_source_track_groups)
                key = (tuple(z['configuration']['uuid'] for z in proposal['source_zones']),
                    tuple(t['uuid'] for t in proposal['source_tracks']))
                if key in attempted: raise ValueError('duplicate_bounded_native_owner_request')
                attempted.add(key)
                board = pcbnew.LoadBoard(str(selected)); materialized = owner.construct(board, proposal)
                child = force._copy_family(selected,outdir/('UNADMITTED-multi-keeper-'+str(index)))
                field._save_field_snapshot(board, child)
                prior, after = inspect(selected), inspect(child)
                row.update(findings_before=prior['finding_count'], findings_after=after['finding_count'])
                if not after['complete'] or after['finding_count'] >= prior['finding_count']:
                    raise ValueError('strict_actual_contour_improvement_required')
                q = quality.analyze_board(pcbnew.LoadBoard(str(child)))
                if q['issue_count'] > initial_quality['issue_count'] or q['non_octilinear_count'] > initial_quality['non_octilinear_count']:
                    raise ValueError('multi_keeper_cannot_worsen_signal_craft')
                report = observe(child,'candidate-'+str(index))
                row['new_native_fault_ids'] = sorted({admission._canonical_identity(v) for v in report['violations']}-faults)
                if report['unconnected_items'] or row['new_native_fault_ids']:
                    raise ValueError('new_multi_keeper_native_fault_or_open_not_waived')
                record = dict(plan=proposal, materialized=materialized)
                proof = owner.receive(source,child,r['records']+[record],board_hint=board_hint)
                row['whole_original_source_receiving'] = proof
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('multi_keeper_whole_source_receiving_refused:'+str(proof['errors']))
                r['records'].append(record); selected = child
                row.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
            except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.Refused) as exc:
                row['refusal'] = type(exc).__name__+':'+str(exc)
            print(json.dumps({k:row.get(k) for k in ('net','accepted','refusal','findings_before','findings_after')}),flush=True)
        r.update(ok=True,complete=True,changed=bool(r['records']),candidate=str(selected),
            candidate_sha256=force._hash(selected),after=inspect(selected))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,owner.Refused) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged'] = epoch == force._code_identity() and family == force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False); r['errors'].append('multi_keeper_stage_source_or_code_changed')
    if not r['ok']: r.update(changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
    force._write(outdir/'stage.json', r)
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--max-requests',type=int,default=16);p.add_argument('--max-accepted',type=int,default=2)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--fill-policy',choices=('native','source_preserving_regions'),default='native')
    p.add_argument('--clip-native-additions',action='store_true')
    p.add_argument('--allow-compatible-keeper-classes',action='store_true')
    p.add_argument('--allow-conservative-keeper-contract',action='store_true',
        help='Explicit preserving mode only: retain any source lock and max new-fill minimum thickness; all other process fields exact')
    p.add_argument('--allow-single-keeper-extension',action='store_true',
        help='Explicit preserving mode only: extend one already consolidated keeper without losing its windows or old fill')
    p.add_argument('--retain-source-track-groups',action='store_true',
        help='Explicit preserving mode only: source tracks and complete source groups stay exact; keeper group ownership never changes')
    p.add_argument('--min-width-mm',type=float,default=1.,help='Contour inventory work floor only; no current-width or fabrication rule change')
    p.add_argument('--native-addition-inset-nm',type=int,default=0);a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet = wx.LogNull()
    r = run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        max_requests=a.max_requests,max_accepted=a.max_accepted,fill_policy=a.fill_policy,
        clip_native_additions=a.clip_native_additions,native_addition_inset_nm=a.native_addition_inset_nm,
        allow_compatible_keeper_classes=a.allow_compatible_keeper_classes,
        allow_conservative_keeper_contract=a.allow_conservative_keeper_contract,min_width_mm=a.min_width_mm,
        allow_single_keeper_extension=a.allow_single_keeper_extension,
        retain_source_track_groups=a.retain_source_track_groups)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}),flush=True)


if __name__ == '__main__':main()
