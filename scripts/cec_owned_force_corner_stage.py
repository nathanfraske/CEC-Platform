"""Bounded source-domain acute finishing, never ordinary reclassification.

The unchanged complete source/sink domain and full per-face width contract
select requests. Existing native geometry proposes; the separate force owner
receives every saved source delta, current floor, field and absolute cut.
No current division, new barrel, placement, outline or release authority.
"""
import argparse
import json
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_current_topology as topology
import cec_force_crossface_receiving as receiver
import cec_scalar_corner_stage as geometry
import cec_route_quality as quality
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_native_drc_runner as native
import cec_stage_admission as admission
import cec_fab_profile as fab


def requests(board,domains,contracts,*,allow_locked_source=False,timeout_s=10.):
    """Read-only finite geometry scope; supplied context grants no saved cut."""
    if (type(domains) is not dict or type(contracts) is not dict
            or type(allow_locked_source) is not bool
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):raise ValueError('bounded_owned_force_corner_context_required')
    deadline=time.monotonic()+timeout_s
    items=list(board.GetTracks());live={force._uid(t):t for t in items}
    if len(items)>16384 or len(live)!=len(items):raise ValueError('unique_bounded_owned_force_inventory_required')
    result=dict(requests=[],refusals=[],complete=False,source_mutated=False,release_authority=False)
    grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    permitted_faces={int(board.GetLayerID(name)) for name in fab.routing_layers(board,include_power=True)}
    findings=quality.analyze_board(board)['issues']
    for issue in findings:
        if time.monotonic()>=deadline:raise ValueError('complete_owned_force_corner_inventory_required')
        net=issue['net'];domain=domains.get(net);contract=contracts.get(net)
        if issue['type']!='acute_backtrack' or not domain or not contract:continue
        ids=issue['track_uuids']
        if (type(domain) is not dict or type(contract) is not dict or domain.get('complete') is not True
                or domain.get('missing_refs') or len(ids)!=2 or not set(ids)<=live.keys()):continue
        source=[live[u] for u in ids]
        if (any(t.GetClass()!='PCB_TRACK' or force._uid(t) in grouped or t.GetParentGroup()
                or t.HasSolderMask() or t.IsLocked() and not allow_locked_source
                or not 0<t.GetLength()<=32000000 or not 0<t.GetWidth()<=20000000
                or not quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0) for t in source)
                or len({int(t.GetLayer()) for t in source})!=1
                or any(int(t.GetLayer()) not in permitted_faces for t in source)
                or len({t.GetWidth() for t in source})!=1):continue
        shared={tuple(source[0].GetStart()),tuple(source[0].GetEnd())}&{
            tuple(source[1].GetStart()),tuple(source[1].GetEnd())}
        if len(shared)!=1:continue
        try:
            for t in source:receiver.require_track_floor(board,t,contract,max(s.GetWidth() for s in source))
        except (ValueError,KeyError,TypeError) as exc:
            result['refusals'].append(dict(net=net,source_track_uuids=sorted(ids),reason=str(exc)));continue
        if len(result['requests'])>=128:raise ValueError('owned_force_corner_request_bound')
        result['requests'].append(dict(net=net,layer=int(source[0].GetLayer()),at_nm=list(next(iter(shared))),
            source_track_uuids=sorted(ids)))
    if time.monotonic()>=deadline:raise ValueError('complete_owned_force_corner_inventory_required')
    result['complete']=True;return result


