"""Seat faulted reference fields beside their actual owners before mapping.

Only exact current native silk findings supply owner eligibility. Existing
mask artwork, every actual bore, printed ink, closed assembled courtyards and
substrate/cutouts reserve space. The factory's readable glyph floors remain
mandatory. A failed finite seat search grants neither hiding nor a back-map
waiver: the separately received chart/projected-courtyard owner remains next.

This changes only the selected Reference properties' at/effects children.
It does not create graphics, groups, footprint artwork, copper or new locks.
"""
from collections import Counter
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
import cec_additive_route_receiving as ast
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
import cec_copper_echo as syntax
import cec_dense_reference_mapping as dense
import cec_field_coupling as field
import cec_force_current as force
import cec_reference_mask_obstacles as masks
import cec_rectangular_field_silk_clearance as ink
import cec_source_retaining_ses_import as raw
import cec_qualified_courtyard_restore as qualified
import cec_joint_connection_search as joint

POLICY='source-native-own-face-reference-periphery-v2'


def _require(value,reason):
    if not value:raise ValueError(reason)


def dependencies():
    return {str(p):force._hash(p)for p in (Path(__file__).resolve(),
        Path(dense.__file__).resolve(),Path(masks.__file__).resolve(),Path(ink.__file__).resolve(),
        Path(qualified.__file__).resolve(),Path(joint.__file__).resolve())}


def _tick(deadline):
    _require(time.monotonic()<deadline,'reference_field_seating_deadline')


def new_native_reference_owner_scope(board,before,after,*,maximum_components=16):
    """Match cleanup eligibility to the strict saved-native receiving delta.

    A moved pad or glyph can keep the same item UUIDs but change a real
    finding's geometry. A topology-only warning key would miss that event
    while the independent receiving gate correctly refuses it. This selects
    exact live Reference owners only; it never hides or qualifies a finding.
    """
    _require(type(maximum_components)is int and 1<=maximum_components<=16,
        'bounded_new_native_reference_owner_scope_required')
    import cec_received_private_stage as stage
    fps=list(board.GetFootprints())
    owners={force._uid(fp.Reference()):force._uid(fp)for fp in fps}
    _require(len(owners)==len(fps),'unambiguous_native_reference_owner_inventory_required')
    introduced=stage.native_findings_delta(before,after)['introduced_native_findings']
    scope=set()
    for encoded in introduced:
        row=json.loads(encoded)
        if row.get('type')not in('silk_overlap','silk_over_copper','silk_edge_clearance'):continue
        for item in row['items']:
            uid=item.get('uuid')
            if uid in owners:scope.add(owners[uid])
    _require(len(scope)<=maximum_components,'bounded_new_native_reference_owner_scope_required')
    return sorted(scope)


def _stamp(reference,row):
    reference.SetTextPos(pcbnew.VECTOR2I(*row['at_nm']))
    reference.SetTextAngle(pcbnew.EDA_ANGLE(row['angle_degrees'],pcbnew.DEGREES_T))
    reference.SetTextSize(pcbnew.VECTOR2I(*row['size_nm']))
    reference.SetTextThickness(row['stroke_nm'])
    reference.SetMirrored(row['layer_id']==pcbnew.B_SilkS)
    # KeepUpright is an independent Source property (`unlocked yes` when
    # false), outside our at/effects ownership. Explicit 0/90 world angles
    # provide readable glyphs without silently taking over that flag.
    reference.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    reference.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)


def _centers(court,glyph,f,max_gap):
    """Actual body/glyph bounds define <=120 local cardinal seat centers."""
    x0,y0,x1,y1=court.bounds;a,b,c,d=glyph.bounds
    points=set()
    gaps=sorted({f['clearance']+.003,min(max_gap,f['clearance']+.15),max_gap})
    for gap in gaps:
        for fraction in (0.,.25,.5,.75,1.):
            x=x0+fraction*(x1-x0);y=y0+fraction*(y1-y0)
            points.update(((x,y0-gap-d),(x,y1+gap-b),(x0-gap-c,y),(x1+gap-a,y)))
    return sorted(points,key=lambda p:(math.dist(p,(court.centroid.x,court.centroid.y)),p))


