"""Receive an exact owned force-trace replacement, without current sharing.

Native saved items, not a worker's success flag, define the cut and additions.
Both absolute Kelvin cuts must pass on changed positive legs; unknown legs
remain strict. This grants neither barrel ampacity nor fabrication release.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_collector_reconstruction as collector
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_current_topology as topology
import cec_native_supply_via_context as web
import cec_native_partition_pair as partitions
import cec_route_quality as craft
import cec_fab_profile as fab


def evidence_replay_budget(value):
    """Explicit bounded proof work, never permission to accept an unknown."""
    if (type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=60.):
        raise ValueError('bounded_absolute_force_evidence_budget_required')
    return float(value)


def native_scope(parent, child, retired, *, max_source_leg_mm=32.):
    """Read-only exact single-net ungrouped cut and fresh conductor inventory."""
    # This is a finite geometry-work bound, not an electrical rule. Keep the
    # default while allowing explicit larger-board reconstructions; all
    # current, native partition, field and absolute Kelvin checks stay below.
    if (type(max_source_leg_mm) not in (int,float) or not math.isfinite(max_source_leg_mm)
            or not 0<max_source_leg_mm<=128.):
        raise ValueError('bounded_explicit_source_leg_work_limit_required')
    if (not isinstance(retired,(list,tuple,set,frozenset)) or not 1<=len(retired)<=32
            or any(type(u) is not str or not u for u in retired)
            or len(retired)!=len(set(retired))):
        raise ValueError('bounded_unique_owned_force_trace_cut_required')
    old={force._uid(t):t for t in parent.GetTracks()}
    new={force._uid(t):t for t in child.GetTracks()}
    if (len(old)!=len(list(parent.GetTracks())) or len(new)!=len(list(child.GetTracks()))
            or len(old)>16384 or len(new)>16384 or not set(retired)<=old.keys()
            or old.keys()-new.keys()!=set(retired)):
        raise ValueError('exact_native_force_replacement_inventory_required')
    net=str(old[next(iter(retired))].GetNetname())
    cut, proof=collector.owned_retirement(parent,net,track_uuids=retired)
    added=[new[u] for u in sorted(new.keys()-old.keys())]
    if (not 1<=len(added)<=256 or any(t.GetClass() not in ('PCB_TRACK','PCB_VIA')
            or t.GetNetname()!=net or t.GetParentGroup() is not None for t in added)):
        raise ValueError('bounded_same_net_fresh_force_conductors_required')
    if any(t.GetWidth()<=0 for t in cut):
        raise ValueError('positive_owned_source_force_width_required')
    if (any(t.GetLength()>max_source_leg_mm*1e6 for t in cut)
            or sum(t.GetLength() for t in cut)>1024000000):
        raise ValueError('owned_source_force_leg_geometry_work_bound')
    return net,cut,added,proof


def require_track_floor(board,item,contract,source_width_nm):
    """Receive the actual face's full budget and the largest authored cut width."""
    if type(source_width_nm) is not int or source_width_nm<=0 or item.GetClass()!='PCB_TRACK':
        raise ValueError('positive_source_trace_floor_required')
    layer=int(item.GetLayer());face=fab.COPPER_LAYER_IDS[layer]
    floor=contract.get('required_by_layer_mm',{}).get(face)
    if (layer not in board.GetEnabledLayers().CuStack()
            or layer in {board.GetLayerID(n) for n in fr.plane_layers(board)}
            or face not in fab.routing_layers(board,include_power=True)
            or face not in contract.get('routing_layers',())
            or type(floor) not in (int,float) or not math.isfinite(floor) or floor<=0
            or str(item.GetNetname())!=contract.get('net')
            or item.GetWidth()<max(source_width_nm,math.ceil(floor*1e6))):
        raise ValueError('complete_source_and_authored_force_width_required')
    return max(source_width_nm,math.ceil(floor*1e6))


def count_manifest(net,retired,added):
    """KiCad's PCB_TRACK inventory INCLUDES vias; via IDs are its subset."""
    incoming=sorted(force._uid(t) for t in added)
    return [dict(net=net,retired_track_uuids=sorted(retired),
        added_track_uuids=incoming,retired_via_uuids=[],
        added_via_uuids=sorted(force._uid(t) for t in added if t.GetClass()=='PCB_VIA'),
        added_zone_uuids=[])]


def preserve_native_partitions(parent,child,retired_track_uuids,*,timeout_s=10.):
    """Compare every real Source island across the independently owned refill.

    Exact old polygon hashes are not retained conductor identities after a
    lawful native refill. Positive per-island overlap tokens still require
    every old pad, copper-only junction and Source island to survive. A zone
    UUID never bridges split islands. This grants no fill/delta/current scope;
    receive() first replays the exact Source cut, additions and Ground refill.
    """
    proof=partitions.compare(parent,child,retired_uuids=retired_track_uuids,timeout_s=timeout_s)
    if (proof.get('available')is not True or proof.get('preserved')is not True
            or proof.get('exact_positive_native_island_overlap')is not True
            or proof.get('whole_zone_uuid_connectivity_credit')is not False):
        raise ValueError('original_retained_native_force_partition_lost')
    return proof


