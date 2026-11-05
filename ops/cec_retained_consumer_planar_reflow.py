"""Same-width planar repair of a source-proved retained consumer island.

Generation history is not current authority: the unchanged native consumer
receiver already derives the exclusive retained island and its exact floor.
This owner touches only positively identified UNGROUPED tracks in that island.
The allocation group, source tap, loads, parts, vias and rules remain exact.
"""
import math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as craft
import cec_supply_consumer_branch as consumer
from cec_native_items import discard_items


def require(condition,message):
    if not condition:raise ValueError(message)


def plan(board,source,*,board_hint,retired_track_uuids,timeout_s=10.):
    require(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0<timeout_s<=10
        and type(board_hint) is str and bool(board_hint),'bounded_retained_consumer_context_required')
    digest=force._hash(Path(__file__));ids=ordinary._ids(retired_track_uuids,'retained_consumer_island_cut',16)
    require(bool(ids),'nonempty_retained_consumer_cut_required')
    inventory=consumer.inventory(board,board_hint=board_hint,timeout_s=timeout_s)
    require(inventory['complete'],'complete_positive_retained_consumer_inventory_required')
    proofs=[q for q in inventory['proofs'] if ids<=q['retained_island_track_requirements'].keys()]
    require(len(proofs)==1,'one_positive_native_retained_consumer_island_required')
    proof=proofs[0];live={force._uid(t):t for t in board.GetTracks()}
    require(ids<=live.keys(),'actual_retained_consumer_source_tracks_required');old=[live[u] for u in sorted(ids)]
    grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    require(not ids&grouped and all(t.GetClass()=='PCB_TRACK' and t.GetNetname()==proof['net']
        and t.GetParentGroup() is None and not t.HasSolderMask() and 0<t.GetLength()<=32000000 for t in old)
        and len({(int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'uniform_ungrouped_retained_consumer_face_width_and_process_required')
    groups=[g for g in board.Groups() if g.GetName().startswith(consumer.PREFIX)
        and g.GetName()[len(consumer.PREFIX):].split('|')[:2]==[proof['root_pad_uuid'],proof['anchor_uuid']]]
    require(len(groups)==1 and groups[0].GetParentGroup() is None,'exact_unnested_retained_allocation_group_required')
    group=groups[0];face=int(old[0].GetLayer());canonical=fab.COPPER_LAYER_IDS[face];width=old[0].GetWidth()
    planes={board.GetLayerID(name) for name in fr.plane_layers(board)}
    allowed={board.GetLayerID(name) for name in fab.routing_layers(board,include_power=True)}
    require(face in board.GetEnabledLayers().CuStack() and face in allowed and face not in planes,
        'actual_enabled_nonplane_retained_consumer_face_required')
    req=proof['retained_island_track_requirements'];floors=[req[u]['required_mm'] for u in ids]
    require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in floors),
        'positive_actual_retained_consumer_face_floors_required')
    spec=fr._project_netclass_resolver(str(source),board=board)(proof['net']) or {}
    floor=max(*(math.ceil(v*1e6) for v in floors),board.GetDesignSettings().m_TrackMinWidth,
        math.ceil(float(spec.get('track_width') or 0)*1e6),
        math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(canonical) or 0)*1e6))
    require(floor<=width<=1000000 and sum(t.GetLength() for t in old)<=64000000,
        'retained_consumer_source_must_already_carry_its_full_actual_floor')
    require(digest==force._hash(Path(__file__)),'retained_consumer_authority_changed')
    return dict(schema=1,source_sha256=force._hash(source),authority_sha256=digest,net=proof['net'],
        group_uuid=force._uid(group),source_group_name=group.GetName(),source_group_members=sorted(force._uid(t) for t in group.GetItems()),
        root_pad_uuid=proof['root_pad_uuid'],anchor_uuid=proof['anchor_uuid'],source_budget=proof['budget'],
        retired_track_uuids=sorted(ids),actual_face_id=face,actual_face=canonical,source_width_nm=width,
        actual_face_floor_nm=floor,source_locked=bool(old[0].IsLocked()),source_has_solder_mask=False,
        source_boundaries=ordinary._boundaries(board,board,old,time.monotonic()+timeout_s),
        source_current_reduced=False,branch_sharing_assumed=False,allocation_group_changed=False,
        private_intermediate_not_an_admission_baseline=True,release_authority=False)


def unchanged_group(board,scope):
    rows=[g for g in board.Groups() if force._uid(g)==scope['group_uuid']]
    require(len(rows)==1 and rows[0].GetName()==scope['source_group_name']
        and sorted(force._uid(t) for t in rows[0].GetItems())==scope['source_group_members'],
        'retained_consumer_allocation_group_changed')