def _reviewed_body_shapes(source,board,board_hint,contract_ids,deadline):
    """Reserve reviewed missing bodies, without adding them to the output.

    The manufacturer contract is independently replayed on a temporary native
    board. Its authored full envelope (not an inset DRC cache or pad bbox) is
    usable only as a conservative label obstacle and nearest-owner boundary.
    This does not restore the source courtyard or receive any body overlap.
    """
    reviewed={};proofs=[];unknown=[]
    for contract_id in contract_ids:
        _tick(deadline)
        proposal=qualified.plan(source,contract_id=contract_id,board_hint=board_hint,
            timeout_s=10.,literal_source=True)
        projected=qualified.construct(source,proposal)
        owners={force._uid(fp):fp for fp in projected.GetFootprints()}
        for row in proposal['records']:
            uid=row['footprint_uuid']
            _require(uid not in reviewed,'ambiguous_reviewed_reference_body_authority')
            # construct independently verifies the exact package, lands,
            # posed native authored contour and actual native closure.
            _require(qualified._contour(owners[uid])==tuple(map(tuple,row['world_points_nm'])),
                'reviewed_reference_native_body_changed')
            shape=Polygon([(x/1e6,y/1e6)for x,y in row['world_points_nm']])
            _require(shape.is_valid and not shape.is_empty and not shape.interiors,
                'positive_full_reviewed_reference_body_required')
            reviewed[uid]=shape
        proofs.append(proposal)
        _tick(deadline)
    shapes={}
    for fp in board.GetFootprints():
        artwork_only=(not list(fp.Pads())and not list(fp.Models())
            and bool(fp.GetAttributes()&pcbnew.FP_BOARD_ONLY)
            and bool(fp.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_BOM)
            and bool(fp.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_POS_FILES))
        if artwork_only:continue
        uid=force._uid(fp)
        try:shape=dense.court(fp)
        except ValueError:
            if uid not in reviewed:
                unknown.append(uid);continue
            shape=reviewed[uid]
        shapes[uid]=shape
    return shapes,proofs,unknown


def _reported_owners(board,report,source,body_shapes):
    fps={force._uid(fp):fp for fp in board.GetFootprints()}
    fields={force._uid(fp.Reference()):u for u,fp in fps.items()};counts=Counter()
    for fault in report['violations']:
        if fault['type']not in('silk_overlap','silk_over_copper','silk_edge_clearance'):continue
        for item in fault['items']:
            if item.get('uuid')in fields:counts[fields[item['uuid']]]+=1
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    grouped.update(u for n in ast._nodes(source)[1].values()if n[0]=='group'for u in ast._members(n))
    found=[]
    for uid in sorted(counts,key=lambda u:(-counts[u],u)):
        fp=fps[uid];ref=fp.Reference();face=pcbnew.B_SilkS if fp.IsFlipped()else pcbnew.F_SilkS
        if(not ref.IsVisible()or ref.IsLocked()or fp.IsLocked()or ref.GetLayer()!=face
            or uid in grouped or force._uid(ref)in grouped or fp.GetParentGroup()):continue
        if uid not in body_shapes:continue
        shape=body_shapes[uid]
        found.append((fp,shape))
    return found


def _cooperative_assignment(menus,originals,faces,clearance,deadline):
    """Choose actual glyphs together; an unchanged field grants no free space.

    Candidate glyphs have already passed the unchanged body/mask/edge and
    nearest-owner tests. A literal stay choice keeps an owner's ORIGINAL ink
    as an obstacle to every changed neighbour. Two stay choices may preserve
    an existing finding, but cannot certify its removal. The final saved
    native finding delta, not this geometric search, owns that claim.
    """
    _require(1<=len(menus)<=16 and set(menus)==set(originals)==set(faces),
        'bounded_complete_cooperative_reference_scope_required')
    domains={};shapes={};rows={};padded={}
    for uid,choices in sorted(menus.items()):
        # A finite, deterministic subset, not a time-dependent best-so-far.
        # Keep both readable cardinal orientations in the same joint domain.
        ordered=sorted(choices,key=lambda r:r[:4])[:95]
        domains[uid]=[]
        for index,(own,distance,angle,at,shape,record)in enumerate(ordered):
            ident=str(index);key=(uid,ident)
            shapes[key]=shape;rows[key]=record
            domains[uid].append(dict(id=ident,cost=round(own*1e6+distance*1e3),
                owner=uid,literal_stay=False))
        shapes[uid,'stay']=originals[uid]
        domains[uid].append(dict(id='stay',cost=1e12,owner=uid,literal_stay=True))
    for key,shape in shapes.items():
        padded[key]=prep(shape.buffer(clearance+.002,join_style=2))
    def conflict(a,b):
        if faces[a['owner']]!=faces[b['owner']]:return False
        if a['literal_stay']and b['literal_stay']:return False
        return bool(padded[a['owner'],a['id']].intersects(shapes[b['owner'],b['id']]))
    _tick(deadline)
    result=joint.solve(domains,conflicts=conflict,timeout_s=min(10.,deadline-time.monotonic()),
        max_states=8192,max_pair_checks=200000)
    _require(result['complete']is True and result['input_unchanged']is True,
        'finite_cooperative_reference_seats_not_completed')
    _tick(deadline)
    selected=result['selected']
    records=[rows[uid,selected[uid]['id']]for uid in sorted(selected)
        if not selected[uid]['literal_stay']]
    proof=dict(scope='finite_joint_own_face_glyph_geometry_not_native_admission',
        states=result['states'],pair_checks=result['pair_checks'],domain_binding=result['domain_binding'],
        selected={uid:selected[uid]['id']for uid in sorted(selected)},
        literal_stay_owners=[uid for uid in sorted(selected)if selected[uid]['literal_stay']],
        immutable_original_ink_retained_for_every_stay=True,
        no_new_copper_or_body_motion_authority=True,release_authority=False)
    return records,proof


