"""Atomic, exact cleanup of newly exposed ordinary tails after reconstruction.

Macro routing can reattach a retained component through a different port and
leave its OLD terminal-free lead behind. A native dangling warning is only a
hint: derive the whole ordinary leaf chain, forbid track locks/groups, then
require independent saved cut-only receiving. This local prefix is never a
new admission baseline. The caller must still compare the final result to
the ORIGINAL macro source, preserving every surviving partition and gate.
An obsolete two-face routing barrel needs its own positive ownership proof
and explicit source-lock retirement authority, never a general via waiver.
"""
import math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_stage_admission as stage
import cec_ordinary_tail_discovery as tails
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_field_coupling as field
from cec_native_items import discard_items


def new_warning_ids(original,proposed):
    def rows(report):
        if (type(report) is not dict or type(report.get('violations')) is not list
                or len(report['violations'])>20000):raise ValueError('bounded_original_and_proposed_native_reports_required')
        for row in report['violations']:
            if (type(row) is not dict or type(row.get('type')) is not str or not row['type']
                    or type(row.get('items')) is not list or not 1<=len(row['items'])<=16
                    or any(type(i) is not dict or type(i.get('uuid')) is not str or not i['uuid'] for i in row['items'])):
                raise ValueError('literal_native_macro_warning_identity_required')
        return report['violations']
    old={stage._canonical_identity(row) for row in rows(original)}
    result=sorted({row['items'][0]['uuid'] for row in rows(proposed)
        if row['type']=='track_dangling' and len(row['items'])==1 and stage._canonical_identity(row) not in old})
    if len(result)>32:raise ValueError('new_native_macro_tail_work_bound')
    return result


