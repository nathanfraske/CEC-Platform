"""Recognize an actual saved chart, not an ancestor's manufacturing authority.

Reconstruct every glyph, scaled native courtyard, title, frame and leader from
the CURRENT immutable Source. Explicit UUIDs only select existing groups.
Nothing here authorizes a footprint pose, copper delta, body clearance, route,
current, mask, fabrication or release. Those independent gates remain due.
"""
from collections import Counter
import hashlib,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_dense_reference_mapping as producer
import cec_reference_map_reownership as geometry
import cec_additive_route_receiving as ast


def _need(value,message):
    if not value:raise ValueError(message)


def dependencies():
    return {str(Path(module.__file__).resolve()):force._hash(Path(module.__file__))
        for module in(producer,geometry)}|{str(Path(__file__).resolve()):force._hash(Path(__file__))}


def _signature(item):
    return json.dumps(geometry._geometry(item),sort_keys=True,separators=(',',':'))


def inspect_many(source,group_uuids,*,timeout_s=10.,_source_board=None):
    _need(type(group_uuids)in(list,tuple)and 1<=len(group_uuids)<=8
        and all(type(u)is str and u for u in group_uuids)and len(set(group_uuids))==len(group_uuids)
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_explicit_existing_chart_groups_required')
    source=Path(source).resolve(strict=True);digest=force._hash(source);epoch=force._code_identity()
    sidecars=force._sidecars(source)
    deps=dependencies();deadline=time.monotonic()+timeout_s
    def tick():_need(time.monotonic()<deadline,'existing_reference_chart_deadline')
    board=_source_board if _source_board is not None else pcbnew.LoadBoard(str(source))
    _need(board is not None and Path(board.GetFileName()).resolve()==source,'exact_current_chart_Source_required')
    root,nodes=ast._nodes(source);groups={force._uid(g):g for g in board.Groups()}
    root_ids=[]
    for node in root[1:]:
        if not isinstance(node,list):continue
        ids=[sub[1].strip('"')for sub in node[1:]if isinstance(sub,list)and len(sub)==2 and sub[0]=='uuid']
        root_ids.extend(ids)
    literal_counts=Counter(root_ids)
    floors=producer.floors(board,source);answer={};owned=set()
    for uid in group_uuids:
        tick();_need(uid in groups and uid in nodes,'actual_saved_chart_group_required');group=groups[uid]
        items=list(group.GetItems());members=[force._uid(i)for i in items]
        _need(group.GetName()==producer.GROUP and group.IsLocked()and not group.GetParentGroup()
            and 1<=len(items)<=128 and len(set(members))==len(members)
            and len(ast._members(nodes[uid]))==len(members)
            and set(ast._members(nodes[uid]))==set(members)and not owned&set(members)
            and all(literal_counts[item]==1 for item in[uid,*members]),
            'complete_disjoint_locked_unnested_saved_chart_group_required')
        _need(all(sum(g.ContainsItem(item)for g in board.Groups())==1 for item in items),
            'chart_members_must_have_unique_actual_group_ownership')
        owners=[i for i in items if i.GetClass()=='FOOTPRINT'];ink=[i for i in items if i.GetClass()!='FOOTPRINT']
        _need(1<=len(owners)<=8 and len({f.GetReference()for f in owners})==len(owners)
            and all(not f.Reference().IsVisible()and not f.IsDNP()and not f.IsLocked()for f in owners),
            'complete_actual_hidden_populated_chart_owners_required')
        _need(all(i.GetClass()in('PCB_SHAPE','PCB_TEXT')and i.IsLocked()for i in ink),
            'only_complete_locked_root_chart_ink_required')
        face=pcbnew.F_SilkS if owners[0].IsFlipped()else pcbnew.B_SilkS
        _need(all(f.IsFlipped()==owners[0].IsFlipped()for f in owners)
            and all(i.GetLayer()==face for i in ink),'one_correct_opposite_chart_face_required')
        titles=[i for i in ink if i.GetClass()=='PCB_TEXT'and i.GetText()=='REF MAP']
        _need(len(titles)==1,'one_exact_existing_chart_title_required')
        labels={}
        for fp in owners:
            matches=[i for i in ink if i.GetClass()=='PCB_TEXT'and i.GetText()==fp.GetReference()]
            _need(len(matches)==1,'one_exact_native_reference_per_chart_owner_required')
            labels[force._uid(fp)]=matches[0]
        _need(sum(i.GetClass()=='PCB_TEXT'for i in ink)==len(owners)+1,'no_unknown_chart_text_required')
        actual=Counter(_signature(i)for i in ink);models=[(fp,producer.court(fp))for fp in owners]
        _need(all(not model.is_empty and model.is_valid for fp,model in models),'actual_closed_Source_chart_courtyards_required')
        first,body=models[0];at=labels[force._uid(first)].GetPosition();matches=[]
        # Exactly the existing public chart producer's finite scale portfolio.
        # Position is observed from actual saved text, never supplied by a worker.
        for scale in(1.5,2.,3.):
            tick();delta=(at.x/1e6-scale*body.centroid.x,at.y/1e6-scale*body.centroid.y)
            try:
                expected,_,records=producer.shapes(board,models,face,floors,positions=delta,scale=scale)
                decoration,_,_=producer.chart_decoration(board,records,models,face,floors)
                expected+=decoration
                for item in expected:item.SetLocked(True)
                if Counter(_signature(i)for i in expected)==actual:matches.append((scale,delta,records))
            except ValueError:continue
        _need(len(matches)==1,'entire_current_Source_chart_geometry_must_reconstruct_uniquely')
        scale,delta,records=matches[0];owned.update(members)
        chart_digest=hashlib.sha256(json.dumps(sorted(actual.elements()),separators=(',',':')).encode()).hexdigest()
        for fp in owners:
            owner=force._uid(fp);_need(owner not in answer,'one_current_chart_association_per_owner_required')
            answer[owner]=dict(owner_uuid=owner,group_uuid=uid,source=str(source),source_sha256=digest,
                reference_association_kind='fresh_current_Source_native_chart_reconstruction',
                chart_geometry_sha256=chart_digest,scale=scale,translation_mm=list(delta),
                member_uuids=sorted(members),complete_current_native_ink_reconstructed=True,
                closed_assembly_body_authority=False,current_authority=False,copper_admission=False,
                pose_authority=False,release_authority=False,
                unrelated_Source_material_not_authorized_by_reference_association=True)
    tick();_need(digest==force._hash(source)and sidecars==force._sidecars(source)and epoch==force._code_identity()
        and deps==dependencies(),'existing_chart_Source_code_or_dependencies_changed')
    return answer
