"""Source-catalogued redundant supply-loop subtraction, not ampacity credit.

Exact caller-owned small full-load traces may be cut only while actual native
connections and every source full-width single-face terminal join survive.
An explicitly named ungrouped barrel may accompany the cut only if the cut
leaves no contacts or contacts on exactly one outer face. Exact on-stroke
shortening may retain a necessary terminal link without keeping its long
obsolete tail. Source loads, copper thicknesses,
width floors and process settings remain fixed. No inferred sharing, new
transition, fill, placement, thermal rating or release authority is granted.
"""
import json,math,time,tempfile
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_current_topology as topology
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_fr as fr
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_copper_echo as syntax
from cec_cell_row_rebuild import _source_binding
from cec_generated_pickup_retirement import _scoped_terminal_partitions
from cec_native_items import discard_items

def _budget(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_supply_loop_deadline_required')
    return time.monotonic()+seconds

def _ids(values,maximum,*,empty=False):
    if (type(values) not in (list,tuple) or not (0 if empty else 1)<=len(values)<=maximum
            or any(type(v) is not str or not v for v in values) or len(set(values))!=len(values)):
        raise ValueError('bounded_unique_literal_supply_loop_inventory_required')
    return sorted(values)

def _contract(board,source,net,hint):
    if type(hint) is not str or not hint or type(net) is not str or not net:
        raise ValueError('explicit_supply_loop_design_basis_required')
    with force._thermal_hint(hint):
        catalog=topology.distributed_supply_contracts(board,hint,
            netclass_resolver=fr._project_netclass_resolver(str(source)))
    contract=catalog['contracts'].get(net)
    if not contract or contract.get('role')!='all_terminal_conservative_aggregate':
        raise ValueError('existing_whole_load_distributed_supply_contract_required')
    authority=contract.get('current_authority') or {}
    if (any(type(authority.get(k)) not in (int,float) or not math.isfinite(authority[k])
            or authority[k]<=0 for k in ('amps','geometry_margin'))
            or type(authority.get('margin_included')) is not bool
            or contract.get('branch_sharing_assumed') is not False
            or not contract.get('routing_layers') or not contract.get('required_by_layer_mm')):
        raise ValueError('unchanged_positive_complete_supply_loop_authority_required')
    return contract

def plan(board,source,*,net,board_hint,track_uuids,via_uuids=(),retained_shortening_nm=(),
         allow_locked_track_uuids=(),allow_locked_via_uuids=(),timeout_s=10.,
         allow_source_inner_layers=False):
    deadline=_budget(timeout_s)
    tracks=_ids(track_uuids,32);vias=_ids(via_uuids,4,empty=True)
    locks=_ids(allow_locked_track_uuids,32,empty=True);vlocks=_ids(allow_locked_via_uuids,4,empty=True)
    if not set(locks)<=set(tracks) or not set(vlocks)<=set(vias) or set(tracks)&set(vias):
        raise ValueError('literal_supply_loop_lock_scope_required')
    contract=_contract(board,source,net,board_hint)
    if type(allow_source_inner_layers) is not bool:
        raise ValueError('explicit_supply_loop_source_inner_face_policy_required')
    allowed_faces={pcbnew.F_Cu,pcbnew.B_Cu}
    if allow_source_inner_layers:
        allowed_faces={int(board.GetLayerID(name)) for name in contract['routing_layers']}
        allowed_faces &= set(map(int,board.GetEnabledLayers().CuStack()))
        allowed_faces -= {int(board.GetLayerID(name)) for name in fr.plane_layers(board)
            if int(board.GetLayerID(name)) not in (pcbnew.F_Cu,pcbnew.B_Cu)}
    live={force._uid(t):t for t in board.GetTracks()}
    if (type(retained_shortening_nm) not in (list,tuple) or len(retained_shortening_nm)>4
            or any(type(r) is not dict or set(r)!={'uuid','start_nm','end_nm','locked_source_requested'}
                or type(r['uuid']) is not str or not r['uuid'] or type(r['locked_source_requested']) is not bool for r in retained_shortening_nm)
            or len({r['uuid'] for r in retained_shortening_nm})!=len(retained_shortening_nm)
            or any(r['uuid'] in tracks+vias for r in retained_shortening_nm)):
        raise ValueError('bounded_literal_retained_supply_shortening_required')
    trims=[]
    for row in sorted(retained_shortening_nm,key=lambda r:r['uuid']):
        item=live.get(row['uuid']);face=fab.COPPER_LAYER_IDS.get(item.GetLayer()) if item else None
        floor=contract['required_by_layer_mm'].get(face)
        if (item is None or item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net
                or item.GetParentGroup() is not None or item.IsLocked() and not row['locked_source_requested']
                or item.GetLayer() not in allowed_faces
                or face not in contract['routing_layers'] or type(floor) not in (int,float)
                or not math.isfinite(floor) or not 0<floor<=1
                or not math.ceil(floor*1e6)<=item.GetWidth()<=1000000
                or not 0<item.GetLength()<=32000000):
            raise ValueError('retained_shortening_full_load_source_track_required')
        start,end=map(tuple,(item.GetStart(),item.GetEnd()));dx,dy=end[0]-start[0],end[1]-start[1]
        length2=dx*dx+dy*dy;projections=[]
        for at in (row['start_nm'],row['end_nm']):
            if type(at) is not list or len(at)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in at):
                raise ValueError('literal_integer_supply_shortening_endpoints_required')
            x,y=at[0]-start[0],at[1]-start[1];dot=x*dx+y*dy
            if x*dy!=y*dx or not 0<=dot<=length2:
                raise ValueError('retained_supply_shortening_must_stay_on_exact_source_stroke')
            projections.append(dot)
        if not 0<projections[1]-projections[0]<length2:
            raise ValueError('strict_positive_nonreversed_supply_shortening_required')
        trims.append(dict(uuid=row['uuid'],source_start_nm=list(start),source_end_nm=list(end),
            start_nm=row['start_nm'],end_nm=row['end_nm'],width_nm=item.GetWidth(),
            layer_id=int(item.GetLayer()),locked=bool(item.IsLocked()),locked_source_requested=row['locked_source_requested']))
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(live)+len(pads)+len(zones)>16384:raise ValueError('supply_loop_material_inventory_bound')
    cuts=[];length=0
    for uid in tracks:
        if time.monotonic()>=deadline:raise ValueError('supply_loop_plan_deadline')
        item=live.get(uid);face=fab.COPPER_LAYER_IDS.get(item.GetLayer()) if item else None
        width=(contract['required_by_layer_mm'].get(face) if face else None)
        if (item is None or item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net
                or item.GetParentGroup() is not None or item.IsLocked() and uid not in locks
                or item.GetLayer() not in allowed_faces
                or face not in contract['routing_layers'] or type(width) not in (int,float)
                or not math.isfinite(width) or not 0<width<=1
                or not math.ceil(width*1e6)<=item.GetWidth()<=1000000
                or not 0<item.GetLength()<=32000000):
            raise ValueError('exact_small_full_load_ungrouped_supply_trace_required:'+uid)
        length+=item.GetLength()
        cuts.append(dict(uuid=uid,layer_id=int(item.GetLayer()),width_nm=int(item.GetWidth()),
            start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),locked=bool(item.IsLocked())))
    if length>256000000:raise ValueError('supply_loop_total_length_bound')
    contacts=[];faces=tuple(board.GetEnabledLayers().CuStack())
    for uid in vias:
        via=live.get(uid)
        if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!=net
                or via.GetParentGroup() is not None or via.IsLocked() and uid not in vlocks
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
                or not 0<via.GetDrillValue()<via.GetWidth(via.TopLayer())):
            raise ValueError('literal_source_supply_loop_through_barrel_required')
        retained=[];old=[];retained_faces=set()
        for item in [*live.values(),*pads,*zones]:
            if time.monotonic()>=deadline:raise ValueError('supply_loop_post_cut_barrel_deadline')
            other=force._uid(item)
            if other==uid:continue
            touched=[]
            for face in faces:
                if not item.IsOnLayer(face):continue
                if item.GetClass()=='ZONE':
                    if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                        if item.Outline().Collide(via.GetEffectiveShape(face),0):
                            raise ValueError('supply_loop_barrel_contact_fill_unknown')
                        continue
                    material=item.GetFilledPolysList(face)
                else:material=item.GetEffectiveShape(face)
                if via.GetEffectiveShape(face).Collide(material,0):touched.append(int(face))
            if not touched:continue
            if item.GetNetname()!=net or item.GetClass()=='PCB_VIA':
                raise ValueError('supply_loop_barrel_foreign_or_other_barrel_contact')
            row=dict(uuid=other,kind=item.GetClass(),face_ids=touched)
            old.append(row)
            if other not in tracks:
                retained.append(row);retained_faces.update(touched)
        orphaned=bool(old) and not retained and all(r['uuid'] in tracks for r in old)
        single_face=bool(retained) and len(retained_faces)==1 and next(iter(retained_faces)) in (pcbnew.F_Cu,pcbnew.B_Cu)
        if not (orphaned or single_face) or not any(r['uuid'] in tracks for r in old):
            raise ValueError('supply_loop_cut_must_leave_orphan_or_one_outer_barrel_contact_face')
        contacts.append(dict(uuid=uid,position_nm=list(via.GetPosition()),
            diameter_nm=via.GetWidth(via.TopLayer()),drill_nm=via.GetDrillValue(),locked=bool(via.IsLocked()),
            original_contacts=sorted(old,key=lambda r:r['uuid']),
            retained_contacts=sorted(retained,key=lambda r:r['uuid']),retained_face_ids=sorted(retained_faces),
            all_original_contacts_are_exact_cut=orphaned))
    return dict(schema=1,scope='exact_source_catalogued_supply_loop_cut',source_binding=_source_binding(board),
        source=str(Path(source).resolve()),net=net,board_hint=board_hint,contract=contract,
        track_uuids=tracks,via_uuids=vias,retained_shortening_nm=[{k:r[k] for k in ('uuid','start_nm','end_nm','locked_source_requested')} for r in trims],
        retained_shortening_source=trims,allow_locked_track_uuids=locks,allow_locked_via_uuids=vlocks,
        allow_source_inner_layers=allow_source_inner_layers,
        source_tracks=cuts,source_barrels=contacts,removed_length_nm=length+sum(
            math.dist(r['source_start_nm'],r['source_end_nm'])-math.dist(r['start_nm'],r['end_nm']) for r in trims),
        independent_saved_receiving_required=True,current_qualified=False,release_authority=False)

