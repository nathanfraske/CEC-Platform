"""Source-owned overlap removal AND rated on-stroke tail shortening.

Exact-union normalization alone can expose the real obsolete end hidden by
two overlapping tracks. Propose deletion plus source-derived shortening as
one atomic transaction. An unchanged positive aggregate-load contract, literal
supply-loop receiving, full original-source current/field/cuts and uncapped
native DRC must all pass. No named net, refdes or position owns a repair.
"""
import argparse
import json
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_collinear_copper as lines
import cec_native_supply_tail_trim as trim
import cec_distributed_loop_retirement as loops
import cec_route_quality as quality
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_native_drc_runner as native
import cec_stage_admission as admission


def requests(board,*,allow_locked_source=False,include_acute_excursions=False):
    if type(allow_locked_source) is not bool:raise ValueError('explicit_rated_overlap_lock_policy_required')
    if type(include_acute_excursions) is not bool:raise ValueError('explicit_rated_acute_excursion_policy_required')
    native_tracks=list(board.GetTracks());tracks={force._uid(t):t for t in native_tracks}
    if len(tracks)>8192 or len(tracks)!=len(native_tracks):
        raise ValueError('rated_overlap_native_inventory_bound_or_ambiguity')
    rows=[];seen=set()
    for finding in quality.analyze_board(board)['issues']:
        kinds=('covered_backtrack','acute_backtrack') if include_acute_excursions else ('covered_backtrack',)
        if finding['type'] not in kinds or len(finding['track_uuids'])!=2:continue
        ids=tuple(sorted(finding['track_uuids']))
        if ids in seen:continue
        seen.add(ids);items=[tracks[u] for u in ids]
        if any(t.GetParentGroup() or t.IsLocked() and not allow_locked_source for t in items):continue
        if finding['type']=='acute_backtrack':
            # Geometry is only a request. Deleting a short excursion and
            # trimming its partner still requires the actual aggregate rail
            # authority, all full-width joins, literal replay and native DRC.
            if (any(t.GetClass()!='PCB_TRACK' or not 0<t.GetLength()<=32000000 for t in items)
                    or len({(str(t.GetNetname()),int(t.GetLayer())) for t in items})!=1):continue
            small,large=sorted(items,key=lambda t:(t.GetLength(),force._uid(t)))
            if small.GetLength()<=1000000 and small.GetLength()<large.GetLength():
                rows.append(dict(net=str(small.GetNetname()),retired_track_uuid=force._uid(small),
                    retained_track_uuid=force._uid(large)))
            continue
        a,b=map(lines._row,items)
        if not a or not b or a['key']!=b['key']:continue
        covers=[(a,b),(b,a)]
        for small,large in covers:
            if (large['width']>=small['width'] and large['lo']<=small['lo']<small['hi']<=large['hi']
                    and (small['lo'],small['hi'])!=(large['lo'],large['hi'])):
                rows.append(dict(net=small['net'],retired_track_uuid=small['uuid'],retained_track_uuid=large['uuid']))
                break
    return rows


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,allow_locked_source=False,
        maximum_requests=4,maximum_trials=16,sense_timeout_s=40.,include_acute_excursions=False):
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool
            or type(maximum_requests) is not int or not 1<=maximum_requests<=8
            or type(maximum_trials) is not int or not 1<=maximum_trials<=32
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0<sense_timeout_s<=60. or reporting_build is None or type(include_acute_excursions) is not bool):
        raise ValueError('bounded_explicit_rated_overlap_stage_required')
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('unchanged_source_hash_and_fresh_rated_overlap_output_required')
    outdir.mkdir(parents=True);epoch=force._code_identity();family=force._family(source,board_hint)
    started=time.monotonic();parent=pcbnew.LoadBoard(str(source))
    source_tracks={force._uid(t):t for t in parent.GetTracks()};before=quality.analyze_board(parent)
    r=dict(source=str(source),source_sha256=expected_source_sha256,candidate=str(source),
        candidate_sha256=expected_source_sha256,code_identity=epoch,ok=False,complete=False,changed=False,
        errors=[],attempts=[],accepted=[],before=before,after=before,
        maximum_requests=maximum_requests,maximum_trials=maximum_trials,
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,
        new_capacity_credited=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        proof=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_rated_overlap_native_inventory_required')
        if force._hash(shadow)!=force._hash(path):raise ValueError('rated_overlap_native_copy_differs')
        r.setdefault('native_producers',{})[label]=proof;return json.loads(dest.read_text())
    try:
        initial=observe(source,'source')
        if initial['unconnected_items']:raise ValueError('zero_open_source_precedes_rated_optional_cleanup')
        faults={admission._canonical_identity(v) for v in initial['violations']}
        candidates=requests(parent,allow_locked_source=allow_locked_source,
            include_acute_excursions=include_acute_excursions);r['source_requests']=candidates
        r['include_acute_excursions']=include_acute_excursions
        cuts=set();shortened={};selected_net=None;source_packets=None
        key=lambda q:(q['type'],q['net'],q['layer'],tuple(q['at_mm']))
        old_keys={key(v) for v in before['issues']}
        for request in candidates[:maximum_requests]:
            net=request['net'];gone=request['retired_track_uuid'];kept=request['retained_track_uuid']
            if gone in cuts or kept in cuts or selected_net is not None and net!=selected_net:continue
            try:
                contract=loops._contract(parent,source,net,board_hint)
                floors={parent.GetLayerID(n):math.ceil(w*1e6) for n,w in contract['required_by_layer_mm'].items()
                    if n in contract['routing_layers'] and w<=1.}
                scope=cuts|{gone}
                choices=trim.propose(parent,kept,required_width_by_layer_nm=floors,
                    retired_track_uuids=sorted(scope),maximum_candidates=8)
            except (ValueError,KeyError,TypeError,RuntimeError) as exc:
                r.setdefault('scope_refusals',[]).append(dict(request=request,refusal=str(exc)));continue
            for choice in choices['proposals']:
                if len(r['attempts'])>=maximum_trials:break
                row=dict(request=request,trim_proposal=choice,accepted=False);r['attempts'].append(row)
                try:
                    retained=dict(shortened);retained[kept]=choice['request']
                    b=pcbnew.LoadBoard(str(source))
                    proposal=loops.plan(b,source,net=net,board_hint=board_hint,track_uuids=sorted(scope),
                        retained_shortening_nm=[retained[u] for u in sorted(retained)],
                        allow_locked_track_uuids=[u for u in sorted(scope) if source_tracks[u].IsLocked()],
                        allow_source_inner_layers=True)
                    loops.subtract(b,proposal);additive._ground_refill(b)
                    child=force._copy_family(source,outdir/('UNADMITTED-rated-overlap-'+str(len(r['attempts'])-1)))
                    field._save_field_snapshot(b,child);saved=pcbnew.LoadBoard(str(child));after=quality.analyze_board(saved)
                    if (after['issue_count']>=r['after']['issue_count'] or after['non_octilinear_count']>before['non_octilinear_count']
                            or {key(v) for v in after['issues']}-old_keys):
                        raise ValueError('strict_whole_source_craft_improvement_required')
                    report=observe(child,'candidate-'+str(len(r['attempts'])-1))
                    row['new_native_fault_ids']=sorted({admission._canonical_identity(v) for v in report['violations']}-faults)
                    if report['unconnected_items'] or row['new_native_fault_ids']:
                        raise ValueError('new_native_fault_or_open_not_waived')
                    literal=loops.receive(source,child,proposal,board_hint=board_hint)
                    row['independent_full_load_literal_receiving']=literal
                    if not literal['ok'] or not literal['complete']:raise ValueError('full_load_literal_phase_refused:'+str(literal['errors']))
                    debt=current.receive(source,child,board_hint=board_hint);row['whole_original_current_debt']=debt
                    if not debt['ok'] or not debt['complete']:raise ValueError('whole_source_current_debt_refused')
                    with force._thermal_hint(board_hint):
                        delta=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-
                            field.blocker_keys(field.field_coupling_summary(str(source))))
                    row['new_field_blocker_keys']=delta
                    if delta:raise ValueError('new_original_source_field_blocker')
                    if source_packets is None:source_packets=sense.replay(source,board_hint=board_hint,timeout_s=sense_timeout_s)
                    fresh=sense.replay(child,board_hint=board_hint,timeout_s=sense_timeout_s)
                    proof=sense.compare_contour_preservation(source_packets,fresh,modified_nets=[net],
                        native_copper_transforms=sense.native_copper_transform_inventory(parent,saved,modified_nets=[net]))
                    row['absolute_native_cut_preservation']=proof
                    if not proof['same_evidence'] or not proof['comparison_complete']:raise ValueError('absolute_original_source_cuts_refused')
                    row.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child),
                        quality_before=r['after']['issue_count'],quality_after=after['issue_count'])
                    cuts=scope;shortened=retained;selected_net=net;r['accepted'].append(dict(row))
                    r.update(candidate=str(child),candidate_sha256=force._hash(child),changed=True,after=after,
                        source_plan=proposal,independent_original_source_receiving=row)
                    break
                except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
                    row['refusal']=type(exc).__name__+':'+str(exc)
        r.update(ok=True,complete=True,retired_source_track_uuids=sorted(cuts),retained_source_trims=list(shortened.values()))
    except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    r['source_family_and_code_unchanged']=stable
    if not stable:r.update(ok=False,complete=False);r['errors'].append('rated_overlap_source_or_code_changed')
    if not r['ok']:r.update(candidate=str(source),candidate_sha256=expected_source_sha256,changed=False)
    r['wall_elapsed_s']=time.monotonic()-started;force._write(outdir/'stage.json',r)
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--include-acute-excursions',action='store_true');a=p.parse_args()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        include_acute_excursions=a.include_acute_excursions)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','errors')}
        |dict(before=r['before']['issue_count'],after=r['after']['issue_count'])),flush=True)


if __name__=='__main__':main()
