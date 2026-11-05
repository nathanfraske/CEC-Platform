"""Exact material preservation under footprint-silk-line-only differences.

This proves a relation, not absolute electrical/Kelvin/fabrication fitness.
The entire saved AST and the entire independently native-serialized AST must
match after omitting ONLY direct F/B.SilkS fp_line children of footprints.
Nothing else (including opaque attributes, models, custom pads, groups,
stackup, nets, outlines and saved fills) is ignored. Print ownership/permission
must be independently received: this module cannot authorize ink removal.
"""
import hashlib,json,math,os,re,tempfile,time
from pathlib import Path

MAX_BYTES=32*1024*1024
MAX_TOKENS=2000000
TOKEN=re.compile(r'"(?:[^"\\]|\\.)*"|;[^\r\n]*|[()]|[^\s();"]+')


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('ink_material_identity_deadline')


def _without_silk_lines(path,deadline):
    import cec_source_literal_additions as literal
    import cec_source_retaining_ses_import as raw
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('ink_identity_native_text_bound')
    text=path.read_text();spans,_=literal._root(text);cuts=[];count=0
    for a,b in spans:
        _tick(deadline)
        part=text[a:b]
        if raw.kind(part)!='footprint':continue
        for x,y in raw.children(part):
            node=part[x:y]
            if raw.kind(node)!='fp_line':continue
            layers=[node[p:q]for p,q in raw.children(node)if raw.kind(node[p:q])=='layer']
            if len(layers)!=1:raise ValueError('unique_native_footprint_line_layer_required')
            atoms=literal._atoms(layers[0][1:-1])
            if len(atoms)!=2 or atoms[0][0]!='layer':raise ValueError('exact_native_line_layer_required')
            if atoms[1][0]in('F.SilkS','B.SilkS'):cuts.append((a+x,a+y));count+=1
    for a,b in reversed(cuts):text=text[:a]+text[b:]
    tokens=[]
    for match in TOKEN.finditer(text):
        if len(tokens)%4096==0:_tick(deadline)
        token=match.group()
        if token.startswith(';'):continue
        tokens.append(token)
        if len(tokens)>MAX_TOKENS:raise ValueError('ink_identity_ast_token_bound')
    _tick(deadline)
    return tokens,count


def _digest(tokens):return hashlib.sha256(json.dumps(tokens,separators=(',',':')).encode()).hexdigest()


def receive(source,candidate,*,timeout_s=10.):
    """Paths only; no caller proof, source board, inventory or cache accepted."""
    result=dict(ok=False,complete=False,comparison_complete=False,same_material=False,
        scope='entire_saved_and_native_ast_identity_except_footprint_silk_lines',
        inherited_electrical_debt='unchanged_not_evaluated',full_kelvin_qualification=False,
        kelvin_isolation_qualified=None,ink_authority=False,new_route_authority=False,
        independent_print_scope_receiving_required=True,
        external_source_electrical_contract_receiving_required=True,admitted=False,release_authority=False)
    started=time.monotonic()
    try:
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
            raise ValueError('bounded_ink_material_identity_required')
        deadline=started+timeout_s
        import pcbnew
        import cec_swig_guard;cec_swig_guard.pin()
        import _pcbnew
        import cec_force_current as force
        import cec_field_coupling as field
        paths=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_ink_identity_paths_required')
        code=force._code_identity();families=[force._family(p)for p in paths]
        source_hashes=[force._hash(p)for p in paths]
        native_files={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(pcbnew,_pcbnew)}
        environment=sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH')
        for suffix in('.kicad_pro','.kicad_dru'):
            values=[p.with_suffix(suffix).read_bytes()if p.with_suffix(suffix).is_file()else None for p in paths]
            if values[0]!=values[1]:raise ValueError('ink_identity_project_or_rule_sidecar_changed:'+suffix)
        _tick(deadline)
        raw=[_without_silk_lines(p,deadline)for p in paths]
        if raw[0][0]!=raw[1][0]:raise ValueError('non_ink_saved_ast_changed')
        native=[];boards=[]
        with tempfile.TemporaryDirectory(prefix='cec-complete-native-ink-identity-')as work:
            for index,path in enumerate(paths):
                _tick(deadline);board=pcbnew.LoadBoard(str(path));boards.append(board)
                if board is None or board.GetClass()!='BOARD':raise ValueError('complete_native_board_required')
                saved=Path(work)/(str(index)+'.kicad_pcb');field._save_field_snapshot(board,saved)
                native.append(_without_silk_lines(saved,deadline))
            if native[0][0]!=native[1][0]:raise ValueError('non_ink_complete_native_ast_changed')
        _tick(deadline)
        if (code!=force._code_identity()or families!=[force._family(p)for p in paths]
                or source_hashes!=[force._hash(p)for p in paths]
                or any(force._hash(Path(p))!=h for p,h in native_files.items())
                or environment!=sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH')):
            raise ValueError('ink_material_identity_source_code_family_or_native_changed')
        _tick(deadline)
        result.update(ok=True,complete=True,comparison_complete=True,same_material=True,
            source=str(paths[0]),candidate=str(paths[1]),saved_sha256=source_hashes,
            code_identity=code,source_families=families,native_implementation=native_files,
            unchanged_saved_ast_sha256=_digest(raw[0][0]),unchanged_native_ast_sha256=_digest(native[0][0]),
            omitted_silk_line_counts=dict(saved=[v[1]for v in raw],native=[v[1]for v in native]),
            reason='identical_complete_query_inputs_not_absolute_query_qualification')
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:result['error']=str(exc)
    result['elapsed_s']=time.monotonic()-started
    return result
