"""Board-independent opposing-face envelope checks and CAD interchange.

Native contours/poses are authority. Heights must be explicitly selected by
footprint, with provenance; unknown parts are errors, never invisible solids.
Design allocations permit placement studies, not manufacturing qualification.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path


def polygon_from_native(poly):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    parts=[]
    for n in range(poly.OutlineCount()):
        ch=poly.Outline(n)
        outer=[(ch.CPoint(i).x/1e6,ch.CPoint(i).y/1e6) for i in range(ch.PointCount())]
        holes=[]
        for h in range(poly.HoleCount(n)):
            ch=poly.Hole(n,h)
            holes.append([(ch.CPoint(i).x/1e6,ch.CPoint(i).y/1e6) for i in range(ch.PointCount())])
        parts.append(Polygon(outer,holes))
    return unary_union(parts)


def footprint_planar_envelope(fp, *, fallback_include_lands=False):
    """Read a native courtyard or conservative fabrication-graphic envelope.

    A missing courtyard must not erase the component from a packing model.
    The fallback is explicitly identified and is not a qualified replacement
    courtyard. Callers may include actual facing copper lands for reservation;
    neither a body dimension nor an assembly clearance is inferred from pads.
    """
    import pcbnew
    from shapely.geometry import box
    from shapely.ops import unary_union
    if type(fallback_include_lands) is not bool:
        raise ValueError('explicit_native_planar_envelope_policy_required')
    face=fp.GetLayer()
    if face not in (pcbnew.F_Cu,pcbnew.B_Cu):
        raise ValueError('native_surface_footprint_face_required')
    native=fp.GetCourtyard(face)
    if native.OutlineCount():
        shape=polygon_from_native(native)
        basis='native_courtyard'
    else:
        layer=pcbnew.F_Fab if face==pcbnew.F_Cu else pcbnew.B_Fab
        graphics=[g for g in fp.GraphicalItems()
                  if g.GetLayer()==layer and isinstance(g,pcbnew.PCB_SHAPE)]
        if not graphics or len(graphics)>256:
            raise ValueError('native courtyard AND bounded fabrication outline required: '+fp.GetReference())
        boxes=[g.GetBoundingBox() for g in graphics]
        shape=box(min(b.GetLeft() for b in boxes)/1e6,min(b.GetTop() for b in boxes)/1e6,
                  max(b.GetRight() for b in boxes)/1e6,max(b.GetBottom() for b in boxes)/1e6)
        basis='native_fabrication_graphic_bbox'
        if fallback_include_lands:
            pads=list(fp.Pads())
            if len(pads)>4096:raise ValueError('native_planar_land_inventory_bound')
            lands=[polygon_from_native(p.GetEffectivePolygon(face)) for p in pads
                   if p.IsOnLayer(face) and p.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH]
            shape=unary_union([shape,*lands])
            basis+='_with_actual_lands'
    if shape.is_empty or not shape.is_valid or shape.area<=0:
        raise ValueError('valid_native_planar_footprint_envelope_required')
    return shape,basis


def same_net_terminal_gap_mm(leaf, owners, *, layer_id):
    """Actual edge distance to explicitly bound same-net native owner pads.

    This measures geometry only. It does not infer a bypass assignment, a
    maximum acceptable inductance, a current allocation or routing permission.
    """
    import pcbnew
    if (type(layer_id) is not int or layer_id not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or not isinstance(owners,(tuple,list)) or not 1<=len(owners)<=32
            or not isinstance(leaf,pcbnew.PAD)
            or any(not isinstance(p,pcbnew.PAD) for p in owners)):
        raise ValueError('bounded_explicit_native_terminal_owner_bank_required')
    ids=[str(p.m_Uuid.AsString()) for p in owners]
    if (len(set(ids))!=len(ids) or str(leaf.m_Uuid.AsString()) in ids
            or leaf.GetNetCode()<=0 or not leaf.GetNetname()
            or any(p.GetNetname()!=leaf.GetNetname() for p in owners)
            or any(not p.IsOnLayer(layer_id) for p in (leaf,*owners))):
        raise ValueError('distinct_same_actual_net_and_face_terminal_bank_required')
    shapes=[polygon_from_native(p.GetEffectivePolygon(layer_id)) for p in (leaf,*owners)]
    if any(s.is_empty or not s.is_valid or s.area<=0 for s in shapes):
        raise ValueError('valid_native_terminal_edge_geometry_required')
    return min(shapes[0].distance(s) for s in shapes[1:])


def extract(board, specification):
    """Complete native population; conservative courtyard prisms by default."""
    import pcbnew
    from shapely.geometry import Point, box, mapping
    from shapely import affinity
    outline=pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline,False):
        raise ValueError('native closed outline required')
    contour=polygon_from_native(outline)
    if contour.geom_type!='Polygon' or not contour.is_valid:
        raise ValueError('one valid laminate polygon required')
    bodies=[];missing=[];holes=[]
    for fp in board.GetFootprints():
        ref=fp.GetReference(); key=str(fp.GetFPID().GetLibItemName())
        row=specification.get(key)
        if row is None:
            missing.append(dict(ref=ref,footprint=key));continue
        height=float(row['height_max_mm'])
        if not math.isfinite(height) or height<0 or not row.get('evidence'):
            raise ValueError('nonnegative sourced height required: '+key)
        for pad in fp.Pads():
            d=pad.GetDrillSize()
            if d.x>0 and d.y>0:
                p=pad.GetPosition()
                holes.append(dict(xy=[p.x/1e6,p.y/1e6],diameter_mm=min(d.x,d.y)/1e6))
                holes[-1].update(size_mm=[d.x/1e6,d.y/1e6],
                                 angle_degrees=float(pad.GetOrientationDegrees()))
        if height==0:
            p=fp.GetPosition()
            bodies.append(dict(ref=ref,footprint=key,height_max_mm=0,
                kind='planar',evidence=row['evidence'],basis=row['basis'],
                pose_mm=[p.x/1e6,p.y/1e6,float(fp.GetOrientationDegrees())]))
            continue
        # Physical lead/drill origin remains KiCad's, including odd rotations.
        p=fp.GetPosition();x,y=p.x/1e6,p.y/1e6
        geometry_source='native_courtyard'
        if 'diameter_max_mm' in row:
            geometry_source='declared_maximum_diameter'
            shape=Point(x,y).buffer(float(row['diameter_max_mm'])/2,quad_segs=48)
        elif 'local_box_mm' in row:
            geometry_source='declared_local_envelope'
            shape=box(*row['local_box_mm'])
            shape=affinity.rotate(shape,-fp.GetOrientationDegrees(),origin=(0,0))
            shape=affinity.translate(shape,x,y)
        else:
            shape,geometry_source=footprint_planar_envelope(fp)
            extra=float(row.get('courtyard_expansion_mm',0))
            if extra<0:raise ValueError('envelopes cannot shrink native courtyards')
            shape=shape.buffer(extra,join_style='mitre')
        if row.get('kind')=='mating_header':
            from shapely.ops import unary_union
            bodies.append(dict(ref=ref+'/housing',footprint=key,xy=mapping(shape),
                height_max_mm=float(row['housing_max_mm']),inward=fp.GetLayer()==pcbnew.F_Cu,
                kind='header_housing',basis=row['basis'],evidence=row['evidence']))
            half=float(row['post_width_max_mm'])/2
            pins=[]
            for pad in fp.Pads():
                p=pad.GetPosition();cx,cy=p.x/1e6,p.y/1e6
                pin=box(cx-half,cy-half,cx+half,cy+half)
                pins.append(affinity.rotate(pin,-fp.GetOrientationDegrees(),origin=(cx,cy)))
            shape=unary_union(pins)
            geometry_source='declared_post_width_at_native_pad_centres'
        bodies.append(dict(ref=ref,footprint=key,xy=mapping(shape),height_max_mm=height,
            inward=fp.GetLayer()==pcbnew.F_Cu,kind=row.get('kind','component'),
            vent_min_mm=row.get('vent_min_mm'),basis=row['basis'],evidence=row['evidence'],geometry_source=geometry_source,
            pose_mm=[x,y,float(fp.GetOrientationDegrees())],
            drill_centres_mm=[[p.GetPosition().x/1e6,p.GetPosition().y/1e6] for p in fp.Pads() if p.GetDrillSize().x>0]))
    return dict(outline=mapping(contour),thickness_mm=board.GetDesignSettings().GetBoardThickness()/1e6,
                bodies=bodies,holes=holes,missing=missing)


def screen(carrier, cover, *, transform, gap, xy_allowance_mm, clearance_mm,
           mating_pairs=(), contacts_verified=False):
    """Conservative interval test, including opposing laminate and vent zones."""
    from shapely.geometry import shape, mapping
    from shapely import affinity
    from cec_stack_fit_screen import interval,contact_registration
    gap=interval(gap)
    if gap is None or gap[0]<=0:raise ValueError('positive local gap bounds required')
    # Reuse the rigid-transform validator without a special coordinate case.
    contact_registration([dict(id='a',xy=[0,0],role='datum')],
                         [dict(id='a',xy=[0,0],role='datum')],transform)
    if any(not math.isfinite(v) or v<0 for v in (xy_allowance_mm,clearance_mm)):
        raise ValueError('finite nonnegative placement allowances required')
    mating={tuple(p) for p in mating_pairs}
    if mating and not contacts_verified:raise ValueError('mating exemption requires contact evidence')
    a={b['ref']:b for b in carrier['bodies']};b={r['ref']:r for r in cover['bodies']}
    if any(x not in a or y not in b for x,y in mating):raise ValueError('missing mating member')
    transformed=[]
    for row in b.values():
        if row['height_max_mm']:
            transformed.append(dict(row,xy=mapping(affinity.affine_transform(shape(row['xy']),transform))))
    rows=[];vents=[];violations=[]
    ca=shape(carrier['outline']);cb=affinity.affine_transform(shape(cover['outline']),transform)
    missing=[dict(side=s,**m) for s,q in [('carrier',carrier),('cover',cover)] for m in q['missing']]
    def record(kind,refs,margin,**extra):
        row=dict(kind=kind,refs=refs,margin_mm=margin,ok=margin>=-1e-8,**extra)
        rows.append(row)
        if not row['ok']:violations.append(row)
    for side,components,opposing in [('carrier',a.values(),cb),('cover',transformed,ca)]:
        for r in components:
            if not r['height_max_mm'] or not r['inward']:continue
            actual=shape(r['xy']);geom=actual.buffer(xy_allowance_mm)
            lateral=max(0.,actual.distance(opposing)-xy_allowance_mm)
            if lateral<=1e-8:
                record('body_to_laminate',[side,r['ref']],gap[0]-r['height_max_mm']-clearance_mm)
            else:
                free=gap[0]-r['height_max_mm']
                distance=math.hypot(lateral,max(0.,free))
                if distance<=clearance_mm+1e-8:
                    record('body_to_laminate_edge_clearance',[side,r['ref']],distance-clearance_mm,
                        lateral_free_mm=lateral,vertical_free_mm=free,spatial_clearance_mm=distance)
            if r.get('vent_min_mm') is not None:
                free=gap[0]-r['height_max_mm']
                record('vent_to_laminate',[side,r['ref']],free-r['vent_min_mm'],free_mm=free)
                vents.append(dict(side=side,ref=r['ref'],xy=mapping(geom),free_mm=free))
    for r in a.values():
        if not r['height_max_mm'] or not r['inward']:continue
        geom=shape(r['xy'])
        for s in transformed:
            if not s['inward'] or (r['ref'],s['ref']) in mating:continue
            free=gap[0]-r['height_max_mm']-s['height_max_mm']
            # Non-overlap in XY does NOT prove three-dimensional clearance:
            # two tall opposing packages can overlap in Z and miss laterally
            # by less than the required body gap. Use the distance between
            # their extruded tolerance envelopes, without an inscribed
            # circular-buffer approximation to the two XY allowances.
            lateral=max(0.,geom.distance(shape(s['xy']))-2*xy_allowance_mm)
            if lateral<=1e-8:
                # Vent space remains a directional vertical requirement,
                # not a Euclidean shortcut around the vent keepout.
                guard=max(clearance_mm,r.get('vent_min_mm') or 0,s.get('vent_min_mm') or 0)
                record('opposing_bodies',[r['ref'],s['ref']],free-guard,free_mm=free)
            else:
                distance=math.hypot(lateral,max(0.,free))
                if distance<=clearance_mm+1e-8:
                    record('opposing_body_edge_clearance',[r['ref'],s['ref']],distance-clearance_mm,
                        lateral_free_mm=lateral,vertical_free_mm=free,spatial_clearance_mm=distance)
    return dict(schema=1,ok=not missing and not violations,missing=missing,checks=rows,
        violations=violations,vents=vents,cover_in_carrier=transformed,
        scope='placement under declared envelopes; not physical release',release_accepted=False,
        conditional_allocations=sorted({r['footprint'] for r in [*a.values(),*b.values()]
            if r['basis']=='design_allocation'}))


def evaluate(carrier_path,cover_path,contract):
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    paths=[Path(p).resolve() for p in (carrier_path,cover_path)]
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    boards=[pcbnew.LoadBoard(str(p)) for p in paths]
    result,data=evaluate_boards(*boards,contract)
    result['sources']=[dict(path=str(p),sha256=h) for p,h in zip(paths,before)]
    result['source_unchanged']=before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    result['ok'] &= result['source_unchanged']
    return result,data


def evaluate_boards(carrier,cover,contract):
    boards=[carrier,cover]
    specification=dict(contract.get('envelopes',{}))
    for group in contract.get('envelope_groups',[]):
        for key in group['footprints']:
            if key in specification:raise ValueError('duplicate envelope: '+key)
            specification[key]={k:v for k,v in group.items() if k!='footprints'}
    data=[extract(b,specification) for b in boards]
    from cec_stack_fit_screen import contact_registration
    contacts=[]
    indexes=[{f.GetReference():f for f in b.GetFootprints()} for b in boards]
    for pair in contract['mating_pairs']:
        fields=[]
        for idx,ref in zip(indexes,pair):
            fields.append([dict(id=p.GetNumber(),xy=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],
                                role=p.GetNumber()) for p in idx[ref].Pads()])
        contacts.append(contact_registration(*fields,contract['transform']))
    verified=all(c['ok'] for c in contacts)
    result=screen(*data,transform=contract['transform'],gap=contract['gap_mm'],
        xy_allowance_mm=contract['xy_allowance_each_mm'],clearance_mm=contract['body_clearance_mm'],
        mating_pairs=contract['mating_pairs'] if verified else (),contacts_verified=verified)
    result['contacts']=contacts
    result['ok'] &= verified
    from shapely.geometry import Point,shape
    from shapely import affinity
    hardware=[]
    for row in contract.get('hardware',[]):
        anchors=[]
        for i,ref in enumerate(row['anchor_pair']):
            fp=indexes[i][ref];p=fp.GetPosition();point=Point(p.x/1e6,p.y/1e6)
            if i:point=affinity.affine_transform(point,contract['transform'])
            anchors.append(point)
        if anchors[0].distance(anchors[1])>.05:raise ValueError('hardware anchors do not coincide')
        keep=anchors[0].buffer(row['diameter_max_mm']/2+contract['xy_allowance_each_mm'])
        conflicts=[]
        for side,bodies in [('carrier',data[0]['bodies']),('cover',result['cover_in_carrier'])]:
            for b in bodies:
                if b.get('inward') and b['height_max_mm'] and keep.intersects(shape(b['xy'])):
                    conflicts.append([side,b['ref']])
        hardware.append(dict(**row,xy=[anchors[0].x,anchors[0].y],conflicts=conflicts,ok=not conflicts))
    result['hardware']=hardware
    result['ok'] &= all(r['ok'] for r in hardware)
    return result,data


def native_translation_check(board, peer, contract, translations, *,
                             receiver='carrier', peer_translations=None, timeout_s=2.):
    """Probe explicit native poses with the SAME paired-board envelope gate.

    Restore all temporary footprint moves, even after refusal or exception.
    This is a read-only feasibility adapter for a bounded placement search,
    not an electrical, same-face clearance, routing or release certificate.
    It retains both boards' actual bodies, both XY allowances, vent margins,
    hardware and numbered mating checks instead of duplicating a simplified
    proposal-only model. Optional explicit peer translations let a matched
    interface move as one transaction, in each board's own native frame.
    Both scopes are validated before either board moves; neither an unmatched
    intermediate pose nor a partially restored transaction is admissible.
    Unknown identities and deadline expiry fail closed.
    """
    import time
    import pcbnew
    from cec_field_coupling import _field_snapshot_inventory
    peer_translations={} if peer_translations is None else peer_translations
    def bounded_scope(scope,minimum):
        return (isinstance(scope,dict) and minimum<=len(scope)<=64
            and all(type(ref) is str and ref and isinstance(delta,(list,tuple))
                and len(delta)==2 and all(type(v) in (int,float)
                    and math.isfinite(v) and abs(v)<=2000 for v in delta)
                for ref,delta in scope.items()))
    if (not isinstance(board,pcbnew.BOARD) or not isinstance(peer,pcbnew.BOARD)
            or board is peer or receiver not in ('carrier','cover')
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or not bounded_scope(translations,1)
            or not bounded_scope(peer_translations,0)):
        raise ValueError('bounded_explicit_native_assembly_translations_required')
    deadline=time.monotonic()+timeout_s
    indexed=[]
    for current,scope in ((board,translations),(peer,peer_translations)):
        fps=list(current.GetFootprints());index={fp.GetReference():fp for fp in fps}
        if len(index)!=len(fps) or not scope.keys()<=index.keys():
            raise ValueError('unique_actual_native_assembly_translation_identity_required')
        indexed.append(index)
    def inventory(current):
        return (_field_snapshot_inventory(current),tuple(sorted(
            (str(fp.m_Uuid.AsString()),str(fp.GetReference()),tuple(fp.GetPosition()),
             float(fp.GetOrientationDegrees()),int(fp.GetLayer()),bool(fp.IsLocked()))
            for fp in current.GetFootprints())))
    before=inventory(board);peer_before=inventory(peer)
    origins=[{ref:tuple(index[ref].GetPosition()) for ref in scope}
        for index,scope in zip(indexed,(translations,peer_translations))]
    moved=[]
    try:
        for context,scope in enumerate((translations,peer_translations)):
            for ref,delta in scope.items():
                if time.monotonic()>=deadline:
                    return dict(ok=False,timed_out=True,source_and_peer_unchanged=True,
                        reason='native_assembly_translation_deadline',release_authority=False)
                moved.append((context,ref))
                indexed[context][ref].Move(pcbnew.VECTOR2I(*(round(v*1e6) for v in delta)))
        carrier,cover=(board,peer) if receiver=='carrier' else (peer,board)
        result,_=evaluate_boards(carrier,cover,contract)
        expired=time.monotonic()>=deadline
    finally:
        for context,ref in reversed(moved):
            indexed[context][ref].SetPosition(pcbnew.VECTOR2I(*origins[context][ref]))
        if inventory(board)!=before or inventory(peer)!=peer_before:
            raise ValueError('native_assembly_translation_changed_source_or_peer')
    return dict(ok=result['ok'] is True and not expired,timed_out=expired,
        reason='native_assembly_translation_deadline' if expired else
               None if result['ok'] is True else 'native_paired_assembly_refused',
        violations=result['violations'],missing=result['missing'],
        source_and_peer_unchanged=True,scope='paired-native-translation-feasibility',
        routing_admitted=False,release_authority=False)


def dependencies(policy,root):
    """Source identity includes the chosen peer, not an unbound latest-file lookup."""
    if policy.get('role') not in ('carrier','cover'):
        raise ValueError('invalid assembly role')
    root=Path(root)
    paths=[root/policy[k] for k in ('contract','pair')]
    pair=json.loads(paths[1].read_text())
    peer=pair['cover' if policy['role']=='carrier' else 'carrier']
    paths.append(root/peer['path'])
    for p in paths:
        if not p.is_file():raise ValueError('assembly dependency missing: '+str(p))
    return paths


def declared_policy(board_path,params=None):
    """Resolve explicit configuration or the policy carried by a native seed."""
    policy=(params or {}).get('assembly_envelope')
    if policy:return policy
    path=Path(board_path)
    if not path.is_file() or b'"CEC_ASSEMBLY_POLICY"' not in path.read_bytes():
        return None
    import pcbnew
    board=pcbnew.LoadBoard(str(path))
    props={str(k):str(v) for k,v in board.GetProperties().asdict().items()}
    raw=props.get('CEC_ASSEMBLY_POLICY')
    if not raw:raise ValueError('native assembly declaration cannot be decoded')
    return json.loads(raw)


def candidate_check(board_path,params=None):
    """Placement/search adapter; no configuration means no paired assembly."""
    policy=declared_policy(board_path,params)
    if not policy:return dict(ok=True,applicable=False,violations=[])
    import pcbnew
    result=policy_check(pcbnew.LoadBoard(str(board_path)),policy,Path(__file__).resolve().parents[1])
    result.pop('cover_in_carrier',None)
    result['check_count']=len(result.pop('checks',[]))
    result['applicable']=True
    return result


def facing_vents(result, contract, receiver):
    """Put the opposing vents into the selected receiving board's frame."""
    from shapely import affinity
    from shapely.geometry import shape,mapping
    if receiver not in ('carrier','cover'):
        raise ValueError('explicit assembly receiver required')
    a,b,d,e,tx,ty=contract['transform'];det=a*e-b*d
    if not math.isfinite(det) or abs(det)<1e-12:
        raise ValueError('invertible assembly transform required')
    inverse=[e/det,-b/det,-d/det,a/det,(b*ty-e*tx)/det,(d*tx-a*ty)/det]
    return [v if receiver=='carrier' else dict(v,xy=mapping(
        affinity.affine_transform(shape(v['xy']),inverse)))
        for v in result['vents'] if v['side']!=receiver]


