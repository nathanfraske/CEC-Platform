"""Receive exact ordinary overhang trims after native macro reconstruction.

New native warning identities are discovery hints, never cut authority.
Only unprotected positive ordinary straight tracks can shrink to exact
integer junction extrema. The existing source-delta receiver independently
replays every contact, surviving partition, geometry and ground refill.
Whole original macro, native DRC and field receiving remain mandatory.
"""
import math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_native_macro_tail_cleanup as hints
import cec_terminal_overhang as overhang
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_current_debt as current
import cec_route_quality as quality
from cec_native_items import discard_items


def construct(source,outdir,*,board_hint,original_native,proposed_native,timeout_s=10.):
    result=dict(schema=1,scope='source_owned_exact_ordinary_macro_junction_trim',ok=False,complete=False,
        changed=False,candidate=None,errors=[],retired_track_uuids=[],incoming_track_uuids=[],
        current_authority=False,release_authority=False,original_macro_receiving_still_required=True)
    started=time.monotonic()
    try:
        # One complete transaction includes fill/save plus TWO independent
        # receivers. Callers may explicitly budget up to thirty seconds for
        # that finite work; the ordinary receiver keeps its own ten-second
        # ceiling. The default and every physical admission gate are unchanged.
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=30
                or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_exact_macro_overhang_context_required')
        result['explicit_total_transaction_wall_s']=float(timeout_s)
        source=Path(source).resolve();outdir=Path(outdir)
        if outdir.exists() or not source.is_file():raise ValueError('fresh_saved_macro_overhang_context_required')
        family=force._family(source,board_hint);epoch=force._code_identity()
        board=pcbnew.LoadBoard(str(source));positive=ordinary.eligible_nets(board,source,board_hint)
        warnings=set(hints.new_warning_ids(original_native,proposed_native))
        grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
        scope=[t for t in board.GetTracks() if force._uid(t) in warnings and t.GetClass()=='PCB_TRACK'
            and not t.IsLocked() and t.GetParentGroup() is None and force._uid(t) not in grouped
            and str(t.GetNetname()) in positive and 0<t.GetWidth()<500000]
        if len(scope)>8:raise ValueError('ordinary_macro_overhang_work_bound')
        result['positive_ordinary_warning_track_uuids']=sorted(force._uid(t) for t in scope)
        plan=overhang.trim_generated_overhangs(board,[force._uid(t) for t in scope],nets=positive)
        result['exact_native_junction_trim']=plan
        if not plan['changed_count']:
            result.update(ok=True,complete=True);return result
        changed={row['uuid'] for row in plan['changes']}
        items=[t for t in board.GetTracks() if force._uid(t) in changed]
        for item in items:
            if not quality.is_canonical_stroke(tuple(item.GetStart()),tuple(item.GetEnd())):
                raise ValueError('ordinary_overhang_trim_must_retain_canonical_stroke')
            replacement=item.Duplicate();replacement.m_Uuid.Clone(pcbnew.KIID());board.Add(replacement)
            result['incoming_track_uuids'].append(force._uid(replacement))
        discard_items(board,items);child=force._copy_family(source,outdir)
        additive._ground_refill(board);field._save_field_snapshot(board,child)
        result.update(candidate=str(child),candidate_sha256=force._hash(child),retired_track_uuids=sorted(changed))
        remaining=timeout_s-(time.monotonic()-started)
        if remaining<=0:raise ValueError('ordinary_macro_overhang_deadline')
        result['independent_exact_source_delta_receiving']=ordinary.receive(source,child,
            board_hint=board_hint,retired_track_uuids=sorted(changed),timeout_s=min(10.,remaining))
        proof=result['independent_exact_source_delta_receiving']
        if not proof['ok'] or not proof['complete']:
            raise ValueError('ordinary_macro_overhang_source_delta_refused:'+str(proof['errors']))
        result['independent_current_nonregression']=current.receive(source,child,board_hint=board_hint)
        proof=result['independent_current_nonregression']
        if not proof['ok'] or not proof['complete']:
            raise ValueError('ordinary_macro_overhang_current_refused:'+str(proof['errors']))
        if (time.monotonic()-started>=timeout_s or family!=force._family(source,board_hint)
                or epoch!=force._code_identity()):
            raise ValueError('ordinary_macro_overhang_source_code_or_deadline_changed')
        result.update(ok=True,complete=True,changed=True,source=str(source),source_sha256=force._hash(source),
            code_identity=epoch,source_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
