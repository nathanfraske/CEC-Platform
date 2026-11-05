"""Retain literal original reference sheets after outer-only reconstruction.

This is construction, not a tolerance in the reference comparator. Only
unchanged source obstacles (or removed foreign vias) may face these sheets.
Every reference polygon, fracture bridge and island flag is copied literally.
The independent exact-sheet, whole-board and native DRC gates stay mandatory.
"""
import hashlib,json,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary

POLICY='literal-original-ground-reference-retention-after-outer-only-reconstruction-v1'
def require(value,message):
    if not value:raise ValueError(message)
def plain(value):return json.loads(json.dumps(value,allow_nan=False))
def frozen(node):return syntax._freeze(node)

def plan(reference_source,incoming,*,board_hint):
    require(type(board_hint) is str and bool(board_hint),'explicit_frozen_reference_context_required')
    paths=[Path(p).resolve() for p in (reference_source,incoming)];epoch=force._code_identity()
    families=[force._family(p,board_hint) for p in paths];boards=[pcbnew.LoadBoard(str(p)) for p in paths]
    nodes=[additive._nodes(p)[1] for p in paths];deadline=time.monotonic()+10.
    require(force._sidecars(paths[0])==force._sidecars(paths[1]) and
        force._preservation_snapshot(paths[0])[1]==force._preservation_snapshot(paths[1])[1],
        'literal_reference_board_settings_outlines_and_sidecars_required')
    with force._thermal_hint(board_hint):profiles=[fab.active_profile_name(b,hint=board_hint) for b in boards]
    require(profiles[0] and profiles[0]==profiles[1],'same_actual_frozen_reference_process_required')
    faces=sorted(int(boards[0].GetLayerID(n)) for n,r in zip(fab.COPPER_LAYERS,fab.get_profile(profiles[0])['roles']) if r=='GND')
    require(faces and all(face in b.GetEnabledLayers().CuStack() for b in boards for face in faces),
        'enabled_dedicated_reference_faces_required')
    # No artwork, footprint, field, group, or other collateral object may
    # change. The incoming route remains owned by its preceding transaction.
    other=[{u:n for u,n in q.items() if n[0] not in ('segment','via','zone','arc')} for q in nodes]
    require(other[0].keys()==other[1].keys() and all(frozen(n)==frozen(other[1][u]) for u,n in other[0].items()),
        'frozen_reference_all_actual_parts_artwork_fields_and_groups_must_stay_exact')
    vias=[{u:n for u,n in q.items() if n[0]=='via'} for q in nodes]
    require(vias[1].keys()<=vias[0].keys() and all(frozen(n)==frozen(vias[0][u]) for u,n in vias[1].items()),
        'frozen_reference_no_new_or_changed_actual_bores_allowed')
    ground_copper=[{force._uid(t) for t in b.GetTracks() if t.GetNetname()=='GND'} for b in boards]
    require(ground_copper[0]==ground_copper[1] and all(frozen(nodes[0][u])==frozen(nodes[1][u]) for u in ground_copper[0]),
        'frozen_reference_original_ground_tracks_and_barrels_must_stay_exact')
    rows=[];covered=set()
    for face in faces:
        # Every surviving non-Ground obstacle on the actual reference face
        # is literal source geometry. Foreign via removal only frees space.
        obstacles=[]
        for b,q in zip(boards,nodes):
            obstacles.append({force._uid(i):q[force._uid(i)] for i in [*b.GetTracks(),*b.Zones()]
                if i.IsOnLayer(face) and i.GetNetname()!='GND'})
        require(obstacles[1].keys()<=obstacles[0].keys() and
            all(frozen(n)==frozen(obstacles[0][u]) for u,n in obstacles[1].items()) and
            all(nodes[0][u][0]=='via' for u in obstacles[0].keys()-obstacles[1].keys()),
            'new_or_changed_reference_face_obstacle_cannot_reuse_frozen_source_fill')
        zones=[{force._uid(z):z for z in b.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(face) and not z.GetIsRuleArea()} for b in boards]
        require(zones[0] and zones[0].keys()==zones[1].keys(),'same_actual_frozen_reference_zone_inventory_required')
        for uid,z in zones[0].items():
            new=zones[1][uid]
            require(list(z.GetLayerSet().CuStack())==list(new.GetLayerSet().CuStack())==[face],
                'one_actual_dedicated_face_per_frozen_reference_zone_required')
            require(additive._without(nodes[0][uid],'filled_polygon')==additive._without(nodes[1][uid],'filled_polygon'),
                'frozen_reference_source_authored_zone_intent_must_stay_exact')
            require(z.IsFilled() and z.HasFilledPolysForLayer(face) and z.GetFilledPolysList(face).OutlineCount()>0,
                'positive_literal_original_reference_sheet_required')
            rows.append(dict(uuid=uid,face=face,source_filled_native_node_sha256=
                hashlib.sha256(repr(frozen(nodes[0][uid])).encode()).hexdigest()))
            covered.add(face)
        require(time.monotonic()<deadline,'frozen_reference_inventory_deadline')
    require(covered==set(faces) and epoch==force._code_identity() and families==[force._family(p,board_hint) for p in paths],
        'frozen_reference_source_epoch_or_face_inventory_changed')
    return plain(dict(policy=POLICY,reference_source=str(paths[0]),reference_sha256=force._hash(paths[0]),
        incoming=str(paths[1]),incoming_sha256=force._hash(paths[1]),board_hint=board_hint,code_identity=epoch,
        authority_sha256=force._hash(Path(__file__)),faces=faces,rows=rows,
        only_foreign_barrel_obstacles_removed=True,numeric_or_area_waiver_used=False,release_authority=False))

