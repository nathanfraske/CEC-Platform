"""One Source-qualified whole-current acute shortcut, not ordinary routing."""
import math
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_route_quality as quality
import cec_scalar_corner_stage as scalar
import cec_full_current_planar_reflow as full
import cec_additive_pair_repair as saver
import cec_source_literal_retirement as literal
import cec_cell_row_rebuild as binding

def _deadline(seconds):
    if type(seconds)not in(int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_full_current_acute_lease_required')
    return time.monotonic()+seconds

def _ids(values):
    if (type(values)not in(list,tuple) or len(values)!=2 or len(set(values))!=2
            or any(type(u)is not str or not u for u in values)):
        raise ValueError('one_exact_source_acute_pair_required')
    return sorted(values)

def plan(board,source,*,board_hint,source_track_uuids,timeout_s=10.):
    deadline=_deadline(timeout_s);ids=_ids(source_track_uuids)
    source=Path(source).resolve(strict=True);epoch=force._code_identity()
    family=force._family(source,board_hint)
    saved=pcbnew.LoadBoard(str(source))
    if binding._source_binding(board)!=binding._source_binding(saved):
        raise ValueError('exact_saved_full_current_acute_source_required')
    live={force._uid(t):t for t in board.GetTracks()}
    issue=[r for r in quality.analyze_board(board)['issues']
        if r['type']=='acute_backtrack' and sorted(r['track_uuids'])==ids]
    if len(issue)!=1:raise ValueError('one_fresh_native_source_acute_pair_required')
    a,b=[live[u]for u in ids]
    shared={tuple(a.GetStart()),tuple(a.GetEnd())}&{tuple(b.GetStart()),tuple(b.GetEnd())}
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    if (len(shared)!=1 or any(t.GetClass()!='PCB_TRACK' or force._uid(t)in grouped
            or t.HasSolderMask() or not quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0)
            for t in (a,b))):
        raise ValueError('exact_ungrouped_canonical_source_acute_pair_required')
    authority=full.plan(board,source,board_hint=board_hint,retired_track_uuids=ids,
        timeout_s=max(.001,deadline-time.monotonic()),max_source_track_mm=32.,max_source_cut_mm=48.)
    if time.monotonic()>=deadline or epoch!=force._code_identity() or family!=force._family(source,board_hint):
        raise ValueError('full_current_acute_source_or_lease_changed')
    return dict(scope='source_whole_current_acute_cleanup',source_sha256=force._hash(source),
        source_track_uuids=ids,request=dict(net=a.GetNetname(),layer=int(a.GetLayer()),
            at_nm=list(next(iter(shared))),source_track_uuids=ids),
        source_authority=authority,current_qualified=False,release_authority=False)

def construct_private(source,candidate,proposal,*,board_hint,timeout_s=10.):
    deadline=_deadline(timeout_s);source,candidate=map(Path,(source,candidate))
    if source.resolve()==candidate.resolve() or force._hash(source)!=force._hash(candidate):
        raise ValueError('distinct_exact_private_acute_source_copy_required')
    board=pcbnew.LoadBoard(str(source))
    fresh=plan(board,source,board_hint=board_hint,
        source_track_uuids=proposal['source_track_uuids'],
        timeout_s=max(.001,deadline-time.monotonic()))
    if fresh!=proposal:raise ValueError('stale_or_forged_full_current_acute_plan')
    old={force._uid(t)for t in board.GetTracks()}
    result=scalar._construct_acute(board,[fresh['request']],deadline=deadline)
    if (result['chamfered']!=1 or sorted(result['retired_track_uuids'])!=fresh['source_track_uuids']
            or not result['details'][0]['proposed_length_nm']<result['details'][0]['source_length_nm']):
        raise ValueError('strictly_shorter_native_full_current_corner_required')
    candidate.write_text(literal.subtract(source.read_text(),fresh['source_track_uuids']))
    saver.save_native_additions(candidate,board,{},old-set(fresh['source_track_uuids']),board_hint=board_hint)
    if time.monotonic()>=deadline:raise ValueError('full_current_acute_construct_deadline')
    return dict(complete=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),
        geometry=result,routing_admitted=False,current_qualified=False,release_authority=False)

def receive(source,candidate,*,board_hint,source_track_uuids,timeout_s=10.):
    started=time.monotonic();result=dict(ok=False,complete=False,errors=[],
        current_qualified=False,release_authority=False,whole_original_receiving_still_required=True)
    try:
        deadline=_deadline(timeout_s);paths=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_full_current_acute_files_required')
        families=[force._family(p,board_hint)for p in paths];epoch=force._code_identity()
        before,after=[pcbnew.LoadBoard(str(p))for p in paths]
        proposal=plan(before,paths[0],board_hint=board_hint,source_track_uuids=source_track_uuids,
            timeout_s=max(.001,deadline-time.monotonic()))
        proof=full.receive(*paths,board_hint=board_hint,
            retired_track_uuids=proposal['source_track_uuids'],max_source_track_mm=32.,
            max_source_cut_mm=48.,timeout_s=max(.001,deadline-time.monotonic()))
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('independent_full_current_acute_reflow_refused:'+str(proof.get('errors')))
        # Reconstruct the deterministic untrusted proposal afresh; receiving
        # requires its exact native new geometry, not a worker success flag.
        expected=scalar._construct_acute(before,[proposal['request']],deadline=deadline)
        if expected['chamfered']!=1:raise ValueError('fresh_native_acute_shortcut_unavailable')
        # Fresh IDs differ; compare all old survivors by UUID and all incoming
        # strokes by exact geometry/width/net/layer/lock, never snapped points.
        retired=set(proposal['source_track_uuids'])
        original=pcbnew.LoadBoard(str(paths[0]));old={force._uid(t)for t in original.GetTracks()}-retired
        def incoming(b):
            return sorted((str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),
                tuple(t.GetStart()),tuple(t.GetEnd()),bool(t.IsLocked()))
                for t in b.GetTracks()if force._uid(t)not in old)
        if incoming(before)!=incoming(after):
            raise ValueError('saved_full_current_acute_geometry_differs_from_fresh_proposal')
        first,last=[quality.analyze_board(b)for b in(original,after)]
        detail=expected['details'][0]
        if (not detail['proposed_length_nm']<detail['source_length_nm']
                or last['issue_count']>=first['issue_count']
                or last['non_octilinear_count']>first['non_octilinear_count']):
            raise ValueError('strict_shorter_craft_improvement_required')
        import collections,json
        counts=lambda q:collections.Counter(json.dumps(i,sort_keys=True)for i in q['issues'])
        if counts(last)-counts(first):raise ValueError('acute_cleanup_introduced_craft_issue')
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint)for p in paths]
                or time.monotonic()>=deadline):raise ValueError('acute_cleanup_live_epoch_or_deadline')
        result.update(ok=True,complete=True,source_proposal=proposal,full_current_receiving=proof,
            fresh_geometry=expected,strictly_shorter=True,craft_before=first,craft_after=last)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
