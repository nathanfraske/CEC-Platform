"""Same-face reconstruction of a positively proved nonplane consumer group.

This separate opt-in owner derives the real face's existing current/project
floor. The original outer-layer, partial-group owner is unchanged. No via,
tap, allocation, package, group identity, sidecar or process may change.
"""
import math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_consumer_group_reconstruction as outer
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as craft
import cec_supply_consumer_branch as consumer


def require(condition,message):
    if not condition:raise ValueError(message)


def plan(board,source,*,board_hint,retired_track_uuids,timeout_s=10.):
    authority_sha256=force._hash(Path(__file__))
    require(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0<timeout_s<=10
        and type(board_hint) is str and bool(board_hint),'bounded_source_planar_consumer_context_required')
    ids=ordinary._ids(retired_track_uuids,'planar_consumer_group_cut',16)
    require(bool(ids),'nonempty_exact_planar_consumer_cut_required')
    inventory=consumer.inventory(board,board_hint=board_hint,timeout_s=timeout_s)
    require(inventory['complete'],'complete_positive_source_planar_consumer_required')
    groups=[g for g in board.Groups() if any(force._uid(t) in ids for t in g.GetItems())]
    require(len(groups)==1,'one_source_planar_consumer_owner_required')
    group=groups[0];members={force._uid(t) for t in group.GetItems()}
    require(group.GetName().startswith(consumer.PREFIX) and group.GetParentGroup() is None and ids<members
        and not any(g.ContainsItem(group) for g in board.Groups()),'partial_unnested_source_planar_consumer_group_required')
    root,anchor,via_csv=group.GetName()[len(consumer.PREFIX):].split('|')
    proofs=[q for q in inventory['proofs'] if q['root_pad_uuid']==root and q['anchor_uuid']==anchor]
    require(len(proofs)==1,'unique_source_planar_consumer_proof_required')
    proof=proofs[0];live={force._uid(t):t for t in board.GetTracks()}
    require(ids<=live.keys(),'actual_planar_consumer_source_tracks_required');old=[live[u] for u in sorted(ids)]
    require(all(t.GetClass()=='PCB_TRACK' and t.GetNetname()==proof['net'] and group.ContainsItem(t)
        and not t.HasSolderMask() and 0<t.GetLength()<=32000000 for t in old)
        and len({(int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'uniform_same_face_planar_consumer_width_and_process_required')
    require(not any(force._uid(g)!=force._uid(group) and any(force._uid(t) in ids for t in g.GetItems())
        for g in board.Groups()),'planar_consumer_cut_has_another_owner')
    face=int(old[0].GetLayer());width=old[0].GetWidth();canonical=fab.COPPER_LAYER_IDS[face]
    planes={board.GetLayerID(name) for name in fr.plane_layers(board)}
    allowed={board.GetLayerID(name) for name in fab.routing_layers(board,include_power=True)}
    require(face in board.GetEnabledLayers().CuStack() and face not in planes and face in allowed,
        'actual_enabled_nonplane_planar_consumer_face_required')
    physical=proof['budget']['required_by_layer_mm'].get(canonical)
    require(type(physical) in (int,float) and math.isfinite(physical) and physical>0,
        'positive_actual_face_planar_consumer_current_floor_required')
    spec=fr._project_netclass_resolver(str(source),board=board)(proof['net']) or {}
    floor=max(math.ceil(physical*1e6),board.GetDesignSettings().m_TrackMinWidth,
        math.ceil(float(spec.get('track_width') or 0)*1e6),
        math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(canonical) or 0)*1e6))
    require(floor<=width<=1000000 and sum(t.GetLength() for t in old)<=64000000,
        'source_planar_consumer_actual_face_full_current_width_required')
    require(authority_sha256==force._hash(Path(__file__)),'planar_consumer_authority_changed_during_plan')
    return dict(schema=1,source_sha256=force._hash(source),net=proof['net'],group_uuid=force._uid(group),
        authority_sha256=authority_sha256,
        source_group_name=group.GetName(),source_group_members=sorted(members),root_pad_uuid=root,anchor_uuid=anchor,
        source_via_uuids=sorted(filter(None,via_csv.split(','))),retired_track_uuids=sorted(ids),source_budget=proof['budget'],
        actual_face_id=face,actual_face=canonical,source_width_nm=width,actual_face_floor_nm=floor,
        source_locked=bool(old[0].IsLocked()),source_has_solder_mask=False,
        required_by_layer_nm={canonical:width},source_boundaries=ordinary._boundaries(board,board,old,time.monotonic()+timeout_s),
        source_current_reduced=False,branch_sharing_assumed=False,private_intermediate_not_an_admission_baseline=True,
        release_authority=False)


subtract=outer.subtract
assign=outer.assign


def receive(source,candidate,*,board_hint,retired_track_uuids,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],source_current_reduced=False,branch_sharing_assumed=False,
        terminal_or_barrel_ampacity_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        authority_sha256=force._hash(Path(__file__))
        families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=plan(parent,source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,timeout_s=timeout_s)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);retired=set(scope['retired_track_uuids']);incoming=new.keys()-old.keys()
        require(old.keys()-new.keys()==retired and 1<=len(incoming)<=64,'exact_saved_planar_consumer_cut_and_incoming_required')
        live={force._uid(t):t for t in child.GetTracks()};require(incoming<=live.keys(),'only_native_planar_consumer_tracks_allowed')
        for uid in incoming:
            item=live[uid]
            require(item.GetClass()=='PCB_TRACK' and item.GetNetname()==scope['net']
                and (int(item.GetLayer()),item.GetWidth(),bool(item.IsLocked()),bool(item.HasSolderMask()))==
                    (scope['actual_face_id'],scope['source_width_nm'],scope['source_locked'],scope['source_has_solder_mask'])
                and craft.is_canonical_stroke(tuple(item.GetStart()),tuple(item.GetEnd()),tolerance_nm=0),
                'exact_saved_planar_consumer_face_width_and_process_required')
        require(sum(live[u].GetLength() for u in incoming)<=80000000,'bounded_saved_planar_consumer_span_required')
        proof=consumer.inventory(child,board_hint=board_hint,timeout_s=timeout_s)
        matches=[q for q in proof['proofs'] if q['root_pad_uuid']==scope['root_pad_uuid']]
        require(proof['complete'] and len(matches)==1 and matches[0]['budget']==scope['source_budget']
            and matches[0]['anchor_uuid']==scope['anchor_uuid'],'same_saved_planar_consumer_budget_and_single_tap_required')
        require(force._preservation_snapshot(source)[1]==force._preservation_snapshot(candidate)[1]
            and force._sidecars(source)==force._sidecars(candidate),'planar_consumer_parts_settings_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-planar-consumer-replay-') as temp:
            path=force._copy_family(source,Path(temp)/'family');subtract(parent,scope);field._save_field_snapshot(parent,path)
            root,nodes=additive._nodes(path)
            path.write_text(additive._render([root[0],*root[1:],*[new[u] for u in sorted(incoming)]])+'\n')
            rebuilt=pcbnew.LoadBoard(str(path));assign(rebuilt,scope,sorted(incoming),[])
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,path);_,expected=additive._nodes(path)
            require(expected.keys()==new.keys() and all(syntax._freeze(expected[u])==syntax._freeze(new[u]) for u in new),
                'exact_planar_consumer_source_replay_differs')
        boundary_parent=pcbnew.LoadBoard(str(source))
        boundaries=ordinary._boundaries(boundary_parent,child,[t for t in boundary_parent.GetTracks()
            if force._uid(t) in retired],time.monotonic()+timeout_s)
        first=ordinary._partition(pcbnew.LoadBoard(str(source)),time.monotonic()+timeout_s,retired_uuids=retired)
        last=ordinary._partition(child,time.monotonic()+timeout_s,retained_keys=set().union(*first))
        require(all(any(p<=q for q in last) for p in first),'planar_consumer_lost_surviving_native_partition')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in (source,candidate)],
            'planar_consumer_source_candidate_or_code_changed')
        require(authority_sha256==scope['authority_sha256']==force._hash(Path(__file__)),
            'planar_consumer_authority_changed_during_receiving')
        result.update(ok=True,complete=True,source_scope=scope,saved_source_consumer_proof=matches[0],
            incoming_track_uuids=sorted(incoming),incoming_via_uuids=[],all_original_surviving_partitions_preserved=True,
            exact_native_ground_refill_replayed=True,restored_full_width_source_boundaries=boundaries,
            source_candidate_and_code_unchanged=True,actual_face_current_floor_rederived=True,
            authority_sha256=authority_sha256)
    except (ValueError,RuntimeError,KeyError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
