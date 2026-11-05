"""Exact, bounded full-current planar reflow, never an ordinary-net waiver.

One existing source-owned current domain or explicitly budgeted distributed
supply owns a bounded explicit ungrouped cut. An incomplete aggregate domain
cannot fall back to the distributed role; source/sink roles are never guessed.
Replacement tracks retain its source width, face and complete current contract.
Every old boundary, surviving partition, control reservation and unowned item
must replay. No vias, pours, component moves or inferred sharing are allowed.
Full native DRC, fields, current, pairs and release checks remain independent.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_current_capture as capture
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
from cec_native_items import discard_items


def _budget(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 10:
        raise ValueError('bounded_full_current_planar_reflow_required')
    return time.monotonic() + seconds


def source_work_bounds(max_source_track_mm=8.,max_source_cut_mm=32.):
    """Bound source reach only; never current, width, ownership or a waiver.

    The short defaults remain unchanged. Explicit finite reconstruction may
    cover <=32 mm per edge and <=48 mm total of the SAME full-current source
    bus. No extra retirement, layer change, sharing credit or longer receiving
    deadline follows. Every native boundary and unaffected item still replays.
    """
    values=(max_source_track_mm,max_source_cut_mm)
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=limit
            for v,limit in zip(values,(32.,48.))):
        raise ValueError('bounded_explicit_full_current_source_reach_required')
    return tuple(float(v) for v in values)


def _model(board, source, net, board_hint):
    """Select positive existing authority; no signal-width/current fallback."""
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        if net in domains:
            domain=domains[net]
            contract=topology.route_width_contracts(board,board_hint=board_hint).get(net)
            if (domain.get('complete') is not True or not domain.get('source_refs')
                    or not domain.get('sink_refs') or not contract):
                raise ValueError('complete_existing_full_current_source_domain_required')
            raw=(contract.get('current_authority') or {})
            if raw.get('source')=='current_domain_authority':
                # The existing width checker also owns explicit thermal
                # source/sink contracts. Re-derive their exact authority
                # from this actual native board; a spelling whitelist must
                # not make a complete rated domain permanently unrepairable.
                # This is NOT a distributed fallback, a fuse rating, a new
                # current or permission to accept an incomplete domain.
                from cec_series_current_domain import validate_existing_domain_authority
                sources,sinks=domain['source_refs'],domain['sink_refs']
                owners=domain.get('authority_refs')
                if (type(sources)not in(list,tuple)or type(sinks)not in(list,tuple)
                        or type(owners)not in(list,tuple)
                        or any(type(ref)is not str or not ref.strip() for ref in(*sources,*sinks,*owners))
                        or len(set(sources))!=len(sources)or len(set(sinks))!=len(sinks)
                        or len(set(owners))!=len(owners)
                        or set(sources)&set(sinks)
                        or set(owners)!=(set(sources)|set(sinks))
                        or domain.get('missing_refs')
                        or (domain.get('binding')or{}).get('off_net_required_refs')
                        or type(domain.get('amps'))not in(int,float)
                        or not math.isfinite(domain['amps'])or domain['amps']<=0
                        or raw.get('amps')!=domain['amps']
                        or not validate_existing_domain_authority(board,net,raw)):
                    raise ValueError('exact_complete_existing_native_domain_authority_required')
            elif raw.get('source')!='board_design_basis':
                raise ValueError('complete_existing_full_current_source_domain_required')
            kind='aggregate_source_sink'
        else:
            distributed=topology.distributed_supply_contracts(board,board_hint,
                include_nets=[net],netclass_resolver=fr._project_netclass_resolver(str(source),board=board))
            contract=distributed['contracts'].get(net);domain=None
            if (not contract or contract.get('role')!='all_terminal_conservative_aggregate'
                    or contract.get('source_sink_inferred') is not False
                    or contract.get('branch_sharing_assumed') is not False):
                raise ValueError('positive_existing_distributed_supply_contract_required')
            kind='explicit_all_terminal_distributed_supply'
    authority=(contract or {}).get('current_authority') or {}
    permitted_source=(authority.get('source')in('board_design_basis','component_power_budget')
        or kind=='aggregate_source_sink'and authority.get('source')=='current_domain_authority')
    if (contract.get('net')!=net or not permitted_source or
            any(type(authority.get(k)) not in (int,float) or not math.isfinite(authority[k])
                or authority[k]<=0 for k in ('amps','geometry_margin')) or
            authority['geometry_margin']<1 or type(authority.get('margin_included')) is not bool or
            authority['margin_included'] and authority['geometry_margin']!=1):
        raise ValueError('unchanged_positive_explicit_planar_current_authority_required')
    return kind,domain,contract


def _source_width_floor(board, source, contract, layer):
    """Geometry/process floor only; this does NOT supply current ownership.

    Read-only scheduling may reuse a freshly derived per-net model on one
    unchanged native board. Plan/receiving still rederive that actual model.
    """
    import cec_fab_profile as fab
    canonical = fab.COPPER_LAYER_IDS[layer]
    if (layer not in board.GetEnabledLayers().CuStack() or
            layer in {board.GetLayerID(name) for name in fr.plane_layers(board)} or
            canonical not in contract.get('routing_layers', ())):
        raise ValueError('existing_source_current_routing_face_required')
    physical = contract['required_by_layer_mm'].get(canonical)
    if type(physical) not in (int,float) or not math.isfinite(physical) or physical <= 0:
        raise ValueError('positive_actual_face_current_width_required')
    spec = fr._project_netclass_resolver(str(source),board=board)(contract['net']) or {}
    return max(math.ceil(physical*1e6), board.GetDesignSettings().m_TrackMinWidth,
        math.ceil(float(spec.get('track_width') or 0)*1e6),
        math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(canonical) or 0)*1e6))


def plan(board, source, *, board_hint, retired_track_uuids, timeout_s=10.,
         max_source_track_mm=8.,max_source_cut_mm=32.):
    deadline = _budget(timeout_s)
    source_span,source_total=source_work_bounds(max_source_track_mm,max_source_cut_mm)
    retired = ordinary._ids(retired_track_uuids, 'full_current_planar_cut', 8)
    if not retired:
        raise ValueError('nonempty_exact_full_current_planar_cut_required')
    live = {force._uid(t): t for t in board.GetTracks()}
    if not retired <= live.keys():
        raise ValueError('full_current_planar_cut_stale')
    tracks = [live[u] for u in sorted(retired)]
    if (any(t.GetClass() != 'PCB_TRACK' or t.GetParentGroup() is not None for t in tracks)
            or len({str(t.GetNetname()) for t in tracks}) != 1
            or len({int(t.GetLayer()) for t in tracks}) != 1
            or len({int(t.GetWidth()) for t in tracks}) != 1):
        raise ValueError('one_ungrouped_same_width_same_face_current_cut_required')
    net = str(tracks[0].GetNetname())
    layer = int(tracks[0].GetLayer())
    if not net or layer not in board.GetEnabledLayers().CuStack() or layer in {
            board.GetLayerID(name) for name in fr.plane_layers(board)}:
        raise ValueError('actual_enabled_nonplane_current_face_required')
    kind,domain,contract=_model(board,source,net,board_hint)
    # The exact native board is already in hand. Reloading it for every
    # candidate repeats source I/O, not an independent saved receiving pass.
    floor = _source_width_floor(board,source,contract,layer)
    face = board.GetLayerName(layer)
    width = int(tracks[0].GetWidth())
    if (not floor <= width <= 10000000
            or any(not 0 < t.GetLength() <= source_span*1e6 for t in tracks)
            or sum(t.GetLength() for t in tracks) > source_total*1e6):
        raise ValueError('bounded_unchanged_full_current_planar_width_and_span_required')
    if time.monotonic() >= deadline:
        raise ValueError('full_current_planar_inventory_deadline')
    return dict(schema=1, scope='exact_bounded_whole_current_planar_reflow',
        net=net, layer=face, layer_id=layer, width_nm=width, full_current_floor_nm=floor,
        contract=contract, domain=domain, current_domain_kind=kind, source_sha256=force._hash(source),
        retired_track_uuids=sorted(retired), original_length_nm=sum(t.GetLength() for t in tracks),
        max_source_track_mm=source_span,max_source_cut_mm=source_total,
        source_boundaries=ordinary._boundaries(board, board, tracks, deadline),
        current_sharing_inferred=False, source_current_reduced=False,
        vias_or_pours_authorized=False, release_authority=False)


def receive(source, candidate, *, board_hint, retired_track_uuids, timeout_s=10.,
            max_source_track_mm=8.,max_source_cut_mm=32.):
    result = dict(schema=1, scope='independent_full_current_planar_reflow',
        ok=False, complete=False, errors=[], routing_admitted=False, release_authority=False,
        current_authority=False, inherited_debt_qualified=False)
    try:
        deadline = _budget(timeout_s)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proposal = plan(parent, source, board_hint=board_hint,
            retired_track_uuids=retired_track_uuids, timeout_s=timeout_s,
            max_source_track_mm=max_source_track_mm,max_source_cut_mm=max_source_cut_mm)
        retired = set(proposal['retired_track_uuids'])
        _, old = additive._nodes(source)
        _, new = additive._nodes(candidate)
        if old.keys()-new.keys() != retired:
            raise ValueError('saved_full_current_cut_differs_from_exact_source_scope')
        incoming = new.keys()-old.keys()
        items = [t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 1 <= len(items) <= 32 or {force._uid(t) for t in items} != incoming:
            raise ValueError('only_bounded_planar_current_replacement_tracks_allowed')
        if any(t.GetClass() != 'PCB_TRACK' or str(t.GetNetname()) != proposal['net']
                or int(t.GetLayer()) != proposal['layer_id']
                or t.GetWidth() != proposal['width_nm'] for t in items):
            raise ValueError('replacement_must_retain_exact_source_current_width_and_face')
        if sum(t.GetLength() for t in items) > proposal['original_length_nm']+8000000:
            raise ValueError('full_current_planar_local_detour_length_bound')
        craft = quality.analyze_board(child, track_uuid_scope=incoming)
        if not craft['geometry_ok'] or not craft['craft_ok']:
            raise ValueError('full_current_planar_canonical_craft_refused')
        fresh_kind,fresh_domain,fresh=_model(child,candidate,proposal['net'],board_hint)
        with force._thermal_hint(board_hint):
            guard = capture.Guard(parent, source, net=proposal['net'],
                board_hint=board_hint, timeout_s=min(timeout_s, max(.001, deadline-time.monotonic())))
        if (fresh != proposal['contract'] or fresh_kind!=proposal['current_domain_kind']
                or fresh_domain!=proposal['domain']):
            raise ValueError('full_current_planar_source_contract_changed')
        for item in items:
            if not guard(tuple(item.GetStart()), tuple(item.GetEnd()),
                    item.GetWidth(), int(item.GetLayer())):
                raise ValueError('full_current_planar_control_reservation_refused')
        original = {force._uid(t):t for t in parent.GetTracks()}
        result['restored_source_boundaries'] = ordinary._boundaries(parent, child,
            [original[u] for u in sorted(retired)], deadline)
        import cec_native_partition_pair as partitions
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('full_current_planar_partition_deadline')
        paired=partitions.compare(parent,child,timeout_s=min(10.,remaining),retired_uuids=retired)
        result['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('full_current_planar_lost_surviving_native_partition')
        with tempfile.TemporaryDirectory(prefix='cec-full-current-planar-replay-') as work:
            projected = force._copy_family(source, Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected))
            discard_items(basis, [t for t in basis.GetTracks() if force._uid(t) in retired])
            import cec_source_literal_retirement as literal_cut
            result['literal_native_cut_projection']=literal_cut.write_native_projection(
                source,projected,retired,basis)
            _, nodes = additive._nodes(projected)
            if nodes.keys() != old.keys()-retired or any(
                    sexpr._freeze(nodes[u]) != sexpr._freeze(old[u]) for u in nodes):
                raise ValueError('full_current_planar_cut_changed_unowned_source_material')
            remaining = min(timeout_s, deadline-time.monotonic())
            if remaining <= 0:
                raise ValueError('full_current_planar_saved_replay_deadline')
            replay = additive.receive(projected, candidate, timeout_s=remaining)
            result['exact_source_cut_additions_ground_and_rule_replay'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('independent_full_current_planar_source_delta_refused')
        if families != [force._family(p, board_hint) for p in (source, candidate)] or epoch != force._code_identity():
            raise ValueError('full_current_planar_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            source_proposal=proposal, retired_track_uuids=sorted(retired), retired_via_uuids=[],
            added_native_uuids=sorted(incoming), source_control_capture=guard.report(),
            all_surviving_native_partitions_preserved=True, source_width_and_current_exact=True,
            full_drc_current_field_pair_and_kelvin_receiving_still_required=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive_force_sense_chain(source,candidate,*,board_hint,phases,
                             timeout_s=10.,sense_timeout_s=20.):
    """Requalify a finite planar-current lineage and its absolute copper cuts.

    Changed positive cut witnesses can legitimately name different tracks.
    They are NOT ignored: retype each exact planar transaction, reconstruct
    the whole original-source cut/additions, derive actual native manifests,
    preserve current debt and require two fresh absolute geometric cut passes.
    Unchanged unknown/failing legs stay strict. This is not fab qualification.
    """
    result=dict(schema=1,scope='exact_planar_current_chain_and_physical_cut_receiving',
        ok=False,complete=False,errors=[],current_qualified=False,
        inherited_debt_qualified=False,routing_admitted=False,release_authority=False)
    try:
        _budget(timeout_s)
        if (type(board_hint) is not str or not board_hint or type(phases) not in (list,tuple)
                or not 1<=len(phases)<=4 or any(type(r) is not dict or
                    not {'kind','candidate','retired_track_uuids'}<=set(r) or
                    not set(r)<={'kind','candidate','retired_track_uuids',
                        'max_source_track_mm','max_source_cut_mm'} or
                    r['kind']!='full_current_planar_reflow' for r in phases)
                or type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s)
                or not 0<sense_timeout_s<=30):
            raise ValueError('bounded_exact_planar_current_physical_chain_required')
        for row in phases:
            source_work_bounds(row.get('max_source_track_mm',8.),row.get('max_source_cut_mm',32.))
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        paths=[source,*[Path(r['candidate']).resolve() for r in phases]]
        if paths[-1]!=candidate or len(set(paths))!=len(paths):
            raise ValueError('exact_saved_planar_chain_end_and_unique_lineage_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        import cec_source_cut_chain as chain
        typed=chain.receive(source,candidate,board_hint=board_hint,phases=phases,
            timeout_s=timeout_s,per_phase_leases=True)
        result['exact_typed_source_cut_chain']=typed
        if not typed.get('ok') or not typed.get('complete'):
            raise ValueError('independent_planar_current_chain_retyping_refused')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        old={force._uid(t):t for t in parent.GetTracks()}
        new={force._uid(t):t for t in child.GetTracks()}
        retired=set(old)-set(new);added=set(new)-set(old)
        if (retired!=set(typed['retired_track_uuids']) or typed['retired_via_uuids']
                or not 1<=len(retired)<=32 or not 1<=len(added)<=128
                or any(old[u].GetClass()!='PCB_TRACK' for u in retired)
                or any(new[u].GetClass()!='PCB_TRACK' for u in added)):
            raise ValueError('actual_whole_source_planar_chain_manifest_differs')
        nets={str(old[u].GetNetname()) for u in retired}|{str(new[u].GetNetname()) for u in added}
        transforms=[dict(net=net,retired_track_uuids=sorted(u for u in retired if old[u].GetNetname()==net),
            added_track_uuids=sorted(u for u in added if new[u].GetNetname()==net),
            retired_via_uuids=[],added_via_uuids=[],retired_zone_uuids=[],added_zone_uuids=[])
            for net in sorted(nets)]
        import cec_current_debt as debt
        current=debt.receive(source,candidate,board_hint=board_hint)
        result['whole_source_current_debt_receiving']=current
        if not current.get('ok') or not current.get('complete'):
            raise ValueError('whole_source_planar_chain_current_debt_refused')
        import cec_force_sense_evidence as sense
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in (source,candidate)]
        preservation=sense.compare_contour_preservation(before,after,modified_nets=sorted(nets),
            native_copper_transforms=transforms)
        result['physical_preservation']=preservation
        if (not preservation.get('comparison_complete') or not preservation.get('same_evidence')):
            raise ValueError('two_absolute_clipped_cuts_and_strict_unaffected_evidence_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('planar_physical_chain_source_phase_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),code_identity=epoch,phases=phases,
            native_count_manifest=transforms,source_sense=before,candidate_sense=after,
            source_current_and_widths_unchanged=True,full_native_drc_and_stack_receiving_still_required=True)
    except (ValueError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