def plan(source,*,grade,board_hint,maximum_components=8,seed_index=0,
         owner_uuid_scope=(),max_gap_mm=1.5,timeout_s=10.,reviewed_courtyard_contract_ids=(),
         cooperative=False):
    _require(type(maximum_components)is int and 1<=maximum_components<=16
        and type(seed_index)is int and 0<=seed_index<128
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10
        and type(max_gap_mm)in(int,float)and math.isfinite(max_gap_mm)and .25<=max_gap_mm<=2.,
        'bounded_source_reference_field_seating_required')
    _require(type(cooperative)is bool,'bounded_explicit_cooperative_reference_seating_required')
    _require(type(owner_uuid_scope)in(list,tuple)and len(owner_uuid_scope)<=16
        and len(set(owner_uuid_scope))==len(owner_uuid_scope)
        and all(type(u)is str and u for u in owner_uuid_scope),
        'bounded_exact_reference_field_owner_scope_required')
    _require(type(reviewed_courtyard_contract_ids)in(list,tuple)
        and len(reviewed_courtyard_contract_ids)<=8
        and all(type(k)is str and k for k in reviewed_courtyard_contract_ids)
        and len(set(reviewed_courtyard_contract_ids))==len(reviewed_courtyard_contract_ids),
        'bounded_explicit_reviewed_reference_body_contracts_required')
    started=time.monotonic();deadline=started+timeout_s;bound=dependencies()
    board,f,native,binding=dense.source_context(source,grade,board_hint)
    _require(max_gap_mm>=f['clearance']+.003,'readable_reference_field_gap_below_factory_floor')
    body_shapes,reviewed_bodies,unknown_bodies=_reviewed_body_shapes(source,board,board_hint,
        reviewed_courtyard_contract_ids,deadline)
    models=_reported_owners(board,native,source,body_shapes)
    if owner_uuid_scope:
        _require(set(owner_uuid_scope)<={force._uid(fp)for fp,_ in models},
            'reference_field_owner_not_reported_eligible')
        models=[m for m in models if force._uid(m[0])in owner_uuid_scope]
    _require(seed_index<len(models),'no_source_native_reference_field_seed')
    selected=models[seed_index:seed_index+maximum_components]
    excluded={force._uid(fp.Reference())for fp,_ in selected}
    material=assembly.polygon_from_native(geometry.outline_material(board)).buffer(-f['edge'],join_style=2)
    material_ready=prep(material);base={};pending={};courts={}
    for face in sorted({fp.Reference().GetLayer()for fp,_ in selected}):
        _tick(deadline)
        _require(not any(force._uid(fp)in unknown_bodies and fp.GetLayer()==
            (pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu)for fp in board.GetFootprints()),
            'one_literal_closed_source_courtyard_required')
        # Every physical body remains reserved. A missing body is permitted
        # only from the explicitly reviewed exact-package obstacle context;
        # an unknown/partial body still refuses, never from pad extents.
        hard=dense.obstacles(board,face,excluded,f['clearance'],assembled_bodies=False,
            via_ink_policy='native_mask_and_bore')
        artwork,_=masks.native_mask_artwork(board,face)
        face_bodies=[body_shapes[force._uid(fp)]for fp in board.GetFootprints()
            if force._uid(fp)in body_shapes and fp.GetLayer()==
                (pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu)]
        base[face]=unary_union([hard,artwork.buffer(f['clearance']+.002,join_style=2),
            *[shape.buffer(f['clearance']+.002,join_style=2)for shape in face_bodies]])
        pending[face]={force._uid(fp):dense.polygon(fp.Reference(),face)
            for fp,_ in selected if fp.Reference().GetLayer()==face}
        courts[face]={force._uid(fp):body_shapes[force._uid(fp)]for fp in board.GetFootprints()
            if fp.GetLayer()==(pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu)
            and force._uid(fp)in body_shapes}
    records=[];refusals=[];menus={};common_rows={};faces={}
    for fp,court in selected:
        _tick(deadline);uid=force._uid(fp);face=int(fp.Reference().GetLayer());ref=fp.Reference()
        blocked=prep(base[face]if cooperative else unary_union([base[face],
            *[p.buffer(f['clearance']+.002,join_style=2)
            for u,p in pending[face].items()if u!=uid]]))
        common=dict(footprint_uuid=uid,reference_field_uuid=force._uid(ref),reference=fp.GetReference(),
            layer_id=face,size_nm=[round(f['height']*1e6)]*2,stroke_nm=round(f['stroke']*1e6))
        candidates=[]
        for angle in(0,90):
            _stamp(ref,dict(common,at_nm=[0,0],angle_degrees=angle))
            glyph=dense.polygon(ref,face)
            for center in _centers(court,glyph,f,max_gap_mm):
                _tick(deadline);at=[round(x*1e6)for x in center]
                ink=affinity.translate(glyph,at[0]/1e6,at[1]/1e6)
                if not material_ready.covers(ink)or blocked.intersects(ink):continue
                # A nearby unlabelled mark must clearly belong to THIS
                # physical owner. Ambiguous seats go to the map primitive.
                own=court.distance(ink.centroid)
                if own>max_gap_mm+max(ink.bounds[2]-ink.bounds[0],ink.bounds[3]-ink.bounds[1]):continue
                if any(other.distance(ink.centroid)<=own+.000001
                    for other_uid,other in courts[face].items()if other_uid!=uid):continue
                candidates.append((own,math.dist(center,(court.centroid.x,court.centroid.y)),angle,at,ink))
        if cooperative:
            faces[uid]=face;common_rows[uid]=common
            menus[uid]=[(own,distance,angle,at,shape,
                dict(common,at_nm=at,angle_degrees=angle))
                for own,distance,angle,at,shape in candidates]
            continue
        if not candidates:
            refusals.append(dict(footprint_uuid=uid,reference=fp.GetReference(),reason='finite_own_face_readable_seats_occupied'))
            continue
        _,_,angle,at,ink=min(candidates,key=lambda r:r[:4])
        record=dict(common,at_nm=at,angle_degrees=angle)
        _stamp(ref,record);pending[face][uid]=ink;records.append(record)
    cooperative_proof=None
    if cooperative:
        originals={uid:shape for face in pending.values()for uid,shape in face.items()}
        records,cooperative_proof=_cooperative_assignment(menus,originals,faces,f['clearance'],deadline)
        refusals=[dict(footprint_uuid=uid,reference=common_rows[uid]['reference'],
            reason='finite_joint_seating_retained_literal_source_field')
            for uid in cooperative_proof['literal_stay_owners']]
    _require(records,'no_readable_clear_source_reference_field_seat')
    _tick(deadline)
    _require(bound==dependencies()and binding['source_family']==force._family(source,board_hint),
        'reference_field_source_or_dependencies_changed')
    result=dict(schema=1,policy=POLICY,binding=binding,dependencies=bound,board_hint=board_hint,
        grade=str(Path(grade).resolve()),request=dict(maximum_components=maximum_components,
            seed_index=seed_index,owner_uuid_scope=list(owner_uuid_scope),max_gap_mm=max_gap_mm,timeout_s=timeout_s,
            reviewed_courtyard_contract_ids=list(reviewed_courtyard_contract_ids)),
        reviewed_body_reservations=reviewed_bodies,
        reviewed_bodies_are_obstacles_only_not_source_courtyard_or_overlap_admission=True,
        records=records,refusals=refusals,fields_stay_visible_on_owner_face=True,
        reference_identity_preserved=True,source_keep_upright_flag_preserved=True,
        no_new_artwork_or_copper_or_group_authority=True,
        factory_readable_glyph_floors_preserved=True,release_authority=False)
    # Old v2 recipes keep their explicit old request. New callers opt into a
    # separately replayable finite search, without silently relabelling old
    # physical/native evidence as a current cooperative result.
    if cooperative:
        result['request']['cooperative']=True
        result['cooperative_search']=cooperative_proof
    return result


