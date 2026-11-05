"""Bounded certified island closure BEFORE copper or footprint displacement.

Uses the existing exact router and admission contract. Only a current native
residual snapshot may schedule this stage; it is never a routing waiver.
"""
from __future__ import annotations

import copy
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import time


def bound_snapshot(board_path, completion):
    import cec_certificate_repair as repair
    import cec_final_residual as residual
    payload = repair._completion_payload(completion)
    report = payload.get('final_residual')
    try:
        return bool(residual.valid_snapshot(report) and
                    residual._identity(board_path) == report['source_identity'])
    except (OSError, ValueError):
        return False


def prepare_completion(source_path, scratch_path, completion):
    """Remeasure after family-copy metadata relocation; never forge a binding.

    The normal copier rehomes the frozen skeleton pointer and project name.
    Those byte changes correctly invalidate the old snapshot. A fresh native
    survey of the copied artifact is cheaper and narrower than a whole-net
    route search, and still validates exactly the artifact being repaired.
    """
    import cec_certificate_repair as repair
    if bound_snapshot(scratch_path, completion):
        return completion, dict(status='already_bound_to_scratch')
    if not bound_snapshot(source_path, completion):
        return completion, dict(status='source_snapshot_not_current')
    try:
        fresh = repair._spawn_apply(fresh_completion, (str(scratch_path),), timeout_s=25.)
        if bound_snapshot(scratch_path, fresh):
            return fresh, dict(status='native_remeasurement_after_copy')
        return completion, dict(status='copy_remeasurement_not_bound')
    except Exception as exc:
        return completion, dict(status='copy_remeasurement_failed',
            error='%s: %s' % (type(exc).__name__, str(exc)[:400]))


def fair_targets(rows):
    """Interleave nets, retaining nearest-first deterministic local choices."""
    buckets = defaultdict(list)
    for row in rows:
        ends = row['route_endpoints']
        distance = math.hypot(ends[0]['x_mm']-ends[1]['x_mm'],
                              ends[0]['y_mm']-ends[1]['y_mm'])
        buckets[row['target_net']].append((distance, row['pair_key'], row))
    ranked = []
    for values in buckets.values():
        values.sort(key=lambda value: value[:2])
        ranked.extend((index, distance, key, row)
                      for index, (distance, key, row) in enumerate(values))
    return [row for _, _, _, row in sorted(ranked, key=lambda value: value[:3])]


def scheduling_feedback(prior, attempts):
    """Bounded retry ordering only, never a clearance or no-path certificate.

    Geometry changes invalidate sampled-domain suppression, but need not erase
    the fact that a pair was just tried. Retain that observation to visit fresh
    pairs before returning to costly/refused ones. A fresh native snapshot and
    every construction/receiving check are still required on the changed PCB.
    """
    counts = {}
    for key, value in (prior.items() if isinstance(prior, dict) else ()):
        if (type(key) is str and 0 < len(key) <= 128 and type(value) is int
                and 0 < value <= 4096):
            counts[key] = value
        if len(counts) >= 4096:
            break
    for row in attempts[:4096] if isinstance(attempts, list) else ():
        target = row.get('target') if isinstance(row, dict) else None
        key = target.get('pair_key') if isinstance(target, dict) else None
        # A process-startup exception is not evidence of attempted geometry.
        if (type(key) is str and 0 < len(key) <= 128
                and isinstance(row.get('completion'), dict)):
            if key in counts or len(counts) < 4096:
                counts[key] = min(4096, counts.get(key, 0) + 1)
    return counts


