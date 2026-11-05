"""Fresh canonical-print-origin -> selected print -> Reference-only chain.

No serialized context or worker receipt is authority. Historical print metadata
is checked explicitly while its geometry is independently recompiled now.
Scope only; every original-selected-parent electrical/native gate remains due.
"""
import json,math,re,tempfile,time
from pathlib import Path


def _need(value,message):
    if not value:raise ValueError(message)


def _bound(row):
    import cec_force_current as force
    _need(type(row)is dict and set(row)=={'path','sha256'}and type(row['path'])is str
        and type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']), 'exact_hashed_file_required')
    _need(not Path(row['path']).is_symlink(),'declared_symlink_refused')
    path=Path(row['path']).resolve(strict=True)
    _need(path.is_file()and force._hash(path)==row['sha256'],'declared_file_changed')
    return path


def validate(declaration,selected,candidate):
    _need(type(declaration)is dict and set(declaration)=={'schema','origin','steps'}
        and type(declaration['schema'])is int and declaration['schema']==1,'exact_annotation_chain_schema_required')
    rows=declaration['steps']
    _need(type(rows)is list and len(rows)==2,'exact_two_link_chain_required')
    paths=[_bound(declaration['origin'])];proposals=[]
    for index,row in enumerate(rows):
        kinds=('print_context',)if index==0 else('reference_fields','reference_map')
        _need(type(row)is dict and set(row)=={'kind','candidate','proposal'}and row['kind']in kinds,'exact_annotation_chain_kind_required')
        paths.append(_bound(row['candidate']));proposals.append(_bound(row['proposal']))
    _need(len(set(paths+proposals))==5,'distinct_annotation_chain_paths_required')
    _need(paths[1]==Path(selected).resolve(strict=True)and paths[2]==Path(candidate).resolve(strict=True),'current_selected_chain_endpoint_required')
    return paths,proposals


def _files(root):
    root=Path(root);result={}
    for path in root.rglob('*'):
        _need(not path.is_symlink(),'chain_family_symlink_refused')
        if path.is_file():result[str(path.relative_to(root))]=path.read_bytes()
    return result


def _native_map_ancestor(ancestor,report,tool,canonical,timeout_s):
    """Actual ancestor observation; quarantine only this verified job's lock."""
    import shutil
    import cec_force_current as force
    import cec_native_drc_runner as native
    import cec_native_runtime as runtime
    ancestor=Path(ancestor).resolve(strict=True);report=Path(report).resolve()
    lock=runtime.lock_path(ancestor)
    if lock.exists()or lock.is_symlink():
        failure=ValueError('preexisting_map_ancestor_runtime_lock_refused')
        failure.native_runtime_evidence=runtime.failure_evidence(ancestor)
        raise failure
    _need(not report.is_relative_to(ancestor.parent),'map_runtime_report_must_be_outside_family')
    target=report.parent/'runtime-lock'
    evidence=report.parent/(report.stem+'-runtime-evidence')
    manifest=report.parent/(report.stem+'-runtime-evidence.json')
    _need(all(not p.exists()and not p.is_symlink()for p in(target,evidence,manifest)),
        'fresh_map_runtime_quarantine_required')
    before=_files(ancestor.parent);raw_producer=None
    def run_native():
        nonlocal raw_producer
        result=native.run(ancestor,report,reporting_build=tool,footprint_table=canonical,timeout_s=timeout_s)
        raw_producer=result
        after=_files(ancestor.parent);after.pop(str(lock.relative_to(ancestor.parent)),None)
        _need(before==after,'native_map_ancestor_family_mutated')
        return result
    # The report may live on /tmp while the actual ancestor lives on DrvFS.
    # Both creation fences MUST share the ancestor's filesystem clock. Never
    # put temporary evidence inside its exact family or compare wall clocks.
    with tempfile.TemporaryDirectory(prefix='.cec-map-native-runtime-',dir=ancestor.parent.parent)as directory:
        local=Path(directory)/'runtime';observed=None;failure_diagnostic=None
        try:
            producer,observed=runtime.observe(ancestor,local,run_native)
            if observed.get('generated'):
                owned=Path(observed['new']);data=owned.read_bytes()
                _need(force._hash(owned)==observed['sha256'],'map_runtime_lock_preservation_failed')
                shutil.copyfile(owned,target)
                _need(target.read_bytes()==data and force._hash(target)==observed['sha256'],
                    'map_runtime_lock_preservation_failed')
        except Exception as exc:
            failure_diagnostic=getattr(exc,'native_runtime_evidence',runtime.failure_evidence(ancestor,raw_producer))
            failure_diagnostic['raw_producer']=raw_producer
            failure_diagnostic.update(copied_evidence_root=str(evidence),evidence_manifest=str(manifest))
            failure=ValueError(str(exc));failure.native_runtime_evidence=failure_diagnostic
            raise failure from exc
        finally:
            # Preserve exact original marker/owned-lock bytes even on refusal;
            # a failed or foreign lock remains untouched at its Source.
            if local.is_dir():
                saved=_files(local)
                shutil.copytree(local,evidence)
                _need(saved==_files(evidence),'map_runtime_evidence_copy_changed')
                force._write(manifest,dict(schema=1,ancestor=str(ancestor),
                    local_evidence_root=str(local),copied_evidence_root=str(evidence),
                    exact_file_sha256={name:force._hash(evidence/name)for name in saved},
                    observation=observed,failure_diagnostic=failure_diagnostic,files_preserved_exactly=True,
                    runtime_lock_copy=str(target)if target.is_file()else None,
                    no_preexisting_lock_adopted=True,release_authority=False))
    _need(before==_files(ancestor.parent),'native_map_ancestor_family_mutated')
    return producer


def _phase_names(nested=False,reference=False,*,reference_map=False):
    return (['map_native','map_plan','map_reconstruct','map_receive']if nested else [])+['origin_plan','origin_construct','origin_compare']+(
        (['reference_reconstruct']if reference_map else [])+['reference_scope','reference_material']
        if reference else [])+['identity_live']


def _fresh_nested_map(origin,declaration,board_hint,canonical,work,call,timeout_s):
    """Replay a finite historical recipe with NEW actual-ancestor native evidence."""
    import cec_force_current as force
    import cec_mask_search_reference_mapping as maps
    import cec_native_drc_runner as native
    _need(type(declaration)is dict and set(declaration)in(
        {'source','proposal'},{'source','proposal','mapped_source'},
        {'source','proposal','mapped_source','association_identity'}),
        'exact_nested_map_declaration_required')
    query_mode='association_identity'in declaration
    _need(not query_mode or (type(declaration['association_identity'])is str
        and declaration['association_identity']=='same_literal_map_queries'),
        'exact_nested_map_association_query_mode_required')
    ancestor=_bound(declaration['source']);proposal_path=_bound(declaration['proposal'])
    mapped=_bound(declaration['mapped_source'])if 'mapped_source'in declaration else origin
    _need(len({ancestor,origin,proposal_path,*([mapped]if 'mapped_source'in declaration else [])})
        ==(4 if 'mapped_source'in declaration else 3),'distinct_nested_map_boundaries_required')
    old=json.loads(proposal_path.read_text());binding=old['binding']
    _need(old['board_hint']==board_hint and old.get('reverse_ownership')=='rigid_root_group_per_component'
        and old.get('mode')=='opposite_face_projected_courtyard'
        and (not query_mode or old.get('opposite_face_chart',False)is False)
        and Path(binding['source']).resolve(strict=True)==ancestor
        and binding['source_sha256']==force._hash(ancestor)
        and binding['source_family']==force._family(ancestor,board_hint),
        'exact_historical_map_ancestor_binding_required')
    grade=_bound(dict(path=old['grade'],sha256=binding['grade_sha256']))
    _need(Path(binding['grade']).resolve(strict=True)==grade,'historical_map_grade_path_changed')
    report=_bound(dict(path=binding['native_report'],sha256=binding['native_report_sha256']))
    historical_grade=json.loads(grade.read_text())
    rows=[r for key,r in historical_grade['boards'].items() if key in('source','candidate')
        and r.get('sha256')==force._hash(ancestor)]
    _need(len(rows)==1,'exact_historical_map_grade_source_required')
    produced=rows[0]['native_producer']
    _need(Path(produced['report']).resolve(strict=True)==report
        and produced['report_sha256']==force._hash(report),'historical_map_native_report_binding_changed')
    # This historical path is ONLY an untrusted tool locator. run() verifies
    # the official cap-only build, loaded module, source and library context.
    tool=Path(produced['reporting_build']['root'])
    paths=(ancestor,origin,mapped,proposal_path,grade,report)
    hashes={str(p):force._hash(p)for p in paths}
    families=[force._family(p,board_hint)for p in(ancestor,origin,mapped)]
    epoch=force._code_identity()
    fresh_report=work/'map-native.json'
    producer=call('map_native',lambda:_native_map_ancestor(ancestor,fresh_report,tool,canonical,timeout_s))
    _need(producer.get('ok')is True and producer.get('complete')is True
        and producer['native_inventory']['potentially_truncated']is False,
        'fresh_nested_map_native_grade_refused:'+str(producer.get('errors')))
    fresh_grade=work/'map-grade.json'
    force._write(fresh_grade,dict(code_identity=epoch,boards={'source':dict(
        sha256=force._hash(ancestor),native_producer=producer)},native_only_discovery=True,
        no_scope_or_selection_or_release_authority=True))
    options=dict(grade=fresh_grade,board_hint=board_hint,maximum_components=old['maximum_components'],
        seed_index=old['seed_index'],reverse_ownership='rigid_root_group_per_component',
        owner_uuid_scope=old.get('owner_uuid_scope',()),
        reviewed_courtyard_contract_ids=old.get('reviewed_courtyard_contract_ids',()),
        via_ink_policy=old.get('via_ink_policy','reserve_native_lands'))
    for key in('peripheral_reverse_seats','interrupt_projected_body_guides','opposite_face_chart',
            'project_native_fab_body','positive_leaders_only'):
        if key in old:
            _need(type(old[key])is bool,'explicit_historical_map_recipe_flag_required')
            options[key]=old[key]
    # Discovery and independent saved receiving are distinct finite stages.
    # In particular, legacy discovery must not also receive the saved artifact
    # here and then repeat that same independent receiver below.
    replay=(None if old.get('positive_leaders_only')is True else
        maps.existing_replay(ancestor,mapped,**options))
    fresh=call('map_plan',lambda:(maps.plan(ancestor,**options)
        if replay is None else replay.plan()))
    # Ignore ONLY freshness evidence, never historical geometry, finite options,
    # original Source binding, factory floors, policy or operation metadata.
    def semantics(q):
        q=json.loads(json.dumps(q));q.pop('grade',None);b=q['binding']
        for key in('grade','grade_sha256','native_report','native_report_sha256','code_identity','authority_sha256'):
            b.pop(key,None)
        if 'mask_search_binding'in q:q['mask_search_binding'].pop('input_sha256',None)
        return q
    _need(semantics(old)==semantics(fresh),'historical_map_recipe_or_geometry_changed')
    # Discovery is not saved receiving. The print replay below independently
    # reconstructs and receives this fresh finite map exactly once.
    fresh_path=work/'map-proposal.json';force._write(fresh_path,fresh)
    _need(epoch==force._code_identity()and families==[force._family(p,board_hint)for p in(ancestor,origin,mapped)]
        and all(force._hash(Path(p))==h for p,h in hashes.items()),'nested_map_inputs_or_epoch_changed')
    result=dict(source=declaration['source'],proposal=dict(path=str(fresh_path),sha256=force._hash(fresh_path)))
    if 'mapped_source'in declaration:result['mapped_source']=declaration['mapped_source']
    if query_mode:result['association_identity']='same_literal_map_queries'
    return result


def _origin_replay(origin,selected,historical_path,board_hint,call,timeout_s):
    """Reconstruct actual print bytes now; old metadata is NEVER an epoch waiver."""
    import cec_nonpolar_print_context as print_op
    import cec_optional_body_ink_contract as body
    import cec_received_private_stage as stage
    import cec_native_library_context as libraries
    import cec_synth_pipeline as synth
    historical=json.loads(historical_path.read_text())
    _need(historical['board_hint']==board_hint,'exact_chain_board_hint_required')
    canonical=Path(synth.Config.load(board_hint).dir)/'fp-lib-table'
    old=stage.stable(libraries.authority(origin,canonical))
    context=stage.stable(libraries.authority(selected,selected.parent/'fp-lib-table'))
    _need(stage.stable(historical['old_library_context'])==old,'historical_origin_context_changed')
    _need((selected.parent/'print-proposal.json').read_bytes()==historical_path.read_bytes(),
        'historical_print_proposal_changed')
    expected_metadata=dict(candidate=str(selected),library_table=str(selected.parent/'fp-lib-table'),
        old_library_context=historical['old_library_context'],new_library_context=context,
        physical_original_template_authority_retained=True,whole_stage_source_current_native_receiving_still_required=True,
        admitted=False,release_authority=False)
    _need(json.loads((selected.parent/'print-context.json').read_text())==expected_metadata,
        'historical_print_context_metadata_changed')
    with tempfile.TemporaryDirectory(prefix='cec-fresh-print-origin-')as work:
        transition=historical.get('reference_mapping_transition')
        if transition is not None:
            transition=_fresh_nested_map(origin,transition,board_hint,canonical,Path(work),call,timeout_s)
        options=dict(library_table=str(canonical),
            footprint_ids=historical['footprint_ids'],expected_instance_uuids=historical['expected_instance_uuids'],
            board_hint=board_hint,
            optional_body_footprint_ids=historical.get('optional_body_footprint_ids',()),
            reference_mapping_transition=transition,
            source_chart_group_uuids=historical.get('source_chart_group_uuids',()))
        replay=print_op.staged_replay(origin,options=options,timeout_s=timeout_s,candidate=selected)
        if transition is not None:
            call('map_reconstruct',replay.map_reconstruct)
            call('map_receive',replay.map_receive)
        fresh=call('origin_plan',replay.plan)
        artifact=call('origin_construct',lambda:replay.reconstruct(Path(work)/'exact'))
        proof=call('origin_compare',lambda:replay.compare_origin(selected,historical_path))
        _need(proof.get('ok')is True and proof.get('complete')is True,
            'fresh_origin_literal_print_family_replay_failed')
    return old,context,canonical


def receive_print_row(candidate,declaration,*,board_hint,assembly_instance=None,timeout_s=10.):
    """Explicit fresh-origin replay for a selected historical print artifact.

    Recompiles the positively typed operation under current code, compares
    the WHOLE saved family, and freshly derives actual native authority.
    Historical success receipts and serialized contexts grant no authority.
    """
    import cec_force_current as force
    import cec_received_private_stage as stage
    import cec_native_library_context as libraries
    import cec_nonpolar_print_context as print_op
    result=dict(ok=False,complete=False,scope_only=True,admitted=False,release_authority=False,
        full_kelvin_qualification=False,all_original_selected_parent_gates_still_required=True)
    timings={};started=time.monotonic()
    try:
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
            'bounded_annotation_phase_required')
        _need(type(declaration)is dict and set(declaration)=={'source','proposal'},
            'exact_fresh_origin_declaration_required')
        origin=_bound(declaration['source']);historical=_bound(declaration['proposal'])
        candidate=Path(candidate).resolve(strict=True)
        _need(candidate.is_file()and len({origin,candidate,historical})==3,'distinct_print_origin_paths_required')
        paths=(origin,candidate);code=force._code_identity();families=[force._family(p,board_hint)for p in paths]
        inputs={str(p):force._hash(p)for p in(*paths,historical)}
        import cec_optional_body_ink_contract as body
        deps={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(print_op,print_op.ink,print_op.ink.frame,body)}
        def call(name,fn):
            t=time.monotonic();value=fn();timings[name]=time.monotonic()-t
            _need(timings[name]<timeout_s,'annotation_'+name+'_deadline');return value
        old,context,canonical=_origin_replay(origin,candidate,historical,board_hint,call,timeout_s)
        def identity_live():
            a=stage.identity(origin,board_hint,assembly_instance)
            b=stage.identity(candidate,board_hint,stage.matched_instance(assembly_instance,candidate))
            _need(a['native_library_authority']==old and b['native_library_authority']==old,
                'default_canonical_identity_conflict')
            _need(code==force._code_identity()and families==[force._family(p,board_hint)for p in paths]
                and all(force._hash(Path(p))==h for p,h in {**inputs,**deps}.items())
                and old==stage.stable(libraries.authority(origin,canonical))
                and context==stage.stable(libraries.authority(candidate,candidate.parent/'fp-lib-table')),
                'print_origin_source_code_or_dependencies_changed')
            return a,dict(b,native_library_authority=context)
        a,b=call('identity_live',identity_live)
        _need(time.monotonic()-started<len(_phase_names('map_native'in timings))*timeout_s,'print_origin_aggregate_deadline')
        result.update(ok=True,complete=True,source_identity=a,candidate_identity=b,
            old_library_context=old,new_library_context=context,independent_origin_recompiled=True,
            inputs=inputs,dependencies=deps,code_identity=code,
            source_native_arguments=dict(board_hint=None,footprint_table=str(canonical)),
            candidate_native_arguments=dict(board_hint=None,footprint_table=str(candidate.parent/'fp-lib-table')))
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:
        result['error']=str(exc)
        if hasattr(exc,'native_runtime_evidence'):result['native_runtime_failure']=exc.native_runtime_evidence
    result.update(timings_s=timings,elapsed_s=time.monotonic()-started,
        bounded_composition=dict(per_constituent_limit_s=timeout_s,
            constituents=_phase_names('map_native'in timings),
            aggregate_limit_s=len(_phase_names('map_native'in timings))*timeout_s))
    return result


