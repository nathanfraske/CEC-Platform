"""Bounded native field layout for moved supports, without hiding or resizing.

Reference/value identity, font, thickness, visibility, layer and all component
geometry remain source-authored. Only bounded cardinal text poses can move.
This advisory constructor still requires saved KiCad DRC and exact replay.
"""
import math
import time
import pcbnew
import cec_force_current as force

MAX_OWNER_DISTANCE_MM = 5.0


def _native_boxes_near(a,b,clearance):
    """A disjoint native bbox rejects work, never certifies a legal seat."""
    return not (a.GetRight()+clearance<b.GetLeft() or b.GetRight()+clearance<a.GetLeft()
        or a.GetBottom()+clearance<b.GetTop() or b.GetBottom()+clearance<a.GetTop())


def construct_changed_components(board, changed_footprint_uuids, *, timeout_per_component_s=10.):
    """Jointly solve overlapping five-mm text domains, not one owner at a time.

    Independent changed regions must not consume a shared eight-owner budget.
    Conversely, neighboring changed owners must be solved together so an
    early label cannot consume a later owner's only seat. Native collision
    discovery and the existing per-component bound remain unchanged. The
    complete operation restores all field poses if any component is refused.
    This is advisory geometry only; saved native DRC still decides admission.
    """
    if (type(changed_footprint_uuids) not in (list,tuple,set)
            or not 1<=len(changed_footprint_uuids)<=64
            or len(set(changed_footprint_uuids))!=len(changed_footprint_uuids)
            or any(type(u) is not str or not u for u in changed_footprint_uuids)
            or type(timeout_per_component_s) not in (int,float)
            or not math.isfinite(timeout_per_component_s) or not 0<timeout_per_component_s<=10):
        raise ValueError('bounded_native_changed_field_components_required')
    owners={force._uid(fp):fp for fp in board.GetFootprints()}
    changed=set(changed_footprint_uuids)
    if not changed<=owners.keys():raise ValueError('native_changed_field_owner_identity_required')
    remaining=set(changed);components=[]
    while remaining:
        root=min(remaining);remaining.remove(root);cohort={root};pending=[root]
        while pending:
            uid=pending.pop();at=tuple(owners[uid].GetPosition())
            adjacent={other for other in remaining if math.dist(at,tuple(owners[other].GetPosition()))
                <=2*MAX_OWNER_DISTANCE_MM*1000000}
            remaining-=adjacent;cohort|=adjacent;pending.extend(sorted(adjacent))
        if len(cohort)>8:
            return dict(ok=False,reason='native_connected_changed_field_component_bound',
                component_footprint_uuids=sorted(cohort),release_authority=False)
        components.append(sorted(cohort))
    originals=[(f,pcbnew.VECTOR2I(f.GetPosition()),f.GetTextAngle().AsDegrees())
        for fp in owners.values() for f in (fp.Reference(),fp.Value())]
    accepted=False;layouts=[]
    try:
        for cohort in components:
            result=construct_collision_cohort(board,cohort,timeout_s=timeout_per_component_s,
                include_changed_owners=True,candidate_choices=4,allow_mixed_silk_fields=True)
            layouts.append(dict(changed_footprint_uuids=cohort,receiving=result))
            if not result['ok']:
                return dict(ok=False,reason='native_changed_field_component_refused',
                    local_components=layouts,release_authority=False)
        accepted=True
        return dict(ok=True,local_components=layouts,
            source_strings_fonts_visibility_and_layers_preserved=True,
            component_and_copper_geometry_changed=False,release_authority=False)
    finally:
        if not accepted:
            for f,position,angle in originals:
                f.SetPosition(position);f.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))


