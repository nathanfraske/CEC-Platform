"""Bounded source-typed EN-to-IN local control links, not power distribution.

An immutable selected manufacturer/package and actual EN==IN netlist own the
task. IN must already have a native conductor; EN must be wholly isolated.
Replay a simple class-width path with process-qualified local vias, preserving
every existing copper item and partition. No rail budget, force path, placement,
zone outline, current/Kelvin or release gate is changed or qualified here.
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
import cec_device_power_roles as roles
import cec_current_debt as current_debt
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_placement_geometry as geometry
import cec_return_escape as escape
import cec_route_quality as craft
import cec_search_budget as search_budget
import cec_stage_admission as stage
import cec_support_pivot_receiving as support
import cec_native_component_ports as native_ports


def _budget(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10:
        raise ValueError('bounded_tied_control_budget_required')
    return value


def targets(board):
    graph=fr._read_only_route_connectivity(board);result=[]
    for fp in board.GetFootprints():
        model=roles.tied_enable_contract(fp)
        if not model:continue
        ends=[]
        for key in ('enable_pin','input_pin'):
            pads=[p for p in fp.Pads() if str(p.GetNumber())==model[key]]
            if len(pads)!=1:break
            ends.append(pads[0])
        if len(ends)!=2:continue
        enable,supply=ends
        layer=escape.smd_surface_layer(enable)
        if (enable.HasHole() or supply.HasHole() or layer is None
                or escape.smd_surface_layer(supply)!=layer or enable.GetNetCode()<=0
                or enable.GetNetCode()!=supply.GetNetCode()
                or math.dist(force._point(enable),force._point(supply))>3.5e6
                or not support.source_land_isolated(board,enable,graph)):
            continue
        connected=list(graph.GetConnectedItems(supply))
        if not any(i.GetClass() in ('PCB_TRACK','PCB_VIA','ZONE') for i in connected):continue
        result.append(dict(owner=fp.GetReference(),pin=model['enable_pin'],input_pin=model['input_pin'],
            pad_uuid=force._uid(enable),input_uuid=force._uid(supply),net=str(enable.GetNetname()),
            a_nm=list(enable.GetPosition()),b_nm=list(supply.GetPosition()),layer=layer,manufacturer=model))
    return sorted(result,key=lambda row:(row['pad_uuid'],row['input_uuid']))


def _capture_sites(board,task,*,deadline):
    """Finite exact contacts on the selected IN's existing native island.

    A same-net name alone never grants a landing. Discovery is bound to the
    selected manufacturer IN, at most 2 mm from that terminal; the independent
    saved receiver regenerates this menu from SOURCE, not the constructed PCB.
    """
    owner=board.FindFootprintByReference(task['owner'])
    supply=owner.FindPadByNumber(task['input_pin'])
    root=dict(at_nm=list(supply.GetPosition()),
        layers=[int(layer) for layer in supply.GetLayerSet().CuStack()],
        native_uuids=[task['input_uuid']],pad_uuid=task['input_uuid'])
    return native_ports.endpoints(board,task['net'],root,toward_nm=task['a_nm'],
        max_sites=16,max_shift_mm=2.,deadline=deadline,diverse_native_sites=True,
        prefer_native_via_access=True)


def _simple_paths(board,tasks,incoming,*,source_board,deadline=None):
    """Use every new edge in one EN-to-proved-IN-island chain, not a spur."""
    deadline=time.monotonic()+10. if deadline is None else deadline
    used=set();gained=[]
    for task in tasks:
        tracks=[t for t in incoming if t.GetNetname()==task['net']]
        origin=tuple(task['a_nm'])
        if not any((t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==origin and t.IsOnLayer(task['layer']))
                or (t.GetClass()=='PCB_TRACK' and t.GetLayer()==task['layer'] and origin in
                    (tuple(t.GetStart()),tuple(t.GetEnd()))) for t in tracks):
            continue  # Another untouched same-net EN is not this received path.
        width=max(board.GetDesignSettings().m_TrackMinWidth,int(cells._netclass(board,task['net'])['width']))
        vertices={};edges={};vias=[];planar=0.
        def edge(uid,a,b):
            if a==b:raise ValueError('control_link_zero_length_or_duplicate_transition')
            edges[uid]=(a,b)
            for v in (a,b):vertices.setdefault(v,[]).append(uid)
        for item in tracks:
            uid=force._uid(item)
            if item.GetClass()=='PCB_VIA':
                allowed,reason=fab.local_pofv_via_decision(board,item)
                if not allowed:raise ValueError('control_link_local_via_unqualified:'+str(reason))
                vias.append(item);continue
            if item.GetClass()!='PCB_TRACK' or item.GetWidth()!=width:
                raise ValueError('control_link_requires_full_class_straight_tracks')
            planar+=item.GetLength()/1e6
            edge(uid,(*item.GetStart(),item.GetLayer()),(*item.GetEnd(),item.GetLayer()))
        start=(*task['a_nm'],task['layer'])
        captures=_capture_sites(source_board,task,deadline=deadline)
        endings={(*site['at_nm'],layer) for site in captures for layer in site['layers']}
        vertices.setdefault(start,[])
        for end in endings:vertices.setdefault(end,[])
        for via in vias:
            xy=tuple(via.GetPosition());faces=sorted(v for v in vertices
                if v[:2]==xy and via.IsOnLayer(v[2]))
            if len(faces)!=2:raise ValueError('control_link_barrel_not_two_active_face_transition')
            edge(force._uid(via),*faces)
        if not tracks or planar>4. or len(vias)>2:continue
        cursor=start;chain=[]
        while cursor not in endings:
            expected=1 if cursor==start else 2
            if len(vertices.get(cursor,[]))!=expected:break
            options=[u for u in vertices[cursor] if u not in chain]
            if len(options)!=1:break
            uid=options[0];chain.append(uid);a,b=edges[uid];cursor=b if cursor==a else a
            if len(chain)>64:break
        if cursor in endings and len(vertices[cursor])==1 and set(chain)==set(edges):
            used.update(chain);gained.append(dict(task=task,path_mm=planar,item_uuids=chain,
                retained_input_capture=next(site for site in captures
                    if tuple(site['at_nm'])==cursor[:2] and cursor[2] in site['layers'])))
    if used!={force._uid(i) for i in incoming}:raise ValueError('control_link_has_spur_cycle_branch_or_wrong_endpoint')
    return gained


def _construct_control_leaf(board,task,*,deadline):
    """A positively typed EN leaf is not a capacitor's full-load supply link.

    Use the receiver's existing 4 mm simple-chain bound during construction.
    The bypass-link heuristic (1.4 times pin separation) excluded the legal
    route around the intervening NC land before search even began. Exact
    SOURCE input-island contacts and at most two independently qualified
    local vias are alternatives; no guessed current or neckdown is permitted.
    Source/current receiving still owns acceptance of the resulting leaf.
    """
    if not any(row==task for row in targets(board)):
        raise ValueError('fresh_selected_manufacturer_control_task_required')
    owner=board.FindFootprintByReference(task['owner'])
    enable=owner.FindPadByNumber(task['pin']);supply=owner.FindPadByNumber(task['input_pin'])
    spec=cells._netclass(board,task['net'])
    width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
    clearance=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
    diagnostics=dict(scope='source_typed_control_leaf_not_supply_distribution',
        width_nm=width,clearance_nm=clearance,max_length_mm=4.,
        manufacturer_maximum_current_unknown=True,current_qualified=False)
    def construction(ops):
        made=[]
        for op in ops:
            if op[0]=='trk':
                _kind,a,b,w,layer=op
                track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I(*a));track.SetEnd(pcbnew.VECTOR2I(*b))
                track.SetWidth(w);track.SetLayer(layer)
            elif op[0]=='via':
                _kind,at,drill,diameter=op
                track=pcbnew.PCB_VIA(board);track.SetPosition(pcbnew.VECTOR2I(*at))
                track.SetDrill(fr._nm(drill));track.SetWidth(fr._nm(diameter))
                track.SetViaType(pcbnew.VIATYPE_THROUGH);track.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            else:raise ValueError('control_leaf_unknown_native_operation')
            track.SetNetCode(enable.GetNetCode());track.SetLocked(True)
            board.Add(track);made.append(track)
        return made
    def retained_heading_clear(ops):
        # A path ending at the input pin from the wrong direction can overlap
        # its existing supply escape. Evaluate the complete native proposal,
        # including retained headings, before choosing it; do not accept a
        # backtracking stub just because it closes an airwire.
        tracks=[op for op in ops if op[0]=='trk'];vias=[op for op in ops if op[0]=='via']
        if (len(vias)>2 or any(op[3]!=width for op in tracks)
                or sum(math.dist(tuple(op[1]),tuple(op[2])) for op in tracks)>4000000):return False
        proof=craft.assess_proposed_route(board,[dict(net=task['net'],layer=layer,
            start_nm=list(a),end_nm=list(b),width_nm=w) for _kind,a,b,w,layer in tracks],deadline=deadline)
        return proof['ok'] is True and proof['complete'] is True
    captures=_capture_sites(board,task,deadline=deadline)
    diagnostics['source_input_capture_sites']=captures
    ops=None
    # Fund the finite native landing portfolio before spending the lease on
    # a maze aimed at one buried package pin. No site gains inferred access.
    for site in captures:
        if time.monotonic()>=deadline:break
        if task['layer'] not in site['layers']:continue
        legs=fr._guarded_profiled_lastmile_legs(board,enable.GetPosition(),pcbnew.VECTOR2I(*site['at_nm']),
            width,task['layer'],clearance,enable.GetNetCode(),
            lambda a,b,half:fr._edge_leg_clear(board,a,b,half+clearance),
            allow_maze=False,canonical_only=True,deadline_monotonic=deadline,max_length_nm=4000000,
            path_validator=lambda path:retained_heading_clear([('trk',a,b,w,task['layer']) for a,b,w in path]))
        if legs:ops=[('trk',a,b,w,task['layer']) for a,b,w in legs];break
    allowed=fr._lastmile_route_layers(board,net_name=task['net'],spec=spec,exclude_front=False)
    if not ops:
        bridge_trials=[]
        bridge_sites=sorted(enumerate(captures),
            key=lambda row:(not row[1].get('native_via_access',False),row[0]))
        for _index,site in bridge_sites[:4]:
            if time.monotonic()>=deadline:break
            trial_deadline=min(deadline,time.monotonic()+.45)
            detail={}
            with search_budget.scoped(1024):
                ops=fr._lastmile_bridge(board,task['a_nm'],[task['layer']],site['at_nm'],site['layers'],
                    width,enable.GetNetCode(),allowed,clearance,
                    dia=max(.6,float(spec['via_dia'])),drill=max(.3,float(spec['via_drill'])),
                    seat_limit=1,leg_ok=lambda a,b,h:fr._edge_leg_clear(board,a,b,h+clearance),
                    allow_maze=False,deadline_monotonic=trial_deadline,max_length_nm=4000000,
                    ops_ok=retained_heading_clear,diagnostics=detail,multilayer_lays=allowed,
                    max_seat_radius_mm=4.,middle_max_vias=2,refine_stubs=True)
            bridge_trials.append(dict(capture=site,found=bool(ops),search=detail))
            if ops:break
        diagnostics['native_capture_bridge_trials']=bridge_trials
    with search_budget.scoped(4096) as work:
        if not ops and time.monotonic()<deadline:
            legs=fr._guarded_profiled_lastmile_legs(board,enable.GetPosition(),supply.GetPosition(),
                width,task['layer'],clearance,enable.GetNetCode(),
                lambda a,b,half:fr._edge_leg_clear(board,a,b,half+clearance),
                allow_maze=True,refine_maze=True,deadline_monotonic=deadline,
                max_length_nm=4000000,
                path_validator=lambda path:retained_heading_clear([('trk',a,b,w,task['layer']) for a,b,w in path]))
            if legs:ops=[('trk',a,b,w,task['layer']) for a,b,w in legs]
        diagnostics['search_work']=work.report()
    if not ops:return None,'bounded_control_leaf_search_unproved',diagnostics
    items=construction(ops)
    return dict(status='typed-control-leaf',items=items,width_mm=width/1e6,
        length_mm=sum(t.GetLength() for t in items if t.GetClass()=='PCB_TRACK')/1e6,
        max_local_mm=4.,vias=sum(t.GetClass()=='PCB_VIA' for t in items)),None,diagnostics


def receive(source,candidate,*,board_hint,timeout_s=10.):
    result=dict(schema=1,ok=False,complete=False,errors=[],routing_admitted=False,
        branch_current_qualified=False,rail_current_qualified=False,kelvin_qualified=False,
        release_authority=False,manufacturer_maximum_current_unknown=True)
    try:
        _budget(timeout_s)
        if type(board_hint) is not str or not board_hint:raise ValueError('bound_control_board_identity_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        tasks=targets(parent)
        if not tasks:raise ValueError('source_typed_isolated_supply_tied_enable_required')
        exact=additive.receive(source,candidate,timeout_s=timeout_s);result['exact_additive_receiving']=exact
        if not exact['ok'] or not exact['complete']:raise ValueError('control_link_exact_additive_receiving_refused')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        added=set(new)-set(old);incoming=[t for t in child.GetTracks() if force._uid(t) in added]
        if not 1<=len(incoming)<=64:raise ValueError('bounded_control_link_material_required')
        groups=[g for g in child.Groups() if force._uid(g) in added]
        if any(g.GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP or any(
                i.GetClass()!='PCB_VIA' or force._uid(i) not in added for i in g.GetItems()) for g in groups):
            raise ValueError('control_link_unexpected_ownership_group')
        if ({force._uid(t) for t in incoming}|{force._uid(g) for g in groups})!=added:
            raise ValueError('control_link_unexpected_added_material')
        gained=_simple_paths(child,tasks,incoming,source_board=parent,
            deadline=time.monotonic()+timeout_s);result['gained_controls']=gained
        if not gained:raise ValueError('no_source_typed_control_link_gain')
        # Reject an unintended second supply/consumer component, even on the
        # same net. A short EN stub is not permission to build a power trunk.
        deadline=time.monotonic()+timeout_s;parts=ordinary._partition(parent,deadline)
        prior=fr._read_only_route_connectivity(parent);final=fr._read_only_route_connectivity(child)
        for row in gained:
            task=row['task'];fp=parent.FindFootprintByReference(task['owner'])
            supply=fp.FindPadByNumber(task['input_pin'])
            allowed={force._uid(supply),task['pad_uuid']}|{force._uid(i) for i in prior.GetConnectedItems(supply)}
            after=child.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
            reached={force._uid(i) for i in final.GetConnectedItems(after)}
            if (reached & set(old))-allowed:raise ValueError('control_link_acquired_unowned_source_component')
            if not set(row['item_uuids'])<=reached:raise ValueError('control_link_contains_disconnected_new_material')
        retained=set().union(*parts);updated=ordinary._partition(child,deadline,retained_keys=retained)
        if any(not any(p<=q for q in updated) for p in parts):raise ValueError('control_link_lost_source_partition')
        result['physical']=geometry.evaluate(candidate,timeout_s=timeout_s)
        result['craft']=craft.analyze_board(child,track_uuid_scope={force._uid(i) for i in incoming})
        if not result['physical']['ok'] or not result['craft']['craft_ok']:raise ValueError('control_link_physical_or_craft_refused')
        with tempfile.TemporaryDirectory(prefix='cec-control-link-receiving-') as work:
            work=Path(work);grades=[]
            for name,path in [('source',source),('candidate',candidate)]:
                private=force._copy_family(path,work/name);output=work/(name+'.json')
                run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all','--output',str(output),str(private)],
                    capture_output=True,text=True,timeout=timeout_s)
                if run.returncode:raise ValueError('control_link_native_drc_failed')
                grades.append(json.loads(output.read_text()))
        before,after=grades;known={stage._canonical_identity(v) for v in before['violations']}
        inventories=(support._silk_inventory(parent,old),support._silk_inventory(child,new))
        faults=[];inherited=[]
        for finding in after['violations']:
            if stage._canonical_identity(finding) in known:continue
            proof=support._inherited_silk_overlap(parent,child,finding,old,new,inventories=inventories)
            (inherited if proof else faults).append(proof or finding)
        result.update(source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),
            raw_drc=len(after['violations']),new_native_faults=faults,proved_inherited_silk_collisions=inherited)
        if faults or result['opens']>=result['source_opens']:raise ValueError('no_nonregressing_native_control_closure')
        with force._thermal_hint(board_hint):
            before_field=field.field_coupling_summary(str(source),board=parent)
            after_field=field.field_coupling_summary(str(candidate),board=child)
        result['new_field_blockers']=sorted(field.blocker_keys(after_field)-field.blocker_keys(before_field))
        if result['new_field_blockers']:raise ValueError('control_link_new_field_blockers')
        result['current_debt_receiving']=current_debt.receive(source,candidate,board_hint=board_hint)
        if not result['current_debt_receiving']['ok'] or not result['current_debt_receiving']['complete']:
            raise ValueError('control_link_new_or_unproved_current_model_debt')
        stable=families==[force._family(p,board_hint) for p in (source,candidate)] and epoch==force._code_identity()
        if not stable:raise ValueError('control_link_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            all_original_poses_power_copper_and_partitions_preserved=True,
            board=str(candidate),board_sha256=force._hash(candidate),full_release_receiving_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,directory,*,board_hint,source_sha256,timeout_s=10.):
    _budget(timeout_s)
    if type(board_hint) is not str or not board_hint:raise ValueError('bound_control_board_identity_required')
    source,directory=[Path(p).resolve() for p in (source,directory)]
    if directory.exists() or force._hash(source)!=source_sha256:raise ValueError('fresh_control_output_and_exact_source_required')
    family=force._family(source,board_hint);epoch=force._code_identity();directory.mkdir(parents=True)
    board=pcbnew.LoadBoard(str(source));old={force._uid(t) for t in board.GetTracks()}
    report=dict(schema=1,ok=False,source=str(source),source_sha256=source_sha256,trials=[],
        routing_admitted=False,release_authority=False,branch_current_qualified=False)
    deadline=time.monotonic()+timeout_s
    tasks=targets(board)[:4]
    for index,task in enumerate(tasks):
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        link,error,diagnostics=_construct_control_leaf(board,task,
            deadline=min(deadline,time.monotonic()+remaining/(len(tasks)-index)))
        report['trials'].append(dict(task=task,error=error,diagnostics=diagnostics,
            construction={k:v for k,v in (link or {}).items() if k!='items'}))
        # One simple leaf per transaction. In particular, two ENs on the same
        # rail cannot smuggle a second branch into the first path's receipt.
        if link is not None:break
    incoming=[t for t in board.GetTracks() if force._uid(t) not in old]
    if incoming:
        fr.group_local_pofv_signal_vias(board,[i for i in incoming if i.GetClass()=='PCB_VIA'])
        candidate=force._copy_family(source,directory/'candidate')
        additive._ground_refill(board);field._save_field_snapshot(board,candidate)
        additive.bind_local_via_rule(board,candidate)
        report['receiving']=receive(source,candidate,board_hint=board_hint,timeout_s=timeout_s)
        if report['receiving']['ok']:
            report.update(ok=True,board=str(candidate),board_sha256=force._hash(candidate),
                source_opens=report['receiving']['source_opens'],opens=report['receiving']['opens'])
    stable=family==force._family(source,board_hint) and epoch==force._code_identity()
    report['source_family_and_code_unchanged']=stable;report['ok']&=stable
    force._write(directory/'receiving.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--hint',required=True)
    a=p.parse_args();report=run(a.source,a.out,board_hint=a.hint,source_sha256=a.source_sha256)
    print(json.dumps({k:report.get(k) for k in ('ok','source_opens','opens','board','source_family_and_code_unchanged')}),flush=True)
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