def construct(source,proposal):
    fresh=plan(source,grade=proposal['grade'],board_hint=proposal['board_hint'],**proposal['request'])
    _require(fresh==proposal,'stale_or_forged_reference_field_seating_plan')
    board=pcbnew.LoadBoard(str(source));owners={force._uid(fp):fp for fp in board.GetFootprints()}
    for row in fresh['records']:_stamp(owners[row['footprint_uuid']].Reference(),row)
    return board


def _literal(source_text,native_text,proposal):
    old,new=raw.inventory(source_text),raw.inventory(native_text);text=source_text
    for row in sorted(proposal['records'],key=lambda r:old[r['footprint_uuid']][0],reverse=True):
        uid=row['footprint_uuid'];a,z=old[uid];x,y=new[uid];before=source_text[a:z];after=native_text[x:y]
        def prop(node):
            rows=[(i,j,node[i:j])for i,j in raw.children(node)
                if raw.kind(node[i:j])=='property'and raw.node_uuid(node[i:j])==row['reference_field_uuid']]
            _require(len(rows)==1,'exact_source_native_reference_property_required')
            return rows[0]
        i,j,original=prop(before);_,_,expected=prop(after)
        spans=[]
        for tag in('at','effects'):
            left=[(u,v)for u,v in raw.children(original)if raw.kind(original[u:v])==tag]
            right=[expected[u:v]for u,v in raw.children(expected)if raw.kind(expected[u:v])==tag]
            _require(len(left)==len(right)==1,'unique_known_reference_field_pose_and_effects_required')
            spans.append((*left[0],right[0]))
        # The producer owns only ordinary native text effects, not future
        # opaque author metadata that a native no-op serializer might drop.
        effect=next(original[u:v]for u,v in raw.children(original)if raw.kind(original[u:v])=='effects')
        _require(all(raw.kind(effect[u:v])in('font','justify')for u,v in raw.children(effect)),
            'opaque_reference_effects_require_separate_ownership')
        fonts=[effect[u:v]for u,v in raw.children(effect)if raw.kind(effect[u:v])=='font']
        _require(len(fonts)==1 and all(raw.kind(fonts[0][u:v])in('face','size','thickness','bold','italic')
            for u,v in raw.children(fonts[0])),
            'opaque_reference_font_requires_separate_ownership')
        for u,v,replacement in sorted(spans,reverse=True):original=original[:u]+replacement+original[v:]
        before=before[:i]+original+before[j:];text=text[:a]+before+text[z:]
    return text


