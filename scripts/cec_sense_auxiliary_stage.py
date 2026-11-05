"""Saved, source-typed package straps before ordinary net scheduling.

Only literal manufacturer-declared same-net input straps are admitted. This
does not complete a force net, allocate branch current, or qualify Kelvin.
"""
import json
import math
import os
from pathlib import Path
import time


def receive_straps(source, candidate, *, timeout_s=10.):
    """Independently own ALL new copper as isolated literal package straps.

    The existing native auxiliary classifier checks manufacturer/package/pins,
    exact source nets, short straight geometry and every unowned same-net
    interior contact. A producer's claimed UUID list is never authority.
    Full source replay, current, native DRC and parity are separate gates.
    """
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_auxiliary_receiving_required')
    import pcbnew
    import cec_force_current as force
    import cec_pair_semantics as semantics
    import cec_sense_auxiliary as auxiliary
    import cec_measurement_auxiliary_cut as isolation
    import cec_measurement_terminal_access as access
    import cec_device_power_roles as roles
    import cec_cell_row_rebuild as row
    deadline=time.monotonic()+timeout_s
    parent,child=[pcbnew.LoadBoard(str(p))for p in (source,candidate)]
    binding=[row._source_binding(b)for b in (parent,child)]
    old={force._uid(t)for t in parent.GetTracks()}
    tracks={force._uid(t):t for t in child.GetTracks()}
    incoming=set(tracks)-old
    if not 1<=len(incoming)<=64 or any(tracks[u].GetClass()!='PCB_TRACK' for u in incoming):
        raise ValueError('bounded_new_track_only_auxiliary_delta_required')
    owned=set();proofs=[];graphs={}
    for fp in parent.GetFootprints():
        if time.monotonic()>=deadline:raise ValueError('auxiliary_receiving_deadline')
        paired=semantics.footprint_input_contract(fp)
        declared=semantics.current_auxiliary_input_contract(paired[0])if paired else None
        if not declared:continue
        for a_pin,b_pin,*_roles in declared[1]:
            aa=[p for p in fp.Pads()if p.GetNumber()==a_pin]
            bb=[p for p in fp.Pads()if p.GetNumber()==b_pin]
            if len(aa)!=1 or len(bb)!=1:continue
            a,b=aa[0],bb[0]
            if not a.GetNetname()or a.GetNetname()!=b.GetNetname():continue
            net=a.GetNetname()
            if net not in graphs:graphs[net]=auxiliary.native_contact_graph(parent,net,deadline=deadline)
            if auxiliary.reached(graphs[net],a,b,deadline=deadline):continue
            model=roles.footprint_contract(fp)
            if not model:continue
            # Neither endpoint may be an existing alternate force pickup.
            # Even contact *inside* that endpoint land would bypass the
            # separately required Kelvin departure if it already fed a bus.
            if any(access._input_island(p,list({force._uid(i):i for i in
                    [p,*graphs[net].GetConnectedItems(p)]}.values()),model,
                    deadline=deadline)is None for p in (a,b)):
                continue
            try:
                proof=isolation.plan(child,force._uid(b),timeout_s=max(.001,deadline-time.monotonic()))
            except ValueError:
                continue  # Unchanged unresolved pairs confer no incoming scope.
            ids=set(proof['track_uuids'])
            if (not ids or not ids<=incoming or ids&owned
                    or proof['boundary_uuids']!=[force._uid(a)]
                    or proof['net']!=net or proof['auxiliary_pin']!=a_pin
                    or proof['paired_input_pin']!=b_pin):
                raise ValueError('exact_source_pending_auxiliary_scope_required')
            owned.update(ids);proofs.append(proof)
    if owned!=incoming:raise ValueError('unowned_auxiliary_copper_or_force_pickup')
    if binding!=[row._source_binding(b)for b in (parent,child)]:
        raise ValueError('auxiliary_receiving_mutated_native_boards')
    return dict(ok=True,complete=True,proofs=proofs,owned_new_track_uuids=sorted(owned),
        current_authority=False,kelvin_qualified=False,release_authority=False,
        no_unowned_same_net_interior_contacts=True,
        source_ends_stranded_manufacturer_input_copper=True,
        independent_full_source_native_current_and_parity_still_required=True)


def _receive_full(source,candidate,board_hint,directory):
    """Persist completed gates and the full fail stack even on refusal."""
    import cec_force_current as force
    directory=Path(directory);directory.mkdir(exist_ok=False)
    report=dict(ok=False,release_authority=False,current_qualified=False,kelvin_qualified=False)
    try:
        return _receive_full_checks(source,candidate,board_hint,directory,report)
    except Exception as exc:
        import traceback
        report.update(ok=False,error=repr(exc),traceback=traceback.format_exc())
        raise
    finally:
        force._write(directory/'receiving.json',report)


