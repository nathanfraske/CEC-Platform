"""Compose Source-owned ordinary preclears with one to three quiet inputs.

Build-only orchestration, not a new routing role or physical receiver. Each
saved preclear is independently received. The public finite Source-cut chain
also replays their combined delta. Strict contact/current preservation applies
BEFORE the quiet repair boundary; only the existing saved quiet-input receiver
may derive a repaired leg on its own suffix. No worker verdict or caller
repair-net, current, geometry, callback, timeout or exclusion is accepted.
"""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import re
import sys
import time

import cec_force_current as force
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_source_cut_chain as cut_chain
import cec_source_functional_ground_cohort as functional_ground
import root_receive_local_transaction_20261022 as base
import root_ordinary_barrel_chain_phase_20261027 as barrel

PREFIX_KINDS = {'ordinary_reflow', 'ordinary_source_reflow', barrel.KIND}
GROUND_KIND = 'source_functional_ground_cohort'
GROUND_FIELDS = {'kind', 'candidate', 'candidate_sha256', 'owner_pad_uuid', 'via_uuid'}
MEASUREMENT_KIND = 'measurement_quiet_fanout'
PRINT_KIND = 'print_context'
LEASE_S = 10.
MAX_MEASUREMENT_PHASES = 3


def _sequence(phases):
    kinds = base.validate_phases(phases)
    first_quiet = next((i for i, kind in enumerate(kinds) if kind == MEASUREMENT_KIND), len(kinds))
    before = phases[:first_quiet]
    ground = before[-1] if before and before[-1]['kind'] == GROUND_KIND else None
    ordinary = before[:-1] if ground is not None else before
    quiet = phases[first_quiet:-1]
    if (kinds[-1] != PRINT_KIND or not 1 <= len(quiet) <= MAX_MEASUREMENT_PHASES
            or any(row['kind'] != MEASUREMENT_KIND for row in quiet)
            or kinds.count(GROUND_KIND) != int(ground is not None)
            or not (2 <= len(ordinary) <= 3 if ground is not None else 1 <= len(ordinary) <= 2)
            or any(row['kind'] not in PREFIX_KINDS for row in ordinary)):
        raise ValueError('exact_Source_ordinary_prefix_optional_Ground_then_quiet_and_print_required')
    for row in phases:
        if (type(row['candidate']) is not str or not row['candidate']
                or any(ord(c) < 32 for c in row['candidate'])
                or type(row['candidate_sha256']) is not str
                or re.fullmatch('[0-9a-f]{64}', row['candidate_sha256']) is None):
            raise ValueError('exact_saved_preclear_measurement_boundary_required')
    # The unchanged base validator owns both the six-phase cap and distinct
    # actual input IDs. The saved suffix receiver separately rederives and
    # rejects duplicate manufacturer/net/leg identities, never caller roles.
    return ordinary, ground, phases[first_quiet:]