def construct_collision_cohort(board, changed_footprint_uuids, *, timeout_s=10., max_owners=8,
                               include_changed_owners=False,candidate_choices=1,allow_mixed_silk_fields=False):
    """Reflow only neighboring fields hit by actual changed pad/ink geometry.

    A moved support's labels may be legal while its new pad openings collide
    with stationary neighbors' labels. Rediscover those neighbors in native
    geometry; do not infer them from refdes or authorize any component motion.
    Opt-in joint layout includes the changed owners in the same largest-ink
    first solve: seating a small owner first must not consume the only legal
    slot of a larger impacted neighbor. Defaults retain neighbor-only scope.
    The complete bounded cohort rolls back on failure. Saved DRC still decides
    admission, and this constructor grants no clearance or release waiver.
    """
    if (type(changed_footprint_uuids) not in (list, tuple, set)
            or not 1 <= len(changed_footprint_uuids) <= 8
            or len(set(changed_footprint_uuids)) != len(changed_footprint_uuids)
            or any(type(u) is not str or not u for u in changed_footprint_uuids)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_owners) is not int
            or not 1 <= max_owners <= 8 or type(include_changed_owners) is not bool
            or type(candidate_choices) is not int or not 1<=candidate_choices<=4
            or type(allow_mixed_silk_fields) is not bool):
        raise ValueError('bounded_native_neighbor_field_cohort_required')
    owners = {force._uid(fp): fp for fp in board.GetFootprints()}
    changed = set(changed_footprint_uuids)
    if not changed <= owners.keys():
        raise ValueError('native_changed_field_owner_identity_required')
    deadline = time.monotonic() + timeout_s
    gap = max(150000, int(board.GetDesignSettings().m_SilkClearance))
    targets = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for uid in sorted(changed):
        fp = owners[uid]
        for silk, copper, mask in ((pcbnew.F_SilkS, pcbnew.F_Cu, pcbnew.F_Mask),
                                   (pcbnew.B_SilkS, pcbnew.B_Cu, pcbnew.B_Mask)):
            targets[silk].extend((p.GetEffectiveShape(copper),
                gap + max(0, p.GetSolderMaskExpansion(copper)) + 1000)
                for p in fp.Pads() if p.IsOnLayer(copper) and p.IsOnLayer(mask))
            targets[silk].extend((g.GetEffectiveShape(), gap + 1000)
                for g in fp.GraphicalItems() if g.GetLayer() == silk
                and (not hasattr(g, 'IsVisible') or g.IsVisible()))
    impacted = []
    for uid, fp in sorted(owners.items()):
        if time.monotonic() >= deadline:
            return dict(ok=False, reason='native_neighbor_field_cohort_deadline', release_authority=False)
        if uid in changed:
            continue
        if any(f.IsVisible() and f.GetLayer() in targets
                and any(f.GetEffectiveTextShape().Collide(shape, clearance)
                        for shape, clearance in targets[f.GetLayer()])
                for f in (fp.Reference(), fp.Value())):
            impacted.append(uid)
    if len(impacted) > max_owners or len(changed | set(impacted)) > 8:
        return dict(ok=False, reason='native_neighbor_field_cohort_bound',
            impacted_footprint_uuids=impacted, release_authority=False)
    # Place the largest source-authored ink first. Only not-yet-placed fields
    # in this exact rediscovered cohort may be omitted as provisional peers.
    # Each subsequent owner sees every completed seat; no pad, graphic or
    # external label is omitted. Any failure restores the complete cohort.
    def ink_area(uid):
        areas = []
        for f in (owners[uid].Reference(), owners[uid].Value()):
            shape = f.GetEffectiveTextShape()
            bounds = shape.BBox()
            areas.append(bounds.GetWidth() * bounds.GetHeight())
        return max(areas)
    impacted.sort(key=lambda uid: (-ink_area(uid), uid))
    layout_owners = sorted(set(impacted) | (changed if include_changed_owners else set()),
        key=lambda uid: (-ink_area(uid), uid))
    originals = [(f, pcbnew.VECTOR2I(f.GetPosition()), f.GetTextAngle().AsDegrees())
        for uid in layout_owners for f in (owners[uid].Reference(), owners[uid].Value())]
    layouts = []
    search_states=0
    last_refusal=[]
    accepted = False
    try:
        def solve(index,chosen):
            nonlocal search_states,last_refusal
            if index==len(layout_owners):return chosen
            uid=layout_owners[index]
            pending={force._uid(f) for other in layout_owners[index+1:]
                for f in (owners[other].Reference(),owners[other].Value())}
            baseline=[(f,pcbnew.VECTOR2I(f.GetPosition()),f.GetTextAngle().AsDegrees())
                for other in layout_owners[index:] for f in (owners[other].Reference(),owners[other].Value())]
            for rank in range(candidate_choices):
                if search_states>=64 or time.monotonic()>=deadline:return None
                for f,position,angle in baseline:
                    f.SetPosition(position);f.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
                search_states+=1
                result=_construct(board,owners[uid].GetReference(),allow_multiland_owner=True,
                    timeout_s=min(10.,deadline-time.monotonic()),pending_field_uuids=pending,candidate_rank=rank,
                    allow_mixed_silk_fields=allow_mixed_silk_fields)
                result=dict(result,ref=owners[uid].GetReference(),footprint_uuid=uid,candidate_rank=rank)
                if not result['ok']:
                    last_refusal=chosen+[result];break
                found=solve(index+1,chosen+[result])
                if found is not None:return found
            return None
        found=solve(0,[])
        if found is None:
            return dict(ok=False,reason='bounded_native_neighbor_field_backtracking_refused',
                layouts=last_refusal,search_states=search_states,release_authority=False)
        layouts=found
        accepted = True
        return dict(ok=True, impacted_footprint_uuids=impacted,
            reflowed_footprint_uuids=layout_owners, include_changed_owners=include_changed_owners, layouts=layouts,
            source_strings_fonts_visibility_and_layers_preserved=True,search_states=search_states,
            component_and_copper_geometry_changed=False, release_authority=False)
    finally:
        if not accepted:
            for f, position, angle in originals:
                f.SetPosition(position)
                f.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))


