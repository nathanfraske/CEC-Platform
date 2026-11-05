"""Receive a complete redundant same-net outer collector and trace bundle.

Source locks require exact caller authorization; groups, planes and barrels
cannot be cut. Nothing new is emitted and no current sharing is inferred.
Every survivor, whole-source rated path, actual no-cut terminal connection,
and changed/unchanged clipped cut must survive independent saved replay.
This is not thermal, barrel, shielding, fabrication or release qualification.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_current_path_receiving as current_paths
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_kelvin_copper_cut as physical
import cec_ordinary_route_receiving as ordinary
import cec_redundant_force_branch as branch
import cec_native_copper_delta as material_delta
from cec_native_items import discard_items


def _ids(values,*,empty=False):
    if (type(values) not in (list,tuple,set,frozenset)
            or not (0 if empty else 1)<=len(values)<=36
            or any(type(u) is not str or not u for u in values)
            or len(set(values))!=len(values)):
        raise ValueError('exact_bounded_force_bundle_native_inventory_required')
    return set(values)


def _terminal_graph(board,net,*,timeout_s=10.):
    """Actual lower material model: islands/drills/barrels, never zone-owner IDs."""
    work=physical._Work(time.monotonic()+timeout_s)
    pads,tracks,zones,copper=physical._inventory(board,work)
    terminals=[p for p in pads if str(p.GetNetname())==net]
    if (not 2<=len(terminals)<=64 or any(p.GetAttribute() not in
            (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH) for p in terminals)):
        raise ValueError('bounded_actual_conducting_force_terminals_required')
    actual=[i for i in pads+tracks if str(i.GetNetname())==net]
    poured=[z for z in zones if str(z.GetNetname())==net]
    if len(actual)+len(poured)>physical.MAX_NET_ITEMS:
        raise ValueError('force_bundle_physical_material_bound')
    drilled={physical._key(i):i for i in pads+tracks if i.GetClass()=='PCB_VIA'
        or i.GetClass()=='PAD' and i.HasHole()}
    anchor=min(terminals,key=force._uid)
    others=[p for p in terminals if force._uid(p)!=force._uid(anchor)]
    model=physical._model(actual,drilled,poured,copper,anchor,anchor,others,
        False,work,cut_enabled=False)
    physical._validate_linear_epochs(work)
    reached={r['uuid'] for r in model['reached_authority']}|{force._uid(anchor)}
    wanted={force._uid(p) for p in terminals}
    if reached!=wanted:
        raise ValueError('force_bundle_actual_source_terminal_material_disconnected')
    return dict(pad_uuids=sorted(wanted),all_actual_terminals_definitely_connected=True,
        actual_filled_components=model['components'],plated_current_qualified=False)


def receive(source,candidate,*,board_hint,native_uuids,
            allow_locked_native_uuids=(),timeout_s=20.):
    result=dict(schema=1,scope='exact_saved_redundant_force_collector_bundle',ok=False,
        complete=False,errors=[],current_qualified=False,plated_barrel_current_qualified=False,
        full_kelvin_qualification=False,inherited_debt_qualified=False,release_authority=False)
    try:
        if (type(board_hint) is not str or not board_hint
                or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=60):
            raise ValueError('bounded_force_bundle_receiving_context_required')
        requested=_ids(native_uuids);unlocked=_ids(allow_locked_native_uuids,empty=True)
        if not unlocked<=requested:raise ValueError('force_bundle_lock_scope_not_in_exact_cut')
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_force_bundle_saved_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        live={force._uid(i):i for i in [*parent.GetTracks(),*parent.Zones()]}
        if not requested<=live.keys():raise ValueError('force_bundle_source_scope_stale')
        selected=[live[u] for u in sorted(requested)]
        nets={str(i.GetNetname()) for i in selected}
        zones=[i for i in selected if i.GetClass()=='ZONE']
        edges=[i for i in selected if i.GetClass()=='PCB_TRACK']
        if (len(nets)!=1 or not 1<=len(zones)<=4 or len(edges)>32
                or len(zones)+len(edges)!=len(selected)):
            raise ValueError('one_force_net_outer_zone_and_optional_tracks_only')
        net=next(iter(nets));planes={parent.GetLayerID(n) for n in fr.plane_layers(parent)}
        grouped={force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        for item in selected:
            if item.GetParentGroup() is not None or force._uid(item) in grouped:
                raise ValueError('force_bundle_group_reconstruction_not_authorized')
            if item.IsLocked() and force._uid(item) not in unlocked:
                raise ValueError('force_bundle_exact_source_lock_authorization_required')
            if item.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu) or item.GetLayer() in planes:
                raise ValueError('force_bundle_outer_nonplane_copper_only')
        for zone in zones:
            if (zone.GetIsRuleArea() or len(zone.GetLayerSet().CuStack())!=1
                    or not zone.IsFilled() or not zone.HasFilledPolysForLayer(zone.GetLayer())
                    or not zone.GetFilledPolysList(zone.GetLayer()).OutlineCount()):
                raise ValueError('force_bundle_known_nonempty_native_zone_material_required')
        domain,contract=branch._model(parent,net,board_hint)
        if (domain,contract)!=branch._model(child,net,board_hint):
            raise ValueError('force_bundle_unchanged_whole_current_authority_required')
        root,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if old.keys()-new.keys()!=requested or new.keys()-old.keys():
            raise ValueError('force_bundle_exact_source_minus_bundle_only')
        if (force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('force_bundle_source_metadata_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-force-bundle-replay-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            projected=pcbnew.LoadBoard(str(expected))
            discard_items(projected,[i for i in [*projected.GetTracks(),*projected.Zones()]
                if force._uid(i) in requested])
            additive._ground_refill(projected);field._save_field_snapshot(projected,expected)
            _,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('force_bundle_exact_native_cut_and_ground_refill_replay_differs')
        old_parts=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=requested)
        new_parts=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*old_parts))
        if not branch.preserved_partitions(old_parts,new_parts):
            raise ValueError('force_bundle_surviving_copper_or_land_partition_lost')
        physical_graphs=[_terminal_graph(b,net) for b in (parent,child)]
        if physical_graphs[0]['pad_uuids']!=physical_graphs[1]['pad_uuids']:
            raise ValueError('force_bundle_actual_native_terminal_inventory_changed')
        resolver=fr._project_netclass_resolver(str(paths[0]))
        current=current_paths.compare(*[force._graph(b,net,domain,contract,resolver(net) or {})[0]
            for b in (parent,child)])
        result['current_path_preservation']=current
        if not current['ok'] or not current['complete'] or current['new_joins']:
            raise ValueError('force_bundle_trace_and_rated_connections_not_preserved')
        current_debt=debt.receive(*paths,board_hint=board_hint)
        result['current_debt_receiving']=current_debt
        if not current_debt['ok'] or not current_debt['complete']:
            raise ValueError('force_bundle_current_debt_changed_or_worsened')
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=timeout_s) for p in paths]
        transforms=[dict(net=net,retired_track_uuids=sorted(force._uid(t) for t in edges),
            retired_via_uuids=[],retired_zone_uuids=sorted(force._uid(z) for z in zones),
            added_track_uuids=[],added_via_uuids=[],added_zone_uuids=[])]
        preservation=sense.compare_contour_preservation(before,after,modified_nets=[net],
            native_copper_transforms=transforms)
        result['physical_preservation']=preservation
        if not preservation['comparison_complete'] or not preservation['same_evidence']:
            raise ValueError('force_bundle_changed_cuts_or_unaffected_evidence_not_preserved')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))-
                field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if delta:raise ValueError('force_bundle_new_native_field_blocker')
        # Removing a zone UUID does not necessarily remove its copper:
        # surviving capsules may cover it. Keep electrical acceptance
        # separate from an actual saved-material witness. Never call an
        # object-count reduction a freed routing corridor.
        changed_faces=sorted({int(i.GetLayer()) for i in selected})
        material=material_delta.compare(parent,child,net=net,layer_ids=changed_faces)
        result['native_material_delta']=material
        if not material['ok'] or not material['complete']:
            raise ValueError('complete_actual_force_bundle_material_delta_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('force_bundle_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),code_identity=epoch,net=net,
            retired_track_uuids=transforms[0]['retired_track_uuids'],
            retired_zone_uuids=transforms[0]['retired_zone_uuids'],added_native_uuids=[],
            native_count_manifest=transforms,actual_physical_terminal_graphs=physical_graphs,
            unchanged_source_current_domain=domain,unchanged_source_current_contract=contract,
            source_sense=before,candidate_sense=after,new_field_blockers=delta,
            exact_native_source_minus_bundle_received=True,
            routing_corridor_freed_not_inferred=True,
            full_native_drc_stack_and_release_receiving_still_required=True)
    except (ValueError,TypeError,KeyError,OSError,physical.Unknown) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