def _unsampled_native_pairs_worker(board_path, report):
    """Resolve every omitted open, not just the optional diagnostic ray sample.

    These are native endpoint demands, not clearance certificates or routing
    permission. The constructor still proves its actual path independently.
    """
    import pcbnew
    import cec_final_residual as residual
    import cec_route_dimensions as dimensions
    if not residual.valid_snapshot(report) or residual._identity(board_path) != report['source_identity']:
        raise ValueError('current_native_frontier_snapshot_required')
    board = pcbnew.LoadBoard(board_path)
    objects = {item.m_Uuid.AsString(): item for item in board.GetTracks()}
    objects.update({zone.m_Uuid.AsString(): zone for zone in board.Zones()})
    objects.update({pad.m_Uuid.AsString(): pad for fp in board.GetFootprints() for pad in fp.Pads()})
    resolver = dimensions.project_resolver(board_path, board=board)
    sampled = {row['index'] for row in report['residual_details']}
    rows, errors = [], []
    for index, row in enumerate(report['unconnected_items']):
        if index in sampled:
            continue
        try:
            items = row.get('items') or []
            if len(items) != 2:
                raise ValueError('native_open_requires_two_endpoints')
            a, start, endpoint_a = residual._endpoint(items[0], objects, board)
            b, end, endpoint_b = residual._endpoint(items[1], objects, board)
            if a.GetNetCode() != b.GetNetCode():
                raise ValueError('native_open_endpoints_have_different_nets')
            endpoints = [dict(endpoint_a, endpoint='a', x_mm=start[0], y_mm=start[1]),
                         dict(endpoint_b, endpoint='b', x_mm=end[0], y_mm=end[1])]
            spec = resolver(endpoint_a['net'])
            rows.append(dict(detail=dict(index=index, distance_mm=math.dist(start, end)),
                certificate=dict(net=endpoint_a['net'], endpoints=endpoints,
                    width_mm=spec['track_width'], clearance_mm=spec['clearance'],
                    conclusion='native_demand_not_a_path_clearance_proof',
                    search=dict(performed=False))))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(dict(index=index, reason=str(exc)))
    if residual._identity(board_path) != report['source_identity']:
        raise ValueError('native_frontier_source_changed')
    return dict(rows=rows, errors=errors)


def targets(board_path, completion, *, limit=8):
    import cec_certificate_repair as repair
    if not bound_snapshot(board_path, completion):
        return dict(targets=[], skipped=[], stop='current_snapshot_required')
    protected = repair._spawn_apply(_protected_nets_worker, (str(board_path),))
    rows, skipped, seen = [], [], set()
    refusals = list(repair.refusal_certificates(completion))
    native = repair._completion_payload(completion).get('final_residual') or {}
    if native.get('details_missing', 0) > 0:
        frontier = repair._spawn_apply(_unsampled_native_pairs_worker, (str(board_path), native))
        refusals.extend(frontier['rows'])
        skipped.extend(frontier['errors'])
    for refusal in refusals:
        cert, detail = refusal['certificate'], refusal['detail']
        net = str(cert.get('net') or detail.get('net') or '')
        endpoints = cert.get('endpoints')
        try:
            valid = (net and isinstance(endpoints, list) and len(endpoints) == 2 and
                     all(isinstance(p, dict) and all(math.isfinite(float(p[k]))
                         for k in ('x_mm', 'y_mm')) for p in endpoints))
            width = float(cert.get('width_mm') or .25)
            clearance = float(cert.get('clearance_mm') or 0.)
            distance = float(detail.get('distance_mm') or 0.)
            valid = valid and all(math.isfinite(v) and v >= 0 for v in
                                  (width, clearance, distance)) and width > 0
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            skipped.append(dict(net=net, reason='invalid_certificate_pair'))
            continue
        reason = protected.get(net) or repair.protected_net_reason(net, width_mm=width)
        if reason:
            skipped.append(dict(net=net, reason=reason))
            continue
        identity = [net, sorted(json.dumps({k: p.get(k) for k in
                    ('kind', 'uuid', 'ref', 'pad', 'x_mm', 'y_mm', 'copper_layers')},
                    sort_keys=True) for p in endpoints)]
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(target_net=net, route_endpoints=copy.deepcopy(endpoints),
                         width_mm=width, clearance_mm=clearance,
                         distance_mm=distance, pair_key=key))
    # Pure distance order lets several short, caged lands exhaust every
    # batch before other nets get any search. Grant one frontier per net
    # before revisiting that net; neither ordering grants routing authority.
    rows = fair_targets(rows)
    return dict(targets=rows[:max(0, int(limit))], skipped=skipped,
                stop='planned', eligible_count=len(rows))