def reconcile_placement_reservations(board, *, source_path, updates, root):
    """Replace explicitly superseded FP-only guards with current vent guards.

    This is an opt-in private placement transition, NOT name-based keepout
    deletion. Each old UUID must contain exactly one current projected vent;
    its nominated replacement is an existing all-four-exclusions native rule
    on the same face, covering that whole vent. The hash-pinned current source
    assembly must already pass. No copper rule, peer, envelope, tolerance or
    release receipt may be changed by this operation.
    """
    import pcbnew
    from shapely.geometry import shape
    import cec_field_coupling as field
    if not isinstance(updates,list) or not 1<=len(updates)<=4:
        raise ValueError('bounded explicit superseded reservation pairs required')
    source_path=Path(source_path).resolve()
    source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
    policy=declared_policy(source_path)
    if not policy:raise ValueError('current paired assembly declaration required')
    props={str(k):str(v) for k,v in board.GetProperties().asdict().items()}
    if json.loads(props.get('CEC_ASSEMBLY_POLICY','null'))!=policy:
        raise ValueError('live candidate assembly declaration changed')
    authority=dependencies(policy,root)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in authority]
    source=pcbnew.LoadBoard(str(source_path))
    baseline=policy_check(source,policy,root)
    if not baseline.get('ok') or not baseline.get('authority_unchanged'):
        raise ValueError('source current assembly is not admitted')
    vents=facing_vents(baseline,json.loads(authority[0].read_text()),policy['role'])
    zones={z.m_Uuid.AsString():z for z in board.Zones()}
    selected=set();replacements=set();vent_refs=set();prepared=[]
    before=field._field_snapshot_inventory(board)
    for request in updates:
        if (not isinstance(request,dict)
                or set(request)!=set(('reservation_uuid','replacement_guard_uuid'))):
            raise ValueError('exact explicit reservation transition required')
        uid,guard_uid=request['reservation_uuid'],request['replacement_guard_uuid']
        if (uid in selected or guard_uid in replacements or uid==guard_uid
                or uid not in zones or guard_uid not in zones):
            raise ValueError('unique live reservation and replacement required')
        old,guard=zones[uid],zones[guard_uid]
        if (old.IsLocked() or not old.GetIsRuleArea()
                or tuple(old.GetLayerSet().Seq())!=(pcbnew.F_Cu,)
                or not old.GetDoNotAllowFootprints() or old.GetDoNotAllowTracks()
                or old.GetDoNotAllowVias() or old.GetDoNotAllowZoneFills()):
            raise ValueError('only an unlocked facing FP-only provisional guard may be superseded')
        if (not guard.GetIsRuleArea() or tuple(old.GetLayerSet().Seq())!=tuple(guard.GetLayerSet().Seq())
                or not all((guard.GetDoNotAllowFootprints(),guard.GetDoNotAllowTracks(),
                            guard.GetDoNotAllowVias(),guard.GetDoNotAllowZoneFills()))):
            raise ValueError('existing full native vent protection required')
        old_shape=polygon_from_native(old.Outline())
        guard_shape=polygon_from_native(guard.Outline())
        if (old_shape.is_empty or not old_shape.is_valid or guard_shape.is_empty
                or not guard_shape.is_valid or not old_shape.buffer(.000002).covers(guard_shape)):
            raise ValueError('replacement must lie wholly inside superseded guard')
        matching=[v for v in vents if guard_shape.buffer(.000002).covers(shape(v['xy']))]
        if len(matching)!=1 or matching[0]['ref'] in vent_refs:
            raise ValueError('unique current projected vent required')
        selected.add(uid);replacements.add(guard_uid);vent_refs.add(matching[0]['ref'])
        prepared.append((old,pcbnew.SHAPE_POLY_SET(old.Outline()),
            pcbnew.SHAPE_POLY_SET(guard.Outline()),dict(reservation_uuid=uid,
                replacement_guard_uuid=guard_uid,opposing_vent_ref=matching[0]['ref'],
                before_bounds_mm=list(old_shape.bounds),after_bounds_mm=list(guard_shape.bounds))))
    if selected&replacements:raise ValueError('reservation updates cannot replace one another')
    def copy_contours(zone,poly):
        # SetOutline takes a native pointer without transferring SWIG
        # ownership. A temporary owned clone would later free the live zone
        # outline. Copy into its existing owned polygon instead.
        live=zone.Outline();live.RemoveAllContours();live.Append(poly)
    try:
        for old,_,replacement,_ in prepared:copy_contours(old,replacement)
        after=field._field_snapshot_inventory(board)
        allowed={('zone',uid) for uid in selected}
        if (before.keys()!=after.keys()
                or any(before[k]!=after[k] for k in before if k not in allowed)
                or source_hash!=hashlib.sha256(source_path.read_bytes()).hexdigest()
                or hashes!=[hashlib.sha256(p.read_bytes()).hexdigest() for p in authority]):
            raise ValueError('reservation reconciliation changed unrelated material or authority')
    except Exception:
        for old,original,_,_ in prepared:copy_contours(old,original)
        raise
    return dict(ok=True,scope='explicit-current-assembly-placement-reservation-transition',
        source_sha256=source_hash,updates=[r for _,_,_,r in prepared],
        authority=[dict(path=str(p),sha256=h) for p,h in zip(authority,hashes)],
        all_current_vent_guards_unchanged=True,all_unrelated_material_exact=True,
        routing_admitted=False,release_authority=False)


