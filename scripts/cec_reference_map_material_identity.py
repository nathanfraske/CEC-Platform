"""Exact material relation under independently received rigid-root maps.

The map receiver, not a caller UUID list, owns new root ink/group nodes and
selected Reference visibility. No absolute Kelvin or manufacturing authority.
"""
import json,math,os,tempfile,time
from pathlib import Path
import cec_ink_material_identity as base


def _need(value,message):
    if not value:raise ValueError(message)


def _project(path,ids,refs,child,deadline):
    import cec_source_literal_additions as literal
    import cec_source_retaining_ses_import as raw
    text=Path(path).read_text();_need(len(text.encode())<=base.MAX_BYTES,'map_ast_byte_bound')
    spans,_=literal._root(text);cuts=[];found=set();fields=set();all_ids=set()
    for a,b in spans:
        base._tick(deadline);node=text[a:b];kind=raw.kind(node);uid=raw.node_uuid(node)
        if uid:
            _need(uid not in all_ids,'duplicate_root_identity');all_ids.add(uid)
        if uid in ids:
            _need(child and kind in('gr_text','gr_line','gr_poly','gr_rect','gr_arc','gr_circle','group'), 'non_annotation_owned_root_refused')
            found.add(uid);cuts.append((a,b));continue
        if kind!='footprint':continue
        for x,y in raw.children(node):
            prop=node[x:y]
            if raw.kind(prop)!='property':continue
            refid=raw.node_uuid(prop)
            if refid not in refs:continue
            _need(refid not in fields and uid==refs[refid],'unique_actual_reference_owner_required')
            _need(base.TOKEN.findall(prop)[:3]==['(','property','"Reference"'],'actual_reference_property_required')
            fields.add(refid)
            hide=[(p,q)for p,q in raw.children(prop)if raw.kind(prop[p:q])=='hide']
            _need(len(hide)<=1,'unique_reference_visibility_required')
            for p,q in hide:cuts.append((a+x+p,a+x+q))
    _need(found==(ids if child else set())and fields==set(refs),'complete_owned_map_scope_required')
    for a,b in sorted(cuts,reverse=True):text=text[:a]+text[b:]
    tokens=[]
    for m in base.TOKEN.finditer(text):
        if len(tokens)%4096==0:base._tick(deadline)
        if not m.group().startswith(';'):tokens.append(m.group())
        _need(len(tokens)<=base.MAX_TOKENS,'map_ast_token_bound')
    return tokens