def _protected_nets_worker(board_path):
    import pcbnew
    import cec_fr
    from cec_pair_semantics import coupled_pair_names, analog_input_pairs
    board = pcbnew.LoadBoard(board_path)
    protected = {net: 'coupled_pair' for _, p, n in coupled_pair_names(board) for net in (p, n)}
    protected.update({net: 'kelvin_or_sense' for pair in cec_fr._board_kelvin_pairs(board)
                      for net in pair})
    protected.update({row[key]: 'kelvin_or_sense' for row in analog_input_pairs(board)
                      for key in ('p', 'n')})
    resolver = cec_fr._project_netclass_resolver(board_path)
    import cec_current_topology as topology
    hint = os.environ.get('CEC_THERMAL_BOARD_HINT') or str(board_path)
    domains = topology.board_current_domains(board, board_hint=hint)
    for info in board.GetNetInfo().NetsByNetcode().values():
        net = info.GetNetname()
        spec = resolver(net) or {}
        if float(spec.get('track_width') or 0.) > 1.0:
            protected[net] = 'wide_or_high_current'
        authority = topology.current_contract_for_net(net, hint, domains)
        if (authority is not None and net.rsplit('/', 1)[-1] != 'GND'):
            amps = authority.get('amps') if isinstance(authority, dict) else None
            if type(amps) not in (int, float) or not math.isfinite(amps) or amps < 0:
                protected[net] = 'explicit_current_authority_invalid'
            elif amps > 0:
                # A netclass width is not an ampacity/barrel proof. Explicit
                # supplies belong to the existing current-rated constructors,
                # even if their ordinary project width happens to be 0.2 mm.
                protected[net] = 'explicit_current_rated_constructor_required'
    return protected


def _invariant_worker(before_path, after_path):
    """The additive stage may add copper, never move/remove/relabel old objects."""
    import pcbnew
    import cec_interface_eco as eco
    import cec_local_copper_cell as cell
    import cec_route_copper_lineage as lineage
    import cec_placement_route_prefix as prefix
    import cec_fr
    from cec_ground_plane import _zone_declaration_signature
    before, after = (pcbnew.LoadBoard(str(p)) for p in (before_path, after_path))
    old, new = cell.copper_inventory(before), cell.copper_inventory(after)
    terms = dict(existing_copper_exact=all(new.get(k) == v for k, v in old.items()),
                 footprint_poses_exact=eco.poses(before) == eco.poses(after),
                 electrical_identity_exact=lineage.electrical_identity(before) ==
                                           lineage.electrical_identity(after),
                 zone_declarations_exact=_zone_declaration_signature(before) ==
                                         _zone_declaration_signature(after))
    for suffix in ('.kicad_pro', '.kicad_dru'):
        a, b = (Path(p).with_suffix(suffix) for p in (before_path, after_path))
        terms[suffix] = (a.exists() == b.exists() and
                        (not a.exists() or eco.rule_digest(a) == eco.rule_digest(b)))
    # A retention proof is not a completed-power ownership grant. Exact
    # source-plus-delta replay below retains even unadmitted local copper.
    frozen = prefix.capture(before_path,include_local_authority=False)
    terms['protected_copper_exact'] = cec_fr.check_copper_geometry_prefix(after_path, frozen)['ok']
    terms['qualified_pairs_exact'] = prefix.check_qualified_pairs(after_path, frozen)['ok']
    import cec_additive_route_receiving
    replay=cec_additive_route_receiving.receive(before_path,after_path,
        allow_endpoint_neckdown_additions=True,
        board_hint=os.environ.get('CEC_THERMAL_BOARD_HINT') or str(before_path))
    terms['native_source_delta_replay'] = replay.get('ok') is True and replay.get('complete') is True
    # An incoming qualified POFV member can lower its exact-object group rule.
    # Accept only the independent source-derived rule, never a broad waiver.
    terms['.kicad_dru'] = replay.get('exact_object_rule_matches_independent_native_replay') is True
    import cec_current_debt
    current = cec_current_debt.receive(before_path, after_path,
        board_hint=os.environ.get('CEC_THERMAL_BOARD_HINT') or str(before_path))
    terms['exact_current_debt_nonregression'] = current.get('ok') is True and current.get('complete') is True
    current = {key: value for key, value in current.items()
               if key not in ('before_result', 'after_result')}
    return dict(ok=all(terms.values()), terms=terms, native_replay=replay, current_debt=current,
                added_items=len(new.keys()-old.keys()),release_authority=False)


