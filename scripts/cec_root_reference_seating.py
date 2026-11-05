"""Source-owned root-map caption/leader seating; no component motion.

Only an independently recognized external rigid opposite-face map qualifies.
All circuit/material inputs remain exact; this is not electrical qualification.
"""
import json,math,tempfile,time
from pathlib import Path
import pcbnew
from shapely import affinity
from shapely.ops import nearest_points,unary_union
import cec_force_current as force
import cec_source_reference_group_transport as ownership
import cec_source_retaining_ses_import as raw
import cec_source_literal_additions as literal
import cec_field_coupling as field
import cec_reference_field_seating as seats
import cec_mask_search_reference_mapping as masks
import cec_reference_mask_obstacles as apertures


def _need(v,message):
    if not v:raise ValueError(message)


def dependencies():
    return {str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in
        (ownership,field,seats,seats.dense,masks,apertures,raw,literal)}|{str(Path(__file__).resolve()):force._hash(Path(__file__))}


def _obstacles(board,face,excluded,gap):
    """Native mask/bore obstacles with explicit ROOT-item exclusions too.

    dense.obstacles' exclusion parameter is field-only; subtracting an owned
    polygon from its union could incorrectly carve an overlapping foreign item.
    Build the union from individually retained actual items instead.
    """
    shapes=[];cu=pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu
    for item in board.GetDrawings():
        if item.GetLayer()==face and force._uid(item)not in excluded:shapes.append(seats.dense.polygon(item,face))
    for fp in board.GetFootprints():
        if fp.GetLayer()==cu:shapes.append(seats.dense.court(fp))
        for item in [*fp.GraphicalItems(),*fp.GetFields()]:
            if item.GetLayer()==face and force._uid(item)not in excluded and(not hasattr(item,'IsVisible')or item.IsVisible()):
                shapes.append(seats.dense.polygon(item,face))
    shapes.extend(seats.assembly.polygon_from_native(p)for _,p in seats.ink._mask_openings(board,face,'native_mask_and_bore'))
    return unary_union(shapes).buffer(gap+.002,join_style=2)


def _nodes(board,proof):
    group=next(g for g in board.Groups()if force._uid(g)==proof['group_uuid'])
    items=list(group.GetItems());fp=next(i for i in items if i.GetClass()=='FOOTPRINT')
    text=next(i for i in items if i.GetClass()=='PCB_TEXT');lines=[i for i in items if i.GetClass()=='PCB_SHAPE']
    court=seats.assembly.polygon_from_native(fp.GetCourtyard(fp.GetLayer()))
    chain=fp.GetCourtyard(fp.GetLayer()).COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    edges={tuple(sorted((vertices[i],vertices[(i+1)%len(vertices)])))for i in range(len(vertices))}
    actual={tuple(sorted((tuple(i.GetStart()),tuple(i.GetEnd())))):i for i in lines}
    outline=edges if edges<=actual.keys()else ownership._rectangular_corner_arms(vertices,text.GetTextThickness())
    _need(outline is not None and outline<=actual.keys(),'exact_source_outline_required')
    leaders=[i for pair,i in actual.items()if pair not in outline]
    _need(len(leaders)==1,'external_source_map_with_one_existing_leader_required')
    return fp,text,leaders[0],court,lines


def _opposite_reservations(board,face,owners,gap,stroke,own_uuid):
    """Conservative future-map space from actual unmapped Source owners.

    These polygons only REMOVE caption seats. They authorize no new map,
    hidden field, component motion, artwork deletion or circuit change.
    """
    _need(type(owners)in(list,tuple)and len(owners)<=8 and len(set(owners))==len(owners)
        and all(type(u)is str and u and u!=own_uuid for u in owners),
        'bounded_distinct_opposite_reference_reservations_required')
    fps={force._uid(fp):fp for fp in board.GetFootprints()};shapes=[];records=[]
    for uid in owners:
        fp=fps.get(uid)
        _need(fp is not None and not fp.IsDNP()and fp.Reference().IsVisible()
            and fp.Reference().GetLayer()==(pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS)
            and face!=(pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS)
            and fp.GetParentGroup()is None,
            'actual_unmapped_opposite_source_reference_owner_required')
        court=seats.dense.court(fp)
        shapes.append(court.buffer(gap+stroke/2+.002,join_style=2))
        records.append(dict(owner_uuid=uid,reference=fp.GetReference(),
            courtyard_xy_mm=[list(p)for p in court.exterior.coords]))
    return unary_union(shapes),records


