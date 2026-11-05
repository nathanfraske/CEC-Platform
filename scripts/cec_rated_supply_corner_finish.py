"""Bounded full-load supply-corner finishing, never ordinary reclassification.

Geometry comes from the existing contact-preserving native miter constructor.
Electrical ownership comes independently from the saved source's complete
distributed-supply contract. Main force nets, plane routes, new holes, poses,
load changes and current-sharing assumptions are outside this operation.
"""
from collections import Counter
import copy
import json
from pathlib import Path
import math
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_rated_branch_repair as rated
import cec_scalar_corner_stage as geometry
import cec_fab_profile as fab


def _catalog(board,source,hint):
    with force._thermal_hint(hint):
        catalog=topology.distributed_supply_contracts(board,hint,
            netclass_resolver=fr._project_netclass_resolver(str(source)))
        force_nets=set(topology.board_current_domains(board,hint))
    result={}
    for net,contract in catalog['contracts'].items():
        authority=contract.get('current_authority') or {}
        if (net in force_nets or net=='GND' or contract.get('role')!='all_terminal_conservative_aggregate'
                or contract.get('branch_sharing_assumed') is not False
                or type(authority.get('margin_included')) is not bool
                or any(type(authority.get(k)) not in (int,float) or not math.isfinite(authority[k])
                    or authority[k]<=0 for k in ('amps','geometry_margin'))):continue
        result[net]=contract
    return result


