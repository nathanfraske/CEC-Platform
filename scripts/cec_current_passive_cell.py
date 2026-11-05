"""Complete bounded reconstruction of detached series-current passives.

Every moved land must join its actual opposite Source aggregate authority
with unchanged full-current geometry. No old copper, pour, part, barrel or
pinout may be retired. This uses the existing independent Source-pose and
additive saved receiver; constructing a private result never admits it.
"""
import json
import math
from pathlib import Path
import subprocess
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_complete_cell_receiving as paths
import cec_decoupler_cell as cells
import cec_detached_current_passive_pose as passive
import cec_force_current as force
import cec_ground_return_preservation as ground
import cec_pose_additive_reconstruction as pose_receiving
import cec_protector_cell as ports
from cec_source_current_ports import full_width_connection as _full_width_connection


SCOPE='source_complete_detached_current_passive_cell-v1'


def _deadline(seconds):
    if type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10.:
        raise ValueError('bounded_current_passive_constituent_required')
    return time.monotonic()+seconds


def _left(deadline):
    left=deadline-time.monotonic()
    if left<=0:raise ValueError('current_passive_constituent_deadline')
    return min(10.,left)


def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def compile(source,poses,*,board_hint,max_shift_mm=6.,timeout_s=10.):
    deadline=_deadline(timeout_s)
    q=passive.plan(source,poses,board_hint=board_hint,max_shift_mm=max_shift_mm,timeout_s=_left(deadline))
    parent=pcbnew.LoadBoard(q['source']);private=pcbnew.LoadBoard(q['source'])
    passive.apply(private,q)
    selected={r['ref']for r in q['records']};requests={}
    for record in q['records']:
        fp=private.FindFootprintByReference(record['ref'])
        for domain in record['current_domains']:
            _left(deadline);data=domain['domain'];ref=record['ref']
            is_source=ref in data['source_refs'];is_sink=ref in data['sink_refs']
            if is_source==is_sink:raise ValueError('exclusive_actual_passive_aggregate_terminal_role_required')
            opposite=data['sink_refs']if is_source else data['source_refs']
            if set(opposite)&selected:raise ValueError('fixed_opposite_current_authority_ports_required')
            inventory=ports._aggregate_ports(parent,Path(q['source']),domain['net'],
                dict(source_refs=opposite),domain['contract'],deadline)
            pad=fp.FindPadByNumber(domain['pin'])
            candidates=[*inventory['root_ports'],*[ports._stroke_port(s,tuple(pad.GetPosition()))
                for s in inventory['retained_full_width_strokes']]]
            target=min(candidates,key=lambda p:(math.dist(p['at_nm'],tuple(pad.GetPosition())),
                p.get('pad_uuid',''),p.get('native_uuids',[])))
            face=int(next(iter(pad.GetLayerSet().CuStack())))
            width=ports.full._source_width_floor(parent,Path(q['source']),domain['contract'],face)
            with force._thermal_hint(board_hint):current=cells._supply_current_widths(parent,domain['net'])
            if current is None or current['current_authority']!=domain['contract']['current_authority']:
                raise ValueError('unchanged_complete_passive_current_contract_required')
            key=record['footprint_uuid']+':'+domain['pin']
            requests[key]=dict(kind='source_boundary',net=domain['net'],a=ports._port(pad),b=target,
                width_nm=width,unchanged_full_rail_current_contract=current,
                every_surviving_source_component_port_mandatory=True,
                exact_moved_passive_pin=dict(footprint_uuid=record['footprint_uuid'],pin=domain['pin']),
                actual_opposite_current_authority_refs=opposite)
    screen=ports._screen(private,selected,deadline)
    result=dict(schema=1,scope=SCOPE,source=q['source'],source_sha256=q['source_sha256'],
        board_hint=board_hint,source_family=q['source_family'],code_identity=q['code_identity'],
        pose_plan=q,requests=requests,pose_screen=screen,projected_native_binding=row._source_binding(private),
        every_moved_pin_is_mandatory=True,no_source_copper_retirement=True,
        complete_saved_receiving_still_required=True,routing_admitted=False,current_qualified=False,release_authority=False)
    if force._code_identity()!=q['code_identity']or force._family(Path(q['source']),board_hint)!=q['source_family']:
        raise ValueError('current_passive_compile_source_or_code_changed')
    _left(deadline)
    return private,_stable(result)