def plan(source,*,board_hint,owner_uuid,group_uuid,timeout_s=10.,opposite_owner_uuid_reservations=(),
         seat_gap_samples_mm=()):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_root_reference_plan_required')
    _need(type(seat_gap_samples_mm)in(list,tuple)and len(seat_gap_samples_mm)<=6
        and all(type(v)in(int,float)and math.isfinite(v)and .25<=v<=3. for v in seat_gap_samples_mm)
        and len(set(seat_gap_samples_mm))==len(seat_gap_samples_mm),
        'bounded_existing_local_root_caption_gap_samples_required')
    start=time.monotonic();deadline=start+timeout_s;source=Path(source).resolve(strict=True)
    epoch=force._code_identity();family=force._family(source,board_hint);deps=dependencies()
    remaining=deadline-time.monotonic();_need(remaining>0,'root_reference_plan_deadline')
    proof=ownership.inspect_many(source,[(owner_uuid,group_uuid)],timeout_s=remaining)[0]
    _need(time.monotonic()<deadline,'root_reference_plan_deadline')
    board=pcbnew.LoadBoard(str(source));fp,text,leader,court,lines=_nodes(board,proof)
    floor=seats.dense.floors(board,source);face=text.GetLayer();gap=floor['clearance'];stroke=text.GetTextThickness()/1e6
    material=seats.assembly.polygon_from_native(seats.geometry.outline_material(board)).buffer(-floor['edge'],join_style=2)
    text_id=force._uid(text);leader_id=force._uid(leader)
    artwork,_=apertures.native_mask_artwork(board,face)
    mask=artwork.buffer(gap+.002,join_style=2)
    hard_text=_obstacles(board,face,{text_id,leader_id},gap)
    # The leader attaches to the existing source outline, so only those
    # positively owned strokes are omitted from its foreign-ink obstacles.
    hard_leader=_obstacles(board,face,{text_id,*[force._uid(i)for i in lines]},gap)
    reserve,reservations=_opposite_reservations(board,face,opposite_owner_uuid_reservations,
        gap,stroke,owner_uuid)
    hard_text=unary_union([hard_text,reserve]);hard_leader=unary_union([hard_leader,reserve])
    trials=0;choices=[];reasons=dict(material=0,text=0,leader=0,not_external=0)
    for angle in(0,90):
        text.SetPosition(pcbnew.VECTOR2I(0,0));text.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        glyph=seats.dense.polygon(text,face)
        centers={p for sample in (3.,*seat_gap_samples_mm)
            for p in seats._centers(court,glyph,floor,sample)}
        for center in sorted(centers):
            _need(time.monotonic()<deadline,'root_reference_plan_deadline');trials+=1
            at=[round(v*1e6)for v in center];text.SetPosition(pcbnew.VECTOR2I(*at))
            ink=seats.dense.polygon(text,face)
            if court.intersects(ink.buffer(gap+.002)):
                reasons['not_external']+=1;continue
            envelope=ink.envelope.buffer(gap+stroke/2+.002,join_style=2)
            a,z=nearest_points(court,envelope);ends=[[round(v*1e6)for v in p.coords[0]]for p in(a,z)]
            if ends[0]==ends[1]:reasons['not_external']+=1;continue
            leader.SetStart(pcbnew.VECTOR2I(*ends[0]));leader.SetEnd(pcbnew.VECTOR2I(*ends[1]))
            lead=seats.dense.polygon(leader,face)
            if not material.covers(unary_union([ink,lead])):reasons['material']+=1;continue
            if ink.intersects(hard_text)or ink.intersects(mask):reasons['text']+=1;continue
            if lead.intersects(hard_leader)or lead.intersects(mask):reasons['leader']+=1;continue
            choices.append((math.dist(center,(court.centroid.x,court.centroid.y)),angle,at,ends))
    _need(choices,'no_clear_source_owned_root_caption_seat')
    _,angle,at,ends=min(choices)
    _need(epoch==force._code_identity()and family==force._family(source,board_hint)and deps==dependencies(),'root_reference_source_or_runtime_changed')
    _need(time.monotonic()<deadline,'root_reference_plan_deadline')
    result=dict(schema=1,policy='source-owned-external-root-reference-seating-v1',source=str(source),source_sha256=force._hash(source),
        board_hint=board_hint,owner_uuid=owner_uuid,group_uuid=group_uuid,timeout_s=timeout_s,
        code_identity=epoch,source_family=family,dependencies=deps,ownership=proof,
        text_uuid=text_id,leader_uuid=leader_id,at_nm=at,angle_degrees=angle,leader_endpoints_nm=ends,
        tested_positions=trials,refusals=reasons,mutation_scope='owned_root_text_at_and_same_leader_start_end_only',
        current_authority=False,full_kelvin_qualification=False,admitted=False,release_authority=False)
    if opposite_owner_uuid_reservations:
        result.update(opposite_owner_uuid_reservations=list(opposite_owner_uuid_reservations),
            source_opposite_courtyard_reservations=reservations,
            reservations_constrain_search_only=True)
    if seat_gap_samples_mm:result['seat_gap_samples_mm']=list(seat_gap_samples_mm)
    return result