def save_native_additions(board_path,board,report,original_track_uuids,*,board_hint=None):
    """Finalize only additive copper, ground antipads and exact new-via rules.

    No global normalization, re-netting or power refill. The independent
    source-delta receiver and native DRC still decide whether this child is
    admissible. Existing power debt remains debt; its copper stays exact.
    """
    import cec_additive_route_receiving as receiving
    import cec_field_coupling as field
    import cec_fr
    import pcbnew
    import tempfile
    import cec_source_retaining_ses_import as source_text_io
    import cec_source_literal_additions as literal_additions
    # Read the actual saved target before any native serializer can normalize
    # opaque source footprints, fields, root metadata or purposeful copper.
    original_source_text = source_text_io.raw_text(board_path)
    import cec_additive_portal_compaction
    import cec_new_track_body_echo
    report['new_native_body_echo_compaction']=cec_new_track_body_echo.compact(board,original_track_uuids)
    report['new_portal_compaction']=cec_additive_portal_compaction.compact(
        board,original_track_uuids,board_path=board_path,board_hint=board_hint)
    additions=[item for item in board.GetTracks()
               if item.m_Uuid.AsString() not in original_track_uuids]
    pofv=cec_fr.group_local_pofv_signal_vias(board,additions)
    if pofv:report['local_pofv_signal_vias']=pofv
    ground=receiving._ground_refill(board)
    # Native serialization contributes only exact new copper/group nodes and
    # native existing-GND fill children. Never serialize source FPs into target.
    with tempfile.TemporaryDirectory(prefix='.cec-literal-additive-',
            dir=Path(board_path).resolve().parent) as work:
        native_path = Path(work) / 'native.kicad_pcb'
        field._save_field_snapshot(board,native_path)
        native_text = source_text_io.raw_text(native_path)
        literal_text = literal_additions.assemble(
            original_source_text, native_text, ground_ids=ground)
    if source_text_io.raw_text(board_path) != original_source_text:
        raise ValueError('literal_additive_target_changed_before_publish')
    source_text_io.write_raw(board_path, literal_text)
    report['source_literal_additive_producer'] = dict(
        source_sha256=hashlib.sha256(original_source_text.encode('utf-8')).hexdigest(),
        native_sha256=hashlib.sha256(native_text.encode('utf-8')).hexdigest(),
        output_sha256=hashlib.sha256(literal_text.encode('utf-8')).hexdigest(),
        retained_original_root_and_source_nodes=True,
        only_native_additions_ground_fills_and_typed_monotone_group_members=True,
        requires_independent_native_current_and_source_replay=True,
        release_authority=False)
    # Emit exact canonical group rules from the actual literal saved child,
    # not from a serializer-normalized in-memory source representation.
    saved_board = pcbnew.LoadBoard(str(board_path))
    report['local_pofv_signal_via_rule']=receiving.bind_local_via_rule(saved_board,board_path)
    incoming_endpoints=[i for g in saved_board.Groups() if g.GetName()==cec_fr.ENDPOINT_NECKDOWN_GROUP
        for i in g.GetItems() if i.m_Uuid.AsString() not in original_track_uuids]
    if incoming_endpoints:
        report['native_complete_endpoint_group_rule']=receiving.bind_local_endpoint_rule(saved_board,board_path)
    report['zone_refill']=dict(scope='existing_ground_only',performed=bool(ground),
        ground_uuids=ground,protected_power_fill_recompiled=False)
    return report


