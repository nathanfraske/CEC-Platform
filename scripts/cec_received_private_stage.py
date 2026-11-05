"""Bounded received private frontiers. Not wired to automatic waves yet.

No external callable, producer receipt or caller UUID whitelist is authority.
Failed families remain explicitly UNADMITTED; only publication.json exposes
a selected private artifact. No canonical/ledger file is ever modified.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))
def digest(value):return hashlib.sha256(json.dumps(stable(value),sort_keys=True).encode()).hexdigest()
def write(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,sort_keys=True,indent=2));os.replace(temporary,path)


def identity(source,hint,instance):
    import cec_force_current as force
    import cec_source_retaining_ses_import as retaining
    import cec_synth_pipeline as synth,cec_full_pipeline as pipeline
    import cec_native_library_context as libraries
    from cec_suite_source_audit_cache import SuiteSourceAuditCache
    cfg=synth.Config.load(hint)
    # Worker uses this explicit named-board hint. Include the SAME effective
    # environment in the parent's suite epoch without leaking it to callers.
    with force._thermal_hint(hint):
        suite_epoch=SuiteSourceAuditCache(pipeline.ROOT)._signature('generalization')
    return stable(dict(source=str(Path(source).resolve()),family=force._family(source,hint),
        code=force._code_identity(),assembly=retaining.assembly_identity(source,instance),
        params=cfg.params,source_authorities=pipeline._files_signature(pipeline._source_files(cfg,source)),
        native_library_authority=libraries.authority(source,Path(cfg.dir)/'fp-lib-table'),
        suite_source_code_policy_epoch=suite_epoch))


def matched_instance(instance,candidate):
    if instance is None:return None
    result=stable(instance)
    result['members'][result['role']]={'path':str(Path(candidate).resolve()),
        'sha256':hashlib.sha256(Path(candidate).read_bytes()).hexdigest()}
    return result


def admitted(gates):
    required={'operator','invariants','field','ground_returns','source_intake','candidate_intake',
        'parity','native','craft','source_live'}
    return set(gates)==required and all(value is True for value in gates.values())


def route_craft_delta(before,after):
    """Exact issue geometry/identity/multiplicity, not a count-only trade.

    Inherited advisory defects may remain while opens decrease, without
    qualifying them. Removing one old defect cannot pay for a different new
    reverse jog, arbitrary heading or other craft finding anywhere else.
    """
    from collections import Counter
    def inventory(report,key,count):
        rows=report.get(key);total=report.get(count)
        if (type(rows)is not list or type(total)is not int or total!=len(rows)
                or any(type(row)is not dict for row in rows)):
            raise ValueError('complete_saved_craft_inventory_required')
        return Counter(json.dumps(row,sort_keys=True,allow_nan=False)for row in rows)
    introduced={}
    for key,count in (('issues','issue_count'),('non_octilinear','non_octilinear_count')):
        old=inventory(before,key,count);new=inventory(after,key,count)
        introduced[key]=[json.loads(row)for row in sorted((new-old).elements())]
    return dict(ok=not any(introduced.values()),introduced_issues=introduced['issues'],
        introduced_non_octilinear=introduced['non_octilinear'],
        inherited_craft_qualified=False,exact_geometry_identity_and_multiplicity_checked=True)


def receiving_diagnostic(path):
    """Compact evidence from the saved worker report, never admission authority.

    A finite constructor refusal is not a native or electrical gate failure.
    Preserve that distinction without changing publish() or trusting a worker
    success flag. Unknown/missing gates remain unknown, not passed.
    """
    path=Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size>16*1024*1024:
        raise ValueError('bounded_saved_receiving_diagnostic_required')
    data=path.read_bytes();value=json.loads(data)
    if type(value)is not dict or type(value.get('gates'))is not dict:
        raise ValueError('saved_receiving_diagnostic_schema_required')
    gates=value['gates']
    if any(type(k)is not str or not k or len(k)>128 for k in gates):
        raise ValueError('saved_receiving_diagnostic_gate_name_required')
    reason=value.get('reason')
    if reason is not None and (type(reason)is not str or len(reason)>1024):
        raise ValueError('bounded_saved_receiving_reason_required')
    return dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),reason=reason,
        reported_gate_count=len(gates),failed_or_unknown_reported_gates=sorted(
            k for k,v in gates.items() if v is not True),
        complete_admission_gate_set_present=set(gates)=={
            'operator','invariants','field','ground_returns','source_intake','candidate_intake',
            'parity','native','craft','source_live'},admission_authority=False)


def native_findings_delta(before,after):
    """Every severity, exact native geometry and multiplicity; no scorer waiver.

    A complete ordinary join with an attached new dangling stub must not pass
    merely because track_dangling is a warning. Removing some old warnings
    does not pay for new ones. Native unconnected items are checked separately.
    """
    from collections import Counter
    def inventory(report):
        rows=report['violations']
        if type(rows) is not list:raise ValueError('complete_native_violation_inventory_required')
        result=Counter()
        for row in rows:
            if row.get('severity') not in ('error','warning'):
                raise ValueError('known_native_finding_severity_required')
            value=dict(row);value['items']=sorted((dict(item) for item in row['items']),
                key=lambda item:json.dumps(item,sort_keys=True))
            result[json.dumps(value,sort_keys=True,separators=(',',':'))]+=1
        return result
    old,new=inventory(before),inventory(after)
    introduced=sorted((new-old).elements())
    return dict(ok=not introduced,introduced_native_findings=introduced,
        scope='all_saved_native_errors_and_warnings_exact_geometry_and_multiplicity',
        inherited_findings_qualified=False)


def receive_field_transition(source,candidate,child,old,*,operator,operator_proof,board_hint):
    """An exact ordinary cut needs the actual-parent replacement field API.

    The additive API deliberately refuses missing inherited track IDs. Do
    not erase those IDs to fake an additive baseline: independently receive
    the typed cut again and compare the real original parent's field/fills.
    """
    import cec_field_coupling as field
    if operator=='ordinary_escape_corridor':
        return field.assess_native_ordinary_replacement(source,candidate,
            retired_track_uuids=operator_proof['retired_track_uuids'],board_hint=board_hint,timeout_s=10.)
    return field.assess_native_additions(child,old,board_path=str(candidate),board_hint=board_hint,timeout_s=10.)


def column_scope_receive(source,candidate,*,board_hint,net):
    """Saved native cuts only; publication still requires EVERY shared gate.

    Avoid nesting additive/current-debt replay inside the column's ten-second
    geometry lease. Those are independently performed by _invariant_worker
    below, under the stage's unchanged whole-process lease.
    """
    import pcbnew
    import cec_ordinary_power_columns as columns
    parent,child=[pcbnew.LoadBoard(str(p))for p in (source,candidate)]
    return columns.receive_native(parent,child,source=source,board_hint=board_hint,
                                  net=net,timeout_s=10.)


def require_native_tool(proof,expected):
    # cec_native_drc_runner.run returns this descriptor in reporting_build,
    # not in native report JSON or a caller-supplied engine label.
    if (proof.get('ok')is not True or proof.get('complete')is not True
            or proof.get('source_and_producer_unchanged')is not True
            or not expected or stable(proof.get('reporting_build'))!=stable(expected)):
        raise ValueError('native_tool_epoch_or_inventory_incomplete')


def receive_intakes(cfg,source,candidate,out,*,assembly_instance=None):
    """Reuse global SOURCE audits only. Both saved PCB intakes remain live."""
    import cec_full_pipeline as pipeline
    from cec_suite_source_audit_cache import SuiteSourceAuditCache
    session=SuiteSourceAuditCache(pipeline.ROOT)
    selected=matched_instance(assembly_instance,candidate);reports={}
    for name,path,instance in [('source',source,assembly_instance),('candidate',candidate,selected)]:
        reports[name+'_intake']=pipeline._source_intake(cfg,path,Path(out)/(name+'-intake.json'),
            allow_derived_input=True,assembly_instance=instance,suite_audit_cache=session)
    reports['suite_source_audit_cache']=session.evidence()
    return reports,session


def publish(receipt,publication,*,live):
    """Commit selection only after parent live checks, never infer missing gates."""
    if not admitted(receipt.get('gates',{})) or not live():
        return dict(ok=False,prefix_accepted=False,selected=None,release_authority=False,
                    reason='independent_gates_or_live_epoch_refused')
    result=dict(ok=True,prefix_accepted=True,selected=receipt['candidate'],
        candidate_sha256=receipt['candidate_sha256'],completed_nets=[],
        current_qualified=False,release_authority=False)
    path=Path(publication)
    if path.exists():raise ValueError('fresh_publication_namespace_required')
    write(path,result)
    try:
        if not live():raise ValueError('late_source_epoch_changed')
    except Exception:
        # Only remove this exact new unchanged receipt, never someone else's.
        if path.exists() and json.loads(path.read_text())==result:path.unlink()
        raise
    return result


def run(source,out,*,board_hint,expected_source_sha256,operator='ground',net=None,
        pad_uuid=None,assembly_instance=None,wall_s=120,native_s=10,max_successes=1):
    if (operator not in ('ground','ordinary_columns','ordinary_native_portals','ordinary_native_portfolio','ordinary_escape_corridor','quiet_signal','quiet_native_portals','measurement_input','distributed_supply','sensitive_scalar') or type(board_hint)is not str or not board_hint
            or type(wall_s)not in (int,float)or not math.isfinite(wall_s)or not 0<wall_s<=120
            or type(native_s)not in (int,float)or native_s!=10 or type(max_successes)is not int or max_successes!=1
            or operator in ('ordinary_columns','ordinary_native_portals','ordinary_native_portfolio','ordinary_escape_corridor','quiet_signal','quiet_native_portals','distributed_supply','sensitive_scalar')and(type(net)is not str or not net)
            or operator in ('ground','measurement_input')and net is not None
            or operator in ('measurement_input','ordinary_escape_corridor')and(type(pad_uuid)is not str or not pad_uuid)
            or operator=='ground' and pad_uuid is not None and(type(pad_uuid)is not str or not pad_uuid)
            or operator not in ('ground','measurement_input','ordinary_escape_corridor')and pad_uuid is not None):raise ValueError('explicit_bounded_received_operator_required')
    source=Path(source).resolve(strict=True);root=Path(out).resolve()
    if root==source.parent or source.parent in root.parents:raise ValueError('disjoint_output_namespace_required')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected_source_sha256:raise ValueError('expected_source_epoch_changed')
    before=identity(source,board_hint,assembly_instance)
    import cec_native_drc_runner as native
    native_profile=native._describe_build('/home/codex/.cache/cec/native-drc-10.0.5')
    request=stable(dict(source=str(source),board_hint=board_hint,expected_source_sha256=expected_source_sha256,
        operator=operator,net=net,pad_uuid=pad_uuid,assembly_instance=assembly_instance,native_s=native_s,max_successes=max_successes,
        wall_s=wall_s,identity=before,native_tool=native_profile,
        module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    key=digest(request);directory=root/key
    if directory.exists():
        cached=directory/'attempt.json'
        if cached.is_file():
            result=json.loads(cached.read_text())
            if result.get('key')==key and result.get('attempt_complete') is True and identity(source,board_hint,assembly_instance)==before:
                return dict(ok=False,prefix_accepted=False,selected=None,cached_attempt=True,
                    reason='exact_epoch_already_attempted',prior_receipt=str(cached),completed_nets=[])
        raise ValueError('unfinished_or_unfamiliar_operator_namespace')
    directory.mkdir(parents=True,exist_ok=False);request['directory']=str(directory)
    write(directory/'request.json',request)
    from cec_fr_bounded_transcript import Transcript
    transcript=Transcript(directory/'diagnostics');log_limit=transcript.limit
    import threading
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(directory/'request.json')],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    buffers=[bytearray(),bytearray()]
    def drain(stream,index):
        while True:
            chunk=stream.read(65536)
            if not chunk:break
            buffers[index].extend(chunk)
            if len(buffers[index])>log_limit:del buffers[index][log_limit//4:-3*log_limit//4]
    threads=[threading.Thread(target=drain,args=(stream,i),daemon=True)for i,stream in enumerate((process.stdout,process.stderr))]
    for thread in threads:thread.start()
    timeout=False
    try:process.wait(timeout=wall_s)
    except subprocess.TimeoutExpired:
        import signal
        timeout=True;os.killpg(process.pid,signal.SIGKILL);process.wait()
    for thread in threads:thread.join(timeout=12)
    transcript.capture(bytes(buffers[0]),bytes(buffers[1]));transcript.finish('timeout'if timeout else'completed',returncode=process.returncode)
    report=directory/'receiving.json';result=dict(ok=False,prefix_accepted=False,selected=None,completed_nets=[])
    if not timeout and process.returncode==0 and report.is_file():
        received=json.loads(report.read_text())
        def live():
            if identity(source,board_hint,assembly_instance)!=before:return False
            if native._describe_build('/home/codex/.cache/cec/native-drc-10.0.5')!=native_profile:return False
            if not received.get('candidate'):return False
            selected=matched_instance(assembly_instance,received['candidate'])
            return (identity(received['candidate'],board_hint,selected)==received.get('candidate_identity')
                and hashlib.sha256(Path(received['candidate']).read_bytes()).hexdigest()==received.get('candidate_sha256'))
        try:result=publish(received,directory/'publication.json',live=live)
        except Exception as exc:
            result=dict(ok=False,prefix_accepted=False,selected=None,completed_nets=[],
                        reason='publication_refused:'+type(exc).__name__+':'+str(exc))
    if report.is_file():
        try:result['receiving_diagnostic']=receiving_diagnostic(report)
        except (ValueError,TypeError,OSError,json.JSONDecodeError)as exc:
            result['receiving_diagnostic_error']=type(exc).__name__+':'+str(exc)
    result.update(key=key,attempt_complete=True,diagnostics=str(directory),whole_worker_timed_out=timeout)
    write(directory/'attempt.json',result);return result


def worker(request):
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    import pcbnew
    import cec_force_current as force,cec_synth_pipeline as synth,cec_full_pipeline as pipeline
    import cec_additive_pair_repair as additive,cec_source_retaining_ses_import as retaining
    import cec_native_drc_runner as native,cec_field_coupling as field
    import cec_ground_return_preservation as returns,cec_route_quality as quality,cec_constraints as constraints
    source=Path(request['source']);out=Path(request['directory']);hint=request['board_hint']
    os.environ['CEC_THERMAL_BOARD_HINT']=hint
    if identity(source,hint,request['assembly_instance'])!=request['identity']:raise ValueError('queued_source_epoch_changed')
    b=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in b.GetTracks()}
    attempts=[]
    if request['operator']=='ground':
        import cec_ground_component_join as tracks,cec_ground_mesh_entry as mesh
        import cec_ground_local_mesh_entry as local_mesh
        for module in (tracks,mesh,local_mesh):
            options={'obstacle_aware':True} if module is mesh else {}
            if request.get('pad_uuid') is not None:options['pad_uuid']=request['pad_uuid']
            plan=module.plan(b,board_hint=hint,timeout_s=10.,**options);attempts.append(dict(module=module.__name__,plan=plan))
            if plan.get('error'):return dict(gates={},reason='proposal_unknown',attempts=attempts)
            if plan.get('complete'):break
        else:return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        construct=lambda:module.construct_private(b,plan,board_hint=hint)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,timeout_s=10.)
    elif request['operator']=='distributed_supply':
        import cec_distributed_supply_stage as module
        plan=module.plan(b,source,board_hint=hint,net=request['net'],timeout_s=10.)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=force._copy_family(source,out/'UNADMITTED-family')
        construction=module.construct_private(source,candidate,plan,board_hint=hint,timeout_s=10.)
        attempts[-1]['construction']=construction
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,net=request['net'],timeout_s=10.)
    elif request['operator']=='ordinary_native_portfolio':
        import cec_native_portal_cpu_portfolio as portfolio
        import cec_ordinary_signal_completion as module
        construction=portfolio.construct(source,out/'UNADMITTED-cpu-portfolio',board_hint=hint,
            net=request['net'],maximum_lanes=7,max_workers=4,wall_s=min(40.,request['wall_s']*.4))
        attempts.append(dict(module=portfolio.__name__,construction=construction))
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=Path(construction['received_private_candidates'][0]['candidate'])
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,net=request['net'],timeout_s=10.)
    elif request['operator']=='ordinary_columns':
        import cec_ordinary_power_columns as module
        plan=module.plan(b,source=source,board_hint=hint,net=request['net'],timeout_s=10.)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        construct=lambda:module.construct_private(b,plan,source=source,board_hint=hint)
        receive=lambda candidate:column_scope_receive(source,candidate,board_hint=hint,net=request['net'])
    elif request['operator'] in ('quiet_signal','quiet_native_portals'):
        import cec_quiet_signal_completion as module
        plan=module.plan(b,source,board_hint=hint,net=request['net'],timeout_s=10.)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=force._copy_family(source,out/'UNADMITTED-family')
        strategy={'strategy':'native_portals'}if request['operator']=='quiet_native_portals'else{}
        construction=module.construct_private(source,candidate,plan,board_hint=hint,timeout_s=20.,**strategy)
        attempts[-1]['construction']=construction
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,net=request['net'],timeout_s=10.)
    elif request['operator']=='measurement_input':
        import cec_isolated_measurement_completion as module
        limits=dict(path_length_budget_nm=module.path_length_work_limit(
            request.get('path_length_budget_nm',module.MAX_PATH_LENGTH_NM)))
        plan=module.plan(b,source,board_hint=hint,pad_uuid=request['pad_uuid'],timeout_s=10.,**limits)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=force._copy_family(source,out/'UNADMITTED-family')
        construction=module.construct_private(source,candidate,plan,board_hint=hint,timeout_s=20.,**limits)
        attempts[-1]['construction']=construction
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,pad_uuid=request['pad_uuid'],timeout_s=10.,**limits)
    elif request['operator'] in ('ordinary_native_portals','sensitive_scalar'):
        if request['operator']=='ordinary_native_portals':
            import cec_ordinary_signal_completion as module
        else:
            import cec_sensitive_scalar_completion as module
        plan=module.plan(b,source,board_hint=hint,net=request['net'],timeout_s=10.)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=force._copy_family(source,out/'UNADMITTED-family')
        construction=module.construct_private(source,candidate,plan,board_hint=hint,timeout_s=20.)
        attempts[-1]['construction']=construction
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,net=request['net'],timeout_s=10.)
    elif request['operator']=='ordinary_escape_corridor':
        import cec_ordinary_escape_corridor as module
        plan=module.plan(b,source,board_hint=hint,net=request['net'],pad_uuid=request['pad_uuid'],timeout_s=10.)
        attempts.append(dict(module=module.__name__,plan=plan))
        if not plan.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        candidate=force._copy_family(source,out/'UNADMITTED-family')
        construction=module.construct_private(source,candidate,plan['offers'][0],board_hint=hint,timeout_s=40.)
        attempts[-1]['construction']=construction
        if not construction.get('complete'):return dict(gates={},reason='finite_proposal_incomplete',attempts=attempts)
        receive=lambda candidate:module.receive(source,candidate,board_hint=hint,net=request['net'],
            pad_uuid=request['pad_uuid'],timeout_s=10.)
    else:raise ValueError('unknown_received_private_worker_operator')
    if request['operator'] not in ('quiet_signal','quiet_native_portals','measurement_input','ordinary_native_portals','ordinary_native_portfolio','ordinary_escape_corridor','distributed_supply','sensitive_scalar'):
        construct();candidate=force._copy_family(source,out/'UNADMITTED-family')
        additive.save_native_additions(candidate,b,{},old,board_hint=hint)
    layout=dict(scope_receiver={'ordinary_columns':'column_saved_native_cuts',
        'ground':'ground_saved_operator','quiet_signal':'source_typed_quiet_saved_native_join',
        'quiet_native_portals':'source_typed_quiet_saved_native_join',
        'ordinary_native_portals':'source_typed_ordinary_saved_native_join',
        'ordinary_native_portfolio':'source_typed_ordinary_saved_native_join',
        'distributed_supply':'source_qualified_aggregate_supply_saved_native_join',
        'sensitive_scalar':'source_typed_sensitive_scalar_saved_native_join',
        'ordinary_escape_corridor':'source_typed_atomic_ordinary_corridor_join',
        'measurement_input':'source_typed_isolated_measurement_saved_native_join'}[request['operator']],
        scope_timeout_s=10.,whole_worker_lease_s=request['wall_s'],
        mandatory_shared_receivers=['invariants','field','ground_returns','source_intake',
            'candidate_intake','parity','native','craft','source_live'],
        invariants_independently_include=['exact_native_source_delta','qualified_pair_prefix',
            'exact_object_rule_replay','current_debt_nonregression'],
        scope_receipt_alone_never_admits=True)
    reports=dict(attempts=attempts,receiving_layout=layout,operator=receive(candidate))
    if not reports['operator'].get('ok') or not reports['operator'].get('complete'):
        return dict(gates={},reports=reports,reason='operator_saved_receiver_refused')
    if request['operator']=='ground' and request.get('pad_uuid') is not None:
        import cec_ground_component_join as target_ground
        reports['ground_target']=target_ground.receive_target(source,candidate,board_hint=hint,
            pad_uuid=request['pad_uuid'],timeout_s=10.)
        if reports['ground_target'].get('ok') is not True:
            return dict(gates={},reports=reports,reason='targeted_saved_merge_refused')
    reports['invariants']=(module.invariants(source,candidate,board_hint=hint)
        if request['operator']=='ordinary_escape_corridor' else additive._invariant_worker(source,candidate))
    if reports['invariants'].get('ok')is not True:
        return dict(gates={},reports=reports,reason='source_current_replay_refused')
    child=pcbnew.LoadBoard(str(candidate));parent=pcbnew.LoadBoard(str(source))
    reports['field']=receive_field_transition(source,candidate,child,old,operator=request['operator'],
        operator_proof=reports['operator'],board_hint=hint)
    reports['ground_returns']=returns.receive(parent,child,timeout_s=10.)
    cfg=synth.Config.load(hint);selected=matched_instance(request['assembly_instance'],candidate)
    gates={name:reports[name].get('ok')is True and reports[name].get('complete',name=='invariants')is True
           for name in ('operator','invariants','field','ground_returns')}
    intake_reports,intake_session=receive_intakes(cfg,source,candidate,out,assembly_instance=request['assembly_instance'])
    reports.update(intake_reports)
    for name,path in [('source',source),('candidate',candidate)]:
        intake=reports[name+'_intake']
        gates[name+'_intake']=intake.get('ok')is True and intake.get('intake',{}).get('ok')is True
        proof=native.run(path,out/(name+'-native.json'),reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,board_hint=hint)
        reports.setdefault('native_producers',{})[name]=proof
        try:
            require_native_tool(proof,request['native_tool'])
        except ValueError:
            # Preserve every already computed real phase and the FAILED
            # producer's diagnostic instead of discarding the fail stack in
            # the outer exception handler. Partial gates never publish.
            gates['native']=False
            return dict(gates=gates,reports=reports,
                reason='native_producer_refused:'+name,candidate=str(candidate),
                candidate_sha256=force._hash(candidate),
                current_qualified=False,release_authority=False)
        context=proof.get('native_library_context',{})
        if (context.get('bound')is not True or context.get('source_and_context_unchanged')is not True
                or stable(context.get('authority'))!=request['identity']['native_library_authority']):
            raise ValueError('native_library_authority_differs_from_received_stage_epoch')
    before=json.loads((out/'source-native.json').read_text());after=json.loads((out/'candidate-native.json').read_text())
    reports['raw_errors']=retaining.raw_error_delta(before,after)
    reports['all_native_findings']=native_findings_delta(before,after)
    gates['native']=(reports['raw_errors']['ok']is True and reports['all_native_findings']['ok']is True
        and not before.get('excluded_violations',[]) and not after.get('excluded_violations',[])
        and not any(v.get('severity')=='error'for v in after['violations'])
        and len(after['unconnected_items'])<len(before['unconnected_items']))
    reports['parity']=constraints._chk_sch_pcb_sync(child,str(candidate),{'sch':str(cfg.sch)})
    gates['parity']=reports['parity'][0]is True
    craft=[quality.analyze_board(x)for x in (parent,child)]
    craft_delta=route_craft_delta(*craft)
    reports['route_craft']=dict(source=craft[0],candidate=craft[1],
        **craft_delta,
        actual_saved_boards_observed=True,findings_suppressed=False,
        counts_are_not_inherited_craft_qualification=True)
    gates['craft']=craft_delta['ok'] is True
    gates['source_live']=identity(source,hint,request['assembly_instance'])==request['identity']
    reports['suite_source_audit_cache']=intake_session.evidence()
    return dict(gates=gates,reports=reports,candidate=str(candidate),candidate_sha256=force._hash(candidate),
        candidate_identity=identity(candidate,hint,selected),
        candidate_assembly_instance=selected,current_qualified=False,release_authority=False)


if __name__=='__main__':
    import traceback
    request=json.loads(Path(sys.argv[2]).read_text())
    try:result=worker(request)
    except Exception:result=dict(gates={},error=traceback.format_exc())
    write(Path(request['directory'])/'receiving.json',result)