def subtract(board,scope):
    unchanged_group(board,scope)
    items=[t for t in board.GetTracks() if force._uid(t) in scope['retired_track_uuids']]
    require(len(items)==len(scope['retired_track_uuids']) and all(not t.GetParentGroup() for t in items),
        'exact_ungrouped_retained_consumer_subtraction_required')
    discard_items(board,items)


def assign(board,scope,track_uuids,via_uuids):
    unchanged_group(board,scope);require(not via_uuids,'retained_planar_consumer_cannot_add_vias')
    live={force._uid(t):t for t in board.GetTracks()}
    require(set(track_uuids)<=live.keys() and all(not live[u].GetParentGroup() for u in track_uuids),
        'new_retained_consumer_strokes_must_remain_ungrouped')


def receive(source,candidate,*,board_hint,retired_track_uuids,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],source_current_reduced=False,branch_sharing_assumed=False,
        terminal_or_barrel_ampacity_qualified=False,allocation_group_changed=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        digest=force._hash(Path(__file__));families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=plan(parent,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,timeout_s=timeout_s)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);retired=set(scope['retired_track_uuids']);incoming=new.keys()-old.keys()
        require(old.keys()-new.keys()==retired and 1<=len(incoming)<=64,'exact_retained_consumer_source_delta_required')
        live={force._uid(t):t for t in child.GetTracks()};require(incoming<=live.keys(),'only_new_planar_retained_consumer_tracks_allowed')
        for uid in incoming:
            t=live[uid]
            require(t.GetClass()=='PCB_TRACK' and not t.GetParentGroup() and t.GetNetname()==scope['net']
                and (int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()),bool(t.HasSolderMask()))==
                    (scope['actual_face_id'],scope['source_width_nm'],scope['source_locked'],scope['source_has_solder_mask'])
                and craft.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0),
                'exact_retained_consumer_saved_face_width_and_process_required')
        require(sum(live[u].GetLength() for u in incoming)<=80000000,'bounded_retained_consumer_new_span_required')
        unchanged_group(child,scope);fresh=consumer.inventory(child,board_hint=board_hint,timeout_s=timeout_s)
        matches=[q for q in fresh['proofs'] if q['root_pad_uuid']==scope['root_pad_uuid']]
        require(fresh['complete'] and len(matches)==1 and matches[0]['budget']==scope['source_budget']
            and matches[0]['anchor_uuid']==scope['anchor_uuid']
            and incoming<=matches[0]['retained_island_track_requirements'].keys(),
            'same_saved_exclusive_consumer_island_budget_and_tap_required')
        require(force._preservation_snapshot(source)[1]==force._preservation_snapshot(candidate)[1]
            and force._sidecars(source)==force._sidecars(candidate),'retained_consumer_unowned_parts_rules_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-retained-consumer-replay-') as temp:
            path=force._copy_family(source,Path(temp)/'family');subtract(parent,scope);field._save_field_snapshot(parent,path)
            root,_=additive._nodes(path)
            path.write_text(additive._render([root[0],*root[1:],*[new[u] for u in sorted(incoming)]])+'\n')
            rebuilt=pcbnew.LoadBoard(str(path));assign(rebuilt,scope,sorted(incoming),[])
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,path);_,expected=additive._nodes(path)
            require(expected.keys()==new.keys() and all(syntax._freeze(expected[u])==syntax._freeze(new[u]) for u in new),
                'exact_retained_consumer_source_replay_differs')
        boundary=pcbnew.LoadBoard(str(source))
        restored=ordinary._boundaries(boundary,child,[t for t in boundary.GetTracks() if force._uid(t) in retired],time.monotonic()+timeout_s)
        first=ordinary._partition(pcbnew.LoadBoard(str(source)),time.monotonic()+timeout_s,retired_uuids=retired)
        last=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=set().union(*first))
        require(all(any(p<=q for q in last) for p in first),'retained_consumer_lost_surviving_partition')
        require(epoch==force._code_identity() and digest==scope['authority_sha256']==force._hash(Path(__file__))
            and families==[force._family(p,board_hint) for p in (source,candidate)],'retained_consumer_receiving_epoch_changed')
        result.update(ok=True,complete=True,source_scope=scope,incoming_track_uuids=sorted(incoming),incoming_via_uuids=[],
            saved_source_consumer_proof=matches[0],all_original_surviving_partitions_preserved=True,
            exact_native_ground_refill_replayed=True,restored_full_width_source_boundaries=restored,
            source_candidate_and_code_unchanged=True,actual_face_current_floor_rederived=True,
            exact_allocation_group_preserved=True,retained_island_reproved_from_saved_native_topology=True)
    except (ValueError,RuntimeError,KeyError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
