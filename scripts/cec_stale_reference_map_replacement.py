"""Exact annotation-only reseating of a rigid, translated stale body map.

Explicit owner/group/hash selection binds the stale association. Existing
map inspection proves the complete geometry at its inferred old position;
it is never relaxed to accept arbitrary fragments or functional marks.
No placement, copper, current, clipping or fabrication authority is granted.
"""
import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import pcbnew
import cec_additive_route_receiving as ast
import cec_copper_echo as syntax
import cec_force_current as force
import cec_source_reference_group_transport as maps
import cec_source_retaining_ses_import as raw


def _need(value, reason):
    if not value: raise ValueError(reason)


def _move_node(node, delta):
    result=copy.deepcopy(node)
    keys={'at'} if node[0] in ('footprint','gr_text') else {'start','end'}
    found=set()
    for part in result[1:]:
        if isinstance(part,list) and part and part[0] in keys:
            found.add(part[0])
            for axis in (0,1):part[axis+1]=str(Decimal(str(part[axis+1]))+Decimal(delta[axis])/Decimal(1000000))
    _need(found==keys,'exact_native_annotation_coordinates_required')
    return result


def _literal(source, replacements):
    text=raw.raw_text(source);spans=raw.inventory(text)
    for uid in sorted(replacements,key=lambda u:spans[u][0],reverse=True):
        a,z=spans[uid];text=text[:a]+ast._render(replacements[uid])+text[z:]
    return text


def plan(source, *, source_sha256, owner_uuid, group_uuid):
    source=Path(source).resolve(strict=True)
    _need(type(source_sha256)is str and source_sha256==force._hash(source),'exact_stale_map_source_hash_required')
    code=force._code_identity();family=force._family(source)
    nodes=ast._nodes(source)[1];board=pcbnew.LoadBoard(str(source))
    groups=[g for g in board.Groups() if force._uid(g)==group_uuid]
    _need(len(groups)==1,'one_explicit_stale_map_group_required')
    group=groups[0];members=list(group.GetItems())
    owners=[i for i in members if i.GetClass()=='FOOTPRINT']
    texts=[i for i in members if i.GetClass()=='PCB_TEXT']
    lines=[i for i in members if i.GetClass()=='PCB_SHAPE']
    _need(len(owners)==len(texts)==1 and len(lines)+2==len(members)
          and force._uid(owners[0])==owner_uuid,'exact_typed_owner_reference_and_guide_members_required')
    owner=owners[0];text=texts[0]
    _need(group.GetName()==maps.PREFIX+owner.GetReference() and text.GetText()==owner.GetReference(),
          'exact_source_owner_reference_binding_required')
    _need(4<=len(lines)<=5 and all(i.GetShape()==pcbnew.SHAPE_T_SEGMENT for i in lines),
          'complete_rectangle_and_optional_leader_only_required')
    court=owner.GetCourtyard(owner.GetLayer())
    _need(court.OutlineCount()==1 and court.HoleCount(0)==0,'one_source_courtyard_required')
    chain=court.COutline(0);vertices=[tuple(chain.CPoint(i)) for i in range(chain.PointCount())]
    _need(len(vertices)==4 and len({x for x,y in vertices})==len({y for x,y in vertices})==2,
          'cardinal_rectangular_source_courtyard_required')
    edges={tuple(sorted((a,z))) for a,z in zip(vertices,vertices[1:]+vertices[:1])}
    actual={tuple(sorted((tuple(i.GetStart()),tuple(i.GetEnd())))) for i in lines}
    _need(len(actual)==len(lines),'unique_stale_guide_strokes_required')
    # Enumerate exact vertex alignments, not a bbox tolerance or shape allowlist.
    candidates=set()
    for segment in actual:
        for point in segment:
            for vertex in vertices:
                delta=(point[0]-vertex[0],point[1]-vertex[1])
                shifted={tuple(sorted(((a[0]+delta[0],a[1]+delta[1]),(z[0]+delta[0],z[1]+delta[1])))) for a,z in edges}
                if shifted<=actual:candidates.add(delta)
    _need(len(candidates)==1,'one_exact_translated_source_rectangle_required')
    stale_delta=next(iter(candidates))
    _need(stale_delta!=(0,0) and max(map(abs,stale_delta))<=128000000,'bounded_actual_stale_translation_required')
    # Existing inspector proves font, exact opposite face, unique membership,
    # hidden reference, no foreign/functional strokes and exact nearest leader.
    with tempfile.TemporaryDirectory(prefix='cec-stale-map-proof-') as directory:
        virtual=force._copy_family(source,Path(directory)/'virtual')
        raw.write_raw(virtual,_literal(source,{owner_uuid:_move_node(nodes[owner_uuid],stale_delta)}))
        proof=maps.inspect(virtual,owner_uuid=owner_uuid,group_uuid=group_uuid)
        _need(proof.get('outline_style') is None,'complete_stale_rectangle_required')
    annotation_ids=sorted(force._uid(i) for i in [text,*lines])
    _need(force._hash(source)==source_sha256 and force._code_identity()==code and force._family(source)==family,
          'stale_map_source_or_code_changed')
    return dict(schema=1,scope='exact_explicit_source_stale_rectangle_annotation_replacement',
                source=str(source),source_sha256=source_sha256,code_identity=code,source_family=family,
                owner_uuid=owner_uuid,group_uuid=group_uuid,reference=owner.GetReference(),
                annotation_uuids=annotation_ids,delta_nm=[-v for v in stale_delta],
                original_group_members=sorted(force._uid(i) for i in members),
                source_nodes={u:nodes[u] for u in [owner_uuid,group_uuid,*annotation_ids]},
                owner_pose_and_all_material_unchanged=True,release_authority=False)