def receive(source,candidate,retired_track_uuids,*,board_hint,max_source_leg_mm=32.,sense_timeout_s=10.):
    result=dict(schema=1,scope='fresh_exact_owned_force_crossface_receiving',
        ok=False,complete=False,errors=[],source_current_reduced=False,
        branch_sharing_assumed=False,new_capacity_credited=False,
        unknown_evidence_qualified=False,plated_barrel_current_qualified=False,
        fab_ready=False,release_authority=False)
    try:
        sense_timeout_s=evidence_replay_budget(sense_timeout_s)
        if type(board_hint) is not str or not board_hint:
            raise ValueError('explicit_force_board_context_required')
        paths=[Path(q).resolve() for q in (source,candidate)]
        epoch=force._code_identity();families=[force._family(q,board_hint) for q in paths]
        parent,child=[pcbnew.LoadBoard(str(q)) for q in paths]
        net,cut,added,ownership=native_scope(parent,child,retired_track_uuids,
            max_source_leg_mm=max_source_leg_mm)
        result['source_leg_geometry_work_limit_mm']=max_source_leg_mm
        root,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        retired=set(retired_track_uuids);incoming={force._uid(t) for t in added}
        if old.keys()-new.keys()!=retired or new.keys()-old.keys()!=incoming:
            raise ValueError('force_replacement_cannot_change_other_native_items')
        if (force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('force_replacement_source_metadata_or_sidecars_changed')
        with force._thermal_hint(board_hint):
            domains=topology.board_current_domains(parent,board_hint)
            contract=topology.route_width_contracts(parent,board_hint=board_hint).get(net)
        domain=domains.get(net)
        if not domain or not domain['complete'] or domain['missing_refs'] or not contract:
            raise ValueError('positive_complete_existing_force_domain_required')
        source_width=max(t.GetWidth() for t in cut)
        for item in added:
            if item.GetClass()=='PCB_TRACK':
                require_track_floor(parent,item,contract,source_width)
        # Rebuild exactly source-minus-owned-cut plus the ACTUAL fresh items
        # and deterministic native ground refill. Every unrelated shape, pad,
        # footprint, property and keeper must survive byte-for-byte replay.
        with tempfile.TemporaryDirectory(prefix='cec-force-crossface-receiving-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            rebuilt_root=[root[0],*[node for node in root[1:] if not (
                isinstance(node,list) and next((str(x[1]).strip('"') for x in node if isinstance(x,list)
                    and len(x)>1 and x[0]=='uuid'),None) in retired)],
                *[new[u] for u in sorted(incoming)]]
            expected.write_text(additive._render(rebuilt_root)+'\n')
            rebuilt=pcbnew.LoadBoard(str(expected));rebuilt.SetFileName(str(expected))
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,expected)
            _,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('exact_force_reconstruction_and_native_ground_refill_differs')
        partition_proof=preserve_native_partitions(parent,child,retired,timeout_s=10.)
        result['native_partition_preservation']={k:v for k,v in partition_proof.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        web_proofs=[web.receive(child,force._uid(t),contract,timeout_s=2.)
            for t in added if t.GetClass()=='PCB_VIA']
        if not all(q['ok'] and q['complete'] for q in web_proofs):
            raise ValueError('actual_full_source_two_face_contact_web_required')
        debt=current.receive(*paths,board_hint=board_hint)
        if not debt['ok'] or not debt['complete']:
            raise ValueError('unchanged_source_current_debt_required')
        quality=craft.analyze_board(child,track_uuid_scope=incoming)
        if not quality['craft_ok']:
            raise ValueError('canonical_source_force_route_craft_required')
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if delta:raise ValueError('new_native_force_field_blocker')
        before,after=[sense.replay(q,board_hint=board_hint,timeout_s=sense_timeout_s) for q in paths]
        result['absolute_evidence_replay_budget_s']=sense_timeout_s
        result['absolute_evidence_replay_completion']=[dict(complete=q['complete'],
            identity_stable=q['identity_stable'],stop=q['stop']) for q in (before,after)]
        transforms=count_manifest(net,retired,added)
        preservation=sense.compare_contour_preservation(before,after,modified_nets=[net],
            native_copper_transforms=transforms)
        result['physical_preservation']=preservation
        if not preservation['comparison_complete'] or not preservation['same_evidence']:
            raise ValueError('two_absolute_changed_cuts_and_strict_unaffected_evidence_required:'+str(preservation.get('errors')))
        stable=epoch==force._code_identity() and families==[force._family(q,board_hint) for q in paths]
        if not stable:raise ValueError('force_reconstruction_source_family_or_code_changed')
        result.update(ok=True,complete=True,net=net,exact_owned_cut=ownership,
            source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_family_and_code_unchanged=True,
            preserved_authored_source_width_nm=source_width,
            unchanged_source_current_contract=contract,incoming_uuids=sorted(incoming),
            exact_native_reconstruction_and_ground_refill=True,
            original_retained_partitions_restored=True,actual_full_web_contacts=web_proofs,
            whole_source_current_receiving=debt,new_route_craft=quality,
            physical_preservation=preservation,new_field_blockers=delta,
            fresh_uncapped_native_fifty_checks_stack_and_outline_receiving_still_required=True)
    except (ValueError,KeyError,TypeError,StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