def _target_worker(board_path,target,search_s):
    import cec_certificate_repair as repair
    return repair._certified_via_target_worker(
        board_path,target,search_s,additive_only=True)


def _search_allowance(remaining_s, *, min_search_s=5., admission_reserve_s=10.,
                      max_watchdog_s=45.):
    """Fund useful search plus save/IPC and admission, or decline the trial."""
    watchdog = min(max_watchdog_s, remaining_s - admission_reserve_s)
    search = watchdog - min(5., watchdog * .2)
    return (watchdog, search) if search >= min_search_s else None


def attempt(board_path, before, target, *, work_dir, token,
            wall_budget_s=60., effort=None, preserve_family=False):
    import cec_certificate_repair as repair
    if not math.isfinite(wall_budget_s) or wall_budget_s <= 0:
        raise ValueError('additive stage budget must be finite and positive')
    deadline = time.monotonic() + wall_budget_s
    parent = repair._WORKER_DEADLINE.get()
    if parent is not None:
        deadline = min(parent, deadline)
    if _search_allowance(deadline-time.monotonic()) is None:
        return dict(adopted=False, attempts=[], stop='additive_stage_wall_budget')
    if effort is not None and not effort.claim('certified_additive'):
        return dict(adopted=False, attempts=[], stop='effort_budget')
    trial = None
    row = dict(stage='certified_additive', target=target, accepted=False)
    deadline_token = repair._WORKER_DEADLINE.set(deadline)
    try:
        import cec_force_current
        trial = str(cec_force_current._copy_family(
            board_path,Path(work_dir)/('additive-'+str(token))))
        # Reserve admission time and native-save/IPC time inside the parent cap.
        remaining = deadline-time.monotonic()
        allowance = _search_allowance(remaining)
        if allowance is None:
            return dict(adopted=False, attempts=[], stop='additive_stage_wall_budget')
        watchdog, search = allowance
        row.update(target_budget_s=search, target_watchdog_s=watchdog)
        completion = repair._spawn_apply(_target_worker,
            (trial, target, search), timeout_s=watchdog)
        row['completion'] = completion
        if not completion.get('closed'):
            row['decision'] = ('target_search_timeout' if completion.get('timed_out')
                               else 'target_still_refused')
        else:
            # The constructor saved a ground-only source-delta transaction;
            # a second global refill would destroy its exact power boundary.
            # Diagnostics are not incoming authority companions. A same-stem
            # board.drc.json becomes part of the exact saved family and used
            # to make our own fresh DRC invalidate every additive receipt.
            drc_path = str(Path(work_dir)/('additive-'+str(token)+'-native-drc.json'))
            repair._spawn_apply(repair._run_drc, (trial, drc_path))
            after = repair._spawn_apply(repair._score_worker, (trial, drc_path))
            ok, decision = repair._accepts(before, after)
            invariants = repair._spawn_apply(_invariant_worker, (board_path, trial))
            row.update(after=after, invariants=invariants,
                       accepted=bool(ok and invariants['ok']),
                       decision=decision if invariants['ok'] else 'additive_invariants_regressed')
            if row['accepted']:
                if preserve_family:
                    # This portfolio owns only PCB additions and their exact
                    # via rule. Preserve every opaque authority sidecar; no
                    # rebinding or newly claimed replacement authority here.
                    import shutil
                    shutil.copy2(trial,board_path)
                    for suffix in ('.kicad_dru',):
                        rule=Path(trial).with_suffix(suffix)
                        if rule.is_file():shutil.copy2(rule,Path(board_path).with_suffix(suffix))
                    row['lineage']=dict(written=False,reason='retention_only_portfolio',
                        grants_replacement_authority=False)
                else:
                    row['lineage'] = repair._spawn_apply(_record_worker, (board_path, trial))
                    repair._copy_board_family(trial, board_path)
                return dict(adopted=True, attempts=[row], accepted=row, after=after,
                            stop='accepted_one_remeasure_required')
    except Exception as exc:
        row.update(decision='additive_worker_error', error='%s: %s' %
                   (type(exc).__name__, str(exc)[:600]))
    finally:
        repair._WORKER_DEADLINE.reset(deadline_token)
    return dict(adopted=False, attempts=[row], stop=row['decision'])