def replay_poses(base,target):
    """Copy only the two allowed text poses into a SOURCE-reconstructed owner.

    The caller compares the complete serialized owner afterwards. A worker
    cannot smuggle a smaller/hidden label, changed string or other geometry
    through these two setters. No separate footprint properties are copied.
    """
    wanted={f.GetName():f for f in target.GetFields()}
    at=base.GetPosition()
    for field in base.GetFields():
        if field.GetName() not in ('Reference','Value'):continue
        other=wanted.get(field.GetName())
        if (other is None or force._uid(field)!=force._uid(other)
                or other.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS)
                or field.GetLayer()!=other.GetLayer()
                or math.hypot(other.GetPosition().x-at.x,other.GetPosition().y-at.y)>MAX_OWNER_DISTANCE_MM*1e6
                or abs(other.GetTextAngle().AsDegrees()/90-round(other.GetTextAngle().AsDegrees()/90))>1e-8):
            raise ValueError('bounded_source_authored_support_text_poses_required')
        field.SetPosition(other.GetPosition());field.SetTextAngle(other.GetTextAngle())


def construct(board,ref, *, allow_multiland_owner=False, timeout_s=10.):
    return _construct(board, ref, allow_multiland_owner=allow_multiland_owner, timeout_s=timeout_s)


