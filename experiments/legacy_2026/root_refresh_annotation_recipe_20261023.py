"""Recompile a selected annotation recipe; never relabel an old epoch.

The actual ancestor gets a NEW native report under independently received
print-library authority. The public planner and saved receiver then rederive
the operation under current code. The selected PCB must remain byte-exact.
"""
import argparse,copy,json,time
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import cec_force_current as force
import cec_chained_annotation_transition as chain
import cec_received_private_stage as stage
import cec_native_drc_runner as native
import cec_reference_field_seating as fields
import cec_mask_search_reference_mapping as maps
import typed_print_runtime as runtime


def recipe_options(old,*,kind,grade,board_hint):
    """Only public finite search inputs; old bindings/success never copied."""
    if kind not in('reference_fields','reference_map')or old.get('board_hint')!=board_hint:
        raise ValueError('explicit_matching_annotation_recipe_required')
    # Field planners serialize their finite inputs in request; map planners
    # retain the original top-level public input schema. Never copy either
    # planner's old binding, discovered geometry, proof or success metadata.
    inputs=old.get('request',old)if kind=='reference_fields'else old
    if type(inputs)is not dict:raise ValueError('explicit_annotation_recipe_inputs_required')
    result=dict(grade=Path(grade),board_hint=board_hint,
        maximum_components=inputs['maximum_components'],seed_index=inputs['seed_index'],
        owner_uuid_scope=copy.deepcopy(inputs.get('owner_uuid_scope',())),
        reviewed_courtyard_contract_ids=copy.deepcopy(inputs.get('reviewed_courtyard_contract_ids',())))
    if kind=='reference_fields':
        result['timeout_s']=10.
        for key in('max_gap_mm','cooperative'):
            if key in inputs:result[key]=copy.deepcopy(inputs[key])
    else:
        if old.get('reverse_ownership')!='rigid_root_group_per_component':
            raise ValueError('rigid_annotation_recipe_required')
        result.update(reverse_ownership='rigid_root_group_per_component',
            via_ink_policy=old.get('via_ink_policy','reserve_native_lands'))
        if 'peripheral_reverse_seats'in old:
            if type(old['peripheral_reverse_seats'])is not bool:
                raise ValueError('explicit_peripheral_reverse_search_flag_required')
            result['peripheral_reverse_seats']=old['peripheral_reverse_seats']
        if 'interrupt_projected_body_guides'in old:
            if type(old['interrupt_projected_body_guides'])is not bool:
                raise ValueError('explicit_projected_body_guide_interruption_required')
            result['interrupt_projected_body_guides']=old['interrupt_projected_body_guides']
        if 'opposite_face_chart'in old:
            if type(old['opposite_face_chart'])is not bool:
                raise ValueError('explicit_opposite_face_reference_chart_required')
            result['opposite_face_chart']=old['opposite_face_chart']
        if 'project_native_fab_body'in old:
            if type(old['project_native_fab_body'])is not bool:
                raise ValueError('explicit_native_fab_body_projection_required')
            result['project_native_fab_body']=old['project_native_fab_body']
        if 'positive_leaders_only'in old:
            if type(old['positive_leaders_only'])is not bool:
                raise ValueError('explicit_positive_reference_leader_policy_required')
            result['positive_leaders_only']=old['positive_leaders_only']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--board',required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    plan=json.loads(a.plan.read_text());rows={r['board']:r for r in plan['boards']};row=rows[a.board]
    selected=Path(row['path']).resolve(strict=True);assert force._hash(selected)==row['sha256']
    declaration=row['annotation_transition'];paths,proposals=chain.validate(declaration,
        declaration['steps'][0]['candidate']['path'],selected)
    origin,base,selected=paths;kind=declaration['steps'][1]['kind']
    code=force._code_identity();plan_hash=force._hash(a.plan)
    families={key:force._family(Path(r['path']),key)for key,r in rows.items()}
    ancestor_families=[force._family(p,a.board)for p in paths]
    inputs={str(p):force._hash(p)for p in(a.plan,*paths,*proposals,Path(__file__))}
    deps={**fields.dependencies(),**maps.dependencies(),str(Path(runtime.__file__).resolve()):force._hash(Path(runtime.__file__))}
    # Rewind only the matched member, never a whole older stack or board guess.
    base_instance=stage.matched_instance(row.get('assembly_instance'),base)
    origin_instance=stage.matched_instance(base_instance,origin)
    print_declaration=dict(source=declaration['origin'],proposal=declaration['steps'][0]['proposal'])
    authority=chain.receive_print_row(base,print_declaration,board_hint=a.board,
        assembly_instance=origin_instance,timeout_s=10.)
    assert authority['ok']and authority['complete'],authority.get('error')
    tool=Path('/home/codex/.cache/cec/native-drc-10.0.5')
    producer,preserved=runtime.observe(base,a.out/'ancestor-runtime',lambda:native.run(base,
        a.out/'ancestor-native.json',reporting_build=tool,timeout_s=10.,**authority['candidate_native_arguments']))
    stage.require_native_tool(producer,native._describe_build(tool))
    context=producer['native_library_context']
    assert context['bound']and context['source_and_context_unchanged']
    assert stage.stable(context['authority'])==authority['new_library_context']
    grade=a.out/'fresh-ancestor-grade.json'
    force._write(grade,dict(code_identity=code,boards={'source':dict(sha256=force._hash(base),native_producer=producer)},
        native_only_discovery=True,no_scope_or_selection_or_release_authority=True))
    old=json.loads(proposals[1].read_text());operation=fields if kind=='reference_fields'else maps
    options=recipe_options(old,kind=kind,grade=grade,board_hint=a.board)
    fresh=(operation.replay_existing_plan(base,selected,**options)if kind=='reference_map'else
        operation.plan(base,**options))
    qpath=a.out/'fresh-proposal.json';force._write(qpath,fresh)
    updated=copy.deepcopy(declaration)
    updated['steps'][1]['proposal']=dict(path=str(qpath.resolve()),sha256=force._hash(qpath))
    received=chain.receive(base,selected,updated,board_hint=a.board,assembly_instance=base_instance,timeout_s=10.)
    assert received['ok']and received['complete'],received.get('error')
    assert code==force._code_identity()and plan_hash==force._hash(a.plan)
    assert inputs=={p:force._hash(Path(p))for p in inputs}
    assert families=={key:force._family(Path(r['path']),key)for key,r in rows.items()}
    assert ancestor_families==[force._family(p,a.board)for p in paths]
    assert all(force._hash(Path(p))==h for p,h in deps.items())
    proof=dict(ok=True,complete=True,scope_only=True,board=a.board,selected=str(selected),
        selected_sha256=force._hash(selected),annotation_transition=updated,receiving=received,
        actual_fresh_ancestor_native=producer,ancestor_runtime_preserved=preserved,
        old_receipt_or_grade_relabelled=False,selected_pcb_or_companions_changed=False,
        independent_public_plan_and_saved_reconstruction_passed=True,
        original_nine_and_ancestor_families_unchanged=True,inputs=inputs,dependencies=deps,
        code_identity=code,goal_complete=False,release_authority=False)
    force._write(a.out/'receiving.json',proof)
    updated_plan=copy.deepcopy(plan)
    target=next(r for r in updated_plan['boards']if r['board']==a.board)
    target['annotation_transition']=updated
    updated_plan['parent_plan']=dict(path=str(a.plan.resolve()),sha256=plan_hash)
    updated_plan['fresh_annotation_recipe_receiving']=dict(path=str((a.out/'receiving.json').resolve()),sha256=force._hash(a.out/'receiving.json'))
    updated_plan['fresh_nine_board_receiving_required']=True
    force._write(a.out/'plan.json',updated_plan)
    print(json.dumps(dict(ok=True,pcb_unchanged=True,plan=str(a.out/'plan.json'),sha256=force._hash(a.out/'plan.json'))),flush=True)


if __name__=='__main__':main()
