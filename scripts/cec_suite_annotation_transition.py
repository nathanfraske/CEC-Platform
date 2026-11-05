"""Exact suite dispatch for independently received annotation provenance.

No newest-file search, caller context, or historical success receipt is an
authority. The selected plan explicitly chooses exactly one typed transition.
"""
from pathlib import Path

KINDS=('print_context_transition','replayed_print_context_transition','annotation_transition',
       'component_internal_transition')


def kind(row):
    found=[key for key in KINDS if key in row]
    if len(found)>1:raise ValueError('ambiguous_suite_annotation_transition')
    return found[0]if found else None


def receive_row(path,row,*,board_hint,timeout_s=10.):
    import cec_received_private_stage as stage
    import cec_print_context_transition as original
    import cec_chained_annotation_transition as chained
    selected=kind(row)
    if selected is None:return None
    declaration=row[selected]
    if selected=='component_internal_transition':
        import cec_component_metadata_transition as component
        proof=component.receive(path,declaration,board_hint=board_hint,
            assembly_instance=row.get('assembly_instance'),timeout_s=timeout_s)
    elif selected=='annotation_transition':
        # Only validation resolves these declared endpoints. No path inferred
        # from directory ordering or worker-selected library context is used.
        endpoints,_=chained.validate(declaration,declaration['steps'][0]['candidate']['path'],path)
        instance=stage.matched_instance(row.get('assembly_instance'),endpoints[1])
        proof=chained.receive(endpoints[1],path,declaration,board_hint=board_hint,
            assembly_instance=instance,timeout_s=timeout_s)
    else:
        instance=stage.matched_instance(row.get('assembly_instance'),Path(declaration['source']['path']))
        receive=original.receive_row if selected=='print_context_transition'else chained.receive_print_row
        proof=receive(path,declaration,board_hint=board_hint,assembly_instance=instance,timeout_s=timeout_s)
    return dict(proof,suite_annotation_transition_kind=selected)


def same_replay(a,b):
    import cec_print_context_transition as original
    import cec_chained_annotation_transition as chained
    selected=a.get('suite_annotation_transition_kind')
    if selected not in KINDS or b.get('suite_annotation_transition_kind')!=selected:return False
    if selected=='component_internal_transition':
        import cec_component_metadata_transition as component
        compare=component.same_replay
    else:compare=original.same_replay if selected=='print_context_transition'else(
        chained.same_print_replay if selected=='replayed_print_context_transition'else chained.same_replay)
    return compare({k:v for k,v in a.items()if k!='suite_annotation_transition_kind'},
        {k:v for k,v in b.items()if k!='suite_annotation_transition_kind'})


def dependencies():
    import cec_force_current as force
    import cec_nonpolar_print_context as print_op
    import cec_optional_body_ink_contract as body
    import cec_reference_field_seating as fields
    import cec_mask_search_reference_mapping as maps
    import cec_component_internal_connections as connections
    import cec_component_metadata_transition as component
    import cec_component_jumper_metadata as jumper
    modules=(print_op,print_op.ink,print_op.ink.frame,body,connections,component,jumper)
    return {**{str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in modules},
        **fields.dependencies(),**maps.dependencies()}
