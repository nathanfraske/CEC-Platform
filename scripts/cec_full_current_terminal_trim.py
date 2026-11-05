"""Trim a literal source-current dead tip back to its retained native tee.

A trace endpoint can overshoot an interior contact while remaining connected,
so an open count and degree-two bend census cannot detect it. This owner only
shortens an exact straight source edge to an existing perpendicular centreline
contact. It adds no copper outside that source capsule, retains every native
adjacency/contact-web witness, and independently replays the original complete
current contract. No current sharing, pad/barrel/pour move or release follows.
"""
from collections import Counter,defaultdict
import json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_full_current_corner_finish as material
import cec_native_track_ports as ports
import cec_precision_route as precision
import cec_rated_supply_corner_finish as signatures
from cec_native_items import discard_items


def _settings(allow_locked_source):
    if type(allow_locked_source) is not bool:
        raise ValueError('explicit_terminal_trim_lock_context_required')


def _geometry(board,source,allow_locked_source,deadline):
    _settings(allow_locked_source)
    if Path(board.GetFileName()).resolve()!=Path(source).resolve():
        raise ValueError('literal_saved_terminal_trim_source_required')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(tracks)+len(pads)>16384:raise ValueError('terminal_trim_native_inventory_bound')
    if len({force._uid(t) for t in tracks})!=len(tracks):raise ValueError('duplicate_terminal_trim_track_identity')
    grouped=defaultdict(list)
    for t in tracks:
        if t.GetClass()=='PCB_TRACK':grouped[str(t.GetNetname()),int(t.GetLayer())].append(t)
    rows=[]
    for (net,face),edges in sorted(grouped.items()):
        if not net or net=='GND':continue
        contacts=[t for t in tracks if t.GetNetname()==net and t.IsOnLayer(face)]
        contacts += [p for p in pads if p.GetNetname()==net and p.IsOnLayer(face)]
        contacts += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net and z.IsOnLayer(face)]
        for t in edges:
            if time.monotonic()>=deadline:raise ValueError('terminal_trim_geometry_deadline')
            if (t.GetParentGroup() or t.HasSolderMask() or t.IsLocked() and not allow_locked_source or
                    not 0<t.GetLength()<=32000000 or not 0<t.GetWidth()<=10000000):continue
            a,b=map(tuple,(t.GetStart(),t.GetEnd()));d=(b[0]-a[0],b[1]-a[1])
            if d[0] and d[1] and abs(d[0])!=abs(d[1]):continue
            taps=defaultdict(set)
            for peer in edges:
                if peer is t or peer.GetWidth()!=t.GetWidth():continue
                u,v=map(tuple,(peer.GetStart(),peer.GetEnd()));pv=(v[0]-u[0],v[1]-u[1])
                if not any(pv) or d[0]*pv[0]+d[1]*pv[1]!=0:continue
                determinant=d[0]*pv[1]-d[1]*pv[0]
                numerator=(u[0]-a[0])*pv[1]-(u[1]-a[1])*pv[0]
                if not determinant:continue
                nx,ny=a[0]*determinant+d[0]*numerator,a[1]*determinant+d[1]*numerator
                if nx%determinant or ny%determinant:continue
                at=(nx//determinant,ny//determinant)
                if at not in (a,b) and ports.on_centerline(t,at) and ports.on_centerline(peer,at):
                    taps[at].add(force._uid(peer))
            for tip,far in ((a,b),(b,a)):
                options=sorted(taps,key=lambda q:(math.dist(q,tip),q))
                if not options:continue
                at=options[0];length=math.dist(tip,at)
                # Scheduling floor only (2 um); never a relaxed electrical
                # width/clearance. Real visible material and exact source
                # contact/current receiving remain mandatory, including for
                # a short tip already sitting inside its retained tap.
                if not 2000<=length<=min(2000000,.4*t.GetLength()):continue
                point=pcbnew.VECTOR2I(*tip);free=True
                for other in contacts:
                    if other is t or force._uid(other) in taps[at]:continue
                    if time.monotonic()>=deadline:raise ValueError('terminal_trim_geometry_deadline')
                    if other.GetClass()=='ZONE':
                        if not other.IsFilled() or not other.HasFilledPolysForLayer(face):
                            if other.GetBoundingBox().Contains(point):free=False;break
                            continue
                        shape=other.GetFilledPolysList(face)
                    else:shape=other.GetEffectiveShape(face)
                    if shape.Collide(point,1):free=False;break
                if free:rows.append(dict(net=net,layer=face,width_nm=int(t.GetWidth()),source_track_uuid=force._uid(t),
                    free_end_nm=list(tip),retained_end_nm=list(far),junction_nm=list(at),retained_tap_uuids=sorted(taps[at])))
                if len(rows)>128:raise ValueError('terminal_trim_candidate_bound')
    return sorted(rows,key=lambda r:(-math.dist(r['free_end_nm'],r['junction_nm']),r['net'],r['layer'],r['source_track_uuid']))


def _replacement(old,request):
    new=old.Duplicate();point=pcbnew.VECTOR2I(*request['junction_nm'])
    if tuple(old.GetStart())==tuple(request['free_end_nm']):new.SetStart(point)
    elif tuple(old.GetEnd())==tuple(request['free_end_nm']):new.SetEnd(point)
    else:raise ValueError('literal_terminal_trim_source_endpoint_required')
    return new


def _contacts(board,old,new,request,deadline):
    face=request['layer'];width=request['width_nm'];rows=[]
    old_shape=old.GetEffectiveShape(face);new_shape=new.GetEffectiveShape(face)
    peeled=old.Duplicate();peeled.SetStart(pcbnew.VECTOR2I(*request['junction_nm']));peeled.SetEnd(pcbnew.VECTOR2I(*request['free_end_nm']))
    peeled_shape=peeled.GetEffectiveShape(face)
    items=[*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads()),*board.Zones()]
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('terminal_trim_contact_deadline')
        if force._uid(item)==force._uid(old) or item.GetNetname()!=request['net'] or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE' and item.GetIsRuleArea():continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                if item.GetBoundingBox().Intersects(old.GetBoundingBox()):raise ValueError('terminal_trim_nearby_fill_unknown')
                continue
            shape=item.GetFilledPolysList(face)
        else:shape=item.GetEffectiveShape(face)
        if not shape.Collide(old_shape,0):continue
        if not shape.Collide(new_shape,0):raise ValueError('terminal_trim_would_lose_native_adjacency')
        uid=force._uid(item)
        if uid in request['retained_tap_uuids']:
            # Exact native straight capsules are a segment Minkowski-summed
            # with the same round width kernel. An exact shared centreline
            # site therefore retains a FULL source-width disk, independent
            # of tessellation angle, erosion cost or a 1-nm polygon artifact.
            # Both same-width source strokes already bound the old contact
            # witness by this diameter. No guessed manufacturing margin.
            if (item.GetClass()!='PCB_TRACK' or item.GetWidth()!=width or
                    not ports.on_centerline(item,request['junction_nm']) or
                    not ports.on_centerline(old,request['junction_nm']) or
                    not ports.on_centerline(new,request['junction_nm'])):
                raise ValueError('terminal_trim_exact_shared_native_kernel_required')
            rows.append(dict(uuid=uid,kind=item.GetClass(),method='exact_same_width_native_capsule_kernel',
                unchanged_native_contact_disk_diameter_nm=width))
        else:
            # Actual removed material is a subset of this entire suffix
            # capsule. A disjoint retained contact is literally unchanged;
            # a side contact on it needs another owner, not a tolerance.
            if not shape.Collide(peeled_shape,1):
                rows.append(dict(uuid=uid,kind=item.GetClass(),method='peeled_native_capsule_disjoint',
                    complete_source_contact_material_unchanged=True))
            elif item.GetClass()=='PCB_TRACK' and item.GetWidth()>0:
                # For two native capsules, the largest inscribed common
                # disk radius is min(r1,r2,(r1+r2-distance(axes))/2).
                # Erosion distributes over intersection, and each eroded
                # capsule has the SAME axis and a reduced round kernel.
                # Exact axis-distance equality therefore preserves that
                # source contact-web witness without expensive polygons.
                args=tuple(item.GetStart()),tuple(item.GetEnd())
                first=ports.segment_distance_squared(tuple(old.GetStart()),tuple(old.GetEnd()),*args)
                last=ports.segment_distance_squared(tuple(new.GetStart()),tuple(new.GetEnd()),*args)
                if first!=last or 4*first>=(width+item.GetWidth())**2:
                    raise ValueError('terminal_trim_would_shrink_exact_native_capsule_contact_web:'+uid)
                rows.append(dict(uuid=uid,kind=item.GetClass(),method='exact_capsule_axis_distance_preserved',
                    unchanged_axis_distance_squared_nm=dict(numerator=first.numerator,denominator=first.denominator),
                    unchanged_source_width_nm=width,unchanged_retained_width_nm=int(item.GetWidth()),
                    inscribed_contact_disk_radius_exactly_preserved=True))
            else:raise ValueError('terminal_trim_peeled_suffix_has_other_native_contact:'+uid)
    if not set(request['retained_tap_uuids'])<={r['uuid'] for r in rows}:
        raise ValueError('terminal_trim_actual_tap_contact_missing')
    return rows


