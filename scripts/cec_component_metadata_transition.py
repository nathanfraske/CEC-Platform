"""Typed fitted-component model ECO after a freshly replayed print scope.

The original board's missing model remains explicit debt.  It is not given
a new schematic-parity grade.  Only the independently proved metadata-only
descendant may use this bridge; all final intake, native, current, physical
contact, return and field checks remain mandatory on the actual descendant.
"""
import json
import math
from pathlib import Path
import re
import time

import cec_component_internal_connections as component
import cec_force_current as force

KIND = 'component_internal_transition'
DECLARATION_FIELDS = {'source', 'proposal', 'source_row'}
SOURCE_KINDS = ('print_context_transition', 'replayed_print_context_transition', 'annotation_transition')


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _bound(record):
    _need(type(record) is dict and set(record) == {'path', 'sha256'}
          and type(record['path']) is str and record['path']
          and type(record['sha256']) is str and re.fullmatch('[0-9a-f]{64}', record['sha256']),
          'exact_component_transition_file_binding_required')
    raw = Path(record['path'])
    _need(not raw.is_symlink(), 'component_transition_file_alias_refused')
    path = raw.resolve(strict=True)
    _need(path.is_file() and force._hash(path) == record['sha256'],
          'component_transition_bound_file_changed')
    return path


def validate(candidate, declaration, board_hint):
    import cec_suite_annotation_transition as annotations
    _need(type(declaration) is dict and set(declaration) == DECLARATION_FIELDS,
          'exact_component_metadata_transition_declaration_required')
    source = _bound(declaration['source'])
    proposal = _bound(declaration['proposal'])
    candidate = Path(candidate).resolve(strict=True)
    _need(len({source, proposal, candidate}) == 3
          and not source.samefile(candidate), 'distinct_component_metadata_boundaries_required')
    row = declaration['source_row']
    _need(type(row) is dict and row.get('board') == board_hint
          and row.get('sha256') == force._hash(source)
          and Path(row.get('path', '')).resolve(strict=True) == source
          and annotations.kind(row) in SOURCE_KINDS
          and KIND not in row, 'exact_nonrecursive_original_source_recipe_required')
    return source, proposal, candidate


def receive(candidate, declaration, *, board_hint, assembly_instance=None, timeout_s=10.):
    """Compose two fresh bounded scopes, then derive the actual child identity."""
    import cec_suite_annotation_transition as annotations
    import cec_received_private_stage as stage
    import cec_native_library_context as libraries
    import cec_synth_pipeline as synth
    component._deadline(timeout_s)
    source, proposal_path, candidate = validate(candidate, declaration, board_hint)
    inputs = {str(p): force._hash(p) for p in (source, proposal_path, candidate)}
    code = force._code_identity()
    families = [force._family(p, board_hint) for p in (source, candidate)]
    started = time.monotonic()
    # A prior receipt is never accepted. Replay the entire actual original
    # annotation recipe again under the current code and Source epoch.
    original = annotations.receive_row(source, declaration['source_row'],
                                       board_hint=board_hint, timeout_s=timeout_s)
    _need(original is not None and original.get('ok') is True and original.get('complete') is True,
          'fresh_original_annotation_scope_required')
    proposal = json.loads(proposal_path.read_text())
    metadata_started = time.monotonic()
    model = component.receive(source, candidate, proposal, timeout_s=timeout_s)
    _need(model.get('ok') is True and model.get('complete') is True
          and model.get('scope_only') is True and bool(model.get('scope', {}).get('changed_refs')),
          'fresh_nonempty_component_model_scope_required')
    metadata_elapsed = time.monotonic() - metadata_started
    identity_started = time.monotonic()
    cfg = synth.Config.load(board_hint)
    canonical = Path(cfg.dir) / 'fp-lib-table'
    canonical_source = stage.stable(libraries.authority(source, canonical))
    canonical_child = stage.stable(libraries.authority(candidate, canonical))
    _need(canonical_source == canonical_child,
          'component_metadata_changed_canonical_footprint_references')
    arguments = original['candidate_native_arguments']
    _need(type(arguments) is dict and set(arguments) == {'board_hint', 'footprint_table'}
          and arguments['board_hint'] is None and type(arguments['footprint_table']) is str,
          'fresh_explicit_original_native_print_context_required')
    table = Path(arguments['footprint_table']).resolve(strict=True)
    old_context = stage.stable(libraries.authority(source, table))
    new_context = stage.stable(libraries.authority(candidate, table))
    _need(old_context == original['candidate_identity']['native_library_authority']
          and new_context == old_context,
          'component_metadata_changed_received_print_library_material')
    instance = stage.matched_instance(assembly_instance, candidate)
    raw_identity = stage.identity(candidate, board_hint, instance)
    _need(raw_identity['native_library_authority'] == canonical_child,
          'component_metadata_default_identity_context_conflict')
    # This is a newly computed child identity. Only the freshly received
    # unchanged print-library authority may replace its canonical default.
    child_identity = dict(raw_identity, native_library_authority=new_context)
    _need(code == force._code_identity()
          and families == [force._family(p, board_hint) for p in (source, candidate)]
          and all(force._hash(p) == h for p, h in inputs.items())
          and new_context == stage.stable(libraries.authority(candidate, table)),
          'component_transition_source_code_family_or_context_changed')
    identity_elapsed = time.monotonic() - identity_started
    _need(metadata_elapsed < timeout_s and identity_elapsed < timeout_s,
          'component_metadata_or_identity_constituent_deadline')
    return dict(ok=True, complete=True, scope_only=True,
        source_annotation=original, component_model_scope=model,
        source_identity=original['candidate_identity'],
        candidate_identity=child_identity, candidate_native_arguments=dict(arguments),
        source_native_arguments=dict(arguments), old_library_context=old_context,
        new_library_context=new_context,
        original_source_missing_model_is_debt_not_a_new_parity_pass=True,
        all_final_native_intake_parity_current_ground_field_and_contact_gates_still_required=True,
        physical_copper_current_and_release_qualification_inferred=False,
        bounded_composition=dict(kind='fresh_original_recipe_then_component_scope_then_identity',
                                 per_constituent_limit_s=timeout_s),
        timings_s=dict(source_recipe=metadata_started-started,
                       component_scope=metadata_elapsed, identity_live=identity_elapsed),
        admitted=False, release_authority=False)


def same_replay(left, right):
    import cec_suite_annotation_transition as annotations
    for value in (left, right):
        if value.get('ok') is not True or value.get('complete') is not True:
            return False
        bounds = value.get('bounded_composition', {})
        limit = bounds.get('per_constituent_limit_s')
        try:
            component._deadline(limit)
        except (ValueError, TypeError):
            return False
        if bounds != dict(kind='fresh_original_recipe_then_component_scope_then_identity',
                          per_constituent_limit_s=limit):
            return False
        timing = value.get('timings_s', {})
        if set(timing) != {'source_recipe', 'component_scope', 'identity_live'}:
            return False
        if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0
               for t in timing.values()):
            return False
        if any(type(timing[k]) not in (int, float) or not 0 <= timing[k] < limit
               for k in ('component_scope', 'identity_live')):
            return False
    if not annotations.same_replay(left['source_annotation'], right['source_annotation']):
        return False
    return ({k: v for k, v in left.items() if k not in ('source_annotation', 'timings_s')}
            == {k: v for k, v in right.items() if k not in ('source_annotation', 'timings_s')})
