"""Bounded saved-source batches of contact-preserving ordinary corners.

Uses the existing native corner scheduler/constructor and independent
ordinary subtract/add receiver. Power, GND, pairs, sense, clocks, zones,
components and vias gain no mutation authority. Every trial starts from one
unchanged source. New native warnings withdraw actual implicated requests,
never disappear into a weighted score or an aggregate violation threshold.
"""
import argparse
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_copper_reuse as reuse
import cec_current_debt as current
import cec_exact_overlap_stage as overlap
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_native_drc_runner as native
import cec_native_scalar_corner_scope as corners
import cec_fab_profile as fab
import cec_ordinary_route_receiving as ordinary
import cec_ordinary_corner_collateral as collateral
import cec_route_corner_contacts as contacts
import cec_route_quality as quality
import cec_stage_admission as admission
from cec_native_items import discard_items


GEOMETRY_POLICIES = ('right_angle_chamfer', 'acute_shortcut')


def _acute_inventory(board, nets):
    """Schedule exact ordinary acute pairs, not proximity-aliased junctions.

    Eligibility is still independently derived by saved receiving. This
    finite inventory grants no authority over pairs, rails, tees or contacts.
    """
    if (not isinstance(nets, (set, frozenset))
            or any(type(net) is not str or not net for net in nets)):
        raise ValueError('positive_scalar_net_scope_required')
    deadline = time.monotonic() + 10.
    tracks = list(board.GetTracks())
    if len(tracks) + sum(len(list(fp.Pads())) for fp in board.GetFootprints()) > 16384:
        raise ValueError('native_scalar_inventory_exceeds_bound')
    live = {force._uid(t): t for t in tracks}
    if len(live) != len(tracks):
        raise ValueError('native_scalar_duplicate_track_identity')
    grouped = {force._uid(t) for g in board.Groups() for t in g.GetItems()}
    layers = {int(board.GetLayerID(name)) for name in
              fab.routing_layers(board, include_power=False)}
    selected, scope, skipped = [], set(), {}
    report = quality.analyze_board(board)
    if time.monotonic() >= deadline:
        raise ValueError('complete_native_ordinary_corner_inventory_required')
    for issue in report['issues']:
        if time.monotonic() >= deadline:
            raise ValueError('complete_native_ordinary_corner_inventory_required')
        ids = issue['track_uuids']
        if (issue['type'] != 'acute_backtrack' or issue['net'] not in nets
                or len(ids) != 2 or any(uid not in live for uid in ids)):
            continue
        a, b = (live[uid] for uid in ids)
        shared = ({tuple(a.GetStart()), tuple(a.GetEnd())}
                  & {tuple(b.GetStart()), tuple(b.GetEnd())})
        if (a.GetClass() != 'PCB_TRACK' or b.GetClass() != 'PCB_TRACK'
                or a.GetNetCode() != b.GetNetCode()
                or a.GetLayer() != b.GetLayer() or int(a.GetLayer()) not in layers
                or not 0 < a.GetWidth() == b.GetWidth() < 500000
                or len(shared) != 1 or any(uid in grouped for uid in ids)
                or any(t.HasSolderMask() for t in (a, b))
                or any(not quality.is_canonical_stroke(t.GetStart(), t.GetEnd(),
                    tolerance_nm=0) or t.GetLength() > 32000000 for t in (a, b))):
            skipped['unsupported_exact_pair'] = skipped.get('unsupported_exact_pair', 0) + 1
            continue
        # A shared source edge cannot be rewritten twice in one transaction.
        if scope & set(ids):
            skipped['overlapping_request'] = skipped.get('overlapping_request', 0) + 1
            continue
        if len(selected) >= 128 or len(scope | set(ids)) > 256:
            raise ValueError('complete_native_ordinary_corner_inventory_required')
        scope.update(ids)
        selected.append(dict(net=issue['net'], layer=int(a.GetLayer()),
            at_nm=list(next(iter(shared))), source_track_uuids=sorted(ids)))
    return dict(selected=selected, scope=sorted(scope), skipped=skipped,
        inventory_complete=True, mutation_or_contact_authority_granted=False)