def _construct(source,proposal):
    started=time.monotonic()
    options={k:proposal[k]for k in('board_hint','owner_uuid','group_uuid','timeout_s')}
    for key in ('opposite_owner_uuid_reservations','seat_gap_samples_mm'):
        if key in proposal:options[key]=proposal[key]
    fresh=plan(source,**options)
    _need(fresh==proposal,'stale_or_forged_root_reference_proposal')
    board=pcbnew.LoadBoard(str(source));_,text,leader,_,_=_nodes(board,fresh['ownership'])
    text.SetPosition(pcbnew.VECTOR2I(*fresh['at_nm']));text.SetTextAngle(pcbnew.EDA_ANGLE(fresh['angle_degrees'],pcbnew.DEGREES_T))
    leader.SetStart(pcbnew.VECTOR2I(*fresh['leader_endpoints_nm'][0]));leader.SetEnd(pcbnew.VECTOR2I(*fresh['leader_endpoints_nm'][1]))
    _need(time.monotonic()-started<proposal['timeout_s'],'root_reference_reconstruction_deadline')
    return board


def _literal(source_text,native_text,q):
    old,new=raw.inventory(source_text),raw.inventory(native_text);changes=[]
    for uid,kinds,expected_kind in((q['text_uuid'],('at',),'gr_text'),(q['leader_uuid'],('start','end'),'gr_line')):
        _need(uid in old and uid in new,'exact_owned_root_nodes_required')
        a,b=old[uid];x,y=new[uid];before=source_text[a:b];after=native_text[x:y]
        _need(raw.kind(before)==raw.kind(after)==expected_kind,'exact_owned_root_node_kind_required')
        for kind in kinds:
            rows=[(p,z)for p,z in raw.children(before)if raw.kind(before[p:z])==kind]
            fresh=[after[p:z]for p,z in raw.children(after)if raw.kind(after[p:z])==kind]
            _need(len(rows)==len(fresh)==1,'unique_owned_root_coordinate_required')
            p,z=rows[0];changes.append((a+p,a+z,fresh[0]))
    for a,b,value in sorted(changes,reverse=True):source_text=source_text[:a]+value+source_text[b:]
    return source_text


def write_private(source,candidate,proposal):
    source,candidate=map(Path,(source,candidate))
    _need(source.resolve()!=candidate.resolve()and source.read_bytes()==candidate.read_bytes(),'exact_private_root_reference_source_copy_required')
    board=_construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-root-reference-seat-')as work:
        native=Path(work)/'board.kicad_pcb';field._save_field_snapshot(board,native)
        raw.write_raw(candidate,_literal(source.read_text(),native.read_text(),proposal))
    return dict(text_uuid=proposal['text_uuid'],leader_uuid=proposal['leader_uuid'],all_other_source_bytes_exact=True)


def receive(source,candidate,proposal):
    result=dict(ok=False,complete=False,admitted=False,release_authority=False,current_authority=False,
        full_kelvin_qualification=False,inherited_electrical_debt='unchanged_not_evaluated')
    started=time.monotonic();phase_started=started;timings={};limit=proposal.get('timeout_s')if type(proposal)is dict else None
    try:
        _need(type(limit)in(int,float)and math.isfinite(limit)and 0<limit<=10,'bounded_root_reference_receiving_required')
        source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
        _need(source!=candidate,'distinct_saved_root_reference_paths_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        board=_construct(source,proposal)
        timings['source_reconstruction']=time.monotonic()-started
        _need(timings['source_reconstruction']<limit,'root_reference_reconstruction_deadline')
        phase_started=time.monotonic();deadline=phase_started+limit
        def live_tick():_need(time.monotonic()<deadline,'root_reference_literal_native_live_deadline')
        live_tick()
        with tempfile.TemporaryDirectory(prefix='cec-root-reference-receive-')as work:
            expected=Path(work)/'expected.kicad_pcb';field._save_field_snapshot(board,expected)
            live_tick()
            _need(_literal(source.read_text(),expected.read_text(),proposal)==candidate.read_text(),'root_reference_changed_unowned_literal_source')
            previous=candidate
            for index in range(2):
                live_tick()
                saved=Path(work)/(str(index)+'.kicad_pcb');field._save_field_snapshot(pcbnew.LoadBoard(str(previous)),saved)
                live_tick()
                _need(seats.dense.syntax._freeze(seats.dense.additive._nodes(expected)[0])==seats.dense.syntax._freeze(seats.dense.additive._nodes(saved)[0]),'root_reference_whole_native_roundtrip_changed')
                previous=saved
        _need(force._sidecars(source)==force._sidecars(candidate),'root_reference_sidecars_changed')
        _need(epoch==force._code_identity()and families==[force._family(p,proposal['board_hint'])for p in(source,candidate)]and proposal['dependencies']==dependencies(),'root_reference_source_code_or_dependencies_changed')
        live_tick();timings['literal_native_material_live']=time.monotonic()-phase_started
        _need(time.monotonic()-started<2*limit,'root_reference_aggregate_deadline')
        result.update(ok=True,complete=True,same_material=True,comparison_complete=True,
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            all_circuit_query_inputs_exact=True,independent_native_and_whole_transaction_receiving_required=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:result['error']=str(exc)
    result.update(timings_s=timings,elapsed_s=time.monotonic()-started,
        bounded_composition=dict(source_reconstruction_limit_s=limit,literal_native_material_live_limit_s=limit,
            aggregate_limit_s=2*limit if type(limit)in(int,float)else None,
            timing_observations_are_not_scope_authority=True))
    return result
