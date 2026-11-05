"""Bounded joint terminal-reach/orientation proposals, never route authority."""
import itertools
import math

from cec_placement_search_domain import rotate_board_point, rigid_cell_transform
from cec_translation_halfplanes import normalized, contains


# Existing tap-constructor reach, shared with the early placement receiver.
# This is a construction-domain limit, not an electrical or safety rating.
MAX_TAP_DISTANCE_MM = 9.0


def direct_range_evidence(relations, *, max_distance_mm=MAX_TAP_DISTANCE_MM):
    """Measure the actual two named input pads, not the closer shunt terminal.

    Relationships and pin functions come from the existing source/topology
    checker. Unknown-device and filtered relationships retain their separate
    checks; this function does not invent a straight copper bypass through a
    filter or qualify an unknown pinout. It is geometry only, never a route.
    """
    maximum = float(max_distance_mm)
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError('positive finite tap reach required')
    refused, checked, skipped = [], 0, 0
    for relation in relations:
        contract = relation.get('follower_pad_contract') or {}
        if not contract or relation.get('relation_kind') == 'filtered':
            skipped += 1
            continue
        selected = relation.get('selected_pads') or {}
        pairs = relation.get('terminal_correspondences') or []
        if (len(contract) != 2 or selected != contract or len(pairs) != 2
                or {pair['net'] for pair in pairs} != set(contract)):
            raise ValueError('complete actual current-input geometry required')
        for pair in pairs:
            source, target = _point(pair['source']), _point(pair['target'])
            distance = math.dist(source, target)
            checked += 1
            if distance <= maximum + 1e-9:
                continue
            refused.append(dict(net=pair['net'], source_ref=relation['anchor_ref'],
                target_ref=relation['ref'], target_pad=contract[pair['net']],
                source_position_mm=list(source), target_position_mm=list(target),
                current_distance_mm=distance, max_distance_mm=maximum,
                required_closer_mm=distance-maximum,
                reason_kind='current_input_out_of_tap_range'))
    return dict(schema=1, ok=not refused, checked=checked,
                skipped_relations=skipped, max_distance_mm=maximum,
                refused=refused, copper_connectivity_proved=False,
                release_authority=False)


def from_craft_evidence(candidate, evidence, *, immutable=(), policy=None,
                        diagnostics=None, dependency_context=None):
    """Use the existing joint native solver before a full route probe.

    Failed reach is necessary placement evidence, so an expensive route search
    is not needed to generate these repairs. Exact source identity, complete
    owner/bypass transforms, native cavities and normal final receiving remain
    mandatory. No source copper is modified by proposal generation.
    """
    from pathlib import Path
    import pcbnew
    import cec_placement_evidence_identity as identity
    from cec_placement_search_domain import relocation_radius

    policy = policy or {}
    report = dict(schema=1, proposals=0, reason='no_direct_range_refusal',
                  allows_power_replan=False, release_authority=False)
    def finish(moves, reason):
        report.update(reason=reason, proposals=len(moves))
        if diagnostics is not None:
            diagnostics.update(report)
        return moves
    order = evidence.get('critical_terminal_order') or {}
    failures = order.get('range_refusals') or []
    if not failures:
        return finish([], report['reason'])
    binding = ((evidence.get('input_identity') or {}).get('files') or {}).get('board') or {}
    if (evidence.get('input_identity_after') or not binding.get('path')
            or not binding.get('sha256')):
        return finish([], 'missing_or_changed_measured_source_identity')
    path = Path(binding['path'])
    if identity.digest(path) != binding['sha256']:
        return finish([], 'measured_source_bytes_changed')
    groups = {}
    for row in (evidence.get('decoupler') or {}).get('details') or ():
        owner, cap = row.get('owner_ref'), row.get('cap_ref')
        if row.get('status') == 'assigned' and owner and cap:
            groups.setdefault(owner, []).append(cap)
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        return finish([], 'measured_source_unloadable')
    # Preserve a detector's comparator and each owner's assigned bypass, not
    # only the current-input package. The same native relation guard already
    # rejects proposals that split these stations; bring its complete group
    # into the search BEFORE choosing a cavity instead of filtering every
    # otherwise useful primary pose afterwards.
    if dependency_context is None and 'detection_cell' in evidence:
        import cec_placement_dependencies as dependencies
        dependency_context=dependencies.from_board(path,craft=evidence)
    if dependency_context is not None:
        import cec_placement_relation_guard as relations
        if (dependency_context.get('ok') is not True
                or dependency_context.get('board_sha256')!=binding['sha256']
                or not dependency_context.get('relation_guard')
                or not relations.binding_matches(dependency_context['relation_guard'],candidate.P)):
            return finish([], 'unbound_primary_station_dependencies')
        from cec_placement_station_groups import station_groups
        stations=station_groups([dict(physical_refs=group)
            for group in dependency_context.get('groups',())]+[
                dict(physical_refs=[owner,*refs]) for owner,refs in groups.items()])
        for owner in {str(row.get('target_ref') or '') for row in failures}:
            for station in stations:
                if owner in station:
                    groups[owner]=[ref for ref in station if ref!=owner]
        report['complete_station_members']=groups
    moves = from_native_relations(board, candidate, failures,
        order.get('details') or [], groups, immutable=immutable,
        max_translation_mm=relocation_radius(candidate, policy,
                                            'placement_kelvin_range_repair_max_mm'),
        max_per_ref=max(0, int(policy.get('placement_terminal_range_proposals', 8))),
        use_cavities=True, reserved_regions=(evidence.get('power_body_clearance') or {}).get(
            'reserved_regions') or ())
    if dependency_context is not None:
        import cec_placement_dependencies as dependencies
        moves,report['primary_relation_filter']=dependencies.filter_moves(
            dependency_context,candidate.P,moves)
    # An eight-rotation menu for the first owner must not consume the finite
    # trial budget before other failed sensing cells receive one proposal.
    by_owner = {}
    for move in moves:
        by_owner.setdefault(move['ref'], []).append(move)
    moves = [items[index] for index in range(max(map(len, by_owner.values()), default=0))
             for items in by_owner.values() if index < len(items)]
    if identity.digest(path) != binding['sha256']:
        return finish([], 'measured_source_changed_during_proposals')
    report['board_sha256'] = binding['sha256']
    return finish(moves, 'bound_joint_terminal_reach_proposals' if moves
                  else 'no_eligible_joint_terminal_reach_proposal')


