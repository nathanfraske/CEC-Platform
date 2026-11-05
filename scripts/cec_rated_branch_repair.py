"""Receive bounded rated-supply reconstruction plus additive ordinary escapes.

An existing distributed-load contract, not a net name or an assumed current
split, owns the exact retired planar branch. This is a bounded cooperative
transaction: the old branch's real boundaries and every surviving native
conductor partition must be restored. All replacement supply copper retains
the full existing load width. Main force copper, poses, and power fills are
outside this scope. Independent native DRC, current, field, pair, and physical
contact receiving are still mandatory; this module grants no release authority.
An explicit separate aggregate-fault tier repairs only proved undersized inner
strokes of a complete existing source/sink domain. It must restore the whole
rated path, preserves the full unchanged load and allows no new vias or scalar
additions. This does not make an aggregate bus a distributed supply branch.
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
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def source_span_mm(value, *, allow_undersized_reconstruction=False):
    """Bound explicit source reach only; never relax width, role or ownership.

    The default stays at 8 mm. A caller may opt into up to 32 mm for a
    legacy source edge crossing a local header/cell corridor. This does not
    permit a main force bus, inferred branch load, extra cut or neckdown.
    Every original conductor partition and boundary must still be restored.
    The separate proved-undersized-inner repair tier may explicitly reach
    64 mm. Its long edges must be actual native current faults, not merely
    ordinary fully rated branches; the selected source cut is capped at
    128 mm in that tier. Neither limit is electrical authority.
    """
    if (type(allow_undersized_reconstruction) is not bool
            or type(value) not in (int,float) or not math.isfinite(value)
            or not 0 < value <= (64 if allow_undersized_reconstruction else 32)):
        raise ValueError('finite_small_rated_source_span_required')
    return float(value)


def replacement_width_mm(value, *, allow_rated_layer_bridges=False):
    """Bound reconstruction work, not the electrical width authority.

    An inner layer can require a wider replacement for the SAME complete
    source load. The legacy 0.35-mm ceiling remains the default; widening it
    requires explicit layer-bridge scope. Source eligibility is unchanged:
    only an already full-load-rated small outer branch can be retired.
    """
    if (type(allow_rated_layer_bridges) is not bool
            or type(value) not in (int,float) or not math.isfinite(value)
            or not 0 < value <= 5.
            or value > .35 and not allow_rated_layer_bridges):
        raise ValueError('bounded_explicit_rated_replacement_width_required')
    return float(value)


def retirement_count(value):
    """Explicit finite source work scope; source roles/widths stay unchanged."""
    if type(value) is not int or not 1 <= value <= 32:
        raise ValueError('bounded_explicit_rated_retirement_count_required')
    return value


def source_width_mm(value):
    """Finite work scope for an already full-load-rated distributed supply.

    The default remains 0.35 mm. An explicit ceiling up to 1 mm can cover
    medium-current outer-layer supplies; aggregate force domains and
    measurement/pair/ground nets remain excluded by the independent catalog.
    This never reduces the source load or its layer-specific physical floor.
    """
    if (type(value) not in (int,float) or not math.isfinite(value)
            or not 0 < value <= 1.):
        raise ValueError('bounded_explicit_rated_source_width_required')
    return float(value)


def reconstruction_options(options):
    """Finite public phase schema only; no file, role or current authority."""
    allowed={'allow_rated_layer_bridges','max_source_track_mm','allow_qualified_local_vias',
        'max_replacement_width_mm','max_retired_tracks','max_source_width_mm',
        'allow_rated_source_inner_layers','repair_undersized_source',
        'use_source_declared_consumer_island','repair_aggregate_current_domain',
        'retire_obsolete_terminal_vias'}
    if type(options)is not dict or not set(options)<=allowed:
        raise ValueError('exact_bounded_rated_reconstruction_options_required')
    flags={k:options.get(k,False)for k in allowed if k not in {
        'max_source_track_mm','max_replacement_width_mm','max_retired_tracks','max_source_width_mm'}}
    if any(type(v)is not bool for v in flags.values()):
        raise ValueError('explicit_boolean_rated_reconstruction_modes_required')
    if flags['allow_rated_source_inner_layers']and not flags['allow_rated_layer_bridges']:
        raise ValueError('inner_source_requires_explicit_full_load_layer_bridge')
    if flags['repair_undersized_source']and not flags['allow_rated_source_inner_layers']:
        raise ValueError('undersized_source_repair_requires_explicit_inner_scope')
    if flags['allow_qualified_local_vias']and not flags['allow_rated_layer_bridges']:
        raise ValueError('qualified_local_vias_require_explicit_rated_bridge_mode')
    if flags['use_source_declared_consumer_island']and flags['repair_undersized_source']:
        raise ValueError('distinct_explicit_source_consumer_reconstruction_scope_required')
    if flags['repair_aggregate_current_domain']and not flags['repair_undersized_source']:
        raise ValueError('aggregate_domain_repair_requires_explicit_undersized_inner_scope')
    if flags['retire_obsolete_terminal_vias']and (
            not flags['repair_undersized_source'] or flags['repair_aggregate_current_domain']
            or flags['use_source_declared_consumer_island']):
        raise ValueError('obsolete_terminal_barrels_only_explicit_distributed_inner_fault_repair')
    source_span_mm(options.get('max_source_track_mm',8.),
        allow_undersized_reconstruction=flags['repair_undersized_source'])
    replacement_width_mm(options.get('max_replacement_width_mm',.35),
        allow_rated_layer_bridges=flags['allow_rated_layer_bridges'])
    retirement_count(options.get('max_retired_tracks',8))
    source_width_mm(options.get('max_source_width_mm',.35))
    return dict(options)


def _aggregate_repair_contracts(board, source, nets, board_hint):
    """Positive whole-domain authority, never a distributed-load fallback.

    This distinct repair tier owns only native, proved undersized inner
    strokes. Every replacement carries the complete unchanged source/sink
    load. A net name, small tap load or a newly guessed allocation is not
    authority to repair a pass-through conductor.
    """
    import cec_full_current_planar_reflow as full
    contracts = {}; domains = {}
    for net in sorted(nets):
        kind, domain, contract = full._model(board, source, net, board_hint)
        if (kind != 'aggregate_source_sink' or domain.get('net') != net
                or type(domain.get('amps')) not in (int, float)
                or not math.isfinite(domain['amps']) or domain['amps'] <= 0
                or domain.get('amps') != contract.get('amps')):
            raise ValueError('complete_unchanged_aggregate_repair_authority_required')
        contracts[net] = contract; domains[net] = domain
    return dict(contracts=contracts), domains


def plan(board, source, *, board_hint, retired_track_uuids, timeout_s=10.,
         max_source_track_mm=8.,max_retired_tracks=8,max_source_width_mm=.35,
         allow_rated_source_inner_layers=False,repair_undersized_source=False,
         use_source_declared_consumer_island=False,repair_aggregate_current_domain=False,
         retire_obsolete_terminal_vias=False):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_rated_branch_inventory_required')
    count=retirement_count(max_retired_tracks)
    source_ceiling=source_width_mm(max_source_width_mm)
    if type(allow_rated_source_inner_layers) is not bool:
        raise ValueError('explicit_full_load_inner_source_scope_required')
    if (type(repair_undersized_source) is not bool
            or repair_undersized_source and not allow_rated_source_inner_layers):
        raise ValueError('undersized_source_repair_requires_explicit_inner_scope')
    if (type(use_source_declared_consumer_island) is not bool
            or use_source_declared_consumer_island and repair_undersized_source):
        raise ValueError('distinct_explicit_source_consumer_reconstruction_scope_required')
    if (type(repair_aggregate_current_domain) is not bool
            or repair_aggregate_current_domain and not repair_undersized_source):
        raise ValueError('aggregate_domain_repair_requires_explicit_undersized_inner_scope')
    if (type(retire_obsolete_terminal_vias)is not bool
            or retire_obsolete_terminal_vias and (not repair_undersized_source
                or repair_aggregate_current_domain or use_source_declared_consumer_island)):
        raise ValueError('obsolete_terminal_barrels_only_explicit_distributed_inner_fault_repair')
    span=source_span_mm(max_source_track_mm,
        allow_undersized_reconstruction=repair_undersized_source)
    planes={int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    retired = ordinary._ids(retired_track_uuids, 'rated_branch_retirement', count)
    if not retired:
        raise ValueError('nonempty_exact_rated_branch_scope_required')
    resolver = fr._project_netclass_resolver(str(source))
    tracks = {force._uid(t): t for t in board.GetTracks()}
    aggregate_domains = {}
    if repair_aggregate_current_domain:
        if not retired <= tracks.keys():
            raise ValueError('aggregate_current_source_cut_stale')
        authority, aggregate_domains = _aggregate_repair_contracts(board, source,
            {str(tracks[u].GetNetname()) for u in retired}, board_hint)
    else:
        with force._thermal_hint(board_hint):
            authority = topology.distributed_supply_contracts(board, board_hint,
                netclass_resolver=resolver)
    consumer_scope=None
    if use_source_declared_consumer_island:
        import cec_rated_consumer_scope as consumer
        local,consumer_scope=consumer.bind(board,authority['contracts'],retired,board_hint=board_hint)
        authority=dict(authority,contracts=local)
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    selected = {};repairs=[]
    for uid in sorted(retired):
        t = tracks.get(uid)
        net = str(t.GetNetname()) if t is not None else ''
        contract = authority['contracts'].get(net)
        layer = board.GetLayerName(t.GetLayer()) if t is not None else ''
        canonical=fab.COPPER_LAYER_IDS.get(t.GetLayer()) if t is not None else None
        required = (contract or {}).get('required_by_layer_mm', {}).get(layer,
            (contract or {}).get('required_by_layer_mm',{}).get(canonical))
        authorized_source_face=(t is not None and t.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu))
        if allow_rated_source_inner_layers and t is not None:
            authorized_source_face=(int(t.GetLayer()) in enabled-planes
                and (canonical in (contract or {}).get('routing_layers',())
                    or layer in (contract or {}).get('routing_layers',())))
        fully_rated=(required is not None and 0<required<=source_ceiling
            and t is not None and math.ceil(required*1e6)<=t.GetWidth())
        repairable=(repair_undersized_source and t is not None
            and t.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
            and required is not None and math.isfinite(required) and required>0
            and 0<t.GetWidth()<math.ceil(required*1e6))
        if repair_aggregate_current_domain and not repairable:
            raise ValueError('aggregate_repair_only_proved_undersized_inner_strokes:'+uid)
        if retire_obsolete_terminal_vias and not repairable:
            raise ValueError('obsolete_terminal_repair_only_proved_undersized_inner_strokes:'+uid)
        if t is not None and t.GetLength()>32000000 and not repairable:
            raise ValueError('extended_source_reach_only_proved_undersized_inner_strokes:'+uid)
        if (t is None or t.GetClass() != 'PCB_TRACK' or uid in grouped
                or not authorized_source_face
                or not contract or not (fully_rated or repairable)
                or not 0<t.GetWidth()<=math.floor(source_ceiling*1e6)
                or not 0 < t.GetLength() <= span*1e6):
            raise ValueError('retired_edge_not_small_explicit_full_load_branch:' + uid)
        selected[net] = contract
        if repairable:repairs.append((uid,net,canonical,t.GetWidth()/1e6,required))
    if span>32 and sum(tracks[u].GetLength() for u in retired)>128000000:
        raise ValueError('bounded_extended_undersized_source_cut_required')
    repair_keys=[]
    if repair_undersized_source:
        if not repairs:raise ValueError('undersized_source_repair_needs_actual_inner_fault')
        import cec_constraints as constraints
        import cec_current_debt as debt
        with force._thermal_hint(board_hint):
            checked=constraints.CHECKERS['trace-width-high-current'](board,str(source),{})
        evidence=debt._snapshot(checked)
        if repair_aggregate_current_domain:
            for net in selected:
                fault=evidence['atoms'].get(('domain',net))
                if (not fault or fault['original_connectivity'] is not True
                        or fault['rated_connectivity'] is not False):
                    raise ValueError('proved_preexisting_undersized_aggregate_path_required:'+net)
        for uid,net,canonical,actual,required in repairs:
            key=('domain_trace' if repair_aggregate_current_domain else 'trace',net,uid,canonical)
            atom=evidence['atoms'].get(key)
            authority=selected[net].get('current_authority')
            import json
            if (not atom or abs(atom['actual']-actual)>1e-9
                    or abs(atom['required']-required)>1e-9 or not authority
                    or atom['authority']!=json.dumps(authority,sort_keys=True,separators=(',',':'),allow_nan=False)):
                raise ValueError('exact_complete_native_source_current_fault_required:'+uid)
            repair_keys.append(list(key))
    obsolete=None
    if retire_obsolete_terminal_vias:
        # Only this independent Source compiler can derive obsolete barrels
        # and their exact factory-group membership. A caller supplies no via
        # list, unlock permission, pad role, or current allocation.
        import cec_source_obsolete_supply_barrels as barrels
        obsolete=barrels.plan(board,source,selected,sorted(retired),
            board_hint=board_hint,timeout_s=timeout_s)
    retired_vias=[]if obsolete is None else obsolete['retired_via_uuids']
    boundaries = ordinary._boundaries(board, board,
        [tracks[u] for u in sorted(retired)], time.monotonic() + timeout_s,
        exclusive_retired_via_uuids=retired_vias)
    return dict(schema=1, scope='bounded_source_rated_branch_reconstruction',
        retired_track_uuids=sorted(retired), contracts=selected,
        source_boundaries=boundaries, source_sha256=force._hash(source),
        max_source_track_mm=span,
        extended_undersized_source_reach=span>32,
        max_retired_tracks=count,
        max_source_width_mm=source_ceiling,
        allow_rated_source_inner_layers=allow_rated_source_inner_layers,
        repair_undersized_source=repair_undersized_source,
        repair_aggregate_current_domain=repair_aggregate_current_domain,
        retire_obsolete_terminal_vias=retire_obsolete_terminal_vias,
        retired_via_uuids=retired_vias,
        obsolete_terminal_barrel_source=obsolete,
        source_local_factory_group_uuids=[]if obsolete is None else obsolete['source_local_factory_group_uuids'],
        aggregate_current_domains=aggregate_domains,
        exact_source_current_fault_keys=repair_keys,
        source_declared_consumer_scope=consumer_scope,
        full_load_width_required=True, inferred_branch_load=False,
        current_qualified=False, release_authority=False)


def _receive_steps(source, candidate, *, board_hint, retired_track_uuids, timeout_s=10.,
            allow_rated_layer_bridges=False,max_source_track_mm=8.,allow_qualified_local_vias=False,
            max_replacement_width_mm=.35,max_retired_tracks=8,max_source_width_mm=.35,
            allow_rated_source_inner_layers=False,repair_undersized_source=False,
            use_source_declared_consumer_island=False,repair_aggregate_current_domain=False,
            retire_obsolete_terminal_vias=False):
    """Independently type the cut, then replay source-minus-cut-plus-additions.

    New rated material keeps the unchanged full-load width. Explicit layer
    bridges also retain the source-authorized layer and barrel contracts. New
    ordinary copper may close blocked pins, but may not retire other material
    or claim a supply, differential, sense, ground, or clock exemption.
    """
    result = dict(schema=1, scope='rated_branch_and_additive_scalar_receiving',
        ok=False, complete=False, errors=[], release_authority=False,
        inherited_debt_qualified=False, current_authority=False)
    stage='source_inventory'
    try:
        if type(allow_rated_layer_bridges) is not bool:
            raise ValueError('explicit_rated_layer_bridge_mode_required')
        if (type(allow_rated_source_inner_layers) is not bool
                or allow_rated_source_inner_layers and not allow_rated_layer_bridges):
            raise ValueError('inner_source_requires_explicit_full_load_layer_bridge')
        width_ceiling=replacement_width_mm(max_replacement_width_mm,
            allow_rated_layer_bridges=allow_rated_layer_bridges)
        if (type(allow_qualified_local_vias) is not bool
                or allow_qualified_local_vias and not allow_rated_layer_bridges):
            raise ValueError('qualified_local_vias_require_explicit_rated_bridge_mode')
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proposal = plan(parent, source, board_hint=board_hint,
            retired_track_uuids=retired_track_uuids, timeout_s=timeout_s,
            max_source_track_mm=max_source_track_mm,max_retired_tracks=max_retired_tracks,
            max_source_width_mm=max_source_width_mm,
            allow_rated_source_inner_layers=allow_rated_source_inner_layers,
            repair_undersized_source=repair_undersized_source,
            use_source_declared_consumer_island=use_source_declared_consumer_island,
            repair_aggregate_current_domain=repair_aggregate_current_domain,
            retire_obsolete_terminal_vias=retire_obsolete_terminal_vias)
        if retire_obsolete_terminal_vias:
            yield 'source_inventory',None
            stage='saved_native_material'
        retired_tracks=set(proposal['retired_track_uuids'])
        retired_vias=set(proposal['retired_via_uuids'])
        retired=retired_tracks|retired_vias
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        if old.keys() - new.keys() != retired:
            raise ValueError('saved_rated_retirement_differs_from_source_scope')
        incoming = new.keys() - old.keys()
        if not 1 <= len(incoming) <= 256:
            raise ValueError('bounded_rated_branch_additions_required')
        ordinary_nets = ordinary.eligible_nets(parent, source, board_hint)
        original = {force._uid(t): t for t in parent.GetTracks()}
        replacement = [t for t in child.GetTracks() if force._uid(t) in incoming]
        resolver = fr._project_netclass_resolver(str(source))
        lengths = {n: 0. for n in proposal['contracts']}
        rated_ids, scalar_ids, rated_vias, qualified_vias = [], [], [], []
        for t in replacement:
            net = str(t.GetNetname()); contract = proposal['contracts'].get(net)
            if contract:
                if t.GetClass()=='PCB_VIA' and allow_rated_layer_bridges:
                    spec=fr._project_netclass_resolver(str(source))(net) or {}
                    diameter,drill,_=fab.board_legal_through_via_geometry(child,
                        max(.6,float(spec.get('via_diameter') or .6)),
                        max(.3,float(spec.get('via_drill') or .3)))
                    ordinary_geometry=(t.GetWidth(t.TopLayer())>=round(diameter*1e6)
                        and t.GetDrillValue()>=round(drill*1e6))
                    qualified=(fab.local_pofv_via_decision(child,t) if allow_qualified_local_vias
                        else (False,'qualified local via mode not enabled'))
                    if (t.GetViaType()!=pcbnew.VIATYPE_THROUGH or t.TopLayer()!=pcbnew.F_Cu
                            or t.BottomLayer()!=pcbnew.B_Cu
                            or not (ordinary_geometry or qualified[0] is True)):
                        raise ValueError('rated_bridge_barrel_below_unchanged_through_geometry')
                    if not ordinary_geometry:
                        qualified_vias.append(dict(uuid=force._uid(t),basis=qualified[1]))
                    rated_vias.append(force._uid(t))
                    if len(rated_vias)>4:raise ValueError('rated_layer_bridge_barrel_count_bound')
                    continue
                required = contract.get('required_by_layer_mm', {}).get(child.GetLayerName(t.GetLayer()),
                    contract.get('required_by_layer_mm',{}).get(fab.COPPER_LAYER_IDS.get(t.GetLayer())))
                spec=resolver(net) or {}
                by_layer=spec.get('track_width_by_layer_mm') or {}
                class_width = max(child.GetDesignSettings().m_TrackMinWidth,
                    math.ceil(float(spec.get('track_width') or .2)*1e6),
                    math.ceil(float(by_layer.get(fab.COPPER_LAYER_IDS.get(t.GetLayer())) or 0)*1e6),
                    math.ceil(float(by_layer.get(child.GetLayerName(t.GetLayer())) or 0)*1e6))
                if repair_undersized_source:
                    class_width=max(class_width,max(original[u].GetWidth() for u in retired_tracks
                        if str(original[u].GetNetname())==net))
                allowed=(fab.COPPER_LAYER_IDS.get(t.GetLayer()) in contract.get('routing_layers',())) \
                    if allow_rated_layer_bridges else t.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu)
                # Match both canonical and user-facing layer aliases to the
                # immutable contract. Neither a plane nor an arbitrary layer
                # is authorized merely because it appears in the stack.
                if allow_rated_layer_bridges:
                    allowed=allowed or child.GetLayerName(t.GetLayer()) in contract.get('routing_layers',())
                if (t.GetClass() != 'PCB_TRACK' or not allowed
                        or required is None
                        or not max(math.ceil(required * 1e6), class_width) <= t.GetWidth()
                            <= math.floor(width_ceiling * 1e6)):
                    raise ValueError('incoming_rated_branch_is_not_full_load_planar')
                lengths[net] += t.GetLength() / 1e6
                rated_ids.append(force._uid(t))
            elif net in ordinary_nets and t.GetClass() in ('PCB_TRACK', 'PCB_VIA'):
                spec = resolver(net) or {}
                if t.GetClass() == 'PCB_TRACK':
                    if t.GetWidth() < max(child.GetDesignSettings().m_TrackMinWidth,
                            round(float(spec.get('track_width') or .2)*1e6)):
                        raise ValueError('incoming_scalar_track_below_unchanged_class_minimum')
                elif not fab.local_pofv_via_decision(child, t)[0]:
                    diameter, drill, _ = fab.board_legal_through_via_geometry(child,
                        max(.6,float(spec.get('via_diameter') or .6)),
                        max(.3,float(spec.get('via_drill') or .3)))
                    if (t.GetWidth(t.TopLayer()) < round(diameter*1e6)
                            or t.GetDrillValue() < round(drill*1e6)):
                        raise ValueError('incoming_scalar_via_below_unchanged_class_minimum')
                scalar_ids.append(force._uid(t))
            else:
                raise ValueError('incoming_copper_outside_rated_and_scalar_scope')
        if not rated_ids or len(rated_ids) > 64:
            raise ValueError('bounded_actual_rated_reconstruction_required')
        if retire_obsolete_terminal_vias:
            if rated_vias or scalar_ids or any(t.GetLayer()not in(pcbnew.F_Cu,pcbnew.B_Cu)
                    for t in replacement):
                raise ValueError('obsolete_terminal_barrel_repair_full_load_surface_only')
            import cec_surface_supply_path_graph as surface
            physical=surface.prove(parent,child,source,list(proposal['contracts'].values()),timeout_s=timeout_s)
            result['drill_subtracted_full_width_surface_paths']=physical
            if physical.get('complete')is not True or physical.get('all_source_pads_surface_connected')is not True:
                raise ValueError('obsolete_terminal_barrel_repair_needs_all_source_pads_physical_surface_path')
        if repair_aggregate_current_domain:
            if rated_vias or scalar_ids:
                raise ValueError('aggregate_fault_repair_is_planar_full_load_only')
            import cec_pair_local_reference_refinement as source_chain
            source_path = [original[u] for u in sorted(retired_tracks)]
            if (len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in source_path}) != 1
                    or len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in replacement}) != 1):
                raise ValueError('one_uniform_source_and_replacement_aggregate_path_required')
            old_ports = source_chain._chain(source_path)
            new_ports = source_chain._chain(replacement)
            if {tuple(old_ports[0]),tuple(old_ports[-1])} != {tuple(new_ports[0]),tuple(new_ports[-1])}:
                raise ValueError('complete_original_aggregate_path_endpoints_must_replay')
            import cec_route_quality as quality
            craft = quality.analyze_board(child, track_uuid_scope=incoming)
            if not craft['geometry_ok'] or not craft['craft_ok']:
                raise ValueError('aggregate_fault_repair_canonical_craft_required')
        for net, length in lengths.items():
            old_length = sum(original[u].GetLength()/1e6 for u in retired_tracks
                if str(original[u].GetNetname()) == net)
            if not 0 < length <= old_length + 16:
                raise ValueError('source_local_rated_reconstruction_length_bound')
        result['restored_source_boundaries'] = ordinary._boundaries(parent, child,
            [original[u] for u in sorted(retired_tracks)], time.monotonic()+timeout_s,
            exclusive_retired_via_uuids=retired_vias)
        # A real through-via changes Ground antipads and thus exact fill keys.
        # Match positive native material overlap per island/face, not a whole
        # zone UUID or an obsolete polygon hash. Every retained pad/track/via,
        # original component and exact Source cut still has to survive.
        import cec_native_partition_pair as partitions
        paired=partitions.compare(parent,child,timeout_s=timeout_s,retired_uuids=retired)
        result['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('rated_reconstruction_lost_surviving_native_partition')
        if repair_aggregate_current_domain:
            fresh, domains = _aggregate_repair_contracts(child, candidate,
                proposal['contracts'], board_hint)
            if domains != proposal['aggregate_current_domains']:
                raise ValueError('aggregate_fault_repair_source_sink_authority_changed')
            rated_paths = {}
            for net, domain in domains.items():
                rated_paths[net] = force._graph(child, net, domain,
                    fresh['contracts'][net], resolver(net) or {})[0]
                if not rated_paths[net]['rated_connectivity']['connected']:
                    raise ValueError('aggregate_fault_repair_must_restore_complete_rated_path')
            result['independent_complete_rated_paths'] = rated_paths
        else:
            with force._thermal_hint(board_hint):
                fresh = topology.distributed_supply_contracts(child, board_hint,
                    netclass_resolver=fr._project_netclass_resolver(str(source)))
        if use_source_declared_consumer_island:
            import cec_rated_consumer_scope as consumer
            result['independent_saved_consumer_scope']=consumer.receive(child,fresh['contracts'],
                proposal['source_declared_consumer_scope'],proposal['contracts'],rated_ids,rated_vias,
                board_hint=board_hint)
        elif {n: fresh['contracts'].get(n) for n in proposal['contracts']} != proposal['contracts']:
            raise ValueError('rated_reconstruction_changed_existing_load_contract')
        with tempfile.TemporaryDirectory(prefix='cec-rated-branch-replay-') as work:
            projected = force._copy_family(source, Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected))
            discard_items(basis, [t for t in basis.GetTracks() if force._uid(t) in retired])
            # A native no-op save can normalize unrelated hidden properties.
            # The independent electrical cut is above; project its literal
            # Source-minus-cut without rewriting any unowned bytes, and
            # separately require the complete native material inventory.
            groups=proposal['source_local_factory_group_uuids']
            if groups:
                import cec_source_literal_group_retirement as literal_cut
                result['literal_source_subtraction'] = literal_cut.write_native_projection(
                    source,projected,sorted(retired),
                    proposal['obsolete_terminal_barrel_source']['factory_group_member_retirements'],basis)
            else:
                import cec_source_literal_retirement as literal_cut
                result['literal_source_subtraction'] = literal_cut.write_native_projection(
                    source, projected, sorted(retired), basis)
            _, nodes = additive._nodes(projected)
            import cec_bypass_return_reseat as bypass_return
            if (nodes.keys() != old.keys()-retired or any(
                    not bypass_return.exact_factory_group_subtraction(old[u],nodes[u],retired_vias)
                    if u in groups else sexpr._freeze(nodes[u]) != sexpr._freeze(old[u]) for u in nodes)):
                raise ValueError('rated_subtraction_changed_unowned_source_material')
            replay = additive.receive(projected, candidate, timeout_s=timeout_s)
            result['exact_source_cut_additions_ground_and_rule_replay'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('independent_rated_source_delta_replay_refused')
            if rated_vias:
                # All enabled layers, real hole spacing and the original
                # source-minus-proved-cut govern each new barrel. Geometry
                # does NOT manufacture an ampacity certificate for the via.
                gap=max(basis.GetDesignSettings().m_MinClearance,200000)
                for t in replacement:
                    if force._uid(t) not in rated_vias:continue
                    if not fr._via_spot_clear(basis,t.GetPosition(),t.GetWidth(t.TopLayer()),
                            gap,{t.GetNetCode()},drill_nm=t.GetDrillValue(),net_code=t.GetNetCode(),foreign_cache={}):
                        raise ValueError('rated_layer_bridge_original_all_layer_guard_refused')
        if retire_obsolete_terminal_vias:
            yield 'saved_native_material',None
            stage='final_current_and_identity'
        if repair_undersized_source:
            import cec_current_debt as current_debt
            improved=current_debt.receive(source,candidate,board_hint=board_hint)
            result['strict_source_current_fault_repair']=improved
            if (improved.get('ok') is not True or improved.get('complete') is not True
                    or improved.get('after_fault_objects',math.inf)>
                    improved.get('before_fault_objects',0)-len(proposal['exact_source_current_fault_keys'])):
                raise ValueError('undersized_source_repair_must_strictly_reduce_current_faults_without_new_debt')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity()):
            raise ValueError('rated_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            retired_track_uuids=sorted(retired_tracks),retired_via_uuids=sorted(retired_vias),
            source_local_factory_group_uuids=proposal['source_local_factory_group_uuids'],
            added_native_uuids=sorted(incoming),
            rated_replacement_track_uuids=sorted(rated_ids), scalar_addition_uuids=sorted(scalar_ids),
            rated_replacement_via_uuids=sorted(rated_vias),allow_rated_layer_bridges=allow_rated_layer_bridges,
            max_replacement_width_mm=width_ceiling,
            source_small_branch_eligibility_unchanged=proposal['max_source_width_mm']==.35 and not repair_undersized_source,
            source_distributed_load_ownership_unchanged=not repair_aggregate_current_domain,
            source_aggregate_current_domain_unchanged=repair_aggregate_current_domain,
            allow_qualified_local_vias=allow_qualified_local_vias,qualified_local_rated_vias=qualified_vias,
            new_barrel_ampacity_credited=False,barrel_and_thermal_qualification_still_required=bool(rated_vias),
            source_proposal=proposal, all_surviving_native_partitions_preserved=True,
            main_force_copper_poses_and_power_fills_exact=not repair_aggregate_current_domain,
            all_unowned_current_copper_poses_and_power_fills_exact=True,
            full_drc_current_field_pair_and_kelvin_receiving_still_required=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
        result['failed_verification_stage']=stage
    yield stage,result


def receive(source, candidate, *, board_hint, retired_track_uuids, timeout_s=10.,
            allow_rated_layer_bridges=False,max_source_track_mm=8.,allow_qualified_local_vias=False,
            max_replacement_width_mm=.35,max_retired_tracks=8,max_source_width_mm=.35,
            allow_rated_source_inner_layers=False,repair_undersized_source=False,
            use_source_declared_consumer_island=False,repair_aggregate_current_domain=False,
            retire_obsolete_terminal_vias=False):
    """Receive the whole saved transaction; no prepared receipt is accepted.

    The explicit obsolete-barrel mode composes THREE separate <=10-second
    leases: fresh Source ownership/current-fault inventory; saved native
    material/physical/literal replay; and fresh whole current debt plus final
    identity. Its aggregate bound is three leases, not a longer native check.
    No intermediate yield is a PASS, route admission or reusable authority.
    Other modes retain their existing public receiving/budget behavior.
    """
    options=locals().copy()
    work=_receive_steps(**options);leases=[];result=None
    expected=('source_inventory','saved_native_material','final_current_and_identity')
    try:
        for index in range(3):
            started=time.monotonic();name,value=next(work);elapsed=time.monotonic()-started
            leases.append(dict(stage=name,elapsed_s=elapsed,maximum_s=timeout_s))
            if retire_obsolete_terminal_vias is True and elapsed>=timeout_s:
                raise ValueError('rated_receiving_constituent_deadline:'+name)
            if retire_obsolete_terminal_vias is True and name!=expected[index]:
                raise ValueError('rated_receiving_constituent_order_changed')
            if value is not None:
                if type(value)is not dict or retire_obsolete_terminal_vias is True and index!=2 and (
                        value.get('ok')is True or value.get('complete')is True):
                    raise ValueError('rated_receiving_intermediate_cannot_be_complete')
                result=value;break
        if result is None:
            raise ValueError('rated_receiving_incomplete_constituent_sequence')
    except Exception as exc:
        result=dict(ok=False,complete=False,errors=[type(exc).__name__+':'+str(exc)],release_authority=False)
    finally:
        work.close()
    if retire_obsolete_terminal_vias is True:
        result.update(explicit_independent_verification_leases=leases,
            maximum_verification_leases=3,per_constituent_maximum_s=timeout_s,
            no_intermediate_receiving_authority=True)
    return result