def construct(proposal,*,timeout_s=10.):
    _deadline(timeout_s)
    report=dict(schema=1,scope='private_complete_detached_current_passive_construction',complete=False,
        phases={},errors=[],per_constituent_limit_s=timeout_s,maximum_constituents=4,
        partial_candidate_emitted=False,routing_admitted=False,current_qualified=False,release_authority=False)
    start=phase_started=time.monotonic();stage='source_compilation';deadline=phase_started+timeout_s
    try:
        if type(proposal)is not dict or proposal.get('scope')!=SCOPE:
            raise ValueError('typed_complete_current_passive_proposal_required')
        p=proposal['pose_plan'];request=p['request']
        board,q=compile(proposal['source'],request['poses'],board_hint=proposal['board_hint'],
            max_shift_mm=request['max_shift_mm'],timeout_s=_left(deadline))
        if _stable(q)!=_stable(proposal):raise ValueError('stale_or_forged_complete_current_passive_proposal')
        if not q['pose_screen']['ok']:raise ValueError('current_passive_native_pose_screen_refused')
        _left(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started)
        stage='connection_menus';phase_started=time.monotonic();deadline=phase_started+timeout_s
        parent=pcbnew.LoadBoard(q['source'])
        menu=escape.menus(board,q['requests'],board_path=q['source'],board_hint=q['board_hint'],
            timeout_s=_left(deadline),include_power_layer=True,source_board=parent)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,menu=menu)
        if set(menu['domains'])!=set(q['requests'])or any(not v for v in menu['domains'].values()):
            raise ValueError('every_current_passive_pin_needs_a_guarded_connection_menu')
        _left(deadline)
        stage='complete_joint_selection';phase_started=time.monotonic();deadline=phase_started+timeout_s
        selection=escape.choose(board,menu,timeout_s=_left(deadline))
        if not selection['complete']:raise ValueError('complete_current_passive_selection_refused')
        incoming=escape.construct_private(board,menu,selection)
        connected={key:_full_width_connection(parent,board,q['source'],r,q['board_hint'],deadline)
            for key,r in q['requests'].items()}
        if any(v is None or not v['all_named_contacts_connected']or not v['zone_and_foreign_net_edges_excluded']
                for v in connected.values()):raise ValueError('every_current_passive_named_endpoint_connection_required')
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,selection=selection,
            named_endpoints=connected,added_native_uuids=[force._uid(t)for t in incoming])
        _left(deadline)
        stage='final_paths_and_ground';phase_started=time.monotonic();deadline=phase_started+timeout_s
        additive._ground_refill(board)
        received=paths._receive_paths(parent,board,q['requests'],{force._uid(t)for t in incoming},q['board_hint'],deadline,
            received_barrel_uuids=[force._uid(t)for t in incoming if t.GetClass()=='PCB_VIA'])
        returns=ground.receive(parent,board,timeout_s=_left(deadline))
        if not returns['ok']or not returns['complete']:raise ValueError('current_passive_ground_return_preservation_refused')
        for key,r in q['requests'].items():
            result=_full_width_connection(parent,board,q['source'],r,q['board_hint'],deadline)
            if result is None or not result['all_named_contacts_connected']or not result['zone_and_foreign_net_edges_excluded']:
                raise ValueError('current_passive_final_named_connection_lost:'+key)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,paths=received,all_source_ground_returns=returns)
        if force._code_identity()!=q['code_identity']or force._family(Path(q['source']),q['board_hint'])!=q['source_family']:
            raise ValueError('current_passive_construction_source_or_code_changed')
        _left(deadline)
        report.update(complete=True,elapsed_s=time.monotonic()-start,proposal=q,
            independent_original_parent_saved_receiving_still_required=True)
        return board,report
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,subprocess.TimeoutExpired)as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
        report['phases'].setdefault(stage,{})['elapsed_s']=time.monotonic()-phase_started
        report.update(failed_stage=stage,elapsed_s=time.monotonic()-start,no_path_proof=False)
        return None,report