def inventory(board, nets, *, minimum_nm=50000, maximum_nm=200000,
              geometry_policy='right_angle_chamfer'):
    if geometry_policy not in GEOMETRY_POLICIES:
        raise ValueError('explicit_scalar_corner_geometry_policy_required')
    if geometry_policy == 'acute_shortcut':
        return _acute_inventory(board, nets)
    result=corners.select(board,nets,minimum_chamfer_nm=minimum_nm,
        maximum_chamfer_nm=maximum_nm,maximum_candidates=128,
        maximum_scoped_tracks=256,timeout_s=10.)
    if not result['inventory_complete']:
        raise ValueError('complete_native_ordinary_corner_inventory_required')
    return result


def _construct_acute(board, requests, *, deadline):
    """Native-guarded proposals; saved-source receiving remains mandatory."""
    retired, owners, records = [], {}, []
    for row in requests:
        if time.monotonic() >= deadline:
            break
        live = {force._uid(t): t for t in board.GetTracks()}
        source = [live[uid] for uid in row['source_track_uuids']]
        corner = tuple(row['at_nm'])
        outer = [t.GetEnd() if tuple(t.GetStart()) == corner else t.GetStart()
                 for t in source]
        layer, code, width = source[0].GetLayer(), source[0].GetNetCode(), source[0].GetWidth()
        zones, copper = fr._foreign_shape_indexes(board, layer, {code})
        def clear(a, b, w):
            return (time.monotonic() < deadline
                    and quality.is_canonical_stroke(a, b, tolerance_nm=0)
                    and fr._edge_leg_clear(board, a, b, (w + 1) // 2)
                    and fr._snapshot_foreign_clear(a, b, w, 200000, zones, copper))
        point = pcbnew.VECTOR2I(*corner)
        old = [(outer[0], point, width), (point, outer[1], width)]
        record = dict(request=row, changed=False, proposal_trials=[])
        records.append(record)
        # Reuse only actual retained straight copper, excluding both old
        # edges being retired. The exact integer interval proof preserves
        # the full capsule union, not just endpoint connectivity. Otherwise
        # a locally shorter turn can emit a new overlap/backtrack against a
        # neighbor. No source item or rounded land is trimmed by this step.
        retained = reuse.RetainedCopper((t for t in reuse.native_inventory(board)
            if t['uuid'] not in row['source_track_uuids']), max_items=16384)
        options=[]
        # Both exact orientations are a finite portfolio. Source UUID sort
        # order must not choose a duplicate neighbor over an already retained
        # route. Prefer the least NEW material after exact native reuse.
        for reverse in (False,True):
            order=[1,0] if reverse else [0,1]
            directed=[(outer[order[0]],point,width),(point,outer[order[1]],width)]
            proposed=quality.guarded_corner_shortcuts(directed,clear,
                max_corner_nm=1500000,deadline_monotonic=deadline)
            trial=dict(reverse=reverse,changed=False);record['proposal_trials'].append(trial)
            if [(tuple(a),tuple(b),w) for a,b,w in proposed]==[
                    (tuple(a),tuple(b),w) for a,b,w in directed]:continue
            proof=contacts.preserve_contacts(board,source,
                tuple(pcbnew.SHAPE_SEGMENT(a,b,w) for a,b,w in proposed),
                layer_id=layer,net_code=code,deadline_monotonic=deadline,max_items=16384)
            trial['native_contact_preservation']=proof
            if not proof['ok']:continue
            residual,reuse_proof=retained.subtract([
                dict(net=row['net'],layer=int(layer),start_nm=list(a),end_nm=list(b),
                    width_nm=w,source_index=order[min(index,1)])
                for index,(a,b,w) in enumerate(proposed)],max_checks=65536,max_proposed=2)
            trial['retained_native_copper_reuse']=reuse_proof
            if len(residual)>8:continue
            trial['changed']=True
            rank=(sum(math.dist(r['start_nm'],r['end_nm']) for r in residual),len(residual),
                tuple(sorted((tuple(r['start_nm']),tuple(r['end_nm'])) for r in residual)))
            options.append((rank,proposed,residual,proof,reuse_proof))
        if not options:
            record['refusal']='no_bounded_native_clear_contact_preserving_shortcut';continue
        _,proposed,residual,proof,reuse_proof=min(options,key=lambda option:option[0])
        record['native_contact_preservation']=proof
        record['retained_native_copper_reuse'] = reuse_proof
        incoming = []
        for material in residual:
            t = source[material['source_index']].Duplicate()
            t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*material['start_nm']))
            t.SetEnd(pcbnew.VECTOR2I(*material['end_nm'])); board.Add(t)
            uid = force._uid(t); incoming.append(uid)
            owners[uid] = list(row['source_track_uuids'])
        retired.extend(row['source_track_uuids'])
        record.update(changed=True, incoming_track_uuids=incoming,
            source_length_nm=sum(math.dist(tuple(a), tuple(b)) for a,b,w in old),
            proposed_length_nm=sum(math.dist(tuple(a), tuple(b)) for a,b,w in proposed))
        discard_items(board, source)
    return dict(retired_track_uuids=sorted(retired), incoming_source_owners=owners,
        details=records, chamfered=sum(row['changed'] for row in records),
        geometry_policy='acute_shortcut', mutation_or_release_admission=False)