def _record_worker(before_path, after_path):
    import cec_route_copper_lineage as lineage
    return lineage.record_optional(before_path, after_path, producer='certified-additive-pair')


def fresh_completion(board_path):
    import cec_final_residual as residual
    return dict(final_residual=residual.measure(board_path, max_details=32, wall_timeout_s=20.))


def sweep(board_path, before, completion, *, work_dir, effort,
          stage_budget_s=60., max_targets=4, preserve_family=False,
          scheduling_history=None):
    """Finite breadth-first attempts, then remeasure before using another pair."""
    import cec_certificate_repair as repair
    import cec_final_residual as residual
    prior = ((completion or {}).get('plan') or {}).get('certified_additive') or {}
    # History cannot consume the candidate limit: skip previously funded
    # pairs, THEN count this wave's new trials. Keep inspection itself bounded.
    prior_budgets = prior.get('sampled_pair_budgets') or {}
    feedback = scheduling_feedback(scheduling_history, [])
    planned = targets(board_path, completion,
                      limit=max(0, int(max_targets)) +
                            min(4096, len(prior_budgets) + len(feedback)))
    report = dict(schema=1, **planned, attempts=[], adopted=False,
                  schedule='before_live_probe_and_displacement', wall_budget_s=stage_budget_s)
    if not planned['targets']:
        return report
    report.update(input_identity=residual._identity(board_path),
                  algorithm_revision=repair.REPAIR_ALGORITHM_REVISION)
    sampled = {}
    if (prior.get('input_identity') == report['input_identity'] and
            prior.get('algorithm_revision') == report['algorithm_revision']):
        sampled = {key: float(value) for key, value in prior_budgets.items()
                   if isinstance(value, (int, float)) and math.isfinite(value) and value > 0}
    report['sampled_pair_budgets'] = sampled
    report['tried_pair_keys'] = sorted(sampled)
    # Partial searches must not consume every fresh batch before untouched
    # demands. Retain deterministic net fairness within the unseen tier;
    # afterward allow larger funded retries, smallest prior budget first.
    planned['targets'] = sorted(planned['targets'],
        key=lambda target: (sampled.get(target['pair_key'], 0.),
                            feedback.get(target['pair_key'], 0)))
    report['scheduling_feedback'] = dict(scope='ordering_only_no_search_suppression',
        previous_pair_count=len(feedback))
    deadline = time.monotonic()+stage_budget_s
    tried = 0
    for index, target in enumerate(planned['targets']):
        remaining = deadline-time.monotonic()
        allowance = _search_allowance(remaining)
        if allowance is None:
            report['stop'] = 'additive_stage_wall_budget'
            break
        _watchdog, planned_search = allowance
        if sampled.get(target['pair_key'], 0.) >= planned_search:
            report['stop'] = 'unchanged_pair_domain_already_sampled'
            continue
        if tried >= max(0, int(max_targets)):
            report['stop'] = 'additive_stage_attempt_budget'
            break
        result = attempt(board_path, before, target, work_dir=work_dir,
                         token=index, wall_budget_s=remaining, effort=effort,
                         preserve_family=preserve_family)
        report['attempts'].extend(result['attempts'])
        if result['attempts']:
            tried += 1
            # Failed worker startup/IPC is not sampled geometry. Only an
            # actual returned search report can suppress an equivalent retry.
            used = max((float(row.get('target_budget_s') or 0.)
                        for row in result['attempts']
                        if isinstance(row.get('completion'), dict)), default=0.)
            if used > 0:
                sampled[target['pair_key']] = max(used, sampled.get(target['pair_key'], 0.))
            report['tried_pair_keys'] = sorted(sampled)
        report['stop'] = result['stop']
        if result['adopted']:
            report.update(adopted=True, after=result['after'], accepted=result['accepted'])
            break
    return report