def rederive_saved_plan(board,proposal):
    """Reconstruct SOURCE authority at the JSON boundary, never trust flags.

    Real catalog layer tuples become JSON arrays on disk. Re-derive the
    complete actual plan and require exact canonical JSON equality, then
    return the fresh native-Python plan to the unchanged strict receivers.
    No geometry, number, margin, role or source-binding change is normalized.
    This read-only helper itself grants no saved-candidate admission.
    """
    if type(proposal) is not dict:raise ValueError('literal_saved_supply_loop_plan_required')
    fresh=plan(board,proposal['source'],net=proposal['net'],board_hint=proposal['board_hint'],
        **{k:proposal[k] for k in ('track_uuids','via_uuids','retained_shortening_nm','allow_locked_track_uuids','allow_locked_via_uuids')},
        allow_source_inner_layers=proposal.get('allow_source_inner_layers',False))
    def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if canonical(fresh)!=canonical(proposal):
        raise ValueError('saved_supply_loop_plan_does_not_match_actual_source')
    return fresh


def subtract(board,proposal):
    fresh=plan(board,proposal['source'],net=proposal['net'],board_hint=proposal['board_hint'],
        **{k:proposal[k] for k in ('track_uuids','via_uuids','retained_shortening_nm','allow_locked_track_uuids','allow_locked_via_uuids')},
        allow_source_inner_layers=proposal.get('allow_source_inner_layers',False))
    if fresh!=proposal:raise ValueError('source_supply_loop_stale_or_forged_proposal')
    cuts=set(proposal['track_uuids']+proposal['via_uuids'])
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in cuts])
    live={force._uid(t):t for t in board.GetTracks()}
    for row in proposal['retained_shortening_nm']:
        item=live[row['uuid']];item.SetStart(pcbnew.VECTOR2I(*row['start_nm']));item.SetEnd(pcbnew.VECTOR2I(*row['end_nm']))

