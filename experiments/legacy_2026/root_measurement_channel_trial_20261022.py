"""Finite source-bound channel cohort experiment; no production selection."""
import argparse
import json
from pathlib import Path
import time
import traceback

import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_measurement_channel_cohort as cohort
import cec_native_cell_pose_domains as domains


def experiment_exit_status(result):
    """A caught exception/empty menu must not look like unattended success."""
    if result.get('error'):
        return 1, 'rejected'
    if result['stage']=='route':
        saved=result.get('independent_saved_receiving',{})
        if (result.get('complete_route_screen',{}).get('complete') is True
                and saved.get('ok') is True and saved.get('complete') is True):
            return 0, 'received_private_descendant'
        return 2, 'bounded_proposal_incomplete'
    if result['stage']=='domains':
        return ((0,'offered_private_frames') if result.get('domain_proof',{}).get('offers')
            else (2,'bounded_proposal_incomplete'))
    return 0,'inspected_frame'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--board', required=True)
    selector=p.add_mutually_exclusive_group(required=True)
    selector.add_argument('--owner-uuid')
    selector.add_argument('--control-shunt-uuid')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', choices=('inspect', 'domains', 'route'), default='domains')
    p.add_argument('--shift-x', type=float, default=.25)
    p.add_argument('--shift-y', type=float, default=0.)
    p.add_argument('--turn', type=int, choices=(0,90,180,270), default=0)
    p.add_argument('--radius', type=float, default=3.)
    p.add_argument('--explore-offset-x',type=float,default=0.)
    p.add_argument('--explore-offset-y',type=float,default=0.)
    p.add_argument('--max-shift', type=float, default=16.)
    p.add_argument('--retain-source-barrels', action='store_true')
    p.add_argument('--frame', type=Path)
    p.add_argument('--control-shunt-frame',type=Path,
        help='Additional explicit Source-bound control-shunt poses; independently typed before composition')
    p.add_argument('--reference-group-uuid', action='append', default=[])
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('fresh_experiment_namespace_required')
    a.out.mkdir(parents=True)
    started = time.monotonic()
    selected_plan = json.loads(a.plan.read_text())
    rows = {r['board']: r for r in selected_plan['boards']}
    row = rows[a.board]
    source = Path(row['path']).resolve()
    families = {key: force._family(Path(r['path']), key) for key, r in rows.items()}
    code = force._code_identity()
    driver_hash=force._hash(Path(__file__))
    assert all(force._hash(Path(r['path'])) == r['sha256'] for r in rows.values())
    r = dict(schema=1, source=str(source), source_sha256=force._hash(source),
        board_hint=a.board, plan=str(a.plan.resolve()), plan_sha256=force._hash(a.plan),
        code_identity=code,driver_sha256=driver_hash,release_authority=False,source_selected=False,
        routing_admitted=False, fab_ready=False, stage=a.mode)
    try:
        parent = pcbnew.LoadBoard(str(source))
        if a.control_shunt_uuid:
            import cec_control_shunt_placement as control_shunt
            selected=[f for f in parent.GetFootprints() if force._uid(f)==a.control_shunt_uuid]
            if len(selected)!=1:raise ValueError('one_literal_source_control_shunt_required')
            fp=selected[0]
            initial={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]}
            with control_shunt.capture_exports() as initial_exports:
                proof=control_shunt.plan(parent,initial,board_hint=a.board,
                    reference_group_uuids=a.reference_group_uuid)
            r['initial_control_shunt_raw_source_exports']=initial_exports
            if set(proof)!=set(initial):raise ValueError('positive_source_control_shunt_role_required')
            selection=dict(scope='source_canonical_control_shunt_passive_frame',poses=initial,source_proof=proof)
        else:
            selection = cohort.select(parent, board_hint=a.board, owner_uuid=a.owner_uuid,
                reference_group_uuids=a.reference_group_uuid)
        r['cohort'] = selection
        if a.control_shunt_frame:
            import cec_control_shunt_placement as control_shunt
            extra=json.loads(a.control_shunt_frame.read_text())
            if set(extra)!={'source_sha256','poses'} or extra['source_sha256']!=r['source_sha256']:
                raise ValueError('exact_source_bound_control_shunt_frame_required')
            if set(extra['poses'])&set(selection['poses']):
                raise ValueError('additional_control_shunt_frame_must_be_disjoint')
            with control_shunt.capture_exports() as extra_exports:
                extra_proof=control_shunt.plan(parent,extra['poses'],board_hint=a.board,
                    reference_group_uuids=a.reference_group_uuid)
            if not extra_proof or set(extra_proof)!=set(extra['poses']):
                raise ValueError('every_additional_pose_requires_fresh_control_shunt_source_role')
            r['additional_control_shunts']=dict(frame=str(a.control_shunt_frame.resolve()),
                frame_sha256=force._hash(a.control_shunt_frame),source_proof=extra_proof,raw_source_exports=extra_exports)
            selection=dict(selection,poses={**selection['poses'],**extra['poses']})
        frame = json.loads(a.frame.read_text()) if a.frame else {}
        if frame:
            assert frame['source_sha256'] == r['source_sha256']
            assert set(frame['poses']) == set(selection['poses'])
            poses = frame['poses']
            options = frame['options']
        else:
            poses = {ref: [q[0]+a.shift_x, q[1]+a.shift_y, (q[2]+a.turn)%360]
                for ref, q in selection['poses'].items()}
            options = dict(board_hint=a.board, max_shift_mm=a.max_shift,
                allow_owned_locked_escapes=True, rebuild_projected_ground=not a.retain_source_barrels)
        r['frame'] = dict(source_sha256=r['source_sha256'], poses=poses, options=options)
        if a.reference_group_uuid:
            options['reference_group_uuids']=a.reference_group_uuid
        force._write(a.out/'frame.json', r['frame'])
        if a.mode == 'domains':
            origins={}
            if a.explore_offset_x or a.explore_offset_y:
                origins={ref:[pose[0]+a.explore_offset_x,pose[1]+a.explore_offset_y]
                    for ref,pose in selection['poses'].items()}
            proof = domains.propose(source, poses, **options, transport_source_barrels=not a.retain_source_barrels,
                radius_mm=a.radius, grid_mm=.5, timeout_s=10., max_candidates=64,
                max_results=2, complete_owner_ground=True,
                search_origins_mm=origins,
                allow_ordinary_obstacle_reconstruction=not a.retain_source_barrels,
                refine_source_singletons=False)
            r['domain_proof'] = proof
            for index, offer in enumerate(proof['offers']):
                force._write(a.out/('offer-'+str(index)+'.json'), dict(
                    source_sha256=r['source_sha256'], poses=offer['poses'],
                    options=offer.get('source_construction_options', options)))
            print(json.dumps(dict(offers=len(proof['offers']),
                domains={key: len(v) for key, v in proof['domains'].items()},
                stages=proof['domain_stages'], fresh=proof['fresh_receiving']), default=str), flush=True)
        else:
            import cec_control_shunt_placement as control_shunt
            with control_shunt.capture_exports() as raw_exports:
                try:board, packet = compiler.compile(source, poses, **options)
                finally:r['compiled_control_shunt_raw_source_exports']=raw_exports
            r['source_macro_packet'] = packet
            pre = compiler.pre_refill_barrel_screen(board, packet)
            r['pre_refill'] = pre
            if not pre['ok']:
                raise ValueError('pre_refill_native_barrel_refused')
            additive._ground_refill(board)
            native = compiler.native_pose_screen(parent, board, packet)
            r['native_pose'] = native
            if not native['ok']:
                raise ValueError('native_pose_refused')
            if a.mode == 'route':
                proof = macro.screen(source, board, packet, board_hint=a.board,
                    cooperative_conflict_negotiation=True)
                r['complete_route_screen'] = proof
                if proof['complete']:
                    escape.construct_private(board, proof['packet'], proof['selection'])
                    additive._ground_refill(board)
                    old = {force._uid(t) for t in parent.GetTracks()}
                    incoming = [t for t in board.GetTracks()
                        if force._uid(t) not in old and t.GetClass() == 'PCB_VIA']
                    if incoming:
                        fr.group_local_pofv_signal_vias(board, incoming)
                    candidate = force._copy_family(source, a.out/'UNADMITTED-family')
                    r['source_preserving_macro_save']=macro.save_private(board,candidate,packet)
                    additive.bind_local_via_rule(board, candidate)
                    r.update(candidate=str(candidate), candidate_sha256=force._hash(candidate))
                    r['independent_saved_receiving'] = macro.receive(source, candidate, **options)
                print(json.dumps(dict(complete=proof['complete'], errors=proof['errors'],
                    empty=proof.get('empty_obligations'),
                    saved=r.get('independent_saved_receiving', {}).get('ok')), default=str), flush=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        r['error'] = type(exc).__name__+':'+str(exc)
        r['failure_stack'] = traceback.format_exc()
        trace = exc.__traceback__
        while trace:
            local = trace.tb_frame.f_locals
            if trace.tb_frame.f_code.co_filename.endswith('cec_cell_macro_requests.py'):
                if trace.tb_frame.f_code.co_name=='compile':
                    r['failed_compilation_inventory']={key:local[key] for key in
                        ('proposal','transport','extras','requests') if key in local}
                if trace.tb_frame.f_code.co_name=='_compose_retained_demands':
                    item=local.get('t');pad=local.get('pad')
                    r['retained_composition_refusal'] = dict(request_id=local.get('key'),
                        request=local.get('request'),source_edge=dict(uuid=force._uid(item),
                            width_nm=int(item.GetWidth()),net=item.GetNetname(),
                            points_nm=[list(item.GetStart()),list(item.GetEnd())]) if item else None,
                        source_pad=dict(uuid=force._uid(pad),ref=pad.GetParentFootprint().GetReference(),
                            pin=pad.GetNumber(),at_nm=list(pad.GetPosition())) if pad else None)
            if trace.tb_frame.f_code.co_filename.endswith('cec_smd_macro_transport.py'):
                item = local.get('t')
                if item is not None and hasattr(item, 'GetClass'):
                    actual_source = local.get('source')
                    group = next((g for g in actual_source.Groups() if g.ContainsItem(item)), None)
                    r['transport_refusal_context'] = dict(uuid=force._uid(item),
                        native_class=item.GetClass(), net=item.GetNetname(),
                        group=group.GetName() if group else None,
                        group_uuid=force._uid(group) if group else None,
                        points=local.get('points'), displacements=local.get('ds'),
                        source_owned_dogbone=force._uid(item) in local.get('owned_dogbones', set()),
                        group_items=[dict(uuid=force._uid(i), native_class=i.GetClass())
                            for i in group.GetItems()] if group else [])
            trace = trace.tb_next
        print(r['failure_stack'], flush=True)
    r.update(code_unchanged=code == force._code_identity(),
        driver_unchanged=driver_hash==force._hash(Path(__file__)),
        plan_unchanged=r['plan_sha256'] == force._hash(a.plan),
        all_nine_families_unchanged=families == {
            key: force._family(Path(x['path']), key) for key, x in rows.items()},
        elapsed_s=time.monotonic()-started)
    assert r['code_unchanged'] and r['driver_unchanged'] and r['plan_unchanged'] and r['all_nine_families_unchanged']
    status,outcome=experiment_exit_status(r)
    r.update(exit_status=status,experiment_outcome=outcome)
    force._write(a.out/'receipt.json', r)
    print(json.dumps(dict(receipt=str(a.out/'receipt.json'), error=r.get('error'),
        elapsed_s=r['elapsed_s'],exit_status=status,outcome=outcome), default=str), flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