def construct(proposal):
    reference,incoming=[pcbnew.LoadBoard(proposal[k]) for k in ('reference_source','incoming')]
    source={force._uid(z):z for z in reference.Zones()};live={force._uid(z):z for z in incoming.Zones()}
    for row in proposal['rows']:
        old,new=source[row['uuid']],live[row['uuid']];face=row['face'];new.UnFill()
        new.SetFilledPolysList(face,old.GetFilledPolysList(face).CloneDropTriangulation());new.SetIsFilled(True)
        for i in range(old.GetFilledPolysList(face).OutlineCount()):
            if old.IsIsland(face,i):new.SetIsIsland(face,i)
    return incoming

def receive(reference_source,incoming,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],numeric_or_area_waiver_used=False,
        pair_reference_or_current_qualified=False,release_authority=False)
    try:
        paths=[Path(p).resolve() for p in (reference_source,incoming,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in paths]
        require(plan(*paths[:2],board_hint=board_hint)==proposal,'stale_or_forged_literal_reference_retention_plan')
        require(force._sidecars(paths[1])==force._sidecars(paths[2]),'frozen_reference_candidate_sidecars_changed')
        _,old=additive._nodes(paths[1]);_,got=additive._nodes(paths[2]);_,reference=additive._nodes(paths[0])
        with tempfile.TemporaryDirectory(prefix='cec-literal-reference-') as work:
            expected=force._copy_family(paths[1],Path(work)/'expected');field._save_field_snapshot(construct(proposal),expected)
            _,want=additive._nodes(expected)
            require(want.keys()==got.keys() and all(frozen(n)==frozen(got[u]) for u,n in want.items()),
                'unowned_literal_reference_reconstruction_or_collateral_mutation')
        ids={r['uuid'] for r in proposal['rows']}
        require(old.keys()==got.keys() and all(frozen(n)==frozen(got[u]) for u,n in old.items() if u not in ids)
            and all(frozen(reference[u])==frozen(got[u]) for u in ids),'literal_original_reference_sheet_nodes_not_exact')
        boards=[pcbnew.LoadBoard(str(p)) for p in paths[1:]]
        before=ordinary._partition(boards[0],time.monotonic()+10.)
        after=ordinary._partition(boards[1],time.monotonic()+10.,retained_keys=set().union(*before))
        require(all(any(a<=z for z in after) for a in before),'literal_reference_retention_lost_native_component')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in paths],
            'literal_reference_retention_family_or_epoch_changed')
        result.update(ok=True,complete=True,reference_sha256=force._hash(paths[0]),source_sha256=force._hash(paths[1]),
            candidate_sha256=force._hash(paths[2]),every_original_reference_node_byte_exact=True,
            all_other_incoming_native_objects_exact=True,all_incoming_native_partitions_preserved=True,
            restored_reference_zone_uuids=sorted(ids),new_holes_parts_or_reference_face_obstacles=0,
            independent_exact_reference_inclusion_and_whole_native_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