def _fresh(source, proposal):
    fresh=plan(source,source_sha256=proposal['source_sha256'],owner_uuid=proposal['owner_uuid'],group_uuid=proposal['group_uuid'])
    _need(syntax._freeze(fresh)==syntax._freeze(proposal),'stale_or_forged_annotation_replacement_required')
    return fresh


def write_private(source,candidate,proposal):
    source=Path(source).resolve();candidate=Path(candidate).resolve()
    _need(source!=candidate and force._hash(source)==force._hash(candidate),'exact_distinct_private_source_copy_required')
    _need(force._sidecars(source)==force._sidecars(candidate),'annotation_source_companions_must_remain_exact')
    q=_fresh(source,proposal)
    replacements={u:_move_node(q['source_nodes'][u],q['delta_nm']) for u in q['annotation_uuids']}
    raw.write_raw(candidate,_literal(source,replacements))
    return dict(changed_annotation_uuids=q['annotation_uuids'],footprint_and_group_unchanged=True,release_authority=False)


def receive(source,candidate,proposal):
    q=_fresh(source,proposal);candidate=Path(candidate).resolve(strict=True)
    _need(candidate!=Path(source).resolve(),'distinct_annotation_child_required')
    _need(force._sidecars(Path(source).resolve())==force._sidecars(candidate),'annotation_source_companions_must_remain_exact')
    replacements={u:_move_node(q['source_nodes'][u],q['delta_nm']) for u in q['annotation_uuids']}
    _need(raw.raw_text(candidate)==_literal(source,replacements),'whole_board_exact_annotation_delta_required')
    proof=maps.inspect(candidate,owner_uuid=q['owner_uuid'],group_uuid=q['group_uuid'])
    return dict(ok=True,complete=True,source_sha256=q['source_sha256'],candidate_sha256=force._hash(candidate),
                exact_changed_annotation_uuids=q['annotation_uuids'],all_other_source_bytes_exact=True,
                existing_source_association_inspector_passes=True,current_qualified=False,release_authority=False)