def _single_construct(source,outdir,*,board_hint,original_native,proposed_native,timeout_s=10.,
              allow_locked_obsolete_port_vias=False,allow_locked_obsolete_track_uuids=()):
    started=time.monotonic();result=dict(schema=1,scope='new_native_ordinary_macro_tail_cleanup',
        ok=False,complete=False,changed=False,errors=[],candidate=None,release_authority=False,
        original_macro_source_receiving_still_required=True,inherited_native_faults_not_suppressed=True)
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
                or type(board_hint) is not str or not board_hint
                or type(allow_locked_obsolete_port_vias) is not bool):raise ValueError('bounded_macro_tail_receiving_context_required')
        source=Path(source).resolve();outdir=Path(outdir)
        permitted_locks=ordinary._ids(allow_locked_obsolete_track_uuids,'macro_tail_locked_track_scope',32)
        if not source.is_file() or source.suffix!='.kicad_pcb':raise ValueError('saved_native_macro_tail_source_required')
        if outdir.exists():raise ValueError('fresh_private_macro_tail_output_required')
        family=force._family(source,board_hint);epoch=force._code_identity()
        warnings=new_warning_ids(original_native,proposed_native);result['new_warning_uuids']=warnings
        if not warnings:
            result.update(ok=True,complete=True);return result
        board=pcbnew.LoadBoard(str(source))
        discovery=tails.discover(board,source,board_hint,warnings,timeout_s=timeout_s)
        result['source_native_leaf_chain_discovery']=discovery
        retired=discovery['proposed_exact_track_uuids']
        if not discovery['complete'] or not retired:raise ValueError('no_positive_source_ordinary_macro_tail')
        live={force._uid(t):t for t in board.GetTracks()}
        if not permitted_locks<=live.keys() or any(live[u].GetClass()!='PCB_TRACK' for u in permitted_locks):
            raise ValueError('exact_source_macro_tail_track_lock_scope_required')
        if any(live[u].IsLocked() and u not in permitted_locks or live[u].GetParentGroup() is not None
                or any(g.ContainsItem(live[u]) for g in board.Groups()) for u in retired):
            raise ValueError('macro_tail_source_lock_or_group_requires_separate_authority')
        locked_tracks=sorted(u for u in retired if live[u].IsLocked())
        # Retiring an old layer exit can make its routing barrel obsolete.
        # Prove the compound cut against the SAME pre-cut prefix, rather than
        # deleting a track, promoting that intermediate, then chasing the via
        # warning. Never prune an already single-face source hole/test point.
        port_vias=[];port_proofs=[];locked_vias=[];grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
        positive=ordinary.eligible_nets(board,source,board_hint);retired_set=set(retired)
        for via in board.GetTracks():
            if (via.GetClass()!='PCB_VIA' or str(via.GetNetname()) not in positive
                    or force._uid(via) in grouped):continue
            exits={int(live[u].GetLayer()) for u in retired if live[u].GetNetCode()==via.GetNetCode()
                and via.IsOnLayer(live[u].GetLayer()) and via.GetEffectiveShape(live[u].GetLayer()).Collide(
                    live[u].GetEffectiveShape(live[u].GetLayer()),0)}
            if not exits:continue
            uid=force._uid(via)
            try:
                ownership=ordinary._redundant_single_face_vias(board,{uid},retired_tracks=retired_set,
                    nets=positive,unlock={uid} if via.IsLocked() else set(),deadline=started+timeout_s)
            except ValueError:continue
            before_faces=exits|set(ownership[0]['retained_contact_layers'])
            if len(before_faces)<2:continue
            if via.IsLocked() and not allow_locked_obsolete_port_vias:
                raise ValueError('obsolete_routing_port_requires_exact_source_lock_retirement_authority')
            port_vias.append(uid)
            if via.IsLocked():locked_vias.append(uid)
            port_proofs.append(dict(via_uuid=uid,source_actual_contact_faces=sorted(before_faces),
                post_cut_single_face_receiving=ownership[0],source_locked=bool(via.IsLocked())))
            if len(port_vias)>4:raise ValueError('macro_tail_obsolete_routing_port_bound')
        # A routing port can contain a tiny source-authored stem joining its
        # exact centre to the retained junction. Derive those from actual
        # native via lands, then independently discover the terminal-free
        # chain on a PRIVATE in-memory post-cut board. Do this before saving
        # the one compound delta, not through a warning-chasing loop.
        stem_candidates=[];stem_witnesses=[]
        for uid,item in live.items():
            if (uid in retired_set or item.GetClass()!='PCB_TRACK' or item.IsLocked()
                    or uid in grouped or str(item.GetNetname()) not in positive
                    or not 0<item.GetWidth()<500000):continue
            for port in port_vias:
                via=live[port]
                if item.GetNetCode()!=via.GetNetCode() or not via.IsOnLayer(item.GetLayer()):continue
                radius=int(via.GetWidth(via.TopLayer()))//2-(int(item.GetWidth())+1)//2-force.SURFACE_CONTACT_INSET_NM
                centre=tuple(via.GetPosition())
                if (radius>0 and all(sum((x-y)**2 for x,y in zip(point,centre))<=radius*radius
                        for point in (tuple(item.GetStart()),tuple(item.GetEnd())))):
                    stem_candidates.append(uid);stem_witnesses.append(dict(track_uuid=uid,retired_port_via_uuid=port,
                        entire_original_capsule_inside_original_via_land=True,
                        contact_inset_nm=force.SURFACE_CONTACT_INSET_NM));break
        if len(stem_candidates)>8:raise ValueError('source_port_subsumed_stem_work_bound')
        if stem_candidates:
            probe=pcbnew.LoadBoard(str(source));discard_items(probe,[t for t in probe.GetTracks()
                if force._uid(t) in retired_set|set(port_vias)])
            stem_hint=tails.discover(probe,source,board_hint,stem_candidates,
                timeout_s=max(.001,timeout_s-(time.monotonic()-started)))
            result['private_post_cut_subsumed_stem_discovery']=stem_hint
            # A longer attached branch or a real load is not covered by this
            # narrow land-subsumed extension. It remains a separate refusal.
            if not stem_hint['complete'] or not set(stem_hint['proposed_exact_track_uuids'])<=set(stem_candidates):
                raise ValueError('subsumed_port_stem_is_not_an_independently_derived_local_leaf')
            selected_stems=set(stem_hint['proposed_exact_track_uuids'])
            retired=sorted(retired_set|selected_stems)
            result['source_subsumed_port_stem_witnesses']=[w for w in stem_witnesses if w['track_uuid'] in selected_stems]
        child=force._copy_family(source,outdir)
        discard_items(board,[live[u] for u in [*retired,*port_vias]]);additive._ground_refill(board)
        field._save_field_snapshot(board,child)
        result.update(candidate=str(child),candidate_sha256=force._hash(child),retired_track_uuids=retired,
            retired_via_uuids=sorted(port_vias),locked_via_scope_used=sorted(locked_vias),
            locked_track_scope_used=locked_tracks,
            original_two_face_port_retirement_witnesses=port_proofs)
        remaining=timeout_s-(time.monotonic()-started)
        if remaining<=0:raise ValueError('native_macro_tail_deadline')
        proof=ordinary.receive(source,child,board_hint=board_hint,retired_track_uuids=retired,
            allow_locked_track_uuids=locked_tracks,
            redundant_single_face_via_uuids=sorted(port_vias),allow_locked_via_uuids=sorted(locked_vias),
            allow_redundant_cut_only=True,timeout_s=remaining)
        result['independent_saved_ordinary_cut_receiving']=proof
        if not proof['ok'] or not proof['complete']:
            raise ValueError('native_macro_tail_exact_cut_receiving_refused:'+str(proof['errors']))
        if family!=force._family(source,board_hint) or epoch!=force._code_identity():
            raise ValueError('native_macro_tail_source_or_code_changed')
        result.update(ok=True,complete=True,changed=True,source=str(source),source_sha256=force._hash(source),
            code_identity=epoch,source_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result


def construct(source,outdir,*,board_hint,original_native,proposed_native,timeout_s=10.,
              allow_locked_obsolete_port_vias=False,native_grade=None,allow_locked_obsolete_track_uuids=()):
    """Close a bounded native warning cascade against ONE immutable prefix.

    Each pass must remove new source-owned ordinary copper. Intermediate
    reports guide discovery, never become an admission baseline. Final
    receiving replays the UNION of cuts against the original prefix in one
    exact transaction. At most four passes/32 tracks/four barrels are allowed.
    """
    if native_grade is None:
        return _single_construct(source,outdir,board_hint=board_hint,original_native=original_native,
            proposed_native=proposed_native,timeout_s=timeout_s,
            allow_locked_obsolete_port_vias=allow_locked_obsolete_port_vias,
            allow_locked_obsolete_track_uuids=allow_locked_obsolete_track_uuids)
    result=dict(schema=1,scope='bounded_whole_original_native_macro_tail_closure',ok=False,complete=False,
        changed=False,candidate=None,errors=[],passes=[],retired_track_uuids=[],retired_via_uuids=[],
        release_authority=False,original_macro_source_receiving_still_required=True,
        inherited_native_faults_not_suppressed=True,intermediate_prefixes_not_admission_baselines=True,
        maximum_passes=4,maximum_track_cuts=32,maximum_barrel_cuts=4,outer_wall_bound_s=90.)
    started=time.monotonic()
    try:
        source=Path(source).resolve();outdir=Path(outdir)
        if not callable(native_grade) or outdir.exists():raise ValueError('fresh_bounded_native_tail_closure_required')
        family=force._family(source,board_hint);epoch=force._code_identity()
        permitted_locks=ordinary._ids(allow_locked_obsolete_track_uuids,'macro_tail_locked_track_scope',32)
        original_board=pcbnew.LoadBoard(str(source))
        original_tracks={force._uid(t):t for t in original_board.GetTracks()}
        if not permitted_locks<=original_tracks.keys() or any(original_tracks[u].GetClass()!='PCB_TRACK' for u in permitted_locks):
            raise ValueError('exact_original_macro_tail_track_lock_scope_required')
        old_ids={stage._canonical_identity(v) for v in original_native['violations']}
        current=source;report=proposed_native;tracks=set();vias=set();locked=set();locked_tracks=set();seen={force._hash(source)}
        for index in range(4):
            if time.monotonic()-started>=90:raise ValueError('native_macro_tail_outer_wall_bound')
            warnings=new_warning_ids(original_native,report)
            new_barrels=[v for v in report['violations'] if v['type']=='via_dangling'
                and stage._canonical_identity(v) not in old_ids]
            if not warnings:
                if new_barrels:raise ValueError('new_native_barrel_fault_requires_separate_receiver')
                break
            step=_single_construct(current,outdir/('PRIVATE-PASS-%d-NOT-ADMITTED'%index),board_hint=board_hint,
                original_native=original_native,proposed_native=report,timeout_s=timeout_s,
                allow_locked_obsolete_port_vias=allow_locked_obsolete_port_vias,
                allow_locked_obsolete_track_uuids=sorted(permitted_locks-tracks))
            result['passes'].append(step)
            if not step['ok'] or not step['complete'] or not step['changed']:
                raise ValueError('native_macro_tail_closure_refused_or_plateau:'+str(step['errors']))
            before=(len(tracks),len(vias));tracks.update(step['retired_track_uuids']);vias.update(step['retired_via_uuids'])
            locked.update(step['locked_via_scope_used'])
            locked_tracks.update(step.get('locked_track_scope_used',()))
            if before==(len(tracks),len(vias)) or len(tracks)>32 or len(vias)>4:
                raise ValueError('native_macro_tail_monotonic_source_work_bound')
            current=Path(step['candidate']);digest=force._hash(current)
            if digest in seen:raise ValueError('native_macro_tail_closure_repeated_saved_state')
            seen.add(digest);report=native_grade(current,index)
        else:
            if new_warning_ids(original_native,report) or any(v['type']=='via_dangling'
                    and stage._canonical_identity(v) not in old_ids for v in report['violations']):
                raise ValueError('native_macro_tail_closure_pass_bound')
        if current==source:
            result.update(ok=True,complete=True,changed=False);return result
        # Re-derive the FINAL barrel roles from the initial immutable prefix,
        # not the roles they happened to have in a previous cleanup pass.
        parent=pcbnew.LoadBoard(str(source));positive=ordinary.eligible_nets(parent,source,board_hint)
        exclusive=set();redundant=set();deadline=time.monotonic()+timeout_s
        for uid in sorted(vias):
            try:
                ordinary._exclusive_retired_vias(parent,{uid},retired_tracks=tracks,nets=positive,
                    unlock=locked,deadline=deadline);exclusive.add(uid)
            except ValueError:
                ordinary._redundant_single_face_vias(parent,{uid},retired_tracks=tracks,nets=positive,
                    unlock=locked,deadline=deadline);redundant.add(uid)
        proof=ordinary.receive(source,current,board_hint=board_hint,retired_track_uuids=sorted(tracks),
            allow_locked_track_uuids=sorted(locked_tracks),
            retired_via_uuids=sorted(exclusive),redundant_single_face_via_uuids=sorted(redundant),
            allow_locked_via_uuids=sorted(locked),allow_redundant_cut_only=True,timeout_s=timeout_s)
        result['whole_original_prefix_exact_ordinary_receiving']=proof
        if not proof['ok'] or not proof['complete']:
            raise ValueError('whole_original_macro_tail_closure_not_received:'+str(proof['errors']))
        if family!=force._family(source,board_hint) or epoch!=force._code_identity() or time.monotonic()-started>=90:
            raise ValueError('native_macro_tail_original_source_code_or_wall_bound_changed')
        result.update(ok=True,complete=True,changed=True,source=str(source),source_sha256=force._hash(source),
            candidate=str(current),candidate_sha256=force._hash(current),code_identity=epoch,
            retired_track_uuids=sorted(tracks),retired_via_uuids=sorted(vias),locked_via_scope_used=sorted(locked),
            locked_track_scope_used=sorted(locked_tracks),
            final_exclusive_barrel_uuids=sorted(exclusive),final_single_face_barrel_uuids=sorted(redundant),
            original_prefix_received_as_one_delta=True,source_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