def write_private(source,candidate,proposal):
    source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
    _require(source!=candidate and force._hash(source)==force._hash(candidate),
        'exact_private_reference_field_source_copy_required')
    board=construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-reference-field-')as temp:
        expected=Path(temp)/'native.kicad_pcb';field._save_field_snapshot(board,expected)
        text=_literal(raw.raw_text(source),raw.raw_text(expected),proposal)
    raw.write_raw(candidate,text)
    return dict(changed_reference_field_uuids=[r['reference_field_uuid']for r in proposal['records']],
        all_other_literal_source_bytes_preserved=True)


def receive(source,candidate,proposal):
    result=dict(ok=False,complete=False,errors=[],release_authority=False,
        full_native_field_current_Ground_intake_and_visual_receiving_still_required=True)
    try:
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        _require(source!=candidate,'distinct_reference_field_source_and_candidate_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        board=construct(source,proposal)
        with tempfile.TemporaryDirectory(prefix='cec-reference-field-receiving-')as temp:
            expected=Path(temp)/'expected.kicad_pcb';field._save_field_snapshot(board,expected)
            _require(_literal(raw.raw_text(source),raw.raw_text(expected),proposal)==raw.raw_text(candidate),
                'reference_field_changed_unowned_literal_source')
            roundtrip_path=candidate
            for name in('first','second'):
                saved=Path(temp)/(name+'.kicad_pcb');field._save_field_snapshot(pcbnew.LoadBoard(str(roundtrip_path)),saved)
                _require(syntax._freeze(dense._root_annotation_order(ast._nodes(expected)[0]))
                    ==syntax._freeze(dense._root_annotation_order(ast._nodes(saved)[0])),
                    'reference_field_native_roundtrip_changed_unowned_source')
                roundtrip_path=saved
        _require(force._sidecars(source)==force._sidecars(candidate),'reference_field_source_companions_changed')
        _require(epoch==force._code_identity()and dependencies()==proposal['dependencies']
            and families==[force._family(p,proposal['board_hint'])for p in(source,candidate)],
            'reference_field_family_code_or_dependency_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            exact_reference_properties_only=True,all_copper_parts_pads_poses_models_rules_exact=True,
            visible_own_face_readable_native_glyphs=True,whole_saved_second_native_roundtrip_stable=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