def source_inventory(board,hint,*,allow_locked_source=False):
    with force._thermal_hint(hint):
        domains=topology.board_current_domains(board,hint)
        contracts=topology.route_width_contracts(board,board_hint=hint)
    return requests(board,domains,contracts,allow_locked_source=allow_locked_source)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_requests=4,sense_timeout_s=40.):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or reporting_build is None or type(allow_locked_source) is not bool
            or type(max_requests) is not int or not 1<=max_requests<=8
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0<sense_timeout_s<=60.):raise ValueError('bounded_explicit_saved_owned_force_corner_context_required')
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_and_fresh_owned_force_corner_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    started=time.monotonic()
    r=dict(source=str(source),source_sha256=expected_source_sha256,candidate=str(source),
        candidate_sha256=expected_source_sha256,code_identity=epoch,ok=False,complete=False,
        changed=False,attempts=[],errors=[],source_selected=False,routing_admitted=False,
        fab_ready=False,release_authority=False,new_current_or_sharing_authority=False)
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        proof=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_owned_force_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        parent=pcbnew.LoadBoard(str(source));before=quality.analyze_board(parent)
        initial=source_inventory(parent,board_hint,allow_locked_source=allow_locked_source)
        r.update(before=initial,before_craft=before['issue_count'])
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('zero_opens_precede_optional_owned_force_finishing')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        for index,request in enumerate(initial['requests'][:max_requests]):
            row=dict(request=request,accepted=False);r['attempts'].append(row)
            try:
                b=pcbnew.LoadBoard(str(source))
                proposal=geometry._construct_acute(b,[request],deadline=time.monotonic()+10.)
                row['untrusted_geometry']=proposal
                if not proposal['chamfered']:raise ValueError('no_native_clear_contact_preserving_force_shortcut')
                child=force._copy_family(source,outdir/('UNADMITTED-owned-force-acute-'+str(index)))
                additive._ground_refill(b);field._save_field_snapshot(b,child)
                after=quality.analyze_board(pcbnew.LoadBoard(str(child)))
                key=lambda v:(v['type'],v['net'],v['layer'],tuple(v['at_mm']))
                if (after['issue_count']>=before['issue_count']
                        or after['non_octilinear_count']>before['non_octilinear_count']
                        or {key(v) for v in after['issues']}-{key(v) for v in before['issues']}
                        or not after['power_contours']['complete'] or not before['power_contours']['complete']
                        or after['power_contours']['finding_count']>before['power_contours']['finding_count']):
                    raise ValueError('strict_whole_board_force_craft_gain_without_new_contour_required')
                observed=observe(child,'candidate-'+str(index))
                added=sorted({admission._canonical_identity(v) for v in observed['violations']}-faults)
                row['new_native_fault_ids']=added
                if observed['unconnected_items'] or added:raise ValueError('owned_force_native_opens_or_new_warning')
                proof=receiver.receive(source,child,proposal['retired_track_uuids'],
                    board_hint=board_hint,sense_timeout_s=sense_timeout_s)
                row['independent_force_receiving']=proof
                if not proof['ok'] or not proof['complete']:raise ValueError('whole_source_owned_force_receiving_refused:'+str(proof['errors']))
                remaining=source_inventory(pcbnew.LoadBoard(str(child)),board_hint,allow_locked_source=allow_locked_source)
                row.update(accepted=True,candidate=str(child),candidate_sha256=force._hash(child))
                r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                    after=remaining,after_craft=after['issue_count'],retired_track_uuids=proposal['retired_track_uuids'],
                    independent_force_receiving=proof)
                break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:row['refusal']=type(exc).__name__+':'+str(exc)
        if not r['changed']:r.update(after=initial,after_craft=before['issue_count'])
        r.update(ok=True,complete=True,all_eligible_owned_force_requests_clean=not r['after']['requests'])
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    r['source_family_and_code_unchanged']=stable
    if not stable:r.update(ok=False,complete=False);r['errors'].append('owned_force_source_or_code_changed')
    r['wall_elapsed_s']=time.monotonic()-started;force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--expected-source-sha256',required=True);p.add_argument('--board-hint',required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--max-requests',type=int,default=4)
    p.add_argument('--sense-timeout-s',type=float,default=40.);a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        max_requests=a.max_requests,sense_timeout_s=a.sense_timeout_s)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        before=r.get('before_craft'),after=r.get('after_craft'),candidate_sha256=r['candidate_sha256'],errors=r['errors'])),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