def _receive_full_checks(source,candidate,board_hint,directory,report):
    import pcbnew
    import cec_force_current as force
    import cec_synth_pipeline as synth
    import cec_full_pipeline as pipeline
    import cec_constraints as constraints
    import cec_additive_pair_repair as additive
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    import cec_source_retaining_ses_import as retaining
    family=[force._family(p,board_hint)for p in (source,candidate)]
    code=force._code_identity();cfg=synth.Config.load(board_hint)
    report['source_typed_auxiliary_isolation']=receive_straps(source,candidate)
    report['invariants']=additive._invariant_worker(str(source),str(candidate))
    import cec_ordinary_route_receiving as ordinary
    parent,child=[pcbnew.LoadBoard(str(p))for p in (source,candidate)]
    partition_deadline=time.monotonic()+10.
    before_parts=ordinary._partition(parent,partition_deadline)
    retained=set().union(*before_parts)
    after_parts=ordinary._partition(child,partition_deadline,retained_keys=retained)
    lost=[part for part in before_parts if not any(part<=other for other in after_parts)]
    report['source_native_partitions']=dict(ok=not lost,source_partitions=len(before_parts),
        lost_source_partitions=len(lost),scope='all_retained_native_lands_and_conductors_not_current_rating')
    for name,path in (('source',source),('candidate',candidate)):
        report[name+'_intake']=pipeline._source_intake(cfg,path,directory/(name+'-intake.json'),allow_derived_input=True)
        retaining.require_intake(report[name+'_intake'])
        producer=native.run(path,directory/(name+'-native.json'),timeout_s=10.,
            reporting_build=os.environ.get('CEC_NATIVE_DRC_REPORTING_BUILD',str(Path.home()/'.cache/cec/native-drc-10.0.5')))
        if not producer['ok']or not producer['complete']:raise ValueError('incomplete_auxiliary_native_report')
        report[name+'_native_tool']=producer
    before,after=[json.loads((directory/(name+'-native.json')).read_text())for name in ('source','candidate')]
    report['native_geometry']=admission.native_geometry_nonregression(before,after)
    report['raw_native_error_delta']=retaining.raw_error_delta(before,after)
    report['parity']=constraints._chk_sch_pcb_sync(pcbnew.LoadBoard(str(candidate)),str(candidate),{'sch':str(cfg.sch)})
    report['source_opens']=len(before['unconnected_items']);report['opens']=len(after['unconnected_items'])
    report['strict_native_improvement']=report['opens']<report['source_opens']
    report['source_candidate_and_code_unchanged']=(family==[force._family(p,board_hint)for p in (source,candidate)]and code==force._code_identity())
    report['ok']=all((report['source_typed_auxiliary_isolation']['ok'],report['invariants']['ok'],
        report['native_geometry']['ok'],report['native_geometry']['complete'],report['raw_native_error_delta']['ok'],
        report['parity'][0],report['strict_native_improvement'],report['source_candidate_and_code_unchanged'],
        report['source_native_partitions']['ok']))
    report['candidate_sha256']=force._hash(candidate)
    return report


def _worker_impl(source,board_hint,directory,search_s):
    import pcbnew
    import cec_force_current as force
    import cec_sense_auxiliary as auxiliary
    import cec_additive_pair_repair as additive
    source,directory=Path(source),Path(directory)
    report=dict(ok=True,prefix_accepted=False,selected=str(source),completed_nets=[],
        current_qualified=False,kelvin_qualified=False,release_authority=False)
    with force._thermal_hint(board_hint):
        board=pcbnew.LoadBoard(str(source))
        original={force._uid(t)for t in board.GetTracks()}
        report['construction']=auxiliary.construct(board,board_path=str(source),timeout_s=search_s,
            require_source_isolated=True)
        if report['construction'].get('refused'):
            report.update(ok=False,status='construction_refused')
            return report  # No partial failed batch may be saved or promoted.
        if not report['construction']['generated_item_count']:
            refused=bool(report['construction'].get('refused'))
            report.update(ok=not refused,status='construction_refused' if refused else 'no_op')
            return report
        candidate=force._copy_family(source,directory/'candidate')
        report['finalized']=additive.save_native_additions(candidate,board,{},original,board_hint=board_hint)
        report['receiving']=_receive_full(source,candidate,board_hint,directory/'checks')
        if report['receiving']['ok']:
            report.update(status='received_improvement',prefix_accepted=True,selected=str(candidate),board_sha256=force._hash(candidate),
                source_opens=report['receiving']['source_opens'],opens=report['receiving']['opens'])
        else:report['ok']=False
    return report


def _worker(source,board_hint,directory,search_s):
    import cec_force_current as force
    try:
        report=_worker_impl(source,board_hint,directory,search_s)
    except Exception as exc:
        import traceback
        report=dict(ok=False,prefix_accepted=False,selected=str(source),completed_nets=[],
            error=repr(exc),traceback=traceback.format_exc(),
            unadmitted_directory=str(directory),release_authority=False)
    force._write(Path(directory)/'worker-receiving.json',report)
    return report


def run(source,directory,*,board_hint,source_sha256,search_s=10.):
    """One isolated <=120 s attempt; never rewrite source or mark a net done."""
    if (type(search_s)not in (int,float)or not math.isfinite(search_s)or not 0<search_s<=10
            or type(board_hint)is not str or not board_hint):
        raise ValueError('bounded_source_auxiliary_stage_required')
    import cec_force_current as force
    import cec_certificate_repair as repair
    source,directory=Path(source).resolve(),Path(directory).resolve()
    force._check_proposal_directory(directory,force._protected_paths(source,board_hint))
    if directory.exists()or force._hash(source)!=source_sha256:
        raise ValueError('fresh_auxiliary_output_and_exact_source_required')
    family=force._family(source,board_hint);code=force._code_identity()
    directory.mkdir(parents=True)
    report=dict(ok=False,prefix_accepted=False,selected=str(source),completed_nets=[],
        source=str(source),source_sha256=source_sha256,release_authority=False)
    try:
        report.update(repair._spawn_apply(_worker,(str(source),board_hint,str(directory),search_s),
            timeout_s=120.,search_budget_arg=3))
    except Exception as exc:
        import traceback
        report.update(ok=False,prefix_accepted=False,selected=str(source),error=repr(exc),
            traceback=traceback.format_exc(),worker_failure_evidence=getattr(exc,'certificate_worker_diagnostics',None))
    report['source_and_code_unchanged']=family==force._family(source,board_hint)and code==force._code_identity()
    if not report['source_and_code_unchanged']:
        report.update(ok=False,prefix_accepted=False,selected=str(source))
    force._write(directory/'receiving.json',report)
    return report