def receive(source,candidate,proposal_path,*,timeout_s=10.,staged_map_replay=False):
    """Exact map material; optional independent reconstruction/comparison stages."""
    result=dict(ok=False,complete=False,same_material=False,comparison_complete=False,
        scope_only=True,admitted=False,release_authority=False,mutation_authority=False,
        full_kelvin_qualification=False,kelvin_isolation_qualified=None,
        inherited_electrical_debt='unchanged_not_evaluated',independent_map_receiving_required=True)
    started=time.monotonic();timings={}
    try:
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_map_identity_required')
        _need(type(staged_map_replay)is bool,'explicit_staged_map_replay_boolean_required')
        import pcbnew,_pcbnew
        import cec_swig_guard;cec_swig_guard.pin()
        import cec_force_current as force
        import cec_field_coupling as field
        import cec_mask_search_reference_mapping as maps
        paths=[Path(p).resolve(strict=True)for p in(source,candidate,proposal_path)]
        _need(len(set(paths))==3,'distinct_map_identity_paths_required')
        source,candidate,proposal_path=paths;proposal=json.loads(proposal_path.read_text())
        _need(proposal.get('reverse_ownership')=='rigid_root_group_per_component'
            and proposal.get('mode')in('opposite_face_projected_courtyard','nearby_opposite_face_mapping_chart'),
            'only_rigid_root_reverse_map_supported')
        code=force._code_identity();families=[force._family(p)for p in paths[:2]];hashes=[force._hash(p)for p in paths]
        deps={**maps.dependencies(),str(Path(base.__file__).resolve()):force._hash(Path(base.__file__))}
        native={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(pcbnew,_pcbnew)}
        def env():return sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH')
        environment=env()
        if staged_map_replay:
            replay=maps.saved_replay(source,candidate,proposal,timeout_s=timeout_s)
            replay.reconstruct();timings['map_reconstruct']=time.monotonic()-started
            _need(timings['map_reconstruct']<timeout_s,'map_reconstruct_deadline')
            scope_start=time.monotonic();proof=replay.receive()
            timings['map_scope']=time.monotonic()-scope_start
        else:
            proof=maps.receive(source,candidate,proposal)
            timings['map_scope']=time.monotonic()-started
        _need(timings['map_scope']<timeout_s,'map_scope_deadline')
        _need(proof.get('ok')is True and proof.get('complete')is True,'independent_map_scope_refused:'+str(proof.get('errors')))
        material_start=time.monotonic();deadline=material_start+timeout_s
        manifest=proof['manifest'];ids=set(manifest['added_root_annotation_uuids'])|set(manifest['added_reverse_group_uuids'])
        if proposal['mode']=='nearby_opposite_face_mapping_chart':
            _need(proposal.get('opposite_face_chart')is True and manifest.get('added_group_uuid')
                and not manifest['added_reverse_group_uuids'],'exact_independently_received_rear_chart_group_required')
            ids.add(manifest['added_group_uuid'])
        else:_need(not manifest.get('added_group_uuid'),'projected_reference_cannot_own_chart_group')
        _need(ids and len(ids)<=256,'bounded_reverse_map_root_scope_required')
        records=proposal['records'];_need(type(records)is list and 1<=len(records)<=8,'bounded_map_owner_scope_required')
        refs={r['reference_field_uuid']:r['footprint_uuid']for r in records}
        _need(len(refs)==len(records)and len(set(refs.values()))==len(records),'unique_map_owner_scope_required')
        for suffix in('.kicad_pro','.kicad_dru'):
            values=[p.with_suffix(suffix).read_bytes()if p.with_suffix(suffix).is_file()else None for p in paths[:2]]
            _need(values[0]==values[1],'map_project_or_rules_changed')
        raw=[_project(p,ids,refs,i==1,deadline)for i,p in enumerate(paths[:2])]
        _need(raw[0]==raw[1],'non_map_saved_ast_changed')
        boards=[];rendered=[]
        with tempfile.TemporaryDirectory(prefix='cec-map-material-')as work:
            for i,p in enumerate(paths[:2]):
                base._tick(deadline);b=pcbnew.LoadBoard(str(p));boards.append(b)
                _need(b is not None and b.GetClass()=='BOARD','complete_native_board_required')
                saved=Path(work)/(str(i)+'.kicad_pcb');field._save_field_snapshot(b,saved)
                rendered.append(_project(saved,ids,refs,i==1,deadline))
            _need(rendered[0]==rendered[1],'non_map_native_ast_changed')
        _need(code==force._code_identity()and families==[force._family(p)for p in paths[:2]]
            and hashes==[force._hash(p)for p in paths]and environment==env()
            and all(force._hash(Path(p))==h for p,h in {**deps,**native}.items()),'map_source_code_dependency_or_native_changed')
        base._tick(deadline);timings['material_live']=time.monotonic()-material_start
        _need(time.monotonic()-started<(3 if staged_map_replay else 2)*timeout_s,'map_identity_aggregate_deadline')
        result.update(ok=True,complete=True,same_material=True,comparison_complete=True,
            source=str(source),candidate=str(candidate),proposal=str(proposal_path),saved_sha256=hashes,
            map_scope=proof,owned_root_annotation_uuids=sorted(ids),owned_reference_fields=refs,
            unchanged_saved_ast_sha256=base._digest(raw[0]),unchanged_native_ast_sha256=base._digest(rendered[0]),
            code_identity=code,dependencies=deps,native_implementation=native)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:result['error']=str(exc)
    bounds=dict(map_scope_limit_s=timeout_s,material_live_limit_s=timeout_s,
        aggregate_limit_s=(3 if staged_map_replay is True else 2)*timeout_s)
    if staged_map_replay is True:bounds['map_reconstruct_limit_s']=timeout_s
    result.update(timings_s=timings,elapsed_s=time.monotonic()-started,bounded_composition=bounds)
    return result