def discover(board,source,*,board_hint,allow_locked_source=False,include_source_inner_layers=False,
             minimum_nm=50000,maximum_nm=200000):
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool
            or type(include_source_inner_layers) is not bool
            or type(minimum_nm) is not int or type(maximum_nm) is not int
            or not 1<=minimum_nm<=maximum_nm<=2000000
            or Path(source).resolve()!=Path(board.GetFileName()).resolve()):
        raise ValueError('explicit_bounded_rated_supply_finishing_context_required')
    contracts=_catalog(board,source,board_hint);inventory=geometry.inventory(board,set(contracts),
        minimum_nm=minimum_nm,maximum_nm=maximum_nm)
    live={force._uid(t):t for t in board.GetTracks()};selected=[];refusals=Counter()
    planes={int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    for row in inventory['selected']:
        items=[live[u] for u in row['source_track_uuids']];contract=contracts[row['net']]
        face=int(items[0].GetLayer());canonical=fab.COPPER_LAYER_IDS.get(face)
        floor=contract.get('required_by_layer_mm',{}).get(board.GetLayerName(face),
            contract.get('required_by_layer_mm',{}).get(canonical))
        permitted=(face in (pcbnew.F_Cu,pcbnew.B_Cu) or include_source_inner_layers and face not in planes
            and canonical in contract.get('routing_layers',()))
        if (not permitted or type(floor) not in (int,float) or not math.isfinite(floor) or floor<=0
                or any(t.HasSolderMask() or t.GetParentGroup() or t.GetLength()>32000000
                    or t.IsLocked() and not allow_locked_source
                    or not math.ceil(floor*1e6)<=t.GetWidth()<=499000 for t in items)):
            refusals['outside_exact_full_load_source_process_or_face']=refusals.get('outside_exact_full_load_source_process_or_face',0)+1
            continue
        selected.append(row)
    return dict(complete=True,requests=selected,contracts=contracts,geometric_inventory=inventory,
        refusals=dict(refusals),source_mutated=False,ordinary_role_inferred=False,
        inherited_debt_qualified=False,release_authority=False)


def plan(board,source,requests,*,board_hint,allow_locked_source=False,include_source_inner_layers=False,
         minimum_nm=50000,maximum_nm=200000):
    if type(requests) is not list or not 1<=len(requests)<=16:
        raise ValueError('bounded_explicit_rated_supply_corner_batch_required')
    inventory=discover(board,source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        include_source_inner_layers=include_source_inner_layers,minimum_nm=minimum_nm,maximum_nm=maximum_nm)
    if any(r not in inventory['requests'] for r in requests) or len({repr(r) for r in requests})!=len(requests):
        raise ValueError('literal_source_rated_supply_corner_requests_required')
    ids=sorted({u for r in requests for u in r['source_track_uuids']})
    if len(ids)>32:raise ValueError('bounded_rated_supply_corner_track_scope_required')
    typed=rated.plan(board,Path(source),board_hint=board_hint,retired_track_uuids=ids,
        max_source_track_mm=32.,max_retired_tracks=32,max_source_width_mm=.499,
        allow_rated_source_inner_layers=include_source_inner_layers)
    return dict(schema=1,source_sha256=force._hash(Path(source)),source_binding=binding._source_binding(board),
        requests=copy.deepcopy(requests),contracts=json.loads(json.dumps(typed['contracts'],allow_nan=False)),allow_locked_source=allow_locked_source,
        include_source_inner_layers=include_source_inner_layers,minimum_nm=minimum_nm,maximum_nm=maximum_nm,
        full_source_load_preserved=True,ordinary_role_inferred=False,current_qualified=False,release_authority=False)


def materialize(board,source,proposal,*,board_hint):
    fresh=plan(board,source,proposal['requests'],board_hint=board_hint,
        **{k:proposal[k] for k in ('allow_locked_source','include_source_inner_layers','minimum_nm','maximum_nm')})
    if fresh!=proposal:raise ValueError('stale_or_forged_rated_supply_corner_plan')
    result=geometry.construct(board,proposal['requests'],set(proposal['contracts']),
        allow_locked_source=proposal['allow_locked_source'],minimum_nm=proposal['minimum_nm'],
        maximum_nm=proposal['maximum_nm'],timeout_s=10.)
    if not result['chamfered']:raise ValueError('no_actual_contact_preserving_rated_supply_corner_change')
    return dict(result,added_native_uuids=sorted(result['incoming_source_owners']),
        generic_geometry_is_not_ordinary_net_authority=True,release_authority=False)


def _signature(node):
    return syntax._freeze([q for q in node if not (isinstance(q,list) and q and q[0]=='uuid')])


def _header(root,nodes):
    # _nodes returns the complete root too. Compare its non-item settings
    # separately: fresh native item UUIDs are matched by their COMPLETE
    # process/geometry signatures below, never by a weakened geometry hash.
    owned={id(n) for n in nodes.values()}
    return syntax._freeze([q for q in root if id(q) not in owned])


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False,
        whole_current_fields_absolute_Kelvin_native_DRC_stack_and_release_still_required=True)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        parent=pcbnew.LoadBoard(str(source))
        fresh=plan(parent,source,proposal['requests'],board_hint=board_hint,
            **{k:proposal[k] for k in ('allow_locked_source','include_source_inner_layers','minimum_nm','maximum_nm')})
        if fresh!=proposal:raise ValueError('saved_rated_supply_corner_source_plan_changed')
        _,old=additive._nodes(source);got_root,got=additive._nodes(candidate)
        retired=set(old)-set(got);added=set(got)-set(old)
        if not retired or not added or any(got[u][0]!='segment' for u in added):
            raise ValueError('rated_supply_corner_track_only_native_delta_required')
        with tempfile.TemporaryDirectory(prefix='cec-rated-supply-corner-') as tmp:
            expected_path=force._copy_family(source,Path(tmp)/'expected')
            expected=pcbnew.LoadBoard(str(expected_path))
            q=plan(expected,expected_path,proposal['requests'],board_hint=board_hint,
                **{k:proposal[k] for k in ('allow_locked_source','include_source_inner_layers','minimum_nm','maximum_nm')})
            made=materialize(expected,expected_path,q,board_hint=board_hint)
            field._save_field_snapshot(expected,expected_path);want_root,want=additive._nodes(expected_path)
            want_added=set(want)-set(old)
            if (_header(want_root,want)!=_header(got_root,got) or retired!=set(made['retired_track_uuids'])
                    or set(want)&set(old)!=set(got)&set(old)
                    or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in set(want)&set(old))
                    or Counter(_signature(want[u]) for u in want_added)!=Counter(_signature(got[u]) for u in added)):
                raise ValueError('exact_independent_saved_rated_supply_corner_replay_differs')
        if force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('rated_supply_corner_source_sidecars_changed')
        # This is a separate full-load electrical owner, not the geometry
        # constructor's ordinary receiver. Wider source branches/inner faces
        # still require their original complete layer-specific load floors.
        proof=rated.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),
            max_source_track_mm=32.,max_retired_tracks=32,max_source_width_mm=.499,
            max_replacement_width_mm=.499,allow_rated_layer_bridges=True,
            allow_rated_source_inner_layers=proposal['include_source_inner_layers'])
        result['independent_full_source_load_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('full_load_rated_supply_corner_receiving_refused:'+str(proof['errors']))
        live0={force._uid(t):t for t in parent.GetTracks()};child=pcbnew.LoadBoard(str(candidate))
        live1={force._uid(t):t for t in child.GetTracks()}
        before=sum(live0[u].GetLength() for u in retired);after=sum(live1[u].GetLength() for u in added)
        if not after<before:raise ValueError('rated_supply_corner_must_strictly_reduce_trace_length')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('rated_supply_corner_sources_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),
            chamfered=made['chamfered'],source_length_nm=before,replacement_length_nm=after,
            saved_trace_length_mm=(before-after)/1e6,ordinary_reclassification=False,new_barrels=0,
            exact_saved_geometry_replay=True,full_source_current_and_margins_unchanged=True,
            main_force_buses_pads_poses_planes_and_rules_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