def _ground_row(row):
    if type(row) is not dict or set(row) != GROUND_FIELDS or row['kind'] != GROUND_KIND:
        raise ValueError('exact_Source_functional_Ground_identity_schema_required')
    for name in ('owner_pad_uuid', 'via_uuid'):
        value = row[name]
        if type(value) is not str or barrel.UUID.fullmatch(value) is None:
            raise ValueError('exact_Source_functional_Ground_' + name + '_required')
    if row['owner_pad_uuid'] == row['via_uuid']:
        raise ValueError('distinct_Source_functional_Ground_pad_and_barrel_required')
    if (type(row['candidate']) is not str or not row['candidate']
            or any(ord(c) < 32 for c in row['candidate'])
            or type(row['candidate_sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', row['candidate_sha256']) is None):
        raise ValueError('exact_saved_functional_Ground_boundary_required')
    return row


def _raw_bound(report, path, hint, epoch):
    family = force._family(path, hint)
    if (type(report) is not dict or report.get('complete') is not True
            or report.get('identity_stable') is not True or report.get('board_hint') != hint
            or report.get('source') != str(path)
            or report.get('source_family_before') != family
            or report.get('source_family_after') != family
            or report.get('code_before') != epoch or report.get('code_after') != epoch):
        raise ValueError('fresh_exact_saved_raw_sense_boundary_required')


def _cut_phase(row):
    common = dict(candidate=row['candidate'], retired_track_uuids=list(row['retired_track_uuids']))
    if row['kind'] in ('ordinary_reflow', 'ordinary_source_reflow'):
        return dict(kind='ordinary', allow_locked_track_uuids=list(row.get('allow_locked_track_uuids', [])), **common)
    if row['kind'] == barrel.KIND:
        # The unchanged barrel dispatcher independently requires these exact
        # Source objects to be unlocked, ungrouped and exclusively owned.
        return dict(kind='ordinary_exclusive_via_path', allow_locked_track_uuids=[],
            retired_via_uuids=list(row['retired_via_uuids']), allow_locked_via_uuids=[], **common)
    raise ValueError('unsupported_Source_preclear_cut_kind')


def _compose(source, candidate, phases, evidence, *, board_hint, assembly_instance, suffix_receiver):
    prefix, ground_phase, suffix = _sequence(phases)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    paths = [source, *[Path(row['candidate']).resolve(strict=True) for row in phases]]
    if (paths[-1] != candidate or len(set(paths)) != len(paths)
            or any(a.samefile(b) for i, a in enumerate(paths) for b in paths[i+1:])):
        raise ValueError('distinct_exact_Source_preclear_measurement_paths_required')
    for path, row in zip(paths[1:], phases):
        if force._hash(path) != row['candidate_sha256']:
            raise ValueError('saved_preclear_measurement_hash_changed')
    epoch = force._code_identity()
    families = [force._family(p, board_hint) for p in paths]
    dependencies = base.annotation_dependencies()
    if type(evidence) not in (list, tuple) or len(evidence) != 2:
        raise ValueError('two_actual_raw_transaction_endpoints_required')
    for path, raw in zip((source, candidate), evidence):
        _raw_bound(raw, path, board_hint, epoch)
    original_raw = copy.deepcopy(evidence)
    started = time.monotonic()
    # A finite composition of unchanged physical leases. The cut-chain owner
    # itself caps n receiving phases plus one whole-Source replay. The suffix
    # retains its existing quiet/print constituent structure, not one raised
    # native deadline. Identity/comparison work has a separate finite budget.
    # Actual quiet receivers plus print, with the same two finite allowances
    # for suffix material/comparison/identity work as the former single-input
    # path. One input therefore keeps its original four-lease total. These
    # are composition budgets, never an extension of a physical phase lease.
    measurement_count = len(suffix)-1
    suffix_limit = LEASE_S * (len(suffix)+2)
    aggregate_limit = LEASE_S * (2 * len(prefix) + 4 + (4 if ground_phase is not None else 0)) + suffix_limit
    result = dict(same_evidence=False, comparison_complete=False, errors=[],
        scope='Source_ordinary_preclear_then_independent_quiet_input_suffix',
        full_kelvin_qualification=False, current_qualified=False, release_authority=False,
        inherited_debt_qualified=False, raw_parent_and_candidate_evidence_not_rewritten=True,
        independent_constituent_limit_s=LEASE_S, aggregate_limit_s=aggregate_limit,
        actual_measurement_suffix_count=measurement_count,
        independent_suffix_limit_s=suffix_limit,
        timings_s={}, independently_received_prefix_phases=[])

    def call(name, fn, limit=LEASE_S):
        t = time.monotonic(); value = fn(); elapsed = time.monotonic() - t
        result['timings_s'][name] = elapsed
        if elapsed > limit or time.monotonic()-started > aggregate_limit:
            raise ValueError('bounded_preclear_measurement_constituent_deadline:' + name)
        return value

    try:
        cursor = source
        for index, row in enumerate(prefix):
            prior = cursor
            actual, proof = call('typed_prefix_' + str(index), lambda:base.receive_phase(
                source, prior, row, board_hint,
                assembly_instance=base.stage.matched_instance(assembly_instance, prior)))
            actual = Path(actual).resolve(strict=True)
            result['independently_received_prefix_phases'].append(dict(kind=row['kind'],
                source=str(prior), candidate=str(actual), receiving=proof))
            if (proof.get('ok') is not True or proof.get('complete') is not True
                    or actual != Path(row['candidate']).resolve(strict=True)
                    or force._hash(actual) != row['candidate_sha256']):
                raise ValueError('actual_Source_preclear_saved_receiver_refused')
            cursor = actual
        result['actual_measurement_parent'] = str(cursor)
        cuts = [_cut_phase(row) for row in prefix]
        chain = call('whole_Source_cut_chain', lambda:cut_chain.receive(source, cursor,
            board_hint=board_hint, phases=cuts, timeout_s=LEASE_S, per_phase_leases=True),
            LEASE_S * (len(cuts)+1))
        result['whole_Source_cut_chain'] = chain
        if chain.get('ok') is not True or chain.get('complete') is not True:
            raise ValueError('independent_whole_Source_preclear_cut_chain_refused')
        debt = call('prefix_current', lambda:current.receive(source, cursor, board_hint=board_hint))
        result['prefix_current'] = debt
        if (debt.get('ok') is not True or debt.get('complete') is not True
                or debt.get('source_candidate_and_code_unchanged') is not True):
            raise ValueError('independent_Source_preclear_current_preservation_refused')
        raw = call('prefix_raw_sense', lambda:sense.replay(cursor, board_hint=board_hint, timeout_s=LEASE_S))
        result['raw_measurement_parent_evidence'] = raw
        _raw_bound(raw, cursor, board_hint, epoch)
        old, intermediate = [base.pcbnew.LoadBoard(str(p)) for p in (source, cursor)]
        nets = base.changed_native_nets(old, intermediate)
        transforms = base.contact_manifest(old, intermediate, nets)
        strict = call('strict_Source_to_preclear', lambda:base.strict_contact_transition(
            evidence[0], raw, nets, transforms))
        result.update(source_evidence_match=strict, strict_prefix_actual_modified_nets=nets,
            strict_prefix_native_copper_transforms=transforms,
            measurement_repair_authority_not_applied_to_prefix=True)
        if strict.get('same_evidence') is not True or strict.get('comparison_complete') is not True:
            raise ValueError('strict_Source_to_preclear_contact_preservation_refused')
        if ground_phase is not None:
            prior = cursor
            actual, proof = call('typed_functional_Ground', lambda:base.receive_phase(
                source, prior, ground_phase, board_hint,
                assembly_instance=base.stage.matched_instance(assembly_instance, prior)))
            actual = Path(actual).resolve(strict=True)
            result['independently_received_prefix_phases'].append(dict(kind=GROUND_KIND,
                source=str(prior), candidate=str(actual), receiving=proof))
            if (proof.get('ok') is not True or proof.get('complete') is not True
                    or actual != Path(ground_phase['candidate']).resolve(strict=True)
                    or force._hash(actual) != ground_phase['candidate_sha256']):
                raise ValueError('actual_Source_functional_Ground_saved_receiver_refused')
            ground_debt = call('functional_Ground_current', lambda:current.receive(prior, actual, board_hint=board_hint))
            result['functional_Ground_current'] = ground_debt
            if (ground_debt.get('ok') is not True or ground_debt.get('complete') is not True
                    or ground_debt.get('source_candidate_and_code_unchanged') is not True):
                raise ValueError('functional_Ground_current_preservation_refused')
            ground_raw = call('functional_Ground_raw_sense', lambda:sense.replay(actual,
                board_hint=board_hint, timeout_s=LEASE_S))
            result['raw_functional_Ground_evidence'] = ground_raw
            _raw_bound(ground_raw, actual, board_hint, epoch)
            left, right = [base.pcbnew.LoadBoard(str(p)) for p in (prior, actual)]
            ground_nets = base.changed_native_nets(left, right)
            ground_manifest = base.contact_manifest(left, right, ground_nets)
            relation = call('strict_functional_Ground_contact', lambda:base.strict_contact_transition(
                raw, ground_raw, ground_nets, ground_manifest))
            result.update(strict_functional_Ground_contact=relation,
                functional_Ground_actual_modified_nets=ground_nets,
                functional_Ground_native_copper_transforms=ground_manifest)
            if relation.get('same_evidence') is not True or relation.get('comparison_complete') is not True:
                raise ValueError('strict_functional_Ground_contact_preservation_refused')
            cursor, raw = actual, ground_raw
            result['actual_measurement_parent'] = str(cursor)
        # Only the actual suffix is passed to the unchanged existing input
        # receiver. It freshly derives the pad/manufacturer/net/leg and applies
        # absolute AFTER native copper proof; no prefix cut ID becomes a waiver.
        original_phase_receiver = base.receive_phase
        suffix_receives = []

        def timed_suffix_phase(original, parent, row, hint, *, assembly_instance=None):
            index = len(suffix_receives)
            if index >= len(suffix) or row != suffix[index]:
                raise ValueError('exact_actual_quiet_suffix_dispatch_order_required')
            value = call('typed_suffix_' + str(index) + '_' + row['kind'],
                lambda:original_phase_receiver(original, parent, row, hint,
                    assembly_instance=assembly_instance))
            suffix_receives.append(row['kind'])
            return value

        try:
            base.receive_phase = timed_suffix_phase
            remainder = call('independent_measurement_suffix', lambda:suffix_receiver(
                cursor, candidate, suffix, [raw, evidence[1]], board_hint=board_hint,
                assembly_instance=base.stage.matched_instance(assembly_instance, cursor)),
                suffix_limit)
        finally:
            base.receive_phase = original_phase_receiver
        if suffix_receives != [row['kind'] for row in suffix]:
            raise ValueError('complete_actual_quiet_suffix_saved_receiving_required')
        result['independently_received_measurement_suffix'] = remainder
        if (type(remainder) is not dict or remainder.get('same_evidence') is not True
                or remainder.get('comparison_complete') is not True):
            raise ValueError('independent_quiet_input_absolute_after_refused')
        result.update(same_evidence=True, comparison_complete=True)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    if (evidence != original_raw or epoch != force._code_identity()
            or families != [force._family(p, board_hint) for p in paths]
            or dependencies != base.annotation_dependencies()):
        result.update(same_evidence=False, comparison_complete=False)
        result['errors'].append('preclear_measurement_raw_Source_family_or_dependency_changed')
    result['elapsed_s'] = time.monotonic()-started
    if result['elapsed_s'] > aggregate_limit:
        result.update(same_evidence=False, comparison_complete=False)
        result['errors'].append('bounded_preclear_measurement_composition_deadline')
    return result


@contextmanager
def installed():
    with barrel.installed():
        previous = (base.isolated_measurement_contact_transition, base.annotation_dependencies,
            base.validate_phases, base.receive_phase)
        original_contact, original_dependencies, original_validate, original_receive = previous

        def validate(phases):
            old = base.KINDS
            try:
                base.KINDS = {**old, GROUND_KIND:GROUND_FIELDS-{'kind', 'candidate', 'candidate_sha256'}}
                kinds = original_validate(phases)
            finally:
                base.KINDS = old
            for row in phases:
                if row['kind'] == GROUND_KIND:
                    _ground_row(row)
            return kinds

        def receive(original, parent, row, hint, *, assembly_instance=None):
            if row.get('kind') != GROUND_KIND:
                return original_receive(original, parent, row, hint, assembly_instance=assembly_instance)
            _ground_row(row)
            parent, child = [Path(p).resolve(strict=True) for p in (parent, row['candidate'])]
            if parent.samefile(child) or force._hash(child) != row['candidate_sha256']:
                raise ValueError('distinct_exact_saved_functional_Ground_boundary_required')
            proof = functional_ground.receive(parent, child, owner_pad_uuid=row['owner_pad_uuid'],
                via_uuid=row['via_uuid'], board_hint=hint, timeout_s=LEASE_S)
            if (proof.get('ok') is not True or proof.get('complete') is not True
                    or force._hash(child) != row['candidate_sha256']):
                raise ValueError('public_Source_functional_Ground_saved_receiver_refused:' + str(proof))
            return child, proof

        def contact(source, candidate, phases, evidence, *, board_hint, assembly_instance=None):
            kinds = base.validate_phases(phases)
            if MEASUREMENT_KIND not in kinds or not (PREFIX_KINDS | {GROUND_KIND}).intersection(kinds):
                return original_contact(source, candidate, phases, evidence,
                    board_hint=board_hint, assembly_instance=assembly_instance)
            return _compose(source, candidate, phases, evidence, board_hint=board_hint,
                assembly_instance=assembly_instance, suffix_receiver=original_contact)

        def dependencies():
            return {**original_dependencies(), **{str(Path(m.__file__).resolve()):force._hash(m.__file__)
                for m in (cut_chain, current, sense, functional_ground)}, str(Path(__file__).resolve()):force._hash(__file__)}

        base.isolated_measurement_contact_transition, base.annotation_dependencies = contact, dependencies
        base.validate_phases, base.receive_phase = validate, receive
        try:
            yield
        finally:
            (base.isolated_measurement_contact_transition, base.annotation_dependencies,
                base.validate_phases, base.receive_phase) = previous


def main():
    args = sys.argv[1:]
    if args.count('--out') != 1:
        raise ValueError('one_saved_preclear_measurement_transaction_output_required')
    out = Path(args[args.index('--out')+1])
    with installed():
        dependencies = base.annotation_dependencies()
        status = base.main()
        if dependencies != base.annotation_dependencies():
            raise ValueError('preclear_measurement_dispatch_dependencies_changed')
    path = out/'receiving.json'; result = json.loads(path.read_text())
    result['inputs'].update(dependencies)
    result['registered_ordinary_preclear_measurement_receiver'] = dict(
        prefix_kinds=sorted(PREFIX_KINDS), measurement_kind=MEASUREMENT_KIND,
        maximum_measurement_suffix_phases=MAX_MEASUREMENT_PHASES,
        unchanged_total_phase_cap=base.MAX_LOCAL_PHASES,
        distinct_Source_inputs_and_fresh_actual_repair_legs_required=True,
        suffix_budget_derived_from_actual_phase_count=True,
        exact_actual_saved_boundaries=True, maximum_ordinary_prefix_phases=3,
        optional_functional_Ground_kind=GROUND_KIND,
        functional_Ground_receiver='cec_source_functional_ground_cohort.receive',
        exact_functional_Ground_pad_and_barrel_identities_only=True,
        unchanged_public_Source_cut_chain='cec_source_cut_chain.receive',
        unchanged_suffix_receiver='isolated_measurement_contact_transition',
        strict_prefix_current_and_native_contact_preservation=True,
        all_original_parent_gates_retained=True, constituent_limit_s=LEASE_S,
        caller_role_or_current_or_repair_leg_overrides=False, release_authority=False)
    force._write(path, result)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