def _point(value):
    point=tuple(map(float,value))
    if len(point)!=2 or not all(math.isfinite(v) for v in point):
        raise ValueError('terminal geometry requires finite two-dimensional points')
    return point


def _crosses(a,b,c,d):
    def orient(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    return (((o1 < -1e-9 and o2 > 1e-9) or (o2 < -1e-9 and o1 > 1e-9))
            and ((o3 < -1e-9 and o4 > 1e-9) or (o4 < -1e-9 and o3 > 1e-9)))


def translation_sites(centres, radius, *, halfplanes=()):
    """Finite witnesses inside equal-radius discs in translation space.

    Endpoints, nearest radial projections and circle intersections cover the
    ordinary two-terminal lens without a board-sized raster. This menu is not
    a completeness/no-path claim for topology, copper clearance or placement.
    """
    centres=[_point(p) for p in centres]
    radius=float(radius)
    planes=normalized(halfplanes)
    if not centres or not math.isfinite(radius) or radius<=0:
        raise ValueError('terminal range requires a positive finite radius')
    proposals=[(0.,0.),*centres,
        (sum(p[0] for p in centres)/len(centres),sum(p[1] for p in centres)/len(centres))]
    for x,y in centres:
        norm=math.hypot(x,y)
        if norm>0:proposals.append((x-radius*x/norm,y-radius*y/norm))
    for a,b in itertools.combinations(centres,2):
        dx,dy=b[0]-a[0],b[1]-a[1];distance=math.hypot(dx,dy)
        if distance<=1e-12 or distance>2*radius+1e-9:continue
        height=math.sqrt(max(0.,radius*radius-distance*distance/4))
        mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
        for sign in (-1,1):
            proposals.append((mid[0]-sign*height*dy/distance,
                              mid[1]+sign*height*dx/distance))
    for nx,ny,offset in planes:
        proposals.append((nx*offset,ny*offset))
        for x,y in centres:
            distance=offset-nx*x-ny*y
            if abs(distance)>radius+1e-9:continue
            height=math.sqrt(max(0.,radius*radius-distance*distance))
            for sign in (-1,1):
                proposals.append((x+nx*distance-sign*ny*height,
                                  y+ny*distance+sign*nx*height))
    for (ax,ay,ac),(bx,by,bc) in itertools.combinations(planes,2):
        determinant=ax*by-ay*bx
        if abs(determinant)>1e-12:
            proposals.append(((ac*by-ay*bc)/determinant,
                              (ax*bc-ac*bx)/determinant))
    unique={tuple(round(v,9) for v in p):p for p in proposals
            if contains(p,planes) and all(math.dist(p,c)<=radius+1e-8 for c in centres)}
    return [unique[key] for key in sorted(unique,key=lambda p:(math.hypot(*p),p))]


def joint_cell_proposals(poses, root, correspondences, *, max_distance_mm,
                         max_translation_mm, margin_mm=.3, limit=8,
                         site_provider=None):
    """Rotate a complete cell and jointly close every supplied terminal radius.

    Correspondences contain exact fixed source and current moving pad points.
    No net spelling, device pinout or board identity is inferred here. Pairs of
    direct demand rays must not cross. Complete physical/native routing gates
    still own adoption; ray topology is only a necessary proposal constraint.
    """
    radius=float(max_distance_mm)-float(margin_mm)
    cap=float(max_translation_mm)
    if not math.isfinite(cap) or cap<0 or not math.isfinite(radius) or radius<=0:
        raise ValueError('invalid bounded terminal search domain')
    if not math.isfinite(float(margin_mm)) or float(margin_mm)<0:
        raise ValueError('invalid terminal proposal margin')
    correspondences=list(correspondences)
    pairs=[(_point(row['source']),_point(row['target'])) for row in correspondences]
    approaches=[]
    for index,row in enumerate(correspondences):
        if 'approach' not in row:continue
        approach=row['approach'];start=_point(approach['origin'])
        normal=_point(approach['normal']);minimum=float(approach['min_mm'])
        if not math.isfinite(minimum) or minimum<0:
            raise ValueError('finite nonnegative approach distance required')
        nx,ny,_=normalized([(*normal,0.)])[0]
        approaches.append((index,start,(nx,ny),minimum))
    if len(pairs)<2:return []
    origin=_point(poses[root][:2]);rows=[]
    for angle in (0.,90.,180.,270.):
        rotated=[(source,rotate_board_point(target,origin,angle)) for source,target in pairs]
        centres=[(a[0]-b[0],a[1]-b[1]) for a,b in rotated]
        planes=[(n[0],n[1],minimum-(rotated[index][1][0]-start[0])*n[0]
                    -(rotated[index][1][1]-start[1])*n[1])
                for index,start,n,minimum in approaches]
        kwargs={'translation_halfplanes':planes} if planes else {}
        extra=list(site_provider(angle,centres,radius,**kwargs)) if site_provider else []
        cavity_keys={tuple(round(v,8) for v in _point(p)) for p in extra}
        sites={tuple(round(v,8) for v in _point(p)):_point(p)
               for p in [*extra,*translation_sites(centres,radius,halfplanes=planes)]}
        for key,shift in sites.items():
            displacement=math.hypot(*shift)
            if displacement>cap+1e-9 or (angle==0 and displacement<1e-9):continue
            if not all(math.dist(shift,c)<=radius+1e-8 for c in centres):continue
            if not contains(shift,planes):continue
            rays=[(a,(b[0]+shift[0],b[1]+shift[1])) for a,b in rotated]
            if any(_crosses(a,b,c,d) for (a,b),(c,d) in itertools.combinations(rays,2)):
                continue
            lengths=[math.dist(a,b) for a,b in rays]
            moved=rigid_cell_transform(poses,root,angle,shift)
            rows.append(dict(placements=moved,rotation_deg=angle,
                dx_mm=shift[0],dy_mm=shift[1],terminal_distances_mm=lengths,
                terminal_crossings=0,range_limit_mm=float(max_distance_mm),
                proposal_margin_mm=float(margin_mm),displacement_mm=displacement,
                cavity_witness=key in cavity_keys,
                approach_slacks_mm=[nx*shift[0]+ny*shift[1]-offset
                                    for nx,ny,offset in planes]))
    # Preserve orientation diversity: one candidate per angle before a second
    # translation of that same angle, all under the caller's finite cap.
    by_angle={}
    for row in sorted(rows,key=lambda r:(not r['cavity_witness'],r['displacement_mm'],
            sum(r['terminal_distances_mm']),r['rotation_deg'],r['dx_mm'],r['dy_mm'])):
        by_angle.setdefault(row['rotation_deg'],[]).append(row)
    selected=[]
    while by_angle and len(selected)<max(0,int(limit)):
        heads=sorted((items[0] for items in by_angle.values()),key=lambda r:(
            not r['cavity_witness'],r['displacement_mm'],sum(r['terminal_distances_mm']),r['rotation_deg']))
        for row in heads:
            if len(selected)>=max(0,int(limit)):break
            selected.append(row);items=by_angle[row['rotation_deg']];items.pop(0)
            if not items:del by_angle[row['rotation_deg']]
    return selected


def native_cavity_provider(board, candidate, root, members, *,
                           max_translation_mm, reserved_regions=(), clearance_mm=.1):
    """Conservative native-courtyard free space intersected with reach discs.

    This is a proposal sampler only. Copper reservations are not translated or
    trimmed. Bounding envelopes may refuse valid space; exact downstream gates
    remain authoritative. The loaded board is never modified.
    """
    import pcbnew
    from cec_cell_packing import contact_translation_sites
    footprints={fp.GetReference():fp for fp in board.GetFootprints()}
    faces={ref:bool(fp.IsFlipped()) for ref,fp in footprints.items()}
    member_faces={faces[ref] for ref in members}
    boxes={}
    for ref,fp in footprints.items():
        envelopes=[pad.GetBoundingBox() for pad in fp.Pads() if pad.IsOnCopperLayer()]
        for layer in (pcbnew.F_CrtYd,pcbnew.B_CrtYd):
            courtyard=fp.GetCourtyard(layer)
            if courtyard is not None and not courtyard.IsEmpty():envelopes.append(courtyard.BBox())
        if not envelopes:continue
        boxes[ref]=(min(b.GetLeft() for b in envelopes)/1e6,
                    min(b.GetTop() for b in envelopes)/1e6,
                    max(b.GetRight() for b in envelopes)/1e6,
                    max(b.GetBottom() for b in envelopes)/1e6)
    obstacles=[b for ref,b in boxes.items() if ref not in members and
        (faces[ref] in member_faces or any(p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH
                                         for p in footprints[ref].Pads()))]
    # A reservation's net/face/exempt-ref contract applies to each member,
    # not to the whole macro. The owner can be an intended rail endpoint
    # while its supply bypass is still foreign to that very same rail.
    # Treating every region as a global body obstacle erased legitimate
    # cavities and left only collision-prone analytic fallback proposals.
    member_obstacles=[]
    pad_members=[]
    def rectangle(region,margin):
        value=region.get('box')
        if value is None and all(k in region for k in ('x0','y0','x1','y1')):
            value=[region[k] for k in ('x0','y0','x1','y1')]
        if not isinstance(value,(tuple,list)) or len(value)!=4:
            raise ValueError('complete reservation rectangle required')
        x0,y0,x1,y1=map(float,value)
        margin=float(margin)
        if not all(math.isfinite(v) for v in (x0,y0,x1,y1,margin)) or margin<0:
            raise ValueError('finite reservation geometry required')
        extra=max(0.,margin-float(clearance_mm))
        return (min(x0,x1)-extra,min(y0,y1)-extra,
                max(x0,x1)+extra,max(y0,y1)+extra)
    for ref in members:
        nets={str(p.GetNetname()) for p in footprints[ref].Pads() if p.GetNetname()}
        side='B.Cu' if faces[ref] else 'F.Cu'
        items=[]
        for region in reserved_regions:
            if not region.get('all_layers') and str(region.get('layer') or 'F.Cu')!=side:
                continue
            if ('exempt_refs' in region and ref in region['exempt_refs']
                    or 'exempt_refs' not in region and region.get('net') in nets):
                continue
            items.append(rectangle(region,region.get('clearance_mm',.4)))
        member_obstacles.append(items)
        # A body endpoint exemption is not an exemption for every copper land
        # on that package. A monitor touching both force nets still has GND,
        # supply and data pads which must not consume either rated corridor.
        # Add those actual pad envelopes as virtual moving members; they
        # never become independent placements or authorize modifying a pour.
        for pad in footprints[ref].Pads():
            if not pad.IsOnCopperLayer():continue
            exclusions=[]
            minimum=float(board.GetDesignSettings().m_MinClearance)/1e6
            try:minimum=max(minimum,float(pad.GetNet().GetNetClassSlow().GetClearance())/1e6)
            except (AttributeError,TypeError):pass
            for region in reserved_regions:
                layer=region.get('layer') or 'F.Cu'
                if not region.get('all_layers'):
                    layer_id=board.GetLayerID(str(layer))
                    if layer_id<0:raise ValueError('known reservation copper layer required')
                    if not pad.IsOnLayer(layer_id):continue
                if pad.GetNetname() and region.get('net')==pad.GetNetname():continue
                raw_margin=float(region.get('clearance_mm',minimum))
                if not math.isfinite(raw_margin) or raw_margin<0:
                    raise ValueError('finite reservation geometry required')
                margin=max(minimum,raw_margin)
                exclusions.append(rectangle(region,margin))
            if exclusions:
                bb=pad.GetBoundingBox()
                pad_members.append(((bb.GetLeft()/1e6,bb.GetTop()/1e6,
                                     bb.GetRight()/1e6,bb.GetBottom()/1e6),exclusions))
    member_obstacles.extend(items for _box,items in pad_members)
    origin=candidate.P[root][:2];cap=float(max_translation_mm)

    def sites(angle,centres,radius,*,translation_halfplanes=()):
        parts=[]
        for ref in members:
            if ref not in boxes:return []
            x0,y0,x1,y1=boxes[ref]
            points=[rotate_board_point(p,origin,angle)
                    for p in ((x0,y0),(x0,y1),(x1,y0),(x1,y1))]
            parts.append((min(p[0] for p in points),min(p[1] for p in points),
                          max(p[0] for p in points),max(p[1] for p in points)))
        for (x0,y0,x1,y1),_items in pad_members:
            points=[rotate_board_point(p,origin,angle)
                    for p in ((x0,y0),(x0,y1),(x1,y0),(x1,y1))]
            parts.append((min(p[0] for p in points),min(p[1] for p in points),
                          max(p[0] for p in points),max(p[1] for p in points)))
        bounds=(max(-cap,-min(p[0] for p in parts)),max(-cap,-min(p[1] for p in parts)),
                min(cap,float(candidate.W)-max(p[2] for p in parts)),
                min(cap,float(candidate.H)-max(p[3] for p in parts)))
        if bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:return []
        return contact_translation_sites(parts,bounds=bounds,obstacles=obstacles,
            clearance=clearance_mm,max_sites=64,preferred_origin=(0.,0.),
            reach_discs=[(c,radius) for c in centres],
            translation_halfplanes=translation_halfplanes,
            member_obstacles=member_obstacles)
    return sites


def _bind_approaches(correspondence, pad_pairs, rows, anchor):
    """Bind measured launch deficits and include the other input in the move.

    This restricts this proposal family to forward canonical access. It is NOT
    a global rule that a legal inward-first path cannot later double back.
    The source geometry is shared with construction; independent native route
    and placement gates still decide whether any proposed move is admissible.
    """
    measured=[row for row in rows if 'inward_vector' in row]
    if not measured:return True
    if len(correspondence)!=2 or len(list(anchor.Pads()))!=2:return False
    import cec_fr
    try:
        minima=[float(row['canonical_min_inward_mm']) for row in measured]
        if any(not math.isfinite(v) or v<=0 for v in minima):return False
        contracts={}
        for index,(source,target) in enumerate(pad_pairs):
            other=pad_pairs[1-index][0]
            size=source.GetSize();reach=math.hypot(size.x/1e6,size.y/1e6)/2
            tx,ty,nx,ny=cec_fr._inner_edge_pt(source,other.GetPosition(),
                                            inset_mm=min(.12,reach*.25))
            contracts[source.GetNetname()]=dict(origin=(tx,ty),normal=(nx,ny),
                                                min_mm=max(minima))
        by_net={row['net']:(row,pads) for row,pads in zip(correspondence,pad_pairs)}
        for row in measured:
            pair,(_,target)=by_net[str(row['net'])]
            contract=contracts[row['net']]
            if str(row['target_pad'])!=str(target.GetNumber()):return False
            for key,expected in (('source_position_mm',pair['source']),
                    ('target_position_mm',pair['target']),
                    ('tap_start_position_mm',contract['origin']),
                    ('inward_vector',contract['normal'])):
                if math.dist(_point(row[key]),expected)>3e-6:return False
            actual=sum((pair['target'][axis]-contract['origin'][axis])*
                       contract['normal'][axis] for axis in (0,1))
            stated=float(row['target_inward_mm'])
            if not math.isfinite(stated) or abs(stated-actual)>3e-6:return False
        for pair in correspondence:pair['approach']=contracts[pair['net']]
    except (KeyError,TypeError,ValueError,OverflowError):
        return False
    return True


def from_native_relations(board, candidate, range_rows, terminal_details, groups, *,
                          immutable=(), max_translation_mm, max_per_ref=8,
                          use_cavities=False, reserved_regions=()):
    """Bind the proposal model to native pads and existing electrical contracts."""
    fixed=set(immutable);footprints={}
    for fp in board.GetFootprints():
        if fp.GetReference() in footprints:
            raise ValueError('ambiguous native footprint reference')
        footprints[fp.GetReference()]=fp
    obligations={}
    for row in range_rows:
        try:
            excess=float(row.get('required_closer_mm') or 0)
            inward=float(row.get('target_inward_mm',float('nan')))
            minimum=float(row.get('canonical_min_inward_mm',float('nan')))
            limit=float(row.get('max_distance_mm') or 0)
        except (TypeError,ValueError,OverflowError):continue
        launch_deficit=('inward_vector' in row and math.isfinite(inward)
                        and math.isfinite(minimum) and minimum>0 and inward<minimum)
        if not ((math.isfinite(excess) and excess>0) or launch_deficit):continue
        key=(str(row.get('source_ref') or ''),str(row.get('target_ref') or ''))
        if math.isfinite(limit) and limit>0:obligations.setdefault(key,[]).append(row)
    result=[]
    for relation in terminal_details:
        root=str(relation.get('ref') or '');anchor=str(relation.get('anchor_ref') or '')
        demands=obligations.get((anchor,root))
        if not demands or root not in candidate.P or anchor not in candidate.P:continue
        members=tuple(dict.fromkeys((root,*groups.get(root,()))))
        if anchor in members or any(ref in fixed or ref not in candidate.P for ref in members):continue
        if root not in footprints or anchor not in footprints:continue
        # Only the exact materialized incumbent can supply pad geometry.
        bound=True
        for ref in (root,anchor,*members):
            fp=footprints.get(ref)
            if fp is None:bound=False;break
            pose=candidate.P[ref]
            if (not all(math.isfinite(float(v)) for v in pose)
                    or math.dist(pose[:2],(fp.GetPosition().x/1e6,fp.GetPosition().y/1e6))>2e-6
                    or abs((float(pose[2])-fp.GetOrientationDegrees()+180)%360-180)>1e-6):
                bound=False;break
            if hasattr(candidate,'back_refs') and bool(fp.IsFlipped())!=(ref in candidate.back_refs):
                bound=False;break
        if not bound:continue
        correspondence=[];pad_pairs=[]
        for net,pin in (relation.get('selected_pads') or {}).items():
            sources=[p for p in footprints[anchor].Pads() if p.GetNetname()==net and p.IsOnCopperLayer()]
            targets=[p for p in footprints[root].Pads() if p.GetNetname()==net
                     and str(p.GetNumber())==str(pin) and p.IsOnCopperLayer()]
            if len(sources)!=1 or len(targets)!=1:correspondence=[];break
            pad_pairs.append((sources[0],targets[0]))
            correspondence.append(dict(net=net,source=(sources[0].GetPosition().x/1e6,sources[0].GetPosition().y/1e6),
                target=(targets[0].GetPosition().x/1e6,targets[0].GetPosition().y/1e6)))
        if len(correspondence)<2:continue
        if not _bind_approaches(correspondence,pad_pairs,demands,footprints[anchor]):continue
        sites=(native_cavity_provider(board,candidate,root,members,
                max_translation_mm=max_translation_mm,reserved_regions=reserved_regions)
               if use_cavities else None)
        for index,proposal in enumerate(joint_cell_proposals(
                {ref:candidate.P[ref] for ref in members},root,correspondence,
                max_distance_mm=min(float(row['max_distance_mm']) for row in demands),
                max_translation_mm=max_translation_mm,
                limit=max_per_ref,site_provider=sites)):
            result.append(dict(proposal,ref=root,refs=list(members),
                position=proposal['placements'][root],kind='terminal_range_order_closure',
                blockage_witness=True,budget_group='terminal-range:%s:%s:%s'%(anchor,root,index),
                anchor_ref=anchor,terminal_correspondences=correspondence,
                approach_proposal_only=any('approach' in pair for pair in correspondence)))
    return result