def _construct(board,ref, *, allow_multiland_owner=False, timeout_s=10., pending_field_uuids=frozenset(),candidate_rank=0,
               allow_mixed_silk_fields=False):
    if (type(allow_multiland_owner) is not bool or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(candidate_rank) is not int or not 0<=candidate_rank<=3
            or type(allow_mixed_silk_fields) is not bool):
        raise ValueError('bounded_native_owner_field_layout_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise TimeoutError('native_owner_field_layout_deadline')
    fp=board.FindFootprintByReference(ref)
    if (fp is None or not 1<=len(list(fp.Pads()))<=128
            or not allow_multiland_owner and len(list(fp.Pads()))!=2):
        raise ValueError('two_land_support_or_explicit_bounded_multiland_owner_required')
    fields=[fp.Reference(),fp.Value()]
    if allow_mixed_silk_fields:
        fields=[f for f in fields if f.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)]
        if not fields:
            return dict(ok=True,ref=ref,tries=0,fields=[],non_silkscreen_fields_unchanged=True,release_authority=False)
    if (any(f.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS) for f in fields)
            or len({f.GetLayer() for f in fields})!=1):
        return dict(ok=False,reason='source_fields_not_silkscreen')
    original=[(pcbnew.VECTOR2I(f.GetPosition()),f.GetTextAngle().AsDegrees()) for f in fields]
    at=fp.GetPosition();layer=fields[0].GetLayer();copper=pcbnew.F_Cu if layer==pcbnew.F_SilkS else pcbnew.B_Cu
    gap=max(150000,int(board.GetDesignSettings().m_SilkClearance))
    peers=[];pads=[]
    for owner in board.GetFootprints():
        tick()
        peers.extend(f for f in [*owner.GetFields(),*owner.GraphicalItems()]
            if f.GetLayer()==layer and force._uid(f) not in {force._uid(v) for v in fields} | pending_field_uuids
            and (not hasattr(f,'IsVisible') or f.IsVisible()))
        pads.extend(p for p in owner.Pads() if p.IsOnLayer(copper) and p.IsOnLayer(pcbnew.F_Mask if copper==pcbnew.F_Cu else pcbnew.B_Mask))
    peers.extend(t for t in board.GetDrawings() if t.GetLayer()==layer
        and (not hasattr(t,'IsVisible') or t.IsVisible()))
    def shape(t):return t.GetEffectiveTextShape() if hasattr(t,'GetEffectiveTextShape') else t.GetEffectiveShape()
    bounds=board.GetBoardEdgesBoundingBox();tries=0;accepted=False
    try:
        # Test each source-authored field separately before combining legal
        # seats. A rigid pair template needlessly assumes a common free slot.
        # Prefer horizontal text, then readable vertical, on a finite 0.5 mm
        # grid within the same five-mm owner locality used by the receiver.
        # This bounds pose construction, not an electrical/clearance waiver.
        radius=round(MAX_OWNER_DISTANCE_MM*2)
        offsets=sorted(((x*.5,y*.5) for x in range(-radius,radius+1) for y in range(-radius,radius+1)
            if x*x+y*y<=radius*radius),key=lambda p:(p[0]*p[0]+p[1]*p[1],p[1],p[0]))
        # An exact native-shape bbox can only reject a disjoint pair. This
        # broad phase avoids expensive glyph collisions with every distant
        # board label for every seat; overlapping boxes still use the same
        # native glyph/mask collision and the unchanged clearance.
        peer_shapes=[(shape(p),None) for p in peers]
        peer_shapes=[(s,s.BBox()) for s,_ in peer_shapes]
        mask_shapes=[(p.GetEffectiveShape(copper),gap+max(0,p.GetSolderMaskExpansion(copper))+1000)
            for p in pads]
        mask_shapes=[(s,s.BBox(),c) for s,c in mask_shapes]
        seats=[]
        for text in fields:
            legal=[]
            for angle in (0,90):
                for dx,dy in offsets:
                    tick()
                    tries+=1
                    position=at+pcbnew.VECTOR2I(round(dx*1e6),round(dy*1e6))
                    text.SetPosition(position);text.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
                    native_shape=shape(text)
                    box=native_shape.BBox()
                    if not bounds.Contains(box):continue
                    if any(_native_boxes_near(box,b,gap+1000) and native_shape.Collide(p,gap+1000)
                            for p,b in peer_shapes):continue
                    if any(_native_boxes_near(box,b,clearance) and native_shape.Collide(p,clearance)
                            for p,b,clearance in mask_shapes):continue
                    legal.append((position,angle,native_shape))
            seats.append(legal)
        if len(fields)==1:
            legal=sorted(seats[0],key=lambda q:(q[1],(q[0].x-at.x)**2+(q[0].y-at.y)**2,q[0].x,q[0].y))
            if len(legal)>candidate_rank:
                position,angle,_=legal[candidate_rank];fields[0].SetPosition(position)
                fields[0].SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));accepted=True
                return dict(ok=True,ref=ref,tries=tries,max_owner_distance_mm=MAX_OWNER_DISTANCE_MM,
                    source_strings_fonts_visibility_and_layers_preserved=True,non_silkscreen_fields_unchanged=True,
                    fields=[dict(uuid=force._uid(f),name=f.GetName(),at_nm=list(f.GetPosition()),angle_deg=f.GetTextAngle().AsDegrees()) for f in fields],
                    release_authority=False)
            return dict(ok=False,reason='bounded_native_single_silk_field_layout_refused',tries=tries)
        best=[];diverse={}
        for first in seats[0]:
            tick()
            for second in seats[1]:
                tick()
                # Keep a compact, consistently oriented chart beside its
                # owner. A pair of independently legal but scattered labels
                # is not the preferred result.
                axis='x' if first[1]==0 else 'y'
                alignment=abs(getattr(first[0],axis)-getattr(second[0],axis))
                distance=sum((v[0].x-at.x)**2+(v[0].y-at.y)**2 for v in (first,second))
                score=(first[1]!=second[1],alignment,distance,first[1])
                # Native glyph collision can be costly for long part names.
                # A seat that cannot beat the best legal exact score needs no
                # collision solve. Keep first-on-tie behavior and the same
                # exhaustive finite optimum, without storing all legal pairs.
                feature=(first[1],second[1],
                    (first[0].x+second[0].x>2*at.x),
                    (first[0].y+second[0].y>2*at.y),
                    (second[0].x>first[0].x) if first[1] else (second[0].y>first[0].y))
                if candidate_rank==0 and best and score>=best[0][0]:continue
                if candidate_rank>0 and feature in diverse and score>=diverse[feature][0]:continue
                if first[2].Collide(second[2],gap+1000):continue
                if candidate_rank==0:best=[(score,first,second)]
                else:diverse[feature]=(score,first,second)
        if candidate_rank>0 and diverse:
            pool=sorted(diverse.values(),key=lambda row:row[0]);best=[pool.pop(0)]
            def separation(a,b):
                return sum((a[i][0].x-b[i][0].x)**2+(a[i][0].y-b[i][0].y)**2
                    +4000000000000*(a[i][1]!=b[i][1]) for i in (1,2))
            while pool and len(best)<=candidate_rank:
                chosen=max(range(len(pool)),key=lambda i:min(separation(pool[i],q) for q in best))
                best.append(pool.pop(chosen))
        if len(best)>candidate_rank:
            _,first,second=best[candidate_rank]
            for text,(position,angle,_) in zip(fields,(first,second)):
                text.SetPosition(position);text.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
            accepted=True
            return dict(ok=True,ref=ref,tries=tries,max_owner_distance_mm=MAX_OWNER_DISTANCE_MM,
                source_strings_fonts_visibility_and_layers_preserved=True,
                fields=[dict(uuid=force._uid(f),name=f.GetName(),at_nm=list(f.GetPosition()),angle_deg=f.GetTextAngle().AsDegrees()) for f in fields],
                release_authority=False)
        return dict(ok=False,reason='bounded_native_support_field_layout_refused',tries=tries,
            legal_field_seats={f.GetName():len(rows) for f,rows in zip(fields,seats)})
    except TimeoutError:
        return dict(ok=False,reason='native_owner_field_layout_deadline',tries=tries)
    finally:
        # Preserve the candidate only on a positive advisory result.
        if not accepted:
            for f,(position,angle) in zip(fields,original):
                f.SetPosition(position);f.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
