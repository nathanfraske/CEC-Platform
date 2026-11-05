"""Staged opt-in SES admission. No default router behavior or release authority.

The parent enforces a whole-operation process lease. The worker reuses the
existing SES importer, then discards its source nodes and retains only new
copper. Source text is opaque except existing GND filled_polygon children.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time


def scripts_directory(location):
    """Resolve either scripts/module.py or build/stage/module.py layouts."""
    for parent in Path(location).resolve().parents:
        if (parent/'cec_fr.py').is_file() and (parent/'cec_force_current.py').is_file():
            return parent
        candidate=parent/'scripts'
        if (candidate/'cec_fr.py').is_file() and (candidate/'cec_force_current.py').is_file():
            return candidate
    raise ValueError('repository_scripts_directory_not_found')


def assembly_identity(source, instance):
    if instance is None:
        return None
    import cec_assembly_instance
    import cec_full_pipeline as pipeline
    return json.loads(json.dumps(cec_assembly_instance.resolve(source,instance,pipeline.ROOT),default=str))


def require_intake(intake):
    if not intake.get('ok') or not intake.get('intake',{}).get('ok'):
        raise ValueError('live_source_intake_refused')


def require_saved_route_craft(report,before_metrics,after_metrics):
    """No new saved craft finding may be paid for by removing another one.

    Reuse the already-fresh scorer inventories, not a stale receipt or another
    native pass. Missing/errored craft evidence withholds import admission.
    This grants no release authority to inherited incomplete board geometry.
    """
    from cec_received_private_stage import route_craft_delta
    inventories=[]
    for metrics in (before_metrics,after_metrics):
        detail=getattr(metrics,'detail',None)
        quality=detail.get('route_quality') if type(detail)is dict else None
        if type(quality)is not dict or quality.get('error'):
            raise ValueError('complete_saved_route_craft_evidence_required')
        inventories.append(quality)
    proof=route_craft_delta(*inventories)
    report['saved_route_craft_nonregression']=proof
    if proof.get('ok') is not True:
        raise ValueError('introduced_saved_route_craft_defects')
    return proof


def raw_error_delta(before,after):
    """Do not let a scorer or a same-UUID changed geometry hide new errors."""
    from collections import Counter
    def signature(row):
        value=dict(row)
        value['items']=sorted((dict(item) for item in row['items']),
                              key=lambda item:json.dumps(item,sort_keys=True))
        return json.dumps(value,sort_keys=True,separators=(',',':'))
    old=Counter(signature(v) for v in before['violations'] if v.get('severity')=='error')
    new=Counter(signature(v) for v in after['violations'] if v.get('severity')=='error')
    introduced=list((new-old).elements())
    return dict(ok=not introduced,introduced_error_geometry=sorted(introduced),
                scope='all_saved_native_error_rows_not_scorer_filtered')


def introduced_dangling_ids(before,after,source_ids,added_nodes,retired=()):
    """Exact saved native diagnostics only; never geometric guesses/source cuts."""
    from cec_stage_admission import _canonical_identity
    old={_canonical_identity(v) for v in before['violations']}
    selected=set()
    for row in after['violations']:
        if row['type']!='track_dangling' or _canonical_identity(row) in old:continue
        ids={item['uuid'] for item in row['items'] if item.get('uuid')}
        if (len(ids)!=1 or ids & set(source_ids) or not ids<=added_nodes.keys()
                or any(kind(added_nodes[u])!='segment' for u in ids)):
            raise ValueError('dangling_diagnostic_not_single_exact_new_track')
        selected.update(ids)
    if selected & set(retired) or len(selected|set(retired))>16:
        raise ValueError('finite_new_object_retirement_budget_exceeded')
    return selected


def require_cleanup_receiving(report, source_delta, current):
    """Persist both complete prechecks even when cleanup is refused."""
    report.setdefault('dangling_cleanup_prechecks', []).append(dict(
        source_delta=source_delta, current=current))
    if not all(p.get('ok') and p.get('complete') for p in (source_delta, current)):
        raise ValueError('pre_cleanup_source_or_current_replay_refused')


def preserve_refusal(proof,root,reason,*,max_bytes=64*1024*1024):
    """Retain bounded evidence under unmistakable UNADMITTED names, not output."""
    import shutil
    import uuid
    proof,root=Path(proof),Path(root)
    root.mkdir(parents=True,exist_ok=True)
    saved=root/('UNADMITTED-source-retaining-'+uuid.uuid4().hex)
    saved.mkdir()
    manifest=dict(ok=False,admitted=False,release_authority=False,reason=str(reason),
                  source_proof_directory=str(proof),files=[],omitted=[],byte_budget=max_bytes)
    remaining=max_bytes
    files=[p for p in proof.iterdir() if p.is_file() and p.suffix in ('.json','.log')]
    family=proof/'candidate'
    if family.is_dir():files.extend(p for p in family.iterdir() if p.is_file())
    for src in sorted(files):
        destination=(saved/'UNADMITTED-board-family'/src.name if src.parent==family else saved/src.name)
        limit=1024*1024 if src.suffix=='.log' else 32*1024*1024
        size=src.stat().st_size
        if src.is_symlink() or size>remaining or size>limit:
            manifest['omitted'].append(dict(path=str(src),size=size,reason='bounded_evidence_limit_or_alias'))
            continue
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(src,destination)
        if digest(src)!=digest(destination):raise ValueError('refusal_evidence_changed_during_copy')
        remaining-=size
        manifest['files'].append(dict(path=str(destination.relative_to(saved)),sha256=digest(destination),size=size))
    manifest['retained_bytes']=max_bytes-remaining
    (saved/'UNADMITTED.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return saved


def digest(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def children(text, *, root_end=False):
    """Direct S-expression children as exact spans; quoted/comment-safe."""
    depth = 0
    quoted = escaped = comment = False
    start = None
    spans = []
    end = None
    for i, c in enumerate(text):
        if comment:
            if c == '\n':
                comment = False
            continue
        if quoted:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
            continue
        if c == ';':
            comment = True
        elif c == '"':
            quoted = True
        elif c == '(':
            if depth == 1:
                start = i
            depth += 1
        elif c == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced_source')
            if depth == 1:
                spans.append((start, i + 1))
            if depth == 0:
                end = i
    if depth or quoted:
        raise ValueError('unbalanced_source')
    return end if root_end else spans


def kind(node):
    return re.match(r'\(\s*([^\s()]+)', node).group(1)


def node_uuid(node):
    for a, b in children(node):
        child = node[a:b]
        if kind(child) == 'uuid':
            return child.split(None, 1)[1].strip().rstrip(')').strip().strip('"')
    return None


def inventory(text):
    result = {}
    for a, b in children(text):
        uid = node_uuid(text[a:b])
        if uid:
            if uid in result:
                raise ValueError('ambiguous_native_uuid')
            result[uid] = (a, b)
    return result


def replace_fills(original, regenerated):
    """Retain all source zone bytes outside individual filled_polygon nodes."""
    spans = [(a, b) for a, b in children(original)
             if kind(original[a:b]) == 'filled_polygon']
    fills = [regenerated[a:b] for a, b in children(regenerated)
             if kind(regenerated[a:b]) == 'filled_polygon']
    insertion = spans[0][0] if spans else original.rfind(')')
    for a, b in reversed(spans):
        original = original[:a] + original[b:]
    return original[:insertion] + '\n'.join(fills) + original[insertion:]


def assemble(source_text, imported_text, retired=(), ground_text=None, ground_ids=()):
    old = inventory(source_text)
    new = inventory(imported_text)
    added = {u: imported_text[a:b] for u, (a, b) in new.items() if u not in old}
    retired = set(retired)
    if retired & set(old) or not retired <= set(added):
        raise ValueError('retirement_not_exact_new_copper')
    if any(kind(n) not in ('segment', 'via') for n in added.values()):
        raise ValueError('unsupported_new_node')
    result = source_text
    if ground_text is not None:
        ground = inventory(ground_text)
        for uid in sorted(ground_ids, key=lambda u: old[u][0], reverse=True):
            a, b = old[uid]
            x, y = ground[uid]
            result = result[:a] + replace_fills(source_text[a:b], ground_text[x:y]) + result[b:]
    # Keep the original root suffix, whitespace, unknown fields and comments.
    end = children(result, root_end=True)
    return result[:end] + '\n' + '\n'.join(n for u, n in added.items()
                                           if u not in retired) + '\n' + result[end:]


def retain_replay_source_nodes(stencil,regenerated,source_ids,ground_ids):
    """Independent replay retains approved original opaque nodes, not new nodes.

    New primitives remain the native serializer's result and must still compare
    exactly. Source/GND fields come from the validated source-plus-delta stencil;
    only native independently recomputed filled_polygon children are substituted.
    """
    old=inventory(stencil);new=inventory(regenerated)
    if not set(source_ids)<=old.keys() or not set(source_ids)<=new.keys():
        raise ValueError('native_replay_lost_source_uuid')
    result=regenerated
    for uid in sorted(source_ids,key=lambda u:new[u][0],reverse=True):
        a,b=new[uid];x,y=old[uid]
        retained=stencil[x:y]
        if uid in ground_ids:retained=replace_fills(retained,regenerated[a:b])
        result=result[:a]+retained+result[b:]
    return result


def raw_text(path):
    # Path.read_text normalizes CRLF; authority bytes must not be normalized.
    return Path(path).read_bytes().decode('utf-8')


def write_raw(path, text):
    Path(path).write_bytes(text.encode('utf-8'))


def assert_receipt_live(receipt, source, ses, board_hint, assembly_instance=None,trace_layer_scope=None):
    import cec_force_current as force
    import cec_synth_pipeline as synth
    import cec_native_drc_runner as native
    import cec_rated_trace_scope as trace_scope
    epoch = receipt['epoch']
    with force._thermal_hint(board_hint):
        family = force._family(source, board_hint)
    if (epoch['family'] != family
            or epoch['code'] != force._code_identity()
            or epoch['helper'] != digest(__file__)
            or epoch['ses'] != digest(ses)
            or any(digest(p) != h for p,h in epoch['inputs'].items())
            or epoch['params'] != json.loads(json.dumps(synth.Config.load(board_hint).params))
            or epoch.get('new_trace_scope') != trace_scope.bind_source(source,board_hint,trace_layer_scope)
            or epoch['assembly_instance'] != assembly_instance
            or epoch['assembly_identity'] != assembly_identity(source,assembly_instance)
            or epoch['native_tool'] != native._describe_build('/home/codex/.cache/cec/native-drc-10.0.5')):
        raise ValueError('publication_live_epoch_changed')
    trace_scope.assert_receipt(receipt,epoch.get('new_trace_scope'))


def route_once_operator(source, ses, output, *, board_hint,
                        expected_source_sha256, wall_s=120., native_s=10.,assembly_instance=None,
                        cleanup_dangling=False,diagnostics_root=None,
                        publication_guard=None,trace_layer_scope=None):
    """Optional route_once callback; default route_once never invokes this.

    Refuse pre-existing outputs, and copy all admitted family members without
    rewriting the board. Naming changes are content-exact, not new authority.
    """
    import cec_force_current as force
    import shutil
    import tempfile
    source, output = Path(source).resolve(), Path(output).resolve()
    if publication_guard is not None and not callable(publication_guard):
        raise ValueError('callable_live_publication_guard_required')
    if publication_guard is not None and publication_guard() is False:
        raise ValueError('live_publication_guard_refused')
    if output == source:
        raise ValueError('source_output_alias')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cec-ses-retain-',dir=output.parent) as private:
        try:
            receipt = import_retaining_source(source, ses, Path(private)/'proof',
                board_hint=board_hint, expected_source_sha256=expected_source_sha256,
                wall_s=wall_s, native_s=native_s,assembly_instance=assembly_instance,
                cleanup_dangling=cleanup_dangling,trace_layer_scope=trace_layer_scope)
            candidate = Path(receipt['candidate'])
            companions, _ = force._companion_inventory(candidate)
            copies=[(p,output.with_suffix(ext)) for ext,p in companions.items() if p.is_file()]
            def live_check():
                assert_receipt_live(receipt,source,ses,board_hint,assembly_instance,trace_layer_scope)
                if publication_guard is not None and publication_guard() is False:
                    raise ValueError('live_publication_guard_refused')
            return publish_transaction(receipt,candidate,output,copies,Path(private)/'proof',
                Path(private)/'publish',live_check)
        except Exception as exc:
            proof=Path(private)/'proof'
            if proof.is_dir():
                import traceback
                (proof/'operator-error.json').write_text(json.dumps(dict(ok=False,
                    release_authority=False,error=str(exc),traceback=traceback.format_exc()[-65536:]),indent=2)+'\n')
            saved=preserve_refusal(proof,diagnostics_root or output.parent/'source-retaining-diagnostics',exc) if proof.is_dir() else None
            raise ValueError('source_retaining_import_UNADMITTED: '+str(exc)+'; retained='+str(saved)) from exc


def publish_transaction(receipt,candidate,output,sidecars,proof_source,stage,live_check):
    """Stage everything, exclusively link board LAST; rollback exact own files.

    Never overwrite another writer, recursively delete a final directory, or
    remove a file whose inode/content changed after our exclusive creation.
    """
    import shutil
    output=Path(output);stage=Path(stage)
    # force._companion_inventory owns the entire '<board stem>.*' namespace.
    # Evidence must not look like a non-file saved-board sidecar.
    proof_dir=output.parent/('source-retaining-proof-'+output.stem)
    copies=[*sidecars,(Path(candidate),output)]
    targets=[dst for _,dst in copies]+[proof_dir]
    existing_family=any(p.name.startswith(output.stem+'.') for p in output.parent.iterdir())
    if (len(set(targets))!=len(targets) or existing_family
            or any(os.path.lexists(p) for p in targets)):
        raise ValueError('existing_publication_target_refused')
    stage.mkdir()
    prepared=[]
    for i,(src,dst) in enumerate(copies):
        staged=stage/str(i)
        shutil.copy2(src,staged)
        if digest(src)!=digest(staged):
            raise ValueError('staged_family_not_exact')
        prepared.append((staged,dst))
    staged_proof=stage/'proof'
    shutil.copytree(proof_source,staged_proof,
        ignore=shutil.ignore_patterns('scratch-import','candidate'))
    receipt=dict(receipt,candidate=str(output),proof_directory=str(proof_dir),
                 publication={str(dst):digest(src) for src,dst in prepared})
    (staged_proof/'published-receiving.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    owned=[];directories=[]
    def link(src,dst):
        st=src.stat();hashed=digest(src)
        os.link(src,dst)  # exclusive, unlike rename/replace on POSIX
        owned.append((dst,st.st_dev,st.st_ino,hashed))
    def directory(path):
        path.mkdir();st=path.stat();directories.append((path,st.st_dev,st.st_ino))
    try:
        live_check()
        for src,dst in prepared[:-1]:link(src,dst)
        directory(proof_dir)
        for src in sorted(staged_proof.rglob('*')):
            dst=proof_dir/src.relative_to(staged_proof)
            if src.is_dir():directory(dst)
            else:link(src,dst)
        live_check()
        link(*prepared[-1])  # board is the final publication marker
        live_check()
        return receipt
    except BaseException:
        for path,dev,ino,hashed in reversed(owned):
            try:
                st=path.lstat()
                if (st.st_dev,st.st_ino)==(dev,ino) and digest(path)==hashed:
                    path.unlink()
            except FileNotFoundError:pass
        for path,dev,ino in reversed(directories):
            try:
                st=path.lstat()
                if (st.st_dev,st.st_ino)==(dev,ino):path.rmdir()
            except OSError:pass
        raise


def canonical_rules(board, target, source):
    """Always rebuild from authority, Via then Endpoint, never append ancestry."""
    import cec_additive_route_receiving as receive
    src = Path(source).with_suffix('.kicad_dru')
    dst = Path(target).with_suffix('.kicad_dru')
    if src.exists():
        dst.write_bytes(src.read_bytes())
    elif dst.exists():
        dst.unlink()
    receive.bind_local_via_rule(board, target)
    receive.bind_local_endpoint_rule(board, target)


def import_retaining_source(source, ses, output_dir, *, board_hint,
                            wall_s=120., native_s=10., expected_source_sha256=None,
                            assembly_instance=None,cleanup_dangling=False,trace_layer_scope=None):
    """Explicit authority required; returns proof receipt, raises on refusal.

    Nothing is published to route_once's output until the caller checks ok.
    The receipt is diagnostic, not a reusable completed-net certificate.
    """
    if (not board_hint or not 0 < native_s <= 10 or not 0 < wall_s <= 300
            or type(cleanup_dangling) is not bool
            or not isinstance(expected_source_sha256, str)
            or not re.fullmatch('[0-9a-f]{64}', expected_source_sha256)):
        raise ValueError('explicit_authority_and_bounded_leases_required')
    import cec_rated_trace_scope as trace_scope
    trace_layer_scope=trace_scope.normalize(trace_layer_scope)
    # Resolve real current/profile authority before any worker output is created.
    trace_scope.bind_source(source,board_hint,trace_layer_scope)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    request = dict(source=str(Path(source).resolve()), ses=str(Path(ses).resolve()),
                   output_dir=str(output_dir), board_hint=board_hint,
                   assembly_instance=assembly_instance,
                   cleanup_dangling=cleanup_dangling,trace_layer_scope=trace_layer_scope,
                   native_s=native_s, expected_source_sha256=expected_source_sha256)
    request_path = output_dir / 'request.json'
    request_path.write_text(json.dumps(request))
    started = time.monotonic()
    with (output_dir / 'worker.log').open('w') as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    '--worker', str(request_path)],
                                   stdout=log, stderr=log, start_new_session=True)
        try:
            status = process.wait(timeout=wall_s)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise TimeoutError('source_retaining_import_whole_lease_expired')
    receipt = json.loads((output_dir / 'receiving.json').read_text())
    receipt['whole_elapsed_s'] = time.monotonic() - started
    if status or not receipt.get('ok'):
        raise ValueError('source_retaining_import_refused: ' + str(receipt.get('error')))
    return receipt


def _worker(request):
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet = wx.LogNull()
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_synth_pipeline as synth
    import cec_full_pipeline as pipeline
    import cec_additive_route_receiving as receive
    import cec_field_coupling as field
    import cec_native_drc_runner as native
    import cec_current_debt as debt
    import cec_score as score
    import cec_constraints as constraints
    import cec_rated_trace_scope as trace_scope
    from cec_stage_admission import native_geometry_nonregression
    source, ses, out = (Path(request[k]) for k in ('source', 'ses', 'output_dir'))
    key = request['board_hint']
    os.environ['CEC_THERMAL_BOARD_HINT'] = key
    cfg = synth.Config.load(key)
    if request['expected_source_sha256'] != digest(source):
        raise ValueError('explicit_source_epoch_mismatch')
    def epoch():
        return dict(family=force._family(source, key), code=force._code_identity(),
                    helper=digest(__file__), ses=digest(ses),
                    inputs={str(p): digest(p) for p in pipeline._source_files(cfg, source)},
                    params=json.loads(json.dumps(cfg.params)),
                    new_trace_scope=trace_scope.bind_source(source,key,request.get('trace_layer_scope')),
                    assembly_instance=request.get('assembly_instance'),
                    assembly_identity=assembly_identity(source,request.get('assembly_instance')),
                    native_tool=native._describe_build('/home/codex/.cache/cec/native-drc-10.0.5'))
    before = epoch()
    report = dict(ok=False, release_authority=False, completed_nets_grandfathered=[],
                  source=str(source), source_sha256=digest(source), epoch=before)
    started = time.monotonic()
    try:
        intake = pipeline._source_intake(cfg, source, out/'source-intake.json', allow_derived_input=True,
                                        assembly_instance=request.get('assembly_instance'))
        report['source_intake'] = intake
        require_intake(intake)
        source_native = out/'source-native.json'
        proof = native.run(source, source_native, reporting_build='/home/codex/.cache/cec/native-drc-10.0.5', timeout_s=request['native_s'],board_hint=request['board_hint'])
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('incomplete_source_native')
        before_drc = json.loads(source_native.read_text())
        before_metrics = score.score(str(source), drc_json=str(source_native))
        # Existing receiver owns source validation; no stale certificates accepted.
        raw = force._copy_family(source, out/'scratch-import')
        with synth._oracle_env(cfg.params):
            os.environ.pop('CEC_POURFIRST_STATE', None)
            for option in ('CEC_POWER_PICKUP','CEC_LASTMILE','CEC_LASTMILE_FINAL','CEC_ZONE_ISLAND_BRIDGE'):
                os.environ[option] = '0'
            fr.import_ses(str(source), str(ses), str(raw), kelvin_taps=False,
                          skip_locked_taps=True, power_pours=(), completed_nets=())
        report['import_elapsed_s'] = time.monotonic()-started
        raw_native = out/'import-native.json'
        proof = native.run(raw, raw_native, reporting_build='/home/codex/.cache/cec/native-drc-10.0.5', timeout_s=request['native_s'],board_hint=request['board_hint'])
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('incomplete_import_native')
        old = inventory(raw_text(source))
        added = set(inventory(raw_text(raw)))-set(old)
        faults = [v for v in json.loads(raw_native.read_text())['violations']
                  if v['severity']=='error' and v['type']=='track_width']
        retired = set()
        for row in faults:
            ids = {i['uuid'] for i in row['items'] if i.get('uuid')}
            if len(ids)!=1 or not ids <= added:
                raise ValueError('width_fault_not_single_new_copper')
            retired.update(ids)
        if len(retired)>16:
            raise ValueError('retirement_budget_exceeded')
        width_retired=set(retired)
        target = force._copy_family(source, out/'candidate')
        base = raw_text(source)
        imported=raw_text(raw)
        imported_spans=inventory(imported)
        added_nodes={u:imported[a:b] for u,(a,b) in imported_spans.items() if u in added}
        def rebuild():
            write_raw(target, assemble(base, imported, retired))
            board = pcbnew.LoadBoard(str(target))
            ground_ids = receive._ground_refill(board)
            field._save_field_snapshot(board, target)
            regenerated = raw_text(target)
            write_raw(target, assemble(base, imported, retired, regenerated, ground_ids))
            canonical_rules(pcbnew.LoadBoard(str(target)), target, source)
            return ground_ids
        ground_ids=rebuild()
        if request.get('assembly_instance') is not None:
            # Explicit child descriptor: retain exact peer/contract authority,
            # replace only this saved member, then rerun the physical gate.
            selected=json.loads(json.dumps(request['assembly_instance']))
            selected['members'][selected['role']]={'path':str(target),'sha256':digest(target)}
            candidate_intake=pipeline._source_intake(cfg,target,out/'candidate-intake.json',
                allow_derived_input=True,assembly_instance=selected)
            report['candidate_assembly_instance']=selected
            report['candidate_intake']=candidate_intake
            require_intake(candidate_intake)
        report['dangling_cleanup_rounds']=[]
        previous_opens=None
        for iteration in range(4):  # at most three finite cleanup rounds
            final_native=out/('native.json' if not iteration else 'native-cleanup-%d.json'%iteration)
            proof=native.run(target,final_native,reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=request['native_s'],board_hint=request['board_hint'])
            if not proof.get('ok') or not proof.get('complete'):raise ValueError('incomplete_final_native')
            drc=json.loads(final_native.read_text())
            if previous_opens is not None and len(drc['unconnected_items'])>previous_opens:
                raise ValueError('cleanup_increased_saved_native_opens')
            geometry=native_geometry_nonregression(before_drc,drc)
            report['native_geometry_nonregression']=geometry
            if geometry.get('ok') and geometry.get('complete'):break
            if (not request.get('cleanup_dangling') or iteration==3 or not geometry.get('complete')
                    or geometry.get('new_physical_fault_types')!=['track_dangling']):
                raise ValueError('raw_native_geometry_regressed')
            exact=introduced_dangling_ids(before_drc,drc,old,added_nodes,retired)
            if not exact:raise ValueError('no_exact_introduced_dangling_cleanup')
            pre_replay=receive.receive(source,target,timeout_s=request['native_s'],board_hint=key,allow_endpoint_neckdown_additions=True)
            pre_current=debt.receive(source,target,board_hint=key)
            require_cleanup_receiving(report,pre_replay,pre_current)
            report['dangling_cleanup_rounds'].append(dict(exact_retired_new_uuids=sorted(exact),
                before_native=str(final_native),before_source_replay=pre_replay,before_current=pre_current,
                before_raw_error_delta=raw_error_delta(before_drc,drc)))
            previous_opens=len(drc['unconnected_items']);retired.update(exact);ground_ids=rebuild()
        report['raw_native_error_delta']=raw_error_delta(before_drc,drc)
        if not report['raw_native_error_delta']['ok']:
            raise ValueError('raw_native_error_geometry_changed')
        metrics = score.score(str(target), drc_json=str(final_native))
        replay = receive.receive(source, target, timeout_s=request['native_s'], board_hint=key,
                                 allow_endpoint_neckdown_additions=True)
        current = debt.receive(source, target, board_hint=key)
        parity = constraints._chk_sch_pcb_sync(pcbnew.LoadBoard(str(target)),str(target),{'sch':cfg.sch})
        report.update(candidate=str(target), candidate_sha256=digest(target),
                      retired_width_fault_uuids=sorted(width_retired),
                      retired_dangling_uuids=sorted(retired-width_retired), ground_refilled=ground_ids,
                      independent_source_delta_replay=replay, current_debt=current, parity=parity,
                      metrics=dict(opens=len(drc['unconnected_items']), scored_drc=metrics.drc,
                                   native_errors=sum(v['severity']=='error' for v in drc['violations']),
                                   kelvin_ok=metrics.kelvin_ok, diffpair_ok=metrics.diffpair_ok))
        # Receiver schemas deliberately fail closed rather than infer authority.
        if not replay.get('ok') or not replay.get('complete'):
            raise ValueError('independent_source_delta_refused')
        if not current.get('ok') or not current.get('complete'):
            raise ValueError('current_debt_refused')
        if not parity[0]:
            raise ValueError('live_schematic_parity_refused')
        if metrics.drc > before_metrics.drc:
            raise ValueError('introduced_scored_native_faults')
        if len(drc['unconnected_items']) > len(before_drc['unconnected_items']):
            raise ValueError('connectivity_regressed')
        require_saved_route_craft(report,before_metrics,metrics)
        # Mandatory prepublication gate; no postcommit trace-scope refusal.
        report['new_trace_layer_receiving']=trace_scope.receive(source,target,
            board_hint=key,scope=request.get('trace_layer_scope'))
        if not report['new_trace_layer_receiving'].get('ok') or not report['new_trace_layer_receiving'].get('complete'):
            raise ValueError('introduced_track_layer_scope_refused')
        report['before_metrics'] = dict(opens=len(before_drc['unconnected_items']),scored_drc=before_metrics.drc)
        report['epoch_unchanged'] = before == epoch()
        if not report['epoch_unchanged']:
            raise ValueError('live_epoch_changed')
        report['ok'] = True
    except Exception as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
    finally:
        report['elapsed_s'] = time.monotonic()-started
        (out/'receiving.json').write_text(json.dumps(report, indent=2, default=str)+'\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.path.insert(0, str(scripts_directory(__file__)))
    sys.exit(_worker(json.loads(Path(sys.argv[2]).read_text())))