def footprint_reservation_check(board):
    """Conservative actual courtyard/land check of native no-footprint rules."""
    import pcbnew
    import cec_synth_pipeline as synth
    from shapely.geometry import box
    findings=[]
    guards=[z for z in board.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowFootprints()]
    for fp in board.GetFootprints():
        native=fp.GetCourtyard(fp.GetLayer())
        if native.OutlineCount():body=polygon_from_native(native)
        else:
            x0,x1,y0,y1=synth._footprint_courtyard_box(fp);body=box(x0,y0,x1,y1)
        if body.is_empty or not body.is_valid:
            raise ValueError('native footprint reservation geometry unavailable')
        for z in guards:
            # Other-side SMT bodies do not occupy this face; plated lands do.
            same_face=z.IsOnLayer(fp.GetLayer())
            intersects=(same_face and body.intersects(polygon_from_native(z.Outline())))
            if not intersects:
                intersects=any(z.IsOnLayer(layer) and pad.IsOnLayer(layer)
                    and z.Outline().Collide(pad.GetEffectiveShape(layer),0)
                    for pad in fp.Pads() if pad.HasHole()
                    for layer in (pcbnew.F_Cu,pcbnew.B_Cu))
            if intersects:findings.append(dict(ref=fp.GetReference(),
                footprint_uuid=fp.m_Uuid.AsString(),reservation_uuid=z.m_Uuid.AsString()))
    return dict(ok=not findings,findings=findings,rule_count=len(guards),
        scope='native-footprint-reservations-only-not-route-or-release')


