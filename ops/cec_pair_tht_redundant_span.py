"""Retire redundant declared-pair strokes between lands of one unchanged PTH.

This is source-only subtraction, not new routing or a PTH current rating.
Each native track's two centerline ports must lie on the same actual plated
pad. The complete surviving native graph and all pair metrics must survive.
Unchanged pad/plane/bores and exact primitive subset prove no new physical
reference deficit; no approximation, epsilon or layer-connectivity guess is
used to create reference metal. No existing SMD lobe gate is broadened.
"""
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_native_reference_sheet_inclusion as sheets
import cec_ordinary_route_receiving as ordinary
import cec_pair_local_reference_refinement as pairs
from cec_native_items import discard_items

POLICY = 'unchanged-plated-terminal-declared-pair-redundant-stroke-subtraction-v1'
def require(value, message):
    if not value: raise ValueError(message)


def plan(source, *, board_hint, pair_name, track_uuids, allow_locked_source=False):
    source = Path(source).resolve()
    require(type(allow_locked_source) is bool and type(pair_name) is str and pair_name
        and type(board_hint) is str and board_hint, 'explicit_tht_pair_subtraction_context_required')
    cuts = ordinary._ids(track_uuids, 'redundant_tht_pair_source_tracks', 8)
    require(cuts, 'nonempty_bounded_tht_pair_subtraction_required')
    b = pcbnew.LoadBoard(str(source))
    pair_list = [q for q in pairs.precision.derive_coupled_pairs(str(source), board=b) if q['name'] == pair_name]
    require(len(pair_list) == 1, 'one_actual_declared_pair_contract_required')
    pair = pair_list[0]; tracks = {force._uid(t): t for t in b.GetTracks()}
    require(cuts <= tracks.keys(), 'actual_source_tht_pair_tracks_required')
    pads = [pad for pad in b.GetPads() if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pad.HasHole()]
    records = []
    for uid in sorted(cuts):
        t = tracks[uid]
        require(t.GetClass() == 'PCB_TRACK' and t.GetNetname() in (pair['p'], pair['n'])
            and t.GetWidth() == round(pair['width']*1e6) and not t.GetParentGroup()
            and not t.HasSolderMask() and (not t.IsLocked() or allow_locked_source),
            'literal_pair_width_net_face_process_and_source_lock_required')
        owners = [pad for pad in pads if pad.GetNetname() == t.GetNetname() and pad.IsOnLayer(t.GetLayer())
            and all(pad.GetEffectiveShape(t.GetLayer()).Collide(point) for point in (t.GetStart(), t.GetEnd()))]
        require(len(owners) == 1, 'both_source_ports_must_share_one_actual_plated_pad')
        pad = owners[0]
        # This records a source interface, not full-disc containment. The
        # complete native after-cut graph and pair completion below decide
        # whether all unchanged conductors really still reach their lands.
        records.append(dict(track_uuid=uid, pad_uuid=force._uid(pad), net=t.GetNetname(),
            layer=int(t.GetLayer()), source_length_nm=t.GetLength()))
    return dict(policy=POLICY, source_sha256=force._hash(source), code_identity=force._code_identity(),
        authority_sha256=force._hash(Path(__file__)), board_hint=board_hint, pair_name=pair_name,
        pair=pair, track_uuids=sorted(cuts), allow_locked_source=allow_locked_source, records=records,
        source_centerline_length_nm=sum(row['source_length_nm'] for row in records),
        new_copper_or_drills=0, source_terminal_or_barrel_current_qualified=False, release_authority=False)


def construct(source, proposal):
    fresh = plan(source, **{k: proposal[k] for k in ('board_hint', 'pair_name', 'track_uuids', 'allow_locked_source')})
    require(fresh == proposal, 'stale_or_forged_tht_pair_subtraction_plan')
    b = pcbnew.LoadBoard(str(source))
    discard_items(b, [t for t in b.GetTracks() if force._uid(t) in proposal['track_uuids']])
    return b


