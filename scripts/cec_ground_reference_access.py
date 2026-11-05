"""Source-derived stationary reference returns to actual grounded owner pins.

No net/refdes/coordinate exceptions, placement changes or power-bus edits.
An explicit manufacturer ground-reference role and independently connected
assigned bypass/true-ground component are required. This is an additive
private routing slice, never current, Kelvin, stack or release qualification.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_local_branch_access as access
import cec_placement_geometry as geometry
import cec_route_quality as craft
import cec_return_escape as return_escape
import cec_stage_admission as stage
import cec_support_pivot_receiving as support
import cec_constraints as constraints
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_route_dimensions as dimensions
import cec_native_track_prefix as prefix


def stranded_surface_ground_pads(board, *, ground_net='GND', timeout_s=2., limit=128):
    """Discover actual ground-pad islands even when DRC names their stub.

    Only positive native contact to a FILLED own-net zone counts as the plane
    reference. A reported via, nearby pour or THT body is not connectivity.
    This is discovery only, not authorization of a route or current rating.
    """
    if (type(ground_net) is not str or not ground_net
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(limit) is not int or not 1<=limit<=128):
        raise ValueError('bounded_stranded_ground_pad_discovery_required')
    deadline=time.monotonic()+timeout_s
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==ground_net]
    if not zones or any(not z.IsFilled() for z in zones):
        raise ValueError('actual_filled_ground_reference_required')
    pads=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==ground_net]
    material=[*pads,*[t for t in board.GetTracks() if t.GetNetname()==ground_net],*zones]
    if len(material)>16384:
        raise ValueError('stranded_ground_native_inventory_bound')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in material:
        if time.monotonic()>=deadline or not graph.Add(item):
            raise ValueError('stranded_ground_native_graph_unknown')
    zone_ids={force._uid(z) for z in zones}
    stranded=[]
    for pad in pads:
        if time.monotonic()>=deadline:
            raise ValueError('stranded_ground_native_graph_deadline')
        if return_escape.smd_surface_layer(pad) is None:
            continue
        reached={force._uid(i) for i in graph.GetConnectedItems(pad)}
        if not reached & zone_ids:
            stranded.append(force._uid(pad))
            if len(stranded)>limit:
                raise ValueError('stranded_ground_pad_inventory_bound')
    return sorted(stranded)


def assigned_ground_tasks(board, hint, *, timeout_s=2., limit=64):
    """Source-assigned IC grounds, including native dangling-stub islands.

    A ratsnest may name the stub rather than the ground pad. Independently
    compare real native components instead of requiring a pad-named airwire
    or an entirely bare terminal. Only explicit manufacturer ground roles
    and their own selected bypasses are eligible; never nearest-GND routing.
    This proves a construction opportunity, not an energized/rated plane or
    satisfaction of the owner's local ground-loop requirement.
    """
    if (type(timeout_s) not in (float, int) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(limit) is not int or not 1 <= limit <= 64):
        raise ValueError('bounded_assigned_ground_discovery_required')
    deadline = time.monotonic() + timeout_s
    with force._thermal_hint(hint):
        assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    selected = {}
    for row in assignment['assigned'].values():
        selected.setdefault(row['cap_ref'], []).append(row['requirement'])
    if sum(fp.GetPadCount() for fp in board.GetFootprints()) + len(list(board.GetTracks())) > 16384:
        raise ValueError('assigned_ground_inventory_budget')
    graph = fr._read_only_route_connectivity(board)
    floor = dimensions.board_limits(board)
    tasks = []
    for ref, requirements in sorted(selected.items()):
        if time.monotonic() >= deadline:
            raise ValueError('assigned_ground_discovery_deadline')
        if len(requirements) != 1:
            continue
        req = requirements[0]
        if (req.get('return_rail') or 'GND') != 'GND':
            continue
        owner = board.FindFootprintByReference(req['ref'])
        cap = board.FindFootprintByReference(ref)
        manufacturer = roles.footprint_contract(owner) if owner else None
        if not manufacturer or not cap:
            continue
        grounds = [p for p in cap.Pads() if p.GetNetname() == 'GND']
        if len(grounds) != 1 or return_escape.smd_surface_layer(grounds[0]) is None:
            continue
        target = grounds[0]
        with force._thermal_hint(hint):
            entry = cells._existing_return(board, target, 1.5)
        if entry is None:
            continue
        via = entry[1]
        diameter, drill = via.GetWidth(via.TopLayer()), via.GetDrillValue()
        blocked, _ = fab.via_at_pad_conflicts(board, via.GetPosition(), diameter, drill, via.GetNetCode())
        if (blocked is not None or diameter < round(floor['via_diameter']*1e6)
                or drill < round(floor['via_drill']*1e6)
                or diameter - drill < 2*round(floor['annular']*1e6)):
            continue
        reached = {force._uid(target)} | {force._uid(i) for i in graph.GetConnectedItems(target)}
        if force._uid(via) not in reached:
            continue
        for pad in owner.Pads():
            if time.monotonic() >= deadline:
                raise ValueError('assigned_ground_discovery_deadline')
            if (manufacturer['pins'].get(str(pad.GetNumber())) != 'ground'
                    or pad.GetNetname() != target.GetNetname() or pad.GetNetCode() != target.GetNetCode()
                    or return_escape.smd_surface_layer(pad) != return_escape.smd_surface_layer(target)
                    or sum(p.GetNumber() == pad.GetNumber() for p in owner.Pads()) != 1
                    or force._uid(pad) in reached
                    or math.dist(tuple(pad.GetPosition()), tuple(target.GetPosition())) > 3.5e6):
                continue
            with force._thermal_hint(hint):
                if cells._existing_return(board, pad, 1.5) is not None:
                    continue
            tasks.append(dict(owner=req['ref'], pin=str(pad.GetNumber()),
                role='manufacturer_ground', net=str(pad.GetNetname()), pad_uuid=force._uid(pad),
                cap=ref, cap_pad=str(target.GetNumber()), destination_uuid=force._uid(target),
                a_nm=list(pad.GetPosition()), b_nm=list(target.GetPosition()),
                qualified_existing_ground_via_uuid=force._uid(via),
                manufacturer_source=manufacturer['source'], local_ground_quality_qualified=False))
            if len(tasks) > limit:
                raise ValueError('assigned_ground_target_budget')
    if time.monotonic() >= deadline:
        raise ValueError('assigned_ground_discovery_deadline')
    return sorted(tasks, key=lambda row: (row['owner'], row['pin'], row['destination_uuid']))


def _tasks(board, hint):
    return [row for row in access.targets(board,board_hint=hint)
        if row['role']=='ground_reference' and row['verified_ground_alternatives']] + assigned_ground_tasks(board, hint)


def _destinations(task):
    """Two source-proved return choices, never a nearest arbitrary GND pad.

    targets() already independently proves the assigned bypass return is
    connected to the owner's manufacturer ground. Returning REF to either
    endpoint of that same grounded component is legitimate; always forcing
    a path through the package can unnecessarily cross its supply branch.
    """
    return access._destinations(task)


def _linear_returns(board,tasks,tracks,*,source_board=None):
    """Every new edge must be used by a simple exact endpoint return chain.

    Native ground connectivity alone would admit gratuitous nearby spurs or
    loops. The stationary compiler emits exact pad-centre endpoints; derive
    that obligation again here from the immutable source, not the packet.
    """
    by_endpoint={};by_uid={force._uid(t):t for t in tracks};used=set();gained=[]
    for t in tracks:
        if (t.GetClass()!='PCB_TRACK' or t.GetStart()==t.GetEnd()
                or t.GetWidth()!=max(board.GetDesignSettings().m_TrackMinWidth,
                    int(cells._netclass(board,t.GetNetname())['width']))):
            raise ValueError('reference_return_requires_full_class_nonzero_straight_tracks')
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
            by_endpoint.setdefault((t.GetNetname(),t.GetLayer(),at),[]).append(force._uid(t))
    for task in tasks:
        for destination in _destinations(task):
            origin=tuple(task['a_nm']);target=tuple(destination['at_nm'])
            # PAD.GetLayer() can retain its default face after a native flip;
            # the actual enabled SMD copper layer-set owns the return chain.
            origin_pad=board.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
            layer=return_escape.smd_surface_layer(origin_pad)
            if layer is None:raise ValueError('reference_return_requires_one_native_surface')
            origins=[origin]
            if task['role']=='manufacturer_ground':
                if source_board is None:raise ValueError('immutable_source_ground_boundary_required')
                old_pad=source_board.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
                graph=fr._read_only_route_connectivity(source_board)
                old_tracks=[t for t in graph.GetConnectedItems(old_pad) if t.GetClass()=='PCB_TRACK'
                    and t.GetNetCode()==old_pad.GetNetCode() and t.GetLayer()==layer]
                del graph
                origins += sorted({at for (net,lay,at),edges in by_endpoint.items()
                    if net==task['net'] and lay==layer and len(edges)==1 and any(
                        old.GetWidth()>=by_uid[edges[0]].GetWidth() and prefix.on_centerline(at,old)
                        for old in old_tracks)})
            found=False
            for seat in origins:
                cursor=seat;chain=[];length=0.
                while cursor!=target:
                    choices=[u for u in by_endpoint.get((task['net'],layer,cursor),[]) if u not in chain]
                    if len(choices)!=1:break
                    uid=choices[0];t=by_uid[uid];chain.append(uid);length+=t.GetLength()/1e6
                    if len(chain)>64 or length>4.:break
                    cursor=tuple(t.GetEnd()) if tuple(t.GetStart())==cursor else tuple(t.GetStart())
                if cursor==target and chain and length<=4.:
                    final_path=(cells._shortest_track_path_mm(board,origin_pad,
                        board.FindFootprintByReference(destination['ref']).FindPadByNumber(destination['pin']))
                        if task['role']=='manufacturer_ground' else length)
                    if final_path is None or final_path>4.:continue
                    used.update(chain);gained.append(dict(task=task,destination=destination,
                        saved_native_path_mm=final_path,new_linear_track_uuids=chain,
                        source_component_boundary_nm=list(seat)));found=True;break
            if found:break
    if set(by_uid)!=used:raise ValueError('reference_addition_contains_spur_cycle_branch_or_wrong_endpoint')
    return gained


def receive(source,candidate,*,board_hint,timeout_s=10.):
    result=dict(schema=1,ok=False,complete=False,errors=[],release_authority=False,
        routing_admitted=False,current_authority=False,kelvin_qualified=False)
    try:
        if type(timeout_s) not in (float,int) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('bounded_ground_reference_receiving_required')
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        families=[force._family(p,board_hint) for p in (source,candidate)]
        epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        tasks=_tasks(parent,board_hint)
        if not tasks:raise ValueError('source_verified_ground_reference_tasks_required')
        delta=additive.receive(source,candidate,timeout_s=timeout_s)
        result['independent_exact_additive_receiving']=delta
        if not delta['ok'] or not delta['complete']:raise ValueError('ground_reference_additive_receiving_refused')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        incoming=set(new)-set(old)
        tracks=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 1<=len(tracks)==len(incoming)<=64:raise ValueError('bounded_track_only_reference_additions_required')
        if any(t.GetClass()!='PCB_TRACK' or t.GetNetname() not in {r['net'] for r in tasks} for t in tracks):
            raise ValueError('unexpected_reference_return_material')
        gained=_linear_returns(child,tasks,tracks,source_board=parent)
        if not gained:raise ValueError('no_source_isolated_reference_return_gain')
        result['gained_references'] = gained
        # Every new segment must be in a gained source-local return, not an
        # arbitrary extra ground route smuggled into a favourable open count.
        graph=fr._read_only_route_connectivity(child)
        reached=set()
        for row in gained:
            task=row['task'];pad=child.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
            reached|={force._uid(i) for i in graph.GetConnectedItems(pad)}
        if not incoming<=reached:raise ValueError('reference_addition_has_unconnected_extra_copper')
        for track in tracks:
            endpoints=(tuple(track.GetStart()),tuple(track.GetEnd()))
            if not any(track.GetNetname()==r['task']['net'] and all(
                min(math.dist(at,r['task']['a_nm']),math.dist(at,r['destination']['at_nm']))<=4e6
                for at in endpoints) for r in gained):
                raise ValueError('reference_addition_outside_source_locality')
        physical=geometry.evaluate(candidate,timeout_s=timeout_s)
        result['physical_placement']=physical
        if not physical['ok']:raise ValueError('reference_return_physical_placement_refused')
        quality=craft.analyze_board(child,track_uuid_scope=incoming)
        result['craft']=quality
        if not quality['craft_ok']:raise ValueError('reference_return_craft_refused')
        with tempfile.TemporaryDirectory(prefix='cec-ground-reference-receiving-') as work:
            work=Path(work);grades=[]
            for name,path in [('source',source),('candidate',candidate)]:
                private=force._copy_family(path,work/name);output=work/(name+'.json')
                run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all',
                    '--output',str(output),str(private)],capture_output=True,text=True,timeout=timeout_s)
                if run.returncode:raise ValueError('reference_return_native_drc_failed')
                grades.append(json.loads(output.read_text()))
        before,after=grades
        known={stage._canonical_identity(v) for v in before['violations']}
        inventories=(support._silk_inventory(parent,old),support._silk_inventory(child,new))
        faults=[];inherited=[]
        for finding in after['violations']:
            if stage._canonical_identity(finding) in known:continue
            proof=support._inherited_silk_overlap(parent,child,finding,old,new,inventories=inventories)
            (inherited if proof else faults).append(proof or finding)
        result.update(source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),
            raw_drc=len(after['violations']),new_native_faults=faults,
            positively_proved_inherited_silk_collisions=inherited,gained_references=gained)
        if faults or result['opens']>=result['source_opens']:raise ValueError('no_nonregressing_saved_reference_closure')
        with force._thermal_hint(board_hint):
            original=field.field_coupling_summary(str(source),board=parent)
            updated=field.field_coupling_summary(str(candidate),board=child)
        field_new=sorted(field.blocker_keys(updated)-field.blocker_keys(original))
        result['new_field_blockers']=field_new
        if field_new:raise ValueError('reference_return_new_field_blockers')
        stable=families==[force._family(p,board_hint) for p in (source,candidate)] and epoch==force._code_identity()
        if not stable:raise ValueError('reference_return_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            exact_parent_material_and_poses_preserved=True,board=str(candidate),board_sha256=force._hash(candidate),
            full_current_kelvin_stack_and_release_receiving_still_required=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,directory,*,board_hint,source_sha256,timeout_s=10.):
    if type(timeout_s) not in (float,int) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_reference_return_search_required')
    source,directory=map(lambda p:Path(p).resolve(),(source,directory))
    if directory.exists() or force._hash(source)!=source_sha256:
        raise ValueError('fresh_reference_output_and_exact_source_required')
    families=force._family(source,board_hint);epoch=force._code_identity();directory.mkdir(parents=True)
    board=pcbnew.LoadBoard(str(source));report=dict(schema=1,ok=False,source=str(source),
        source_sha256=source_sha256,routing_admitted=False,release_authority=False,trials=[])
    immutable=pcbnew.LoadBoard(str(source))
    old={force._uid(t) for t in board.GetTracks()};deadline=time.monotonic()+timeout_s
    for task in _tasks(board,board_hint)[:8]:
        owner=board.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
        for destination in _destinations(task):
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            target=board.FindFootprintByReference(destination['ref']).FindPadByNumber(destination['pin'])
            diagnostics={}
            with force._thermal_hint(board_hint):
                link,error=cells._add_supply_link(board,owner,target,lock=True,
                    link_role='shared-ground-entry',diagnostics=diagnostics,search_timeout_s=min(2.,remaining),
                    refine_maze=task['role']=='manufacturer_ground')
            clipped=None
            if link is not None and task['role']=='manufacturer_ground' and link.get('items'):
                clipped=prefix.clip(immutable,board,task['pad_uuid'],link['items'])
            report['trials'].append(dict(task=task,destination=destination,error=error,
                link={k:v for k,v in (link or {}).items() if k!='items'},diagnostics=diagnostics,
                source_prefix_clipping=clipped))
            if link is not None:break
    incoming={force._uid(t) for t in board.GetTracks()}-old
    report['created_uuids']=sorted(incoming)
    if incoming:
        child=force._copy_family(source,directory/'candidate')
        additive._ground_refill(board);field._save_field_snapshot(board,child)
        report.update(proposed_board=str(child), proposed_board_sha256=force._hash(child),
            proposed_board_is_not_admitted=True)
        report['receiving']=receive(source,child,board_hint=board_hint,timeout_s=timeout_s)
        if report['receiving']['ok']:
            report.update(ok=True,board=str(child),board_sha256=force._hash(child),
                source_opens=report['receiving']['source_opens'],opens=report['receiving']['opens'])
    stable=families==force._family(source,board_hint) and epoch==force._code_identity()
    report['source_family_and_code_unchanged']=stable;report['ok']&=stable
    force._write(directory/'receiving.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-sha256',required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--hint',required=True);args=parser.parse_args()
    report=run(args.source,args.out,board_hint=args.hint,source_sha256=args.source_sha256)
    print(json.dumps({k:report.get(k) for k in ('ok','source_opens','opens','board','source_family_and_code_unchanged')}))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