def vent_reservations(board, vents, *, install=False):
    """Project capacitor vents into native front-face rules and check copper.

    Input polygons are already in this receiving board's coordinate frame.
    The caller must rerun this when either board or its pose changes.
    """
    import pcbnew
    from shapely.geometry import shape
    from shapely.ops import unary_union
    results=[]
    for row in vents:
        geom=shape(row['xy']);poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in list(geom.exterior.coords)[:-1]:poly.Append(round(x*1e6),round(y*1e6))
        hits=[]
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.IsOnLayer(pcbnew.F_Cu) and poly.Collide(pad.GetEffectiveShape(pcbnew.F_Cu),0):
                    hits.append('pad:'+fp.GetReference()+'.'+pad.GetNumber())
        for item in board.GetTracks():
            if item.IsOnLayer(pcbnew.F_Cu) and poly.Collide(item.GetEffectiveShape(pcbnew.F_Cu),0):
                hits.append('track_or_via:'+item.m_Uuid.AsString())
        for z in board.Zones():
            if not z.GetIsRuleArea() and z.GetLayerSet().Contains(pcbnew.F_Cu):
                if z.IsFilled() and z.GetFilledPolysList(pcbnew.F_Cu).Collide(poly,0):
                    hits.append('filled_zone:'+z.m_Uuid.AsString())
        if install:
            if hits:raise ValueError('vent reservation would cover native copper: '+str(hits))
            z=pcbnew.ZONE(board);z.SetIsRuleArea(True);z.SetLayer(pcbnew.F_Cu)
            z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True)
            z.SetDoNotAllowZoneFills(True);z.SetDoNotAllowFootprints(True)
            z.SetZoneName('ASSEMBLY VENT '+row['ref']+' - keep facing surface clear')
            out=z.Outline();out.NewOutline()
            for x,y in list(geom.exterior.coords)[:-1]:out.Append(round(x*1e6),round(y*1e6))
            board.Add(z)
        guards=[polygon_from_native(z.Outline()) for z in board.Zones() if z.GetIsRuleArea()
                and z.GetLayerSet().Contains(pcbnew.F_Cu) and z.GetDoNotAllowTracks()
                and z.GetDoNotAllowVias() and z.GetDoNotAllowZoneFills() and z.GetDoNotAllowFootprints()]
        covered=bool(guards) and unary_union(guards).buffer(.000002).covers(geom)
        results.append(dict(ref=row['ref'],copper_hits=hits,native_rule_covers=covered,ok=not hits and covered))
    return results