def construct(board, requests, nets, *, allow_locked_source=False,
              minimum_nm=50000, maximum_nm=200000, timeout_s=10.,
              geometry_policy='right_angle_chamfer'):
    """Untrusted in-memory constructor; scopes do not grant saved admission."""
    if (type(requests) is not list or not 1<=len(requests)<=16
            or type(allow_locked_source) is not bool
            or not isinstance(nets,(set,frozenset))
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_native_scalar_batch_required')
    # Re-derive every request from this actual board rather than trusting a
    # caller's UUID/name list. No grouped source or immutable launch is owned.
    actual=inventory(board,nets,minimum_nm=minimum_nm,maximum_nm=maximum_nm,
        geometry_policy=geometry_policy)
    actual_rows={tuple(row['source_track_uuids']):row for row in actual['selected']}
    scope=set()
    for row in requests:
        if (type(row) is not dict or type(row.get('source_track_uuids')) is not list
                or len(row['source_track_uuids'])!=2
                or any(type(uid) is not str for uid in row['source_track_uuids'])
                or actual_rows.get(tuple(row['source_track_uuids']))!=row):
            raise ValueError('exact_actual_native_scalar_corner_request_required')
        scope.update(row['source_track_uuids'])
    if len({tuple(row['source_track_uuids']) for row in requests})!=len(requests):
        raise ValueError('distinct_native_scalar_corner_requests_required')
    if len(scope)>32:raise ValueError('ordinary_receiver_retired_scope_bound')
    source={force._uid(t):t for t in board.GetTracks()}
    if not allow_locked_source and any(source[u].IsLocked() for u in scope):
        raise ValueError('explicit_locked_scalar_source_permission_required')
    if geometry_policy == 'acute_shortcut':
        return _construct_acute(board, requests, deadline=time.monotonic()+timeout_s)
    endpoints={u:(tuple(t.GetStart()),tuple(t.GetEnd())) for u,t in source.items()
        if t.GetClass()=='PCB_TRACK'}
    deadline=time.monotonic()+timeout_s;records=[];owners={}
    excluded={str(t.GetNetname()) for t in source.values()}-set(nets)
    for row in requests:
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        ids=set(row['source_track_uuids']);live={force._uid(t):t for t in board.GetTracks()}
        locks={u:bool(t.IsLocked()) for u,t in live.items()}
        try:
            for uid,t in live.items():
                if uid not in ids:t.SetLocked(True)
            result=fr.chamfer_unlocked_right_angles(board,
                max_chamfer_mm=maximum_nm/1e6,min_chamfer_mm=minimum_nm/1e6,
                max_width_mm=.499,exclude_nets=excluded,
                allow_locked_track_uuids=ids if allow_locked_source else (),
                timeout_s=min(10.,remaining),max_corners=8192,max_chamfers=1)
        finally:
            for t in board.GetTracks():
                uid=force._uid(t)
                if uid in locks:t.SetLocked(locks[uid])
        incoming={force._uid(t) for t in board.GetTracks()}-live.keys()
        if not result['chamfered']:
            if incoming:raise ValueError('refused_native_chamfer_added_material')
            records.append(dict(request=row,changed=False,native_result=result));continue
        if len(incoming)!=1:raise ValueError('one_exact_native_chamfer_bridge_required')
        for uid in incoming:owners[uid]=sorted(ids)
        records.append(dict(request=row,changed=True,native_result=result))
    changed={force._uid(t) for t in board.GetTracks() if force._uid(t) in endpoints
        and (tuple(t.GetStart()),tuple(t.GetEnd()))!=endpoints[force._uid(t)]}
    if not changed<=scope:raise ValueError('native_chamfer_changed_unscoped_source')
    # Explicit replacement IDs distinguish genuine source retirement from a
    # silent in-place rewrite. Literal original locks were already restored.
    replaced=[]
    for t in list(board.GetTracks()):
        uid=force._uid(t)
        if uid not in changed:continue
        new=t.Duplicate();new.m_Uuid.Clone(pcbnew.KIID());board.Add(new);replaced.append(t)
        owners[force._uid(new)]=[uid]
    discard_items(board,replaced)
    return dict(retired_track_uuids=sorted(changed),incoming_source_owners=owners,
        details=records,chamfered=sum(row['changed'] for row in records),
        mutation_or_release_admission=False)


def withdraw(requests, violations, owners):
    """Map literal new-native fault items back to their finite source scopes."""
    scope={u for row in requests for u in row['source_track_uuids']};mapped=[]
    for violation in violations:
        ids=set()
        for item in violation['items']:
            uid=item.get('uuid');ids.update(owners.get(uid,[]))
            if uid in scope:ids.add(uid)
        mapped.append(dict(items=[dict(uuid=uid) for uid in sorted(ids)]))
    return overlap.withdraw_implicated(requests,mapped)


def receive_saved(source,candidate,construction,*,board_hint,sense_timeout_s):
    retired=construction['retired_track_uuids'];result=dict(ok=False,complete=False,errors=[],release_authority=False)
    try:
        _,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(candidate)
        cut_only=not bool(new_nodes.keys()-old_nodes.keys())
        proof=ordinary.receive(source,candidate,retired_track_uuids=retired,board_hint=board_hint,
            allow_locked_track_uuids=retired,allow_redundant_cut_only=cut_only,timeout_s=10.)
        result['actual_saved_redundant_cut_only']=cut_only
        result['whole_original_ordinary_delta']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('original_ordinary_delta_refused')
        debt=current.receive(source,candidate,board_hint=board_hint);result['whole_original_current_debt']=debt
        if not debt['ok'] or not debt['complete']:raise ValueError('original_scalar_corner_current_debt_refused')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-
                field.blocker_keys(field.field_coupling_summary(str(source))))
        result['new_field_blocker_keys']=delta
        if delta:raise ValueError('new_native_scalar_corner_field_blocker')
        old=pcbnew.LoadBoard(str(source));new=pcbnew.LoadBoard(str(candidate))
        first={force._uid(t):t for t in old.GetTracks()};last={force._uid(t):t for t in new.GetTracks()}
        changed=sorted({str(first[u].GetNetname()) for u in retired})
        packets=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in (source,candidate)]
        for packet in packets:
            if any(row.get('ok') is not True for row in packet['clipped_isolation']['details'] if row['net'] in changed):
                raise ValueError('changed_corner_requires_positive_absolute_source_and_child_cuts')
        incoming=last.keys()-first.keys();transforms=[]
        for net in changed:
            transforms.append(dict(net=net,retired_track_uuids=sorted(u for u in retired if str(first[u].GetNetname())==net),
                added_track_uuids=sorted(u for u in incoming if str(last[u].GetNetname())==net),
                retired_via_uuids=[],added_via_uuids=[],added_zone_uuids=[]))
        cuts=sense.compare_contour_preservation(*packets,modified_nets=changed,native_copper_transforms=transforms)
        result['physical_kelvin_preservation']=cuts
        if not cuts['comparison_complete'] or not cuts['same_evidence']:
            raise ValueError('native_scalar_corner_absolute_or_unaffected_cuts_refused')
        result.update(ok=True,complete=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_requests=16,max_trials=4,sense_timeout_s=40.,minimum_chamfer_nm=50000,
        geometry_policy='right_angle_chamfer'):
    started=time.monotonic()
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool
            or type(max_requests) is not int or not 1<=max_requests<=16
            or type(max_trials) is not int or not 1<=max_trials<=8
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0<sense_timeout_s<=60 or reporting_build is None
            or type(expected_source_sha256) is not str or len(expected_source_sha256)!=64
            or type(minimum_chamfer_nm) is not int or not 20000<=minimum_chamfer_nm<=50000
            or geometry_policy not in GEOMETRY_POLICIES):
        raise ValueError('bounded_explicit_saved_scalar_corner_context_required')
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_hash_and_fresh_scalar_corner_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    result=dict(source=str(source),source_sha256=expected_source_sha256,candidate=str(source),
        candidate_sha256=expected_source_sha256,code_identity=epoch,errors=[],attempts=[],changed=False,
        ok=False,complete=False,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,
        minimum_chamfer_nm=minimum_chamfer_nm,geometry_policy=geometry_policy)
    def observe(path,label):
        # Native KiCad may materialize missing project settings. DRC gets an
        # exact private family, never authority to write into the source.
        shadow=force._copy_family(path,outdir/(label+'-native-input'))
        dest=outdir/(label+'.drc.json');proof=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        result.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_scalar_corner_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        b=pcbnew.LoadBoard(str(source));nets=ordinary.eligible_nets(b,source,board_hint)
        before=inventory(b,nets,minimum_nm=minimum_chamfer_nm,geometry_policy=geometry_policy);result['before']=before
        craft_before=quality.analyze_board(b);result['craft_before']=craft_before
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('native_open_closure_precedes_optional_corner_stage')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        live={force._uid(t):t for t in b.GetTracks()};active=[];scope=set()
        for request in before['selected']:
            ids=set(request['source_track_uuids'])
            if not allow_locked_source and any(live[u].IsLocked() for u in ids):continue
            if len(active)>=max_requests or len(scope|ids)>32:break
            active.append(request);scope|=ids
        result['initial_requests']=active
        for index in range(max_trials):
            if not active:break
            row=dict(index=index,accepted=False,requests=active);result['attempts'].append(row)
            b=pcbnew.LoadBoard(str(source));step=time.monotonic()
            construction=construct(b,active,nets,allow_locked_source=allow_locked_source,
                minimum_nm=minimum_chamfer_nm,geometry_policy=geometry_policy)
            row['construction_elapsed_s']=time.monotonic()-step
            row['construction']=construction
            if not construction['chamfered']:row['refusal']='no_contact_preserving_native_corner';break
            candidate=force._copy_family(source,outdir/('UNADMITTED-scalar-corners-'+str(index)))
            additive._ground_refill(b);field._save_field_snapshot(b,candidate)
            _,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(candidate)
            def fabrication(node):
                return tuple(sorted((syntax._freeze(child) for child in node[1:]
                    if not isinstance(child,list) or not child or child[0] not in ('start','end','uuid')),key=repr))
            permitted={fabrication(old_nodes[u]) for u in construction['retired_track_uuids']}
            if any(new_nodes[u][0]!='segment' or fabrication(new_nodes[u]) not in permitted
                    for u in new_nodes.keys()-old_nodes.keys()):
                row['refusal']='incoming_chamfer_fabrication_not_exact_source';break
            after=inventory(b,nets,minimum_nm=minimum_chamfer_nm,geometry_policy=geometry_policy);craft_after=quality.analyze_board(b)
            key=lambda v:(v['type'],v['net'],v['layer'],tuple(v['at_mm']))
            if (len(after['selected'])>=len(before['selected'])
                    or craft_after['issue_count']>craft_before['issue_count']
                    or craft_after['non_octilinear_count']>craft_before['non_octilinear_count']
                    or {key(v) for v in craft_after['issues']}-{key(v) for v in craft_before['issues']}):
                row['refusal']='no_strict_corner_gain_or_new_route_craft';break
            step=time.monotonic();observed=observe(candidate,'candidate-'+str(index))
            row['native_report_elapsed_s']=time.monotonic()-step
            added=[v for v in observed['violations'] if admission._canonical_identity(v) not in faults]
            row['new_native_fault_ids']=[admission._canonical_identity(v) for v in added]
            if observed['unconnected_items']:row['refusal']='new_native_open';break
            collateral_used=set()
            for collateral_round in range(4):
                if (not added or geometry_policy!='acute_shortcut'
                        or len(added)>4-len(collateral_used)):break
                # A loop cut can expose a short retained ordinary tail. Do
                # not waive its warning or delete it in a later unbound pass.
                # Native fault UUIDs and exact SOURCE adjacency provide a
                # finite proposal; full original-source receiving below
                # independently checks the expanded atomic transaction.
                proposal=collateral.plan(source,candidate,added,construction['retired_track_uuids'],nets,
                    allow_locked_source=allow_locked_source)
                row.setdefault('native_collateral_scope',proposal)
                row.setdefault('native_collateral_scopes',[]).append(proposal)
                if proposal['ok']:
                    row.setdefault('new_native_fault_ids_before_collateral',row['new_native_fault_ids'])
                    child=force._copy_family(candidate,outdir/('UNADMITTED-scalar-corners-'+str(index)+'-collateral-'+str(collateral_round)))
                    b=pcbnew.LoadBoard(str(child));extra=set(proposal['retired_track_uuids'])
                    if not extra or extra & collateral_used:raise ValueError('collateral_must_make_bounded_new_progress')
                    collateral_used|=extra
                    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in extra])
                    additive._ground_refill(b);field._save_field_snapshot(b,child);candidate=child
                    construction['retired_track_uuids']=sorted(set(construction['retired_track_uuids'])|extra)
                    construction.setdefault('native_collateral_retirements',[]).append(proposal)
                    after=inventory(b,nets,minimum_nm=minimum_chamfer_nm,geometry_policy=geometry_policy)
                    craft_after=quality.analyze_board(b)
                    if (len(after['selected'])>=len(before['selected'])
                            or craft_after['issue_count']>craft_before['issue_count']
                            or craft_after['non_octilinear_count']>craft_before['non_octilinear_count']
                            or {key(v) for v in craft_after['issues']}-{key(v) for v in craft_before['issues']}):
                        row['refusal']='collateral_has_no_strict_gain_or_new_route_craft';break
                    observed=observe(candidate,'candidate-'+str(index)+'-collateral-'+str(collateral_round))
                    added=[v for v in observed['violations'] if admission._canonical_identity(v) not in faults]
                    row['new_native_fault_ids']=[admission._canonical_identity(v) for v in added]
                    if observed['unconnected_items']:row['refusal']='collateral_new_native_open';break
                else:break
            if row.get('refusal'):break
            if added:
                active,blocked=withdraw(active,added,construction['incoming_source_owners'])
                row.update(refusal='new_native_faults_rejected_not_waived',withdrawn_source_uuids=blocked);continue
            step=time.monotonic()
            proof=receive_saved(source,candidate,construction,board_hint=board_hint,sense_timeout_s=sense_timeout_s)
            row['independent_receiving_elapsed_s']=time.monotonic()-step
            row['independent_receiving']=proof
            if not proof['ok'] or not proof['complete']:row['refusal']='whole_original_scalar_corner_receiving_refused';break
            row.update(accepted=True,candidate=str(candidate),candidate_sha256=force._hash(candidate))
            result.update(changed=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),
                after=after,craft_after=craft_after,independent_receiving=proof,construction=construction)
            break
        if not result['changed']:result.update(after=before,craft_after=craft_before)
        result.update(ok=True,complete=True,all_eligible_corner_requests_clean=not result['after']['selected'])
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    result['source_family_and_code_unchanged']=stable
    if not stable:result.update(ok=False,complete=False);result['errors'].append('scalar_corner_source_or_code_changed')
    result['wall_elapsed_s']=time.monotonic()-started
    result['native_report_invocations']=len(result.get('native_producers',{}))
    force._write(outdir/'stage.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--max-requests',type=int,default=16);p.add_argument('--max-trials',type=int,default=4)
    p.add_argument('--sense-timeout-s',type=float,default=40.)
    p.add_argument('--minimum-chamfer-nm',type=int,default=50000)
    p.add_argument('--geometry-policy',choices=GEOMETRY_POLICIES,default='right_angle_chamfer')
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        max_requests=a.max_requests,max_trials=a.max_trials,sense_timeout_s=a.sense_timeout_s,
        minimum_chamfer_nm=a.minimum_chamfer_nm,geometry_policy=a.geometry_policy)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        before=len(r.get('before',{}).get('selected',[])),after=len(r.get('after',{}).get('selected',[])),errors=r['errors'])),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
