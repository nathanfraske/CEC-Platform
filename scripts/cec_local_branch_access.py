"""Bounded source-derived measurement detour plus local supply/reference access.

Stationary ICs and bypasses are the first, minimum-motion construction tier.
Only a positively owned thin measurement leaf can move; all force copper,
barrels, component poses and schematic identities remain exact. A separate
receiver restores every old partition and checks saved native/field evidence.
Neither source debt nor a local topology receipt becomes release authority.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import pcbnew
from shapely.geometry import LineString
from shapely.ops import unary_union
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_ordinary_route_receiving as ordinary
import cec_placement_geometry as geometry
import cec_power_connectivity as power
import cec_source_literal_retirement as literal_cut
import cec_stage_admission as stage
import cec_support_pivot_receiving as support
from cec_native_items import discard_items


def _destinations(task):
    # Both returns belong to the same source-verified grounded component.
    # Prefer the actual owner ground for a stationary grounded REF; forcing
    # a path to the bypass on the other side can cross its measurement leaf.
    return [*task.get('verified_ground_alternatives',()),
        dict(ref=task['cap'],pin=task['cap_pad'],uuid=task['destination_uuid'],
            role='assigned_bypass_return',at_nm=task['b_nm'])]


def targets(board, *, board_hint):
    """Only truly isolated supply or explicitly ground-tied reference lands."""
    rows = [r for r in power.fragmented_ics(power.inventory(board))
        if r['no_other_native_contacts'] and r['role'] in ('supply', 'ground_reference')]
    with force._thermal_hint(board_hint):
        assignment = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    result = []
    for row in rows:
        fp = board.FindFootprintByReference(row['ic'])
        manufacturer = roles.footprint_contract(fp)
        if not manufacturer:
            continue
        caps = [v for v in assignment['assigned'].values()
            if v['requirement']['ref'] == row['ic']
                and (v['requirement'].get('return_rail') or 'GND') == 'GND']
        if row['role'] == 'supply':
            caps = [v for v in caps if str(v['requirement']['pin']) == row['pin']]
        if len(caps) != 1:
            continue
        cap = board.FindFootprintByReference(caps[0]['cap_ref'])
        owner_pad = fp.FindPadByNumber(row['pin'])
        wanted = row['net']
        destination = [p for p in cap.Pads() if str(p.GetNetname()) == wanted]
        if len(destination) != 1:
            continue
        if row['role'] == 'ground_reference':
            grounds = [p for p in fp.Pads() if manufacturer['pins'].get(str(p.GetNumber())) == 'ground'
                and p.GetNetname() == wanted]
            if len(grounds) != 1:
                continue
            graph = pcbnew.CONNECTIVITY_DATA()
            for item in [*(p for f in board.GetFootprints() for p in f.Pads()),
                         *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]:
                if not graph.Add(item):
                    raise ValueError('reference_source_graph_unknown')
            if force._uid(grounds[0]) not in {force._uid(i) for i in graph.GetConnectedItems(destination[0])}:
                continue
        if math.dist(list(owner_pad.GetPosition()), list(destination[0].GetPosition())) > 3.5e6:
            continue
        alternatives=[]
        if row['role']=='ground_reference':
            # A source-verified actual ground land is a valid reference-return
            # destination too. The bypass remains the assignment witness;
            # a long forced detour to its land is not the only legal topology.
            alternatives=[dict(ref=row['ic'],pin=str(p.GetNumber()),uuid=force._uid(p),
                role='manufacturer_ground',at_nm=list(p.GetPosition())) for p in grounds
                if math.dist(list(owner_pad.GetPosition()),list(p.GetPosition()))<=3.5e6]
        result.append(dict(owner=row['ic'], pin=row['pin'], role=row['role'], net=wanted,
            pad_uuid=force._uid(owner_pad), cap=cap.GetReference(), cap_pad=str(destination[0].GetNumber()),
            destination_uuid=force._uid(destination[0]),
            a_nm=list(owner_pad.GetPosition()), b_nm=list(destination[0].GetPosition()),
            verified_ground_alternatives=alternatives))
    return sorted(result, key=lambda r: (r['owner'], r['pin'], r['pad_uuid']))


def _private_retire(board, proposal):
    if leaf._binding(board) != proposal['source_native_binding']:
        raise ValueError('measurement_leaf_source_binding_changed')
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in proposal['track_uuids']])


def _task_leases(tasks):
    """Fund one causal port before reserving an unrelated unsolved port.

    Receiving already requires at least one genuine isolated-terminal gain
    and restoration of the entire owned leaf. A constructor must not cage
    that restoration with a supply path it is not going to construct. The
    multi-port portfolio remains available; this is search ordering only.
    """
    leases=[];seen=set()
    owners=sorted({r['owner'] for r in tasks})[:4]
    for grouped in (False,True):
        for owner in owners:
            cohort=sorted((r for r in tasks if r['owner']==owner),
                key=lambda r:(r['role']!='ground_reference',r['pad_uuid']))
            cohorts=[cohort] if grouped else [[r] for r in cohort]
            for selected in cohorts:
                for mode in ('owner','assigned'):
                    destinations={r['pad_uuid']:_destinations(r)[0 if mode=='owner' else -1]
                        for r in selected}
                    key=tuple(sorted((u,d['uuid']) for u,d in destinations.items()))
                    if key not in seen:
                        leases.append((owner,selected,destinations));seen.add(key)
    return leases


def receive_measurement_reflow(source,candidate,*,board_hint,pad_uuid,timeout_s=10.):
    """Receive ONLY a stationary typed input leaf, not a local supply gain.

    No additional net, barrel, placement, or source boundary can change.
    Construction can free a future routing corridor; this receipt alone does
    not certify an open reduction, the downstream route, or manufacture.
    """
    return receive(source,candidate,board_hint=board_hint,pad_uuid=pad_uuid,
        timeout_s=timeout_s,_construction_role='measurement_leaf_reflow')


def _fresh_native_placement(child, candidate, snapshot_path, data, *, input_companions):
    """Interpret this call's real DRC only for an exact, unique-ID copy.

    No external report parameter or cache enters ``receive``. This private
    helper supplies no saved-board authority: the receiver's native producer,
    full Source/candidate family fence and all electrical gates remain owed.
    Unsupported copies fall back to the unchanged independent diagnostic.
    """
    import cec_fr
    ids = [match.group(3).lower() for match in cec_fr._BOARD_UUID_RE.finditer(snapshot_path.read_text())]
    companions = force._sidecars(candidate)
    produced_companions = force._sidecars(snapshot_path)
    changed = {key for key in companions.keys() | produced_companions.keys()
               if companions.get(key) != produced_companions.get(key)}
    # KiCad can emit a NEW local UI-preference file beside its disposable
    # native input. This is not a rule input. Permit that output only when
    # absent from the exact pre-run copy; never ignore an altered existing
    # companion, rules, or any change to the actual saved candidate family.
    generated_preferences = (changed == {'.kicad_prl'}
        and companions.get('.kicad_prl') is None
        and produced_companions.get('.kicad_prl') is not None)
    if (not ids or len(ids) != len(set(ids))
            or force._hash(snapshot_path) != force._hash(candidate)
            or input_companions != companions
            or changed and not generated_preferences):
        return None
    snapshot = pcbnew.LoadBoard(str(snapshot_path))
    if field._field_snapshot_inventory(snapshot) != field._field_snapshot_inventory(child):
        return None
    physical = geometry._classify_native_snapshot(snapshot, data)
    physical.update(board=str(candidate), sha256=force._hash(candidate),
        source_unchanged=True, diagnostic_identity_normalization=dict(changed=0),
        reused_current_receiver_native_report=True,
        exact_native_geometry_and_unique_ids_rechecked=True,
        exact_snapshot_and_native_rule_companions_rechecked=True,
        native_generated_local_preferences_only=generated_preferences)
    return physical


def receive(source, candidate, *, board_hint, pad_uuid=None, pad_uuids=None, timeout_s=10.,
            _construction_role='stationary_cell_gain'):
    result = dict(schema=1, scope='stationary_cell_measurement_leaf_access_receiving',
        ok=False, complete=False, errors=[], routing_admitted=False, release_authority=False,
        current_authority=False, kelvin_qualified=False, placement_authority_transferred=False)
    try:
        if _construction_role not in ('stationary_cell_gain','measurement_leaf_reflow'):
            raise ValueError('explicit_typed_local_construction_role_required')
        reflow_only=_construction_role=='measurement_leaf_reflow'
        result['scope']=('stationary_measurement_leaf_only_receiving' if reflow_only else result['scope'])
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 10:
            raise ValueError('invalid_local_branch_receiving_budget')
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in (source, candidate)]
        code = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        if ((pad_uuid is None)==(pad_uuids is None)
                or pad_uuids is not None and (type(pad_uuids) not in (list,tuple)
                    or not 1<=len(pad_uuids)<=4)):
            raise ValueError('one_explicit_bounded_stationary_leaf_cohort_required')
        selected=[pad_uuid] if pad_uuids is None else list(pad_uuids)
        if (any(type(uid) is not str or not uid for uid in selected)
                or len(set(selected))!=len(selected)):
            raise ValueError('unique_actual_stationary_measurement_lands_required')
        proposals=[leaf.plan(parent,uid,timeout_s=timeout_s) for uid in selected]
        proposal=proposals[0]
        retained={u for q in proposals for u in q['track_uuids']}
        if (len({q['owner'] for q in proposals})!=1
                or len(retained)!=sum(len(q['track_uuids']) for q in proposals)
                or any(retained&set(q['boundary_uuids']) for q in proposals)):
            raise ValueError('disjoint_same_owner_source_leaves_with_retained_boundaries_required')
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        # Keep an EXACT original contact tail when only the interior escape
        # changes. Less retirement is not broader authority: each surviving
        # native node must be byte-exact and form one boundary-end suffix.
        preserved=set()
        for q in proposals:
            tail=[]
            for uid in reversed(q['track_uuids']):
                if uid not in new:break
                if sexpr._freeze(old[uid])!=sexpr._freeze(new[uid]):
                    raise ValueError('preserved_measurement_contact_tail_changed')
                tail.append(uid)
            if set(q['track_uuids'])&new.keys()!=set(tail):
                raise ValueError('only_exact_contiguous_measurement_contact_tail_may_survive')
            preserved.update(tail)
        retained-=preserved
        if not retained:raise ValueError('actual_source_owned_measurement_reflow_required')
        if old.keys()-new.keys() != retained:
            raise ValueError('leaf_retirement_not_exact_source_owned_scope')
        # No IC/bypass pose, force material, old via or other authored node
        # can be changed by this stationary construction tier.
        if any(sexpr._freeze(old[u]) != sexpr._freeze(new[u]) for u in old.keys()-retained):
            raise ValueError('local_branch_changed_unowned_native_material')
        incoming = new.keys()-old.keys()
        if not 1 <= len(incoming) <= 64:
            raise ValueError('bounded_local_branch_additions_required')
        replacements=[]
        for original in proposals:
            replacement = leaf.plan(child, original['pad_uuid'], timeout_s=timeout_s)
            if (replacement['boundary_uuids'] != original['boundary_uuids']
                    or replacement['points_nm'][0] != original['points_nm'][0]
                    or replacement['points_nm'][-1] != original['points_nm'][-1]
                    or replacement['width_nm'] != original['width_nm']
                    or replacement['layer'] != original['layer']
                    or not set(replacement['track_uuids']) <= incoming|preserved
                    or [u for u in replacement['track_uuids'] if u in preserved]
                        !=[u for u in original['track_uuids'] if u in preserved]):
                raise ValueError('measurement_leaf_boundary_width_or_layer_changed')
            # Keep every OTHER reconstructed member and local link present.
            # A source-minus-whole-cohort query alone could miss new mutual
            # clearances or contacts between the final replacement members.
            scratch = pcbnew.LoadBoard(str(candidate))
            discard_items(scratch, [t for t in scratch.GetTracks()
                if force._uid(t) in replacement['track_uuids']])
            if not leaf.path_clear(scratch, original, replacement['points_nm'], timeout_s=timeout_s):
                raise ValueError('replacement_acquires_unowned_contact_or_clearance_fault')
            replacements.append(replacement)
        tasks = [r for r in targets(parent, board_hint=board_hint) if r['owner'] == proposal['owner']]
        allowed = {r['net'] for r in tasks}
        gained = []
        ground_tracks=[t for t in child.GetTracks() if force._uid(t) in incoming
            and force._uid(t) not in {u for q in replacements for u in q['track_uuids']}
            and t.GetNetname() in {r['net'] for r in tasks if r['role']=='ground_reference'}]
        if ground_tracks:
            import cec_ground_reference_access as ground
            grounded=ground._linear_returns(parent,
                [r for r in tasks if r['role']=='ground_reference'],ground_tracks)
            gained.extend(dict(r['task'],destination=r['destination'],
                native_saved_path_mm=r['saved_native_path_mm']) for r in grounded)
        for row in tasks:
            if row['role']=='ground_reference':continue
            owner = child.FindFootprintByReference(row['owner']).FindPadByNumber(row['pin'])
            cap = child.FindFootprintByReference(row['cap']).FindPadByNumber(row['cap_pad'])
            path = cells._shortest_track_path_mm(child, owner, cap)
            if path is not None and path <= 4.:
                gained.append(dict(row, native_saved_path_mm=path))
        if reflow_only and incoming!={u for q in replacements for u in q['track_uuids']}-preserved:
            raise ValueError('measurement_reflow_cannot_add_nonleaf_material')
        if not gained and not reflow_only:
            raise ValueError('no_source_isolated_cell_terminal_gain')
        new_leaf = {u for q in replacements for u in q['track_uuids']}
        for track in child.GetTracks():
            uid = force._uid(track)
            if uid not in incoming or uid in new_leaf:
                continue
            if track.GetNetname() not in allowed or track.GetClass() != 'PCB_TRACK':
                raise ValueError('unexpected_nonlocal_or_barrel_addition')
            points = [list(track.GetStart()), list(track.GetEnd())]
            if not any(track.GetNetname() == r['net'] and all(
                    min(math.dist(p, r['a_nm']), math.dist(p, r['b_nm'])) <= 4e6 for p in points)
                    for r in tasks):
                raise ValueError('cell_addition_outside_source_locality')
        old_parts = ordinary._partition(parent, time.monotonic()+timeout_s, retired_uuids=retained)
        retained_keys = set().union(*old_parts)
        new_parts = ordinary._partition(child, time.monotonic()+timeout_s, retained_keys=retained_keys)
        if any(not any(p <= q for q in new_parts) for p in old_parts):
            raise ValueError('local_branch_lost_source_terminal_or_conductor_partition')
        with tempfile.TemporaryDirectory(prefix='cec-local-branch-access-') as directory:
            directory = Path(directory)
            projected = force._copy_family(source, directory/'projected')
            baseline = pcbnew.LoadBoard(str(projected))
            discard_items(baseline,[t for t in baseline.GetTracks() if force._uid(t) in retained])
            # A projection is an exact Source-minus-owned-cut, not a new
            # serialization epoch for unrelated groups or footprint fields.
            # Keep the opaque Source records and independently compare the
            # complete native inventory with this positively owned cut.
            result['independent_source_minus_leaf_projection'] = literal_cut.write_native_projection(
                source, projected, retained, baseline)
            delta = additive.receive(projected, candidate, timeout_s=timeout_s)
            result['independent_exact_retirement_additive_replay'] = delta
            if not delta['ok'] or not delta['complete']:
                raise ValueError('local_branch_additive_replay_refused')
            grades = []
            physical = None
            for name, path in [('before', source), ('after', candidate)]:
                isolated = force._copy_family(path, directory/name)
                input_companions = force._sidecars(isolated)
                out = directory/(name+'.json')
                run = subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all',
                    '--output', str(out), str(isolated)], capture_output=True, text=True, timeout=timeout_s)
                if run.returncode:
                    raise ValueError('local_branch_native_drc_failed')
                data = json.loads(out.read_text())
                grades.append(data)
                if name == 'after':
                    # Reuse only THIS receiver's freshly produced native
                    # report, not a caller verdict or a saved/global cache.
                    # Its exact copied rules remain in force. Ambiguous IDs
                    # or any geometry mismatch use the historical independent
                    # diagnostic-normalization path instead, never a waiver.
                    physical = _fresh_native_placement(child, candidate, isolated, data,
                        input_companions=input_companions)
        before, after = grades
        known = {stage._canonical_identity(v) for v in before['violations']}
        unseen = [v for v in after['violations'] if stage._canonical_identity(v) not in known]
        faults, inherited = [], []
        for v in unseen:
            proof = support._inherited_silk_overlap(parent, child, v, old, new)
            (inherited if proof else faults).append(proof or v)
        result.update(source_opens=len(before['unconnected_items']), opens=len(after['unconnected_items']),
            raw_drc=len(after['violations']), new_native_faults=faults,
            positively_proved_inherited_silk_collisions=inherited)
        if faults or (result['opens'] > result['source_opens'] if reflow_only
                      else result['opens'] >= result['source_opens']):
            raise ValueError('no_nonregressing_saved_native_closure')
        if physical is None:
            physical = geometry.evaluate(candidate, timeout_s=timeout_s)
        if physical['ok'] is not True:
            raise ValueError('local_branch_physical_placement_refused')
        with force._thermal_hint(board_hint):
            first = field.field_coupling_summary(str(source), board=parent)
            last = field.field_coupling_summary(str(candidate), board=child)
        field_new = sorted(field.blocker_keys(last)-field.blocker_keys(first))
        if field_new:
            raise ValueError('local_branch_new_field_coupling_blocker')
        stable = families == [force._family(p, board_hint) for p in (source, candidate)] and code == force._code_identity()
        if not stable:
            raise ValueError('local_branch_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            source_leaf=proposal, retained_boundary_uuids=proposal['boundary_uuids'],
            new_leaf=replacements[0],source_leaves=proposals,new_leaves=replacements,
            retired_track_uuids=sorted(retained),retired_via_uuids=[],
            preserved_exact_measurement_contact_tail_uuids=sorted(preserved),
            added_native_uuids=sorted(incoming),gained_source_isolated_terminals=gained,
            all_original_terminal_and_surviving_conductor_partitions_preserved=True,
            exact_force_copper_barrels_and_component_poses_preserved=True,
            physical_placement=physical, new_field_blockers=field_new,
            board=str(candidate), board_sha256=force._hash(candidate),
            full_current_kelvin_stack_and_release_receiving_still_required=True)
        if reflow_only:
            result.update(downstream_route_not_admitted=True,open_reduction_certified=False,
                only_exact_typed_measurement_leaf_changed=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source, directory, *, board_hint, source_sha256, timeout_s=10., max_trials=8):
    if (type(timeout_s) not in (float, int) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
            or type(max_trials) is not int or not 1 <= max_trials <= 8):
        raise ValueError('invalid_branch_access_construction_bounds')
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if directory.exists() or force._hash(source) != source_sha256:
        raise ValueError('fresh_branch_output_and_exact_source_hash_required')
    family, epoch = force._family(source, board_hint), force._code_identity()
    directory.mkdir(parents=True)
    report = dict(schema=1, source=str(source), source_sha256=source_sha256,
        ok=False, release_authority=False, routing_admitted=False, trials=[], refusals=[],
        guarded_paths=0, path_refusal_counts={}, path_refusal_examples=[], maze_searches=[],
        read_only_retired_snapshot_loads=0, constructed_snapshot_loads=0)
    board = pcbnew.LoadBoard(str(source))
    tasks = targets(board, board_hint=board_hint)
    deadline = time.monotonic()+timeout_s
    leases=_task_leases(tasks)
    for owner,cohort,destinations in leases:
        # Reserve the requested local links before ordinary detour search.
        avoid = unary_union([LineString([r['a_nm'], destinations[r['pad_uuid']]['at_nm']]).buffer(325000)
            for r in cohort])
        fp = board.FindFootprintByReference(owner)
        catalog = roles.footprint_contract(fp)
        for pad in fp.Pads():
            if catalog['pins'].get(str(pad.GetNumber())) != 'measurement':
                continue
            try:
                proposal = leaf.plan(board, force._uid(pad), timeout_s=timeout_s)
            except ValueError as exc:
                report['refusals'].append(dict(owner=owner, pin=pad.GetNumber(), reason=str(exc)))
                continue
            original = LineString(proposal['points_nm']).buffer(proposal['width_nm']/2+1000)
            if not original.intersects(avoid):
                continue
            # Failed geometric queries do not mutate a candidate. Keep one
            # exact private source-minus-leaf board warm for this proposal,
            # then reload from source only for actual construction. Never
            # carry its shapes or indexes across a constructed trial/pose.
            scratch = pcbnew.LoadBoard(str(source)); _private_retire(scratch, proposal)
            report['read_only_retired_snapshot_loads'] += 1
            scratch_binding = leaf._binding(scratch)
            compiled=leaf.compile_path_guard(scratch,proposal,avoid=avoid,
                timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            def choices():
                yield from leaf.menus(proposal, avoid=avoid)
                remaining = deadline-time.monotonic()
                if remaining > .1 and len(report['trials']) < max_trials:
                    try:
                        found = leaf.search(scratch, proposal, avoid=avoid, timeout_s=min(2., remaining))
                        report['maze_searches'].append(dict(owner=owner, pin=pad.GetNumber(), **found))
                        if found['points_nm']:
                            yield found['points_nm']
                    except Exception as exc:
                        report['maze_searches'].append(dict(owner=owner, pin=pad.GetNumber(),
                            error=type(exc).__name__+':'+str(exc), no_path_proof=False))
            for points in choices():
                if time.monotonic() >= deadline or len(report['trials']) >= max_trials:
                    break
                try:
                    diagnostic = {}
                    report['guarded_paths'] += 1
                    clear = leaf.path_clear(scratch, proposal, points, avoid=avoid,
                            timeout_s=min(timeout_s, max(.001, deadline-time.monotonic())),
                            diagnostics=diagnostic,_compiled_guard=compiled)
                    if leaf._binding(scratch) != scratch_binding:
                        raise ValueError('read_only_local_branch_snapshot_mutated')
                    if not clear:
                        key = diagnostic['reason']
                        report['path_refusal_counts'][key] = report['path_refusal_counts'].get(key, 0)+1
                        if len(report['path_refusal_examples']) < 24:
                            report['path_refusal_examples'].append(dict(owner=owner,
                                pin=pad.GetNumber(), points_nm=points, **diagnostic))
                        continue
                except Exception as exc:
                    report['refusals'].append(dict(owner=owner, pin=pad.GetNumber(), reason=str(exc)))
                    # A mutating query cannot poison later reuse or borrow
                    # ownership from the removed leaf's private snapshot.
                    if leaf._binding(scratch) != scratch_binding:
                        break
                    continue
                trial = pcbnew.LoadBoard(str(source)); _private_retire(trial, proposal)
                report['constructed_snapshot_loads'] += 1
                if leaf._binding(trial) != scratch_binding:
                    raise ValueError('fresh_local_branch_construction_differs_from_query_source')
                leaf.add_path(trial, proposal, points)
                constructed = []
                with force._thermal_hint(board_hint):
                    for task in cohort:
                        supply = trial.FindFootprintByReference(owner).FindPadByNumber(task['pin'])
                        dest=destinations[task['pad_uuid']]
                        cap = trial.FindFootprintByReference(dest['ref']).FindPadByNumber(dest['pin'])
                        diagnostic = {}
                        remaining = deadline-time.monotonic()
                        if remaining <= 0:
                            break
                        link, error = cells._add_supply_link(trial, supply, cap, lock=True,
                            link_role='shared-ground-entry' if task['role'] == 'ground_reference' else 'supply',
                            diagnostics=diagnostic, search_timeout_s=min(2., remaining))
                        constructed.append(dict(task=task, error=error, link=link, diagnostic=diagnostic))
                record = dict(owner=owner, pad_uuid=force._uid(pad), points_nm=points, cells=constructed)
                report['trials'].append(record)
                if not any(r['link'] is not None for r in constructed):
                    continue
                child = force._copy_family(source, directory/('trial-'+str(len(report['trials'])-1)))
                additive._ground_refill(trial)
                field._save_field_snapshot(trial, child); additive.bind_local_via_rule(trial, child)
                proof = receive(source, child, board_hint=board_hint, pad_uuid=force._uid(pad), timeout_s=timeout_s)
                record['receiving'] = proof
                if proof['ok'] is True:
                    report.update(ok=True, board=str(child), board_sha256=force._hash(child),
                        source_opens=proof['source_opens'], opens=proof['opens'], receiving=proof)
                    break
            if report['ok'] or time.monotonic() >= deadline:
                break
        if report['ok'] or time.monotonic() >= deadline:
            break
    stable = family == force._family(source, board_hint) and epoch == force._code_identity()
    report.update(source_family_and_code_unchanged=stable, construction_lease_exhausted=time.monotonic() >= deadline)
    report['ok'] = report['ok'] and stable
    force._write(directory/'receiving.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--hint', required=True); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.out, board_hint=args.hint, source_sha256=args.source_sha256)
    print(json.dumps({k: report.get(k) for k in ('ok', 'source_opens', 'opens', 'board',
        'source_family_and_code_unchanged', 'construction_lease_exhausted')}), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
