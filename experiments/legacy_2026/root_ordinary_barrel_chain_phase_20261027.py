"""Exact-ID ordinary barrel/track reflow under every original parent gate.

This build-only dispatcher calls the existing public ordinary receiver.
It adds no constructor, role, dimension, grouped-copper permission, current
exception, physical deadline or cached-verdict mechanism. The legacy kind
requires unlocked copper. A distinct Source-owned kind derives only the
actual requested Source lock inventory and delegates it to the existing
public exact-lock receiver; it cannot unlock or retire anything else.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import re
import sys
import time
import pcbnew
import cec_force_current as force
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import root_receive_local_transaction_20261022 as base

KIND = 'ordinary_source_barrel_chain_reflow'
SOURCE_OWNED_KIND = 'source_owned_ordinary_barrel_chain_reflow'
KINDS = {KIND, SOURCE_OWNED_KIND}
FIELDS = {'kind', 'candidate', 'candidate_sha256', 'net',
          'retired_track_uuids', 'retired_via_uuids'}
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def validate_row(row):
    if type(row) is not dict or set(row) != FIELDS or row['kind'] not in KINDS:
        raise ValueError('exact_ordinary_barrel_chain_phase_schema_required')
    net = row['net']
    if (type(net) is not str or not 0 < len(net) <= 256
            or any(ord(c) < 32 for c in net)):
        raise ValueError('literal_ordinary_barrel_chain_net_required')
    for key, minimum, maximum in (('retired_track_uuids', 1, 32), ('retired_via_uuids', 1, 1)):
        value = row[key]
        if (type(value) is not list or not minimum <= len(value) <= maximum
                or any(type(u) is not str or UUID.fullmatch(u) is None for u in value)
                or len(set(value)) != len(value)):
            raise ValueError('bounded_exact_' + key + '_required')
    if set(row['retired_track_uuids']) & set(row['retired_via_uuids']):
        raise ValueError('disjoint_ordinary_track_and_barrel_identities_required')
    if (type(row['candidate']) is not str or not row['candidate']
            or any(ord(c) < 32 for c in row['candidate'])
            or type(row['candidate_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', row['candidate_sha256']) is None):
        raise ValueError('literal_saved_ordinary_barrel_chain_identity_required')
    return row


def _native_scope(parent, child, row, hint, deadline):
    """Restrict this adapter to one old ordinary net and one replacement via.

    No physical positive result is produced here. The public receiver still
    rederives exclusivity, every boundary and partition, exact literal delta,
    process/group rules, and generated-GND-only refill preservation.
    """
    before, after = [pcbnew.LoadBoard(str(p)) for p in (parent, child)]
    net = row['net']
    if net not in ordinary.eligible_nets(before, parent, hint):
        raise ValueError('source_barrel_chain_net_not_positively_ordinary')
    old_list = list(before.GetTracks()); new_list = list(after.GetTracks())
    old = {force._uid(t): t for t in old_list}; new = {force._uid(t): t for t in new_list}
    if len(old) != len(old_list) or len(new) != len(new_list):
        raise ValueError('unique_native_barrel_chain_inventory_required')
    tracks = set(row['retired_track_uuids']); vias = set(row['retired_via_uuids'])
    outgoing = tracks | vias
    if old.keys()-new.keys() != outgoing:
        raise ValueError('actual_source_retirement_differs_from_both_ID_sets')
    grouped = {force._uid(i) for g in before.Groups() for i in g.GetItems()}
    for uid in outgoing:
        item = old[uid]
        expected = 'PCB_TRACK' if uid in tracks else 'PCB_VIA'
        if (item.GetClass() != expected or item.GetNetname() != net
                or item.IsLocked() and row['kind'] != SOURCE_OWNED_KIND
                or uid in grouped or item.GetParentGroup() is not None
                or expected == 'PCB_TRACK' and item.HasSolderMask()):
            raise ValueError('only_exact_unlocked_ungrouped_same_net_Source_copper')
    incoming = [new[u] for u in new.keys()-old.keys()]
    if (not 1 <= len(incoming) <= 64
            or sum(t.GetClass() == 'PCB_VIA' for t in incoming) != 1
            or any(t.GetClass() not in ('PCB_TRACK', 'PCB_VIA') or t.GetNetname() != net
                   for t in incoming)):
        raise ValueError('one_same_net_barrel_and_bounded_ordinary_replacement_required')
    if any(t.GetClass() == 'PCB_VIA' and (t.GetViaType() != pcbnew.VIATYPE_THROUGH
            or {int(t.TopLayer()), int(t.BottomLayer())} != {pcbnew.F_Cu, pcbnew.B_Cu})
            for t in incoming):
        raise ValueError('one_actual_full_span_ordinary_replacement_barrel_required')
    if time.monotonic() >= deadline:
        raise ValueError('ordinary_barrel_chain_dispatch_deadline')
    return dict(allow_locked_track_uuids=sorted(u for u in tracks if old[u].IsLocked()),
        allow_locked_via_uuids=sorted(u for u in vias if old[u].IsLocked()),
        exact_requested_Source_lock_inventory_derived=True,
        grouped_copper_permission=False, unrelated_locked_copper_permission=False)


def receive_phase(original, parent, row, hint, *, assembly_instance=None):
    validate_row(row)
    if type(hint) is not str or not hint:
        raise ValueError('explicit_ordinary_barrel_chain_board_required')
    Path(original).resolve(strict=True)
    parent = Path(parent).resolve(strict=True)
    child = Path(row['candidate']).resolve(strict=True)
    if parent == child or parent.samefile(child) or force._hash(child) != row['candidate_sha256']:
        raise ValueError('distinct_exact_saved_ordinary_barrel_chain_boundary_required')
    source_sha = force._hash(parent)
    deadline = time.monotonic()+10.
    source_locks = _native_scope(parent, child, row, hint, deadline)
    options = ({key:source_locks[key] for key in ('allow_locked_track_uuids','allow_locked_via_uuids')}
        if row['kind'] == SOURCE_OWNED_KIND else {})
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise ValueError('ordinary_barrel_chain_dispatch_deadline')
    proof = ordinary.receive(parent, child, board_hint=hint,
        retired_track_uuids=row['retired_track_uuids'], retired_via_uuids=row['retired_via_uuids'],
        max_retired_tracks=32, timeout_s=remaining, **options)
    if (force._hash(parent) != source_sha or force._hash(child) != row['candidate_sha256']
            or time.monotonic() >= deadline):
        raise ValueError('ordinary_barrel_chain_saved_boundary_or_dispatch_deadline_changed')
    if row['kind'] == SOURCE_OWNED_KIND:
        proof['dispatch_Source_lock_inventory'] = source_locks
    return proof


@contextmanager
def installed():
    previous = base.validate_phases, base.receive_phase, base.annotation_dependencies
    original_validate, original_receive, original_dependencies = previous

    def validate(phases):
        old = base.KINDS
        try:
            base.KINDS = {**old, **{kind:FIELDS-{'kind', 'candidate', 'candidate_sha256'}for kind in KINDS}}
            result = original_validate(phases)
        finally:
            base.KINDS = old
        nets = set()
        net_kinds = {'ordinary_join', 'ordinary_columns', 'can_endpoint_join', 'ordinary_reflow',
                     'ordinary_source_reflow', 'ordinary_source_connected_reflow',
                     'distributed_supply_join', *KINDS}
        for row in phases:
            if row['kind'] in KINDS:
                validate_row(row)
            if row['kind'] in net_kinds:
                if row['net'] in nets:
                    raise ValueError('repeated_local_operator_requires_a_separate_transaction')
                nets.add(row['net'])
        return result

    def receive(original, parent, row, hint, *, assembly_instance=None):
        if row.get('kind') not in KINDS:
            return original_receive(original, parent, row, hint, assembly_instance=assembly_instance)
        validate([row])
        proof = receive_phase(original, parent, row, hint, assembly_instance=assembly_instance)
        if proof.get('ok') is not True or proof.get('complete') is not True:
            raise ValueError('public_ordinary_barrel_chain_saved_receiver_refused:' + str(proof))
        return Path(row['candidate']).resolve(strict=True), proof

    def dependencies():
        return {**original_dependencies(), **{str(Path(m.__file__).resolve()): force._hash(m.__file__)
            for m in (base, ordinary, additive)}, str(Path(__file__).resolve()): force._hash(__file__)}

    base.validate_phases, base.receive_phase, base.annotation_dependencies = validate, receive, dependencies
    try:
        yield
    finally:
        base.validate_phases, base.receive_phase, base.annotation_dependencies = previous


def main():
    args = sys.argv[1:]
    if args.count('--out') != 1:
        raise ValueError('one_explicit_ordinary_barrel_chain_transaction_output_required')
    out = Path(args[args.index('--out')+1])
    with installed():
        dependencies = base.annotation_dependencies()
        status = base.main()
        if dependencies != base.annotation_dependencies():
            raise ValueError('ordinary_barrel_chain_dispatch_dependencies_changed')
    result_path = out/'receiving.json'
    result = json.loads(result_path.read_text())
    result['inputs'].update(dependencies)
    result['registered_saved_receiver'] = dict(kind=KIND, exact_Source_ID_sets_only=True,
        kinds=sorted(KINDS), Source_owned_kind=SOURCE_OWNED_KIND,
        legacy_kind_still_requires_unlocked_Source=True,
        Source_owned_kind_derives_actual_requested_lock_inventory=True,
        maximum_source_tracks=32, maximum_source_vias=1, maximum_incoming_objects=64,
        unchanged_public_receiver='cec_ordinary_route_receiving.receive',
        maximum_local_phases_unchanged=base.MAX_LOCAL_PHASES,
        all_original_parent_gates_retained=True, constituent_limit_s=10.,
        callbacks_or_constructor_verdicts_accepted=False, release_authority=False)
    force._write(result_path, result)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