def same_print_replay(a,b):
    for r in(a,b):
        try:
            bound=r['bounded_composition'];limit=bound['per_constituent_limit_s']
            if(r.get('ok')is not True or r.get('complete')is not True
                or type(limit)not in(int,float)or not math.isfinite(limit)or not 0<limit<=10
                or bound['constituents']not in(_phase_names(),_phase_names(True))
                or bound['aggregate_limit_s']!=len(bound['constituents'])*limit or set(r['timings_s'])!=set(bound['constituents'])
                or not all(type(t)in(int,float)and math.isfinite(t)and 0<=t<limit for t in r['timings_s'].values())
                or not 0<=r['elapsed_s']<len(bound['constituents'])*limit):return False
        except (TypeError,KeyError):return False
    return {k:v for k,v in a.items()if k not in('timings_s','elapsed_s')}=={
        k:v for k,v in b.items()if k not in('timings_s','elapsed_s')}


def receive(selected,candidate,declaration,*,board_hint,assembly_instance=None,timeout_s=10.):
    import cec_force_current as force
    import cec_received_private_stage as stage
    import cec_native_library_context as libraries
    import cec_synth_pipeline as synth
    import cec_nonpolar_print_context as print_op
    import cec_reference_field_seating as fields
    import cec_reference_material_identity as material
    import cec_mask_search_reference_mapping as maps
    import cec_reference_map_material_identity as map_material
    result=dict(ok=False,complete=False,scope_only=True,admitted=False,release_authority=False,
        full_kelvin_qualification=False,inherited_electrical_debt='unchanged_not_evaluated')
    timings={};started=time.monotonic()
    try:
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_annotation_phase_required')
        paths,qs=validate(declaration,selected,candidate);origin,selected,candidate=paths
        code=force._code_identity();families=[force._family(p,board_hint)for p in paths]
        import cec_optional_body_ink_contract as body
        deps={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(print_op,print_op.ink,print_op.ink.frame,body,fields,material,maps,map_material)}
        inputs={str(p):force._hash(p)for p in paths+qs}
        def call(name,fn,limit=timeout_s):
            t=time.monotonic();value=fn();timings[name]=time.monotonic()-t
            _need(timings[name]<limit,'annotation_'+name+'_deadline');return value
        historical=json.loads(qs[0].read_text());q=json.loads(qs[1].read_text())
        _need(historical['board_hint']==board_hint and q['board_hint']==board_hint,'exact_chain_board_hint_required')
        old,context,canonical=_origin_replay(origin,selected,qs[0],board_hint,call,timeout_s)
        annotation_kind=declaration['steps'][1]['kind']
        if annotation_kind=='reference_fields':
            scope=call('reference_scope',lambda:fields.receive(selected,candidate,q))
            _need(scope.get('ok')is True and scope.get('complete')is True,'reference_scope_refused:'+str(scope.get('errors')))
            identity=call('reference_material',lambda:material.receive(selected,candidate,timeout_s=timeout_s))
        else:
            # The rigid-map material receiver already independently reconstructs
            # and receives the exact map. Compose its TWO bounded phases instead
            # of doing that reconstruction twice and then mistakenly treating
            # its two-phase result as one <=10s check. No worker receipt or
            # caller-supplied UUID scope substitutes for its fresh native replay.
            identity=map_material.receive(selected,candidate,qs[1],timeout_s=timeout_s,staged_map_replay=True)
            _need(identity.get('ok')is True and identity.get('complete')is True,
                'reference_material_refused:'+str(identity.get('error')))
            phases=identity['timings_s'];bound=identity['bounded_composition']
            _need(set(phases)=={'map_reconstruct','map_scope','material_live'}and bound==dict(
                map_reconstruct_limit_s=timeout_s,map_scope_limit_s=timeout_s,
                material_live_limit_s=timeout_s,aggregate_limit_s=3*timeout_s)
                and all(type(t)in(int,float)and math.isfinite(t)and 0<=t<timeout_s for t in phases.values())
                and 0<=identity['elapsed_s']<3*timeout_s,'bounded_reference_map_material_phases_required')
            timings['reference_reconstruct']=phases['map_reconstruct']
            timings['reference_scope']=phases['map_scope'];timings['reference_material']=phases['material_live']
            scope=identity['map_scope']
            _need(scope.get('ok')is True and scope.get('complete')is True,'reference_scope_refused:'+str(scope.get('errors')))
        _need(identity.get('ok')is True and identity.get('same_material')is True and identity.get('complete')is True,'reference_material_refused')
        def live_identity():
            before=_files(selected.parent);after=_files(candidate.parent)
            before.pop(selected.name);after.pop(candidate.name)
            _need(before==after,'annotation_companion_library_or_metadata_changed')
            child_context=stage.stable(libraries.authority(candidate,candidate.parent/'fp-lib-table'))
            # Absolute context paths differ, but the exact complete table/library
            # byte replay above and identical FPID reference inventory bind both.
            _need(stage.stable(context['references'])==stage.stable(child_context['references']),'annotation_fpid_references_changed')
            a=stage.identity(selected,board_hint,assembly_instance)
            b=stage.identity(candidate,board_hint,stage.matched_instance(assembly_instance,candidate))
            _need(a['native_library_authority']==old and b['native_library_authority']==old,'default_canonical_identity_conflict')
            _need(old==stage.stable(libraries.authority(origin,canonical))
                and context==stage.stable(libraries.authority(selected,selected.parent/'fp-lib-table')),
                'origin_or_selected_library_context_changed')
            _need(code==force._code_identity()and families==[force._family(p,board_hint)for p in paths]
                and all(force._hash(Path(p))==h for p,h in inputs.items())
                and all(force._hash(Path(p))==h for p,h in deps.items()),'annotation_source_code_or_dependencies_changed')
            return child_context,dict(a,native_library_authority=context),dict(b,native_library_authority=child_context)
        child_context,a,b=call('identity_live',live_identity)
        _need(time.monotonic()-started<len(_phase_names('map_native'in timings,True,
            reference_map=annotation_kind=='reference_map'))*timeout_s,'annotation_aggregate_deadline')
        result.update(ok=True,complete=True,source_identity=a,candidate_identity=b,
            annotation_kind=annotation_kind,
            old_library_context=context,new_library_context=child_context,reference_scope=scope,
            material_identity=identity,code_identity=code,dependencies=deps,inputs=inputs,
            source_native_arguments=dict(board_hint=None,footprint_table=str(selected.parent/'fp-lib-table')),
            candidate_native_arguments=dict(board_hint=None,footprint_table=str(candidate.parent/'fp-lib-table')),
            independent_origin_recompiled=True,all_original_selected_parent_gates_still_required=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:
        result['error']=str(exc)
        if hasattr(exc,'native_runtime_evidence'):result['native_runtime_failure']=exc.native_runtime_evidence
    result['timings_s']=timings;result['elapsed_s']=time.monotonic()-started
    names=_phase_names('map_native'in timings,True,
        reference_map=result.get('annotation_kind')=='reference_map'or 'reference_reconstruct'in timings)
    result['bounded_composition']=dict(per_constituent_limit_s=timeout_s,constituents=names,aggregate_limit_s=len(names)*timeout_s)
    return result


def same_replay(a,b):
    if not all(r.get('ok')is True and r.get('complete')is True for r in(a,b)):return False
    for r in(a,b):
        try:
            bound=r['bounded_composition'];limit=bound['per_constituent_limit_s']
            if(type(limit)not in(int,float)or not math.isfinite(limit)or not 0<limit<=10
                or bound['constituents']not in(
                    _phase_names(reference=True,reference_map=r.get('annotation_kind')=='reference_map'),
                    _phase_names(True,True,reference_map=r.get('annotation_kind')=='reference_map'))
                or bound['aggregate_limit_s']!=len(bound['constituents'])*limit or set(r['timings_s'])!=set(bound['constituents'])
                or not all(type(t)in(int,float)and math.isfinite(t)and 0<=t<limit for t in r['timings_s'].values())
                or not 0<=r['elapsed_s']<len(bound['constituents'])*limit):return False
        except (TypeError,KeyError):return False
    def stable(r):
        r=dict(r);r.pop('timings_s',None);r.pop('elapsed_s',None)
        if 'material_identity'in r:
            r['material_identity']=dict(r['material_identity']);m=r['material_identity']
            if 'timings_s'in m:
                bound=m.get('bounded_composition',{});phases=m['timings_s']
                staged=r.get('annotation_kind')=='reference_map'
                if (set(phases)!=set(('map_reconstruct','map_scope','material_live')if staged else('map_scope','material_live'))or
                        bound.get('map_scope_limit_s')!=bound.get('material_live_limit_s')or
                        (staged and bound.get('map_reconstruct_limit_s')!=bound.get('map_scope_limit_s'))or
                        bound.get('aggregate_limit_s')!=(3 if staged else 2)*bound.get('map_scope_limit_s',0)or
                        not 0<bound.get('map_scope_limit_s',0)<=10 or
                        not all(type(v)in(int,float)and math.isfinite(v)and
                            0<=v<bound['map_scope_limit_s']for v in phases.values())):
                    raise ValueError('bounded_material_timing_replay_required')
                m.pop('timings_s')
            m.pop('elapsed_s',None)
        return r
    try:return stable(a)==stable(b)
    except (ValueError,TypeError):return False