def full_width_face_joins(board,net,contract,*,timeout_s=10.):
    """Only native common-face lands and complete-load traces, no barrels/fills."""
    deadline=_budget(timeout_s);pads=supply._pads(board,net);joined=set();records=[]
    if not 2<=len(pads)<=64:raise ValueError('bounded_supply_loop_actual_terminal_inventory_required')
    for name in contract['routing_layers']:
        if time.monotonic()>=deadline:raise ValueError('supply_loop_full_width_face_deadline')
        face=board.GetLayerID(name)
        if face not in board.GetEnabledLayers().CuStack():raise ValueError('supply_loop_contract_face_missing')
        actual=[p for p in pads if p.IsOnLayer(face) and p.FlashLayer(face)]
        if not actual:continue
        one=dict(contract,routing_layers=[name])
        if supply._surface_layer(board,actual,one)!=face:
            raise ValueError('supply_loop_actual_single_face_lands_unknown')
        floor=contract['required_by_layer_mm'].get(name)
        if type(floor) not in (int,float) or not math.isfinite(floor) or floor<=0:
            raise ValueError('supply_loop_full_width_face_floor_missing')
        tracks=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net
            and t.GetLayer()==face and t.GetWidth()>=math.ceil(floor*1e6)]
        parts=supply._face_partition(actual,tracks,face)
        for part in parts:
            for i,left in enumerate(part):
                joined.update(tuple(sorted((left,right))) for right in part[i+1:])
        records.append(dict(layer_id=int(face),floor_nm=math.ceil(floor*1e6),terminal_partitions=parts))
    return dict(pad_uuids=sorted(force._uid(p) for p in pads),face_records=records,
        joined_terminal_pairs=[list(p) for p in sorted(joined)],no_barrel_or_zone_capacity_credited=True)

