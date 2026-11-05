"""Receive metadata-only annotation recompilation over byte-exact PCBs.

This is not board selection or a stale-proof waiver. Every changed recipe
is independently replayed now; fresh whole-suite native/intake/parity gates
remain mandatory. Original PCB paths, bytes, counts and other plan data stay
exact, and no historical report receives a new code identity.
"""
import copy,json,math,time
from pathlib import Path
import cec_force_current as force


def _need(value,reason):
    if not value:raise ValueError(reason)


def _compare_step(parent,current,proof):
    """Pure rejection-only schema/material-plan comparison, not admission."""
    key=proof.get('board')
    old={r['board']:r for r in parent['boards']};new={r['board']:r for r in current['boards']}
    _need(len(old)==len(new)==len(parent['boards'])==len(current['boards'])==9
        and old.keys()==new.keys(),'unchanged_epoch_exact_nine_board_inventory_required')
    changed=[name for name in old if old[name]!=new[name]]
    _need(changed==[key],'unchanged_epoch_exact_one_recipe_step_required')
    for name in old:
        left,right=copy.deepcopy(old[name]),copy.deepcopy(new[name])
        if name==key:
            a,b=left.pop('annotation_transition',None),right.pop('annotation_transition',None)
            _need(type(a)is dict and type(b)is dict and b==proof.get('annotation_transition'),
                'unchanged_epoch_explicit_annotation_chain_required')
            ac,bc=copy.deepcopy(a),copy.deepcopy(b)
            _need(len(ac['steps'])==len(bc['steps'])==2,'unchanged_epoch_two_link_recipe_required')
            ac['steps'][1].pop('proposal');bc['steps'][1].pop('proposal')
            _need(ac==bc,'unchanged_epoch_original_annotation_material_endpoints_required')
        _need(left==right,'unchanged_epoch_non_annotation_board_data_changed')
    left,right=copy.deepcopy(parent),copy.deepcopy(current)
    for row in(left,right):
        for name in('boards','parent_plan','fresh_annotation_recipe_receiving','fresh_nine_board_receiving_required'):
            row.pop(name,None)
    _need(left==right,'unchanged_epoch_non_annotation_plan_data_changed')
    _need(proof.get('selected')==new[key]['path']and proof.get('selected_sha256')==new[key]['sha256'],
        'unchanged_epoch_literal_selected_board_required')
    return key


def receive(prior_plan,plan,*,maximum_links=9,timeout_s=10.):
    import cec_swig_guard
    cec_swig_guard.pin()
    import cec_chained_annotation_transition as chain
    import cec_received_private_stage as stage
    _need(type(maximum_links)is int and 1<=maximum_links<=9 and type(timeout_s)in(int,float)
        and math.isfinite(timeout_s)and 0<timeout_s<=10.,'bounded_unchanged_annotation_epoch_required')
    paths=[Path(q).resolve(strict=True)for q in(prior_plan,plan)]
    code=force._code_identity();inputs={str(q):force._hash(q)for q in paths}
    target=json.loads(paths[0].read_text());final=json.loads(paths[1].read_text())
    families={r['board']:force._family(Path(r['path']),r['board'])for r in final['boards']}
    selected={r['board']:(r['path'],r['sha256'])for r in final['boards']}
    _need(selected=={r['board']:(r['path'],r['sha256'])for r in target['boards']},
        'unchanged_epoch_all_selected_pcbs_must_be_byte_identical')
    _need(all(force._hash(Path(path))==sha for path,sha in selected.values()),'unchanged_epoch_selected_pcb_changed')
    cursor=paths[1];steps=[];seen=set()
    while cursor!=paths[0]:
        _need(cursor not in seen and len(steps)<maximum_links,'unchanged_epoch_finite_acyclic_parent_chain_required')
        seen.add(cursor);current=json.loads(cursor.read_text())
        parent_ref=current['parent_plan'];parent=Path(parent_ref['path']).resolve(strict=True)
        _need(force._hash(parent)==parent_ref['sha256'],'unchanged_epoch_parent_plan_changed')
        ref=current['fresh_annotation_recipe_receiving'];receipt=Path(ref['path']).resolve(strict=True)
        _need(force._hash(receipt)==ref['sha256'],'unchanged_epoch_recipe_receipt_changed')
        proof=json.loads(receipt.read_text());inputs.update({str(parent):force._hash(parent),str(receipt):force._hash(receipt)})
        _need(all(proof.get(k)is True for k in('ok','complete','scope_only',
            'independent_public_plan_and_saved_reconstruction_passed','original_nine_and_ancestor_families_unchanged'))
            and proof.get('old_receipt_or_grade_relabelled')is False
            and proof.get('selected_pcb_or_companions_changed')is False and proof.get('code_identity')==code,
            'unchanged_epoch_fresh_independent_recipe_required')
        normalized={str(Path(p).resolve(strict=True)):h for p,h in proof['inputs'].items()}
        _need(len(normalized)==len(proof['inputs'])and normalized.get(str(parent))==force._hash(parent),
            'unchanged_epoch_actual_parent_recipe_binding_required')
        _need(all(force._hash(Path(p))==h for p,h in {**proof['inputs'],**proof['dependencies']}.items()),
            'unchanged_epoch_recipe_inputs_changed')
        key=_compare_step(json.loads(parent.read_text()),current,proof)
        row=next(r for r in current['boards']if r['board']==key)
        declaration=row['annotation_transition'];base=Path(declaration['steps'][0]['candidate']['path'])
        instance=stage.matched_instance(row.get('assembly_instance'),base)
        replay=chain.receive(base,Path(row['path']),declaration,board_hint=key,
            assembly_instance=instance,timeout_s=timeout_s)
        _need(replay.get('ok')is True and replay.get('complete')is True
            and chain.same_replay(proof['receiving'],replay),'unchanged_epoch_live_saved_recipe_replay_refused')
        steps.append(dict(board=key,receipt=str(receipt),receipt_sha256=force._hash(receipt),
            actual_saved_recipe_replayed=True));cursor=parent
    _need(code==force._code_identity()and all(force._hash(Path(p))==h for p,h in inputs.items())
        and families=={r['board']:force._family(Path(r['path']),r['board'])for r in final['boards']},
        'unchanged_epoch_source_or_code_changed')
    return dict(ok=True,complete=True,scope='fresh_annotation_metadata_only_over_exact_selected_pcbs',
        prior_plan=str(paths[0]),prior_plan_sha256=inputs[str(paths[0])],plan=str(paths[1]),
        plan_sha256=inputs[str(paths[1])],steps=steps,inputs=inputs,code_identity=code,
        selected_pcb_paths_and_bytes_unchanged=True,whole_nine_board_receiving_still_required=True,
        inherited_debt_qualified=False,release_authority=False)
