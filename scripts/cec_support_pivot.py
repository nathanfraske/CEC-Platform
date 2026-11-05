"""Bounded agent/reviewer recipe: preclear, pivot, route, independently receive.

Recipes are board data, not refdes/coordinate cases in the pipeline. The new
seat is inspected before any source land moves; an exact ordinary preclear
prefix is received first. Current/paired/sense routes cannot be retired. Only
ordinary nets of the finite support cohort enter the second routing slice.
No frozen authority is rebound and no output is promoted to fabrication.
"""
from pathlib import Path
import argparse
import json

import pcbnew
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_pose_clearance as future
import cec_ordinary_route_receiving as ordinary
import cec_support_pivot_receiving as receiving
import cec_support_field_reflow as support_fields


def _route_cohort(board, selected, *, source, board_hint, timeout_s):
    """Finite independently budgeted source-owned nets, not one starving loop.

    At most four two-land owners can enter the pose receiver, hence at most
    eight ordinary nets. Each lease remains bounded at ten seconds, with all
    guards intact. A difficult first net cannot consume the later net's lease.
    """
    future._budget(timeout_s)
    selected=sorted(set(selected))
    if len(selected)>8:raise ValueError('finite_support_cohort_route_leases_required')
    rows=[];resolver=fr._project_netclass_resolver(str(source))
    for net in selected:
        with force._thermal_hint(board_hint):
            trial=fr.synthesize_lastmile(board,include_nets=[net],max_mm=100.,maze_max_mm=30.,
                clearance=0,cap=32,attempts_per_pair=16,field_guard=True,route_craft_guard=True,
                lock=True,netclass_resolver=resolver,wall_timeout_s=timeout_s,per_net_timeout_s=timeout_s)
        rows.append(dict(net=net,lease_s=timeout_s,construction=trial))
    return dict(net_results=rows,closed=sum(r['construction'].get('closed',0) for r in rows),
        legs=sum(r['construction'].get('legs',0) for r in rows),
        max_construction_wall_s=len(rows)*timeout_s,
        independent_saved_receiving_required=True)


def run(source, recipe, directory, *, board_hint, timeout_s=10.):
    source=Path(source).resolve();directory=Path(directory).resolve();future._budget(timeout_s)
    if directory.exists() or source==directory:raise ValueError('fresh_support_pivot_directory_required')
    if force._hash(source)!=recipe.get('source_sha256'):raise ValueError('support_pivot_recipe_source_changed')
    fully_isolated = recipe.get('fully_isolated_reseat', False)
    allow_fields = recipe.get('allow_support_field_reflow', False)
    if type(fully_isolated) is not bool or type(allow_fields) is not bool:
        raise ValueError('explicit_isolated_reseat_recipe_mode_required')
    poses=recipe.get('poses');directory.mkdir(parents=True)
    family=force._family(source,board_hint);code=force._code_identity()
    report=dict(schema=1,source=str(source),source_sha256=force._hash(source),ok=False,
        release_authority=False,routing_admitted=False,placement_authority_transferred=False)
    preclear=future.prepare(source,poses,directory/'preclear',board_hint=board_hint,
        allow_locked_track_uuids=recipe.get('allow_locked_track_uuids',()),timeout_s=timeout_s)
    report['preclear']=preclear
    if preclear['ok'] is not True:
        report['reason']='ordinary_destination_preclear_refused'
        force._write(directory/'receiving.json',report);return report
    prefix=Path(preclear['board']);board=pcbnew.LoadBoard(str(prefix))
    gate=future.plan(board,poses,source=prefix,board_hint=board_hint,timeout_s=timeout_s)
    if not gate['ok'] or gate['blockers']:raise ValueError('received_future_seat_no_longer_clear')
    eligible=ordinary.eligible_nets(board,prefix,board_hint)
    source_positions={force._uid(p):tuple(p.GetPosition()) for ref in poses
        for p in board.FindFootprintByReference(ref).Pads()}
    target=force._copy_family(prefix,directory/'candidate')
    for ref,(x,y,angle) in poses.items():
        fp=board.FindFootprintByReference(ref);fp.SetOrientationDegrees(angle)
        fp.SetPosition(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)))
    # The stationary anchor's unrelated old opens do not own this work lease.
    # Only relocated ordinary terminals get an independent bounded work lease.
    selected=sorted({str(p.GetNetname()) for ref in poses for p in board.FindFootprintByReference(ref).Pads()
        if tuple(p.GetPosition())!=source_positions[force._uid(p)]} & eligible)
    construction=_route_cohort(board,selected,source=prefix,board_hint=board_hint,timeout_s=timeout_s)
    field_layouts=[]
    if allow_fields:
        for ref in sorted(poses):
            layout=support_fields.construct(board,ref);field_layouts.append(layout)
            if not layout['ok']:
                # A later label refusal must not erase the earlier routing
                # trace or leave "candidate" pointing to the unchanged
                # pre-pose copy. Keep the actual trial, explicitly unadmitted.
                additive._ground_refill(board);field._save_field_snapshot(board,target)
                additive.bind_local_via_rule(board,target)
                report.update(reason='bounded_readable_support_fields_refused',field_layouts=field_layouts,
                    ordinary_scope=selected,construction=construction,
                    unadmitted_trial_board=str(target),unadmitted_trial_sha256=force._hash(target),
                    original_source_and_code_unchanged=(family==force._family(source,board_hint)
                        and code==force._code_identity()),
                    independent_saved_receiving_still_required=True)
                force._write(directory/'receiving.json',report);return report
    additive._ground_refill(board);field._save_field_snapshot(board,target)
    additive.bind_local_via_rule(board,target)
    proof=receiving.receive(prefix,target,board_hint=board_hint,timeout_s=timeout_s,
        fully_isolated_reseat=fully_isolated,allow_support_field_reflow=allow_fields)
    final_family=force._family(source,board_hint);final_code=force._code_identity()
    stable=family==final_family and code==final_code
    report.update(ok=proof['ok'] is True and proof['complete'] is True and stable,
        reason='received_preclear_pivot_route_slice' if proof['ok'] and stable else 'pivot_route_slice_refused',
        independent_pivot_receiving=proof,ordinary_scope=selected,construction=construction,
        support_field_layouts=field_layouts,
        original_source_and_code_unchanged=stable,board=str(target),board_sha256=force._hash(target),
        source_family_before=family,source_family_after=final_family,code_before=code,code_after=final_code,
        source_opens=proof.get('source_opens'),opens=proof.get('opens'),
        full_current_kelvin_placement_and_release_receiving_still_required=True)
    force._write(directory/'receiving.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--recipe',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--hint',required=True);p.add_argument('--seconds',type=float,default=10.)
    args=p.parse_args();result=run(args.source,json.loads(args.recipe.read_text()),args.out,
        board_hint=args.hint,timeout_s=args.seconds)
    print(json.dumps({k:result.get(k) for k in ('ok','reason','source_opens','opens','board')}),flush=True)
    print(json.dumps(dict(errors=(result.get('independent_pivot_receiving') or {}).get('errors',[]))),flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