def receive(source,candidate,proposal,*,timeout_s=10.):
    """Independent Source pose/additions/partitions, then named current ports.

    Whole-board native DRC, all original current debt, field, Kelvin,
    parity and stack receiving are still separate mandatory enclosing gates.
    """
    _deadline(timeout_s)
    report=dict(schema=1,scope='saved_complete_current_passive_cell',ok=False,complete=False,
        errors=[],phases={},per_constituent_limit_s=timeout_s,maximum_constituents=3,
        routing_admitted=False,current_qualified=False,release_authority=False)
    stage='source_recompile';begun=phase_started=time.monotonic()
    try:
        deadline=phase_started+timeout_s
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate or type(proposal)is not dict or proposal.get('scope')!=SCOPE:
            raise ValueError('distinct_saved_complete_current_passive_context_required')
        p=proposal['pose_plan'];r=p['request']
        _,q=compile(source,r['poses'],board_hint=proposal['board_hint'],max_shift_mm=r['max_shift_mm'],timeout_s=timeout_s)
        if _stable(q)!=_stable(proposal):raise ValueError('saved_current_passive_fresh_proposal_mismatch')
        if not q['pose_screen']['ok']:raise ValueError('saved_current_passive_native_pose_screen_refused')
        code=force._code_identity();families=[force._family(p,q['board_hint'])for p in(source,candidate)]
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started)
        _left(deadline)
        stage='exact_source_pose_additions';phase_started=time.monotonic();deadline=phase_started+timeout_s
        receipt=pose_receiving.receive(source,candidate,selected_footprint_uuids=[r['footprint_uuid']for r in p['records']],
            board_hint=q['board_hint'],max_shift_mm=r['max_shift_mm'],timeout_s=timeout_s)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,receiving=receipt)
        if not receipt['ok']or not receipt['complete']:raise ValueError('current_passive_independent_saved_pose_receiving_refused')
        _left(deadline)
        stage='saved_current_paths_and_returns';phase_started=time.monotonic();deadline=phase_started+timeout_s
        parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        for record in q['pose_plan']['records']:
            fp=next((f for f in child.GetFootprints()if force._uid(f)==record['footprint_uuid']),None)
            if fp is None or [fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]!=record['target_pose']:
                raise ValueError('saved_current_passive_pose_differs_from_exact_request')
        old={force._uid(t)for t in parent.GetTracks()};new={force._uid(t):t for t in child.GetTracks()if force._uid(t)not in old}
        received=paths._receive_paths(parent,child,q['requests'],set(new),q['board_hint'],deadline,
            received_barrel_uuids=[u for u,t in new.items()if t.GetClass()=='PCB_VIA'])
        for key,r in q['requests'].items():
            result=_full_width_connection(parent,child,source,r,q['board_hint'],deadline)
            if result is None or not result['all_named_contacts_connected']or not result['zone_and_foreign_net_edges_excluded']:
                raise ValueError('saved_current_passive_named_endpoint_connection_required:'+key)
        returns=ground.receive(parent,child,timeout_s=_left(deadline))
        if not returns['ok']or not returns['complete']:raise ValueError('saved_current_passive_ground_return_preservation_refused')
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,paths=received,all_source_ground_returns=returns)
        if code!=force._code_identity()or families!=[force._family(p,q['board_hint'])for p in(source,candidate)]:
            raise ValueError('saved_current_passive_source_candidate_or_code_changed')
        _left(deadline)
        report.update(ok=True,complete=True,elapsed_s=time.monotonic()-begun,
            independent_whole_board_native_current_field_Kelvin_parity_and_stack_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,subprocess.TimeoutExpired)as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc));report.update(failed_stage=stage,elapsed_s=time.monotonic()-begun)
    return report