def policy_check(board,policy,root):
    """Reusable live-candidate vs hash-pinned peer check, independent of filename."""
    import pcbnew
    from cec_stack_fit_screen import vertical_screen
    paths=dependencies(policy,root)
    snapshots=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    contract=json.loads(paths[0].read_text());pair=json.loads(paths[1].read_text())
    if policy['role'] not in ('carrier','cover'):raise ValueError('invalid assembly role')
    peer_key='cover' if policy['role']=='carrier' else 'carrier'
    if snapshots[2]!=pair[peer_key]['sha256']:raise ValueError('assembly peer hash mismatch')
    peer=pcbnew.LoadBoard(str(paths[2]))
    result,data=evaluate_boards(*([board,peer] if policy['role']=='carrier' else [peer,board]),contract)
    result['vertical']=vertical_screen(**contract['vertical'])
    result['ok'] &= result['vertical']['ok']
    # Vents returned in carrier coordinates. Reverse transform for a carrier
    # capacitor facing the cover; never confuse a face flip with 180deg XY.
    receivers={'carrier':board if policy['role']=='carrier' else peer,
               'cover':board if policy['role']=='cover' else peer}
    result['vent_reservations']=[]
    for receiver,target in receivers.items():
        facing=facing_vents(result,contract,receiver)
        # Check both receiving faces: a moving capacitor on this candidate
        # must still fit the reservation on its pinned peer, and vice versa.
        result['vent_reservations'].extend(dict(row,receiver=receiver)
            for row in vent_reservations(target,facing))
    result['ok'] &= all(v['ok'] for v in result['vent_reservations'])
    result['authority_unchanged']=snapshots==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    result['ok'] &= result['authority_unchanged']
    return result


def failure_reasons(result):
    """Keep every failed assembly subgate visible, not just body collisions."""
    reasons={key:result[key] for key in ('violations','missing') if result.get(key)}
    for key in ('contacts','hardware','vent_reservations'):
        rows=[r for r in result.get(key,[]) if not r.get('ok')]
        if rows:reasons[key]=rows
    if result.get('vertical') and not result['vertical'].get('ok'):
        reasons['vertical']=result['vertical']
    if result.get('authority_unchanged') is False:
        reasons['authority_unchanged']=False
    return reasons or {'unclassified_assembly_failure':True}
