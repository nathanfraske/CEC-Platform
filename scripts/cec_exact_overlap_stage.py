"""Finite source-owned overlap cleanup, with no new copper or rating credit.

All trials replay from the SAME saved source. Exact reciprocal native track
capsule coverage and unchanged non-scoped serialization precede native DRC.
If normalization exposes a new native warning, only requests implicated by
its actual scoped UUIDs are withdrawn; the warning is never suppressed.
Current, conductor partitions, fields and absolute clipped cuts are mandatory
before a winner is returned. This optional cleanup has no release authority.
"""
import argparse,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_route_quality as quality
import cec_exact_overlap_receiving as exact
import cec_fab_repair as repair
import cec_field_coupling as field
import cec_current_debt as current
import cec_ordinary_route_receiving as topology
import cec_native_drc_runner as native
import cec_stage_admission as admission
import cec_force_sense_evidence as sense
import cec_contained_track_receiving as contained
from collections import Counter,defaultdict


def _normalization(value):
    if value not in ('exact_overlap','exact_duplicates','strict_containment'):
        raise ValueError('explicit_supported_saved_copper_normalization_required')
    return value


def _duplicate_pairs(source,tracks,*,retain_per_item_locks=False):
    """Exact equal capsules at forks are invisible to a two-leg turn audit.

    Discovery is not deletion authority. Full serialized fabrication fields
    must agree; groups are not owned. Requests still pass scoped repair and
    reciprocal saved-copper/current/native/field/cut receiving afterwards.
    Pair a deterministic witness with each redundant primitive, interleaving
    groups so a single multiply-emitted bus cannot consume the whole menu.
    """
    groups=defaultdict(list)
    for uid,t in sorted(tracks.items()):
        if (t.GetClass()!='PCB_TRACK' or t.GetParentGroup() or t.HasSolderMask()
                or not t.GetNetname()):continue
        ends=tuple(sorted((tuple(t.GetStart()),tuple(t.GetEnd()))))
        if ends[0]==ends[1]:continue
        groups[(str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),ends)].append(uid)
    groups=[ids for ids in groups.values() if len(ids)>1]
    if not groups:return []
    ids={u for group in groups for u in group}
    _,_,serialized=exact._read(Path(source),{'"'+u+'"' for u in ids},
        time.monotonic()+10.,32768,retain_per_item_locks=retain_per_item_locks)
    native={r['uuid'].strip('"'):r['fabrication'] for r in serialized}
    queues=[]
    for group in groups:
        process=defaultdict(list)
        for uid in group:process[native[uid]].append(uid)
        for same in process.values():
            if len(same)>1:queues.append([[same[0],u] for u in same[1:]])
    result=[]
    for index in range(max((len(q) for q in queues),default=0)):
        result.extend(q[index] for q in queues if index<len(q))
    return result


def source_requests(source,*,allow_locked_source=False,max_requests=32,retain_per_item_locks=False,
                    normalization='exact_overlap'):
    """Read-only finite scopes; names, positions and net roles grant nothing."""
    if (type(allow_locked_source) is not bool or type(max_requests) is not int or not 1<=max_requests<=32
            or type(retain_per_item_locks) is not bool):
        raise ValueError('bounded_explicit_overlap_source_policy_required')
    _normalization(normalization)
    board=pcbnew.LoadBoard(str(source));tracks={force._uid(t):t for t in board.GetTracks()}
    if len(tracks)>16384:raise ValueError('bounded_native_overlap_track_inventory_required')
    audit=quality.analyze_board(board);requests=[];skipped=[]
    if normalization=='strict_containment':
        # Only an untrusted, disposable in-memory copy is used for discovery.
        # Every saved trial is independently checked against the original.
        discovery=repair.repair_contained_tracks(board,
            allow_locked_track_uuids=list(tracks) if allow_locked_source else (),
            timeout_s=10.,max_ops=max_requests)
        requests=[dict(net=row['net'],source_track_uuids=[row['uuid'],row['receiver_uuid']],
            retired_track_uuid=row['uuid']) for row in discovery['detail']]
        return dict(requests=requests,skipped=[],before_quality=audit,
            discovery_complete=discovery['complete'],normalization=normalization)
    duplicate_pairs=_duplicate_pairs(source,tracks,retain_per_item_locks=retain_per_item_locks)
    component_sizes=Counter(ids[0] for ids in duplicate_pairs)
    accepted_components=set();refused_components=set();reserved=0
    for ids in duplicate_pairs:
        key=ids[0]
        if key in accepted_components|refused_components:continue
        if reserved+component_sizes[key]<=max_requests:
            accepted_components.add(key);reserved+=component_sizes[key]
        else:refused_components.add(key)
    pending=[dict(type='exact_duplicate_capsule',track_uuids=ids,
        whole_duplicate_component_in_budget=ids[0] in accepted_components) for ids in duplicate_pairs]
    if normalization!='exact_duplicates':
        pending += [issue for issue in audit['issues'] if issue['type']=='covered_backtrack']
    seen=set()
    for issue in pending:
        ids=sorted(set(issue['track_uuids']))
        key=tuple(ids)
        if key in seen:continue
        seen.add(key)
        if not 1<=len(ids)<=2 or not set(ids)<=tracks.keys():
            raise ValueError('exact_actual_overlap_issue_scope_required')
        reason=None
        if issue.get('whole_duplicate_component_in_budget') is False:reason='finite_source_request_budget'
        elif any(tracks[u].GetParentGroup() for u in ids):reason='group_owner_recompile_required'
        elif not allow_locked_source and any(tracks[u].IsLocked() for u in ids):
            reason='explicit_locked_source_scope_permission_required'
        if reason is None:
            _,_,rows=exact._read(Path(source),{'"'+u+'"' for u in ids},time.monotonic()+10.,32768,
                retain_per_item_locks=retain_per_item_locks)
            if len(rows)!=len(ids) or any(row['fabrication']!=rows[0]['fabrication'] for row in rows):
                reason='nonidentical_native_fabrication_or_lock_fields'
        row=dict(net=str(tracks[ids[0]].GetNetname()),source_track_uuids=ids)
        if reason:skipped.append(dict(**row,reason=reason))
        elif len(requests)<max_requests:requests.append(row)
        else:skipped.append(dict(**row,reason='finite_source_request_budget'))
    return dict(requests=requests,skipped=skipped,before_quality=audit,
        exact_duplicate_pairs_discovered=len([r for r in pending if r['type']=='exact_duplicate_capsule']))