def _proposal(board,source,request,board_hint,deadline,model=None):
    old=next(t for t in board.GetTracks() if force._uid(t)==request['source_track_uuid'])
    if request['net'] in {n for pair in precision.derive_coupled_pairs(str(source),board=board) for n in (pair['p'],pair['n'])}:
        raise ValueError('declared_pair_contact_has_no_planar_current_trim_authority')
    if model is None:model=full._model(board,source,request['net'],board_hint)
    floor=full._source_width_floor(board,source,model[2],request['layer'])
    if old.GetWidth()<floor:raise ValueError('source_terminal_trace_is_not_full_current_width')
    keepers=material._retained_corner_keepers(board,dict(net=request['net'],layer=request['layer'],at_nm=request['free_end_nm']),old,deadline)
    if keepers:raise ValueError('terminal_trim_requires_composed_retained_pour_owner')
    new=_replacement(old,request)
    contacts=_contacts(board,old,new,request,deadline)
    visible=material._visible_removed(board,[old],[new],{force._uid(old)},deadline=deadline)
    return dict(request=json.loads(json.dumps(request)),full_current_floor_nm=floor,
        unchanged_source_current_model=json.loads(json.dumps(model)),native_contacts=contacts,
        actual_visible_native_material_removed=visible,source_capsule_subset_by_exact_collinear_end_trim=True)