def receive(source,candidate,proposal,*,board_hint):
    result=dict(schema=1,ok=False,complete=False,errors=[],current_qualified=False,
        thermal_qualified=False,plated_capacity_qualified=False,release_authority=False,
        full_native_drc_field_current_stack_receiving_still_required=True)
    try:
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1] or str(paths[0])!=proposal['source'] or board_hint!=proposal['board_hint']:
            raise ValueError('distinct_exact_source_supply_loop_paths_required')
        families=[force._family(p,board_hint) for p in paths];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        fresh=plan(parent,paths[0],net=proposal['net'],board_hint=board_hint,
            **{k:proposal[k] for k in ('track_uuids','via_uuids','retained_shortening_nm','allow_locked_track_uuids','allow_locked_via_uuids')},
            allow_source_inner_layers=proposal.get('allow_source_inner_layers',False))
        if fresh!=proposal:raise ValueError('fresh_supply_loop_source_proposal_differs')
        if _contract(child,paths[1],proposal['net'],board_hint)!=proposal['contract']:
            raise ValueError('source_supply_loop_load_or_width_authority_changed')
        cuts=set(proposal['track_uuids']+proposal['via_uuids'])
        # A zone UUID is not one conductor: each saved filled island/face
        # remains an independent native node. The old single-island helper
        # cannot receive ordinary six-layer boards, even when the supply cut
        # is unrelated to their multi-face Ground fills. Compare actual
        # paired native partitions, retaining every surviving copper node.
        import cec_native_partition_pair as partitions
        paired=partitions.compare(parent,child,timeout_s=10.,retired_uuids=cuts)
        result['paired_native_partition_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('supply_loop_surviving_native_partition_lost')
        joins=[full_width_face_joins(b,proposal['net'],proposal['contract']) for b in (parent,child)]
        if joins[0]['pad_uuids']!=joins[1]['pad_uuids'] or not set(map(tuple,joins[0]['joined_terminal_pairs']))<=set(map(tuple,joins[1]['joined_terminal_pairs'])):
            raise ValueError('source_full_load_single_face_terminal_join_lost')
        actual=[_scoped_terminal_partitions(b,proposal['net']) for b in (parent,child)]
        if actual[0]['pad_identities']!=actual[1]['pad_identities']:
            raise ValueError('supply_loop_actual_drilled_terminal_inventory_changed')
        if not all(any(set(part)<=set(other)for other in actual[1]['actual_terminal_partitions'])
                for part in actual[0]['actual_terminal_partitions']):
            raise ValueError('supply_loop_actual_drilled_terminal_partition_lost')
        with tempfile.TemporaryDirectory(prefix='cec-supply-loop-replay-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'expected')
            rebuilt=pcbnew.LoadBoard(str(expected));subtract(rebuilt,proposal)
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,expected)
            _,exact=additive._nodes(expected);_,saved=additive._nodes(paths[1])
            if exact.keys()!=saved.keys() or any(syntax._freeze(exact[u])!=syntax._freeze(saved[u]) for u in exact):
                raise ValueError('exact_supply_loop_subtraction_and_refill_replay_differs')
            if force._preservation_snapshot(expected)[1]!=force._preservation_snapshot(paths[1])[1] or force._sidecars(expected)!=force._sidecars(paths[1]):
                raise ValueError('supply_loop_settings_or_source_authority_sidecars_changed')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('supply_loop_code_or_inputs_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            source_candidate_and_code_unchanged=True,code_identity=epoch,source_contract_preserved=True,
            surviving_native_partitions_preserved=True,full_width_face_joins=dict(source=joins[0],candidate=joins[1]),
            actual_drilled_terminal_graphs=dict(source=actual[0],candidate=actual[1]),
            incomplete_source_supply_not_qualified=actual[0]['incomplete_terminal_connectivity_not_qualified'],
            removed_track_uuids=proposal['track_uuids'],removed_via_uuids=proposal['via_uuids'])
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