def withdraw_implicated(requests,violations):
    """Remove whole overlap components implicated by native item identities.

    Unattributed warnings refuse a trial instead of guessing which copper to
    cut. An empty item inventory is not a proof that a warning is harmless.
    """
    if (type(requests) is not list or len(requests)>32 or type(violations) is not list or len(violations)>20000
            or any(type(row) is not dict or type(row.get('source_track_uuids')) is not list
                or not 1<=len(row['source_track_uuids'])<=2
                or any(type(u) is not str or not u for u in row['source_track_uuids']) for row in requests)
            or any(type(row) is not dict or type(row.get('items')) is not list
                or len(row['items'])>256 or any(type(item) is not dict for item in row['items']) for row in violations)):
        raise ValueError('bounded_actual_native_overlap_fault_inventory_required')
    active={u for row in requests for u in row['source_track_uuids']};blocked=set()
    if not violations:return list(requests),[]
    for warning in violations:
        implicated={item.get('uuid') for item in warning.get('items',[])} & active
        if not implicated:raise ValueError('new_native_warning_not_attributable_to_overlap_scope')
        blocked.update(implicated)
    changed=True
    while changed:
        old=set(blocked)
        for row in requests:
            if blocked.intersection(row['source_track_uuids']):blocked.update(row['source_track_uuids'])
        changed=old!=blocked
    retained=[row for row in requests if not blocked.intersection(row['source_track_uuids'])]
    return retained,sorted(blocked)


