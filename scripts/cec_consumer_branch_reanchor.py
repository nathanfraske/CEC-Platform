"""Exact reconstruction of an existing, positively typed consumer feed.

This first bounded operator reuses only retained native terminals/barrels.
It may replace ungrouped thin source-feed tracks and raise exclusive leaf
tracks to their independently recomputed current floor. It cannot change
parts, barrels, pours, interfaces, aggregate budgets, rules or other groups.
Native DRC, Kelvin, field and release receiving remain separate obligations.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_force_current as force
import cec_fab_profile as fab
import cec_ordinary_route_receiving as ordinary
import cec_supply_consumer_branch as consumer
from cec_native_items import discard_items


def _positive_budget(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_consumer_reanchor_receiving_required')
    return time.monotonic() + timeout_s


def _check(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('consumer_reanchor_receiving_deadline')


def receive(source, candidate, *, board_hint, root_pad_uuid,
            retired_track_uuids, timeout_s=10.):
    """Prove the saved child from source primitives, not a producer's receipt.

    IDs select a proposal; native topology and existing design/manufacturer
    contracts grant its scope. Widths are independently derived, never copied
    from a candidate budget or divided by the number of available layers.
    """
    result = dict(schema=1, scope='exclusive_consumer_feed_exact_reconstruction',
        ok=False, complete=False, errors=[], release_authority=False,
        current_qualified=False, new_barrel_capacity_credited=False,
        whole_board_qualification_still_required=True)
    try:
        deadline = _positive_budget(timeout_s)
        if type(board_hint) is not str or not board_hint:
            raise ValueError('consumer_reanchor_design_identity_required')
        if (not isinstance(retired_track_uuids, (list, tuple, set, frozenset))
                or not 1 <= len(retired_track_uuids) <= 8
                or len(set(retired_track_uuids)) != len(retired_track_uuids)):
            raise ValueError('bounded_unique_source_feed_cut_required')
        retired = set(retired_track_uuids)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        baseline = consumer.inventory(parent, board_hint=board_hint, timeout_s=timeout_s)
        rows = [r for r in baseline['proofs'] if r['root_pad_uuid'] == root_pad_uuid]
        if not baseline['complete'] or len(rows) != 1:
            raise ValueError('one_valid_existing_consumer_scope_required')
        source_proof = rows[0]
        groups = [g for g in parent.Groups()
            if g.GetName().startswith(consumer.PREFIX + root_pad_uuid + '|')]
        if len(groups) != 1 or groups[0].GetParentGroup() is not None:
            raise ValueError('one_existing_native_consumer_group_required')
        group = groups[0]; gid = force._uid(group)
        old_members = set(map(force._uid, group.GetItems()))
        old_name = group.GetName()[len(consumer.PREFIX):].split('|')
        child_groups = [g for g in child.Groups() if force._uid(g) == gid]
        if len(child_groups) != 1:
            raise ValueError('consumer_reanchor_group_identity_changed')
        child_group = child_groups[0]
        prefix = consumer.PREFIX + root_pad_uuid + '|'
        if not child_group.GetName().startswith(prefix):
            raise ValueError('consumer_reanchor_root_or_model_changed')
        proposed = child_group.GetName()[len(consumer.PREFIX):].split('|')
        if (len(proposed) != 3 or proposed[1] == old_name[1]
                or proposed[2] != ','.join(sorted(filter(None, old_name[2].split(','))))):
            raise ValueError('consumer_reanchor_requires_new_retained_tap_and_unchanged_barrels')
        tracks = {force._uid(t): t for t in parent.GetTracks()}
        pads = {force._uid(p): p for f in parent.GetFootprints() for p in f.Pads()}
        native = {**pads, **tracks}
        if (not retired <= tracks.keys() or root_pad_uuid not in pads
                or proposed[1] not in native):
            raise ValueError('consumer_reanchor_source_material_missing')
        root = pads[root_pad_uuid]; net = str(root.GetNetname())
        if any(tracks[u].GetClass() != 'PCB_TRACK'
                or tracks[u].GetNetname() != net
                or tracks[u].GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
                or tracks[u].GetParentGroup() is not None
                or not 0 < tracks[u].GetWidth() <= 350000
                or not 0 < tracks[u].GetLength() <= 32000000 for u in retired):
            raise ValueError('consumer_reanchor_requires_bounded_ungrouped_outer_source_feed')
        if native[proposed[1]].GetClass() not in ('PAD', 'PCB_VIA'):
            raise ValueError('consumer_reanchor_requires_retained_native_terminal')
        old_root, old_nodes = additive._nodes(source)
        _, new_nodes = additive._nodes(candidate)
        if old_nodes.keys() - new_nodes.keys() != retired:
            raise ValueError('consumer_reanchor_retirement_differs_from_exact_cut')
        incoming = new_nodes.keys() - old_nodes.keys()
        replacement = {force._uid(t): t for t in child.GetTracks()
            if force._uid(t) in incoming}
        if not 1 <= len(incoming) <= 64 or replacement.keys() != incoming:
            raise ValueError('consumer_reanchor_additions_must_be_only_bounded_native_tracks')
        source_length = sum(tracks[u].GetLength() for u in retired)
        # Source-minus-cut is the load scope. A label or a nearby power IC
        # cannot make an unrelated shared rail acquire this local allowance.
        discard_items(parent, [tracks[u] for u in sorted(retired)])
        material = {force._uid(i): i for i in [*pads.values(), *parent.GetTracks(),
            *[z for z in parent.Zones() if not z.GetIsRuleArea()]] if i.GetNetname() == net}
        graph = consumer._graph(list(material.values()), deadline)
        island, monitors = consumer._island(parent, root, graph, material, deadline)
        if proposed[1] in island or not old_members <= island:
            raise ValueError('consumer_reanchor_cut_not_an_exclusive_source_leaf')
        budget = consumer._with_closed_monitor_loads(parent,
            consumer.contract(parent, root_pad_uuid, board_hint=board_hint), monitors)
        if any(t.GetClass() != 'PCB_TRACK' or t.GetNetname() != net
                or t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
                or t.GetWidth() != math.ceil(budget['required_by_layer_mm'][
                    fab.COPPER_LAYER_IDS[t.GetLayer()]]*1e6)
                or t.GetLength() <= 0 for t in replacement.values()):
            raise ValueError('consumer_reanchor_incoming_not_whole_local_current_outer_tracks')
        if sum(t.GetLength() for t in replacement.values()) > min(50000000, source_length+16000000):
            raise ValueError('consumer_reanchor_finite_route_extension_exceeded')
        if set(map(force._uid, child_group.GetItems())) != old_members | incoming:
            raise ValueError('consumer_reanchor_group_extension_not_exact_new_tracks')
        received = consumer.inventory(child, board_hint=board_hint, timeout_s=timeout_s)
        final = [p for p in received['proofs'] if p['root_pad_uuid'] == root_pad_uuid]
        if (not received['complete'] or len(final) != 1 or final[0]['budget'] != budget
                or final[0]['anchor_uuid'] != proposed[1]
                or set(final[0]['exact_branch_material_uuids']) !=
                    old_members | incoming | set(filter(None, old_name[2].split(',')))):
            raise ValueError('consumer_reanchor_saved_one_tap_load_receiving_refused')
        original_tracks = {force._uid(t): t for t in child.GetTracks()}
        widenings = []
        source_owned = set(source_proof['track_requirements']) | set(
            source_proof['retained_island_track_requirements'])
        for uid, item in material.items():
            _check(deadline)
            if item.GetClass() != 'PCB_TRACK':
                continue
            target = original_tracks[uid]
            if item.GetWidth() == target.GetWidth():
                continue
            floor = math.ceil(budget['required_by_layer_mm'][fab.COPPER_LAYER_IDS[item.GetLayer()]]*1e6)
            if (uid not in island or item.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
                    or item.GetParentGroup() is not None and uid not in source_owned
                    or target.GetWidth() != floor or floor <= item.GetWidth()
                    or floor-item.GetWidth() > (10000 if uid in source_owned else 300000)
                    or item.GetLength() > 32000000):
                raise ValueError('consumer_reanchor_widening_not_exclusive_exact_current_floor')
            widenings.append(dict(uuid=uid, source_width_nm=item.GetWidth(), replacement_width_nm=floor))
            item.SetWidth(floor)
        if len(widenings) > 16:
            raise ValueError('consumer_reanchor_exclusive_widening_work_bound')
        _, old_fixed = force._preservation_snapshot(source)
        _, new_fixed = force._preservation_snapshot(candidate)
        if old_fixed != new_fixed or force._sidecars(source) != force._sidecars(candidate):
            raise ValueError('consumer_reanchor_settings_or_sidecar_changed')
        with tempfile.TemporaryDirectory(prefix='cec-consumer-reanchor-replay-') as work:
            expected = force._copy_family(source, Path(work)/'family')
            field._save_field_snapshot(parent, expected)
            projected_root, projected_nodes = additive._nodes(expected)
            allowed = {r['uuid'] for r in widenings}
            projection_delta = projected_nodes.keys() ^ (old_nodes.keys()-retired)
            projection_delta |= {u for u in projected_nodes.keys() & old_nodes.keys()
                if u not in allowed and sexpr._freeze(projected_nodes[u]) != sexpr._freeze(old_nodes[u])}
            if projection_delta:
                result['source_projection_mismatch_uuids'] = sorted(projection_delta)[:16]
                raise ValueError('consumer_reanchor_projection_changed_unrelated_source_material')
            # Derive group identity/membership from the valid source group;
            # never copy a candidate group, footprint, setting, rule or pour.
            expected_group = []
            for index, row in enumerate(projected_nodes[gid]):
                if index == 1:
                    expected_group.append('"'+consumer.PREFIX+'|'.join(proposed)+'"')
                elif isinstance(row, list) and row and row[0] == 'members':
                    expected_group.append(['members', *['"'+u+'"' for u in sorted(old_members|incoming)]])
                else:
                    expected_group.append(row)
            source_group_node = projected_nodes[gid]
            rewritten = [expected_group if row is source_group_node else row for row in projected_root[1:]]
            root_node = [projected_root[0], *rewritten, *[new_nodes[u] for u in sorted(incoming)]]
            expected.write_text(additive._render(root_node)+'\n')
            replayed = pcbnew.LoadBoard(str(expected))
            result['independently_replayed_ground_uuids'] = additive._ground_refill(replayed)
            field._save_field_snapshot(replayed, expected)
            _, expected_nodes = additive._nodes(expected)
            differences = expected_nodes.keys() ^ new_nodes.keys()
            differences |= {u for u in expected_nodes.keys() & new_nodes.keys()
                if sexpr._freeze(expected_nodes[u]) != sexpr._freeze(new_nodes[u])}
            if differences:
                result['native_replay_mismatch_uuids'] = sorted(differences)[:16]
                raise ValueError('consumer_reanchor_saved_child_differs_from_exact_native_replay')
        first = ordinary._partition(pcbnew.LoadBoard(str(source)), deadline, retired_uuids=retired)
        last = ordinary._partition(child, deadline, retained_keys=set().union(*first))
        if any(not any(p <= q for q in last) for p in first):
            raise ValueError('consumer_reanchor_lost_surviving_native_partition')
        _check(deadline)
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity()):
            raise ValueError('consumer_reanchor_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            retired_track_uuids=sorted(retired), incoming_track_uuids=sorted(incoming),
            exclusive_exact_floor_widenings=widenings, derived_unchanged_design_budget=budget,
            original_consumer_group_uuid=gid, source_anchor_uuid=old_name[1], anchor_uuid=proposed[1],
            all_surviving_native_partitions_preserved=True, new_barrels=0,
            existing_barrels_parts_pours_interfaces_and_rules_exact=True,
            independently_replayed_ground_fill_exact=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
