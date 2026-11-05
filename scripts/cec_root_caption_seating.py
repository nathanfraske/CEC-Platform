"""Reviewed standalone caption seating, optionally raised to readable floors.

The caller's semantic assertion is external review, NOT automatic functional
mark classification or qualification. No footprint field, marker or graphic is
owned. Saved native DRC and all whole-parent gates remain independently required.
"""
import math
import re
import tempfile
import time
from pathlib import Path

import pcbnew
from shapely import affinity
from shapely.ops import unary_union
from shapely.prepared import prep
import cec_reference_field_seating as seats
import cec_source_literal_additions as literal

force=seats.force
raw=seats.raw
POLICY='externally-reviewed-standalone-board-caption-v1'


def _need(value,message):
    if not value:raise ValueError(message)


def dependencies():
    return {str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
        for m in (seats,seats.dense,seats.masks,seats.ink,seats.qualified,literal,raw)}|{
        str(Path(__file__).resolve()):force._hash(Path(__file__).resolve())}


def _root_text(text,uid):
    found=[(a,z)for a,z in literal._root(text)[0]
        if raw.kind(text[a:z])=='gr_text'and raw.node_uuid(text[a:z])==uid]
    _need(len(found)==1,'one_literal_source_root_caption_required')
    return found[0]


def _translated(text,uid,at_nm):
    a,z=_root_text(text,uid);node=text[a:z]
    locations=[(x,y)for x,y in raw.children(node)if raw.kind(node[x:y])=='at']
    _need(len(locations)==1,'one_literal_caption_position_required')
    x,y=locations[0];at=node[x:y]
    match=re.fullmatch(r'(\(at\s+)[^\s()]+(\s+)[^\s()]+(.*\))',at,re.S)
    _need(match is not None,'known_literal_caption_position_required')
    # Preserve angle, flags, spacing and every non-owned byte, even metadata
    # unknown to the native serializer. Only the two translation tokens change.
    def mm(v):return format(v/1e6,'.6f').rstrip('0').rstrip('.')or '0'
    moved=match[1]+mm(at_nm[0])+match[2]+mm(at_nm[1])+match[3]
    return text[:a]+node[:x]+moved+node[y:]+text[z:]


def _edited(text,uid,at_nm,readable=None):
    text=_translated(text,uid,at_nm)
    if readable is None:return text
    a,z=_root_text(text,uid);node=text[a:z]
    def child(parent,tag):
        rows=[(x,y)for x,y in raw.children(parent)if raw.kind(parent[x:y])==tag]
        _need(len(rows)==1,'exact_literal_caption_'+tag+'_required');return rows[0]
    e0,e1=child(node,'effects');effect=node[e0:e1]
    f0,f1=child(effect,'font');font=effect[f0:f1];edits=[]
    # KiCad's literal size is HEIGHT WIDTH, native VECTOR2I is WIDTH HEIGHT.
    for tag,values in [('size',list(reversed(readable['size_nm']))),('thickness',[readable['stroke_nm']])]:
        x,y=child(font,tag);token=font[x:y]
        match=re.fullmatch(r'(\('+tag+r'\s+)([^\s()]+)'+
            (r'(\s+)([^\s()]+)'if len(values)==2 else '')+r'(\s*\))',token)
        _need(match is not None,'known_literal_caption_font_numeric_tokens_required')
        parts=list(match.groups())
        for index,value in enumerate(values):
            old=parts[1+2*index]
            _need(math.isfinite(float(old)),'finite_literal_caption_font_required')
            if round(float(old)*1e6)!=value:
                parts[1+2*index]=format(value/1e6,'.6f').rstrip('0').rstrip('.')or '0'
        edits.append((e0+f0+x,e0+f0+y,''.join(parts)))
    for x,y,replacement in sorted(edits,reverse=True):node=node[:x]+replacement+node[y:]
    return text[:a]+node+text[z:]


def _apply_readable(caption,readable):
    if readable is not None:
        caption.SetTextSize(pcbnew.VECTOR2I(*readable['size_nm']))
        caption.SetTextThickness(readable['stroke_nm'])