def receive_saved(source,candidate,scope,*,board_hint,sense_timeout_s,retain_per_item_locks=False,
                  normalization='exact_overlap'):
    """Independently receive a fixed exact-union candidate; never waive DRC."""
    r=dict(ok=False,complete=False,errors=[],release_authority=False,new_capacity_credited=False)
    try:
        if (type(board_hint) is not str or not board_hint or type(sense_timeout_s) not in (int,float)
                or not math.isfinite(sense_timeout_s) or not 0<sense_timeout_s<=60):
            raise ValueError('explicit_source_overlap_context_and_cut_budget_required')
        _normalization(normalization)
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        r['exact_saved_copper_union']=(contained.receive(source,candidate,source_track_uuids=scope,timeout_s=10.)
            if normalization=='strict_containment' else exact.receive(source,candidate,
                source_track_uuids=scope,timeout_s=10.,retain_per_item_locks=retain_per_item_locks))
        if not r['exact_saved_copper_union']['ok']:raise ValueError('exact_source_copper_union_refused')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('overlap_sidecar_changed')
        first,last=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        old={force._uid(t):t for t in first.GetTracks()};new={force._uid(t):t for t in last.GetTracks()}
        retired=set(old)-new.keys()
        original_parts=topology._partition(first,time.monotonic()+10.,retired_uuids=retired)
        survivors=set().union(*original_parts)
        new_parts=topology._partition(last,time.monotonic()+10.,retained_keys=survivors)
        if not all(any(part<=other for other in new_parts) for part in original_parts):
            raise ValueError('source_native_conductor_partition_lost')
        r['all_surviving_source_native_partitions_preserved']=True
        r['current_debt_receiving']=current.receive(source,candidate,board_hint=board_hint)
        if not r['current_debt_receiving']['ok'] or not r['current_debt_receiving']['complete']:
            raise ValueError('full_source_current_debt_refused')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(candidate)))-
                field.blocker_keys(field.field_coupling_summary(str(source))))
        r['new_field_blocker_keys']=delta
        if delta:raise ValueError('new_source_overlap_field_blocker')
        changed=sorted({str(old[u].GetNetname()) for u in scope if u not in new or
            old[u].GetStart()!=new[u].GetStart() or old[u].GetEnd()!=new[u].GetEnd()})
        if not changed:raise ValueError('no_actual_overlap_change')
        packets=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in (source,candidate)]
        for packet in packets:
            if any(row.get('ok') is not True for row in packet['clipped_isolation']['details']
                   if row['net'] in changed):
                raise ValueError('changed_overlap_net_requires_positive_absolute_source_and_child_cuts')
        transforms=[]
        for net in changed:
            ids=sorted(u for u in retired if str(old[u].GetNetname())==net)
            if ids:transforms.append(dict(net=net,retired_track_uuids=ids,added_track_uuids=[],
                retired_via_uuids=[],added_via_uuids=[],added_zone_uuids=[]))
        r['physical_kelvin_preservation']=sense.compare_contour_preservation(*packets,
            modified_nets=changed,native_copper_transforms=transforms)
        proof=r['physical_kelvin_preservation']
        if not proof['comparison_complete'] or not proof['same_evidence']:
            raise ValueError('exact_union_absolute_cuts_or_unaffected_evidence_refused')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('overlap_source_child_or_code_changed')
        r.update(ok=True,complete=True,modified_nets=changed,retired_track_uuids=sorted(retired),
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),code_identity=epoch)
    except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,max_requests=32,max_trials=4,sense_timeout_s=10.,retain_per_item_locks=False,
        normalization='exact_overlap',overlap_policy='preserve_junctions'):
    _normalization(normalization)
    if (overlap_policy not in ('preserve_junctions','retire_covered')
            or normalization!='exact_overlap' and overlap_policy!='preserve_junctions'):
        raise ValueError('supported_exact_overlap_policy_required')
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or type(allow_locked_source) is not bool or type(retain_per_item_locks) is not bool
            or type(max_requests) is not int or not 1<=max_requests<=32
            or type(max_trials) is not int or not 1<=max_trials<=8 or reporting_build is None
            or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
            or not 0<sense_timeout_s<=60.):
        raise ValueError('bounded_explicit_saved_native_overlap_stage_required')
    source=Path(source).resolve();outdir=Path(outdir).resolve()
    if not source.is_file() or force._hash(source)!=expected_source_sha256 or outdir.exists():
        raise ValueError('exact_source_hash_and_fresh_overlap_output_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    r=dict(schema=1,scope='finite_original_source_exact_overlap_stage',source=str(source),
        source_sha256=expected_source_sha256,code_identity=epoch,candidate=str(source),
        candidate_sha256=expected_source_sha256,ok=False,complete=False,changed=False,errors=[],attempts=[],
        source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False,
        new_capacity_credited=False,max_requests=max_requests,max_trials=max_trials,
        retain_per_item_locks=retain_per_item_locks,normalization=normalization,overlap_policy=overlap_policy)
    def observe(path,label):
        dest=outdir/(label+'.drc.json')
        # Native KiCad may create an editor-local .kicad_prl even during a
        # read-only DRC. Observe a private family, never the frozen input or
        # the candidate whose exact serialization is being received.
        grade=force._copy_family(path,outdir/(label+'-native-grade'))
        proof=native.run(grade,dest,reporting_build=reporting_build,timeout_s=10.)
        r.setdefault('native_producers',{})[label]=proof
        if not proof['ok'] or not proof['complete'] or proof['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_overlap_native_inventory_required')
        return json.loads(dest.read_text())
    try:
        baseline=observe(source,'source')
        if baseline['unconnected_items']:raise ValueError('native_open_closure_precedes_optional_overlap_stage')
        faults={admission._canonical_identity(v) for v in baseline['violations']}
        inventory=source_requests(source,allow_locked_source=allow_locked_source,max_requests=max_requests,
            retain_per_item_locks=retain_per_item_locks,normalization=normalization)
        r.update(inventory=inventory,before=inventory['before_quality']);active=inventory['requests']
        for index in range(max_trials):
            if not active:break
            row=dict(index=index,accepted=False,source_requests=active);r['attempts'].append(row)
            scope=sorted({u for request in active for u in request['source_track_uuids']})
            board=pcbnew.LoadBoard(str(source))
            if normalization=='strict_containment':
                planned=[request['retired_track_uuid'] for request in active]
                count=repair.repair_contained_tracks(board,track_uuid_scope=planned,
                    allow_locked_track_uuids=planned if allow_locked_source else (),
                    timeout_s=10.,max_ops=max_requests)['retired']
            else:
                count=repair.repair_backtracks(board,track_uuid_scope=scope,
                    allow_locked_track_uuids=scope if allow_locked_source else (),timeout_s=10.,overlap_policy=overlap_policy,
                    duplicates_only=normalization=='exact_duplicates')
            if not count:row['refusal']='no_exact_scoped_native_normalization';break
            candidate=force._copy_family(source,outdir/('UNADMITTED-exact-overlap-'+str(index)))
            field._save_field_snapshot(board,candidate)
            row['exact_union']=(contained.receive(source,candidate,source_track_uuids=scope,timeout_s=10.)
                if normalization=='strict_containment' else exact.receive(source,candidate,
                    source_track_uuids=scope,timeout_s=10.,retain_per_item_locks=retain_per_item_locks))
            if not row['exact_union']['ok']:row['refusal']='exact_whole_source_union_refused';break
            observed=observe(candidate,'candidate-'+str(index))
            new_faults=[v for v in observed['violations'] if admission._canonical_identity(v) not in faults]
            row.update(new_native_fault_ids=[admission._canonical_identity(v) for v in new_faults],
                native_opens=len(observed['unconnected_items']),normalized=count)
            if observed['unconnected_items']:row['refusal']='new_native_open';break
            if new_faults:
                active,blocked=withdraw_implicated(active,new_faults)
                row.update(refusal='new_native_faults_rejected_not_waived',withdrawn_source_uuids=blocked)
                continue
            after=quality.analyze_board(pcbnew.LoadBoard(str(candidate)))
            old_acute={(v['net'],v['layer'],tuple(v['at_mm']),v['type'])
                for v in r['before']['issues'] if v['type']!='covered_backtrack'}
            new_acute={(v['net'],v['layer'],tuple(v['at_mm']),v['type'])
                for v in after['issues'] if v['type']!='covered_backtrack'}
            # An exact-union retirement is real structural improvement even
            # when a >2-way source fork hid it from the two-leg turn audit.
            # Geometry/craft must still not regress; all independent physical
            # receivers below remain mandatory, including absolute cuts.
            retired_count=row['exact_union']['source_tracks']-row['exact_union']['candidate_tracks']
            if (after['issue_count']>r['before']['issue_count']
                    or after['non_octilinear_count']>r['before']['non_octilinear_count']
                    or new_acute-old_acute
                    or after['issue_count']==r['before']['issue_count'] and not retired_count):
                row['refusal']='no_strict_native_route_quality_improvement';break
            row['exact_union_retired_native_track_count']=retired_count
            proof=receive_saved(source,candidate,scope,board_hint=board_hint,sense_timeout_s=sense_timeout_s,
                retain_per_item_locks=retain_per_item_locks,normalization=normalization)
            row['independent_receiving']=proof
            if not proof['ok'] or not proof['complete']:row['refusal']='source_overlap_electrical_receiving_refused';break
            row.update(accepted=True,candidate=str(candidate),candidate_sha256=force._hash(candidate))
            r.update(changed=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),
                after=after,independent_receiving=proof,source_track_uuids=scope)
            break
        if not r['changed']:r['after']=r['before']
        r.update(ok=True,complete=True,all_route_quality_findings_clean=r['after']['issue_count']==0)
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    r['source_family_and_code_unchanged']=stable
    if not stable:r.update(ok=False,complete=False);r['errors'].append('exact_overlap_source_or_code_changed')
    force._write(outdir/'stage.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','out','reporting-build'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--board-hint',required=True);p.add_argument('--expected-source-sha256',required=True)
    p.add_argument('--allow-locked-source',action='store_true')
    p.add_argument('--retain-per-item-locks',action='store_true')
    p.add_argument('--normalization',choices=('exact_overlap','exact_duplicates','strict_containment'),default='exact_overlap')
    p.add_argument('--overlap-policy',choices=('preserve_junctions','retire_covered'),default='preserve_junctions')
    p.add_argument('--max-requests',type=int,default=32);p.add_argument('--max-trials',type=int,default=4)
    p.add_argument('--sense-timeout-s',type=float,default=10.)
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,
        max_requests=a.max_requests,max_trials=a.max_trials,sense_timeout_s=a.sense_timeout_s,
        retain_per_item_locks=a.retain_per_item_locks,normalization=a.normalization,overlap_policy=a.overlap_policy)
    print(json.dumps(dict(receipt=str(a.out/'stage.json'),ok=r['ok'],complete=r['complete'],changed=r['changed'],
        candidate=r['candidate'],before=r.get('before',{}).get('issue_count'),
        after=r.get('after',{}).get('issue_count'),errors=r['errors'])),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