def discover(board,source,*,board_hint,allow_locked_source=False):
    if type(board_hint) is not str or not board_hint:raise ValueError('explicit_terminal_trim_board_context_required')
    deadline=time.monotonic()+10.;rows=_geometry(board,source,allow_locked_source,deadline)
    models={};good=[];refusals=[]
    for request in rows:
        try:
            if time.monotonic()>=deadline:raise ValueError('terminal_trim_discovery_deadline')
            net=request['net']
            if net not in models:
                try:models[net]=full._model(board,source,net,board_hint)
                except ValueError as exc:models[net]=str(exc)
            if type(models[net]) is str:raise ValueError(models[net])
            _proposal(board,source,request,board_hint,deadline,models[net]);good.append(request)
        except ValueError as exc:refusals.append(dict(request=request,reason=str(exc)))
    if time.monotonic()>=deadline:raise ValueError('terminal_trim_complete_discovery_deadline')
    return dict(complete=True,requests=good,geometric_source_candidates=len(rows),refusals=refusals,
        source_current_budgets_or_roles_changed=False,release_authority=False)


def plan(board,source,request,*,board_hint,allow_locked_source=False):
    if type(board_hint) is not str or not board_hint:raise ValueError('explicit_terminal_trim_board_context_required')
    deadline=time.monotonic()+10.
    if request not in _geometry(board,source,allow_locked_source,deadline):
        raise ValueError('literal_native_source_terminal_trim_required')
    proposal=_proposal(board,source,request,board_hint,deadline)
    current=full.plan(board,source,board_hint=board_hint,retired_track_uuids=[request['source_track_uuid']],
        max_source_track_mm=32.,max_source_cut_mm=48.)
    if time.monotonic()>=deadline:raise ValueError('terminal_trim_plan_deadline')
    return dict(schema=1,source_sha256=force._hash(Path(source)),source_binding=binding._source_binding(board),
        request=json.loads(json.dumps(request)),allow_locked_source=allow_locked_source,
        native_proposal=proposal,full_current_proposal=json.loads(json.dumps(current)),release_authority=False)