def plan(source,*,grade,board_hint,caption_uuid,expected_text,caption_scope,
         max_translation_mm=5.,step_mm=.5,maximum_candidates=1024,
         reviewed_courtyard_contract_ids=(),timeout_s=10.,raise_to_readable_floor=False):
    _need(type(raise_to_readable_floor)is bool,'strict_boolean_caption_readable_floor_opt_in_required')
    _need(caption_scope==POLICY and type(expected_text)is str and 0<len(expected_text)<=512
        and type(caption_uuid)is str and bool(caption_uuid)
        and type(board_hint)is str and bool(board_hint),'explicit_reviewed_board_caption_scope_required')
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10
        and type(max_translation_mm)in(int,float)and math.isfinite(max_translation_mm)
        and .25<=max_translation_mm<=10 and type(step_mm)in(int,float)
        and math.isfinite(step_mm)and .1<=step_mm<=2
        and type(maximum_candidates)is int and 1<=maximum_candidates<=4096,
        'bounded_caption_seating_search_required')
    _need(type(reviewed_courtyard_contract_ids)in(list,tuple)
        and len(reviewed_courtyard_contract_ids)<=8
        and len(set(reviewed_courtyard_contract_ids))==len(reviewed_courtyard_contract_ids)
        and all(type(k)is str and k for k in reviewed_courtyard_contract_ids),
        'bounded_reviewed_caption_body_context_required')
    start=time.monotonic();deadline=start+timeout_s;deps=dependencies()
    source=Path(source).resolve(strict=True)
    board,f,report,binding=seats.dense.source_context(source,grade,board_hint)
    _root_text(raw.raw_text(source),caption_uuid)
    drawings=list(board.GetDrawings());fps=list(board.GetFootprints());tracks=list(board.GetTracks())
    _need(len(drawings)+len(fps)+len(tracks)<=16384,'bounded_caption_obstacle_inventory_required')
    found=[i for i in drawings if force._uid(i)==caption_uuid and i.GetClass()=='PCB_TEXT']
    _need(len(found)==1,'one_source_root_native_caption_required');caption=found[0]
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    grouped.update(u for n in seats.ast._nodes(source)[1].values()
        if n[0]=='group'for u in seats.ast._members(n))
    _need(caption.GetText()==expected_text and not caption.IsLocked()
        and caption.IsVisible()and caption_uuid not in grouped and not caption.GetParentGroup()
        and caption.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS),
        'exact_visible_unlocked_ungrouped_silk_caption_required')
    _need(any(v.get('type')in('silk_overlap','silk_over_copper','silk_edge_clearance')
        and any(i.get('uuid')==caption_uuid for i in v.get('items',[]))
        for v in report['violations']),'actual_source_native_caption_finding_required')
    _need(raise_to_readable_floor or(min(caption.GetTextSize())>=round(f['height']*1e6)
        and caption.GetTextThickness()>=round(f['stroke']*1e6)),
        'source_caption_below_readable_factory_floor')
    readable=(dict(size_nm=[max(v,round(f['height']*1e6))for v in caption.GetTextSize()],
        stroke_nm=max(caption.GetTextThickness(),round(f['stroke']*1e6)))
        if raise_to_readable_floor else None)
    _apply_readable(caption,readable)
    bodies,proofs,unknown=seats._reviewed_body_shapes(source,board,board_hint,
        reviewed_courtyard_contract_ids,deadline)
    face=caption.GetLayer();cu=pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu
    _need(not any(force._uid(fp)in unknown and fp.GetLayer()==cu for fp in fps),
        'unknown_source_caption_assembled_body')
    obstacles=[]
    for item in drawings:
        seats._tick(deadline)
        if item.GetLayer()==face and force._uid(item)!=caption_uuid:
            obstacles.append(seats.dense.polygon(item,face))
    for fp in fps:
        seats._tick(deadline)
        if fp.GetLayer()==cu and force._uid(fp)in bodies:obstacles.append(bodies[force._uid(fp)])
        for item in [*fp.GetFields(),*fp.GraphicalItems()]:
            if item.GetLayer()==face and(not hasattr(item,'IsVisible')or item.IsVisible()):
                obstacles.append(seats.dense.polygon(item,face))
    obstacles.extend(seats.assembly.polygon_from_native(p)for _,p in
        seats.ink._mask_openings(board,face,'native_mask_and_bore'))
    obstacles.append(seats.masks.native_mask_artwork(board,face)[0])
    blocked=prep(unary_union(obstacles).buffer(f['clearance']+.002,join_style=2))
    material=prep(seats.assembly.polygon_from_native(seats.geometry.outline_material(board))
        .buffer(-f['edge'],join_style=2))
    shape=seats.dense.polygon(caption,face);radius=round(max_translation_mm*1e6)
    step=round(step_mm*1e6);count=radius//step
    _need((2*count+1)**2-1<=maximum_candidates,'caption_candidate_work_limit')
    offsets=sorted(((x*step,y*step)for x in range(-count,count+1)
        for y in range(-count,count+1)if 0<x*x+y*y and (x*step)**2+(y*step)**2<=radius**2),
        key=lambda p:(p[0]*p[0]+p[1]*p[1],p))
    position=tuple(caption.GetPosition());chosen=None
    for delta in offsets:
        seats._tick(deadline);moved=affinity.translate(shape,delta[0]/1e6,delta[1]/1e6)
        if material.contains(moved)and not blocked.intersects(moved):
            chosen=[position[i]+delta[i]for i in (0,1)];break
    _need(chosen is not None,'no_readable_clear_source_caption_seat')
    seats._tick(deadline)
    _need(deps==dependencies()and binding['source_sha256']==force._hash(source)
        and binding['code_identity']==force._code_identity(),'caption_source_or_code_changed')
    result=dict(schema=1,policy=POLICY,source=str(source),grade=str(Path(grade).resolve()),
        board_hint=board_hint,binding=binding,dependencies=deps,caption_uuid=caption_uuid,
        expected_text=expected_text,at_nm=chosen,reviewed_body_reservations=proofs,
        request=dict(caption_uuid=caption_uuid,expected_text=expected_text,caption_scope=caption_scope,
            max_translation_mm=max_translation_mm,step_mm=step_mm,maximum_candidates=maximum_candidates,
            reviewed_courtyard_contract_ids=list(reviewed_courtyard_contract_ids),timeout_s=timeout_s),
        semantic_scope_is_external_review_not_auto_classification=True,
        body_context_is_obstacle_only=True,release_authority=False)
    if raise_to_readable_floor:
        result['request']['raise_to_readable_floor']=True
        result['readable_floor']=readable
    return result


