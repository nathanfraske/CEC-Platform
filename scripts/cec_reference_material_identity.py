"""Exact query-input identity except unique Reference at/effects.

Relation only: independent annotation receiving must establish mutation authority.
No ink, copper, field text, visibility or opaque property attributes are ignored.
"""
import hashlib,json,math,os,tempfile,time
from pathlib import Path
import cec_ink_material_identity as base


def _projection(path,deadline):
    import cec_source_literal_additions as literal
    import cec_source_retaining_ses_import as raw
    text=Path(path).read_text()
    if len(text.encode())>base.MAX_BYTES:raise ValueError('reference_ast_byte_bound')
    spans,_=literal._root(text);cuts=[];owners={};seen=set();field_ids=set()
    def children(node,kind):return [(a,b,node[a:b])for a,b in raw.children(node)if raw.kind(node[a:b])==kind]
    def unique(node,kind):
        rows=children(node,kind)
        if len(rows)!=1:raise ValueError('unique_reference_'+kind+'_required')
        return rows[0]
    def atoms(node):return [v[0]for v in literal._atoms(node[1:-1])]
    for a,b in spans:
        base._tick(deadline);fp=text[a:b]
        if raw.kind(fp)!='footprint':continue
        uid=atoms(unique(fp,'uuid')[2])
        if len(uid)!=2 or uid[1]in seen:raise ValueError('unique_footprint_identity_required')
        seen.add(uid[1]);refs=[]
        for x,y,node in children(fp,'property'):
            # Property nodes contain nested effects: inspect only their
            # literal header, never interpret a nested subtree as scalar.
            values=base.TOKEN.findall(node)
            if len(values)>3 and values[:3]==['(','property','"Reference"']:refs.append((x,y,node))
        if len(refs)!=1:raise ValueError('unique_reference_property_required')
        x,y,node=refs[0];refuid=atoms(unique(node,'uuid')[2])
        if len(refuid)!=2 or refuid[1]in field_ids or refuid[1]in seen:
            raise ValueError('unique_reference_field_identity_required')
        field_ids.add(refuid[1])
        selected=[]
        for kind in('at','effects'):
            p,q,part=unique(node,kind);cuts.append((a+x+p,a+x+q));selected.append(tuple(base.TOKEN.findall(part)))
        owners[uid[1]]=(refuid[1],selected)
    for a,b in sorted(cuts,reverse=True):text=text[:a]+text[b:]
    tokens=[]
    for match in base.TOKEN.finditer(text):
        if len(tokens)%4096==0:base._tick(deadline)
        token=match.group()
        if not token.startswith(';'):tokens.append(token)
        if len(tokens)>base.MAX_TOKENS:raise ValueError('reference_ast_token_bound')
    return tokens,owners


def _compare(paths,deadline):
    rows=[_projection(p,deadline)for p in paths]
    if rows[0][0]!=rows[1][0]or rows[0][1].keys()!=rows[1][1].keys():
        raise ValueError('non_reference_material_ast_changed')
    changed=[]
    for uid,old in rows[0][1].items():
        new=rows[1][1][uid]
        if old[0]!=new[0]:raise ValueError('reference_identity_changed')
        if old!=new:changed.append(uid)
    return base._digest(rows[0][0]),sorted(changed)


def receive(source,candidate,*,timeout_s=10.):
    """Accept paths only; infer exact changed owners, never accept caller scope."""
    started=time.monotonic();result=dict(ok=False,complete=False,same_material=False,
        comparison_complete=False,scope_only=True,admitted=False,mutation_authority=False,
        independent_reference_scope_receiving_required=True,full_kelvin_qualification=False,
        kelvin_isolation_qualified=None,inherited_electrical_debt='unchanged_not_evaluated')
    try:
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
            raise ValueError('bounded_reference_identity_required')
        deadline=started+timeout_s
        import pcbnew,_pcbnew
        import cec_swig_guard;cec_swig_guard.pin()
        import cec_force_current as force
        import cec_field_coupling as field
        paths=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_paths_required')
        code=force._code_identity();families=[force._family(p)for p in paths]
        hashes=[force._hash(p)for p in paths]
        implementations={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(pcbnew,_pcbnew,base)}
        def env():return sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH')
        environment=env()
        for suffix in('.kicad_pro','.kicad_dru'):
            values=[p.with_suffix(suffix).read_bytes()if p.with_suffix(suffix).is_file()else None for p in paths]
            if values[0]!=values[1]:raise ValueError('project_or_rules_changed')
        raw_digest,changed=_compare(paths,deadline)
        boards=[]
        with tempfile.TemporaryDirectory(prefix='cec-reference-material-')as work:
            saved=[]
            for i,p in enumerate(paths):
                base._tick(deadline);board=pcbnew.LoadBoard(str(p));boards.append(board)
                if board is None or board.GetClass()!='BOARD':raise ValueError('complete_native_board_required')
                target=Path(work)/(str(i)+'.kicad_pcb');field._save_field_snapshot(board,target);saved.append(target)
            native_digest,native_changed=_compare(saved,deadline)
            if changed!=native_changed:raise ValueError('saved_native_reference_scope_disagrees')
        if(code!=force._code_identity()or families!=[force._family(p)for p in paths]
            or hashes!=[force._hash(p)for p in paths]or environment!=env()
            or any(force._hash(Path(p))!=h for p,h in implementations.items())):
            raise ValueError('source_code_family_or_native_changed')
        base._tick(deadline)
        result.update(ok=True,complete=True,comparison_complete=True,same_material=True,
            source=str(paths[0]),candidate=str(paths[1]),saved_sha256=hashes,
            changed_owner_uuids=changed,unchanged_saved_ast_sha256=raw_digest,
            unchanged_native_ast_sha256=native_digest,code_identity=code,
            source_families=families,native_implementation=implementations)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:result['error']=str(exc)
    result['elapsed_s']=time.monotonic()-started
    return result