def materialize(board,source,proposal,*,board_hint):
    if plan(board,source,proposal['request'],board_hint=board_hint,allow_locked_source=proposal['allow_locked_source'])!=proposal:
        raise ValueError('stale_or_forged_terminal_trim_plan')
    old=next(t for t in board.GetTracks() if force._uid(t)==proposal['request']['source_track_uuid'])
    new=_replacement(old,proposal['request']);new.m_Uuid.Clone(pcbnew.KIID());board.Add(new)
    discard_items(board,[old]);additive._ground_refill(board)
    return dict(retired_track_uuids=[proposal['request']['source_track_uuid']],added_native_uuids=[force._uid(new)],
        new_vias=0,new_holes=0,release_authority=False)


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False)
    try:
        deadline=time.monotonic()+10.
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)];board=pcbnew.LoadBoard(str(source))
        if plan(board,source,proposal['request'],board_hint=board_hint,allow_locked_source=proposal['allow_locked_source'])!=proposal:
            raise ValueError('saved_source_terminal_trim_plan_changed')
        if force._sidecars(source)!=force._sidecars(candidate) or force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]:
            raise ValueError('terminal_trim_source_metadata_or_sidecars_changed')
        _,old=additive._nodes(source);got_root,got=additive._nodes(candidate);retired=set(old)-set(got);added=set(got)-set(old)
        if retired!={proposal['request']['source_track_uuid']} or len(added)!=1:
            raise ValueError('exact_one_source_terminal_trim_required')
        with tempfile.TemporaryDirectory(prefix='cec-current-terminal-trim-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');expected=pcbnew.LoadBoard(str(path))
            fresh=plan(expected,path,proposal['request'],board_hint=board_hint,allow_locked_source=proposal['allow_locked_source'])
            materialize(expected,path,fresh,board_hint=board_hint);field._save_field_snapshot(expected,path)
            want_root,want=additive._nodes(path);new_ids=set(want)-set(old)
            if (signatures._header(want_root,want)!=signatures._header(got_root,got) or set(want)&set(old)!=set(got)&set(old)
                    or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in set(want)&set(old))
                    or Counter(signatures._signature(want[u]) for u in new_ids)!=Counter(signatures._signature(got[u]) for u in added)):
                raise ValueError('independent_saved_terminal_trim_replay_differs')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('terminal_trim_saved_replay_deadline')
        typed=full.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),timeout_s=remaining,
            max_source_track_mm=32.,max_source_cut_mm=48.)
        if not typed['ok'] or not typed['complete']:raise ValueError('full_current_terminal_trim_receiving_refused:'+str(typed['errors']))
        saved=math.dist(proposal['request']['free_end_nm'],proposal['request']['junction_nm'])/1e6
        if time.monotonic()>=deadline:raise ValueError('terminal_trim_saved_replay_deadline')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('terminal_trim_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),
            net=proposal['request']['net'],saved_trace_length_mm=saved,independent_full_current_receiving=typed,
            source_width_face_current_and_native_contacts_preserved=True,source_capsule_subset_rederived=True,
            new_vias=0,new_holes=0,pads_moved=0,power_pours_changed=False)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