def _replay(source,proposal):
    fresh=plan(source,grade=proposal['grade'],board_hint=proposal['board_hint'],**proposal['request'])
    _need(fresh==proposal,'stale_or_forged_root_caption_plan');return fresh


def construct(source,proposal):
    fresh=_replay(source,proposal);board=pcbnew.LoadBoard(str(source))
    caption=next(i for i in board.GetDrawings()if force._uid(i)==fresh['caption_uuid'])
    _apply_readable(caption,fresh.get('readable_floor'))
    caption.SetTextPos(pcbnew.VECTOR2I(*fresh['at_nm']));return board


def write_private(source,candidate,proposal):
    source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
    _need(source!=candidate and force._hash(source)==force._hash(candidate),
        'exact_private_caption_source_copy_required')
    fresh=_replay(source,proposal)
    raw.write_raw(candidate,_edited(raw.raw_text(source),fresh['caption_uuid'],fresh['at_nm'],fresh.get('readable_floor')))
    return dict(translation_only='readable_floor'not in fresh,
        exact_reviewed_caption_translation_and_readable_floor_only=True,all_nonowned_raw_bytes_preserved=True)


def receive(source,candidate,proposal):
    result=dict(ok=False,complete=False,errors=[],release_authority=False,
        full_native_and_selected_parent_receiving_still_required=True)
    try:
        source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
        _need(source!=candidate,'distinct_caption_source_and_candidate_required')
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        expected=construct(source,proposal)
        _need(raw.raw_text(candidate)==_edited(raw.raw_text(source),proposal['caption_uuid'],proposal['at_nm'],proposal.get('readable_floor')),
            'caption_changed_unowned_literal_source')
        _need(force._sidecars(source)==force._sidecars(candidate),'caption_source_companions_changed')
        with tempfile.TemporaryDirectory(prefix='cec-root-caption-')as work:
            p=Path(work)/'expected.kicad_pcb';seats.field._save_field_snapshot(expected,p)
            canonical=seats.syntax._freeze(seats.ast._nodes(p)[0]);current=candidate
            for name in ('first','second'):
                p=Path(work)/(name+'.kicad_pcb')
                seats.field._save_field_snapshot(pcbnew.LoadBoard(str(current)),p)
                _need(seats.syntax._freeze(seats.ast._nodes(p)[0])==canonical,
                    'caption_native_saved_geometry_or_style_changed');current=p
        _need(epoch==force._code_identity()and families==[force._family(p,proposal['board_hint'])for p in(source,candidate)]
            and dependencies()==proposal['dependencies'],'caption_family_or_code_changed')
        result.update(ok=True,complete=True,translation_only='readable_floor'not in proposal,
            exact_reviewed_caption_translation_and_readable_floor_only=True,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),whole_saved_second_native_roundtrip_stable=True,
            semantic_scope_is_external_review_not_auto_classification=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,StopIteration)as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def query_input_identity(source,candidate,proposal):
    """Entire identity except freshly received caption x/y and opted-in floors.

    Only the literal reviewed caption's received scope is normalized. This is
    identical electrical-query input evidence, not absolute qualification
    and not permission to omit any ink or move a functional marking.
    """
    result=dict(ok=False,complete=False,comparison_complete=False,same_material=False,
        scope='complete_raw_native_identity_except_fresh_reviewed_root_caption_translation',
        mutation_authority=False,full_kelvin_qualification=False,release_authority=False)
    try:
        epoch=force._code_identity();source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
        families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        proof=receive(source,candidate,proposal)
        _need(all(proof.get(k)is True for k in('ok','complete','exact_reviewed_caption_translation_and_readable_floor_only',
            'whole_saved_second_native_roundtrip_stable')),'fresh_exact_caption_scope_required_for_query_identity')
        uid=proposal['caption_uuid']
        readable=proposal.get('readable_floor')
        _need(_edited(raw.raw_text(source),uid,[0,0],readable)==_edited(raw.raw_text(candidate),uid,[0,0],readable),
            'caption_query_changed_nontranslation_raw_inputs')
        native=[];boards=[]
        with tempfile.TemporaryDirectory(prefix='cec-caption-query-')as work:
            for index,path in enumerate((source,candidate)):
                board=pcbnew.LoadBoard(str(path));boards.append(board)
                caption=next(i for i in board.GetDrawings()if force._uid(i)==uid)
                caption.SetTextPos(pcbnew.VECTOR2I(0,0))
                _apply_readable(caption,readable)
                saved=Path(work)/(str(index)+'.kicad_pcb');seats.field._save_field_snapshot(board,saved)
                native.append(seats.syntax._freeze(seats.ast._nodes(saved)[0]))
        _need(native[0]==native[1],'caption_query_changed_complete_native_inputs')
        _need(epoch==force._code_identity()and families==[
            force._family(p,proposal['board_hint'])for p in(source,candidate)],'caption_query_source_family_or_code_changed')
        result.update(ok=True,complete=True,comparison_complete=True,same_material=True,
            independent_translation_receiving=proof,
            all_nontranslation_raw_and_native_inputs_equal=readable is None,
            all_noncaption_translation_and_readable_floor_raw_native_inputs_equal=True,
            inherited_electrical_debt='unchanged_not_evaluated')
        if readable is not None:
            result['scope']='complete_raw_native_identity_except_fresh_reviewed_caption_translation_and_readable_floor'
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,StopIteration)as exc:
        result['error']=type(exc).__name__+':'+str(exc)
    return result