def receive(source, candidate, proposal, *, board_hint):
    result = dict(ok=False, complete=False, errors=[], pair_or_terminal_current_qualified=False,
        current_budget_or_width_floor_changed=False, release_authority=False)
    try:
        source, candidate = [Path(q).resolve() for q in (source, candidate)]
        epoch = force._code_identity(); families = [force._family(q, board_hint) for q in (source, candidate)]
        require(source != candidate and proposal['board_hint'] == board_hint, 'distinct_actual_tht_pair_child_required')
        b = construct(source, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-tht-pair-subtraction-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            field._save_field_snapshot(b, expected)
            require(syntax._freeze(additive._nodes(expected)[0]) == syntax._freeze(additive._nodes(candidate)[0]),
                'tht_pair_subtraction_changed_unowned_saved_native_evidence')
        require(force._sidecars(source) == force._sidecars(candidate)
            and force._preservation_snapshot(source)[1] == force._preservation_snapshot(candidate)[1],
            'tht_pair_subtraction_parts_copper_contracts_fields_stack_or_rules_changed')
        boards = [pcbnew.LoadBoard(str(q)) for q in (source, candidate)]
        part = ordinary._partition(boards[0], time.monotonic()+10., retired_uuids=set(proposal['track_uuids']))
        after = ordinary._partition(boards[1], time.monotonic()+10., retained_keys=set().union(*part))
        require(all(any(p <= q for q in after) for p in part), 'tht_pair_subtraction_lost_a_surviving_native_partition')
        pair = proposal['pair']
        completion = pairs.precision._native_pair_completion(boards[1], pair)
        require(completion['complete'] and completion['connected']
            and not any(q.get('disconnected_copper_uuids') for q in completion['nets'].values()),
            'tht_pair_subtraction_requires_complete_actual_pair_connectivity')
        reference = sheets.receive(source, candidate, board_hint=board_hint, timeout_s=10.)
        require(reference['ok'] and reference['complete'], 'tht_pair_source_actual_reference_sheets_or_drills_changed')
        old, new = [additive._nodes(q)[1] for q in (source, candidate)]
        require(old.keys()-new.keys() == set(proposal['track_uuids']) and not new.keys()-old.keys()
            and all(syntax._freeze(n) == syntax._freeze(new[u]) for u, n in old.items() if u in new),
            'only_literal_received_pair_source_strokes_may_be_retired')
        continuous = pairs.compare_continuous(*[pairs.continuous_from_board(b, pair) for b in boards])
        require(continuous['ok'], 'tht_pair_subtraction_increased_continuous_member_deficit')
        samples = []
        for step in (.5, .25, .1):
            with force._thermal_hint(board_hint):
                metrics = [next(row for row in pairs.constraints.high_speed_pair_summary(str(q), board=b, sample_mm=step)['pairs']
                    if (row['p'], row['n']) == (pair['p'], pair['n'])) for q, b in zip((source, candidate), boards)]
            comparison = pairs.metric_progress(*metrics, coupling=continuous)
            require(comparison['ok'], 'tht_pair_subtraction_full_pair_metrics_regressed:'+str(comparison['errors']))
            samples.append(dict(sample_mm=step, before=metrics[0], after=metrics[1], comparison=comparison))
        debt = current.receive(source, candidate, board_hint=board_hint)
        require(debt['ok'] and debt['complete'], 'tht_pair_subtraction_current_debt_regressed_or_unknown')
        require(epoch == force._code_identity() and families == [force._family(q, board_hint) for q in (source, candidate)],
            'tht_pair_subtraction_input_or_epoch_changed')
        result.update(ok=True, complete=True, code_identity=epoch, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            exact_saved_native_subtraction=True, retired_track_uuids=proposal['track_uuids'],
            every_surviving_pair_and_other_native_partition_preserved=True, exact_pair_completion=completion,
            native_ground_sheet_preservation=reference, source_physical_pair_material_subset_by_exact_primitive_retirement=True,
            continuous_pair_comparison=continuous, full_pair_metric_samples=samples, whole_parent_current_receiving=debt,
            centerline_removed_mm=proposal['source_centerline_length_nm']/1e6,
            native_drc_field_kelvin_ground_and_whole_parent_receiving_still_required=True)
    except (ValueError, RuntimeError, AssertionError, KeyError, TypeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
